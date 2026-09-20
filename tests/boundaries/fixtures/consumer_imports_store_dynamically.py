"""Planted violation, frozen as a fixture: the consumer boundary, call-shaped.

`consumer_violations` resolved imports through `module_imports`, which walks
`ast.Import`/`ast.ImportFrom` only. `importlib.import_module("shepherd.store.db")`
is an `ast.Call`: the store is loaded and reachable exactly as if it had been
imported by statement, and the rule reported the file clean (§T7-3, the fifteen
bare users). The rule now reads `all_imports`, and this file is what makes that
a proof rather than a claim.

The module name is a module-level string constant, because that is how the
spelling is idiomatically written and because a rule resolving only the literal
argument would be one spelling short again.

Inert. Nothing imports this module; the call sits inside a function that is never
invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import importlib

STORE_MODULE = "shepherd.store.db"


def fleet_page() -> object:
    return importlib.import_module(STORE_MODULE)
