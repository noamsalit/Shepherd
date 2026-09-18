"""Indirection fixture 2 of 3: the binary is assembled at runtime.

`["tm" + "ux", ...]` — two constants, neither equal to the binary's name. The
shape `cli_platform_alias_import.py` ships for D55, one level lower: the value is
right and the spelling is absent.
"""

from __future__ import annotations

import subprocess

PREFIX = "tm"
SUFFIX = "ux"


def argv() -> list[str]:
    return [f"{PREFIX}{SUFFIX}", "-L", "shepherd", "kill-session", "-t", "main"]


def run() -> None:
    subprocess.run(argv(), capture_output=True)
