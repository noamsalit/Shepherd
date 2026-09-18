"""The two import properties phase 1 of M4 depends on, plus the layer map's own check.

**DP3 (P-M4-6) — D25's single exception, implemented rather than approximated.**
D25 reads: *"Nothing the UI renders may read a log — the audit view is the
single exception, because it is a literal tail."* The shipped rule
(`test_no_consumer_and_no_tool_surface_reads_a_log`) forbade `toolsurface/`,
`web/`, `cli/` and `master/` from importing `shepherd.logs` **at all**, which is
stricter than the decision it implements, and M4 is the milestone that discovers
it: `invoke()` must write the audit log and `get_audit_log(limit=50)` must tail
it, both at L4.

**Two alternatives are rejected out loud here, where the temptation is.**
(1) Adding `shepherd.toolsurface.audit` to an exemption list — K11: an exemption
is how boundaries die, and the next one is always easier than the first.
(2) Moving the audit writer and reader down to `orchestration/` (L3), which
`toolsurface/` may import freely — the rule's *letter* survives and its
*purpose* is defeated. That is laundering, and it is the defect class this
milestone exists to refuse.

**Exactly one function was widened, and it is named so a later builder does not
loosen two.** `_imports.logs_importer_violations` is the single implementation;
`test_consumer_boundary.log_reader_violations` **is** that object (asserted
below, by identity), and the `consumer_violations` /`FORBIDDEN_BELOW_L4` path was
deliberately **not** touched — it never bound `toolsurface/` in the first place
(its `is_consumer` guard excludes L4), and the packages it does bind — `web/`,
`cli/`, `master/` — stay at zero importers forever.

**DP4 (P-M4-7) — no vendor SDK below L5.** `cli/` imports `toolsurface.registry`,
so a vendor import at L4 makes `shepherd status` pay to load a package that
ships a 216,677,784-byte Claude Code binary. `master/` is the SDK's only home
(D19), so it is the only package outside the scan.

Every import rule in this module resolves **aliases, from-imports and the two
call-shaped spellings** (`importlib.import_module`, `__import__`). A rule keyed
on one exact AST spelling passes on the idiomatic spelling of the same
violation, and `importlib.import_module("claude_agent_sdk")` is not an import
node at all — it is a call. Each form ships its own fixture.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import _imports as boundary
from _parse import parsed


# ----- DP3: exactly one `toolsurface` module imports `shepherd.logs` ----------


def test_the_audit_reader_is_the_single_logs_importer_in_l4() -> None:
    modules = list(boundary.iter_modules())
    # Arrival before absence. Everything below is an emptiness assertion, and an
    # emptiness over a corpus of nothing is the defect this repo keeps shipping.
    assert modules, "the product scan found no modules at all"
    scanned = {module.package for module in modules}
    assert boundary.TOOLSURFACE_PACKAGE in scanned, scanned
    # …and the detector demonstrably sees a real `shepherd.logs` import in this
    # tree, so `violations == []` is an emptiness it could have broken.
    real = [m for m in modules if any(
        boundary.in_package(i, boundary.LOG_PACKAGE) for i in boundary.all_imports(m.path)
    )]
    assert real, "no product module imports shepherd.logs — the detector proves nothing"

    permitted = boundary.audit_writer_paths()
    violations = [
        message
        for module in modules
        for message in boundary.logs_importer_violations(
            module.path, module.package, permitted=permitted
        )
    ]
    assert violations == []
    assert boundary.single_logs_importer_violations(modules, permitted) == []

    with pytest.raises(FileNotFoundError):
        boundary.logs_importer_violations(
            boundary.MISSING_MODULE, "shepherd.toolsurface", permitted=frozenset()
        )

    # The widened rule has exactly one implementation, and this is the assertion
    # that keeps it that way.
    import test_consumer_boundary

    assert test_consumer_boundary.log_reader_violations is boundary.logs_importer_violations


def test_a_second_l4_logs_importer_is_a_violation() -> None:
    """The mutation DP3's widening must still catch, in both spellings."""
    expected = {
        "toolsurface_second_logs_importer.py": {
            "shepherd.toolsurface imports shepherd.logs.jsonl",
            "shepherd.toolsurface imports shepherd.logs.jsonl.RotatingJsonlLog",
        },
        "toolsurface_logs_via_import_module.py": {
            "shepherd.toolsurface imports shepherd.logs.jsonl",
        },
    }
    for name in expected:
        leak = boundary.fixture(name)
        assert boundary.logs_importer_violations(
            leak, "shepherd.toolsurface", permitted=frozenset()
        ) != [], name
        # …and the reported set, written out, so the rule cannot pass by naming
        # some other import it happened to see.
        assert set(
            boundary.logs_importer_violations(leak, "shepherd.toolsurface", permitted=frozenset())
        ) == expected[name], name
        # …and a consumer stays at zero even when it is the declared writer.
        assert boundary.logs_importer_violations(
            leak, "shepherd.web", permitted=frozenset({leak})
        ) != [], name
        # …and silenced only by the layer, never by an unread file (B1).
        assert boundary.logs_importer_violations(
            leak, "shepherd.signals", permitted=frozenset()
        ) == [], name
        # The single declared writer is the one thing that is allowed.
        assert boundary.logs_importer_violations(
            leak, "shepherd.toolsurface", permitted=frozenset({leak})
        ) == [], name


