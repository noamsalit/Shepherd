"""qa6 rulings P3 — BC-06 in a real browser: one step per tool, events on their own line.

The owner's rulings 2, 3 and 4 (`docs/plans/2026-09-27-qa6-owner-rulings.md`),
recorded as U19 in `docs/design/ui-decisions.md`:

* **Ruling 2.** A tool call and its result are one expandable step: the call is
  the title, the result is inside it. A result whose call this page never saw
  still renders, as its own step, so nothing is dropped.
* **Ruling 3.** `turn_ended` and a rate limit that does not stop the turn go to
  the status area's **event line**, `#shepherd-event`, and never to the thread.
  They never write `#shepherd-status` either: that slot keeps its turn id, its
  refusal and its approval word (plan revision 4, B1). A rate limit that stops
  the turn (`status == "rejected"`, RD-4) also enters the thread.
* **Ruling 4.** The SDK's final `result` text, carried on `turn_ended`, is not
  rendered when it equals the turn's last text; a different one is rendered
  once, as prose.

**What is real here** is the same as `test_chat_qa6_live.py`, whose fixture this
file uses: the shipped server on a loopback port, `chat.js` fetched from it, the
committed `shell_harness.html`, and events built by the shipped
`project_to_stream` through the shipped `sse.envelope`, handed to the page's own
`onShepherdEvent`. The status-slot tests send through the real composer to the
real `/api/master/send` route and decide through the real approvals route.

Skipped, not failed, where playwright or chromium is absent.
"""

from __future__ import annotations

import re

import pytest

from web.conftest import TURN_ID, MasterDoubles

from shepherd.core.master import MasterEvent
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.master_turn import project_to_stream
from shepherd.toolsurface.approvals import Approval
from shepherd.toolsurface.stream import StreamDelivery
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, ToolDef
from shepherd.web import sse

pytest.importorskip("playwright.sync_api")

from web.test_chat_qa6_live import DELIVER, chat_page  # noqa: E402,F401 - the shared fixture
from web.test_session_page import FIXTURES, STATIC_ROOT  # noqa: E402

AT = "2026-09-27T10:00:00Z"
TURN = "turn-qa6r-p3"
FINAL = "Two sessions are running and none needs you."

#: Every `.turn` the Shepherd side of the thread holds, as `step:<tool>` or
#: `prose:<text>`, in order — the same reading qa6 U26 takes.
THREAD = """
() => [...document.querySelectorAll('#shepherd-thread > .turn-shepherd')].map(t => {
  const tool = t.querySelector('.step-tool');
  if (tool !== null) { return 'step:' + tool.textContent; }
  return 'prose:' + [...t.querySelectorAll('.prose')].map(p => p.textContent).join(' | ');
})
"""


def _master(
    kind: str,
    *,
    text: str | None = None,
    tool: str | None = None,
    payload: dict[str, object] | None = None,
    turn: str = TURN,
) -> dict[str, object]:
    event = MasterEvent(kind=kind, text=text, tool_name=tool, payload=payload or {}, occurred_at=AT)  # type: ignore[arg-type]
    return sse.envelope(StreamDelivery(seq=1, event=project_to_stream(event, turn)))


def _call(tool: str, use_id: str, arguments: dict[str, object]) -> dict[str, object]:
    return _master("tool_call", tool=tool, payload={"tool_use_id": use_id, "input": arguments})


def _result(tool: str | None, use_id: str, text: str | None, *, is_error: bool = False) -> dict[str, object]:
    return _master("tool_result", text=text, tool=tool, payload={"tool_use_id": use_id, "is_error": is_error})


def _ended(text: str | None, outcome: str = "success", turn: str = TURN) -> dict[str, object]:
    return _master("turn_ended", text=text, payload={"outcome": outcome, "subtype": outcome}, turn=turn)


def _error(text: str | None, turn: str = TURN) -> dict[str, object]:
    """The `error` ending `result_ending` projects from an `is_error` ResultMessage (qa6 BC-07):
    in every probe capture its text is the turn's last assistant text again."""
    payload: dict[str, object] = {
        "outcome": "error",
        "subtype": "success",
        "terminal_reason": "api_error",
        "is_error": True,
    }
    return _master("error", text=text, payload=payload, turn=turn)


def _rate_limit(status: str) -> dict[str, object]:
    return _master("rate_limit", payload={"rate_limit": {"status": status, "rate_limit_type": "five_hour"}})


def _deliver(page, *envelopes: dict[str, object]) -> None:
    for envelope in envelopes:
        page.evaluate(DELIVER, envelope)


def _thread(page) -> list[str]:
    return list(page.evaluate(THREAD))


def _event_line(page) -> str:
    return page.locator("#shepherd-event").inner_text()


def _status(page) -> str:
    return page.locator("#shepherd-status").inner_text()


# ----- ruling 2: one step per tool --------------------------------------------


