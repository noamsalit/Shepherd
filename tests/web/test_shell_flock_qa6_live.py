"""QA round 6, phase P11 — the shell and the Flock, driven in a real browser.

Three bug candidates from `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md`
§8, each proved at the page: the shipped `index.html` from the real
`ThreadingHTTPServer` on a loopback ephemeral port, the real modules, chromium.

- **BC-11** (U38): a page opened while the daemon is down rendered the Flock's
  "no sessions discovered yet" empty state with `registry: 0 sessions` — a dead
  daemon drawn as an empty fleet. An unanswered read is an unknown, never a zero.
- **BC-19** (U2, U4): once the rail is collapsed no Tab-reachable control
  expands it (`#mark` had no tab stop), and the closed phone drawer's
  off-screen nav items were all in the Tab order.
- **BC-18, Flock half** (U41): every event rebuilt the cards with
  `replaceChildren()`, destroying the focused node. The wait here is a DOM
  signal — a `MutationObserver` on `#flock-cards` — never a request count
  (HI-4: the qa6 clause sampled focus before the rebuild had landed).

Skipped, not failed, where chromium is absent — an environment fact.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from web.conftest import NOW, Client, MasterDoubles
from web.test_shell import render_check_constant

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.store.db import Store
from shepherd.store.models import Session

playwright_api = pytest.importorskip("playwright.sync_api")

VIEWPORTS = {
    name: {"width": width, "height": height}
    for name, width, height in render_check_constant("VIEWPORTS")  # type: ignore[misc]
}
PHONE = VIEWPORTS["phone"]
DESKTOP = VIEWPORTS["desktop"]

#: The sentence the Flock owes a reader when nothing answered (BC-11). Spelled
#: here independently of `flock.js` — the spec for the fix, not a read-back.
FLEET_UNKNOWN = "the fleet is unknown — Shepherd did not answer"

#: Bounded Tab walks: the shell has fewer focusable controls than this on any
#: page, so a walk that has not found its target by then never will.
TAB_BUDGET = 60

#: The id of whatever holds focus, and whether it sits inside the side pane.
FOCUS_PROBE = """() => {
  const node = document.activeElement;
  if (node === null || node === document.body) { return null; }
  return { id: node.id, inPane: node.closest(".pane") !== null };
}"""

#: Resolves once `#flock-cards` has had its children changed — the rebuild's own
#: DOM signal, armed before the event is published so it cannot be missed.
ARM_REBUILD = """() => {
  const host = document.getElementById("flock-cards");
  window.__rebuilt = new Promise((resolve) => {
    const observer = new MutationObserver(() => { observer.disconnect(); resolve(true); });
    observer.observe(host, { childList: true });
  });
}"""


class Browser:
    """One chromium page on the shipped index, closed by `close()`."""

    def __init__(self, client: Client, viewport: dict[str, int], *, refuse_api: bool) -> None:
        from playwright.sync_api import sync_playwright

        self._play = sync_playwright().start()
        try:
            self._browser = self._play.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
            self._play.stop()
            pytest.skip(f"chromium is not available: {exc}")
        self.page = self._browser.new_page(viewport=viewport)
        self.errors: list[str] = []
        self.page.on("pageerror", lambda error: self.errors.append(f"pageerror: {error}"))
        if refuse_api:
            # A stopped daemon: every API call is refused at the socket. Routed
            # before `goto`, so the page's first read is already the refused one.
            self.page.route("**/api/**", lambda route: route.abort("connectionrefused"))
        self.page.goto(f"{client.origin}/")
        # The bootstrap has run once `showPage` revealed the landing root.
        self.page.wait_for_selector("#page-shepherd:not([hidden])", state="attached")

    def close(self) -> None:
        self._browser.close()
        self._play.stop()


def _browser(client: Client, viewport: dict[str, int], *, refuse_api: bool) -> Iterator[Browser]:
    opened = Browser(client, viewport, refuse_api=refuse_api)
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def desktop(client: Client, master_doubles: MasterDoubles) -> Iterator[Browser]:
    yield from _browser(client, DESKTOP, refuse_api=False)


@pytest.fixture()
def phone(client: Client, master_doubles: MasterDoubles) -> Iterator[Browser]:
    yield from _browser(client, PHONE, refuse_api=False)


@pytest.fixture()
def dead_daemon(client: Client, master_doubles: MasterDoubles) -> Iterator[Browser]:
    yield from _browser(client, DESKTOP, refuse_api=True)


def _tab_walk(page: object, budget: int = TAB_BUDGET) -> list[dict[str, object]]:
    """Every stop one full Tab cycle through the document lands on.

    Chromium keeps its sequential-navigation starting point wherever focus last
    was, so a walk cannot simply "start at the top". It walks until focus has
    left the document twice — once to finish the partial lap it started in, once
    to close a full one — which visits every tab stop whatever the start.
    """
    stops: list[dict[str, object]] = []
    exits = 0
    for _ in range(budget * 2):
        page.keyboard.press("Tab")  # type: ignore[attr-defined]
        stop = page.evaluate(FOCUS_PROBE)  # type: ignore[attr-defined]
        if stop is None:
            exits += 1
            if exits == 2:
                break
            continue
        stops.append(stop)
    return stops


# ----- BC-11: a dead daemon is not an empty fleet ------------------------------


def test_a_dead_daemon_is_not_an_empty_fleet(dead_daemon: Browser) -> None:
    """U38(b). Every read refused: the Flock says the fleet is unknown.

    The render is waited for by its own outcome — one of the two panels leaves
    `hidden` — so the assertion reads the page after `loadFleet` has drawn.
    """
    page = dead_daemon.page
    page.locator("#nav-fleet").click()
    page.wait_for_function(
        """() => [...document.querySelectorAll("#empty-state, #fleet-unknown")]
                  .some((node) => !node.hidden)"""
    )

    assert not page.locator("#empty-state").is_visible(), "a dead daemon drawn as an empty fleet"
    assert "registry: 0 sessions" not in page.locator("#page-flock").inner_text()
    unknown = page.locator("#fleet-unknown")
    assert unknown.is_visible()
    assert unknown.inner_text().strip() == FLEET_UNKNOWN
    assert [error for error in dead_daemon.errors if "pageerror" in error] == []


def test_an_answering_empty_fleet_still_shows_the_empty_state(desktop: Browser) -> None:
    """F16's other side: a daemon that answered with no sessions is empty, not unknown."""
    page = desktop.page
    page.locator("#nav-fleet").click()
    page.wait_for_selector("#empty-state:not([hidden])")
    assert page.locator("#empty-state").is_visible()
    assert not page.locator("#fleet-unknown").is_visible()
    assert "registry: 0 sessions" in page.locator("#empty-state").inner_text()


