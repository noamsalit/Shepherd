"""T18-3: the composition root's **headroom**, and who owns registration.

ADR-1 caps a file in `daemons/` at 150 lines, and the cap is a proxy for "no
logic in a composition root". `controld.py` has been 150, 154 and 148 across
this plan's writing — a file sitting *on* its cap satisfies the number and not
the constraint: the next wiring change cannot be additive, and the pressure
lands on whatever is easiest to delete, which is the prose.

So this module asserts the constraint the cap stands for, twice:

* the root keeps a **named reserve** under the cap, sized for the wiring M2
  still owes it (the stop path's construction and M2's tools);
* the root **names no capability**: the list of what this build can do lives in
  `toolsurface/compose.py`, and a `register_…` import back in the daemon is the
  regression that would put it back.

Seam: the source text — the same seam `tests/boundaries/` measures the cap at,
because a line budget is a property of the file, not of a running process.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shepherd.daemons import controld

#: ADR-1's cap, restated here rather than imported: `tests/boundaries/_imports`
#: is on the boundary suite's own path only, and a number this test is *about*
#: should be visible in it.
MAX_DAEMON_LINES = 150

#: What the reserve is for, line by line, so it is a budget and not a mood:
#: the stop path's construction is 4 lines (`log_dir`, `diff_dir`, one
#: `StopLog`, the two arguments into `HookLane`), M2's two tools add their
#: directories to the `compose_tool_surface` call, and PEP 8 gets its blank
#: lines back. Ten lines, reserved before they are needed — that is the whole
#: difference between headroom and a file that happens to fit today.
RESERVED_FOR_M2 = 10

ROOT = Path(controld.__file__)


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def imported_names(path: Path) -> set[str]:
    """Every name bound by an import in `path`, by AST — never by importing it."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            found.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.asname or alias.name for alias in node.names)
    return found


def test_the_composition_root_keeps_headroom_under_adr1s_cap() -> None:
    """The root ends this task with room to spare, not on the line."""
    lines = line_count(ROOT)

    assert lines <= MAX_DAEMON_LINES - RESERVED_FOR_M2, (
        f"{ROOT.name} is {lines} lines and ADR-1 caps it at {MAX_DAEMON_LINES}:"
        f" {MAX_DAEMON_LINES - lines} lines of headroom, and M2 still owes it"
        f" {RESERVED_FOR_M2}. Move wiring into toolsurface/compose.py rather"
        " than deleting the prose that explains the order."
    )

    # …and the measurement is real, not a constant: a file that is not there
    # fails loudly rather than measuring 0 (the boundary suite's B1 lesson).
    with pytest.raises(FileNotFoundError):
        line_count(ROOT.with_name("this_composition_root_does_not_exist.py"))


def test_the_composition_root_registers_no_capability_itself() -> None:
    """`compose_tool_surface` owns the list of capabilities; the root owns order.

    The root may still *call* the composition — that is the order, and the order
    is the contract ADR-7 cares about — but it may not know a tool's name.
    """
    names = imported_names(ROOT)

    assert [name for name in sorted(names) if name.startswith("register")] == []
    assert [name for name in sorted(names) if "tools_" in name] == []
    assert "compose_tool_surface" in names


def test_the_line_budget_constants_are_unchanged() -> None:
    """T23: the budget is 150 with 10 reserved, and editing it is not a fix.

    `test_the_composition_root_keeps_headroom_under_adr1s_cap` is red the moment
    the root grows by one line — it is at 140 of 140 — and the cheapest way to
    make that green is to edit one of these two numbers. So they are pinned, and
    **both spellings are pinned**: this file's, which the headroom check reads,
    and `tests/boundaries/_imports.py`'s, which the ADR-1 cap in
    `tests/boundaries/test_composition_root.py` reads. Two constants that can
    drift apart are two budgets.

    The boundary suite's copy is read as **text**, by AST: `tests/boundaries` is
    on its own suite's `sys.path` only, and importing it from here would either
    fail or quietly add a path.
    """
    import ast

    assert MAX_DAEMON_LINES == 150
    assert RESERVED_FOR_M2 == 10

    imports_module = Path(__file__).resolve().parents[1] / "boundaries" / "_imports.py"
    source = imports_module.read_text(encoding="utf-8")
    boundary_values = {
        target.id: node.value.value
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    # Arrival: the file really was read and really does carry the name…
    assert "MAX_DAEMON_LINES" in boundary_values, sorted(boundary_values)
    assert boundary_values["MAX_DAEMON_LINES"] == MAX_DAEMON_LINES
    # …and a file that is not there fails loudly rather than reading as agreement.
    with pytest.raises(FileNotFoundError):
        imports_module.with_name("_no_such_imports.py").read_text(encoding="utf-8")


def test_every_console_script_resolves() -> None:
    """T25: the three processes `pyproject.toml` puts on `PATH` still import.

    A composition root's imports are the process's imports, and M4 gave this one
    a new one — `daemons/plane.py`, which reaches `shepherd.master` and through
    it the vendor SDK. An entry point that names a module which cannot be
    imported is a `shepherd-controld` that fails at the shell rather than in a
    test, and nothing else in this suite loads the three by the names the wheel
    actually installs.

    Read from `pyproject.toml` at test time — never a list written out here, so
    a fourth script is covered the moment it is declared — and each one is
    resolved the way an entry point is: import the module, then read the
    attribute off it.
    """
    import importlib
    import tomllib

    manifest = Path(controld.__file__).resolve().parents[3] / "pyproject.toml"
    scripts = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["scripts"]

    # Arrival: the file really was read and really does declare the daemon.
    assert "shepherd-controld" in scripts, sorted(scripts)

    unresolved = []
    for name, target in scripts.items():
        module_name, _, attribute = target.partition(":")
        try:
            module = importlib.import_module(module_name)
        except Exception as refused:  # noqa: BLE001 - the whole point of the check
            unresolved.append(f"{name} -> {target}: {refused!r}")
            continue
        if not callable(getattr(module, attribute, None)):
            unresolved.append(f"{name} -> {target}: no callable {attribute!r}")
    assert unresolved == []

    # …and a script pointing at nothing is reported rather than skipped, which
    # is what makes `unresolved == []` an emptiness this check could break.
    assert not hasattr(importlib.import_module("shepherd.daemons.controld"), "no_such_entry")
