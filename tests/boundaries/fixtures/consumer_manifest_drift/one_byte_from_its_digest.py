"""Inert fixture: the half of the drift tree that IS one byte from its digest.

Nothing imports this module. The manifest beside this tree records the sha256 of
this file's bytes **with a single byte altered**, so `digest_drift` must report
this path and only this path. That is P-M4-5: without it, "the manifest matches"
and "the comparison does nothing" are indistinguishable.
"""

DRIFTED = "b"
