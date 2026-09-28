"""BC-03: a client resuming with an id from an earlier process (§12).

§12 promises that a client reconnecting with a `Last-Event-ID` "gets the gap
replayed", and that `seq` is monotonic. Before BC-03 every process restarted
`seq` at 0, so a page holding process A's last id (say 812) reconnected to
process B, whose ring held seq 1..3, and was handed nothing: its cursor was
*ahead* of B's head and the ring only knew how to report a cursor *behind* it.

Two halves, each at the ring's own seam (`reset_stream` / `publish` /
`subscribe`):

* each process seeds its sequence above every earlier process's
  (`stream_seq_base()`), so an old id is behind the new ring and the existing
  gap path answers it;
* a cursor ahead of the head — a wall clock stepped back between two starts
  (E5) — is served as cursor 0, which replays the ring rather than nothing.
"""

from __future__ import annotations

import pytest

from shepherd.core.stream import StreamEvent
from shepherd.toolsurface import stream
from shepherd.toolsurface.stream import GAP_EVENT_KIND, publish, subscribe


def event(index: int) -> StreamEvent:
    return StreamEvent(
        kind="session.state",
        session_id=f"s{index}",
        payload={"n": index},
        occurred_at="2026-09-24T00:00:00.000Z",
    )


def test_a_cursor_ahead_of_the_ring_gets_the_new_events() -> None:
    """E5: the head is 3 and the client says 50. Nothing it holds is in this
    ring, so it gets the whole ring — not an empty replay that looks complete."""
    stream.reset_stream()
    for index in range(3):
        publish(event(index))

    replayed = list(subscribe(since_seq=50))

    assert [delivery.event.session_id for delivery in replayed] == ["s0", "s1", "s2"]


def test_a_cursor_from_an_earlier_process_gets_a_gap_then_the_new_events() -> None:
    """B4: A publishes five and stops; B starts well above A; the page comes
    back with A's last id and is told what it missed before B's events."""
    last = 0
    for index in range(5):
        last = publish(event(index))
    stream.reset_stream(seq_base=last + 1000)
    for index in range(3):
        publish(event(10 + index))

    replayed = list(subscribe(since_seq=last))

    assert [delivery.event.kind for delivery in replayed] == [GAP_EVENT_KIND] + [
        "session.state"
    ] * 3
    assert [delivery.event.session_id for delivery in replayed[1:]] == ["s10", "s11", "s12"]


def test_the_seq_base_moves_with_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """PP-D: one millisecond later is a thousand seqs higher."""
    monkeypatch.setattr(stream, "epoch_millis", lambda: 1_758_672_000_000)
    earlier = stream.stream_seq_base()
    monkeypatch.setattr(stream, "epoch_millis", lambda: 1_758_672_000_001)
    later = stream.stream_seq_base()

    assert later - earlier == 1000
    assert stream.SEQ_BASE_PER_MS == 1000
