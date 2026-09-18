"""S5 — projection bounds, measured at 1 / 5 / 25 / 200 sessions.

**G-M4-8 is a design decision and not this pass's to close.** What this scenario
contributes is the thing the decision needs and does not have: *nothing
currently asserts any bound at any size*, and one point (200) is not a growth
curve. The shipped `test_the_master_read_tools_size_does_not_regress` pins two
numbers at one fleet size, which cannot tell a **constant** projection from a
**linear** one — and §11's promise (*"~40 lines regardless of fleet size"*,
about `fleet_summary()`) is precisely a claim about the slope.

So this file measures both projections at four sizes and asserts the **shape**
of the growth rather than a number:

* `fleet_summary` and `fleet_tree` both grow **strictly** with fleet size — so
  neither is bounded today, which is the finding;
* the growth is attributable: the `needs_you` term and the session list are the
  unbounded ones, and `anomalies` — a fixed 38-key dict — is not;
* the byte counts are **printed into the failure message either way**, so the
  numbers reach `docs/plans/m1-m4-qa/harness.md` from a run rather than from a
  memory.

The fixture is **T23's own `seed_fleet`**, imported rather than re-written: two
fleets built two ways are two fixtures, and every number the M4 ledger records
is about that one.

*Lying implementations this now catches:* a projection that was capped for
`fleet_summary` and not for the master's copy of it; a cap applied silently, with
no counted truncation — principle 5 requires *"showing 40 of 213"* rather than a
short list, and the test asserts the row count equals the fleet's own
`needs_you` population at every size.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

from shepherd.core.states import SessionState
from shepherd.store.db import Store, open_store
from shepherd.toolsurface.registry import invoke, reset_registry
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.types import Audience, CallerContext

from toolsurface.test_tools_master import seed_fleet

from ._gate import install_qa_chokepoint
from shepherd.toolsurface.policy import AutonomyLevel

#: The four sizes. 1 and 5 are the shapes a laptop sees on day one; 25 is a busy
#: afternoon; 200 is the number the M4 ledger measured. Four points, because two
#: cannot distinguish a curve from a line and one cannot distinguish either from
#: a constant.
SIZES = (1, 5, 25, 200)

MASTER = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="s5")

#: §11's own sentence, about the projection its own line names (the M4 verifier
#: corrected the attribution: spec lines 560 and 1863 both say `fleet_summary`).
SPEC_LINE_BUDGET = 40


@contextmanager
def fleet_of(tmp_path: Path, size: int) -> Iterator[Store]:
    """One fleet of exactly `size` sessions, in its own store, behind the gate.

    **A fresh store per size, not a cumulative one.** `seed_fleet` numbers its
    sessions from zero (`engine-session-0000`), so a second call re-uses the
    engine session ids it already wrote and the fleet stops growing — measured:
    seeding 1 then 4 more yields **4** sessions, not 5. Four independent fleets
    from one builder is the honest shape, and the 200-session point is then
    byte-for-byte the fixture the M4 ledger measured.
    """
    store = open_store(tmp_path / f"fleet-{size}" / "shepherd.db")
    reset_registry()
    install_qa_chokepoint(AutonomyLevel.LEVEL_2)
    register_read_tools(
        store, projects_root=tmp_path / "projects", pending_approvals=lambda: ()
    )
    try:
        seed_fleet(store, size)
        yield store
    finally:
        reset_registry()
        store.close()


def measured(store: Store, size: int) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Both projections at one fleet size, through the shipped `invoke()`."""
    summary = invoke("fleet_summary", {}, MASTER)
    tree = invoke("fleet_tree", {}, MASTER)
    assert summary.ok is True and tree.ok is True, (summary.error, tree.error)
    return (
        cast("Mapping[str, object]", summary.data),
        cast("Mapping[str, object]", tree.data),
    )


def wire_bytes(payload: Mapping[str, object]) -> int:
    """What the projection costs on the wire, in the compact encoding."""
    return len(json.dumps(payload, separators=(",", ":")).encode())


def pretty_lines(payload: Mapping[str, object]) -> int:
    """What the projection costs a reader, in lines — §11's own unit."""
    return len(json.dumps(payload, indent=2).splitlines())


def curve(tmp_path: Path) -> list[tuple[int, int, int, int, int]]:
    """`(size, summary_bytes, summary_lines, tree_bytes, needs_you_rows)` per size."""
    points = []
    for size in SIZES:
        with fleet_of(tmp_path, size) as store:
            summary, tree = measured(store, size)
            needs_you = summary["needs_you"]
            assert isinstance(needs_you, list)
            assert summary["session_count"] == size, (
                f"seeded {size} sessions, the projection counted"
                f" {summary['session_count']}"
            )
            points.append(
                (
                    size,
                    wire_bytes(summary),
                    pretty_lines(summary),
                    wire_bytes(tree),
                    len(needs_you),
                )
            )
    return points


