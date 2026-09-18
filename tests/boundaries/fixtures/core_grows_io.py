"""Planted violation, frozen as a fixture: the day `core/` grows a capability.

RD-T20-D19 widened the master's import allow-list to `shepherd.core.*` **because**
`core/` is measurably capability-free — *"no I/O, no store, no process, no
socket"*. That is the widening's **condition**, not a coincidence, so
`core_capability_violations` exists to go red the day it stops holding.

Nothing in the shipped tree spells the builtin `open`, so without this file the
builtin branch of that rule would be code no test ever exercised — a rule half of
which is a comment. It carries one of each class:

* a capability **module** (`socket`);
* an `os.*` **identifier** that is not the entropy `core/ids.py` is allowed
  (`os.fork`);
* a capability **builtin**, which needs no import at all and so leaves no import
  node anywhere in the file to key on (`open`).

Inert. Nothing imports this module; every call sits inside a function that is
never invoked, and the module body performs no call at all. `os.fork` in
particular is never executed — CLAUDE.md's rule is that anything whose effect
leaves the process is proved by predicate and by fixture, never by running it.
"""

from __future__ import annotations

import os
import socket


def read_a_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def spawn_a_child() -> object:
    return os.fork()


def open_a_socket() -> object:
    return socket.socket()
