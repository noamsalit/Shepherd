"""T13's read tools: the bucket order, the `unknown` rate, and the stop projection.

Seam: `invoke()`. The page may reach the system through nothing else (D19/D35),
so every assertion here goes through the registry exactly as `web/` does.

Three numbers are asserted separately on purpose (ADR-M2-5, **DP10**): *we could
not map this stop* (`unknown`), *we never saw this stop* (`unclassified`), and
*the turn ended cleanly and no heuristic could tell us whether it finished*
(`completed_low_confidence`). The last is the largest cohort and the one D34
names as the trigger for building the deferred model lane; folded into either of
the other two it stops being a work item anybody can see.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from project_fixture import the_project

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import (
    BUCKET_ORDER,
    CONFIDENT_ENOUGH,
    HEURISTIC_COMPLETED_CONFIDENCE,
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopReason,
    Verdict,
)
from shepherd.store.db import Store, open_store
from shepherd.store.models import Session
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.types import Audience, CallerContext

NOW = "2026-09-16T10:00:30Z"
STALE = "2026-09-16T09:00:00Z"

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="cli", correlation_id="cid-h")

TOOLS_M1 = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "toolsurface" / "tools_m1.py"

#: §13's whitelist after T13. The M1 seventeen plus M2's stop group.
STOP_FIELDS = frozenset(
    {
        "bucket",
        "stop_reason",
        "outcome",
        "why",
        "confidence",
        "decided_by",
        "next_actions",
        "exit_code",
        "ended_at",
    }
)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture(autouse=True)
def tools(store: Store, projects_root: Path) -> None:
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )


def payload(name: str, args: dict[str, object]) -> dict[str, object]:
    result = invoke(name, args, HUMAN)
    assert result.ok is True, result.error
    assert isinstance(result.data, dict)
    return result.data


def seed(store: Store, engine_session_id: str) -> Session:
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=the_project(store),
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )


def verdict(
    reason: StopReason,
    bucket: Bucket,
    *,
    confidence: float,
    actions: tuple[NextAction, ...] = (),
) -> Verdict:
    return Verdict(
        stop_reason=reason,
        bucket=bucket,
        why=f"{reason.value} — the captured wording",
        confidence=confidence,
        decided_by=DecidedBy.HEURISTIC,
        next_actions=actions,
        waiting_on=None,
        missing=(),
    )


RETRY = NextAction(
    text="Retry the request",
    kind=NextActionKind.RETRY,
    target=None,
    source=ActionSource.HEURISTIC,
)
OPEN_PR = NextAction(
    text="Open the pull request",
    kind=NextActionKind.EXTERNAL,
    target="https://example.invalid/pr/1",
    source=ActionSource.HEURISTIC,
)


def stopped_with(
    store: Store,
    engine_session_id: str,
    reason: StopReason,
    bucket: Bucket,
    *,
    confidence: float = 1.0,
    actions: tuple[NextAction, ...] = (),
) -> Session:
    """One session moved to `stopped` through the fold, then given a verdict."""
    session = seed(store, engine_session_id)
    store.apply_fold_delta(
        session.id, FoldDelta(state=SessionState.STOPPED, last_event_at=STALE)
    )
    store.apply_stop_verdict(
        session.id,
        verdict(reason, bucket, confidence=confidence, actions=actions),
        ended_at=STALE,
        exit_code=None,
    )
    return session


def in_state(store: Store, engine_session_id: str, state: SessionState) -> Session:
    session = seed(store, engine_session_id)
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=state,
            last_event_at=NOW,
            needs_you_reason=(
                "idle — waiting for your next instruction"
                if state is SessionState.NEEDS_YOU
                else None
            ),
        ),
    )
    return session


# ----- the bucket order -------------------------------------------------------


def test_fleet_tree_is_ordered_by_bucket(store: Store) -> None:
    """§12's order, which is a **refinement** of §16's, not a replacement.

    The rows are created so that the state order and the bucket order disagree:
    `error` is a *stopped* row and therefore sorts below `running` under
    `fleet_sort_key`, and above it under `fleet_bucket_sort_key` — because an
    errored session is yours to act on and a running one is not.
    """
    finished = stopped_with(store, "eng-finished", StopReason.COMPLETED, Bucket.FINISHED)
    error = stopped_with(store, "eng-error", StopReason.SERVER_ERROR, Bucket.ERROR)
    running = in_state(store, "eng-running", SessionState.RUNNING)
    needs_you = in_state(store, "eng-needs-you", SessionState.NEEDS_YOU)

    sessions = payload("fleet_tree", {})["workspaces"][0]["sessions"]
    assert isinstance(sessions, list)
    assert [row["session_id"] for row in sessions] == [
        needs_you.id,
        error.id,
        running.id,
        finished.id,
    ]
    assert [row["bucket"] for row in sessions] == [
        "needs_you",
        "error",
        "running",
        "finished",
    ]


def test_a_stopped_row_with_no_verdict_is_unclassified_not_green(store: Store) -> None:
    """E-M2-4 / D-4: the `StopFailure` that was lost at `-p` shutdown."""
    session = seed(store, "eng-lost")
    store.apply_fold_delta(
        session.id, FoldDelta(state=SessionState.STOPPED, last_event_at=STALE)
    )
    sessions = payload("fleet_tree", {})["workspaces"][0]["sessions"]
    assert isinstance(sessions, list)
    assert sessions[0]["bucket"] == "unclassified"
    assert sessions[0]["stop_reason"] is None
    assert sessions[0]["next_actions"] == []


# ----- the three numbers ------------------------------------------------------


def test_fleet_summary_reports_the_unknown_rate(store: Store) -> None:
    """Principle 5's headline metric: `unknown / classified`, on the page."""
    stopped_with(store, "eng-a", StopReason.UNKNOWN, Bucket.ERROR)
    stopped_with(store, "eng-b", StopReason.COMPLETED, Bucket.FINISHED)
    stopped_with(store, "eng-c", StopReason.SERVER_ERROR, Bucket.ERROR)
    stopped_with(store, "eng-d", StopReason.RATE_LIMITED, Bucket.PAUSED)

    data = payload("fleet_summary", {})
    assert data["unknown_rate"] == 0.25
    assert data["unknown"] == 1
    assert data["classified"] == 4


