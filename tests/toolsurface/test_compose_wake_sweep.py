"""qa6 rulings P6 — the level-3 waker and the failure recorder, through the
shipped composition (D69, D79, ADR-QR-3, ADR-QR-5).

**The seam is the L4 seam**: `compose_tool_surface` wired exactly as
`daemons/plane.py` wires it, observed from outside through the sweep the root
already hands its 2 s loop, `invoke()`, the counter and the one audit reader.
A waker with passing tests and no caller is the "mechanism with no caller"
defect M4's register names, so the composed checks here are the ones that say
the sweep really reaches it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from shepherd.core.mailbox import MailboxCounts
from shepherd.core.master import MasterRuntime
from shepherd.daemons import plane
from shepherd.orchestration import wake
from shepherd.store.db import Store
from shepherd.toolsurface import compose
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY
from shepherd.toolsurface.types import Audience, CallerContext

from orchestration.test_master_turn import plant_a_waking_stop

from .test_compose_m4 import ARRIVAL_TIMEOUT_S, World, world  # noqa: F401 — `world` is a fixture

#: A message only this file could have produced; it must reach no record.
SECRET = "QA6-P6-COMPOSED-SECRET-the-prompt"


def the_plane() -> compose._MasterPlane:
    installed = compose.master_plane()
    assert installed is not None, "the composition installed no master plane"
    return installed


@pytest.fixture()
def shepherd_project(world: World) -> Iterator[Store]:
    world.store.create_project(name="shepherd", description=None)
    yield world.store


# ----- the adapter ------------------------------------------------------------


def test_the_sweep_still_returns_the_mailbox_counts_and_ticks_the_waker() -> None:
    """`sweep_and_wake` hands the loop the mailbox counts unchanged and ticks the
    waker once per pass — after the mailbox sweep, never instead of it."""
    counts = MailboxCounts(pending=3, delivered=2, deferred=1)
    order: list[str] = []

    def sweep() -> MailboxCounts:
        order.append("sweep")
        return counts

    def tick() -> bool:
        order.append("tick")
        return True

    combined = compose.sweep_and_wake(sweep, tick)

    assert combined() is counts
    assert combined() is counts
    assert order == ["sweep", "tick", "sweep", "tick"]


def test_the_waker_reads_level_3_as_the_policy_spells_it() -> None:
    """`orchestration/` may not import L4's enum, so the waker holds the
    number; this pins that the two agree."""
    assert wake.WAKE_LEVEL == int(AutonomyLevel.LEVEL_3)


# ----- the composed path ------------------------------------------------------


def test_the_composed_sweep_opens_a_wake_turn_at_level_3(
    world: World, shepherd_project: Store
) -> None:
    """The root's own sweep, at level 3, opens one unprompted turn through the
    composed driver. Arrival first: at level 2 the same sweep opens nothing."""
    store = shepherd_project
    plant_a_waking_stop(store)
    wiring = world.compose()
    driver = the_plane().driver
    try:
        assert isinstance(wiring.sweep(), MailboxCounts)
        assert world.built_for == [], "level 2 (the default) opened a wake turn"

        store.set_app_state(AUTONOMY_LEVEL_KEY, int(AutonomyLevel.LEVEL_3))
        assert isinstance(wiring.sweep(), MailboxCounts)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
        assert len(world.built_for) == 1, "the composed sweep opened no wake turn"
        assert wake.peek(store) == (), "the wake turn did not drain the set"

        assert isinstance(wiring.sweep(), MailboxCounts)
        assert len(world.built_for) == 1, "a drained set woke the master twice"
    finally:
        driver.close()


def test_the_composed_driver_counts_and_audits_a_failed_turn(world: World) -> None:
    """ADR-QR-3's wiring: a turn that fails to open bumps `master_failed` once
    and writes one `master_send` record to the real log, carrying the class
    name and never the message."""

    def build(store: Store, turn_id: str) -> MasterRuntime:
        raise RuntimeError(SECRET)

    compose.compose_tool_surface(
        world.store, world.host, world.db_path, world.ingest, build,
        plane.audit_sink(world.store, world.host),
    )
    assert world.store.list_anomaly_counts().get("master_failed", 0) == 0

    answered = invoke(
        "master_send",
        {"text": "hello"},
        CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-p6"),
    )

    assert answered.ok is True and isinstance(answered.data, dict)
    assert answered.data["started"] is False, "arrival: the turn really failed to open"
    assert world.store.list_anomaly_counts().get("master_failed") == 1
    records = read_audit_records(compose.log_root(world.host), 10)
    failed = [r for r in records if r["result"] == "failed"]
    assert len(failed) == 1, records
    assert failed[0]["tool"] == "master_send"
    assert failed[0]["actor_kind"] == "master"
    args = failed[0]["args"]
    assert isinstance(args, dict) and args["error_class"] == "RuntimeError"
    assert args["turn_id"] == failed[0]["correlation_id"]
    assert SECRET not in json.dumps(list(records), default=str)
