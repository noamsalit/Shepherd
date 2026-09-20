"""Installing the chokepoint in a test that composes a tool surface (DP13, T6).

**Why any of these tests needed a line at all.** Before T6, `invoke()` ran every
registered tool with no gate and no audit log; after it, a tool whose blast class
is outside `GATE_FREE_CLASSES` is **refused** when no chokepoint is installed.
Any test that registers a `local_write` or `local_destructive` tool and calls
`invoke()` is standing in for a composition root, and under DP13 a composition
root installs a chokepoint. That is the fix the plan's Exit Criteria names by
name — *"that test is fixed by installing one, never by relaxing the rule"*.

**It installs the shipped gate, not a permissive stub.** `build_authorizer` over
a real `ApprovalStore` at `LEVEL_3`, which §11's table auto-approves for every
class and audience, so nothing here blocks and nothing here hangs — and the
suites that drive the M1/M3 tools now cross the *real* gate and produce *real*
audit records on the way. A stub returning `allowed=True` would have been a
second gate, and the tests would then prove the stub (D42, and P-M4-4's trap one
layer up).

One definition, imported by every caller, rather than five copies of a
permissive lambda: a fixture copied into five files is five things that can
drift, and this repo has paid for that shape twice already (RD-T4-3, RD-T5-5).
"""

from __future__ import annotations

from shepherd.core.clock import utc_now
from shepherd.toolsurface.approvals import ApprovalStore, build_authorizer
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import install_chokepoint
from shepherd.toolsurface.types import AuditRecord


def install_test_chokepoint(
    level: AutonomyLevel = AutonomyLevel.LEVEL_3,
) -> list[AuditRecord]:
    """Install the shipped gate and a collecting sink; return the sink's list.

    The list is live: a caller that wants to assert on what was audited reads it
    after the call, and a caller that only needed `invoke()` to work ignores it.
    """
    records: list[AuditRecord] = []
    install_chokepoint(
        build_authorizer(
            store=ApprovalStore(),
            level=lambda: level,
            publish=lambda event: 0,
            bump=lambda kind: None,
            now=utc_now,
        ),
        records.append,
    )
    return records
