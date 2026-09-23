"""§3d — `HIT_TESTABLE` and `PANE_HEALTHY`, defined **once**, read by reference.

Round 1 said *"hit-testable"* in two scenarios and plain *"clickable"* in three
others, where it degraded to **"present in the DOM"**. It also accepted any
**non-zero** box as a healthy pane — which a 1 px collapse satisfies with a
32 px button inside it. Both are defined here and nowhere else.

`FILL_FLOOR` and `SLACK_PX` are **imported from the product's own checker**
(`tools/render_check.py`), never re-spelled as `0.75` and `1`. A restated
constant is this tree's signature defect: it is exactly what hid D1, a 140 px
unusable band that every gate quoting the restated number reported green over.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

_TOOLS = Path("/root/Shepherd/tools")
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from render_check import FILL_FLOOR, SLACK_PX, VIEWPORTS  # noqa: E402

__all__ = [
    "FILL_FLOOR",
    "SLACK_PX",
    "VIEWPORTS",
    "HitTest",
    "hit_testable",
    "hit_testable_nth",
    "pane_healthy",
]

#: One layout pass, four conditions. Returning the *reasons* rather than a bare
#: boolean is what makes a red readable: "not hit-testable" names which of the
#: four failed and by how much.
_HIT_TESTABLE_JS = """
(args) => {
  const el = document.querySelector(args.selector);
  if (el === null) return {found: false};
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const painted = document.elementFromPoint(cx, cy);
  const style = getComputedStyle(el);
  const slack = args.slack;
  return {
    found: true,
    rect: {top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right,
           width: rect.width, height: rect.height},
    nonZero: rect.width > 0 && rect.height > 0,
    onTop: painted !== null && (painted === el || el.contains(painted)),
    paintedTag: painted === null ? null : painted.tagName + (painted.id ? "#" + painted.id : ""),
    interactive: style.pointerEvents !== "none" && el.disabled !== true,
    inViewport: rect.top >= -slack && rect.left >= -slack
                && rect.bottom <= window.innerHeight + slack
                && rect.right <= window.innerWidth + slack,
    viewport: {width: window.innerWidth, height: window.innerHeight}
  };
}
"""

#: A pane is healthy only if it **wholly contains the box** of a hit-testable
#: descendant — not merely "has one somewhere in the subtree". A pane collapsed
#: to 1 px cannot contain a 32 px control's box, which is precisely the failure
#: *"non-zero"* let through.
_PANE_HEALTHY_JS = """
(args) => {
  const pane = document.querySelector(args.pane);
  const root = document.querySelector(args.root);
  if (pane === null || root === null) return {found: false, pane: pane !== null, root: root !== null};
  const slack = args.slack;
  const box = pane.getBoundingClientRect();
  const rootBox = root.getBoundingClientRect();
  const candidates = pane.querySelectorAll("button, a, input, select, textarea, [tabindex], [role=button]");
  let contained = null;
  for (const el of candidates) {
    const rect = el.getBoundingClientRect();
    if (!(rect.width > 0 && rect.height > 0)) continue;
    const painted = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    if (!(painted !== null && (painted === el || el.contains(painted)))) continue;
    const style = getComputedStyle(el);
    if (style.pointerEvents === "none" || el.disabled === true) continue;
    if (!(rect.top >= -slack && rect.left >= -slack
          && rect.bottom <= window.innerHeight + slack
          && rect.right <= window.innerWidth + slack)) continue;
    const inside = rect.top >= box.top - slack && rect.bottom <= box.bottom + slack
                && rect.left >= box.left - slack && rect.right <= box.right + slack;
    if (inside) { contained = {tag: el.tagName, id: el.id, rect: {top: rect.top, bottom: rect.bottom,
                   left: rect.left, right: rect.right, width: rect.width, height: rect.height}}; break; }
  }
  return {
    found: true,
    paneBox: {top: box.top, bottom: box.bottom, left: box.left, right: box.right,
              width: box.width, height: box.height},
    contains: contained,
    rootBottom: rootBox.bottom,
    fillTarget: window.innerHeight * args.fillFloor,
    viewport: {width: window.innerWidth, height: window.innerHeight}
  };
}
"""

_OVERFLOW_JS = """
(slack) => {
  const doc = document.documentElement;
  return {
    scrollWidth: doc.scrollWidth,
    innerWidth: window.innerWidth,
    overflow: doc.scrollWidth - window.innerWidth,
    slack: slack
  };
}
"""

_VISIBLE_ROOTS_JS = """
() => Array.from(document.querySelectorAll('[id^="page-"]'))
        .filter((el) => el.offsetParent !== null || getComputedStyle(el).display !== "none")
        .map((el) => el.id)
