"""Wave 7, INP #2: the master-driven UI chains — U25-U32 and U46.

This is INP #2's own pytest process (env-plan §1): one in-process composition
(`qa6/inp.py`) whose `build_master` is the harness's `ToolCallingMaster`, so a
turn's tool calls are real calls through the product's gate, approvals and
audit, and only the *model* is scripted. The browser drives the real page:
every send is typed into `#shepherd-input` and submitted with Enter or a click,
every decision is a click on the card. Browser contexts here pass
`abort_master_send=False` — INP is the lane allowed to send (env-plan §2).

A scripted `Turn` is queued **before** the user's send that consumes it. Each
scenario waits for its turn to end (the `master.turn_ended` frame on the
harness's own subscriber) before the next send, because a second send while a
turn is live is refused (M2).

Labels: U25(5) uses a CDP `Input.imeSetComposition` event (a user-equivalent
input-layer event, not a Playwright key — Playwright has no IME API); U25(6)
uses Playwright's `keyboard.insert_text` (the input layer's insertText, as a
paste). U29/U30 install the fetch shim (network timing only). U46's interrupt is
an in-process `invoke()` with a HUMAN context: it has no UI path (Difference 3).

**Mutation `w7-PP2-U29-forged`** (fixtures/mutations/scenarios/w7_pp2_u29_forged.json):
the page's second decide POST is answered, in the page, with a forged
`decided: true` — U29's `api.exactly_one_decided_true` must go false.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.types import Audience, CallerContext

from .. import fetchshim
from ..auditprobe import AuditProbe
from ..browser import BrowserSession
from ..constants import DESKTOP, VIEWPORTS
from ..httpclient import Client, as_dict
from ..inp import Inp
from ..inproc.master import Call, Turn
from ..mutations import active
from ..scenario import scenario
from ..sse_rig import Frame, Subscriber
from ..sub.test_wave6_0_uikit import (
    UI_BOUND_S,
    Shots,
    create_project,
    add_repo,
    go,
    new_repo,
    open_app,
    pane_alive,
    posts_to,
    record_posts,
    settle,
    text_of,
)
from ..verdict import Blocked, Recorder, await_env

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response, Route

MUTATION_U29 = "w7-PP2-U29-forged"
TURN_BOUND_S = 20.0
ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
ASK = "Ask me before anything leaves this machine"
AUTO = "Approve automatically"
COMPOSER_MAX_PX = 144.0


@dataclass
class Master:
    inp: Inp
    client: Client
    stream: Subscriber
    project: str
    repo: Path

    @property
    def port(self) -> int:
        return self.inp.port

    @property
    def k(self) -> int:
        return self.inp.root.k


@pytest.fixture(scope="module")
def master(inp: Inp) -> Iterator[Master]:
    client = inp.client
    repo = new_repo(inp.root.root, "inp-ui")
    project = create_project(client, "QA6 INP UI")
    add_repo(client, project, repo)
    stream = inp.subscribe("U-master")
    try:
        yield Master(inp=inp, client=client, stream=stream, project=project, repo=repo)
    finally:
        stream.close()
        inp.book.clear()


def spawn(master: Master, title: str) -> str:
    data = master.client.post("/api/sessions", {"workspace_id": master.project, "cwd": str(master.repo), "title": title}).data()
    if data.get("spawned") is not True:
        raise Blocked(f"spawn_session did not spawn {title!r}: {data!r}")
    session_id = str(data["session_id"])
    await_env(lambda: pane_alive(master.inp.run, master.k, session_id) or None, 10.0, f"{title}'s pane")
    return session_id


def kill_as_human(master: Master, session_id: str) -> None:
    if pane_alive(master.inp.run, master.k, session_id):
        master.client.post(f"/api/sessions/{session_id}/kill", {})


def compose(page: Page, text: str) -> None:
    page.locator("#shepherd-input").click()
    page.keyboard.type(text)
    page.keyboard.press("Enter")


def turn_frames(master: Master, mark: int, kind: str) -> list[Frame]:
    return [f for f in master.stream.since(mark) if f.kind == kind]


def await_turn_end(master: Master, mark: int, count: int = 1) -> list[Frame]:
    return await_env(lambda: (ended if len(ended := turn_frames(master, mark, "master.turn_ended")) >= count else None),
                     TURN_BOUND_S, f"{count} master.turn_ended frame(s)")


def await_card(page: Page) -> str:
    await_env(lambda: page.locator("#shepherd-thread .approval .approval-acts button").count() >= 2 or None,
              TURN_BOUND_S, "an approval card with live buttons")
    return str(page.locator("#shepherd-thread .approval").last.get_attribute("data-approval-id"))


def kill_turn(session_id: str) -> Turn:
    return Turn(says=f"QA6 killing {session_id}", calls=[Call("kill_session", {"session_id": session_id})])


def reject_by_http(master: Master, approval_id: str) -> None:
    master.client.post(f"/api/approvals/{approval_id}", {"choice": "reject"})


def record_json_responses(page: Page, fragment: str) -> list[tuple[int, object]]:
    sink: list[tuple[int, object]] = []

    def on_response(response: Response) -> None:
        if fragment in response.url and response.request.method == "POST":
            try:
                sink.append((response.status, response.json()))
            except Exception as error:  # a non-JSON answer is recorded as such, never dropped
                sink.append((response.status, f"(not JSON: {error})"))

    page.on("response", on_response)
    return sink


# ----- U25 -------------------------------------------------------------------------------


@scenario("U25")
def test_u25_the_composer_text_classes_keys_double_send(master: Master, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U25")
    rec.note("labels: (5) is a CDP Input.imeSetComposition event; (6) is Playwright keyboard.insert_text")
    book = master.inp.book
    book.clear()
    mark = master.stream.mark()
    accepted = 0
    long_text = "x" * 10_000
    with browser_session.context("U25", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        bodies = record_posts(page)
        go(page, "shepherd", drawer=False)

        def sends() -> int:
            return len(posts_to(log, 0, "/api/master/send"))

        # (1)
        book.push(Turn(says="QA6 U25 one"))
        compose(page, "QA6 one")
        settle(lambda: sends() >= 1 or None, 3.0, page)
        accepted += 1
        await_turn_end(master, mark, accepted)
        rec.equal("ui.1_bubble", "QA6 one", text_of(page.locator("#shepherd-thread .bubble").last))
        status, _ = settle(lambda: ULID.match(text_of(page.locator("#shepherd-status"))) or None)
        rec.check("ui.1_status_turn_id", bool(status), "#shepherd-status shows a turn id", text_of(page.locator("#shepherd-status")))
        rec.equal("api.1_one_post", 1, sends())
        shots(page, "1-one")
        # (2)
        book.push(Turn(says="QA6 U25 two"))
        page.locator("#shepherd-input").click()
        page.keyboard.type("a")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("b")
        rec.equal("ui.2_value_before_enter", "a\nb", page.locator("#shepherd-input").input_value())
        page.keyboard.press("Enter")
        settle(lambda: sends() >= 2 or None, 3.0, page)
        accepted += 1
        await_turn_end(master, mark, accepted)
        rec.equal("api.2_post_body", {"text": "a\nb"}, bodies.of("/api/master/send")[-1] if bodies.of("/api/master/send") else None)
        # (3) empty, (4) whitespace, (5) IME composing
        before = sends()
        page.locator("#shepherd-input").click()
        page.keyboard.press("Enter")
        settle(lambda: sends() > before or None, 1.5, page)
        rec.equal("api.3_no_post_for_empty", before, sends())
        page.keyboard.type("   ")
        page.keyboard.press("Enter")
        settle(lambda: sends() > before or None, 1.5, page)
        rec.equal("api.4_no_post_for_whitespace", before, sends())
        if sends() > before:
            settle(lambda: len(turn_frames(master, mark, "master.turn_ended")) >= accepted + 1 or None, TURN_BOUND_S)
            accepted = len(turn_frames(master, mark, "master.turn_ended"))
        page.locator("#shepherd-input").click()
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.press("Backspace")
        cdp = context.new_cdp_session(page)
        cdp.send("Input.imeSetComposition", {"text": "日本", "selectionStart": 2, "selectionEnd": 2})
        composing_value = page.locator("#shepherd-input").input_value()
        before = sends()
        page.keyboard.press("Enter")
        settle(lambda: sends() > before or None, 1.5, page)
        rec.equal("api.5_no_post_while_composing", before, sends())
        rec.record("ui.5_value_while_composing", composing_value)
        cdp.send("Input.imeSetComposition", {"text": "", "selectionStart": 0, "selectionEnd": 0})
        cdp.detach()
        if sends() > before:
            settle(lambda: len(turn_frames(master, mark, "master.turn_ended")) >= accepted + 1 or None, TURN_BOUND_S)
            accepted = len(turn_frames(master, mark, "master.turn_ended"))
        page.locator("#shepherd-input").click()
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.press("Backspace")
        shots(page, "5-after-ime")
        # (6) 10 000 characters
        book.push(Turn(says="QA6 U25 long"))
        page.locator("#shepherd-input").click()
        page.keyboard.insert_text(long_text)
        height = page.locator("#shepherd-input").evaluate("e => e.getBoundingClientRect().height")
        rec.check("ui.6_box_height_capped", isinstance(height, (int, float)) and float(height) <= COMPOSER_MAX_PX,
                  f"<= {COMPOSER_MAX_PX}px", height)
        before = sends()
        page.keyboard.press("Enter")
        settle(lambda: sends() > before or None, 3.0, page)
        accepted += 1
        await_turn_end(master, mark, accepted)
        bubble = page.locator("#shepherd-thread .bubble").last.text_content() or ""
        rec.equal("ui.6_bubble_length", 10_000, len(bubble))
        rec.equal("api.6_one_post", before + 1, sends())
        shots(page, "6-long")
        # (7) double click on send
        book.push(Turn(says="QA6 U25 double"))
        page.locator("#shepherd-input").click()
        page.keyboard.type("QA6 double")
        before = sends()
        page.locator("#shepherd-send").dblclick()
        settle(lambda: sends() >= before + 2 or None, 2.0, page)
        rec.equal("api.7_one_post_for_a_double_click", before + 1, sends())
        await_turn_end(master, mark, accepted + 1)
        accepted = len(turn_frames(master, mark, "master.turn_ended"))
        shots(page, "7-double")
        started = [b for b in bodies.of("/api/master/send")]
        rec.record("api.every_send_body", [b if not isinstance(b, dict) else {"text": str(b.get("text"))[:40]} for b in started])
        rec.check("stream.a_turn_per_accepted_send", len(turn_frames(master, mark, "master.turn_ended")) >= 4,
                  ">= 4 turns streamed ((1), (2), (6), (7))", len(turn_frames(master, mark, "master.turn_ended")))
        rec.equal("logs.page_errors", [], log.page_errors)
    book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U26 -------------------------------------------------------------------------------


def thread_items(page: Page) -> list[dict[str, str]]:
    value = page.evaluate(
        "() => [...document.querySelectorAll('#shepherd-thread > .turn')].map(t => ({cls: t.className,"
        " prose: [...t.querySelectorAll('.prose')].map(p => p.textContent).join(' | '),"
        " tool: (t.querySelector('.step-tool') || {}).textContent || '', bubble: (t.querySelector('.bubble') || {}).textContent || ''}))"
    )
    return [{str(k): str(v) for k, v in item.items()} for item in value] if isinstance(value, list) else []


#: U26's ordering signal (qa6 rulings P3, REM-FIX 1): the Shepherd side of the thread, snapshotted by the page
#: itself the first time `#shepherd-event` reads "turn ended". Read after the turn, it says what the thread held
#: when the ending was shown, not what it holds now.
AT_TURN_END = """
() => {
  window.__qa6AtTurnEnd = null;
  const line = document.getElementById('shepherd-event');
  if (line === null) { return; }
  new MutationObserver(() => {
    if (window.__qa6AtTurnEnd !== null || !line.textContent.startsWith('turn ended')) { return; }
    window.__qa6AtTurnEnd = [...document.querySelectorAll('#shepherd-thread > .turn-shepherd')].map(t => {
      const tool = t.querySelector('.step-tool');
      if (tool !== null) { return 'step:' + tool.textContent; }
      return 'prose:' + [...t.querySelectorAll('.prose')].map(p => p.textContent).join(' | ');
    });
  }).observe(line, {childList: true, characterData: true, subtree: true});
}
"""


@scenario("U26")
def test_u26_a_turn_renders_line_by_line_with_expandable_tool_steps(master: Master, browser_session: BrowserSession,
                                                                    rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U26")
    book = master.inp.book
    book.clear()
    with browser_session.context("U26", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        go(page, "shepherd", drawer=False)
        page.evaluate(AT_TURN_END)
        mark = master.stream.mark()
        book.push(Turn(says="QA6 U26 prose", calls=[Call("fleet_summary", {})]))
        compose(page, "QA6 U26")
        ended = await_turn_end(master, mark)
        # Rulings 2-4 (U19; qa6 rulings P3): the ending is on the event line beside the status slot,
        # never in the thread; the call and its result are one step; `#shepherd-status` is not read here.
        detail = ended[-1].data.get("detail")
        outcome = detail.get("outcome") if isinstance(detail, dict) else None
        line_says = f"turn ended · {outcome if isinstance(outcome, str) and outcome else '—'}"
        line, _ = settle(lambda: text_of(page.locator("#shepherd-event")) == line_says or None)
        rec.equal("ui.turn_ended_reaches_the_status_area", line_says, text_of(page.locator("#shepherd-event")))
        frames = [f for f in master.stream.since(mark) if f.kind.startswith("master.")]
        rec.record("stream.frames", [f.kind for f in frames])
        items = [item for item in thread_items(page) if not item["bubble"]]
        rec.check("ui.no_turn_ended_line_in_the_thread",
                  not any("turn_ended" in item["prose"] or "turn ended ·" in item["prose"] for item in items),
                  "no .prose reads turn_ended or the event line's 'turn ended ·'", [item["prose"] for item in items])
        # The scripted turn: one text, then fleet_summary's call and result (one step), then the ending
        # (the event line). The text is not repeated: the scripted ending carries none (ruling 4).
        expected = ["prose:QA6 U26 prose", "step:fleet_summary"]
        shown = [f"step:{i['tool']}" if i["tool"] else f"prose:{i['prose']}" for i in items]
        rec.equal("ui.frames_render_in_order", expected, shown[-len(expected):])
        # Ordering, from the page's own snapshot taken when the event line first said the turn ended
        # (AT_TURN_END): the prose and the one step were already there, not added after the ending.
        at_end = page.evaluate("() => window.__qa6AtTurnEnd")
        at_end_tail = [str(entry) for entry in at_end][-len(expected):] if isinstance(at_end, list) else None
        rec.check("ui.prose_and_step_before_turn_ended", bool(line) and at_end_tail == expected,
                  "the prose and the one step were in the thread when the event line first said the turn ended",
                  {"at_turn_end": at_end, "thread": shown, "event_line": text_of(page.locator("#shepherd-event"))})
        rec.block("ui.two_prose_lines_each_as_it_arrives",
                  "the shared ToolCallingMaster emits one `text` event per scripted Turn (inproc/master.py `says`), so a "
                  "turn with two text events cannot be scripted without editing a shared file (SCOPE_INCREASE)")
        steps = page.locator("#shepherd-thread details.step").filter(has_text="fleet_summary")
        rec.equal("ui.one_step_for_the_tool", 1, steps.count())
        shots(page, "1-rendered")
        if steps.count():
            steps.first.locator("summary").click()
            opened, _ = settle(lambda: steps.first.evaluate("d => d.open") is True or None, 3.0)
            rec.check("ui.step_opens", bool(opened), "details.step open", steps.first.evaluate("d => d.open"))
            body = steps.first.locator(".step-body").text_content() or ""
            rec.check("ui.step_detail_not_object_object", "[object Object]" not in body, "no [object Object]", body[:200])
            shots(page, "2-step-open")
        page.reload(wait_until="load")
        await_env(lambda: page.locator("#nav-chat").get_attribute("aria-current") == "page" or None, UI_BOUND_S, "reloaded")
        rec.record("ui.thread_after_reload", thread_items(page))
        shots(page, "3-after-reload")
        rec.equal("logs.page_errors", [], log.page_errors)
    book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U27 / U28 -------------------------------------------------------------------------


def decide_through_the_card(master: Master, browser_session: BrowserSession, rec: Recorder, sid: str, choice: str) -> None:
    shots = Shots(browser_session.artifacts, sid)
    book = master.inp.book
    book.clear()
    audit = AuditProbe.for_instance(master.inp.root)
    target = spawn(master, f"QA6 {sid} target")
    audit_mark = audit.mark()
    with browser_session.context(sid, viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        bodies = record_posts(page)
        go(page, "shepherd", drawer=False)
        mark = master.stream.mark()
        book.push(kill_turn(target))
        compose(page, f"QA6 {sid} please kill it")
        approval = await_card(page)
        card = page.locator(f"[data-approval-id='{approval}']")
        rec.equal("ui.exactly_one_card_for_the_id", 1, card.count())
        rec.equal("ui.card_tool", "kill_session", text_of(card.locator(".approval-tool")))
        meta = [t.strip() for t in card.locator(".approval-meta span").all_text_contents()]
        rec.check("ui.card_summary_names_the_session", len(meta) == 2 and target in meta[0], f"the summary names {target}", meta)
        rec.check("ui.card_deadline", len(meta) == 2 and bool(re.match(r"^\d{4}-\d{2}-\d{2}T", meta[1])), "an ISO deadline", meta)
        alive_before = pane_alive(master.inp.run, master.k, target)
        rec.check("tmux.pane_alive_while_pending", alive_before, "alive before the click (PP-1)", alive_before)
        shots(page, "1-card")
        label = "Approve" if choice == "approve" else "Reject"
        card.locator(".approval-acts button", has_text=label).click()
        word = "approved" if choice == "approve" else "rejected"
        said, _ = settle(lambda: text_of(page.locator("#shepherd-status")) == word or None)
        rec.equal("ui.status_says", word, text_of(page.locator("#shepherd-status")))
        # Ruling 17 (SD-04): the decided card stays inline in the thread, its buttons replaced by the outcome.
        inline = page.locator(f"#shepherd-thread [data-approval-id='{approval}']")
        label_node = inline.locator(".decided")
        kept, _ = settle(lambda: (inline.count() == 1 and label_node.count() == 1 and text_of(label_node) == word) or None, 5.0)
        rec.check("ui.one_inline_card_with_the_outcome", bool(kept) and page.locator(f"[data-approval-id='{approval}']").count() == 1,
                  f"exactly one [data-approval-id={approval}], inside #shepherd-thread, reading {word!r}",
                  {"count": page.locator(f"[data-approval-id='{approval}']").count(),
                   "in_thread": inline.count(),
                   "card_text": text_of(inline.first) if inline.count() else ""})
        shots(page, "2-decided")
        rec.equal("api.one_decide_post", [{"choice": choice}], bodies.of(f"/api/approvals/{approval}"))
        await_turn_end(master, mark)
        if choice == "approve":
            dead, _ = settle(lambda: not pane_alive(master.inp.run, master.k, target) or None)
            rec.check("tmux.pane_gone_after", bool(dead), "the pane gone", pane_alive(master.inp.run, master.k, target))
        else:
            rec.check("tmux.pane_alive_after_reject", pane_alive(master.inp.run, master.k, target), "alive",
                      pane_alive(master.inp.run, master.k, target))
        rows = audit.records_for(audit_mark, "kill_session")
        if choice == "approve":
            rec.equal("logs.audit_approved_by_user", ["user"], [r.get("approved_by") for r in rows])
        else:
            rec.equal("logs.audit_deny_approved_by_null", [("deny", None)], [(r.get("decision"), r.get("approved_by")) for r in rows])
        decided = turn_frames(master, mark, "approval.decided")
        rec.equal("stream.approval_decided", [word], [str(f.data.get("outcome")) for f in decided])
        rec.equal("logs.console_errors", [], log.console_errors())
    kill_as_human(master, target)
    book.clear()
    rec.note(shots.note())
    rec.finish()


@scenario("U27")
def test_u27_approve_through_the_card(master: Master, browser_session: BrowserSession, rec: Recorder) -> None:
    decide_through_the_card(master, browser_session, rec, "U27", "approve")


@scenario("U28")
def test_u28_reject_through_the_card(master: Master, browser_session: BrowserSession, rec: Recorder) -> None:
    decide_through_the_card(master, browser_session, rec, "U28", "reject")


# ----- U29 -------------------------------------------------------------------------------


@scenario("U29")
def test_u29_a_double_click_on_approve_decides_once(master: Master, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U29")
    rec.note("label: the fetch shim holds /api/approvals/<A> so both clicks land before any reply")
    book = master.inp.book
    book.clear()
    audit = AuditProbe.for_instance(master.inp.root)
    target = spawn(master, "QA6 U29 target")
    audit_mark = audit.mark()
    forged: list[str] = []
    with browser_session.context("U29", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        answers = record_json_responses(page, "/api/approvals/")
        go(page, "shepherd", drawer=False)
        mark = master.stream.mark()
        book.push(kill_turn(target))
        compose(page, "QA6 U29 please kill it")
        approval = await_card(page)
        if active(MUTATION_U29):
            seen: list[str] = []

            def forge(route: Route) -> None:
                seen.append(route.request.url)
                if len(seen) == 1:
                    route.continue_()
                    return
                forged.append(route.request.url)
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"ok": True, "data": {"approval_id": approval, "decided": True, "outcome": "approved"},
                     "error": None, "correlation_id": "0" * 32}))

            page.route(f"**/api/approvals/{approval}", forge)
        fetchshim.install(page, f"/api/approvals/{approval}$")
        page.locator(f"[data-approval-id='{approval}'] .approval-acts button", has_text="Approve").dblclick()
        held, _ = settle(lambda: fetchshim.held_count(page) >= 2 or None, 3.0)
        rec.check("shim.both_clicks_held", bool(held), "two decide requests held before any reply", fetchshim.held_count(page))
        before = fetchshim.delivered(page)
        released = fetchshim.release_all(page)
        reached, _ = settle(lambda: fetchshim.delivered(page) >= before + released or None)
        if not reached:
            raise Blocked(f"the shim did not deliver: {before} -> {fetchshim.delivered(page)} of {released}")
        settle(lambda: len(answers) >= 2 or None, 5.0, page)
        if active(MUTATION_U29):
            rec.note(f"QA6 MUTATION {MUTATION_U29} APPLIED: the second decide POST answered in the page with a forged "
                     f"decided:true ({len(forged)} forged)")
        rec.equal("api.two_posts_sent", 2, len(posts_to(log, 0, f"/api/approvals/{approval}")))
        decided = [body for _status, body in answers if isinstance(body, dict)
                   and as_dict(body.get("data") or {}).get("decided") is True]
        rec.equal("api.exactly_one_decided_true", 1, len(decided))
        rec.record("ui.final_status", text_of(page.locator("#shepherd-status")))
        shots(page, "after")
        await_turn_end(master, mark)
        rec.equal("logs.one_kill_session_row", 1, len(audit.records_for(audit_mark, "kill_session")))
        rec.equal("logs.two_decide_approval_rows", 2, len(audit.records_for(audit_mark, "decide_approval")))
        rec.equal("stream.one_approval_decided", 1, len(turn_frames(master, mark, "approval.decided")))
        dead, _ = settle(lambda: not pane_alive(master.inp.run, master.k, target) or None)
        rec.check("tmux.pane_gone", bool(dead), "the pane gone", pane_alive(master.inp.run, master.k, target))
        rec.equal("logs.console_errors", [], log.console_errors())
    kill_as_human(master, target)
    book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U30 -------------------------------------------------------------------------------


@scenario("U30")
def test_u30_a_card_is_shown_once_when_the_load_read_and_the_stream_both_carry_it(master: Master,
                                                                                  browser_session: BrowserSession,
                                                                                  rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U30")
    rec.note("label: add_init_script installs the fetch shim for GET /api/approvals$ before the page's scripts run")
    book = master.inp.book
    book.clear()
    target = spawn(master, "QA6 U30 target")
    approval = ""
    with browser_session.context("U30", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = context.new_page()
        page.add_init_script(script=f"({fetchshim.HOLD_MATCHING_FETCH})('/api/approvals$')")
        page.goto(f"http://127.0.0.1:{master.port}/", wait_until="load")
        await_env(lambda: page.locator("#nav-chat").get_attribute("aria-current") == "page" or None, UI_BOUND_S, "routed")
        await_env(lambda: page.locator("#stream-status").inner_text().strip() == "live" or None, UI_BOUND_S, "live")
        held, _ = settle(lambda: fetchshim.held_count(page) >= 1 or None, 5.0)
        if not held:
            raise Blocked("the load's GET /api/approvals was not held")
        read_bodies: list[object] = []
        page.on("response", lambda response: read_bodies.append(response.json())
                if response.url.endswith("/api/approvals") and response.request.method == "GET" else None)
        mark = master.stream.mark()
        book.push(kill_turn(target))
        compose(page, "QA6 U30 please kill it")
        approval = await_card(page)
        shots(page, "1-from-stream")
        before = fetchshim.delivered(page)
        released = fetchshim.release_all(page)
        reached, _ = settle(lambda: fetchshim.delivered(page) >= before + released or None)
        if not reached:
            raise Blocked("the held approvals read was not delivered")
        settle(lambda: read_bodies or None, 3.0, page)
        listed: list[str] = []
        for body in read_bodies:
            data = as_dict(body.get("data") or {}) if isinstance(body, dict) else {}
            rows = data.get("approvals")
            listed.extend(str(row.get("approval_id")) for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict))
        rec.check("api.released_read_lists_a", approval in listed, f"the read lists {approval}", listed)
        settle(lambda: page.locator(f"[data-approval-id='{approval}']").count() > 1 or None, 2.0)
        rec.equal("ui.exactly_one_element_for_a", 1, page.locator(f"[data-approval-id='{approval}']").count())
        rec.equal("stream.one_approval_created", 1, len(turn_frames(master, mark, "approval.created")))
        shots(page, "2-after-release")
    if approval:
        reject_by_http(master, approval)
    kill_as_human(master, target)
    book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U31 -------------------------------------------------------------------------------


def set_level_by_click(page: Page, label: str) -> None:
    go(page, "settings", drawer=False)
    page.locator("#settings-nav .set-item", has_text="Autonomy").click()
    page.locator("#settings-panel button.opt", has_text=label).click()
    await_env(lambda: page.locator("#settings-panel button.opt", has_text=label).get_attribute("aria-pressed") == "true" or None,
              UI_BOUND_S, f"{label!r} pressed")


@scenario("U31")
def test_u31_flipping_autonomy_changes_whether_a_card_appears(master: Master, browser_session: BrowserSession,
                                                              rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U31")
    book = master.inp.book
    book.clear()
    audit = AuditProbe.for_instance(master.inp.root)
    first = spawn(master, "QA6 U31 first")
    second = spawn(master, "QA6 U31 second")
    approval = ""
    try:
        with browser_session.context("U31", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
            page = open_app(context, master.port)
            set_level_by_click(page, AUTO)
            rec.equal("api.level_3", 3, master.client.get("/api/autonomy").data().get("level"))
            go(page, "shepherd", drawer=False)
            audit_mark = audit.mark()
            mark = master.stream.mark()
            book.push(kill_turn(first))
            compose(page, "QA6 U31 first kill")
            await_turn_end(master, mark)
            rec.equal("ui.no_card_at_level_3", 0, page.locator("#shepherd-thread .approval").count())
            dead, _ = settle(lambda: not pane_alive(master.inp.run, master.k, first) or None)
            rec.check("tmux.first_gone_without_a_click", bool(dead), "gone", pane_alive(master.inp.run, master.k, first))
            rows = audit.records_for(audit_mark, "kill_session")
            rec.equal("logs.first_approved_by_policy", ["policy"], [r.get("approved_by") for r in rows])
            shots(page, "1-level3")
            set_level_by_click(page, ASK)
            rec.equal("api.level_2", 2, master.client.get("/api/autonomy").data().get("level"))
            go(page, "shepherd", drawer=False)
            audit_mark = audit.mark()
            mark = master.stream.mark()
            book.push(kill_turn(second))
            compose(page, "QA6 U31 second kill")
            approval = await_card(page)
            rec.equal("ui.card_at_level_2", 1, page.locator(f"[data-approval-id='{approval}']").count())
            rec.check("tmux.second_alive_while_pending", pane_alive(master.inp.run, master.k, second), "alive",
                      pane_alive(master.inp.run, master.k, second))
            rec.equal("logs.second_pending_no_kill_row", [], [r.get("approved_by") for r in audit.records_for(audit_mark, "kill_session")])
            shots(page, "2-level2-card")
            page.locator(f"[data-approval-id='{approval}'] .approval-acts button", has_text="Reject").click()
            await_turn_end(master, mark)
            rec.equal("logs.console_errors", [], log.console_errors())
    finally:
        master.client.post("/api/autonomy", {"level": 2})
        kill_as_human(master, first)
        kill_as_human(master, second)
        book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U32 -------------------------------------------------------------------------------


@scenario("U32")
def test_u32_the_wake_summary_through_the_ui(master: Master, browser_session: BrowserSession, rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U32")
    rec.note("label: the reply the user sees is scripted; the evidence is the text the master was handed")
    book = master.inp.book
    book.clear()
    with browser_session.context("U32", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        go(page, "shepherd", drawer=False)
        mark = master.stream.mark()
        book.push(Turn(says="QA6 spawning W", calls=[Call("spawn_session", {
            "workspace_id": master.project, "cwd": str(master.repo), "title": "QA6 U32 W"})]))
        compose(page, "QA6 U32 start W")
        await_turn_end(master, mark)
        record = next((r for r in reversed(book.records) if r.results and r.results[0].name == "spawn_session"), None)
        if record is None or record.results[0].is_error:
            raise Blocked(f"the scripted spawn did not run: {record.results if record else None}")
        spawned = json.loads(record.results[0].text)
        worker = str(spawned.get("session_id")) if isinstance(spawned, dict) else ""
        if not spawned or not worker or worker == "None":
            raise Blocked(f"the master's spawn answered no session: {spawned!r}")
        await_env(lambda: pane_alive(master.inp.run, master.k, worker) or None, 10.0, "W's pane")
        master.client.post(f"/api/sessions/{worker}/kill", {})
        await_env(lambda: not pane_alive(master.inp.run, master.k, worker) or None, 10.0, "W killed")
        shots(page, "1-w-killed")
        mark = master.stream.mark()
        book.push(Turn(says="QA6 welcome back"))
        compose(page, "I'm back")
        await_turn_end(master, mark)
        handed = book.records[-1].text
        rec.check("files.turn_input_starts_with_the_wake_header", handed.startswith("while you were away —"),
                  "starts with 'while you were away —'", handed[:200])
        rec.check("files.turn_input_names_w", worker in handed or "QA6 U32 W" in handed, "names W", handed[:400])
        shown, _ = settle(lambda: page.locator("#shepherd-thread .prose", has_text="QA6 welcome back").count() >= 1 or None)
        rec.check("ui.scripted_reply_renders", bool(shown), "the reply in the thread", text_of(page.locator("#shepherd-thread"))[-300:])
        shots(page, "2-reply")
        rec.equal("logs.console_errors", [], log.console_errors())
    book.clear()
    rec.note(shots.note())
    rec.finish()


# ----- U46 -------------------------------------------------------------------------------


@scenario("U46")
def test_u46_a_withdrawn_card_leaves_the_page_and_a_late_click_says_so(master: Master, browser_session: BrowserSession,
                                                                       rec: Recorder) -> None:
    shots = Shots(browser_session.artifacts, "U46")
    rec.note("label: the interrupt is driven by in-process invoke('interrupt_master') with a HUMAN context (no UI path)")
    book = master.inp.book
    book.clear()
    target = spawn(master, "QA6 U46 target")
    with browser_session.context("U46", viewport=VIEWPORTS[DESKTOP], abort_master_send=False) as (context, log):
        page = open_app(context, master.port)
        answers = record_json_responses(page, "/api/approvals/")
        go(page, "shepherd", drawer=False)
        mark = master.stream.mark()
        book.push(kill_turn(target))
        compose(page, "QA6 U46 please kill it")
        approval = await_card(page)
        shots(page, "1-card")
        result = invoke("interrupt_master", {}, CallerContext(audience=Audience.HUMAN, caller_id="qa6-u46",
                                                               correlation_id=uuid.uuid4().hex))
        rec.record("given.interrupt_result", {"ok": getattr(result, "ok", None)})
        buttons = page.locator(f"[data-approval-id='{approval}'] .approval-acts button")
        gone, elapsed = settle(lambda: buttons.count() == 0 or None, 5.0)
        rec.check("ui.no_live_buttons_within_5s", bool(gone), "no Approve/Reject for the id within 5 s",
                  {"buttons": buttons.count(), "elapsed": round(elapsed, 2)})
        if buttons.count():
            buttons.filter(has_text="Approve").first.click()
            settle(lambda: text_of(page.locator("#shepherd-status")) == "already decided" or None, 3.0)
            rec.equal("ui.late_click_says_already_decided", "already decided", text_of(page.locator("#shepherd-status")))
            settle(lambda: answers or None, 3.0, page)
            rec.equal("api.late_post_decided_false", [False],
                      [as_dict(b.get("data") or {}).get("decided") for _s, b in answers if isinstance(b, dict)])
        else:
            rec.record("ui.late_click", "nothing left to click: the card's buttons were withdrawn first")
        shots(page, "2-withdrawn")
        decided = turn_frames(master, mark, "approval.decided")
        rec.equal("stream.approval_decided_withdrawn", ["withdrawn"], [str(f.data.get("outcome")) for f in decided])
        await_turn_end(master, mark)
        rec.check("tmux.pane_alive", pane_alive(master.inp.run, master.k, target), "alive", pane_alive(master.inp.run, master.k, target))
        rec.equal("logs.console_errors", [], log.console_errors())
    kill_as_human(master, target)
    book.clear()
    rec.note(shots.note())
    rec.finish()

