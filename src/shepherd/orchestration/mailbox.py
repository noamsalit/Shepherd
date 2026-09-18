"""T14 — one delivery path: coalesced, idempotent, never onto a draft (D12, D45).

Four verbs: `queue_message`, `coalesce`, `deliver_now` (the turn-boundary
trigger) and `sweep_pending` (the other trigger, the prompt-ready pane). The
store, clock and pane driver are injected, and the write policy is **asked**,
never re-decided here (`orchestration/write_policy.py`).

## The order, and why it is the order

Read the clients, read the pane, decide, and only then send. The clearing form
sends the captured key, **re-reads the pane**, and proceeds only if the box is
now empty. The re-read is the whole safety property: a clear that did not work
is indistinguishable from one that never ran, so without looking again the
clearing form would be worse than refusing (DP10).

## The attached-client precondition, and the part of it that is not closed

P3 captured a human at a second client typing while a programmatic writer
worked: the writer's submit sent **the human's keystrokes, inside Shepherd's own
prompt**. tmux serialises one write, not a sequence. So before anything is
pressed, this module asks how many clients are attached and defers while there
are any — before the clear, because clearing a box a human is typing in deletes
*their* text.

**This narrows the race; it does not close it.** A human can type between the
observation and the submit, and no arrangement of checks inside this design
closes that window — closing it needs an atomic read-modify-submit on the prompt,
which the driver does not offer. The deferral is counted
(`AnomalyKind.MAILBOX_CLIENT_ATTACHED`) so the residual stays visible rather than
hiding behind a check that looks total (principle 5, clause 15).

## D45's second trigger, as a key field rather than as a second policy

An interrupted turn emits no turn-ending hook at all (A13), so the row stays
`running` for ever — and `(running, prompt-ready)` is `QUEUE` in the policy
table, which is the stall D45 exists to prevent. `turn_state` resolves it
without touching the table: for an **owned** session a prompt-ready pane *is*
the turn boundary (D45: "owned sessions have a pty, so prompt-readiness is
observable"), so the key's first field is `stopped` — the value the turn-ending
rule would itself have written, and the one the table reads as "not mid-turn".
It cuts one way only: a mid-turn pane is queued whatever the row says.

## Two recorded deviations from the plan's `Produces`

**`deliver_now` returns a `Delivery`, not a bare `WriteDecision`**: two of its
outcomes are not decisions of the table — an empty mailbox, and the
attached-client deferral the router decided is *not* a new `WriteDecision`
member — and answering either with one of the six is a value a reader cannot act
on. The counts ride along because the sweep needs them, off `mark_delivered`'s
own rowcount. And **that deferral records the anomaly's value in
`last_refusal`**, a column documented as carrying a `WriteDecision`: recording
one of the six instead would lose the reason the column exists for.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.ids import new_ulid
from shepherd.core.mailbox import COALESCE_BULLET, MailboxCounts, MailboxMessage, MailboxOrigin
from shepherd.core.runner import PaneKind, PaneState, RunnerHandle, RunnerRefusal, WriteDecision
from shepherd.core.states import Ownership, SessionState
from shepherd.orchestration.write_policy import decide_write
from shepherd.runner.base import Runner
from shepherd.store.db import Store

__all__ = ["Delivery", "coalesce", "deliver_now", "queue_message", "sweep_pending", "turn_state"]

#: What joins the bullets: one note per line, in queue order.
COALESCE_SEPARATOR = "\n"


@dataclass(frozen=True)
class Delivery:
    """What one attempt did, and why.

    `decision` is `None` when none was taken at all — an empty mailbox, or the
    attached-client precondition, which is not one of the table's six. `reason`
    is what went on the row; `delivered` is the rows **this** attempt retired,
    off the store's own conditional write rather than counted here.
    """

    decision: WriteDecision | None
    reason: str | None
    delivered: int
    deferred: int


def coalesce(messages: Sequence[MailboxMessage]) -> str:
    """D12: five queued notes become one message with five bullets.

    A **single** note is delivered as itself: bulleting it invents a list of one
    for a reader that reads the bullet as structure. Nothing is deduplicated (two
    agents queueing the same sentence queued two notes) and the order is the
    queue's, which is the order the reader will act in.
    """
    if not messages:
        return ""
    if len(messages) == 1:
        return messages[0].body
    return COALESCE_SEPARATOR.join(f"{COALESCE_BULLET}{one.body}" for one in messages)


def turn_state(stored: SessionState, pane: PaneState, ownership: Ownership) -> SessionState:
    """The policy's first key field, answered by the pane where the pane knows.

    D45's second trigger, and the only place here where an observation speaks
    for the row. Owned and prompt-ready is the turn boundary; everything else is
    the stored state, unaltered.
    """
    if ownership is Ownership.OWNED and pane.kind is PaneKind.PROMPT_READY:
        return SessionState.STOPPED
    return stored


def queue_message(
    *,
    store: Store,
    session_id: str,
    body: str,
    origin: MailboxOrigin,
    idempotency_key: str,
    now: Callable[[], str],
) -> MailboxMessage:
    """Queue one note, or hand back the one already queued under its key.

    The returned row is the **stored** one, so a retrying caller gets its own
    first message back rather than a second id it would believe in.
    """
    return store.enqueue(
        MailboxMessage(
            id=new_ulid(),
            session_id=session_id,
            idempotency_key=idempotency_key,
            body=body,
            origin=origin,
            queued_at=now(),
            delivered_at=None,
            delivery_attempts=0,
            last_refusal=None,
        )
    )


def _defer(
    store: Store, ids: tuple[str, ...], reason: str, *, count: AnomalyKind | None
) -> Delivery:
    """Leave the rows pending, say why on each, and count the named member."""
    store.record_refusal(ids, reason)
    if count is not None:
        store.bump_anomaly(count.value)
    decision = WriteDecision(reason) if reason in set(WriteDecision) else None
    return Delivery(decision=decision, reason=reason, delivered=0, deferred=len(ids))


def deliver_now(
    *,
    store: Store,
    runner: Runner,
    handle: RunnerHandle,
    session_id: str,
    state: SessionState,
    ownership: Ownership,
    now: Callable[[], str],
) -> Delivery:
    """One attempt at one session's mailbox: sends once, or defers with a reason."""
    pending = store.pending_for(session_id)
    if not pending:
        return Delivery(decision=None, reason=None, delivered=0, deferred=0)
    ids = tuple(one.id for one in pending)

    if runner.attached_clients(handle) > 0:
        return _defer(
            store,
            ids,
            AnomalyKind.MAILBOX_CLIENT_ATTACHED.value,
            count=AnomalyKind.MAILBOX_CLIENT_ATTACHED,
        )

    pane = runner.pane(handle)
    decision = decide_write(turn_state(state, pane, ownership), pane, ownership)

    if decision is WriteDecision.CLEAR_THEN_SEND:
        runner.clear_input(handle)
        pane = runner.pane(handle)
        decision = decide_write(turn_state(state, pane, ownership), pane, ownership)
        if decision is WriteDecision.CLEAR_THEN_SEND:
            # The box is still drafted, so the clear did not work — which is
            # indistinguishable from never having tried, and is why the re-read
            # is here at all.
            return _defer(
                store,
                ids,
                WriteDecision.REFUSE_INPUT_NOT_EMPTY.value,
                count=AnomalyKind.MAILBOX_INPUT_NOT_EMPTY,
            )

    if decision is not WriteDecision.SEND_NOW:
        return _defer(store, ids, decision.value, count=None)

    runner.write(handle, coalesce(pending).encode("utf-8"))
    runner.write(handle, b"\r")
    moved = store.mark_delivered(ids, now())
    return Delivery(decision=decision, reason=None, delivered=moved, deferred=0)


