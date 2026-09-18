"""Planted violation: a server-wide teardown on the product's own socket.

`shepherd-runner` is D49's socket: it carries owned sessions. K6-a permits the
verb only on a throwaway (`^shepherd-m3-`), and this is the argv that rule is
about.
"""

from __future__ import annotations

import subprocess


def argv() -> list[str]:
    return ["tmux", "-L", "shepherd-runner", "kill-server"]


def run() -> None:
    subprocess.run(["tmux", "-L", "shepherd-runner", "kill-server"], capture_output=True)
