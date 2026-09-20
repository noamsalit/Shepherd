"""Planted violation, frozen as a fixture: ADR-1's root rule, call-shaped.

`from importlib import import_module` then a **bare** `import_module(...)`: the
callee is a plain `ast.Name`, so even a rule matching the dotted spelling
`importlib.import_module` sees nothing. `all_imports` resolves the callee through
its alias origin, which is what makes this form the same rule as the dotted one.

Inert. Nothing imports this module; the call sits inside a function that is never
invoked, and the module body performs no call at all.
"""

from __future__ import annotations

from importlib import import_module

CONTROLD_MODULE = "shepherd.daemons.controld"


def status() -> object:
    return import_module(CONTROLD_MODULE)
