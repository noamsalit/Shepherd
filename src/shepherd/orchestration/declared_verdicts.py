"""Verdicts the orchestration layer *declares* rather than classifies (§3 D73).

A spawn that the runner refused never produced a stop capture, so no rule in
`signals/` can reach its verdict. The spawn knows the answer outright and says
so: `decided_by = declared` at full confidence, bucketed and given its next
actions by M2's own tables, never by a copy of them. Pure: no store, no clock.
"""

from __future__ import annotations

from shepherd.core.stops import DecidedBy, StopReason, Verdict
from shepherd.signals.stop_rules import BUCKET_OF, default_actions

__all__ = ["REFUSED_CONFIDENCE", "refused_verdict"]

#: The runner said no in words; nothing about that is inferred.
REFUSED_CONFIDENCE = 1.0


def refused_verdict(reason: str) -> Verdict:
    """The ending of a row whose start was refused: `refused`, bucket `error`,
    and the refusal's own words as the `why` (capped at `WHY_MAX` by `Verdict`)."""
    return Verdict(
        stop_reason=StopReason.REFUSED,
        bucket=BUCKET_OF[StopReason.REFUSED],
        why=reason,
        confidence=REFUSED_CONFIDENCE,
        decided_by=DecidedBy.DECLARED,
        next_actions=default_actions(
            StopReason.REFUSED, confidence=REFUSED_CONFIDENCE, missing=(), waiting_on=None
        ),
        waiting_on=None,
        missing=(),
    )
