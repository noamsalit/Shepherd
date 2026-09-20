"""T4 — §8's mechanical stop-reason table, over the real captures.

**The differentiator's core.** The table is exercised against the 23
`StopFailure` and the 66 `SessionEnd` payloads two probe runs actually
recorded, never against hand-written payloads: the spec had three field names
wrong (`error_type`, `end_reason`, `start_reason` — they are `error`, `reason`,
`source`), and only a capture catches that.

The map lives in `engines/claude_code/` because D46 keys it on three **engine**
fields, and §5.0 forbids those names in `signals/` (ADR-M2-2, DP4).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.stops import StopReason, TurnEnding
from shepherd.engines.claude_code import stop_map
from shepherd.engines.claude_code.stop_map import (
    BOUNDED_RULES,
    DEFERS,
    ERROR_RULES,
    REASON_RULES,
    UNMAPPED,
    MechanicalResult,
    mechanical_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"

#: The 13-member `StopFailure.error` enum and the 5-member `SessionEnd.reason`
#: enum, verbatim from the binary (`drift_check.py` re-verified them clean at
#: 2.1.273 in this build's step 0).
ERROR_ENUM = (
    "authentication_failed",
    "oauth_org_not_allowed",
    "account_on_hold",
    "verification_required",
    "billing_error",
    "rate_limit",
    "overloaded",
    "invalid_request",
    "model_not_found",
    "server_error",
    "unknown",
    "max_output_tokens",
    "cloud_credential_error",
)
REASON_ENUM = ("clear", "resume", "logout", "prompt_input_exit", "other")


def payloads() -> Iterator[dict[str, object]]:
    """Every captured hook payload from both corpora, including the pty run.

    `pidfd-pty-*/pty-hooks.jsonl` is a filename the `*/hooks.jsonl` glob does
    not match (A5, r3), and it is where C13's observed-process-exit evidence
    lives — so it is named explicitly rather than hoped for.
    """
    sources = [
        *sorted(PROBES.glob("hooks/live/*/events.jsonl")),
        *sorted(PROBES.glob("gap-fill/*/hooks.jsonl")),
        *sorted(PROBES.glob("gap-fill/pidfd-pty-*/pty-hooks.jsonl")),
    ]
    assert sources, "the probe corpora are missing — they are the evidence base"
    for path in sources:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") if isinstance(record, dict) else None
            if isinstance(payload, dict):
                yield payload


def captured(event: str) -> list[dict[str, object]]:
    return [p for p in payloads() if p.get("hook_event_name") == event]


def result(**overrides: object) -> MechanicalResult:
    """`mechanical_reason` with every argument defaulted to "nothing known"."""
    arguments: dict[str, object] = {
        "failure_error": None,
        "end_reason": None,
        "ending": TurnEnding.ABSENT,
        "auto_compact_pending": False,
        "quota_notice": False,
        "process_exit_observed": False,
        "exit_code": None,
    }
    arguments.update(overrides)
    return mechanical_reason(**arguments)  # type: ignore[arg-type]


# ----- totality and purity ----------------------------------------------------


def test_stop_map_is_total_over_both_enums() -> None:
    """P-M2-4: every enum value returns something; none raises; none is `None`."""
    assert len(ERROR_RULES) == 13
    assert len(REASON_RULES) == 5
    assert {rule.value for rule in ERROR_RULES} == set(ERROR_ENUM)
    assert {rule.value for rule in REASON_RULES} == set(REASON_ENUM)

    for value in ERROR_ENUM:
        outcome = result(failure_error=value)
        assert isinstance(outcome.reason, StopReason), value

    for value in REASON_ENUM:
        outcome = result(end_reason=value, ending=TurnEnding.ENDED_TURN)
        assert outcome.reason is None or isinstance(outcome.reason, StopReason), value

    # …and the sentinels are distinct objects, not two names for one thing.
    assert DEFERS is not UNMAPPED


def test_no_error_row_defers() -> None:
    """Every API error decides. The session-ending table is the one that has a
    deferring row, and `mechanical_reason` handles the other case by falling
    through rather than by asserting — so this states the current shape."""
    assert all(isinstance(rule.reason, StopReason) for rule in ERROR_RULES)
    deferring = [rule for rule in REASON_RULES if rule.reason is DEFERS]
    assert [rule.value for rule in deferring] == ["other"]


def test_stop_map_is_pure() -> None:
    """200 cases, same input -> same output, and no I/O anywhere in the module."""
    cases = [
        (error, reason, ending)
        for error in (*ERROR_ENUM, None, "a-value-from-the-future")
        for reason in (*REASON_ENUM, None)
        for ending in TurnEnding
    ]
    assert len(cases) >= 200

    for error, reason, ending in cases:
        first = result(failure_error=error, end_reason=reason, ending=ending)
        second = result(failure_error=error, end_reason=reason, ending=ending)
        assert first == second

    tree = ast.parse(Path(stop_map.__file__).read_text(encoding="utf-8"))
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert names & {"open", "print", "input"} == set()
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported & {"pathlib", "os", "subprocess", "datetime", "time"} == set()


def test_stop_map_never_raises() -> None:
    """Including for a value from a future engine, an empty string and a null."""
    for error in ("", "🙂", "a" * 5000, None, "overloaded"):
        for reason in ("", None, "other", "a-new-reason"):
            for ending in TurnEnding:
                outcome = result(failure_error=error, end_reason=reason, ending=ending)
                assert isinstance(outcome, MechanicalResult)


# ----- precedence: measured, not chosen ---------------------------------------


def test_precedence_is_error_then_reason_then_tail() -> None:
    """On **23/23** `StopFailure` captures the last assistant entry says
    `stop_sequence`. Reading the tail first would classify every API failure as
    unknown, so the order is a measurement, not a preference."""
    both = result(
        failure_error="rate_limit", end_reason="clear", ending=TurnEnding.HELD_TOOL_CALL
    )
    assert both.reason is StopReason.RATE_LIMITED

    reason_over_tail = result(end_reason="clear", ending=TurnEnding.HELD_TOOL_CALL)
    assert reason_over_tail.reason is StopReason.CLEARED

    tail_alone = result(ending=TurnEnding.HELD_TOOL_CALL)
    assert tail_alone.reason is StopReason.STALLED_PENDING_TOOL


def test_quota_notice_outranks_a_bare_tail_but_not_an_api_error() -> None:
    """Step 5: a quota notice decides only when no API error did."""
    assert result(quota_notice=True, ending=TurnEnding.ENDED_TURN).reason is (
        StopReason.QUOTA_PAUSED
    )
    assert result(quota_notice=True, failure_error="rate_limit").reason is (
        StopReason.RATE_LIMITED
    )


def test_ended_turn_defers_to_the_completeness_split() -> None:
    """The one defer that is not an anomaly: the question moves to T8/T9."""
    outcome = result(ending=TurnEnding.ENDED_TURN)
    assert outcome.reason is None
    assert outcome.anomalies == ()


def test_an_absent_tail_is_unknown_and_counted() -> None:
    """E-M2-12: no transcript means `end_turn` cannot be established, so the
    split does not run and the verdict is `unknown` — counted, never guessed."""
    for ending in (TurnEnding.ABSENT, TurnEnding.OTHER):
        outcome = result(ending=ending)
        assert outcome.reason is StopReason.UNKNOWN
        assert AnomalyKind.STOP_UNMAPPED_VALUE in {a.kind for a in outcome.anomalies}


# ----- the captures -----------------------------------------------------------


def test_every_stopfailure_capture_classifies() -> None:
    """All 23, read from the capture files rather than typed from the spec."""
    failures = captured("StopFailure")
    assert len(failures) == 23

    for payload in failures:
        error = payload.get("error")
        assert isinstance(error, str), payload
        outcome = result(failure_error=error)
        assert isinstance(outcome.reason, StopReason)
        assert outcome.detail is not None and error in outcome.detail

    # The distribution, so a corpus that changed under us is loud, not silent.
    seen = [str(payload["error"]) for payload in failures]
    assert seen.count("model_not_found") == 14
    assert seen.count("server_error") == 2
    assert seen.count("authentication_failed") == 2
    assert seen.count("unknown") == 1


def test_every_sessionend_capture_classifies() -> None:
    """All 50 of corpus 1 plus corpus 2's 16 — including the only `resume` and
    `logout` captures that exist anywhere."""
    ends = captured("SessionEnd")
    assert len(ends) == 68

    seen = [str(payload.get("reason")) for payload in ends]
    assert seen.count("other") == 59
    assert seen.count("clear") == 3
    assert seen.count("prompt_input_exit") == 4
    assert seen.count("resume") == 1
    assert seen.count("logout") == 1

    for payload in ends:
        outcome = result(end_reason=str(payload.get("reason")), ending=TurnEnding.ABSENT)
        assert outcome.reason is None or isinstance(outcome.reason, StopReason)


def test_http529_capture_is_server_error() -> None:
    """§8's row says `overloaded`; the capture says `server_error`, and the
    capture is right — `overloaded` has **zero** assignments in the binary."""
    server_errors = [
        payload for payload in captured("StopFailure") if payload.get("error") == "server_error"
    ]
    assert len(server_errors) == 2
    assert any("529" in json.dumps(payload) for payload in server_errors)
    assert result(failure_error="server_error").reason is StopReason.SERVER_ERROR

    # …and the unverified `overloaded` row still maps, because a 529 *could*
    # arrive that way on another account shape. It is marked, not deleted.
    assert result(failure_error="overloaded").reason is StopReason.RATE_LIMITED


def test_plain_400_capture_is_unknown_and_counted() -> None:
    """The engine's own "I don't know" — a **mapped** row, distinct from ours."""
    plain = [p for p in captured("StopFailure") if p.get("error") == "unknown"]
    assert len(plain) == 1

    outcome = result(failure_error="unknown")
    assert outcome.reason is StopReason.UNKNOWN
    # Mapped, so it is NOT an unmapped-value anomaly: the engine answered, and
    # its answer was "unknown". Conflating the two hides which is which.
    assert AnomalyKind.STOP_UNMAPPED_VALUE not in {a.kind for a in outcome.anomalies}
    assert outcome.detail is not None


