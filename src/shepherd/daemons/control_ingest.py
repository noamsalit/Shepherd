"""T10b: `controld`'s ingest listener — the server half of the hop.

A composition root (ADR-1): it wires `bind_listener`, `read_lines` and the
`relay_wire` codec together and holds no logic of its own. `controld` creates
and owns this socket, under the same rules as the ingest socket — umask before
bind, unlink stale, unlink on exit (E20, F15) — and greets every connection
with the schema version it was started with, because §7 migration rule 3 says
`sessiond` waits for that line before it relays anything.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

from shepherd.core.frames import Frame
from shepherd.engines.claude_code.ingest_socket import (
    accept_next,
    bind_listener,
    read_lines,
    unlink_socket,
)
from shepherd.engines.claude_code.relay_wire import (
    Hello,
    WireError,
    decode_frame,
    encode_hello,
)
from shepherd.host.base import SocketPlan

__all__ = ["serve_control_ingest"]


def serve_control_ingest(
    plan: SocketPlan,
    schema_version: int,
    on_frame: Callable[[Frame], None],
    shutdown: threading.Event,
    bound: threading.Event | None = None,
) -> None:
    """`bound` is set the moment the socket is listening, so a caller on another
    thread can wait for the bind instead of polling the path for it to appear
    (T18-3: the composition root asks the binder, rather than implementing a
    readiness loop of its own). Defaulted, so every existing call site is
    unchanged."""
    listener = bind_listener(plan)
    if bound is not None:
        bound.set()
    try:
        while not shutdown.is_set():
            conn = accept_next(listener)
            if conn is None:
                continue
            with conn:
                conn.sendall(encode_hello(Hello(schema_version=schema_version, pid=os.getpid())))
                try:
                    for line in read_lines(conn, shutdown):
                        on_frame(decode_frame(line))
                except (WireError, OSError):
                    # A peer that cannot speak the wire loses its connection,
                    # not the daemon: it reconnects and its buffer is intact.
                    continue
    finally:
        listener.close()
        unlink_socket(plan.path)
