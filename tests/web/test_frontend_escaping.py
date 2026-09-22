"""§13's escaping rule, enforced on the shipped JS rather than promised (T16).

There is no node on this host (D51, K8), so the gate is a scan of the files the
server actually serves. It is a hard gate rather than a judgement call because
the chosen style is static markup filled with `textContent`: the expected number
of allowed exceptions is **zero**, and every scan below carries a self-check
against a fixture that must trip it.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# T19 appends `session.js` and `terminal.js` (§12 page 3). The list is a
# closed set on purpose — a scan over a directory it never enumerated is a
# test that passes by finding nothing — so it is widened by name here rather
# than loosened into a glob. `static/vendor/` is out of scope by construction:
# `js_files()` is a single-level glob, and the vendored emulator is upstream
# code this rule has no authority over.
# T24 appends `chat.js` (§12 page 1), by name and for the same reason T19
# appended the other two: a scan over a directory it never enumerated is a test
# that passes by finding nothing, so this list is widened deliberately rather
# than loosened into a glob. The chat page is the one that most needs it — it
# interpolates the master's own output, which carries tool results.
# **T6.1 replaces `fleet.js` with `flock.js`** — a rename, so the list loses an
# entry and gains one rather than growing. The rename is T6.1's by plan, and it
# is what makes T6.4's manifest arithmetic come out: one path removed, one path
# added. `app.js`'s `import { render } from "./fleet.js"` is the shell's line
# and is rewired by the integration pass; on this branch the import names a file
# that is gone, which `test_session_wiring.py::test_every_shipped_module_is_
# reachable_from_the_page` reports and this task declares rather than hides.
EXPECTED_MODULES = (
    "app.js",
    "chat.js",
    "escape.js",
    "flock.js",
    "rail.js",
    "session.js",
    "sse.js",
    "terminal.js",
)

#: An assignment to an HTML sink, with whatever it was handed.
_HTML_ASSIGNMENT = re.compile(r"\.(innerHTML|outerHTML)\s*=\s*([^;\n]+)")
_INSERT_ADJACENT = re.compile(r"\.insertAdjacentHTML\s*\(([^;\n]*)")

#: A right-hand side that is safe by §13: one quoted literal, no substitution,
#: no concatenation. A template literal with `${}` is not one; neither is `a + b`.
_SINGLE_LITERAL = re.compile(r"""^\s*(?:'[^'\\]*'|"[^"\\]*"|`[^`$\\]*`)\s*$""")

_ESCAPE_CALL = re.compile(r"escapeHtml\s*\(")

#: The characters `escapeHtml` must neutralise — "just a number" is not an excuse.
MUST_ESCAPE = ("&", "<", ">", '"', "'")


def js_files() -> list[Path]:
    return sorted(STATIC_ROOT.glob("*.js"))


def unsafe_sinks(source: str) -> list[str]:
    """Every interpolation into an HTML sink that §13 does not allow.

    A sink is allowed only when its right-hand side is a single string literal
    with no substitution, **or** when every value in it goes through
    `escapeHtml(...)`. Anything else — a bare variable, a `+`, a `${}` — is a
    finding, which is what makes "prefer `textContent`" checkable.
    """
    findings: list[str] = []
    for sink, right_hand_side in _HTML_ASSIGNMENT.findall(source):
        if _SINGLE_LITERAL.match(right_hand_side):
            continue
        if _ESCAPE_CALL.search(right_hand_side):
            continue
        findings.append(f"{sink} = {right_hand_side.strip()}")
    for arguments in _INSERT_ADJACENT.findall(source):
        if _ESCAPE_CALL.search(arguments):
            continue
        if all(_SINGLE_LITERAL.match(part) for part in arguments.split(",")[1:] if part.strip()):
            continue
        findings.append(f"insertAdjacentHTML({arguments.strip()}")
    return findings


def test_the_shipped_modules_are_all_there() -> None:
    """A scan over an empty directory is a test that passes by finding nothing."""
    assert [path.name for path in js_files()] == list(EXPECTED_MODULES)


def test_no_unescaped_interpolation_in_frontend() -> None:
    """§13: zero exceptions, because the page fills slots with `textContent`."""
    findings = [
        f"{path.name}: {finding}" for path in js_files()
        for finding in unsafe_sinks(path.read_text(encoding="utf-8"))
    ]
    assert findings == []


def test_the_escaping_scan_bites() -> None:
    """The gate is only a gate if the violating shapes trip it (B1)."""
    violating = (FIXTURES / "unsafe_sinks.js").read_text(encoding="utf-8")
    findings = unsafe_sinks(violating)
    assert len(findings) == 4
    assert any("${" in finding for finding in findings)
    assert any("+" in finding for finding in findings)
    assert any("insertAdjacentHTML" in finding for finding in findings)

    allowed = (FIXTURES / "safe_sinks.js").read_text(encoding="utf-8")
    assert unsafe_sinks(allowed) == []


def test_escape_html_exists_and_is_used_where_required() -> None:
    """`escapeHtml` is exported and neutralises all five characters.

    The page has no HTML sink to wrap today, so the second half of §13's rule is
    proved on the function itself: a helper that misses `'` is the reason the
    rule says "no exceptions".
    """
    source = (STATIC_ROOT / "escape.js").read_text(encoding="utf-8")
    assert "export function escapeHtml" in source
    for character in MUST_ESCAPE:
        assert f"'{character}'" in source or f'"{character}"' in source, character
    assert "&amp;" in source and "&lt;" in source and "&gt;" in source
    assert "&quot;" in source and "&#39;" in source


def test_no_other_html_injection_paths() -> None:
    """`document.write` and `eval` route around every scan above."""
    for path in js_files():
        source = path.read_text(encoding="utf-8")
        assert "document.write" not in source
        assert "eval(" not in source
        assert "new Function" not in source
