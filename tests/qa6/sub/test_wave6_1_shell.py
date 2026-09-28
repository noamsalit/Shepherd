"""Wave 6, SUB lane: the shell — U1-U6, U33-U37, U44 — through real input only.

One SUB instance for the module, seeded through the product's front door: a
project `Alpha6` (its own one-commit repo inside this instance's root) holding
one attached session, and two attached sessions in Unassigned. That is enough
for every drill-down this module walks (U35-U37). Every navigation is a
Playwright click, keypress or touchscreen tap; every `evaluate` is a read
(`test_wave6_0_uikit`). Each scenario keeps named screenshots per step and per
viewport in `<run_dir>/ui/<id>/`.

Order is file order: U1 first (the wave-6 stop-if reads it).

**Mutation `w6-PP17-U1-root`** (fixtures/mutations/scenarios/w6_pp17_u1_root.json):
the served stylesheet gains one rule that keeps `#page-queues` displayed, so a
second root is visible after every nav — U1's exactly-one-root clause must go
false. Applied at one input (the `app.css` response), never to the product tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from shepherd.core.stops import PALETTE, Bucket

from ..browser import BrowserSession, PageLog
from ..constants import DESKTOP, PHONE, VIEWPORTS, Breakpoints, load
from ..httpclient import Client
from ..instance import Controld
from ..mutations import active
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import Subscriber, subscribe
from ..verdict import Blocked, Recorder, await_env
from .test_wave6_0_uikit import (
    KANBAN_STUB,
    NAV_ID,
    NAV_TEXT,
    QUEUES_STUB,
    ROOTS,
    UI_BOUND_S,
    UNREACHABLE,
    Attached,
    Shots,
    active as focused,
    add_repo,
    api_since,
    attach,
    box,
    computed,
    create_project,
    dialog_open,
    go,
    is_showing,
    nav_click,
    nav_state,
    new_repo,
    open_app,
    press_tab_until,
    scroll_overflow,
    settle,
    text_of,
    url,
    viewport,
)

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Route

MUTATION_U1 = "w6-PP17-U1-root"
#: The one rule the mutation appends to the served stylesheet.
MUTATION_RULE = "\n#page-queues { display: block !important; }\n"
#: WCAG 2.5.5 / patterns #12 (derived): the plan's touch-target size.
TOUCH_TARGET_PX = 44.0


@dataclass
class Shell:
    controld: Controld
    client: Client
    run: RunContext
    stream: Subscriber
    points: Breakpoints
    alpha: str
    alpha_session: Attached
    unassigned: list[Attached] = field(default_factory=list)

    @property
    def port(self) -> int:
        return self.controld.port


@pytest.fixture(scope="module")
def shell(pool: InstancePool, qa6_run: RunContext) -> Iterator[Shell]:
    controld = pool.ready()
    client = controld.client
    repo = new_repo(controld.root.root, "alpha6")
    alpha = create_project(client, "Alpha6", "the shell module's project")
    add_repo(client, alpha, repo)
    in_alpha = attach(pool, controld, repo, "QA6 shell alpha")
    loose = qa6_run.repos / "loose"
    first = attach(pool, controld, loose, "QA6 shell one")
    second = attach(pool, controld, loose, "QA6 shell two")
    stream = subscribe("U-shell", controld.port)
    try:
        yield Shell(controld=controld, client=client, run=qa6_run, stream=stream, points=load(), alpha=alpha,
                    alpha_session=in_alpha, unassigned=[first, second])
    finally:
        stream.close()


def width_name(width: int) -> str:
    return f"w{width}"


def install_root_mutation(context: BrowserContext, hits: list[str]) -> None:
    """`w6-PP17-U1-root`: serve app.css with one extra rule (the one sabotaged input)."""

    def handler(route: Route) -> None:
        response = route.fetch()
        hits.append(route.request.url)
        route.fulfill(response=response, body=response.text() + MUTATION_RULE)

    context.route("**/static/app.css", handler)


def nav_leaks(page: Page) -> dict[str, object]:
    """O33: nothing in the topbar or the nav lists approvals or needs-you rows."""
    value = page.evaluate(
        "() => { const zones = [...document.querySelectorAll('.topbar, nav.pane')];"
        " return {rows: zones.reduce((n, z) => n + z.querySelectorAll('[data-approval-id], [data-session-id], .approval').length, 0),"
        " text: zones.map(z => z.innerText).join(' | ')}; }"
    )
    return dict(value) if isinstance(value, dict) else {}


def explained_by_events(calls: list[str]) -> list[str]:
    """The re-reads an SSE envelope causes (app.js `refreshAll`), which a nav click does not."""
    refresh = ("GET /api/fleet", "GET /api/fleet/tree", "GET /api/projects")
    return [call for call in calls if not call.startswith(refresh)]


# ----- U1 --------------------------------------------------------------------------------


@scenario("U1")
def test_u1_every_root_by_mouse_exactly_one_visible(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U1")
    hits: list[str] = []
    with browser_session.context("U1", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        if active(MUTATION_U1):
            install_root_mutation(context, hits)
        page = open_app(context, shell.port)
        if active(MUTATION_U1):
            # APPLIED only when the sabotage was actually served (hunter L2): the driver keys on the word.
            applied = "APPLIED" if hits else "NOT APPLIED (app.css was never served through the route)"
            rec.note(f"QA6 MUTATION {MUTATION_U1} {applied}: app.css served {len(hits)} time(s) with "
                     f"{MUTATION_RULE.strip()!r} appended ({hits[:2]})")
        load_calls = api_since(log, 0)
        rec.record("api.control_listener_saw_first_paint_reads", load_calls[:8])
        order = ["shepherd", "flock", "projects", "queues", "kanban", "settings", "shepherd"]
        start = len(log.requests)
        mark = shell.stream.mark()
        for index, name in enumerate(order):
            nav_click(page, name)
            settle(lambda: nav_state(page).current == [NAV_ID[name]] or None)
            state = nav_state(page)
            step = f"{index}_{name}"
            rec.equal(f"ui.one_root_visible.{step}", [f"page-{name}"], state.roots)
            rec.equal(f"ui.aria_current.{step}", [NAV_ID[name]], state.current)
            rec.equal(f"ui.topbar_title.{step}", NAV_TEXT[name], state.title)
            leaks = nav_leaks(page)
            rec.check(f"ui.no_approvals_or_needs_you_in_shell.{step}",
                      leaks.get("rows") == 0 and "needs you" not in str(leaks.get("text", "")).lower(),
                      "no [data-approval-id]/[data-session-id]/.approval and no 'needs you' in .topbar or nav.pane (O33)",
                      leaks)
            if name == "queues":
                rec.equal("ui.queues_stub", QUEUES_STUB, text_of(page.locator("#page-queues .stub p")))
            if name == "kanban":
                rec.equal("ui.kanban_stub", KANBAN_STUB, text_of(page.locator("#page-kanban .stub p")))
            shots(page, f"{index}-{name}")
        calls = api_since(log, start)
        events = shell.stream.since(mark)
        unexplained = explained_by_events(calls) if events else calls
        rec.check("api.no_request_from_a_nav_click", not unexplained,
                  "no /api/* request between the first nav click and the last (re-reads an SSE envelope caused excepted)",
                  {"calls": calls, "sse_frames_in_window": [f.kind for f in events]})
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
        rec.equal("api.master_send_aborts", 0, log.master_send_aborts)
    rec.note(shots.note())
    rec.finish()


# ----- U2 --------------------------------------------------------------------------------


def focus_ring(page: Page) -> dict[str, str]:
    value = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement);"
        " return {outline_style: s.outlineStyle, outline_width: s.outlineWidth, box_shadow: s.boxShadow}; }"
    )
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def ring_visible(ring: dict[str, str]) -> bool:
    outline = ring.get("outline_style", "none") != "none" and ring.get("outline_width", "0px") not in ("0px", "")
    shadow = ring.get("box_shadow", "none") not in ("none", "")
    return outline or shadow


@scenario("U2")
def test_u2_every_root_by_keyboard_and_the_collapsed_rail(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U2")
    with browser_session.context("U2", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, shell.port)
        plan = [("shepherd", "Enter"), ("flock", "Enter"), ("queues", "Enter"),
                ("projects", "Space"), ("kanban", "Space"), ("settings", "Space")]
        for name, key in plan:
            target = NAV_ID[name]
            presses = press_tab_until(page, lambda a: a.get("id") == target)
            if presses is None:
                rec.check(f"ui.tab_reaches.{name}", False, f"Tab reaches #{target}", focused(page))
                continue
            ring = focus_ring(page)
            rec.check(f"ui.focus_indicator.{name}", ring_visible(ring),
                      "computed outline or box-shadow is not none on the focused nav item (derived, WCAG 2.4.7)", ring)
            page.keyboard.press(key)
            settle(lambda: is_showing(page, name) or None)
            state = nav_state(page)
            rec.equal(f"ui.one_root_visible.{name}_by_{key}", [f"page-{name}"], state.roots)
            rec.equal(f"ui.aria_current.{name}_by_{key}", [NAV_ID[name]], state.current)
            rec.equal(f"ui.topbar_title.{name}_by_{key}", NAV_TEXT[name], state.title)
            shots(page, f"key-{name}")
        presses = press_tab_until(page, lambda a: a.get("id") == "collapse")
        if presses is None:
            rec.check("ui.tab_reaches_collapse", False, "Tab reaches #collapse", focused(page))
        else:
            page.keyboard.press("Enter")
            collapsed, _ = settle(lambda: page.locator("#shell").get_attribute("data-rail") == "collapsed" or None)
            rec.check("ui.enter_on_collapse_collapses", bool(collapsed), "#shell[data-rail=collapsed]",
                      page.locator("#shell").get_attribute("data-rail"))
            shots(page, "collapsed")
            # The focused #collapse is the first candidate: Enter on it again.
            tried: list[str] = ["collapse"]
            page.keyboard.press("Enter")
            expanded = page.locator("#shell").get_attribute("data-rail") != "collapsed"
            seen: set[str] = {"collapse|pane-collapse|"}
            for _ in range(0 if expanded else 120):
                page.keyboard.press("Tab")
                now = focused(page)
                key_of = f"{now.get('id')}|{now.get('cls')}|{now.get('text')}"
                if now.get("in_pane") != "yes" or "nav-item" in now.get("cls", "") or key_of in seen:
                    if key_of in seen and now.get("in_pane") == "yes":
                        break
                    continue
                seen.add(key_of)
                tried.append(now.get("id") or now.get("cls", "?"))
                page.keyboard.press("Enter")
                if page.locator("#shell").get_attribute("data-rail") != "collapsed":
                    expanded = True
                    break
            rec.check("ui.a_focusable_control_expands_the_rail", expanded,
                      "some control reachable by Tab expands the collapsed rail with Enter (derived, WCAG 2.1.1)",
                      {"tried_in_the_rail": tried, "mark_focusable": page.locator("#mark").evaluate("e => e.tabIndex")})
            shots(page, "after-expand-attempt")
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U3 --------------------------------------------------------------------------------


def hit_testable(page: Page) -> dict[str, bool]:
    value = page.evaluate(
        "() => Object.fromEntries([...document.querySelectorAll('.nav-item')].map(e => {"
        " const r = e.getBoundingClientRect(); const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);"
        " return [e.id, !!hit && e.contains(hit)]; }))"
    )
    return {str(k): bool(v) for k, v in value.items()} if isinstance(value, dict) else {}


@scenario("U3")
def test_u3_collapse_and_expand_the_rail_by_mouse(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U3")
    with browser_session.context("U3", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, shell.port)
        page.locator("#collapse").click()
        settle(lambda: page.locator("#shell").get_attribute("data-rail") == "collapsed" or None)
        rec.equal("ui.rail_collapsed", "collapsed", page.locator("#shell").get_attribute("data-rail"))
        shots(page, "collapsed")
        hits = hit_testable(page)
        rec.check("ui.each_nav_item_hit_testable_collapsed", len(hits) == 6 and all(hits.values()),
                  "the element at each nav item's centre is that item (6 of 6)", hits)
        nav_click(page, "projects")
        shown, _ = settle(lambda: is_showing(page, "projects") or None)
        rec.check("ui.projects_shows_collapsed", bool(shown), "Projects is the one visible root", nav_state(page).as_json())
        shots(page, "projects-collapsed")
        page.locator("#mark").click()
        opened, _ = settle(lambda: page.locator("#shell").get_attribute("data-rail") == "open" or None)
        rec.check("ui.mark_expands", bool(opened), "#shell[data-rail=open] after clicking #mark",
                  page.locator("#shell").get_attribute("data-rail"))
        shots(page, "expanded")
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U4 --------------------------------------------------------------------------------


def pane_box(page: Page) -> dict[str, float] | None:
    return box(page.locator("nav.pane"))


@scenario("U4")
def test_u4_the_phone_drawer_by_touch(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U4")
    with browser_session.context("U4", viewport=VIEWPORTS[PHONE], has_touch=True, is_mobile=True) as (context, log):
        page = open_app(context, shell.port)
        width, _height = viewport(page)
        shots(page, "0-closed")
        page.locator("#drawer-open").tap()
        inside, _ = settle(lambda: (b := pane_box(page)) is not None and b["x"] >= 0 and b["x"] + b["width"] <= width
                           and page.locator("#shell").get_attribute("data-drawer") == "open" or None)
        rec.check("ui.drawer_open_nav_in_viewport", bool(inside), "#shell[data-drawer=open] and the nav inside the viewport",
                  {"drawer": page.locator("#shell").get_attribute("data-drawer"), "pane": pane_box(page)})
        shots(page, "1-open")
        page.locator("#nav-projects").tap()
        shown, _ = settle(lambda: is_showing(page, "projects") and page.locator("#shell").get_attribute("data-drawer") is None or None)
        rec.check("ui.tap_projects_shows_and_closes", bool(shown), "Projects showing and the drawer closed",
                  {"nav": nav_state(page).as_json(), "drawer": page.locator("#shell").get_attribute("data-drawer")})
        shots(page, "2-projects")
        page.locator("#drawer-open").tap()
        settle(lambda: page.locator("#shell").get_attribute("data-drawer") == "open" or None)
        page.keyboard.press("Escape")
        after_escape, _ = settle(lambda: page.locator("#shell").get_attribute("data-drawer") is None or None, 1.0)
        rec.record("ui.drawer_after_escape", page.locator("#shell").get_attribute("data-drawer") or "closed")
        shots(page, "3-after-escape")
        if not after_escape:
            # The open pane covers the toggle (web-ui §2 item 7): a nav tap is the way out.
            page.locator("#nav-projects").tap()
        closed, _ = settle(lambda: page.locator("#shell").get_attribute("data-drawer") is None
                           and (b := pane_box(page)) is not None and b["x"] + b["width"] <= 0 or None)
        if not closed:
            rec.block("ui.drawer_closed_before_tab", f"the drawer did not close: {pane_box(page)}")
        else:
            offscreen: list[str] = []
            for _ in range(14):
                page.keyboard.press("Tab")
                now = focused(page)
                if now.get("in_pane") == "yes" and float(now.get("right", "1")) <= 0:
                    offscreen.append(now.get("id") or now.get("cls", "?"))
            rec.check("ui.no_offscreen_nav_item_takes_focus", not offscreen,
                      "with the drawer closed, no off-screen nav item receives focus (derived, WCAG 2.4.3)", offscreen)
            shots(page, "4-tabbed-closed")
        rec.record("ui.scrim_present", page.locator(".scrim").count())
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U5 --------------------------------------------------------------------------------


@scenario("U5")
def test_u5_an_error_message_shows_and_can_be_dismissed(shell: Shell, browser_session: BrowserSession,
                                                        pool: InstancePool, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U5")
    aborted: list[str] = []
    with browser_session.context("U5", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=False)

        def abort_fleet(route: Route) -> None:
            aborted.append(route.request.url)
            route.abort()

        def is_fleet(address: str) -> bool:
            return address.split("?")[0].endswith("/api/fleet")

        page.route(is_fleet, abort_fleet, times=1)
        # The SSE event: a sidecar change (a new session registers), so the page re-reads.
        shell.unassigned.append(attach(pool, shell.controld, shell.run.repos / "loose", "QA6 shell three"))
        shown, elapsed = settle(lambda: page.locator("#stream-message").is_visible() or None)
        text = text_of(page.locator("#stream-message-text"))
        rec.check("ui.message_shown", bool(shown), "#stream-message visible after the aborted read", text)
        rec.equal("ui.message_text", UNREACHABLE, text)
        rec.check("api.aborted_request_recorded", len(aborted) == 1, "one /api/fleet aborted by the route", aborted)
        shots(page, "shown")
        page.locator("#stream-message-dismiss").click()
        hidden, _ = settle(lambda: not page.locator("#stream-message").is_visible() or None)
        rec.check("ui.dismiss_hides", bool(hidden), "#stream-message hidden after the dismiss click",
                  page.locator("#stream-message").get_attribute("hidden"))
        shots(page, "dismissed")
        page.unroute(is_fleet)
        rec.equal("logs.page_errors", [], log.page_errors)
        rec.record("logs.console_errors_from_the_fault", [e["text"][:120] for e in log.console_errors()])
        rec.record("ui.message_latency_s", round(elapsed, 3))
    rec.note(shots.note())
    rec.finish()


# ----- U6 --------------------------------------------------------------------------------


def tip(page: Page) -> dict[str, str | int]:
    tips = page.locator(".tip[role=tooltip]")
    count = tips.count()
    if count != 1:
        return {"count": count}
    return {
        "count": 1,
        "label": (tips.locator(".tip-label").text_content() or "").strip(),
        "acts": (tips.locator(".tip-who").text_content() or "").strip(),
    }


def expected_tip(bucket: str) -> dict[str, str | int]:
    style = PALETTE[Bucket(bucket)]
    return {"count": 1, "label": style.label, "acts": f"acts: {style.who_acts}"}


def sheet_rows(page: Page) -> list[tuple[str, str]]:
    value = page.evaluate(
        "() => [...document.querySelectorAll('#dlg-legend-list .sheet-row')].map(r => ["
        " (r.querySelector('.sheet-glyph') || {}).textContent || '', (r.querySelector('.sheet-label') || {}).textContent || ''])"
    )
    return [(str(row[0]), str(row[1])) for row in value] if isinstance(value, list) else []


def expected_rows() -> list[tuple[str, str]]:
    order = ("needs_you", "error", "unfinished", "running", "paused", "blocked", "finished", "unclassified")
    return [(PALETTE[Bucket(b)].glyph, PALETTE[Bucket(b)].label) for b in order]


def close_legend(page: Page, how: str) -> None:
    if how == "button":
        page.locator("#dlg-legend .sheet-close").click()
    elif how == "escape":
        page.keyboard.press("Escape")
    else:
        dialog = box(page.locator("#dlg-legend"))
        width, height = viewport(page)
        if dialog is None:
            raise Blocked("the legend dialog has no box to click outside of")
        # A point on the backdrop: left of the dialog box, level with the viewport's middle.
        x = max(2.0, dialog["x"] / 2) if dialog["x"] > 4 else width - 2.0
        page.mouse.click(x, height / 2)


@scenario("U6")
def test_u6_the_legend_by_hover_focus_click_every_opener_and_closer(shell: Shell, browser_session: BrowserSession,
                                                                    rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U6")
    with browser_session.context("U6", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=False)
        keys = page.locator(".legend-key[data-bucket]")
        buckets = [str(keys.nth(i).get_attribute("data-bucket")) for i in range(keys.count())]
        rec.equal("ui.eight_legend_keys", ["needs_you", "error", "unfinished", "running", "paused", "blocked",
                                           "finished", "unclassified"], buckets)
        width, height = viewport(page)
        for bucket in buckets:
            page.locator(f".legend-key[data-bucket={bucket}]").hover()
            seen, _ = settle(lambda: tip(page).get("count") == 1 or None, 2.0)
            rec.equal(f"ui.hover_tip.{bucket}", expected_tip(bucket), tip(page))
            page.mouse.move(width - 4, height - 4)
            gone, _ = settle(lambda: page.locator(".tip").count() == 0 or None, 2.0)
            rec.check(f"ui.hover_tip_leaves.{bucket}", bool(gone), "no .tip after the pointer leaves", page.locator(".tip").count())
        shots(page, "hover-last")
        first = press_tab_until(page, lambda a: a.get("bucket") == buckets[0], limit=40)
        if first is None:
            rec.check("ui.tab_reaches_the_legend", False, "Tab reaches the first legend key", focused(page))
        else:
            for index, bucket in enumerate(buckets):
                if index:
                    page.keyboard.press("Tab")
                now = focused(page)
                rec.equal(f"ui.focus_on.{bucket}", bucket, now.get("bucket"))
                rec.equal(f"ui.focus_tip.{bucket}", expected_tip(bucket), tip(page))
            shots(page, "focus-last")
        for bucket in buckets:
            page.locator(f".legend-key[data-bucket={bucket}]").click()
            opened, _ = settle(lambda: dialog_open(page, "#dlg-legend") or None, 3.0)
            rec.check(f"ui.click_opens_sheet.{bucket}", bool(opened), "#dlg-legend open", dialog_open(page, "#dlg-legend"))
            rec.equal(f"ui.sheet_rows.{bucket}", expected_rows(), sheet_rows(page))
            page.keyboard.press("Escape")
            settle(lambda: not dialog_open(page, "#dlg-legend") or None, 3.0)
        openers = {"key": ".legend-key[data-bucket=needs_you]", "info": ".legend-info"}
        for opener_name, selector in openers.items():
            for closer in ("button", "escape", "outside"):
                page.locator(selector).click()
                opened, _ = settle(lambda: dialog_open(page, "#dlg-legend") or None, 3.0)
                if not opened:
                    rec.check(f"ui.{opener_name}_opens", False, "#dlg-legend open", False)
                    continue
                shots(page, f"open-{opener_name}-{closer}")
                close_legend(page, closer)
                closed, _ = settle(lambda: not dialog_open(page, "#dlg-legend") or None, 3.0)
                rec.check(f"ui.close.{opener_name}.{closer}", bool(closed), "dialog.open false", dialog_open(page, "#dlg-legend"))
                now = focused(page)
                back_on = (now.get("bucket") == "needs_you") if opener_name == "key" else ("legend-info" in now.get("cls", ""))
                rec.check(f"ui.focus_returns.{opener_name}.{closer}", back_on,
                          f"focus back on the opener {selector} (derived)", now)
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    with browser_session.context("U6-phone", viewport=VIEWPORTS[PHONE], has_touch=True, is_mobile=True) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=True, touch=True)
        page.locator(".legend-info").tap()
        opened, _ = settle(lambda: dialog_open(page, "#dlg-legend") or None, 3.0)
        width, height = viewport(page)
        sheet, _ = settle(lambda: (b := box(page.locator("#dlg-legend"))) is not None
                          and abs(b["y"] + b["height"] - height) <= 1.0 or None, 2.0)
        rec.check("ui.phone_sheet_bottom_is_viewport_bottom", bool(opened) and bool(sheet),
                  f"the sheet's bottom edge equals the viewport's ({height}px)", box(page.locator("#dlg-legend")))
        shots(page, "phone-sheet")
        page.locator("#dlg-legend .sheet-close").tap()
        rec.equal("logs.phone_console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U33 -------------------------------------------------------------------------------


@scenario("U33")
def test_u33_with_javascript_off_the_page_claims_nothing_false(shell: Shell, browser_session: BrowserSession,
                                                               rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U33")
    with browser_session.context("U33", viewport=VIEWPORTS[DESKTOP], java_script_enabled=False) as (context, log):
        page = context.new_page()
        page.goto(url(shell.port), wait_until="load")
        rec.equal("ui.no_noscript", 0, page.locator("noscript").count())
        roots_before = [rid for rid in (f"page-{name}" for name in ROOTS) if page.locator(f"#{rid}").is_visible()]
        rec.record("ui.visible_root_js_off", roots_before)
        title_before = text_of(page.locator("#topbar-title"))
        shots(page, "loaded")
        page.locator("#nav-projects").click()
        roots_after = [rid for rid in (f"page-{name}" for name in ROOTS) if page.locator(f"#{rid}").is_visible()]
        rec.equal("ui.click_changes_nothing", (roots_before, title_before), (roots_after, text_of(page.locator("#topbar-title"))))
        status = text_of(page.locator("#stream-status"))
        rec.check("ui.stream_status_not_live", status != "live", "#stream-status does not read 'live' (PP-12)", status)
        shots(page, "after-click")
        rec.equal("api.no_api_request", [], api_since(log, 0))
        rec.record("api.every_request", [f"{e['method']} {e['url']}" for e in log.requests])
    rec.note(shots.note())
    rec.finish()


# ----- U34 -------------------------------------------------------------------------------


def undersized_controls(page: Page) -> list[dict[str, object]]:
    value = page.evaluate(
        "(min) => [...document.querySelectorAll('button, a[href], input, textarea, select, summary, [tabindex]:not([tabindex=\"-1\"])')]"
        ".filter(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);"
        " return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && r.right > 0 && r.bottom > 0"
        " && r.left < innerWidth && r.top < innerHeight; })"
        ".map(e => { const r = e.getBoundingClientRect(); return {el: e.id || e.getAttribute('aria-label') || e.className || e.tagName,"
        " w: Math.round(r.width), h: Math.round(r.height)}; }).filter(c => c.w < min || c.h < min)",
        TOUCH_TARGET_PX,
    )
    return [dict(item) for item in value] if isinstance(value, list) else []


def console_since(log: PageLog, start: int) -> list[str]:
    return [entry["text"][:160] for entry in log.console[start:] if entry["type"] == "error"]


@scenario("U34")
def test_u34_every_root_at_four_widths(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U34")
    points = shell.points
    widths = (VIEWPORTS[PHONE], VIEWPORTS[width_name(points.sheet)], VIEWPORTS[width_name(points.sheet + 1)], VIEWPORTS[DESKTOP])
    for size in widths:
        width = size[0]
        phone = size == VIEWPORTS[PHONE]
        drawer = width <= points.shell
        with browser_session.context(f"U34-{width}", viewport=size, has_touch=phone, is_mobile=phone) as (context, log):
            page = open_app(context, shell.port)
            for name in ROOTS:
                start = len(log.console)
                go(page, name, drawer=drawer, touch=phone)
                if drawer:
                    settle(lambda: (b := box(page.locator("nav.pane"))) is not None and b["x"] + b["width"] <= 0 or None)
                cell = f"w{width}.{name}"
                scroll, inner = scroll_overflow(page)
                rec.check(f"ui.no_sideways_scroll.{cell}", scroll <= inner, "scrollWidth <= innerWidth", (scroll, inner))
                rec.equal(f"ui.one_root.{cell}", [f"page-{name}"], nav_state(page).roots)
                if phone:
                    rec.record(f"ui.touch_targets_under_44.{cell}", undersized_controls(page))
                rec.equal(f"logs.console_errors.{cell}", [], console_since(log, start))
                shots(page, f"w{width}-{name}")
            if width in (points.sheet, points.sheet + 1):
                go(page, "flock", drawer=drawer)
                page.locator(".legend-info").click()
                settle(lambda: dialog_open(page, "#dlg-legend") or None, 3.0)
                vw, vh = viewport(page)
                sheet = box(page.locator("#dlg-legend"))
                is_sheet = sheet is not None and abs(sheet["width"] - vw) <= 1.0 and abs(sheet["y"] + sheet["height"] - vh) <= 1.0
                if width == points.sheet:
                    rec.check(f"ui.legend_is_bottom_sheet.w{width}", is_sheet, f"box width {vw} and bottom {vh}", sheet)
                else:
                    rec.check(f"ui.legend_is_centred_dialog.w{width}", not is_sheet, "not the full-width bottom sheet", sheet)
                shots(page, f"w{width}-legend")
                page.keyboard.press("Escape")
            rec.equal(f"logs.page_errors.w{width}", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U35 -------------------------------------------------------------------------------


def shell_layout(page: Page) -> dict[str, object]:
    vw, _vh = viewport(page)
    rail = box(page.locator("nav.pane"))
    main = box(page.locator(".main"))
    return {"viewport": vw, "rail": rail, "main": main, "drawer_open_visible": page.locator("#drawer-open").is_visible()}


def drawer_closed_offcanvas(layout: dict[str, object]) -> bool:
    rail = layout.get("rail")
    main = layout.get("main")
    vw = layout.get("viewport")
    return (isinstance(rail, dict) and isinstance(main, dict) and isinstance(vw, int)
            and layout.get("drawer_open_visible") is True and rail["x"] + rail["width"] <= 0
            and main["width"] >= vw - 1)


def rail_inline(layout: dict[str, object]) -> bool:
    rail = layout.get("rail")
    main = layout.get("main")
    vw = layout.get("viewport")
    return (isinstance(rail, dict) and isinstance(main, dict) and isinstance(vw, int)
            and layout.get("drawer_open_visible") is False and rail["x"] >= 0 and rail["x"] + rail["width"] <= vw
            and main["x"] >= rail["x"] + rail["width"] - 1)


def visible(page: Page, selector: str) -> bool:
    return page.locator(selector).first.is_visible()


@scenario("U35")
def test_u35_the_760_761_breakpoint(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U35")
    points = shell.points
    for width in (points.shell, points.shell + 1):
        narrow = width == points.shell
        tag = f"w{width}"
        with browser_session.context(f"U35-{width}", viewport=VIEWPORTS[width_name(width)]) as (context, log):
            page = open_app(context, shell.port)
            for name in ROOTS:
                go(page, name, drawer=narrow)
                if narrow:
                    settle(lambda: drawer_closed_offcanvas(shell_layout(page)) or None)
                    layout = shell_layout(page)
                    rec.check(f"ui.shell_drawer_mode.{tag}.{name}", drawer_closed_offcanvas(layout),
                              "#drawer-open visible, the rail off-canvas (right <= 0), the main column the viewport's width", layout)
                else:
                    layout = shell_layout(page)
                    rec.check(f"ui.shell_inline_mode.{tag}.{name}", rail_inline(layout),
                              "#drawer-open not displayed, the rail inline, the main column beside it", layout)
                shots(page, f"{tag}-{name}")
            go(page, "shepherd", drawer=narrow)
            page.locator("#shepherd-input").click()
            page.keyboard.type(f"QA6 bubble {width}")
            page.keyboard.press("Enter")
            bubble = page.locator("#shepherd-thread .bubble").last
            await_env(lambda: bubble.count() > 0 or None, UI_BOUND_S, "the sent bubble rendered")
            max_width = computed(bubble, "max-width")
            if narrow:
                rec.equal(f"ui.bubble_max_width_92.{tag}", "92%", max_width)
            else:
                rec.check(f"ui.bubble_max_width_not_92.{tag}", max_width != "92%", "not 92%", max_width)
            settle(lambda: log.master_send_aborts >= 1 or None, 3.0, page)
            rec.equal(f"api.master_send_aborts.{tag}", 1, log.master_send_aborts)
            shots(page, f"{tag}-bubble")
            go(page, "projects", drawer=narrow)
            row = page.locator(f"#proj-list .proj-row[data-project-id='{shell.alpha}']")
            row.click()
            await_env(lambda: page.locator("#proj-detail .proj-title").count() > 0 or None, UI_BOUND_S, "the project detail painted")
            if narrow:
                one_pane = not visible(page, "#proj-list") and visible(page, "#proj-detail") and visible(page, "#proj-detail .back")
                rec.check(f"ui.projects_one_pane.{tag}", one_pane, "detail alone, with .back", {
                    "list": visible(page, "#proj-list"), "detail": visible(page, "#proj-detail"),
                    "back": visible(page, "#proj-detail .back")})
                shots(page, f"{tag}-projects-detail")
                page.locator("#proj-detail .back").click()
                back, _ = settle(lambda: visible(page, "#proj-list") and not visible(page, "#proj-detail") or None)
                kept = page.locator(f"#proj-list .proj-row[data-project-id='{shell.alpha}']").get_attribute("aria-current")
                rec.check(f"ui.projects_back_keeps_selection.{tag}", bool(back) and kept == "true",
                          "the list again, the row still aria-current", {"back": bool(back), "aria_current": kept})
            else:
                side = visible(page, "#proj-list") and visible(page, "#proj-detail") and not visible(page, "#proj-detail .back")
                rec.check(f"ui.projects_two_panes.{tag}", side, "list and detail side by side, no back control", {
                    "list": visible(page, "#proj-list"), "detail": visible(page, "#proj-detail"),
                    "back": visible(page, "#proj-detail .back")})
                shots(page, f"{tag}-projects")
            go(page, "settings", drawer=narrow)
            page.locator("#settings-nav .set-item", has_text="Autonomy").click()
            await_env(lambda: "Autonomy" in (page.locator("#settings-panel .col-head").text_content() or "") or None, UI_BOUND_S,
                      "the Autonomy panel")
            if narrow:
                one_pane = not visible(page, "#settings-nav") and visible(page, "#settings-panel") and visible(page, "#settings-back")
                rec.check(f"ui.settings_one_pane.{tag}", one_pane, "panel alone, with #settings-back", {
                    "nav": visible(page, "#settings-nav"), "panel": visible(page, "#settings-panel"),
                    "back": visible(page, "#settings-back")})
                shots(page, f"{tag}-settings-detail")
                page.locator("#settings-back").click()
                back, _ = settle(lambda: visible(page, "#settings-nav") and not visible(page, "#settings-panel") or None)
                kept = page.locator("#settings-nav .set-item", has_text="Autonomy").get_attribute("aria-current")
                rec.check(f"ui.settings_back_keeps_selection.{tag}", bool(back) and kept == "true",
                          "the nav again, Autonomy still aria-current", {"back": bool(back), "aria_current": kept})
                go(page, "flock", drawer=True)
                page.locator("#flock-projects .project[data-project-id=unassigned]").click()
                level, _ = settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "sessions" or None)
                sessions_only = visible(page, ".col-sessions") and not visible(page, ".col-projects") and not visible(page, "#flock-detail")
                rec.check(f"ui.flock_drill_sessions.{tag}", bool(level) and sessions_only, "only the sessions column",
                          page.locator("#page-flock").get_attribute("data-level"))
                page.locator("#flock-cards .card").first.click()
                level, _ = settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "detail" or None)
                detail_only = visible(page, "#flock-detail") and not visible(page, ".col-sessions")
                rec.check(f"ui.flock_drill_detail.{tag}", bool(level) and detail_only, "only the detail column",
                          page.locator("#page-flock").get_attribute("data-level"))
                shots(page, f"{tag}-flock-detail")
            else:
                side = visible(page, "#settings-nav") and visible(page, "#settings-panel") and not visible(page, "#settings-back")
                rec.check(f"ui.settings_two_panes.{tag}", side, "nav and panel side by side, no back control", {
                    "nav": visible(page, "#settings-nav"), "panel": visible(page, "#settings-panel"),
                    "back": visible(page, "#settings-back")})
                shots(page, f"{tag}-settings")
            rec.equal(f"logs.console_errors.{tag}", [], [e for e in log.console_errors() if "net::ERR_FAILED" not in e["text"]])
            rec.equal(f"logs.page_errors.{tag}", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U36 -------------------------------------------------------------------------------


def columns(page: Page) -> dict[str, bool]:
    return {"projects": visible(page, ".col-projects"), "sessions": visible(page, ".col-sessions"),
            "detail": visible(page, "#flock-detail")}


@scenario("U36")
def test_u36_the_900_901_breakpoint_on_the_flock(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U36")
    herd = shell.points.herd
    with browser_session.context("U36-900", viewport=VIEWPORTS[width_name(herd)]) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=False)
        rec.equal("ui.w900.start_projects_level", {"projects": True, "sessions": False, "detail": False}, columns(page))
        page.locator("#flock-projects .project[data-project-id=unassigned]").click()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "sessions" or None)
        rec.equal("ui.w900.sessions_level", {"projects": False, "sessions": True, "detail": False}, columns(page))
        shots(page, "w900-sessions")
        page.locator("#flock-cards .card").first.click()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "detail" or None)
        rec.equal("ui.w900.detail_level", {"projects": False, "sessions": False, "detail": True}, columns(page))
        shots(page, "w900-detail")
        page.locator("#flock-detail .back[data-level=sessions]").click()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "sessions" or None)
        rec.equal("ui.w900.detail_back_goes_to_sessions", {"projects": False, "sessions": True, "detail": False}, columns(page))
        page.locator(".col-sessions .back[data-level=projects]").click()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "projects" or None)
        rec.equal("ui.w900.sessions_back_goes_to_projects", {"projects": True, "sessions": False, "detail": False}, columns(page))
        shots(page, "w900-projects")
        rec.equal("logs.w900.console_errors", [], log.console_errors())
    with browser_session.context("U36-901", viewport=VIEWPORTS[width_name(herd + 1)]) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=False)
        page.locator("#flock-projects .project[data-project-id=unassigned]").click()
        cards = page.locator("#flock-cards .card")
        await_env(lambda: cards.count() >= 2 or None, UI_BOUND_S, "two Unassigned cards")
        first_id = str(cards.nth(0).get_attribute("data-session-id"))
        second_id = str(cards.nth(1).get_attribute("data-session-id"))
        cards.nth(0).click()
        settle(lambda: page.locator(f"#flock-cards .card[data-session-id='{first_id}']").get_attribute("aria-current") == "true" or None)
        rec.equal("ui.w901.three_panes", {"projects": True, "sessions": True, "detail": True}, columns(page))
        title_first = text_of(page.locator("#session-title"))
        shots(page, "w901-first")
        page.locator(f"#flock-cards .card[data-session-id='{second_id}']").click()
        settle(lambda: page.locator(f"#flock-cards .card[data-session-id='{second_id}']").get_attribute("aria-current") == "true" or None)
        current = page.evaluate("() => [...document.querySelectorAll('#flock-cards .card')]"
                                ".filter(c => c.getAttribute('aria-current') === 'true').map(c => c.dataset.sessionId)")
        rec.equal("ui.w901.only_the_second_card_current", [second_id], current)
        second_api = shell.client.session(second_id).get("session")
        second_title = second_api.get("title") if isinstance(second_api, dict) else None
        rec.equal("ui.w901.third_pane_shows_the_second", second_title, text_of(page.locator("#session-title")))
        rec.check("ui.w901.third_pane_changed", text_of(page.locator("#session-title")) != title_first,
                  "the title differs from the first session's", title_first)
        rec.equal("ui.w901.still_three_panes", {"projects": True, "sessions": True, "detail": True}, columns(page))
        shots(page, "w901-second")
        rec.equal("logs.w901.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U37 -------------------------------------------------------------------------------


@scenario("U37")
def test_u37_phone_drill_down_on_every_page_by_touch(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U37")
    with browser_session.context("U37", viewport=VIEWPORTS[PHONE], has_touch=True, is_mobile=True) as (context, log):
        page = open_app(context, shell.port)
        go(page, "flock", drawer=True, touch=True)
        rec.equal("ui.flock.level_projects", {"projects": True, "sessions": False, "detail": False}, columns(page))
        page.locator("#flock-projects .project[data-project-id=unassigned]").tap()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "sessions" or None)
        rec.equal("ui.flock.level_sessions", {"projects": False, "sessions": True, "detail": False}, columns(page))
        shots(page, "flock-sessions")
        card = page.locator("#flock-cards .card").first
        card_id = str(card.get_attribute("data-session-id"))
        card.tap()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "detail" or None)
        rec.equal("ui.flock.level_detail", {"projects": False, "sessions": False, "detail": True}, columns(page))
        shots(page, "flock-detail")
        page.locator("#flock-detail .back[data-level=sessions]").tap()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "sessions" or None)
        rec.equal("ui.flock.back_to_sessions", {"projects": False, "sessions": True, "detail": False}, columns(page))
        rec.equal("ui.flock.card_selection_kept", "true",
                  page.locator(f"#flock-cards .card[data-session-id='{card_id}']").get_attribute("aria-current"))
        page.locator(".col-sessions .back[data-level=projects]").tap()
        settle(lambda: page.locator("#page-flock").get_attribute("data-level") == "projects" or None)
        rec.equal("ui.flock.back_to_projects", {"projects": True, "sessions": False, "detail": False}, columns(page))
        rec.equal("ui.flock.project_selection_kept", "true",
                  page.locator("#flock-projects .project[data-project-id=unassigned]").get_attribute("aria-current"))
        shots(page, "flock-back")
        go(page, "projects", drawer=True, touch=True)
        page.locator(f"#proj-list .proj-row[data-project-id='{shell.alpha}']").tap()
        await_env(lambda: page.locator("#proj-detail .proj-title").count() > 0 or None, UI_BOUND_S, "the project detail")
        rec.check("ui.projects.detail_alone", not visible(page, "#proj-list") and visible(page, "#proj-detail"),
                  "detail alone", {"list": visible(page, "#proj-list"), "detail": visible(page, "#proj-detail")})
        shots(page, "projects-detail")
        page.locator("#proj-detail .back").tap()
        settle(lambda: visible(page, "#proj-list") or None)
        rec.check("ui.projects.back_to_list", visible(page, "#proj-list") and not visible(page, "#proj-detail"),
                  "the list alone", {"list": visible(page, "#proj-list"), "detail": visible(page, "#proj-detail")})
        rec.equal("ui.projects.selection_kept", "true",
                  page.locator(f"#proj-list .proj-row[data-project-id='{shell.alpha}']").get_attribute("aria-current"))
        go(page, "settings", drawer=True, touch=True)
        page.locator("#settings-nav .set-item", has_text="Autonomy").tap()
        settle(lambda: visible(page, "#settings-panel") and not visible(page, "#settings-nav") or None)
        rec.check("ui.settings.panel_alone", visible(page, "#settings-panel") and not visible(page, "#settings-nav"),
                  "the panel alone", {"nav": visible(page, "#settings-nav"), "panel": visible(page, "#settings-panel")})
        shots(page, "settings-detail")
        page.locator("#settings-back").tap()
        settle(lambda: visible(page, "#settings-nav") or None)
        rec.check("ui.settings.back_to_nav", visible(page, "#settings-nav") and not visible(page, "#settings-panel"),
                  "the nav alone", {"nav": visible(page, "#settings-nav"), "panel": visible(page, "#settings-panel")})
        rec.equal("ui.settings.selection_kept", "true",
                  page.locator("#settings-nav .set-item", has_text="Autonomy").get_attribute("aria-current"))
        shots(page, "settings-back")
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U44 -------------------------------------------------------------------------------


@scenario("U44")
def test_u44_dark_only_whatever_the_os_asks_for(shell: Shell, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U44")
    seen: dict[str, dict[str, str]] = {}
    for scheme in ("light", "dark"):
        with browser_session.context(f"U44-{scheme}", viewport=VIEWPORTS[DESKTOP], color_scheme=scheme) as (context, log):
            page = open_app(context, shell.port)
            matched = page.evaluate(f"() => matchMedia('(prefers-color-scheme: {scheme})').matches")
            rec.check(f"given.emulated_{scheme}", matched is True, f"prefers-color-scheme: {scheme} matches", matched)
            seen[scheme] = {}
            for name in ROOTS:
                go(page, name, drawer=False)
                seen[scheme][name] = computed(page.locator("body"), "background-color")
                shots(page, f"{scheme}-{name}")
    for name in ROOTS:
        rec.equal(f"ui.body_background_same.{name}", seen.get("dark", {}).get(name), seen.get("light", {}).get(name))
    rec.record("ui.body_backgrounds", seen)
    rec.note(shots.note())
    rec.finish()

