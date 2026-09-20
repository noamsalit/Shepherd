"""Planted violation, frozen as a fixture: §5.0's direction rule, call-shaped.

L2 publishing into L4 is the miss revision 2's ADR-4 shipped (F5). Spelled as a
call it was invisible a second time: `direction_violations` read `module_imports`,
which does not walk `ast.Call`. The import is upward whichever node class carries
it, and the rule now reads `all_imports`.

Inert. Nothing imports this module; the call sits inside a function that is never
invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import importlib

STREAM_MODULE = "shepherd.toolsurface.stream"


def emit() -> object:
    return importlib.import_module(STREAM_MODULE)
