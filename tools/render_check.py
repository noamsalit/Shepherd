#!/usr/bin/env python
"""Render the prototype in a real browser and assert on what came out.

Three bugs shipped to this prototype in one day that reading could not catch:
a block of CSS pasted into the `<script>`, a click handler that was never
inserted because a replace silently matched nothing, and a temporal dead zone.
All three left the markup intact, so the page still *looked* fine.

The rule this encodes: a page is not verified until a browser has run it and a
console error is a failure. Screenshots are the secondary output; the console
and the assertions are the point.

    /root/Shepherd/.venv/bin/python render_check.py shepherd-dark.html
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Phone first, because that is the primary client, then a laptop width.
VIEWPORTS = [("phone", 390, 844), ("desktop", 1280, 900)]

# (page, what must be visible once it is open)
PAGES = [
    ("shepherd", "which sessions are stuck"),
    ("herd", "needs you"),
    ("projects", "payments-api"),
    ("settings", "Autonomy"),
]


def check(path: Path, shots: Path) -> int:
    shots.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height})

            console: list[str] = []
            page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
            page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))

            page.goto(path.resolve().as_uri())
            page.wait_for_timeout(700)

            errors = [c for c in console if c.startswith(("error", "pageerror"))]
            if errors:
                failures += [f"[{name}] {e}" for e in errors]

            # The error surface the prototype paints on itself. If it is on the
            # page, something threw after the handlers were wired.
            if page.locator(".boom").count():
                failures.append(f"[{name}] error banner: {page.locator('.boom').inner_text()}")

            for target, must_see in PAGES:
                nav = page.locator(f'.nav-item[data-page="{target}"]')
                if not nav.count():
                    failures.append(f"[{name}] no nav entry for {target}")
                    continue
                if name == "phone":
                    page.locator("#drawer-open").click()
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
    print(f"\n{len(failures)} failures · screenshots in {shots}")
    return 1 if failures else 0


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "shepherd-dark.html")
    raise SystemExit(check(target, target.parent / "shots"))
