"""Planted violation, frozen as a fixture: the same reach, spelled as a call.

`importlib.import_module("shepherd.toolsurface.registry")` is **not an import
node** — it is a `Call`, and a rule keyed on `ast.Import`/`ast.ImportFrom` sees
nothing here at all. M3 lost three tmux rules to exactly one line of indirection,
so the purity scan resolves both call-shaped spellings and this file is what
proves it.

**Inert.** Nothing imports this module; it is parsed as an AST and never
executed.
"""

from __future__ import annotations

import importlib


def consult_the_registry() -> object:
    registry = importlib.import_module("shepherd.toolsurface.registry")
    return registry.registered_tools()
