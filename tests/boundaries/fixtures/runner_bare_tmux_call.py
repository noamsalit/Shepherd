"""Planted violation: a tmux argv with no `-L`, run.

CLAUDE.md rule 3's exact shape. With no socket flag the command resolves against
the inherited `$TMUX`, so a caller running inside one of the user's panes reaches
the user's server — which is 2026-09-12's blast radius.
"""

from __future__ import annotations

import subprocess


def argv() -> list[str]:
    return ["tmux", "list-sessions"]


def run() -> None:
    subprocess.run(["tmux", "list-sessions"], capture_output=True)
