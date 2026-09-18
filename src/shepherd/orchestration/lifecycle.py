"""T12 — an owned session's end: the kill record, the exit code, rebinding, interrupt.

Five operations over `Store` and the `Runner` seam, clock and publisher injected.
Nothing here opens a connection, starts a process or spells a multiplexer word:
every tmux fact arrives as a `RunnerHandle` or a `PaneRef`.

**A kill is recorded before it is issued (G-M3-9, E-M3-17).** `kill-session`
removes the listing row and `#{pane_dead_status}` with it
(`15-list-sessions-after-kill.txt`), and whether a slow session-ending hook
survives the kill is unverified. So: read the status, write the record, *then*
kill. A crash in between leaves the record — what a later pass can act on —
rather than an orphan nobody knows about. The verdict is written **from the
recorded action**, and a kill the row had no ending for is counted
`KILL_WITHOUT_SESSION_END`.

**Not a second stop writer.** `apply_stop_verdict` still holds the only write of
the stop columns (its statement is not quoted here: the rule guarding it scans
raw source text). This module calls that verb and classifies nothing — a declared
kill is an action taken, not evidence read — and leaves an already-ended row be.

**`/resume` rebinds, it does not stop (C14)**: the row keeps its identity *and
its stop history* and changes one column. `rebind_engine_session_id` is C14's
move, `bind_engine_session_id` is the conditional write for an **unbound** row
and a no-op here — one verb could not express both (blocker T4-1).

**Interrupting is `Escape`, terminating is `kill-session`, and no signal ever
reaches a session** (D43, clause 8); an interrupted turn emits no `Stop` (A13).

**The reconcile is the orphan reaper** for the pane DP5's detached launch makes
durable: a real engine whose row has `runner_handle IS NULL`. The name is
`session_name(session_id)` by construction, which is why re-deriving the handle
is possible at all. A pane with **no** row is counted and shown, never killed —
one Shepherd cannot account for is a fact for a human, not a process to destroy
(principle 5, K6). `runner_name` and `socket` are **required injections the plan's
`Produces` does not list**: a `PaneRef` says nothing about which driver saw it and
only `start` builds a handle (T8-1's situation, T6-2's shape; reported up).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.fold_types import FoldDelta
from shepherd.core.runner import ProcState, RunnerHandle, RunnerRefusal, RunnerRefusal
from shepherd.core.stops import DecidedBy, StopReason, Verdict
from shepherd.core.stream import StreamEvent
from shepherd.runner.base import PaneRef, Runner
from shepherd.runner.tmux_cmd import session_name
from shepherd.signals.stop_rules import BUCKET_OF, default_actions
from shepherd.store.db import Store

__all__ = [
    "INTERRUPT_EVENT",
    "KILL_EVENT",
    "KILL_RECORD_PREFIX",
    "ReconcileCounts",
    "interrupt_session",
    "observe_exit",
    "rebind",
    "reconcile_owned_panes",
    "record_and_terminate",
]

#: The durable record's key space, one key per session: written before the kill,
#: cleared once the kill is accounted for, so a process that dies in between
#: leaves evidence a later pass can read.
KILL_RECORD_PREFIX = "kill."

KILL_EVENT = "session.killed"
INTERRUPT_EVENT = "session.interrupted"
#: A declared kill's `why` says *who* ended the session, which is the whole
#: difference between `killed` and `crashed` on one exit status (E-M3-18); and
#: `1.0`/`DECLARED` because this is an action taken, not evidence read.
KILL_WHY = "Shepherd terminated this session; the kill was recorded before it was issued"
KILL_CONFIDENCE = 1.0


@dataclass(frozen=True)
class ReconcileCounts:
    """What one startup reconcile found. Three numbers, none inferred."""

    rebound: int
    orphaned: int
    intact: int


def observe_exit(*, runner: Runner, handle: RunnerHandle) -> ProcState:
    """One observation of the process behind the pane.

    For an **owned** session this carries a real `exit_code`: `0` (`/exit`), `1`
    (trust refused), `143` (SIGTERM) — the three `#{pane_dead_status}` values the
    listing capture holds. `exit_signal` is the driver's answer, always `None` on
    this evidence (empty even after SIGTERM: the engine handled it and exited
    143); the unknown is recorded, never inferred. Called **before** a kill:
    afterwards the row is gone with its status."""
    return runner.probe(handle)


def record_and_terminate(
    *,
    store: Store,
    runner: Runner,
    handle: RunnerHandle,
    session_id: str,
    now: Callable[[], str],
    publish: Callable[[StreamEvent], None],
) -> ProcState:
    """End one owned session, in the only order that survives a crash mid-way.

    Read the status, write the record, kill, write the verdict from the record.
    A failed kill's `RunnerRefusal` propagates — the session is still alive and a
    caller told "killed" would be told a false thing — and the record stays
    behind, which is the point of writing it first.
    """
    observed = observe_exit(runner=runner, handle=handle)
    recorded_at = now()
    record: dict[str, object] = {
        "session_id": session_id,
        "session_name": handle.session_name,
        "recorded_at": recorded_at,
        "exit_code": observed.exit_code,
        "exit_signal": observed.exit_signal,
    }
    store.set_app_state(f"{KILL_RECORD_PREFIX}{session_id}", record)

    runner.terminate(handle)

    row = store.get_owned_session(session_id)
    if row is None or row.ended_at is None:
        # G-M3-9: no session ending had arrived, so the verdict comes from the
        # record rather than from a hook that may never survive the kill.
        store.bump_anomaly(str(AnomalyKind.KILL_WITHOUT_SESSION_END.value))
        store.apply_stop_verdict(session_id, _killed(), recorded_at, observed.exit_code)
    store.set_app_state(f"{KILL_RECORD_PREFIX}{session_id}", None)
    publish(
        StreamEvent(
            kind=KILL_EVENT,
            session_id=session_id,
            occurred_at=recorded_at,
            payload={
                "exit_code": observed.exit_code,
                "exit_signal": observed.exit_signal,
                "recorded_at": recorded_at,
            },
        )
    )
    return observed


def _killed() -> Verdict:
    """The declared verdict, using M2's own bucket and action tables."""
    return Verdict(
        stop_reason=StopReason.KILLED,
        bucket=BUCKET_OF[StopReason.KILLED],
        why=KILL_WHY,
        confidence=KILL_CONFIDENCE,
        decided_by=DecidedBy.DECLARED,
        next_actions=default_actions(
            StopReason.KILLED, confidence=KILL_CONFIDENCE, missing=(), waiting_on=None
        ),
        waiting_on=None,
        missing=(),
    )


