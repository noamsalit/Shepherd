"""S1 — the gate that can say no, over every shipped tool and both levels.

**The gap this closes, in one sentence.** `tests/chokepoint_fixture.py`'s
`install_test_chokepoint` defaults to `AutonomyLevel.LEVEL_3`, which §11's table
auto-approves for every class and every audience; six suites import it; a grep
for `LEVEL_2` across the three shipped-tool suites returns nothing. **No shipped
tool had ever crossed a gate that could say no.** Production's own default is the
other one — `tools_master.DEFAULT_AUTONOMY_LEVEL` is `LEVEL_2`, *"a
misconfiguration must not read as a licence"* — so the deterministic suite was
proving the level production does not run at.

**What is driven.** Every registered `ToolDef` × both `AutonomyLevel` members ×
each audience in that tool's own `audiences` set, through the shipped `invoke()`
with the shipped `build_authorizer` gate. `AutonomyLevel` has exactly two
members, so this is **full-combinatorial and small** rather than a sampling
problem, and every one of the three populations is enumerated at test time.

**What is observed per cell:** whether a card was raised; whether the handler
ran (a counting handler, asserted zero on deny); the audit record's `decision` /
`approved_by` / `result` / `approval_id`; and that a denied call comes back as a
typed `Failure.REFUSED` rather than a silent success.

**The one substitution, named as a risk.** The handlers are stand-ins that count
and return a literal. The shipped handlers cannot be driven 140 times in the
default lane — `spawn_session` starts a tmux pane, `install_hooks` writes a
settings file, `kill_session` reaches a real pane — and a scenario that had to
skip the destructive half would be a gate test with the gate's subject removed.
The substitution is sound because `invoke()` reads `name`, `audiences`,
`input_schema` and `blast_class` and hands the handler nothing, and it is
**asserted** sound rather than argued: `test_the_stand_ins_differ_from_the_
shipped_tools_in_exactly_one_field` compares every `dataclasses.field` of
`ToolDef` enumerated at test time. `test_the_shipped_handler_meets_the_same_
gate` then drives a real, unsubstituted destructive handler through the real
`compose_tool_surface` at `LEVEL_2` and gets the same denial, which is the
control that keeps the substitution from being the thing that passes.

*Lying implementations this now catches:*

* one that raises the card correctly **and runs the handler anyway** — the
  counter is asserted unchanged across the whole blocked call and after the
  denial;
* one that allows at `LEVEL_2` because every test only ever asked at `LEVEL_3` —
  both members are driven and the expectation is a restatement of §11's table,
  not a call to `decide()`;
* one that writes an `allow` record for a call it denied — `decision`,
  `result` and `approved_by` are asserted per cell;
* one that denies by raising rather than by answering — `Failure.REFUSED` is
  asserted as a value, never as error text.
"""

from __future__ import annotations

import dataclasses
import inspect
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import pytest

from chokepoint_fixture import install_test_chokepoint
from shepherd.toolsurface.approvals import ApprovalOutcome
from shepherd.toolsurface.export import DENIED_TEXT
from shepherd.toolsurface.policy import TABLE, ApprovedBy, AutonomyLevel, Verdict, decide
from shepherd.toolsurface.registry import (
    invoke,
    registered_tools,
    register,
    reset_registry,
)
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    AuditRecord,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolDef,
    ToolResult,
)

from ._gate import ARRIVAL_TIMEOUT_S, QaGate, install_qa_chokepoint
from .conftest import World

# ----- §11's table, restated independently -----------------------------------
#
# **This is not `policy.decide()` consulted, and that is deliberate.** Building
# the expected value out of the object under test is the tautology this repo has
# shipped three times and caught three times. §11's blast-radius table reads:
#
#     | class              | level 2   | level 3 |
#     | local_read         | allow     | allow   |
#     | local_write        | allow     | allow   |
#     | local_destructive  | **ask**   | allow   |
#     | external           | **ask**   | allow   |
#
# written out below from the spec, once, with `test_the_independent_reading_of_
# the_spec_agrees_with_the_shipped_table` comparing the two statements over the
# enumerated product. If they ever disagree, one of them is wrong and the test
# says which cell.

