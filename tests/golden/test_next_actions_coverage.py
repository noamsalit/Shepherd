"""T17 — the per-reason coverage table, as a test, and §14's literal sentence.

**This table is the deliverable.** A lane that reports "174 fixtures pass"
while five reasons have no fixture at all is a lane that lies, so every one of
the twenty `StopReason` values is either produced by a fixture built from real
captures, or excused by a **named** evidence gap — and a gap id nobody wrote
down in the plan is not an excuse.

The two directions both bite:

* a row claiming a fixture whose reason the fixture set does not actually
  produce is a failure — that is the row rotting;
* a row claiming a gap whose reason the fixture set *does* produce is also a
  failure — that is the gap being stale, which is how a closed gap stays open
  in the documentation forever.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from golden.stops import (
    EXPECTED_FIXTURE_COUNT,
    StopFixture,
    composed,
    load_stop_fixtures,
    verdict_table,
)
from shepherd.core.stops import MAX_ACTIONS, StopReason
from shepherd.signals.stop_rules import DEFAULT_ACTIONS, default_actions
from shepherd.signals.verdict import classify

#: The only accepted excuses: the evidence gaps the plan itself names (§the
#: evidence-gap register, G-M2-1 … G-M2-7). Anything else — including a gap id
#: invented at the moment a test went red — is not an excuse.
ACCEPTED_GAPS: Mapping[str, str] = {
    "G-M2-1": "no `quota_*` notification payload was ever captured",
    "G-M2-2": "`crashed` needs an exit code an attached session cannot give (C13)",
    "G-M2-3": "no capture of `message.stop_reason = tool_use` at a `Stop`",
    "G-M2-4": "`killed` needs M4's `action_log`",
    "G-M2-5": "five `StopFailure.error` values were never observed",
    "G-M2-6": "`derailed` has no mechanical detector",
    "G-M2-7": "`blocked_external`'s two buildable sources are M4's and M5's",
}

REAL = "real"
COMPOSED = "composed"
GAP = "gap"

#: The plan's coverage table, row for row. `kind` is the provenance the lane
#: claims, and the tests below check the claim against the fixture set rather
#: than trusting it.
COVERAGE: Mapping[StopReason, tuple[str, str]] = {
    StopReason.RATE_LIMITED: (REAL, "S08_mock_http429"),
    StopReason.AUTH_FAILED: (REAL, "mock 401 / 403"),
    StopReason.ACCOUNT_BLOCKED: (REAL, "mock 400, credit balance"),
    StopReason.BAD_REQUEST: (REAL, "S07_bad_model (real API) and mock prompt-too-long"),
    StopReason.SERVER_ERROR: (REAL, "mock 500 and mock 529"),
    StopReason.TRUNCATED: (REAL, "S08_mock_max_tokens"),
    StopReason.UNKNOWN: (REAL, "S08_mock_http400 — the engine's own `unknown`"),
    StopReason.USER_EXITED: (REAL, "I01_interactive and three more in corpus 2"),
    StopReason.CLEARED: (REAL, "S06_clear, I01, transcript-append"),
    StopReason.LOGGED_OUT: (REAL, "lifecycle-end-*"),
    StopReason.RESUMED_ELSEWHERE: (REAL, "lifecycle-end-*"),
    StopReason.CONTEXT_EXHAUSTED: (REAL, "lifecycle-end-* kill-mid-compaction"),
    StopReason.COMPLETED: (COMPOSED, "a real `Stop` record + a real `end_turn` tail"),
    StopReason.INCOMPLETE: (COMPOSED, "heuristic 1 real; heuristics 2-4 composed"),
    StopReason.STALLED_PENDING_TOOL: (COMPOSED, "G-M2-3 — a real `tool_use` entry, last"),
    StopReason.QUOTA_PAUSED: (GAP, "G-M2-1"),
    StopReason.CRASHED: (GAP, "G-M2-2"),
    StopReason.KILLED: (GAP, "G-M2-4"),
    StopReason.DERAILED: (GAP, "G-M2-6"),
    #: The plan's table says *composed*, and it cannot be: heuristic 5 needs
    #: waiting phrasing in the last assistant message and **no capture in
    #: either corpus contains any** — the vocabulary is spec-derived (T8-1).
    #: Composing one would mean writing the text, which this task forbids.
    #: Recorded as the gap the plan already names for this reason, and written
    #: up in `docs/plans/2026-09-17-m2-BLOCKERS.md` (T17-2).
    StopReason.BLOCKED_EXTERNAL: (GAP, "G-M2-7"),
}


@pytest.fixture(scope="module")
def fixtures() -> list[StopFixture]:
    return load_stop_fixtures()


def test_the_coverage_table_is_total_over_the_vocabulary() -> None:
    """Twenty reasons, twenty rows. Totality by iteration, never by `else`."""
    assert sorted(COVERAGE, key=str) == sorted(StopReason, key=str)
    assert len(COVERAGE) == len(StopReason)


def test_every_stop_reason_has_a_fixture_or_a_named_gap(fixtures: list[StopFixture]) -> None:
    """The coverage table above, checked against what the lane actually builds."""
    assert len(fixtures) == EXPECTED_FIXTURE_COUNT
    produced = {classify(fixture.evidence).stop_reason for fixture in fixtures}

    unexcused = [
        reason.value
        for reason in StopReason
        if reason not in produced
        and not (COVERAGE[reason][0] == GAP and COVERAGE[reason][1] in ACCEPTED_GAPS)
    ]
    assert unexcused == [], "these reasons have neither a fixture nor a named gap"

    stale = [
        reason.value
        for reason in StopReason
        if COVERAGE[reason][0] == GAP and reason in produced
    ]
    assert stale == [], "these reasons claim an evidence gap the lane has closed"

    rotted = [
        reason.value
        for reason in StopReason
        if COVERAGE[reason][0] in (REAL, COMPOSED) and reason not in produced
    ]
    assert rotted == [], "these rows claim a fixture the lane does not build"


def test_a_real_row_is_backed_by_an_uncomposed_fixture(fixtures: list[StopFixture]) -> None:
    """`real` and `composed` are different claims, so they are checked apart.

    A row that says `real` and is only reachable through a pairing we invented
    would be the lane overstating its own evidence — which is the one thing the
    r3 BLOCKING 3 note exists to prevent.
    """
    uncomposed = {
        classify(fixture.evidence).stop_reason
        for fixture in fixtures
        if not composed(fixture)
    }
    overstated = [
        reason.value
        for reason in StopReason
        if COVERAGE[reason][0] == REAL and reason not in uncomposed
    ]
    assert overstated == []


def test_every_stop_reason_in_the_table_has_a_non_empty_action_list_unless_completed(
    fixtures: list[StopFixture],
) -> None:
    """§14's literal sentence, over the checked-in table **and** over all twenty.

    The table alone would leave the four gap reasons untested, and D21's whole
    argument is that a stop nobody can act on is not a product — so the default
    table is walked too.
    """
    rows = verdict_table(fixtures)
    assert len(rows) == EXPECTED_FIXTURE_COUNT
    empty = [
        name
        for name, row in rows.items()
        if not row["next_actions"] and row["stop_reason"] != StopReason.COMPLETED.value
    ]
    assert empty == []

    # DP10: a `completed` the heuristics were not confident about still carries
    # `Review the diff`, so in this lane **every** row has an action.
    assert [name for name, row in rows.items() if not row["next_actions"]] == []

    for reason in StopReason:
        actions = default_actions(reason, confidence=1.0, missing=(), waiting_on=None)
        assert len(actions) <= MAX_ACTIONS
        if reason is StopReason.COMPLETED:
            assert actions == (), "a confident `completed` is the one empty row (P-M2-3)"
        else:
            assert actions, f"{reason.value} has no default action"
            assert all(action.text.strip() for action in actions)
        assert reason in DEFAULT_ACTIONS
