"""Planted violation, frozen as a fixture: the vendor SDK at L4 (DP4).

`cli/` imports `toolsurface.registry`, so an SDK import anywhere under
`shepherd.toolsurface` makes `shepherd status` pay to load a package that ships
a 216,677,784-byte Claude Code binary — and it puts a vendor's vocabulary at L4,
which K13 forbids. `master/` is the SDK's only declared home (D19).

**Three spellings, deliberately.** The alias form is the one that matters, and
the submodule form (`from mcp.server.stdio import …`) never yields the bare root
name at all — a rule comparing the whole dotted name against
`VENDOR_SDK_ROOTS` walks straight past it.

Inert. Nothing imports this module; it is parsed as an AST and never executed.
"""

from __future__ import annotations

import claude_agent_sdk as sdk
from claude_agent_sdk import tool
from mcp.server.stdio import stdio_server


def export(name: str) -> object:
    return sdk.create_sdk_mcp_server(name=name, tools=[tool, stdio_server])
