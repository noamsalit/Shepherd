"""T20 — the vendor-shaped half of D32's exporter, driven through the real SDK.

**The seam is the vendor's own server.** `build_sdk_server` returns an
`McpSdkServerConfig` whose `instance` is a real `mcp.server.Server`, and every
translation assertion below drives that server's own `tools/list` and
`tools/call` handlers rather than reading back the objects this module built.
Testing the intermediate would be the tautology T27 survived: the projection
checked against the thing that produced it. Measured against mcp 2.2.0 /
claude-agent-sdk 0.2.153 — the versions P1 re-pinned.

Only `call` is substituted, at the module global the handler resolves at call
time. Everything else — `@tool`, `create_sdk_mcp_server`, jsonschema
validation, the content conversion — is the shipped vendor path.
"""

from __future__ import annotations

import ast
import threading
from collections.abc import Callable, Iterator, Mapping
from functools import partial
from pathlib import Path

import anyio
import mcp.types as mcp_types
import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import ExportedTool
from shepherd.master import sdk_tools
from shepherd.toolsurface import client
from shepherd.toolsurface.approvals import Approval, ApprovalOutcome, ApprovalStore
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, ToolDef

SRC = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: The three tools every translation test is driven over. The schemas are
#: **written out here as literals** rather than derived from anything the
#: module under test can see: an expected value computed the way the code
#: computes it cannot disagree with it.
FLEET_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {"detail": {"type": "string"}},
}
SPAWN_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {"project_id": {"type": "string"}, "task": {"type": "string"}},
    "required": ["project_id", "task"],
}
ASK_SCHEMA: Mapping[str, object] = {"type": "object", "properties": {}}

TOOLS: tuple[ExportedTool, ...] = (
    ExportedTool("fleet_summary", "Summarise the fleet.", FLEET_SCHEMA),
    ExportedTool("spawn_session", "Start a session on a task.", SPAWN_SCHEMA),
    ExportedTool("ask_session", "Ask a running session a question.", ASK_SCHEMA),
)

#: How long the substituted gate waits. Long enough that a slow host is not a
#: failure, short enough that a release that never comes is a red rather than a
#: hang — the approval's own deadline stays 600 s out, which is what the
#: "released before the deadline" assertion reads.
CALLER_DEADLINE_S = 30.0

CALLER = "master-1"
TURN = "01JB0TURNID0000000000000000"


def a_bump() -> tuple[list[AnomalyKind], Callable[[AnomalyKind], None]]:
    """A counter the master is *handed* — injection, not an import (K24, D19)."""
    seen: list[AnomalyKind] = []
    return seen, seen.append


def wire_tools(config: Mapping[str, object]) -> list[mcp_types.Tool]:
    """`tools/list`, asked of the vendor's server the way the CLI asks it."""
    server = config["instance"]
    entry = server.get_request_handler("tools/list")  # type: ignore[attr-defined]

    async def ask() -> list[mcp_types.Tool]:
        return list((await entry.handler(None, None)).tools)

    return anyio.run(ask)


def on_the_wire(entries: list[mcp_types.Tool]) -> list[Mapping[str, object]]:
    """The entries as the CLI receives them — camel keys, `None`s dropped.

    `Tool.input_schema` is the Python attribute; `inputSchema` is the wire key
    P1 captured, and `dump_jsonrpc` reaches it with exactly this dump. Asserting
    on the attribute would assert on mcp's Python spelling rather than on the
    shape the model is told.
    """
    return [
        {
            key: value
            for key, value in entry.model_dump(
                by_alias=True, mode="json", exclude_none=True
            ).items()
            if key in {"name", "description", "inputSchema"}
        }
        for entry in entries
    ]


async def call_tool(
    config: Mapping[str, object], name: str, args: Mapping[str, object]
) -> mcp_types.CallToolResult:
    """`tools/call`, on the vendor's server, inside the caller's event loop."""
    server = config["instance"]
    entry = server.get_request_handler("tools/call")  # type: ignore[attr-defined]
    params = mcp_types.CallToolRequestParams(name=name, arguments=dict(args))
    result: mcp_types.CallToolResult = await entry.handler(None, params)
    return result


