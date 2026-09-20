"""The same violation as a string, which no identifier-only scan can see."""

from shepherd.engines.claude_code import spawn as engine


def may_spawn() -> bool:
    record = getattr(engine, "_CLAUDE_CODE_CAPABILITIES")
    return bool(record.can_spawn)
