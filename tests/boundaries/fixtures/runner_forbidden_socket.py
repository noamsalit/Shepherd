"""Planted violation, frozen as a fixture: an argv that names the user's socket.

P-M3-15's positive control. `test_no_tmux_call_in_the_tree_can_reach_the_users_socket`
asserted `offenders == []` over the tree and had no fixture the scan was proved
to *catch*, so "no file names the user's socket" and "the scan cannot see a file
that names the user's socket" were indistinguishable — the absence-without-
arrival shape this milestone keeps finding.

**Inert by construction.** There is no `subprocess` import, no `run()`, and
nothing here ever starts a process: the argv is a list of strings, read by the
AST scanner and handed to `check_tmux_argv`, which refuses it. The 2026-09-17
rule in CLAUDE.md is why the file is shaped this way — a planted violation is a
fixture that nothing executes, not a line in a module the suite imports.

Never imported by the product.
"""

from __future__ import annotations

#: The one socket that is never permitted, by any configuration, for any verb.
USERS_SOCKET = "shepherd"


def argv() -> list[str]:
    return ["tmux", "-L", USERS_SOCKET, "list-sessions"]
