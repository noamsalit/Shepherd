"""Real-browser plumbing: a per-MODULE Playwright lifecycle and user-like input.

**Never session-scoped.** qa5 held sync Playwright open for the whole session,
which leaves a running asyncio loop in the main thread and breaks every later
`sync_playwright()` in the same process (W7.1, existing-harness §5). Here
`BrowserSession.start()` is called by a module fixture and `stop()` at module
end, and `stop()` asserts the loop is gone.

**Every user action is a Playwright click, dblclick, hover, keypress, type,
mouse down/up or touchscreen tap** (test-plan §0 row "fetch shim"). This
module offers no JS click and no JS `dialog.close()` as a UI action. If a
scenario ever needs one it must call a function whose name starts with `js_`
and label the scenario; there is none here.

Listeners (console, pageerror, request, response, websocket) are attached to a
context **before** any navigation, and each scenario's log is dumped to
`<run_dir>/ui/<scenario>/` with a screenshot.

**Sync Playwright delivers page events only during a Playwright call.** A
predicate that reads a `PageLog` (requests, console, websockets) while the
harness merely sleeps polls a list that never grows. `pump(page)` makes the
cheapest Playwright call there is so queued events are dispatched, and
`settle(predicate, bound_s, page)` pumps before every poll.

Playwright is imported inside `start()`, so importing this module does nothing.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

from . import paths
from .verdict import Blocked, observe

if TYPE_CHECKING:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        ConsoleMessage,
        Locator,
        Page,
        Playwright,
        Request,
        Response,
        Route,
        WebSocket,
    )

MASTER_SEND_GLOB = "**/api/master/send"

#: A harness liveness bound for a UI change caused by one user input
#: (not a product SLO — test-plan §0 rule 1).
UI_BOUND_S = 10.0

T = TypeVar("T")


@dataclass
class PageLog:
    """What the page did, from Playwright's own events (test-plan §5 browser row)."""

    console: list[dict[str, str]] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    requests: list[dict[str, str]] = field(default_factory=list)
    responses: list[dict[str, object]] = field(default_factory=list)
    websockets: list[str] = field(default_factory=list)
    master_send_aborts: int = 0

    def console_errors(self) -> list[dict[str, str]]:
        return [entry for entry in self.console if entry["type"] == "error"]

    def requests_to(self, path_fragment: str, method: str | None = None) -> list[dict[str, str]]:
        return [
            entry for entry in self.requests
            if path_fragment in entry["url"] and (method is None or entry["method"] == method)
        ]

    def status_of(self, path_fragment: str) -> list[int]:
        found: list[int] = []
        for entry in self.responses:
            url = entry.get("url")
            status = entry.get("status")
            if isinstance(url, str) and path_fragment in url and isinstance(status, int):
                found.append(status)
        return found

    def as_json(self) -> dict[str, object]:
        return {
            "console": self.console,
            "page_errors": self.page_errors,
            "requests": self.requests,
            "responses": self.responses,
            "websockets": self.websockets,
            "master_send_aborts": self.master_send_aborts,
        }


