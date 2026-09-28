"""Wave 7, SUB lane: U40 — a permanently refused stream says so.

Its own module because it needs its own chromium: launched with
`--host-resolver-rules=MAP qa6.test 127.0.0.1` (BUILDING.md §4), so the page's
Host header is `qa6.test:<port>` and the product's host check refuses the
stream and every POST (S1/S2) while the plain GETs still answer. A second
sync-Playwright in the same thread as the conftest's `browser_session` is not
possible, so this module never requests that fixture.

The plan's "wait 10 s" is an observation window for the status to settle; it
is read as `observe` for up to 10 s, never as readiness.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..auditprobe import AuditProbe
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Recorder, await_env
from .test_wave6_0_uikit import (
    UI_BOUND_S,
    Shots,
    attach,
    dialog_open,
    go,
    settle,
    text_of,
    url,
)

HOST = "qa6.test"
OBSERVE_S = 10.0


@pytest.fixture(scope="module")
def mapped_browser(qa6_run: RunContext) -> Iterator[BrowserSession]:
    session = BrowserSession(qa6_run.run_dir / "ui", launch_args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
    session.start()
    try:
        yield session
    finally:
        problems = session.stop()
        for problem in problems:
            qa6_run.teardown_problem("U40 browser", problem)


@scenario("U40")
def test_u40_a_permanently_refused_stream_says_so(pool: InstancePool, qa6_run: RunContext, mapped_browser: BrowserSession,
                                                  rec: Recorder) -> None:
    shots = Shots(mapped_browser.artifacts, "U40")
    controld = pool.ready()
    attach(pool, controld, qa6_run.repos / "loose", "QA6 U40 session", state="running")
    audit = AuditProbe.for_instance(controld.root)
    mark = audit.mark()
    names_before = {str(p.get("name")) for p in controld.client.projects()}
    with mapped_browser.context("U40", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = context.new_page()
        page.goto(url(controld.port, HOST), wait_until="load")
        await_env(lambda: page.locator("#nav-chat").get_attribute("aria-current") == "page" or None, UI_BOUND_S,
                  "the app routed to Shepherd")
        refused, _ = settle(lambda: 403 in log.status_of("/api/events") or None, OBSERVE_S, page)
        rec.check("api.events_403", bool(refused), "/api/events answered 403", log.status_of("/api/events"))
        settled, _ = settle(lambda: text_of(page.locator("#stream-status")) == "unreadable" or None, OBSERVE_S)
        status = text_of(page.locator("#stream-status"))
        rec.check("ui.status_neither_live_nor_reconnecting", status not in ("live", "reconnecting"),
                  "#stream-status reads neither 'live' nor 'reconnecting' (it reads 'unreadable')", status)
        shots(page, "1-status")
        go(page, "projects", drawer=False)
        page.locator("#proj-new").click()
        await_env(lambda: dialog_open(page, "#dlg-project") or None, UI_BOUND_S, "the project dialog")
        page.locator("#p-name").click()
        page.keyboard.type("QA6 U40 refused")
        page.locator("#p-save").click()
        shown, _ = settle(lambda: page.locator("#p-refusal").is_visible() or None)
        rec.check("ui.create_shows_a_refusal", bool(shown), "#p-refusal visible", text_of(page.locator("#p-refusal")))
        settle(lambda: 403 in log.status_of("/api/projects") or None, 3.0, page)
        rec.check("api.create_post_403", 403 in log.status_of("/api/projects"), "the create POST answered 403",
                  log.status_of("/api/projects"))
        rec.equal("ui.no_row_added", 0, page.locator("#proj-list .proj-row", has_text="QA6 U40 refused").count())
        shots(page, "2-create")
    names_after = {str(p.get("name")) for p in controld.client.projects()}
    rec.equal("db.no_project_created", sorted(names_before), sorted(names_after))
    rec.equal("logs.no_audit_row", [], [r.get("tool") for r in audit.mutations_since(mark)])
    rec.note(shots.note())
    rec.finish()
