"""Table B — the fold's rule table, and the three cross-cutting rules (T11).

Nothing in this module names an engine event: the fold's whole point is that it
cannot. Signals are built from `SignalKind` and neutral `fields` keys, which is
exactly the surface `engines/claude_code/normalise.py` hands it.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.fold_types import CLEARED_STAMP, FoldDelta, SessionSnapshot
from shepherd.core.signals import SIGNAL_FIELD_KEYS, Signal, SignalKind
from shepherd.core.states import SessionState
from shepherd.signals.fold import FoldResult, fold
from shepherd.signals.rules import FOLD_RULES, RULE_BY_KIND, IdentitySets

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"

T0 = "2026-09-14T10:00:00Z"
T1 = "2026-09-14T10:00:05Z"

#: Columns no fold rule may ever write: they belong to the process lane (pid,
#: proc_start), the registry lane (observed_at) and the binder (repo_id).
FORBIDDEN_COLUMNS = frozenset({"pid", "proc_start", "observed_at", "repo_id"})


def signal(kind: SignalKind, **fields: object) -> Signal:
    return Signal(
        kind=kind,
        engine_session_id="engine-1",
        cwd="/tmp/work",
        transcript_path="/root/.claude/projects/p/engine-1.jsonl",
        received_at=T1,
        fields=fields,
        raw_kind="opaque-to-the-fold",
    )


def snapshot(**overrides: object) -> SessionSnapshot:
    base: dict[str, object] = {
        "session_id": "01SESSION",
        "engine_session_id": "engine-1",
        "state": SessionState.RUNNING,
        "last_event_at": T0,
        "observed_at": None,
        "needs_you_reason": None,
        "brief": None,
        "cwd": "/tmp/work",
        "repo_id": "01REPO",
        "model": None,
        "tasks_total": 0,
        "tasks_done": 0,
        "active_subagents": 0,
        "repos_touched": (),
        "live_subagent_ids": frozenset(),
        "created_task_ids": frozenset(),
        "completed_task_ids": frozenset(),
        "title": None,
        "title_source": "brief",
        "pid": None,
        "proc_start": None,
        "ended_at": None,
        "auto_compact_at": None,
        "quota_notice_at": None,
    }
    base.update(overrides)
    return SessionSnapshot(**base)  # type: ignore[arg-type]


def advanced(prior: SessionSnapshot, result: FoldResult) -> SessionSnapshot:
    """The caller's job: carry the delta and the identity sets forward."""
    changes: dict[str, object] = {
        field.name: getattr(result.delta, field.name)
        for field in dataclass_fields(result.delta)
        if getattr(result.delta, field.name) is not None
    }
    changes["live_subagent_ids"] = result.sets.live_subagent_ids
    changes["created_task_ids"] = result.sets.created_task_ids
    changes["completed_task_ids"] = result.sets.completed_task_ids
    merged: dict[str, object] = {
        field.name: getattr(prior, field.name) for field in dataclass_fields(prior)
    }
    merged.update(changes)
    return SessionSnapshot(**merged)  # type: ignore[arg-type]


# ----- the table is a total function of SignalKind (r4/r5) -----------------


def test_every_signal_kind_has_exactly_one_rule() -> None:
    kinds = [rule.kind for rule in FOLD_RULES]
    assert sorted(kinds, key=str) == sorted(SignalKind, key=str)
    assert len(kinds) == len(set(kinds)) == len(SignalKind)
    assert set(RULE_BY_KIND) == set(SignalKind)


def test_every_fold_rule_cites_an_existing_section() -> None:
    """A6/K1: no shape is asserted without a capture, enforced mechanically."""
    headings = {
        line.lstrip("#").strip()
        for line in SCHEMAS.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }
    assert len(headings) > 50
    for rule in FOLD_RULES:
        assert rule.evidence, f"{rule.kind} cites nothing"
        cited = rule.evidence.lstrip("§").strip()
        assert cited in headings, f"{rule.kind} cites {rule.evidence!r}, not a section"


def test_no_rule_references_stop_reason() -> None:
    """D46/E9: the field does not exist in 26 captures or the CLI's own schema."""
    sources = [
        (REPO_ROOT / "src" / "shepherd" / "signals" / name).read_text(encoding="utf-8")
        for name in ("rules.py", "fold.py", "ordering.py")
    ]
    for source in sources:
        assert "stop_reason" not in source
    assert "stop_reason" not in str(sorted(SIGNAL_FIELD_KEYS))


# ----- cross-cutting rule 1: the receiver stamps every signal (C8) ---------


