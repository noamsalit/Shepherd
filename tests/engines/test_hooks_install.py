"""T9: install, uninstall and inspect — in a throwaway directory, always.

**K3 is the first rule of this file.** No test here names the real
`~/.claude/settings.json`; the settings path is a parameter and every value it
takes is under `tmp_path`. `test_real_user_settings_untouched` proves that
mechanically rather than by inspection, using the session guard in
`tests/conftest.py`.

The shapes asserted are the captured ones (data-schemas §"Hooks config schema"):
`hooks` is an object keyed by event name; each event maps to an array of matcher
groups; each group carries `hooks: [{type, command, timeout}]`; an extra key such
as `_shepherd_managed` is accepted silently. C6/E16 is why install backs up
first and validates after — one malformed `PreToolUse` or `PermissionRequest`
entry disables *every* hook in the file, including ours.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from shepherd.engines.claude_code.events import ALL_HOOK_EVENT_NAMES, SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hooks_config import (
    MANAGED_MARKER,
    HookInspection,
    InstallResult,
    install_hooks,
    inspect_hooks,
    uninstall_hooks,
)
from shepherd.engines.claude_code.hookd_command import (
    HOOK_ENTRY_TIMEOUT_S,
    HookEntry,
    build_hook_entry,
)
from shepherd.host.base import HookDispatchPlan, SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, LinuxHost
from shepherd.host.mac import MacHost

#: A user's own hook, in the captured shape. It must survive us, byte for byte.
FOREIGN_SETTINGS: dict[str, object] = {
    "model": "claude-haiku-4-5-20251001",
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "/usr/local/bin/audit.sh", "timeout": 15}],
            }
        ]
    },
}


def write_settings(path: Path, settings: object) -> bytes:
    payload = (json.dumps(settings, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return payload


def linux_entry(socket_path: Path) -> HookEntry:
    plan = SocketPlan(
        path=socket_path,
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )
    return build_hook_entry(plan, LinuxHost().hook_dispatch(plan))


@pytest.fixture
def entry() -> HookEntry:
    built = linux_entry(Path("/run/user/0/shepherd/sessiond.sock"))
    if not built.available:
        pytest.skip(f"no dispatcher on this host: {built.reason}")
    return built


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    write_settings(path, FOREIGN_SETTINGS)
    return path


def loaded(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def hooks_of(path: Path) -> dict[str, object]:
    value = loaded(path)["hooks"]
    assert isinstance(value, dict)
    return value


def groups_for(path: Path, event: str) -> list[dict[str, object]]:
    value = hooks_of(path)[event]
    assert isinstance(value, list)
    return [group for group in value if isinstance(group, dict)]


def managed_groups(path: Path, event: str) -> list[dict[str, object]]:
    return [group for group in groups_for(path, event) if group.get(MANAGED_MARKER) is True]


# --------------------------------------------------------------------------
# K3 — the guarantee that outranks every other assertion in this file.
# --------------------------------------------------------------------------


def test_real_user_settings_untouched(
    real_user_settings: Any,
    settings_observer: Callable[[Path], Any],
    settings_path: Path,
    entry: HookEntry,
) -> None:
    """P13: install for real, into a throwaway file, and the pre-image holds.

    The session fixture asserts the same thing again when the suite ends; this
    test asserts it *after a real install*, which is the moment it could break.
    """
    install_hooks(settings_path, entry)
    uninstall_hooks(settings_path)
    assert settings_observer(real_user_settings.path.parent) == real_user_settings
    # The paths this file touches are all throwaway, by construction.
    assert real_user_settings.path != settings_path


def test_the_guard_notices_a_change(
    settings_observer: Callable[[Path], Any], tmp_path: Path, entry: HookEntry
) -> None:
    """A guard that cannot fail is not a guard: prove it fires on a stand-in."""
    stand_in = tmp_path / "config"
    stand_in.mkdir()
    absent = settings_observer(stand_in)
    install_hooks(stand_in / "settings.json", entry)
    assert settings_observer(stand_in) != absent


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------


def test_install_backs_up_first(settings_path: Path, entry: HookEntry) -> None:
    pre_image = settings_path.read_bytes()
    result = install_hooks(settings_path, entry)
    assert result.refused_reason is None
    assert result.backup_path.exists()
    assert result.backup_path.read_bytes() == pre_image
    assert settings_path.read_bytes() != pre_image


def test_installed_entries_are_marked(settings_path: Path, entry: HookEntry) -> None:
    install_hooks(settings_path, entry)
    for event in SUBSCRIBED_EVENTS:
        groups = managed_groups(settings_path, event)
        assert len(groups) == 1, event
        entries = groups[0]["hooks"]
        assert isinstance(entries, list) and len(entries) == 1
        assert entries[0][MANAGED_MARKER] is True
        assert entries[0]["type"] == "command"


def test_install_sets_explicit_timeout(settings_path: Path, entry: HookEntry) -> None:
    """E18: the default is 600 s of blocking, so every entry names its own."""
    install_hooks(settings_path, entry)
    for event in SUBSCRIBED_EVENTS:
        entries = managed_groups(settings_path, event)[0]["hooks"]
        assert isinstance(entries, list)
        assert entries[0]["timeout"] == HOOK_ENTRY_TIMEOUT_S
        assert entries[0]["timeout"] != 600


def test_install_is_idempotent(settings_path: Path, entry: HookEntry) -> None:
    """E17: twice ⇒ identical bytes, so two scopes carry one identical command."""
    install_hooks(settings_path, entry)
    once = settings_path.read_bytes()
    result = install_hooks(settings_path, entry)
    assert result.refused_reason is None
    assert settings_path.read_bytes() == once
    assert result.backup_path.read_bytes() == once


def test_installed_command_is_the_host_command_verbatim(
    settings_path: Path, entry: HookEntry
) -> None:
    """P20: no second spelling reaches disk — the host's string, substituted only."""
    dispatch = LinuxHost().hook_dispatch(
        SocketPlan(
            path=Path("/run/user/0/shepherd/sessiond.sock"),
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
        )
    )
    install_hooks(settings_path, entry)
    for event in SUBSCRIBED_EVENTS:
        entries = managed_groups(settings_path, event)[0]["hooks"]
        assert isinstance(entries, list)
        assert entries[0]["command"] == dispatch.command