"""


@dataclass(frozen=True)
class HitTest:
    selector: str
    found: bool
    detail: dict[str, Any]

    @property
    def ok(self) -> bool:
        if not self.found:
            return False
        return bool(
            self.detail["nonZero"]
            and self.detail["onTop"]
            and self.detail["interactive"]
            and self.detail["inViewport"]
        )

    def why(self) -> str:
        if not self.found:
            return f"{self.selector}: no such element"
        failed = [
            name
            for name in ("nonZero", "onTop", "interactive", "inViewport")
            if not self.detail[name]
        ]
        return f"{self.selector}: failed {failed}; {self.detail}"


def hit_testable(page: Page, selector: str) -> HitTest:
    """§3d's four conditions, measured in one layout pass."""
    result = page.evaluate(_HIT_TESTABLE_JS, {"selector": selector, "slack": SLACK_PX})
    return HitTest(selector=selector, found=bool(result["found"]), detail=dict(result))


def assert_hit_testable(page: Page, selector: str, context: str = "") -> HitTest:
    test = hit_testable(page, selector)
    assert test.ok, f"{context} HIT_TESTABLE failed — {test.why()}"
    return test


_HIT_TESTABLE_NTH_JS = """
(args) => {
  const el = document.querySelectorAll(args.selector)[args.index];
  if (el === undefined) return {found: false};
  const rect = el.getBoundingClientRect();
  const painted = document.elementFromPoint(rect.left + rect.width / 2,
                                            rect.top + rect.height / 2);
  const style = getComputedStyle(el);
  const slack = args.slack;
  return {
    found: true,
    rect: {top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right,
           width: rect.width, height: rect.height},
    nonZero: rect.width > 0 && rect.height > 0,
    onTop: painted !== null && (painted === el || el.contains(painted)),
    interactive: style.pointerEvents !== "none" && el.disabled !== true,
    inViewport: rect.top >= -slack && rect.left >= -slack
                && rect.bottom <= window.innerHeight + slack
                && rect.right <= window.innerWidth + slack,
    viewport: {width: window.innerWidth, height: window.innerHeight}
  };
}
"""


def hit_testable_nth(page: Page, selector: str, index: int) -> HitTest:
    """`HIT_TESTABLE` over the nth match of a plain CSS selector.

    Playwright's `>> nth=` syntax is a *locator* selector and is not valid CSS,
    so `eval_on_selector` rejects it outright — which is how a settings-nav
    assertion turned into a `SyntaxError` rather than a measurement.
    """
    result = page.evaluate(
        _HIT_TESTABLE_NTH_JS, {"selector": selector, "index": index, "slack": SLACK_PX}
    )
    return HitTest(selector=f"{selector}[{index}]", found=bool(result["found"]), detail=dict(result))


def assert_hit_testable_nth(page: Page, selector: str, index: int, context: str = "") -> HitTest:
    test = hit_testable_nth(page, selector, index)
    assert test.ok, f"{context} HIT_TESTABLE failed — {test.why()}"
    return test


def pane_healthy(page: Page, pane: str, root: str) -> dict[str, Any]:
    return dict(
        page.evaluate(
            _PANE_HEALTHY_JS,
            {"pane": pane, "root": root, "slack": SLACK_PX, "fillFloor": FILL_FLOOR},
        )
    )


def assert_pane_healthy(page: Page, pane: str, root: str, context: str = "") -> dict[str, Any]:
    """Both halves of §3d, and the second is the one that defeats B2/B18.

    The root-rectangle check is structurally blind to intra-page grid collapse,
    so the containment half is measured at the **pane**; and *"non-zero"* is a
    one-pixel floor, so the fill half is the product's own `FILL_FLOOR`.
    """
    result = pane_healthy(page, pane, root)
    assert result["found"], f"{context} pane or root missing: {result}"
    assert result["contains"] is not None, (
        f"{context} {pane} wholly contains no HIT_TESTABLE control's box — "
        f"pane box {result['paneBox']}"
    )
    assert result["rootBottom"] >= result["fillTarget"], (
        f"{context} {root} reaches {result['rootBottom']:.1f}px, below FILL_FLOOR's "
        f"{result['fillTarget']:.1f}px of a {result['viewport']['height']}px viewport"
    )
    return result


def assert_no_horizontal_overflow(page: Page, context: str = "") -> None:
    """Containment against the **viewport**, never against a parent.

    B3: a self-sizing box grows to fit, so a 307,418 px container passed every
    "content fits its box" assertion. A parent-relative containment assertion is
    unfalsifiable here.
    """
    result = page.evaluate(_OVERFLOW_JS, SLACK_PX)
    assert result["overflow"] <= SLACK_PX, (
        f"{context} horizontal overflow of {result['overflow']}px beyond the "
        f"{result['innerWidth']}px viewport (slack {SLACK_PX})"
    )


def visible_roots(page: Page) -> list[str]:
    return [str(name) for name in page.evaluate(_VISIBLE_ROOTS_JS)]


def assert_one_root_visible(page: Page, context: str = "") -> str:
    roots = visible_roots(page)
    assert len(roots) == 1, f"{context} expected exactly one visible [id^=page-], saw {roots}"
    return roots[0]
