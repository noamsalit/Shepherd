"""D68 / ADR-QR-1: `controld`'s RPC listener — the CLI's owner-only door.

A composition root (ADR-1): it wires `bind_listener`, `read_to_eof` and
`toolsurface.rpc.answer_request` together and holds no logic of its own. The
wire, its validation and the forced `HUMAN` audience are all `answer_request`'s;
this module only moves bytes. The socket lives under the same rules as the
other two — umask before bind (0600 in a 0700 dir), unlink stale, unlink on
exit (E20, F15), hold the claim's lock until the listener returns (D72).

One connection at a time: one request is read to EOF (1 s idle bound), one
reply is written, and the connection is closed. A peer that hangs up early
loses its connection, never the daemon.
"""

from __future__ import annotations

import threading

from shepherd.engines.claude_code.ingest_socket import (
    accept_next,
    bind_listener,
    owned_inode,
    read_to_eof,
    release_claim,
    unlink_owned_socket,
)
from shepherd.host.base import SocketPlan
from shepherd.toolsurface.rpc import RPC_SOCKET_NAME, answer_request

__all__ = ["RPC_SOCKET_NAME", "BindFailed", "serve_control_rpc"]


class BindFailed(RuntimeError):
    """A listener thread never reported its socket bound (qa6 P10 REM-FIX M-3).

    Deliberately no `OSError`: `controld.main` reads an `OSError` out of `start`
    as a busy port, and a socket that never bound is not one."""


def serve_control_rpc(
    plan: SocketPlan,
    shutdown: threading.Event,
    bound: threading.Event | None = None,
) -> None:
    """Serve until `shutdown` is set. `bound` is set once the socket listens,
    for `serve_control_ingest`'s reason: the root waits on the binder rather
    than polling the path."""
    listener = bind_listener(plan)
    inode = owned_inode(plan.path)
    if bound is not None:
        bound.set()
    try:
        while not shutdown.is_set():
            conn = accept_next(listener)
            if conn is None:
                continue
            with conn:
                try:
                    conn.sendall(answer_request(read_to_eof(conn)))
                except OSError:
                    # A probe, or a client that left before its reply. Nothing
                    # else can escape: `answer_request` is total (REM-FIX H-1).
                    continue
    finally:
        listener.close()
        try:
            unlink_owned_socket(plan.path, inode)
        finally:
            release_claim(plan.path)  # after the unlink, so nobody binds before it (D72)
