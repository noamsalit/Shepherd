"""A replayed pipe for the vendor's client — the seam T21 is tested at.

**What is substituted, and what is not.** Exactly one thing: the pipe that would
otherwise hold a `claude` subprocess. `ClaudeSDKClient`, its `Query`, the control
protocol, the message parser, the permission callback and the in-process MCP
server are all the shipped vendor code, driven the way the CLI drives them. A
double that stood in for the *client* would be asserting that our projection
agrees with our own idea of the engine's shapes — the tautology this repo has
already paid for once (T27's survivor).

**The lines are the engine's own.** Every frame below is either lifted from a
probe capture or built to the shape `data-schemas.md` records, so the parser is
fed what the parser really meets.

**Nothing here starts a process, sends a signal, or leaves the interpreter.**
`tests/master/test_sdk_master.py`'s `live` check is the only thing in this task
that starts a real engine, and it is deselected by `addopts`.
"""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

import anyio
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.transport import Transport

Line = Mapping[str, Any]

SESSION = "f9a84381-89d6-482a-b8b2-0579bd370f80"


# ----- the frames, in the engine's own shapes ---------------------------------


def init_line(*, tools: Sequence[str] = (), session: str = SESSION) -> dict[str, Any]:
    """`system/init` — the line T22 asserts the isolation lock from."""
    return {
        "type": "system",
        "subtype": "init",
        "session_id": session,
        "cwd": "/tmp/shepherd-tape",
        "tools": list(tools),
        "mcp_servers": [{"name": "shepherd", "status": "connected", "source": "sdk"}],
        "plugins": [],
        "model": "claude-haiku-4-5",
        "uuid": "1dbbd7a6-0000-4000-8000-000000000001",
    }


def text_line(text: str, *, session: str = SESSION) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": None,
        },
        "parent_tool_use_id": None,
        "session_id": session,
        "uuid": "1dbbd7a6-0000-4000-8000-000000000002",
    }


def tool_call_line(
    name: str, args: Mapping[str, Any], *, use_id: str, session: str = SESSION
) -> dict[str, Any]:
    """A `tool_use` block under the engine's **prefixed** spelling of our name."""
    return {
        "type": "assistant",
        "message": {
            "id": "msg_02",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5",
            "content": [
                {
                    "type": "tool_use",
                    "id": use_id,
                    "name": f"mcp__shepherd__{name}",
                    "input": dict(args),
                }
            ],
            "stop_reason": "tool_use",
        },
        "parent_tool_use_id": None,
        "session_id": session,
        "uuid": "1dbbd7a6-0000-4000-8000-000000000003",
    }


def tool_result_line(use_id: str, text: str, *, session: str = SESSION) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": [{"type": "text", "text": text}],
                    "is_error": False,
                }
            ],
        },
        "parent_tool_use_id": None,
        "session_id": session,
        "uuid": "1dbbd7a6-0000-4000-8000-000000000004",
    }


def result_line(
    *,
    subtype: str = "success",
    terminal_reason: str | None = "completed",
    session: str = SESSION,
) -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": subtype,
        "duration_ms": 10,
        "duration_api_ms": 8,
        "is_error": subtype != "success",
        "num_turns": 1,
        "session_id": session,
        "total_cost_usd": 0.0,
        "usage": {},
        "result": "done",
        "terminal_reason": terminal_reason,
        "permission_denials": [],
        "uuid": "1dbbd7a6-0000-4000-8000-000000000005",
    }


def rate_limit_line(*, session: str = SESSION) -> dict[str, Any]:
    return {
        "type": "rate_limit_event",
        "session_id": session,
        "uuid": "1dbbd7a6-0000-4000-8000-000000000006",
        "rate_limit_info": {
            "status": "allowed",
            "resetsAt": 1789692000,
            "rateLimitType": "five_hour",
            "overageStatus": "rejected",
            "isUsingOverage": False,
        },
    }


def belt_request_line(tool: str, *, request_id: str = "req_belt_1") -> dict[str, Any]:
    """The `can_use_tool` control request P3 captured, verbatim in shape.

    This is the frame that makes DP7's belt **reachable** in a deterministic run:
    the CLI asks, the vendor's `Query` routes it to `can_use_tool`, and the
    answer comes back out of this pipe as a `control_response` we can read.
    """
    return {
        "type": "control_request",
        "request_id": request_id,
        "request": {
            "subtype": "can_use_tool",
            "tool_name": tool,
            "input": {"id": "ses_a1"},
            "display_name": "Shadow Tool",
            "permission_suggestions": [],
            "tool_use_id": "toolu_01NZscrf9wfervpK7MW5gbEK",
        },
    }


