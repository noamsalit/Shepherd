"""MUT-G4, frozen as a fixture: the teardown reached by a **prefix**.

This is the shape the M3 verifier planted into `runner/local.py` and watched
survive all 1 470 default tests: a new `LocalRunner` method that spells no
`kill-server` and no `tmux`, hands one word to the product's own argv builder,
and destroys `shepherd-runner` — every owned session at once.

tmux resolves an unambiguous command-name prefix. Measured on this host
(tmux 3.4, socket `shepherd-m3-verify`, torn down): `kill-serv` returns `rc=0`
and `ls` then reports no server running.

Never imported by the product. `argv()` exists so the runtime net can be handed
the list the interpreter really built, the way every other fixture here does.
"""

from __future__ import annotations

from shepherd.runner.tmux_cmd import DEFAULT_SOCKET, tmux_argv

PREFIX = "kill-serv"


def argv() -> list[str]:
    return tmux_argv(DEFAULT_SOCKET, PREFIX)


def reset_all(run: object) -> list[str]:
    """The MUT-G4 method verbatim: one word, through the product's builder."""
    return tmux_argv(DEFAULT_SOCKET, "kill-serve")
