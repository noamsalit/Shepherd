"""D42's option block and the master runtime behind the sixth seam (T21).

**What this module is.** `AgentSDKMaster` is the v1 `MasterRuntime`: it holds the
vendor's client, projects what that client streams into `MasterEvent`s (ADR-M4-5),
and carries D42's two belts — the option block that removes the engine's own
capabilities, and the permission callback that denies whatever the first belt
missed (DP7).

**Three things arrive as injected callables rather than imports (K24, D19).** A
module under `master/` may not reach a store, so the anomaly counter is a `bump`
the composition root closes over; the id of the turn we are running inside is the
turn driver's and not ours, so it is a supplier read per call; and the withdrawal
that frees a blocked tool worker is the tool-surface client's function, handed in
by the root that also binds it. **None of the three is defaulted.** A default for
any of them is the failure this milestone has already paid for twice — a counter
nobody increments, and a release key that matches nothing while every test stays
green (`docs/plans/m4-blockers/t4.md` §T4-2, `t20.md` §T20-2).

**One client per turn, and that is forced rather than chosen.** `send()` is an
`AsyncIterator` (§6:472, DP12) and the turn driver owns one event loop per turn
on a worker thread it tears down with the turn. A vendor client is bound to the
loop it connected on, so a client held across turns would be a client held across
loops. It is therefore built inside `send()` and disconnected in `send()`'s
`finally`, which is also why `resume()` cannot mutate anything in place: there is
no live connection between turns to mutate (DP9 — the SDK has no `resume()`
method and each resume is a new subprocess).

**`interrupt()` and `close()` withdraw first, then touch the engine** (ADR-M4-3).
Probe P2 measured that no cancellation of any kind reaches a running in-process
tool handler — not deferred, never delivered, and the worker outlives both turn
and client — so our own store's compare-and-set is the *only* thing that can free
a worker blocked in front of a human-shaped gate before its 600 s deadline.
Reversed, the two would leave that worker blocked for ten minutes while every
test stayed green.

**The turn ends when we say it ended.** After an interrupt this runtime stops
projecting and emits its own terminal event rather than relaying whatever the
engine had already buffered. §6's verb is *"end the turn in flight"*, and a turn
that went on emitting tool calls after the user killed it has not ended — the
vendor's own result for that turn arrives later and is nobody's answer by then
(P2: `error_during_execution` / `aborted_tools`).
"""

from __future__ import annotations

import asyncio
from asyncio import run_coroutine_threadsafe
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import Future
from contextlib import suppress
from typing import Literal

from claude_agent_sdk import (
    CanUseTool,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLINotFoundError,
    McpSdkServerConfig,
    PermissionResult,
    PermissionResultDeny,
    SettingSource,
    SystemMessage,
    ToolPermissionContext,
    Transport,
)

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import (
    CURATED_MASTER_FACTS,
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterRefusal,
)
from shepherd.master.projection import (
    INTERRUPTED_OUTCOME,
    OUTCOME_KEY,
    TERMINAL_KINDS,
    master_event,
    project_events,
    session_payload,
)
from shepherd.master.sdk_tools import MCP_SERVER_KEY, build_sdk_server, prefixed_names

#: D10: the master cannot dispatch subagents. Written as a tuple here and handed
#: to the option block as a list, because the vendor's field is a list and a
#: module-level mutable would be one shared list every runtime could edit.
DISALLOWED_TOOLS: tuple[str, ...] = ("Agent", "Task")

#: D10 / P4. `[]` is not `None`: `None` means *"read this host's settings"*, and
#: P4 measured the difference — the user's cc10x plugin is loaded under `None`
#: and absent under `[]`, same binary, same everything else.
SETTING_SOURCES: tuple[SettingSource, ...] = ()


