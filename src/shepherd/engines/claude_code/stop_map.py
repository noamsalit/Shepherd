"""§8's mechanical stop-reason table, as code (T4, ADR-M2-2).

**This is the differentiator's core**, and it lives in the adapter because D46
keys it on three *engine* fields — the stop-failure error, the session-ending
reason, and the transcript's turn ending — and §5.0/K13 forbid those names in
`signals/`. Putting the table in `signals/` keyed on a neutral field name would
be the same leak wearing a neutral key: the *values* would still be the
engine's. The neutral key is not the point; the neutral vocabulary is.

**A table, not branches.** One row per enum value, each carrying the
`data-schemas.md` section it came from, because a rule that cannot cite a
capture is a shape somebody typed from memory (K1, D41 — the spec had three of
these field names wrong). `test_every_stop_rule_cites_an_existing_section` is
the only mechanical enforcement of that rule, exactly as M1's Table B has.

**The precedence is a property of the function, not of a row**, and it was
measured rather than chosen: on **23 of 23** stop-failure captures the
transcript's last assistant entry says `stop_sequence`, so reading the tail
first would classify every API failure as unknown.

    5. a quota notice        (only when no API error said otherwise)
    1. the API error         -> a row wins outright, confidence 1.0
    2. the session-ending    -> a mapped row wins; the catch-all DEFERS (DP8)
    4. the compaction bound  -> ONLY when a session ending drove the stop
    3. the turn ending       -> held call / token cap decide; a finished turn
                                DEFERS to the completeness split

Three reasons in the vocabulary are **unreachable here and say so**: `crashed`
(C13 — an attached session gives an exit *time* and never an exit *code*),
`killed` (needs M4's action log) and `derailed` (no mechanical detector
exists). `test_crashed_and_killed_are_never_produced` keeps that honest over
every combination of inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.stops import StopReason, TurnEnding


@dataclass(frozen=True)
class _Sentinel:
    """A result that is not a reason. Two of them, and they mean different
    things to whoever reads the count (principle 5)."""

    name: str


#: The value decided nothing and handed the question on. **Not** an unknown:
#: nothing failed, the answer is simply somewhere else.
DEFERS: Final = _Sentinel("defers")

#: No row claims this value. It becomes `unknown` **and** is counted, with the
#: actual value in the detail so the backlog item is actionable.
UNMAPPED: Final = _Sentinel("unmapped")


@dataclass(frozen=True)
class StopRule:
    """One row of §8's table.

    `verified` is `False` for the five rows that ship from the binary's enum
    with **no capture** (G-M2-5). Marked rather than omitted: the value exists
    in the engine, so a row is better than an unmapped surprise — and marked
    rather than silently trusted, so nobody reads it as evidence.
    """

    value: str
    reason: StopReason | _Sentinel
    evidence: str
    verified: bool


_STOP_FAILURE = "§StopFailure"
_SESSION_END = "§SessionEnd"
_ENUMERATIONS = (
    "§Enumerations (SessionStart.source, SessionEnd.reason, StopFailure.error,"
    " Notification.notification_type)"
)
_RESUME_AND_LOGOUT = "§`SessionEnd.reason` = `resume` and `logout`"
_AUTO_COMPACTION = (
    "§Auto compaction: `PreCompact{trigger:auto}` / `PostCompact`, and death mid-compaction"
)
_OBSERVED_EXIT = "§Observed process exit for a process Shepherd did not spawn (pidfd)"
_NOTIFICATION = "§Notification"

#: The 13 values of the engine's stop-failure enum — all of them, so an engine
#: upgrade that adds a fourteenth is an `UNMAPPED` with a name rather than a
#: crash. `drift_check.py` re-verifies the list against the running binary.
ERROR_RULES: tuple[StopRule, ...] = (
    StopRule("rate_limit", StopReason.RATE_LIMITED, _ENUMERATIONS, verified=True),
    # 0 assignments in the binary; a real 529 arrives as `server_error` (N7).
    StopRule("overloaded", StopReason.RATE_LIMITED, _ENUMERATIONS, verified=False),
    StopRule("authentication_failed", StopReason.AUTH_FAILED, _STOP_FAILURE, verified=True),
    StopRule("oauth_org_not_allowed", StopReason.AUTH_FAILED, _ENUMERATIONS, verified=False),
    # §8 maps neither of the next two anywhere; they exist in the enum (DP8).
    StopRule("verification_required", StopReason.AUTH_FAILED, _ENUMERATIONS, verified=False),
    StopRule("cloud_credential_error", StopReason.AUTH_FAILED, _ENUMERATIONS, verified=False),
    StopRule("account_on_hold", StopReason.ACCOUNT_BLOCKED, _ENUMERATIONS, verified=False),
    StopRule("billing_error", StopReason.ACCOUNT_BLOCKED, _STOP_FAILURE, verified=True),
    # Only a prompt-too-long 400 arrives this way; a plain 400 is `unknown`.
    StopRule("invalid_request", StopReason.BAD_REQUEST, _STOP_FAILURE, verified=True),
    StopRule("model_not_found", StopReason.BAD_REQUEST, _STOP_FAILURE, verified=True),
    StopRule("server_error", StopReason.SERVER_ERROR, _STOP_FAILURE, verified=True),
    # Arrives with no stop event at all (E-M2-2): the error decides alone.
    StopRule("max_output_tokens", StopReason.TRUNCATED, _STOP_FAILURE, verified=True),
    # The engine's own "I don't know" — MAPPED, and therefore not counted as
    # one of ours. Conflating the two hides which side the gap is on.
    StopRule("unknown", StopReason.UNKNOWN, _STOP_FAILURE, verified=True),
)

#: The 5 values of the engine's session-ending enum.
REASON_RULES: tuple[StopRule, ...] = (
    StopRule("prompt_input_exit", StopReason.USER_EXITED, _SESSION_END, verified=True),
    StopRule("clear", StopReason.CLEARED, _SESSION_END, verified=True),
    StopRule("logout", StopReason.LOGGED_OUT, _RESUME_AND_LOGOUT, verified=True),
    StopRule("resume", StopReason.RESUMED_ELSEWHERE, _RESUME_AND_LOGOUT, verified=True),
    # 47 of 50 corpus captures, and §8 has no row for it (DP8). It says the
    # process ended and nothing about why, so it defers.
    StopRule("other", DEFERS, _SESSION_END, verified=True),
)

#: The three rows that are **not** a simple lookup. They are rules of the
#: function rather than of a value, and they carry an `evidence` citation for
#: the same reason every other row does (K1): each is a bound somebody has to
#: be able to check against a capture.
BOUNDED_RULES: tuple[StopRule, ...] = (
    StopRule("auto_compaction_then_death", StopReason.CONTEXT_EXHAUSTED, _AUTO_COMPACTION, True),
    # [UNVERIFIED] payload: the mark is set from the notification *type* alone,
    # and no resume time is displayed because none has been captured (G-M2-1).
    StopRule("quota_notice", StopReason.QUOTA_PAUSED, _NOTIFICATION, False),
    StopRule("observed_exit_no_code", StopReason.UNKNOWN, _OBSERVED_EXIT, True),
)

_ERROR_BY_VALUE: Mapping[str, StopRule] = {rule.value: rule for rule in ERROR_RULES}
_REASON_BY_VALUE: Mapping[str, StopRule] = {rule.value: rule for rule in REASON_RULES}

#: ADR-M2-3's narrowing, as the map's third step. A finished turn is the one
#: ending that decides nothing here — the completeness split answers it.
_ENDING_REASONS: Mapping[TurnEnding, StopReason | _Sentinel] = {
    TurnEnding.HELD_TOOL_CALL: StopReason.STALLED_PENDING_TOOL,
    TurnEnding.HIT_TOKEN_CAP: StopReason.TRUNCATED,
    TurnEnding.ENDED_TURN: DEFERS,
    TurnEnding.OTHER: UNMAPPED,
    TurnEnding.ABSENT: UNMAPPED,
}

#: The one sentence §8 owes a reader whose session's row says `unknown` because
#: the kernel would not tell us how it died.
EXIT_CODE_UNOBSERVABLE_WHY = (
    "process exited; an attached session gives an exit time but no exit code (C13)"
)

_RESUME_DETAIL = "the session ended and continued as a new session id"


@dataclass(frozen=True)
class MechanicalResult:
    """`reason is None` means the adapter **deferred**: the completeness split
    owns the question, and nothing here failed."""

    reason: StopReason | None
    detail: str | None
    anomalies: tuple[Anomaly, ...]


def mechanical_reason(
    *,
    failure_error: str | None,
    end_reason: str | None,
    ending: TurnEnding,
    auto_compact_pending: bool,
    quota_notice: bool,
    process_exit_observed: bool,
    exit_code: int | None,
) -> MechanicalResult:
    """Engine values in, a `StopReason` or a deferral out. Pure; never raises."""
    anomalies: list[Anomaly] = []

    # 5 — a quota notice decides only when no API error did.
    if quota_notice and not failure_error:
        return _decided(StopReason.QUOTA_PAUSED, "a quota notice arrived and no turn followed")

    # 1 — the API error, which outranks everything the transcript could say.
    if failure_error:
        rule = _ERROR_BY_VALUE.get(failure_error)
        if rule is None:
            anomalies.append(
                _anomaly(
                    AnomalyKind.STOP_UNMAPPED_VALUE,
                    f"no row claims the stop failure {failure_error!r}",
                )
            )
            return _decided(
                StopReason.UNKNOWN, f"the engine reported {failure_error!r}", anomalies
            )
        if isinstance(rule.reason, StopReason):
            return _decided(rule.reason, f"the engine reported {failure_error!r}", anomalies)
        # No error row defers today (`test_no_error_row_defers`). If one ever
        # does, it hands the question to the next step rather than to a
        # narrowing `assert` that vanishes under `python -O`.

    # 2 — the session ending. The catch-all defers; an unknown spelling counts.
    if end_reason:
        rule = _REASON_BY_VALUE.get(end_reason)
        if rule is None:
            anomalies.append(
                _anomaly(
                    AnomalyKind.STOP_UNMAPPED_VALUE,
                    f"no row claims the session ending {end_reason!r}",
                )
            )
            return _decided(
                StopReason.UNKNOWN, f"the session ended as {end_reason!r}", anomalies
            )
        if isinstance(rule.reason, StopReason):
            return _decided(rule.reason, _end_detail(rule.reason, end_reason), anomalies)
        anomalies.append(
            _anomaly(
                AnomalyKind.STOP_DEFERRED_VALUE,
                f"the session ending {end_reason!r} says the process ended and nothing about why",
            )
        )

    # 4 — the compaction bound, and it needs BOTH guards (r3 BLOCKING 1).
    #
    # §8's word is *death*, and the death path is the one carrying a session
    # ending; a clean turn ending carries none. Without this guard the rule
    # fires on every healthy compacted turn, because the mark is still set when
    # the classifying stop arrives — which is how two required tests came to
    # contradict each other at revision 2. The other guard is the fold's kind
    # split (T10), and both are specified because each closes it alone.
    if auto_compact_pending and end_reason is not None:
        return _decided(
            StopReason.CONTEXT_EXHAUSTED,
            "auto-compaction started and the session died before it finished",
            anomalies,
        )

    # C13 — an observed exit with nothing else to go on. Honest, not guessed.
    if process_exit_observed and exit_code is None:
        anomalies.append(
            _anomaly(AnomalyKind.EXIT_CODE_UNOBSERVABLE, EXIT_CODE_UNOBSERVABLE_WHY)
        )
        return _decided(StopReason.UNKNOWN, EXIT_CODE_UNOBSERVABLE_WHY, anomalies)

    # 3 — the transcript's turn ending.
    outcome = _ENDING_REASONS[ending]
    if isinstance(outcome, StopReason):
        return _decided(outcome, _ending_detail(ending), anomalies)
    if outcome is DEFERS:
        return MechanicalResult(reason=None, detail=None, anomalies=tuple(anomalies))
    anomalies.append(
        _anomaly(
            AnomalyKind.STOP_UNMAPPED_VALUE,
            f"the turn ending was {ending.value!r}, so nothing established how the turn ended",
        )
    )
    return _decided(
        StopReason.UNKNOWN, "no signal established why this session stopped", anomalies
    )


def _end_detail(reason: StopReason, end_reason: str) -> str:
    """E-M2-9: `resume` misleads, so its detail says what actually happened."""
    if reason is StopReason.RESUMED_ELSEWHERE:
        return _RESUME_DETAIL
    return f"the session ended as {end_reason!r}"


def _ending_detail(ending: TurnEnding) -> str:
    if ending is TurnEnding.HELD_TOOL_CALL:
        return "the turn ended holding an unexecuted tool call"
    return "the turn ran out of output tokens"


def _decided(
    reason: StopReason, detail: str, anomalies: list[Anomaly] | None = None
) -> MechanicalResult:
    return MechanicalResult(
        reason=reason, detail=detail, anomalies=tuple(anomalies or ())
    )


def _anomaly(kind: AnomalyKind, detail: str) -> Anomaly:
    return Anomaly(kind=kind, detail=detail, engine_session_id=None)
