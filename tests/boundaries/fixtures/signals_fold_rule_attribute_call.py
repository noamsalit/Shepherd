# EVASION fixture (C6): the exclusion was keyed on the callee's bare NAME, so
# any module's `FoldRule` — including one that is not ours — switched it off.
from shepherd.signals import rules

TABLE = (rules.FoldRule(kind=None, emits=(), evidence="§SubagentStop"),)
