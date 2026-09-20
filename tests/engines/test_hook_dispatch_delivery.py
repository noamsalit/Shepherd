"""G1/G2/E34: the hook command this host would install, run for real.

`tests/engines/test_hookd_command.py` asserts on the *string*. This file runs
it. It takes the command from `HostPlatform.hook_dispatch()` — never a literal
of its own (P20) — hands it to `/bin/sh` exactly as a settings-file hook entry
does, and reads what arrives on a real `AF_UNIX` socket.

It exists because the macOS flag set was the one thing D55 refused to guess at
(G2, E34) and because the obvious guess is wrong in the worst way: Apple's
`nc -U -w 0` looks like OpenBSD's `-q0`, delivers small frames 10/10, bounds a
hung peer at 27 ms — and silently truncates a 40 KB frame to 16 KB
(`docs/probes/2026-09-20-macos-g1-capture.md` Result 2, 3/3). No assertion about
a string can tell those two commands apart. A bind, a write and a read can.

Three properties, on whichever platform is running:

* **delivery** — both captured frame sizes arrive byte-identical (E34 Result 2);
* **boundedness** — a `sessiond` that accepts and never reads costs the hook a
  bounded wait, not an unbounded one. This is what `timeout 0.25` buys on Linux
  and what nothing in Apple's `nc` provides;
* **exit 0, always** — no listener, no socket, no delivery: the hook still exits
  0 (principle 4, C-1). A hook that fails a tool call is worse than a blind one.
"""

from __future__ import annotations

import dataclasses
import shlex
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import HOOK_ENTRY_TIMEOUT_S, build_hook_entry
from shepherd.host.base import SocketPlan
from shepherd.host.detect import detect_host

#: data-schemas §"Common input fields", first example — one real hook payload.
SMALL_FRAME = (
    b'{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","cwd":"/tmp/x",'
    b'"hook_event_name":"PreToolUse","tool_name":"Bash"}\n'
)

#: Result 2 of `docs/probes/2026-09-16-hookd-latency.md`: 40 KB arrives complete.
LARGE_FRAME = b'{"pad":"' + b"x" * 40_000 + b'"}\n'

#: Far above the measured 264-324 ms (macOS) and 250 ms (Linux `timeout 0.25`),
#: and far below the 5 s the settings entry gives the hook (E18). A command that
#: needs more than this against a wedged peer is unbounded in the way that
#: matters, whatever number it eventually returns in.
HUNG_PEER_CEILING_S = 2.0

#: How long the reader thread is given to see EOF after the command returns.
DRAIN_S = 5.0


def plan_at(path: Path) -> SocketPlan:
    """The running host's real modes and budget, pointed at a throwaway path."""
    host = detect_host()
    return dataclasses.replace(host.control_socket("sessiond"), path=path)


class Listener:
    """One real `AF_UNIX` listener. `hang=True` accepts and never reads."""

    def __init__(self, path: Path, hang: bool = False) -> None:
        self.received: list[bytes] = []
        self._hang = hang
        #: Accepted connections kept alive for this listener's lifetime. A
        #: `hang=True` peer that lets its `conn` go out of scope is not a wedged
        #: peer: CPython drops the last reference, closes the fd, and the writer
        #: gets EOF/EPIPE in microseconds — so the bound below passes against a
        #: command with no bound at all. `test_the_wedge_fixture_really_wedges_
        #: an_unbounded_writer` is the negative control that keeps this honest.
        self._held: list[socket.socket] = []
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(path))
        self._sock.listen(4)
        self._drained = threading.Event()
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        try:
            conn, _ = self._sock.accept()
        except OSError:  # pragma: no cover - only when close() wins the race
            return
        if self._hang:
            self._held.append(conn)
            return
        with conn:
            buffer = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buffer += chunk
            self.received.append(buffer)
        self._drained.set()

    def await_drain(self, timeout: float = DRAIN_S) -> None:
        self._drained.wait(timeout)

    def close(self) -> None:
        for held in self._held:
            held.close()
        self._held.clear()
        self._sock.close()


def dispatch(command: str, payload: bytes, ceiling_s: float) -> tuple[float, int]:
    """Run the hook command the way a settings entry does: `sh -c`, stdin, exit."""
    started = time.monotonic()
    completed = subprocess.run(
        ["/bin/sh", "-c", command],
        input=payload,
        capture_output=True,
        timeout=ceiling_s,
        check=False,
    )
    return time.monotonic() - started, completed.returncode


def entry_command(path: Path) -> str:
    """The exact string that would be written into a settings file."""
    plan = plan_at(path)
    entry = build_hook_entry(plan, detect_host().hook_dispatch(plan))
    assert entry.available is True, (
        f"this host cannot dispatch a hook at all: {entry.reason}. "
        f"Requirements: {detect_host().hook_dispatch(plan).requires}"
    )
    assert entry.timeout_s == HOOK_ENTRY_TIMEOUT_S
    return entry.command


