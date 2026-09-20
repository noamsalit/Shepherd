"""T21 — `AgentSDKMaster`, driven through the vendor's own client.

**The seam is the vendor's, not ours.** Every behavioural check below drives a
real `ClaudeSDKClient` over a replay transport (`tests/master/tape.py`): the
SDK's control protocol, its message parser and its permission callback all run,
and the only substitution is the pipe that would otherwise hold a `claude`
subprocess. A test that fed `AgentSDKMaster` objects we had constructed ourselves
would be asserting that our projection agrees with our own idea of the engine's
shapes, which is the tautology T27's survivor was.

**The projection's expected values come from the probe captures, not from the
code.** `test_every_captured_stream_object_projects` reads P1's raw stream off
disk, derives what each line *should* become from the line's own JSON, and
compares that to what the module produced. Neither side is the other's mirror.

**Deterministic and live are labelled** (DP10, `data-schemas.md`): the option
block proves nothing about isolation on its own, so the check that reads it says
so, and the one assertion that can only be made against a running engine is
`live`-marked and reads `system/init`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions, CLIConnectionError

from shepherd.core.anomalies import AnomalyKind
from shepherd.host.detect import detect_host
from shepherd.core.master import (
    CURATED_MASTER_FACTS,
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterRefusal,
)
from shepherd.master import projection, sdk_master
from shepherd.master.sdk_tools import TOOL_PREFIX, prefixed_names

from . import tape

#: Every wait in this file is bounded. A mutant that hangs is not a red: it
#: produces no verdict and stalls whoever runs the suite next (§T20-7, §T4).
TURN_TIMEOUT_S = 30.0

#: An opaque conversation id. The runtime owns what it means, so nothing here
#: parses it — it is only ever compared to itself.
CONVERSATION = "ses_01JBQ8Z9XKME5RT3VWNY6P0DFG"

REPO_ROOT = Path(__file__).resolve().parents[2]

FLEET_SUMMARY = ExportedTool(
    name="fleet_summary",
    description="The fleet, bounded at ~40 lines regardless of its size (§11).",
    input_schema={"type": "object", "properties": {}},
)
KILL_SESSION = ExportedTool(
    name="kill_session",
    description="End one session by id.",
    input_schema={
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
)
TOOLS: tuple[ExportedTool, ...] = (FLEET_SUMMARY, KILL_SESSION)

#: A server config shaped the way `create_sdk_mcp_server` returns one. The real
#: builder needs a caller id, a turn-id supplier and a counter (T20), none of
#: which the option block has any business holding — so the option-block check
#: mounts a stand-in and the behavioural checks below mount the real thing.
INERT_SERVER: object = {"type": "sdk", "name": "shepherd", "instance": None}


def options_for(
    tools: tuple[ExportedTool, ...] = TOOLS,
    resume_id: str | None = None,
) -> ClaudeAgentOptions:
    return sdk_master.build_options(
        tools=tools,
        system_prompt="You are the orchestrator.",
        resume_id=resume_id,
        model="claude-haiku-4-5",
        cli_path=None,
        belt=None,
        server=INERT_SERVER,  # type: ignore[arg-type]
    )


def test_the_option_block_locks_the_master() -> None:
    """D42's block, asserted field by field — **the deterministic half only**.

    DP10 and `data-schemas.md` are both explicit that this proves nothing about
    isolation on its own: `data-schemas.md` records a master whose option block
    looked exactly like this one while `system/init` listed `Bash`, `Read` and
    `Write` and it ran `echo hi`. What the engine *reports* is T22's assertion
    and the `live` check at the foot of this file; this one asserts only that we
    asked for the right thing.
    """
    options = options_for()

    assert options.tools == []  # D42 — the only option that removes built-ins
    assert options.strict_mcp_config is True  # D42 — no account connectors
    assert options.setting_sources == []  # D10 / P4 — not None: see the module
    assert options.disallowed_tools == ["Agent", "Task"]  # D10 — no subagents
    assert options.cwd is None
    assert options.cli_path is None  # E-M4-9 — the bundled binary
    assert options.model == "claude-haiku-4-5"  # §17 — never a constant

    # …as a **set**, and derived from the projection rather than written out: a
    # second list of tool names is the drift D32 deleted three lists to prevent.
    assert set(options.allowed_tools) == set(prefixed_names(TOOLS))
    assert set(options.allowed_tools) == {f"{TOOL_PREFIX}{t.name}" for t in TOOLS}
    assert options.allowed_tools, "an empty allow-list makes the set equality vacuous"

    mounted = options.mcp_servers
    assert isinstance(mounted, dict), mounted
    assert set(mounted) == {"shepherd"}
    assert options.resume is None
    assert options_for(resume_id="ses_7f3k").resume == "ses_7f3k"  # D10


def test_the_option_block_asks_for_no_settings_source_at_all() -> None:
    """`[]` and `None` are different questions, and P4 measured the difference.

    Same binary, same flag settings, same throwaway cwd: under `None` the host's
    cc10x plugin is loaded and `system/init.plugins` names it; under `[]` it is
    empty. A `None` here would be the isolation lock silently off, and no
    assertion on any other option value would notice.
    """
    empty = json.loads(
        (
            REPO_ROOT
            / "docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/answer.json"
        ).read_text(encoding="utf-8")
    )
    measured = {run["setting_sources"]: run["plugins"] for run in _p4_runs(empty)}
    assert measured[None], "P4's None run loaded no plugin — the capture moved"
    assert measured["[]"] == [], measured["[]"]
    assert options_for().setting_sources == []
    assert options_for().setting_sources is not None


def _p4_runs(answer: object) -> list[dict[str, object]]:
    """P4's two runs, keyed by the `setting_sources` they were given."""
    assert isinstance(answer, dict)
    runs = answer.get("runs", answer)
    assert isinstance(runs, (list, dict))
    found: list[dict[str, object]] = []
    for run in runs.values() if isinstance(runs, dict) else runs:
        if isinstance(run, dict) and "plugins" in run and "setting_sources" in run:
            sources = run["setting_sources"]
            found.append(
                {
                    "setting_sources": None if sources is None else "[]",
                    "plugins": run["plugins"],
                }
            )
    assert len(found) == 2, found
    return found




