"""§12's stream, serialised: one envelope, a monotonic `seq`, explicit gaps.

The ring and its sequence live in L4 (`toolsurface.stream`, ADR-7). This module
owns exactly one thing: turning a `StreamDelivery` into the bytes §12 specifies,
and turning a `Last-Event-ID` header back into a cursor. Nothing here decides
what is in the ring, and nothing here talks to a socket.

Three properties the page depends on:

* **`id:` is the `seq`.** `StreamEvent` has no sequence field — the ring issues
  one — so `subscribe()` yields the pair and the frame carries it. That is what
  makes `Last-Event-ID` resumable rather than approximate.
* **A gap is an event.** A client further behind than `STREAM_RING_SIZE` gets a
  `stream.gap` frame naming the range it missed, then the rest. Principle 5: it
  is told, never handed a truncated history that looks complete.
* **No polling.** `subscribe()` blocks on a condition variable; the idle
  keep-alive is a comment line, not a datum, so the page never asks twice for
  something that has not changed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

from shepherd.toolsurface.stream import StreamDelivery, subscribe

SSE_CONTENT_TYPE = "text/event-stream"

#: How long the stream waits between events before writing a keep-alive comment.
#: A comment is not a message: it keeps the connection from being reaped without
#: telling the page anything, which is the opposite of a poll.
IDLE_TIMEOUT_S = 15.0

KEEPALIVE = b": keep-alive\n\n"
OPENED = b": open\n\n"

#: §12's envelope promotes these two out of the payload; the rest is `data`.
SESSION_ID_KEY = "session_id"
PROJECT_ID_KEY = "project_id"

_UNKNOWN_TIME = "unknown"


def parse_last_event_id(raw: str | None) -> int | None:
    """The cursor a reconnecting client claims, or `None` for "from now on".

    An unreadable header is treated as absent rather than as zero: replaying the
    whole ring to a client that sent nonsense is a worse failure than starting
    it at the tail, and it never raises.
    """
    if raw is None:
        return None
    try:
        seq = int(raw.strip())
    except ValueError:
        return None
    return seq if seq >= 0 else None


def _jsonable(value: object) -> object:
    """§13's whitelist at the last sink: primitives pass, everything else is text.

    A payload carrying anything richer than JSON cannot reach the browser as an
    object it might introspect — it arrives as a string, or not at all.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def envelope(delivery: StreamDelivery) -> dict[str, object]:
    """§12's exact keys — `seq`, `at`, `type`, `session_id`, `project_id`, `data`."""
    event = delivery.event
    payload = event.payload
    project_id = payload.get(PROJECT_ID_KEY)
    return {
        "seq": delivery.seq,
        "at": event.occurred_at or _UNKNOWN_TIME,
        "type": event.kind,
        "session_id": event.session_id,
        "project_id": project_id if isinstance(project_id, str) else None,
        "data": {
            str(key): _jsonable(value)
            for key, value in payload.items()
            if key not in (SESSION_ID_KEY, PROJECT_ID_KEY)
        },
    }


def frame(body: Mapping[str, object]) -> bytes:
    """One `text/event-stream` frame. `id:` is the `seq` a reconnect resumes from.

    There is deliberately **no `event:` field**. `EventSource` delivers a named
    frame only to a listener registered for that exact name, so naming the
    frames would mean the page silently drops every event type it was not
    written to expect — and §12's type list grows at M2. One envelope, one
    `message` listener, and the page dispatches on `type` inside it.
    """
    return f"id: {body['seq']}\ndata: {json.dumps(body)}\n\n".encode()


def stream(since_seq: int | None, idle_timeout_s: float = IDLE_TIMEOUT_S) -> Iterator[bytes]:
    """The backlog after `since_seq`, then whatever arrives — forever.

    The loop ends when the caller stops writing, which is what a closed tab
    looks like from here. It never returns to ask whether something changed:
    `subscribe()` blocks until the ring wakes it.
    """
    yield OPENED
    cursor = since_seq
    while True:
        delivered = False
        for delivery in subscribe(cursor, idle_timeout_s=idle_timeout_s):
            cursor = delivery.seq
            delivered = True
            yield frame(envelope(delivery))
        if not delivered:
            yield KEEPALIVE
        # `cursor` stays `None` until the first event arrives, so an idle tail
        # subscriber re-subscribes at the tail rather than replaying the ring.
        # The instant between the two is the one window in which a tail client
        # can miss an event; see BLOCKER T15-1 — closing it needs a current-seq
        # datum from L4, not a second mechanism here.
