"""The event ring behind `subscribe()` (RD3, ADR-4, ADR-7, §12).

§12 requires a stream with **no polling in the browser**, a monotonic `seq`, and
gap replay for a client that reconnects with a `Last-Event-ID`. L4 is the only
legal home for it: `signals/` is L2 and may not import upward, so the
composition root publishes what `signals/` returned, and `StreamEvent` lives in
`core/` precisely so neither side imports the other.

ADR-7's two rules are the whole implementation:

* **One lock**, held across append-and-increment and across a subscriber's
  snapshot, so no reader can observe a `seq` whose event is not in the ring yet;
* a **bounded** ring — when a client's cursor has fallen off the end, the gap is
  delivered as an event rather than papered over. Unknown is a first-class value
  (principle 5): a client that missed 4 000 events is told so, and never handed a
  quietly truncated history that looks complete.

`subscribe()` yields `StreamDelivery`, not a bare `StreamEvent`: §12's
`Last-Event-ID` contract is about the `seq`, and `StreamEvent` (`core/`, T1) has
no room for one. Pairing them here keeps the sequence owned by the ring that
issues it.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from shepherd.core.clock import epoch_millis
from shepherd.core.stream import StreamEvent

#: ADR-7. At the fold's observed rates this is many minutes of history, which is
#: longer than any reconnect that is not a restart.
STREAM_RING_SIZE: int = 4096

#: The gap is an event, so it travels the same path as everything else and needs
#: no second channel to reach the page.
GAP_EVENT_KIND = "stream.gap"

_UNKNOWN_TIME = "unknown"

#: BC-03: how many seqs one process may issue per millisecond of wall time
#: before it could reach the next process's first. A restart seeds the ring at
#: `epoch_millis() * SEQ_BASE_PER_MS`, so a client still holding an id from the
#: previous process is *behind* the new ring and is told about the gap. At
#: today's clock that is ~1.8e15 — below 2^53, exact in JSON and in JavaScript.
SEQ_BASE_PER_MS: int = 1000


@dataclass(frozen=True)
class StreamDelivery:
    """One event with the sequence the ring gave it."""

    seq: int
    event: StreamEvent


_CONDITION = threading.Condition(threading.Lock())
_RING: deque[StreamDelivery] = deque(maxlen=STREAM_RING_SIZE)
_SEQ = 0


def publish(event: StreamEvent) -> int:
    """Append and increment under one lock; the new `seq` is returned.

    Called by the composition root — **never** by `signals/` (ADR-4, F5).
    """
    global _SEQ
    with _CONDITION:
        _SEQ += 1
        _RING.append(StreamDelivery(seq=_SEQ, event=event))
        _CONDITION.notify_all()
        return _SEQ


def stream_seq_base() -> int:
    """The first sequence value a process starting now should issue after."""
    return epoch_millis() * SEQ_BASE_PER_MS


def reset_stream(seq_base: int = 0) -> None:
    """Empty the ring and restart the sequence at `seq_base`.

    Startup passes `stream_seq_base()` (BC-03); every test keeps the default 0.
    """
    global _SEQ
    with _CONDITION:
        _RING.clear()
        _SEQ = seq_base
        _CONDITION.notify_all()


def _gap(cursor: int, oldest_seq: int, occurred_at: str) -> StreamDelivery:
    return StreamDelivery(
        seq=oldest_seq - 1,
        event=StreamEvent(
            kind=GAP_EVENT_KIND,
            session_id=None,
            payload={"missed_from": cursor + 1, "missed_through": oldest_seq - 1},
            occurred_at=occurred_at,
        ),
    )


def _drain_locked(cursor: int) -> list[StreamDelivery]:
    """Everything the ring still holds after `cursor`, gap marker first.

    Called with `_CONDITION` held — that is what makes the snapshot atomic
    against a concurrent `publish()` (ADR-7).
    """
    pending = [delivery for delivery in _RING if delivery.seq > cursor]
    if not pending:
        return []
    oldest = pending[0].seq
    if oldest > cursor + 1:
        occurred_at = pending[0].event.occurred_at or _UNKNOWN_TIME
        return [_gap(cursor, oldest, occurred_at), *pending]
    return pending


def subscribe(
    since_seq: int | None, idle_timeout_s: float | None = None
) -> Iterator[StreamDelivery]:
    """Everything after `since_seq`, then whatever arrives next.

    `since_seq=None` starts at the tail — a new client wants what happens from
    now, not the last hour. With `idle_timeout_s=None` the iterator ends once the
    backlog is drained (the replay case); with a timeout it waits that long
    between events before ending, which is how a live stream is held open
    without a poll.

    A cursor *ahead* of the head is not from this ring — the wall clock stepped
    back between two starts (BC-03, E5) — so it is served as `0`: the client
    gets the ring, with the gap marker when the ring does not start at 1.
    """
    with _CONDITION:
        cursor = _SEQ if since_seq is None else since_seq
        if cursor > _SEQ:
            cursor = 0
    while True:
        with _CONDITION:
            pending = _drain_locked(cursor)
            if not pending:
                if idle_timeout_s is None or not _CONDITION.wait(idle_timeout_s):
                    return
                pending = _drain_locked(cursor)
                if not pending:
                    continue
            cursor = pending[-1].seq
        yield from pending
