"""D-5 is applied, not merely available: `can_spawn` comes from `capabilities()`.

T10 shipped `capabilities(*, pane_driver_available: bool)` — the only thing that
applies D-5's degrade — beside a module constant that carries
`can_spawn=True` **unconditionally**. The router ratified the function *on the
condition that T11 closes the gap*, in its own words: a caller that reads the
constant instead of calling the function "gets `True` on a host with no pane
driver and D-5 never fires", and that must be held by **a check, not a
convention** (`docs/plans/2026-09-17-m3-BLOCKERS.md`, the T10 ratification and
T10-R2).

It is not a hypothetical spelling. **Task 11's own `Consumes` line names
`CLAUDE_CODE_CAPABILITIES`**, so a builder following the plan literally writes
the violation — which is why the first fixture below is that exact line.

**T10-R2 already made the constant private** (`_CLAUDE_CODE_CAPABILITIES`, out of
`__all__`), and this file asserts that too, in
`test_the_constant_is_private_and_unexported`. The privacy and the rule are not
alternatives: a leading underscore is a convention any import can ignore, and
`getattr(module, "_CLAUDE_CODE_CAPABILITIES")` is a string that no
identifier-only scan sees. Three planted spellings are proved to go red here —
the from-import, the module-alias attribute, and the `getattr` string.

**Two rules, because the constant is only half the hole.**
`capabilities(pane_driver_available=True)` returns the same un-degraded record
through the front door, so the argument must be a *fact the caller was handed*,
never a literal. `admission.py` passes the runner's own answer.

Scope scanned: `src/**/*.py`, recursive, every product module — with the engine
module that **defines** the constant exempt by **file**, not by package, so its
neighbours in `engines/claude_code/` are not exempted with it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import MISSING_MODULE, SRC_ROOT, fixture, iter_modules
from _parse import parsed

#: The file that defines the record. A file, not a package: `package_of` resolves
#: every module under `engines/claude_code/` to one package, and a package-wide
#: exemption would have covered `registry.py`, `normalise.py` and the rest.
OWNER_MODULE = SRC_ROOT / "engines" / "claude_code" / "spawn.py"

#: Both spellings. The private one is what exists today; the public one is what
#: the plan's `Consumes` line still says, and what a re-export would bring back.
CONSTANT_NAMES: frozenset[str] = frozenset(
    {"CLAUDE_CODE_CAPABILITIES", "_CLAUDE_CODE_CAPABILITIES"}
)

#: The function that applies the degrade, and the argument that carries the fact.
FUNCTION_NAME = "capabilities"
FACT_KEYWORD = "pane_driver_available"

#: Who may ask. Still a **set, compared exactly** — widened by one at T23, not
#: relaxed: `toolsurface/compose.py` is the composition, and D29's ceiling
#: (`can_set_title`) has to reach `register_rename_tool` as a value because
#: `toolsurface/` may read neither the record nor the engine's vocabulary. Its
#: fact is the startup reconcile's own answer from the driver — the same
#: observation `admission.py` passes — and `test_no_production_path_hands_the_
#: degrade_a_literal` is what keeps that true of both callers.
PERMITTED_CALLERS: frozenset[str] = frozenset(
    {"orchestration/admission.py", "toolsurface/compose.py"}
)


def constant_reads(path: Path) -> list[str]:
    """Every way this file names the capability record, by AST.

    Four node classes, because a rule keyed on one spelling passes on the
    idiomatic spelling of the same violation (the M1 batch-1 finding): the
    imported name, a bare `Name`, an `Attribute` off any module alias, and a
    **string constant**, which is how `getattr` reaches a private name.
    """
    found: list[str] = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.ImportFrom):
            found += [
                f"imports {alias.name}"
                for alias in node.names
                if alias.name in CONSTANT_NAMES
            ]
        elif isinstance(node, ast.Name) and node.id in CONSTANT_NAMES:
            found.append(f"names {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in CONSTANT_NAMES:
            found.append(f"reads .{node.attr}")
        elif isinstance(node, ast.Constant) and node.value in CONSTANT_NAMES:
            found.append(f"spells {node.value!r}")
    return found


def literal_facts(path: Path) -> list[str]:
    """Calls to `capabilities()` whose `pane_driver_available` is a constant.

    A literal `True` produces the un-degraded record through the front door, so
    the degrade would be dead code on every host. The value has to come from
    somewhere that can say no.
    """
    found: list[str] = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else ""
        )
        if name != FUNCTION_NAME:
            continue
        for keyword in node.keywords:
            if keyword.arg == FACT_KEYWORD and isinstance(keyword.value, ast.Constant):
                found.append(f"passes {FACT_KEYWORD}={keyword.value.value!r}, a literal")
    return found


def test_no_production_path_reads_the_capability_record_directly() -> None:
    """Every module but the one that defines it goes through `capabilities()`."""
    offenders = [
        f"{module.path.relative_to(SRC_ROOT)}: {violation}"
        for module in iter_modules()
        if module.path.resolve() != OWNER_MODULE.resolve()
        for violation in constant_reads(module.path)
    ]
    assert offenders == [], (
        "the capability record carries can_spawn=True unconditionally; only "
        "capabilities(pane_driver_available=...) applies D-5's degrade:\n  "
        + "\n  ".join(offenders)
    )


def test_no_production_path_hands_the_degrade_a_literal() -> None:
    """The other half: the fact must be a fact, not a `True` somebody typed."""
    offenders = [
        f"{module.path.relative_to(SRC_ROOT)}: {violation}"
        for module in iter_modules()
        for violation in literal_facts(module.path)
    ]
    assert offenders == [], "\n  ".join(offenders)


@pytest.mark.parametrize(
    "name",
    [
        "orchestration_reads_the_capability_constant.py",
        "orchestration_reads_the_capability_constant_via_attribute.py",
        "orchestration_reads_the_capability_constant_via_getattr.py",
    ],
)
def test_the_rule_bites_on_each_planted_spelling(name: str) -> None:
    """Three spellings of one violation, each proved to fire.

    The first is Task 11's `Consumes` line written out; the second is what a
    from-import ban misses; the third is a string, invisible to any scan that
    collects identifiers only.
    """
    assert constant_reads(fixture(name)) != []


def test_the_rule_stays_quiet_on_the_correct_call() -> None:
    """A scan needs a negative control proving it stays quiet, not only a
    positive one proving it fires (the M3 T2/T3 finding)."""
    clean = fixture("orchestration_calls_the_capability_function.py")
    assert constant_reads(clean) == []
    assert literal_facts(clean) == []


def test_the_literal_rule_bites_on_a_hardcoded_fact() -> None:
    """`capabilities(pane_driver_available=True)` is the un-degraded record."""
    assert literal_facts(fixture("orchestration_calls_capabilities_without_the_fact.py")) != []


def test_the_degrade_is_actually_wired_where_the_spawn_reads_it() -> None:
    """Wiring, not only absence: the one production caller exists and is real.

    A rule that only forbids something is satisfied by a tree in which nobody
    asks the question at all — `can_spawn` would then be unread rather than
    correct. This asserts the call is there, in `orchestration/`, with the
    keyword, and that it is the only one.
    """
    callers = {
        str(module.path.relative_to(SRC_ROOT))
        for module in iter_modules()
        for node in ast.walk(parsed(module.path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == FUNCTION_NAME
        and any(keyword.arg == FACT_KEYWORD for keyword in node.keywords)
    }
    assert callers == PERMITTED_CALLERS, callers


def test_the_constant_is_private_and_unexported() -> None:
    """T10-R2 made it unimportable rather than asking a builder to remember.

    Asserted here as well as relied on: `__all__` is what `from … import *` and
    every reader's expectation follow, and a re-export is one line away.
    """
    from shepherd.engines.claude_code import spawn as engine

    assert "CLAUDE_CODE_CAPABILITIES" not in engine.__all__
    assert not hasattr(engine, "CLAUDE_CODE_CAPABILITIES")
    assert hasattr(engine, "_" + "CLAUDE_CODE_CAPABILITIES"), (
        "the record still exists; it is private, and this rule is what keeps the "
        "privacy from being a convention"
    )
    assert engine.capabilities(pane_driver_available=False).can_spawn is False
    assert engine.capabilities(pane_driver_available=True).can_spawn is True


def test_the_exemption_is_a_file_not_a_package() -> None:
    """`trust.py` sits in the exempt module's package and is NOT exempt."""
    rogue = fixture("orchestration_reads_the_capability_constant.py")
    assert constant_reads(rogue) != []
    assert (SRC_ROOT / "engines" / "claude_code" / "trust.py").resolve() != OWNER_MODULE.resolve()


def test_the_scan_reads_the_file_before_anything_else() -> None:
    """B1: a missing path raises rather than returning an empty, honest-looking list."""
    with pytest.raises(FileNotFoundError):
        constant_reads(MISSING_MODULE)
    with pytest.raises(FileNotFoundError):
        literal_facts(MISSING_MODULE)
