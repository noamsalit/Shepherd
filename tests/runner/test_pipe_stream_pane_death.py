"""BC-09: a terminal stream ends when its pane dies.

`_PipeStream.chunks()` used to end only once `closed` was set, and only
`close()` sets it — which the WebSocket handler (`web/server.py`) calls in its
`finally`, *after* `chunks()` ends. Nothing observed the pane, so a killed pane
left the handler thread polling an idle file forever and the socket never saw
its close frame (qa6 T4 `stream.close_1000`).

**No tmux server is started by this module.** Every test drives `LocalRunner`
through its one injected command seam, `run_argv`, scripted per verb; the sink
is a real file under `tmp_path`, written by the test where `cat` would write.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from shepherd.core.anomalies import Anomaly
from shepherd.core.runner import RunnerHandle
from shepherd.host.base import DetachedLaunch
from shepherd.runner.local import RUNNER_NAME, CommandResult, LocalRunner
from shepherd.runner.tmux_cmd import DEFAULT_SOCKET

NAME = "shepherd_01JBQ8Z9XKME5RT3VWNY6P0DFG"
HANDLE = RunnerHandle(runner=RUNNER_NAME, socket=DEFAULT_SOCKET, session_name=NAME)
#: `probe_a` / `probe_sig` of `14-list-sessions-after-sigterm.txt`, re-keyed to
#: an owned name (the same rows `test_local.py` uses): alive, then dead with 143.
ALIVE_ROW = f"{NAME}|1|0||title|160|45|4041880\n".encode()
DEAD_ROW = f"{NAME}|0|1|143||160|45|4042531\n".encode()
NO_PREFIX = DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True)

#: The plan's bound on the consumer: the pane dies after the first poll, and the
#: stream must be over well inside this.
JOIN_S = 3.0

OK = CommandResult(rc=0, stdout=b"", stderr=b"")


class ScriptedTmux:
    """A `run_argv` answering each `list-sessions` from a script, and recording.

    `listings[n]` is the n-th listing's stdout; past the end the last one
    repeats. `on_listing[n]`, if present, runs just before the n-th answer — the
    place a test writes bytes the pane emitted in its last moment.
    """

    def __init__(self, listings: list[bytes], on_listing: dict[int, Callable[[], None]]) -> None:
        self.listings = listings
        self.on_listing = on_listing
        self.calls: list[list[str]] = []
        self.unpipe_rc = 0

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        if "list-sessions" in argv:
            index = sum("list-sessions" in call for call in self.calls) - 1
            self.on_listing.get(index, lambda: None)()
            stdout = self.listings[min(index, len(self.listings) - 1)]
            return CommandResult(rc=0, stdout=stdout, stderr=b"")
        if "pipe-pane" in argv and "-o" not in argv:
            if self.unpipe_rc:
                return CommandResult(
                    rc=self.unpipe_rc, stdout=b"", stderr=f"can't find session: {NAME}".encode()
                )
        return OK


def driver(tmux: ScriptedTmux, sink_dir: Path) -> LocalRunner:
    anomalies: list[Anomaly] = []
    return LocalRunner(
        socket=DEFAULT_SOCKET,
        run_argv=tmux,
        launch=NO_PREFIX,
        now=lambda: "2026-09-24T10:00:00.000000+00:00",
        spawn_argv=lambda spec, *, frame_bytes: ["claude-stub"],
        record_anomaly=anomalies.append,
        sink_dir=sink_dir,
    )


def consume(chunks: Callable[[], Iterator[bytes]]) -> tuple[threading.Thread, list[bytes]]:
    """Drain `chunks()` on a thread, the way the WebSocket handler does."""
    received: list[bytes] = []

    def run() -> None:
        for chunk in chunks():
            received.append(chunk)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, received


def append(sink: Path, data: bytes) -> None:
    """Where `cat >> <sink>` would write."""
    with sink.open("ab") as handle:
        handle.write(data)


def test_chunks_end_after_the_pane_is_gone(tmp_path: Path) -> None:
    """E10 (killed): the listing stops naming the session after its first poll.

    The bytes the pane wrote *just before* it went — appended to the sink at the
    very moment the listing first reports it gone, after the stream last read
    nothing — must still arrive: the stream drains its tail before it ends.
    """
    sink = tmp_path / f"{NAME}.pipe"
    tmux = ScriptedTmux(
        listings=[ALIVE_ROW, b""],
        on_listing={1: lambda: append(sink, b"-tail")},
    )
    stream = driver(tmux, tmp_path).attach(HANDLE)
    sink.write_bytes(b"head")
    thread, received = consume(stream.chunks)
    try:
        thread.join(JOIN_S)
        assert not thread.is_alive(), "chunks() still polling after the pane was gone"
    finally:
        stream.close()
        thread.join(JOIN_S)
    assert b"".join(received) == b"head-tail"
    assert sum("list-sessions" in call for call in tmux.calls) == 2


def test_chunks_end_when_the_pane_exits_by_itself(tmp_path: Path) -> None:
    """E10 (exited): `remain-on-exit on` keeps the row, marked dead — still an end."""
    sink = tmp_path / f"{NAME}.pipe"
    tmux = ScriptedTmux(listings=[ALIVE_ROW, DEAD_ROW], on_listing={})
    stream = driver(tmux, tmp_path).attach(HANDLE)
    sink.write_bytes(b"frame")
    thread, received = consume(stream.chunks)
    try:
        thread.join(JOIN_S)
        assert not thread.is_alive(), "chunks() still polling after the pane exited"
    finally:
        stream.close()
        thread.join(JOIN_S)
    assert b"".join(received) == b"frame"


def test_a_live_pane_keeps_its_stream_open(tmp_path: Path) -> None:
    """The negative: a pane that stays listed alive is asked about, and not ended."""
    tmux = ScriptedTmux(listings=[ALIVE_ROW], on_listing={})
    stream = driver(tmux, tmp_path).attach(HANDLE)
    thread, _ = consume(stream.chunks)
    try:
        thread.join(1.2)
        assert sum("list-sessions" in call for call in tmux.calls) >= 1  # arrival first
        assert thread.is_alive()  # …absence of an end second
    finally:
        stream.close()
        thread.join(JOIN_S)
    assert not thread.is_alive()


def test_stopping_a_stream_whose_pane_is_gone_does_not_raise(tmp_path: Path) -> None:
    """The handler's `finally` unpipes a pane tmux already removed: not a raise."""
    tmux = ScriptedTmux(listings=[b""], on_listing={})
    stream = driver(tmux, tmp_path).attach(HANDLE)
    tmux.unpipe_rc = 1
    stream.close()
    unpipes = [call for call in tmux.calls if "pipe-pane" in call and "-o" not in call]
    assert len(unpipes) == 1  # the unpipe was reached, and answered non-zero
    stream.close()  # still idempotent
    assert len([c for c in tmux.calls if "pipe-pane" in c and "-o" not in c]) == 1
