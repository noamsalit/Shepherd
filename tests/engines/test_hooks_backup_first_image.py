"""qa6 BC-20 (ruling 7): `.shepherd-backup` holds the FIRST pre-install image, forever.

Seam: `install_hooks` / `uninstall_hooks` over `tmp_path` (K3): the real
`~/.claude/settings.json` is never named here, and `tests/conftest.py`'s session
guard watches it regardless.

The backup is written once, from the first image the product ever saw, and no
later install or uninstall replaces it (PP6). A backup the user already had is
theirs and is kept too. Uninstall removes exactly our entries and restores no
bytes: a byte restore would throw away the user's edits made since the install
(the rejected alternative in the rulings record).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.engines.claude_code.hooks_config import (
    BACKUP_SUFFIX,
    install_hooks,
    uninstall_hooks,
)
from shepherd.host.base import SocketPlan
from shepherd.host.detect import detect_host

#: Non-canonical on purpose (4-space indent, unsorted keys), so a byte restore
#: and a re-serialisation are distinguishable.
FIRST_IMAGE = b'{\n    "zeta": 1,\n    "model": "opus",\n    "alpha": {\n        "b": 2,\n        "a": 1\n    }\n}\n'
FIRST_SETTINGS: dict[str, object] = {"zeta": 1, "model": "opus", "alpha": {"b": 2, "a": 1}}

#: A backup the user made themselves, before Shepherd ever ran.
USERS_OWN_BACKUP = b'{"mine": "do not clobber"}\n'

INSTALL_UNINSTALL_ROUNDS = 4


@pytest.fixture
def entry() -> HookEntry:
    """An installable entry for *this* host, as `test_hooks_install.py` builds one."""
    host = detect_host()
    plan = SocketPlan(
        path=Path("/run/user/0/shepherd/sessiond.sock"),
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=host.control_socket("sessiond").socket_path_budget,
    )
    built = build_hook_entry(plan, host.hook_dispatch(plan))
    if not built.available:
        pytest.skip(f"no dispatcher on this host: {built.reason}")
    return built


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    path.write_bytes(FIRST_IMAGE)
    return path


def backup_of(settings_path: Path) -> Path:
    return settings_path.with_name(settings_path.name + BACKUP_SUFFIX)


def loaded(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return {str(key): item for key, item in value.items()}


def test_a_second_install_keeps_the_first_pre_install_image(
    settings_path: Path, entry: HookEntry
) -> None:
    first = install_hooks(settings_path, entry)
    second = install_hooks(settings_path, entry)

    assert first.refused_reason is None
    assert second.refused_reason is None
    assert backup_of(settings_path).read_bytes() == FIRST_IMAGE
    assert second.backup_path == backup_of(settings_path)


def test_uninstall_never_overwrites_the_backup(settings_path: Path, entry: HookEntry) -> None:
    install_hooks(settings_path, entry)
    result = uninstall_hooks(settings_path)

    assert result.refused_reason is None
    assert result.events_installed > 0
    assert backup_of(settings_path).read_bytes() == FIRST_IMAGE


def test_a_backup_that_exists_before_the_first_install_is_kept(
    settings_path: Path, entry: HookEntry
) -> None:
    backup_of(settings_path).write_bytes(USERS_OWN_BACKUP)

    install_hooks(settings_path, entry)
    uninstall_hooks(settings_path)

    assert backup_of(settings_path).read_bytes() == USERS_OWN_BACKUP


def test_uninstall_removes_only_our_entries_and_restores_no_bytes(
    settings_path: Path, entry: HookEntry
) -> None:
    install_hooks(settings_path, entry)
    edited = loaded(settings_path)
    edited["edited_after_install"] = True
    settings_path.write_text(json.dumps(edited, indent=2) + "\n", encoding="utf-8")

    result = uninstall_hooks(settings_path)

    assert result.refused_reason is None
    assert loaded(settings_path) == {**FIRST_SETTINGS, "edited_after_install": True}
    assert settings_path.read_bytes() != FIRST_IMAGE
    assert backup_of(settings_path).read_bytes() == FIRST_IMAGE


def test_the_backup_equals_the_first_image_over_many_installs_and_uninstalls(
    settings_path: Path, entry: HookEntry
) -> None:
    """PP6: N rounds of install then uninstall, and the backup never moves."""
    for _ in range(INSTALL_UNINSTALL_ROUNDS):
        assert install_hooks(settings_path, entry).refused_reason is None
        assert backup_of(settings_path).read_bytes() == FIRST_IMAGE
        assert uninstall_hooks(settings_path).refused_reason is None
        assert backup_of(settings_path).read_bytes() == FIRST_IMAGE
    assert loaded(settings_path) == FIRST_SETTINGS
