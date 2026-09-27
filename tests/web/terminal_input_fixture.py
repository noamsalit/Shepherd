"""Shared doubles for P12's terminal-input tests (a named module, not a conftest).

`ScriptedRunner`'s own stream yields the screen once and ends, so the server's
writer loop sends its close frame at once and there is no open socket left to
type into. `HoldingRunner` keeps every other member of the real double and
replaces only `attach`, with a stream that stays open until it is closed —
which is the state a human is in while they type.

Its `write` is the real double's, behind three knobs a test sets (REM-FIX 1):
`gate` holds a write in flight, `fault` makes the next write raise, and
`tmux` first sends the bytes through the real `LocalRunner.write` over a
`run_argv` that refuses what tmux refuses (`command too long`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from runner.test_local_write_chunks import RecordingTmux, scripted

from shepherd.core.runner import RunnerHandle
from shepherd.runner.base import ByteStream
from shepherd.runner.local import RUNNER_NAME
from shepherd.runner.tmux_cmd import DEFAULT_SOCKET
from shepherd.testkit.scripted_runner import ScriptedRunner

#: The longest any held stream stays open. A bound, so a test that forgot to
#: close one cannot hang the suite.
HOLD_S = 10.0


class HeldStream:
    """A `ByteStream` that delivers nothing and ends only when closed."""

    def __init__(self) -> None:
        self.closed = threading.Event()

    def chunks(self) -> Iterator[bytes]:
        self.closed.wait(HOLD_S)
        return iter(())

    def close(self) -> None:
        self.closed.set()


class HoldingRunner:
    """The scripted runner with a held-open `attach`; everything else is real."""

    def __init__(self, inner: ScriptedRunner) -> None:
        self._inner = inner
        self.streams: list[HeldStream] = []
        self.gate = threading.Event()
        self.gate.set()
        self.in_flight = threading.Event()
        self.fault: BaseException | None = None
        self.tmux: RecordingTmux | None = None

    def attach(self, handle: RunnerHandle) -> ByteStream:
        stream = HeldStream()
        self.streams.append(stream)
        return stream

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        self.in_flight.set()
        self.gate.wait(HOLD_S)
        fault, self.fault = self.fault, None
        if fault is not None:
            raise fault
        if self.tmux is not None:
            local = RunnerHandle(RUNNER_NAME, DEFAULT_SOCKET, handle.session_name)
            scripted(self.tmux, Path("/nonexistent")).write(local, data)
        self._inner.write(handle, data)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)
