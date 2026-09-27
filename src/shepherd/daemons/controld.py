"""T18: `controld` — the composition root, and the only writer (D37, ADR-1).

Every line is a call into a module tested without a process: no branching logic,
no fold rule, no route, no host branch — ADR-1's 150-line cap is the proxy for
that, and `toolsurface/compose.py` now holds the capabilities this build has and
the ring it publishes them through (T18-3). What is left here is the order, and
ADR-1's cap is kept with a **reserve**, not met exactly: a root sitting on its
cap cannot take its next wiring change additively, and the pressure then lands
on the prose that explains the order.

The order is the contract (D71): claim the sockets, holding the lock for life (D72;
a refusal must cost nothing) → bind HTTP+SSE on loopback (T15, §13), serving nothing
yet, so a busy port refuses before any write → open the store (migrate, one writer
thread) → `compose_tool_surface`, which empties the ring and freezes the registry
**before the server serves** (ADR-7 §4, as amended) → the control-ingest listener
(T10b) and the CLI's owner-only RPC listener (D68), each setting its `bound` once
listening → `run_discovery_loop`, which owns the 2.0 s cadence *and* the liveness
sweep (T7b, A8) → `serve_forever` → on SIGTERM stop the loops, unlink, close the
store. Both lanes return one `FoldResult` shape across one writer (D37). Shutdown's
own logic — what a join that timed out means — is `daemons/shutdown.py`.
"""

from __future__ import annotations

import argparse
import threading
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from shepherd.daemons.control_ingest import ClaimFailed, SocketInUse, claim_socket, serve_control_ingest
from shepherd.daemons.control_rpc import RPC_SOCKET_NAME, serve_control_rpc
from shepherd.daemons.plane import ShutdownOutcome, audit_sink, build_master, shut_down
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME, INGEST_SOCKET_NAME, install_shutdown_handlers
from shepherd.host.base import HostPlatform, SocketPathTooLong
from shepherd.host.detect import detect_host
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import STOP_PREFIX, StopLog
from shepherd.signals.discovery_loop import run_discovery_loop
from shepherd.signals.hook_lane import HookLane
from shepherd.store.db import Store, open_store
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION, MigrationRefused
from shepherd.toolsurface.compose import compose_tool_surface, log_root, publish_result, transcript_root
from shepherd.toolsurface.stream import publish
from shepherd.web import static_root
from shepherd.web.server import LOOPBACK_HOST, create_server

DB_NAME, DEFAULT_PORT, JOIN_TIMEOUT_S = "shepherd.db", 8787, 10.0
BIND_TIMEOUT_S = 10.0  #: `start()` returns only once both sockets are bound (E20's window).
EXIT_OK, EXIT_REFUSED = 0, 2


@dataclass(frozen=True)
class Controld:
    """One running composition, and everything shutdown needs to undo it."""
    store: Store
    server: ThreadingHTTPServer
    port: int
    control_socket_path: Path
    rpc_socket_path: Path
    shutdown: threading.Event
    threads: tuple[threading.Thread, ...]


def start(host: HostPlatform, port: int, engine_config_dir: Path | None = None) -> Controld:
    """Wire everything and return once both sockets are bound.

    The socket plan and the port are validated **first**: `open_store` migrates
    a database in and starts a thread, and a refusal that wrote `shepherd.db` is no refusal.
    """
    plan, rpc = (claim_socket(host.control_socket(name)) for name in (CONTROL_SOCKET_NAME, RPC_SOCKET_NAME))
    ingest, db_path = host.control_socket(INGEST_SOCKET_NAME), host.dirs().data_dir / DB_NAME
    with ExitStack() as undo:  # a refusal past the bind leaves nothing half-started
        server = undo.enter_context(create_server(LOOPBACK_HOST, port, static_root=static_root()))  # binds only
        store = open_store(db_path)
        undo.callback(store.close)
        wiring = compose_tool_surface(store, host, db_path, ingest, build_master, audit_sink(store, host))  # ADR-7
        undo.pop_all()

    shutdown, bound, rpc_bound = threading.Event(), threading.Event(), threading.Event()
    stop_log = StopLog(RotatingJsonlLog(log_root(host), STOP_PREFIX))
    lane = HookLane(store=store, publish=publish, stop_log=stop_log, projects_root=transcript_root(engine_config_dir))
    ingest_args = {"plan": plan, "schema_version": EXPECTED_SCHEMA_VERSION,
                   "on_frame": lane.apply, "shutdown": shutdown, "bound": bound}
    scan_args = {"store": store, "host": host, "on_result": publish_result,
                 "shutdown": shutdown, "engine_config_dir": engine_config_dir, "sweep": wiring.sweep}
    threads = (
        threading.Thread(target=serve_control_ingest, kwargs=ingest_args, name="ingest", daemon=True),
        threading.Thread(target=serve_control_rpc, args=(rpc, shutdown, rpc_bound), name="rpc", daemon=True),  # D68
        threading.Thread(target=run_discovery_loop, kwargs=scan_args, name="scan", daemon=True),
        threading.Thread(target=server.serve_forever, name="http", daemon=True),
    )
    for thread in threads:
        thread.start()
    if not (bound.wait(BIND_TIMEOUT_S) and rpc_bound.wait(BIND_TIMEOUT_S)):
        raise TimeoutError(f"a control socket was never bound: {plan.path}, {rpc.path}")
    return Controld(store, server, int(server.server_address[1]), plan.path, rpc.path, shutdown, threads)


def stop(running: Controld) -> ShutdownOutcome:
    """F15/ADR-7: stop the loops, unlink the sockets, join, close the store."""
    running.shutdown.set()
    running.server.shutdown()
    running.server.server_close()
    return shut_down(running.threads, running.store.close, JOIN_TIMEOUT_S)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shepherd-controld")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--engine-config-dir", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Start, wait for SIGTERM, shut down. The process, in five lines."""
    args = parse_args(argv)
    try:
        running = start(detect_host(), args.port, args.engine_config_dir)
    except (SocketPathTooLong, SocketInUse, ClaimFailed, MigrationRefused) as refused:  # D72: not a port
        print(f"controld refuses to start: {refused}")
        return EXIT_REFUSED
    except OSError as refused:  # a held port is a refusal, like an over-long path
        print(f"controld refuses to start: port {args.port} is not available ({refused})")
        return EXIT_REFUSED
    print(f"controld: http://{LOOPBACK_HOST}:{running.port} · {running.control_socket_path}")
    install_shutdown_handlers(running.shutdown)
    running.shutdown.wait()
    print(f"controld stopped: {stop(running)}")  # principle 5: a hung thread is said
    return EXIT_OK


def run() -> int:
    return main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
