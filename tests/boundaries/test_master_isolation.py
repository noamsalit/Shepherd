"""T22 — D19 as an **allow-list**, and the residue named rather than claimed gone.

**Why an allow-list and not the shipped consumer rule.** `CONSUMER_PACKAGES`
already contains `shepherd.master`, and `FORBIDDEN_BELOW_L4` is a **deny-list**
that names neither `shepherd.core` nor `shepherd.host` — because `cli/`, the
other D19-governed consumer, has legitimately imported both since M1 (§T7-6).
D19 is stricter than D35: *"reaching the rest of the system only through the
tool-surface client — never a direct import of storage, signals, queues, or
runners."* A deny-list would pass a master that imported `shepherd.host` or
`shepherd.engines.claude_code`, so the master gets an allow-list and the shipped
deny-list keeps running over it as the second net
(`test_the_shipped_deny_list_is_the_second_net_and_is_looser_than_this_one`).

**Every spelling, and a fixture for each.** A boundary rule keyed on one AST
spelling passes on the idiomatic spelling of the very violation it was written
for. `importlib.import_module("shepherd.store.db")` and `__import__(...)` are
`ast.Call` nodes, **not** import nodes; T7 measured that the shared
`module_imports` helper is blind to them and that fifteen shipped rules use it
bare (§T7-3). This rule resolves imports through `all_imports`, which is
`module_imports | dynamic_import_targets`, and ships five inert fixtures — direct,
aliased, from-import, dotted-call and bare-name-call plus `__import__`.

**Reported sets are written out, never counted and never merely non-empty.** A
non-emptiness assertion over a fixture carrying two violations cannot tell
*"caught all of them"* from *"caught the easy one"* — which is exactly the mutant
that survived T7's first sweep. Two of the five fixtures carry two violations
each for that reason.

**Arrival before absence, as an assertion.** Every check that asserts something
is *clean* first asserts the scan found the package and read real imports out of
it, and every scan reads the file before it applies any package exemption, so a
nonexistent path **raises** rather than reporting `[]` (B1, `MISSING_MODULE`).

**The widening carries its own condition.** `core/` is on the allow-list
*because* it is capability-free (RD-T20-D19), so that is asserted here rather
than assumed: the day a `core/` module grows I/O, this rule goes red and the
widening is re-argued instead of silently inherited.

**This file is the deterministic half of nothing.** Clause 9's deterministic half
is T21's `test_the_option_block_locks_the_master`, over the option block; its
live half is `tests/e2e/test_live_master_isolation.py`, over `system/init`. This
is the *structural* rule — a third claim, about imports, and it is filed under
neither of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from _imports import (
    CONSUMER_PACKAGES,
    FIXTURE_DIR,
    FORBIDDEN_BELOW_L4,
    MASTER_ALLOWED_IMPORTS,
    MASTER_FORBIDDEN_FLOOR,
    MASTER_PACKAGE,
    MISSING_MODULE,
    REPO_ROOT,
    SRC_ROOT,
    all_imports,
    fixture,
    in_package,
    iter_modules,
    master_import_violations,
    module_imports,
    permitted_master_import,
    resolved_identifiers,
)

CORE_ROOT = SRC_ROOT / "core"

#: D19's allow-list, its floor and its predicate now live in `_imports` — the
#: shared walker — because T21 had grown a **second** implementation of the same
#: predicate inline in `tests/toolsurface/test_client.py`, and §T22-6 named the
#: convergence. `logs_importer_violations` moved there first, for the same
#: reason: *"one function rather than two that can drift apart"*.
#: `tests/boundaries/test_one_definition_site.py` is what keeps it at one.

#: The five inert fixtures, one per spelling. Enumerated here and iterated at
#: test time; the reported set of each is written out in
#: `EXPECTED_FIXTURE_VIOLATIONS`, never counted.
FIXTURES: tuple[str, ...] = (
    "master_imports_the_store.py",
    "master_imports_orchestration_via_alias.py",
    "master_imports_the_store_dynamically.py",
    "master_imports_the_runner_from_a_package.py",
    "master_imports_the_logs_via_a_bare_name.py",
)

#: What each fixture must report, **whole**. Two of the five carry two
#: violations, because a non-emptiness assertion over a fixture with several
#: violations cannot distinguish *"caught all of them"* from *"caught the easy
#: one"* — T7's own surviving mutant, recorded in §T7-7.
EXPECTED_FIXTURE_VIOLATIONS: dict[str, list[str]] = {
    "master_imports_the_store.py": ["shepherd.store.db"],
    "master_imports_orchestration_via_alias.py": ["shepherd.orchestration.wake"],
    "master_imports_the_store_dynamically.py": ["shepherd.store.db"],
    "master_imports_the_runner_from_a_package.py": [
        "shepherd.runner",
        "shepherd.runner.local",
    ],
    "master_imports_the_logs_via_a_bare_name.py": [
        "shepherd.logs.jsonl",
        "shepherd.signals.fold",
    ],
}

#: The fixtures that **must** construct at module scope, each with the reason.
#: `_binds_real_fold_rule` and the engine-vocabulary rules are about a
#: *construction site* — where a `FoldRule` is built and with what `evidence` —
#: so a fixture that moved the construction into a function would no longer be
#: the thing under test. Named here, with their reason, rather than left outside
#: the scan: the scan below binds **every** planted file in this package, because
#: "a planted violation is an inert fixture" is a claim about all of them and an
#: enumerated subset is a claim about the ones somebody remembered.
#:
#: None of the five performs an effect that leaves the process (CLAUDE.md rule
#: 2): each builds a dataclass or calls a local stub. The rule that matters —
#: *nothing imports them* — binds these five exactly as it binds the rest.
MODULE_SCOPE_FIXTURES: dict[str, str] = {
    "signals_fake_evidence_kwarg.py": (
        "the rule is about an `evidence=` kwarg on a call that is not ours; the "
        "call site is the fixture"
    ),
    "signals_fake_fold_rule_class.py": (
        "a locally declared `class FoldRule` used to switch the scan off (C6); "
        "the construction is what proves it no longer does"
    ),
    "signals_fold_rule_attribute_call.py": (
        "`m.FoldRule(...)` — the attribute spelling of the same exclusion"
    ),
    "signals_fold_rule_definition_site.py": (
        "the declared structural exclusion (ADR-6, F4) is the value of `evidence` "
        "in a real `FoldRule` construction"
    ),
    "signals_fold_rule_evidence.py": (
        "the same exclusion with the real vocabulary, so the scan reads the "
        "value rather than the call"
    ),
}

#: The fixture for `core_capability_violations`' own positive control. Kept out
#: of `FIXTURES` because it is not a master-import fixture and has no entry in
#: `EXPECTED_FIXTURE_VIOLATIONS`; folded back in for the inertness check, which
#: binds every planted file in this package whatever rule it serves.
CORE_FIXTURES: tuple[str, ...] = ("core_grows_io.py",)

#: What that fixture must report, whole: one capability module, one `os.*`
#: identifier and one builtin — the three classes, so dropping any one branch of
#: the rule disagrees with a literal.
EXPECTED_CORE_VIOLATIONS: list[str] = ["open", "os.fork", "socket"]

#: Modules that are a capability whatever you do with them. `core/` importing any
#: of these is the day RD-T20-D19's widening is re-argued.
#:
#: **`os` is deliberately absent**, and the reason is measured rather than
#: assumed: `core/ids.py` imports it for `os.urandom`, which is entropy and not
#: I/O. The `os` half of the rule is written one level down, at the identifier,
#: so `os.urandom` passes and `os.system` does not.
CORE_CAPABILITY_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "socket",
        "sqlite3",
        "shutil",
        "signal",
        "selectors",
        "asyncio",
        "multiprocessing",
        "http",
        "urllib",
        "ssl",
        "tempfile",
        "io",
        "pathlib",
        "ctypes",
        "mmap",
        "fcntl",
        "pty",
        "resource",
        "webbrowser",
    }
)

#: Every `os.*` name `core/` is allowed to resolve. Measured on this tree: one.
CORE_PERMITTED_OS_NAMES: frozenset[str] = frozenset({"os", "os.urandom"})

#: Capability *builtins*, which need no import and so leave no import node to key
#: on — the same blindness one node class over.
CORE_CAPABILITY_BUILTINS: frozenset[str] = frozenset(
    {"open", "eval", "exec", "compile", "__import__"}
)


def core_capability_violations(path: Path) -> list[str]:
    """Every capability `path` reaches — the condition under RD-T20-D19's widening.

    Three classes, because a capability arrives three ways: as a module import, as
    an `os.*` identifier `core/` has no business resolving, and as a builtin that
    needs no import at all. Identifiers are read **after alias resolution**, so
    `import os as o; o.system` is the same violation as `os.system`.

    **The builtin class used to be a second, inline `ast.walk` right here**, because
    `resolved_identifiers` collected dotted chains only and `open(path)` leaves no
    chain to collect — the same blindness as the call-shaped import, one node class
    over (§T22-3). That made this one boundary rule with two halves in two shapes,
    which is RD-T5-5's defect in miniature. The walker was widened instead — it now
    collects a bare name when it is a **callee**, which a field never is — and the
    inline branch is gone. `core_grows_io.py` still reports all three classes, and
    `EXPECTED_CORE_VIOLATIONS` is what says so.
    """
    imported = all_imports(path)
    names = resolved_identifiers(path)
    found = {
        name
        for name in imported
        if name.split(".")[0] in CORE_CAPABILITY_MODULES
    }
    found |= {
        name
        for name in names
        if name.split(".")[0] == "os" and name not in CORE_PERMITTED_OS_NAMES
    }
    found |= names & CORE_CAPABILITY_BUILTINS
    return sorted(found)


def test_master_imports_only_the_client_and_the_sdk() -> None:
    """P-M4-8. The real package is clean, and the rule bites on all five spellings.

    Arrival first, and it is an assertion rather than a comment: the scan is
    shown to have found the master's modules and to have read real import names
    out of them **before** the emptiness of the violation list is allowed to
    mean anything. A rule pointed at nothing reports nothing.
    """
    scanned = {
        module.path.name
        for module in iter_modules()
        if in_package(module.package, MASTER_PACKAGE)
    }
    assert {"sdk_master.py", "sdk_tools.py", "projection.py", "prompt.py"} <= scanned, (
        f"the master scan found only {sorted(scanned)}"
    )

    seen: set[str] = set()
    violations: dict[str, list[str]] = {}
    for module in iter_modules():
        if not in_package(module.package, MASTER_PACKAGE):
            continue
        seen |= all_imports(module.path)
        found = master_import_violations(module.path, module.package)
        if found:
            violations[module.path.name] = found
    assert "claude_agent_sdk" in seen, (
        "the scan read no vendor import out of master/, so it is not reading imports"
    )
    assert "shepherd.toolsurface.client" in seen, (
        "the scan read no client import out of master/, so it is not reading imports"
    )
    assert violations == {}, violations

    # …and the rule bites, with the **whole reported set** written out per
    # fixture. Two of the five carry two violations each, so a rule that caught
    # only the first would disagree with a literal rather than with itself.
    assert {
        name: master_import_violations(fixture(name), MASTER_PACKAGE)
        for name in FIXTURES
    } == EXPECTED_FIXTURE_VIOLATIONS

    # B1: a scan that cannot raise on a missing path is a scan that never opened
    # one. The package exemption is applied to the *result*, after the read.
    with pytest.raises(FileNotFoundError):
        master_import_violations(MISSING_MODULE, MASTER_PACKAGE)
    with pytest.raises(FileNotFoundError):
        master_import_violations(MISSING_MODULE, "shepherd.cli")


def test_the_allow_list_is_asserted_whole() -> None:
    """The allowed set, compared against a literal written in this test.

    Not derived from the rule and not recomputed the way the rule computes it: a
    set equality against a typed-out literal is what makes *"adding a package to
    the allow-list to make a build pass"* a **plan change** rather than an edit
    (Task 22's Out-of-Scope Drift names it as a Decision pressure by name).
    """
    assert MASTER_ALLOWED_IMPORTS == frozenset(
        {
            "shepherd.toolsurface.client",
            "shepherd.core",
            "shepherd.master",
            "claude_agent_sdk",
            "anyio",
        }
    )
    # The seam is the client, singular — `registry` is **not** on it, because a
    # master that can reach `registry` can reach `registered_tools()` and read
    # around `invoke()`.
    assert not permitted_master_import("shepherd.toolsurface.registry")
    assert not permitted_master_import("shepherd.toolsurface")
    # Prefixes match on **module boundaries**. A bare `startswith` would let a
    # package called `shepherd.coretools` in through the `shepherd.core` entry —
    # the defect is invisible today because no such package exists, which is
    # exactly when it is worth an assertion rather than a review.
    assert not permitted_master_import("shepherd.coretools.thing")
    assert not permitted_master_import("shepherd.masterful")
    assert not permitted_master_import("claude_agent_sdk_shim")
    assert permitted_master_import("shepherd.toolsurface.client")
    assert permitted_master_import("shepherd.toolsurface.client.call")


def test_the_allow_list_has_a_floor_and_the_floor_is_not_a_hole() -> None:
    """RD-T20-D19's clause, restated where a reader of D19 will look for it.

    The floor is redundant under an allow-list *today* — every one of these is
    already outside it — and it is written down anyway, for the same reason
    `tests/toolsurface/test_client.py` grew one when T21 widened the permitted
    set to `shepherd.master.*`: the next widening is argued against a rule that
    still says, in D19's own vocabulary, what may never be reached.

    Enumerated at test time and asserted as a property of the predicate, never
    by planting a module into a live tree.
    """
    assert MASTER_FORBIDDEN_FLOOR == frozenset(
        {
            "shepherd.store",
            "shepherd.logs",
            "shepherd.orchestration",
            "shepherd.daemons",
            "shepherd.web",
            "shepherd.signals",
            "shepherd.runner",
            "shepherd.engines",
            "shepherd.providers",
        }
    )
    assert MASTER_FORBIDDEN_FLOOR & MASTER_ALLOWED_IMPORTS == frozenset()
    for package in sorted(MASTER_FORBIDDEN_FLOOR):
        assert not permitted_master_import(package), package
        assert not permitted_master_import(f"{package}.anything"), package
    # Arrival: the predicate says yes to something, or the loop above proves
    # nothing but that it always says no.
    assert permitted_master_import("shepherd.core.anomalies.AnomalyKind")
    assert permitted_master_import("shepherd.master.projection")
    assert permitted_master_import("claude_agent_sdk.ClaudeSDKClient")
    assert permitted_master_import("anyio.to_thread")
    assert permitted_master_import("asyncio")  # stdlib


def test_the_rule_sees_a_dynamic_import() -> None:
    """The call form, and the measurement that shows it is not free.

    The second assertion is the one that matters: `module_imports` — the helper
    fifteen shipped rules use bare — reports this fixture as importing
    `importlib` and **nothing else**. So the rule's extension to the call form is
    not decoration; drop it and the fixture goes clean while the store is loaded
    and reachable exactly as if it had been imported by statement.
    """
    dotted = fixture("master_imports_the_store_dynamically.py")
    bare = fixture("master_imports_the_logs_via_a_bare_name.py")

    assert master_import_violations(dotted, MASTER_PACKAGE) == ["shepherd.store.db"]
    assert master_import_violations(bare, MASTER_PACKAGE) == [
        "shepherd.logs.jsonl",
        "shepherd.signals.fold",
    ]

    assert "shepherd.store.db" not in module_imports(dotted), (
        "module_imports has been widened — §T7-3 is closed and this check's "
        "premise needs re-reading"
    )
    assert not [
        name for name in module_imports(bare) if name.startswith("shepherd.")
    ], sorted(module_imports(bare))


def test_the_fixtures_are_inert() -> None:
    """By AST, and never by a text search — a grep for `import` reads a docstring.

    Two properties, because "inert" is two claims:

    1. **Nothing executes on import.** The module body contains no call at all;
       every planted call sits inside a function nobody invokes. Asserted over
       the top-level statements, so a call moved up to module scope is red.
    2. **Nothing imports them.** The fixture directory is not a package (no
       `__init__.py`), and no module anywhere under `src/` or `tests/` names one
       of these files as an import — by statement or by call.

    This is CLAUDE.md's mutation rule made mechanical: *a planted violation is an
    inert fixture that nothing imports*. The 2026-09-17 reboot is what a fixture
    that runs costs.
    """
    assert not (FIXTURE_DIR / "__init__.py").exists(), (
        "the fixture directory became a package, so its modules are importable"
    )

    planted = sorted(path.name for path in FIXTURE_DIR.glob("*.py"))
    # Arrival: the enumeration found the whole package, not a stale tuple. Every
    # fixture this file names is in it, and so is every fixture every *other*
    # rule in this package plants — which is the point of scanning the directory.
    assert {*FIXTURES, *CORE_FIXTURES, *MODULE_SCOPE_FIXTURES} <= set(planted), planted
    assert "runner_kill_server.py" in planted and "hookd_command_clean.py" in planted

    offenders: dict[str, str] = {}
    for name in planted:
        path = fixture(name)
        source = path.read_text(encoding="utf-8")
        # Non-empty **source**, not a non-empty AST body: `oversized_module.py` is
        # 601 comment lines, because the rule it serves counts lines rather than
        # statements. Each fixture's own rule is what asserts its content is the
        # content (B3); this half only asserts it was not emptied.
        assert source.strip(), name
        body = ast.parse(source).body
        calls = [
            node
            for statement in body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
        ]
        if calls:
            offenders[name] = ast.unparse(calls[0])
    assert set(offenders) == set(MODULE_SCOPE_FIXTURES), {
        "undeclared": sorted(set(offenders) - set(MODULE_SCOPE_FIXTURES)),
        "declared but inert": sorted(set(MODULE_SCOPE_FIXTURES) - set(offenders)),
    }
    for name, reason in MODULE_SCOPE_FIXTURES.items():
        assert len(reason.split()) >= 8, name

    module_names = {Path(name).stem for name in planted}

    def importers_of(wanted: frozenset[str]) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for path in sorted(
            (*SRC_ROOT.rglob("*.py"), *(REPO_ROOT / "tests").rglob("*.py"))
        ):
            if "__pycache__" in path.parts or path.parent == FIXTURE_DIR:
                continue
            named = {
                name.rpartition(".")[2] if "." in name else name
                for name in all_imports(path)
            } & wanted
            if named:
                found[str(path.relative_to(REPO_ROOT))] = sorted(named)
        return found

    # **Positive control, and it is what stops this from being a scan of
    # nothing.** The same detector is pointed at a module that *is* imported all
    # over this package, and must find it — including from this very file.
    control = importers_of(frozenset({"_imports"}))
    assert "tests/boundaries/test_master_isolation.py" in control, sorted(control)
    assert len(control) >= 5, sorted(control)

    assert importers_of(frozenset(module_names)) == {}


def test_core_is_capability_free_which_is_why_the_widening_holds() -> None:
    """RD-T20-D19's **condition**, asserted rather than inherited.

    `core/` is on the master's allow-list because it is vocabulary — dataclasses,
    enums, Protocols and a ULID minter — and *"`core/` is measurably
    capability-free"* is the third of the three facts that settled the widening.
    A condition nobody checks is a condition that expires quietly, so the day a
    `core/` module grows I/O this goes red and the widening is re-argued.

    **`os` is not banned wholesale, and the reason is measured, not assumed:**
    `core/ids.py` imports it for `os.urandom`, which is entropy, not I/O. So the
    `os` half of the rule is written at the **identifier** level — every `os.*`
    name `core/` resolves must be on a written-out list — while the modules that
    are capabilities whatever you do with them are banned outright.

    Non-vacuity is proved by pointing the same scan at a module that **is** a
    capability: `store/db.py` opens sqlite, and the rule reports it.
    """
    assert core_capability_violations(CORE_ROOT / "ids.py") == []

    scanned = 0
    for module in iter_modules():
        if not in_package(module.package, "shepherd.core"):
            continue
        scanned += 1
        assert core_capability_violations(module.path) == [], module.path.name
    assert scanned >= 5, f"the core scan found only {scanned} modules"

    # …and the non-shepherd.core Shepherd imports are none: `core/` is L1 and
    # imports nothing of ours but itself.
    reached = {
        name
        for module in iter_modules()
        if in_package(module.package, "shepherd.core")
        for name in all_imports(module.path)
        if name.startswith("shepherd.") and not name.startswith("shepherd.core.")
    }
    assert reached == set(), sorted(reached)

    # The rule bites, twice over. `store/db.py` is **shipped** code that is
    # supposed to hold a capability — nothing planted, nothing edited — and the
    # fixture carries one of each of the rule's three classes, reported **whole**
    # so that dropping a branch disagrees with a literal rather than with itself.
    assert "sqlite3" in core_capability_violations(SRC_ROOT / "store" / "db.py")
    assert (
        core_capability_violations(fixture(CORE_FIXTURES[0])) == EXPECTED_CORE_VIOLATIONS
    )

    # …and the walker widening behind the third class is a **widening, not a
    # rewrite**: the two dotted spellings `resolved_identifiers` resolved before
    # still resolve, and the bare-name call is what it gained. Asserted at the
    # helper, because the rule above would report the same three names if the
    # inline branch had merely moved rather than converged.
    names = resolved_identifiers(fixture(CORE_FIXTURES[0]))
    assert {"os.fork", "socket.socket"} <= names, sorted(names)
    assert "open" in names, sorted(names)
    # A field is still never mistaken for an origin: `handle.read` stays a bare
    # dotted chain and no bare *attribute* name enters the set.
    assert "read" not in names and "handle.read" in names, sorted(names)

    with pytest.raises(FileNotFoundError):
        core_capability_violations(MISSING_MODULE)


def test_the_shipped_deny_list_is_the_second_net_and_is_looser_than_this_one() -> None:
    """Why this file exists, asserted over the shipped rule's own constants.

    The allow-list did not replace the deny-list: `shepherd.master` is in
    `CONSUMER_PACKAGES`, so `test_consumer_boundary`'s rule already binds every
    module under `master/` and keeps running over it. That rule is **not
    re-implemented here** — RD-T5-5 is the standing finding that a boundary rule
    copied into a second file is a rule that can be widened in one place and keep
    biting from another — so what is asserted is the two facts the allow-list's
    existence rests on, measured off the shipped constants:

    1. the deny-list does bind `master/`; and
    2. it names neither `core` nor `host`, so a master importing
       `shepherd.host.detect` or `shepherd.engines.claude_code` would pass it.

    Tighten `FORBIDDEN_BELOW_L4` and this goes red — which is correct: the
    rationale for a second rule would have changed and is owed a re-reading. Note
    that tightening it is **not** free, and §T7-6 measured why: `cli/` imports
    `core.anomalies`, `core.states`, `host.base` and `host.detect` today, and
    D38 forbids M4 from changing `cli/`.
    """
    assert MASTER_PACKAGE in CONSUMER_PACKAGES
    assert "shepherd.core" not in FORBIDDEN_BELOW_L4
    assert "shepherd.host" not in FORBIDDEN_BELOW_L4
    assert not permitted_master_import("shepherd.host.detect")
    assert not permitted_master_import("shepherd.engines.claude_code")

    # …and the packages the deny-list *does* name are a strict subset of this
    # rule's floor, so the two never disagree about a verdict.
    assert FORBIDDEN_BELOW_L4 <= MASTER_FORBIDDEN_FLOOR | {"shepherd.logs"}, sorted(
        FORBIDDEN_BELOW_L4 - MASTER_FORBIDDEN_FLOOR
    )
