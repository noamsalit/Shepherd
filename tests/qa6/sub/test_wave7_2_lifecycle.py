"""Wave 7, SUB lane: the daemon's lifecycle as a page sees it — U38 (stopped), U39
(restarted on the same port).

Each scenario owns its instances and stops them itself (SIGTERM to the recorded
`Popen` pid only). **U38 installs no `/api/master/send` abort route** (env-plan
§2): the daemon is down, no master can start, and an aborted route would fake
the very network failure U38 observes. U38(b) installs the fetch shim with
`add_init_script` before the page's scripts run (labelled: network timing only).

U38's 31 s and U39's 30 s re-live bound are the plan's named observation
windows (BUILDING.md §2); nothing else here sleeps.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from .. import fetchshim
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..instance import RestartFailed, wait_restart_ready
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import CONTROL_MULTIPLE, Blocked, Recorder, await_env
from .test_wave6_0_uikit import (
    SETTINGS_UNREACHABLE,
    UI_BOUND_S,
    UNREACHABLE,
    Shots,
    attach,
    dialog_open,
    go,
    open_app,
    settle,
    text_of,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

#: The feature map's declared oracle: not `live` after > 2 x keep-alive (2 x 15 s).
STOPPED_WINDOW_S = 31.0
RELIVE_BOUND_S = 30.0
AFTER_RESTART_BOUND_S = 10.0
ASK = "Ask me before anything leaves this machine"
AUTO = "Approve automatically"


def create_through_dialog(page: Page, name: str) -> None:
    page.locator("#proj-new").click()
    await_env(lambda: dialog_open(page, "#dlg-project") or None, UI_BOUND_S, "the project dialog")
    page.locator("#p-name").click()
    page.keyboard.type(name)
    page.locator("#p-save").click()


# ----- U38 -------------------------------------------------------------------------------


@scenario("U38")
def test_u38_a_stopped_daemon_is_never_shown_as_live_or_as_an_empty_fleet(pool: InstancePool, qa6_run: RunContext,
                                                                          browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U38")
    first = pool.ready()
    attach(pool, first, qa6_run.repos / "loose", "QA6 U38 session", state="running")
    with browser_session.context("U38-a", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, first.port)
        shots(page, "a-0-live")
        code = first.stop()
        rec.record("proc.first_stop", {"code": code, "line": first.stop_line})
        started = time.monotonic()
        # The named observation window: nothing is awaited, the page is left alone.
        page.wait_for_timeout(STOPPED_WINDOW_S * 1000)
        status = text_of(page.locator("#stream-status"))
        rec.check("ui.a_not_live_after_31s", status != "live", "#stream-status is not 'live' 31 s after the stop", status)
        rec.record("ui.a_status_after_31s", {"status": status, "waited_s": round(time.monotonic() - started, 1)})
        shots(page, "a-1-after-31s")
        go(page, "projects", drawer=False)
        create_through_dialog(page, "QA6 U38 while down")
        refused, _ = settle(lambda: text_of(page.locator("#p-refusal")) == UNREACHABLE or None)
        rec.equal("ui.a_project_dialog_unreachable", UNREACHABLE, text_of(page.locator("#p-refusal")))
        shots(page, "a-2-project")
        page.keyboard.press("Escape")
        go(page, "shepherd", drawer=False)
        page.locator("#shepherd-input").click()
        page.keyboard.type("QA6 U38 while down")
        page.keyboard.press("Enter")
        settle(lambda: text_of(page.locator("#shepherd-status")) == UNREACHABLE or None)
        rec.equal("ui.a_composer_unreachable", UNREACHABLE, text_of(page.locator("#shepherd-status")))
        shots(page, "a-3-composer")
        go(page, "settings", drawer=False)
        page.locator("#settings-nav .set-item", has_text="Autonomy").click()
        page.locator("#settings-panel button.opt", has_text=AUTO).click()
        settle(lambda: text_of(page.locator("#settings-note")) == SETTINGS_UNREACHABLE or None)
        rec.equal("ui.a_settings_note_unreachable", SETTINGS_UNREACHABLE, text_of(page.locator("#settings-note")))
        shots(page, "a-4-settings")
        message = page.locator("#stream-message")
        if message.is_visible():
            page.locator("#stream-message-dismiss").click()
            cleared, _ = settle(lambda: not message.is_visible() or None)
            rec.check("ui.a_dismiss_clears_the_shell_message", bool(cleared), "hidden after the dismiss click", message.is_visible())
        else:
            rec.record("ui.a_shell_message", "no shell message was shown while the daemon was down")
        rec.equal("api.a_no_abort_route", 0, log.master_send_aborts)
        rec.equal("logs.a_page_errors", [], log.page_errors)
        rec.record("ui.a_refused_latency", bool(refused))
    second = pool.ready()
    attach(pool, second, qa6_run.repos / "loose", "QA6 U38 second", state="running")
    with browser_session.context("U38-b", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        rec.note("label: U38(b) installs the fetch shim with add_init_script before the page's scripts (network timing only)")
        page = context.new_page()
        page.add_init_script(script=f"({fetchshim.HOLD_MATCHING_FETCH})('/api/fleet(/tree)?$')")
        page.goto(f"http://127.0.0.1:{second.port}/", wait_until="load")
        held, _ = settle(lambda: fetchshim.held_count(page) >= 2 or None)
        if not held:
            raise Blocked(f"the first-paint fleet reads were not held (held={fetchshim.held_count(page)})")
        second.stop()
        before = fetchshim.delivered(page)
        released = fetchshim.release_all(page)
        reached, _ = settle(lambda: fetchshim.delivered(page) >= before + released or None)
        rec.check("shim.b_delivered", bool(reached), f"__delivered + {released}", fetchshim.delivered(page))
        go(page, "flock", drawer=False)
        empty_visible = page.locator("#empty-state").is_visible()
        sources = text_of(page.locator("#empty-state-sources")) if empty_visible else ""
        claims_empty = empty_visible and "no sessions discovered yet" in text_of(page.locator("#empty-state")) \
            and "registry: 0 sessions" in sources
        rec.check("ui.b_dead_is_not_an_empty_fleet", not claims_empty,
                  "the Flock does not show 'no sessions discovered yet' with 'registry: 0 sessions' (dead != empty)",
                  {"empty_state_visible": empty_visible, "sources": sources})
        shots(page, "b-flock")
        rec.equal("logs.b_page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U39 -------------------------------------------------------------------------------


@scenario("U39")
def test_u39_a_page_open_across_a_daemon_restart_keeps_up(pool: InstancePool, qa6_run: RunContext,
                                                          browser_session: BrowserSession, rec: Recorder,
                                                          request: pytest.FixtureRequest) -> None:
    shots = Shots(browser_session.artifacts, "U39")
    first = pool.ready()
    attach(pool, first, qa6_run.repos / "loose", "QA6 U39 session", state="running")
    port = first.port
    with browser_session.context("U39", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        tab_a = open_app(context, port)
        go(tab_a, "projects", drawer=False)
        for index in range(10):
            created = first.client.create_project(f"QA6 U39 churn {index}")
            project = created.get("project")
            if isinstance(project, dict):
                first.client.delete_project(str(project["project_id"]))
        settle(lambda: tab_a.locator("#proj-list .proj-row", has_text="QA6 U39 churn").count() == 0 or None)
        shots(tab_a, "a-0-before")
        first.stop()
        restarted = pool.start(first.root, port=port)
        request.addfinalizer(restarted.stop)
        try:
            wait_restart_ready(restarted)
        except Blocked as blocked:  # EADDRINUSE only (H2)
            raise Blocked(f"the OS would not re-bind the port for the restart: {blocked.reason}") from blocked
        except RestartFailed as failed:  # the product did not come back on its own root: FAIL (H2)
            rec.check("proc.restart_ready", False, "the same-port restart is ready", str(failed))
            rec.finish()
            return
        if restarted.port != port:
            raise Blocked(f"the restart bound {restarted.port}, not {port}")
        relive, relive_s = settle(lambda: text_of(tab_a.locator("#stream-status")) == "live" or None, RELIVE_BOUND_S)
        if not relive:
            raise Blocked(f"tab A's stream never read live again within {RELIVE_BOUND_S}s")
        rec.record("ui.a_live_again_after_s", round(relive_s, 2))
        tab_b = open_app(context, port)
        go(tab_b, "projects", drawer=False)
        started = time.monotonic()
        create_through_dialog(tab_b, "QA6-after-restart")
        in_b, _ = settle(lambda: tab_b.locator("#proj-list .proj-row", has_text="QA6-after-restart").count() == 1 or None)
        control_s = max(time.monotonic() - started, 1e-3)
        if not in_b:
            raise Blocked("tab B (the control) never listed QA6-after-restart")
        rec.check("ui.b_lists_it", True, "B lists QA6-after-restart (control)", f"{control_s:.3f}s")
        shots(tab_b, "b-created")
        in_a, _ = settle(lambda: tab_a.locator("#proj-list .proj-row", has_text="QA6-after-restart").count() == 1 or None,
                         AFTER_RESTART_BOUND_S)
        if in_a:
            rec.check("ui.a_lists_it_within_10s", True, "A lists QA6-after-restart", True)
        elif AFTER_RESTART_BOUND_S >= CONTROL_MULTIPLE * control_s:
            rec.fail_bound("ui.a_lists_it_within_10s", "tab A lists QA6-after-restart (C-9)", AFTER_RESTART_BOUND_S,
                           f"tab B listed it {control_s:.3f}s after its Save")
        else:
            rec.block("ui.a_lists_it_within_10s", f"unqualified: control {control_s:.3f}s")
        tab_a.bring_to_front()
        shots(tab_a, "a-after")
        names = [str(p.get("name")) for p in restarted.client.projects()]
        rec.check("api.project_exists", "QA6-after-restart" in names, "the project exists", names)
        network = [e["text"][:120] for e in log.console_errors() if "net::ERR_" in e["text"] or "Failed to load resource" in e["text"]]
        rec.record("logs.network_errors_during_the_restart_window", network)
        rec.equal("logs.console_errors_other_than_the_stopped_daemons_network_errors", [],
                  [e for e in log.console_errors() if e["text"][:120] not in network])
        rec.equal("logs.page_errors", [], log.page_errors)
    # Stop the restarted daemon here: it shares the first one's socket path, and
    # the pool checks each stopped instance's socket is gone in list order.
    restarted.stop()
    rec.note(shots.note())
    rec.finish()