def test_unknown_rate_is_zero_not_nan_when_nothing_is_classified() -> None:
    """A fresh install divides by zero unless somebody decided not to."""
    data = payload("fleet_summary", {})
    assert data["unknown_rate"] == 0.0
    assert data["classified"] == 0
    assert data["unknown"] == 0
    assert data["unclassified"] == 0
    assert data["completed_low_confidence"] == 0
    assert json.dumps(data)


def test_unclassified_is_reported_separately_from_unknown(store: Store) -> None:
    """ADR-M2-5: a reason a rule wrote is not a stop no verdict ever reached."""
    stopped_with(store, "eng-unknown", StopReason.UNKNOWN, Bucket.ERROR)
    never = seed(store, "eng-never")
    store.apply_fold_delta(
        never.id, FoldDelta(state=SessionState.STOPPED, last_event_at=STALE)
    )

    data = payload("fleet_summary", {})
    assert data["unknown"] == 1
    assert data["unclassified"] == 1
    assert data["unknown_rate"] == 1.0  # one classified stop, and it is unknown
    by_bucket = data["by_bucket"]
    assert isinstance(by_bucket, dict)
    # `unknown` is a *reason*; its bucket is `error` (BUCKET_OF). `unclassified`
    # is the row that never got a verdict at all — one row, and a different one.
    assert by_bucket["error"] == 1
    assert by_bucket["unclassified"] == 1


