"""Planted violation, frozen as a fixture: the gate reaching for a clock.

`decide()` is a pure function of three enum values, which is what makes it
provable by table over the enumerated product (P-M4-1, DP11). A clock — or the
registry, or anything else below L4 — makes it a function of the world instead,
and the table stops being a proof of anything. `shepherd.core.clock` is the
specific import the purity scan exists to catch, in the ordinary from-import
spelling.

**Inert.** Nothing imports this module. It is read as text and parsed as an AST,
and it is never on an import path the suite executes (CLAUDE.md, 2026-09-17: a
shadow tree isolates files, not effects, and the only safe planted violation is
one that never runs).
"""

from __future__ import annotations

from shepherd.core.clock import Clock


def decide(clock: Clock) -> str:
    return clock.now()