def test_other_defers_and_is_not_an_unknown() -> None:
    """DP8 — 47 of 50 corpus captures, and §8 has no row for it.

    It says the process ended and nothing about why, so it **defers** to the
    completeness split. The defer is counted under its own kind: a reader who
    sees it as an unknown goes looking for a missing rule that does not exist.
    """
    outcome = result(end_reason="other", ending=TurnEnding.ENDED_TURN)

    assert outcome.reason is None
    kinds = {anomaly.kind for anomaly in outcome.anomalies}
    assert AnomalyKind.STOP_DEFERRED_VALUE in kinds
    assert AnomalyKind.STOP_UNMAPPED_VALUE not in kinds


def test_unmapped_error_is_unknown_and_counted() -> None:
    """Principle 5: a value no row claims is `unknown` **and** an anomaly, and
    the detail names the actual value so the backlog item is actionable."""
    outcome = result(failure_error="a_reason_from_a_later_engine")

    assert outcome.reason is StopReason.UNKNOWN
    assert AnomalyKind.STOP_UNMAPPED_VALUE in {a.kind for a in outcome.anomalies}
    assert "a_reason_from_a_later_engine" in " ".join(a.detail for a in outcome.anomalies)


def test_unmapped_session_end_reason_is_unknown_and_counted() -> None:
    outcome = result(end_reason="a_reason_from_a_later_engine", ending=TurnEnding.ENDED_TURN)
    assert outcome.reason is StopReason.UNKNOWN
    assert AnomalyKind.STOP_UNMAPPED_VALUE in {a.kind for a in outcome.anomalies}