# ----- the pipe ----------------------------------------------------------------


class TapeTransport(Transport):
    """One connection, playing recorded frames and recording what was written.

    A turn's frames are released when the client writes the user message that
    opens that turn, which is the CLI's own order. `interrupt` is honoured the
    way the engine honours it: the rest of the turn is **dropped**, and the
    result the engine sends for an interrupted turn (P2:
    `error_during_execution` / `aborted_tools`) is delivered in its place.
    """

    def __init__(
        self,
        turns: Sequence[Sequence[Line]],
        *,
        watch: Callable[[str], None] | None = None,
    ) -> None:
        self._turns = [list(turn) for turn in turns]
        self._watch = watch or (lambda _event: None)
        self.written: list[dict[str, Any]] = []
        self.connects = 0
        self.closed = False
        self._ready = False
        self._send, self._receive = anyio.create_memory_object_stream[dict[str, Any]](
            math.inf
        )

    # -- Transport ---------------------------------------------------------

    async def connect(self) -> None:
        self.connects += 1
        self._ready = True

    async def write(self, data: str) -> None:
        for raw in data.splitlines():
            if raw.strip():
                self._handle(json.loads(raw))

    def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async def frames() -> AsyncIterator[dict[str, Any]]:
            async for frame in self._receive:
                yield frame

        return frames()

    async def close(self) -> None:
        self.closed = True
        self._ready = False
        self._send.close()

    def is_ready(self) -> bool:
        return self._ready

    async def end_input(self) -> None:
        return None

    # -- the engine's side --------------------------------------------------

    def _handle(self, message: dict[str, Any]) -> None:
        self.written.append(message)
        if message.get("type") == "control_request":
            subtype = str(message["request"].get("subtype"))
            self._watch(subtype)
            if subtype == "interrupt":
                self._interrupted()
            self._reply(message["request_id"], {})
            return
        if message.get("type") == "user":
            self._watch("user")
            self._play_turn()

    def _play_turn(self) -> None:
        turn = self._turns.pop(0) if self._turns else [result_line()]
        for frame in turn:
            self._send.send_nowait(dict(frame))

    def _interrupted(self) -> None:
        """Drop what the killed turn had left and end it the way P2 measured."""
        if self._turns:
            self._turns.pop(0)
        self._send.send_nowait(
            result_line(subtype="error_during_execution", terminal_reason="aborted_tools")
        )

    def _reply(self, request_id: str, payload: Mapping[str, Any]) -> None:
        self._send.send_nowait(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": dict(payload),
                },
            }
        )


def opener(
    *tapes: TapeTransport,
) -> tuple[Callable[[ClaudeAgentOptions], Transport], list[ClaudeAgentOptions]]:
    """A transport factory answering one tape per connection, and the options it saw.

    A **factory**, not an instance: a client is built per turn, and a connection
    that had already played its frames cannot answer the next one. The options
    are captured so a check can assert what the runtime *asked the engine for*
    on each connection — which is how "resume rebuilt the client" is observed
    without reaching inside it.
    """
    remaining = list(tapes)
    seen: list[ClaudeAgentOptions] = []

    def open_transport(options: ClaudeAgentOptions) -> Transport:
        seen.append(options)
        if not remaining:
            raise AssertionError("the runtime opened more connections than there are tapes")
        return remaining.pop(0)

    return open_transport, seen


# ----- one runtime, arranged to a script --------------------------------------


def frames_for(
    says: str,
    calls: Sequence[tuple[str, Mapping[str, Any]]],
    ends: str,
    *,
    tools: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """The frames an engine would send for one arranged turn.

    `ends` is the contract suite's word for how the turn finishes, and it is
    honoured with the engine's **own** endings: `turn_ended` is a `success`
    result and `error` is the `error_during_execution` / `aborted_tools` pair P2
    captured. An ending this function has no engine shape for is refused rather
    than approximated — a turn that ended differently from the way the row asked
    is a row asserting something nobody requested.
    """
    endings = {
        "turn_ended": result_line(),
        "error": result_line(
            subtype="error_during_execution", terminal_reason="aborted_tools"
        ),
    }
    if ends not in endings:
        raise AssertionError(f"no engine ending is recorded for {ends!r}")
    frames = [init_line(tools=tools), text_line(says)]
    for index, (name, arguments) in enumerate(calls):
        frames.append(tool_call_line(name, arguments, use_id=f"toolu_{index}"))
    frames.append(endings[ends])
    return frames
