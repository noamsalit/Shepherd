"""The same violation through a module alias — the spelling a from-import ban misses."""

from shepherd.engines.claude_code import spawn as engine


def may_spawn() -> bool:
    return engine._CLAUDE_CODE_CAPABILITIES.can_spawn
