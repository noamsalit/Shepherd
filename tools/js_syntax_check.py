#!/usr/bin/env python
"""Parse every named ES module in chromium and report the ones that do not parse.

Why this exists as a *tool* and not as a test. The page ships plain ES modules
with no build step (D51), so nothing between the author and the browser ever
looks at the syntax — the first reader is chromium, at render time, and its
report is a console error in a headless run. This parses them up front.

**It parses with the engine the code actually runs in.** The first version of
this tool used `esprima`, which is an **ES2017** parser: it reports FAIL on
optional chaining, `??`, `||=`, class fields, private fields, optional catch
binding, numeric separators and `import.meta` — all of which every shipping
browser has accepted for years. A gate that fails browser-correct code has two
outcomes and both are worse than no gate: the JS gets written down to ES2017 to
appease a parser nobody chose, or the check quietly stops being run while the
tasks that require it claim a gate they did not pass. **The ceiling of this gate
is now whatever chromium supports, which is the only ceiling that matters.**
That also retires A6: the undeclared third-party parser is gone, so no rule is
needed to keep `tests/` from importing it.

**What is lost, said plainly:** chromium does not expose a line number for a
module compile error — neither `e.stack` nor the console carries one when the
failing `import()` is caught. The report names the file and the message
(`Unexpected token ';'`), where `esprima` also named the line. That is the price
of parsing the real language instead of a proxy for it.

**A syntax error and a missing file are different defects.** A file that cannot
be read is reported by name before chromium is ever started, and a module that
parses and then *throws* on a blank page — which every page module does, since
they all wire the DOM at import time — is not a parse failure and is not
reported. Only `SyntaxError` counts.

    /root/Shepherd/.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js

Exit 0 when every file parsed, 1 when any did not — and 1 when there was
nothing to parse, because a gate that passed by not running is not a gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Route, sync_playwright

#: A hostname chromium never resolves, because every request to it is fulfilled
#: from disk by the route below. Files are addressed by their absolute path so
#: relative imports between them resolve exactly as they would when served.
ORIGIN = "http://js-syntax-check.localhost/"
BLANK = ORIGIN + "__blank__"

#: Import it, and report the failure only when it is a *syntax* error. An
#: evaluation error (a DOM lookup on a blank page, a missing dependency) is a
#: different thing and this tool does not claim to find it.
PROBE = """async (url) => {
  try { await import(url); return null; }
  catch (e) { return (e && e.name === 'SyntaxError') ? String(e.message || e) : null; }
}"""


def _serve_from_disk(route: Route) -> None:
    path = route.request.url[len(ORIGIN) :].split("?")[0]
    if route.request.url == BLANK:
        route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>js</title>")
        return
    try:
        body = Path("/" + path.lstrip("/")).read_text()
    except OSError:
        route.fulfill(status=404, content_type="text/plain", body="not found")
        return
    route.fulfill(status=200, content_type="text/javascript", body=body)


def parse_failures(paths: list[Path]) -> list[tuple[Path, str]]:
    """`(path, message)` for each file chromium could not parse as a module."""
    found: list[tuple[Path, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route(ORIGIN + "**", _serve_from_disk)
        page.goto(BLANK)
        for path in paths:
            message = page.evaluate(PROBE, ORIGIN + str(path).lstrip("/"))
            if message is not None:
                found.append((path, message))
        browser.close()
    return found


def main(paths: list[str]) -> int:
    """Parse each path as an ES module. Returns 0 when all of them parsed."""
    if not paths:
        # Written as a shell glob wherever this is an acceptance command, and
        # bash's non-matching-glob passthrough is the *shell's* mitigation: it
        # evaporates under `nullglob`, under zsh, under `find | xargs`, and
        # under any Python or Make caller. `0 file(s) · 0 failure(s)` and exit
        # 0 is a gate reporting success for having checked nothing.
        print("no files given")
        return 1

    failures = 0
    readable: list[Path] = []
    for raw in paths:
        path = Path(raw)
        try:
            path.read_text()
        except OSError as exc:
            print(f"FAIL {path}: {exc}")
            failures += 1
            continue
        readable.append(path.resolve())

    if readable:
        for path, message in parse_failures(readable):
            print(f"FAIL {path}: {message}")
            failures += 1

    print(f"{len(paths)} file(s) · {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
