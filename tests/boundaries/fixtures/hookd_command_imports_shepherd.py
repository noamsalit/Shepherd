"""Builds the hook entry's command string (T8).

NEGATIVE fixture (r6, A4): this module carries a normal module docstring and
imports its own argument types from `shepherd.host`. The rule is a property of
the **emitted command**, not of this module's imports — read the other way it
fires on T8's own prescribed signature and on this very docstring.
"""

from shepherd.host import HookDispatchPlan, SocketPlan


def build_hook_entry(plan: SocketPlan, dispatch: HookDispatchPlan) -> str:
    return f"cat | nc -U -q0 {plan.socket_path}"