def test_every_signal_stamps_last_event_at_from_the_receiver() -> None:
    for kind in SignalKind:
        result = fold(signal(kind), snapshot(), "2027-05-05T05:05:05Z")
        assert result.delta.last_event_at == "2027-05-05T05:05:05Z", kind


def test_fold_is_pure_in_its_prior() -> None:
    prior = snapshot(live_subagent_ids=frozenset({"a1"}), active_subagents=1)
    before = repr(prior)
    fold(signal(SignalKind.SUBAGENT_FINISHED, subagent_id="a1"), prior, T1)
    assert repr(prior) == before


# ----- cross-cutting rule 3: the inferred needs_you clear (G5, r5) ---------


@pytest.mark.parametrize(
    "kind",
    [
        SignalKind.PROMPT_SUBMITTED,
        SignalKind.TOOL_STARTED,
        SignalKind.TOOL_FINISHED,
        SignalKind.TOOL_FAILED,
        SignalKind.TOOL_BATCH_FINISHED,
        SignalKind.INPUT_RESOLVED,
        SignalKind.SESSION_STOPPED,
        SignalKind.STOP_FAILED,
    ],
)
def test_needs_you_is_cleared_by_the_next_activity(kind: SignalKind) -> None:
    waiting = snapshot(state=SessionState.NEEDS_YOU, needs_you_reason="permission: Bash(rm)")
    result = fold(signal(kind, prompt="go on", ask="x"), waiting, T1)
    assert result.delta.needs_you_reason == ""
    assert result.delta.state is not SessionState.NEEDS_YOU


@pytest.mark.parametrize(
    "kind",
    [
        SignalKind.SESSION_REGISTERED,
        SignalKind.TURN_PROGRESS,
        SignalKind.NOTICE_UNMAPPED,
        SignalKind.SUBAGENT_STARTED,
        SignalKind.SUBAGENT_FINISHED,
        SignalKind.TASK_CREATED,
        SignalKind.TASK_COMPLETED,
        SignalKind.FILES_CHANGED,
        SignalKind.CWD_CHANGED,
        SignalKind.MODEL_CHANGED,
        SignalKind.UNKNOWN,
    ],
)
def test_non_clearing_kinds_leave_needs_you_standing(kind: SignalKind) -> None:
    waiting = snapshot(state=SessionState.NEEDS_YOU, needs_you_reason="permission: Bash(rm)")
    result = fold(signal(kind, next_cwd="/tmp/other", model="m", subagent_id="a"), waiting, T1)
    assert result.delta.needs_you_reason is None
    assert result.delta.state is None or result.delta.state is SessionState.NEEDS_YOU


def test_a_clear_on_a_session_that_was_not_waiting_writes_nothing() -> None:
    result = fold(signal(SignalKind.TOOL_STARTED), snapshot(), T1)
    assert result.delta.needs_you_reason is None
    assert result.delta.state is SessionState.RUNNING


def test_needs_input_sets_the_state_and_the_actual_ask() -> None:
    result = fold(signal(SignalKind.NEEDS_INPUT, ask="permission: Bash(git push)"), None, T1)
    assert result.delta.state is SessionState.NEEDS_YOU
    assert result.delta.needs_you_reason == "permission: Bash(git push)"


def test_needs_you_reason_is_the_actual_ask() -> None:
    idle = fold(
        signal(SignalKind.NEEDS_INPUT, ask="idle — waiting for your next instruction"), None, T1
    )
    permission = fold(signal(SignalKind.NEEDS_INPUT, ask="permission: Write(/tmp/a)"), None, T1)
    assert idle.delta.needs_you_reason != permission.delta.needs_you_reason
    assert idle.delta.needs_you_reason == "idle — waiting for your next instruction"


# ----- C11: the brief ------------------------------------------------------


def test_brief_ignores_injected_prompts() -> None:
    """C11: injected `<task-notification>` XML is not the user's brief."""
    injected = "<task-notification>\n<task-id>af9f464d</task-id>\n</task-notification>"
    result = fold(signal(SignalKind.PROMPT_SUBMITTED, prompt=injected), snapshot(), T1)
    assert result.delta.brief is None


def test_brief_is_only_set_once() -> None:
    first = fold(signal(SignalKind.PROMPT_SUBMITTED, prompt="Build the thing"), None, T1)
    assert first.delta.brief == "Build the thing"
    later = fold(
        signal(SignalKind.PROMPT_SUBMITTED, prompt="Now do something else"),
        snapshot(brief="Build the thing"),
        T1,
    )
    assert later.delta.brief is None