@pytest.fixture
def substituted_call(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[tuple[str, Mapping[str, object], str, str]]]:
    """Record what the handler asks the tool-surface client for."""
    seen: list[tuple[str, Mapping[str, object], str, str]] = []

    def fake_call(
        name: str, args: Mapping[str, object], caller_id: str, correlation_id: str
    ) -> Mapping[str, object]:
        seen.append((name, dict(args), caller_id, correlation_id))
        return {"content": [{"type": "text", "text": f"ran {name}"}], "is_error": False}

    monkeypatch.setattr(sdk_tools, "call", fake_call)
    yield seen


# ----- translation ------------------------------------------------------------


def test_every_exported_tool_becomes_one_sdk_tool() -> None:
    """Both sides enumerated, compared as sets — never a count.

    The enumeration rule: the expected set is *every* `ExportedTool` handed in,
    read off the input tuple; the actual set is what the vendor's own
    `tools/list` answers. A dropped tool and a mangled name are two different
    failures of the same equality.
    """
    seen, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
    )

    assert config["type"] == "sdk"
    assert config["name"] == sdk_tools.MCP_SERVER_KEY == "shepherd"

    expected = {tool.name for tool in TOOLS}
    assert expected, "the fixture exports nothing — the equality below is vacuous"
    assert {entry.name for entry in wire_tools(config)} == expected
    assert set(sdk_tools.prefixed_names(TOOLS)) == {
        f"mcp__shepherd__{name}" for name in expected
    }
    assert seen == []


def test_the_schema_and_description_reach_the_wire_unchanged() -> None:
    """D53 at this boundary, asserted against literals and against the branch.

    `_build_input_schema` passes a dict through only when it has a string
    `type` **and** `properties` (P1, re-confirmed at 0.2.153). The first half
    asserts the pass-through against the schemas written above; the second
    drives a schema **without** `properties` through the same vendor code and
    watches it become a different tool — which is what makes the first half an
    assertion rather than a coincidence.
    """
    _, bump = a_bump()
    entries = {
        entry["name"]: entry
        for entry in on_the_wire(
            wire_tools(
                sdk_tools.build_sdk_server(
                    TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
                )
            )
        )
    }
    # The whole entry, in P1's captured spelling: `{"name", "description",
    # "inputSchema"}`, camel because the key is MCP's wire and not ours.
    assert entries["spawn_session"] == {
        "name": "spawn_session",
        "description": "Start a session on a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["project_id", "task"],
        },
    }
    assert entries["ask_session"]["inputSchema"] == {
        "type": "object",
        "properties": {},
    }

    mangled = ExportedTool("mangle_me", "d", {"project_id": str})
    other = on_the_wire(
        wire_tools(
            sdk_tools.build_sdk_server(
                (mangled,), CALLER, turn_id=lambda: TURN, bump=bump
            )
        )
    )
    assert other[0]["inputSchema"] == {
        "type": "object",
        "properties": {"project_id": {"type": "string"}},
        "required": ["project_id"],
    }


def test_the_handler_calls_the_client_with_our_own_name(
    substituted_call: list[tuple[str, Mapping[str, object], str, str]],
) -> None:
    """K13: the prefix is a vendor detail and never reaches the tool surface."""
    _, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
    )

    async def drive() -> mcp_types.CallToolResult:
        return await call_tool(config, "spawn_session", {"project_id": "p1", "task": "t"})

    result = anyio.run(drive)
    assert substituted_call == [
        ("spawn_session", {"project_id": "p1", "task": "t"}, CALLER, TURN)
    ]
    assert result.is_error is False
    assert [block.text for block in result.content] == ["ran spawn_session"]


# ----- ADR-M4-3: the blocking call runs off the loop ---------------------------


class BlockingCall:
    """A substituted `call` that blocks its thread the way `invoke()` can.

    §11's gate waits up to 600 s inside `invoke()`. This is that, in
    milliseconds: it records the thread it ran on, waits for a release, and
    says whether it is still waiting — which is what lets a test assert that a
    worker was **still blocked** at the moment the loop made progress.
    """

    def __init__(self) -> None:
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()
        self.in_flight = 0
        self.max_in_flight = 0
        self.returned: list[str] = []
        self.correlation_ids: list[str] = []
        self._lock = threading.Lock()

    def __call__(
        self, name: str, args: Mapping[str, object], caller_id: str, correlation_id: str
    ) -> Mapping[str, object]:
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.correlation_ids.append(correlation_id)
        self.entered.release()
        try:
            self.release.wait(10.0)
        finally:
            with self._lock:
                self.in_flight -= 1
            self.returned.append(name)
        return {"content": [{"type": "text", "text": f"ran {name}"}], "is_error": False}

    def wait_until_entered(self, count: int = 1) -> bool:
        return all(self.entered.acquire(timeout=5.0) for _ in range(count))


