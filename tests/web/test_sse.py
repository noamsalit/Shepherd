"""T15's stream half: §12's envelope, `seq`, and gap replay over real HTTP.

Seam: HTTP. §12's contract is about bytes on a socket — `Last-Event-ID` is a
request header and `id:` is a frame field, so a test that called `subscribe()`
directly would prove nothing about the thing a browser reconnects to.
"""

from __future__ import annotations

import json

from web.conftest import Client

from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.stream import GAP_EVENT_KIND, STREAM_RING_SIZE, publish
from shepherd.web import routes

#: §12's envelope, exactly. A key more is a leak; a key fewer is a broken page.
ENVELOPE_KEYS = frozenset({"seq", "at", "type", "session_id", "project_id", "data"})

AT = "2026-09-08T11:04:12Z"


def state_change(session_id: str = "s-1", to: str = "needs_you") -> StreamEvent:
    return StreamEvent(
        kind="session.state_changed",
        session_id=session_id,
        payload={
            "project_id": "w-1",
            "from": "running",
            "to": to,
            "why": "idle — waiting for your next instruction",
        },
        occurred_at=AT,
    )


def envelopes(frames: list[dict[str, str]]) -> list[dict[str, object]]:
    decoded: list[dict[str, object]] = []
    for frame in frames:
        if "data" not in frame:
            continue
        body: object = json.loads(frame["data"])
        assert isinstance(body, dict)
        decoded.append(body)
    return decoded


def test_sse_envelope_shape(client: Client) -> None:
    """§12: one endpoint, one envelope, and the id a reconnect resumes from."""
    publish(state_change())
    frames = client.frames(routes.SSE_PATH, count=1, headers={"Last-Event-ID": "0"})
    assert len(frames) == 1
    assert frames[0]["id"] == "1"
    # No `event:` field: a named frame reaches only a listener registered for
    # that name, so naming them would drop every type the page does not yet
    # know about. The type travels inside the envelope instead.
    assert "event" not in frames[0]

    body = envelopes(frames)[0]
    assert set(body) == ENVELOPE_KEYS
    assert body["seq"] == 1
    assert body["at"] == AT
    assert body["type"] == "session.state_changed"
    assert body["session_id"] == "s-1"
    assert body["project_id"] == "w-1"
    data = body["data"]
    assert isinstance(data, dict)
    assert data["to"] == "needs_you"
    assert data["why"] == "idle — waiting for your next instruction"


def test_sse_content_type_is_a_stream(client: Client) -> None:
    publish(state_change())
    frames = client.frames(routes.SSE_PATH, count=1, headers={"Last-Event-ID": "0"})
    assert frames != []


def test_sse_seq_monotonic(client: Client) -> None:
    """P12: the page's cursor only ever moves forward."""
    for index in range(3):
        publish(state_change(session_id=f"s-{index}"))
    frames = client.frames(routes.SSE_PATH, count=3, headers={"Last-Event-ID": "0"})
    seqs = [int(frame["id"]) for frame in frames]
    assert seqs == [1, 2, 3]
    assert [body["seq"] for body in envelopes(frames)] == [1, 2, 3]


def test_sse_replay_from_last_event_id(client: Client) -> None:
    """§12: a reconnecting client sends `Last-Event-ID` and gets the gap."""
    for index in range(4):
        publish(state_change(session_id=f"s-{index}"))
    frames = client.frames(routes.SSE_PATH, count=2, headers={"Last-Event-ID": "2"})
    assert [int(frame["id"]) for frame in frames] == [3, 4]


def test_sse_without_last_event_id_starts_at_the_tail(client: Client) -> None:
    """A new tab wants what happens next, not the last hour."""
    for index in range(3):
        publish(state_change(session_id=f"s-{index}"))
    frames = client.frames(routes.SSE_PATH, count=1, read_timeout=2.0)
    assert frames == []


def test_sse_replay_gap_is_explicit(client: Client) -> None:
    """Principle 5: a client past the ring is told so, never handed a partial."""
    published = STREAM_RING_SIZE + 50
    for index in range(published):
        publish(state_change(session_id=f"s-{index}"))
    frames = client.frames(routes.SSE_PATH, count=2, headers={"Last-Event-ID": "1"})
    first = envelopes(frames)[0]
    assert first["type"] == GAP_EVENT_KIND
    data = first["data"]
    assert isinstance(data, dict)
    # The ring holds seqs 51..4146, so a client at seq 1 missed exactly 2..50 —
    # and is told the range rather than handed a history that looks complete.
    assert data["missed_from"] == 2
    assert data["missed_through"] == published - STREAM_RING_SIZE
    assert data["missed_through"] == 50
    # …and the frame after the gap is the oldest event the ring still holds.
    assert int(frames[1]["id"]) == 51
