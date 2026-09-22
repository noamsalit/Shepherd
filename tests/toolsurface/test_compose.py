"""T18-3: the composition helper's own seam — what this build is composed of.

`compose_tool_surface` had no test of its own. It was observed only through
`tests/daemons/test_controld.py`, which binds two unix sockets and an HTTP
server to see it — a fine acceptance test and a poor microscope. The list of
capabilities a build has should be readable off one assertion, and ADR-7's
"frozen before the server can serve" should be provable without a server.

Seam: the module's public interface (`compose_tool_surface`, `publish_result`)
plus the two module-global surfaces it composes — the registry and the ring.
Nothing here reaches inside a handler.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.daemons import plane
from shepherd.core.fold_types import FoldDelta, FoldResult
from shepherd.core.stream import StreamEvent
from shepherd.host.base import HookDispatchPlan, HostDirs, LoginPersistence, SocketPlan, Supervision
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface import compose, tools_m3
from shepherd.toolsurface.registry import RegistryFrozen, register, registered_tools
from shepherd.toolsurface.stream import publish, subscribe
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef

#: The capabilities M1 shipped, read off the three `tools_*` modules that declare
#: them — a **list, compared**, never a count. A count cannot tell a build that
#: lost `inspect_hooks` from one that gained a tool and lost two.
M1_TOOL_NAMES: tuple[str, ...] = (
    "engine_version",
    "fleet_summary",
    "fleet_tree",
    "get_session",
    "inspect_hooks",
    "install_hooks",
    "list_projects",
    "list_sessions",
    "list_subagents",
    "schema_status",
    "uninstall_hooks",
)

#: What M2 adds to the surface. Named separately so a reader can see, in one
#: assertion, exactly which capability this milestone gave the build — and so a
#: lost M1 tool can never be hidden by a gained M2 one.
M2_TOOL_NAMES: tuple[str, ...] = ("replay",)

#: What M3 adds (T23): Task 18's twelve, plus T20's `rename_session`, which is
#: registered by its own function and not by the bulk register. Named as a list
#: for M1's reason — a count cannot tell a build that lost the terminal from one
#: that gained a rename and lost two.
M3_TOOL_NAMES: tuple[str, ...] = (*tools_m3.M3_TOOL_NAMES, "rename_session")

#: What M4 adds (T25): `tools_master.py`'s ten, registered by the composition
#: root. Written out for M1's reason — a lost M3 tool must not be hidden by a
#: gained M4 one — and the ten are the whole of what `register_master_tools`
#: puts on the surface, which `tests/toolsurface/test_compose_m4.py::
#: test_the_master_tools_are_registered_by_the_composition` asserts by
#: enumerating rather than by this list.
M4_TOOL_NAMES: tuple[str, ...] = (
    "decide_approval",
    "get_audit_log",
    "get_autonomy_level",
    "interrupt_master",
    "list_approvals",
    "master_send",
    "report_blocked",
    "request_help",
    "set_autonomy_level",
    "wake_summary",
)

#: What T3.2 adds: D57's project lifecycle, registered by the composition root.
#: Written out for the same reason the four lists above are — a list built from
#: `tools_projects.PROJECT_TOOL_NAMES` would agree with itself no matter which
#: verbs the composition actually reached.
#:
#: **Six, not the plan's seven.** `delete_project` is not registered: its store
#: verb calls the injected `kill` inside the writer transaction, and the shipped
#: kill path writes to the store first, which deadlocks the writer thread. The
#: seventh name arrives on this line with the store-side split.
PROJECT_TOOL_NAMES_HERE: tuple[str, ...] = (
    "add_repo",
    "create_project",
    "get_project",
    "list_repos",
    "remove_repo",
    "rename_project",
)

ALL_TOOL_NAMES: tuple[str, ...] = tuple(
    sorted(
        M1_TOOL_NAMES
        + M2_TOOL_NAMES
        + M3_TOOL_NAMES
        + M4_TOOL_NAMES
        + PROJECT_TOOL_NAMES_HERE
    )
)

NOW = "2026-09-17T10:00:00Z"


@dataclass(frozen=True)
class World:
    """Everything `compose_tool_surface` takes, all of it under `tmp_path`."""

    store: Store
    host: ScriptedHost
    db_path: Path
    ingest: SocketPlan


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    # K3: the engine config dir is a throwaway, so nothing here can even read
    # the real `~/.claude`, let alone write beside it.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    runtime_dir = tmp_path / "run"
    host = ScriptedHost(
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
        # The client and the plane are module-global by ADR-7, exactly as the
        # registry and the ring are: a composition that survived a check would
        # decide the next one.
        from shepherd.toolsurface.client import reset_master_client

        reset_master_client()
        compose.reset_master_plane()
        store.close()


def compose_world(world: World) -> None:
    """The shipped call, with the shipped plane on both of its M4 arguments.

    `plane.build_master` is passed rather than a double and is never called: the
    master is lazy (RD6), so composing starts no runtime and no vendor process —
    which is itself the property `test_no_master_is_built_before_a_turn_asks_
    for_one` asserts one file over.
    """
    compose.compose_tool_surface(
        world.store,
        world.host,
        world.db_path,
        world.ingest,
        plane.build_master,
        plane.audit_sink(world.store, world.host),
    )


def an_event(kind: str) -> StreamEvent:
    return StreamEvent(kind=kind, session_id="s-1", payload={}, occurred_at=NOW)


def test_compose_registers_every_tool_the_daemon_had(world: World) -> None:
    """The names the helper registers, compared against M1's list as a list."""
    assert registered_tools() == {}

    compose_world(world)

    assert tuple(sorted(registered_tools())) == ALL_TOOL_NAMES


def test_compose_is_called_before_freeze_registry(world: World) -> None:
    """ADR-7: written by one thread at startup, read-only from the return."""
    compose_world(world)

    with pytest.raises(RegistryFrozen):
        register(
            ToolDef(
                name="too_late",
                description="registered after the composition returned",
                input_schema={"type": "object", "properties": {}},
                blast_class=BlastClass.LOCAL_READ,
                handler=lambda args, ctx: None,
                audiences=frozenset({Audience.HUMAN}),
            )
        )


def test_compose_publishes_every_event_of_a_fold_result(world: World) -> None:
    """ADR-4: `signals/` produces events and the composition publishes them.

    The adapter belongs beside the surface it publishes through, not in the
    daemon: the daemon owns the *order* things are wired in, and a loop over a
    result is not an order (T18-3 — the cap is a proxy for "no logic here").
    """
    compose_world(world)
    result = FoldResult(
        delta=FoldDelta(),
        events=(an_event("session.registered"), an_event("session.updated")),
        anomalies=(Anomaly(kind=AnomalyKind.UNKNOWN_EVENT_NAME, detail="x", engine_session_id=None),),
    )

    compose.publish_result(result)

    assert [delivery.event.kind for delivery in subscribe(0)] == [
        "session.registered",
        "session.updated",
    ]


def test_compose_empties_the_ring_the_build_publishes_through(world: World) -> None:
    """One call composes both module-global surfaces (ADR-7), so a restart in
    one process cannot serve the previous composition's backlog."""
    publish(an_event("left.over"))
    assert [delivery.event.kind for delivery in subscribe(0)] == ["left.over"]

    compose_world(world)

    assert list(subscribe(0)) == []
