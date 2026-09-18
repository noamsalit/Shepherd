"""T8: the hook entry — one command, from one definition site, or a refusal.

Every assertion here is about a *string*: what `build_hook_entry` packages for a
settings file. The command's text is `host/`'s (P20, E34); this module's job is
to quote the socket path into it, refuse an unusable path, and be byte-stable so
the same dispatcher in two scopes deduplicates (E17,
data-schemas §"User-scope hooks with `_shepherd_managed`").
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import (
    HOOK_ENTRY_TIMEOUT_S,
    HookEntry,
    build_hook_entry,
)
from shepherd.host.base import HookDispatchPlan, SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, LinuxHost

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "shepherd"
    / "engines"
    / "claude_code"
    / "hookd_command.py"
)


def socket_plan(path: Path, budget: int = LINUX_SOCKET_PATH_BUDGET) -> SocketPlan:
    return SocketPlan(path=path, dir_mode=0o700, sock_mode=0o600, socket_path_budget=budget)


def host_dispatch(plan: SocketPlan) -> HookDispatchPlan:
    """The real seam, so no test here ever spells the command itself (P20)."""
    return LinuxHost().hook_dispatch(plan)


def test_command_is_byte_stable() -> None:
    plan = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    first = build_hook_entry(plan, host_dispatch(plan))
    second = build_hook_entry(plan, host_dispatch(plan))
    assert first.available is True
    assert first.command == second.command
    assert first == second
    assert first.timeout_s == HOOK_ENTRY_TIMEOUT_S
    # E18: explicit, because the default is 600 s of blocking.
    assert HOOK_ENTRY_TIMEOUT_S == 5
    assert 0 < HOOK_ENTRY_TIMEOUT_S < 600


def test_command_comes_from_the_host_seam() -> None:
    """AST: this module constructs no dispatch literal of its own (P20, E34)."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert literals, "the module was read, and it does have code literals"
    for literal in literals:
        for marker in ("nc", "-q0", "timeout 0.25"):
            assert marker not in literal, f"{literal!r} respells the dispatch command"

    # …and the command it returns really is the host's, unchanged.
    plan = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    dispatch = host_dispatch(plan)
    assert build_hook_entry(plan, dispatch).command == dispatch.command


def test_command_quotes_socket_path() -> None:
    """A path a shell would split is quoted; an ordinary one is untouched (E17)."""
    ordinary = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    assert build_hook_entry(ordinary, host_dispatch(ordinary)).command.endswith("|| true")

    awkward = socket_plan(Path("/tmp/shepherd probe/sessiond.sock"))
    entry = build_hook_entry(awkward, host_dispatch(awkward))
    assert entry.available is True
    assert "'/tmp/shepherd probe/sessiond.sock'" in entry.command
    # The path appears exactly once, quoted — nothing else was rewritten.
    assert entry.command.count("/tmp/shepherd probe/sessiond.sock") == 1


def test_command_refuses_path_over_budget() -> None:
    """E19: 107 bytes bind on Linux, 108 do not — so 108 never reaches a file."""
    too_long = Path("/run/user/0/shepherd") / ("x" * 90) / "sessiond.sock"
    plan = socket_plan(too_long)
    assert len(str(too_long).encode("utf-8")) > LINUX_SOCKET_PATH_BUDGET
    entry = build_hook_entry(plan, host_dispatch(plan))
    assert entry.available is False
    assert entry.command == ""
    assert str(LINUX_SOCKET_PATH_BUDGET) in entry.reason
    assert entry.reason != ""


def test_preflight_reports_missing_binary() -> None:
    """G2: the binary is absent ⇒ a refusal with a reason, never a silent hook."""
    plan = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    unavailable = HookDispatchPlan(
        command="",
        requires=("timeout", "netcat"),
        available=False,
        reason="missing on this host: netcat",
    )
    entry = build_hook_entry(plan, unavailable)
    assert entry.available is False
    assert entry.command == ""
    assert entry.reason == unavailable.reason


def test_preflight_refuses_a_command_that_does_not_name_the_socket() -> None:
    """A dispatch command that lost the path would install a hook writing nowhere."""
    plan = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    detached = HookDispatchPlan(
        command="true || true",
        requires=("timeout",),
        available=True,
        reason="a command that names no socket",
    )
    entry = build_hook_entry(plan, detached)
    assert entry.available is False
    assert entry.command == ""


def test_hook_entry_is_frozen() -> None:
    plan = socket_plan(Path("/run/user/0/shepherd/sessiond.sock"))
    entry = build_hook_entry(plan, host_dispatch(plan))
    assert isinstance(entry, HookEntry)
    with pytest.raises(AttributeError):
        entry.command = "x"  # type: ignore[misc]
