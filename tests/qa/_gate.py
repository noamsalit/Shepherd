"""The shipped gate, installed at a level a test chooses, with its store exposed.

**Why this exists rather than `tests/chokepoint_fixture.py`.** That fixture is
the right seam and six suites use it, but it builds its `ApprovalStore` inside
itself and hands back only the audit sink's list. At `LEVEL_3` — its default —
that is enough, because nothing ever blocks. At `LEVEL_2` a destructive call
**parks on a card for 600 s**, and a caller that cannot reach the store cannot
answer one. So this module is `install_test_chokepoint`'s own body with the
store, the stream events and the anomaly counts kept.

**It is not a second gate.** Everything here is shipped code —
`build_authorizer` over a real `ApprovalStore`, installed through the shipped
`install_chokepoint`. Nothing decides anything: the level is a value handed to
the shipped `level()` callable, exactly as `compose_tool_surface` hands it
`lambda: autonomy_level(store)`. `test_s1_gate_that_can_say_no.py::
test_this_packages_gate_agrees_with_the_shipped_fixture` drives one call through
both and compares the audit records, so *"same gate"* is an observation rather
than a claim in this docstring.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import utc_now
from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.approvals import Approval, ApprovalStore, build_authorizer
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import install_chokepoint
from shepherd.toolsurface.types import AuditRecord

#: Every wait in this package is bounded. A mutant that hangs is not a red, and
#: two M4 tasks paid for learning that. Far beyond anything here takes, far below
#: the 600 s approval deadline — the gap is what makes *"released, not timed
#: out"* an observation.
ARRIVAL_TIMEOUT_S = 10.0


@dataclass
class QaGate:
    """One installed chokepoint and everything a check needs to read off it."""

    approvals: ApprovalStore
    level: AutonomyLevel
    records: list[AuditRecord] = field(default_factory=list)
    events: list[StreamEvent] = field(default_factory=list)
    anomalies: list[AnomalyKind] = field(default_factory=list)

    def wait_for_card(self, timeout_s: float = ARRIVAL_TIMEOUT_S) -> Approval:
        """Block until exactly one card is pending. Arrival, never a sleep."""
        waiter = threading.Event()
        for _ in range(int(timeout_s * 200)):
            pending = self.approvals.pending()
            if pending:
                return pending[0]
            waiter.wait(0.005)
        raise AssertionError(f"no approval card was raised within {timeout_s}s")


def install_qa_chokepoint(level: AutonomyLevel) -> QaGate:
    """`install_test_chokepoint(level)`, with the store and the ring kept."""
    gate = QaGate(approvals=ApprovalStore(), level=level)
    install_chokepoint(
        build_authorizer(
            store=gate.approvals,
            level=lambda: gate.level,
            publish=lambda event: (gate.events.append(event), 0)[1],
            bump=gate.anomalies.append,
            now=utc_now,
        ),
        gate.records.append,
    )
    return gate
