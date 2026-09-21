#!/usr/bin/env python
"""Parse every named ES module and report the ones that do not parse.

Why this exists as a *tool* and not as a test. The page ships plain ES modules
with no build step (D51), so nothing between the author and the browser ever
looks at the syntax — the first reader is chromium, at render time, and its
report is a console error in a headless run. This parses them up front.

**It is an acceptance command, not a gate.** Its parser is a third-party package
that this project does not declare in `pyproject.toml`, and a suite that
imported it would make a green run depend on a package nobody installed. So no
file under `tests/` imports this module, or names its parser; the one test that
exercises it runs it as a subprocess and reads the exit code (A6).

    /root/Shepherd/.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js

Exit 0 when every file parsed, 1 when any did not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import esprima  # type: ignore[import-untyped]  # no stubs; tools/ is not gated


def main(paths: list[str]) -> int:
    """Parse each path as an ES module. Returns 0 when all of them parsed."""
    failures = 0
    for raw in paths:
        path = Path(raw)
        try:
            source = path.read_text()
        except OSError as exc:
            print(f"FAIL {path}: {exc}")
            failures += 1
            continue
        try:
            esprima.parseModule(source)
        except Exception as exc:  # esprima raises its own Error type
            # The message carries the line, which is the only part a reader
            # acts on; the exception class is noise here.
            print(f"FAIL {path}: {exc}")
            failures += 1

    print(f"{len(paths)} file(s) · {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
