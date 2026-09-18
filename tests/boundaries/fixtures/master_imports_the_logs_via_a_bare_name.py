"""Planted violation, frozen as a fixture: two more call-shaped spellings.

Two of them on purpose, and that is the point of this file. A rule asserted
*non-empty* over a fixture with several violations cannot tell **"it caught all
of them"** from **"it caught the easy one"** — T7's own surviving mutant. The
test writes out the whole reported set for this fixture, so dropping either
spelling from the rule is red.

* `from importlib import import_module` then a **bare** `import_module(LOG)` —
  the callee is a plain `ast.Name`, so a rule matching the dotted spelling
  `importlib.import_module` sees nothing.
* `__import__("shepherd.signals.fold")` — the builtin, which needs no import at
  all and therefore leaves no import node anywhere in the file to key on.

Inert. Nothing imports this module; both calls sit inside functions that are
never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

from importlib import import_module

LOG_MODULE = "shepherd.logs.jsonl"


def open_the_log() -> object:
    return import_module(LOG_MODULE)


def load_the_fold() -> object:
    return __import__("shepherd.signals.fold")
