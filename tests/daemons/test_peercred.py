"""`SO_PEERCRED` at the seam it was left open at (BLOCKER T10, option (c)).

The blocker's recommendation: a `peercred()` **module function** in `host/linux.py`
and `host/mac.py`, injected by the composition root. It keeps D55's six seam
members intact (Decision pressure 2 spent the sixth on `hook_dispatch`), keeps
the Linux-only socket constant inside `host/` — where
`tests/boundaries/test_platform_branching.py` says platform facts must live — and
uses the injection point `serve_ingest` already has.

Two seams are exercised here, and the second is the one that matters:

1. `peercred(sock)` against a real `AF_UNIX` socket pair;
2. `serve_ingest(..., peer_credentials=detect_peercred())` — the way `sessiond`
   wires it — with a real client connecting, so `Frame.peer_pid` is a pid read
   off a kernel struct rather than one a test handed in.

E21 still stands: the frame's own `CLAUDE_PID` is the authoritative owning pid,
and walking `/proc` from a peer pid races the hook's exit. This is the
spoof-resistant *second* opinion, not a replacement for it.
"""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

import pytest
from test_sessiond_socket import Collector, await_true, dispatch, listening, plan_for

from shepherd.engines.claude_code.ingest_socket import SHUTDOWN_DRAIN_S, serve_ingest
from shepherd.host.detect import detect_peercred
from shepherd.host.linux import peercred

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"), reason="SO_PEERCRED is a Linux socket option"
)

PAYLOAD = b'{"hook_event_name":"PreToolUse"}\n'


def test_peercred_reads_this_process_off_a_real_socket() -> None:
    """A socket pair is both peers at once, so the answer is checkable."""
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with left, right:
        assert peercred(left) == os.getpid()
        assert peercred(right) == os.getpid()


def test_peercred_on_a_socket_that_has_no_peer_is_unknown() -> None:
    """Principle 5: a credential we cannot read is `None`, never a guessed pid."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as lonely:
        assert peercred(lonely) is None


def test_detect_peercred_gives_the_composition_root_one_callable() -> None:
    """The branch stays in `host/` — the daemon asks for the reader, not the OS."""
    reader = detect_peercred()
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with left, right:
        assert reader(left) == os.getpid()


def test_the_injected_reader_puts_a_real_pid_on_the_frame(tmp_path: Path) -> None:
    """The whole point: with the reader injected, `peer_pid` stops being `None`."""
    plan = plan_for(tmp_path)
    collector = Collector()
    stop = threading.Event()
    thread = threading.Thread(
        target=serve_ingest,
        kwargs={
            "plan": plan,
            "on_frame": collector.on_frame,
            "on_shutdown": collector.on_shutdown,
            "shutdown": stop,
            "peer_credentials": detect_peercred(),
        },
        daemon=True,
    )
    thread.start()
    try:
        await_true(plan.path.exists, "the socket was never bound")
        dispatch(plan.path, PAYLOAD)
        await_true(lambda: collector.count() == 1, "no frame arrived")
    finally:
        stop.set()
        thread.join(timeout=SHUTDOWN_DRAIN_S + 2.0)

    assert collector.frames[0].peer_pid == os.getpid()


def test_without_the_reader_the_pid_is_an_honest_unknown(tmp_path: Path) -> None:
    """The state T10 shipped, kept as the default: nothing injected, nothing guessed."""
    plan = plan_for(tmp_path)
    collector = Collector()
    with listening(plan, collector):
        dispatch(plan.path, PAYLOAD)
        await_true(lambda: collector.count() == 1, "no frame arrived")
    assert collector.frames[0].peer_pid is None
