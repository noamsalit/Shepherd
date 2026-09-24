"""Wave 6, SUB lane: Settings — U22 (all ten sections), U23 (the autonomy toggle lives
only here), U24 (a refused or unreachable autonomy change is visible).

One SUB instance. U24's two faults are injected with `page.route` and labelled
(a 400 envelope, then an aborted request); every selection is a real click.
Each scenario leaves the level at 2 (the plan's Cleanup rows).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from ..auditprobe import AuditProbe
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld, app_state
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Recorder, await_env
from typing import TYPE_CHECKING

from .test_wave6_0_uikit import (
    ROOTS,
    SETTINGS_UNREACHABLE,
    UI_BOUND_S,
    Shots,
    go,
    open_app,
    record_posts,
    settle,
    text_of,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

ASK = "Ask me before anything leaves this machine"
AUTO = "Approve automatically"
SECTIONS = ("Account", "Notifications", "API keys", "Autonomy", "Shepherd", "Discovery", "Limits", "Users & access",
            "Data", "System")
UNBUILT = ("Account", "Notifications", "API keys", "Shepherd", "Limits", "Users & access")
BUILT_PANELS = ("Autonomy", "Discovery", "Data", "System")


@dataclass
class Settings:
    controld: Controld
    client: Client
    run: RunContext

    @property
    def port(self) -> int:
        return self.controld.port


@pytest.fixture(scope="module")
def settings(pool: InstancePool, qa6_run: RunContext) -> Iterator[Settings]:
    controld = pool.ready()
    client = controld.client
    client.create_project("QA6 Settings seed")
    yield Settings(controld=controld, client=client, run=qa6_run)


def level(client: Client) -> object:
    return client.get("/api/autonomy").data().get("level")


def open_section(page: Page, title: str) -> None:
    page.locator("#settings-nav .set-item", has_text=title).first.click()
    await_env(lambda: (page.locator("#settings-panel .col-head").text_content() or "").startswith(title) or None,
              UI_BOUND_S, f"Settings → {title}")


def option(page: Page, label: str) -> str | None:
    return page.locator("#settings-panel button.opt", has_text=label).get_attribute("aria-pressed")


# ----- U22 -------------------------------------------------------------------------------


@scenario("U22")
def test_u22_settings_all_ten_sections(settings: Settings, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U22")
    with browser_session.context("U22", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, settings.port)
        go(page, "settings", drawer=False)
        groups = [t.strip() for t in page.locator("#settings-nav .set-group").all_text_contents()]
        rec.equal("ui.groups", ["Yours", "This instance"], groups)
        for title in SECTIONS:
            open_section(page, title)
            item = page.locator("#settings-nav .set-item", has_text=title).first
            chip_in_nav = item.locator(".soon").count() == 1
            chip_in_panel = page.locator("#settings-panel .col-head .soon").count() == 1
            if title in UNBUILT:
                reason = (page.locator("#settings-panel .notbuilt span").text_content() or "").strip()
                rec.check(f"ui.unbuilt_chip_and_reason.{title}", chip_in_nav and chip_in_panel and len(reason) > 20,
                          "a 'not built' chip in the nav and the panel, and a reason sentence",
                          {"nav_chip": chip_in_nav, "panel_chip": chip_in_panel, "reason": reason[:120]})
            else:
                rec.check(f"ui.built_has_no_chip.{title}", not chip_in_nav and not chip_in_panel, "no chip",
                          {"nav_chip": chip_in_nav, "panel_chip": chip_in_panel})
            rec.check(f"ui.no_object_object.{title}", "[object Object]" not in (page.locator("#settings-panel").text_content() or ""),
                      "no [object Object]", (page.locator("#settings-panel").text_content() or "")[:200])
            shots(page, f"section-{title.replace(' ', '-').replace('&', 'and')}")
            if title == "Autonomy":
                labels = [t.strip() for t in page.locator("#settings-panel button.opt").all_text_contents()]
                rec.equal("ui.autonomy_two_options", [ASK, AUTO], labels)
            if title == "Discovery":
                hooks = as_dict(settings.client.fleet().get("discovery")).get("hooks")
                rec.equal("ui.discovery_hooks_equals_fleet", hooks,
                          (page.locator("#settings-panel .src-state").text_content() or "").strip())
            if title == "Data":
                page_rows = page.evaluate(
                    "() => [...document.querySelectorAll('#settings-panel .audit-row')].map(r =>"
                    " [...r.querySelectorAll('span')].map(s => s.textContent))")
                shown = [tuple(str(cell) for cell in row) for row in page_rows] if isinstance(page_rows, list) else []
                api = [as_dict(r) for r in as_list(settings.client.get("/api/audit").data().get("records"))]
                reads = {str(r.get("tool")) for r in api if r.get("blast_class") == "local_read"}
                expected = {(str(r.get("at")), str(r.get("tool")), str(r.get("decision")),
                             "—" if r.get("approved_by") is None else str(r.get("approved_by")))
                            for r in api if r.get("blast_class") != "local_read"}
                page_mutations = [row for row in shown if len(row) == 4 and row[1] not in reads]
                missing = [row for row in page_mutations if row not in expected]
                rec.check("ui.data_rows_match_audit_non_reads", bool(page_mutations) and not missing,
                          "every non-read row on the page is an /api/audit row (at, tool, decision, approved_by)",
                          {"page_non_read_rows": page_mutations[:5], "unmatched": missing[:5]})
            if title == "System":
                facts = [t.strip() for t in page.locator("#settings-panel dl.facts dt").all_text_contents()]
                rec.equal("ui.system_facts", ["server time", "sessions known", "unclassified stops"], facts)
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U23 -------------------------------------------------------------------------------


@scenario("U23")
def test_u23_the_autonomy_toggle_lives_only_in_settings(settings: Settings, browser_session: BrowserSession,
                                                        rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U23")
    audit = AuditProbe.for_instance(settings.controld.root)
    mark = audit.mark()
    try:
        with browser_session.context("U23", viewport=VIEWPORTS[DESKTOP]) as (context, log):
            page = open_app(context, settings.port)
            bodies = record_posts(page)
            go(page, "settings", drawer=False)
            open_section(page, "Autonomy")
            labels = [t.strip() for t in page.locator("#settings-panel button.opt").all_text_contents()]
            rec.equal("ui.labels_exact", [ASK, AUTO], labels)
            notes = [t.strip() for t in page.locator("#settings-panel .row-note").all_text_contents()]
            rec.check("ui.auto_option_says_still_logged", len(notes) == 2 and "audit log" in notes[1] and "still" in notes[1],
                      "the second option's note says auto-approved actions are still logged (O17)", notes)
            for step, (label, value) in enumerate(((AUTO, 3), (ASK, 2))):
                page.locator("#settings-panel button.opt", has_text=label).click()
                pressed, _ = settle(lambda: option(page, label) == "true" or None)
                rec.check(f"ui.aria_pressed_follows.{value}", bool(pressed), f"{label!r} aria-pressed true",
                          {ASK: option(page, ASK), AUTO: option(page, AUTO)})
                rec.equal(f"api.get_agrees.{value}", value, level(settings.client))
                rec.equal(f"db.level.{value}", value, app_state(settings.controld.db, "autonomy_level"))
                shots(page, f"{step}-level-{value}")
            rec.equal("api.posts_3_then_2", [{"level": 3}, {"level": 2}], bodies.of("/api/autonomy"))
            for name in ROOTS:
                if name == "settings":
                    continue
                go(page, name, drawer=False)
                root_text = page.locator(f"#page-{name}").text_content() or ""
                controls = page.locator(f"#page-{name} button.opt").count()
                rec.check(f"ui.no_autonomy_control_on.{name}", ASK not in root_text and AUTO not in root_text and controls == 0,
                          "neither label and no .opt", {"labels": [x for x in (ASK, AUTO) if x in root_text], "opts": controls})
            rec.equal("logs.console_errors", [], log.console_errors())
        rows = audit.records_for(mark, "set_autonomy_level")
        rec.equal("logs.audit_two_rows_claimed_human", ["claimed_human", "claimed_human"], [r.get("approved_by") for r in rows])
    finally:
        settings.client.post("/api/autonomy", {"level": 2})
    rec.note(shots.note())
    rec.finish()


# ----- U24 -------------------------------------------------------------------------------


REFUSED = '{"ok": false, "data": null, "error": "request failed", "correlation_id": "qa6-corr"}'


@scenario("U24")
def test_u24_a_refused_or_unreachable_autonomy_change_is_visible(settings: Settings, browser_session: BrowserSession,
                                                                 rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U24")
    rec.note("label: network faults via page.route (a 400 envelope, then an aborted request)")
    with browser_session.context("U24", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, settings.port)
        go(page, "settings", drawer=False)
        open_section(page, "Autonomy")
        before = option(page, AUTO)

        def refuse(route: Route) -> None:
            if route.request.method == "POST":
                route.fulfill(status=400, content_type="application/json", body=REFUSED)
            else:
                route.continue_()

        page.route("**/api/autonomy", refuse)
        page.locator("#settings-panel button.opt", has_text=AUTO).click()
        shown, _ = settle(lambda: "qa6-corr" in (page.locator("#page-settings").text_content() or "") or None, 3.0)
        rec.check("ui.refusal_visible_with_correlation_id", bool(shown), "a visible refusal containing qa6-corr (S8)",
                  text_of(page.locator("#settings-note")))
        rec.equal("ui.aria_pressed_unchanged", before, option(page, AUTO))
        shots(page, "1-refused")
        page.unroute("**/api/autonomy", refuse)

        def abort(route: Route) -> None:
            if route.request.method == "POST":
                route.abort()
            else:
                route.continue_()

        page.route("**/api/autonomy", abort)
        page.locator("#settings-panel button.opt", has_text=AUTO).click()
        note, _ = settle(lambda: text_of(page.locator("#settings-note")) == SETTINGS_UNREACHABLE or None, 3.0)
        rec.check("ui.unreachable_note", bool(note), SETTINGS_UNREACHABLE, text_of(page.locator("#settings-note")))
        shots(page, "2-unreachable")
        page.unroute("**/api/autonomy", abort)
        rec.equal("api.level_still_2", 2, level(settings.client))
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()