#: Does §11 make this class **ask** at level 2? Total over `BlastClass`, and
#: asserted total against the enum enumerated at test time, so a fifth class is
#: a failing build rather than a cell that quietly reads as "allow".
ASKS_AT_LEVEL_2: Mapping[BlastClass, bool] = {
    BlastClass.LOCAL_READ: False,
    BlastClass.LOCAL_WRITE: False,
    BlastClass.LOCAL_DESTRUCTIVE: True,
    BlastClass.EXTERNAL: True,
}


@dataclass(frozen=True)
class Expected:
    """What §11 + DP2 say happens in one cell, said without asking the gate."""

    asks: bool
    approved_by: ApprovedBy | None


def expected_for(
    blast_class: BlastClass, level: AutonomyLevel, audience: Audience
) -> Expected:
    """§11's table, plus DP2's `HUMAN` column and K23's attribution.

    DP2: a human-audience call on a **gated** class is allowed without a card,
    because `authorize()` bounds what an agent does *on your behalf* and a human
    clicking `[Kill]` is not acting on anyone's behalf. K23: that stamp is
    unauthenticated, so the attribution is `CLAIMED_HUMAN` — *a caller claimed
    HUMAN and policy allowed it* — never `USER`.

    **The attribution is a property of the class, not of the level, and that is
    a reading rather than a quotation.** §11's table has two columns, `level 2`
    and `level 3`, and says only `allow` / `ask`; it says nothing at all about
    *who* an allowance is attributed to. The first form of this predicate read
    the level-3 rows as *"level 3 auto-approves, therefore policy"* and
    disagreed with the shipped `TABLE` on exactly two cells —
    `local_destructive/3/human` and `external/3/human`, which the build
    attributes to `CLAIMED_HUMAN`. The build is right and the reading was
    over-specified: a record cannot tell those two cases apart after the fact,
    and `CLAIMED_HUMAN` is the value that claims *less*. Recorded in
    `docs/plans/m1-m4-qa/harness.md` as a spec gap — §11 does not state the
    attribution at level 3 — rather than absorbed into this function silently.
    """
    gated = ASKS_AT_LEVEL_2[blast_class]
    if not gated:
        return Expected(asks=False, approved_by=ApprovedBy.POLICY)
    if audience is Audience.HUMAN:
        return Expected(asks=False, approved_by=ApprovedBy.CLAIMED_HUMAN)
    if level is AutonomyLevel.LEVEL_2:
        return Expected(asks=True, approved_by=None)
    return Expected(asks=False, approved_by=ApprovedBy.POLICY)


def test_the_independent_reading_of_the_spec_is_total_over_the_blast_classes() -> None:
    """A map with a hole decides what happens when the hole is reached."""
    assert set(ASKS_AT_LEVEL_2) == set(BlastClass)


def test_the_independent_reading_of_the_spec_agrees_with_the_shipped_table() -> None:
    """Two statements of §11, compared over the product enumerated at test time.

    The point is that they are *two*: this file's expectation never calls
    `decide()`, so a table edited to auto-approve a destructive call would make
    this check red here and every S1 cell red below — rather than moving both
    sides of an equality at once.
    """
    disagreements = []
    for (blast_class, level, audience), decision in TABLE.items():
        expected = expected_for(blast_class, level, audience)
        actual_asks = decision.verdict is Verdict.ASK
        if actual_asks != expected.asks or decision.approved_by != expected.approved_by:
            disagreements.append(
                f"{blast_class.value}/{int(level)}/{audience.value}:"
                f" spec says asks={expected.asks} by={expected.approved_by};"
                f" TABLE says asks={actual_asks} by={decision.approved_by}"
            )
    assert set(TABLE) == {
        (blast_class, level, audience)
        for blast_class in BlastClass
        for level in AutonomyLevel
        for audience in Audience
    }
    assert disagreements == []


# ----- the population, enumerated -------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One (tool, level, audience) of the full-combinatorial product."""

    tool: ToolDef
    level: AutonomyLevel
    audience: Audience

    def __str__(self) -> str:
        return f"{self.tool.name}/{self.tool.blast_class.value}/L{int(self.level)}/{self.audience.value}"