def test_resume_says_what_it_actually_means() -> None:
    """E-M2-9: §8's name misleads. The same pane continues as a **different**
    session id, and the detail has to say so or a reader infers a move."""
    outcome = result(end_reason="resume", ending=TurnEnding.ABSENT)
    assert outcome.reason is StopReason.RESUMED_ELSEWHERE
    assert outcome.detail is not None
    assert "new session id" in outcome.detail


def test_logout_is_an_error_bucket_reason() -> None:
    assert result(end_reason="logout").reason is StopReason.LOGGED_OUT


# ----- the two bounded rows ---------------------------------------------------


def test_benign_auto_compact_is_not_context_exhausted() -> None:
    """C12 over `autocompact-real-*` — the exact sequence that made revision 2
    self-contradictory: `PreCompact{auto}` -> `MessageDisplay` -> `Stop`, with
    the mark still set when the classifying stop arrives.

    The real capture is replayed as a sequence so the *shape* is the corpus's,
    not a claim about it: 2 of 3 real-API turns compact benignly.
    """
    events = _sequence("autocompact-real-*")
    assert events.count(("PreCompact", "auto")) >= 3
    # The benign pattern: a `PreCompact{auto}` with a later turn ending.
    assert ("Stop", None) in events

    outcome = result(auto_compact_pending=True, ending=TurnEnding.ENDED_TURN)
    assert outcome.reason is not StopReason.CONTEXT_EXHAUSTED
    assert outcome.reason is None  # deferred to the completeness split