# ----- BC-19: the shell by keyboard ---------------------------------------------


def test_the_collapsed_rail_expands_by_keyboard(desktop: Browser) -> None:
    """U2. Collapse the rail; Tab reaches `#mark`; Enter expands, and Space too."""
    page = desktop.page
    shell = page.locator("#shell")

    # Open rail: `#mark` is decoration beside a reachable `#collapse`, no stop.
    assert "mark" not in [stop["id"] for stop in _tab_walk(page)]

    page.locator("#collapse").click()
    assert shell.get_attribute("data-rail") == "collapsed"

    stops = [stop["id"] for stop in _tab_walk(page)]
    assert "mark" in stops, stops
    page.locator("#mark").focus()
    page.keyboard.press("Enter")
    assert shell.get_attribute("data-rail") == "open"

    page.locator("#collapse").click()
    page.locator("#mark").focus()
    page.keyboard.press(" ")
    assert shell.get_attribute("data-rail") == "open"
    assert page.locator("#mark").get_attribute("role") == "button"
    assert page.locator("#mark").get_attribute("aria-label")


def test_the_closed_drawer_takes_no_focus(phone: Browser) -> None:
    """U4, at 390 px. Tab never lands in the closed drawer; open, it is reachable."""
    page = phone.page

    stops = _tab_walk(page)
    assert stops, "the walk found no focusable control at all"
    in_pane = [stop["id"] for stop in stops if stop["inPane"]]
    assert in_pane == [], in_pane

    page.locator("#drawer-open").click()
    page.wait_for_function(
        '() => getComputedStyle(document.querySelector("nav.pane")).visibility === "visible"'
    )
    page.locator("#nav-settings").focus()
    assert page.evaluate(FOCUS_PROBE) == {"id": "nav-settings", "inPane": True}

    # Close it again: once the slide-out has run, it leaves the Tab order again.
    page.locator("#drawer-open").click()
    page.wait_for_function(
        '() => getComputedStyle(document.querySelector("nav.pane")).visibility === "hidden"'
    )
    assert [stop["id"] for stop in _tab_walk(page) if stop["inPane"]] == []


