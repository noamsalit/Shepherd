"""The liveness backstop and §16's fleet order (T11, `signals/ordering.py`)."""

from __future__ import annotations

from dataclasses import replace

from shepherd.core.states import SessionState
from shepherd.core.stops import BUCKET_ORDER, Bucket
from shepherd.signals.ordering import (
    LIVENESS_WINDOW_S,
    bucket_of,
    effective_state,
    fleet_bucket_sort_key,
    fleet_sort_key,
    is_live,
)
from shepherd.store.models import FleetRow

NOW = "2026-09-14T12:00:00Z"


def row(session_id: str, state: SessionState, last_event_at: str | None) -> FleetRow:
    return FleetRow(
        session_id=session_id,
        engine_session_id="engine-" + session_id,
        workspace_id="01WS",
        workspace_name="work",
        repo_name=None,
        state=state,
        title=None,
        brief=None,
        needs_you_reason=None,
        tasks_done=0,
        tasks_total=0,
        active_subagents=0,
        last_event_at=last_event_at,
        cwd="/tmp/work",
    )


def test_the_window_is_ninety_seconds() -> None:
    assert LIVENESS_WINDOW_S == 90
    assert is_live("2026-09-14T11:59:01Z", NOW)
    assert not is_live("2026-09-14T11:58:00Z", NOW)
    assert not is_live(None, NOW)
    assert not is_live("not a timestamp", NOW)


def test_a_silent_running_session_is_not_running() -> None:
    fresh = row("01A", SessionState.RUNNING, "2026-09-14T11:59:30Z")
    stale = row("01B", SessionState.RUNNING, "2026-09-14T11:00:00Z")
    assert effective_state(fresh, NOW) is SessionState.RUNNING
    assert effective_state(stale, NOW) is not SessionState.RUNNING


def test_silence_never_demotes_a_session_that_is_blocked_on_you() -> None:
    waiting = row("01C", SessionState.NEEDS_YOU, "2026-09-14T09:00:00Z")
    assert effective_state(waiting, NOW) is SessionState.NEEDS_YOU


def test_fleet_ordering_puts_needs_you_first_and_stopped_last() -> None:
    rows = [
        row("01STOPPED", SessionState.STOPPED, "2026-09-14T11:59:59Z"),
        row("01RUNNING", SessionState.RUNNING, "2026-09-14T11:59:59Z"),
        row("01STALE", SessionState.RUNNING, "2026-09-14T10:00:00Z"),
        row("01WAITING", SessionState.NEEDS_YOU, "2026-09-14T08:00:00Z"),
    ]
    ordered = [item.session_id for item in sorted(rows, key=lambda item: fleet_sort_key(item, NOW))]
    assert ordered == ["01WAITING", "01RUNNING", "01STALE", "01STOPPED"]


def test_the_tiebreak_is_stable_within_a_bucket() -> None:
    rows = [
        row("01C", SessionState.RUNNING, "2026-09-14T11:59:59Z"),
        row("01A", SessionState.RUNNING, "2026-09-14T11:59:58Z"),
        row("01B", SessionState.RUNNING, "2026-09-14T11:59:57Z"),
    ]
    ordered = [item.session_id for item in sorted(rows, key=lambda item: fleet_sort_key(item, NOW))]
    assert ordered == ["01A", "01B", "01C"]
    assert [fleet_sort_key(item, NOW)[0] for item in rows] == [1, 1, 1]


# ----- T7: the fleet's eight-bucket ordering ---------------------------------
#
# Built **on top of** `effective_state` and `fleet_sort_key`, never instead of
# them: every test above still passes verbatim, which is what "additive" means.


def stopped_row(
    session_id: str, outcome: str | None, last_event_at: str = "2026-09-14T09:00:00Z"
) -> FleetRow:
    return replace(row(session_id, SessionState.STOPPED, last_event_at), outcome=outcome)


def test_bucket_order_matches_section_12() -> None:
    """§12, l.1945 verbatim for its first seven entries."""
    assert [bucket.value for bucket in BUCKET_ORDER[:7]] == [
        "needs_you",
        "error",
        "unfinished",
        "running",
        "paused",
        "blocked",
        "finished",
    ]


def test_bucket_order_is_section_12_plus_unclassified() -> None:
    """A1 — §12's eighth entry is `idle`, and `idle` is **not** a bucket.

    M1's D-2 resolved `idle` as a *workspace-level* rendering (a workspace all
    of whose sessions are stopped), never a session state. Substituting
    `unclassified` for it while calling the tuple "§12 verbatim" would be a
    quiet reversal; the tuple is §12's seven **plus** ours, and the spec line
    says `idle` where this says nothing.
    """
    assert len(BUCKET_ORDER) == 8
    assert BUCKET_ORDER[7] is Bucket.UNCLASSIFIED
    assert "idle" not in {bucket.value for bucket in Bucket}
    assert set(BUCKET_ORDER) == set(Bucket)


def test_unclassified_is_its_own_bucket() -> None:
    """D-4 — a stopped row with no verdict is never green and never red."""
    assert bucket_of(stopped_row("01NONE", None), NOW) is Bucket.UNCLASSIFIED
    assert BUCKET_ORDER.index(Bucket.UNCLASSIFIED) > BUCKET_ORDER.index(Bucket.FINISHED)


