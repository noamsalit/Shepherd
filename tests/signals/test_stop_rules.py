"""D21's bucket map and default action table (T7, `signals/stop_rules.py`).

Two total tables over the twenty `StopReason` values, and one derivation that
turns a reason plus its confidence into *the one thing a human could do*. §14's
literal sentence is the load-bearing test here: **a stop reason with an empty
action list on a non-`completed` verdict is a test failure.**
"""

from __future__ import annotations

from shepherd.core.stops import (
    ACTION_TEXT_MAX,
    CONFIDENT_ENOUGH,
    MAX_ACTIONS,
    ActionSource,
    Bucket,
    NextActionKind,
    StopReason,
)
from shepherd.signals.stop_rules import BUCKET_OF, DEFAULT_ACTIONS, default_actions

#: Every call shape the table is exercised through, so a "total" claim is
#: measured over the parameters too and not only over the enum.
CONFIDENCES = (0.0, 0.5, 0.79, CONFIDENT_ENOUGH, 1.0)


def test_every_stop_reason_has_a_bucket_and_actions() -> None:
    """P-M2-3 — totality by iterating the enum, never by listing keys."""
    for reason in StopReason:
        assert reason in BUCKET_OF, reason
        assert reason in DEFAULT_ACTIONS, reason
        assert isinstance(BUCKET_OF[reason], Bucket)
    assert len(BUCKET_OF) == len(list(StopReason)) == 20


def test_the_bucket_map_is_section_8s_outcome_class_column() -> None:
    """Spelled out rather than recomputed: the expected side is §8's table."""
    assert BUCKET_OF[StopReason.RATE_LIMITED] is Bucket.PAUSED
    assert BUCKET_OF[StopReason.QUOTA_PAUSED] is Bucket.PAUSED
    assert BUCKET_OF[StopReason.COMPLETED] is Bucket.FINISHED
    assert BUCKET_OF[StopReason.BLOCKED_EXTERNAL] is Bucket.BLOCKED
    for reason in (
        StopReason.AUTH_FAILED,
        StopReason.ACCOUNT_BLOCKED,
        StopReason.BAD_REQUEST,
        StopReason.SERVER_ERROR,
        StopReason.STALLED_PENDING_TOOL,
        StopReason.CRASHED,
        StopReason.LOGGED_OUT,
        StopReason.UNKNOWN,
    ):
        assert BUCKET_OF[reason] is Bucket.ERROR, reason
    for reason in (
        StopReason.TRUNCATED,
        StopReason.KILLED,
        StopReason.CONTEXT_EXHAUSTED,
        StopReason.USER_EXITED,
        StopReason.CLEARED,
        StopReason.RESUMED_ELSEWHERE,
        StopReason.INCOMPLETE,
        StopReason.DERAILED,
    ):
        assert BUCKET_OF[reason] is Bucket.UNFINISHED, reason


def test_non_completed_verdict_never_has_an_empty_action_list() -> None:
    """§14's literal words, over every reason and every confidence."""
    for reason in StopReason:
        if reason is StopReason.COMPLETED:
            continue
        for confidence in CONFIDENCES:
            actions = default_actions(
                reason, confidence=confidence, missing=(), waiting_on=None
            )
            assert actions != (), f"{reason} at {confidence} has nothing to do"


def test_completed_is_empty_only_above_the_threshold() -> None:
    """ADR-M2-5 / DP10 — the clean stop that is *not* confident carries an action."""
    confident = default_actions(
        StopReason.COMPLETED, confidence=CONFIDENT_ENOUGH, missing=(), waiting_on=None
    )
    assert confident == ()
    unsure = default_actions(
        StopReason.COMPLETED, confidence=0.5, missing=(), waiting_on=None
    )
    assert len(unsure) == 1
    assert unsure[0].text == "Review the diff"
    assert unsure[0].kind is NextActionKind.INSPECT


def test_action_list_is_capped_at_three() -> None:
    for reason in StopReason:
        for confidence in CONFIDENCES:
            actions = default_actions(
                reason,
                confidence=confidence,
                missing=("a", "b", "c", "d", "e"),
                waiting_on="https://example.invalid/pr/1",
            )
            assert len(actions) <= MAX_ACTIONS, reason


