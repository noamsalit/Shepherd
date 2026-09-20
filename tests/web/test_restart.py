"""BLOCKING 2: `controld` must be able to restart on its own port (D37).

D37's promise has two halves: one writer, and *restart the control plane without
losing the agents*. The second half is worth nothing if the new process cannot
bind the port the old one was serving on.

It cannot, unless the listening socket sets `SO_REUSEADDR`. The fleet page holds
an SSE connection for as long as the tab is open, and the server closes it on the
way out, so a connection in `TIME_WAIT` with the daemon's port as its **local**
address is the *normal* end state of any run a human actually watched — not an
edge case. `bind()` then fails with `EADDRINUSE` for up to two minutes.

The rest of `tests/web/` binds `port=0`, which is why this was invisible: an
ephemeral port is never the port that was just in use. Every test here therefore
picks one concrete port and uses it twice.
"""

from __future__ import annotations

import http.client
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from shepherd.web.server import LOOPBACK_HOST, create_server

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"


def a_free_port() -> int:
    """A port nothing is listening on, so the only reason a bind can fail is us."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((LOOPBACK_HOST, 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def serving(port: int) -> tuple[ThreadingHTTPServer, threading.Thread]:
    bound = create_server(LOOPBACK_HOST, port, static_root=STATIC_ROOT)
    thread = threading.Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    return bound, thread


def stop(bound: ThreadingHTTPServer, thread: threading.Thread) -> None:
    """What `controld.stop` does on SIGTERM: shut down, close, join."""
    bound.shutdown()
    bound.server_close()
    thread.join(timeout=5)


@pytest.fixture()
def port() -> Iterator[int]:
    yield a_free_port()


def connect_and_be_hung_up_on(port: int) -> int:
    """One real client request that the *server* closes — the page's own shape.

    `Connection: close` is what the SSE handler sends on every stream, so the
    closing side is the daemon, and the socket left in `TIME_WAIT` has the
    daemon's port as its local address. This is the state a restart meets.
    """
    connection = http.client.HTTPConnection(LOOPBACK_HOST, port, timeout=10)
    try:
        connection.request("GET", "/", headers={"Connection": "close"})
        response = connection.getresponse()
        response.read()
        return int(response.status)
    finally:
        connection.close()


#: Linux's kernel table. Present or absent; nothing else distinguishes the two
#: readers below, and the absent case is macOS, not an error (principle 5).
PROC_NET_TCP = Path("/proc/net/tcp")

#: `TCP_TIME_WAIT` as `/proc/net/tcp` spells it.
PROC_TCP_TIME_WAIT = "06"

#: …and as `netstat` spells it.
NETSTAT_TIME_WAIT = "TIME_WAIT"


def time_wait_from_proc(port: int) -> int:
    """`/proc/net/tcp`: `local_address` is `<hex ip>:<hex port>`, state is hex."""
    found = 0
    with PROC_NET_TCP.open(encoding="utf-8") as table:
        next(table)
        for line in table:
            fields = line.split()
            local_port = int(fields[1].split(":")[1], 16)
            if local_port == port and fields[3] == PROC_TCP_TIME_WAIT:
                found += 1
    return found


def time_wait_from_netstat(port: int) -> int:
    """BSD `netstat -an -p tcp`: `127.0.0.1.<port>`, state is the last column.

    The port is separated from the address by a **dot**, not a colon, on both
    `tcp4` (`127.0.0.1.54321`) and `tcp6` (`::1.54321`), so it is taken from the
    right rather than by splitting the whole field.
    """
    completed = subprocess.run(
        ["netstat", "-an", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=True,
    )
    found = 0
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 6 or fields[-1] != NETSTAT_TIME_WAIT:
            continue
        local = fields[3].rsplit(".", 1)
        if len(local) == 2 and local[1].isdigit() and int(local[1]) == port:
            found += 1
    return found


def time_wait_on(port: int) -> int:
    """Sockets whose *local* address is this port and which are in `TIME_WAIT`.

    Two kernels, two tables. This used to read `/proc/net/tcp` unconditionally,
    which on macOS is a `FileNotFoundError` inside a helper the test's own
    precondition depends on — so the failure arrived as a missing file rather
    than as anything about `SO_REUSEADDR`.

    A reader that silently returned 0 would be worse than the crash: the caller
    asserts `await_time_wait(port) > 0` precisely so a table this code cannot
    read shows up as a red precondition instead of a vacuous pass (B1).
    """
    if PROC_NET_TCP.exists():
        return time_wait_from_proc(port)
    return time_wait_from_netstat(port)


def await_time_wait(port: int, ceiling_s: float = 10.0) -> int:
    """Serve pages until the kernel shows one of them in `TIME_WAIT`.

    Which side of a closed connection lands in `TIME_WAIT` depends on who sent
    `FIN` first, and that is a race even when the server is the one closing. The
    request is cheap, so the test drives the state it needs rather than sampling
    once and hoping — a precondition that is sometimes absent is a test that is
    sometimes vacuous.
    """
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        assert connect_and_be_hung_up_on(port) == 200
        found = time_wait_on(port)
        if found > 0:
            return found
        time.sleep(0.05)
    return 0


def test_the_daemon_restarts_on_its_own_port_after_a_page_connected(port: int) -> None:
    """Boot, serve one page, stop cleanly, boot again on the same port."""
    first, thread = serving(port)

    # The precondition this test exists for: the port really is in TIME_WAIT.
    # Without it the assertion below could pass against an empty table (B1).
    assert await_time_wait(port) > 0

    stop(first, thread)
    assert time_wait_on(port) > 0

    second, thread = serving(port)
    try:
        assert int(second.server_address[1]) == port
        assert connect_and_be_hung_up_on(port) == 200
    finally:
        stop(second, thread)


def test_address_reuse_is_a_stated_choice_not_an_inherited_default() -> None:
    """The flag is load-bearing, so it is asserted rather than left to a base class.

    `ThreadingHTTPServer` sets it True and `socketserver.TCPServer` sets it
    False; which one `FleetServer` inherits is exactly the kind of fact that
    changes under you. §13's rule is about the *address* it binds, not about
    whether it may re-bind it.
    """
    from shepherd.web.server import FleetServer

    assert FleetServer.allow_reuse_address is True
