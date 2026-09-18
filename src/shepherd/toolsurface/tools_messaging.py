"""T18's message half: the three capabilities that carry words to a session.

Split out of `tools_m3.py` rather than raising its size cap — this repo has
taken that trade eight times before today and been right each time, and the
halves are three jobs, not one: **start and stop** a session (`tools_m3.py`),
**type at its terminal** (`tools_terminal.py`), and **say something to it and
read the answer**, which is this file. All three are size-asserted, so a split
cannot hide growth.

`toolsurface/` is L4 and composes: the queue, the clear-and-re-read, the 96-key
write policy and the headless fork are all `orchestration/`'s, called and never
restated. What this file adds is §13's projection and one property Task 18
words directly — **the result names the decision**. A refusal rendered as a
generic failure is how `REFUSE_DIALOG` becomes invisible, and `REFUSE_DIALOG` is
the policy declining to type over a screen that is asking a human a question.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.mailbox import MailboxOrigin
from shepherd.core.runner import RunnerRefusal, WriteDecision
from shepherd.orchestration.ask import AskResult, ForkRunner, ask_session
from shepherd.orchestration.mailbox import Delivery, deliver_now, queue_message
from shepherd.orchestration.write_policy import refusal_text
from shepherd.runner.base import Runner
from shepherd.store.db import Store
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
    arg_optional_str,
    arg_str,
)

__all__ = [
    "build_messaging_tools",
    "list_mailbox",
    "project_ask",
    "project_delivery",
    "send",
]

Clock = Callable[[], str]

#: What `origin` defaults to. A capability reached through `invoke()` with no
#: stated origin is somebody at a surface asking for it.
DEFAULT_ORIGIN = MailboxOrigin.USER_UI


def _origin(args: ToolArgs) -> MailboxOrigin:
    """Who says they queued this, from migration 003's own closed set.

    Three audiences may call `send_to_session` (§11), and the handler signature
    carries arguments and **not** a `CallerContext` — so the caller labels the
    row rather than the surface guessing `user_ui` for a master. It is a
    **label, not authority**: nothing is permitted or refused on the strength of
    it, and M4's gate is where a claimed identity is reconciled with the
    audience `invoke()` already knows (D38). Refused rather than coerced, because
    an unrecognised origin silently becoming `user_ui` is a row that lies.
    """
    value = args.get("origin")
    if value is None:
        return DEFAULT_ORIGIN
    if not isinstance(value, str) or value not in set(MailboxOrigin):
        raise ToolArgumentRefused(
            f"origin {value!r} is not one of {sorted(str(one.value) for one in MailboxOrigin)}"
        )
    return MailboxOrigin(value)

_EVERY_AUDIENCE = frozenset({Audience.MASTER, Audience.SESSION, Audience.HUMAN})
_MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})


def project_delivery(delivery: Delivery, message_id: str) -> dict[str, object]:
    """One attempt's outcome, with the decision as a **value** beside its text.

    `decision` is `None` when the mailbox took none at all — an empty queue, or
    the attached-client precondition, which the router decided is not a seventh
    member of the write policy's six (BLOCKER-T1-3). `reason` is what went on
    the row, which for that precondition is the anomaly's own name rather than
    the nearest `WriteDecision`: recording a decision there would lose the very
    reason the column exists for (T14, principle 5).
    """
    decision = delivery.decision
    return {
        "message_id": message_id,
        "queued": True,
        "decision": None if decision is None else str(decision.value),
        "decision_text": None if decision is None else refusal_text(decision),
        "reason": delivery.reason,
        "delivered": delivery.delivered,
        "deferred": delivery.deferred,
    }


def project_ask(result: AskResult) -> dict[str, object]:
    """`method` has no absent value, so a downgrade to the mailbox is never
    silent — that is principle 5 at `AskResult`'s own return type, kept here."""
    return {
        "text": result.text,
        "method": result.method,
        "from_fork_of": result.from_fork_of,
        "duration_ms": result.duration_ms,
        "refusal": result.refusal,
    }


