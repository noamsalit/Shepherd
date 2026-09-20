"""Planted violation, frozen as a fixture: the **call-shaped** breach (P-M4-8).

`importlib.import_module("shepherd.store.db")` is an `ast.Call`, not an
`ast.Import`. An AST rule walking `ast.Import`/`ast.ImportFrom` alone **does not
see this file at all**, while the store is loaded and reachable exactly as if it
had been imported by statement. T7 measured that the shared `module_imports`
helper is blind to it and that fifteen shipped rules use it bare
(`docs/plans/2026-09-17-m4-BLOCKERS.md` §T7-3).

The module name is a module-level string constant rather than a literal argument,
because that is how the spelling is idiomatically written — and because a rule
that only resolved the literal would be one spelling short again.

Inert. Nothing imports this module; the call below sits inside a function that is
never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import importlib

STORE_MODULE = "shepherd.store.db"


def open_the_store() -> object:
    return importlib.import_module(STORE_MODULE)