def test_kill_during_compaction_is_context_exhausted() -> None:
    """E-M2-8 over `lifecycle-end-*`: `PreCompact{auto}` then a session ending
    with no `PostCompact` between them. The one positive fixture."""
    events = _sequence("lifecycle-end-*")
    compacts = [index for index, event in enumerate(events) if event == ("PreCompact", "auto")]
    ends = [index for index, event in enumerate(events) if event[0] == "SessionEnd"]
    assert compacts and ends
    last_compact = compacts[-1]
    assert not any(
        event[0] == "PostCompact" for event in events[last_compact:]
    ), "the capture no longer holds a death mid-compaction — re-probe"
    assert any(index > last_compact for index in ends)

    outcome = result(auto_compact_pending=True, end_reason="other", ending=TurnEnding.ABSENT)
    assert outcome.reason is StopReason.CONTEXT_EXHAUSTED


def test_compaction_bound_requires_an_end_reason() -> None:
    """r3 BLOCKING 1, guard 2 — §8's word is *death*, and the death path is the
    one carrying a session ending. The same evidence without it must not
    classify, or the bound fires on every healthy compacted turn."""
    without = result(auto_compact_pending=True, end_reason=None, ending=TurnEnding.ABSENT)
    assert without.reason is not StopReason.CONTEXT_EXHAUSTED

    with_it = result(auto_compact_pending=True, end_reason="other", ending=TurnEnding.ABSENT)
    assert with_it.reason is StopReason.CONTEXT_EXHAUSTED


def test_quota_rule_reads_only_the_notification_type() -> None:
    """G-M2-1: the quota mark is set from the notification **type** alone.

    No payload field is read, because none has been captured. A resume time we
    have never seen is a field we would be inventing, and §8 would display it.
    """
    assert result(quota_notice=True, ending=TurnEnding.ABSENT).reason is StopReason.QUOTA_PAUSED

    source = Path(stop_map.__file__).read_text(encoding="utf-8")
    for forbidden in ("resetsAt", "resets_at", "retry_after", "retryAfter", "resume_at"):
        assert forbidden not in source


def test_observed_exit_without_a_stop_event_is_honest_about_the_exit_code() -> None:
    """C13 — the pidfd probe gives an exit *time* and never an exit *code*.

    `waitid(P_PIDFD)` returns `ChildProcessError` for a process we did not
    spawn, which is exactly why `crashed` and `stopped` are not separable at
    M2. The verdict says so instead of picking one.
    """
    results = json.loads(
        (PROBES / "gap-fill/pidfd-pty-20260914T175854Z/results.json").read_text(encoding="utf-8")
    )
    observed = results["pidfd_exit_via_trust_refusal"]
    assert observed["is_our_child"] is False
    assert "ChildProcessError" in observed["waitid_P_PIDFD"]
    assert observed["poll_after_ms"] > 0  # an exit *time* is observable

    outcome = result(process_exit_observed=True, exit_code=None)
    assert outcome.reason is StopReason.UNKNOWN
    assert outcome.detail is not None
    assert "exit code" in outcome.detail and "C13" in outcome.detail
    assert AnomalyKind.EXIT_CODE_UNOBSERVABLE in {a.kind for a in outcome.anomalies}


