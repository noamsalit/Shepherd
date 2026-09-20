"""Inert fixture: the half of the drift tree that has NOT moved.

Nothing imports this module. It is read as bytes by `digest_set` and never
executed. It exists so the negative control can prove the comparison reports
**exactly one** path rather than "everything differs", which a broken digest
function would also produce.
"""

STEADY = "this file matches the digest recorded for it"