def test_every_action_text_is_within_eighty_chars() -> None:
    for reason in StopReason:
        actions = default_actions(
            reason,
            confidence=0.1,
            missing=("x" * 200,),
            waiting_on="u" * 300,
        )
        for action in actions:
            assert 0 < len(action.text) <= ACTION_TEXT_MAX, (reason, action.text)


def test_incomplete_row_never_exceeds_three_actions_with_many_missing() -> None:
    """N14 / A7 — five findings still yield three items, and `Requeue` is one."""
    for reason in (StopReason.INCOMPLETE, StopReason.DERAILED):
        actions = default_actions(
            reason,
            confidence=0.5,
            missing=("one", "two", "three", "four", "five"),
            waiting_on=None,
        )
        assert len(actions) == 3
        assert actions[-1].text == "Requeue with what's missing"
        assert [a.kind for a in actions] == [NextActionKind.REQUEUE] * 3
        # truncated to TWO of the five, which is the deviation N14 records
        assert "one" in actions[0].text
        assert "two" in actions[1].text
        assert all("three" not in a.text for a in actions)


def test_reauth_text_has_no_empty_provider_slot() -> None:
    """N15 / A7 — never `Re-authenticate ` with a trailing blank or a `<…>`."""
    for reason in (StopReason.AUTH_FAILED, StopReason.LOGGED_OUT):
        actions = default_actions(reason, confidence=1.0, missing=(), waiting_on=None)
        assert [a.text for a in actions] == ["Re-authenticate"]
        assert actions[0].kind is NextActionKind.REAUTH
        assert actions[0].target is None


def test_blocked_external_degrades_rather_than_guessing() -> None:
    """G-M2-7 — `waiting_on` is `None` at M2, so the text says so out loud."""
    unknown = default_actions(
        StopReason.BLOCKED_EXTERNAL, confidence=0.5, missing=(), waiting_on=None
    )
    assert len(unknown) == 1
    assert unknown[0].text == "Chase — what it is waiting on is not recorded"
    assert unknown[0].target is None
    named = default_actions(
        StopReason.BLOCKED_EXTERNAL,
        confidence=0.5,
        missing=(),
        waiting_on="https://example.invalid/pr/1",
    )
    assert named[0].text == "Chase https://example.invalid/pr/1"
    assert named[0].target == "https://example.invalid/pr/1"
    assert named[0].kind is NextActionKind.EXTERNAL


def test_a_paused_row_says_it_resumes_by_itself_and_shows_no_time() -> None:
    """G-M2-1 — no capture carries a reset time, so none is rendered."""
    for reason in (StopReason.RATE_LIMITED, StopReason.QUOTA_PAUSED):
        actions = default_actions(reason, confidence=1.0, missing=(), waiting_on=None)
        assert [a.kind for a in actions] == [NextActionKind.NONE, NextActionKind.RETRY]
        assert actions[0].text == "Resumes by itself — nothing to do"
        assert all(not any(ch.isdigit() for ch in a.text) for a in actions)


def test_every_action_kind_is_reachable_from_some_row() -> None:
    """All nine, or the enum is aspirational (D21's list, DP5)."""
    reached = {
        action.kind
        for reason in StopReason
        for confidence in CONFIDENCES
        for action in default_actions(
            reason, confidence=confidence, missing=("a",), waiting_on="https://x.invalid"
        )
    }
    assert reached == set(NextActionKind)


def test_every_default_action_is_sourced_as_heuristic() -> None:
    """§8's ordering guarantee ranks `declared` > `llm` > `heuristic`; these are
    the floor, and nothing at M2 writes the other two."""
    for reason in StopReason:
        for action in default_actions(
            reason, confidence=0.1, missing=("a",), waiting_on="https://x.invalid"
        ):
            assert action.source is ActionSource.HEURISTIC


def test_the_static_table_is_non_empty_for_every_reason_but_completed() -> None:
    """P-M2-3's second clause, asserted on the table itself."""
    for reason in StopReason:
        rows = DEFAULT_ACTIONS[reason]
        if reason is StopReason.COMPLETED:
            assert rows == ()
        else:
            assert rows != (), reason