def shipped_tools(world: World) -> tuple[ToolDef, ...]:
    """Every `ToolDef` *this build composes*, read off the shipped registry.

    Enumerated by composing, never listed: a literal list of tools is how S1
    goes stale the first time a milestone registers an eleventh capability, and
    the whole claim of this scenario is *"every registered tool"*.
    """
    world.compose()
    tools = tuple(registered_tools().values())
    reset_registry()
    assert tools, "the composition registered no tools at all"
    return tools


def cells(tools: tuple[ToolDef, ...]) -> tuple[Cell, ...]:
    """The full-combinatorial product. Three enumerations, no literal anywhere."""
    return tuple(
        Cell(tool=tool, level=level, audience=audience)
        for tool in tools
        for level in AutonomyLevel
        for audience in sorted(tool.audiences)
    )


#: One value per JSON Schema `type` the registry's required arguments use. The
#: set is asserted to cover every type actually required, so a tool declaring a
#: type this table has no value for is a **failing** build rather than a cell
#: quietly dropped from the matrix.
_VALUE_BY_TYPE: Mapping[str, object] = {
    "string": "qa-s1",
    "integer": 1,
    "number": 1.0,
    "boolean": True,
    "object": {},
    "array": [],
}


def required_types(tool: ToolDef) -> tuple[str, ...]:
    schema = tool.input_schema
    properties = cast("Mapping[str, Mapping[str, object]]", schema.get("properties", {}))
    required = cast("tuple[str, ...]", tuple(schema.get("required", ())))
    return tuple(str(properties[name].get("type")) for name in required)


def minimal_args(tool: ToolDef) -> ToolArgs:
    """Exactly the required arguments, each of its declared type.

    `invoke()` refuses an unknown argument, so this is the required set and
    nothing more — and the values only have to survive `_argument_problem`,
    because the handler under this matrix is a counter.
    """
    schema = tool.input_schema
    properties = cast("Mapping[str, Mapping[str, object]]", schema.get("properties", {}))
    required = cast("tuple[str, ...]", tuple(schema.get("required", ())))
    return {
        name: _VALUE_BY_TYPE[str(properties[name].get("type"))] for name in required
    }


def test_every_required_argument_type_in_the_registry_has_a_value(world: World) -> None:
    """Arrival for the matrix itself: the synthesiser covers the real registry."""
    used = {kind for tool in shipped_tools(world) for kind in required_types(tool)}
    assert used, "no registered tool declares a required argument at all"
    assert used <= set(_VALUE_BY_TYPE), f"no value for {sorted(used - set(_VALUE_BY_TYPE))}"


# ----- the stand-ins ----------------------------------------------------------


