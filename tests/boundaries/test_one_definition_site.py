"""RD-T5-5 — a boundary predicate has **one** definition site, found by property.

**The defect this exists for, in the words the router recorded it in.** DP3's
rule existed in *three* places; T7 widened one and audited a second — the wrong
one, whose own guard excluded L4 so it never bound the module in question — and
the third lived in `tests/logs/test_stop_log.py`, walked `toolsurface/` directly,
and was **red on arrival** against the very file DP3's widening existed to
permit. D19's master predicate then grew a second implementation the same way:
T21's inline block in `tests/toolsurface/test_client.py` and T22's
`master_import_violations`. *They agreed exactly, and the duplication was the
defect, not either copy* — because a rule copied into a second file is a rule
that can be widened in one place and keep biting from another, and the copy is
invisible to whoever owns the original.

**Nothing in this tree asserted that a boundary rule has one implementation.**
This module does, and it does it **by property** rather than by a list of the
rules somebody remembered: every module-level function under `tests/` that reads
Python source *structurally* — it walks `ast.*` nodes, or it calls one of the
shared walker's scanners — is a rule of this kind, whatever it is called and
wherever it lives. So a fourth copy cannot arrive unnoticed: it either collides
with an existing name (caught as a second site) or it arrives as a name nobody
declared (caught by the inventory equality).

**Two assertions, and they fail for different reasons.**

1. `second_definition_sites()` — a name defined twice. The reviewed exceptions
   are in `DECLARED_SECOND_SITES`, which is **non-empty today**: four scanners
   were already duplicated when this check landed, each is named with its reason
   and its owner, and a *stale* entry (a name that has since converged) is red
   too. A declaration nobody re-checks is the thing this file exists to refuse.
2. `undeclared_scanners()` — a scanner in a module the inventory does not name.
   The inventory is per **module**, not per function: a new rule inside a file
   that already holds rules is ordinary work, and a rule appearing in a file
   nobody thought held rules is the event RD-T5-5 is about.

**The scan reads the file before it decides anything** (B1) and
`MISSING_MODULE` raises rather than reporting `{}`, like every other rule here.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest
from _imports import MISSING_MODULE, REPO_ROOT, Module, modules_defining

TESTS_ROOT = REPO_ROOT / "tests"

#: The shared walker's scanners. A function that calls one of these is reading
#: source structurally even if it never names `ast` itself — which is the whole
#: point of the walker existing, and would otherwise be a way out of this rule.
SHARED_SCANNERS: frozenset[str] = frozenset(
    {
        "all_imports",
        "dynamic_import_targets",
        "identifiers",
        "imported_names",
        "layer_map_violations",
        "logs_importer_violations",
        "master_import_violations",
        "module_imports",
        "modules_defining",
        "parsed",
        "resolved_identifiers",
        "single_logs_importer_violations",
        "string_literals",
        "vendor_sdk_violations",
    }
)

#: The names that had a second definition site when this check landed, each with
#: the reason it is still two and who owns closing it. **Every entry is asserted
#: to still be a duplicate**, so a converged name cannot leave a stale exemption
#: behind (the remediation's MUT-1: a stale exemption is a hole).
#:
#: None of these four is a *boundary* rule in the D19/DP3 sense — they are import
#: and literal readers used by ordinary module-level assertions — which is why
#: they are declared rather than converged in this pass: converging them changes
#: the population four shipped checks measure, and that is a change with its own
#: mutation ledger, not a line. They are recorded here so the next person sees
#: four, in one place, with their reasons, instead of finding the fifth.
DECLARED_SECOND_SITES: Mapping[str, str] = {
    "identifiers": (
        "`_imports.identifiers(path)` reads a file; `tests/web/test_security.py`'s "
        "reads an `ast.Module`, because its own self-check parses a synthetic "
        "module from a string and has no file to hand. Same name, different "
        "argument — the collision is real and the convergence needs the shared "
        "walker to grow a tree-taking form first. Owner: whoever does."
    ),
    "imported_names": (
        "three sites: `tests/daemons/test_controld.py`, "
        "`tests/daemons/test_controld_composition.py` and "
        "`tests/toolsurface/test_client.py`. The first two return the names an "
        "import *binds*; the third returns module paths **and** bound symbols. "
        "One name, two meanings — and `test_controld.py`'s docstring defends the "
        "copy in exactly the words RD-T5-5 refuses (*'repeated rather than "
        "shared'*). Owner: router."
    ),
    "imported_modules": (
        "`tests/test_core_types.py` resolves relative imports against a package; "
        "`tests/toolsurface/test_policy.py` resolves the two call-shaped "
        "spellings. Both are `module_imports`/`all_imports` re-derived — the "
        "fourth and fifth implementations of the walker in this tree, measured "
        "by this check. Owner: router."
    ),
    "parsed": (
        "`_parse.parsed` is the shared walker's cached `ast.parse`; "
        "`tests/signals/test_normalise.py`'s `parsed` parses a **hook payload** "
        "into a `Signal` and has nothing to do with Python source. A genuine "
        "name collision rather than a copied rule — and it is exactly the kind "
        "the name half of this check is for, because the next reader of either "
        "file has to work out which one they are looking at. Owner: router; the "
        "cheap fix is a rename on the signals side."
    ),
    "purity_violations": (
        "`tests/test_core_types.py` proves `core/` imports only stdlib and "
        "`core`; `tests/toolsurface/test_policy.py` proves `policy.py` imports "
        "only a written-out permitted set. Two purity rules, two populations, "
        "one name — and both rest on their own `imported_modules`, which is the "
        "duplication one row up. Owner: router."
    ),
    "scope_violations": (
        "Gate A's (`test_consumer_surface_frozen.py`) and Gate B's "
        "(`test_consumer_surface_additive.py`). They guard different freezes — a "
        "digest set and a route/import table — and the remediation's "
        "`subset_violations` was written to the same shape deliberately. This is "
        "a shared **idiom**, not a shared rule, and renaming either would make "
        "the gates harder to read. Declared rather than converged, on purpose. "
        "Owner: nobody — this entry exists to say the collision was looked at."
    ),
    "_string_literals": (
        "`tests/signals/test_normalise.py` takes a path, `tests/test_core_runner.py` "
        "takes source text; both are `_imports.string_literals` without its "
        "docstring exclusion. Owner: router."
    ),
}

#: Every test module that holds a source-reading rule, enumerated at test time
#: and compared as a **set**. A rule arriving in a file that held none is the
#: event this names; a rule arriving beside its siblings is ordinary work.
DECLARED_SCANNER_MODULES: frozenset[str] = frozenset(
    {
        "tests/boundaries/_imports.py",
        "tests/boundaries/_parse.py",
        "tests/boundaries/_taint.py",
        "tests/boundaries/test_capability_degrade.py",
        "tests/boundaries/test_collected_node_ids.py",
        "tests/boundaries/test_consumer_surface_additive.py",
        "tests/boundaries/test_consumer_surface_frozen.py",
        "tests/boundaries/test_composition_root.py",
        "tests/boundaries/test_consumer_boundary.py",
        "tests/boundaries/test_dispatch_command_site.py",
        "tests/boundaries/test_engine_config_is_read_only.py",
        "tests/boundaries/test_engine_vocabulary.py",
        "tests/boundaries/test_hookd_isolation.py",
        "tests/boundaries/test_layer_direction.py",
        "tests/boundaries/test_master_isolation.py",
        "tests/boundaries/test_one_clock.py",
        "tests/boundaries/test_one_definition_site.py",
        "tests/boundaries/test_platform_branching.py",
        "tests/boundaries/test_session_audience.py",
        "tests/boundaries/test_stop_reason_is_never_read_from_a_payload.py",
        "tests/boundaries/test_storage_boundary.py",
        "tests/boundaries/test_tmux_blast_radius.py",
        "tests/boundaries/test_ws_read_path.py",
        "tests/cli/test_replay_command.py",
        "tests/contracts/test_hostplatform_contract.py",
        "tests/contracts/test_master_contract.py",
        "tests/daemons/test_controld.py",
        "tests/daemons/test_controld_composition.py",
        "tests/daemons/test_sessiond_isolation.py",
        "tests/engines/test_evidence.py",
        "tests/engines/test_registry_source.py",
        "tests/engines/test_spawn_argv.py",
        "tests/master/test_prompt.py",
        "tests/master/test_sdk_tools.py",
        "tests/orchestration/test_ask.py",
        "tests/orchestration/test_master_turn.py",
        # The M1–M4 QA pass (2026-09-18). `modules_that_call_resume` is S6's
        # single-caller scan for `MasterRuntime.resume()` — the same shape as
        # `test_master_turn.py`'s `modules_that_call_send` (P-M4-21) and
        # deliberately **not** shared with it: they answer about different
        # members, and one parameterised walker over two rules is the shape
        # RD-T5-5 asks for only when the rule is the same rule.
        "tests/qa/test_s6_restart_continuity.py",
        "tests/runner/test_local.py",
        "tests/signals/test_discovery_loop.py",
        "tests/signals/test_normalise.py",
        "tests/signals/test_replay.py",
        "tests/signals/test_verdict.py",
        "tests/store/test_retry_link.py",
        "tests/store/test_store_delegation.py",
        "tests/test_core_master.py",
        "tests/test_core_runner.py",
        "tests/test_core_types.py",
        "tests/testkit/test_scripted_master.py",
        "tests/toolsurface/test_approvals.py",
        "tests/toolsurface/test_client.py",
        "tests/toolsurface/test_export.py",
        "tests/toolsurface/test_policy.py",
        "tests/toolsurface/test_registry_gate.py",
        "tests/web/test_routes.py",
        "tests/web/test_security.py",
        "tests/web/test_ws.py",
    }
)


def reads_source_structurally(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this function inspect Python source as a tree?

    Two ways, and both are needed: it names an `ast.*` member, or it calls one of
    the shared walker's scanners. A rule written entirely in terms of
    `all_imports` names `ast` nowhere, and it is exactly the kind of rule this
    check is about.
    """
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "ast"
        ):
            return True
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id in SHARED_SCANNERS
        ):
            return True
    return False


