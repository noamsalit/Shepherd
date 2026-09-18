"""T24 — §12's page 1, asserted on the bytes the server actually serves.

**Seam, stated because it bounds every claim below.** There is no browser, no
node and no npm on this host (G-M3-6, K10), so nothing here proves the page
*renders*. Every assertion is about bytes on disk or bytes on a socket: the
shipped static files parsed and never executed, plus real HTTP requests through
`invoke()` against a live loopback server. That the conversation appears, that a
card's two buttons resolve it and that the toggle moves is on T24's **manual**
checklist, exactly as M3's clause 11 says of the terminal.

The four lessons M3's T19 review paid for are the acceptance conditions here:

* **Reachability is a property of the graph.** `chat.js` is walked from
  `index.html`'s `<script>` tags by the shipped walker, and the walk is proved
  to *bite* on this page by re-running it over an `app.js` whose chat import has
  been removed in memory. M3 shipped a page nothing loaded and eight tests read
  it as text and passed.
* **A field crossing a JSON seam takes the producer's key list as its input.**
  The producers are called — `project_approval`, `project_to_stream` through
  `sse.envelope`, and the shipped `build_authorizer`'s own publish — and the
  page's reads are compared against what they emit.
* **`hidden` in static markup inverts a render assertion's failure direction**,
  so the renders are enumerated syntactically and compared as whole sets.
* **An allow-list's scope is itself a claim that needs a negative control**, so
  the HTML-sink scan runs over the shipped `fixtures/pty_sinks.js` too.
"""

from __future__ import annotations

import re
import threading
import time

from web.conftest import TURN_ID, Client, MasterDoubles

from shepherd.core.master import MasterEvent
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.master_turn import TurnRefused, TurnStarted, project_to_stream
from shepherd.toolsurface.approvals import (
    APPROVAL_CREATED_KIND,
    APPROVAL_DECIDED_KIND,
    ApprovalOutcome,
    ApprovalStore,
    build_authorizer,
)
from shepherd.toolsurface.audit import encode_audit_record
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.stream import StreamDelivery
from shepherd.toolsurface.tools_master import project_approval, project_turn
from shepherd.toolsurface.types import (
    ActorKind,
    AuditRecord,
    Audience,
    BlastClass,
    CallerContext,
    ToolDef,
)
from shepherd.web import sse


#: A quoted string is not a field read. `"approval.created"` is the event kind
#: this page dispatches on, and a scan that read it as `approval.created` would
#: report a field no producer emits — a false finding, which erodes a real gate
#: faster than a missing one. Template literals are **kept**: `${body.error}` is
#: a genuine read of the response envelope.
_QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")


def field_reads(text: str, identifier: str) -> set[str]:
    """Every attribute the page reads off `identifier`, comments and quotes out."""
    body = _QUOTED.sub('""', code_only(text))
    return set(re.findall(rf"\b{identifier}\.(\w+)", body))


def _audit_record() -> AuditRecord:
    """One decided call, as `invoke()` builds it. Only its **key list** is used."""
    return AuditRecord(
        at="2026-09-16T10:00:30Z",
        correlation_id="c-1",
        actor_kind=ActorKind.HUMAN,
        actor_id="web",
        tool="kill_session",
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        args={},
        autonomy_level=2,
        decision="allow",
        approved_by="user",
        approval_id="ap-1",
        result="ok",
        failure=None,
        duration_ms=3,
    )
from web.test_frontend_escaping import unsafe_sinks
from web.test_session_page import (
    FIXTURES,
    STATIC_ROOT,
    block_after,
    code_only,
    html_sink_findings,
    source,
)
from web.test_session_wiring import assignments, reachable_modules


def test_chat_js_is_reachable_from_the_page() -> None:
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    reached = reachable_modules(markup, source)
    assert "chat.js" in reached, sorted(reached)


# ----- the routes, through `invoke()` over a real socket ----------------------


