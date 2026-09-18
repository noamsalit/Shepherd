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

from shepherd.core.stream import StreamEvent

#: ADR-7. At the fold's observed rates this is many minutes of history, which is
#: longer than any reconnect that is not a restart.
STREAM_RING_SIZE: int = 4096

#: The gap is an event, so it travels the same path as everything else and needs
#: no second channel to reach the page.
GAP_EVENT_KIND = "stream.gap"

_UNKNOWN_TIME = "unknown"


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


def reset_stream() -> None:
    """Empty the ring and restart the sequence. Startup, and every test."""
    global _SEQ
    with _CONDITION:
        _RING.clear()
        _SEQ = 0
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
    """
    with _CONDITION:
        cursor = _SEQ if since_seq is None else since_seq
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