def is_a_rule(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Is this function a boundary rule — **by body or by name**?

    By body: it inspects source as a tree (`reads_source_structurally`).

    By name: it ends in `_violations` — this tree's convention for a rule that
    returns readable findings — or it is one of the shared walker's scanners.
    The name half is not decoration. A copy that **stubs the body**
    (`def master_import_violations(path, package): return []`) inspects nothing,
    so the body half walks straight past it, and a stub is exactly how a second
    implementation arrives: somebody needed the name to exist in their file.
    Measured: without the name half, MUT-12 — a second `master_import_violations`
    planted in the very file §T22-6 named — **survived**.
    """
    return (
        reads_source_structurally(node)
        or node.name.endswith("_violations")
        or node.name in SHARED_SCANNERS
    )


def scanners_in(path: Path) -> dict[str, int]:
    """`name -> line` for every module-level boundary rule in `path`.

    Module level only. A closure inside a test is that test's own working, not a
    rule another file could come to depend on — and a `test_*` function is the
    assertion, never the predicate.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name: node.lineno
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("test_")
        and is_a_rule(node)
    }


def scanner_sites() -> dict[str, list[str]]:
    """`name -> ['tests/…/x.py:12', …]` over the whole test tree.

    `fixtures/` is excluded: a planted violation is source somebody wrote to be
    *read*, not a rule that reads.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or "fixtures" in path.parts:
            continue
        for name, line in scanners_in(path).items():
            found.setdefault(name, []).append(
                f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"
            )
    return found


def second_definition_sites(
    sites: Mapping[str, list[str]], declared: Mapping[str, str]
) -> list[str]:
    """Names with more than one definition site that nobody declared.

    A pure predicate over two mappings, so both of its failure paths can be
    driven from a literal instead of shipping untested — the shape `scope_violations`
    uses in Gate A and `subset_violations` uses in the remediation.
    """
    return sorted(
        f"{name} is defined {len(where)} times: {where}"
        for name, where in sites.items()
        if len(where) > 1 and name not in declared
    )


def stale_declarations(
    sites: Mapping[str, list[str]], declared: Mapping[str, str]
) -> list[str]:
    """Declared exceptions that are no longer duplicated — or gone entirely."""
    return sorted(
        f"{name} is declared as a second site but has {len(sites.get(name, []))}"
        for name in declared
        if len(sites.get(name, [])) < 2
    )


def undeclared_scanner_modules(
    sites: Mapping[str, list[str]], declared: frozenset[str]
) -> list[str]:
    """Modules holding a source-reading rule that the inventory does not name."""
    live = {where.rsplit(":", 1)[0] for places in sites.values() for where in places}
    return sorted(
        f"{module} holds a source-reading rule and is not in the inventory"
        for module in live - declared
    )


def test_every_source_reading_rule_has_one_definition_site() -> None:
    """RD-T5-5, as a property of the tree rather than of anyone's memory."""
    sites = scanner_sites()

    # Arrival, as an assertion and not a comment: the scan is shown to have found
    # the rules this check is about **before** its emptiness is allowed to mean
    # anything. A scan pointed at nothing reports no duplication.
    assert {"module_imports", "all_imports", "master_import_violations"} <= set(sites), (
        f"the scan found only {sorted(sites)}"
    )
    # The two predicates RD-T5-5 and §T22-6 are about, each at exactly one site,
    # and that site is the shared walker. Compared by **file**, not by line: a
    # line number is a spelling, and a check that goes red when a docstring gains
    # a sentence teaches its readers to re-bless it.
    for predicate in ("master_import_violations", "logs_importer_violations"):
        assert [where.rsplit(":", 1)[0] for where in sites[predicate]] == [
            "tests/boundaries/_imports.py"
        ], sites[predicate]

    assert second_definition_sites(sites, DECLARED_SECOND_SITES) == []
    assert stale_declarations(sites, DECLARED_SECOND_SITES) == []
    assert undeclared_scanner_modules(sites, DECLARED_SCANNER_MODULES) == []

    # …and the inventory is exact in the other direction too: a module that
    # stopped holding a rule must leave, or the set decays into a list of places
    # somebody once looked.
    live = {where.rsplit(":", 1)[0] for places in sites.values() for where in places}
    assert live == set(DECLARED_SCANNER_MODULES), {
        "undeclared": sorted(live - set(DECLARED_SCANNER_MODULES)),
        "declared but gone": sorted(set(DECLARED_SCANNER_MODULES) - live),
    }


