"""The one definition site for every literal round 5 repeats.

C-8 is the reason this module exists. `tests/web/test_projects_page.py` and
`tests/web/test_settings_live.py` each re-spell `1280x900` and reference
`render_check.VIEWPORTS` zero times — the drift that hid D1, a 140 px unusable
band between the two widths every gate happened to use. Round 5 must not
reproduce the defect it is reporting, so **no width literal appears in any other
`.py` file in this package**; every width arrives from `ROUND5_WIDTHS`, and
S30's three arrive from `render_check.VIEWPORTS` (test plan §3d).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import shepherd.web

#: The shipped stylesheet, read from the **package that is actually served**
#: rather than from a repo-relative guess, so a run against an installed build
#: parses the CSS that build sends.
STATIC_DIR: Final[Path] = Path(shepherd.web.__file__).parent / "static"

#: The nine measured boundary widths (test plan §2, §3d). Name -> (w, h).
#: 760/761 bracket the `max-width: 760px` media query **inclusively**; 900 is
#: the top of the band D1 lived in; 320 and 2560 are the extremes nothing has
#: ever driven.
ROUND5_WIDTHS: Final[dict[str, tuple[int, int]]] = {
    "w320": (320, 568),
    "w390": (390, 844),
    "w760": (760, 1024),
    "w761": (761, 1024),
    "w820": (820, 1180),
    "w900": (900, 1200),
    "w1280": (1280, 900),
    "w1920": (1920, 1080),
    "w2560": (2560, 1440),
}

#: **The drill-down breakpoint, parsed out of the stylesheet, never restated.**
#: `app.css` is the definition site: `@media (max-width: 760px) { .panes2 { … } }`
#: is what makes the two-pane pages a drill-down, and `_two_pane_health` decides
#: which side of it a measured width is on. A literal copied into a `.py` is D1's
#: exact mechanism — a width restated away from its source, silently drifting
#: when the source moves, while every gate keeps reporting green. So it is read.
#:
#: The regex is anchored on the `.panes2` rule *inside* the block, not on the
#: first `max-width` in the file: `app.css` carries several media queries and
#: matching any of them would bind the wrong number with no error.
_DRILL_RULE: Final[re.Pattern[str]] = re.compile(
    r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{\s*\.panes2\b"
)


def _parse_drill_breakpoint() -> int:
    text = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    matches = _DRILL_RULE.findall(text)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one `@media (max-width: Npx) {{ .panes2 …` block in "
            f"{STATIC_DIR / 'app.css'}; found {matches!r}. The drill-down breakpoint "
            f"cannot be read, and guessing it is how D1 stayed green."
        )
    return int(matches[0])


#: Read at import, so a stylesheet that moved its breakpoint fails loudly here
#: rather than silently mis-classifying every width measurement downstream.
DRILL_MAX_WIDTH: Final[int] = _parse_drill_breakpoint()

#: The bracket must straddle the **measured** breakpoint inclusively. If the CSS
#: moves to 820, `w760`/`w761` stop bracketing anything and S24 stops measuring
#: the boundary it exists for — so the relationship is asserted, not assumed.
if ROUND5_WIDTHS["w760"][0] != DRILL_MAX_WIDTH or ROUND5_WIDTHS["w761"][0] != DRILL_MAX_WIDTH + 1:
    raise AssertionError(
        f"app.css's drill-down breakpoint is {DRILL_MAX_WIDTH}px, which "
        f"w760={ROUND5_WIDTHS['w760'][0]} and w761={ROUND5_WIDTHS['w761'][0]} no "
        f"longer bracket. S24's boundary widths must follow the stylesheet."
    )

#: Per-scenario slices, by name, so a scenario body names a slice and never a
#: number. Test plan S21-S24 each name their widths in prose; these are those.
S21_WIDTHS: Final[tuple[str, ...]] = ("w390", "w820", "w1280")
S22_WIDTH: Final[str] = "w1280"
S23_WIDTHS: Final[tuple[str, ...]] = ("w320", "w1920", "w2560")
S24_WIDTHS: Final[tuple[str, ...]] = ("w760", "w761", "w820", "w900")
#: S15 and S19 and S25 drive the phone; S9/S28/S32/S33 the desktop.
PHONE: Final[str] = "w390"
DESKTOP: Final[str] = "w1280"

#: **Every scenario a full run must account for** (test plan §4, S0-S34).
#:
#: The run report is only allowed to become `qa5-latest.json` when its record
#: set is exactly this. The reason is measured, not theoretical: across 140 run
#: files the emitter had written, `FAIL` totalled 0 and 47 were all-green with
#: `scenarios: 0` — a failing scenario aborted before its `record()` call and
#: vanished, and the partial file then overwrote `latest` anyway. A report that
#: cannot express a failure is not a report.
#: `BRINGUP` and `WAVE2-LIVENESS` are harness-level rows a full run also writes
#: (`test_smoke_bringup.py:24`, `test_wave2_events.py:39`). They are part of the
#: planned set because they are part of a complete run: the environment arrived,
#: and the rig re-proved itself before wave 2 consumed it.
PLANNED_SCENARIOS: Final[tuple[str, ...]] = (
    *(f"S{index}" for index in range(35)),
    "BRINGUP",
    "WAVE2-LIVENESS",
)

#: A test function name carries its scenario id: `test_s13_...` -> `S13`. The
#: three harness-level tests (bring-up and the two rig re-proofs) match nothing
#: and are recorded under their own node name, which puts them in `extra` and
#: refuses publication — a bring-up that failed must not produce a "latest".
SCENARIO_IN_TEST_NAME: Final[re.Pattern[str]] = re.compile(r"^test_s(\d+)(?:_|$)")

#: The throwaway tmux socket. `-L <this>` is `argv[1]` on **every** invocation.
#: The user's own socket is never named here or anywhere in this package.
QA_SOCKET: Final[str] = "shepherd-qa"

#: The four owned panes (test plan §3b) and the fixture-side control pane.
PANES: Final[tuple[str, ...]] = (
    "shepherd_r5a",
    "shepherd_r5b",
    "shepherd_r5c",
    "shepherd_r5d",
)
CONTROL_PANE: Final[str] = "shepherd_r5z"
PANE_COLS, PANE_ROWS = 160, 45

#: Every wait in this harness is bounded and loud. `sleep N` is not readiness.
CEILING_S: Final[float] = 10.0
FRAME_CEILING_S: Final[float] = 10.0

#: S20/S21's enumerated control set (test plan S20). **Named selectors, never
#: "every element on the page"**: an unbounded differential degrades into an
#: assertion over the whole document or over nothing, which is what `r1` had.
#: Each entry is `(name, css_selector)` and each selector was read out of the
#: shipped shell, not guessed — the legend's opener is a *class*
#: (`flock.js:307`), not an id, and a set that spelled it `#legend-info` would
#: have silently matched nothing and made the differential vacuous.
CONTROL_SET: Final[tuple[tuple[str, str], ...]] = (
    ("nav-shepherd", '.nav-item[data-page="shepherd"]'),
    ("nav-flock", '.nav-item[data-page="flock"]'),
    ("nav-projects", '.nav-item[data-page="projects"]'),
    ("nav-queues", '.nav-item[data-page="queues"]'),
    ("nav-kanban", '.nav-item[data-page="kanban"]'),
    ("nav-settings", '.nav-item[data-page="settings"]'),
    ("drawer-open", "#drawer-open"),
    ("collapse", "#collapse"),
    ("legend-info", "#flock-legend .legend-info"),
    ("proj-new", "#proj-new"),
)

#: **Where each control lives, so the differential has a non-vacuity floor.**
#:
#: `CONTROL_SET` is a *differential*: a name True in the baseline and False in
#: the variant is a regression. An entry False on **both** sides drops out
#: silently — and a renamed id, or a selector that stopped matching anything at
#: all, drops out identically. That is the exact failure the enumerated set was
#: introduced to prevent: it degrades into an assertion over nothing, and prints
#: green.
#:
#: The floor is resolution, measured **on the page the control actually lives
#: on**. `#proj-new` is not in the Flock's DOM and never will be, so measuring
#: its presence from the Flock proves nothing; measuring it from Projects proves
#: the id still exists. `"shell"` means the persistent chrome, present on every
#: page — the nav rail, the drawer opener, the collapse control.
CONTROL_PAGE: Final[dict[str, str]] = {
    "nav-shepherd": "shell",
    "nav-flock": "shell",
    "nav-projects": "shell",
    "nav-queues": "shell",
    "nav-kanban": "shell",
    "nav-settings": "shell",
    "drawer-open": "shell",
    "collapse": "shell",
    "legend-info": "flock",
    "proj-new": "projects",
}

#: Every `CONTROL_SET` name must say where it lives, or the floor has a hole in
#: exactly the shape of the entry somebody forgot.
if {name for name, _ in CONTROL_SET} != set(CONTROL_PAGE):
    raise AssertionError(
        f"CONTROL_SET and CONTROL_PAGE disagree: "
        f"{ {name for name, _ in CONTROL_SET} ^ set(CONTROL_PAGE) }"
    )

#: The six nav entries, in shell order.
NAV_PAGES: Final[tuple[str, ...]] = (
    "shepherd",
    "flock",
    "projects",
    "queues",
    "kanban",
    "settings",
)