def build_options(
    tools: tuple[ExportedTool, ...],
    system_prompt: str,
    resume_id: str | None,
    model: str,
    cli_path: str | None,
    belt: CanUseTool | None,
    server: McpSdkServerConfig,
    settings: str | None = None,
) -> ClaudeAgentOptions:
    """D42's block, with each line's decision named beside it.

    `server` is a seventh parameter the plan's pinned signature does not have.
    `build_sdk_server` needs the caller id, the turn-id supplier and the counter
    (T20 §T20-1, §T20-2), and an option builder holding those three would be an
    option builder that could raise an anomaly. It is built by the caller and
    mounted here. Recorded in `docs/plans/m4-blockers/t21.md`.

    **`model` and `cli_path` are parameters, never constants.** §17 names
    hard-coding the model as the mistake by name; `cli_path=None` means the
    bundled binary, which is the default the composition root passes and E-M4-9
    allows a config to override.

    **`settings` is `None` in D42's block and is not decoration.** `None` means
    the flag is absent, which is what the plan writes; a path is the belt a run
    against a real engine wears so it can never read the operator's own
    `~/.claude/settings.json`. `setting_sources=[]` already excludes user scope
    (P4), and the probe harness passes both anyway — two levers, kept separate,
    exactly as P4 recommends for `tools` and `strict_mcp_config`.
    """
    return ClaudeAgentOptions(
        model=model,  # §17 — from config, never a constant
        system_prompt=system_prompt,  # T19 — a string replaces the engine's own
        tools=[],  # D42 — the ONLY option that removes built-ins
        strict_mcp_config=True,  # D42 — drops the account's connectors
        setting_sources=list(SETTING_SOURCES),  # D10; DP10 records what it keeps
        disallowed_tools=list(DISALLOWED_TOOLS),  # D10 — no subagents
        allowed_tools=list(prefixed_names(tools)),  # auto-approve ours; the belt sees the rest
        mcp_servers={MCP_SERVER_KEY: server},  # T20
        can_use_tool=belt,  # D42's second belt, DP7's reading
        resume=resume_id,  # D10 — the conversation survives a restart
        cwd=None,  # D10; and it keys the engine's transcript directory
        cli_path=cli_path,  # E-M4-9, RD9 — None is the bundled binary
        settings=settings,  # `None` is D42's block; a path is the isolation belt
    )


#: What the belt says when it denies. DP7: it never allows and it never decides,
#: so there is one sentence and the tool's own prefixed name is appended to it —
#: a denial that does not say what was denied is a denial an operator cannot act
#: on, and a test asserting the whole message would be asserting a spelling.
BELT_DENIAL = "this master may only call the tools Shepherd mounted for it"

#: How long a turn's teardown waits for an interrupt it already sent. Bounded,
#: because the thing on the other end is a subprocess we did not write: a
#: teardown that waited forever would hold the turn's thread open on exactly the
#: path a user reaches by giving up on a turn.
SDK_INTERRUPT_TIMEOUT_S = 10.0


def _curated(name: str) -> bool | int | str:
    return CURATED_MASTER_FACTS[name].value


def _curated_flag(name: str) -> bool:
    value = _curated(name)
    if not isinstance(value, bool):
        raise MasterRefusal(f"the curated fact {name} is not a flag: {value!r}")
    return value


