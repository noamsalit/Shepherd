"""A call that supplies no runner fact: the degrade cannot be applied from nothing."""

from shepherd.engines.claude_code.spawn import capabilities


def may_spawn() -> bool:
    return capabilities(pane_driver_available=True).can_spawn