def sweep_pending(
    *,
    store: Store,
    runner: Runner,
    now: Callable[[], str],
    handles: Mapping[str, RunnerHandle],
) -> MailboxCounts:
    """D45's second trigger, over the only sessions worth a look (RD4).

    `sessions_with_pending()` is one indexed query, so an empty mailbox costs
    **zero** driver calls — a sweep that polled the fleet would pay a capture per
    owned pane, per pass. `delivered`/`deferred` are what **this** sweep did.
    """
    delivered = deferred = 0
    for session_id in store.sessions_with_pending():
        handle = handles.get(session_id)
        row = store.get_owned_session(session_id)
        if handle is None or row is None:
            ids = tuple(one.id for one in store.pending_for(session_id))
            deferred += _defer(
                store, ids, WriteDecision.REFUSE_NO_PTY.value, count=None
            ).deferred
            continue
        try:
            outcome = deliver_now(
                store=store,
                runner=runner,
                handle=handle,
                session_id=session_id,
                state=row.state,
                ownership=row.ownership,
                now=now,
            )
        except RunnerRefusal as refusal:
            ids = tuple(one.id for one in store.pending_for(session_id))
            deferred += _defer(store, ids, str(refusal.reason), count=None).deferred
            continue
        delivered += outcome.delivered
        deferred += outcome.deferred
    return MailboxCounts(
        pending=store.mailbox_counts().pending, delivered=delivered, deferred=deferred
    )
