"""The public classifier, and D34's one named call site (T9).

One pure function of one immutable record. Everything it needs was assembled
at the stop (ADR-M2-1), so it opens nothing, asks nothing and can be replayed
months later against a log line.

**The composition, in order:**

1. the adapter decided mechanically → that reason, `decided_by = mechanical`,
   confidence 1.0. §8: *"that short-circuit is what keeps the common case
   free"*;
2. the adapter **deferred** and the turn ended cleanly → `classify_end_turn`,
   `decided_by = heuristic`, confidence from the split;
3. otherwise → `unknown`, counted. DP7: a turn ending nobody mapped decides
   nothing, and saying nothing is not the same as saying "fine";
4. the bucket and the `next_actions[]` come free in the same pass (D21).

**What is deliberately absent, and why the absence is tested.** There is no
`Classifier` protocol, no model id, no credential lookup, no prompt, no client
and no second call site of `classify_end_turn`. D34 defers the LLM lane, and an
interface with zero implementations behind it is D9's mistake in its purest
form. Building the lane means filling **one function** in; nothing else in the
system moves, and `test_classify_end_turn_has_one_call_site` plus
`test_no_llm_lane_exists` are what keep that true.
"""

from __future__ import annotations

from shepherd.core.stops import (
    DecidedBy,
    StopEvidence,
    StopReason,
    TurnEnding,
    Verdict,
)
from shepherd.signals.heuristics import SplitResult, split_completeness
from shepherd.signals.stop_rules import BUCKET_OF, default_actions

__all__ = ["classify", "classify_end_turn"]

#: §8's "mechanical, confidence 1.0".
MECHANICAL_CONFIDENCE = 1.0

#: `unknown` is the one answer that must never read as settled: it *is* the
#: tuning backlog, and a backlog whose rows claim confidence 1.0 is a backlog
#: nobody works. `decided_by` is still `mechanical` — a rule wrote it — and
#: that pairing is exactly ADR-M2-5's distinction between "a rule said unknown"
#: and "no verdict ever arrived" (which is `unclassified`, and not a verdict).
UNKNOWN_CONFIDENCE = 0.0

WHY_NO_ENDING = "nothing established how the turn ended"
WHY_UNREADABLE = "this stop record could not be read"


def classify_end_turn(evidence: StopEvidence) -> SplitResult:
    """D34's one named call site for the deferred LLM verdict lane.

    Today this returns the heuristic result unchanged. Building the lane means
    filling this function in; nothing else in the system moves. There is no
    `Classifier` seam, deliberately — an interface with zero implementations
    behind it is D9's mistake in its purest form.
    """
    return split_completeness(evidence)


def classify(evidence: StopEvidence) -> Verdict:
    """One stop record in, one `Verdict` out. Pure, deterministic, never raises.

    **The `except` is a boundary guard, not a blanket one** (P-M2-2). A record
    reaching this function has usually just been built in memory — but it can
    equally be a JSON line some *earlier build* wrote to the stop log, and
    `shepherd replay` must survive one unreadable record out of 412 rather than
    dying on it. An unreadable record becomes `unknown` at confidence 0, which
    the fleet counts and `replay` can act on; a readable one takes the ordinary
    path, so a genuine bug in a rule is never laundered into a green row.
    """
    try:
        return _classify(evidence)
    except Exception:  # the trust boundary; see the docstring above
        return _verdict(
            StopReason.UNKNOWN,
            why=WHY_UNREADABLE,
            confidence=UNKNOWN_CONFIDENCE,
            decided_by=DecidedBy.MECHANICAL,
            missing=(),
        )


def _classify(evidence: StopEvidence) -> Verdict:
    mechanical = evidence.mechanical
    if mechanical is not None:
        reason = StopReason(mechanical)
        return _verdict(
            reason,
            why=evidence.mechanical_detail or _mechanical_why(reason),
            confidence=(
                UNKNOWN_CONFIDENCE
                if reason is StopReason.UNKNOWN
                else MECHANICAL_CONFIDENCE
            ),
            decided_by=DecidedBy.MECHANICAL,
            missing=(),
        )

    if evidence.tail.ending is TurnEnding.ENDED_TURN:
        split = classify_end_turn(evidence)
        return _verdict(
            split.reason,
            why=split.why,
            confidence=split.confidence,
            decided_by=DecidedBy.HEURISTIC,
            missing=split.missing,
        )

    return _verdict(
        StopReason.UNKNOWN,
        why=WHY_NO_ENDING,
        confidence=UNKNOWN_CONFIDENCE,
        decided_by=DecidedBy.MECHANICAL,
        missing=(),
    )


def _verdict(
    reason: StopReason,
    *,
    why: str,
    confidence: float,
    decided_by: DecidedBy,
    missing: tuple[str, ...],
) -> Verdict:
    """The bucket and the actions, computed free in the same pass (D21).

    `waiting_on` is `None` on every verdict M2 can produce (G-M2-7):
    `blocked_external`'s two buildable sources are M4's `report_blocked()` and
    M5's work-item status, so nothing here can name what a session waits on
    without guessing — and the action text says so rather than showing a blank.
    """
    waiting_on: str | None = None
    return Verdict(
        stop_reason=reason,
        bucket=BUCKET_OF[reason],
        why=why,
        confidence=confidence,
        decided_by=decided_by,
        next_actions=default_actions(
            reason, confidence=confidence, missing=missing, waiting_on=waiting_on
        ),
        waiting_on=waiting_on,
        missing=missing,
    )


def _mechanical_why(reason: StopReason) -> str:
    """A sentence, when the adapter had no detail to give.

    Never the empty string: §7's `why` is rendered to a human, and a blank cell
    reads as a bug in the page rather than as silence from a rule.
    """
    return f"the adapter resolved this stop as {reason.value.replace('_', ' ')}"