class Counter:
    """A handler that counts and returns a literal. Reaches nothing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, args: ToolArgs, ctx: CallerContext) -> object:
        with self._lock:
            self.calls += 1
        return {"qa_stand_in": self.name}


def stand_in(tool: ToolDef, counter: Counter) -> ToolDef:
    """The shipped `ToolDef` with its handler replaced and nothing else.

    `dataclasses.replace` rather than a re-construction, so a field added to
    `ToolDef` is carried over rather than silently defaulted.
    """
    return dataclasses.replace(tool, handler=counter)


def test_the_stand_ins_differ_from_the_shipped_tools_in_exactly_one_field(
    world: World,
) -> None:
    """The substitution's whole safety argument, asserted rather than written.

    Every `dataclasses.field` of `ToolDef` is enumerated **at test time**, so a
    field added to the shape is compared by default. `handler` is the one
    difference, and it is named as the one difference — not skipped.
    """
    names = tuple(field.name for field in dataclasses.fields(ToolDef))
    assert "handler" in names, "ToolDef no longer has a handler; S1's premise moved"
    compared = tuple(name for name in names if name != "handler")
    assert compared, "ToolDef has no field but its handler"

    differences = []
    for tool in shipped_tools(world):
        replaced = stand_in(tool, Counter(tool.name))
        for name in compared:
            if getattr(replaced, name) != getattr(tool, name):
                differences.append(f"{tool.name}.{name}")
        # Arrival: the one field really did change.
        assert replaced.handler is not tool.handler
    assert differences == []


# ----- the matrix -------------------------------------------------------------


@dataclass
class Observation:
    """What one cell did, as facts rather than as a verdict."""

    cell: Cell
    card_raised: bool
    ran_while_blocked: int
    """How many times the handler ran **before the card was answered**. The only
    moment at which *"raised the card and ran the handler anyway"* is visible."""
    ran_total: int
    result: ToolResult
    record: AuditRecord | None


def context(audience: Audience, correlation_id: str) -> CallerContext:
    return CallerContext(
        audience=audience, caller_id=f"qa-{audience.value}", correlation_id=correlation_id
    )


def drive(
    cell: Cell, gate: QaGate, counter: Counter, *, answer: ApprovalOutcome
) -> Observation:
    """One cell, driven through the shipped `invoke()`.

    A cell the gate blocks on runs on its own thread, because the shipped
    authorizer parks the **calling** thread in `await_decision` for up to 600 s.
    The card is waited for by arrival and answered with `answer`; the handler's
    count is read **while the call is still blocked**, which is the only moment
    at which *"the card was raised and the handler ran anyway"* is visible.
    """
    correlation = f"s1-{cell}-{answer.value}"
    answers: list[ToolResult] = []
    before_records = len(gate.records)
    before_calls = counter.calls

    def call_it() -> None:
        answers.append(
            invoke(cell.tool.name, minimal_args(cell.tool), context(cell.audience, correlation))
        )

    caller = threading.Thread(target=call_it, name=f"s1-{cell}", daemon=True)
    caller.start()

    # **Whether a card was raised is measured, never predicted.** Polling for
    # *either* terminal condition — the call came back, or a card is pending —
    # is what lets a cell that wrongly raises a card, and a cell that wrongly
    # does not, both fail as themselves rather than as a timeout. Bounded: a
    # mutant that hangs is not a red.
    waiter = threading.Event()
    card_raised = False
    ran_while_blocked = 0
    for _ in range(int(ARRIVAL_TIMEOUT_S * 200)):
        if gate.approvals.pending():
            card = gate.approvals.pending()[0]
            card_raised = True
            ran_while_blocked = counter.calls - before_calls
            assert gate.approvals.decide(card.id, answer) is True, "the card was already terminal"
            break
        if not caller.is_alive():
            break
        waiter.wait(0.005)
    caller.join(ARRIVAL_TIMEOUT_S)
    assert not caller.is_alive(), f"{cell} never came back"
    assert gate.approvals.pending() == (), f"{cell} left a card behind"
    assert answers, f"{cell} produced no answer at all"

    new = gate.records[before_records:]
    assert len(new) <= 1, f"{cell} produced {len(new)} audit records for one call"
    return Observation(
        cell=cell,
        card_raised=card_raised,
        ran_while_blocked=ran_while_blocked,
        ran_total=counter.calls - before_calls,
        result=answers[0],
        record=new[0] if new else None,
    )


def run_matrix(world: World, *, answer: ApprovalOutcome) -> list[str]:
    """Every cell of the product, and every disagreement it produced.

    Failures are **collected** rather than raised at the first one: a matrix that
    stops at cell three tells you about cell three, and the shape of a gate
    defect is usually a whole row or a whole column.
    """
    tools = shipped_tools(world)
    problems: list[str] = []
    for level in AutonomyLevel:
        reset_registry()
        gate = install_qa_chokepoint(level)
        counters = {tool.name: Counter(tool.name) for tool in tools}
        for tool in tools:
            register(stand_in(tool, counters[tool.name]))
        for cell in (cell for cell in cells(tools) if cell.level is level):
            counter = counters[cell.tool.name]
            seen = drive(cell, gate, counter, answer=answer)
            problems.extend(judge(seen, answer=answer))
        reset_registry()
    return problems


def judge(seen: Observation, *, answer: ApprovalOutcome) -> list[str]:
    """§11's expectation for this cell, compared against what really happened."""
    cell = seen.cell
    expected = expected_for(cell.tool.blast_class, cell.level, cell.audience)
    ran = seen.ran_total
    problems: list[str] = []

    def bad(what: str) -> None:
        problems.append(f"{cell}: {what}")

    if seen.card_raised != expected.asks:
        bad(f"card_raised={seen.card_raised}, §11 says asks={expected.asks}")
    if seen.record is None:
        bad("no audit record was written for a decided call")
        return problems

    denied = expected.asks and answer is not ApprovalOutcome.APPROVED
    if denied:
        # The gate said no. Three facts, and the first is the one the whole
        # scenario exists for: the handler did not run.
        if seen.ran_while_blocked != 0 or ran != 0:
            bad(
                "the handler ran on a denied call"
                f" (while blocked={seen.ran_while_blocked}, total={ran})"
            )
        if seen.result.ok is not False or seen.result.failure is not Failure.REFUSED:
            bad(f"a denied call answered ok={seen.result.ok} failure={seen.result.failure}")
        if seen.result.error is None or DENIED_TEXT not in seen.result.error:
            bad(f"the denial does not carry export.DENIED_TEXT: {seen.result.error!r}")
        if seen.record.decision != "deny" or seen.record.result != "denied":
            bad(f"audit says decision={seen.record.decision!r} result={seen.record.result!r}")
        if seen.record.approved_by is not None:
            bad(f"a rejected call is attributed to {seen.record.approved_by!r}")
        if seen.record.approval_id is None:
            bad("a denied call's record carries no approval_id")
    else:
        if ran != 1:
            bad(f"the handler ran {ran} times on an allowed call")
        if seen.card_raised and seen.ran_while_blocked != 0:
            bad("the handler ran before the person answered the card")
        if seen.result.ok is not True or seen.result.failure is not None:
            bad(f"an allowed call answered ok={seen.result.ok} failure={seen.result.failure}")
        if seen.record.decision != "allow" or seen.record.result != "ok":
            bad(f"audit says decision={seen.record.decision!r} result={seen.record.result!r}")
        by = ApprovedBy.USER if expected.asks else expected.approved_by
        if seen.record.approved_by != (by.value if by is not None else None):
            bad(f"approved_by={seen.record.approved_by!r}, expected {by!r}")
        if expected.asks != (seen.record.approval_id is not None):
            bad(f"approval_id={seen.record.approval_id!r} for asks={expected.asks}")

    # The record's own identity, on every cell either way.
    if seen.record.tool != cell.tool.name:
        bad(f"audit names tool {seen.record.tool!r}")
    if seen.record.blast_class is not cell.tool.blast_class:
        bad(f"audit names blast_class {seen.record.blast_class!r}")
    if seen.record.actor_kind is not ActorKind(cell.audience.value):
        bad(f"audit names actor_kind {seen.record.actor_kind!r} for {cell.audience!r}")
    return problems


