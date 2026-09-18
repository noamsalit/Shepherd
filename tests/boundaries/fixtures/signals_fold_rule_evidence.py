# NEGATIVE fixture 1 (ADR-6, F4): the one declared structural exclusion, in its
# consumer form. A rule citing its captured evidence is clean, and must stay
# clean, or the first thing a builder does is add an exemption.
#
# The `FoldRule` name is bound from `shepherd.*` (C6): the exclusion is anchored
# to OUR type, not to any callee that happens to share its bare name.
from shepherd.core.signals import SignalKind
from shepherd.signals.rules import FoldRule

RULES = (
    FoldRule(kind=SignalKind.NEEDS_INPUT, delta_fn=None, emits=(), evidence="§Notification"),
    FoldRule(kind=SignalKind.SUBAGENT_FINISHED, delta_fn=None, emits=(), evidence="§SubagentStop"),
)
