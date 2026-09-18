"""S3 — M3's terminal reads under M4's gate, at both levels.

`get_session_output` and `terminal_snapshot` driven through a gate **that can
block**, at both `AutonomyLevel` members, as each audience that declares them.
They are `local_read`, so §11 lets them through without a card — which means the
only thing there is to assert is the **audit record**, and that is exactly why
this scenario is worth writing: an M3 tool's own suite has no audit log to look
at, and M4's audit tests drive M4's own tools.

**G-M4-17, driven rather than cited.** `registry.GATE_FREE_CLASSES` is
`{LOCAL_READ}`, so in a process that never composed a chokepoint a read **runs
and is not audited** — `cli/main.py`'s `register_local_reads` is that process,
and `invoke()` has no sink to write to. The residue is named in the shipped
docstring; here it is a driven observation with a positive control beside it, so
*"nothing was audited"* is distinguished from *"nothing can be audited"*.

*The lying implementation this catches:* **one that audits reads only when a
chokepoint happens to be installed by a test.** The two halves are driven in one
file — composed and uncomposed, same tools, same arguments — so the difference
between them is the composition and nothing else. A build that started auditing
the uncomposed case (or stopped auditing the composed one) moves exactly one of
these two checks.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.states import Origin, Ownership
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.compose import log_root, master_plane
from shepherd.toolsurface.policy import ApprovedBy, AutonomyLevel
from shepherd.toolsurface.registry import (
    GATE_FREE_CLASSES,
    chokepoint,
    invoke,
    registered_tools,
    reset_registry,
)
from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    Failure,
    ToolDef,
)

from ._gate import install_qa_chokepoint
from .conftest import World

REPO_ROOT = Path(__file__).resolve().parents[2]
COPIES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "transcripts" / "copies"
A_REAL_TRANSCRIPT = (
    COPIES / "-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl"
)
ENGINE_SESSION_ID = "7c27bb7f-5390-48b0-8b2e-cf4004113d09"

#: The two tools this scenario is about, by the name §11 gives them. This is a
#: **subject list**, not a population: S1 owns "every registered tool", and S3
#: owns these two by name because they are the two M3 reads M4 wrapped a gate
#: around. `test_the_subjects_are_registered_and_are_reads` re-derives their
#: class and audiences from the composed registry rather than restating them.
SUBJECTS = ("get_session_output", "terminal_snapshot")


@dataclass(frozen=True)
class Composed:
    """One composed build with a real, readable session in it."""

    world: World
    session_id: str


@pytest.fixture()
def composed(world: World, tmp_path: Path) -> Iterator[Composed]:
    """A real attached session, with a real captured transcript behind it.

    The transcript is placed under the **engine's** project root as the
    composition resolves it (`compose.transcript_root()` → `CLAUDE_CONFIG_DIR /
    projects`), so the read the tool performs is the read production performs.
    """
    session = world.store.register_session(
        engine_session_id=ENGINE_SESSION_ID,
        workspace_id=world.store.upsert_workspace("shepherd", str(tmp_path / "work")).id,
        repo_id=None,
        cwd=str(tmp_path / "work"),
        started_at="2026-09-18T09:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    projects = tmp_path / "engine-config" / "projects" / "-a-lossy-slug"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / f"{ENGINE_SESSION_ID}.jsonl").write_bytes(A_REAL_TRANSCRIPT.read_bytes())
    world.compose()
    yield Composed(world=world, session_id=session.id)


def context(audience: Audience, correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=audience, caller_id=f"qa-{audience.value}", correlation_id=correlation_id
    )


def subject(name: str) -> ToolDef:
    tool = registered_tools().get(name)
    assert tool is not None, f"{name} is not in the composed registry"
    return tool


def test_the_subjects_are_registered_and_are_reads(composed: Composed) -> None:
    """Arrival for the scenario: the two tools exist, and they are `local_read`.

    Their class is **read off the registry**, never asserted from a literal —
    if `terminal_snapshot` were ever reclassified, every audit expectation below
    would be about the wrong thing, and this says so first.
    """
    for name in SUBJECTS:
        tool = subject(name)
        assert tool.blast_class is BlastClass.LOCAL_READ, (
            f"{name} is {tool.blast_class}; S3's whole premise is that it is a read"
        )
        assert tool.audiences, f"{name} declares no audience at all"
    assert GATE_FREE_CLASSES == frozenset({BlastClass.LOCAL_READ}), (
        "GATE_FREE_CLASSES moved; G-M4-17's residue is a different shape now"
    )


def test_every_read_by_every_declared_audience_at_both_levels_is_audited(
    composed: Composed,
) -> None:
    """The composed half. One record per call, `allow`, attributed to policy.

    Both levels are driven because *"a read needs no card"* is a claim about
    **both** columns of §11's row, and the deterministic suite has only ever
    asked at the column that auto-approves everything. The audiences are the
    tool's own set, enumerated at test time.
    """
    assert chokepoint() is not None, "the composition installed no chokepoint"

    problems: list[str] = []
    expected_calls = 0
    for level in AutonomyLevel:
        composed.world.store.set_app_state(AUTONOMY_LEVEL_KEY, int(level))
        for name in SUBJECTS:
            tool = subject(name)
            for audience in sorted(tool.audiences):
                expected_calls += 1
                correlation = f"s3-{name}-{int(level)}-{audience.value}"
                result = invoke(
                    name, {"session_id": composed.session_id}, context(audience, correlation)
                )
                if result.failure is Failure.UNAVAILABLE:
                    problems.append(f"{correlation}: refused before the gate ({result.error})")

    records = read_audit_records(log_root(composed.world.host), expected_calls * 2)
    seen = {record["correlation_id"]: record for record in records}
    for level in AutonomyLevel:
        for name in SUBJECTS:
            for audience in sorted(subject(name).audiences):
                correlation = f"s3-{name}-{int(level)}-{audience.value}"
                record = seen.get(correlation)
                if record is None:
                    problems.append(f"{correlation}: no audit record was written")
                    continue
                if record["decision"] != "allow":
                    problems.append(f"{correlation}: decision={record['decision']!r}")
                if record["approved_by"] != ApprovedBy.POLICY.value:
                    problems.append(f"{correlation}: approved_by={record['approved_by']!r}")
                if record["approval_id"] is not None:
                    problems.append(
                        f"{correlation}: a read raised a card ({record['approval_id']})"
                    )
                if record["blast_class"] != BlastClass.LOCAL_READ.value:
                    problems.append(f"{correlation}: blast_class={record['blast_class']!r}")
                if record["actor_kind"] != audience.value:
                    problems.append(f"{correlation}: actor_kind={record['actor_kind']!r}")
    assert expected_calls > 0, "no cell was driven at all"
    assert problems == []


def test_no_read_ever_parks_on_a_card_at_either_level(composed: Composed) -> None:
    """§11's `local_read` row, both columns, asserted on the store itself.

    A read that raised a card would leave one pending — the call would still
    have returned if somebody answered it, so the *answer* is not the
    observation. Arrival: the store is proved able to hold a card first, by
    the destructive tool on the same surface, or this emptiness proves nothing.
    """
    plane = master_plane()
    assert plane is not None, "the composition installed no plane"
    assert plane.approvals.pending() == ()

    for level in AutonomyLevel:
        composed.world.store.set_app_state(AUTONOMY_LEVEL_KEY, int(level))
        for name in SUBJECTS:
            for audience in sorted(subject(name).audiences):
                invoke(
                    name,
                    {"session_id": composed.session_id},
                    context(audience, f"s3-card-{name}-{int(level)}-{audience.value}"),
                )
                assert plane.approvals.pending() == (), (
                    f"{name} raised an approval card as {audience.value} at level {int(level)}"
                )


# ----- G-M4-17: the same read, in a process that never composed ---------------


def test_a_read_in_a_process_that_never_composed_runs_and_is_not_audited(
    world: World,
) -> None:
    """The residue, driven — and the positive control is the composed half.

    Two invocations of the **same** shipped read, differing only in whether a
    chokepoint was installed. The first records nothing because there is no sink
    to record to; the second records. That difference is G-M4-17 exactly, and it
    is what makes *"unaudited"* a measured fact rather than a docstring.
    """
    reset_registry()
    assert chokepoint() is None, "the registry arrived with a gate installed"

    from shepherd.toolsurface.tools_engine import register_engine_tools

    register_engine_tools(
        db_path=world.db_path, drift_record_path=world.db_path.parent / "drift.json"
    )
    reads = [
        tool for tool in registered_tools().values() if tool.blast_class in GATE_FREE_CLASSES
    ]
    assert reads, "the standalone registration registered no read at all"
    tool = reads[0]
    audience = sorted(tool.audiences)[0]

    ungated = invoke(tool.name, {}, context(audience, "s3-ungated"))
    assert ungated.ok is True, f"a gate-free read was refused with no gate: {ungated.error}"

    # The control: the identical call, with the shipped gate installed, writes
    # a record. Same tool, same args, same audience.
    gate = install_qa_chokepoint(AutonomyLevel.LEVEL_2)
    gated = invoke(tool.name, {}, context(audience, "s3-gated"))
    assert gated.ok is True
    assert [record.correlation_id for record in gate.records] == ["s3-gated"], (
        "the composed half wrote no record either — this comparison proves nothing"
    )
    # …and the ungated call is nowhere in it. There is no second sink it could
    # have gone to: `install_chokepoint` is the only writer of `_CHOKEPOINT`.
    assert "s3-ungated" not in {record.correlation_id for record in gate.records}
    reset_registry()


def test_a_non_read_in_a_process_that_never_composed_is_refused(world: World) -> None:
    """DP13's other half, so the check above is not read as *"nothing is gated"*.

    A `local_read` runs ungated **because its class is in `GATE_FREE_CLASSES`**,
    and the way to show that is the class that is not: same uncomposed process,
    a destructive tool, refused. Driven off the composed registry's own
    classification rather than a literal tool name.
    """
    world.compose()
    destructive = next(
        tool
        for tool in registered_tools().values()
        if tool.blast_class not in GATE_FREE_CLASSES
    )
    name, audience = destructive.name, sorted(destructive.audiences)[0]
    schema = destructive.input_schema
    required = tuple(schema.get("required", ()))  # type: ignore[arg-type]
    args = {key: "qa-s3" for key in required}

    reset_registry()
    from shepherd.toolsurface.registry import register

    register(destructive)
    refused = invoke(name, args, context(audience, "s3-nogate"))
    reset_registry()

    assert refused.ok is False
    assert refused.failure is Failure.UNAVAILABLE, (
        "a tool outside GATE_FREE_CLASSES ran in a process with no chokepoint"
    )