def test_a_tool_call_and_its_result_are_one_step(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(
        page,
        _call("spawn_session", "tu-1", {"cwd": "/tmp/x", "brief": "b"}),
        _result("spawn_session", "tu-1", "spawned s-1"),
    )
    assert _thread(page) == ["step:spawn_session"]
    step = page.locator("#shepherd-thread details.step")
    assert step.count() == 1
    # The call is the title; the result is inside the one step, beside the call's keys.
    assert step.locator("summary .step-tool").inner_text() == "spawn_session"
    body = step.locator(".step-body").text_content() or ""
    assert "arguments: brief, cwd" in body, body
    assert "spawned s-1" in body, body
    # Folded until opened: the thread reads as prose.
    assert step.evaluate("d => d.open") is False
    assert errors == [], errors


def test_a_result_with_no_call_still_renders_as_its_own_step(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(
        page,
        _call("fleet_summary", "tu-1", {}),
        _result("fleet_summary", "tu-1", "2 running"),
        # A result for a call this page never saw (the page opened mid-turn).
        _result("list_sessions", "tu-unseen", "s-1, s-2"),
    )
    assert _thread(page) == ["step:fleet_summary", "step:list_sessions"]
    bodies = page.locator("#shepherd-thread .step-body").all_text_contents()
    assert bodies[1] == "s-1, s-2", bodies
    assert errors == [], errors


def test_a_failed_tool_result_is_visibly_marked(chat_page) -> None:
    """REM-FIX 1 (3): `is_error` is not dropped, merged into its call's step or not."""
    page, errors, _ = chat_page
    _deliver(
        page,
        _call("kill_session", "tu-1", {"session_id": "s-1"}),
        _result("kill_session", "tu-1", "no such session", is_error=True),
        _result("list_sessions", "tu-unseen", "refused", is_error=True),
        _call("fleet_summary", "tu-2", {}),
        _result("fleet_summary", "tu-2", "2 running"),
    )
    bodies = page.locator("#shepherd-thread .step-body").all_text_contents()
    assert bodies[0].splitlines()[-1] == "error · no such session", bodies
    assert bodies[1] == "error · refused", bodies
    assert bodies[2].splitlines()[-1] == "2 running", bodies
    assert errors == [], errors


def test_a_call_left_open_at_the_turn_end_is_not_matched_later(chat_page) -> None:
    """REM-FIX 1 (7): a turn's open steps are dropped when it ends."""
    page, errors, _ = chat_page
    _deliver(page, _call("fleet_summary", "tu-1", {}), _ended(None), _result("fleet_summary", "tu-1", "late"))
    assert _thread(page) == ["step:fleet_summary", "step:fleet_summary"]
    assert errors == [], errors


# ----- ruling 3: events go to the event line ----------------------------------


def test_turn_ended_goes_to_the_status_line_not_the_thread(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(page, _master("text", text="Done."), _ended(None))
    assert _thread(page) == ["prose:Done."]
    assert "turn_ended" not in page.locator("#shepherd-thread").inner_text()
    assert _event_line(page) == "turn ended · success"
    assert errors == [], errors


def test_a_rate_limit_that_does_not_stop_the_turn_goes_to_the_status_line(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(page, _master("text", text="Working."), _rate_limit("allowed_warning"))
    assert _thread(page) == ["prose:Working."]
    assert _event_line(page) == "rate limit · allowed_warning"
    assert errors == [], errors


def test_a_rejected_rate_limit_is_also_shown_in_the_thread(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(page, _rate_limit("rejected"))
    assert _thread(page) == ["prose:rate limit · rejected"]
    assert _event_line(page) == "rate limit · rejected"
    assert errors == [], errors


# ----- ruling 4: the final text once ------------------------------------------


def test_a_final_result_text_equal_to_the_last_text_is_not_rendered_twice(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(page, _master("text", text=FINAL), _ended(FINAL))
    assert _thread(page) == [f"prose:{FINAL}"]
    assert _event_line(page) == "turn ended · success"
    assert errors == [], errors


def test_a_final_result_text_that_differs_is_rendered_once(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(
        page,
        _master("text", text="Checking the fleet."),
        _call("fleet_summary", "tu-1", {}),
        _result("fleet_summary", "tu-1", "2 running"),
        _ended(FINAL),
    )
    assert _thread(page) == ["prose:Checking the fleet.", "step:fleet_summary", f"prose:{FINAL}"]
    # The last text is per turn: another turn's text does not suppress this one's.
    _deliver(page, _master("text", text="Other.", turn="turn-other"), _ended("Other.", turn=TURN))
    assert _thread(page)[-2:] == ["prose:Other.", "prose:Other."]
    assert errors == [], errors


# ----- ruling 4 for every ending: the `error` ending (REM-FIX 1) --------------


def test_an_error_ending_equal_to_the_last_text_says_error_not_the_text_again(chat_page) -> None:
    """Two turns; the second ends `error` with the probe's shape (text == the last text)."""
    page, errors, _ = chat_page
    _deliver(page, _master("text", text="First answer.", turn="turn-a"), _ended("First answer.", turn="turn-a"))
    _deliver(page, _master("text", text=FINAL, turn="turn-b"), _error(FINAL, turn="turn-b"))
    assert _thread(page) == ["prose:First answer.", f"prose:{FINAL}", "prose:error"]
    assert _event_line(page) == "turn ended · error"
    assert errors == [], errors


def test_an_error_ending_with_new_or_no_text_is_rendered(chat_page) -> None:
    page, errors, _ = chat_page
    _deliver(page, _master("text", text="Working."), _error("the API refused the request"))
    assert _thread(page) == ["prose:Working.", "prose:the API refused the request"]
    assert _event_line(page) == "turn ended · error"
    _deliver(page, _error(None, turn="turn-other"))
    assert _thread(page)[-1] == "prose:error"
    assert errors == [], errors


# ----- the status slot keeps its own writers ----------------------------------


def _send(page, text: str) -> None:
    page.locator("#shepherd-input").fill(text)
    page.click("#shepherd-send")


def test_turn_ended_is_shown_in_the_event_line_and_the_status_keeps_the_turn_id(
    chat_page, master_doubles: MasterDoubles
) -> None:
    page, errors, _ = chat_page
    _send(page, "what's running?")
    page.wait_for_function("id => document.getElementById('shepherd-status').textContent === id", arg=TURN_ID)
    _deliver(page, _ended(None, turn=TURN_ID))
    assert _event_line(page) == "turn ended · success"
    assert _status(page) == TURN_ID
    _deliver(page, _rate_limit("allowed_warning"))
    assert _event_line(page) == "rate limit · allowed_warning"
    assert _status(page) == TURN_ID
    assert errors == [], errors


def _kill_tool() -> ToolDef:
    return ToolDef(
        name="kill_session",
        description="stop a session",
        input_schema={"type": "object", "properties": {}},
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=lambda args, ctx: None,
        audiences=frozenset({Audience.MASTER}),
    )


def _created(approval: Approval) -> dict[str, object]:
    event = StreamEvent(
        kind="approval.created",
        session_id=None,
        payload={
            "approval_id": approval.id,
            "tool": approval.tool,
            "summary": approval.summary,
            "turn_id": approval.turn_id,
            "deadline_at": approval.deadline_at,
        },
        occurred_at=AT,
    )
    return sse.envelope(StreamDelivery(seq=2, event=event))


def _both_events_leave_the_status(page, expected: str) -> None:
    _deliver(page, _ended(None))
    assert _status(page) == expected
    assert _event_line(page) == "turn ended · success"
    _deliver(page, _rate_limit("allowed_warning"))
    assert _status(page) == expected
    assert _event_line(page) == "rate limit · allowed_warning"


def test_an_event_never_touches_the_status_after_an_approval_or_a_refusal(
    chat_page, master_doubles: MasterDoubles
) -> None:
    page, errors, _ = chat_page
    ctx = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id=TURN)
    approval = master_doubles.approvals.create(_kill_tool(), {}, ctx)
    _deliver(page, _created(approval))
    approve = page.locator(f"#shepherd-thread [data-approval-id='{approval.id}'] button", has_text="Approve")

    approve.click()
    page.wait_for_function("() => document.getElementById('shepherd-status').textContent === 'approved'")
    _both_events_leave_the_status(page, "approved")

    # The card keeps its buttons until `approval.decided` arrives, so a second
    # click is the compare-and-set loser (E-M4-1).
    approve.click()
    page.wait_for_function("() => document.getElementById('shepherd-status').textContent === 'already decided'")
    _both_events_leave_the_status(page, "already decided")

    master_doubles.refusal = "a turn is already running"
    _send(page, "and now?")
    page.wait_for_function(
        "() => document.getElementById('shepherd-status').textContent === 'a turn is already running'"
    )
    _both_events_leave_the_status(page, "a turn is already running")
    assert errors == [], errors


def test_a_send_clears_the_last_turns_event_line(chat_page, master_doubles: MasterDoubles) -> None:
    """REM-FIX 1 (2): the previous turn's ending does not sit beside the new turn's id."""
    page, errors, _ = chat_page
    _deliver(page, _ended(None))
    assert _event_line(page) == "turn ended · success"
    _send(page, "and now?")
    page.wait_for_function("id => document.getElementById('shepherd-status').textContent === id", arg=TURN_ID)
    assert _event_line(page) == ""
    assert errors == [], errors


def test_an_event_fills_an_empty_status_area(chat_page) -> None:
    """No send yet: the event line is what shows, and the status slot stays empty."""
    page, errors, _ = chat_page
    assert _event_line(page) == ""
    _deliver(page, _rate_limit("allowed"))
    assert _event_line(page) == "rate limit · allowed"
    assert _status(page) == ""
    assert errors == [], errors


# ----- the markup: a polite live region beside the status ---------------------


EVENT_LINE = re.compile(
    r'<p class="status" id="shepherd-status"></p>\s*'
    r'<p class="status event-line" id="shepherd-event" aria-live="polite"></p>'
)


@pytest.mark.parametrize(
    "page_file",
    [STATIC_ROOT / "index.html", FIXTURES / "shell_harness.html"],
    ids=["index", "shell_harness"],
)
def test_the_event_line_is_polite_live_region_beside_the_status(page_file) -> None:
    markup = page_file.read_text(encoding="utf-8")
    assert markup.count('id="shepherd-event"') == 1, page_file
    assert EVENT_LINE.search(markup) is not None, page_file