def test_low_confidence_completions_are_counted_and_not_folded_into_unknown(
    store: Store,
) -> None:
    """**DP10 / r3 BLOCKING 4.** D34 makes a clean stop `completed` at 0.5.

    `BUCKET_OF[COMPLETED]` is `finished`, which is green *regardless of
    confidence*, so ~96% of clean stops would otherwise render as a verification
    nobody performed and be counted by nothing. The cohort is its own number,
    beside the rate and folded into neither it nor `unclassified`.
    """
    assert HEURISTIC_COMPLETED_CONFIDENCE < CONFIDENT_ENOUGH
    stopped_with(
        store,
        "eng-clean",
        StopReason.COMPLETED,
        Bucket.FINISHED,
        confidence=HEURISTIC_COMPLETED_CONFIDENCE,
    )
    stopped_with(
        store, "eng-sure", StopReason.COMPLETED, Bucket.FINISHED, confidence=1.0
    )

    data = payload("fleet_summary", {})
    assert data["completed_low_confidence"] == 1
    assert data["unknown"] == 0
    assert data["unknown_rate"] == 0.0
    assert data["unclassified"] == 0
    assert data["classified"] == 2
    by_bucket = data["by_bucket"]
    assert isinstance(by_bucket, dict)
    assert by_bucket["finished"] == 2


def test_by_bucket_names_every_bucket_even_at_zero(store: Store) -> None:
    """The census the eight chips render. A bucket at zero is a bucket shown."""
    in_state(store, "eng-live", SessionState.RUNNING)
    by_bucket = payload("fleet_summary", {})["by_bucket"]
    assert isinstance(by_bucket, dict)
    assert set(by_bucket) == {bucket.value for bucket in Bucket}
    assert by_bucket["running"] == 1
    assert by_bucket["error"] == 0
    # …and it arrives in §12's display order, so the page renders the order it
    # was handed rather than learning `BUCKET_ORDER` in JavaScript (T14).
    assert list(by_bucket) == [bucket.value for bucket in BUCKET_ORDER]


# ----- the stop projection ----------------------------------------------------


def test_get_session_returns_the_same_actions_as_the_fleet(store: Store) -> None:
    """§12: the master reads the identical items rather than re-reasoning."""
    session = stopped_with(
        store,
        "eng-actions",
        StopReason.SERVER_ERROR,
        Bucket.ERROR,
        actions=(RETRY, OPEN_PR),
    )
    from_fleet = payload("fleet_tree", {})["workspaces"][0]["sessions"]
    assert isinstance(from_fleet, list)
    one = payload("get_session", {"session_id": session.id})["session"]
    assert isinstance(one, dict)
    assert one["next_actions"] == from_fleet[0]["next_actions"]
    assert one["next_actions"] == [
        {
            "text": "Retry the request",
            "kind": "retry",
            "target": None,
            "source": "heuristic",
        },
        {
            "text": "Open the pull request",
            "kind": "external",
            "target": "https://example.invalid/pr/1",
            "source": "heuristic",
        },
    ]
    assert one["bucket"] == "error"
    assert one["why"] == "server_error — the captured wording"
    assert one["decided_by"] == "heuristic"


def test_project_session_whitelists_the_new_fields(store: Store) -> None:
    """§13: a field not on the list is not projected — still true after T13."""
    session = stopped_with(
        store, "eng-white", StopReason.COMPLETED, Bucket.FINISHED, actions=(RETRY,)
    )
    one = payload("get_session", {"session_id": session.id})["session"]
    assert isinstance(one, dict)
    assert STOP_FIELDS <= set(one)
    assert "owner_id" not in one
    assert "pid" not in one
    assert "engine_session_id" not in one
    assert "auto_compact_at" not in one
    assert "quota_notice_at" not in one
    assert json.dumps(one)


def test_no_read_tool_touches_a_log_path() -> None:
    """P-M2-10 / K14: nothing the UI renders comes from a log file."""
    source = TOOLS_M1.read_text(encoding="utf-8")
    assert "shepherd.logs" not in source
    assert "StopLog" not in source
    assert "open(" not in source
    assert "read_stop_records" not in source


def test_schema_is_validated_at_registration() -> None:
    """D53 — inherited behaviour, re-asserted where the tools are."""
    for name, tool in registered_tools().items():
        schema = tool.input_schema
        assert isinstance(schema, dict), name
        assert schema["type"] == "object", name
        assert isinstance(schema["properties"], dict), name


def test_every_new_tool_declares_its_audiences() -> None:
    """ADR-3: `web/` is `HUMAN`, so every read tool must admit one."""
    for name, tool in registered_tools().items():
        assert tool.audiences != frozenset(), name
        assert Audience.HUMAN in tool.audiences, name
