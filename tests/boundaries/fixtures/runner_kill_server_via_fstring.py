"""Indirection fixture 3 of 3: the verb is assembled at runtime.

`f"kill-{verb}"` — the argv reads `kill-server` and the file contains no constant
that does. The socket is the product's own (D49), which is exactly where the verb
is forbidden: a teardown here ends every owned session at once.

The shape `cli_platform_module_alias.py` ships for D55.
"""

from __future__ import annotations

import subprocess

SCOPE = "server"


def argv() -> list[str]:
    return ["tmux", "-L", "shepherd-runner", f"kill-{SCOPE}"]


def run() -> None:
    subprocess.run(argv(), capture_output=True)
