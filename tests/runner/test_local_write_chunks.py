"""P12 REM-FIX 1 #1: a write longer than one tmux command reaches the pane whole.

`LocalRunner.write` sent the whole payload as **one** `send-keys -H` argv, one
hex word per byte. tmux refuses a client-to-server message over its
`MAX_IMSGSIZE` with `command too long` (rc 1): reproduced on tmux 3.6a at about
5.4 KB of payload, and about 100 KB hits the platform's `E2BIG` before tmux is
reached at all. A paste into the terminal view is one WebSocket frame, so a
paste of a few kilobytes ended the stream.

Two seams:

* `LocalRunner` through its one injected command seam, `run_argv` (default
  lane, no tmux anywhere): every call it makes is within the measured ceiling
  `TMUX_COMMAND_LIMIT_B`, and the calls' hex words decode back to the payload,
  in order.
* A real tmux server on the private throwaway socket `SOCKET` (`live` lane,
  `test_runner_contract.py`'s fixture pattern): the bytes arrive on a real pane.
  `-L` is on every call, teardown included, and the socket can never be
  `shepherd` — `permitted_sockets` refuses it at construction.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly
from shepherd.core.runner import TMUX_COMMAND_LIMIT_B, RunnerHandle, SessionSpec, command_size
from shepherd.host.base import DetachedLaunch
from shepherd.runner.local import RUNNER_NAME, CommandResult, LocalRunner, make_run_argv
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    VERSION_ARGV,
    permitted_commands,
    permitted_sockets,
)

NAME = "shepherd_01JBQ8Z9XKME5RT3VWNY6P0DFG"
HANDLE = RunnerHandle(runner=RUNNER_NAME, socket=DEFAULT_SOCKET, session_name=NAME)
NO_PREFIX = DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True)
NOW = "2026-09-27T10:00:00.000000+00:00"

#: This module's own throwaway server. Never `shepherd`, never the runner's default.
SOCKET = "shepherd-m3-write-chunks"

#: More than three times the ~5.4 KB tmux refused in one command.
LONG = 20_480

OK = CommandResult(rc=0, stdout=b"", stderr=b"")


class RecordingTmux:
    """A `run_argv` that answers like tmux does to a message over its ceiling."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        if command_size(argv) > TMUX_COMMAND_LIMIT_B:
            return CommandResult(rc=1, stdout=b"", stderr=b"command too long")
        return OK

    def payloads(self) -> list[bytes]:
        """Each `send-keys -H` call's bytes, decoded from its hex words."""
        return [
            bytes(int(word, 16) for word in argv[argv.index("-t") + 2 :])
            for argv in self.calls
            if "send-keys" in argv and "-H" in argv
        ]


def scripted(tmux: RecordingTmux, sink_dir: Path) -> LocalRunner:
    anomalies: list[Anomaly] = []
    return LocalRunner(
        socket=DEFAULT_SOCKET,
        run_argv=tmux,
        launch=NO_PREFIX,
        now=lambda: NOW,
        spawn_argv=lambda spec, *, frame_bytes: ["cat"],
        record_anomaly=anomalies.append,
        sink_dir=sink_dir,
    )


def pattern(size: int) -> bytes:
    """Every byte value, repeated: a split that dropped or reordered one shows."""
    return bytes(index % 256 for index in range(size))


def test_a_long_write_goes_out_in_commands_tmux_accepts(tmp_path: Path) -> None:
    """20 KB is five `send-keys -H` calls, each inside the ceiling, whose bytes
    are the payload in order."""
    tmux = RecordingTmux()
    payload = pattern(LONG)
    scripted(tmux, tmp_path).write(HANDLE, payload)
    sizes = [command_size(argv) for argv in tmux.calls]
    assert all(size <= TMUX_COMMAND_LIMIT_B for size in sizes), sizes
    assert [len(chunk) for chunk in tmux.payloads()] == [4096, 4096, 4096, 4096, 4096]
    assert b"".join(tmux.payloads()) == payload


def test_a_keystroke_is_still_one_command(tmp_path: Path) -> None:
    """The ordinary case is unchanged: one key, one call, the same argv."""
    tmux = RecordingTmux()
    scripted(tmux, tmp_path).write(HANDLE, b"\x1b[A")
    assert tmux.calls == [
        [VERSION_ARGV[0], "-L", DEFAULT_SOCKET, "send-keys", "-H", "-t", f"={NAME}:", "1b", "5b", "41"]
    ]


def test_an_empty_write_sends_nothing(tmp_path: Path) -> None:
    """No bytes, no command: tmux would take `send-keys -H -t x` with no keys."""
    tmux = RecordingTmux()
    scripted(tmux, tmp_path).write(HANDLE, b"")
    assert tmux.calls == []


# ----- the live lane: a real server on this module's throwaway socket ---------


@pytest.fixture()
def live_runner(tmp_path: Path) -> Iterator[LocalRunner]:
    """A `LocalRunner` on `SOCKET` whose pane is `dd of=<RECEIVED>`: what the pane
    read is on disk byte for byte, not re-drawn on a screen the tty echo shares."""
    if shutil.which(VERSION_ARGV[0]) is None:
        pytest.skip(f"no multiplexer binary on this host, so no server on {SOCKET}")
    run_argv = make_run_argv(permitted_sockets(SOCKET), permitted_commands("cat", "dd"))
    anomalies: list[Anomaly] = []
    received = tmp_path / RECEIVED
    runner = LocalRunner(
        socket=SOCKET,
        run_argv=run_argv,
        launch=NO_PREFIX,
        now=lambda: NOW,
        spawn_argv=lambda spec, *, frame_bytes: ["dd", f"of={received}"],
        record_anomaly=anomalies.append,
        sink_dir=tmp_path,
    )
    runner.ensure_server()
    try:
        yield runner
    finally:
        run_argv([VERSION_ARGV[0], "-L", SOCKET, "kill-server"])


#: The file the pane's `dd` writes what it read to.
RECEIVED = "received.bin"


def lines_of(size: int) -> bytes:
    """Numbered 79-character lines, each ended by Enter: printable ASCII only, so
    the tty's one input transform on the way to `dd` is `ICRNL` (CR to LF)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    lines = [f"L{index:04d} " + (alphabet * 3)[index % 36 :][:73] for index in range(size // 80)]
    return "".join(f"{line}\r" for line in lines).encode("ascii")


@pytest.mark.live
def test_a_paste_longer_than_one_tmux_command_reaches_a_real_pane_exactly(
    live_runner: LocalRunner, tmp_path: Path
) -> None:
    """20 KB written to a real pane: the program in it reads every byte, in order."""
    spec = SessionSpec(
        session_id="01JBQ8Z9XKME5RT3VWNY6P0DFG",
        engine_session_id="71757dd1-5375-4801-b467-7898a0bc1194",
        cwd=str(tmp_path),
        brief=None,
        title=None,
        model=None,
        effort=None,
        engine="stub",
        runner="write-chunks",
        env={},
    )
    handle = live_runner.start(spec)
    payload = lines_of(LONG)
    assert len(payload) == LONG
    live_runner.write(handle, payload)
    received = tmp_path / RECEIVED
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if received.exists() and received.stat().st_size >= len(payload):
            break
        time.sleep(0.1)
    assert received.read_bytes() == payload.replace(b"\r", b"\n")