@pytest.fixture
def blocking_call(monkeypatch: pytest.MonkeyPatch) -> Iterator[BlockingCall]:
    blocker = BlockingCall()
    monkeypatch.setattr(sdk_tools, "call", blocker)
    try:
        yield blocker
    finally:
        blocker.release.set()


def test_a_blocking_tool_does_not_stall_the_loop(blocking_call: BlockingCall) -> None:
    """P-M4-11 / DP5. The loop that reads the CLI's stdout keeps running.

    **Arrival before absence, and the arrival is mutated**: a sibling coroutine
    is asserted to have made progress *while* the blocking call was still in
    flight (`in_flight == 1` at the moment the ticks were counted), then the
    call is released and its result asserted. Made inline, the handler pins the
    loop, the sibling never ticks, and `fail_after` fires — which is the single
    mutation DP5 exists to prevent.
    """
    _, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
    )
    ticks = 0

    async def drive() -> mcp_types.CallToolResult:
        nonlocal ticks
        result: list[mcp_types.CallToolResult] = []

        async def one() -> None:
            result.append(await call_tool(config, "fleet_summary", {"detail": "x"}))

        with anyio.fail_after(10.0):
            async with anyio.create_task_group() as group:
                group.start_soon(one)
                assert await anyio.to_thread.run_sync(blocking_call.wait_until_entered)
                for _ in range(5):
                    await anyio.sleep(0.01)
                    ticks += 1
                assert blocking_call.in_flight == 1, "the worker had already returned"
                assert blocking_call.returned == []
                blocking_call.release.set()
        return result[0]

    answer = anyio.run(drive)
    assert ticks == 5
    assert blocking_call.returned == ["fleet_summary"]
    assert [block.text for block in answer.content] == ["ran fleet_summary"]


def test_the_limiter_is_pinned_not_inherited(blocking_call: BlockingCall) -> None:
    """Two calls, one at a time (RD12). anyio's inherited default is 40.

    Asserted behaviourally rather than by reading the keyword: the second call
    is proved to still be *outside* `invoke()` while the first blocks. With
    `limiter=` omitted both enter at once and `max_in_flight` is 2.
    """
    assert sdk_tools.MASTER_TOOL_LIMITER.total_tokens == 1
    _, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
    )

    async def drive() -> None:
        with anyio.fail_after(10.0):
            async with anyio.create_task_group() as group:
                group.start_soon(call_tool, config, "fleet_summary", {"detail": "a"})
                group.start_soon(call_tool, config, "ask_session", {})
                assert await anyio.to_thread.run_sync(blocking_call.wait_until_entered)
                for _ in range(5):
                    await anyio.sleep(0.01)
                assert blocking_call.max_in_flight == 1
                blocking_call.release.set()

    anyio.run(drive)
    assert sorted(blocking_call.returned) == ["ask_session", "fleet_summary"]
    assert blocking_call.max_in_flight == 1


def test_a_handler_abandons_rather_than_pins_the_loop(
    blocking_call: BlockingCall,
) -> None:
    """`abandon_on_cancel=True`, and the orphan it produces is counted (K24).

    The cancellation is asserted to land **while the worker is still inside the
    blocking call** — which is exactly what the default (`False`, "ignore
    cancellations in the host task until the operation has completed in the
    worker") cannot do: at the default the scope could not close until the
    worker returned, and the `fail_after` below would fire.

    `MASTER_TOOL_RESULT_ORPHANED` is bumped through the **injected** counter,
    never a store this module could not import (D19).
    """
    seen, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
    )

    async def drive() -> None:
        with anyio.fail_after(5.0):
            async with anyio.create_task_group() as group:
                group.start_soon(call_tool, config, "fleet_summary", {"detail": "a"})
                assert await anyio.to_thread.run_sync(blocking_call.wait_until_entered)
                assert blocking_call.in_flight == 1
                group.cancel_scope.cancel()

    anyio.run(drive)
    assert blocking_call.in_flight == 1, "the worker was not abandoned; it was waited on"
    assert blocking_call.returned == []
    assert seen == [AnomalyKind.MASTER_TOOL_RESULT_ORPHANED]
    blocking_call.release.set()


