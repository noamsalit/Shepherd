"""qa6 P14 — the Shepherd page in a real browser: BC-06 (step body), BC-25, BC-26.

**What is real here.** The server is the shipped `ThreadingHTTPServer` on an
ephemeral loopback port; `chat.js` is fetched from `/static/` by it; the shell
is the committed `fixtures/shell_harness.html` (the seam every UI regression
test uses, `test_settings_live.py`). The stream events are built by the
shipped producers — `project_to_stream` through `sse.envelope` for the master's
tool steps, the shipped `ApprovalStore` for the card — and handed to the page's
own `onShepherdEvent`, which is exactly what `app.js` does with every frame.

**What each test pins, and the qa6 scenario it answers.**

* BC-06 (U26 `ui.step_detail_not_object_object`, L1's recorded bodies): no
  tool step body is `[object Object]`. A call names its argument **keys** and
  never their values (the rule the approval card keeps for raw arguments); a
  result shows its text, or says it had none. How many steps a call and its
  result render as is the owner's question and is deliberately not asserted.
* BC-25 composer (U25 clauses 4 and 5): whitespace-only text posts nothing, and
  an Enter pressed while an IME composition is open posts nothing — while a
  multi-line message still posts byte for byte (the send is not trimmed).
* BC-26 (U30): an approval carried by both the first-paint read and the stream
  is one card, in either arrival order.

Skipped, not failed, where playwright or chromium is absent: an environment
fact, not a code defect.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from web.conftest import Client, MasterDoubles, hold_fetches

from shepherd.core.master import MasterEvent
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.master_turn import project_to_stream
from shepherd.toolsurface.approvals import Approval
from shepherd.toolsurface.stream import StreamDelivery
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, ToolDef
from shepherd.web import sse

pytest.importorskip("playwright.sync_api")

from web.test_settings_live import _harness_at  # noqa: E402 - after the skip

AT = "2026-09-24T10:00:00Z"
TURN = "turn-qa6-p14"

#: A value no page may print: it is an argument *value*, and the step names keys.
ARGUMENT_VALUE = "value-the-step-must-not-print"

MOUNT_ONLY = """
async (url) => {
  const chat = await import(url);
  chat.mountShepherd();
  document.getElementById("page-flock").hidden = true;
  document.getElementById("page-shepherd").hidden = false;
  window.__chat = chat;
  return true;
}
"""

DELIVER = "(envelope) => { window.__chat.onShepherdEvent(envelope); return true; }"


def _envelope(event: StreamEvent, seq: int) -> dict[str, object]:
    return sse.envelope(StreamDelivery(seq=seq, event=event))


def _master(kind: str, *, text: str | None, tool: str | None, payload: dict[str, object]) -> dict[str, object]:
    event = MasterEvent(kind=kind, text=text, tool_name=tool, payload=payload, occurred_at=AT)  # type: ignore[arg-type]
    return _envelope(project_to_stream(event, TURN), seq=1)


def _created(approval: Approval) -> dict[str, object]:
    """`approval.created` as the shipped authorizer publishes it (same five keys)."""
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
    return _envelope(event, seq=2)


def _kill_tool() -> ToolDef:
    return ToolDef(
        name="kill_session",
        description="stop a session",
        input_schema={"type": "object", "properties": {}},
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=lambda args, ctx: None,
        audiences=frozenset({Audience.MASTER}),
    )


@pytest.fixture()
def chat_page(client: Client) -> Iterator[tuple[Any, list[str], Any]]:
    """A chromium page on the committed harness with only `chat.js` mounted."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
            pytest.skip(f"chromium is not available: {exc}")
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on(
            "console",
            lambda message: errors.append(f"{message.type}: {message.text}")
            if message.type == "error"
            else None,
        )
        page.route(
            f"{client.origin}/__shell__",
            lambda route: route.fulfill(
                status=200, content_type="text/html", body=_harness_at(client.origin)
            ),
        )
        page.goto(f"{client.origin}/__shell__")
        page.evaluate(MOUNT_ONLY, f"{client.origin}/static/chat.js")
        yield page, errors, context
        browser.close()


# ----- BC-06: the step body ---------------------------------------------------


