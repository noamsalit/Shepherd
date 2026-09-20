"""Planted violation, frozen as a fixture: the same DP3 breach, call-shaped.

`importlib.import_module("shepherd.logs.jsonl")` is **not an `ast.Import` node**
— it is an `ast.Call`. A boundary rule that walks import nodes only reports this
file as clean, which is how a rule keyed on one exact spelling passes on the
idiomatic spelling of the very violation it was written for. M3 shipped that
defect three times.

Inert. Nothing imports this module; the call below sits inside a function that
is never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import importlib

LOG_MODULE = "shepherd.logs.jsonl"


def open_the_log() -> object:
    return importlib.import_module(LOG_MODULE)
