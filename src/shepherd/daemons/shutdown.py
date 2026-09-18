"""F15's join, with the answer kept — the shutdown logic ADR-1 will not let the
composition root hold.

`thread.join(timeout=…)` returns `None` whether the thread exited or the timeout
expired; the only way to tell them apart is `is_alive()` afterwards. `controld`
discarded it for all three threads and then closed the store, so a thread that
would not exit read exactly like one that had.

Principle 5 decides the rest: a thread that will not exit is an **unknown**, and
an unknown is counted and displayed rather than converted into a fact.

* it is **named** — "1 of 3 did not exit" and *which* is the difference between
  a stuck ingest listener and a stuck HTTP serve loop;
* the store is **not closed** while it is true. `Store.close()` drains the write
  queue and joins its writer with no timeout, so closing under a thread that is
  still enqueueing writes trades a visible unknown for an invisible hang. The
  process is exiting either way and SQLite's durability does not depend on a
  clean `close()`; the outcome says the store was left open, so the skip is a
  reported decision rather than a silent one.

**Clause 20 lands here, and ADR-M4-6 says why here.** Shutdown has to end the
orchestrator's turn and free every worker parked in front of an approval — P2
measured that no cancellation reaches a running in-process tool handler, so our
own compare-and-set is the *only* thing that can release one, and a process that
exited without it would leave a worker waiting ten minutes for a daemon that is
gone. The step is a call into `toolsurface/compose.py`'s holder rather than a
parameter, because `controld.stop()` is three lines the root cannot grow: this
module is **not** a composition root (no 140-line budget, ADR-1's `daemons/` cap
is 150 and this file is well under it), so the logic goes where the lines are.
It runs **before** the join: the turn's worker is a thread, and joining it
before releasing what blocks it is how a shutdown reports a hung thread it
caused itself.

Deliberately **not** an `AnomalyKind` (`core/anomalies.py`): every member there
is counted by `Store.bump_anomaly` into `app_state` and read back through a
**running** daemon's `fleet_summary`. This condition is observed while that store
is the thing in doubt and the daemon is one line from gone, so a member here
would be a count with no writer and no reader. It goes where shutdown can
actually be seen: the process's own exit line.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from shepherd.toolsurface.compose import close_master


@dataclass(frozen=True)
class ShutdownOutcome:
    """What the join found, in the words the exit line prints."""

    joined: tuple[str, ...]
    hung: tuple[str, ...]
    store_closed: bool
    timeout_s: float
    withdrawn: int = 0
    """How many approvals shutdown had to withdraw to free a blocked worker
    (clause 20). Counted and said, never assumed to be zero: a shutdown that
    released somebody is a fact the exit line should carry, and the day it is
    consistently non-zero is the day something is asking for approvals nothing
    answers."""

    def __str__(self) -> str:
        released = "" if not self.withdrawn else f" · {self.withdrawn} approvals withdrawn"
        if not self.hung:
            return f"{len(self.joined)} threads exited · store closed{released}"
        total = len(self.joined) + len(self.hung)
        return (
            f"{len(self.hung)} of {total} threads did not exit within"
            f" {self.timeout_s}s and are unknown, not exited:"
            f" {', '.join(self.hung)} · store left open{released}"
        )


def shut_down(
    threads: Sequence[threading.Thread],
    close_store: Callable[[], None],
    timeout_s: float,
) -> ShutdownOutcome:
    """End the master, free every blocked worker, join, then close the store.

    The order is the contract. The master's turn is ended and its approvals are
    withdrawn **first** (clause 20): a worker parked in front of a card is
    released by our own store or by nothing at all, and joining the threads
    before releasing them would report a hang this function caused. The store is
    closed only if every thread exited, which is the rule this module already
    kept.
    """
    withdrawn = close_master(timeout_s)
    joined: list[str] = []
    hung: list[str] = []
    for thread in threads:
        thread.join(timeout=timeout_s)
        (hung if thread.is_alive() else joined).append(thread.name)
    if not hung:
        close_store()
    return ShutdownOutcome(
        joined=tuple(joined),
        hung=tuple(hung),
        store_closed=not hung,
        timeout_s=timeout_s,
        withdrawn=withdrawn,
    )