# ----- C10: the subagent counter ------------------------------------------


def test_subagent_count_never_negative() -> None:
    prior = snapshot()
    unmatched = fold(signal(SignalKind.SUBAGENT_FINISHED), prior, T1)
    assert unmatched.delta.active_subagents == 0
    stranger = fold(signal(SignalKind.SUBAGENT_FINISHED, subagent_id="never-started"), prior, T1)
    assert stranger.delta.active_subagents == 0


def test_subagent_internal_stops_are_ignored_and_counted() -> None:
    """C10: 2 of 4 captured stops are internal — no id, no pair, one anomaly."""
    prior = snapshot(live_subagent_ids=frozenset({"a1"}), active_subagents=1)
    result = fold(signal(SignalKind.SUBAGENT_FINISHED), prior, T1)
    assert result.delta.active_subagents == 1
    assert [anomaly.kind for anomaly in result.anomalies] == [AnomalyKind.SUBAGENT_UNDERFLOW]
    assert result.sets.live_subagent_ids == frozenset({"a1"})


def test_subagents_pair_by_id() -> None:
    prior = snapshot()
    started = fold(signal(SignalKind.SUBAGENT_STARTED, subagent_id="a1"), prior, T1)
    assert started.delta.active_subagents == 1
    prior = advanced(prior, started)
    again = fold(signal(SignalKind.SUBAGENT_STARTED, subagent_id="a2"), prior, T1)
    assert again.delta.active_subagents == 2
    prior = advanced(prior, again)
    stopped = fold(signal(SignalKind.SUBAGENT_FINISHED, subagent_id="a1"), prior, T1)
    assert stopped.delta.active_subagents == 1
    assert stopped.anomalies == ()
    prior = advanced(prior, stopped)
    # the same stop twice is an unmatched stop, counted, and still not negative
    repeated = fold(signal(SignalKind.SUBAGENT_FINISHED, subagent_id="a1"), prior, T1)
    assert repeated.delta.active_subagents == 1
    assert [anomaly.kind for anomaly in repeated.anomalies] == [AnomalyKind.SUBAGENT_UNDERFLOW]


# ----- P11: tasks ----------------------------------------------------------


def test_tasks_done_never_exceeds_total() -> None:
    prior = snapshot()
    created = fold(signal(SignalKind.TASK_CREATED, task_id="1"), prior, T1)
    assert created.delta.tasks_total == 1
    prior = advanced(prior, created)
    # a completion for a task never announced cannot inflate the count
    stranger = fold(signal(SignalKind.TASK_COMPLETED, task_id="99"), prior, T1)
    assert stranger.delta.tasks_done == 0
    prior = advanced(prior, stranger)
    done = fold(signal(SignalKind.TASK_COMPLETED, task_id="1"), prior, T1)
    assert done.delta.tasks_done == 1
    assert done.delta.tasks_done <= created.delta.tasks_total


def test_repeated_task_ids_are_a_set_not_a_counter() -> None:
    prior = snapshot()
    for _ in range(3):
        result = fold(signal(SignalKind.TASK_CREATED, task_id="1"), prior, T1)
        prior = advanced(prior, result)
    assert prior.tasks_total == 1


# ----- C9: repos_touched ---------------------------------------------------


def test_repos_touched_from_posttooluse_paths() -> None:
    prior = snapshot(repo_id="01REPO", cwd="/tmp/work")
    result = fold(
        signal(SignalKind.TOOL_FINISHED, changed_paths=("/tmp/work/src/a.py",)), prior, T1
    )
    assert result.delta.repos_touched == ("01REPO",)


def test_a_path_outside_the_sessions_repo_is_not_attributed_to_it() -> None:
    prior = snapshot(repo_id="01REPO", cwd="/tmp/work")
    result = fold(signal(SignalKind.TOOL_FINISHED, changed_paths=("/tmp/other/a.py",)), prior, T1)
    assert result.delta.repos_touched is None


def test_repos_touched_is_a_set_and_keeps_what_it_had() -> None:
    prior = snapshot(repo_id="01REPO", cwd="/tmp/work", repos_touched=("01OTHER",))
    result = fold(signal(SignalKind.TOOL_FINISHED, changed_paths=("/tmp/work/a.py",)), prior, T1)
    assert result.delta.repos_touched == ("01OTHER", "01REPO")
    again = fold(signal(SignalKind.TOOL_FINISHED, changed_paths=("/tmp/work/b.py",)), prior, T1)
    assert again.delta.repos_touched == ("01OTHER", "01REPO")