@pytest.mark.parametrize(
    ("name", "frame"),
    [("small", SMALL_FRAME), ("40kb", LARGE_FRAME)],
)
def test_the_installed_command_delivers_the_frame_byte_for_byte(
    tmp_path: Path, name: str, frame: bytes
) -> None:
    """Delivery, not "it exited 0": the bytes on the socket are compared."""
    path = tmp_path / "sessiond.sock"
    command = entry_command(path)
    listener = Listener(path)
    try:
        elapsed, code = dispatch(command, frame, ceiling_s=HUNG_PEER_CEILING_S * 5)
        listener.await_drain()
    finally:
        listener.close()

    assert code == 0, f"the hook must always exit 0 (principle 4); {name} exited {code}"
    assert listener.received, f"{name}: nothing arrived on the socket at all"
    assert listener.received[0] == frame, (
        f"{name}: {len(listener.received[0])} of {len(frame)} bytes arrived — "
        "a partial frame is the silent failure E34 names, not a slow one"
    )
    assert elapsed < HOOK_ENTRY_TIMEOUT_S


def test_a_peer_that_never_reads_costs_the_hook_a_bounded_wait(tmp_path: Path) -> None:
    """A wedged `sessiond` must not wedge the agent (spec l.312, principle 4).

    The 40 KB frame is the case that matters: it exceeds the Unix socket buffer
    (`net.local.stream.sendspace` = 8192 on macOS), so the writer blocks in
    `write()` — where no netcat timeout flag reaches it. Only an outer bound
    does: `timeout 0.25` on Linux, a `Time::HiRes` `alarm` on macOS.
    """
    path = tmp_path / "sessiond.sock"
    command = entry_command(path)
    listener = Listener(path, hang=True)
    try:
        elapsed, code = dispatch(command, LARGE_FRAME, ceiling_s=HUNG_PEER_CEILING_S)
    finally:
        listener.close()

    assert code == 0, "a hook whose peer wedged must still exit 0"
    assert elapsed < HUNG_PEER_CEILING_S


def test_no_listener_at_all_is_still_exit_zero(tmp_path: Path) -> None:
    """The socket file does not exist: nothing is delivered, nothing fails."""
    path = tmp_path / "sessiond.sock"
    command = entry_command(path)
    assert not path.exists()

    elapsed, code = dispatch(command, SMALL_FRAME, ceiling_s=HUNG_PEER_CEILING_S)
    assert code == 0
    assert elapsed < HUNG_PEER_CEILING_S


def test_the_command_under_test_is_the_hosts_own(tmp_path: Path) -> None:
    """B1: the three tests above would pass against any working command.

    This is what ties them to the product: the string they run is the one
    `hook_dispatch()` returns, with the path quoted and nothing else changed.
    """
    path = tmp_path / "sessiond.sock"
    plan = plan_at(path)
    dispatch_plan = detect_host().hook_dispatch(plan)

    assert dispatch_plan.available is True
    assert str(path) in dispatch_plan.command
    # `build_hook_entry` substitutes the path shell-quoted and changes nothing
    # else, so the string these tests ran is the host's own, exactly (P20).
    assert entry_command(path) == dispatch_plan.command.replace(
        str(path), shlex.quote(str(path)), 1
    )


#: An unbounded writer against the same fixture: connect, write the whole frame,
#: and block in `sendall()` for as long as the peer refuses to read. It is
#: deliberately **not** the product command — no `timeout`, no `perl` alarm, no
#: netcat flag — because its whole job is to be the slow case.
#:
#: Stdlib Python rather than a bare `nc` so that it is unbounded on both
#: platforms for the same reason (a blocked `write()`), not for whichever reason
#: that host's netcat happens to supply.
UNBOUNDED_WRITER = (
    "exec {python} -c '"
    "import socket,sys\n"
    "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
    "s.connect(sys.argv[1])\n"
    "s.sendall(sys.stdin.buffer.read())\n"
    "' {path}"
)


def test_the_wedge_fixture_really_wedges_an_unbounded_writer(tmp_path: Path) -> None:
    """Negative control for the test above (B1).

    `test_a_peer_that_never_reads_costs_the_hook_a_bounded_wait` is the single
    executable proof behind D55's macOS re-decision and it is only worth that if
    its fixture can *fail*. Until 2026-09-20 it could not: `Listener._accept()`
    held the accepted connection in a local, so `return` dropped the last
    reference, CPython closed the fd, and the "never reads" peer actually hung
    up in microseconds. Every command bounded or not came back in ~20 ms and the
    bound assertion passed against the regression it exists to catch.

    So this test asserts the complement, against the **same** `Listener(hang=
    True)`: a writer with no outer bound must blow through `HUNG_PEER_CEILING_S`.
    If the fixture ever stops wedging, this goes red and says so — the bound
    test alone cannot.
    """
    path = tmp_path / "sessiond.sock"
    command = UNBOUNDED_WRITER.format(
        python=shlex.quote(sys.executable), path=shlex.quote(str(path))
    )
    listener = Listener(path, hang=True)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            dispatch(command, LARGE_FRAME, ceiling_s=HUNG_PEER_CEILING_S)
    finally:
        listener.close()