# ----- the key the release path matches on (ADR-M4-3, §T4-2) ------------------


@pytest.fixture
def bind() -> Iterator[Callable[[ApprovalStore], None]]:
    """Wire the composition root's side of T16's seam, and unwire it after.

    `bind_master_client` is the root's verb, never the master's (RD-T16-1), so
    a test standing in for the root is where it belongs.
    """

    def wire(store: ApprovalStore) -> None:
        client.bind_master_client(
            withdraw_approval=store.withdraw,
            withdraw_turn_approvals=store.withdraw_all,
            autonomy_level=lambda: 2,
            )

    try:
        yield wire
    finally:
        client.reset_master_client()


def test_a_withdrawal_releases_the_blocked_call_before_its_deadline(
    bind: Callable[[ApprovalStore], None],
) -> None:
    """The handler's `correlation_id` **is** the turn id, proved by the release.

    §T4-2: `ApprovalStore.create()` reads `turn_id` off `ctx.correlation_id`,
    and `withdraw_all(turn_id)` matches on it — so a handler passing anything
    else leaves every blocked worker riding its full 600 s deadline while every
    test stays green. This drives the **real** store: a card is raised inside
    the substituted `call`, the worker blocks in `await_decision`, and the sweep
    T27 runs on `interrupt_master()` is what releases it.

    **The clock is injected and never advances**, so "it was withdrawn" cannot
    be the timeout wearing a different name (P-M4-22's shape at this seam):
    `deadline_at` stays 600 s in the future for the whole test.
    """
    # The wall clock is injected (the card's own `deadline_at` is then an exact
    # literal, ten minutes out); `monotonic` is real, so a key that matches
    # nothing ends as a **readable timeout** instead of a suite that hangs.
    store = ApprovalStore(now=lambda: "2026-09-17T12:00:00.000Z", timeout_s=600.0)
    gate = ToolDef(
        name="spawn_session",
        description="Start a session on a task.",
        input_schema=SPAWN_SCHEMA,
        blast_class=BlastClass.LOCAL_WRITE,
        handler=lambda args, ctx: None,
        audiences=frozenset({Audience.MASTER}),
    )
    raised: list[Approval] = []
    entered = threading.Semaphore(0)
    bind(store)

    def gated_call(
        name: str, args: Mapping[str, object], caller_id: str, correlation_id: str
    ) -> Mapping[str, object]:
        approval = store.create(
            gate,
            args,
            CallerContext(
                audience=Audience.MASTER,
                caller_id=caller_id,
                correlation_id=correlation_id,
            ),
        )
        raised.append(approval)
        entered.release()
        outcome = store.await_decision(approval.id, CALLER_DEADLINE_S)
        return {
            "content": [{"type": "text", "text": outcome.value}],
            "is_error": outcome is not ApprovalOutcome.APPROVED,
        }

    _, bump = a_bump()

    async def drive(monkeypatch: pytest.MonkeyPatch) -> mcp_types.CallToolResult:
        monkeypatch.setattr(sdk_tools, "call", gated_call)
        config = sdk_tools.build_sdk_server(
            TOOLS, CALLER, turn_id=lambda: TURN, bump=bump
        )
        answers: list[mcp_types.CallToolResult] = []

        async def one() -> None:
            answers.append(
                await call_tool(
                    config, "spawn_session", {"project_id": "p1", "task": "t"}
                )
            )

        with anyio.fail_after(10.0):
            async with anyio.create_task_group() as group:
                group.start_soon(one)
                assert await anyio.to_thread.run_sync(
                    partial(entered.acquire, True, 10.0)
                ), "no card was raised — the gate was never reached"
                # Arrival: the card exists, and it is keyed by the turn.
                assert [approval.turn_id for approval in store.pending()] == [TURN]
                assert raised[0].deadline_at == "2026-09-17T12:10:00.000Z"
                # Released through the **client's** verb, which is what
                # `AgentSDKMaster.interrupt()` and `.close()` call — not by
                # reaching into the store the way only a test could.
                assert client.withdraw_turn_approvals(TURN) == 1
        return answers[0]

    with pytest.MonkeyPatch.context() as patcher:
        result = anyio.run(drive, patcher)

    assert [block.text for block in result.content] == ["withdrawn"]
    assert result.is_error is True
    assert store.pending() == ()


# ----- the two boundary properties this module is the exception to ------------