def test_every_declared_second_site_carries_its_reason() -> None:
    """A named exception list is only a list of excuses without the reasons.

    Each entry names *where* the copies are and *who* closes it — the shape
    `RETIRED_NODE_IDS` uses, which is the precedent for a non-empty exception
    list in this tree.
    """
    assert DECLARED_SECOND_SITES, "the exception list is empty — say so in the test"
    for name, reason in DECLARED_SECOND_SITES.items():
        assert "Owner:" in reason or "owner" in reason, name
        assert len(reason.split()) >= 12, name


def test_the_duplication_check_bites() -> None:
    """Both predicates, on literals, so the expected answer is not recomputed.

    The live tree satisfies them, so written inline they would be assertions
    nothing could exercise — the shape of the defect they exist to prevent.
    """
    one = {"storage_violations": ["tests/boundaries/test_storage_boundary.py:32"]}
    two = {
        "storage_violations": [
            "tests/boundaries/test_storage_boundary.py:32",
            "tests/logs/test_stop_log.py:88",
        ]
    }

    assert second_definition_sites(one, {}) == []
    assert second_definition_sites(two, {}) == [
        "storage_violations is defined 2 times: "
        "['tests/boundaries/test_storage_boundary.py:32', 'tests/logs/test_stop_log.py:88']"
    ]
    # …and a declared exception silences that one and nothing else.
    assert second_definition_sites(two, {"storage_violations": "declared"}) == []
    assert second_definition_sites(
        {**two, "clock_violations": ["a:1", "b:2"]}, {"storage_violations": "declared"}
    ) == ["clock_violations is defined 2 times: ['a:1', 'b:2']"]

    # A declaration that has outlived its duplication is a hole, not a tidy-up.
    assert stale_declarations(two, {"storage_violations": "declared"}) == []
    assert stale_declarations(one, {"storage_violations": "declared"}) == [
        "storage_violations is declared as a second site but has 1"
    ]
    assert stale_declarations({}, {"gone_entirely": "declared"}) == [
        "gone_entirely is declared as a second site but has 0"
    ]

    # …and the inventory half.
    assert undeclared_scanner_modules(one, frozenset(DECLARED_SCANNER_MODULES)) == []
    assert undeclared_scanner_modules(
        {"new_rule": ["tests/somewhere/test_new.py:10"]}, frozenset()
    ) == ["tests/somewhere/test_new.py holds a source-reading rule and is not in the inventory"]


