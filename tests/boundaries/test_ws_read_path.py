"""The WebSocket read path has exactly one caller, and it is the input pump.

**History (BLOCKER-T19-c, reversed by D76).** Until P12 `src/` contained **no**
caller of the parser: `web/server.py::_terminal` wrote the 101, the snapshot,
the live chunks and a close frame and never read a byte back, because the
browser→pane keystroke path was out of scope by decision. This module asserted
that absence, so that the day a read loop arrived it would have to bring its own
tests rather than inherit `tests/web/test_ws.py`'s unit tests of the framer.

It arrived in P12 (owner ruling 18, SD-05; D76; ADR-QR-4), with its own tests —
`tests/web/test_ws_input_pump.py` at the loop's seam and
`tests/web/test_terminal_input_server.py` on the wire — and the rule became
the stronger positive one: `ws.parse_frame` is called by **one** function in
the product, `ws.pump_input`; `ws.pump_input` is called by **one** method,
`FleetHandler._read_keys`; and `_read_keys` is started by **one** method,
`FleetHandler._terminal`, after the origin check, the handshake and the audited
open. A second read loop anywhere in `src/` is red here.

Seam: the source text of `src/`, by AST with origin resolution — the seam every
rule in this package uses, because "nothing else calls this" is a property of
the tree and not of a running process.

**Arrival before absence.** Three separate ways this rule could pass while
measuring nothing, each asserted against:

* the parser might not be there at all — `modules_defining` finds it by
  **property, not filename** (B2), so the module may be renamed and the rule
  still follows it;
* the scan might resolve no `ws` name whatsoever (a renamed module, a broken
  walker, an unread file) — so the write half of the same module
  (`handshake_response`, `build_frame`, `close_frame`) is asserted to have real
  callers in `src/` by this very scan;
* the scan might never open a file — `MISSING_MODULE` must raise.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import (
    MISSING_MODULE,
    REPO_ROOT,
    Module,
    fixture,
    iter_modules,
    modules_defining,
    resolved_identifiers,
)

#: The read half. `parse_frame` is the entry point; the other three are its
#: vocabulary. Outside the framer's own module, only `pump_input` may be used —
#: so a name from this tuple appearing anywhere else in `src/` is a second
#: read loop.
READ_PATH_NAMES: tuple[str, ...] = ("parse_frame", "Frame", "WebSocketClosed", "close_code")
PARSER_NAME = "parse_frame"
PUMP_NAME = "pump_input"

#: Where the one read loop is allowed to live, and who may start it (ADR-QR-4).
PUMP_CALLER = "FleetHandler._read_keys"
READER_STARTER = "FleetHandler._terminal"

#: The write half, which the product really does call. Not a rule — the arrival
#: assertion that keeps the rule above from being a scan of nothing.
REACHED_NAMES: tuple[str, ...] = ("handshake_response", "build_frame", "close_frame")


def parser_module() -> str:
    """The dotted module that defines the parser, found by property (B2).

    Never a hard-coded `shepherd.web.ws`: a rule that can be switched off with
    `git mv` is not a rule, and this package has shipped two of those.
    """
    defining = modules_defining(PARSER_NAME)
    assert len(defining) == 1, f"expected exactly one definition of {PARSER_NAME}: {defining}"
    return f"{defining[0].package}.{defining[0].path.stem}"


def ws_name_users(path: Path, package: str, names: tuple[str, ...]) -> list[str]:
    """Every listed `ws` name this module resolves to — origin-resolved (r6).

    Reads the file before anything else (B1). `from shepherd.web import ws` then
    `ws.parse_frame(...)`, `from shepherd.web.ws import parse_frame`, and
    `import shepherd.web.ws` then the full dotted chain all resolve to the same
    origin, so no spelling walks past this.
    """
    module = parser_module()
    used = resolved_identifiers(path)
    return [f"{package} uses {module}.{name}" for name in names if f"{module}.{name}" in used]


def scan(names: tuple[str, ...]) -> list[str]:
    return [
        message
        for found in iter_modules()
        for message in ws_name_users(found.path, found.package, names)
    ]


def callers_in(path: Path, callee: str) -> set[str]:
    """`Class.method` / `function` names in `path` whose body names `callee`.

    Names, not just calls: `threading.Thread(target=self._read_keys)` starts a
    function without calling it, and a rule that saw only calls would miss the
    thread that runs the loop. Qualified by the enclosing class, so two methods
    of the same name in two classes are two answers.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                named = {
                    sub.attr if isinstance(sub, ast.Attribute) else sub.id
                    for sub in ast.walk(child)
                    if isinstance(sub, (ast.Attribute, ast.Name))
                }
                if callee in named:
                    found.add(child.name if owner is None else f"{owner}.{child.name}")

    visit(tree, None)
    return found