def imported_roots(source: str) -> set[str]:
    """Every module named by an import in one file — aliases and from-imports.

    A rule keyed on one AST spelling passes on the idiomatic spelling of the
    same violation, which is §T7-3's blindness; both node kinds are read here.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def outside_docstrings(source: str) -> str:
    """The file's text with every docstring blanked out.

    Not a scan of string *constants*: `f"mcp__{KEY}__"` is a `JoinedStr` and
    carries no constant holding the prefix, so a constants-only rule passes on
    the idiomatic spelling of the violation — §T7-3's blindness and §T11-4's
    dynamic-import fixture, one layer along. Blanking the prose and reading the
    rest as text sees every spelling, including a split one.
    """
    lines = source.splitlines()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        first = node.body[0].value
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        for index in range(first.lineno - 1, (first.end_lineno or first.lineno)):
            lines[index] = ""
    return "\n".join(lines)


#: The root of the vendor's prefix, matched rather than the whole word so that
#: an interpolated spelling is a violation too.
PREFIX_ROOT = "mcp__"


def prefix_spellers(root: Path) -> list[str]:
    """Product files that put the vendor prefix in code rather than in prose."""
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if PREFIX_ROOT in outside_docstrings(path.read_text(encoding="utf-8"))
    )


def test_the_prefixed_name_is_only_spelled_here() -> None:
    """K13. The vendor's tool prefix is `master/`'s word and nobody else's.

    Two halves, in this order. **The scanner is proved to bite** on an inert
    fixture parsed from text — never a file planted in any tree — and it is
    proved to ignore the same word in a docstring, which is how
    `toolsurface/export.py` can explain the prefix without spelling it.
    Only then is the absence over `src/` asserted.
    """
    planted = 'PREFIX = "mcp__shepherd__"\ndef f() -> str:\n    return PREFIX\n'
    assert PREFIX_ROOT in outside_docstrings(planted)
    interpolated = 'KEY = "shepherd"\nPREFIX = f"mcp__{KEY}__"\n'
    assert PREFIX_ROOT in outside_docstrings(interpolated)
    in_prose = '"""The mcp__shepherd__ prefix lives in master/."""\nX = 1\n'
    assert PREFIX_ROOT not in outside_docstrings(in_prose)

    spellers = prefix_spellers(SRC)
    assert spellers == ["master/sdk_tools.py"]


def test_sdk_tools_reaches_only_the_client_and_the_vendor() -> None:
    """D19, at the one module the rule exists to bound.

    D19 is *"the master reaches the rest of the system only through the
    tool-surface client"*, and this is the only module in the build that may
    also reach the vendor. Both directions are asserted as equalities: a
    fourth `shepherd` import is a failing build, and so is the vendor import
    going missing — which is what proves the scanner can see one.
    """
    source = (SRC / "master" / "sdk_tools.py").read_text(encoding="utf-8")
    roots = imported_roots(source)
    assert {root for root in roots if root.startswith("shepherd")} == {
        "shepherd.core.anomalies",
        "shepherd.core.master",
        "shepherd.toolsurface.client",
    }
    assert {root for root in roots if root.split(".")[0] == "claude_agent_sdk"} == {
        "claude_agent_sdk"
    }
    assert not [root for root in roots if root.split(".")[0] == "mcp"]


def test_each_call_carries_the_turn_it_is_running_inside(
    blocking_call: BlockingCall,
) -> None:
    """The turn id is read per call, not captured when the server is built.

    A runtime can serve more than one turn — `resume()` keeps the conversation
    and T27 mints a fresh `turn_id` for each — so a value captured at build time
    would key the second turn's approvals to the first turn, and
    `withdraw_all()` would sweep a turn that has already ended while leaving the
    live one blocked.
    """
    turns = iter(["01JB0TURN0000000000000001", "01JB0TURN0000000000000002"])
    _, bump = a_bump()
    config = sdk_tools.build_sdk_server(
        TOOLS, CALLER, turn_id=lambda: next(turns), bump=bump
    )

    async def drive() -> None:
        with anyio.fail_after(10.0):
            blocking_call.release.set()
            await call_tool(config, "fleet_summary", {"detail": "a"})
            await call_tool(config, "ask_session", {})

    anyio.run(drive)
    assert blocking_call.correlation_ids == [
        "01JB0TURN0000000000000001",
        "01JB0TURN0000000000000002",
    ]