def test_the_detector_reads_the_file_and_knows_a_rule_from_a_test() -> None:
    """B1, and the classifier's own two branches, on planted text.

    The classifier is the half that decides what counts as a rule, so it is
    exercised directly: a function that walks `ast` counts, a function that calls
    the shared walker counts **even though it never names `ast`**, and a plain
    helper does not.
    """
    with pytest.raises(FileNotFoundError):
        scanners_in(MISSING_MODULE)

    def classify(source: str) -> dict[str, int]:
        tree = ast.parse(source)
        return {
            node.name: node.lineno
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("test_")
            and is_a_rule(node)
        }

    assert classify("def walks(p):\n    return ast.walk(p)\n") == {"walks": 1}
    assert classify("def delegates(p):\n    return all_imports(p)\n") == {"delegates": 1}
    assert classify("def plain(a, b):\n    return a + b\n") == {}
    # …and by **name**, which is what catches a stubbed copy: this body inspects
    # nothing at all, and a body-only detector let MUT-12 survive.
    assert classify("def master_import_violations(p, q):\n    return []\n") == {
        "master_import_violations": 1
    }
    assert classify("def storage_violations(p, q):\n    return []\n") == {
        "storage_violations": 1
    }
    # a test is the assertion, never the predicate…
    assert classify("def test_x():\n    assert ast.walk(1)\n") == {}
    # …and a closure inside one is that test's own working.
    assert classify("def test_x():\n    def inner(p):\n        return ast.walk(p)\n") == {}


