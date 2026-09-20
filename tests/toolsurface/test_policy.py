"""T3: the gate as a pure, total function over an enumerated domain (§11, D8, DP2, DP11, K23).

Seam: `shepherd.toolsurface.policy` — the module's public surface. Nothing here
reaches into a branch; `decide()` and `TABLE` are the whole interface.

**Why the domain is enumerated rather than counted (P-M4-1, K19).** No
`external`-class tool is registered at M4 (DP11/G-M4-7), so a test that walks the
registry and claims to cover every blast class passes without ever evaluating the
`external` row — a check that reports success without checking, in the one
function this milestone is about. The domain is therefore built from the enums
themselves at test time and compared as a **set**, never as a length: M3 shipped
an `== 17` that stayed green while the population it counted changed underneath
it, and `test_the_totality_check_is_a_set_not_a_length` reads this file's own AST
to keep that from happening here.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
from pathlib import Path

from shepherd.toolsurface.policy import (
    AGENT_AUDIENCES,
    APPROVAL_TIMEOUT_S,
    TABLE,
    ApprovedBy,
    AutonomyLevel,
    Decision,
    Verdict,
    decide,
)
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    AuditRecord,
    AuthzOutcome,
    BlastClass,
    CallerContext,
)

POLICY_SOURCE = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "toolsurface" / "policy.py"


def enumerated_domain() -> frozenset[tuple[BlastClass, AutonomyLevel, Audience]]:
    """The enumeration rule, in one place and written out.

    The domain of `decide` is the full cartesian product of the three enums as
    they exist **at test time** — `itertools.product(set(BlastClass),
    set(AutonomyLevel), set(Audience))`. Adding a member to any of the three
    widens this set, and the totality assertion below goes red until a row
    covers it. Nothing here counts anything.
    """
    return frozenset(
        itertools.product(set(BlastClass), set(AutonomyLevel), set(Audience))
    )


def test_the_gate_is_total_over_the_enumerated_product() -> None:
    """P-M4-1. Set equality against `itertools.product`, never a length."""
    domain = enumerated_domain()
    # Arrival before the comparison: an empty product would make every
    # assertion below true by vacuity (the shape clause 6's scope controls exist
    # for, one file over).
    assert domain
    assert set(TABLE) == domain

    # …and the function answers from that table for every member of it, so a
    # branch cannot answer where the table does not.
    answered = {key for key in domain if isinstance(decide(*key), Decision)}
    assert answered == domain
    assert {decide(*key) for key in domain} == set(TABLE.values())


def test_a_human_destructive_call_is_allowed_and_attributed_as_claimed_human() -> None:
    """DP2 + K23. A human-audience call is allowed with no card — and the record
    says *a caller claimed HUMAN and policy allowed it*, never *a person
    approved this*.

    `Audience.HUMAN` is an **unauthenticated self-stamp**: `web/server.py:230`
    and `cli/main.py:164` each construct a `CallerContext` claiming it and
    nothing proves it. `user` is reserved for the one case a person demonstrably
    acted — a click on a card — because the audit log is the artefact the next
    incident is reconstructed from.
    """
    for blast_class in (BlastClass.LOCAL_DESTRUCTIVE, BlastClass.EXTERNAL):
        for level in set(AutonomyLevel):
            assert decide(blast_class, level, Audience.HUMAN) == Decision(
                verdict=Verdict.ALLOW, approved_by=ApprovedBy.CLAIMED_HUMAN
            ), (blast_class, level)

    # The two values are distinct members with distinct wire spellings. Both
    # halves are asserted: collapsing them into one member and aliasing one to
    # the other's string are the same defect wearing two faces.
    assert ApprovedBy.CLAIMED_HUMAN is not ApprovedBy.USER
    assert ApprovedBy.CLAIMED_HUMAN.value == "claimed_human"
    assert ApprovedBy.USER.value == "user"
    assert len({member.value for member in ApprovedBy}) == len(list(ApprovedBy))

    # …and `user` is not something this function can ever produce: a person
    # pressing Approve happens in T4, past the gate. Enumerated, not sampled.
    assert ApprovedBy.USER not in {decision.approved_by for decision in TABLE.values()}


def test_an_agent_destructive_call_at_level_two_asks() -> None:
    """§11's level-2 column, over the audiences DP2 turns on.

    `AGENT_AUDIENCES` is the set the human/agent asymmetry is drawn against, so
    it is asserted against the enum rather than against a literal list that
    would drift: it is every audience that is not `HUMAN`.
    """
    assert AGENT_AUDIENCES
    assert AGENT_AUDIENCES == set(Audience) - {Audience.HUMAN}
    assert Audience.HUMAN not in AGENT_AUDIENCES

    for audience in AGENT_AUDIENCES:
        for blast_class in (BlastClass.LOCAL_DESTRUCTIVE, BlastClass.EXTERNAL):
            assert decide(blast_class, AutonomyLevel.LEVEL_2, audience) == Decision(
                verdict=Verdict.ASK, approved_by=None
            ), (blast_class, audience)
            # …and the level-3 half, so an inversion of the branch cannot be
            # hidden by only ever driving one level (§11, D8).
            assert decide(blast_class, AutonomyLevel.LEVEL_3, audience) == Decision(
                verdict=Verdict.ALLOW, approved_by=ApprovedBy.POLICY
            ), (blast_class, audience)
        # The read and write classes never ask, at either level.
        for blast_class in (BlastClass.LOCAL_READ, BlastClass.LOCAL_WRITE):
            for level in set(AutonomyLevel):
                assert decide(blast_class, level, audience) == Decision(
                    verdict=Verdict.ALLOW, approved_by=ApprovedBy.POLICY
                ), (blast_class, level, audience)

    # `ASK` is reachable from exactly the cells §11 asks at, enumerated rather
    # than counted: an agent audience, a level-2 call, a class that leaves the
    # fleet or destroys part of it.
    assert {key for key, decision in TABLE.items() if decision.verdict is Verdict.ASK} == {
        (blast_class, AutonomyLevel.LEVEL_2, audience)
        for blast_class in (BlastClass.LOCAL_DESTRUCTIVE, BlastClass.EXTERNAL)
        for audience in AGENT_AUDIENCES
    }
    assert APPROVAL_TIMEOUT_S == 600.0


def test_the_caller_context_field_is_defaulted() -> None:
    """DP2/K23: `ActorKind.WORKER` must be reachable, and Gate A must survive it.

    `web/server.py:230,299` and `cli/main.py:164` construct a `CallerContext`
    with exactly `audience`, `caller_id` and `correlation_id`. A **required**
    `actor_kind` would mean editing all three call sites, which takes
    `test_completing_l4_changed_no_consumer_byte` red with it — so the field is
    defaulted, and this check is what holds it that way.

    Arrival before absence: the field is asserted to **exist** before anything
    is asserted about its default. A test that only constructed the three-argument
    form would pass just as happily against a `CallerContext` that never grew the
    field at all, and DP2's M5 promise would be unimplementable again.
    """
    fields = {field.name: field for field in dataclasses.fields(CallerContext)}
    assert "actor_kind" in fields, sorted(fields)
    assert fields["actor_kind"].default is None

    # The three arguments the shipped consumers pass, and nothing else.
    ctx = CallerContext(audience=Audience.HUMAN, caller_id="cli", correlation_id="cid")
    assert ctx.actor_kind is None

    # …and the field the default exists for is reachable, which is the half
    # revision 1 could not express: `Audience` has no worker member, so deriving
    # `actor_kind` from the audience made `WORKER` unwritable.
    worker = CallerContext(
        audience=Audience.MASTER,
        caller_id="wrk_1",
        correlation_id="cid",
        actor_kind=ActorKind.WORKER,
    )
    assert worker.actor_kind is ActorKind.WORKER
    assert ActorKind.WORKER.value not in {member.value for member in Audience}

    # The vocabulary the injection points need, held in `types.py` because it
    # imports nothing but stdlib: `registry.py` can hold a gate and a sink
    # without dragging `shepherd.logs` in transitively (DP3).
    assert {member.value for member in ActorKind} == {"master", "session", "human", "worker"}
    assert {field.name for field in dataclasses.fields(AuthzOutcome)} == {
        "allowed",
        "approved_by",
        "approval_id",
        "reason",
    }
    assert {field.name for field in dataclasses.fields(AuditRecord)} == {
        "at",
        "correlation_id",
        "actor_kind",
        "actor_id",
        "tool",
        "blast_class",
        "args",
        "autonomy_level",
        "decision",
        "approved_by",
        "approval_id",
        "result",
        "failure",
        "duration_ms",
    }


#: Everything `policy.py` is allowed to name. Stdlib that cannot reach the
#: world, plus L4's own vocabulary — and `shepherd.toolsurface.types` is the
#: only `shepherd` module on the list.
PERMITTED_IMPORTS = frozenset(
    {"__future__", "collections.abc", "dataclasses", "enum", "shepherd.toolsurface.types"}
)


def imported_modules(path: Path) -> frozenset[str]:
    """Every module a source file names, in all four spellings.

    `import x`, `import x as y`, `from x import y` — and the two call-shaped
    forms, `importlib.import_module("x")` and `__import__("x")`, which are not
    import nodes at all. A rule that reads only the first two passes on the
    idiomatic spelling of the same violation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
        elif isinstance(node, ast.Call):
            target = node.func
            name = (
                target.attr
                if isinstance(target, ast.Attribute)
                else target.id
                if isinstance(target, ast.Name)
                else None
            )
            if name in {"import_module", "__import__"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return frozenset(found)


def purity_violations(path: Path) -> list[str]:
    return sorted(name for name in imported_modules(path) if name not in PERMITTED_IMPORTS)


def test_the_gate_reads_no_clock_and_no_registry() -> None:
    """The purity map's row for `decide()`, asserted rather than asserted-about.

    A gate that reads a clock is a gate a table cannot prove, and a gate that
    consults the registry answers a question about what happens to be registered
    — which at M4 means the `external` row is never evaluated (DP11/G-M4-7).
    """
    # Arrival first, twice over. The scan sees this file's real imports…
    seen = imported_modules(POLICY_SOURCE)
    assert seen, "the scan found no imports in policy.py at all — the scan is broken"
    assert "shepherd.toolsurface.types" in seen, sorted(seen)
    # …and it demonstrably reports a violation when there is one to report, in
    # both the import spelling and the call spelling, against inert fixtures
    # nothing on the import path ever executes.
    clock_leak = Path(__file__).resolve().parent / "fixtures" / "policy_reads_a_clock.py"
    call_leak = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "policy_imports_the_registry_via_import_module.py"
    )
    assert purity_violations(clock_leak) == ["shepherd.core.clock"]
    assert purity_violations(call_leak) == ["importlib", "shepherd.toolsurface.registry"]

    # Only then the emptiness.
    assert purity_violations(POLICY_SOURCE) == []


