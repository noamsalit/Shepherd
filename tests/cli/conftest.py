"""T17's fixtures. The registry is module-global (ADR-7), so each test starts clean.

Every test here runs under the session-scoped guard in `tests/conftest.py`: no
settings file outside `tmp_path` is ever named, so the real one cannot be
touched (K3).
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from chokepoint_fixture import install_test_chokepoint

from shepherd.engines.claude_code.hookd_command import HookEntry
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface.registry import reset_registry
from shepherd.toolsurface.stream import reset_stream
from shepherd.toolsurface.tools_hooks import register_hook_tools
from shepherd.toolsurface.tools_m1 import register_read_tools

NOW = "2026-09-16T10:00:30Z"


@pytest.fixture(autouse=True)
def clean_toolsurface() -> Iterator[None]:
    reset_registry()
    reset_stream()
    yield
    reset_registry()
    reset_stream()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    return root


def scripted_host(
    *,
    runtime_dir: Path,
    dispatch_available: bool = True,
    dispatch_reason: str = "the dispatcher binaries are present",
    verified: bool = False,
    data_dir: Path | None = None,
    dispatch_command: str | None = None,
) -> ScriptedHost:
    """A host built from the six frozen records (T4), parameterised where doctor cares."""
    dirs = HostDirs(
        data_dir=runtime_dir.parent / "data" if data_dir is None else data_dir,
        config_dir=runtime_dir.parent / "config",
        runtime_dir=runtime_dir,
    )
    socket_plan = SocketPlan(
        path=runtime_dir / "sessiond.sock",
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=107,
    )
    dispatch = HookDispatchPlan(
        command=(
            f"scripted-send {runtime_dir / 'sessiond.sock'}"
            if dispatch_command is None
            else dispatch_command
        ),
        requires=("scripted-send",),
        available=dispatch_available,
        reason=dispatch_reason,
    )
    supervision = Supervision(
        kind="foreground",
        detail="no supervisor on this host",
        manageable=False,
        start_limit_note="five restarts in ten seconds then the unit is refused",
    )
    login = LoginPersistence(
        enabled=None,
        mechanism="none observed",
        detail="no persistence mechanism could be read on this host",
    )
    return ScriptedHost(
        host_dirs=dirs,
        socket_plan=socket_plan,
        dispatch=dispatch,
        supervision_plan=supervision,
        login=login,
        observed_at=NOW,
        is_verified=verified,
    )


def register_tools(
    store: Store,
    projects_root: Path,
    *,
    entry_available: bool = True,
    command: str = "scripted-send /tmp/does-not-exist.sock",
) -> None:
    """The M1 read set plus D38.1's installer trio — the only path `cli/` has.

    **And the chokepoint** (T6, DP13): the installer trio is `local_destructive`,
    and since T6 `invoke()` refuses a non-`local_read` class when no chokepoint is
    installed. This helper is the fixture's composition root, so this is where the
    gate is installed — never by relaxing the rule or re-classing a tool.
    """
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_hook_tools(
        entry=HookEntry(
            command=command if entry_available else "",
            timeout_s=5,
            available=entry_available,
            reason="scripted fixture",
        )
    )


@pytest.fixture()
def out() -> io.StringIO:
    return io.StringIO()


@pytest.fixture()
def err() -> io.StringIO:
    return io.StringIO()
