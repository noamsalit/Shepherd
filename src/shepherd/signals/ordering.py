"""Fleet ordering and the liveness backstop (§16, §8, T11).

Two things live here, and both are **read-time** derivations: they need no event
to become true, so the fold never writes them.

* **The liveness backstop.** §8 defines `running` as "any tool/message signal
  within `LIVENESS_WINDOW_S`". A session whose last signal is older than that is
  therefore not running, whatever the column says — and no event will ever
  arrive to say so, because silence emits nothing.
* **The order.** §16: `needs_you` first, then `running`, then `starting`, then
  `stopped`. A session blocked on a human is not finished; it sorts to the top
  even if it has been silent for an hour, so staleness never demotes it.
"""

from __future__ import annotations

from shepherd.core.clock import parse_stamp
from shepherd.core.states import FLEET_STATE_ORDER, SessionState
from shepherd.core.stops import BUCKET_ORDER, Bucket
from shepherd.store.models import FleetRow

__all__ = [
    "LIVENESS_WINDOW_S",
    "age_seconds",
    "bucket_of",
    "effective_state",
    "fleet_bucket_sort_key",
    "fleet_sort_key",
    "is_live",
    "parse_stamp",
]

#: The `outcome` column holds a `Bucket` *value*, and a value this build did
#: not write — an older spelling, a hand-edited row — is an unknown, never an
#: exception. Membership is asked before the conversion for exactly that.
_BUCKET_VALUES: frozenset[str] = frozenset(bucket.value for bucket in Bucket)

#: §8. Ninety seconds of silence and a session is no longer *running*.
LIVENESS_WINDOW_S: int = 90


def age_seconds(stamp: str | None, now: str) -> float | None:
    """Seconds between `stamp` and `now`, or `None` when either is unreadable.

    `None` here has two causes and they are not the same thing: *never stamped*
    (a session with no event yet) and *unreadable* (a stamp in a spelling
    `core.clock` does not know). Both are unknown ages, and the caller decides.
    """
    if stamp is None:
        return None
    then, current = parse_stamp(stamp), parse_stamp(now)
    if then is None or current is None:
        return None
    return (current - then).total_seconds()


def is_live(last_event_at: str | None, now: str) -> bool:
    """Has this session produced a signal inside the window? (§8)

    An unknown age answers `False` — but that answer is only safe because every
    writer in the system stamps through `core.clock`, so "unreadable" means a
    row this build did not write. It used to mean *every* row: `ordering` owned
    a format no writer used, the parse failed for all of them, and this function
    was `False` always, which emptied §16's `running` bucket in silence. The
    contract that keeps it honest is
    `tests/signals/test_liveness_stamp_contract.py`, which calls each real
    writer rather than spelling a stamp itself.
    """
    age = age_seconds(last_event_at, now)
    return age is not None and age < LIVENESS_WINDOW_S


def effective_state(row: FleetRow, now: str) -> SessionState:
    """The state a reader should believe, with the backstop applied.

    Only `running` is demoted: `needs_you` is a session blocked on a human and
    silence is exactly what it looks like, and `stopped` cannot go staler.
    """
    if row.state is SessionState.RUNNING and not is_live(row.last_event_at, now):
        return SessionState.STARTING
    return row.state


def fleet_sort_key(row: FleetRow, now: str) -> tuple[int, str]:
    """§16's order, then session id.

    The tiebreak is the session's own ulid — creation order, and stable: a live
    page re-sorted on every event must not shuffle rows that did not change.
    """
    state = effective_state(row, now)
    rank = FLEET_STATE_ORDER.index(state) if state in FLEET_STATE_ORDER else len(FLEET_STATE_ORDER)
    return rank, row.session_id


def bucket_of(row: FleetRow, now: str) -> Bucket:
    """§4's palette bucket for one row — **total by construction** (A1, r3).

    Four cases and a final `else`, in this order:

    1. a row blocked on a human is `needs_you`, whatever else is true of it.
       E-M2-26: C21's `idle_prompt` flips an idle TUI 60 s *after* the stop was
       classified, so a classified row can also be waiting on you. The rail
       wins the row; the verdict is not erased, and expanding the row shows it.
       The two facts answer different questions and coexist;
    2. a **live** session is `running` — liveness first, so silence still
       demotes a `running` row exactly as M1's `effective_state` says;
    3. a stopped row **with** an outcome takes the bucket that outcome names;
    4. anything else is `UNCLASSIFIED`.

    **The `else` is not defensive padding; it is a captured case.** C7 records
    a `-p` session whose `StopFailure` hook was killed at shutdown 2/2 times:
    the row is left a *stale* `running` with no stop event, so it matches
    neither "live" nor "stopped with an outcome". Revision 2's four cases let
    it fall off the end. We do not know what happened to it, we say so, and we
    count it (principle 5).
    """
    state = effective_state(row, now)
    if state is SessionState.NEEDS_YOU:
        return Bucket.NEEDS_YOU
    if state in (SessionState.RUNNING, SessionState.STARTING) and is_live(
        row.last_event_at, now
    ):
        return Bucket.RUNNING
    if state is SessionState.STOPPED and row.outcome in _BUCKET_VALUES:
        return Bucket(row.outcome)
    return Bucket.UNCLASSIFIED


def fleet_bucket_sort_key(row: FleetRow, now: str) -> tuple[int, str]:
    """§12's bucket order, then the session's own ulid.

    The same stable tiebreak `fleet_sort_key` chose, and for the same reason: a
    live page re-sorted on every event must not shuffle rows that did not
    change. This key is **additive** — `fleet_sort_key` and `effective_state`
    are unchanged and still answer §16's four-state question.
    """
    return BUCKET_ORDER.index(bucket_of(row, now)), row.session_id
