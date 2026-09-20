"""`fold()` — the pure step from one neutral signal to one column delta (T11).

`(signal, prior, received_at) -> FoldResult`. No clock, no I/O, no globals: the
time comes in as a parameter because **no payload carries one** (C8), and that
is exactly what makes T12's replay of 429 captured events byte-deterministic.

`fold()` is a dict lookup into Table B plus the three cross-cutting rules that
belong to *every* kind:

1. `last_event_at = received_at`, always — the receiver stamps it.
2. registration on an unknown session is the **store's** job, keyed on the
   absence of a row rather than on any kind (D47): a session that was already
   running when hooks were installed never announces itself again.
3. the inferred `needs_you` clear (G5): nothing marks a permission prompt
   resolved, so the next sign of activity clears it. Which kinds count as
   activity is Table B's own `clears_needs_you` column, applied here once
   instead of inside eight rules.

`FoldDelta`, `FoldResult`, `SessionSnapshot`, `IdentitySets` and `CLEARED` are
re-exported, not defined: `core/` owns them (T1, F9) so the store and the
registry can take the types without depending on the fold — and so the hookless
lane returns literally the same `FoldResult` this one does (BLOCKER T7b-1).
"""

from __future__ import annotations

from dataclasses import fields, replace

from shepherd.core.fold_types import (
    CLEARED,
    FoldDelta,
    FoldResult,
    IdentitySets,
    SessionSnapshot,
)
from shepherd.core.signals import Signal
from shepherd.core.states import SessionState
from shepherd.core.stream import StreamEvent
from shepherd.signals.rules import RULE_BY_KIND, event_payload, sets_of

__all__ = [
    "CLEARED",
    "FoldDelta",
    "FoldResult",
    "IdentitySets",
    "SessionSnapshot",
    "fold",
]


def _was_waiting(prior: SessionSnapshot | None) -> bool:
    if prior is None:
        return False
    return prior.state is SessionState.NEEDS_YOU or bool(prior.needs_you_reason)


def fold(signal: Signal, prior: SessionSnapshot | None, received_at: str) -> FoldResult:
    """One signal folded into one delta. Pure, total, and never raises."""
    rule = RULE_BY_KIND[signal.kind]
    delta = rule.delta_fn(signal, prior)

    delta = replace(delta, last_event_at=received_at)
    if delta.state is SessionState.STOPPED:
        delta = replace(delta, ended_at=received_at)
    if rule.clears_needs_you and _was_waiting(prior):
        delta = replace(
            delta,
            needs_you_reason=CLEARED,
            state=delta.state if delta.state is not None else SessionState.RUNNING,
        )

    # The identity sets go out on the delta, through the same one writer as the
    # counts computed from them (D37): before they had a column, a `controld`
    # restart reset every session's pairing (BLOCKER-T6-1, T11-4). They are
    # whole values, so they are always set — an empty set is a real clear.
    sets = rule.sets_fn(signal, prior)
    delta = replace(
        delta,
        live_subagent_ids=sets.live_subagent_ids,
        created_task_ids=sets.created_task_ids,
        completed_task_ids=sets.completed_task_ids,
    )

    session_id = prior.session_id if prior is not None else None
    events = tuple(
        StreamEvent(
            kind=name,
            session_id=session_id,
            payload=event_payload(signal),
            occurred_at=received_at,
        )
        for name in rule.emits
    )
    return FoldResult(
        delta=delta,
        events=events,
        anomalies=rule.anomaly_fn(signal, prior),
        sets=sets,
    )


#: Every field of `FoldDelta`, **read from the dataclass** rather than listed.
#: A list beside a dataclass is a list that falls behind it — which is exactly
#: how seven fields went missing here (see `advance`).
DELTA_FIELDS: frozenset[str] = frozenset(field.name for field in fields(FoldDelta))

#: The three fields `advance` takes from `result.sets` rather than from the
#: delta. They are the fold's identity sets: the delta carries them so they
#: survive a restart through the store, but the pure lane already has the
#: authoritative value in hand, so reading it twice from two places is how the
#: two copies would drift. `test_advance_carries_every_delta_field` knows about
#: this split and checks each half at its own source.
SET_FIELDS: frozenset[str] = frozenset(
    {"live_subagent_ids", "created_task_ids", "completed_task_ids"}
)

#: `needs_you_reason` is the one field whose `CLEARED` sentinel becomes `None`
#: on a snapshot: it is a *reason*, and an empty reason renders as a stale one.
#: The stamps keep `CLEARED_STAMP` verbatim — `fold_types.SessionSnapshot` says
#: why, and every reader of them tests truth rather than `is None`.


def advance(prior: SessionSnapshot, result: FoldResult) -> SessionSnapshot:
    """`prior` with the delta and the identity sets applied.

    The sets now have a column (BLOCKER-T6-1 is closed), so at runtime a caller
    re-reads `Store.snapshot()`. This stays for the pure lane: T12's replay
    folds 429 captured events with no store at all.

    **Totality is the property, and it is enforced, not remembered.** This
    function once listed thirteen of `FoldDelta`'s twenty fields and dropped
    seven — `title`, `title_source`, `auto_compact_at`, `quota_notice_at`,
    `pid`, `proc_start`, `observed_at` — so every pure in-memory replay lost
    them after the first fold, and `context_exhausted` could not be reached at
    all in a lane with no store (BLOCKER T17-1). Nothing went red, because a
    hand-maintained list that mirrors a dataclass is not checked by anything
    that knows the dataclass. `store.DELTA_COLUMNS` had this guard already
    (`test_delta_fields_are_all_known_to_the_store`); the pure lane did not.
    `test_advance_carries_every_delta_field` is now that guard, so the next
    field added to `FoldDelta` fails here until it is carried.
    """
    delta = result.delta
    carried = {
        field: value
        for field in DELTA_FIELDS - SET_FIELDS
        if (value := getattr(delta, field)) is not None
    }
    if (reason := carried.get("needs_you_reason")) is not None:
        carried["needs_you_reason"] = None if reason == CLEARED else reason
    return replace(
        prior,
        **carried,
        live_subagent_ids=result.sets.live_subagent_ids,
        created_task_ids=result.sets.created_task_ids,
        completed_task_ids=result.sets.completed_task_ids,
    )


def initial_sets() -> IdentitySets:
    """The sets a session starts with, for a caller with no prior at all."""
    return sets_of(None)