# ----- the projection, against the probe captures -----------------------------

PROBE_ROOT = REPO_ROOT / "docs/probes/2026-09-17-m4-sdk"

#: What a captured content block must become, derived from the block's own
#: `type` in the raw JSON. A block type absent from this table is a `KeyError`
#: rather than a silent skip: the capture growing a shape this module has never
#: seen is exactly the event that must go red.
BLOCK_KINDS: dict[tuple[str, str], str | None] = {
    ("assistant", "text"): "text",
    ("assistant", "thinking"): "thinking",
    ("assistant", "tool_use"): "tool_call",
    ("user", "tool_result"): "tool_result",
    # The echo of what we sent. It is not something the runtime emitted.
    ("user", "text"): None,
}

#: `ResultMessage.subtype` → the terminal kind, written from the vocabulary
#: `data-schemas.md` §ResultMessage records and P2 measured, not from the module.
RESULT_KINDS: dict[str, str] = {
    "success": "turn_ended",
    "error_during_execution": "error",
}


def captured_lines() -> list[tuple[Path, dict[str, object]]]:
    """Every message-shaped line the engine sent us, enumerated off the captures.

    `_dir == "in"` is the engine's half of the pipe; control traffic is the
    client's business and never reaches a projection. Enumerated rather than
    listed — a capture folder added to the probe directory is covered the day it
    lands.
    """
    message_types = {"assistant", "user", "result", "system", "rate_limit_event"}
    found: list[tuple[Path, dict[str, object]]] = []
    for capture in sorted(PROBE_ROOT.rglob("raw-stream.jsonl")):
        for raw in capture.read_text(encoding="utf-8").splitlines():
            record = json.loads(raw)
            line = record["line"]
            if record["_dir"] == "in" and line.get("type") in message_types:
                found.append((capture, line))
    return found


def expected_kinds(line: dict[str, object]) -> tuple[str, ...]:
    """What this captured line must project to, read out of the line itself."""
    kind = line["type"]
    if kind in ("assistant", "user"):
        message = line["message"]
        assert isinstance(message, dict)
        content = message["content"]
        if isinstance(content, str):
            return ()
        return tuple(
            mapped
            for block in content
            for mapped in (BLOCK_KINDS[(str(kind), block["type"])],)
            if mapped is not None
        )
    if kind == "result":
        return (RESULT_KINDS[str(line["subtype"])],)
    if kind == "rate_limit_event":
        return ("rate_limit",)
    return ()


