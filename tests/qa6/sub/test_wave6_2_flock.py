"""Wave 6, SUB lane: the Flock and the session pane — U7-U14, U41, U42, U43, U45.

This is env-plan §1's "U7/U11/U12 module": one SUB instance with its own named
sessiond **SD-W6**, started at module setup and ready by exactly one probe frame
naming the seeded target `QA6-U-TARGET`, and stopped at module teardown, where
its stop line must read `delivered - 1 == 6` (the six D12-style seed frames).

The seed, all through the product's front doors:

* attached sessions (a harness `sleep` + a sidecar in the captured key set,
  sessions.py; G5) in Unassigned: the running target, a waiting one, and six
  stopped by real-shape hook frames through the product's own dispatch argv —
  finished (`Stop`), truncated, rate_limited, auth_failed, account_blocked,
  bad_request (captures from docs/probes, one field substituted where the
  capture has no such value, exactly as D12) — plus one whose process exits
  with no frame at all (the `unknown` bucket);
* owned fake-engine sessions spawned by `POST /api/sessions` in project
  `Alpha7` (U10's terminal; U11's `killed`) and `Dlg` (U14).

U10, U11 and U14 are SHIM-DEPENDENTS. U14 is labelled **fixture-fiction** for the
session state (a harness sidecar marks the owned session waiting); the parser's
input is the real captured dialog bytes the shim prints.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from shepherd.core.stops import PALETTE, Bucket
from shepherd.host.mac import MacHost

from .. import paths
from ..auditprobe import AuditProbe
from ..browser import BrowserSession, PageLog
from ..constants import DESKTOP, VIEWPORTS
from ..hookrig import captured, copy_transcript, dispatch_argv, frame, send, start_ready_sessiond
from ..httpclient import Client, as_dict
from ..instance import Controld, SessiondManager, SessiondRun, last_scan_at
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sessions import sidecar, write_sidecar
from ..sse_rig import Subscriber, subscribe
from ..verdict import Blocked, CONTROL_MULTIPLE, Recorder, await_env
from .test_wave6_0_uikit import (
    READ_ONLY_BANNER,
    ROOTS,
    UI_BOUND_S,
    Attached,
    Shots,
    active as focused,
    add_repo,
    api_since,
    attach,
    capture_pane,
    computed,
    create_project,
    document_text,
    go,
    js_number,
    kill_owned,
    new_repo,
    open_app,
    pane_alive,
    posts_to,
    press_tab_until,
    rewrite,
    send_line,
    session_api,
    session_title,
    settle,
    spawn_owned,
    text_of,
    tree_sessions,
    wait_until,
    xss_fired,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page, WebSocket

TARGET_NAME = "QA6-U-TARGET"
#: (key, event, capture dir, substitution) — D12's rows for the buckets U7/U11/U12 need.
SEED_FRAMES: tuple[tuple[str, str, str, dict[str, object]], ...] = (
    ("finished", "Stop", "S01_startup_tools", {}),
    ("truncated", "StopFailure", "S08_mock_max_tokens", {}),
    ("rate_limited", "StopFailure", "S08_mock_http429", {}),
    ("auth_failed", "StopFailure", "S08_mock_http401", {}),
    ("account_blocked", "StopFailure", "S08_mock_http429", {"error": "account_on_hold"}),
    ("bad_request", "StopFailure", "S08_mock_prompt_too_long", {}),
)
WAITING_ASK = "permission: Bash(git push)"
XSS = "<img src=x onerror=window.__xss=1>"
#: U11's labels, verbatim from the plan's reading of `DEFAULT_ACTIONS` (stop_rules.py:89-150).
U11_EXPECTED: dict[str, list[tuple[str, str]]] = {
    "killed": [("Re-spawn with the remaining brief", "respawn")],
    "rate_limited": [("Resumes by itself — nothing to do", "none"), ("Retry now", "retry")],
    "auth_failed": [("Re-authenticate", "reauth")],
    "account_blocked": [("Check billing", "external")],
    "bad_request": [("Inspect the request — model or args rejected", "inspect")],
    "truncated": [("Resume — output hit the token cap", "resume")],
}
NOT_BUILT_KINDS = frozenset({"respawn", "retry", "reauth", "resume"})
LIVE_KINDS = frozenset({"none", "inspect", "external"})
#: U14's capture record: what the TUI showed (docs/probes, read-only).
DIALOG_ROW = paths.DIALOG_CAPTURE.parent / "04d-1-row.json"
#: U10's plan bound for the typed keystroke to reach the pane.
TYPED_BOUND_S = 3.0


@dataclass
class Flock:
    controld: Controld
    client: Client
    run: RunContext
    pool: InstancePool
    stream: Subscriber
    manager: SessiondManager
    sessiond: SessiondRun
    argv: list[str]
    target: Attached
    alpha: str
    alpha_repo: Path
    stopped: dict[str, Attached] = field(default_factory=dict)
    waiting: Attached | None = None
    unknown: Attached | None = None
    owned: str = ""
    extra: dict[str, Attached] = field(default_factory=dict)
    owned_all: list[str] = field(default_factory=list)

    @property
    def port(self) -> int:
        return self.controld.port


def seed_stops(flock: Flock) -> None:
    loose = flock.run.repos / "loose"
    for key, event, directory, substitution in SEED_FRAMES:
        session = attach(flock.pool, flock.controld, loose, f"QA6 U7 {key.replace('_', ' ')}", state="running")
        transcript = copy_transcript(flock.controld.root.cfg, session.engine_id)
        payload = frame(captured(directory, event), session_id=session.engine_id, cwd=str(loose),
                        transcript_path=str(transcript), **substitution)
        sent = send(flock.argv, flock.controld.env, payload)
        if sent.rc != 0:
            raise Blocked(f"SD-W6 seed {key}: the dispatch exited {sent.rc}: {sent.stderr[:200]!r}")
        await_env(lambda: session_api(flock.client, session.session_id).get("decided_by") or None, 10.0,
                  f"SD-W6 seed {key}: a verdict")
        session.helper.end()
        flock.stopped[key] = session
    flock.waiting = attach(flock.pool, flock.controld, loose, "QA6 U7 waiting", status="waiting",
                           waiting_for=WAITING_ASK, state="needs_you")
    unknown = attach(flock.pool, flock.controld, loose, "QA6 U7 no verdict", state="running")
    unknown.helper.end()
    await_env(lambda: session_api(flock.client, unknown.session_id).get("state") == "stopped" or None, 10.0,
              "the frameless session stopped")
    flock.unknown = unknown


@pytest.fixture(scope="module")
def flock(pool: InstancePool, qa6_run: RunContext) -> Iterator[Flock]:
    controld = pool.ready()
    client = controld.client
    loose = qa6_run.repos / "loose"
    target = attach(pool, controld, loose, TARGET_NAME, state="running")
    argv, _settings = dispatch_argv(controld)
    manager = pool.sessiond(controld)
    run_sd, _latency = start_ready_sessiond(manager, "SD-W6", argv=argv, target_engine_id=target.engine_id,
                                            target_cwd=str(loose))
    repo = new_repo(controld.root.root, "alpha7")
    alpha = create_project(client, "Alpha7")
    add_repo(client, alpha, repo)
    stream = subscribe("U-flock", controld.port)
    state = Flock(controld=controld, client=client, run=qa6_run, pool=pool, stream=stream, manager=manager,
                  sessiond=run_sd, argv=argv, target=target, alpha=alpha, alpha_repo=repo)
    try:
        seed_stops(state)
        state.owned = spawn_owned(client, alpha, repo, "QA6 U10 owned")
        state.owned_all.append(state.owned)
        for name in ("U9", "U13", "U41", "U45"):
            state.extra[name] = attach(pool, controld, loose, f"QA6 {name} attached", state="running")
        yield state
    finally:
        stream.close()
        for session_id in state.owned_all:
            if pane_alive(qa6_run, controld.root.k, session_id):
                kill_owned(client, session_id)
        manager.stop(run_sd)
        counts = run_sd.counts()
        if counts is None or counts["delivered"] - 1 != len(SEED_FRAMES):
            qa6_run.teardown_problem("SD-W6", f"stop line {run_sd.stop_line!r}: delivered - 1 != {len(SEED_FRAMES)} seed frames")


def open_flock_project(page: Page, project_id: str) -> None:
    go(page, "flock", drawer=False)
    page.locator(f"#flock-projects .project[data-project-id='{project_id}']").click()
    await_env(lambda: page.locator("#flock-cards .card").count() > 0 or None, UI_BOUND_S, f"cards of {project_id}")


def open_card(page: Page, session_id: str) -> None:
    page.locator(f"#flock-cards .card[data-session-id='{session_id}']").click()
    await_env(lambda: page.locator("#session-view").is_visible()
              and page.locator(f"#flock-cards .card[data-session-id='{session_id}']").get_attribute("aria-current") == "true"
              or None, UI_BOUND_S, f"the session pane for {session_id}")


def cards(page: Page) -> list[dict[str, str]]:
    value = page.evaluate(
        "() => [...document.querySelectorAll('#flock-cards .card')].map(c => ({id: c.dataset.sessionId,"
        " cls: c.className, colour: getComputedStyle(c).getPropertyValue('--bucket-colour').trim(),"
        " glyph: (c.querySelector('.card-mark') || {}).textContent || '', title: (c.querySelector('.card-title') || {}).textContent || '',"
        " age: (c.querySelector('.card-age') || {}).textContent || '', ask: (c.querySelector('.card-ask') || {}).textContent || '',"
        " text: c.innerText, current: c.getAttribute('aria-current') || ''}))"
    )
    return [{str(k): str(v) for k, v in item.items()} for item in value] if isinstance(value, list) else []


def bucket_of_class(cls: str) -> str:
    found = re.search(r"\bbucket-([a-z_]+)\b", cls)
    return found.group(1) if found else ""


def rgb(hex_colour: str) -> str:
    value = hex_colour.lstrip("#")
    return f"rgb({int(value[0:2], 16)}, {int(value[2:4], 16)}, {int(value[4:6], 16)})"


# ----- U7 --------------------------------------------------------------------------------


@scenario("U7")
def test_u7_bucket_colours_glyphs_and_the_new_vocabulary(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U7")
    expected_present = {"running", "needs_you", "finished", "unfinished", "paused", "error", "unclassified"}
    with browser_session.context("U7", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        shots(page, "unassigned")
        shown = cards(page)
        buckets = {bucket_of_class(card["cls"]) for card in shown}
        rec.check("given.seven_buckets_present", expected_present <= buckets, sorted(expected_present), sorted(buckets))
        for card in shown:
            bucket = bucket_of_class(card["cls"])
            if bucket not in {b.value for b in Bucket}:
                rec.check(f"ui.card_bucket_known.{card['id']}", False, "a .bucket-* class", card["cls"])
                continue
            style = PALETTE[Bucket(bucket)]
            rec.equal(f"ui.card_colour.{bucket}.{card['id'][-6:]}", style.colour.lower(), card["colour"].lower())
            rec.equal(f"ui.card_glyph.{bucket}.{card['id'][-6:]}", style.glyph, card["glyph"].strip())
        keys = page.locator(".legend-key[data-bucket]")
        labels: list[str] = []
        for index in range(keys.count()):
            key = keys.nth(index)
            bucket = str(key.get_attribute("data-bucket"))
            style = PALETTE[Bucket(bucket)]
            labels.append((key.locator(".legend-label").text_content() or "").strip())
            rec.equal(f"ui.legend_text_colour.{bucket}", rgb(style.colour), computed(key, "color"))
            rec.equal(f"ui.legend_glyph_colour.{bucket}", rgb(style.colour), computed(key.locator(".legend-mark"), "color"))
        rec.equal("ui.visible_labels", ["needs you", "error", "stranded", "running", "limit exceeded", "blocked", "finished",
                                        "unknown"], labels)
        body = document_text(page)
        banned = [word for word in ("Herd", "unfinished", "paused", "unclassified")
                  if re.search(rf"\b{word}\b", body, flags=re.IGNORECASE)]
        rec.check("ui.no_retired_vocabulary", not banned, "none of Herd/unfinished/paused/unclassified as visible text", banned)
        api = {str(row["session_id"]): str(row["bucket"]) for row in tree_sessions(flock.client, "unassigned")}
        dom = {card["id"]: bucket_of_class(card["cls"]) for card in shown}
        rec.equal("api.fleet_buckets_agree_with_cards", api, dom)
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    rec.note(shots.note())
    rec.finish()


# ----- U8 --------------------------------------------------------------------------------


def malformed(client: Client) -> int:
    value = as_dict(client.fleet().get("anomalies")).get("malformed_payload")
    return int(value) if isinstance(value, int) else -1


@scenario("U8")
def test_u8_a_card_carries_exactly_four_things_relative_time(flock: Flock, browser_session: BrowserSession,
                                                             rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U8")
    repo = new_repo(flock.controld.root.root, "times")
    times = create_project(flock.client, "QA6 Times")
    add_repo(flock.client, times, repo)
    before = malformed(flock.client)
    ages = {"now": 0.0, "2 min": 120.0, "11 days": 11 * 86400.0, "400 days": 400 * 86400.0}
    expected = {"now": "just now", "2 min": "2 minutes ago", "11 days": "11 days ago", "400 days": "1 year ago"}
    seeded: dict[str, Attached] = {}
    for label, age in ages.items():
        seeded[label] = attach(flock.pool, flock.controld, repo, f"QA6 U8 {label}", status_age_s=age, started_age_s=age)
    helper = flock.pool.helper()
    no_start = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(repo), name="QA6 U8 no startedAt",
                       drop=("startedAt",))
    write_sidecar(flock.controld.root.sessions, no_start)
    risen, _ = settle(lambda: malformed(flock.client) != before or None, 8.0)
    # "Rises by 1" is a claim about the one file, so it must still hold two scan
    # passes later (the sourced 2.0 s cadence, observed through last_scan_at).
    for _ in range(2):
        seen = last_scan_at(flock.controld.db)
        await_env(lambda: last_scan_at(flock.controld.db) != seen or None, 6.0, "a discovery pass")
    rec.check("api.malformed_payload_rises_by_1", bool(risen) and malformed(flock.client) == before + 1,
              f"{before} + 1, and still after two more scan passes", malformed(flock.client))
    with browser_session.context("U8", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, times)
        shots(page, "times")
        shown = {card["id"]: card for card in cards(page)}
        for label, session in seeded.items():
            card = shown.get(session.session_id)
            rec.equal(f"ui.relative_time.{label}", expected[label], card["age"].strip() if card else None)
        rec.equal("ui.no_card_for_the_timestamp_less_sidecar", 4, len(shown))
        rec.check("ui.no_card_titled_no_startedAt", all("no startedAt" not in c["title"] for c in shown.values()),
                  "absent (§0 rule 3)", [c["title"] for c in shown.values()])
        forbidden = re.compile(r"\b(sonnet|opus|haiku|owned|attached)\b|[0-9A-Z]{26}|/private/tmp|/tmp/", re.IGNORECASE)
        leaks = {c["title"]: forbidden.findall(c["text"]) for c in shown.values() if forbidden.search(c["text"])}
        rec.check("ui.card_carries_no_model_ownership_id_or_path", not leaks, "none", leaks)
        api_rows = {str(r["session_id"]): r for r in tree_sessions(flock.client, times)}
        with_ask = [c["title"] for c in shown.values() if c["ask"].strip()]
        needs_you = [c["title"] for c in shown.values() if api_rows.get(c["id"], {}).get("bucket") == "needs_you"]
        rec.check("ui.ask_only_on_needs_you_cards", set(with_ask) <= set(needs_you), f"asks only on {needs_you}", with_ask)
        rec.record("api.states", {str(r.get("title")): (r.get("state"), r.get("bucket"), r.get("last_event_at"))
                                  for r in api_rows.values()})
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U9 --------------------------------------------------------------------------------


@scenario("U9")
def test_u9_drill_to_an_attached_session_header_banner_three_panes(flock: Flock, browser_session: BrowserSession,
                                                                   rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U9")
    session = flock.extra["U9"]
    with browser_session.context("U9", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        before = {c["id"]: c["current"] for c in cards(page)}
        start = len(log.requests)
        open_card(page, session.session_id)
        shots(page, "open")
        rec.equal("ui.session_title", "QA6 U9 attached", text_of(page.locator("#session-title")))
        rec.equal("ui.session_ownership", "attached", text_of(page.locator("#session-ownership")))
        rec.equal("ui.session_banner", READ_ONLY_BANNER, text_of(page.locator("#session-banner")))
        panes = {name: page.locator(selector).is_visible() for name, selector in
                 (("projects", ".col-projects"), ("sessions", ".col-sessions"), ("detail", "#flock-detail"))}
        rec.equal("ui.three_panes_at_1280", {"projects": True, "sessions": True, "detail": True}, panes)
        after = {c["id"]: c["current"] for c in cards(page)}
        changed = sorted(sid for sid in after if after[sid] != before.get(sid))
        rec.equal("ui.only_the_current_card_changes", [session.session_id], changed)
        reads = [call for call in api_since(log, start, "GET") if call.startswith(f"GET /api/sessions/{session.session_id}")]
        rec.equal("api.get_session_once", [f"GET /api/sessions/{session.session_id}"], reads)
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U10 -------------------------------------------------------------------------------


def xterm_text(page: Page) -> str:
    return str(page.evaluate("() => (document.querySelector('#session-terminal .xterm-rows') || {}).innerText || ''"))


@scenario("U10")
def test_u10_an_owned_sessions_live_terminal_typing_and_the_degraded_path(flock: Flock, browser_session: BrowserSession,
                                                                         rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U10")
    k = flock.controld.root.k
    session_id = flock.owned
    if not pane_alive(flock.run, k, session_id):
        raise Blocked("the owned fake-engine pane is not alive")
    with browser_session.context("U10", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = context.new_page()
        ws_bytes: list[bytes] = []

        def on_socket(socket: WebSocket) -> None:
            socket.on("framereceived", lambda payload: ws_bytes.append(payload if isinstance(payload, bytes) else payload.encode()))

        page.on("websocket", on_socket)
        page.goto(f"http://127.0.0.1:{flock.port}/", wait_until="load")
        await_env(lambda: page.locator("#flock-projects .project").count() > 0 or None, UI_BOUND_S, "first paint")
        open_flock_project(page, flock.alpha)
        open_card(page, session_id)
        screen = page.locator("#session-terminal .xterm-screen")
        shown, _ = settle(lambda: screen.is_visible() or None)
        rec.check("ui.xterm_screen_visible", bool(shown), ".xterm-screen visible", shown)
        cols = page.locator("#session-terminal").get_attribute("data-terminal-cols")
        rows = page.locator("#session-terminal").get_attribute("data-terminal-rows")
        rec.check("ui.terminal_geometry", (cols or "0").isdigit() and (rows or "0").isdigit() and int(cols or 0) > 0
                  and int(rows or 0) > 0, "data-terminal-cols/rows > 0", (cols, rows))
        wire, wire_s = settle(lambda: any(b"QA6-FAKE-CLAUDE" in chunk for chunk in ws_bytes) or None, page=page)
        rec.check("stream.snapshot_on_the_socket", bool(wire), "the WS snapshot carries QA6-FAKE-CLAUDE", len(ws_bytes))
        marker, _ = settle(lambda: "QA6-FAKE-CLAUDE" in xterm_text(page) or None)
        rec.check("ui.xterm_rows_show_the_marker", bool(marker), "the xterm DOM rows contain QA6-FAKE-CLAUDE",
                  {"rows_text": xterm_text(page)[:400], "ws_frames": len(ws_bytes), "wire_s": round(wire_s, 3)})
        shots(page, "1-opened")
        send_line(flock.run, k, session_id, "QA6-LIVE-LINE")
        live_wire, live_s = settle(lambda: any(b"QA6-LIVE-LINE" in chunk for chunk in ws_bytes) or None, page=page)
        rec.check("stream.live_chunk_on_the_socket", bool(live_wire), "a live WS chunk carries QA6-LIVE-LINE", len(ws_bytes))
        live, _ = settle(lambda: "QA6-LIVE-LINE" in xterm_text(page) or None)
        rec.check("ui.xterm_rows_show_the_live_line", bool(live), "the xterm DOM rows contain QA6-LIVE-LINE",
                  {"rows_text": xterm_text(page)[-400:], "live_wire_s": round(live_s, 3)})
        shots(page, "2-live-line")
        control_s = wait_until(lambda: "QA6-LIVE-LINE" in capture_pane(flock.run, k, session_id), 5.0,
                               "the harness's own line in capture-pane (the channel's control)")
        page.locator("#session-terminal").click()
        page.keyboard.type("QA6-TYPED")
        page.keyboard.press("Enter")
        typed, _ = settle(lambda: "QA6-TYPED" in capture_pane(flock.run, k, session_id) or None, TYPED_BOUND_S)
        if typed:
            rec.check("tmux.typed_reaches_the_pane", True, "QA6-TYPED in capture-pane within 3 s", True)
        elif TYPED_BOUND_S >= CONTROL_MULTIPLE * control_s:
            rec.fail_bound("tmux.typed_reaches_the_pane", "QA6-TYPED in capture-pane (C-19)", TYPED_BOUND_S,
                           f"the harness's send-keys line reached capture-pane in {control_s:.3f}s")
        else:
            rec.block("tmux.typed_reaches_the_pane", f"unqualified: control {control_s:.3f}s vs bound {TYPED_BOUND_S}s")
        shots(page, "3-after-typing")
        rec.equal("api.one_terminal_websocket", 1, len([w for w in log.websockets if w.endswith("/terminal")]))
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
    with browser_session.context("U10-degraded", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        context.route("**/static/vendor/xterm.js", lambda route: route.abort())
        page = open_app(context, flock.port)
        open_flock_project(page, flock.alpha)
        open_card(page, session_id)
        degraded, _ = settle(lambda: "QA6-FAKE-CLAUDE" in (page.locator("#session-terminal pre.terminal-screen").text_content() or "")
                             if page.locator("#session-terminal pre.terminal-screen").count() else None)
        rec.check("ui.degraded_pre_shows_the_marker", bool(degraded), "pre.terminal-screen contains QA6-FAKE-CLAUDE",
                  text_of(page.locator("#session-terminal"))[:300])
        output = [c for c in api_since(log, 0, "GET") if c.startswith(f"GET /api/sessions/{session_id}/output")]
        rec.check("api.degraded_reads_output", len(output) >= 1, "GET …/output", output)
        shots(page, "4-degraded")
    rec.note(shots.note())
    rec.finish()


# ----- U11 -------------------------------------------------------------------------------


def header_actions(page: Page) -> list[dict[str, object]]:
    value = page.evaluate(
        "() => [...document.querySelectorAll('#session-actions .session-action-row')].map(r => { const a = r.querySelector('.session-action');"
        " return {ordinal: (r.querySelector('.action-ordinal') || {}).textContent || '', source: (r.querySelector('.action-source') || {}).textContent || '',"
        " tag: a ? a.tagName.toLowerCase() : '', kind: a ? (a.dataset.kind || '') : '', label: a && a.firstChild ? a.firstChild.textContent : '',"
        " disabled: a ? !!a.disabled : null, badge: a ? !!a.querySelector('.action-badge') : null}; })"
    )
    return [dict(item) for item in value] if isinstance(value, list) else []


@scenario("U11")
def test_u11_next_actions_in_the_header_shown_labelled_inert(flock: Flock, browser_session: BrowserSession,
                                                            rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U11")
    killed = spawn_owned(flock.client, flock.alpha, flock.alpha_repo, "QA6 U11 killed")
    flock.owned_all.append(killed)
    answer = kill_owned(flock.client, killed)
    rec.check("given.killed_through_the_kill_route", answer.get("killed") is True, "killed: true", answer)
    targets: dict[str, tuple[str, str]] = {"killed": (flock.alpha, killed)}
    for key in ("rate_limited", "auth_failed", "account_blocked", "bad_request", "truncated"):
        targets[key] = ("unassigned", flock.stopped[key].session_id)
    audit = AuditProbe.for_instance(flock.controld.root)
    with browser_session.context("U11", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        for key, (project_id, session_id) in targets.items():
            open_flock_project(page, project_id)
            open_card(page, session_id)
            listed = header_actions(page)
            api = session_api(flock.client, session_id)
            raw_actions = api.get("next_actions")
            api_actions = [(str(a.get("text")), str(a.get("kind")), str(a.get("source")))
                           for a in (raw_actions if isinstance(raw_actions, list) else []) if isinstance(a, dict)]
            rec.equal(f"ui.header_equals_api.{key}", api_actions,
                      [(str(a["label"]), str(a["kind"] or ("external" if a["tag"] == "a" else "")), str(a["source"])) for a in listed])
            rec.equal(f"ui.labels_and_kinds.{key}", U11_EXPECTED[key], [(str(a["label"]), str(a["kind"])) for a in listed])
            rec.equal(f"ui.ordinals.{key}", [str(i + 1) for i in range(len(listed))], [str(a["ordinal"]) for a in listed])
            for action in listed:
                kind = str(action["kind"])
                if kind in NOT_BUILT_KINDS:
                    rec.check(f"ui.not_built_is_disabled_with_badge.{key}.{kind}", action["disabled"] is True and action["badge"] is True,
                              "disabled with a 'not yet' badge", action)
                elif kind in LIVE_KINDS:
                    rec.check(f"ui.live_kind_enabled.{key}.{kind}", action["disabled"] is False, "enabled", action)
            rec.equal(f"ui.no_action_link.{key}", 0, page.locator("#session-actions a.action-link").count())
            shots(page, f"{key}")
            mark = audit.mark()
            start = len(log.requests)
            before = text_of(page.locator("#session-view"))
            buttons = page.locator("#session-actions .session-action:not([disabled])")
            for index in range(buttons.count()):
                buttons.nth(index).click()
            rec.equal(f"api.no_mutating_request_from_clicks.{key}", [], api_since(log, start, "POST"))
            rec.equal(f"ui.clicks_change_no_state.{key}", before, text_of(page.locator("#session-view")))
            rec.equal(f"logs.no_mutation_audited.{key}", [], [r.get("tool") for r in audit.mutations_since(mark)])
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U12 -------------------------------------------------------------------------------


@scenario("U12")
def test_u12_the_why_note(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U12")
    session = flock.stopped["rate_limited"]
    api = session_api(flock.client, session.session_id)
    with browser_session.context("U12", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        open_card(page, session.session_id)
        note = page.locator("#session-actions details.why-note")
        rec.equal("ui.closed_before", False, note.evaluate("d => d.open"))
        note.locator("summary").click()
        opened, _ = settle(lambda: note.evaluate("d => d.open") is True or None, 3.0)
        rec.check("ui.opens_on_click", bool(opened), "details.why-note open", note.evaluate("d => d.open"))
        expected = f"decided by {api.get('decided_by')} · confidence {js_number(api.get('confidence'))}"
        rec.equal("ui.why_evidence_equals_api", expected, text_of(note.locator(".why-evidence")))
        shots(page, "open")
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U13 -------------------------------------------------------------------------------


def begin_rename(page: Page) -> None:
    page.locator("#session-rename").click()
    await_env(lambda: page.locator("#session-title input.session-rename-input").count() == 1 or None, UI_BOUND_S,
              "the rename input")


def answered(page: Page, log: PageLog, path: str, before: int) -> None:
    """Wait until the rename POST sent after `before` has been answered and painted."""
    settle(lambda: len(log.status_of(path)) > before
           and page.locator("#session-title input.session-rename-input").count() == 0 or None, 3.0, page)


@scenario("U13")
def test_u13_rename_by_click_to_edit_and_its_edge_cases(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U13")
    session = flock.extra["U13"]
    audit = AuditProbe.for_instance(flock.controld.root)
    mark = audit.mark()
    with browser_session.context("U13", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        open_card(page, session.session_id)
        rename_path = f"/api/sessions/{session.session_id}/rename"
        start = len(log.requests)
        begin_rename(page)
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.type("QA6 R1")
        page.keyboard.press("Enter")
        renamed, _ = settle(lambda: text_of(page.locator("#session-title")) == "QA6 R1" or None)
        rec.check("ui.renamed_r1", bool(renamed), "#session-title == 'QA6 R1'", text_of(page.locator("#session-title")))
        rec.check("ui.local_only_visible", page.locator("#session-local-only").is_visible(), "#session-local-only visible (attached)",
                  text_of(page.locator("#session-local-only")))
        settle(lambda: len(posts_to(log, start, rename_path)) >= 1 or None, 3.0, page)
        rec.equal("api.one_post_for_r1", 1, len(posts_to(log, start, rename_path)))
        shots(page, "1-r1")
        for attempt in (1, 2):
            begin_rename(page)
            page.keyboard.press("Escape")
            rec.equal(f"ui.escape_{attempt}_shows_current_title", "QA6 R1", text_of(page.locator("#session-title")))
            shots(page, f"2-escape-{attempt}")
        count = len(posts_to(log, start, rename_path))
        begin_rename(page)
        value = page.locator("#session-title input.session-rename-input").input_value()
        page.keyboard.press("Enter")
        settle(lambda: len(posts_to(log, start, rename_path)) > count or None, 3.0, page)
        answered(page, log, rename_path, count)
        rec.record("ui.enter_on_unchanged_title", {"input_value": value, "title_after": text_of(page.locator("#session-title")),
                                                   "status": text_of(page.locator("#session-rename-status")),
                                                   "posts": len(posts_to(log, start, rename_path)) - count})
        count = len(posts_to(log, start, rename_path))
        begin_rename(page)
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.press("Backspace")
        page.keyboard.press("Enter")
        settle(lambda: len(posts_to(log, start, rename_path)) > count or None, 3.0, page)
        answered(page, log, rename_path, count)
        rec.record("ui.empty_title_result", {"title": text_of(page.locator("#session-title")),
                                             "status": text_of(page.locator("#session-rename-status")),
                                             "db": session_title(flock.controld, session.session_id)})
        shots(page, "3-empty")
        count = len(posts_to(log, start, rename_path))
        begin_rename(page)
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.type("QA6 R2")
        page.keyboard.press("Enter")
        page.keyboard.press("Enter")
        settle(lambda: text_of(page.locator("#session-title")) == "QA6 R2" or None)
        settle(lambda: len(posts_to(log, start, rename_path)) >= count + 2 or None, 2.0, page)
        rec.equal("api.one_post_for_the_double_enter", 1, len(posts_to(log, start, rename_path)) - count)
        shots(page, "4-r2")
        rows = session_title(flock.controld, session.session_id)
        rec.equal("db.title_source_user", "user", rows.get("title_source"))
        total = len(posts_to(log, start, rename_path))
        rec.equal("logs.audit_row_per_post", total, len(audit.records_for(mark, "rename_session")))
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U14 -------------------------------------------------------------------------------


def captured_choices() -> list[tuple[str, str]]:
    decoded: object = json.loads(DIALOG_ROW.read_text(encoding="utf-8"))
    lines = decoded.get("dialog_lines") if isinstance(decoded, dict) else None
    found: list[tuple[str, str]] = []
    for line in lines if isinstance(lines, list) else []:
        match = re.match(r"^\s*(?:❯\s*)?(\d+)\.\s+(.*\S)\s*$", str(line))
        if match:
            found.append((match.group(1), match.group(2)))
    return found


def shown_choices(page: Page) -> list[tuple[str, str]]:
    value = page.evaluate(
        "() => [...document.querySelectorAll('#session-decision section.decision .choice')].map(r => ["
        " (r.querySelector('.choice-n') || {}).textContent || '', (r.querySelector('.choice-text') || {}).firstChild ?"
        " r.querySelector('.choice-text').firstChild.textContent : ''])"
    )
    return [(str(item[0]), str(item[1])) for item in value] if isinstance(value, list) else []


@scenario("U14")
def test_u14_the_needs_you_decision_card_and_choosing_one(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U14")
    rec.note("label: fixture-fiction for the session state (a harness sidecar marks the owned session waiting); "
             "the parser's input is the captured dialog bytes the shim prints (04a-1-dialog.ansi.txt)")
    client = flock.client
    repo = new_repo(flock.controld.root.root, "dlg")
    project = create_project(client, "QA6 Dlg")
    add_repo(client, project, repo)
    mode = flock.controld.root.home / ".qa6-shim-mode"
    mode.write_text("dialog", encoding="utf-8")
    try:
        session_id = spawn_owned(client, project, repo, "QA6 U14 dialog")
    finally:
        mode.unlink()
    flock.owned_all.append(session_id)
    k = flock.controld.root.k
    shown, _ = settle(lambda: "Do you want to proceed?" in capture_pane(flock.run, k, session_id) or None, 8.0)
    if not shown:
        raise Blocked("the shim's captured dialog never reached the pane")
    record = [json.loads(line) for line in flock.run.claude_argv_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    mine = [r for r in record if isinstance(r, dict) and "QA6 U14 dialog" in r.get("argv", [])]
    if not mine:
        raise Blocked("no fake-claude argv line for the U14 spawn")
    argv = [str(a) for a in mine[-1]["argv"]]
    engine = argv[argv.index("--session-id") + 1]
    pid = int(mine[-1]["pid"])
    liveness = MacHost().process_liveness(pid, None)
    if not liveness.alive or liveness.start_token is None:
        raise Blocked(f"the fake engine pid {pid} is not alive to the product's liveness probe")
    body = sidecar(pid=pid, proc_start=liveness.start_token, cwd=str(repo), session_id=engine, status="waiting",
                   waiting_for="permission: Bash(touch perm-1.txt)", name="QA6 U14 dialog")
    write_sidecar(flock.controld.root.sessions, body)
    state, _ = settle(lambda: session_api(client, session_id).get("bucket") == "needs_you" or None, 8.0)
    if not state:
        raise Blocked(f"the owned session never became needs_you: {session_api(client, session_id).get('state')}")
    before_pane = capture_pane(flock.run, k, session_id)
    with browser_session.context("U14", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, project)
        start = len(log.requests)
        open_card(page, session_id)
        listed, _ = settle(lambda: shown_choices(page) or None)
        rec.equal("ui.choices_verbatim_in_order", captured_choices(), shown_choices(page))
        decision_reads = [c for c in api_since(log, start, "GET") if c.startswith(f"GET /api/sessions/{session_id}/decision")]
        rec.check("api.decision_read", len(decision_reads) == 1, "GET …/decision answered once", decision_reads)
        shots(page, "1-card")
        click_start = len(log.requests)
        page.locator("#session-decision section.decision .choice").first.click()
        posted, _ = settle(lambda: posts_to(log, click_start, f"/api/sessions/{session_id}/permission") or None, 3.0, page)
        rec.check("api.choice_posts_permission", bool(posted), "POST …/permission after the click (C-18)",
                  api_since(log, click_start))
        key_seen, _ = settle(lambda: capture_pane(flock.run, k, session_id) != before_pane or None, 3.0)
        if key_seen:
            rec.check("tmux.pane_receives_the_keystroke", True, "the pane changed after the click", True)
        else:
            control_s = wait_until_control(flock, session_id)
            if 3.0 >= CONTROL_MULTIPLE * control_s:
                rec.fail_bound("tmux.pane_receives_the_keystroke", "the choice's keystroke in the pane", 3.0,
                               f"a harness send-keys line reached capture-pane in {control_s:.3f}s")
            else:
                rec.block("tmux.pane_receives_the_keystroke", f"unqualified: control {control_s:.3f}s")
        shots(page, "2-after-click")
        rec.equal("logs.console_errors", [], log.console_errors())
    kill_owned(client, session_id)
    rec.note(shots.note())
    rec.finish()


def wait_until_control(flock: Flock, session_id: str) -> float:
    send_line(flock.run, flock.controld.root.k, session_id, "QA6-CONTROL")
    return wait_until(lambda: "QA6-CONTROL" in capture_pane(flock.run, flock.controld.root.k, session_id), 5.0,
                      "the harness's control line in capture-pane")


# ----- U41 -------------------------------------------------------------------------------


@scenario("U41")
def test_u41_keyboard_focus_survives_a_list_rebuild(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U41")
    focus_on = flock.extra["U9"]
    other = flock.extra["U41"]
    with browser_session.context("U41", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        reached = press_tab_until(page, lambda a: a.get("session") == focus_on.session_id, limit=120)
        if reached is None:
            raise Blocked(f"Tab never reached the card {focus_on.session_id}")
        mark = flock.stream.mark()
        start = len(log.requests)
        rewrite(flock.controld, other, status="waiting", waitingFor="permission: Bash(ls)")
        arrived, _ = settle(lambda: bool(flock.stream.since(mark))
                            and any(c.startswith("GET /api/fleet/tree") for c in api_since(log, start)) or None, page=page)
        rec.check("stream.event_arrived_and_page_reread", bool(arrived), "an SSE frame and a tree re-read (control)",
                  {"frames": [f.kind for f in flock.stream.since(mark)], "calls": api_since(log, start),
                   "start": start, "requests": len(log.requests)})
        settle(lambda: len(api_since(log, start)) >= 2 or None, 2.0, page)
        now = focused(page)
        rec.equal("ui.card_focus_survives", focus_on.session_id, now.get("session"))
        shots(page, "flock-after")
        go(page, "projects", drawer=False)
        reached = press_tab_until(page, lambda a: a.get("project") == flock.alpha, limit=120)
        if reached is None:
            rec.block("ui.row_focus_survives", "Tab never reached the Alpha7 row")
        else:
            mark = flock.stream.mark()
            start = len(log.requests)
            create_project(flock.client, "QA6 U41 new")
            arrived, _ = settle(lambda: any(c.startswith("GET /api/projects") for c in api_since(log, start)) or None, page=page)
            rec.check("stream.project_event_reread", bool(arrived), "a project list re-read (control)",
                      {"calls": api_since(log, start), "start": start, "requests": len(log.requests)})
            settle(lambda: page.locator("#proj-list .proj-row", has_text="QA6 U41 new").count() == 1 or None, 3.0)
            rec.equal("ui.row_focus_survives", flock.alpha, focused(page).get("project"))
            shots(page, "projects-after")
        rec.equal("logs.console_errors", [], log.console_errors())
    rewrite(flock.controld, other, status="busy")
    rec.note(shots.note())
    rec.finish()


# ----- U45 -------------------------------------------------------------------------------


@scenario("U45")
def test_u45_the_session_header_follows_the_sessions_state(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U45")
    session = flock.extra["U45"]
    ask = "permission: Bash(rm -rf build)"
    with browser_session.context("U45", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        open_flock_project(page, "unassigned")
        open_card(page, session.session_id)
        rec.record("ui.header_before", {"state": text_of(page.locator("#session-state")), "chip": text_of(page.locator("#session-chip"))})
        mark = flock.stream.mark()
        rewrite(flock.controld, session, status="waiting", waitingFor=ask)
        card = page.locator(f"#flock-cards .card[data-session-id='{session.session_id}']")
        updated, _ = settle(lambda: "bucket-needs_you" in (card.get_attribute("class") or "") or None)
        painted_at = time.monotonic()
        if not updated:
            raise Blocked("the card never updated to needs_you (the control)")
        frames = [f for f in flock.stream.since(mark) if f.session_id == session.session_id]
        if not frames:
            raise Blocked("no SSE frame for the flipped session reached the harness subscriber")
        # The control: the page painted the card from the same envelope this long
        # after the frame reached the harness (same stream, same page).
        control_s = max(painted_at - frames[0].received_at, 1e-3)
        rec.check("ui.card_updates", True, "card becomes bucket-needs_you (control)",
                  f"painted {control_s:.3f}s after the frame reached the harness")

        def header_follows() -> bool:
            state = text_of(page.locator("#session-state")).replace("_", " ").lower()
            chip = text_of(page.locator("#session-chip")).replace("_", " ").lower()
            return state == "needs you" and chip == "needs you" and ask in text_of(page.locator("#session-why"))

        follows, _ = settle(lambda: header_follows() or None, UI_BOUND_S)
        if follows:
            rec.check("ui.header_follows", True, "header shows needs you and the ask", True)
        elif UI_BOUND_S >= CONTROL_MULTIPLE * control_s:
            rec.fail_bound("ui.header_follows", "#session-state/#session-chip read needs you and #session-why the ask",
                           UI_BOUND_S, f"the card updated in {control_s:.3f}s on the same page")
        else:
            rec.block("ui.header_follows", f"unqualified: control {control_s:.3f}s")
        rec.record("ui.header_after", {"state": text_of(page.locator("#session-state")), "chip": text_of(page.locator("#session-chip")),
                                       "why": text_of(page.locator("#session-why"))})
        shots(page, "after-flip")
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()


# ----- U42 -------------------------------------------------------------------------------


@scenario("U42")
def test_u42_user_text_is_shown_as_text_everywhere(flock: Flock, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U42")
    marked = attach(flock.pool, flock.controld, flock.run.repos / "loose", XSS, state="running")
    project = create_project(flock.client, XSS, XSS)
    dialogs: list[str] = []
    with browser_session.context("U42", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        page.on("dialog", lambda dialog: dialogs.append(dialog.message))

        def no_sink(where: str) -> None:
            rec.equal(f"ui.no_img_src_x.{where}", 0, page.locator("img[src=x]").count())
            rec.equal(f"ui.xss_not_run.{where}", None, xss_fired(page))

        open_flock_project(page, "unassigned")
        card = page.locator(f"#flock-cards .card[data-session-id='{marked.session_id}'] .card-title")
        rec.equal("ui.card_literal", XSS, card.text_content())
        no_sink("card")
        open_card(page, marked.session_id)
        rec.equal("ui.header_literal", XSS, page.locator("#session-title").text_content())
        no_sink("header")
        shots(page, "flock")
        go(page, "projects", drawer=False)
        row = page.locator(f"#proj-list .proj-row[data-project-id='{project}'] .proj-name")
        rec.equal("ui.project_row_literal", XSS, row.text_content())
        page.locator(f"#proj-list .proj-row[data-project-id='{project}']").click()
        await_env(lambda: page.locator("#proj-detail .proj-title").text_content() == XSS or None, UI_BOUND_S, "the detail")
        rec.equal("ui.project_detail_literal", XSS, page.locator("#proj-detail .proj-title").text_content())
        rec.equal("ui.project_description_literal", XSS, page.locator("#proj-detail .desc").first.text_content())
        no_sink("projects")
        page.locator("#proj-delete").click()
        await_env(lambda: page.locator("#dlg-delete").evaluate("d => d.open") or None, UI_BOUND_S, "the delete dialog")
        rec.equal("ui.delete_dialog_title_literal", f"Delete {XSS}", page.locator("#dlg-delete-title").text_content())
        identity = page.locator("#dlg-delete-identity").text_content() or ""
        rec.check("ui.delete_identity_literal", XSS in identity, "the identity rows carry the literal description", identity[:300])
        no_sink("delete-dialog")
        shots(page, "delete-dialog")
        page.keyboard.press("Escape")
        go(page, "settings", drawer=False)
        page.locator("#settings-nav .set-item", has_text="Data").click()
        await_env(lambda: page.locator("#settings-panel .audit").count() == 1 or None, UI_BOUND_S, "Settings → Data")
        no_sink("settings-data")
        rec.record("ui.settings_data_shows_args", XSS in (page.locator("#settings-panel").text_content() or ""))
        shots(page, "settings-data")
        rec.equal("ui.no_dialog_event", [], dialogs)
        rec.equal("logs.console_errors", [], log.console_errors())
    flock.client.delete_project(project)
    rec.note(shots.note())
    rec.finish()


# ----- U43 -------------------------------------------------------------------------------


def bad_text_nodes(page: Page) -> list[str]:
    value = page.evaluate(
        "() => { const out = []; const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);"
        " let n; while ((n = walk.nextNode())) { const t = n.textContent.trim(); const p = n.parentElement;"
        " if (!t || !p || p.closest('script, style')) continue; const r = p.getClientRects();"
        " if (!r.length || getComputedStyle(p).visibility === 'hidden') continue;"
        " if (t.includes('[object Object]') || t === 'undefined' || t === 'NaN') out.push(t.slice(0, 120)); } return out; }"
    )
    return [str(item) for item in value] if isinstance(value, list) else []


@scenario("U43")
def test_u43_nothing_renders_as_object_object_undefined_or_nan(flock: Flock, browser_session: BrowserSession,
                                                               rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U43")
    anomalies = as_dict(flock.client.fleet().get("anomalies"))
    rec.record("given.anomalies_non_zero", {k: v for k, v in anomalies.items() if v})
    with browser_session.context("U43", viewport=VIEWPORTS[DESKTOP]) as (context, log):
        page = open_app(context, flock.port)
        for name in ROOTS:
            go(page, name, drawer=False)
            if name == "flock":
                open_flock_project(page, "unassigned")
                open_card(page, flock.stopped["rate_limited"].session_id)
            rec.equal(f"ui.no_bad_text.{name}", [], bad_text_nodes(page))
            shots(page, name)
        for section in ("Autonomy", "Discovery", "Data", "System"):
            page.locator("#settings-nav .set-item", has_text=section).click()
            await_env(lambda: section in (page.locator("#settings-panel .col-head").text_content() or "") or None,
                      UI_BOUND_S, f"Settings → {section}")
            rec.equal(f"ui.no_bad_text.settings.{section.lower()}", [], bad_text_nodes(page))
            shots(page, f"settings-{section.lower()}")
        rec.equal("logs.console_errors", [], log.console_errors())
    rec.note(shots.note())
    rec.finish()