def test_the_matrix_is_the_full_combinatorial_product(world: World) -> None:
    """Arrival for the matrix: the population is what the enumeration says.

    `AutonomyLevel` has exactly two members, so every tool contributes
    `2 × |audiences|` cells and the total is a **derived** number, never a
    literal. The tool count is asserted non-zero and the derivation is asserted
    against the enumeration, so a registry that composed nothing cannot produce
    a vacuously passing matrix below.
    """
    tools = shipped_tools(world)
    product = cells(tools)
    assert len(product) == sum(len(AutonomyLevel) * len(tool.audiences) for tool in tools)
    assert len(product) > len(tools), "no tool declares an audience"
    assert {cell.level for cell in product} == set(AutonomyLevel)
    assert {cell.audience for cell in product} == set(Audience)


def test_every_tool_at_every_level_for_every_audience_rejected(world: World) -> None:
    """The headline cell: the gate says **no**, and the handler never runs."""
    assert run_matrix(world, answer=ApprovalOutcome.REJECTED) == []


def test_every_tool_at_every_level_for_every_audience_approved(world: World) -> None:
    """The other exit of the same card: a person says yes and the call runs.

    Without this, *"the handler never ran"* above would be satisfied by a gate
    that never runs anything — the unfalsifiable direction the QA strategy warns
    about. `approved_by == "user"` is the fact only `approvals.py` can produce.
    """
    assert run_matrix(world, answer=ApprovalOutcome.APPROVED) == []