def test_the_chat_page_posts_a_turn_through_invoke(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """§12's chat post, end to end: a POST on the declared path reaches
    `master_send`, and the driver double records the text it was handed."""
    response = client.post("/api/master/send", {"text": "what's blocked?"})
    assert response.status == 200, response.body
    body = response.json()
    assert body["ok"] is True, body
    assert master_doubles.sent == ["what's blocked?"]
    assert body["data"]["started"] is True
    assert body["data"]["turn_id"] == TURN_ID


def test_the_two_other_mutations_go_through_invoke(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """The card's buttons and D8's toggle, over the socket a browser has.

    **Arrival before absence, and the arrival is mutated**: the card is asserted
    `pending()` *before* it is decided and `()` after, so a `decide_approval`
    that answered without deciding anything, and a route that resolved to the
    wrong tool, are two different failures rather than one silent pass.
    """
    approval = master_doubles.approvals.create(
        ToolDef(
            name="kill_session",
            description="stop a session",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: None,
            audiences=frozenset({Audience.MASTER}),
        ),
        {},
        CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="c-1"),
    )
    assert [card.id for card in master_doubles.approvals.pending()] == [approval.id]

    listed = client.request("/api/approvals").json()
    assert listed["ok"] is True, listed
    assert [row["approval_id"] for row in listed["data"]["approvals"]] == [approval.id]

    decided = client.post(f"/api/approvals/{approval.id}", {"choice": "approve"})
    assert decided.status == 200, decided.body
    assert decided.json()["data"] == {
        "approval_id": approval.id,
        "decided": True,
        "outcome": "approved",
    }
    assert master_doubles.approvals.pending() == ()

    # D8's toggle: the level is readable before it is written, and the write
    # reports what it moved from — both through `invoke()`.
    assert client.request("/api/autonomy").json()["data"] == {"level": 2}
    moved = client.post("/api/autonomy", {"level": 3})
    assert moved.json()["data"] == {"level": 3, "previous": 2}
    assert client.request("/api/autonomy").json()["data"] == {"level": 3}


def test_a_refused_turn_is_a_result_and_not_an_error(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """RD7/E-M4-4: one turn at a time, and the refusal is readable.

    Rendering a refusal as a `Failure` would tell the page that posting failed
    when the reason is that a turn is already running — a different thing to say
    to a person, and the reason `project_turn` carries both answers in one shape.
    """
    master_doubles.refusal = "a turn is already running"
    body = client.post("/api/master/send", {"text": "again"}).json()
    assert body["ok"] is True, body
    assert body["data"] == {
        "started": False,
        "turn_id": None,
        "started_at": None,
        "reason": "a turn is already running",
    }


# ----- the module graph, and the walk proved to bite on this page -------------


def test_the_reachability_walk_bites_on_the_chat_import() -> None:
    """A reachability assertion is worth exactly what its negative control is.

    The same shipped walker is run twice over the same three files, differing by
    the one import line in `app.js`: without it `chat.js` is reported unreachable
    and with it, reached. A walk that returned everything — or that reached
    `chat.js` because some *other* module happened to name it — passes one of
    these and not both.

    The mutation is **in memory**, never on disk: `reachable_modules` takes its
    reader as a parameter, so the shipped bytes are read for every name but
    `app.js` and the live tree is not touched (RD-T19-7).
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    app = code_only(source("app.js"))
    assert 'from "./chat.js"' in app, "arrival: the bootstrap does not import the page"

    without_chat = "\n".join(
        line for line in app.splitlines() if 'from "./chat.js"' not in line
    )
    assert without_chat != app
    assert "./chat.js" not in without_chat

    def read(name: str) -> str:
        return without_chat if name == "app.js" else source(name)

    assert "chat.js" not in reachable_modules(markup, read)
    assert "chat.js" in reachable_modules(markup, source)


def test_the_shipped_reachability_rule_names_the_chat_page() -> None:
    """M3's rule, extended — `chat.js` is not merely reachable, it is *named*.

    `test_every_shipped_module_is_reachable_from_the_page` compares the whole
    shipped set against the walk, so `chat.js` is already covered by
    construction. It is named there as well, for the reason `session.js` and
    `terminal.js` are: the set difference says *something* is unreachable, and
    the names say *which page is dead* — which is the sentence the M3 review had
    to write by hand.
    """
    wiring = (
        STATIC_ROOT.parents[3] / "tests" / "web" / "test_session_wiring.py"
    ).read_text(encoding="utf-8")
    assert 'assert "chat.js" in reached' in wiring, wiring[:200]


# ----- §13: no HTML sink, with the negative control ---------------------------


def test_the_chat_page_has_no_html_sink() -> None:
    """§13: the master's output contains tool results, and it is untrusted.

    The page fills static markup with `textContent`, so the expected number of
    sinks is **zero** — and the scan is proved to see one by running the same
    function over `fixtures/pty_sinks.js`, which plants five. A scan scoped away
    from the real file, or a token list that had stopped matching, fails the
    second half rather than passing quietly on the first.
    """
    chat = source("chat.js")
    # Arrival: the scan really read the page, and the page really renders text.
    assert "textContent" in chat
    assert len(chat.splitlines()) > 100, len(chat.splitlines())

    assert html_sink_findings(chat) == []
    assert unsafe_sinks(chat) == []

    planted = (FIXTURES / "pty_sinks.js").read_text(encoding="utf-8")
    assert html_sink_findings(planted) != [], "the sink scan no longer sees a sink"
    assert unsafe_sinks(planted) != [], "the escaping scan no longer sees an interpolation"


def test_the_chat_page_asks_again_for_nothing() -> None:
    """§12: no polling anywhere in the UI, asserted on the page that is most
    tempted by it — a card that appears late is a turn that stays blocked.

    Every `fetch` in this file is inside a function whose caller is the first
    paint, a click, or an arriving event. The shapes that would make one
    periodic are absent, and the card path is asserted to be **on the stream**
    by name in `test_an_approval_card_renders_from_a_stream_event` below.
    """
    chat = code_only(source("chat.js"))
    assert "fetch(" in chat, "arrival: the page makes no call at all"
    for shape in ("setInterval", "setTimeout", "requestAnimationFrame", "EventSource"):
        assert shape not in chat, shape


# ----- the JSON seam: the producer's key list is the input --------------------


def _destructive_tool() -> ToolDef:
    return ToolDef(
        name="kill_session",
        description="stop a session",
        input_schema={"type": "object", "properties": {}},
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=lambda args, ctx: None,
        audiences=frozenset({Audience.MASTER}),
    )


def _master_context() -> CallerContext:
    return CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="c-1")


def approval_stream_events() -> list[StreamEvent]:
    """The two approval events the **shipped** authorizer publishes.

    Driven rather than constructed: the page's card is built from what
    `build_authorizer` puts on the ring, so a test that hand-built a
    `StreamEvent` would be comparing the page against a second author's idea of
    the payload — the seam M3's `action.label` crossed wrongly.

    Every wait here is bounded (5 s) and the worker's exit is asserted, because
    an implementation that never publishes must fail rather than hang: a mutant
    that hangs is not a red.
    """
    store = ApprovalStore()
    published: list[StreamEvent] = []
    authorize = build_authorizer(
        store=store,
        level=lambda: AutonomyLevel.LEVEL_2,
        publish=lambda event: (published.append(event), 0)[1],
        bump=lambda kind: None,
        now=lambda: "2026-09-16T10:00:30Z",
    )
    worker = threading.Thread(
        target=lambda: authorize(_destructive_tool(), {}, _master_context()),
        daemon=True,
    )
    worker.start()
    deadline = time.monotonic() + 5.0
    while store.pending() == () and time.monotonic() < deadline:
        time.sleep(0.01)
    raised = store.pending()
    assert raised != (), "arrival: level 2 raised no card for a destructive call"
    assert store.decide(raised[0].id, ApprovalOutcome.APPROVED)
    worker.join(timeout=5.0)
    assert not worker.is_alive(), "the gate never released the worker"
    assert [event.kind for event in published] == [
        APPROVAL_CREATED_KIND,
        APPROVAL_DECIDED_KIND,
    ], [event.kind for event in published]
    return published


def envelope_data(event: StreamEvent, seq: int = 1) -> dict[str, object]:
    body = sse.envelope(StreamDelivery(seq=seq, event=event))
    data = body["data"]
    assert isinstance(data, dict)
    return data


#: What each producer emits, as a literal. These are **requirements**, not
#: transcriptions: each is the key list one side of the JSON seam promises, and
#: comparing the producer against a literal is what stops the check becoming
#: `expected = producer(...)`, which passes by construction (T23's and T27's
#: surviving tautologies).
APPROVAL_ROW_KEYS = frozenset(
    {"approval_id", "turn_id", "tool", "summary", "created_at", "deadline_at"}
)
APPROVAL_CREATED_DATA_KEYS = frozenset(
    {"approval_id", "tool", "summary", "turn_id", "deadline_at"}
)
APPROVAL_DECIDED_DATA_KEYS = frozenset({"approval_id", "tool", "outcome"})
MASTER_EVENT_DATA_KEYS = frozenset({"turn_id", "text", "tool_name", "detail"})
ENVELOPE_KEYS = frozenset({"seq", "at", "type", "session_id", "project_id", "data"})
TURN_RESULT_KEYS = frozenset({"started", "turn_id", "started_at", "reason"})
DECISION_RESULT_KEYS = frozenset({"approval_id", "decided", "outcome"})
AUTONOMY_RESULT_KEYS = frozenset({"level", "previous"})
AUDIT_RESULT_KEYS = frozenset({"records", "limit"})
APPROVAL_LIST_KEYS = frozenset({"approvals"})


def test_the_page_reads_only_fields_the_projection_emits() -> None:
    """M3's `action.label`, one page over — and caught by construction this time.

    Both sides are enumerated. The producers are **called** (the shipped
    authorizer, `project_to_stream` through `sse.envelope`, `project_approval`,
    `project_turn`, `encode_audit_record`) and each is first compared against a
    literal key list, so a producer that drops a key fails here rather than
    silently shrinking the expectation. The page's reads are then scanned by the
    identifier they are read off, and every one must be a key some producer on
    that identifier actually emits.
    """
    created, decided = approval_stream_events()
    assert frozenset(envelope_data(created)) == APPROVAL_CREATED_DATA_KEYS
    assert frozenset(envelope_data(decided)) == APPROVAL_DECIDED_DATA_KEYS
    assert frozenset(sse.envelope(StreamDelivery(seq=1, event=created))) == ENVELOPE_KEYS

    master_event = MasterEvent(
        kind="text",
        text="two things.",
        tool_name=None,
        payload={},
        occurred_at="2026-09-16T10:00:31Z",
    )
    assert frozenset(envelope_data(project_to_stream(master_event, "turn-1"))) == (
        MASTER_EVENT_DATA_KEYS
    )

    card = ApprovalStore().create(_destructive_tool(), {}, _master_context())
    assert frozenset(project_approval(card)) == APPROVAL_ROW_KEYS
    assert frozenset(project_turn(TurnStarted(turn_id="t", started_at="a"))) == (
        TURN_RESULT_KEYS
    )
    assert frozenset(project_turn(TurnRefused(reason="busy"))) == TURN_RESULT_KEYS

    audit_keys = frozenset(encode_audit_record(_audit_record()))
    assert "args" in audit_keys, "arrival: the record really carries the arguments"

    chat = code_only(source("chat.js"))

    # `data.*` is read off a stream envelope's payload **and** off a tool
    # result, so the permitted set is the union of every producer the page can
    # be handed. A field no producer emits is what M3 shipped.
    emitted_data = (
        APPROVAL_CREATED_DATA_KEYS
        | APPROVAL_DECIDED_DATA_KEYS
        | MASTER_EVENT_DATA_KEYS
        | TURN_RESULT_KEYS
        | DECISION_RESULT_KEYS
        | AUTONOMY_RESULT_KEYS
        | AUDIT_RESULT_KEYS
        | APPROVAL_LIST_KEYS
    )
    read_data = field_reads(chat, "data")
    assert {"text", "approval_id", "level", "records"} <= read_data, sorted(read_data)
    assert read_data <= emitted_data, sorted(read_data - emitted_data)

    read_approval = field_reads(chat, "approval")
    assert read_approval != set(), "arrival: the card reads no field at all"
    assert read_approval <= APPROVAL_ROW_KEYS, sorted(read_approval - APPROVAL_ROW_KEYS)

    read_record = field_reads(chat, "record")
    assert "tool" in read_record, sorted(read_record)
    assert read_record <= audit_keys, sorted(read_record - audit_keys)
    # D25 is a *literal tail*, and §13's whitelist is at the sink: the record's
    # arguments are redacted for a log and a page is a wider audience than a log.
    assert "args" not in read_record

    read_envelope = field_reads(chat, "envelope")
    assert {"type", "data"} <= read_envelope, sorted(read_envelope)
    assert read_envelope <= ENVELOPE_KEYS, sorted(read_envelope - ENVELOPE_KEYS)


def test_the_response_envelope_the_page_reads_is_the_one_the_server_sends(
    client: Client,
) -> None:
    """The fourth producer, and the only one that can only be read off a socket."""
    body = client.request("/api/approvals").json()
    assert set(body) == {"ok", "data", "error", "correlation_id"}, sorted(body)
    read = field_reads(source("chat.js"), "body")
    assert read != set(), "arrival: the page reads no response field"
    assert read <= set(body), sorted(read - set(body))


# ----- the card, and where it comes from --------------------------------------


def test_an_approval_card_renders_from_a_stream_event() -> None:
    """§12: the card appears when the call blocks, not when a timer comes round.

    The event is the **shipped** authorizer's own, enveloped by the **shipped**
    `sse.envelope`, so the literal the page dispatches on is compared against
    the type a real blocked call actually puts on the wire — not against a
    constant this test chose. Renaming either side reddens it.

    That the card then *appears on a screen* is the manual checklist; what is
    checkable here is that the page builds it inside the stream handler, that
    its fields are the envelope's own, and that nothing asks again.
    """
    created, decided = approval_stream_events()
    raised = sse.envelope(StreamDelivery(seq=7, event=created))
    assert raised["type"] == APPROVAL_CREATED_KIND
    assert sse.envelope(StreamDelivery(seq=8, event=decided))["type"] == (
        APPROVAL_DECIDED_KIND
    )

    chat = code_only(source("chat.js"))
    assert f'const APPROVAL_CREATED = "{APPROVAL_CREATED_KIND}";' in chat
    assert f'const APPROVAL_DECIDED = "{APPROVAL_DECIDED_KIND}";' in chat

    handler = block_after(chat, "export function onChatEvent")
    assert handler is not None, "the stream handler is not a function on this page"
    assert "APPROVAL_CREATED" in handler, handler
    assert "approvalCard(" in handler, "the card is not built where the event arrives"
    assert "APPROVAL_DECIDED" in handler, handler
    assert "fetch(" not in handler, "the card branch asks the server again"

    # The card's fields are the ones that arrived, and no others.
    built = block_after(chat, "function cardFrom")
    assert built is not None
    from_data = frozenset(re.findall(r"\bdata\.(\w+)", built))
    assert from_data == frozenset({"approval_id", "tool", "summary", "deadline_at"})
    assert from_data <= frozenset(envelope_data(created))

    # …and the list is read exactly once, on the first paint. A second read site
    # is how a stream-fed rail quietly becomes a polled one.
    assert chat.count("read(APPROVALS)") == 1
    first_paint = block_after(chat, "export async function loadChat")
    assert first_paint is not None and "read(APPROVALS)" in first_paint


# ----- the renders, enumerated ------------------------------------------------


#: Every assignment `chat.js` is required to perform, and the requirement each
#: discharges. The enumeration rule is `test_session_wiring.assignments`' and is
#: not restated here: a single-line `target = value;` that is not a declaration.
#: The set is compared **whole**, so a render added, deleted or altered fails
#: here — which is what four surviving deletions in `session.js` cost to learn.
#:
#: **What this rule does not cover, said out loud:** `appendChild` is not an
#: assignment, so the three append sites (a chat line, a card, an audit line)
#: are covered by `test_an_approval_card_renders_from_a_stream_event` and by the
#: field scan instead. A rule that claimed to be total and was not would be
#: worse than one whose edge is stated.
REQUIRED_CHAT_ASSIGNMENTS = {
    # Principle 5's em dash, in the one place every slot on this page goes
    # through: a missing datum renders identically everywhere.
    "element.textContent = textOf(value)",
    # `line(className, text)`: the conversation, the audit tail and nothing else
    # build their nodes here, with the text as text.
    "element.className = className",
    "element.textContent = text",
    # §12's card: the tool, the redacted summary, the deadline, two buttons.
    # `args` are deliberately not among them (§13 at the sink).
    'card.className = "approval-card"',
    "card.dataset.approvalId = approval.approval_id",
    'tool.className = "approval-tool"',
    "tool.textContent = textOf(approval.tool)",
    'summary.className = "approval-summary"',
    "summary.textContent = textOf(approval.summary)",
    'deadline.className = "approval-deadline"',
    "deadline.textContent = textOf(approval.deadline_at)",
    "button.className = `approval-choice approval-${choice}`",
    "button.type = \"button\"",
    "button.textContent = choice",
    # The two words `decide_approval` accepts, carried by the card's own id —
    # never by its position in a list that may have moved underneath.
    "button.onclick = () => decide(approval.approval_id, choice)",
    # D8's toggle offers the level you are not on, and offers nothing at all
    # until one has been read: a guessed level beside a button is a lie a click
    # would act on.
    "next.textContent = state.level === null ? UNKNOWN : String(otherLevel(state.level))",
    "next.disabled = state.level === null",
    "state.level = data.level",
    # The composer clears on send, so a second click cannot repost the first
    # message into a turn that is already running.
    'input.value = ""',
    # The rail's state: a card arrives, a card leaves, and the first paint sets
    # both it and the level.
    "state.approvals = [...state.approvals, raised]",
    "state.approvals = without(state.approvals, data.approval_id)",
    "state.approvals = approvals.approvals",
    "state.level = autonomy.level",
    # `hidden` in static markup inverts the failure direction, so the reveal and
    # the hide are both enumerated: a deleted `view.hidden = false` is a page
    # that silently never appears, and every text assertion still passes.
    "view.hidden = false",
    "view.hidden = true",
    # The two controls §12's page 1 has. Bound to a name first so the rule can
    # see them: `slot("chat-send").onclick = …` is not an assignment this
    # enumeration can read, and an unwired button is exactly the defect
    # `#session-rename` shipped as for a whole task.
    "sendButton.onclick = () => send()",
    "toggle.onclick = () => toggleAutonomy()",
}


def test_render_chat_performs_every_assignment_the_spec_requires() -> None:
    performed = assignments(source("chat.js"))
    assert performed != [], "arrival: the enumeration read no assignment at all"
    assert len(performed) == len(set(performed)), "a duplicated render"
    assert set(performed) == REQUIRED_CHAT_ASSIGNMENTS, {
        "missing": sorted(REQUIRED_CHAT_ASSIGNMENTS - set(performed)),
        "unexpected": sorted(set(performed) - REQUIRED_CHAT_ASSIGNMENTS),
    }


def test_every_id_in_the_chat_view_is_wired_by_the_script() -> None:
    """The mirror M3 needed: an element the markup ships and nothing fills.

    `#session-rename` shipped as a button with no behaviour for a whole task
    because every check ran the other way round — slots ⊆ markup, which is blind
    to markup nothing wires. There is no exclusion list here: every element
    page 1 ships is an element page 1 fills.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    section = re.search(r'<section id="chat-view".*?</section>', markup, flags=re.DOTALL)
    assert section is not None, "arrival: page 1's markup is not in index.html"
    ids = set(re.findall(r'id="([^"]+)"', section.group(0)))
    ids.add("chat-view")
    assert len(ids) >= 8, sorted(ids)

    chat = source("chat.js")
    wired = set(re.findall(r"""(?:slot|fill)\(\s*["']([^"']+)["']""", chat))
    assert ids - wired == set(), sorted(ids - wired)

    # …and the nav entry §12 asks for, wired by the bootstrap that owns routing.
    app = code_only(source("app.js"))
    for entry in ("nav-chat", "nav-fleet", "fleet-view"):
        assert entry in app, entry
    assert 'id="nav-chat"' in markup and 'id="nav-fleet"' in markup


def test_the_chat_view_ships_hidden_and_the_fleet_ships_visible() -> None:
    """The direction `hidden` must fail in, asserted rather than assumed.

    Found by mutation: removing `hidden` from `#chat-view`'s static markup left
    the whole of `tests/web` green at 143 passed. `view.hidden = false` is
    enumerated, so a *deleted reveal* is caught — but a page that was **never
    hidden** reveals itself without the script, and every text-level assertion
    about it still passes. That is M3's lesson 3 arriving from the other side.

    The degrade is the point: with the module graph broken the browser shows the
    fleet — the M1 surface that needs no orchestrator — and not an empty
    conversation frame claiming a master that never answered.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    chat = re.search(r'<section id="chat-view"[^>]*>', markup)
    assert chat is not None, "arrival: page 1's section is not in index.html"
    assert " hidden" in chat.group(0), chat.group(0)

    fleet = re.search(r'<div id="fleet-view"[^>]*>', markup)
    assert fleet is not None, "arrival: the fleet is not in a view of its own"
    assert " hidden" not in fleet.group(0), fleet.group(0)

    # …and the bootstrap is what swaps them, so the two attributes are a degrade
    # rather than a page that renders both.
    app = code_only(source("app.js"))
    assert 'document.getElementById("fleet-view").hidden = true' in app, app
    assert "mountChat()" in app


def test_the_gap_branch_uses_the_streams_own_marker() -> None:
    """Principle 5 on the conversation: a dropped event is said, not hidden.

    The *wording* of the note is deliberately unpinned — nothing captured fixes
    its spelling, and a gate keyed on one sentence is defeated by a paraphrase
    (M3's R4), which is why rewording it is recorded as a **bad mutation** in
    `docs/plans/m4-blockers/t24.md` §T24-3 rather than asserted here. What is
    asserted is the structure a paraphrase cannot satisfy: the page has a gap
    branch, it reaches the conversation, and the kind it keys on is `sse.js`'s
    own exported marker rather than a literal this page chose — so the two
    cannot drift apart in silence.
    """
    chat = code_only(source("chat.js"))
    assert 'import { GAP } from "./sse.js";' in chat
    handler = block_after(chat, "export function onChatEvent")
    assert handler is not None
    assert "envelope.type === GAP" in handler, handler
    assert "say(" in handler, handler

    stream = code_only(source("sse.js"))
    assert 'export const GAP = "stream.gap";' in stream
    # …and the page never respells it.
    assert "stream.gap" not in chat
