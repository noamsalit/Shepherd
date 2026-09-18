"""Planted violation, frozen as a fixture: D19's direct breach (P-M4-8).

`import shepherd.store.db` from a module under `master/` is the plainest form of
the thing D19 forbids by name — *"never a direct import of storage, signals,
queues, or runners"*. The shipped `FORBIDDEN_BELOW_L4` deny-list catches this one
too; the two fixtures beside it are the ones it would miss.

Inert. Nothing imports this module; the reference below sits inside a function
that is never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import shepherd.store.db


def read_the_store() -> object:
    return shepherd.store.db.Store