# ----- BC-18 (Flock half): focus survives an event ------------------------------


@pytest.fixture()
def two_sessions(store: Store) -> tuple[Session, Session]:
    """Two running sessions in one project, written before the page opens.

    Requested **ahead of** the browser fixture in each test's arguments, so the
    page's first read already sees both cards.
    """
    workspace = store.create_project(name="qa6-focus", description=None)
    rows = []
    for engine_id in ("eng-focus-a", "eng-focus-b"):
        row = store.register_session(
            engine_session_id=engine_id,
            workspace_id=workspace.id,
            repo_id=None,
            cwd="/root/Shepherd",
            started_at="2026-09-16T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        store.apply_fold_delta(row.id, FoldDelta(state=SessionState.RUNNING, last_event_at=NOW))
        rows.append(row)
    return rows[0], rows[1]


def _publish_state(session: Session) -> None:
    from shepherd.core.clock import utc_now
    from shepherd.core.stream import StreamEvent
    from shepherd.toolsurface.stream import publish

    publish(
        StreamEvent(
            kind="session.state",
            session_id=session.id,
            payload={"state": "needs_you"},
            occurred_at=utc_now(),
        )
    )


def _open_flock_with(page: object, *sessions: Session) -> None:
    page.locator("#nav-fleet").click()  # type: ignore[attr-defined]
    for session in sessions:
        page.wait_for_selector(f'#flock-cards [data-session-id="{session.id}"]')  # type: ignore[attr-defined]


def _change(store: Store, session: Session) -> None:
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=SessionState.NEEDS_YOU,
            needs_you_reason="waiting on a permission prompt",
            last_event_at=NOW,
        ),
    )


def _active_session_id(page: object) -> object:
    return page.evaluate(  # type: ignore[attr-defined]
        "() => document.activeElement && document.activeElement.dataset.sessionId || null"
    )


def test_card_focus_survives_an_event(
    two_sessions: tuple[Session, Session], store: Store, desktop: Browser
) -> None:
    """U41. The focused card's own session changes; focus is on its new card."""
    first, second = two_sessions
    page = desktop.page
    _open_flock_with(page, first, second)

    page.locator(f'#flock-cards [data-session-id="{first.id}"]').focus()
    assert _active_session_id(page) == first.id

    page.evaluate(ARM_REBUILD)
    _change(store, first)
    _publish_state(first)
    assert page.evaluate("() => window.__rebuilt") is True

    assert _active_session_id(page) == first.id
    assert desktop.errors == []


def test_an_unchanged_card_keeps_its_node_across_an_event(
    two_sessions: tuple[Session, Session], store: Store, desktop: Browser
) -> None:
    """The reuse half: a card whose content did not change is the same node."""
    first, second = two_sessions
    page = desktop.page
    _open_flock_with(page, first, second)

    card = page.locator(f'#flock-cards [data-session-id="{second.id}"]')
    card.focus()
    card.evaluate("(node) => { node.__qa6Marker = true; }")

    page.evaluate(ARM_REBUILD)
    _change(store, first)
    _publish_state(first)
    assert page.evaluate("() => window.__rebuilt") is True

    assert _active_session_id(page) == second.id
    assert page.evaluate("() => document.activeElement.__qa6Marker === true") is True
    assert desktop.errors == []
