"""Table B (ADR-6, T11) — exactly one rule per `SignalKind`, and no engine words.

This module is the fold's whole vocabulary. It names no engine event, reads no
engine field, and never looks at `Signal.raw_kind`: a rule is selected by a dict
lookup on a typed `SignalKind`, which is what makes the table a **total function**
that `test_every_signal_kind_has_exactly_one_rule` can police.

Three rules are deliberately *not* here, because each is one rule for every
kind and modelling them per-kind is what produced revision 4's duplicate rows:
the receiver's `last_event_at` stamp (C8), registration on an unknown session
(D47 — a store operation keyed on *absence*, not a kind), and the inferred
`needs_you` clear (G5). `fold()` applies all three around this table; the only
trace of the third one here is the declared `clears_needs_you` column.

**Every rule carries an `evidence` string naming its `data-schemas.md` section.**
That is the project's first hard rule (no shape asserted without a capture) made
mechanical, and `test_every_fold_rule_cites_an_existing_section` fails the build
if a citation is empty or points at a section that does not exist.

**The identity sets are the fold's own state.** Each rule returns the sets it
would leave behind; `fold()` puts them on the delta and §7's four fold-state
columns persist them, so a `controld` restart no longer resets subagent pairing
(BLOCKER-T6-1/T11-4, closed). A rule that needs a count computes it from those
sets — never by ±1 on a column, which is how C10's captured internal stop
drives a naive counter negative.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.fold_types import (
    CLEARED_STAMP,
    EMPTY_SETS,
    FoldDelta,
    IdentitySets,
    SessionSnapshot,
)
from shepherd.core.signals import (
    HOOK_BLOCK_REFUSAL,
    PERMISSION_REFUSAL,
    Signal,
    SignalKind,
)
from shepherd.core.states import SessionState
from shepherd.signals.fields import (
    read_ask,
    read_changed_paths,
    read_failure_note,
    read_model,
    read_next_cwd,
    read_prompt,
    read_refusal,
    read_start_source,
    read_subagent_id,
    read_task_id,
)

#: C11: the latest prompt is polluted by injected notification XML with no field
#: distinguishing it, so the brief is the first prompt that is not one of these.
INJECTED_PROMPT_PREFIX = "<task-notification>"


def sets_of(prior: SessionSnapshot | None) -> IdentitySets:
    if prior is None:
        return EMPTY_SETS
    return IdentitySets(
        live_subagent_ids=prior.live_subagent_ids,
        created_task_ids=prior.created_task_ids,
        completed_task_ids=prior.completed_task_ids,
    )


DeltaFn = Callable[[Signal, SessionSnapshot | None], FoldDelta]
SetsFn = Callable[[Signal, SessionSnapshot | None], IdentitySets]
AnomalyFn = Callable[[Signal, SessionSnapshot | None], tuple[Anomaly, ...]]


@dataclass(frozen=True)
class FoldRule:
    """One row of Table B. `evidence` is the one position the boundary scan excludes."""

    kind: SignalKind
    delta_fn: DeltaFn
    sets_fn: SetsFn
    anomaly_fn: AnomalyFn
    clears_needs_you: bool
    emits: tuple[str, ...]
    evidence: str


# ----- shared shapes -------------------------------------------------------


def _nothing(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """Liveness only: `fold()` still stamps `last_event_at` on the way out."""
    return FoldDelta()


def _running(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return FoldDelta(state=SessionState.RUNNING)


def _keep_sets(signal: Signal, prior: SessionSnapshot | None) -> IdentitySets:
    return sets_of(prior)


def _no_anomaly(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    return ()


def _counted(signal: Signal, kind: AnomalyKind, detail: str) -> tuple[Anomaly, ...]:
    return (Anomaly(kind=kind, detail=detail, engine_session_id=signal.engine_session_id),)


# ----- the rows ------------------------------------------------------------


def _registered(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """The cwd the session reports. `repo_id` and `started_at` belong to the
    store lane: binding a directory to a repo runs git, and the fold is pure."""
    return FoldDelta(cwd=signal.cwd or None)


def _prompt_delta(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """C11: the FIRST real user prompt is the brief, and it is set once."""
    text = read_prompt(signal)
    if text is None or text.startswith(INJECTED_PROMPT_PREFIX):
        return FoldDelta()
    if prior is not None and prior.brief is not None:
        return FoldDelta()
    return FoldDelta(brief=text)


def _touched(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """C9: a changed path inside the session's own repo marks that repo touched.

    A path outside it names a repo this pure function cannot identify — resolving
    one runs git — so it is left alone rather than guessed at."""
    paths = read_changed_paths(signal)
    if not paths or prior is None or prior.repo_id is None or prior.cwd is None:
        return FoldDelta()
    root = prior.cwd.rstrip("/")
    inside = any(path == root or path.startswith(f"{root}/") for path in paths)
    if not inside:
        return FoldDelta()
    merged = tuple(sorted({*prior.repos_touched, prior.repo_id}))
    return FoldDelta() if merged == tuple(prior.repos_touched) else FoldDelta(repos_touched=merged)


def _tool_finished(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    touched = _touched(signal, prior)
    return FoldDelta(state=SessionState.RUNNING, repos_touched=touched.repos_touched)


def _needs_input(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return FoldDelta(state=SessionState.NEEDS_YOU, needs_you_reason=read_ask(signal))


def _subagent_started_sets(signal: Signal, prior: SessionSnapshot | None) -> IdentitySets:
    sets = sets_of(prior)
    identifier = read_subagent_id(signal)
    if identifier is None:
        return sets
    return IdentitySets(
        live_subagent_ids=sets.live_subagent_ids | {identifier},
        created_task_ids=sets.created_task_ids,
        completed_task_ids=sets.completed_task_ids,
    )


def _subagent_finished_sets(signal: Signal, prior: SessionSnapshot | None) -> IdentitySets:
    sets = sets_of(prior)
    identifier = read_subagent_id(signal)
    if identifier is None:
        return sets
    return IdentitySets(
        live_subagent_ids=sets.live_subagent_ids - {identifier},
        created_task_ids=sets.created_task_ids,
        completed_task_ids=sets.completed_task_ids,
    )


def _subagent_count(sets: IdentitySets) -> FoldDelta:
    """`len()` of a set of ids: clamped at zero by construction, never ±1 (C10)."""
    return FoldDelta(active_subagents=len(sets.live_subagent_ids))


def _subagent_started(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return _subagent_count(_subagent_started_sets(signal, prior))


def _subagent_finished(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return _subagent_count(_subagent_finished_sets(signal, prior))


def _unmatched_stop(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    """C10: an internal agent stops without ever having started (2 of 4 captures)."""
    identifier = read_subagent_id(signal)
    if identifier is not None and identifier in sets_of(prior).live_subagent_ids:
        return ()
    return _counted(signal, AnomalyKind.SUBAGENT_UNDERFLOW, identifier or "no paired id")


def _task_created_sets(signal: Signal, prior: SessionSnapshot | None) -> IdentitySets:
    sets = sets_of(prior)
    identifier = read_task_id(signal)
    if identifier is None:
        return sets
    return IdentitySets(
        live_subagent_ids=sets.live_subagent_ids,
        created_task_ids=sets.created_task_ids | {identifier},
        completed_task_ids=sets.completed_task_ids,
    )


def _task_completed_sets(signal: Signal, prior: SessionSnapshot | None) -> IdentitySets:
    sets = sets_of(prior)
    identifier = read_task_id(signal)
    if identifier is None:
        return sets
    return IdentitySets(
        live_subagent_ids=sets.live_subagent_ids,
        created_task_ids=sets.created_task_ids,
        completed_task_ids=sets.completed_task_ids | {identifier},
    )


def _task_created(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    sets = _task_created_sets(signal, prior)
    return FoldDelta(tasks_total=len(sets.created_task_ids))


def _task_completed(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """P11: done is the intersection, so it can never exceed the total."""
    sets = _task_completed_sets(signal, prior)
    return FoldDelta(tasks_done=len(sets.completed_task_ids & sets.created_task_ids))


def _cwd_changed(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """The new cwd. Re-binding it to a repo runs git, so the caller does that."""
    return FoldDelta(cwd=read_next_cwd(signal))


def _model_changed(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return FoldDelta(model=read_model(signal))


def _stopped(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """M1's row, unchanged: `ended_at` is stamped by `fold()`, and the
    compaction mark is deliberately **not** cleared — a session ending is the
    *death* §8's rule is bounded by (r3 BLOCKING 1)."""
    return FoldDelta(state=SessionState.STOPPED)


