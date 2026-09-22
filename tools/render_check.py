#!/usr/bin/env python
"""Render the page in a real browser and assert on what came out.

Three bugs shipped to this prototype in one day that reading could not catch:
a block of CSS pasted into the `<script>`, a click handler that was never
inserted because a replace silently matched nothing, and a temporal dead zone.
All three left the markup intact, so the page still *looked* fine.

The rule this encodes: a page is not verified until a browser has run it and a
console error is a failure. Screenshots are the secondary output; the console
and the assertions are the point.

**Point it at the served page, not at a file, whenever one is running.** A file
opened over `file://` proves the markup and the script; it cannot prove that the
server hands over the same bytes, that the module graph resolves from
`/static/`, or that the first paint survives a real API answering with real
data. Those are exactly the failures a local file cannot have.

    /root/Shepherd/.venv/bin/python tools/render_check.py --file shepherd-dark.html
    /root/Shepherd/.venv/bin/python tools/render_check.py --url http://127.0.0.1:8765/
    /root/Shepherd/.venv/bin/python tools/render_check.py --url http://127.0.0.1:8765/ --fail-on-empty --must-fill

A bare positional target still works and is still classified by its scheme, so
every command already written down keeps running.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

# Phone first, because that is the primary client, then a laptop width.
VIEWPORTS = [("phone", 390, 844), ("desktop", 1280, 900)]

# The two selectors this tool drives, each with exactly one definition site.
# The shell (`index.html` / `app.js`) and this checker have to agree on them,
# and a second literal spelling on either side is how that agreement rots
# without anyone noticing. Named here, asserted by
# `tests/tools/test_render_check_args.py`, consumed by name in Phase 5's shell.
NAV_SELECTOR = '.nav-item[data-page="{page}"]'
DRAWER_SELECTOR = "#drawer-open"

# Every page root, so the loop can assert *exclusivity* rather than presence.
PAGE_ROOT_SELECTOR = '[id^="page-"]'

# How far a box may miss the edge of the viewport before it is called a defect.
# One pixel, the same tolerance the horizontal-overflow gate uses.
SLACK_PX = 1

# How much of the viewport a page root must reach down to. Measured, not chosen:
# **all twelve** healthy readings on the shipped page — six pages × two
# viewports — put the root's bottom edge exactly on the bottom of the viewport,
# and the one recorded defect of this shape (`.main > .detail` losing its
# `flex: 1`, so the Shepherd page became a content-height box at the top of an
# empty column) read 0.25 and 0.26. The floor sits between the two with a lot of
# room on both sides, because this is a check for **collapsed**, not a pixel
# comparison, and a gate that goes red when a font changes gets turned off.
#
# **Opt-in (`--must-fill`), unlike every other assertion here.** "Every page
# root fills the column it is given" is a claim about *this* shell's layout
# contract, not a property of web pages: a page whose root is a content-height
# `<section>` is a perfectly good page, and four of this tool's own fixtures are
# exactly that. Making it unconditional turned those four red — which would have
# been a checker rejecting correct pages, the opposite of the defect it is here
# to catch.
FILL_FLOOR = 0.75

# What the browser is asked for, per page root, in one round trip — one layout
# pass, so the numbers cannot straddle a reflow and disagree about a page that
# was never in either state.
ROOT_METRICS = """
(selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  const box = el.getBoundingClientRect();
  return { top: box.top, bottom: box.bottom, height: box.height };
}
"""

# (page, what must be visible once it is open)
#
# Six pages, in nav order (`docs/design/ui-decisions.md`). The `must_see` string
# has to be present on the **served** page, not merely on the prototype, so it
# is each page's own name rendered inside its own root — the one thing all six
# can carry, including the two placeholders (Queues and Kanban), which by
# decision have no content this milestone. Phase 5's page roots and Phases 6-9's
# bodies consume this table; a page that cannot show its own name is a page the
# nav is lying about.
PAGES = [
    ("shepherd", "Shepherd"),
    ("flock", "Flock"),
    ("queues", "Queues"),
    ("projects", "Projects"),
    ("kanban", "Kanban"),
    ("settings", "Settings"),
]


@dataclass(frozen=True)
class Args:
    """What the command line asked for."""

    target: str
    shots: Path
    fail_on_empty: bool
    must_fill: bool


def target_url(target: str) -> str:
    """A URL is used as given; anything else is a path resolved to a `file://`.

    Deliberately not a guess: `urlparse` only treats it as a URL when it carries
    an http(s) scheme, so a Windows-style path or a file named `http-notes.html`
    is still read as a path.
    """
    parsed = urlparse(target)
    if parsed.scheme in ("http", "https"):
        return target
    return Path(target).resolve().as_uri()


def default_shots(target: str) -> Path:
    """Screenshots land beside the file when checking one, and in `./shots`
    when checking a URL — a served page has no directory of its own to sit in.
    """
    if urlparse(target).scheme in ("http", "https"):
        return Path("shots")
    return Path(target).parent / "shots"


def parse_args(argv: list[str]) -> Args:
    """`--url` for a served origin, `--file` for the prototype, or a positional.

    The two flags are mutually exclusive because naming both is not an ambiguity
    to resolve by precedence — it is a command whose author meant one of two
    different things, and guessing which would put the checker on the wrong page
    silently.
    """
    parser = argparse.ArgumentParser(description="Render a page and assert on what came out.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--url", help="a served origin, e.g. http://127.0.0.1:8765/")
    where.add_argument("--file", help="a path to a page on disk")
    parser.add_argument(
        "rest",
        nargs="*",
        help="the target and the screenshot directory, positionally: "
        "`TARGET [SHOTS]`, or just `SHOTS` when --url or --file named the target",
    )
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="fail when the origin hands over a page with no text at all",
    )
    parser.add_argument(
        "--must-fill",
        action="store_true",
        help="fail when a page root does not reach the bottom of the viewport "
        "(this shell's contract; not every page's)",
    )
    ns = parser.parse_args(argv)

    # `--url "$VAR"` with `VAR` unset hands argparse an empty string, and a
    # truthiness test reads that as "no target named" — silently retargeting a
    # server check at the prototype file. An empty value is a broken command.
    for flag, value in (("--url", ns.url), ("--file", ns.file)):
        if value is not None and not value.strip():
            parser.error(f"{flag} was given an empty value")

    named = ns.url if ns.url is not None else ns.file
    if named is not None:
        target, rest = named, list(ns.rest)
    else:
        target = ns.rest[0] if ns.rest else "shepherd-dark.html"
        rest = list(ns.rest[1:])

    # Dropping what it cannot place is how a checker ends up pointed somewhere
    # its author did not ask for, quietly.
    if len(rest) > 1:
        parser.error(f"unexpected extra arguments: {' '.join(rest[1:])}")

    shots = Path(rest[0]) if rest else default_shots(target)
    return Args(
        target=target, shots=shots, fail_on_empty=ns.fail_on_empty, must_fill=ns.must_fill
    )


def viewport_faults(
    page: object, target: str, viewport_height: float, must_fill: bool
) -> list[str]:
    """Is this page actually **on the screen**? The gate that did not exist.

    Two of the five defects the first live drive found were pages that rendered
    perfectly and could not be read, and this tool reported *12 pages checked ·
    12 screenshots · 0 failures* over both: nothing overflowed horizontally,
    nothing threw, exactly one root was visible and every page still named
    itself. Reverting either fix turned nothing red in the whole tree except a
    byte-freeze digest, which any changed byte trips and which says nothing
    about the page. It took a person looking at a screenshot.

    So the root is **measured** rather than inferred from what it contains:

    * it has a height at all — a root laid out at zero height is a page nobody
      can read, however correct its markup;
    * it is inside the viewport, top and bottom, to the same one pixel the
      horizontal gate allows;
    * and it **reaches the bottom of the column it was given**. That is the one
      that bites: `.main > .detail` carries `flex: 1` and losing it made the
      Shepherd page a content-height box at the top of an empty column with its
      composer unpinned, at `FILL_FLOOR`'s 0.25 against twelve healthy readings
      of 1.00.

    **What this deliberately does not try to see**, because a checker that
    claims more than it measures is worse than one that claims less: anything
    *inside* the root. `.herd` declaring two grid rows while carrying three
    items crushed the three panes into a 99px strip — and the root's own box was
    byte-identical to the healthy one (56 → 900 of a 900px viewport) in both
    states. No per-root rectangle can distinguish those, and encoding the panes'
    own selectors here would be a second spelling of
    `tests/web/test_shell_live.py::test_each_page_root_fills_the_column_it_is_given`,
    which already holds that claim with both mutations recorded against it. A
    rule written down twice is a rule that drifts.
    """
    metrics = page.evaluate(ROOT_METRICS, f"#page-{target}")  # type: ignore[attr-defined]
    if metrics is None:
        return ["the page root vanished before it could be measured"]

    faults: list[str] = []
    screen = round(viewport_height)
    if metrics["height"] <= 0:
        faults.append("the page root is laid out with zero height")
    if metrics["top"] < -SLACK_PX:
        faults.append(f"the page root starts {round(-metrics['top'])}px above the viewport")
    if metrics["bottom"] > viewport_height + SLACK_PX:
        over = round(metrics["bottom"] - viewport_height)
        faults.append(f"the page root is below the fold — it ends {over}px past a {screen}px viewport")
    elif must_fill and metrics["bottom"] < viewport_height * FILL_FLOOR:
        short = round(viewport_height - metrics["bottom"])
        faults.append(
            f"the page root is collapsed above the fold — it ends {short}px short of "
            f"a {screen}px viewport, with an empty column beneath it"
        )
    return faults


def check(
    origin: str, shots: Path, fail_on_empty: bool = False, must_fill: bool = False
) -> int:
    """Drive every page at every viewport. `origin` is a URL or a path."""
    url = target_url(origin)
    failures: list[str] = []
    opened = 0
    taken = 0
    shots_made = False

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})

            console: list[str] = []
            page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
            page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))

            booms_reported = 0

            def sweep(where: str) -> None:
                """Report — and then forget — everything the page has said.

                Read once, before the navigation loop, this gate covered the
                first 700 ms of a run whose whole substance is the loop. It is
                now read at arrival, after every page opens, and once more at
                the end, so the failure names the page that caused it.

                Forgetting is the other half: a list re-read and never drained
                reports one error once per remaining page, which is noise
                dressed as thoroughness. The banner count works the same way —
                only banners not yet reported are new.
                """
                nonlocal booms_reported
                errors = [c for c in console if c.startswith(("error", "pageerror"))]
                console.clear()
                failures.extend(f"[{name}] {where}: {e}" for e in errors)

                banners = page.locator(".boom")
                painted = banners.count()
                if painted > booms_reported:
                    for i in range(booms_reported, painted):
                        text = banners.nth(i).inner_text()
                        failures.append(f"[{name}] {where}: error banner: {text}")
                    booms_reported = painted

            def open_roots() -> int:
                return page.locator(f"{PAGE_ROOT_SELECTOR}:visible").count()

            page.goto(url)
            page.wait_for_timeout(700)

            # Arrival, before anything else is asked of the page. A server that
            # answers 200 with nothing fails every page check below, and that
            # report reads exactly like a page with no nav — two different
            # defects wearing one sentence. This one says which.
            if fail_on_empty and not page.locator("body").inner_text().strip():
                failures.append(f"[{name}] arrived at an empty page")

            sweep("on arrival")

            # Nothing is open yet, so more than one visible root means the
            # routing never hid anything — U18, which is the defect this tool
            # was written for and the one it could not see.
            arrived_open = open_roots()
            if arrived_open > 1:
                failures.append(f"[{name}] on arrival: {arrived_open} page roots visible at once")

            for target, must_see in PAGES:
                nav = page.locator(NAV_SELECTOR.format(page=target))
                if not nav.count():
                    failures.append(f"[{name}] no nav entry for {target}")
                    continue
                if name == "phone":
                    drawer = page.locator(DRAWER_SELECTOR)
                    # Same shape as the nav entry three lines up. Clicking a
                    # locator that matches nothing raises after 30s, and a
                    # raise loses every failure already collected along with
                    # the summary line — a missing control must be reported,
                    # not thrown.
                    if not drawer.count():
                        failures.append(f"[{name}] no drawer control for {target}")
                        continue
                    drawer.click()
                    page.wait_for_timeout(250)
                nav.click()
                page.wait_for_timeout(350)
                opened += 1

                sweep(f"after opening {target}")

                view = page.locator(f"#page-{target}")
                if not view.is_visible():
                    failures.append(f"[{name}] {target} did not open")
                    continue
                # Presence is not exclusivity: asserting only that the clicked
                # root is visible passes a page on which all six are.
                now_open = open_roots()
                if now_open != 1:
                    failures.append(f"[{name}] {target}: {now_open} page roots visible at once")
                if must_see not in view.inner_text():
                    failures.append(f"[{name}] {target} is missing {must_see!r}")

                failures.extend(
                    f"[{name}] {target}: {complaint}"
                    for complaint in viewport_faults(page, target, height, must_fill)
                )

                if not shots_made:
                    # Lazily, so a run that never reached a page leaves no
                    # empty directory behind claiming it did.
                    shots.mkdir(parents=True, exist_ok=True)
                    shots_made = True
                page.screenshot(path=shots / f"{name}-{target}.png", full_page=False)
                taken += 1

            # Nothing may scroll sideways at any width.
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 1:
                failures.append(f"[{name}] page scrolls sideways by {overflow}px")

            sweep("before the page closed")
            page.close()
        browser.close()

    # A floor on how much was checked. `0 failures` is byte-identical whether
    # twelve assertions ran or none, which is this repo's own "a counter
    # reading 0 because its path never ran" in its reporting form.
    if not opened:
        failures.append("no pages were checked")

    for f in failures:
        print("FAIL", f)
    print(f"\n{url}")
    print(f"{opened} pages checked · {taken} screenshots · {len(failures)} failures")
    print(f"screenshots in {shots}")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys

    args = parse_args(sys.argv[1:])
    raise SystemExit(check(args.target, args.shots, args.fail_on_empty, args.must_fill))
