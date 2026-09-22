"""S4 — the Needs-You rail, fed by three milestones at once.

§12 puts the rail on **every** page and forbids generic text: *"the actual ask
on each row — never 'session needs attention'"*. Its rows are supposed to come
from M2's signals, M3's owned sessions and M4's approvals **simultaneously**,
and the spec's own mock says so in three lines:

    ● 3 NEED YOU    payments-api · permission: Bash(git push) [→]
                    billing-api · PROJ-71937 · question       [→]
                    1 approval pending · work_item_set_status [→]

**Deterministic only.** This host has no browser, so every assertion here is
against the **projection** — `fleet_summary()["needs_you"]` — and never against
the render. `tests/web/test_rail.py` already scans `rail.js`; what nothing
asserted is what the renderer is *handed*.

---

## The defect this scenario found, and the repair it now asserts

`rail.js` renders `fleet_summary`'s `needs_you` list and — in its own words —
**"composes nothing"**. `fleet_summary` builds that list from one place: rows
whose `effective_state` is `SessionState.NEEDS_YOU`, projected through
`project_needs_you`, which whitelists five session columns. There is no approval
in it, no reader of `ApprovalStore.pending()` anywhere in `tools_m1.py`, and the
composition hands `fleet_summary` a `Store` and a clock and nothing else.

So a pending approval — §11's card, the thing a person must answer for a blocked
master turn to continue — was **invisible on every page's rail**. The rail's own
source comments say M4 was to add it (*"M4 adds approvals and, behind a user
setting, a notification…"*); it was not added, and nothing failed.

The repair is a **composition**, not an import-down: `build_read_tools` now takes
a `pending_approvals` reader and `compose_tool_surface` hands it the one
`ApprovalStore` this process gates through, so `fleet_summary` projects §12's
third row kind beside the two it already had. `rail.js` is **byte-unchanged** —
it renders `title · needs_you_reason` and an approval row fills both, which is
exactly the pair §12's mock draws.

Driven here with a **real card raised through the shipped gate**, so the arrival
is measured rather than read off the source: the card is asserted present in
`approvals.pending()` first, and only then asserted present in the projection the
rail is handed.

*Lying implementations this now catches:*

* a rail row whose ask is a category rather than the ask — every row's
  `needs_you_reason` is compared against the text its own source wrote, and the
  approval row's pair is compared against §12's own mock line;
* a count that is not the row count;
* an empty rail indistinguishable from an unread one — both states are driven
  and the difference is asserted at the projection, which is where `rail.js`'s
  three-way branch reads it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from shepherd.core.signals import Signal, SignalKind
from shepherd.core.states import Origin, Ownership
from shepherd.signals.fold import fold
from shepherd.store.db import Store
from shepherd.toolsurface.approvals import ApprovalOutcome
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_m1 import project_needs_you
from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, Failure

from ._gate import ARRIVAL_TIMEOUT_S
from .conftest import World

NOW = "2026-09-18T10:00:00Z"

#: The two asks, each in the voice §12 demands. They are **different strings**
#: so a rail that rendered one row's ask onto both would be caught, and neither
#: is a category: `"session needs attention"` is the wording the spec forbids and
#: `tests/web/test_rail.py` fails the build on.
SIGNAL_ASK = "permission: Bash(git push)"
DIALOG_ASK = "permission dialog open: Edit(src/shepherd/store/db.py)"


@dataclass(frozen=True)
class Rail:
    """One composed build with all three sources driven into it."""

    world: World
    from_m2: str
    """The session id whose `needs_you` came from an M2 signal, folded."""
    from_m3: str
    """The owned session id M3 spawned into a dialog."""


def context(audience: Audience, correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=audience, caller_id=f"qa-{audience.value}", correlation_id=correlation_id
    )


def summary(world: World) -> Mapping[str, object]:
    """`fleet_summary` through the shipped `invoke()`, as the page reads it."""
    result = invoke("fleet_summary", {}, context(Audience.HUMAN, "s4-summary"))
    assert result.ok is True, f"fleet_summary failed: {result.error}"
    return cast("Mapping[str, object]", result.data)


def rows(world: World) -> list[Mapping[str, object]]:
    listed = summary(world)["needs_you"]
    assert isinstance(listed, list), f"needs_you is not a list: {listed!r}"
    return [cast("Mapping[str, object]", row) for row in listed]


def a_session(store: Store, tmp_path: Path, name: str, ownership: Ownership) -> str:
    workspace = store.create_project(name=name, description=None)
    session = store.register_session(
        engine_session_id=f"engine-{name}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=str(tmp_path / name),
        started_at=NOW,
        origin=Origin.EXTERNAL if ownership is Ownership.ATTACHED else Origin.USER_UI,
        ownership=ownership,
    )
    return session.id


def block_it(store: Store, session_id: str, ask: str) -> None:
    """Drive M2's own fold to put a row into `needs_you` with its real ask.

    `fold(NEEDS_INPUT)` → `FoldDelta(state=NEEDS_YOU, needs_you_reason=read_ask)`
    is the shipped rule; the delta is applied through the store's own verb. A
    `FoldDelta` written here by hand would be this test stating the rule the
    rule is supposed to state.
    """
    prior = store.snapshot(session_id)
    assert prior is not None
    result = fold(
        Signal(
            kind=SignalKind.NEEDS_INPUT,
            engine_session_id=f"engine-{session_id}",
            cwd="/does/not/matter",
            transcript_path="",
            received_at=NOW,
            fields={"ask": ask},
            raw_kind="opaque-to-the-fold",
        ),
        prior,
        NOW,
    )
    store.apply_fold_delta(session_id, result.delta)


@pytest.fixture()
def rail(world: World, tmp_path: Path) -> Iterator[Rail]:
    world.compose()
    from_m2 = a_session(world.store, tmp_path, "payments-api", Ownership.ATTACHED)
    from_m3 = a_session(world.store, tmp_path, "billing-api", Ownership.OWNED)
    block_it(world.store, from_m2, SIGNAL_ASK)
    block_it(world.store, from_m3, DIALOG_ASK)
    yield Rail(world=world, from_m2=from_m2, from_m3=from_m3)


# ----- the two sources that do reach the rail --------------------------------


def test_the_rail_carries_a_row_per_blocked_session_with_its_own_ask(
    rail: Rail,
) -> None:
    """M2's signal and M3's owned session, side by side, each naming its own ask.

    The asks are compared as a **set**, so a projection that repeated one row's
    reason onto both is caught, and a count is never asserted as a literal — it
    is the size of the set this test drove in.
    """
    listed = rows(rail.world)
    assert {row["session_id"] for row in listed} == {rail.from_m2, rail.from_m3}
    assert {row["needs_you_reason"] for row in listed} == {SIGNAL_ASK, DIALOG_ASK}
    by_id = {row["session_id"]: row for row in listed}
    assert by_id[rail.from_m2]["needs_you_reason"] == SIGNAL_ASK
    assert by_id[rail.from_m3]["needs_you_reason"] == DIALOG_ASK
    # …and every row names its workspace, which is the other half of §12's line.
    assert all(row["workspace_name"] for row in listed)


def test_the_rails_row_shape_is_the_projections_own(rail: Rail) -> None:
    """The keys `rail.js` reads are the keys the projection promises.

    Enumerated from `project_needs_you` applied to a real fleet row rather than
    written out here: a whitelist restated in a test is a second whitelist, and
    the two drift the first time a column is added.
    """
    listed = rows(rail.world)
    fleet = {row.session_id: row for row in rail.world.store.fleet()}
    expected = set(project_needs_you(fleet[rail.from_m2]))
    assert expected, "project_needs_you produced no keys at all"
    assert all(set(row) == expected for row in listed)
    # The three §12 needs by name, so a projection that dropped the ask while
    # keeping its shape is still caught.
    assert {"session_id", "title", "needs_you_reason"} <= expected


def test_an_empty_rail_is_distinguishable_from_an_unread_one(world: World) -> None:
    """`rail.js`'s three-way branch, at the projection it branches on.

    `!summary || !Array.isArray(summary.needs_you)` → *unknown*; `length === 0`
    → the 4 px green line; otherwise the amber bar. So the projection has to
    make **empty** and **absent** different values, and this drives both: a
    composed read with nothing blocked, and a read that failed.
    """
    world.compose()
    empty = summary(world)["needs_you"]
    assert empty == [], f"the fleet was not empty to begin with: {empty!r}"
    assert isinstance(empty, list), "an empty rail must still be a list, not null"

    # The absent state, reached the way a page reaches it: a read that failed.
    # `Failure.UNAVAILABLE` carries `data=None`, which is `!summary` in the
    # renderer — the third branch, and a different value from `[]`.
    unread = invoke("fleet_summary", {}, context(Audience.SESSION, "s4-unread"))
    assert unread.ok is False and unread.failure is Failure.UNAVAILABLE, (
        "fleet_summary now answers the SESSION audience; pick another closed door"
    )
    assert unread.data is None


# ----- the third source, and where it stops ----------------------------------


def test_a_pending_approval_reaches_the_needs_you_rail(rail: Rail) -> None:
    """**D2's repair, driven.** §12's third row kind, on the rail at last.

    A real card, raised through the shipped gate by a real destructive call on
    another thread. Arrival first — the card is asserted **pending** on the
    composition's own store — and only then is its presence in the rail the page
    is handed asserted.

    The row is compared against §12's own mock line, reassembled the way
    `rail.js` reassembles it (`titleOf(row)` then `askOf(row)`, which is what
    that module renders and this test may not restate differently). The count is
    the **row count**, derived from what this test drove in, never a literal.
    """
    world = rail.world
    plane = _plane()
    world.store.set_app_state(AUTONOMY_LEVEL_KEY, int(AutonomyLevel.LEVEL_2))
    destructive = next(
        tool
        for tool in registered_tools().values()
        if tool.blast_class is BlastClass.LOCAL_DESTRUCTIVE
        and Audience.MASTER in tool.audiences
    )
    required = tuple(destructive.input_schema.get("required", ()))  # type: ignore[arg-type]
    args = {key: "no-such-session" for key in required}

    before = rows(world)
    assert {row["session_id"] for row in before} == {rail.from_m2, rail.from_m3}, (
        "the rail was not the two session rows before the card was raised"
    )

    caller = threading.Thread(
        target=lambda: invoke(destructive.name, args, context(Audience.MASTER, "s4-card")),
        name="s4-blocked-call",
        daemon=True,
    )
    caller.start()
    try:
        waiter = threading.Event()
        card = None
        for _ in range(int(ARRIVAL_TIMEOUT_S * 200)):
            pending = plane.approvals.pending()
            if pending:
                card = pending[0]
                break
            waiter.wait(0.005)
        assert card is not None, "no card was raised; this proves nothing about the rail"
        assert card.tool == destructive.name

        # The rail, read while the card is genuinely pending.
        listed = rows(world)
        session_rows = [row for row in listed if row["session_id"] is not None]
        approval_rows = [row for row in listed if row["session_id"] is None]
        assert {row["session_id"] for row in session_rows} == {rail.from_m2, rail.from_m3}, (
            "the approval row displaced a session row"
        )
        assert len(approval_rows) == len(plane.approvals.pending()), (
            "the rail's approval rows are not one per pending card"
        )
        assert len(listed) == len(session_rows) + len(approval_rows)

        # §12's own third line, rebuilt the way `rail.js` renders a row.
        approval = approval_rows[0]
        rendered = f"{approval['title']} · {approval['needs_you_reason']}"
        assert rendered == f"1 approval pending · {card.tool}", rendered
        assert card.tool in str(approval["needs_you_reason"]), (
            "the approval row does not name the tool that is waiting — §12 forbids"
            " a category where the actual ask belongs"
        )

        # One row shape for both kinds, derived from the projection rather than
        # written out — `rail.js` composes nothing and must not have to branch.
        fleet = {row.session_id: row for row in world.store.fleet()}
        expected = set(project_needs_you(fleet[rail.from_m2]))
        assert expected, "project_needs_you produced no keys at all"
        assert all(set(row) == expected for row in listed), [sorted(row) for row in listed]
    finally:
        plane.approvals.decide(card.id, ApprovalOutcome.REJECTED) if card else None
        caller.join(ARRIVAL_TIMEOUT_S)
        assert not caller.is_alive(), "the blocked call was never released"

    # Absence after arrival: a decided card leaves the rail.
    after = rows(world)
    assert {row["session_id"] for row in after} == {rail.from_m2, rail.from_m3}
    assert [row for row in after if row["session_id"] is None] == [], (
        "a decided approval is still on the rail"
    )


def _plane() -> object:
    from shepherd.toolsurface.compose import master_plane

    plane = master_plane()
    assert plane is not None, "the composition installed no plane"
    return plane
