"""Planted violation: a `-t` that matches by prefix.

`-t shepherd_x` also selects `shepherd_x2`, so the keys land in a session the
caller never named (CLAUDE.md rule 4, A5).
"""

from __future__ import annotations

import subprocess


def argv() -> list[str]:
    return ["tmux", "-L", "shepherd-runner", "send-keys", "-t", "shepherd_x", "hi", "Enter"]


def run() -> None:
    subprocess.run(
        ["tmux", "-L", "shepherd-runner", "send-keys", "-t", "shepherd_x", "hi", "Enter"],
        capture_output=True,
    )
