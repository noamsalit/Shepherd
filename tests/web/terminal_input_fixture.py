"""Shared doubles for P12's terminal-input tests (a named module, not a conftest).

`ScriptedRunner`'s own stream yields the screen once and ends, so the server's
writer loop sends its close frame at once and there is no open socket left to
type into. `HoldingRunner` keeps every other member of the real double and
replaces only `attach`, with a stream that stays open until it is closed —
which is the state a human is in while they type.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from shepherd.core.runner import RunnerHandle
from shepherd.runner.base import ByteStream
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

    def attach(self, handle: RunnerHandle) -> ByteStream:
        stream = HeldStream()
        self.streams.append(stream)
        return stream

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)