def test_blocked_sorts_below_running() -> None:
    """§12's deliberate choice: it is real, it is visible, it is not yours."""
    assert BUCKET_ORDER.index(Bucket.BLOCKED) > BUCKET_ORDER.index(Bucket.RUNNING)


def test_a_stopped_row_takes_the_bucket_its_outcome_names() -> None:
    for bucket in Bucket:
        taken = bucket_of(stopped_row("01X", bucket.value), NOW)
        assert taken is bucket, bucket


def test_bucket_of_is_total() -> None:
    """A1, r3 — every state x (outcome present/absent) x (live/stale) answers.

    The case revision 2 fell off the end of is real: C7 records a `-p` session
    whose `StopFailure` was killed at shutdown **2/2 times**, so the row is a
    stale `running` with no stop event — neither live nor stopped-with-an-
    outcome. It is `UNCLASSIFIED`: we do not know, we say so, we count it.
    """
    live, stale = "2026-09-14T11:59:59Z", "2026-09-14T10:00:00Z"
    for state in SessionState:
        for outcome in (None, "finished", "not-a-bucket-anyone-wrote"):
            for last_event_at in (live, stale, None):
                got = bucket_of(replace(row("01T", state, last_event_at), outcome=outcome), NOW)
                assert isinstance(got, Bucket), (state, outcome, last_event_at)
                assert got in BUCKET_ORDER

    silent_runner = row("01C7", SessionState.RUNNING, stale)
    assert silent_runner.outcome is None
    assert bucket_of(silent_runner, NOW) is Bucket.UNCLASSIFIED


def test_an_unreadable_outcome_is_unclassified_not_a_crash() -> None:
    """A column value this build did not write is an unknown, not an exception."""
    assert bucket_of(stopped_row("01BAD", "idle"), NOW) is Bucket.UNCLASSIFIED
    assert bucket_of(stopped_row("01BAD", ""), NOW) is Bucket.UNCLASSIFIED


def test_needs_you_outranks_a_stopped_verdict() -> None:
    """E-M2-26 / §8 — C21's `idle_prompt` flips a classified session to
    `needs_you` 60 s after the `Stop`. The rail wins the row; the verdict is
    not erased, and expanding the row still shows it."""
    waiting = replace(row("01W", SessionState.NEEDS_YOU, "2026-09-14T08:00:00Z"), outcome="finished")
    assert bucket_of(waiting, NOW) is Bucket.NEEDS_YOU
    assert waiting.outcome == "finished"
    assert fleet_bucket_sort_key(waiting, NOW)[0] < fleet_bucket_sort_key(
        stopped_row("01F", "finished"), NOW
    )[0]


def test_liveness_demotion_still_applies_before_bucketing() -> None:
    """M1's `effective_state`, unchanged and still first in line."""
    fresh = row("01A", SessionState.RUNNING, "2026-09-14T11:59:30Z")
    stale = row("01B", SessionState.RUNNING, "2026-09-14T11:00:00Z")
    assert bucket_of(fresh, NOW) is Bucket.RUNNING
    assert effective_state(stale, NOW) is SessionState.STARTING
    assert bucket_of(stale, NOW) is Bucket.UNCLASSIFIED


def test_a_live_starting_session_is_running() -> None:
    """§16 sorts `starting` below `running`; §4's palette has no chip for it,
    so a session that is live and has produced nothing to act on is `running`."""
    assert bucket_of(row("01S", SessionState.STARTING, "2026-09-14T11:59:59Z"), NOW) is Bucket.RUNNING


def test_the_bucket_sort_key_orders_a_mixed_fleet() -> None:
    rows = [
        stopped_row("01FIN", "finished"),
        stopped_row("01ERR", "error"),
        row("01RUN", SessionState.RUNNING, "2026-09-14T11:59:59Z"),
        replace(row("01YOU", SessionState.NEEDS_YOU, "2026-09-14T08:00:00Z"), outcome=None),
        stopped_row("01NONE", None),
        stopped_row("01BLK", "blocked"),
    ]
    ordered = [
        item.session_id for item in sorted(rows, key=lambda item: fleet_bucket_sort_key(item, NOW))
    ]
    assert ordered == ["01YOU", "01ERR", "01RUN", "01BLK", "01FIN", "01NONE"]


def test_the_bucket_tiebreak_is_the_session_ulid() -> None:
    """The same stable tiebreak M1 chose: a live page re-sorted on every event
    must not shuffle rows that did not change."""
    rows = [stopped_row("01C", "finished"), stopped_row("01A", "finished"), stopped_row("01B", "finished")]
    ordered = [
        item.session_id for item in sorted(rows, key=lambda item: fleet_bucket_sort_key(item, NOW))
    ]
    assert ordered == ["01A", "01B", "01C"]


def test_m1_fleet_sort_key_is_unchanged() -> None:
    """The new key is additive: §16's four-state order still answers as it did."""
    assert fleet_sort_key(row("01R", SessionState.RUNNING, "2026-09-14T11:59:59Z"), NOW) == (1, "01R")
    assert fleet_sort_key(stopped_row("01S", "finished"), NOW) == (3, "01S")
