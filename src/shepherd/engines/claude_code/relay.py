"""T10b: the client half of the `sessiond` → `controld` hop (D37).

`controld` is the control plane: it folds hook events, owns the database, and
may restart, upgrade and crash freely. `sessiond` is the one process that
cannot restart without killing agents. This module is what makes that asymmetry
survivable — a bounded, in-memory, in-order buffer that holds frames while
`controld` is away and drains them when it returns.

Three rules, each from a written decision rather than from taste:

* **The buffer is not an event store** (D24). It is bounded at
  `RELAY_BUFFER_MAX` and it drains on reconnect. Nothing here persists, and
  `shepherd recompute` rebuilds history from transcripts.
* **Overflow is counted, not silently dropped** (principle 5). Past the bound
  the newest frame is refused and `RelayStats.overflowed` records it, so the
  loss is a number a human can see rather than a gap nobody can explain.
* **`sessiond` never migrates** (§7 migration rule 3). The relay sends nothing
  until `controld` has reported the schema version it expects. A wrong version
  is not an error to retry through — it buffers, counts, and keeps waiting.
  Two processes racing one migration is the bug you cannot debug at 2am.

The transport is a single long-lived connection carrying newline-delimited
frames (`relay_wire`), owned end to end by one background thread; `send()` only
ever touches the deque. Nothing in this module imports `store` — `sessiond` is
not a writer (D37), and `tests/boundaries/test_storage_boundary.py` makes that
mechanical.
"""

from __future__ import annotations

import socket
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.frames import Frame
from shepherd.engines.claude_code.relay_wire import WireError, decode_hello, encode_frame

#: D24's bound: enough to cover a long `controld` restart, small enough that a
#: `sessiond` holding it cannot become a memory problem for the agents it must
#: never harm (principle 4).
RELAY_BUFFER_MAX = 10_000

#: (floor, ceiling). Never busier than 0.1 s — a reconnect storm against a
#: socket that is not there costs nothing but wakeups; never slower than 2.0 s,
#: because that is the longest a restarted `controld` should wait to be found.
RELAY_BACKOFF_S: tuple[float, float] = (0.1, 2.0)

#: How long `controld` has to say hello before the attempt is abandoned.
HELLO_TIMEOUT_S = 2.0

#: How long the sender waits for a new frame before re-checking its flags.
IDLE_POLL_S = 0.02


def backoff_delay(attempt: int, bounds: tuple[float, float] = RELAY_BACKOFF_S) -> float:
    """Exponential backoff, clamped to `bounds`. Pure, so the bound is testable
    without waiting for it."""
    floor, ceiling = bounds
    return min(ceiling, floor * (2.0**attempt))


@dataclass(frozen=True)
class RelayStats:
    """Everything a human needs to answer "did we lose anything, and why?"."""

    buffered: int
    overflowed: int
    delivered: int
    connected: bool
    schema_mismatch: int
    last_error: str | None


class Relay:
    """Send frames to `controld`, or hold them until it comes back."""

    def __init__(
        self,
        target: Path,
        max_buffered: int,
        expected_version: int,
        *,
        backoff: tuple[float, float] = RELAY_BACKOFF_S,
    ) -> None:
        self._target = target
        self._max_buffered = max_buffered
        self._expected_version = expected_version
        self._backoff = backoff
        self._buffer: deque[Frame] = deque()
        self._lock = threading.Lock()
        self._wakeup = threading.Condition(self._lock)
        self._stopping = threading.Event()
        self._overflowed = 0
        self._delivered = 0
        self._schema_mismatch = 0
        self._connected = False
        self._last_error: str | None = None
        self._conn: socket.socket | None = None
        self._sender = threading.Thread(target=self._run, name="relay", daemon=True)
        self._sender.start()

    # ---- the caller's side: never blocks, never raises, never drops silently.

    def send(self, frame: Frame) -> None:
        with self._wakeup:
            if len(self._buffer) >= self._max_buffered:
                self._overflowed += 1
                return
            self._buffer.append(frame)
            self._wakeup.notify()

    def stats(self) -> RelayStats:
        with self._lock:
            return RelayStats(
                buffered=len(self._buffer),
                overflowed=self._overflowed,
                delivered=self._delivered,
                connected=self._connected,
                schema_mismatch=self._schema_mismatch,
                last_error=self._last_error,
            )

    def close(self, drain_s: float) -> RelayStats:
        """Give the buffer `drain_s` to empty, then stop. Returns the final
        count, so a shutdown that lost frames says so (F15, principle 5)."""
        deadline = threading.Event()
        timer = threading.Timer(drain_s, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                with self._lock:
                    if not self._buffer:
                        break
                deadline.wait(IDLE_POLL_S)
        finally:
            timer.cancel()
        self._stopping.set()
        with self._wakeup:
            self._wakeup.notify_all()
        self._sender.join(timeout=max(drain_s, 1.0))
        self._shut()
        return self.stats()

    # ---- the sender thread: owns the connection and the handshake.

    def _run(self) -> None:
        attempt = 0
        while not self._stopping.is_set():
            if self._conn is None:
                if self._connect():
                    attempt = 0
                    continue
                self._stopping.wait(backoff_delay(attempt, self._backoff))
                attempt = min(attempt + 1, 64)
                continue
            self._drain_once()

    def _connect(self) -> bool:
        """Connect and complete §7 rule 3's handshake. False means "not yet"."""
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.settimeout(HELLO_TIMEOUT_S)
            conn.connect(str(self._target))
            hello = decode_hello(_read_line(conn))
        except (OSError, WireError) as error:
            conn.close()
            self._note(f"{type(error).__name__}: {error}")
            return False
        if hello.schema_version != self._expected_version:
            conn.close()
            with self._lock:
                self._schema_mismatch += 1
            self._note(
                f"controld reports schema version {hello.schema_version}, "
                f"this sessiond expects {self._expected_version}: buffering, never migrating"
            )
            return False
        conn.settimeout(None)
        with self._lock:
            self._conn = conn
            self._connected = True
            self._last_error = None
        return True

    def _drain_once(self) -> None:
        """Send one frame, in order. A failed send puts the frame back."""
        with self._wakeup:
            if not self._buffer:
                self._wakeup.wait(IDLE_POLL_S)
                return
            frame = self._buffer.popleft()
            conn = self._conn
        if conn is None:  # closed underneath us; the frame is still ours
            self._requeue(frame)
            return
        try:
            conn.sendall(encode_frame(frame))
        except OSError as error:
            self._requeue(frame)
            self._shut()
            self._note(f"{type(error).__name__}: {error}")
            return
        with self._lock:
            self._delivered += 1

    def _requeue(self, frame: Frame) -> None:
        with self._wakeup:
            self._buffer.appendleft(frame)

    def _shut(self) -> None:
        with self._lock:
            conn, self._conn, self._connected = self._conn, None, False
        if conn is not None:
            conn.close()

    def _note(self, detail: str) -> None:
        with self._lock:
            self._last_error = detail


def _read_line(conn: socket.socket) -> bytes:
    """One newline-delimited line, or `b""` at EOF. Used only for the hello:
    every later line on this connection travels the other way."""
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(1)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        if chunk == b"\n":
            return b"".join(chunks)