def test_crashed_and_killed_are_never_produced() -> None:
    """P-M2-12 — the honest form of G-M2-2/4/6. `crashed` needs an exit code
    C13 says is not observable; `killed` needs M4's `action_log`; `derailed`
    has no mechanical detector. All three exist in the vocabulary and are
    unreachable, and a test is the only thing that keeps that true."""
    unreachable = {StopReason.CRASHED, StopReason.KILLED, StopReason.DERAILED}
    produced = {
        result(
            failure_error=error,
            end_reason=reason,
            ending=ending,
            auto_compact_pending=compact,
            quota_notice=quota,
            process_exit_observed=exited,
            exit_code=code,
        ).reason
        for error in (*ERROR_ENUM, None, "future")
        for reason in (*REASON_ENUM, None)
        for ending in TurnEnding
        for compact in (True, False)
        for quota in (True, False)
        for exited in (True, False)
        for code in (None, 0, 137)
    }
    assert produced & unreachable == set()


# ----- K1's only mechanical enforcement ---------------------------------------


def test_every_stop_rule_cites_an_existing_section() -> None:
    """P-M2-13 — the same enforcement M1 gave Table B: a row's `evidence` must
    name a heading that **exists** in `data-schemas.md`. It is the only
    mechanical check behind the project's first hard rule (K1)."""
    headings = {
        line.lstrip("#").strip()
        for line in SCHEMAS.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }
    assert len(headings) > 50

    # The three bounded rows are included deliberately: a rule that is a
    # property of the function still rests on a capture, and K1 does not stop
    # at the rows that happen to be a lookup.
    assert len(BOUNDED_RULES) == 3
    for rule in (*ERROR_RULES, *REASON_RULES, *BOUNDED_RULES):
        assert rule.evidence, f"{rule.value} cites nothing"
        cited = rule.evidence.lstrip("§").strip()
        assert cited in headings, f"{rule.value} cites {rule.evidence!r}, not a section"


def test_unverified_rows_are_marked() -> None:
    """G-M2-5: five rows ship from the binary enum with **no capture**.

    The marker is read by a test so the honesty cannot be quietly deleted —
    which is the difference between a known gap and a silent assumption.
    """
    unverified = {rule.value for rule in ERROR_RULES if not rule.verified}
    assert unverified == {
        "overloaded",
        "oauth_org_not_allowed",
        "verification_required",
        "cloud_credential_error",
        "account_on_hold",
    }
    captured_errors = {str(p.get("error")) for p in captured("StopFailure")}
    assert unverified & captured_errors == set(), "a marked row now HAS a capture"

    verified = {rule.value for rule in ERROR_RULES if rule.verified}
    assert verified == captured_errors


def test_no_rule_references_the_hook_payloads_stop_reason() -> None:
    """P-M2-5 / K15 / D46 — the field does not exist. Not in 26 captures, not
    in the CLI's own zod schema, and therefore not in this table."""
    source = Path(stop_map.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert "stop_reason" not in literals

    # …and it is absent from the 26 `Stop` captures, which is *why*.
    stops = captured("Stop")
    assert len(stops) >= 26
    assert not any("stop_reason" in payload for payload in stops)


def test_the_map_reads_the_captured_field_names() -> None:
    """The spec had three wrong (`error_type`, `end_reason`, `start_reason`).

    The parameter names here are neutral by construction, so the check is on
    the captures: `error` and `reason` are the keys that exist.
    """
    for payload in captured("StopFailure"):
        assert "error" in payload and "error_type" not in payload
    for payload in captured("SessionEnd"):
        assert "reason" in payload and "end_reason" not in payload


def _sequence(pattern: str) -> list[tuple[str, str | None]]:
    """`(hook_event_name, trigger)` for one gap-fill run, in capture order."""
    matches = sorted(PROBES.glob(f"gap-fill/{pattern}/hooks.jsonl"))
    assert matches, pattern
    events: list[tuple[str, str | None]] = []
    for line in matches[0].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line).get("payload", {})
        trigger = payload.get("trigger")
        events.append(
            (str(payload.get("hook_event_name")), trigger if isinstance(trigger, str) else None)
        )
    return events


@pytest.mark.parametrize("value", ERROR_ENUM)
def test_each_error_value_has_exactly_one_row(value: str) -> None:
    assert len([rule for rule in ERROR_RULES if rule.value == value]) == 1


@pytest.mark.parametrize("value", REASON_ENUM)
def test_each_reason_value_has_exactly_one_row(value: str) -> None:
    assert len([rule for rule in REASON_RULES if rule.value == value]) == 1