def test_every_captured_stream_object_projects() -> None:
    """Every object the engine ever sent us, projected — **enumerated, not listed**.

    Two independent sources meet here: the expectation comes from the captured
    JSON's own `type`/`subtype` fields, and the actual comes from the module
    driving the SDK's own parser over the same line. Goes red if a kind is
    dropped, and red if the capture grows a shape `BLOCK_KINDS` does not name.
    """
    from claude_agent_sdk._internal.message_parser import parse_message

    lines = captured_lines()
    assert len(lines) > 50, len(lines)  # the enumerator found the captures

    seen: set[str] = set()
    names: dict[str, str] = {}
    previous: Path | None = None
    for capture, line in lines:
        if capture != previous:
            names, previous = {}, capture
        events = projection.project_events(
            parse_message(line), bump=lambda kind: None, tool_names=names
        )
        assert tuple(event.kind for event in events) == expected_kinds(line), (
            capture.name,
            line.get("type"),
            line.get("subtype"),
        )
        seen.update(event.kind for event in events)

    # …and the captures really do exercise every kind a real engine can emit.
    assert seen == {"text", "thinking", "tool_call", "tool_result", "rate_limit", "turn_ended", "error"}, sorted(seen)


# ----- the runtime, driven through the vendor's client ------------------------


def build_master(
    open_transport: Callable[[ClaudeAgentOptions], object],
    *,
    counted: list[AnomalyKind] | None = None,
    withdrawn: list[str] | None = None,
    order: list[str] | None = None,
    resume_id: str | None = None,
    turn: str = "01JBQ8Z9XKME5RT3VWNY6P0DFG",
) -> sdk_master.AgentSDKMaster:
    """One runtime with its three injected callables recording rather than acting."""

    def bump(kind: AnomalyKind) -> None:
        (counted if counted is not None else []).append(kind)

    def withdraw(turn_id: str) -> int:
        if order is not None:
            order.append("withdraw")
        (withdrawn if withdrawn is not None else []).append(turn_id)
        return 0

    master = sdk_master.AgentSDKMaster(
        caller_id="master",
        turn_id=lambda: turn,
        bump=bump,
        withdraw_turn_approvals=withdraw,
        model="claude-haiku-4-5",
        resume_id=resume_id,
        open_transport=open_transport,  # type: ignore[arg-type]
    )
    master.configure(TOOLS, "You are the orchestrator.")
    return master


def drain(master: sdk_master.AgentSDKMaster, text: str = "what needs me?") -> tuple[MasterEvent, ...]:
    """One whole turn, bounded. A turn that hangs is not a result (§T20-7)."""

    async def go() -> tuple[MasterEvent, ...]:
        async with asyncio.timeout(TURN_TIMEOUT_S):
            return tuple([event async for event in master.send(text)])

    return asyncio.run(go())


def a_turn(*, session: str = tape.SESSION) -> list[dict[str, object]]:
    return [
        tape.init_line(tools=list(prefixed_names(TOOLS)), session=session),
        tape.text_line("looking", session=session),
        tape.tool_call_line("fleet_summary", {}, use_id="toolu_1", session=session),
        tape.tool_result_line("toolu_1", "3 sessions", session=session),
        tape.result_line(session=session),
    ]


def kinds(events: Sequence[MasterEvent]) -> tuple[str, ...]:
    return tuple(event.kind for event in events)


def test_capabilities_answers_from_the_curated_table() -> None:
    """Every field of `MasterCapabilities`, against the curated fact it names.

    Enumerated with `dataclasses.fields()` on both sides: a hand-written list
    would stop covering the day DP8's decision not to add a sixth field is
    revisited, and the table is keyed by field name for exactly that reason.
    """
    record = build_master(tape.opener()[0]).capabilities()
    declared = [field.name for field in dataclasses.fields(MasterCapabilities)]
    assert declared, "MasterCapabilities enumerated no fields"
    assert set(declared) == set(CURATED_MASTER_FACTS), declared
    for name in declared:
        assert getattr(record, name) == CURATED_MASTER_FACTS[name].value, name


