"""Wave 6, SUB lane: the Projects page — U15-U21 — every control by real input.

One SUB instance, seeded through the product's routes: `Alpha` (a description,
one repo made inside this instance's root, one attached session), one
`Payments`, and an empty project. U19(b)-(d) spawn owned fake-engine sessions
(SHIM-DEPENDENT) in projects of their own. Every dialog is driven by clicks and
keys; no dialog is closed from JS. Two network faults are injected with
`page.route` and labelled (U17's refused description save, U18's refused
removal). Each scenario restores what it changed (the plan's Cleanup rows).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ..auditprobe import AuditProbe
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import Subscriber, subscribe
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
    is_showing,
    nav_state,
    kill_owned,
    new_repo,
    open_app,
    pane_alive,
    posts_to,
    project_rows,
    record_posts,
    session_api,
    settle,
    spawn_owned,
    text_of,
    xss_fired,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

NEEDS_NAME = "A project needs a name — this one is only whitespace."  # projects.js:54
NO_SESSIONS = "No sessions have run here."  # projects.js renderDetail
NO_DESCRIPTION = "No description."
XSS = '<img src=x onerror="window.__xss=1">'
REFUSED_ENVELOPE = '{"ok": false, "data": null, "error": "request failed", "correlation_id": "qa6-refused"}'


@dataclass
class Projects:
    controld: Controld
    client: Client
    run: RunContext
    pool: InstancePool
    stream: Subscriber
    alpha: str
    alpha_repo: Path
    alpha_session: Attached
    payments: str
    empty: str
    owned: list[str] = field(default_factory=list)

    @property
    def port(self) -> int:
        return self.controld.port

    @property
    def root(self) -> Path:
        return self.controld.root.root


@pytest.fixture(scope="module")
def projects(pool: InstancePool, qa6_run: RunContext) -> Iterator[Projects]:
    controld = pool.ready()
    client = controld.client
    repo = new_repo(controld.root.root, "alpha15")
    alpha = create_project(client, "Alpha", "alpha desc")
    add_repo(client, alpha, repo)
    session = attach(pool, controld, repo, "QA6 U15 alpha session", state="running")
    payments = create_project(client, "Payments")
    empty = create_project(client, "QA6 Empty")
    stream = subscribe("U-projects", controld.port)
    state = Projects(controld=controld, client=client, run=qa6_run, pool=pool, stream=stream, alpha=alpha,
                     alpha_repo=repo, alpha_session=session, payments=payments, empty=empty)
    try:
        yield state
    finally:
        stream.close()
        for session_id in state.owned:
            if pane_alive(qa6_run, controld.root.k, session_id):
                kill_owned(client, session_id)


def open_projects(page: Page) -> None:
    go(page, "projects", drawer=False)
    await_env(lambda: page.locator("#proj-list .proj-row").count() > 0 or None, UI_BOUND_S, "the project list")


def open_row(page: Page, project_id: str) -> None:
    page.locator(f"#proj-list .proj-row[data-project-id='{project_id}']").click()
    await_env(lambda: page.locator(f"#proj-list .proj-row[data-project-id='{project_id}']").get_attribute("aria-current") == "true"
              and page.locator("#proj-detail .proj-title").count() == 1 or None, UI_BOUND_S, f"the detail of {project_id}")


def row_ids(page: Page) -> list[str]:
    value = page.evaluate("() => [...document.querySelectorAll('#proj-list .proj-row')].map(r => r.dataset.projectId)")
    return [str(item) for item in value] if isinstance(value, list) else []


def row_name(page: Page, project_id: str) -> str | None:
    row = page.locator(f"#proj-list .proj-row[data-project-id='{project_id}'] .proj-name")
    return row.text_content() if row.count() else None


def project_ids_named(client: Client, name: str) -> list[str]:
    return [str(p["project_id"]) for p in client.projects() if p.get("name") == name]


def project_repos(client: Client, project_id: str) -> list[dict[str, object]]:
    answer = client.get(f"/api/projects/{project_id}/repos").data()
    return [as_dict(r) for r in as_list(answer.get("repos"))]


# ----- U15 -------------------------------------------------------------------------------


@scenario("U15")
def test_u15_the_projects_list_and_detail(projects: Projects, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U15")
    second = create_project(projects.client, "Payments")
    try:
        with browser_session.context("U15", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, projects.port)
            open_projects(page)
            ids = row_ids(page)
            rec.equal("ui.unassigned_last", "unassigned", ids[-1] if ids else None)
            rec.equal("ui.unassigned_reserved", "true",
                      page.locator("#proj-list .proj-row[data-project-id=unassigned]").get_attribute("data-reserved"))
            for pid in (projects.payments, second):
                shown = page.locator(f"#proj-list .proj-row[data-project-id='{pid}'] .proj-id")
                rec.equal(f"ui.duplicate_name_shows_id.{pid[-6:]}", pid, shown.text_content() if shown.count() else None)
            shots(page, "list")
            for label, pid in (("alpha", projects.alpha), ("empty", projects.empty), ("unassigned", "unassigned")):
                start = len(log.requests)
                open_row(page, pid)
                gets = [c for c in api_since(log, start, "GET") if c == f"GET /api/projects/{pid}"]
                rec.equal(f"api.one_get_per_click.{label}", 1, len(gets))
                shots(page, f"detail-{label}")
                if label == "alpha":
                    paths = [t.strip() for t in page.locator("#proj-detail .path-text").all_text_contents()]
                    stored = [str(r["root_path"]) for r in project_repos(projects.client, pid)]
                    rec.equal("ui.alpha_repo_path_in_full", stored, paths)
                    links = page.locator("#proj-detail .sess-mini a.mini-open")
                    rec.equal("ui.alpha_sessions_as_links", [projects.alpha_session.session_id],
                              [str(links.nth(i).get_attribute("data-session-id")) for i in range(links.count())])
                if label == "empty":
                    rec.check("ui.empty_sentence", NO_SESSIONS in (page.locator("#proj-detail .sess-mini").text_content() or ""),
                              NO_SESSIONS, page.locator("#proj-detail .sess-mini").text_content())
                if label == "unassigned":
                    rec.equal("ui.unassigned_has_no_edit_or_delete", (0, 0),
                              (page.locator("#proj-edit").count(), page.locator("#proj-delete").count()))
            rec.equal("logs.console_errors", [], log.console_errors())
    finally:
        projects.client.delete_project(second)
    rec.note(shots.note())
    rec.finish()


# ----- U16 -------------------------------------------------------------------------------


def open_create(page: Page) -> None:
    if dialog_open(page, "#dlg-project"):
        page.keyboard.press("Escape")
        await_env(lambda: not dialog_open(page, "#dlg-project") or None, UI_BOUND_S, "the project dialog closed")
    page.locator("#proj-new").click()
    await_env(lambda: dialog_open(page, "#dlg-project") or None, UI_BOUND_S, "the project dialog open")


def type_into(page: Page, selector: str, text: str) -> None:
    page.locator(selector).click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.press("Backspace")
    if text:
        page.keyboard.type(text)


@scenario("U16")
def test_u16_create_a_project_name_classes_cancel_escape_duplicate(projects: Projects, browser_session: BrowserSession,
                                                                   rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U16")
    audit = AuditProbe.for_instance(projects.controld.root)
    mark = audit.mark()
    stream_mark = projects.stream.mark()
    created: list[str] = []
    long_name = "QA6 " + "L" * 196
    posts = 0
    with browser_session.context("U16", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, projects.port)
        open_projects(page)

        def post_count() -> int:
            return len([c for c in posts_to(log, 0, "/api/projects") if c == "POST /api/projects"])

        # (1) empty
        open_create(page)
        before = post_count()
        page.locator("#p-save").click()
        rec.check("ui.1_empty_stays_open_invalid", dialog_open(page, "#dlg-project")
                  and bool(page.locator("#p-name").evaluate("e => e.matches(':invalid')")), "open and #p-name :invalid",
                  dialog_open(page, "#dlg-project"))
        rec.equal("api.1_no_post", before, post_count())
        shots(page, "1-empty")
        # (2) whitespace
        type_into(page, "#p-name", "   ")
        page.locator("#p-save").click()
        settle(lambda: page.locator("#p-refusal").is_visible() or None, 3.0)
        rec.equal("ui.2_whitespace_refusal", NEEDS_NAME, text_of(page.locator("#p-refusal")))
        rec.equal("api.2_no_post", before, post_count())
        shots(page, "2-whitespace")
        # (3)-(6): each closes, the row shows the exact text, one POST each
        for case, name, desc, submit in (("3", "QA6 New", "QA6 desc", "enter"), ("4", long_name, "", "save"),
                                         ("5", "Café 🚀 項目", "", "save"), ("6", XSS, "", "save")):
            open_create(page)
            before = post_count()
            type_into(page, "#p-name", name)
            if desc:
                type_into(page, "#p-desc", desc)
                page.locator("#p-name").click()
            if submit == "enter":
                page.keyboard.press("Enter")
            else:
                page.locator("#p-save").click()
            closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
            rec.check(f"ui.{case}_closes", bool(closed), "the dialog closes", dialog_open(page, "#dlg-project"))
            ids = project_ids_named(projects.client, name)
            created.extend(ids)
            pid = ids[-1] if ids else ""
            settle(lambda: row_name(page, pid) is not None or None)
            rec.equal(f"ui.{case}_row_exact_text", name, row_name(page, pid))
            settle(lambda: post_count() > before or None, 3.0, page)
            rec.equal(f"api.{case}_one_post", before + 1, post_count())
            if case == "6":
                rec.equal("ui.6_no_img_src_x", 0, page.locator("img[src=x]").count())
                rec.equal("ui.6_xss_not_run", None, xss_fired(page))
            shots(page, f"{case}-created")
        # (7) duplicate: warn, then create
        open_create(page)
        before = post_count()
        type_into(page, "#p-name", "Payments")
        page.locator("#p-save").click()
        settle(lambda: page.locator("#p-refusal").is_visible() or None, 3.0)
        warning = text_of(page.locator("#p-refusal"))
        rec.check("ui.7_first_save_warns", 'There is already a project named "Payments"' in warning and dialog_open(page, "#dlg-project"),
                  "the duplicate warning, dialog still open", warning)
        rec.equal("api.7_no_post_on_first_save", before, post_count())
        shots(page, "7-warned")
        page.locator("#p-save").click()
        closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
        settle(lambda: post_count() > before or None, 3.0, page)
        rec.check("ui.7_second_save_creates", bool(closed), "closed after the second Save", dialog_open(page, "#dlg-project"))
        rec.equal("api.7_one_post_on_second_save", before + 1, post_count())
        payments = project_ids_named(projects.client, "Payments")
        created.extend(pid for pid in payments if pid != projects.payments)
        rec.check("db.7_two_payments_distinct_ids", len(payments) == 2 and len(set(payments)) == 2,
                  "two Payments rows with distinct ids", payments)
        # Cancel and Escape
        for closer in ("cancel", "escape"):
            open_create(page)
            before = post_count()
            type_into(page, "#p-name", f"QA6 not {closer}")
            if closer == "cancel":
                page.locator("#dlg-project .dlg-acts button", has_text="Cancel").click()
            else:
                page.keyboard.press("Escape")
            closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
            rec.check(f"ui.{closer}_closes", bool(closed), "closed", dialog_open(page, "#dlg-project"))
            rec.equal(f"api.{closer}_no_post", before, post_count())
        posts = post_count()
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.equal("logs.audit_create_project_per_post", posts, len(audit.records_for(mark, "create_project")))
    frames = [f for f in projects.stream.since(stream_mark) if f.kind == "project.created"]
    rec.equal("stream.project_created_per_post", posts, len(frames))
    for pid in sorted(set(created)):
        projects.client.delete_project(pid)
    rec.note(shots.note())
    rec.finish()


# ----- U17 -------------------------------------------------------------------------------


def open_edit(page: Page) -> None:
    page.locator("#proj-edit").click()
    await_env(lambda: dialog_open(page, "#dlg-project")
              and text_of(page.locator("#dlg-project-title")) == "Edit project" or None, UI_BOUND_S, "the edit dialog")


@scenario("U17")
def test_u17_edit_a_project_a_partial_save_does_not_repeat_the_rename(projects: Projects, browser_session: BrowserSession,
                                                                      rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U17")
    rec.note("label: network fault via page.route (the second save's description POST answered 400 in the page)")
    pid = projects.alpha
    rename_path = f"/api/projects/{pid}/rename"
    describe_path = f"/api/projects/{pid}/description"
    try:
        with browser_session.context("U17", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, projects.port)
            bodies = record_posts(page)
            open_projects(page)
            open_row(page, pid)
            open_edit(page)
            type_into(page, "#p-name", "Alpha2")
            type_into(page, "#p-desc", "")
            start = len(log.requests)
            page.locator("#p-save").click()
            closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
            rec.check("ui.first_save_closes", bool(closed), "closed", dialog_open(page, "#dlg-project"))
            settle(lambda: row_name(page, pid) == "Alpha2" or None)
            rec.equal("ui.row_reads_alpha2", "Alpha2", row_name(page, pid))
            settle(lambda: page.locator("#proj-detail .desc").first.text_content() == NO_DESCRIPTION or None)
            rec.equal("ui.no_description", NO_DESCRIPTION, page.locator("#proj-detail .desc").first.text_content())
            sent = [c.split(" ", 1)[1] for c in api_since(log, start, "POST")]
            rec.equal("api.first_save_sends_rename_then_description", [rename_path, describe_path], sent)
            rec.equal("api.description_body_is_empty_object", [{}], bodies.of(describe_path))
            shots(page, "1-saved")

            def refuse(route: Route) -> None:
                route.fulfill(status=400, content_type="application/json", body=REFUSED_ENVELOPE)

            open_edit(page)
            type_into(page, "#p-name", "Alpha3")
            type_into(page, "#p-desc", "d3")
            page.route(f"**{describe_path}", refuse)
            start = len(log.requests)
            page.locator("#p-save").click()
            refused, _ = settle(lambda: page.locator("#p-refusal").is_visible() or None)
            rec.check("ui.failed_save_stays_open_with_refusal", bool(refused) and dialog_open(page, "#dlg-project"),
                      "open, #p-refusal visible", text_of(page.locator("#p-refusal")))
            shots(page, "2-refused")
            page.unroute(f"**{describe_path}", refuse)
            page.locator("#p-save").click()
            closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
            rec.check("ui.second_save_closes", bool(closed), "closed", dialog_open(page, "#dlg-project"))
            settle(lambda: len(posts_to(log, start, describe_path)) >= 2 or None, 3.0, page)
            renames = posts_to(log, start, rename_path)
            rec.equal("api.one_rename_across_failed_and_second_save", 1, len(renames))
            row = project_rows(projects.controld, "Alpha3")
            rec.equal("db.final_name_and_description", [{"id": pid, "name": "Alpha3", "description": "d3"}], row)
            open_edit(page)
            page.keyboard.press("Escape")
            closed, _ = settle(lambda: not dialog_open(page, "#dlg-project") or None)
            rec.check("ui.escape_closes", bool(closed), "closed", dialog_open(page, "#dlg-project"))
            shots(page, "3-final")
            rec.record("logs.console_errors", [e["text"][:120] for e in log.console_errors()])
    finally:
        projects.client.rename_project(pid, "Alpha")
        projects.client.describe_project(pid, "alpha desc")
    rec.note(shots.note())
    rec.finish()


# ----- U18 -------------------------------------------------------------------------------


def dialog_paths(page: Page) -> list[str]:
    return [t.strip() for t in page.locator("#p-paths .path .path-text").all_text_contents()]


def add_path(page: Page, text: str, how: str) -> None:
    type_into(page, "#p-new-path", text)
    if how == "enter":
        page.keyboard.press("Enter")
    elif how == "button":
        page.locator("#p-add-path").click()
    else:
        page.locator("#p-add-path").dblclick()


@scenario("U18")
def test_u18_repo_paths_in_the_edit_dialog(projects: Projects, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U18")
    rec.note("label: network fault via page.route (a repos/remove answered 400 in the page)")
    pid = projects.alpha
    one = new_repo(projects.root, "u18-one")
    two = new_repo(projects.root, "u18-two")
    three = new_repo(projects.root, "u18-three")
    plain = projects.root / "u18-plain"
    plain.mkdir()
    missing = projects.root / "u18-missing"
    add_post = f"/api/projects/{pid}/repos/add"
    remove_post = f"/api/projects/{pid}/repos/remove"
    original = {str(r["repo_id"]) for r in project_repos(projects.client, pid)}
    try:
        with browser_session.context("U18", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, projects.port)
            open_projects(page)
            open_row(page, pid)
            open_edit(page)
            settle(lambda: dialog_paths(page) or None)
            for label, path, how in (("one_by_enter", one, "enter"), ("two_by_button", two, "button")):
                start = len(log.requests)
                add_path(page, str(path), how)
                added, _ = settle(lambda: str(path) in [p.rstrip("/") for p in dialog_paths(page)]
                                  or any(p.endswith(path.name) for p in dialog_paths(page)) or None)
                rec.check(f"ui.{label}_adds", bool(added), f"a row for {path.name}", dialog_paths(page))
                rec.check(f"ui.{label}_dialog_stays_open", dialog_open(page, "#dlg-project"), "open", dialog_open(page, "#dlg-project"))
                settle(lambda: posts_to(log, start, add_post) or None, 3.0, page)
                rec.equal(f"api.{label}_one_add", 1, len(posts_to(log, start, add_post)))
                others = [c for c in api_since(log, start, "POST") if "/rename" in c or "/description" in c]
                rec.equal(f"api.{label}_no_rename_or_description", [], others)
            shots(page, "1-added")
            for label, text in (("non_repo", str(plain)), ("nonexistent", str(missing)), ("relative", "relative/u18")):
                rows = len(dialog_paths(page))
                start = len(log.requests)
                add_path(page, text, "button")
                refused, _ = settle(lambda: page.locator("#p-refusal").is_visible() or None)
                settle(lambda: posts_to(log, start, add_post) or None, 3.0, page)
                rec.check(f"ui.{label}_refusal_shown", bool(refused), "#p-refusal visible", text_of(page.locator("#p-refusal")))
                rec.equal(f"ui.{label}_adds_no_row", rows, len(dialog_paths(page)))
                shots(page, f"2-{label}")
            repos = project_repos(projects.client, pid)
            first = next((r for r in repos if str(r["root_path"]).endswith("u18-one")), None)
            if first is None:
                raise Blocked("the first added repo is not in list_repos")
            first_id = str(first["repo_id"])
            page.locator(f"#p-paths button[data-repo-id='{first_id}']").click()
            gone, _ = settle(lambda: not any(p.endswith("u18-one") for p in dialog_paths(page)) or None)
            rec.check("ui.remove_takes_the_row_away", bool(gone), "no u18-one row", dialog_paths(page))
            add_path(page, str(one), "enter")
            back, _ = settle(lambda: any(p.endswith("u18-one") for p in dialog_paths(page)) or None)
            rec.check("ui.re_add_brings_it_back", bool(back), "a u18-one row again", dialog_paths(page))
            shots(page, "3-readded")
            readded = next((r for r in project_repos(projects.client, pid) if str(r["root_path"]).endswith("u18-one")), None)

            def refuse(route: Route) -> None:
                route.fulfill(status=400, content_type="application/json", body=REFUSED_ENVELOPE)

            page.route(f"**{remove_post}", refuse)
            if readded is not None:
                page.locator(f"#p-paths button[data-repo-id='{readded['repo_id']}']").click()
                settle(lambda: page.locator("#p-refusal").is_visible() or None, 3.0)
                rec.check("ui.refused_remove_keeps_the_row", any(p.endswith("u18-one") for p in dialog_paths(page)),
                          "the u18-one row remains", dialog_paths(page))
                rec.check("ui.refused_remove_shows_a_refusal", page.locator("#p-refusal").is_visible(),
                          "a visible refusal (derived)", text_of(page.locator("#p-refusal")))
            else:
                rec.block("ui.refused_remove_keeps_the_row", "the re-added repo is not in list_repos")
            page.unroute(f"**{remove_post}", refuse)
            shots(page, "4-refused-remove")
            start = len(log.requests)
            add_path(page, str(three), "double")
            settle(lambda: len(posts_to(log, start, add_post)) >= 1 or None, 3.0, page)
            settle(lambda: any(p.endswith("u18-three") for p in dialog_paths(page)) or None)
            rec.equal("ui.double_click_leaves_one_row", 1, len([p for p in dialog_paths(page) if p.endswith("u18-three")]))
            rec.record("api.double_click_add_posts", len(posts_to(log, start, add_post)))
            shots(page, "5-double")
            stored = sorted(str(r["root_path"]) for r in project_repos(projects.client, pid))
            rec.equal("db.repo_rows_match_the_dialog", stored, sorted(dialog_paths(page)))
            rec.record("logs.console_errors", [e["text"][:120] for e in log.console_errors()])
    finally:
        for repo in project_repos(projects.client, pid):
            if str(repo["repo_id"]) not in original:
                projects.client.remove_repo(pid, str(repo["repo_id"]))
    rec.note(shots.note())
    rec.finish()


# ----- U19 -------------------------------------------------------------------------------


def open_delete(page: Page) -> None:
    page.locator("#proj-delete").click()
    await_env(lambda: dialog_open(page, "#dlg-delete") or None, UI_BOUND_S, "the delete dialog")


def choices(page: Page) -> dict[str, bool]:
    value = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#dlg-delete-choices .dlg-choice')]"
                          ".map(c => [c.dataset.choice, !c.disabled]))")
    return {str(k): bool(v) for k, v in value.items()} if isinstance(value, dict) else {}


def owned_project(projects: Projects, name: str) -> tuple[str, str, Path]:
    repo = new_repo(projects.root, name.lower().replace(" ", "-"))
    pid = create_project(projects.client, name)
    add_repo(projects.client, pid, repo)
    session = spawn_owned(projects.client, pid, repo, f"{name} owned")
    projects.owned.append(session)
    return pid, session, repo


@scenario("U19")
def test_u19_delete_dialog_every_choice(projects: Projects, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U19")
    client = projects.client
    k = projects.controld.root.k
    repo_a = new_repo(projects.root, "u19-a")
    del_a = create_project(client, "QA6 Del A")
    add_repo(client, del_a, repo_a)
    ended = attach(projects.pool, projects.controld, repo_a, "QA6 Del A ended", state="running")
    ended.helper.end()
    await_env(lambda: session_api(client, ended.session_id).get("state") == "stopped" or None, 10.0, "the Del A session ended")
    del_b, owned_b, _repo_b = owned_project(projects, "QA6 Del B")
    del_d, owned_d, _repo_d = owned_project(projects, "QA6 Del D")
    repo_e = new_repo(projects.root, "u19-e")
    del_e = create_project(client, "QA6 Del E")
    add_repo(client, del_e, repo_e)
    attach(projects.pool, projects.controld, repo_e, "QA6 Del E attached", state="running")
    with browser_session.context("U19", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, projects.port)
        bodies = record_posts(page)
        open_projects(page)
        # (a)
        open_row(page, del_a)
        open_delete(page)
        rec.equal("ui.a_title", "Delete QA6 Del A", text_of(page.locator("#dlg-delete-title")))
        rec.check("ui.a_identity", del_a in (page.locator("#dlg-delete-identity").text_content() or ""), "the project id",
                  page.locator("#dlg-delete-identity").text_content())
        rec.check("ui.a_session_count", "1 session record" in text_of(page.locator("#dlg-delete-body")),
                  "names 1 session record", text_of(page.locator("#dlg-delete-body")))
        rec.check("ui.a_doomed_list", ended.session_id in (page.locator("#dlg-delete-doomed").text_content() or ""),
                  "the doomed list names the ended session", page.locator("#dlg-delete-doomed").text_content())
        shots(page, "a-1-dialog")
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        gone, _ = settle(lambda: text_of(page.locator("#dlg-delete-body")) == "The project is gone." or None)
        rec.check("ui.a_gone_sentence", bool(gone), "The project is gone.", text_of(page.locator("#dlg-delete-body")))
        rec.check("ui.a_dialog_stays_until_cancel", dialog_open(page, "#dlg-delete"), "still open", dialog_open(page, "#dlg-delete"))
        shots(page, "a-2-gone")
        page.locator("#dlg-delete-cancel").click()
        closed, _ = settle(lambda: not dialog_open(page, "#dlg-delete") or None)
        rec.check("ui.a_cancel_closes", bool(closed), "closed", dialog_open(page, "#dlg-delete"))
        settle(lambda: del_a not in row_ids(page) or None)
        rec.check("ui.a_row_gone", del_a not in row_ids(page), "no row", row_ids(page))
        rec.equal("api.a_one_delete_empty_body", [{}], bodies.of(f"/api/projects/{del_a}/delete"))
        # (b) refused, then "Wait"
        open_row(page, del_b)
        open_delete(page)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        offered, _ = settle(lambda: set(choices(page)) == {"kill_sessions", "orphan", "cancel"} or None)
        rec.check("ui.b_three_choices", bool(offered), "kill_sessions, orphan, cancel", choices(page))
        shots(page, "b-1-refused")
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=cancel]").click()
        closed, _ = settle(lambda: not dialog_open(page, "#dlg-delete") or None)
        rec.check("ui.b_wait_closes", bool(closed), "closed", dialog_open(page, "#dlg-delete"))
        rec.check("ui.b_project_remains", del_b in row_ids(page) and del_b in project_ids_named(client, "QA6 Del B"),
                  "the row and the project remain", row_ids(page))
        rec.equal("api.b_one_refused_delete_then_nothing", [{}], bodies.of(f"/api/projects/{del_b}/delete"))
        # (c) kill_sessions
        open_delete(page)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        settle(lambda: "kill_sessions" in choices(page) or None)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=kill_sessions]").click()
        gone, _ = settle(lambda: text_of(page.locator("#dlg-delete-body")) == "The project is gone." or None)
        rec.check("ui.c_deleted", bool(gone), "The project is gone.", text_of(page.locator("#dlg-delete-body")))
        rec.equal("api.c_kill_sessions_body", [{}, {}, {"on_running": "kill_sessions"}], bodies.of(f"/api/projects/{del_b}/delete"))
        pane_gone, _ = settle(lambda: not pane_alive(projects.run, k, owned_b) or None)
        rec.check("tmux.c_pane_gone", bool(pane_gone), "the pane gone", pane_alive(projects.run, k, owned_b))
        shots(page, "c-deleted")
        page.locator("#dlg-delete-cancel").click()
        # (d) orphan
        settle(lambda: del_d in row_ids(page) or None)
        open_row(page, del_d)
        open_delete(page)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        settle(lambda: "orphan" in choices(page) or None)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=orphan]").click()
        gone, _ = settle(lambda: text_of(page.locator("#dlg-delete-body")) == "The project is gone." or None)
        rec.check("ui.d_deleted", bool(gone), "The project is gone.", text_of(page.locator("#dlg-delete-body")))
        rec.equal("api.d_orphan_body", [{}, {"on_running": "orphan"}], bodies.of(f"/api/projects/{del_d}/delete"))
        page.locator("#dlg-delete-cancel").click()
        go(page, "flock", drawer=False)
        page.locator("#flock-projects .project[data-project-id=unassigned]").click()
        card, _ = settle(lambda: page.locator(f"#flock-cards .card[data-session-id='{owned_d}']").count() == 1 or None)
        rec.check("ui.d_card_under_unassigned", bool(card), "the orphaned session's card in Unassigned",
                  page.locator("#flock-cards").text_content())
        rec.check("tmux.d_pane_alive", pane_alive(projects.run, k, owned_d), "alive", pane_alive(projects.run, k, owned_d))
        shots(page, "d-unassigned")
        # (e) attached only: kill_sessions disabled; (f) Escape
        open_projects(page)
        open_row(page, del_e)
        open_delete(page)
        page.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        settle(lambda: "kill_sessions" in choices(page) or None)
        rec.equal("ui.e_kill_sessions_disabled", False, choices(page).get("kill_sessions"))
        shots(page, "e-refused")
        page.keyboard.press("Escape")
        closed, _ = settle(lambda: not dialog_open(page, "#dlg-delete") or None)
        rec.check("ui.f_escape_closes", bool(closed), "closed", dialog_open(page, "#dlg-delete"))
        rec.equal("logs.console_errors", [], log.console_errors())
    kill_owned(client, owned_d)
    rec.note(shots.note())
    rec.finish()


# ----- U20 -------------------------------------------------------------------------------


@scenario("U20")
def test_u20_delete_in_one_tab_act_in_another(projects: Projects, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U20")
    client = projects.client
    q = create_project(client, "QA6 U20 Q")
    mark = projects.stream.mark()
    with browser_session.context("U20", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        tab_a = open_app(context, projects.port)
        tab_b = open_app(context, projects.port)
        for tab in (tab_a, tab_b):
            open_projects(tab)
            open_row(tab, q)
        tab_a.bring_to_front()
        open_delete(tab_a)
        tab_a.locator("#dlg-delete-choices .dlg-choice[data-choice=delete]").click()
        settle(lambda: text_of(tab_a.locator("#dlg-delete-body")) == "The project is gone." or None)
        tab_a.locator("#dlg-delete-cancel").click()
        started = projects.stream.since(mark)
        lost, elapsed = settle(lambda: q not in row_ids(tab_b) or None, 5.0)
        rec.check("ui.b_list_loses_the_row_within_5s", bool(lost), "B's list without Q within 5 s (SSE)",
                  {"b_rows": row_ids(tab_b), "elapsed": round(elapsed, 2), "a_rows_has_q": q in row_ids(tab_a)})
        shots(tab_b, "b-after")
        tab_b.bring_to_front()
        live_actions = tab_b.locator("#proj-edit").count() + tab_b.locator("#proj-delete").count()
        rec.equal("ui.b_offers_no_live_edit_or_delete_for_q", 0, live_actions)
        if tab_b.locator("#proj-edit").count():
            start = len(log.requests)
            tab_b.locator("#proj-edit").click()
            refused, _ = settle(lambda: tab_b.locator("#p-refusal").is_visible() or None, 3.0)
            rec.check("ui.b_edit_shows_a_refusal", bool(refused), "a visible refusal", text_of(tab_b.locator("#p-refusal")))
            rec.record("api.b_requests_after_edit", api_since(log, start))
        rec.equal("logs.page_errors_both_tabs", [], log.page_errors)
        rec.record("stream.frames_seen_during", [f.kind for f in started])
    deleted = [f for f in projects.stream.since(mark) if f.kind == "project.deleted" and f.project_id == q]
    rec.equal("stream.one_project_deleted", 1, len(deleted))
    rec.equal("db.q_gone", [], project_ids_named(client, "QA6 U20 Q"))
    rec.note(shots.note())
    rec.finish()


# ----- U21 -------------------------------------------------------------------------------


@scenario("U21")
def test_u21_a_projects_session_link_opens_it_in_the_flock(projects: Projects, browser_session: BrowserSession,
                                                           rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U21")
    session = projects.alpha_session
    title = str(session_api(projects.client, session.session_id).get("title"))
    with browser_session.context("U21", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, projects.port)
        open_projects(page)
        open_row(page, projects.alpha)
        link = page.locator(f"#proj-detail a.mini-open[data-session-id='{session.session_id}']")
        start = len(log.requests)
        link.click()
        shown, _ = settle(lambda: is_showing(page, "flock") and text_of(page.locator("#session-title")) == title or None)
        rec.check("ui.flock_shows_the_session", bool(shown), f"Flock visible, #session-title == {title!r}",
                  {"nav": nav_state(page).as_json(), "title": text_of(page.locator("#session-title"))})
        reads = [c for c in api_since(log, start, "GET") if c == f"GET /api/sessions/{session.session_id}"]
        rec.equal("api.get_session_once", 1, len(reads))
        shots(page, "same-tab")
        go(page, "projects", drawer=False)
        link = page.locator(f"#proj-detail a.mini-open[data-session-id='{session.session_id}']")
        pages_before = len(context.pages)
        link.click(modifiers=["Meta"])
        opened, _ = settle(lambda: len(context.pages) > pages_before or None, 5.0)
        if opened:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("load")
            settle(lambda: new_page.locator("#nav-chat").get_attribute("aria-current") is not None or None)
            rec.record("ui.new_tab_visible_root", {"url": new_page.url, "nav": nav_state(new_page).as_json()})
            shots(new_page, "new-tab")
        else:
            # A finding, recorded (no deep links; app.js's delegated handler calls preventDefault).
            rec.record("ui.new_tab_visible_root", {"new_tab_opened": False, "same_tab_after_meta_click": nav_state(page).as_json()})
            shots(page, "meta-click-same-tab")
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()
