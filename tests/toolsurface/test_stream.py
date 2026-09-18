"""T14's second half: the event ring behind `subscribe()` (RD3, ADR-4, ADR-7, §12).

Seam: `publish()` / `subscribe()`. No test reaches into the ring itself.
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

from shepherd.core.stream import StreamEvent
from shepherd.toolsurface.stream import (
    GAP_EVENT_KIND,
    STREAM_RING_SIZE,
    StreamDelivery,
    publish,
    subscribe,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"


def event(index: int) -> StreamEvent:
    return StreamEvent(
        kind="session.state",
        session_id=f"s{index}",
        payload={"n": index},
        occurred_at="2026-09-16T00:00:00Z",
    )


def test_publish_returns_a_monotonic_seq() -> None:
    assert [publish(event(i)) for i in range(3)] == [1, 2, 3]


def test_subscribe_replays_from_seq() -> None:
    """§12: a reconnecting client resumes from its `Last-Event-ID`."""
    for index in range(4):
        publish(event(index))
    replayed = list(subscribe(2))
    assert [delivery.seq for delivery in replayed] == [3, 4]
    assert [delivery.event.session_id for delivery in replayed] == ["s2", "s3"]


def test_subscribe_without_a_cursor_starts_at_the_tail() -> None:
    publish(event(0))
    assert list(subscribe(None)) == []
    seq = publish(event(1))
    assert [delivery.seq for delivery in subscribe(seq - 1)] == [seq]


def test_subscribe_reports_gap_explicitly() -> None:
    """P12/principle 5: a client that fell off the ring is told, never fed a lie."""
    for index in range(STREAM_RING_SIZE + 5):
        publish(event(index))
    deliveries = list(subscribe(1))
    assert deliveries[0].event.kind == GAP_EVENT_KIND
    assert deliveries[0].event.payload["missed_from"] == 2
    assert deliveries[0].event.payload["missed_through"] == 5
    assert deliveries[1].seq == 6
    assert [delivery.seq for delivery in deliveries] == sorted(
        delivery.seq for delivery in deliveries
    )
    assert all(
        later.seq > earlier.seq for earlier, later in zip(deliveries, deliveries[1:], strict=False)
    )


def test_subscribe_reports_no_gap_when_the_ring_still_holds_the_cursor() -> None:
    for index in range(3):
        publish(event(index))
    assert [delivery.event.kind for delivery in subscribe(0)] == ["session.state"] * 3


def test_stream_ring_is_thread_safe() -> None:
    """P19/ADR-7: one lock across append-and-increment and across a snapshot."""
    total = 500
    seen: dict[int, list[int]] = {}
    started = threading.Barrier(5)

    def reader(index: int) -> None:
        started.wait()
        seen[index] = [delivery.seq for delivery in subscribe(0, idle_timeout_s=0.5)]

    readers = [threading.Thread(target=reader, args=(index,)) for index in range(4)]
    for thread in readers:
        thread.start()
    started.wait()
    for count in range(total):
        publish(event(count))
    for thread in readers:
        thread.join(timeout=10)

    assert len(seen) == 4
    for seqs in seen.values():
        assert seqs == list(range(1, len(seqs) + 1))
        assert seqs[-1] == total


def test_signals_does_not_import_toolsurface() -> None:
    """ADR-4/F5: `signals/` is L2 and may not import upward. The composition root
    publishes; `signals/` returns a `StreamEvent`, which lives in `core/`."""
    offenders: list[str] = []
    for path in sorted((SRC_ROOT / "signals").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            offenders += [
                f"{path.name} imports {name}"
                for name in imported
                if name.startswith("shepherd.toolsurface")
            ]
    assert offenders == []
    assert StreamDelivery(seq=1, event=event(0)).event.kind == "session.state"