def test_install_registers_no_worktree_create(settings_path: Path, entry: HookEntry) -> None:
    """data-schemas: any command hook on WorktreeCreate breaks `--worktree`."""
    install_hooks(settings_path, entry)
    assert "WorktreeCreate" in ALL_HOOK_EVENT_NAMES
    assert "WorktreeCreate" not in SUBSCRIBED_EVENTS
    assert "WorktreeCreate" not in hooks_of(settings_path)


def test_install_refuses_without_dispatch_binary(settings_path: Path) -> None:
    """G2, both shapes: a missing binary, and `MacHost`'s unverified flag set."""
    pre_image = settings_path.read_bytes()
    plan = SocketPlan(
        path=Path("/run/user/0/shepherd/sessiond.sock"),
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )
    missing = build_hook_entry(
        plan,
        HookDispatchPlan(
            command="", requires=("timeout", "netcat"), available=False, reason="missing: netcat"
        ),
    )
    result = install_hooks(settings_path, missing)
    assert result.refused_reason is not None
    assert settings_path.read_bytes() == pre_image

    mac_dispatch = MacHost().hook_dispatch(plan)
    assert mac_dispatch.available is False  # unverified off-platform (D55, G1)
    mac_result = install_hooks(settings_path, build_hook_entry(plan, mac_dispatch))
    assert mac_result.refused_reason is not None
    assert settings_path.read_bytes() == pre_image


def test_install_refuses_over_socket_path_budget(settings_path: Path) -> None:
    """E19: a path that cannot bind never reaches a settings file."""
    pre_image = settings_path.read_bytes()
    too_long = Path("/run/user/0/shepherd") / ("x" * 90) / "sessiond.sock"
    over_budget = linux_entry(too_long)
    assert over_budget.available is False
    result = install_hooks(settings_path, over_budget)
    assert result.refused_reason is not None
    assert str(LINUX_SOCKET_PATH_BUDGET) in result.refused_reason
    assert settings_path.read_bytes() == pre_image


