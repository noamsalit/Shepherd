"""T10b, D37's guarantee: `controld` may restart; `sessiond` may not.

The buffer is not an event store (D24). It is what keeps a `controld` restart
from costing anything within its bound, and what makes the cost **counted**
rather than silent when the bound is exceeded (principle 5) — `shepherd
recompute` rebuilds the rest from transcripts.

Real sockets throughout: buffering and drain-in-order are properties of the
transport, and a mock of the transport cannot disagree with the code.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from shepherd.core.frames import Frame
from shepherd.daemons.control_ingest import serve_control_ingest
from shepherd.engines.claude_code.relay import (
    RELAY_BACKOFF_S,
    RELAY_BUFFER_MAX,
    Relay,
    backoff_delay,
)
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

CEILING_S = 5.0
QUIET_S = 0.3
FAST_BACKOFF = (0.01, 0.05)


def control_plan(tmp_path: Path) -> SocketPlan:
    return SocketPlan(
        path=tmp_path / "shepherd" / "controld.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


def frame(index: int) -> Frame:
    return Frame(
        payload=b'{"n":%d}\n' % index,
        received_at=f"2026-09-16T00:00:{index:02d}+00:00",
        peer_pid=index,
    )


def await_true(predicate: object, message: str, ceiling_s: float = CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(message)


class Received:
    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.lock = threading.Lock()

    def on_frame(self, frame_in: Frame) -> None:
        with self.lock:
            self.frames.append(frame_in)

    def count(self) -> int:
        with self.lock:
            return len(self.frames)

    def payloads(self) -> list[bytes]:
        with self.lock:
            return [f.payload for f in self.frames]


@contextmanager
def controld(plan: SocketPlan, received: Received) -> Iterator[None]:
    stop = threading.Event()
    thread = threading.Thread(
        target=serve_control_ingest,
        args=(plan, EXPECTED_SCHEMA_VERSION, received.on_frame, stop),
        daemon=True,
    )
    thread.start()
    await_true(plan.path.exists, "controld never bound its socket")
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=CEILING_S)
        assert not thread.is_alive()


def test_relay_buffers_while_controld_down(tmp_path: Path) -> None:
    """Nothing is delivered and nothing is lost while there is no listener."""
    plan = control_plan(tmp_path)
    relay = Relay(plan.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
    try:
        for index in range(5):
            relay.send(frame(index))
        time.sleep(QUIET_S)
        stats = relay.stats()
        assert stats.buffered == 5
        assert stats.delivered == 0
        assert stats.overflowed == 0
        assert not stats.connected
        assert stats.last_error is not None, "a down controld is a known state, not a silent one"
    finally:
        relay.close(0.1)


def test_relay_buffer_overflow_is_counted(tmp_path: Path) -> None:
    """Principle 5: past the bound the loss is counted, never silent."""
    plan = control_plan(tmp_path)
    relay = Relay(plan.path, 3, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
    try:
        for index in range(10):
            relay.send(frame(index))
        stats = relay.stats()
        assert stats.buffered == 3, "the buffer is bounded"
        assert stats.overflowed == 7, "every dropped frame is counted"
        assert stats.delivered == 0
    finally:
        relay.close(0.1)


def test_relay_drains_in_order_on_reconnect(tmp_path: Path) -> None:
    """The whole point of the split: a `controld` restart costs nothing within
    the bound, and the frames arrive in the order the hooks produced them."""
    plan = control_plan(tmp_path)
    relay = Relay(plan.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
    received = Received()
    try:
        for index in range(20):
            relay.send(frame(index))
        time.sleep(QUIET_S)
        assert relay.stats().delivered == 0, "delivered to a controld that is not running"

        with controld(plan, received):
            await_true(lambda: received.count() == 20, "the buffer never drained")
            assert received.payloads() == [frame(index).payload for index in range(20)]

        # …and a second restart drains the frames sent in between, still in order.
        for index in range(20, 25):
            relay.send(frame(index))
        with controld(plan, received):
            await_true(lambda: received.count() == 25, "the second drain never happened")
            assert received.payloads() == [frame(index).payload for index in range(25)]
        stats = relay.stats()
        assert stats.delivered == 25
        assert stats.overflowed == 0
    finally:
        relay.close(0.5)


def test_relay_backoff_is_bounded() -> None:
    """Never busier than 0.1 s, never slower than 2.0 s, never going backwards.

    The bounds are the plan's numbers, not a re-computation of the formula.
    """
    floor, ceiling = RELAY_BACKOFF_S
    assert (floor, ceiling) == (0.1, 2.0)
    delays = [backoff_delay(attempt) for attempt in range(60)]
    assert delays[0] == 0.1
    assert all(0.1 <= delay <= 2.0 for delay in delays), delays
    assert all(later >= earlier for earlier, later in zip(delays, delays[1:])), delays
    assert delays[-1] == 2.0, "the backoff must reach its ceiling and stay there"


def test_control_ingest_unlinks_socket_on_shutdown(tmp_path: Path) -> None:
    """F15/E20: a stale path gives `ECONNREFUSED` and blocks the next bind."""
    plan = control_plan(tmp_path)
    received = Received()
    with controld(plan, received):
        assert plan.path.exists()
    assert not plan.path.exists(), "controld left its socket behind"

    # …and the proof that this is what matters: it binds again immediately.
    with controld(plan, received):
        assert plan.path.exists()
    assert not plan.path.exists()
