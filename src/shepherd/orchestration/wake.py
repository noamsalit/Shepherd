"""T9 — D31's wake set: the query, the summary the master is handed, and the
stamp that makes draining idempotent.

The wake set is **a query, not a table** (D31). It is master-owned sessions that
stopped `unfinished` or `error` since the master's last turn, and `store/` owns
that sentence: `wake_candidates(since)` is the verb, and nothing here re-states
its `WHERE` clause. What this module owns is the three things the store cannot:
where `since` comes from, what the master is handed, and when the stamp moves.

**One projection, two callers.** Level 2 drains at the start of your next turn
and level 3 drains when the stop happens; they differ in *when* `drain()` is
called and never in what it returns. `peek()` is the same projection without the
stamp, for a caller that wants to look without consuming.

**The master re-reads a classification it can already see** (§12). `why`,
`next_actions[]` and the outcome were written by M2's stop lane when the session
stopped; this module copies them onto a `WakeItem` and classifies nothing. A
projection that re-reasoned about a stop would be a second classifier with a
second opinion, and the first one is the one the fleet page already shows.

**The clock is read before the rows and the stamp written after them, and that
order is the whole design of `drain()`.** Between reading the candidates and
writing the stamp there is a window in which a session can stop. Stamping the
instant the read *finished* would place that stop before the stamp, and it would
never wake anything again — a lost stop. Stamping the instant the read *began*
places it after, so the worst case is that a row is drained twice, which is a
repeated line in a summary rather than work nobody is ever told about. Losing a
stop is the failure this component exists to prevent; repeating one is not.

**Level 3 wakes the master** (D69, ADR-QR-5). `LevelThreeWaker.tick()` rides
the existing 2 s sweep — no thread is added — and at level 3, with an item whose
`retry_of` lineage is below `MAX_MASTER_ATTEMPTS` (the plan's RD-3), it calls
the injected `open_wake`, which is `TurnDriver.wake_turn`. A turn holding the
slot makes that return `None` and drains nothing, so the next tick offers the
wake again. A stop in a lineage already at the cap opens nothing, is counted
once per session as `wake_retry_cap_reached`, and waits for the next user turn.

`needs_you` is absent for the same reason D31 gives: that is the human's rail,
and routing it to an agent would hide the one thing the platform exists to show
you. The exclusion is the store verb's, and `test_needs_you_never_wakes_the_
master` asserts it against a `needs_you` row that is the newest stop in the
fleet — "excluded by construction" is a claim that needs a row to prove it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.stops import PALETTE, Bucket, NextAction
from shepherd.orchestration.admission import MAX_MASTER_ATTEMPTS
from shepherd.store.db import Store
from shepherd.store.models import Session

__all__ = [
    "MASTER_LAST_TURN_KEY",
    "WAKE_LEVEL",
    "LevelThreeWaker",
    "WakeItem",
    "WakeSummary",
    "drain",
    "peek",
    "render_wake_text",
]

#: §7's `app_state` key, D31's stamp. `store/` has no constant for it — it is a
#: key in a key/value table, and the component that owns the meaning owns the
#: spelling.
MASTER_LAST_TURN_KEY = "master_last_turn_at"

#: §12's opening line, verbatim.
WAKE_HEADER = "while you were away —"

#: D8's level 3, as the number the injected `level()` answers. L3 may not import
#: `toolsurface.policy.AutonomyLevel` (§5.0), so the value is held here and
#: `test_the_waker_reads_level_3_as_the_policy_spells_it` pins the two together.
WAKE_LEVEL = 3

#: Every value `Bucket` holds, so the projection maps an outcome to a bucket
#: without re-stating *which* outcomes wake the master. That clause belongs to
#: `wake_candidates`; a copy of it here would be a second filter to keep in
#: agreement with the first.
_BUCKET_VALUES = {bucket.value: bucket for bucket in Bucket}


@dataclass(frozen=True)
class WakeItem:
    """One row of §12's summary: a bucket glyph, the title, the one-line `why`,
    and the first `next_actions[]` item as a button. All four are the **row's
    own** values, read back rather than recomputed."""

    session_id: str
    title: str | None
    bucket: Bucket
    why: str | None
    first_action: NextAction | None


@dataclass(frozen=True)
class WakeSummary:
    """What a drain consumed, and the instant the stamp now holds.

    `drained_at` is on the summary because a caller that logs a drain should log
    the instant the *set* was cut at, not the instant it got around to writing
    the log line."""

    items: tuple[WakeItem, ...]
    drained_at: str


def _since(store: Store) -> str | None:
    """The master's last turn, or `None` for a master that has never had one.

    `app_state` hands back whatever JSON the key holds, so the stamp is narrowed
    here. A value that is not a stamp is treated as *no stamp*: the set widens
    to every candidate, which repeats rows. The other reading — treat an
    unreadable stamp as "now" — silently drops every stop older than it.
    """
    value = store.get_app_state(MASTER_LAST_TURN_KEY)
    return value if isinstance(value, str) else None


def _item(row: Session) -> WakeItem:
    """§12's shape from the row M2 already wrote. No classifier is called."""
    return WakeItem(
        session_id=row.id,
        title=row.title,
        bucket=_BUCKET_VALUES.get(row.outcome or "", Bucket.UNCLASSIFIED),
        why=row.why,
        first_action=row.next_actions[0] if row.next_actions else None,
    )