# ----- the same property, over `src/` (RD-T4-3, §T6-4) -----------------------

#: The three names that were declared twice in product code until the QA-prep
#: pass, each with the module that is now their **only** home. Both duplications
#: were forced, and identically: the clean import would have dragged
#: `shepherd.logs` into `shepherd status` through `cli/`'s import of `registry`,
#: and **the shipped DP3 rule checks only direct importers, so it would have
#: passed while being defeated**. `types.py` is stdlib-only, which is why it can
#: hold all three without re-opening the hole.
#:
#: They were held by **drift guards** — two modules compared for equality. A
#: drift guard makes a second declaration *safe*; it does not make it *absent*,
#: and it says nothing at all about a third. This does.
ONE_DECLARATION_EACH: Mapping[str, str] = {
    "SECRET_KEY_MARKERS": "shepherd.toolsurface.types",
    "REDACTED": "shepherd.toolsurface.types",
    "actor_kind_of": "shepherd.toolsurface.types",
}


def declaring_modules(name: str) -> list[str]:
    """Every product module binding `name` at module level, as dotted names.

    `modules_defining` is the shared walker's discovery-by-property (B2) and it
    counts **bindings**, never imports — so a module that imports the name reads
    the one declaration rather than adding another.
    """
    return sorted(f"{module.package}.{module.path.stem}" for module in modules_defining(name))


def test_the_redaction_rule_has_one_definition_site() -> None:
    """RD-T4-3, closed and kept closed."""
    assert declaring_modules("SECRET_KEY_MARKERS") == ["shepherd.toolsurface.types"]
    assert declaring_modules("REDACTED") == ["shepherd.toolsurface.types"]

    # Arrival: the discovery really does find declarations in this tree, so the
    # two assertions above are about the rule and not about a scan of nothing.
    assert "shepherd.toolsurface.registry" in declaring_modules("GENERIC_ERROR")
    assert declaring_modules("a_name_no_module_binds") == []


def test_the_actor_kind_derivation_has_one_definition_site() -> None:
    """§T6-4, closed and kept closed.

    `registry.py` held the second copy and `audit.py` the first; both now import
    from `types.py`. A third — in a new module, under the same forced constraint
    — is a failing build here rather than a drift guard somebody remembers to
    write.
    """
    assert declaring_modules("actor_kind_of") == ["shepherd.toolsurface.types"]
    assert declaring_modules("_actor_kind_of") == []
    assert declaring_modules("_KIND_BY_AUDIENCE") == ["shepherd.toolsurface.types"]


def test_the_src_side_check_bites() -> None:
    """The predicate on a literal, and the table it reads asserted whole.

    The live tree satisfies the two checks above, so the *second declaration*
    case would otherwise ship untested — which is the shape of the defect this
    file exists to prevent.
    """
    assert set(ONE_DECLARATION_EACH) == {"SECRET_KEY_MARKERS", "REDACTED", "actor_kind_of"}
    for name, home in ONE_DECLARATION_EACH.items():
        assert declaring_modules(name) == [home], name

    def second_declarations(found: Mapping[str, list[str]]) -> list[str]:
        return sorted(
            f"{name} is declared in {sorted(where)}"
            for name, where in found.items()
            if where != [ONE_DECLARATION_EACH[name]]
        )

    assert second_declarations({name: [home] for name, home in ONE_DECLARATION_EACH.items()}) == []
    assert second_declarations(
        {"REDACTED": ["shepherd.toolsurface.types", "shepherd.toolsurface.audit"]}
    ) == [
        "REDACTED is declared in "
        "['shepherd.toolsurface.audit', 'shepherd.toolsurface.types']"
    ]
    # …and a declaration that moved house is caught as readily as one that was
    # copied: the home is part of the property, not a comment beside it.
    assert second_declarations({"actor_kind_of": ["shepherd.toolsurface.audit"]}) == [
        "actor_kind_of is declared in ['shepherd.toolsurface.audit']"
    ]

    # B1, on the discovery the whole section rests on.
    assert isinstance(next(iter(modules_defining("SECRET_KEY_MARKERS")), None), Module)
