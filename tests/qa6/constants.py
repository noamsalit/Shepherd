"""The one definition site for every width literal qa6 uses, parsed from app.css.

Copied from `tests/qa5/constants.py` (re-proved by
`fixtures/mutations/constants.json`, env-plan §4 step 1a) and cut down to what
qa6 needs: the stylesheet is read from the **installed** package, each
breakpoint is parsed out of the rule it governs (never "the first max-width in
the file"), and the qa6 viewport set (test-plan §2 row 32) is asserted to
straddle every parsed breakpoint, so a stylesheet that moved a breakpoint fails
loudly here instead of silently mis-classifying every width downstream.

Parsing happens in `load()`, not at import (the package is import-inert).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import shepherd.web

STATIC_DIR: Final[Path] = Path(shepherd.web.__file__).parent / "static"

#: Each breakpoint, anchored on the first selector of the block it opens.
_RULES: Final[dict[str, re.Pattern[str]]] = {
    "sheet": re.compile(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{\s*dialog\.sheet\b"),
    "panes2": re.compile(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{\s*\.panes2\b"),
    "shell": re.compile(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{\s*\.shell\b"),
    "herd": re.compile(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{\s*\.herd\b"),
}

#: qa6's viewports (test-plan §0/§1: 390×844, 600/601, 760/761, 900/901, 1280×900).
VIEWPORTS: Final[dict[str, tuple[int, int]]] = {
    "w390": (390, 844),
    "w600": (600, 900),
    "w601": (601, 900),
    "w760": (760, 1024),
    "w761": (761, 1024),
    "w900": (900, 1200),
    "w901": (901, 1200),
    "w1280": (1280, 900),
}
DESKTOP: Final[str] = "w1280"
PHONE: Final[str] = "w390"


@dataclass(frozen=True)
class Breakpoints:
    sheet: int
    panes2: int
    shell: int
    herd: int


def parse(css: str) -> Breakpoints:
    found: dict[str, int] = {}
    for name, pattern in _RULES.items():
        matches = pattern.findall(css)
        if len(matches) != 1:
            raise AssertionError(
                f"expected exactly one `@media (max-width: Npx) {{ {name} …` block; found {matches!r}"
            )
        found[name] = int(matches[0])
    return Breakpoints(sheet=found["sheet"], panes2=found["panes2"], shell=found["shell"], herd=found["herd"])


def check_viewports(points: Breakpoints) -> None:
    """Every breakpoint must be bracketed inclusively by a viewport pair."""
    widths = {width for width, _height in VIEWPORTS.values()}
    for name, value in (("sheet", points.sheet), ("panes2", points.panes2), ("shell", points.shell), ("herd", points.herd)):
        if value not in widths or value + 1 not in widths:
            raise AssertionError(f"breakpoint {name}={value}px is not bracketed by the qa6 viewports {sorted(widths)}")


def load() -> Breakpoints:
    points = parse((STATIC_DIR / "app.css").read_text(encoding="utf-8"))
    check_viewports(points)
    return points