def test_install_rolls_back_on_invalid_result(
    settings_path: Path, entry: HookEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C6: validate after writing; a bad result restores the pre-image."""
    from shepherd.engines.claude_code import hooks_config

    pre_image = settings_path.read_bytes()

    def corrupt(path: Path, payload: bytes) -> None:
        path.write_bytes(b"{not json at all")

    monkeypatch.setattr(hooks_config, "write_bytes", corrupt)
    result = install_hooks(settings_path, entry)
    assert result.refused_reason is not None
    assert settings_path.read_bytes() == pre_image


def test_install_detects_pre_existing_breakage(tmp_path: Path, entry: HookEntry) -> None:
    """E16: a foreign malformed PreToolUse entry disables every hook in the file."""
    path = tmp_path / "settings.json"
    write_settings(
        path,
        {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command"}]}]}},
    )
    before = inspect_hooks(path)
    assert before.pre_existing_breakage != ()
    assert any("PreToolUse" in message for message in before.pre_existing_breakage)

    result = install_hooks(path, entry)
    assert result.warnings != ()
    assert any("PreToolUse" in warning for warning in result.warnings)


def test_install_refuses_invalid_json_rather_than_clobbering(
    tmp_path: Path, entry: HookEntry
) -> None:
    """Invalid JSON voids the whole file (E16) — but it is still the user's."""
    path = tmp_path / "settings.json"
    path.write_bytes(b"{ this is not json")
    result = install_hooks(path, entry)
    assert result.refused_reason is not None
    assert path.read_bytes() == b"{ this is not json"


def test_dry_run_writes_nothing(settings_path: Path, entry: HookEntry) -> None:
    pre_image = settings_path.read_bytes()
    result = install_hooks(settings_path, entry, dry_run=True)
    assert result.refused_reason is None
    assert result.events_installed == len(SUBSCRIBED_EVENTS)
    assert settings_path.read_bytes() == pre_image
    assert not result.backup_path.exists() or result.backup_path == settings_path


# --------------------------------------------------------------------------
# Uninstall and inspect
# --------------------------------------------------------------------------


def test_uninstall_leaves_foreign_hooks(settings_path: Path, entry: HookEntry) -> None:
    install_hooks(settings_path, entry)
    result = uninstall_hooks(settings_path)
    assert result.refused_reason is None
    assert loaded(settings_path) == FOREIGN_SETTINGS


def test_uninstall_is_idempotent(settings_path: Path, entry: HookEntry) -> None:
    install_hooks(settings_path, entry)
    uninstall_hooks(settings_path)
    once = settings_path.read_bytes()
    result = uninstall_hooks(settings_path)
    assert result.refused_reason is None
    assert settings_path.read_bytes() == once


def test_inspect_counts_ours_and_theirs(settings_path: Path, entry: HookEntry) -> None:
    before = inspect_hooks(settings_path, entry)
    assert before == HookInspection(
        installed=False,
        managed_entries=0,
        foreign_entries=1,
        pre_existing_breakage=(),
        command_matches_current_host=False,
    )
    install_hooks(settings_path, entry)
    after = inspect_hooks(settings_path, entry)
    assert after.installed is True
    assert after.managed_entries == len(SUBSCRIBED_EVENTS)
    assert after.foreign_entries == 1
    assert after.command_matches_current_host is True

    stale = HookEntry(
        command="true", timeout_s=entry.timeout_s, available=True, reason=entry.reason
    )
    assert inspect_hooks(settings_path, stale).command_matches_current_host is False


def test_install_result_names_the_file_it_touched(settings_path: Path, entry: HookEntry) -> None:
    result = install_hooks(settings_path, entry)
    assert isinstance(result, InstallResult)
    assert result.settings_path == settings_path
    assert result.events_installed == len(SUBSCRIBED_EVENTS)


def test_subscribed_events_are_real_event_names() -> None:
    assert set(SUBSCRIBED_EVENTS) <= set(ALL_HOOK_EVENT_NAMES)
    assert len(set(SUBSCRIBED_EVENTS)) == len(SUBSCRIBED_EVENTS)
    assert len(ALL_HOOK_EVENT_NAMES) == 33