def test_a_turn_streams_what_the_engine_sent_and_ends_once() -> None:
    """The whole path, through the vendor's own parser and control protocol.

    **Arrival before anything else in this file**: the events moved, the tool's
    name arrived **unprefixed** (K13 — the prefix never leaves `master/`), and the
    engine's session id rode out on the payload under the spelling the turn
    driver reads it off.
    """
    pipe = tape.TapeTransport([a_turn()])
    opener, seen = tape.opener(pipe)
    master = build_master(opener)

    events = drain(master)

    assert kinds(events) == ("text", "tool_call", "tool_result", "turn_ended")
    assert [event.tool_name for event in events if event.kind == "tool_call"] == [
        "fleet_summary"
    ]
    assert all(TOOL_PREFIX not in (event.tool_name or "") for event in events)
    # …and the result is attributed to the call it answers. The engine sends a
    # result back with the `tool_use_id` and no name at all, so a runtime that
    # did not remember the call reports `None` here and a chat page shows an
    # answer with nothing to attach it to.
    assert [event.tool_name for event in events if event.kind == "tool_result"] == [
        "fleet_summary"
    ]
    assert events[-1].payload[projection.OUTCOME_KEY] == "success"
    assert events[0].payload[projection.MASTER_SESSION_KEY] == tape.SESSION
    assert len(seen) == 1, "one turn opened more than one connection"
    assert pipe.closed, "the turn left its connection open"


def test_the_session_key_has_one_spelling() -> None:
    """The driver reads the id off the payload; two spellings is a lost session.

    `orchestration/` is L3 and this is L5, so the constant cannot be imported
    here (§5.0) and is declared twice. That is exactly the shape §T4-3 caught
    between `audit.py` and the gate, and the repair is the same: a check that
    goes red on divergence rather than a comment asking for agreement.
    """
    from shepherd.orchestration.master_turn import MASTER_SESSION_KEY

    assert projection.MASTER_SESSION_KEY == MASTER_SESSION_KEY


def test_the_belt_denies_and_counts() -> None:
    """DP7's belt, reached the way P3 measured it — through the engine's own ask.

    The `can_use_tool` control request is delivered on the pipe in P3's captured
    shape, the vendor's `Query` routes it to the callback, and the answer is read
    back off the wire rather than by calling our own method. **Arrival first**:
    the response is asserted to have reached the pipe at all before its
    `behavior` is asserted, and the counter is asserted empty before the turn.
    """
    shadow = f"{TOOL_PREFIX}delete_everything"
    turn = [
        tape.init_line(tools=list(prefixed_names(TOOLS))),
        tape.belt_request_line(shadow),
        tape.result_line(),
    ]
    counted: list[AnomalyKind] = []
    pipe = tape.TapeTransport([turn])
    opener, _ = tape.opener(pipe)
    master = build_master(opener, counted=counted)
    assert counted == []  # arrival: the counter had not moved before the turn

    drain(master)

    answers = [
        written["response"]["response"]
        for written in pipe.written
        if written.get("type") == "control_response"
        and written["response"]["request_id"] == "req_belt_1"
    ]
    assert len(answers) == 1, pipe.written  # arrival: the belt answered on the wire
    assert answers[0]["behavior"] == "deny", answers[0]
    assert shadow in str(answers[0].get("message")), answers[0]
    assert counted == [AnomalyKind.MASTER_TOOL_UNEXPECTED], counted


def test_an_unmapped_result_counts_rather_than_raises() -> None:
    """G-M4-5: an ending we have no word for still ends the turn.

    P5 was deliberately not run — provoking `error_max_budget_usd` costs money —
    so the two unprovoked subtypes will first be met in production. The turn ends
    with `outcome="unknown"` and the counter moves; an exception here would be a
    chat page whose turn never ends because the engine used a word we did not
    recognise.
    """
    counted: list[AnomalyKind] = []
    turn = [tape.result_line(subtype="error_out_of_cheese", terminal_reason=None)]
    opener, _ = tape.opener(tape.TapeTransport([turn]))
    events = drain(build_master(opener, counted=counted))

    assert kinds(events) == ("turn_ended",)
    assert events[-1].payload[projection.OUTCOME_KEY] == projection.UNKNOWN_OUTCOME
    assert counted == [AnomalyKind.MASTER_RESULT_UNMAPPED], counted
    # …and a terminal reason nobody has seen takes the same counted path.
    counted.clear()
    strange = [tape.result_line(subtype="success", terminal_reason="taken_by_the_wind")]
    opener, _ = tape.opener(tape.TapeTransport([strange]))
    ending = drain(build_master(opener, counted=counted))[-1]
    assert ending.payload[projection.OUTCOME_KEY] == projection.UNKNOWN_OUTCOME
    assert counted == [AnomalyKind.MASTER_RESULT_UNMAPPED], counted