def test_at_least_one_cell_of_the_matrix_actually_raises_a_card(world: World) -> None:
    """Arrival before absence, for the *scenario*.

    Every assertion above about denial is vacuous if no cell ever asks. This
    names which cells can, by driving them, and records the measured shape of
    the reachable gate: a `(class, level, audience)` row of §11 that no
    registered tool can reach is a row the product proves nothing about.
    """
    tools = shipped_tools(world)
    asking = {
        (cell.tool.name, cell.audience)
        for cell in cells(tools)
        if expected_for(cell.tool.blast_class, cell.level, cell.audience).asks
    }
    assert asking, (
        "no registered tool can raise an approval card at any level for any"
        " audience — §11's gate is unreachable from this build's registry"
    )

    reset_registry()
    gate = install_qa_chokepoint(AutonomyLevel.LEVEL_2)
    counters = {tool.name: Counter(tool.name) for tool in tools}
    for tool in tools:
        register(stand_in(tool, counters[tool.name]))
    raised = 0
    for name, audience in sorted(asking, key=lambda pair: (pair[0], pair[1].value)):
        tool = registered_tools()[name]
        seen = drive(
            Cell(tool=tool, level=AutonomyLevel.LEVEL_2, audience=audience),
            gate,
            counters[name],
            answer=ApprovalOutcome.REJECTED,
        )
        raised += int(seen.card_raised)
    reset_registry()
    assert raised == len(asking)


def test_the_reachable_ask_rows_of_the_spec_table_are_measured(world: World) -> None:
    """Which of §11's four `ask` rows any registered tool can actually reach.

    Recorded as a **measurement**, not as a requirement: the answer is a fact
    about what this build registers, and `docs/plans/m1-m4-qa/harness.md` carries
    it. What is asserted is only that the measurement is not empty and that the
    unreachable rows are unreachable for the reason the registry gives —
    otherwise a future build that registered an `external` tool would leave this
    check silently measuring the old shape.
    """
    tools = shipped_tools(world)
    ask_rows = {
        (blast_class, level, audience)
        for (blast_class, level, audience) in TABLE
        if expected_for(blast_class, level, audience).asks
    }
    reachable = {
        (cell.tool.blast_class, cell.level, cell.audience)
        for cell in cells(tools)
        if expected_for(cell.tool.blast_class, cell.level, cell.audience).asks
    }
    assert reachable, "no registered tool reaches any ask row"
    assert reachable <= ask_rows

    for blast_class, level, audience in sorted(
        ask_rows - reachable, key=lambda row: (row[0].value, int(row[1]), row[2].value)
    ):
        # An unreachable row is unreachable because no registered tool carries
        # that class **with** that audience. That is a fact about the registry;
        # anything else means the reasoning above has gone stale.
        assert not any(
            tool.blast_class is blast_class and audience in tool.audiences for tool in tools
        ), f"{blast_class}/{level}/{audience} is reachable but was not driven"


# ----- the controls ----------------------------------------------------------


def test_the_shipped_fixture_still_defaults_to_the_level_that_cannot_say_no() -> None:
    """The gap S1 exists to close, asserted so it cannot close by accident.

    If somebody changes `install_test_chokepoint`'s default to `LEVEL_2`, this
    goes red and the harness note in `docs/plans/m1-m4-qa/harness.md` is stale —
    which is the correct outcome, because six suites would then be proving
    something different from what they were proving when this was written.
    """
    default = inspect.signature(install_test_chokepoint).parameters["level"].default
    assert default is AutonomyLevel.LEVEL_3
    assert decide(
        BlastClass.LOCAL_DESTRUCTIVE, default, Audience.MASTER
    ).verdict is Verdict.ALLOW


def test_this_packages_gate_agrees_with_the_shipped_fixture(world: World) -> None:
    """`_gate.install_qa_chokepoint` is `install_test_chokepoint` with the store
    kept — asserted by driving one call through each and comparing the records.

    A second gate that happened to answer differently would make every cell above
    a statement about this file rather than about the product.
    """
    tools = shipped_tools(world)
    subject = next(
        tool for tool in tools if tool.blast_class is BlastClass.LOCAL_DESTRUCTIVE
    )
    audience = sorted(subject.audiences)[0]

    reset_registry()
    shipped_records = install_test_chokepoint()  # its default: LEVEL_3
    counter = Counter(subject.name)
    register(stand_in(subject, counter))
    through_shipped = invoke(subject.name, minimal_args(subject), context(audience, "c-a"))

    reset_registry()
    gate = install_qa_chokepoint(AutonomyLevel.LEVEL_3)
    mine = Counter(subject.name)
    register(stand_in(subject, mine))
    through_mine = invoke(subject.name, minimal_args(subject), context(audience, "c-b"))
    reset_registry()

    assert through_shipped.ok is through_mine.ok is True
    assert counter.calls == mine.calls == 1
    assert len(shipped_records) == len(gate.records) == 1
    for field in ("decision", "result", "approved_by", "approval_id", "blast_class", "tool"):
        assert getattr(shipped_records[0], field) == getattr(gate.records[0], field), field


