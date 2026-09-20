"""ADR-1: `daemons/` is the composition root — thin, and nothing imports it.

**Imports are resolved through `all_imports`, not `module_imports`** (QA-prep,
§T7-3). `from importlib import import_module` then a bare `import_module(...)`
leaves the callee as a plain `ast.Name`: the bare helper reported such a file as
importing `importlib` and nothing else, while `controld` was loaded. The walker
itself is unchanged — the bare users were swapped, not `module_imports` — and it
is still read below, in the assertion that keeps this rule's premise honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    DAEMONS_PACKAGE,
    MISSING_MODULE,
    MAX_DAEMON_LINES,
    MAX_SOURCE_LINES,
    all_imports,
    fixture,
    in_package,
    iter_modules,
    module_imports,
)


def daemon_import_violations(path: Path, package: str) -> list[str]:
    """Reads the file before consulting the package (B1).

    The root may wire itself together — but that exemption is applied to a
    *result*, not used to skip the open. Handed its own exempt package, the
    early-returning version passed for a nonexistent path.
    """
    found = [
        f"{package} imports {imported}"
        for imported in sorted(all_imports(path))
        if in_package(imported, DAEMONS_PACKAGE)
    ]
    return [] if in_package(package, DAEMONS_PACKAGE) else found


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def over_limit(path: Path, limit: int) -> bool:
    return line_count(path) > limit


def test_nothing_imports_daemons() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in daemon_import_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        daemon_import_violations(MISSING_MODULE, DAEMONS_PACKAGE)

    # self-check: the leak fires outside the root, which is what makes the clean
    # half below an exemption rather than an unread file (B1). The reported set is
    # written out rather than asserted non-empty: this rule was **widened** in the
    # QA-prep pass, and a widening is only safe if what it caught before is still
    # caught in the same words.
    leak = fixture("cli_imports_daemons.py")
    assert daemon_import_violations(leak, "shepherd.cli") == [
        "shepherd.cli imports shepherd.daemons",
        "shepherd.cli imports shepherd.daemons.controld",
    ]
    assert daemon_import_violations(leak, DAEMONS_PACKAGE) == []
    assert "shepherd.daemons.controld" in module_imports(leak)

    # …and the **call-shaped** spelling, which is the half the bare helper never
    # saw. Swap `all_imports` back to `module_imports` and this is the line that
    # goes red, while the statement-form assertion above stays green — which is
    # what makes the widening a widening and not a rewrite.
    dynamic = fixture("cli_imports_daemons_dynamically.py")
    assert daemon_import_violations(dynamic, "shepherd.cli") == [
        "shepherd.cli imports shepherd.daemons.controld"
    ]
    assert not [
        name for name in module_imports(dynamic) if name.startswith("shepherd.")
    ], sorted(module_imports(dynamic))
    assert daemon_import_violations(dynamic, DAEMONS_PACKAGE) == []


def test_no_source_file_exceeds_600_lines() -> None:
    too_long = [
        f"{module.path.name}: {line_count(module.path)} lines"
        for module in iter_modules()
        if over_limit(module.path, MAX_SOURCE_LINES)
    ]
    assert too_long == []

    # ADR-1's 150-line cap on the composition root, so logic cannot hide in wiring.
    fat_daemons = [
        f"{module.path.name}: {line_count(module.path)} lines"
        for module in iter_modules()
        if in_package(module.package, DAEMONS_PACKAGE)
        and over_limit(module.path, MAX_DAEMON_LINES)
    ]
    assert fat_daemons == []

    with pytest.raises(FileNotFoundError):
        line_count(MISSING_MODULE)

    # self-check: one fixture, both caps.
    oversized = fixture("oversized_module.py")
    assert line_count(oversized) == 601
    assert over_limit(oversized, MAX_SOURCE_LINES)
    assert over_limit(oversized, MAX_DAEMON_LINES)