def test_the_single_importer_property_is_an_equality_not_a_licence() -> None:
    """Proved on a fixture corpus, because the live one is empty until T5.

    `audit_writer_paths()` returns nothing today — T5 has not shipped
    `toolsurface/audit.py` — so the live equality is `{} == {}`, which is exactly
    the vacuous green this module is about. The same function is therefore driven
    over a corpus built from fixtures, where both directions can fail.
    """
    writer = boundary.fixture("toolsurface_second_logs_importer.py")
    other = boundary.fixture("toolsurface_logs_via_import_module.py")
    clean = boundary.fixture("toolsurface_imports_the_vendor_sdk.py")

    def as_l4(path: Path) -> boundary.Module:
        return boundary.Module(path=path, package="shepherd.toolsurface")

    # One writer, one importer, and they are the same module: clean.
    assert boundary.single_logs_importer_violations(
        [as_l4(writer), as_l4(clean)], frozenset({writer})
    ) == []
    # A second importer: red.
    assert boundary.single_logs_importer_violations(
        [as_l4(writer), as_l4(other)], frozenset({writer})
    ) != []
    # A declared writer that imports no log — discovery found the wrong module: red.
    assert boundary.single_logs_importer_violations(
        [as_l4(clean)], frozenset({clean})
    ) != []
    # Two declared writers: "exactly one" is an equality, not a licence.
    assert boundary.single_logs_importer_violations(
        [as_l4(writer), as_l4(other)], frozenset({writer, other})
    ) != []
    # An importer with no declared writer at all: red.
    assert boundary.single_logs_importer_violations([as_l4(writer)], frozenset()) != []


# ----- DP4: no vendor SDK below L5 -------------------------------------------


