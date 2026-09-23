"""`ToolCallingMaster` — the deterministic master for the INP lanes (test-plan Difference 5; env-plan §6).

The shipped `testkit.ScriptedMaster` records calls but never runs a tool (its
`Turn` docstring says so), so it can never raise an approval card. This one
does run them — **through the product's own `toolsurface.client.call`**, the
function the SDK MCP handler calls, so it cannot bypass the audience check, the
schema check, the gate or the audit record.

* A `MasterRuntime` with the six members (`configure`, `send`, `resume`,
  `interrupt`, `close`, `capabilities`).
* `send(text)` pops one `Turn(says, calls, ends)` from a thread-safe book the
  scenario fills. For each call it yields `tool_call`, then awaits
  `anyio.to_thread.run_sync(client.call, name, args, "master", turn_id)` (a
  worker thread, so a call blocked on an approval does not block the loop),
  then yields `tool_result` with `is_error` and records the result's text.
* A call's `args` may be a mapping **or a function of the earlier results in
  the same turn** (P10 needs the id `create_project` returned — review pass 1
  finding 14).
* An empty book ends the turn with `error`: a harness mis-script, and the
  scenario that sees it is BLOCKED, never FAIL.
* `interrupt()` sets a flag; the pending call is freed by the product's own
  `withdraw_all`, which the turn driver runs before `interrupt()`.

`shepherd.daemons.controld.build_master` is replaced by
`build_tool_calling_master` for one composition per pytest process
(`qa6/inp.py`); the real daemon has no fake-master switch (T2).
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field

import anyio

from shepherd.core.master import (
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterEventKind,
    MasterRefusal,
    MasterRuntime,
)
from shepherd.core.clock import utc_now
from shepherd.daemons.plane import MASTER_CALLER_ID
from shepherd.store.db import Store
from shepherd.testkit.scripted_master import SCRIPTED_CAPABILITIES
from shepherd.toolsurface import client

EMPTY_BOOK = "QA6-EMPTY-SCRIPT: no scripted turn was queued for this send (a harness mis-script: BLOCKED)"


@dataclass(frozen=True)
class CallResult:
    name: str
    args: Mapping[str, object]
    is_error: bool
    text: str
    raw: Mapping[str, object]


Args = Mapping[str, object] | Callable[[Sequence[CallResult]], Mapping[str, object]]


@dataclass(frozen=True)
class Call:
    name: str
    args: Args = field(default_factory=dict)


@dataclass(frozen=True)
class Turn:
    says: str
    calls: Sequence[Call] = ()
    ends: MasterEventKind = "turn_ended"


@dataclass
class TurnRecord:
    turn_id: str
    text: str
    results: list[CallResult] = field(default_factory=list)
    interrupted: bool = False
    ended: str = ""


class ScriptBook:
    """The queue of scripted turns and the record every turn leaves, across runtimes.

    `build_master` is called per turn, so the record cannot live on one
    runtime: this book is process-global for the one composition.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turns: deque[Turn] = deque()
        self.records: list[TurnRecord] = []
        self.configured_tools: tuple[ExportedTool, ...] = ()
        self.system_prompts: list[str] = []
        self.resumed: list[str] = []
        self.interrupts = 0
        self.runtimes = 0

    def push(self, *turns: Turn) -> None:
        with self._lock:
            self._turns.extend(turns)

    def pop(self) -> Turn | None:
        with self._lock:
            return self._turns.popleft() if self._turns else None

    def pending(self) -> int:
        with self._lock:
            return len(self._turns)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()


BOOK = ScriptBook()


def _event(kind: MasterEventKind, *, text: str | None = None, tool_name: str | None = None,
           payload: Mapping[str, object] | None = None) -> MasterEvent:
    return MasterEvent(kind=kind, text=text, tool_name=tool_name, payload=dict(payload or {}), occurred_at=utc_now())


def _result_text(raw: Mapping[str, object]) -> str:
    content = raw.get("content")
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return ""


class ToolCallingMaster:
    """One turn's runtime. Six members; `close()` makes `send()` refuse (DP9)."""

    def __init__(self, turn_id: str, book: ScriptBook = BOOK) -> None:
        self.turn_id = turn_id
        self.book = book
        self.closed = False
        self._interrupted = False
        book.runtimes += 1

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        self.book.configured_tools = tools
        self.book.system_prompts.append(system_prompt)

    async def send(self, text: str) -> AsyncIterator[MasterEvent]:
        if self.closed:
            raise MasterRefusal("this ToolCallingMaster is closed")
        record = TurnRecord(turn_id=self.turn_id, text=text)
        self.book.records.append(record)
        turn = self.book.pop()
        if turn is None:
            record.ended = "error"
            yield _event("error", text=EMPTY_BOOK)
            return
        yield _event("text", text=turn.says)
        for step in turn.calls:
            if self._interrupted:
                break
            args = step.args(tuple(record.results)) if callable(step.args) else step.args
            yield _event("tool_call", tool_name=step.name, payload=dict(args))
            raw = await anyio.to_thread.run_sync(client.call, step.name, dict(args), MASTER_CALLER_ID, self.turn_id)
            result = CallResult(name=step.name, args=dict(args), is_error=bool(raw.get("is_error")),
                                text=_result_text(raw), raw=dict(raw))
            record.results.append(result)
            yield _event("tool_result", tool_name=step.name, payload={"is_error": result.is_error, "text": result.text})
        record.interrupted = self._interrupted
        record.ended = turn.ends
        yield _event(turn.ends, payload={"interrupted": self._interrupted})

    def resume(self, master_session_id: str) -> None:
        self.book.resumed.append(master_session_id)

    def interrupt(self) -> None:
        self.book.interrupts += 1
        self._interrupted = True

    def capabilities(self) -> MasterCapabilities:
        return SCRIPTED_CAPABILITIES

    def close(self) -> None:
        self.closed = True


def build_tool_calling_master(store: Store, turn_id: str) -> ToolCallingMaster:
    """The drop-in for `shepherd.daemons.controld.build_master` (same signature).

    Mirrors the product's per-turn factory in what it hands the runtime: the
    master's exported tool set, and a resume of the stored conversation id if
    one exists — the scripted runtime records both.
    """
    runtime = ToolCallingMaster(turn_id)
    runtime.configure(client.master_tools(), "QA6 ToolCallingMaster: scripted, no model")
    conversation = store.get_app_state("master_session_id")
    if isinstance(conversation, str) and conversation:
        runtime.resume(conversation)
    return runtime


def conforms(turn_id: str) -> MasterRuntime:
    """Static proof (mypy --strict) that `ToolCallingMaster` satisfies the six-member seam."""
    return ToolCallingMaster(turn_id)