def test_a_result_that_ended_badly_is_still_one_turn() -> None:
    """P2's own ending, replayed: `error_during_execution` / `aborted_tools`."""
    turn = [
        tape.text_line("starting"),
        tape.result_line(subtype="error_during_execution", terminal_reason="aborted_tools"),
    ]
    opener, _ = tape.opener(tape.TapeTransport([turn]))
    events = drain(build_master(opener))

    assert kinds(events) == ("text", "error")
    assert events[-1].payload[projection.OUTCOME_KEY] == "error_during_execution"
    assert events[-1].kind in projection.TERMINAL_KINDS


def test_resume_rebuilds_the_client_and_persists_the_new_id() -> None:
    """DP9: a resume is a **new** connection, because the engine offers nothing else.

    **Arrival first**: the first connection is asserted to have opened, streamed
    and closed before `resume()` is called, so what the second turn shows is
    bound to the resume rather than to a runtime that never worked. Goes red if
    `resume()` mutates in place — which the SDK cannot do — because the second
    turn would then run on the first connection and its options would carry no
    resume id.
    """
    first = tape.TapeTransport([a_turn()])
    second = tape.TapeTransport([a_turn(session="ses_after_resume")])
    opener, seen = tape.opener(first, second)
    master = build_master(opener)

    assert master.conversation_id() is None
    assert kinds(drain(master))[-1] == "turn_ended"  # arrival: it worked
    assert first.connects == 1 and first.closed

    master.resume(CONVERSATION)
    assert master.conversation_id() == CONVERSATION  # arrival: the id landed

    events = drain(master, "where were we?")

    assert second.connects == 1, "resume did not rebuild the client"
    assert seen[0].resume is None and seen[1].resume == CONVERSATION
    assert master.conversation_id() == CONVERSATION  # …and a turn kept it
    # The engine's own id for the new subprocess is what gets persisted: it is a
    # different fact from the conversation, and the 2026-09-14 resume capture is
    # why — a resumed conversation came back under a new session id.
    assert events[0].payload[projection.MASTER_SESSION_KEY] == "ses_after_resume"


def test_a_lost_resume_starts_a_new_conversation_and_counts() -> None:
    """E-M4-8: the transcript is gone, so the conversation is new — and counted.

    **Arrival first**: the failing connection is asserted to have been attempted
    *with* the resume id before the recovery is asserted, so a runtime that never
    tried to resume at all cannot pass this.
    """
    counted: list[AnomalyKind] = []
    fresh = tape.TapeTransport([a_turn(session="ses_brand_new")])
    opened: list[ClaudeAgentOptions] = []

    def opener(options: ClaudeAgentOptions) -> object:
        opened.append(options)
        if len(opened) == 1:
            raise CLIConnectionError("no conversation found with session ID")
        return fresh

    master = build_master(opener, counted=counted, resume_id=CONVERSATION)
    events = drain(master)

    assert opened[0].resume == CONVERSATION  # arrival: it really tried
    assert opened[1].resume is None
    assert counted == [AnomalyKind.MASTER_RESUME_LOST], counted
    assert kinds(events)[-1] == "turn_ended"
    assert events[0].payload[projection.MASTER_SESSION_KEY] == "ses_brand_new"


def test_a_connection_that_fails_without_a_resume_is_raised_not_swallowed() -> None:
    """The negative half: a lost transcript is a recovery, an unreachable engine is not."""

    def opener(options: ClaudeAgentOptions) -> object:
        raise CLIConnectionError("the engine is not there")

    counted: list[AnomalyKind] = []
    with pytest.raises(CLIConnectionError):
        drain(build_master(opener, counted=counted))
    assert counted == [], counted


