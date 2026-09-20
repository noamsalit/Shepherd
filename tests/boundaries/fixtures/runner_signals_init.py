"""Planted violation, frozen as a fixture: a signal delivered to init.

This is the shape the M3 verifier planted into `runner/local.py` on 2026-09-17
to prove P-M3-7's lint catches it. The lint does catch it — but the verifier
planted it into the *shadow tree's live source*, the suite imported and ran
`interrupt()` before the lint test was reached, and `SIGINT` to pid 1 is how the
kernel spells Ctrl+Alt+Del. The host rebooted: 66 days of uptime and three live
Remote Control sessions, gone.

The rule this fixture exists to enforce: **a planted violation lives here, inert,
and is read by the AST scanner — it is never written into a module the suite
imports.** `runner_kill_server.py` established the pattern after the equivalent
tmux incident; this is the same lesson one layer down, from signals to pids.

`tests/conftest.py` carries the runtime half of the net, because a static scan
cannot protect against code it has not scanned yet.

Never imported by the product.
"""

from __future__ import annotations

import os
import signal

INIT = 1


def go() -> None:
    """The planted line verbatim. Inert: nothing imports this module."""
    os.kill(INIT, signal.SIGINT)
