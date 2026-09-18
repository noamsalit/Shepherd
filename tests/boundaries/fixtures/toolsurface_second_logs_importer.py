"""Planted violation, frozen as a fixture: a SECOND `toolsurface` logs importer.

DP3 widens P-M2-10 to D25's own text — **exactly one** module in
`shepherd.toolsurface` may import `shepherd.logs`, and it is found by property
(the module that defines `build_audit_sink`), never by an exemption list. This
file is the mutation that rule must catch: a second L4 module reaching for the
log, in the ordinary from-import spelling.

Inert. Nothing imports this module; it is parsed as an AST and never executed.
The import statement below never runs. Its sibling
`toolsurface_logs_via_import_module.py` carries the call-shaped spelling of the
same violation, because a rule keyed on one exact AST node passes on the other.
"""

from __future__ import annotations

from shepherd.logs.jsonl import RotatingJsonlLog


def tail_the_audit_log(log: RotatingJsonlLog) -> None:
    """The temptation, written out: a second module deciding it is also the tail."""
    log.read()
