"""Indirection fixture 1 of 3: the binary arrives as an imported constant.

This is the one the M3 reviews called out by name — `from .tmux_cmd import
TMUX_BIN` — and it is the worst of the three, because the argv it produces has
**no `-L`** at all. There is no string constant equal to the binary's name
anywhere in this file, so no literal-matching rule can see it; the interpreter
can, and so can `check_tmux_argv`, because by then the argv is a list of strings.

It is the shape `cli_platform_from_import.py` already ships for D55: an import
that leaves no dotted chain behind.
"""

from __future__ import annotations

import subprocess

from shepherd.runner.tmux_cmd import VERSION_ARGV

BINARY = VERSION_ARGV[0]


def argv() -> list[str]:
    return [BINARY, "list-sessions"]


def run() -> None:
    subprocess.run(argv(), capture_output=True)
