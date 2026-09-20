# self-check fixture for test_layer_direction_is_downward_only:
# L2 publishing into L4 — the exact miss revision 2's ADR-4 shipped (F5).
from shepherd.toolsurface.stream import publish


def emit() -> None:
    publish()