def test_no_vendor_sdk_below_l5() -> None:
    modules = list(boundary.iter_modules())
    assert modules
    scanned = boundary.NO_VENDOR_SDK_PACKAGES
    # The plan names ten packages; the scan is derived from `LAYER_OF` at test
    # time and must cover every one of them. Enumerated, never counted (K19).
    assert {
        "shepherd.toolsurface",
        "shepherd.web",
        "shepherd.cli",
        "shepherd.core",
        "shepherd.store",
        "shepherd.signals",
        "shepherd.orchestration",
        "shepherd.runner",
        "shepherd.engines",
        "shepherd.host",
    } <= scanned, scanned
    assert "shepherd.master" not in scanned, "master/ is the SDK's declared home (D19)"
    # Arrival: the scan really does reach live modules in the scanned packages.
    reached = {m.package for m in modules if boundary.vendor_scanned(m.package)}
    assert {"shepherd.toolsurface", "shepherd.web", "shepherd.cli"} <= reached, reached

    violations = [
        message
        for module in modules
        for message in boundary.vendor_sdk_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        boundary.vendor_sdk_violations(boundary.MISSING_MODULE, "shepherd.toolsurface")


def test_a_vendor_import_below_l5_is_a_violation_in_every_spelling() -> None:
    plain = boundary.fixture("toolsurface_imports_the_vendor_sdk.py")
    dynamic = boundary.fixture("toolsurface_imports_the_vendor_sdk_dynamically.py")

    seen = boundary.all_imports(plain)
    assert "claude_agent_sdk" in seen, seen          # `import claude_agent_sdk as sdk`
    assert "claude_agent_sdk.tool" in seen, seen     # `from claude_agent_sdk import tool`
    # The submodule form never yields the bare root name, which is why the rule
    # matches on `name.split(".")[0]` and not on the whole dotted string.
    assert "mcp" not in seen and "mcp.server.stdio" in seen, seen
    assert {"claude_agent_sdk", "mcp"} <= boundary.all_imports(dynamic)

    # The reported set, written out. `!= []` is not enough: this fixture names
    # three vendor imports and one bare root among them, so a rule that matched
    # the whole dotted name and walked past `from mcp.server.stdio import …`
    # would still return a non-empty list and survive. (It did — mutation M12.)
    assert set(boundary.vendor_sdk_violations(plain, "shepherd.toolsurface")) == {
        "shepherd.toolsurface imports claude_agent_sdk",
        "shepherd.toolsurface imports claude_agent_sdk.tool",
        "shepherd.toolsurface imports mcp.server.stdio",
        "shepherd.toolsurface imports mcp.server.stdio.stdio_server",
    }
    assert set(boundary.vendor_sdk_violations(dynamic, "shepherd.cli")) == {
        "shepherd.cli imports claude_agent_sdk",
        "shepherd.cli imports mcp",
    }

    for leak in (plain, dynamic):
        assert boundary.vendor_sdk_violations(leak, "shepherd.toolsurface") != []
        assert boundary.vendor_sdk_violations(leak, "shepherd.cli") != []
        assert boundary.vendor_sdk_violations(leak, "shepherd.core") != []
        # …silenced only by the package, never by an unread file (B1).
        assert boundary.vendor_sdk_violations(leak, "shepherd.master") == []


# ----- the layer map names real packages --------------------------------------


def test_every_layer_entry_names_a_real_package() -> None:
    """Every built package has a layer, and every unbuilt layer entry is spec'd.

    The plan asked for one direction only — *every key in `LAYER_OF` resolves to
    a package that exists*. **That rule cannot be written green in this tree, and
    that is a plan defect, not a finding about the code:** step 0b row 4 requires
    `shepherd.master` to be in `LAYER_OF` *before* `master/` is built, precisely
    so D19's rule bites the moment it appears, and `shepherd.providers` is the
    same shape (§5.0's L2 row, unbuilt). Deleting either entry to make the rule
    green would switch off the rule the entry exists to arm. Recorded in
    `docs/plans/2026-09-17-m4-BLOCKERS.md`.

    So the rule ships in the two halves that are both true and both bite:
    every package **on disk** has a layer (an unlayered package escapes
    `direction_violations` and `consumer_violations` entirely), and every layer
    entry with **no** package on disk is one §5.0's own table declares — read out
    of the spec, never out of an exemption list.
    """
    built = boundary.built_packages()
    declared = boundary.spec_layer_packages()
    assert built, "no packages found under src/shepherd"
    assert {"shepherd.core", "shepherd.web", "shepherd.toolsurface"} <= built, built
    assert {"shepherd.providers", "shepherd.master"} <= declared, declared
    assert boundary.NOT_A_LAYER == frozenset({"shepherd.testkit"})
    assert boundary.NOT_A_LAYER <= built, "the one declared non-layer must exist"

    assert boundary.layer_map_violations(frozenset(boundary.LAYER_OF), built, declared) == []

    # …and both halves are proved to bite, on literals rather than on the tree.
    assert boundary.layer_map_violations(
        frozenset({"shepherd.core"}), frozenset({"shepherd.core", "shepherd.newthing"}), declared
    ) != []
    assert boundary.layer_map_violations(
        frozenset({"shepherd.core", "shepherd.invented"}), frozenset({"shepherd.core"}), declared
    ) != []
    assert boundary.layer_map_violations(
        frozenset({"shepherd.core", "shepherd.providers"}), frozenset({"shepherd.core"}), declared
    ) == []


# ----- the fixtures are inert --------------------------------------------------


def test_the_l4_fixtures_are_inert() -> None:
    """CLAUDE.md's mutation rule, asserted by **AST**.

    A planted violation is a fixture nothing imports. Inertness is asserted on
    the module body — no call at module level, so nothing would run even if the
    file were imported — and on the import set, which is bounded by the exact
    violation each fixture exists to be. It is **not** asserted by a text search
    for `import`: every one of these files says the word in its docstring while
    explaining why it is inert, and that prose is what a text search would find.
    """
    expected: dict[str, frozenset[str]] = {
        "toolsurface_second_logs_importer.py": frozenset(
            {"__future__", "__future__.annotations", "shepherd.logs.jsonl",
             "shepherd.logs.jsonl.RotatingJsonlLog"}
        ),
        "toolsurface_logs_via_import_module.py": frozenset(
            {"__future__", "__future__.annotations", "importlib", "shepherd.logs.jsonl"}
        ),
        "toolsurface_imports_the_vendor_sdk.py": frozenset(
            {"__future__", "__future__.annotations", "claude_agent_sdk", "claude_agent_sdk.tool",
             "mcp.server.stdio", "mcp.server.stdio.stdio_server"}
        ),
        "toolsurface_imports_the_vendor_sdk_dynamically.py": frozenset(
            {"__future__", "__future__.annotations", "importlib", "claude_agent_sdk", "mcp"}
        ),
    }
    for name, allowed in expected.items():
        path = boundary.fixture(name)
        tree = parsed(path)
        assert boundary.all_imports(path) == allowed, name
        top_level_calls = [
            node
            for statement in tree.body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert top_level_calls == [], f"{name} executes something at import time"
        assert "import" in path.read_text(encoding="utf-8")  # the prose the AST ignores
    assert not (boundary.FIXTURE_DIR / "__init__.py").exists()
