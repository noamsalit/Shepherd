"""Planted violation, frozen as a fixture: D26's storage boundary, call-shaped.

`__import__("sqlite3")` needs no import statement at all, so it leaves **no
import node anywhere in the file** for a rule keyed on `ast.Import` to find —
while the driver is loaded and `connect` is one attribute away. The builtin
spelling rather than `importlib` on purpose: it is the form with nothing to walk.

Inert. Nothing imports this module; the call sits inside a function that is never
invoked, and the module body performs no call at all.
"""

from __future__ import annotations


def fold_and_save() -> object:
    return __import__("sqlite3")
