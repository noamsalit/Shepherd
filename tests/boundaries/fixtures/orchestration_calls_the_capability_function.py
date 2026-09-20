"""The negative control: the correct call, which the rule must stay quiet about."""

from shepherd.engines.claude_code.spawn import capabilities


def may_spawn(pane_driver_available: bool) -> bool:
    return capabilities(pane_driver_available=pane_driver_available).can_spawn
