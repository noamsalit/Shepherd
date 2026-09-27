"""T10: the ingest socket — bind, accept, read to EOF, hand the frame over.

The logic half of `sessiond` (ADR-1: `daemons/` holds no logic). Every rule
here has a capture behind it in data-schemas §"Unix domain socket at mode 0600
+ `SO_PEERCRED`":

* **`umask` before `bind()`** (E20). A socket's mode comes from the umask at
  bind time; with the default 022 the capture shows `srwxr-xr-x`. There is no
  chmod window to close afterwards, so the mode is set the only way it can be.
* **unlink before bind, and unlink on exit** (E20, F15). A stale socket file
  gives clients `ECONNREFUSED` and the next bind `EADDRINUSE`. A `sessiond`
  that cannot rebind after a crash is a `sessiond` that cannot restart. Only a
  *stale* file is unlinked: `claim_socket` refuses a path a live listener still
  accepts on (qa6 BC-16), so a second start is a refusal, not a theft.
* **a claim is a lock held for life** (D72, ADR-QR-2). `claim_socket` takes an
  exclusive `flock` on `<socket>.lock` and keeps it until the listener's
  `finally` calls `release_claim`, so there is no claim-to-bind window (E16),
  and a path that refuses the probe while the lock is ours is stale by
  construction, which the macOS full backlog alone could not prove. The kernel
  drops the lock when the holder exits, crash included. The probe still runs on
  every claim, to refuse an older binary that holds no lock.
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
import fcntl
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

#: How long `claim_socket` waits for a live owner to accept its probe (BC-16).
CLAIM_PROBE_TIMEOUT_S = 0.25

#: The lock file beside each socket (D72). Never unlinked: unlinking it would let
#: two processes lock two different inodes at the same path.
LOCK_SUFFIX = ".lock"

#: This process's claims, `{socket path: lock fd}`. Process-wide, so a second
#: claim in the owning process is re-entrant **for the lock only** (ADR-QR-2).
_HELD: dict[Path, int] = {}
_HELD_GUARD = threading.Lock()

#: One bind's umask window at a time (see `_umask`).
_UMASK_GUARD = threading.Lock()


class SocketInUse(RuntimeError):
    """The socket path is held by a listener that is still accepting (BC-16).

    Not an `OSError`: a caller that reads every `OSError` as "the port is
    taken" must not report a held socket as a held port.
    """


class ClaimFailed(RuntimeError):
    """The claim could not be taken at all (D72): the socket dir could not be
    made, or the lock file opened or locked for a reason other than another
    holder (`ENOLCK`, `EACCES`, …). Nobody holds the path; this host cannot
    lock it. Not an `OSError`, for `SocketInUse`'s reason: it is not a port.
    """


def _claim_failed(what: Path, error: OSError) -> ClaimFailed:
    return ClaimFailed(f"cannot claim {what}: {error.strerror or error}")


@contextmanager
def _umask(mode: int) -> Iterator[None]:
    """Set the umask for exactly one bind, then put it back.

    `umask` is process-global: leaving it set would change the mode of every
    file the process creates afterwards. Serialised, because `controld` binds
    two listeners on two threads (D68): two interleaved save/set/restore pairs
    would restore the socket's umask, not the process's.
    """
    with _UMASK_GUARD:
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


def owned_inode(path: Path) -> int:
    """The inode an owner bound at `path`, read right after its bind."""
    return os.stat(path).st_ino


def unlink_owned_socket(path: Path, inode: int) -> None:
    """Unlink `path` only if it is still the socket this owner bound.

    A newer owner may have replaced the path since the bind (a stale-reclaim
    after this owner stopped accepting); its socket is not ours to remove.
    """
    try:
        current = os.stat(path).st_ino
    except FileNotFoundError:
        return
    if current == inode:
        unlink_socket(path)


def _is_live(path: Path) -> bool:
    """Whether a listener accepts on `path` — connect, then close unread.

    Only a refusal or an absence proves nobody is serving it. Any other error
    (a probe that timed out, would block, …) met a listener that may be busy,
    so the path is treated as held: a false refusal is a retry, a false
    "stale" is the theft BC-16 refuses. Limit: a macOS listener whose backlog
    is full also answers `ECONNREFUSED`, which no probe can tell apart.
    """
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(CLAIM_PROBE_TIMEOUT_S)
    try:
        probe.connect(str(path))
    except (ConnectionRefusedError, FileNotFoundError):
        return False
    except OSError:
        return True
    finally:
        probe.close()
    return True


def _held_elsewhere(path: Path) -> SocketInUse:
    return SocketInUse(f"{path} is held by a running process")


def _take_lock(path: Path) -> bool:
    """Lock `<path>.lock` for this process; whether this call newly took it.

    `os.open` descriptors are non-inheritable, so a child the daemon spawns
    never keeps its lock alive after the daemon exits.
    """
    lock = path.with_name(path.name + LOCK_SUFFIX)
    with _HELD_GUARD:
        if path in _HELD:
            return False
        try:
            fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as error:
            raise _claim_failed(lock, error) from error
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:  # only a lock another holder has is "in use"
            os.close(fd)
            raise _held_elsewhere(path) from None
        except OSError as error:
            os.close(fd)
            raise _claim_failed(lock, error) from error
        except BaseException:
            os.close(fd)
            raise
        _HELD[path] = fd
        return True


def release_claim(path: Path) -> None:
    """Give up this process's claim on `path`; one it does not hold is a no-op.

    The lock file stays (see `LOCK_SUFFIX`)."""
    with _HELD_GUARD:
        fd = _HELD.pop(path, None)
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)  # closing drops the lock even if the unlock raised


def claim_socket(plan: SocketPlan) -> SocketPlan:
    """`plan`, if its path is free or stale; `SocketInUse` if a live process
    holds it; `ClaimFailed` if the dir or the lock cannot be had at all.
    Unlinking a stale file is safe; unlinking a live one is theft.

    The order is ADR-QR-2's: make the socket dir at `plan.dir_mode` (the first
    `controld` start claims before anything else has made it) → take the lock,
    unless this process already holds it → probe, on **every** claim. A claim
    the probe refuses gives back a lock it newly took, and leaves a re-entrant
    holder's lock alone: that owner is still serving.
    """
    try:
        plan.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(plan.path.parent, plan.dir_mode)
    except OSError as error:
        raise _claim_failed(plan.path.parent, error) from error
    newly_locked = _take_lock(plan.path)
    if plan.path.exists() and _is_live(plan.path):
        if newly_locked:
            release_claim(plan.path)
        raise _held_elsewhere(plan.path)
    return plan


def bind_listener(plan: SocketPlan, backlog: int = LISTEN_BACKLOG) -> socket.socket:
    """A listening socket at `plan.path`, at `plan.sock_mode`, in a directory at
    `plan.dir_mode`. Shared by both listeners so the two sockets in M1 cannot
    drift apart in the one property an attacker cares about. The directory is
    `claim_socket`'s to make, so a dir that cannot be had is `ClaimFailed`."""
    claim_socket(plan)
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
    start binds instead of failing with `EADDRINUSE`, and only then releases
    the claim (D72), so no second owner can bind before the unlink.
    """
    listener = bind_listener(plan)
    inode = owned_inode(plan.path)
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
        try:
            unlink_owned_socket(plan.path, inode)
        finally:
            release_claim(plan.path)