class BrowserSession:
    """One Playwright + one chromium, for one test module."""

    def __init__(self, artifacts: Path, launch_args: Sequence[str] = ()) -> None:
        self.artifacts = artifacts
        self.launch_args = list(launch_args)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.version = ""

    def start(self) -> None:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(paths.BROWSERS_PATH))
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True, args=self.launch_args)
        except Exception as error:  # a browser that cannot launch is an environment fact
            self._playwright.stop()
            self._playwright = None
            raise Blocked(f"chromium did not launch: {error}") from error
        self.version = self._browser.version
        if not self.version:
            raise Blocked("chromium launched with an empty version")

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise Blocked("the browser is not started")
        return self._browser

    def stop(self) -> list[str]:
        """Close the browser, stop Playwright, and prove no loop was left behind."""
        problems: list[str] = []
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        if running_loop_in_main_thread():
            problems.append("an asyncio loop is still running in the main thread after playwright.stop() (W7.1)")
        return problems

    @contextmanager
    def context(
        self,
        scenario: str,
        *,
        viewport: tuple[int, int] = (1280, 900),
        has_touch: bool = False,
        is_mobile: bool = False,
        java_script_enabled: bool = True,
        abort_master_send: bool = True,
        color_scheme: Literal["dark", "light", "no-preference", "null"] | None = None,
    ) -> Iterator[tuple[BrowserContext, PageLog]]:
        """A fresh context with listeners attached before any navigation."""
        log = PageLog()
        context = self.browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            has_touch=has_touch,
            is_mobile=is_mobile,
            java_script_enabled=java_script_enabled,
            color_scheme=color_scheme,
        )

        def on_page(page: Page) -> None:
            attach(page, log)

        context.on("page", on_page)
        if abort_master_send:
            def abort(route: Route) -> None:
                log.master_send_aborts += 1
                route.abort()

            context.route(MASTER_SEND_GLOB, abort)
        try:
            yield context, log
        finally:
            out = self.artifacts / scenario
            out.mkdir(parents=True, exist_ok=True)
            for index, page in enumerate(context.pages):
                try:
                    page.screenshot(path=str(out / f"page{index}.png"), full_page=True)
                except Exception as error:  # the page may already be gone; say so, never swallow
                    log.page_errors.append(f"(harness) screenshot failed: {error}")
            (out / "pagelog.json").write_text(json.dumps(log.as_json(), indent=1), encoding="utf-8")
            context.close()


def attach(page: Page, log: PageLog) -> None:
    def on_console(message: ConsoleMessage) -> None:
        log.console.append({"type": message.type, "text": message.text})

    def on_error(error: Exception) -> None:
        log.page_errors.append(str(error))

    def on_request(request: Request) -> None:
        log.requests.append({"method": request.method, "url": request.url})

    def on_response(response: Response) -> None:
        log.responses.append({"url": response.url, "status": response.status})

    def on_websocket(socket: WebSocket) -> None:
        log.websockets.append(socket.url)

    page.on("console", on_console)
    page.on("pageerror", on_error)
    page.on("request", on_request)
    page.on("response", on_response)
    page.on("websocket", on_websocket)


def running_loop_in_main_thread() -> bool:
    """True if an asyncio loop is running in this (main) thread — the W7.1 leak."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


# ----- waiting on a page (sync Playwright dispatches events only inside its calls) -----------


def pump(page: Page) -> None:
    """Let Playwright deliver queued page events (request, response, console, websocket…).

    The sync API dispatches event callbacks only while a Playwright call is in
    progress, so a predicate that reads the `PageLog` alone would poll a list
    that never grows. Measured (STAGE B, wave 6): a fetch the page made 0.6 s
    after an SSE frame was not in the log 30 s later while the loop only slept.
    """
    page.wait_for_timeout(1)


def settle(predicate: Callable[[], T | None], bound_s: float = UI_BOUND_S, page: Page | None = None) -> tuple[T | None, float]:
    """Poll a UI predicate (`verdict.observe`); the caller classifies a blown bound.

    Pass `page` whenever the predicate reads the `PageLog`: every poll then
    pumps first (see `pump`). A predicate that queries the DOM through a
    locator is itself a Playwright call and needs no `page`.
    """
    if page is None:
        return observe(predicate, bound_s)
    target = page

    def pumped() -> T | None:
        pump(target)
        return predicate()

    return observe(pumped, bound_s)


# ----- user-like input only -----------------------------------------------------


def click(locator: Locator) -> None:
    """A real pointer click (Playwright moves the mouse and dispatches events)."""
    locator.click()


def press(page: Page, key: str) -> None:
    page.keyboard.press(key)


def type_text(page: Page, text: str) -> None:
    page.keyboard.type(text)


def tap(locator: Locator) -> None:
    locator.tap()


def hover(locator: Locator) -> None:
    locator.hover()


def visible_roots(page: Page) -> list[str]:
    """Ids of the visible `#page-*` roots (read-only query)."""
    value = page.evaluate(
        "() => [...document.querySelectorAll('[id^=\"page-\"]')]"
        ".filter(e => e.offsetParent !== null || getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0)"
        ".map(e => e.id)"
    )
    return [str(item) for item in value] if isinstance(value, list) else []
