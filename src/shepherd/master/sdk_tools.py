"""D32's vendor-shaped exporter — the only module that may import the SDK.

**Read this first: everything vendor about the master's tools is here.** DP4's
rule is that `claude_agent_sdk` and `mcp` appear nowhere below L5, in any
spelling — statement, alias, from-import, submodule, or a call that resolves a
name — and `tests/boundaries/test_l4_import_rules.py::test_no_vendor_sdk_below_l5`
makes that a failing build rather than a convention. `master/` is L5, so the
~30 lines below are the whole of the translation: `@tool`, the `mcp__shepherd__`
prefix, and `create_sdk_mcp_server`. Everything upstream of them is
`ExportedTool`, which knows nothing about a vendor, and everything downstream is
`toolsurface.client.call`, which knows nothing about a model.

**D19's allow-list is the client and the SDK, and nothing else.** No store, no
`shepherd.logs`, no runner, nothing at L3 or below. That is why the two things
this module cannot reach on its own — a counter and the id of the turn it is
running inside — **arrive as callables the composition root injects**. An
injection is not an import, so the allow-list is intact and the members are
still reachable (K24); a module under `master/` that imported a store to count
an anomaly would be a site that can never run, which is the always-zero counter
the enum's own section refuses.

**The handler runs the blocking call off the loop (ADR-M4-3, DP5).**
`registry.invoke()` is synchronous and §11's gate can block inside it for 600 s,
while this handler runs on the same event loop that reads the CLI's stdout.
Calling `invoke()` inline wedges that loop: `interrupt()` is never written,
`control_cancel_request` is never read, and D54's withdrawal becomes
unimplementable for ten minutes. So the call goes to a worker thread, with two
settings written out rather than inherited:

* `abandon_on_cancel=True` — anyio's default is `False`, documented as *"ignore
  cancellations in the host task until the operation has completed in the
  worker"*, i.e. a cancellation that could not arrive until the approval had
  already timed out. That is the outcome D54 exists to prevent, reached by the
  mechanism written to prevent it.
* `limiter=MASTER_TOOL_LIMITER` — anyio's default capacity is **40**, a number
  nobody here chose. One turn at a time (RD7/RD12) is the bound this design
  already states, so the limiter states it too.

**There is no withdrawal logic in this file, and that is the design.** P2
measured that no cancellation of any kind reaches a running in-process handler:
the worker thread ran all twenty of its seconds, sixteen of them after the
`interrupt()`. A blocked worker is therefore released by **our own store** —
`AgentSDKMaster.interrupt()` / `.close()` call
`client.withdraw_turn_approvals(turn_id)`, whose compare-and-set wakes it — and
by nothing else. The one obligation that leaves here is the **key**: the store
reads an approval's turn from `CallerContext.correlation_id`, so the handler
passes the **turn id** and nothing else there. A plausible-looking id would
match nothing, every blocked worker would ride its full deadline, and every test
in the tree would stay green (`docs/plans/m4-blockers/t4.md` §T4-2).

**What the SDK does with our schema, measured rather than assumed (D53).**
`create_sdk_mcp_server` passes a schema through unchanged **only** when it has a
string `type` and a `properties` key; anything else it reads as a
`{param: python_type}` map with every key required, which silently produces a
*different tool*. `registry.validate_schema` is what makes that true upstream,
`toolsurface/export.py` asserts it at its own seam, and
`tests/master/test_sdk_tools.py` re-asserts it here against the installed SDK's
own behaviour, including the mangling branch — because an assertion whose
opposite is untested is a coincidence.

**No policy, no decision, no second gate.** The audience filter, the schema
validation, the gate and the audit record are all `invoke()`'s, reached through
one function. This module chooses nothing: it names tools, hands arguments to
the client, and hands the answer back in the shape the SDK expects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial

import anyio
from anyio.to_thread import run_sync
from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import ExportedTool
from shepherd.toolsurface.client import call

#: The server's name in `mcp_servers={…}` and the middle of every prefixed tool
#: name. One spelling, because the two must agree and nothing checks them.
MCP_SERVER_KEY = "shepherd"

#: What the SDK calls our tools once they are mounted, and the only place in
#: `src/` this word appears outside a docstring (K13). Spelled out rather than
#: interpolated from `MCP_SERVER_KEY`: the two must agree, and a scan for the
#: literal is what asserts the prefix has not leaked into another layer.
#: `MasterEvent.tool_name` carries **our** name; the prefix never leaves here.
TOOL_PREFIX = "mcp__shepherd__"

#: One master tool call at a time (RD12). The number matters: each call can be
#: parked in front of a human-shaped gate for ten minutes, and anyio's inherited
#: default would allow forty of them.
MASTER_TOOL_CAPACITY = 1

#: Pinned, module-level, and shared by every server this module builds — the
#: bound is on the master, not on one call. anyio's limiter survives being
#: created outside a running loop and being used by successive loops, which is
#: what a per-turn runtime needs.
MASTER_TOOL_LIMITER = anyio.CapacityLimiter(MASTER_TOOL_CAPACITY)


def prefixed_names(tools: tuple[ExportedTool, ...]) -> tuple[str, ...]:
    """The same tools, spelled the way `allowed_tools` has to spell them.

    Derived from the projection rather than written down beside it: a second
    list of tool names is the drift D32 deleted three hand-maintained lists to
    prevent, and DP7's belt is only meaningful if this set and the mounted set
    are the same set by construction.
    """
    return tuple(f"{TOOL_PREFIX}{exported.name}" for exported in tools)


def _sdk_tool(
    exported: ExportedTool,
    caller_id: str,
    turn_id: Callable[[], str],
    bump: Callable[[AnomalyKind], None],
) -> SdkMcpTool[Mapping[str, object]]:
    """One `ExportedTool` as one vendor tool, closed over its wiring."""

    @tool(exported.name, exported.description, dict(exported.input_schema))
    async def handler(args: Mapping[str, object]) -> dict[str, object]:
        # `turn_id()` is read **per call**, not per server: the runtime is built
        # once and can serve several turns, and a turn id captured at build time
        # would key every later approval to a turn that has already ended.
        blocking = partial(call, exported.name, args, caller_id, turn_id())
        try:
            answer = await run_sync(
                blocking,
                abandon_on_cancel=True,
                limiter=MASTER_TOOL_LIMITER,
            )
        except anyio.get_cancelled_exc_class():
            # The worker keeps running — P2 measured that it always does — and
            # its result now has nowhere to go. That is the condition an
            # operator cannot otherwise see, so it is counted rather than
            # swallowed, through the injected counter (K24).
            bump(AnomalyKind.MASTER_TOOL_RESULT_ORPHANED)
            raise
        return dict(answer)

    return handler


def build_sdk_server(
    tools: tuple[ExportedTool, ...],
    caller_id: str,
    *,
    turn_id: Callable[[], str],
    bump: Callable[[AnomalyKind], None],
) -> McpSdkServerConfig:
    """Mount the master's tools as the in-process MCP server D42's block names.

    `turn_id` and `bump` are keyword-only and required, and neither is in the
    plan's pinned signature — see `docs/plans/m4-blockers/t20.md` §T20-1 and
    §T20-2. A default for either would be the failure this build has already
    paid for twice: a counter nobody increments, and a release key that matches
    nothing while the tests stay green.
    """
    return create_sdk_mcp_server(
        name=MCP_SERVER_KEY,
        tools=[_sdk_tool(exported, caller_id, turn_id, bump) for exported in tools],
    )
