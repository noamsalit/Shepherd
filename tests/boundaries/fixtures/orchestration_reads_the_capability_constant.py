"""A planted violation: the plan's own `Consumes` line, followed literally.

`CLAUDE_CODE_CAPABILITIES` carries `can_spawn=True` unconditionally, so this
module decides a host with no pane driver *can* spawn and D-5 never fires.
"""

from shepherd.engines.claude_code.spawn import CLAUDE_CODE_CAPABILITIES


def may_spawn() -> bool:
    return CLAUDE_CODE_CAPABILITIES.can_spawn
