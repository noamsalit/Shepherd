"""Every `fetch` in the shipped modules is inside a `try` (QA defect 2).

**The defect this file exists for.** Stop `controld`, open the page, type a
project name and press Create: the dialog stays open, the refusal line stays
hidden and empty, and nothing anywhere says why. The only trace is an unhandled
`pageerror: Failed to fetch` on a console nobody has open.

The cause is one line of shape, repeated. Every module's transport is

    const body = await response.json();     // runs only if the fetch resolved

so a **rejected** `fetch` — a refused socket, a stopped daemon, a dropped
network — walks past every refusal path the module has. `projects.js` even
ships an element built for exactly this case (`#p-refusal`) and never reached
it.

**It is systemic, which is why the gate is systemic.** QA enumerated the set:
`session.js` and `terminal.js` caught the rejection; `app.js`, `projects.js`,
`settings.js` and `chat.js` did not. The pattern had been written twice and
missed four times, so a fix at the four sites would be a fix that the seventh
module reintroduces. This is a scan of the bytes the server actually serves,
in the style `test_frontend_escaping.py` established for §13: a hard gate over
a **closed set** of file names, with a fixture that must trip it.

**What it can and cannot see.** It is a brace walk, not a parser: it knows
whether a `fetch(` is lexically inside a `try { … }` block in the same file,
and it does not know whether the `catch` does anything useful. That half is
proved by behaviour — `test_projects_page.py::test_a_create_that_never_reaches_
the_server_says_so` and `test_shell_live.py::test_the_shell_says_when_a_read_
never_reaches_the_server` drive an aborted route in a real browser and read the
sentence off the page. A scan alone would certify a silent `catch {}`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: The same closed set `test_frontend_escaping.py` keeps, minus the modules
#: that call no `fetch` at all — and the equality below is what keeps it
#: closed, because a scan over a list somebody has to remember to extend
#: certifies the files somebody remembered.
EXPECTED_CALLERS = (
    "app.js",
    "chat.js",
    "projects.js",
    "session.js",
    "settings.js",
    "terminal.js",
)


def strip_noise(source: str) -> str:
    """The source with comments and literals blanked, length preserved.

    Blanked rather than removed so every reported offset is still the offset in
    the real file. A `fetch(` inside a string or a comment is not a call, and a
    brace inside one is not a block — both were in this tree on the day this
    was written.
    """
    out = list(source)
    index = 0
    end = len(source)
    while index < end:
        char = source[index]
        two = source[index : index + 2]
        if two == "//":
            while index < end and source[index] != "\n":
                out[index] = " "
                index += 1
            continue
        if two == "/*":
            while index < end and source[index - 1 : index + 1] != "*/":
                out[index] = " "
                index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            while index < end:
                if source[index] == "\\":
                    out[index] = out[index + 1] = " "
                    index += 2
                    continue
                if source[index] == quote:
                    break
                out[index] = " "
                index += 1
            index += 1
            continue
        index += 1
    return "".join(out)


def unguarded_fetches(source: str) -> list[int]:
    """The 1-based line of every `fetch(` not lexically inside a `try` block.

    A stack of open blocks, each remembering whether the `{` that opened it was
    preceded by the word `try`. A `fetch(` is guarded if any block on the stack
    is a `try` — `any`, not `top`, because the call is normally a statement or
    two down inside one.
    """
    text = strip_noise(source)
    stack: list[bool] = []
    offenders: list[int] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "{":
            stack.append(text[:index].rstrip().endswith("try"))
            index += 1
            continue
        if char == "}":
            if stack:
                stack.pop()
            index += 1
            continue
        if text.startswith("fetch(", index) and not (
            index > 0 and (text[index - 1].isalnum() or text[index - 1] in "._$")
        ):
            if not any(stack):
                offenders.append(text[:index].count("\n") + 1)
            index += 6
            continue
        index += 1
    return offenders


def js_files() -> dict[str, Path]:
    return {path.name: path for path in sorted(STATIC_ROOT.glob("*.js"))}


def test_the_caller_set_is_exactly_the_modules_that_call_fetch() -> None:
    """The closed set, checked against the directory rather than trusted.

    A new page module that talks to the API is a new place this defect can
    live, and a list that nobody extended would report it as clean by never
    looking at it.
    """
    calling = {
        name
        for name, path in js_files().items()
        if "fetch(" in strip_noise(path.read_text(encoding="utf-8"))
    }
    assert calling == set(EXPECTED_CALLERS), calling.symmetric_difference(
        EXPECTED_CALLERS
    )


@pytest.mark.parametrize("name", EXPECTED_CALLERS)
def test_every_fetch_is_inside_a_try(name: str) -> None:
    """The gate itself, one module at a time so a failure names the file."""
    source = js_files()[name].read_text(encoding="utf-8")
    assert unguarded_fetches(source) == [], (
        f"{name}: a fetch that rejects walks past every refusal path this "
        f"module has, at line(s) {unguarded_fetches(source)}"
    )


def test_the_gate_catches_an_unguarded_fetch() -> None:
    """The gate is seen to fail, on a fixture nothing imports.

    `fixtures/unreachable_fetch.js` is read as text and never loaded: it holds
    one guarded call and one that is not, plus the three shapes the scanner has
    to be blind to — `fetch(` inside a string, inside a comment, and a brace
    inside a string that would otherwise unbalance the stack.
    """
    fixture = (FIXTURES / "unreachable_fetch.js").read_text(encoding="utf-8")
    found = unguarded_fetches(fixture)

    lines = fixture.splitlines()
    assert [lines[line - 1].strip() for line in found] == [
        "const response = await fetch(path);"
    ], found
