"""Planted violation, frozen as a fixture: the from-import spelling (P-M4-8).

`from shepherd.runner import local` names neither `shepherd.runner.local` nor any
dotted path a substring rule would match, and D19's sentence names runners
outright. It is here because *"the rule covers every spelling"* is a claim that
needs a fixture per spelling, not a comment.

Inert. Nothing imports this module; the reference below sits inside a function
that is never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

from shepherd.runner import local


def run_something() -> object:
    return local
