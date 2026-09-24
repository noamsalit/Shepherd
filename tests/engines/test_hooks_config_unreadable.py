"""qa6 BC-20: a settings file that cannot be read is a refusal, not a traceback.

Seam: `install_hooks` / `inspect_hooks`. The settings file is always under
`tmp_path` (K3): the real `~/.claude/settings.json` is never named here, and
`tests/conftest.py`'s session guard watches it regardless.

Mode 000 does not stop root, so the test is skipped there (E12) — a root run
would read the file and prove nothing about the refusal.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.engines.claude_code.hooks_config import BACKUP_SUFFIX, inspect_hooks, install_hooks
from shepherd.host.base import SocketPlan
from shepherd.host.detect import detect_host

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="mode 000 does not stop root (E12)"
)

SETTINGS = {"model": "claude-haiku-4-5-20251001"}


def host_entry() -> HookEntry:
    """An installable entry for *this* host, as `test_hooks_install.py` builds one."""
    host = detect_host()
    plan = SocketPlan(
        path=Path("/run/user/0/shepherd/sessiond.sock"),
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=host.control_socket("sessiond").socket_path_budget,
    )
    return build_hook_entry(plan, host.hook_dispatch(plan))


@pytest.fixture
def unreadable_settings(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(SETTINGS), encoding="utf-8")
    path.chmod(0o000)
    try:
        yield path
    finally:
        path.chmod(0o600)


def test_an_unreadable_settings_file_is_a_refusal(unreadable_settings: Path) -> None:
    entry = host_entry()
    if not entry.available:
        pytest.skip(f"no dispatcher on this host: {entry.reason}")

    result = install_hooks(unreadable_settings, entry)

    assert result.refused_reason is not None and result.refused_reason != ""
    assert "cannot be read" in result.refused_reason
    assert "left untouched" in result.refused_reason
    assert result.events_installed == 0
    assert not unreadable_settings.with_name(unreadable_settings.name + BACKUP_SUFFIX).exists()


def test_inspecting_an_unreadable_settings_file_does_not_raise(unreadable_settings: Path) -> None:
    inspection = inspect_hooks(unreadable_settings)

    assert inspection.installed is False
    assert inspection.managed_entries == 0
    assert any("cannot be read" in line for line in inspection.pre_existing_breakage)
