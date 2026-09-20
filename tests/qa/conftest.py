"""The composed product, under `tmp_path`, for the whole QA package.

`compose_tool_surface` is the seam every scenario here starts from: it is the
one function that says what this build *is*, and testing anything less than it
is testing a milestone rather than the product.

**K3, by construction.** `CLAUDE_CONFIG_DIR` and every `XDG_*` variable point
into `tmp_path` before anything composes, so nothing in this package can read
the real `~/.claude`, let alone write beside it. The session-wide guards in
`tests/conftest.py` still run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.core.master import (
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterRuntime,
)
from shepherd.daemons import plane
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface import client, compose
from shepherd.toolsurface.registry import reset_registry
from shepherd.toolsurface.stream import reset_stream

NOW = "2026-09-18T10:00:00Z"


class IdleMaster:
    """A `MasterRuntime` that opens a turn and ends it without an event.

    A double, and named as one: building a real `AgentSDKMaster` would put a
    vendor subprocess behind a default-lane test. Nothing here is a claim about
    what a runtime does — that is `tests/master/`'s and the contract suite's.
    """

    def __init__(self) -> None:
        self.closed = 0
        self.configured: tuple[ExportedTool, ...] = ()
        self.prompts: list[str] = []
        self.resumed: list[str] = []
        self.interrupts = 0

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        self.configured = tools

    def send(self, text: str) -> AsyncIterator[MasterEvent]:
        """The seam's own signature, spelled out rather than widened to `object`.

        `tests/e2e/test_live_lane_typechecks.py` type-checks this module — it is
        the `conftest.py` beside a live-marked test — and it caught the first
        version of this double, whose `send` answered `object` and whose
        `capabilities` did too. A double that does not satisfy the Protocol it
        stands in for is a double that can drift away from the seam without
        anything noticing, which is exactly what §14.2's `Scripted*` peers exist
        to prevent.
        """
        self.prompts.append(text)

        async def stream() -> AsyncIterator[MasterEvent]:
            if False:  # pragma: no cover - an empty async generator
                yield MasterEvent(
                    kind="turn_ended",
                    text=None,
                    tool_name=None,
                    payload={},
                    occurred_at=NOW,
                )

        return stream()

    def resume(self, master_session_id: str) -> None:
        self.resumed.append(master_session_id)

    def interrupt(self) -> None:
        self.interrupts += 1

    def capabilities(self) -> MasterCapabilities:  # pragma: no cover
        raise AssertionError("no capability is read in this package")

    def close(self) -> None:
        self.closed += 1


@dataclass
class World:
    """Everything `compose_tool_surface` takes, all of it under `tmp_path`."""

    store: Store
    host: ScriptedHost
    db_path: Path
    ingest: SocketPlan
    built_for: list[str] = field(default_factory=list)
    masters: list[IdleMaster] = field(default_factory=list)

    def compose(self) -> compose.M4Wiring:
        """The shipped call, with the shipped plane's audit sink on the far side."""

        def build(store: Store, turn_id: str) -> MasterRuntime:
            self.built_for.append(turn_id)
            master = IdleMaster()
            self.masters.append(master)
            runtime: MasterRuntime = master
            return runtime

        return compose.compose_tool_surface(
            self.store,
            self.host,
            self.db_path,
            self.ingest,
            build,
            plane.audit_sink(self.store, self.host),
        )


def scripted_host(tmp_path: Path) -> ScriptedHost:
    """A host whose every directory and socket is under `tmp_path`."""
    runtime_dir = tmp_path / "run"
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=tmp_path / "data",
            config_dir=tmp_path / "config",
            runtime_dir=runtime_dir,
        ),
        socket_plan=SocketPlan(
            path=runtime_dir / "sessiond.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(
            command=f"scripted-send {runtime_dir / 'sessiond.sock'}",
            requires=("scripted-send",),
            available=True,
            reason="scripted fixture",
        ),
        supervision_plan=Supervision(
            kind="foreground",
            detail="no supervisor on this host",
            manageable=False,
            start_limit_note="five restarts in ten seconds then the unit is refused",
        ),
        login=LoginPersistence(
            enabled=None,
            mechanism="none observed",
            detail="no persistence mechanism could be read on this host",
        ),
        observed_at=NOW,
    )


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """One composed build, torn down the way the composition itself starts.

    The teardown resets the three module globals this build holds (ADR-7): a
    registry, a ring or a plane that survives a test is state that decides the
    next one.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))

    host = scripted_host(tmp_path)
    db_path = tmp_path / "data" / "shepherd.db"
    store = open_store(db_path)
    try:
        yield World(
            store=store,
            host=host,
            db_path=db_path,
            ingest=host.control_socket("sessiond"),
        )
    finally:
        client.reset_master_client()
        compose.reset_master_plane()
        reset_registry()
        reset_stream()
        store.close()