def send(*, store: Store, runner: Runner, now: Clock, args: ToolArgs) -> dict[str, object]:
    """Queue first, then try to deliver. The queue is what makes a refusal safe.

    D45: a message the policy will not send **now** is still a message, and it
    stays on the row with the reason on it rather than being lost with a failed
    call. So the row is written before the pane is looked at, and a caller that
    retries under the same `idempotency_key` gets its own first message back
    instead of a second id it would believe in.
    """
    session_id = arg_str(args, "session_id")
    row = store.get_owned_session(session_id)
    if row is None:
        # There is no row to queue against — the mailbox is keyed on one, and a
        # queue verb that invented the row would make a typo durable. A value,
        # never a raise: `invoke()` would flatten a raise into "request failed",
        # where a human cannot tell a mistyped id from a crashed daemon.
        return {
            "message_id": None,
            "queued": False,
            "decision": None,
            "decision_text": None,
            "reason": f"{session_id}: no such session",
            "delivered": 0,
            "deferred": 0,
        }
    message = queue_message(
        store=store,
        session_id=session_id,
        body=arg_str(args, "body"),
        origin=_origin(args),
        idempotency_key=arg_str(args, "idempotency_key"),
        now=now,
    )
    handle = row.runner_handle
    if handle is None:
        # A row with no pane of ours — attached, or T12's orphan. The message
        # stays queued and says so with the policy's own member, not with a
        # bespoke string a page cannot branch on.
        return project_delivery(
            Delivery(
                decision=WriteDecision.REFUSE_NO_PTY,
                reason=WriteDecision.REFUSE_NO_PTY.value,
                delivered=0,
                deferred=1,
            ),
            message.id,
        )
    try:
        delivery = deliver_now(
            store=store,
            runner=runner,
            handle=handle,
            session_id=session_id,
            state=row.state,
            ownership=row.ownership,
            now=now,
        )
    except RunnerRefusal as refusal:
        return project_delivery(
            Delivery(decision=None, reason=refusal.reason, delivered=0, deferred=1), message.id
        )
    return project_delivery(delivery, message.id)


def list_mailbox(*, store: Store, session_id: str | None) -> dict[str, object]:
    """Pending, delivered, deferred — and `last_refusal`, which is the field that
    says why a queue that is not moving is not moving (T14's column)."""
    counts = store.mailbox_counts()
    pending = store.pending_for(session_id) if session_id is not None else []
    return {
        "session_id": session_id,
        "pending": counts.pending,
        "delivered": counts.delivered,
        "deferred": counts.deferred,
        "last_refusal": next(
            (one.last_refusal for one in reversed(pending) if one.last_refusal is not None),
            None,
        ),
        "messages": [
            {
                "id": one.id,
                "body": one.body,
                "origin": str(one.origin.value),
                "queued_at": one.queued_at,
                "delivery_attempts": one.delivery_attempts,
                "last_refusal": one.last_refusal,
            }
            for one in pending
        ],
    }


def build_messaging_tools(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    run_fork: ForkRunner,
    binary: str,
    projects_root: Path,
    can_fork: bool,
) -> tuple[ToolDef, ...]:
    """The three, with their dependencies closed over (D32)."""
    return (
        ToolDef(
            name="send_to_session",
            description="Queue a message and try to deliver it; the result names the decision.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "body": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                    "origin": {"type": "string"},
                },
                "required": ["session_id", "body", "idempotency_key"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: send(store=store, runner=runner, now=now, args=args),
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="ask_session",
            description="D13's synchronous question, answered by a headless fork (DP7).",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["session_id", "question"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: project_ask(
                ask_session(
                    store=store,
                    run_fork=run_fork,
                    now=now,
                    binary=binary,
                    projects_root=projects_root,
                    can_fork=can_fork,
                    session_id=arg_str(args, "session_id"),
                    question=arg_str(args, "question"),
                )
            ),
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="list_mailbox",
            description="Pending, delivered, deferred — and why a queue is not moving.",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_mailbox(
                store=store, session_id=arg_optional_str(args, "session_id")
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
    )
