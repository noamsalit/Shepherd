"""T10: the ingest socket — bind, accept, read to EOF, hand the frame over.

The logic half of `sessiond` (ADR-1: `daemons/` holds no logic). Every rule
here has a capture behind it in data-schemas §"Unix domain socket at mode 0600
+ `SO_PEERCRED`":

* **`umask` before `bind()`** (E20). A socket's mode comes from the umask at
  bind time; with the default 022 the capture shows `srwxr-xr-x`. There is no
  chmod window to close afterwards, so the mode is set the only way it can be.
* **unlink before bind, and unlink on exit** (E20, F15). A stale socket file
  gives clients `ECONNREFUSED` and the next bind `EADDRINUSE`. A `sessiond`
  that cannot rebind after a crash is a `sessiond` that cannot restart.
* **read to EOF** (§"Hook runtime contract"). The dispatcher writes and closes
  and never waits for a reply; a listener that stops at the first short read
  truncates a 40 KB frame that the probe verified arrives complete.
* **the path budget belongs to the seam** (E19). `control_socket()` raises
  `SocketPathTooLong` before a bind is ever attempted, so nothing here measures
  a path — it would be a second authority for a platform fact (D55).

`peer_credentials` is injected rather than called inline. `SO_PEERCRED` is
Linux-only and credentials are captured at `connect()`, so walking `/proc` from
them races the peer's exit (E21) — and `CLAUDE_PID` in the frame is
authoritative anyway. The parameter exists so the composition root can supply a
platform-specific lookup without this module naming one; its absence is `None`,
an unknown pid (principle 5), never a guess.
"""

from __future__ import annotations

import errno
import os
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from shepherd.core.clock import utc_now
from shepherd.core.frames import Frame
from shepherd.host.base import SocketPlan

#: How long `accept()` blocks before the shutdown flag is re-read. Small enough
#: that `SIGTERM` is acted on promptly, large enough not to spin.
ACCEPT_TIMEOUT_S = 0.05

#: A hook that connects and then stalls must not hold the listener. §8 bounds a
#: hung `sessiond` at 250 ms from the hook's side; this is the mirror bound.
READ_TIMEOUT_S = 1.0

#: How long a clean shutdown may spend draining before the socket is unlinked
#: and the process exits (F15). The plan's value.
SHUTDOWN_DRAIN_S = 2.0

RECV_CHUNK = 65_536
LISTEN_BACKLOG = 64


@contextmanager
def _umask(mode: int) -> Iterator[None]:
    """Set the umask for exactly one bind, then put it back.

    `umask` is process-global: leaving it set would change the mode of every
    file the process creates afterwards.
    """
    previous = os.umask(0o777 & ~mode)
    try:
        yield
    finally:
        os.umask(previous)


def unlink_socket(path: Path) -> None:
    """Remove a socket path, tolerating one that is already gone (principle 5)."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as error:  # pragma: no cover - a directory we do not own
        if error.errno not in (errno.EACCES, errno.EPERM):
            raise


def bind_listener(plan: SocketPlan, backlog: int = LISTEN_BACKLOG) -> socket.socket:
    """A listening socket at `plan.path`, at `plan.sock_mode`, in a directory at
    `plan.dir_mode`. Shared by both listeners so the two sockets in M1 cannot
    drift apart in the one property an attacker cares about."""
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(plan.path.parent, plan.dir_mode)
    unlink_socket(plan.path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with _umask(plan.sock_mode):
            listener.bind(str(plan.path))
        listener.listen(backlog)
        listener.settimeout(ACCEPT_TIMEOUT_S)
    except BaseException:
        listener.close()
        raise
    return listener


def accept_next(listener: socket.socket) -> socket.socket | None:
    """One connection, or `None` if none arrived within the accept timeout."""
    try:
        conn, _ = listener.accept()
    except (TimeoutError, socket.timeout):
        return None
    except OSError as error:
        if error.errno in (errno.EBADF, errno.EINVAL):  # the listener was closed
            return None
        raise
    return conn


def read_to_eof(conn: socket.socket) -> bytes:
    """Everything the peer wrote before it shut its write side.

    The whole payload, never the first chunk: a 40 KB frame arrives in several
    reads, and the dispatcher's EOF is the only end-of-frame marker this hop
    has.
    """
    conn.settimeout(READ_TIMEOUT_S)
    chunks: list[bytes] = []
    while True:
        try:
            chunk = conn.recv(RECV_CHUNK)
        except (TimeoutError, socket.timeout, ConnectionResetError):
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def read_lines(conn: socket.socket, shutdown: threading.Event) -> Iterator[bytes]:
    """Newline-delimited lines from a long-lived connection, until EOF.

    The other framing in M1 (T10b's relay hop): the ingest socket above is one
    connection per frame ended by EOF, this one is many frames on one
    connection, so the delimiter is the frame boundary and a partial tail is
    held until the rest of it arrives.
    """
    conn.settimeout(ACCEPT_TIMEOUT_S)
    pending = b""
    while not shutdown.is_set():
        try:
            chunk = conn.recv(RECV_CHUNK)
        except (TimeoutError, socket.timeout):
            continue
        except OSError:
            return
        if not chunk:
            return
        pending += chunk
        while b"\n" in pending:
            line, _, pending = pending.partition(b"\n")
            yield line


def now_iso() -> str:
    return utc_now()


def serve_ingest(
    plan: SocketPlan,
    on_frame: Callable[[Frame], None],
    on_shutdown: Callable[[], None],
    shutdown: threading.Event,
    peer_credentials: Callable[[socket.socket], int | None] | None = None,
) -> None:
    """Accept, frame, relay — and leave nothing behind on the way out (F15).

    Returns when `shutdown` is set: it stops accepting, gives the caller its
    drain window through `on_shutdown`, then unlinks the socket so the next
    start binds instead of failing with `EADDRINUSE`.
    """
    listener = bind_listener(plan)
    try:
        while not shutdown.is_set():
            conn = accept_next(listener)
            if conn is None:
                continue
            with conn:
                peer_pid = peer_credentials(conn) if peer_credentials is not None else None
                payload = read_to_eof(conn)
            if payload:
                on_frame(Frame(payload=payload, received_at=now_iso(), peer_pid=peer_pid))
    finally:
        listener.close()
        on_shutdown()
        unlink_socket(plan.path)
