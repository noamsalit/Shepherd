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
    /root/Shepherd/.venv/bin/python tools/render_check.py --url http://127.0.0.1:8765/ --fail-on-empty

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
    ns = parser.parse_args(argv)

    named = ns.url or ns.file
    if named:
        target, positional_shots = named, ns.rest[:1]
    else:
        target = ns.rest[0] if ns.rest else "shepherd-dark.html"
        positional_shots = ns.rest[1:2]

    shots = Path(positional_shots[0]) if positional_shots else default_shots(target)
    return Args(target=target, shots=shots, fail_on_empty=ns.fail_on_empty)


def check(origin: str, shots: Path, fail_on_empty: bool = False) -> int:
    """Drive every page at every viewport. `origin` is a URL or a path."""
    url = target_url(origin)
    shots.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})

            console: list[str] = []
            page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
            page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))

            page.goto(url)
            page.wait_for_timeout(700)

            # Arrival, before anything else is asked of the page. A server that
            # answers 200 with nothing fails every page check below, and that
            # report reads exactly like a page with no nav — two different
            # defects wearing one sentence. This one says which.
            if fail_on_empty and not page.locator("body").inner_text().strip():
                failures.append(f"[{name}] arrived at an empty page")

            errors = [c for c in console if c.startswith(("error", "pageerror"))]
            if errors:
                failures += [f"[{name}] {e}" for e in errors]

            # The error surface the prototype paints on itself. If it is on the
            # page, something threw after the handlers were wired.
            if page.locator(".boom").count():
                failures.append(f"[{name}] error banner: {page.locator('.boom').inner_text()}")

            for target, must_see in PAGES:
                nav = page.locator(NAV_SELECTOR.format(page=target))
                if not nav.count():
                    failures.append(f"[{name}] no nav entry for {target}")
                    continue
                if name == "phone":
                    page.locator(DRAWER_SELECTOR).click()
                    page.wait_for_timeout(250)
                nav.click()
                page.wait_for_timeout(350)

                view = page.locator(f"#page-{target}")
                if not view.is_visible():
                    failures.append(f"[{name}] {target} did not open")
                    continue
                if must_see not in view.inner_text():
                    failures.append(f"[{name}] {target} is missing {must_see!r}")

                page.screenshot(path=shots / f"{name}-{target}.png", full_page=False)

            # Nothing may scroll sideways at any width.
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 1:
                failures.append(f"[{name}] page scrolls sideways by {overflow}px")

            page.close()
        browser.close()

    for f in failures:
        print("FAIL", f)
    print(f"\n{url}")
    print(f"{len(failures)} failures · screenshots in {shots}")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys

    args = parse_args(sys.argv[1:])
    raise SystemExit(check(args.target, args.shots, args.fail_on_empty))