def peek(store: Store) -> tuple[WakeItem, ...]:
    """What a drain would hand over right now, consuming nothing."""
    return tuple(_item(row) for row in store.wake_candidates(_since(store)))


def drain(store: Store, now: Callable[[], str]) -> WakeSummary:
    """The wake set, consumed: the same rows never arrive twice.

    The stamp moves **whether or not anything was in the set** (E-M4-18). A
    stamp conditional on a non-empty drain leaves the previous turn's instant
    standing, and a stop that happened in between is then attributed to a turn
    that had already ended.
    """
    moment = now()
    items = peek(store)
    store.set_app_state(MASTER_LAST_TURN_KEY, moment)
    return WakeSummary(items=items, drained_at=moment)


def _line(item: WakeItem) -> str:
    """One summary row: glyph, title, `why`, and the action as a button."""
    parts = [PALETTE[item.bucket].glyph, item.title or item.session_id]
    if item.why:
        parts.append(item.why)
    if item.first_action is not None:
        parts.append(f"[{item.first_action.text}]")
    return "      " + "   ".join(parts)


def render_wake_text(summary: WakeSummary) -> str:
    """§12's "while you were away —", or the empty string.

    An empty summary renders nothing at all rather than an empty header: the
    summary opens the first turn where *anything* stopped, and a header over no
    rows is a line the master would have to explain away.
    """
    if not summary.items:
        return ""
    count = len(summary.items)
    plural = "" if count == 1 else "s"
    lines = [
        WAKE_HEADER,
        f"    {count} session{plural} stopped needing a decision",
        *(_line(item) for item in summary.items),
    ]
    return "\n".join(lines)


class LevelThreeWaker:
    """D69's opener, ticked by the 2 s sweep. `tick()` is `True` when it opened
    a turn.

    Everything is injected: the level (read per tick, so a toggle takes effect
    on the next sweep), the opener (`TurnDriver.wake_turn`, whose `None` means
    "not now") and the counter. `declined` remembers the sessions already
    counted at the cap, so the anomaly is bumped once per session rather than
    once per 2 s pass.
    """

    def __init__(
        self,
        store: Store,
        *,
        level: Callable[[], int],
        open_wake: Callable[[], object],
        bump: Callable[[str], None],
    ) -> None:
        self._store = store
        self._level = level
        self._open_wake = open_wake
        self._bump = bump
        self.declined: set[str] = set()

    def tick(self) -> bool:
        """One sweep's look: open a wake turn if level 3 has something to act on."""
        if self._level() != WAKE_LEVEL:
            return False
        if not self._eligible(peek(self._store)):
            return False
        return self._open_wake() is not None

    def _eligible(self, items: tuple[WakeItem, ...]) -> tuple[WakeItem, ...]:
        """RD-3: the items whose lineage the master could still retry. A capped
        item is counted once and left in the set for the next user turn."""
        eligible: list[WakeItem] = []
        for item in items:
            if self._store.retry_chain_depth(item.session_id) < MAX_MASTER_ATTEMPTS:
                eligible.append(item)
            elif item.session_id not in self.declined:
                self.declined.add(item.session_id)
                self._bump(AnomalyKind.WAKE_RETRY_CAP_REACHED.value)
        return tuple(eligible)
