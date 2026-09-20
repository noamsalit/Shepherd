"""Planted violation, frozen as a fixture: DP4's breach in its call-shaped spellings.

`importlib.import_module("claude_agent_sdk")` and `__import__("mcp")` are
**calls**, not import nodes. The 216 MB is paid identically either way, so a
rule that walks import nodes alone is a rule its defeater has never met.

Inert. Nothing imports this module; both calls sit inside functions that are
never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import importlib

VENDOR = "claude_agent_sdk"


def load_the_sdk() -> object:
    return importlib.import_module(VENDOR)


def load_the_protocol() -> object:
    return __import__("mcp")