def test_no_step_renders_object_object(chat_page) -> None:
    page, errors, _ = chat_page
    call = _master(
        "tool_call",
        text=None,
        tool="spawn_session",
        payload={"tool_use_id": "tu-1", "input": {"cwd": ARGUMENT_VALUE, "brief": ARGUMENT_VALUE}},
    )
    result = _master(
        "tool_result", text="spawned s-1", tool="spawn_session",
        payload={"tool_use_id": "tu-1", "is_error": False},
    )
    silent = _master(
        "tool_result", text=None, tool="spawn_session",
        payload={"tool_use_id": "tu-1", "is_error": False},
    )
    bare = _master(
        "tool_call", text=None, tool="fleet_summary", payload={"tool_use_id": "tu-2", "input": {}}
    )
    for envelope in (call, result, silent, bare):
        page.evaluate(DELIVER, envelope)

    bodies = page.locator("#shepherd-thread .step-body").all_text_contents()
    assert len(bodies) == 4, bodies
    assert not any("[object Object]" in body for body in bodies), bodies
    # A call names its argument keys, and never a value.
    assert "brief" in bodies[0] and "cwd" in bodies[0], bodies[0]
    assert ARGUMENT_VALUE not in page.locator("#shepherd-thread").inner_text()
    # A result is its text; an empty one says so rather than showing a blank.
    assert bodies[1] == "spawned s-1", bodies[1]
    assert bodies[2] == "(no result text)", bodies[2]
    # A call with no arguments is still a readable line, not an object or a blank.
    assert bodies[3].strip() != "" and bodies[3] != "—", bodies[3]
    assert errors == [], errors


# ----- BC-25: the composer ----------------------------------------------------


def test_whitespace_only_text_posts_nothing(chat_page, master_doubles: MasterDoubles) -> None:
    page, errors, _ = chat_page
    page.locator("#shepherd-input").click()
    page.keyboard.type("   ")
    page.keyboard.press("Enter")
    page.locator("#shepherd-input").fill(" \n\t ")
    page.click("#shepherd-send")
    page.wait_for_timeout(250)
    assert master_doubles.sent == [], master_doubles.sent

    # The send is not trimmed: a real multi-line message still posts as typed.
    page.locator("#shepherd-input").fill("a\nb ")
    page.click("#shepherd-send")
    page.wait_for_timeout(250)
    assert master_doubles.sent == ["a\nb "], master_doubles.sent
    assert errors == [], errors


def test_enter_during_composition_posts_nothing(chat_page, master_doubles: MasterDoubles) -> None:
    page, errors, context = chat_page
    page.locator("#shepherd-input").click()
    cdp = context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": "日本", "selectionStart": 2, "selectionEnd": 2})
    assert page.locator("#shepherd-input").input_value() == "日本"
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    assert master_doubles.sent == [], master_doubles.sent

    # Once the composition is committed (`insertText` ends it), Enter is an
    # ordinary send. CDP's synthetic Enter above also inserted a newline, which
    # a real IME would consume, so the posted text is whatever the box holds.
    cdp.send("Input.insertText", {"text": "日本"})
    cdp.detach()
    committed = page.locator("#shepherd-input").input_value()
    assert committed.startswith("日本"), committed
    page.keyboard.press("Enter")
    page.wait_for_timeout(250)
    assert master_doubles.sent == [committed], master_doubles.sent
    assert errors == [], errors


# ----- BC-26: one card per approval -------------------------------------------


def _pending(master_doubles: MasterDoubles) -> Approval:
    ctx = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id=TURN)
    return master_doubles.approvals.create(_kill_tool(), {}, ctx)


def test_an_approval_in_both_the_load_read_and_the_stream_is_one_card(
    chat_page, master_doubles: MasterDoubles
) -> None:
    page, errors, _ = chat_page
    approval = _pending(master_doubles)
    card = f"#shepherd-thread [data-approval-id='{approval.id}']"

    # Order 1 (U30's): the stream event lands while the first-paint read is held.
    hold_fetches(page, "/api/approvals$")
    page.evaluate("() => { window.__load = window.__chat.loadShepherd(); return true; }")
    page.wait_for_function("() => window.__held.length === 1")
    page.evaluate(DELIVER, _created(approval))
    assert page.locator(card).count() == 1
    page.evaluate("() => window.__release()")
    page.evaluate("async () => { await window.__load; return true; }")
    assert page.evaluate("() => window.__delivered") == 1
    assert page.locator(card).count() == 1, page.locator("#shepherd-thread").inner_text()

    # Order 2: the read already painted it, and the stream carries it again.
    page.evaluate(DELIVER, _created(approval))
    assert page.locator(card).count() == 1

    # …and a second approval, carried only by the stream, is still shown.
    other = _pending(master_doubles)
    page.evaluate(DELIVER, _created(other))
    assert page.locator(f"#shepherd-thread [data-approval-id='{other.id}']").count() == 1
    assert page.locator("#shepherd-thread .approval").count() == 2
    assert errors == [], errors
