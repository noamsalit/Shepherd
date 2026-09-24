"""Wave 7, SUB lane: the C-26 races — R1-R7 — with the parked-fetch shim.

**Label: every R scenario installs `fetchshim.HOLD_MATCHING_FETCH` with
`page.evaluate`.** That JS changes *network timing only*: it holds a matching
request inside the page and sends it on release (test-plan Difference 8). Every
user action is still a Playwright click, keypress or mouse down/up.

**The positive control, per scenario:** `window.__delivered` must increment by
exactly the number of requests released. If it does not, the scenario is
BLOCKED (wave 7's stop-if, applied at scenario granularity): a shim that never
released proves nothing about the product.

**Mutation `w7-PP11-R7-stale`** (fixtures/mutations/scenarios/w7_pp11_r7_stale.json):
B's project read is answered in the page with A's project, so the detail paints
A's data while B was the last thing asked for — exactly PP-11's failure. R7's
`ui.detail_shows_b` must go false. Applied at one input (a `page.route` on B's
read), never to the product tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from .. import fetchshim
from ..auditprobe import AuditProbe
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld, app_state
from ..mutations import active
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Blocked, Recorder, await_env
from .test_wave6_0_uikit import (
    UI_BOUND_S,
    Attached,
    Shots,
    add_repo,
    api_since,
    attach,
    create_project,
    dialog_open,
    go,
    new_repo,
    open_app,
    session_api,
    session_title,
    settle,
    text_of,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

MUTATION_R7 = "w7-PP11-R7-stale"
ASK = "Ask me before anything leaves this machine"
AUTO = "Approve automatically"
LABEL = "label: fetch shim installed with page.evaluate (network timing only; every action is real input)"


@dataclass
class Races:
    controld: Controld
    client: Client
    run: RunContext
    pool: InstancePool
    session_a: Attached
    session_b: Attached
    project_a: str
    project_b: str
    repos_a: list[str]
    repos_b: list[str]
    project_p: str

    @property
    def port(self) -> int:
        return self.controld.port


def two_repos(parent: Path, stem: str) -> list[Path]:
    return [new_repo(parent, f"{stem}-1"), new_repo(parent, f"{stem}-2")]


@pytest.fixture(scope="module")
def races(pool: InstancePool, qa6_run: RunContext) -> Iterator[Races]:
    controld = pool.ready()
    client = controld.client
    loose = qa6_run.repos / "loose"
    session_a = attach(pool, controld, loose, "QA6 R session A", state="running")
    session_b = attach(pool, controld, loose, "QA6 R session B", state="running")
    project_a = create_project(client, "QA6 R project A")
    project_b = create_project(client, "QA6 R project B")
    repos_a = [str(p) for p in two_repos(controld.root.root, "ra")]
    repos_b = [str(p) for p in two_repos(controld.root.root, "rb")]
    for pid, repos in ((project_a, repos_a), (project_b, repos_b)):
        for repo in repos:
            add_repo(client, pid, Path(repo))
    project_p = create_project(client, "QA6 R project P")
    yield Races(controld=controld, client=client, run=qa6_run, pool=pool, session_a=session_a, session_b=session_b,
                project_a=project_a, project_b=project_b, repos_a=repos_a, repos_b=repos_b, project_p=project_p)


def release(page: Page, rec: Recorder, name: str, first: bool = False) -> bool:
    """Release (all, or the oldest) held request and prove the shim delivered it."""
    before = fetchshim.delivered(page)
    released = fetchshim.release_first(page) if first else fetchshim.release_all(page)
    if released < 1:
        rec.block(f"shim.{name}_released", f"nothing was held to release (held={fetchshim.held_count(page)})")
        return False
    reached, _ = settle(lambda: fetchshim.delivered(page) >= before + released or None)
    ok = bool(reached) and fetchshim.delivered(page) == before + released
    if ok:
        rec.check(f"shim.{name}_delivered", True, f"__delivered + {released}", fetchshim.delivered(page))
    else:
        rec.block(f"shim.{name}_delivered", f"__delivered {before} -> {fetchshim.delivered(page)} after releasing {released}")
    return ok


def hold_until(page: Page, rec: Recorder, name: str, count: int = 1) -> bool:
    held, _ = settle(lambda: fetchshim.held_count(page) >= count or None)
    if not held:
        rec.block(f"shim.{name}_held", f"the matching request was never held (held={fetchshim.held_count(page)})")
    return bool(held)


def open_flock(page: Page) -> None:
    go(page, "flock", drawer=False)
    page.locator("#flock-projects .project[data-project-id=unassigned]").click()
    await_env(lambda: page.locator("#flock-cards .card").count() > 0 or None, UI_BOUND_S, "the Unassigned cards")


def open_projects(page: Page) -> None:
    go(page, "projects", drawer=False)
    await_env(lambda: page.locator("#proj-list .proj-row").count() > 0 or None, UI_BOUND_S, "the project list")


def title_of(client: Client, session_id: str) -> str:
    return str(session_api(client, session_id).get("title"))


# ----- R1 --------------------------------------------------------------------------------


@scenario("R1")
def test_r1_loadfleet_never_applies_half_of_a_refresh(races: Races, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R1")
    rec.note(LABEL)
    aborted: list[str] = []
    with browser_session.context("R1", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, races.port)
        open_flock(page)
        cards_before = page.locator("#flock-cards .card").count()
        fetchshim.install(page, "/api/fleet/tree$")
        start = len(log.requests)
        added = attach(races.pool, races.controld, races.run.repos / "loose", "QA6 R1 new running", state="running")
        if not hold_until(page, rec, "tree"):
            rec.finish()
            return

        def abort_tree(route: Route) -> None:
            aborted.append(route.request.url)
            route.abort()

        page.route(lambda address: address.split("?")[0].endswith("/api/fleet/tree"), abort_tree)
        if not release(page, rec, "tree"):
            rec.finish()
            return
        settle(lambda: aborted or None, 3.0, page)
        fleet_reads = [c for c in api_since(log, start, "GET") if c == "GET /api/fleet"]
        rec.check("api.fleet_served_tree_aborted", bool(fleet_reads) and len(aborted) == 1,
                  "/api/fleet served and /api/fleet/tree aborted (control)", {"fleet": fleet_reads, "aborted": aborted})
        shots(page, "after-release")
        cards_after = page.locator("#flock-cards .card").count()
        api_running = as_dict(races.client.fleet().get("counts")).get("running")
        rec.record("ui.after_release", {"cards_before": cards_before, "cards_after": cards_after,
                                        "new_card_shown": page.locator(f"#flock-cards .card[data-session-id='{added.session_id}']").count(),
                                        "api_running": api_running,
                                        "stop_summary": text_of(page.locator("#stop-summary"))})
        rec.block("ui.running_count_agrees_with_running_cards",
                  "unobservable as written: the Flock renders no running count (flock.js draws unknown_rate, "
                  "completed_low_confidence, unclassified and per-project session counts, all but the first three from "
                  "the tree), so a half-applied refresh cannot show a running count that disagrees with the cards")
    rec.note(shots.note())
    rec.finish()


# ----- R2 --------------------------------------------------------------------------------


@scenario("R2")
def test_r2_the_last_autonomy_click_wins(races: Races, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R2")
    rec.note(LABEL)
    audit = AuditProbe.for_instance(races.controld.root)
    mark = audit.mark()
    try:
        with browser_session.context("R2", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, races.port)
            go(page, "settings", drawer=False)
            page.locator("#settings-nav .set-item", has_text="Autonomy").click()
            await_env(lambda: page.locator("#settings-panel button.opt").count() == 2 or None, UI_BOUND_S, "the options")
            fetchshim.install(page, "/api/autonomy$")
            page.locator("#settings-panel button.opt", has_text=AUTO).click()
            if not hold_until(page, rec, "level3"):
                rec.finish()
                return
            fetchshim.set_holding(page, False)
            page.locator("#settings-panel button.opt", has_text=ASK).click()
            settle(lambda: page.locator("#settings-panel button.opt", has_text=ASK).get_attribute("aria-pressed") == "true" or None)
            shots(page, "1-ask-answered")
            if not release(page, rec, "level3", first=True):
                rec.finish()
                return
            settle(lambda: len([r for r in audit.records_for(mark, "set_autonomy_level")]) >= 2 or None, 3.0)
            pressed = page.locator("#settings-panel button.opt", has_text=ASK).get_attribute("aria-pressed")
            rec.equal("ui.last_click_wins_ask_pressed", "true", pressed)
            shots(page, "2-after-release")
            rec.equal("api.level_is_2", 2, races.client.get("/api/autonomy").data().get("level"))
            rec.equal("db.level_is_2", 2, app_state(races.controld.db, "autonomy_level"))
            rows = audit.records_for(mark, "set_autonomy_level")
            levels = [as_dict(r.get("args")).get("level") for r in rows]
            rec.record("logs.audit_rows_in_arrival_order", levels)
            rec.equal("logs.two_audit_rows", 2, len(rows))
    finally:
        races.client.post("/api/autonomy", {"level": 2})
    rec.note(shots.note())
    rec.finish()


# ----- R3 --------------------------------------------------------------------------------


@scenario("R3")
def test_r3_a_rename_reply_never_paints_into_another_session(races: Races, browser_session: BrowserSession,
                                                             rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R3")
    rec.note(LABEL)
    a, b = races.session_a, races.session_b
    b_title = title_of(races.client, b.session_id)
    with browser_session.context("R3", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, races.port)
        open_flock(page)
        page.locator(f"#flock-cards .card[data-session-id='{a.session_id}']").click()
        await_env(lambda: text_of(page.locator("#session-title")) == title_of(races.client, a.session_id) or None,
                  UI_BOUND_S, "A's pane")
        page.locator("#session-rename").click()
        await_env(lambda: page.locator("#session-title input").count() == 1 or None, UI_BOUND_S, "the rename input")
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.type("QA6-A-NEW")
        fetchshim.install(page, f"/api/sessions/{a.session_id}/rename$")
        page.keyboard.press("Enter")
        if not hold_until(page, rec, "rename"):
            rec.finish()
            return
        page.locator(f"#flock-cards .card[data-session-id='{b.session_id}']").click()
        await_env(lambda: text_of(page.locator("#session-title")) == b_title or None, UI_BOUND_S, "B's pane")
        shots(page, "1-b-open")
        if not release(page, rec, "rename"):
            rec.finish()
            return
        settle(lambda: 200 in log.status_of(f"/api/sessions/{a.session_id}/rename") or None, 3.0, page)
        rec.equal("ui.third_pane_shows_b_unchanged", b_title, text_of(page.locator("#session-title")))
        shots(page, "2-after-release")
        rec.equal("db.a_title_is_new", "QA6-A-NEW", session_title(races.controld, a.session_id).get("title"))
        rec.equal("api.rename_200", [200], log.status_of(f"/api/sessions/{a.session_id}/rename"))
    rec.note(shots.note())
    rec.finish()


# ----- R4 --------------------------------------------------------------------------------


def dialog_paths(page: Page) -> list[str]:
    return sorted(t.strip() for t in page.locator("#p-paths .path .path-text").all_text_contents())


@scenario("R4")
def test_r4_an_old_projects_paths_never_appear_in_anothers_edit_dialog(races: Races, browser_session: BrowserSession,
                                                                        rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R4")
    rec.note(LABEL)
    a, b = races.project_a, races.project_b
    stored_b = sorted(str(r["root_path"]) for r in as_list(races.client.get(f"/api/projects/{b}/repos").data().get("repos"))
                      if isinstance(r, dict))
    with browser_session.context("R4", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, races.port)
        open_projects(page)
        page.locator(f"#proj-list .proj-row[data-project-id='{a}']").click()
        await_env(lambda: page.locator("#proj-edit").count() == 1 and text_of(page.locator("#proj-detail .proj-title")) == "QA6 R project A"
                  or None, UI_BOUND_S, "A's detail")
        fetchshim.install(page, f"/api/projects/{a}/repos$")
        page.locator("#proj-edit").click()
        if not hold_until(page, rec, "a_repos"):
            rec.finish()
            return
        page.keyboard.press("Escape")
        await_env(lambda: not dialog_open(page, "#dlg-project") or None, UI_BOUND_S, "A's dialog closed")
        page.locator(f"#proj-list .proj-row[data-project-id='{b}']").click()
        await_env(lambda: text_of(page.locator("#proj-detail .proj-title")) == "QA6 R project B" or None, UI_BOUND_S, "B's detail")
        page.locator("#proj-edit").click()
        await_env(lambda: dialog_paths(page) == stored_b or None, UI_BOUND_S, "B's paths in the dialog")
        shots(page, "1-b-dialog")
        if not release(page, rec, "a_repos"):
            rec.finish()
            return
        settle(lambda: 200 in log.status_of(f"/api/projects/{a}/repos") or None, 3.0, page)
        rec.equal("ui.b_dialog_lists_only_b_repos", stored_b, dialog_paths(page))
        shots(page, "2-after-release")
        order = [str(entry.get("url")) for entry in log.responses if "/repos" in str(entry.get("url"))]
        rec.record("api.repos_reads_answer_order", [u.split("/api/", 1)[1] for u in order])
    rec.note(shots.note())
    rec.finish()


# ----- R5 --------------------------------------------------------------------------------


@scenario("R5")
def test_r5_a_list_refresh_never_swallows_a_click_on_edit(races: Races, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R5")
    rec.note(LABEL)
    p = races.project_p
    extra = ""
    try:
        with browser_session.context("R5", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, races.port)
            open_projects(page)
            page.locator(f"#proj-list .proj-row[data-project-id='{p}']").click()
            await_env(lambda: text_of(page.locator("#proj-detail .proj-title")) == "QA6 R project P" or None, UI_BOUND_S, "P's detail")
            fetchshim.install(page, "/api/projects$")
            extra = create_project(races.client, "QA6 R5 other client")
            if not hold_until(page, rec, "list"):
                rec.finish()
                return
            edit = page.locator("#proj-edit")
            handle = edit.element_handle()
            where = edit.bounding_box()
            if where is None or handle is None:
                raise Blocked("#proj-edit has no box to press on")
            page.mouse.move(where["x"] + where["width"] / 2, where["y"] + where["height"] / 2)
            page.mouse.down()
            start = len(log.requests)
            if not release(page, rec, "list"):
                page.mouse.up()
                rec.finish()
                return
            settle(lambda: any(c == f"GET /api/projects/{p}" for c in api_since(log, start, "GET")) or None, 3.0, page)
            settle(lambda: not handle.evaluate("e => e.isConnected") or None, 3.0)
            rec.record("ui.pressed_button_replaced_before_mouse_up", not handle.evaluate("e => e.isConnected"))
            page.mouse.up()
            opened, _ = settle(lambda: dialog_open(page, "#dlg-project") or None, 3.0)
            rec.check("ui.edit_dialog_open_for_p", bool(opened) and text_of(page.locator("#dlg-project-title")) == "Edit project"
                      and page.locator("#p-name").input_value() == "QA6 R project P",
                      "#dlg-project open in edit mode for P", {"open": dialog_open(page, "#dlg-project"),
                                                              "title": text_of(page.locator("#dlg-project-title"))})
            shots(page, "after-mouse-up")
    finally:
        if extra:
            races.client.delete_project(extra)
    rec.note(shots.note())
    rec.finish()


# ----- R6 --------------------------------------------------------------------------------


@scenario("R6")
def test_r6_a_slow_session_read_never_paints_over_the_newer_one(races: Races, browser_session: BrowserSession,
                                                                rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R6")
    rec.note(LABEL)
    a, b = races.session_a, races.session_b
    b_title = title_of(races.client, b.session_id)
    with browser_session.context("R6", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, races.port)
        open_flock(page)
        fetchshim.install(page, f"/api/sessions/{a.session_id}$")
        page.locator(f"#flock-cards .card[data-session-id='{a.session_id}']").click()
        if not hold_until(page, rec, "a_read"):
            rec.finish()
            return
        page.locator(f"#flock-cards .card[data-session-id='{b.session_id}']").click()
        await_env(lambda: text_of(page.locator("#session-title")) == b_title or None, UI_BOUND_S, "B's pane")
        if not release(page, rec, "a_read"):
            rec.finish()
            return
        settle(lambda: 200 in log.status_of(f"/api/sessions/{a.session_id}") or None, 3.0, page)
        rec.equal("ui.third_pane_shows_b", b_title, text_of(page.locator("#session-title")))
        order = [str(e.get("url")).rsplit("/", 1)[1] for e in log.responses
                 if str(e.get("url")).rsplit("/", 1)[-1] in (a.session_id, b.session_id)]
        rec.check("api.a_answered_after_b", order[-2:] == [b.session_id, a.session_id], "B's read answered, then A's (control)", order)
        shots(page, "after-release")
    rec.note(shots.note())
    rec.finish()


# ----- R7 --------------------------------------------------------------------------------


@scenario("R7")
def test_r7_a_slow_project_read_never_paints_over_the_newer_one(races: Races, browser_session: BrowserSession,
                                                                rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "R7")
    rec.note(LABEL)
    a, b = races.project_a, races.project_b
    stale: list[str] = []
    with browser_session.context("R7", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, races.port)
        if active(MUTATION_R7):
            a_body = races.client.get(f"/api/projects/{a}").text

            def stale_answer(route: Route) -> None:
                stale.append(route.request.url)
                route.fulfill(status=200, content_type="application/json", body=a_body)

            page.route(f"**/api/projects/{b}", stale_answer)
        open_projects(page)
        fetchshim.install(page, f"/api/projects/{a}$")
        page.locator(f"#proj-list .proj-row[data-project-id='{a}']").click()
        if not hold_until(page, rec, "a_read"):
            rec.finish()
            return
        page.locator(f"#proj-list .proj-row[data-project-id='{b}']").click()
        settle(lambda: page.locator("#proj-detail .proj-title").count() == 1 or None)
        if not release(page, rec, "a_read"):
            rec.finish()
            return
        settle(lambda: 200 in log.status_of(f"/api/projects/{a}") or None, 3.0, page)
        if active(MUTATION_R7):
            applied = "APPLIED" if stale else "NOT APPLIED (the stale answer was never served)"  # hunter L2
            rec.note(f"QA6 MUTATION {MUTATION_R7} {applied}: B's read answered in the page with A's project ({len(stale)} hit(s))")
        rec.equal("ui.detail_shows_b", "QA6 R project B", text_of(page.locator("#proj-detail .proj-title")))
        order = [str(e.get("url")).rsplit("/", 1)[1] for e in log.responses if str(e.get("url")).rsplit("/", 1)[-1] in (a, b)]
        rec.check("api.a_answered_after_b", order[-2:] == [b, a], "B's read answered, then A's (control)", order)
        shots(page, "after-release")
    rec.note(shots.note())
    rec.finish()