# ----- the remaining column effects ---------------------------------------


def test_cwd_change_moves_the_session() -> None:
    result = fold(signal(SignalKind.CWD_CHANGED, next_cwd="/tmp/work/sub"), snapshot(), T1)
    assert result.delta.cwd == "/tmp/work/sub"
    assert result.delta.repo_id is None  # re-binding needs git: the caller's job


def test_model_change_records_the_destination() -> None:
    result = fold(signal(SignalKind.MODEL_CHANGED, model="claude-sonnet-5"), snapshot(), T1)
    assert result.delta.model == "claude-sonnet-5"


def test_stopping_sets_the_end_time_from_the_receiver() -> None:
    for kind in (SignalKind.SESSION_STOPPED, SignalKind.STOP_FAILED):
        result = fold(signal(kind, failure_note="model_not_found"), snapshot(), T1)
        assert result.delta.state is SessionState.STOPPED
        assert result.delta.ended_at == T1


def test_session_registered_records_the_cwd() -> None:
    result = fold(signal(SignalKind.SESSION_REGISTERED, start_source="resume"), None, T1)
    assert result.delta.cwd == "/tmp/work"


# ----- principle 5: unknowns are counted -----------------------------------


def test_unmapped_values_are_counted() -> None:
    unknown = fold(signal(SignalKind.UNKNOWN), snapshot(), T1)
    assert [anomaly.kind for anomaly in unknown.anomalies] == [AnomalyKind.UNKNOWN_EVENT_NAME]
    notice = fold(signal(SignalKind.NOTICE_UNMAPPED), snapshot(), T1)
    assert [anomaly.kind for anomaly in notice.anomalies] == [AnomalyKind.UNMAPPED_NOTICE]
    failed = fold(signal(SignalKind.STOP_FAILED, failure_note="model_not_found"), snapshot(), T1)
    assert [anomaly.kind for anomaly in failed.anomalies] == [AnomalyKind.STOP_FAILED]
    assert failed.anomalies[0].detail == "model_not_found"
    assert failed.anomalies[0].engine_session_id == "engine-1"


def test_an_unknown_event_is_never_dropped() -> None:
    result = fold(signal(SignalKind.UNKNOWN), snapshot(), T1)
    assert result.delta.last_event_at == T1


# ----- P2/P3: the properties ----------------------------------------------


def _random_signal(rng: random.Random) -> Signal:
    kind = rng.choice(list(SignalKind))
    keys = rng.sample(sorted(SIGNAL_FIELD_KEYS), rng.randint(0, 4))
    values: list[object] = [
        "",
        "x",
        "/tmp/work/a.py",
        ("/tmp/work/a.py",),
        (),
        "<task-notification>x",
        123,
        None,
        {"a": 1},
    ]
    fields: Mapping[str, object] = {key: rng.choice(values) for key in keys}
    return Signal(
        kind=kind,
        engine_session_id=rng.choice(["engine-1", ""]),
        cwd=rng.choice(["/tmp/work", ""]),
        transcript_path="",
        received_at=T1,
        fields=fields,
        raw_kind="opaque",
    )


def test_fold_never_raises() -> None:
    """P2: 200 mutated signals, every kind, hostile field values."""
    rng = random.Random(20260916)
    priors = [None, snapshot(), snapshot(state=SessionState.NEEDS_YOU, needs_you_reason="x")]
    for index in range(200):
        candidate = _random_signal(rng)
        result = fold(candidate, priors[index % len(priors)], T1)
        assert isinstance(result, FoldResult)


def test_fold_is_deterministic() -> None:
    rng = random.Random(4)
    for _ in range(50):
        candidate = _random_signal(rng)
        prior = snapshot()
        first = fold(candidate, prior, T1)
        second = fold(candidate, prior, T1)
        assert first.delta == second.delta
        assert first.anomalies == second.anomalies
        assert first.sets == second.sets


def test_fold_writes_only_declared_fields() -> None:
    """P3: the fold owns its columns and never reaches into another lane's."""
    rng = random.Random(7)
    for _ in range(100):
        result = fold(_random_signal(rng), snapshot(), T1)
        written = {
            field.name
            for field in dataclass_fields(result.delta)
            if getattr(result.delta, field.name) is not None
        }
        assert written & FORBIDDEN_COLUMNS == set(), written


def test_a_delta_is_the_only_thing_the_fold_returns_to_the_store() -> None:
    result = fold(signal(SignalKind.TURN_PROGRESS), snapshot(), T1)
    assert isinstance(result.delta, FoldDelta)
    assert isinstance(result.sets, IdentitySets)
    assert result.events == () or all(event.occurred_at == T1 for event in result.events)