class AgentSDKMaster:
    """The v1 `MasterRuntime`. Six members, and one client per turn.

    **The three things it cannot reach on its own are required and undefaulted**
    (K24, D19, §T20-2): the counter, the live turn's id and the withdrawal. A
    default for any of them is a counter nobody increments or a release key that
    matches nothing, with every test still green.

    The four that *are* defaulted each default to the plan's own option block:
    the bundled binary, no conversation to resume, no settings file, and a real
    `claude`. `open_transport=None` is the production answer — a check that wants
    the vendor's client without the vendor's subprocess substitutes the **pipe**,
    which is the one thing in the path we did not write.
    """

    def __init__(
        self,
        *,
        caller_id: str,
        turn_id: Callable[[], str],
        bump: Callable[[AnomalyKind], None],
        withdraw_turn_approvals: Callable[[str], int],
        model: str,
        cli_path: str | None = None,
        resume_id: str | None = None,
        settings: str | None = None,
        open_transport: Callable[[ClaudeAgentOptions], Transport] | None = None,
    ) -> None:
        self._caller_id = caller_id
        self._turn_id = turn_id
        self._bump = bump
        self._withdraw_turn_approvals = withdraw_turn_approvals
        self._model = model
        self._cli_path = cli_path
        self._settings = settings
        self._resume_id = resume_id
        self._conversation_id = resume_id
        self._open_transport = open_transport
        self._tools: tuple[ExportedTool, ...] = ()
        self._system_prompt = ""
        self._client: ClaudeSDKClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._interrupting: Future[None] | None = None
        self._system_init: Mapping[str, object] | None = None
        self._closed = False
        self._interrupted = False

    # ----- the seam's six members ------------------------------------------

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        """Mount the tool set and the frozen prompt (DP12).

        Held rather than applied: the option block is built per turn, because the
        client is, and a `configure()` that reached into a live connection would
        be the in-place mutation `resume()`'s own check exists to forbid.
        """
        self._tools = tools
        self._system_prompt = system_prompt

    async def send(self, text: str) -> AsyncIterator[MasterEvent]:
        """One turn: everything the engine streams, until exactly one ending.

        **Exactly one terminal event, and it is last.** The engine's own result
        ends the turn when the turn ran to completion; when it did not — an
        interrupt, a `close()`, or a stream that stopped without a result — this
        runtime writes the ending itself. A consumer that never sees a turn end
        is a chat page that hangs, and §6's verb is *"end the turn in flight"*.
        """
        if self._closed:
            raise MasterRefusal(
                "this master is closed; build another runtime for the next turn"
            )
        self._loop = asyncio.get_running_loop()
        self._interrupted = False
        tool_names: dict[str, str] = {}
        client = await self._open()
        self._client = client
        ended = False
        try:
            await client.query(text)
            async for message in client.receive_response():
                self._note_capabilities(message)
                for event in project_events(
                    message, bump=self._bump, tool_names=tool_names
                ):
                    yield event
                    ended = ended or event.kind in TERMINAL_KINDS
                if self._interrupted or self._closed:
                    break
            if not ended:
                yield master_event(
                    "error",
                    text=None,
                    payload={
                        **session_payload(self._conversation_id),
                        OUTCOME_KEY: INTERRUPTED_OUTCOME,
                    },
                )
        finally:
            await self._release(client)

    def resume(self, master_session_id: str) -> None:
        """Continue a conversation — by **rebuilding**, because that is all the
        engine offers (DP9).

        There is no `resume()` on the vendor's client and no way to re-point a
        connected one: a resume is a new subprocess reading the transcript the id
        names. So this records the id and the next turn opens on it. Nothing is
        mutated in place because between turns there is nothing live to mutate.
        """
        self._resume_id = master_session_id
        self._conversation_id = master_session_id

    def interrupt(self) -> None:
        """End the turn in flight — **withdraw first, then touch the engine**.

        ADR-M4-3, and P2 is why the order is not a preference: no cancellation of
        any kind reaches a running in-process tool handler, so a worker parked in
        front of an approval is freed by our own store's compare-and-set or by
        nothing at all until its 600 s deadline. Reversed, the engine would be
        told to stop while the thing actually blocking the turn kept waiting.
        """
        self._withdraw_turn_approvals(self._turn_id())
        self._interrupted = True
        client, loop = self._client, self._loop
        if client is None or loop is None or loop.is_closed():
            return
        # Scheduled, never awaited here: `interrupt()` is called from the turn
        # driver's thread *and* from inside the consuming loop itself, and a
        # blocking wait from the second would deadlock on the loop it is waiting
        # for. The turn's teardown is what reaps it, bounded.
        #
        # **Bound as a module global on purpose.** This call *is* the moment the
        # runtime touches the engine, and it is the only such moment that
        # happens while `interrupt()` is still running — the coroutine it
        # schedules does not start until this method has returned, so an
        # ordering check watching the *wire* cannot tell the two orders apart.
        # `test_interrupt_withdraws_before_it_touches_the_sdk` substitutes this
        # name (the technique `sdk_tools.py`'s own tests use for `call`), and the
        # mutation that swaps the two lines is red because of it.
        self._interrupting = run_coroutine_threadsafe(client.interrupt(), loop)

    def capabilities(self) -> MasterCapabilities:
        """§6's record, answered from `CURATED_MASTER_FACTS` (DP8).

        Two of the five cannot be known before the first turn and one was never
        observed at all, so the table names where each came from and this reads
        it. A runtime that invented them on the first call would be answering
        with a guess a later turn could contradict.
        """
        billing = _curated("billing_mode")
        if billing == "seat":
            mode: Literal["seat", "api"] = "seat"
        elif billing == "api":
            mode = "api"
        else:
            raise MasterRefusal(f"the curated billing mode is not one of ours: {billing!r}")
        return MasterCapabilities(
            billing_mode=mode,
            owns_history=_curated_flag("owns_history"),
            owns_compaction=_curated_flag("owns_compaction"),
            supports_parallel_tool_calls=_curated_flag("supports_parallel_tool_calls"),
            context_window=int(_curated("context_window")),
        )

    def close(self) -> None:
        """Release the runtime (DP9). Idempotent, and it withdraws first.

        `daemons/shutdown.py` calls this unconditionally, so a second call that
        raised would turn a clean shutdown into a stack trace. The withdrawal
        runs on every call rather than only the first: it is a compare-and-set
        over approvals this turn raised, so a second one frees nothing and costs
        nothing, while skipping it on a re-entrant shutdown would leave a worker
        blocked for the same ten minutes `interrupt()` exists to prevent.
        """
        self._withdraw_turn_approvals(self._turn_id())
        self._closed = True
        self._interrupted = True

    # ----- what the master reports about itself -----------------------------

    def conversation_id(self) -> str | None:
        """The conversation this runtime is continuing, or `None` for a new one.

        **Not the engine's session id, and the difference is measured.** The
        2026-09-14 resume capture shows a resumed conversation coming back under
        a *new* `session_id` — so the engine's id answers *"which subprocess"*,
        while this answers *"which conversation"*, which is the one §12's chat
        and D10's continuity are about. The engine's id rides on the events, under
        `MASTER_SESSION_KEY`, where the turn driver persists it.
        """
        return self._conversation_id

    def system_init(self) -> Mapping[str, object] | None:
        """What the engine reported about itself on the last turn it opened.

        §18 says of the isolation lock: *"verify in M4 and assert it in a test —
        do not trust it"*, and the option block is not the thing to assert (a
        master whose options looked right ran `echo hi`). This is the channel T22
        reads `tools`, `mcp_servers` and `plugins` off.
        """
        return self._system_init

    # ----- DP7's belt --------------------------------------------------------

    async def _belt(
        self,
        tool_name: str,
        tool_input: Mapping[str, object],
        context: ToolPermissionContext,
    ) -> PermissionResult:
        """D42's second belt: **it denies, it counts, it never decides**.

        P3 measured what reaches it — a tool that is mounted but absent from
        `allowed_tools`, which for this master is a tool we did not mount at all,
        since the allow-list *is* the mounted set by construction. A second
        decider would be a second policy: the gate behind `invoke()` is the only
        one, and anything arriving here has already gone around it.

        The count goes through the injected `bump` (K24): `master/` may not reach
        a store, and a member named here but handed to nothing would be a counter
        that can never move.
        """
        self._bump(AnomalyKind.MASTER_TOOL_UNEXPECTED)
        return PermissionResultDeny(message=f"{BELT_DENIAL} ({tool_name})")

    # ----- one client per turn ----------------------------------------------

    async def _open(self) -> ClaudeSDKClient:
        """Connect, and answer a lost transcript with a new conversation (E-M4-8).

        A resume whose transcript is gone is not an error the user can do
        anything about, so it starts a new conversation and **says so** through
        the counter. It is tried exactly once: a second failure is the engine
        being unreachable, which is a different fact and is raised.
        """
        resume_id = self._resume_id
        try:
            return await self._connect(resume_id)
        except CLINotFoundError:
            raise
        except ClaudeSDKError:
            if resume_id is None:
                raise
            self._bump(AnomalyKind.MASTER_RESUME_LOST)
            self._resume_id = None
            self._conversation_id = None
            return await self._connect(None)

    async def _connect(self, resume_id: str | None) -> ClaudeSDKClient:
        options = build_options(
            tools=self._tools,
            system_prompt=self._system_prompt,
            resume_id=resume_id,
            model=self._model,
            cli_path=self._cli_path,
            belt=self._belt,
            server=build_sdk_server(
                self._tools,
                self._caller_id,
                turn_id=self._turn_id,
                bump=self._bump,
            ),
            settings=self._settings,
        )
        transport = self._open_transport(options) if self._open_transport else None
        client = ClaudeSDKClient(options=options, transport=transport)
        await client.connect()
        return client

    async def _release(self, client: ClaudeSDKClient) -> None:
        """End the turn's connection, whatever the turn did.

        The interrupt this turn may have sent is reaped **before** the
        disconnect and on a bound wait: a pending control request cancelled by
        the teardown is a task nobody ever looks at, and an unbounded wait here
        would hang the turn's own thread on the path a user takes to get out of
        a turn.
        """
        pending, self._interrupting = self._interrupting, None
        if pending is not None:
            with suppress(Exception, asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.wrap_future(pending), SDK_INTERRUPT_TIMEOUT_S
                )
        with suppress(Exception):
            await client.disconnect()
        self._client = None
        self._loop = None

    def _note_capabilities(self, message: object) -> None:
        if isinstance(message, SystemMessage) and message.subtype == "init":
            self._system_init = dict(message.data)
