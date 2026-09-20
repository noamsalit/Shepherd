"""T8: the settings-file entry for the hook dispatcher.

**This module does not author the dispatch command.** `host/` is its one
definition site (P20): the text, its flags and the 250 ms bound are
`HostPlatform.hook_dispatch(plan).command`, measured at 3.2 ms per invocation in
`docs/probes/2026-09-16-hookd-latency.md` Result 1b — and 253.6 ms if a second
copy of it ever loses a flag, while still delivering, which is why there is only
one copy. Revision 2 of the plan carried that second copy; this module exists on
the other side of that lesson and *quotes a path into* the host's string.

Three things it owns:

  * **quoting** — the control socket path is substituted into the host's command
    shell-quoted, so a directory with a space cannot silently split the command;
  * **refusal** — an over-budget path (E19), an unavailable dispatcher (G2), or
    a command that does not name our socket at all, each produce an entry marked
    unavailable *with a reason*. A hook that exits 0 having delivered nothing is
    exactly the failure principle 5 forbids hiding;
  * **byte stability** (E17) — the same inputs give the same string, so the same
    dispatcher registered in user and project scope deduplicates and runs once
    (data-schemas §"User-scope hooks with `_shepherd_managed`").

`timeout_s` is set explicitly because the per-entry default is 600 s of blocking
(E18, C7, data-schemas §"Hook runtime contract").
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from shepherd.host.base import HookDispatchPlan, SocketPlan

#: E18/C7: the per-entry timeout Claude Code applies. Five seconds is three
#: orders of magnitude above the measured 3.2 ms and two below the 600 s
#: default, so a wedged host costs a session five seconds, not ten minutes.
HOOK_ENTRY_TIMEOUT_S = 5


@dataclass(frozen=True)
class HookEntry:
    """What goes into a settings file: one command, one timeout, one verdict."""

    command: str
    timeout_s: int
    available: bool
    reason: str


def _refused(reason: str) -> HookEntry:
    """A refusal carries no command at all, so nothing can install it by mistake."""
    return HookEntry(command="", timeout_s=HOOK_ENTRY_TIMEOUT_S, available=False, reason=reason)


def build_hook_entry(plan: SocketPlan, dispatch: HookDispatchPlan) -> HookEntry:
    """Package the host's dispatch command as a settings entry, or refuse."""
    path = str(plan.path)
    size = len(path.encode("utf-8"))
    if size > plan.socket_path_budget:
        return _refused(
            f"control socket path is {size} bytes, budget is "
            f"{plan.socket_path_budget}: {path}"
        )
    if not dispatch.available:
        return _refused(dispatch.reason)
    if path not in dispatch.command:
        return _refused(
            "the host's dispatch command does not name the control socket path: "
            f"{path}"
        )
    return HookEntry(
        command=dispatch.command.replace(path, shlex.quote(path), 1),
        timeout_s=HOOK_ENTRY_TIMEOUT_S,
        available=True,
        reason=dispatch.reason,
    )