def test_both_projections_grow_strictly_with_the_fleet(tmp_path: Path) -> None:
    """Neither projection is bounded — measured at four sizes, not argued.

    Strict growth is the assertion because it is the one that fails the day
    either projection is capped: a capped `fleet_summary` would stop growing
    between 25 and 200, and this test would go red naming the pair of sizes.
    That is the correct outcome — the cap is G-M4-8's fix and this scenario's
    job is to notice it landing.
    """
    points = curve(tmp_path)
    assert [point[0] for point in points] == list(SIZES)

    report = "\n".join(
        f"  {size:>3} sessions · summary {sb:>6} B / {sl:>4} lines"
        f" · tree {tb:>7} B · needs_you {ny}"
        for size, sb, sl, tb, ny in points
    )
    summary_bytes = [point[1] for point in points]
    tree_bytes = [point[3] for point in points]
    assert summary_bytes == sorted(summary_bytes) and len(set(summary_bytes)) == len(SIZES), (
        f"fleet_summary is no longer strictly growing — a bound may have landed:\n{report}"
    )
    assert tree_bytes == sorted(tree_bytes) and len(set(tree_bytes)) == len(SIZES), (
        f"fleet_tree is no longer strictly growing — a bound may have landed:\n{report}"
    )


def test_the_unbounded_term_is_needs_you_and_it_is_never_truncated(
    tmp_path: Path,
) -> None:
    """Attribute the growth, and prove no silent cap is hiding inside it.

    Principle 5: if a projection ever truncates, it must say *"showing 40 of
    213"* rather than hand back a short list. So the row count is compared
    against the fleet's **own** `needs_you` population, counted off the store at
    every size — which is a silent cap's only tell.
    """
    problems = []
    for size in SIZES:
        with fleet_of(tmp_path, size) as store:
            summary, _tree = measured(store, size)
            rows = summary["needs_you"]
            assert isinstance(rows, list)
            in_store = sum(
                1 for row in store.fleet() if row.state is SessionState.NEEDS_YOU
            )
            if len(rows) != in_store:
                problems.append(
                    f"{size} sessions: the projection lists {len(rows)} needs_you"
                    f" rows, the store holds {in_store} — a silent truncation"
                )
            if in_store == 0:
                problems.append(
                    f"{size} sessions: no needs_you row at all; the term is untested"
                )
    assert problems == []


def test_the_fixed_terms_do_not_grow(tmp_path: Path) -> None:
    """The control for the growth check: something in the payload is constant.

    `anomalies` is every `AnomalyKind` at zero plus whatever was counted, so at
    a fleet that counts none it is the same dict at 1 session and at 200. If
    *everything* grew, "grows strictly" would be a statement about JSON rather
    than about the projection.
    """
    with fleet_of(tmp_path, SIZES[0]) as store:
        small, _ = measured(store, SIZES[0])
    with fleet_of(tmp_path, SIZES[-1]) as store:
        large, _ = measured(store, SIZES[-1])

    assert small["anomalies"] == large["anomalies"], "the control term grew too"
    assert set(small) == set(large), "the projections do not even have the same keys"
    assert wire_bytes(small) < wire_bytes(large), "the payload did not grow at all"


def test_the_spec_line_budget_against_the_projection_it_names(
    tmp_path: Path,
) -> None:
    """§11's *"~40 lines regardless of fleet size"*, measured — and recorded.

    **This is a measurement with a message, not a requirement being enforced.**
    G-M4-8 is open and its fix is a design decision; what this asserts is only
    that the measurement was taken at every size and that the smallest fleet is
    already over, because *"already over at the smallest fleet"* is the fact that
    makes this a design problem rather than a scaling one.
    """
    lines = {}
    for size in SIZES:
        with fleet_of(tmp_path, size) as store:
            summary, _ = measured(store, size)
            lines[size] = pretty_lines(summary)

    assert set(lines) == set(SIZES)
    assert lines[SIZES[0]] > SPEC_LINE_BUDGET, (
        "fleet_summary is now within §11's ~40 line budget at the smallest fleet"
        f" ({lines[SIZES[0]]} lines) — G-M4-8 may be closed; re-read this check"
    )
    assert lines[SIZES[-1]] > lines[SIZES[0]], f"measured: {lines}"