def interrupt_session(
    *,
    store: Store,
    runner: Runner,
    handle: RunnerHandle,
    session_id: str,
    now: Callable[[], str],
    publish: Callable[[StreamEvent], None],
) -> None:
    """`Escape` — what a user pressing Ctrl-C would do, and never a signal (D43).

    An interrupted turn emits **no `Stop`** (A13), so nothing here writes a
    state, an ending or a stop column: the session is left as it was and the pane
    poll decides. What is recorded is that something happened now — the mailbox's
    second delivery trigger (D45).
    """
    runner.interrupt(handle)
    store.apply_fold_delta(session_id, FoldDelta(last_event_at=now()))
    publish(
        StreamEvent(
            kind=INTERRUPT_EVENT,
            session_id=session_id,
            occurred_at=now(),
            payload={"session_name": handle.session_name},
        )
    )


def rebind(*, store: Store, session_id: str, new_engine_session_id: str) -> None:
    """C14: `/resume` moves the row's engine binding and ends nothing.

    Reached from `HookLane`'s `on_engine_session_rebound` parameter. Not a stop:
    the row keeps its identity and its stop history, where a delete-and-insert
    loses everything the row knows.
    """
    store.rebind_engine_session_id(session_id, new_engine_session_id)


def reconcile_owned_panes(
    *,
    store: Store,
    runner: Runner,
    now: Callable[[], str],
    runner_name: str,
    socket: str,
) -> ReconcileCounts:
    """At startup, once: adopt the handle-less, count the unaccounted.

    Rows whose pane is gone are left to the normal stop path. It runs before the
    first spawn asks §11's total cap, which counts **panes**: an orphan fills a
    slot whether or not anything knows of it, and enumerating afterwards leaves
    it invisible to the count that bounds it.
    """
    rebound = orphaned = intact = 0
    for ref in runner.list_owned_panes():
        if not _is_ours(ref):
            orphaned += 1
            store.bump_anomaly(str(AnomalyKind.ORPHANED_PANE.value))
            continue
        row = store.get_owned_session(ref.session_id)
        if row is None:
            orphaned += 1
            store.bump_anomaly(str(AnomalyKind.ORPHANED_PANE.value))
        elif row.runner_handle is None:
            store.set_runner_handle(
                ref.session_id,
                RunnerHandle(runner=runner_name, socket=socket, session_name=ref.session_name),
            )
            store.apply_fold_delta(ref.session_id, FoldDelta(last_event_at=now()))
            rebound += 1
        else:
            intact += 1
    return ReconcileCounts(rebound=rebound, orphaned=orphaned, intact=intact)


def _is_ours(ref: PaneRef) -> bool:
    """The name is deterministic: a pane not matching its own id is not ours."""
    try:
        return session_name(ref.session_id) == ref.session_name
    except RunnerRefusal:
        # An id tmux would silently re-address is not addressable, so the pane
        # cannot be adopted — it is counted, which is what a caller can act on.
        return False
