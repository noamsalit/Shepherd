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

import errno
import json
from pathlib import Path
from types import TracebackType
from typing import IO, Callable, cast

import pytest

from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.engines.claude_code.hooks_config import (
    BACKUP_SUFFIX,
    MANAGED_MARKER,
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
    assert first.warnings == ()
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

    installed = install_hooks(settings_path, entry)
    uninstalled = uninstall_hooks(settings_path)

    assert installed.refused_reason is None
    assert uninstalled.refused_reason is None
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


# --------------------------------------------------------------------------
# REM-FIX 1: uninstall never creates the backup; a failed write leaves none;
# only a regular file counts as a backup; a kept backup that is not this run's
# pre-image is said so.
# --------------------------------------------------------------------------


def warnings_naming(path: Path, warnings: tuple[str, ...]) -> list[str]:
    return [warning for warning in warnings if str(path) in warning]


def test_uninstall_after_an_install_into_a_missing_file_writes_no_backup(
    tmp_path: Path, entry: HookEntry
) -> None:
    """Uninstall's pre-image always holds our entries, so it is never worth backing up."""
    settings_path = tmp_path / "settings.json"

    installed = install_hooks(settings_path, entry)
    uninstalled = uninstall_hooks(settings_path)

    assert installed.refused_reason is None
    assert uninstalled.refused_reason is None
    assert uninstalled.events_installed > 0
    assert not backup_of(settings_path).exists()
    assert not backup_of(settings_path).is_symlink()
    assert uninstalled.backup_path == settings_path


def test_uninstall_reports_the_backup_the_install_wrote(settings_path: Path, entry: HookEntry) -> None:
    install_hooks(settings_path, entry)
    result = uninstall_hooks(settings_path)

    assert result.refused_reason is None
    assert result.backup_path == backup_of(settings_path)


class FailingWrite:
    """A backup handle that lands a few bytes and then runs out of disk."""

    def __init__(self, handle: IO[bytes]) -> None:
        self.handle = handle

    def __enter__(self) -> FailingWrite:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.handle.close()

    def write(self, payload: bytes) -> int:
        self.handle.write(payload[:5])
        raise OSError(errno.ENOSPC, "No space left on device")

    def close(self) -> None:
        self.handle.close()


def test_a_failed_backup_write_leaves_no_backup_and_the_next_install_writes_one(
    settings_path: Path, entry: HookEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open: Callable[..., object] = Path.open

    def open_with_a_full_disk(self: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        handle = real_open(self, mode, *args, **kwargs)
        if self.name.endswith(BACKUP_SUFFIX) and any(flag in mode for flag in "wxa"):
            return FailingWrite(cast(IO[bytes], handle))
        return handle

    monkeypatch.setattr(Path, "open", open_with_a_full_disk)
    with pytest.raises(OSError):
        install_hooks(settings_path, entry)
    monkeypatch.undo()

    assert not backup_of(settings_path).exists()
    assert settings_path.read_bytes() == FIRST_IMAGE
    result = install_hooks(settings_path, entry)
    assert result.refused_reason is None
    assert backup_of(settings_path).read_bytes() == FIRST_IMAGE


def plant_directory(backup: Path, tmp_path: Path) -> None:
    backup.mkdir()


def plant_dangling_symlink(backup: Path, tmp_path: Path) -> None:
    backup.symlink_to(tmp_path / "nowhere")


def plant_symlink_to_a_file(backup: Path, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_bytes(FIRST_IMAGE)
    backup.symlink_to(target)


@pytest.mark.parametrize(
    "plant",
    [plant_directory, plant_dangling_symlink, plant_symlink_to_a_file],
    ids=["directory", "dangling_symlink", "symlink_to_a_file"],
)
def test_only_a_regular_file_counts_as_a_backup(
    settings_path: Path,
    entry: HookEntry,
    tmp_path: Path,
    plant: Callable[[Path, Path], None],
) -> None:
    backup = backup_of(settings_path)
    plant(backup, tmp_path)

    installed = install_hooks(settings_path, entry)
    uninstalled = uninstall_hooks(settings_path)

    assert installed.refused_reason is None
    assert installed.backup_path == settings_path
    assert warnings_naming(backup, installed.warnings)
    assert uninstalled.refused_reason is None
    assert uninstalled.backup_path == settings_path
    assert warnings_naming(backup, uninstalled.warnings)


def test_a_kept_backup_that_is_not_this_runs_pre_image_is_reported(
    settings_path: Path, entry: HookEntry
) -> None:
    install_hooks(settings_path, entry)
    second = install_hooks(settings_path, entry)

    named = warnings_naming(backup_of(settings_path), second.warnings)
    assert any("first pre-install image" in warning for warning in named), second.warnings
    assert second.backup_path == backup_of(settings_path)


def test_a_kept_backup_holding_shepherd_entries_is_reported(
    settings_path: Path, entry: HookEntry, tmp_path: Path
) -> None:
    """A backup left by an older build (which overwrote it) holds our own entries."""
    donor = tmp_path / "donor" / "settings.json"
    donor.parent.mkdir()
    donor.write_bytes(FIRST_IMAGE)
    install_hooks(donor, entry)
    polluted = donor.read_bytes()
    assert MANAGED_MARKER.encode() in polluted
    backup_of(settings_path).write_bytes(polluted)

    result = install_hooks(settings_path, entry)

    named = warnings_naming(backup_of(settings_path), result.warnings)
    assert any("Shepherd entries" in warning for warning in named), result.warnings
    assert backup_of(settings_path).read_bytes() == polluted