def _turn_stopped(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """A turn ended: the session survived the compaction, so the mark goes.
    One of two independent guards on the `context_exhausted` bound; the other
    is the adapter's stop map, which also requires a session ending. Either
    alone closes the benign capture (auto-compaction → progress → a turn
    ending), and both ship because §8 calls this row likely-a-bug territory.

    **The quota mark goes the same way (BLOCKER T10-2, option 1, applied by the
    decision-log owner).** Both cells are evidence about *the turn that just
    ended*, not about the session's history, and §8's wording for the quota
    column — "a quota notice arrived and **no turn followed**" — is a sequencing
    claim a mark with no clear cannot express: uncleared it says "a notice
    arrived, ever". A mark that is set and never cleared is a latch, and the
    first user to hit a real quota limit would have every later stop in that
    session read `quota_paused`, which D18 costs as a parked work item.
    Splitting `QUOTA_NOTICE` by payload *value* stays refused until a notice is
    actually captured (G-M2-1: the type only)."""
    return FoldDelta(
        state=SessionState.STOPPED,
        auto_compact_at=CLEARED_STAMP,
        quota_notice_at=CLEARED_STAMP,
    )


# The two marks D24 would otherwise discard. Each stamp is the signal's own
# `received_at` — what the receiver put on it (C8), and the same value `fold()`
# stamps `last_event_at` with; a rule cannot reach `fold()`'s parameter, and
# minting a second clock to avoid that is the defect P22 exists to prevent.


def _compact_started(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return FoldDelta(auto_compact_at=signal.received_at)


def _compact_finished(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    return FoldDelta(auto_compact_at=CLEARED_STAMP)


def _quota_notice(signal: Signal, prior: SessionSnapshot | None) -> FoldDelta:
    """G-M2-1: the notification **type** decided this; no payload field is read."""
    return FoldDelta(quota_notice_at=signal.received_at)


def _stop_failed_anomaly(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    return _counted(signal, AnomalyKind.STOP_FAILED, read_failure_note(signal) or "stop failed")


#: The neutral `refusal` value → the member that counts it. Total over
#: `REFUSAL_VALUES`; a value outside it is not named here and is not counted,
#: because naming it would be a guess (BLOCKER T11-2).
_REFUSAL_ANOMALIES: Mapping[str, AnomalyKind] = {
    HOOK_BLOCK_REFUSAL: AnomalyKind.TOOL_BLOCKED_BY_HOOK,
    PERMISSION_REFUSAL: AnomalyKind.TOOL_PERMISSION_REFUSED,
}


def _refused_batch(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    """Table B's "counts that a refusal happened" cell, now that a neutral field
    carries the fact and `AnomalyKind` has a member for it (BLOCKER T11-2)."""
    refusal = read_refusal(signal)
    kind = None if refusal is None else _REFUSAL_ANOMALIES.get(refusal)
    if kind is None:
        return ()
    return _counted(signal, kind, f"tool batch refused: {refusal}")


def _unmapped_notice(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    return _counted(signal, AnomalyKind.UNMAPPED_NOTICE, signal.raw_kind)


def _unknown_event(signal: Signal, prior: SessionSnapshot | None) -> tuple[Anomaly, ...]:
    return _counted(signal, AnomalyKind.UNKNOWN_EVENT_NAME, signal.raw_kind)


FOLD_RULES: tuple[FoldRule, ...] = (
    FoldRule(
        kind=SignalKind.SESSION_REGISTERED,
        delta_fn=_registered,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("session_registered",),
        evidence="§SessionStart",
    ),
    FoldRule(
        kind=SignalKind.PROMPT_SUBMITTED,
        delta_fn=_prompt_delta,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("prompt_submitted",),
        evidence="§UserPromptSubmit",
    ),
    FoldRule(
        kind=SignalKind.TURN_PROGRESS,
        delta_fn=_nothing,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=(),
        evidence="§MessageDisplay",
    ),
    FoldRule(
        kind=SignalKind.TOOL_STARTED,
        delta_fn=_running,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("tool_started",),
        evidence="§PreToolUse",
    ),
    FoldRule(
        kind=SignalKind.TOOL_FINISHED,
        delta_fn=_tool_finished,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("tool_finished",),
        evidence="§PostToolUse",
    ),
    FoldRule(
        kind=SignalKind.TOOL_FAILED,
        delta_fn=_running,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("tool_failed",),
        evidence="§PostToolUseFailure",
    ),
    FoldRule(
        kind=SignalKind.TOOL_BATCH_FINISHED,
        delta_fn=_running,
        sets_fn=_keep_sets,
        anomaly_fn=_refused_batch,
        clears_needs_you=True,
        emits=("tool_batch_finished",),
        evidence="§PostToolBatch",
    ),
    FoldRule(
        kind=SignalKind.NEEDS_INPUT,
        delta_fn=_needs_input,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("needs_input",),
        evidence="§PermissionRequest",
    ),
    FoldRule(
        kind=SignalKind.INPUT_RESOLVED,
        delta_fn=_nothing,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("input_resolved",),
        evidence="§PermissionDenied",
    ),
    FoldRule(
        kind=SignalKind.NOTICE_UNMAPPED,
        delta_fn=_nothing,
        sets_fn=_keep_sets,
        anomaly_fn=_unmapped_notice,
        clears_needs_you=False,
        emits=(),
        evidence="§Notification",
    ),
    FoldRule(
        kind=SignalKind.SUBAGENT_STARTED,
        delta_fn=_subagent_started,
        sets_fn=_subagent_started_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("subagent_started",),
        evidence="§SubagentStart",
    ),
    FoldRule(
        kind=SignalKind.SUBAGENT_FINISHED,
        delta_fn=_subagent_finished,
        sets_fn=_subagent_finished_sets,
        anomaly_fn=_unmatched_stop,
        clears_needs_you=False,
        emits=("subagent_finished",),
        evidence="§SubagentStop",
    ),
    FoldRule(
        kind=SignalKind.TASK_CREATED,
        delta_fn=_task_created,
        sets_fn=_task_created_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("task_created",),
        evidence="§TaskCreated / TaskCompleted",
    ),
    FoldRule(
        kind=SignalKind.TASK_COMPLETED,
        delta_fn=_task_completed,
        sets_fn=_task_completed_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("task_completed",),
        evidence="§TaskCreated / TaskCompleted",
    ),
    FoldRule(
        kind=SignalKind.FILES_CHANGED,
        delta_fn=_touched,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("files_changed",),
        evidence="§FileChanged",
    ),
    FoldRule(
        kind=SignalKind.CWD_CHANGED,
        delta_fn=_cwd_changed,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("cwd_changed",),
        evidence="§CwdChanged",
    ),
    FoldRule(
        kind=SignalKind.MODEL_CHANGED,
        delta_fn=_model_changed,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=("model_changed",),
        evidence="§PreModelSwitch / PostModelSwitch",
    ),
    FoldRule(
        kind=SignalKind.TURN_STOPPED,
        delta_fn=_turn_stopped,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("session_stopped",),
        evidence="§Stop",
    ),
    FoldRule(
        kind=SignalKind.SESSION_STOPPED,
        delta_fn=_stopped,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=True,
        emits=("session_stopped",),
        evidence="§SessionEnd",
    ),
    FoldRule(
        kind=SignalKind.COMPACT_STARTED,
        delta_fn=_compact_started,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=(),
        evidence=(
            "§Auto compaction: `PreCompact{trigger:auto}` / `PostCompact`,"
            " and death mid-compaction"
        ),
    ),
    FoldRule(
        kind=SignalKind.COMPACT_FINISHED,
        delta_fn=_compact_finished,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=(),
        evidence="§PreCompact / PostCompact",
    ),
    FoldRule(
        kind=SignalKind.QUOTA_NOTICE,
        delta_fn=_quota_notice,
        sets_fn=_keep_sets,
        anomaly_fn=_no_anomaly,
        clears_needs_you=False,
        emits=(),
        evidence=(
            "§Enumerations (SessionStart.source, SessionEnd.reason,"
            " StopFailure.error, Notification.notification_type)"
        ),
    ),
    FoldRule(
        kind=SignalKind.STOP_FAILED,
        delta_fn=_stopped,
        sets_fn=_keep_sets,
        anomaly_fn=_stop_failed_anomaly,
        clears_needs_you=True,
        emits=("session_stopped",),
        evidence="§StopFailure",
    ),
    FoldRule(
        kind=SignalKind.UNKNOWN,
        delta_fn=_nothing,
        sets_fn=_keep_sets,
        anomaly_fn=_unknown_event,
        clears_needs_you=False,
        emits=(),
        evidence="§Hook event names (the enum)",
    ),
)

#: The lookup `fold()` dispatches on — one row per kind, asserted by test.
RULE_BY_KIND: Mapping[SignalKind, FoldRule] = {rule.kind: rule for rule in FOLD_RULES}


def event_payload(signal: Signal) -> Mapping[str, object]:
    """What a stream event carries: neutral keys only, both of them optional."""
    payload: dict[str, object] = {}
    source = read_start_source(signal)
    if source is not None:
        payload["start_source"] = source
    ask = read_ask(signal)
    if ask is not None:
        payload["ask"] = ask
    return payload
