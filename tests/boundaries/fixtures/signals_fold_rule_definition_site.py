# NEGATIVE fixture (C6): the definition site. `signals/rules.py` declares the
# real ADR-6 FoldRule, so a bare `FoldRule(...)` here means our type.
from dataclasses import dataclass

from shepherd.core.signals import SignalKind


@dataclass(frozen=True)
class FoldRule:
    kind: SignalKind
    emits: tuple[str, ...]
    evidence: str


RULES = (FoldRule(kind=SignalKind.NEEDS_INPUT, emits=(), evidence="§Notification"),)
