"""BLOCKER-T19-c, made mechanical: `src/` contains **no caller** of the parser.

`web/ws.py` is a complete, unit-tested RFC 6455 framer. Half of it is a *reader*
— `parse_frame`, `Frame`, `WebSocketClosed`, `close_code` — and this build never
reads a byte from an upgraded socket: `web/server.py::_terminal` writes the 101,
the snapshot frame, the live chunks and a close frame, and then hangs up. There
is no browser→pane keystroke path in M3 **by decision** (BLOCKER-T19-c: adding
one would mean a POST route outside T18's closed set, which clause 11's
route-closure test asserts as closed).

So the reader's fourteen tests in `tests/web/test_ws.py` assert a contract with
no implementer — `test_a_partial_frame_asks_for_more_bytes_instead_of_guessing`
says the caller "reads more and asks again", and there is no caller. That is
T19's dead `session.js` one layer down: a test whose seam is a function,
asserting quality for code nothing runs. The parser is real and correct and is
exactly what a future read loop will use, so **nothing here deletes anything**.

What this rule does is stop the vacuity being **inherited silently**. It is the
absence written down where it fails loudly: the day someone wires a read loop,
this test goes red, and the red says that the read loop must bring its own
tests rather than inherit the parser's.

Seam: the source text of `src/`, by AST with origin resolution — the seam every
rule in this package uses, because "nothing calls this" is a property of the
tree and not of a running process.

**Arrival before absence.** Three separate ways this rule could pass while
measuring nothing, each asserted against:

* the parser might not be there at all — `modules_defining` finds it by
  **property, not filename** (B2), so the module may be renamed and the rule
  still follows it;
* the scan might resolve no `ws` name whatsoever (a renamed module, a broken
  walker, an unread file) — so the **reached** half of the same module
  (`handshake_response`, `build_frame`, `close_frame`) is asserted to have real
  callers in `src/` by this very scan;
* the scan might never open a file — `MISSING_MODULE` must raise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    MISSING_MODULE,
    Module,
    fixture,
    iter_modules,
    modules_defining,
    resolved_identifiers,
)

#: The read half. `parse_frame` is the entry point and the one T19-c is about;
#: the other three are its vocabulary and cannot be used without it, so a name
#: from this tuple appearing anywhere in `src/` means the read path has arrived.
READ_PATH_NAMES: tuple[str, ...] = ("parse_frame", "Frame", "WebSocketClosed", "close_code")
PARSER_NAME = "parse_frame"

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


def test_the_ws_parser_has_no_caller_anywhere_in_src() -> None:
    """T19-c: nothing in the product reads a client frame, and that is the plan.

    If this is red for you: you have wired the read loop. Do not delete this
    test and do not point it at the new code — `tests/web/test_ws.py`'s parser
    tests are **unit** tests of a framer and prove nothing about a loop that
    reads a socket, decides on a `(None, 0)`, and fails a connection. Write the
    read loop's own tests, then retire this rule with them in the tree.
    """
    # Arrival 1: the parser exists and this rule is pointed at it. The module
    # is *found* by property, so a rename cannot switch the rule off — but it is
    # also named here, so a rename is reported rather than absorbed. If you
    # renamed `ws.py`, the fix is this line and the fixture's imports.
    assert modules_defining(PARSER_NAME) != []
    assert parser_module().endswith(".ws"), f"{PARSER_NAME} moved to {parser_module()}"

    # Arrival 2: the scan really does resolve names from this module — the
    # write half has callers, found by the same walk that reports the read half.
    reached = scan(REACHED_NAMES)
    assert reached != [], "the scan resolved no ws name at all: it is measuring nothing"
    assert any("shepherd.web uses" in message for message in reached), reached

    # …and only then, the absence.
    assert scan(READ_PATH_NAMES) == []

    # Arrival 3: a scan that cannot raise on a missing path never opened one (B1).
    with pytest.raises(FileNotFoundError):
        ws_name_users(MISSING_MODULE, "shepherd.web", READ_PATH_NAMES)


def test_the_rule_fires_on_a_module_that_does_read_the_socket() -> None:
    """The self-check: a read loop is detected, in every spelling it has.

    Without this the rule above is an assertion that an empty list is empty.
    The fixture is `web/server.py::_terminal` as it would look the day the
    browser→pane path is built, and it is never shipped.
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
    """The measurement BLOCKER-T19-c records, kept live rather than quoted.

    `tests/web/test_ws.py` marks each of its parser tests with
    `parser_has_no_caller_in_src`, and that decorator's registry is asserted
    there against an independent AST derivation. What is asserted here is the
    half that makes the count *mean* something: the callers are zero.
    """
    assert scan(READ_PATH_NAMES) == []

    definitions: list[Module] = modules_defining(PARSER_NAME)
    assert [module.package for module in definitions] == ["shepherd.web"]
