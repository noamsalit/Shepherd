"""The vendor-free projection every exporter is built on (D32, D53, DP4).

D32's claim is *"one declaration feeds every exporter"*. This module **is** that
declaration read outward: `ToolDef` → `ExportedTool` for one audience, plus the
bound call that runs `invoke()` and encodes its result as the `content[]` +
`is_error` shape a model reads.

**No vendor name appears below, and none may (DP4, D19).** `cli/` imports
`toolsurface.registry`, so a `claude_agent_sdk` import at L4 would make
`shepherd status` load a package that ships a 208 MB binary; and a seam that
carries a vendor's shape is the D9 mistake committed inside the fix for it. The
~30 lines of vendor translation — `create_sdk_mcp_server`, `@tool`, the
`mcp__shepherd__` prefix — live in `master/sdk_tools.py`, which is the only
module in the build that may import the SDK.
`tests/boundaries/test_l4_import_rules.py::test_no_vendor_sdk_below_l5` makes
that a failing build rather than a convention.

**Why the projection carries three fields and not six.** `ExportedTool` is name,
description and schema: exactly what a runtime needs in order to tell a model a
capability exists. The handler, the audience set and the blast class stay behind
`invoke()` — they are *gate* vocabulary, and a runtime holding them could reason
about its own permissions.

**D53, and the measured fact the next binding's author must read first.**
`create_sdk_mcp_server` passes a schema through unchanged **only** when it has a
string `type` *and* a `properties` key; any other dict it reads as a
`{param: python_type}` map with every key required, which silently produces a
*different tool* (`_build_input_schema`, claude-agent-sdk 0.2.153 —
re-confirmed unchanged by `docs/probes/2026-09-17-m4-sdk/FINDINGS.md` §P1).
It also validates arguments with `jsonschema` before calling the handler. Claude
Code 2.1.270, driving a tier-2 stdio server, forwarded a `tools/call` missing a
required property **unvalidated** (`data-schemas.md` §Tier-2 stdio MCP
`tools/call`). Two bindings that each validate differently would falsify D32's
central claim, which is why validation lives in neither of them:
**`registry.invoke()` validates before the handler, and it is the only
validator.** A future binding that adds its own is adding a second opinion.

**The encoded shapes are captured, not invented** (`data-schemas.md`):

* `tools/list` entries are `{"name", "description", "inputSchema"}` — the camel
  spelling is the MCP wire's, observed in §In-process MCP `initialize` and
  `tools/list` and in §Tier-2 stdio MCP `initialize` and `tools/list`.
* a call result is `{"content": [{"type": "text", "text": …}], "is_error": bool}`
  — the handler-side spelling captured in `handler-calls.jsonl`, which the SDK
  turns into the wire's `isError`.
* a denial's text is §11's own `"you declined this"`, read verbatim by the model
  (§`can_use_tool`, and the `tool_result` it produces).

Nothing here caches: the registry is frozen before the server binds (ADR-7), so
a cache would be a second copy of an immutable thing. Order is by name, so two
exporters over the same audience list the same tools in the same order.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from shepherd.core.master import ExportedTool
from shepherd.toolsurface.registry import GENERIC_ERROR, invoke, registered_tools
from shepherd.toolsurface.types import Audience, CallerContext, ToolResult

#: What a model is told when a human declined the call. §11's `authorize()`
#: returns `Deny("you declined this")` and the capture shows the text reaching
#: the model unchanged, so it is one literal here rather than one per binding.
DENIED_TEXT = "you declined this"

#: The MCP wire spelling of a tool's schema in a `tools/list` entry. Camel, and
#: it is the protocol's, not a vendor's — the same key appears in the in-process
#: and the stdio captures.
SCHEMA_WIRE_KEY = "inputSchema"


def exported_tools(audience: Audience) -> tuple[ExportedTool, ...]:
    """The tools this audience may call, as the three fields a model needs.

    The audience filter is total: a tool that is not projected here is also
    refused by `invoke()`, because both read the same `audiences` field.
    """
    tools = registered_tools()
    return tuple(
        ExportedTool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in (tools[name] for name in sorted(tools))
        if audience in tool.audiences
    )


# `tools_list_payload()` was retired here by the router after T20 (RD-T11-1).
# Its only consumer was the tier-2 stdio binding, cut with Tasks 12-15, and T20
# measured that `create_sdk_mcp_server` builds the `tools/list` entry itself from
# `(name, description, input_schema)` — there is no parameter a pre-built payload
# could fill. Shipping it would have been a translator nothing calls, which is the
# defect the Track C cut invoked by name (M3's T25/F1, and M3's uncalled RFC 6455
# parser before it).
#
# **The wire shape is not lost.** `SCHEMA_WIRE_KEY` below is still the captured
# camel `inputSchema`, and `tests/master/test_sdk_tools.py::
# test_the_schema_and_description_reach_the_wire_unchanged` asserts the vendor's
# own `tools/list` answer against `{"name", "description", "inputSchema"}` written
# out as a literal — a stronger statement than this function made, because it
# reads what the SDK actually emits rather than what we would have handed it.


def _text(result: ToolResult) -> str:
    """The one text block a model reads.

    An *empty* error is a tool the model will retry forever, so a failure with
    no text of its own falls back to the generic literal `invoke()` would have
    used. `ToolResult(ok=False, error=None)` typechecks, so this is a value the
    encoder can genuinely be handed.
    """
    if not result.ok:
        return result.error or GENERIC_ERROR
    data = result.data
    return data if isinstance(data, str) else json.dumps(data, default=str)


def result_payload(result: ToolResult) -> Mapping[str, object]:
    """One `ToolResult` as the captured `content[]` + `is_error` shape."""
    return {"content": [{"type": "text", "text": _text(result)}], "is_error": not result.ok}


def call_exported(
    name: str, args: Mapping[str, object], ctx: CallerContext
) -> Mapping[str, object]:
    """Run one exported tool through `invoke()` and encode what came back.

    Everything a binding needs is here: the audience check, the argument
    validation and the audit path are `invoke()`'s, and an exporter that reached
    a handler any other way would be the private path D32 exists to remove.
    """
    return result_payload(invoke(name, args, ctx))