def test_the_shipped_handler_meets_the_same_gate(world: World) -> None:
    """The control for the substitution: a **real** handler, denied.

    Composed by `compose_tool_surface`, at production's own default level, with
    nothing replaced — `kill_session` on a session that has no pane, so the
    handler is real and harmless. The denial has to look exactly like the
    matrix's denial, or the matrix is measuring its own stand-ins.
    """
    from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY

    wiring = world.compose()
    world.store.set_app_state(AUTONOMY_LEVEL_KEY, int(AutonomyLevel.LEVEL_2))
    subject = next(
        tool
        for tool in registered_tools().values()
        if tool.blast_class is BlastClass.LOCAL_DESTRUCTIVE
        and Audience.MASTER in tool.audiences
    )
    answers: list[ToolResult] = []
    caller = threading.Thread(
        target=lambda: answers.append(
            invoke(subject.name, minimal_args(subject), context(Audience.MASTER, "s1-real"))
        ),
        name="s1-real-handler",
        daemon=True,
    )
    caller.start()

    waiter = threading.Event()
    card = None
    for _ in range(int(ARRIVAL_TIMEOUT_S * 200)):
        pending = wiring.approvals.pending()
        if pending:
            card = pending[0]
            break
        waiter.wait(0.005)
    assert card is not None, "the shipped composition raised no card at LEVEL_2"
    assert card.tool == subject.name
    assert wiring.approvals.decide(card.id, ApprovalOutcome.REJECTED) is True
    caller.join(ARRIVAL_TIMEOUT_S)
    assert not caller.is_alive()

    assert answers[0].ok is False
    assert answers[0].failure is Failure.REFUSED
    assert answers[0].error is not None and DENIED_TEXT in answers[0].error


@pytest.mark.parametrize("level", sorted(AutonomyLevel))
def test_a_call_with_the_wrong_audience_is_refused_before_the_gate(
    world: World, level: AutonomyLevel
) -> None:
    """C-M4-1's order, at both levels: audience **before** the gate.

    A tool refused for its audience produces `UNAVAILABLE` and **no record** —
    auditing it would turn the log into a request log an agent can fill by
    guessing names (C-M4-2, D25). Driven at both levels because "the audience
    check happens first" is a claim about order that a level-3 test cannot make:
    at level 3 everything is allowed anyway.
    """
    tools = shipped_tools(world)
    # A tool §11 never asks about, so the arrival call below cannot park on a
    # card and this check stays synchronous at both levels.
    narrow = next(
        tool
        for tool in tools
        if tool.audiences != set(Audience) and not ASKS_AT_LEVEL_2[tool.blast_class]
    )
    outsider = next(audience for audience in Audience if audience not in narrow.audiences)

    reset_registry()
    gate = install_qa_chokepoint(level)
    counter = Counter(narrow.name)
    register(stand_in(narrow, counter))
    refused = invoke(narrow.name, minimal_args(narrow), context(outsider, "s1-audience"))
    # Arrival: the same tool, same level, from an audience it *does* declare.
    allowed_audience = sorted(narrow.audiences)[0]
    allowed = invoke(
        narrow.name, minimal_args(narrow), context(allowed_audience, "s1-audience-ok")
    )
    reset_registry()

    assert allowed.ok is True, "the arrival call was refused; this proves nothing"
    assert refused.ok is False
    assert refused.failure is Failure.UNAVAILABLE
    assert counter.calls == 1, "the refused call reached the handler"
    assert [record.actor_kind for record in gate.records] == [
        ActorKind(allowed_audience.value)
    ], "a call refused for its audience reached the audit log"