def test_the_ws_parser_has_exactly_one_caller_the_input_pump() -> None:
    """D76 / ADR-QR-4: one read loop, reached one way.

    Successor of `test_the_ws_parser_has_no_caller_anywhere_in_src` (T19-c),
    retired in P12 when the loop it guarded against was built with its own
    tests. If this is red for you: a second place reads a client frame. Route it
    through `ws.pump_input`, or retire this rule with a decision that says why.
    """
    # Arrival 1: the parser exists and this rule is pointed at it.
    defining = modules_defining(PARSER_NAME)
    assert defining != []
    assert parser_module().endswith(".ws"), f"{PARSER_NAME} moved to {parser_module()}"
    ws_path = defining[0].path

    # Arrival 2: the scan really does resolve names from this module.
    reached = scan(REACHED_NAMES)
    assert reached != [], "the scan resolved no ws name at all: it is measuring nothing"
    assert any("shepherd.web uses" in message for message in reached), reached

    # The read half is used by no module but its own.
    assert scan(READ_PATH_NAMES) == []
    # Inside it, `parse_frame` has exactly one caller: the pump.
    assert callers_in(ws_path, PARSER_NAME) == {PUMP_NAME}

    # The pump is used by exactly one module, and in it by exactly one method,
    # which exactly one method starts.
    pump_users = scan((PUMP_NAME,))
    assert pump_users == [f"shepherd.web uses {parser_module()}.{PUMP_NAME}"], pump_users
    users = [found.path for found in iter_modules() if ws_name_users(found.path, found.package, (PUMP_NAME,))]
    assert [path.name for path in users] == ["server.py"], users
    server = users[0]
    assert callers_in(server, PUMP_NAME) == {PUMP_CALLER}
    assert callers_in(server, PUMP_CALLER.split(".")[1]) == {READER_STARTER}

    # Arrival 3: a scan that cannot raise on a missing path never opened one (B1).
    with pytest.raises(FileNotFoundError):
        ws_name_users(MISSING_MODULE, "shepherd.web", READ_PATH_NAMES)


def test_the_rule_fires_on_a_module_that_does_read_the_socket() -> None:
    """The self-check: a read loop is detected, in every spelling it has.

    Without this the rule above is an assertion that an empty list is empty.
    The fixture is a read loop written *outside* `ws.pump_input` — a second
    reader, the thing the rule above forbids — and it is never shipped.
    """
    leak = fixture("web_reads_the_upgraded_socket.py")

    fired = ws_name_users(leak, "shepherd.web", READ_PATH_NAMES)
    # All four, and the fixture writes each one in a different import spelling —
    # dotted, bare, fully qualified and aliased — so no spelling walks past.
    assert sorted(fired) == sorted(
        f"shepherd.web uses {parser_module()}.{name}" for name in READ_PATH_NAMES
    ), fired

    # The fixture is a fixture, not a shipped module: `iter_modules` scans
    # `src/` only, so the rule above is not green merely because this file is
    # outside its reach by accident.
    assert leak not in [found.path for found in iter_modules()]


def test_the_parser_tests_outnumber_the_parsers_callers() -> None:
    """The measurement T19-c recorded, kept live after D76 gave it a caller.

    `tests/web/test_ws.py` exercises `parse_frame` and its vocabulary directly;
    since P12 the product calls it from exactly one place. The count of unit
    tests of the framer still exceeds the count of its callers, and the one
    caller — the pump — has a test module of its own.
    """
    ws_tests = REPO_ROOT / "tests" / "web" / "test_ws.py"
    pump_tests = REPO_ROOT / "tests" / "web" / "test_ws_input_pump.py"
    parser_tests = {
        node.name
        for node in ast.parse(ws_tests.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(
            (isinstance(sub, ast.Attribute) and sub.attr in READ_PATH_NAMES)
            for sub in ast.walk(node)
        )
    }
    definitions: list[Module] = modules_defining(PARSER_NAME)
    assert [module.package for module in definitions] == ["shepherd.web"]
    callers = callers_in(definitions[0].path, PARSER_NAME)
    assert callers == {PUMP_NAME}
    assert len(parser_tests) > len(callers), sorted(parser_tests)
    assert "def test_" in pump_tests.read_text(encoding="utf-8")
