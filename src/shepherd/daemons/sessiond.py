"""T10: `sessiond` — the process that must not restart.

A composition root, and nothing else (ADR-1): it asks the host where its two
sockets are, builds a relay, installs the signal handlers, and hands everything
to `serve_ingest`. Every rule it obeys is implemented one layer down, in
`engines/claude_code/`, where it can be tested without a process.

Two facts shape this file:

* **It never touches the database** (D37). `controld` is the only writer, and
  §7 migration rule 3 says `sessiond` never migrates — it waits for `controld`
  to report the schema version over the UDS. So the version it expects arrives
  as an argument (from the unit file that starts it), never from `store`, and
  `tests/daemons/test_sessiond_isolation.py` proves the whole import closure of
  this module cannot reach one.
* **A dead daemon degrades visibility, never agents** (principle 4). A socket
  path that does not fit the platform's budget is a refusal to start with a
  readable reason (E19), not a traceback in a hook's stderr.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from collections.abc import Sequence
from types import FrameType

from shepherd.engines.claude_code.ingest_socket import SHUTDOWN_DRAIN_S, serve_ingest
from shepherd.engines.claude_code.relay import RELAY_BUFFER_MAX, Relay
from shepherd.host.base import SocketPathTooLong
from shepherd.host.detect import detect_host, detect_peercred

#: The two sockets in M1, named at the seam: hooks → `sessiond`, and
#: `sessiond` → `controld`. `controld` creates and owns the second one.
INGEST_SOCKET_NAME = "sessiond"
CONTROL_SOCKET_NAME = "controld"

EXIT_OK = 0
EXIT_REFUSED = 2


def install_shutdown_handlers(shutdown: threading.Event) -> None:
    """`SIGTERM` and `SIGINT` stop the accept loop; the drain and the unlink
    happen on the main thread, where they can take their bounded time (F15)."""

    def request_shutdown(signum: int, frame: FrameType | None) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shepherd-sessiond", description=__doc__)
    parser.add_argument(
        "--expected-schema-version",
        type=int,
        required=True,
        help="the schema version controld must report before any frame is relayed",
    )
    parser.add_argument("--buffer-max", type=int, default=RELAY_BUFFER_MAX)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    host = detect_host()
    try:
        ingest = host.control_socket(INGEST_SOCKET_NAME)
        control = host.control_socket(CONTROL_SOCKET_NAME)
    except SocketPathTooLong as error:
        print(f"sessiond refuses to start: {error}", file=sys.stderr)
        return EXIT_REFUSED

    relay = Relay(control.path, args.buffer_max, args.expected_schema_version)
    shutdown = threading.Event()
    install_shutdown_handlers(shutdown)

    def drain() -> None:
        """The bounded drain window, and what it cost — principle 5: a frame
        that did not make it is a number a human can read, never a silence."""
        stats = relay.close(SHUTDOWN_DRAIN_S)
        print(
            f"sessiond stopped: delivered={stats.delivered} buffered={stats.buffered} "
            f"overflowed={stats.overflowed} schema_mismatch={stats.schema_mismatch}",
            file=sys.stderr,
        )

    serve_ingest(
        plan=ingest,
        on_frame=relay.send,
        on_shutdown=drain,
        shutdown=shutdown,
        # BLOCKER T10, option (c): the platform's peer-credential reader, chosen
        # in `host/` and injected here. `Frame.peer_pid` becomes a pid the kernel
        # recorded at `connect()` (E21) instead of an honest `None` — a second
        # opinion beside the frame's own `CLAUDE_PID`, never a replacement.
        peer_credentials=detect_peercred(),
    )
    return EXIT_OK


def run() -> int:
    """The console entry point's body."""
    return main()


if __name__ == "__main__":  # pragma: no cover - the process entry point
    raise SystemExit(main())