#: The totality check is these two functions: the enumeration rule and the
#: comparison that uses it. Both are read as AST below.
TOTALITY_CHECK = ("enumerated_domain", "test_the_gate_is_total_over_the_enumerated_product")


def test_the_totality_check_is_a_set_not_a_length() -> None:
    """K19, and M3's `== 17` is why this test exists.

    A totality assertion written as a count stays green while the population it
    counts changes underneath it — the domain gains an `Audience` member, loses
    a `BlastClass` row, and twenty-four is still twenty-four. The check above is
    a **set equality against `itertools.product` enumerated at test time**, and
    this one reads its source to keep it that way: no `len()`, no comparison
    against a numeric literal, and the product call present where the rule says
    it is.
    """
    tree = ast.parse(Path(__file__).resolve().read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in TOTALITY_CHECK
    }
    # Arrival: the AST scan found the functions it is about. A rename turns this
    # red rather than turning the whole check into an emptiness over nothing —
    # which is the failure mode clause 15's subset assertion exists for, one
    # file over.
    assert set(functions) == set(TOTALITY_CHECK), sorted(functions)

    for name in TOTALITY_CHECK:
        body = functions[name]
        calls = {
            node.func.id
            for node in ast.walk(body)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "len" not in calls, f"{name} counts where it must compare sets"
        for compare in (n for n in ast.walk(body) if isinstance(n, ast.Compare)):
            operands = [compare.left, *compare.comparators]
            numeric = [
                operand
                for operand in operands
                if isinstance(operand, ast.Constant)
                and isinstance(operand.value, int)
                and not isinstance(operand.value, bool)
            ]
            assert numeric == [], f"{name} compares against a literal count"

    # …and the enumeration rule really is `itertools.product` over the three
    # enums, rather than a hand-written list of keys that would drift.
    rule = functions["enumerated_domain"]
    products = [
        node
        for node in ast.walk(rule)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "product"
    ]
    assert products and products[1:] == [], ast.dump(rule)
    enums = {
        node.args[0].id
        for node in ast.walk(products[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }
    assert enums == {"BlastClass", "AutonomyLevel", "Audience"}
    docstring = ast.get_docstring(rule) or ""
    assert "itertools.product" in docstring