def test_interrupt_withdraws_before_it_touches_the_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-M4-3's order, asserted on a recording pipe rather than described.

    P2 measured that no cancellation reaches a running in-process handler, so the
    withdrawal is the only thing that can free a worker blocked in front of a
    card. Swapped, the engine would be told to stop while the thing actually
    holding the turn waited out its 600 s deadline — and every other assertion in
    this file would still pass.

    **Arrival first**: the turn is asserted to have reached the first call before
    the interrupt is issued, so the second call's absence is *because of* it.
    """
    order: list[str] = []
    turn_one = [
        tape.init_line(tools=list(prefixed_names(TOOLS))),
        tape.tool_call_line("fleet_summary", {}, use_id="toolu_1"),
    ]
    turn_two = [
        tape.tool_call_line("kill_session", {"id": "ses_7f3k"}, use_id="toolu_2"),
        tape.result_line(),
    ]
    pipe = tape.TapeTransport(
        [turn_one + turn_two], watch=lambda subtype: order.append(subtype)
    )
    opener, _ = tape.opener(pipe)
    withdrawn: list[str] = []
    master = build_master(opener, withdrawn=withdrawn, order=order)
    master.configure(TOOLS, "You are the orchestrator.")

    # **The observation point is the hand-off, not the wire.** The coroutine
    # `interrupt()` schedules does not begin until `interrupt()` has returned, so
    # a check watching the control request appear on the pipe records the
    # withdrawal first under *either* order and proves nothing. This records the
    # instant the runtime hands work to the engine, substituted at the module
    # global the method resolves at call time.
    scheduled = sdk_master.run_coroutine_threadsafe

    def watched(coroutine: object, loop: object) -> object:
        order.append("engine")
        return scheduled(coroutine, loop)  # type: ignore[arg-type]

    monkeypatch.setattr(sdk_master, "run_coroutine_threadsafe", watched)

    async def go() -> tuple[MasterEvent, ...]:
        seen: list[MasterEvent] = []
        async with asyncio.timeout(TURN_TIMEOUT_S):
            async for event in master.send("go"):
                seen.append(event)
                if (event.kind, event.tool_name) == ("tool_call", "fleet_summary"):
                    master.interrupt()
        return tuple(seen)

    events = asyncio.run(go())
    names = [event.tool_name for event in events if event.kind == "tool_call"]

    assert "fleet_summary" in names, kinds(events)  # arrival — the synchronisation
    assert "kill_session" not in names, names
    assert withdrawn == ["01JBQ8Z9XKME5RT3VWNY6P0DFG"], withdrawn
    # The order, as an assertion: the withdrawal is recorded before the engine
    # ever sees the interrupt control request.
    assert "engine" in order, order
    assert order.index("withdraw") < order.index("engine"), order
    # …and the engine really was told, on the wire, in the end.
    assert "interrupt" in order, order
    # …and the turn ended exactly once, last.
    ended = [event for event in events if event.kind in projection.TERMINAL_KINDS]
    assert len(ended) == 1 and events[-1] is ended[0], kinds(events)


def test_close_withdraws_and_then_refuses_every_later_turn() -> None:
    """DP9's teeth, and the withdrawal ADR-M4-3 puts in front of them.

    **Arrival first**: a turn is streamed before `close()`, so the refusal is
    bound to the close rather than to a runtime that never worked. Idempotent,
    because `daemons/shutdown.py` calls it unconditionally.
    """
    withdrawn: list[str] = []
    opener, _ = tape.opener(tape.TapeTransport([a_turn()]))
    master = build_master(opener, withdrawn=withdrawn)

    assert drain(master)  # arrival
    master.close()
    assert withdrawn == ["01JBQ8Z9XKME5RT3VWNY6P0DFG"], withdrawn

    with pytest.raises(MasterRefusal) as refused:
        drain(master)
    assert refused.value.reason, "the refusal carries no reason a caller could act on"

    master.close()
    with pytest.raises(MasterRefusal):
        drain(master)


# ----- the live half ----------------------------------------------------------


LIVE_TURN_TIMEOUT_S = 120.0
PID_GONE_TIMEOUT_S = 20.0

#: Everything that could tell a spawned engine it is inside this session. The
#: probe harness scrubs exactly these before it spawns a CLI, and a live check
#: that skipped it would be measuring this session rather than a fresh master.
INHERITED_PREFIXES = ("CLAUDE", "ANTHROPIC", "AI_AGENT")


def pid_is_alive(pid: int) -> bool:
    """The host seam, never a signal (D55, CLAUDE.md 2026-09-17).

    A liveness probe that sends a signal is a liveness probe that can end
    something, so `os.kill(pid, 0)` stays refused. `process_liveness` reads a
    table on both platforms — `/proc/<pid>/stat` on Linux, `ps -o lstart=` on
    macOS — and sends nothing.

    It was `Path(f"/proc/{pid}").exists()`, which on macOS is `False` for every
    pid. `test_close_terminates_the_cli` therefore failed at its *arrival*
    assertion (`assert pid_is_alive(pid)`) against a real engine that was
    running perfectly well.
    """
    return detect_host().process_liveness(pid, None).alive


@pytest.mark.live
def test_close_terminates_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one assertion no replayed pipe can make: a real engine, and its pid.

    **Arrival first, on the pid**: the turn is streamed until the engine's own
    process is found and asserted *alive*, and only then is `close()` called and
    the absence asserted. An implementation that never spawned anything would
    satisfy the absence perfectly, which is why the arrival is the assertion and
    not the comment.

    It also records `system/init` — the channel §18 says to assert the isolation
    lock from, *"do not trust it"* being said of the option block. What this
    check asserts of it is only that it arrived and names our server; the lock
    itself is T22's, deliberately, and is not pre-empted here.

    Explicit `--settings` into `tmp_path`, an empty cwd that is not the repo, and
    every inherited `CLAUDE*`/`ANTHROPIC*` variable scrubbed — the probe
    harness's own safety sequence. `~/.claude/` is never written.
    """
    settings = tmp_path / "flag-settings.json"
    settings.write_text("{}", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    for name in list(os.environ):
        if name.startswith(INHERITED_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(work)

    master = sdk_master.AgentSDKMaster(
        caller_id="master",
        turn_id=lambda: "01JBQ8Z9XKME5RT3VWNY6P0DFG",
        bump=lambda kind: None,
        withdraw_turn_approvals=lambda turn_id: 0,
        model="claude-haiku-4-5",
        settings=str(settings),
    )
    master.configure((), "Answer with the single word OK and stop there.")

    seen: list[MasterEvent] = []
    pids: list[int] = []

    async def go() -> None:
        async with asyncio.timeout(LIVE_TURN_TIMEOUT_S):
            async for event in master.send("Say OK."):
                seen.append(event)
                pid = engine_pid(master)
                if pid is not None and pid not in pids:
                    pids.append(pid)
                    assert pid_is_alive(pid), pid  # the arrival
                    master.close()

    asyncio.run(go())

    assert seen, "a live turn streamed nothing"
    assert pids, "no engine process was ever found — the arrival never happened"
    assert seen[-1].kind in projection.TERMINAL_KINDS, kinds(seen)

    reported = master.system_init()
    assert reported is not None, "the engine reported no system/init"
    servers = reported["mcp_servers"]
    assert isinstance(servers, list), servers
    assert [server["name"] for server in servers] == ["shepherd"]
    # `scratchpad/` is gitignored builder residue, so it exists on the host that
    # wrote this test and on no other. A clone that has never run a mutation
    # driver has no `m4-t21/`, and the evidence dump below then fails the test
    # after every assertion it exists to make has already passed.
    capture = REPO_ROOT / "scratchpad/m4-t21/system-init.json"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(
        json.dumps(reported, indent=2, sort_keys=True), encoding="utf-8"
    )

    deadline = time.monotonic() + PID_GONE_TIMEOUT_S
    while any(pid_is_alive(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert [pid for pid in pids if pid_is_alive(pid)] == [], pids


def engine_pid(master: sdk_master.AgentSDKMaster) -> int | None:
    """The engine's own pid, read off the vendor's transport.

    Private on both sides, and named as such: the seam has no pid reader and one
    added for a single live check would be a member with no production caller.
    """
    client = getattr(master, "_client", None)
    transport = getattr(client, "_transport", None)
    process = getattr(transport, "_process", None)
    pid = getattr(process, "pid", None)
    return int(pid) if isinstance(pid, int) else None