# ----- BLOCKER-T6-1 / T11-4: the sets survive a `controld` restart ----------


def test_subagent_pairing_survives_a_controld_restart(tmp_path: Path) -> None:
    """D37 lets `controld` restart freely; before the sets had a column, a
    restart silently reset every session's pairing and an in-flight subagent's
    stop was counted as an underflow that was not one.

    The restart here is real: the store is closed and reopened on the same
    file, so the only path from the start to the stop is the database.
    """
    from shepherd.core.states import Origin, Ownership
    from shepherd.store.db import open_store

    db_path = tmp_path / "state" / "shepherd.db"
    store = open_store(db_path)
    workspace = store.create_project(name="w", description=None)
    session = store.register_session(
        engine_session_id="engine-1",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp/work",
        started_at=T0,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    started = fold(signal(SignalKind.SUBAGENT_STARTED, subagent_id="a1"), None, T0)
    assert started.delta.active_subagents == 1
    store.apply_fold_delta(session.id, started.delta)
    store.close()

    reopened = open_store(db_path)
    try:
        prior = reopened.snapshot(session.id)
        assert prior is not None
        assert prior.live_subagent_ids == frozenset({"a1"})

        stopped = fold(signal(SignalKind.SUBAGENT_FINISHED, subagent_id="a1"), prior, T1)
        assert stopped.anomalies == ()
        assert stopped.delta.active_subagents == 0
        row = reopened.apply_fold_delta(session.id, stopped.delta)
        assert row.active_subagents == 0
        after = reopened.snapshot(session.id)
        assert after is not None
        assert after.live_subagent_ids == frozenset()
    finally:
        reopened.close()


def test_every_delta_field_reaches_a_store_column() -> None:
    """One writer, one rule set (D37): a field the fold sets and the store
    drops is a value that exists only until the process ends."""
    from shepherd.store.db import DELTA_COLUMNS

    assert {field.name for field in dataclass_fields(FoldDelta)} == set(DELTA_COLUMNS)


# ----- T10: the two marks D24 would otherwise discard ----------------------


def test_auto_compact_mark_is_set_and_cleared() -> None:
    """C12/N9, r3 BLOCKING 1. The mark is set by auto-compaction, cleared by a
    compaction finishing **and by a turn ending** — and deliberately NOT by a
    session ending, which is the *death* §8's rule is bounded by."""
    set_by = fold(signal(SignalKind.COMPACT_STARTED), snapshot(), T1)
    assert set_by.delta.auto_compact_at == T1

    marked = advanced(snapshot(), set_by)
    assert marked.auto_compact_at == T1

    finished = fold(signal(SignalKind.COMPACT_FINISHED), marked, T1)
    assert finished.delta.auto_compact_at == CLEARED_STAMP

    turn_ended = fold(signal(SignalKind.TURN_STOPPED), marked, T1)
    assert turn_ended.delta.auto_compact_at == CLEARED_STAMP

    session_ended = fold(signal(SignalKind.SESSION_STOPPED), marked, T1)
    assert session_ended.delta.auto_compact_at is None, "a session ending is the death"


def test_session_stopped_keeps_its_m1_column_effect() -> None:
    """The row M1 shipped is untouched: the split added a kind, it did not
    rewrite an existing one."""
    result = fold(signal(SignalKind.SESSION_STOPPED), snapshot(), T1)
    written = {
        field.name: getattr(result.delta, field.name)
        for field in dataclass_fields(result.delta)
        if getattr(result.delta, field.name) is not None
    }
    assert written["state"] is SessionState.STOPPED
    assert written["ended_at"] == T1
    assert "auto_compact_at" not in written
    assert "quota_notice_at" not in written
    assert RULE_BY_KIND[SignalKind.SESSION_STOPPED].clears_needs_you is True
    assert RULE_BY_KIND[SignalKind.SESSION_STOPPED].emits == ("session_stopped",)


def test_quota_notice_marks_the_session_and_nothing_else() -> None:
    """G-M2-1: the notice is a mark, not a state change — the session may still
    be running, and D24 would discard the event that proves the notice."""
    result = fold(signal(SignalKind.QUOTA_NOTICE), snapshot(), T1)
    assert result.delta.quota_notice_at == T1
    assert result.delta.state is None
    assert result.delta.auto_compact_at is None
    assert result.anomalies == ()
    assert result.events == ()
