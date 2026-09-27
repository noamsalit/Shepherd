#!/usr/bin/env python3
"""The `needs_real_home` launcher (env-plan §1 Difference 2 and 6; test-plan Difference 6, 11).

Under `LIVE_AUTH_MODE = needs_real_home` the engine must run with the user's
real `HOME` to find its login, but `MacHost` derives Shepherd's `data_dir` from
`HOME`, so the console script with a real `HOME` would write into the user's
real Shepherd database. This launcher is the same composition as
`shepherd.daemons.controld.main` with one difference: the host is injected,
`MacHost(environ={"HOME": <sandbox home>, "TMPDIR": <sandbox tmp>})`, and
`engine_config_dir=<sandbox cfg>` keeps discovery off the user's real sessions.

It prints the product's own start line, installs the product's own SIGTERM
handler, and prints the product's own `controld stopped:` line from
`controld.stop`'s outcome — so readiness and the stop-line oracle are the same
as for a SUB instance. The console script itself is covered by every SUB run.

    .venv/bin/python tests/qa6/launch_controld.py --port 0 --shepherd-home H \\
        --shepherd-tmpdir T --discovery-config-dir CFG
"""

from __future__ import annotations

import argparse
import errno
import sys
from collections.abc import Sequence
from pathlib import Path

from shepherd.daemons import controld
from shepherd.daemons.control_ingest import ClaimFailed, SocketInUse
from shepherd.daemons.sessiond import install_shutdown_handlers
from shepherd.host.base import SocketPathTooLong
from shepherd.host.mac import MacHost
from shepherd.web.server import LOOPBACK_HOST


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qa6-launch-controld")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--shepherd-home", type=Path, required=True)
    parser.add_argument("--shepherd-tmpdir", type=Path, required=True)
    parser.add_argument("--discovery-config-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.port == 8787:  # R1: the user's daemon; mirrors paths.FORBIDDEN_PORT without importing the harness
        sys.stdout.write("qa6 launcher refuses port 8787 (R1)\n")
        return 2
    host = MacHost(environ={"HOME": str(args.shepherd_home), "TMPDIR": str(args.shepherd_tmpdir)})
    try:
        running = controld.start(host, args.port, args.discovery_config_dir)
    except (SocketPathTooLong, SocketInUse, ClaimFailed) as refused:  # D72: a held or unclaimable socket is not a port
        sys.stdout.write(f"controld refuses to start: {refused}\n")
        return controld.EXIT_REFUSED
    except OSError as refused:
        # Only EADDRINUSE is a port that "is not available" (hunter L4); any other OSError is named as itself.
        if refused.errno == errno.EADDRINUSE:
            sys.stdout.write(f"controld refuses to start: port {args.port} is not available ({refused})\n")
        else:
            sys.stdout.write(f"controld refuses to start: {type(refused).__name__}: {refused}\n")
        return controld.EXIT_REFUSED
    sys.stdout.write(f"controld: http://{LOOPBACK_HOST}:{running.port} · {running.control_socket_path}\n")
    sys.stdout.flush()
    install_shutdown_handlers(running.shutdown)
    running.shutdown.wait()
    sys.stdout.write(f"controld stopped: {controld.stop(running)}\n")
    sys.stdout.flush()
    return controld.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
