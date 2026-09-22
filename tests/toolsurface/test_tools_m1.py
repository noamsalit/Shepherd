"""T14's tools: the read set `web/`, the fleet page and `cli/` need, plus the
three hook-installer tools D38.1 puts behind `invoke()`.

Seam: `invoke()`. Every assertion goes through it, because that is the only path
a consumer has — and D38's acceptance test is that M4 changes no consumer file.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.engines.claude_code.hookd_command import HookEntry
from shepherd.store.db import Store, open_store
from shepherd.store.models import UNASSIGNED_PROJECT_ID, Session
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_hooks import register_hook_tools
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext

NOW = "2026-09-16T10:00:30Z"

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="cli", correlation_id="cid-h")
SESSION = CallerContext(audience=Audience.SESSION, caller_id="s1", correlation_id="cid-s")

READ_TOOL_NAMES = frozenset(
    {
        "fleet_summary",
        "fleet_tree",
        "list_projects",
        "list_sessions",
        "get_session",
        "list_subagents",
    }
)
HOOK_TOOL_NAMES = frozenset({"install_hooks", "uninstall_hooks", "inspect_hooks"})

#: §13: an explicit field whitelist at every response sink — never a raw row.
SESSION_FIELDS = frozenset(
    {
        "session_id",
        "workspace_id",
        "repo_id",
        "origin",
        "ownership",
        "engine",
        "title",
        "state",
        "brief",
        "cwd",
        "started_at",
        "last_event_at",
        "needs_you_reason",
        "model",
        "tasks_done",
        "tasks_total",
        "active_subagents",
        # M2's stop group (T13). Added to the constant, not to any assertion:
        # every M1 test body below is unchanged, so `fleet_tree`'s three tests
        # still hold BLOCKER T16-1 closed against a refinement of the order.
        "bucket",
        "stop_reason",
        "outcome",
        "why",
        "confidence",
        "decided_by",
        "next_actions",
        "exit_code",
        "ended_at",
    }
)


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


@pytest.fixture(autouse=True)
def tools(store: Store, projects_root: Path) -> None:
    # T6/DP13: D38.1's installer trio is `local_destructive`, so the fixture that
    # stands in for the composition root installs the chokepoint it would.
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_hook_tools(
        entry=HookEntry(command="nc -U /tmp/x", timeout_s=5, available=True, reason="")
    )


def seen_hint(count: int) -> str:
    return f"three reads answer the whole list: workspaces, repo counts, last activity — saw {count}"


def the_project(store: Store, name: str = "shepherd") -> str:
    """The project of that name, created once.

    `create_project` is no longer keyed by name (E1: `/work/api` and
    `/personal/api` are two projects), so a helper that called it per session
    used to return one row and now returns one per call. The fixture wants one
    project, so it says so.
    """
    for workspace in store.list_workspaces():
        if workspace.name == name:
            return workspace.id
    return store.create_project(name=name, description=None).id


def seed(store: Store, engine_session_id: str = "eng-1") -> Session:
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=the_project(store),
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )


def payload(name: str, args: dict[str, object], ctx: CallerContext = HUMAN) -> dict[str, object]:
    result = invoke(name, args, ctx)
    assert result.ok is True, result.error
    assert isinstance(result.data, dict)
    return result.data


def test_m1_tools_are_all_local_read() -> None:
    """The read set is `local_read`; only D38.1's installer trio is destructive."""
    tools = registered_tools()
    assert READ_TOOL_NAMES <= set(tools)
    assert all(tools[name].blast_class is BlastClass.LOCAL_READ for name in READ_TOOL_NAMES)
    assert all(
        tools[name].blast_class is BlastClass.LOCAL_DESTRUCTIVE for name in HOOK_TOOL_NAMES
    )
    assert set(tools) == READ_TOOL_NAMES | HOOK_TOOL_NAMES


def test_every_read_tool_admits_a_human() -> None:
    """ADR-3: `web/` and `cli/` are `HUMAN`, and §11's lists are kept verbatim."""
    tools = registered_tools()
    assert all(Audience.HUMAN in tools[name].audiences for name in READ_TOOL_NAMES)
    assert tools["list_sessions"].audiences == frozenset(
        {Audience.MASTER, Audience.SESSION, Audience.HUMAN}
    )
    assert tools["fleet_summary"].audiences == frozenset({Audience.MASTER, Audience.HUMAN})
    assert invoke("fleet_summary", {}, SESSION).ok is False
    assert invoke("list_sessions", {}, SESSION).ok is True


def test_fleet_summary_is_correct_on_an_empty_database() -> None:
    """F16 — the greenfield first five minutes: zero counts, no exception."""
    data = payload("fleet_summary", {})
    assert data["counts"] == {
        "needs_you": 0,
        "running": 0,
        "starting": 0,
        "stopped": 0,
    }
    assert data["needs_you"] == []
    assert data["session_count"] == 0
    assert isinstance(data["anomalies"], dict)
    assert set(data["anomalies"].values()) == {0}
    discovery = data["discovery"]
    assert isinstance(discovery, dict)
    assert discovery["hooks"] == "unknown"
    assert discovery["registry_sessions"] == 0


def test_fleet_summary_counts_states_and_lists_needs_you(store: Store) -> None:
    session = seed(store)
    store.set_app_state(
        "discovery_status",
        {
            "hooks": "absent",
            "registry_sessions": 3,
            "sdk_cli_skipped": 1,
            "skipped_other": 0,
            "unknown_status": 0,
            "scan_interval_s": 2.0,
            "last_scan_at": NOW,
        },
    )
    store.bump_anomaly("unknown_registry_status")
    data = payload("fleet_summary", {})
    counts = data["counts"]
    assert isinstance(counts, dict)
    assert counts["starting"] == 1
    assert data["session_count"] == 1
    assert data["needs_you"] == []
    anomalies = data["anomalies"]
    assert isinstance(anomalies, dict)
    assert anomalies["unknown_registry_status"] == 1
    discovery = data["discovery"]
    assert isinstance(discovery, dict)
    assert discovery["hooks"] == "absent"
    assert discovery["registry_sessions"] == 3
    assert discovery["sdk_cli_skipped"] == 1
    assert session.state is SessionState.STARTING


def test_fleet_summary_applies_the_liveness_backstop(store: Store) -> None:
    """§8: `running` with no signal inside the window is not running (T11)."""
    session = seed(store)
    store.set_app_state("x", 1)
    data = payload("fleet_summary", {})
    assert isinstance(data["counts"], dict)
    assert data["counts"]["running"] == 0
    assert session.last_event_at is None


def test_list_projects_returns_workspaces(store: Store) -> None:
    """D22: a project **is** a workspace — and after D57 it carries a
    description and a repo count rather than a `root_path` it never had.

    `last_activity_at` is derived from the project's sessions (ADR-P4), so the
    project with a session reports one and the seeded `unassigned` — which has
    none — reports `None` rather than a fabricated timestamp.
    """
    project = store.create_project(name="shepherd", description="the one")
    store.add_repo(
        workspace_id=project.id,
        root_path="/root/Shepherd",
        name="Shepherd",
        git_common_dir="/root/Shepherd/.git",
        vcs_remote=None,
    )
    store.register_session(
        engine_session_id="eng-p1",
        workspace_id=project.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )

    projects = payload("list_projects", {})["projects"]
    assert isinstance(projects, list)
    # E21/N1: a fresh install already holds the seeded reserved project.
    assert [p["name"] for p in projects] == ["Unassigned", "shepherd"]
    assert projects[1] == {
        "project_id": project.id,
        "name": "shepherd",
        "description": "the one",
        "repo_count": 1,
        "last_activity_at": "2026-09-16T10:00:00Z",
    }
    assert projects[0] == {
        "project_id": UNASSIGNED_PROJECT_ID,
        "name": "Unassigned",
        "description": "Work that matched no declared project.",
        "repo_count": 0,
        "last_activity_at": None,
    }


def test_the_project_list_issues_a_bounded_number_of_statements(store: Store) -> None:
    """M4/RD-3 — `repo_count` and `last_activity_at` are one query each for the
    **whole list**, never one per project.

    The control is the measurement across two fixture sizes: eight projects
    cost the same statements as one. An N+1 would grow with the list, and no
    assertion on the *payload* could tell the two apart.
    """

    def statements_for(project_count: int) -> int:
        for index in range(project_count):
            store.create_project(name=f"project-{index}", description=None)
        seen: list[str] = []
        connection = store._read()  # noqa: SLF001 - the tracing seam has no public door
        connection.set_trace_callback(seen.append)
        try:
            payload("list_projects", {})
        finally:
            connection.set_trace_callback(None)
        return len(seen)

    one = statements_for(1)
    eight = statements_for(8)
    assert one == eight, f"the project list is an N+1: {one} then {eight}"
    assert eight <= 3, seen_hint(eight)


def test_list_sessions_filters_by_project_and_state(store: Store) -> None:
    session = seed(store)
    all_rows = payload("list_sessions", {})["sessions"]
    assert isinstance(all_rows, list)
    assert len(all_rows) == 1
    assert payload("list_sessions", {"project_id": "nope"})["sessions"] == []
    assert payload("list_sessions", {"state": "stopped"})["sessions"] == []
    matched = payload("list_sessions", {"project_id": session.workspace_id, "state": "starting"})
    assert isinstance(matched["sessions"], list)
    assert len(matched["sessions"]) == 1


def test_list_sessions_rejects_an_unknown_state(store: Store) -> None:
    """Principle 5: an unknown value is refused, never silently treated as *all*."""
    seed(store)
    assert invoke("list_sessions", {"state": "on_fire"}, HUMAN).ok is False


def test_get_session_returns_one_row_and_the_subagent_rollup(store: Store) -> None:
    session = seed(store)
    data = payload("get_session", {"session_id": session.id})
    assert data["found"] is True
    row = data["session"]
    assert isinstance(row, dict)
    assert row["session_id"] == session.id
    assert data["subagents"] == {
        "session_id": session.id,
        "active": 0,
        "tasks_done": 0,
        "tasks_total": 0,
    }


def test_get_session_says_not_found_rather_than_failing(store: Store) -> None:
    data = payload("get_session", {"session_id": "nope"})
    assert data == {"found": False, "session": None, "subagents": None}


def test_response_projects_an_explicit_field_whitelist(store: Store) -> None:
    """§13: never a raw DB row, and never a spread of one."""
    session = seed(store)
    row = payload("get_session", {"session_id": session.id})["session"]
    assert isinstance(row, dict)
    assert set(row) == SESSION_FIELDS
    assert "owner_id" not in row
    assert "pid" not in row
    assert "engine_session_id" not in row
    listed = payload("list_sessions", {})["sessions"]
    assert isinstance(listed, list)
    assert set(listed[0]) == SESSION_FIELDS
    assert json.dumps(listed)  # every sink is JSON-serialisable, so nothing is a dataclass


def in_state(store: Store, engine_session_id: str, state: SessionState) -> Session:
    """One seeded session, moved to `state` through the one writer."""
    session = seed(store, engine_session_id=engine_session_id)
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=state,
            last_event_at=NOW,
            needs_you_reason="waiting for your answer" if state is SessionState.NEEDS_YOU else None,
        ),
    )
    return session


def test_fleet_tree_orders_by_state_not_by_creation(store: Store) -> None:
    """§16 (BLOCKER T16-1): `needs_you` floats to the top, `stopped` sinks.

    The three rows are created stopped-first, so creation order and state order
    disagree — which is what gives the assertion teeth. The order is computed in
    L2/L4 (`fleet_sort_key`) and handed to the page; the page never re-derives it.
    """
    stopped = in_state(store, "eng-stopped", SessionState.STOPPED)
    running = in_state(store, "eng-running", SessionState.RUNNING)
    needs_you = in_state(store, "eng-needs-you", SessionState.NEEDS_YOU)

    data = payload("fleet_tree", {})
    workspaces = data["workspaces"]
    assert isinstance(workspaces, list)
    assert len(workspaces) == 1
    sessions = workspaces[0]["sessions"]
    assert isinstance(sessions, list)
    assert [row["session_id"] for row in sessions] == [needs_you.id, running.id, stopped.id]
    # …and that is not the order they were created in, so the tool did something.
    assert [row["session_id"] for row in sessions] != [stopped.id, running.id, needs_you.id]

    assert workspaces[0]["project_id"] == stopped.workspace_id
    assert workspaces[0]["name"] == "shepherd"
    assert data["session_count"] == 3
    # §13: the same explicit whitelist as every other sink — never a raw row.
    assert set(sessions[0]) == SESSION_FIELDS
    assert json.dumps(data)


def test_fleet_tree_applies_the_read_time_liveness_backstop(store: Store) -> None:
    """§8: a `running` row that has been silent past the window is not running.

    This is the half `web/` could never do for itself (T16-1 option (a)): the
    demotion needs `last_event_at` compared inside L2, not a state string.
    """
    session = seed(store, engine_session_id="eng-silent")
    store.apply_fold_delta(
        session.id,
        FoldDelta(state=SessionState.RUNNING, last_event_at="2026-09-16T09:00:00Z"),
    )
    sessions = payload("fleet_tree", {})["workspaces"][0]["sessions"]
    assert isinstance(sessions, list)
    assert sessions[0]["state"] == "starting"


def test_fleet_tree_is_empty_and_honest_on_a_fresh_database() -> None:
    data = payload("fleet_tree", {})
    assert data["workspaces"] == []
    assert data["session_count"] == 0
    assert data["now"] == NOW


def test_list_subagents_reads_the_transcript(store: Store, projects_root: Path) -> None:
    session = seed(store, engine_session_id="eng-42")
    project_dir = projects_root / "-root-Shepherd"
    subagent_dir = project_dir / "eng-42" / "subagents"
    subagent_dir.mkdir(parents=True)
    (project_dir / "eng-42.jsonl").write_text("", encoding="utf-8")
    (subagent_dir / "agent-a1.meta.json").write_text(
        json.dumps({"agentType": "builder", "description": "build T14"}), encoding="utf-8"
    )
    data = payload("list_subagents", {"session_id": session.id})
    rows = data["subagents"]
    assert isinstance(rows, list)
    assert rows[0]["agent_id"] == "a1"
    assert rows[0]["agent_type"] == "builder"
    assert rows[0]["state"] == "unknown"
    assert set(rows[0]) == {
        "agent_id",
        "agent_type",
        "description",
        "started_at",
        "last_activity_at",
        "state",
        "source",
    }
    assert data["transcript_found"] is True
    # Principle 5: this subagent has no `.jsonl` (E26) and no notification to read
    # its state from (C20/E28). Both are counted rather than hidden, and the tool
    # passes the count through to the page.
    assert data["anomaly_count"] == 2


def test_list_subagents_reports_a_missing_transcript(store: Store) -> None:
    """E26: a transcript that is not there is a value, not a traceback."""
    session = seed(store)
    data = payload("list_subagents", {"session_id": session.id})
    assert data == {
        "session_id": session.id,
        "subagents": [],
        "transcript_found": False,
        "anomaly_count": 0,
    }


def test_hook_tools_require_an_explicit_settings_path(tmp_path: Path) -> None:
    """K3: nothing in this surface points at `~/.claude` — the caller names the file."""
    tools = registered_tools()
    for name in sorted(HOOK_TOOL_NAMES):
        schema = tools[name].input_schema
        assert schema["required"] == ["settings_path"]
        assert invoke(name, {}, HUMAN).ok is False
    assert all(tools[name].audiences == frozenset({Audience.HUMAN}) for name in HOOK_TOOL_NAMES)


def test_install_then_inspect_then_uninstall_through_invoke(tmp_path: Path) -> None:
    """D38.1: `cli/` reaches the installer through `invoke()`, never through `engines/`."""
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    installed = payload("install_hooks", {"settings_path": str(settings)})
    assert installed["refused_reason"] is None
    assert isinstance(installed["events_installed"], int)
    assert installed["events_installed"] > 0
    assert set(installed) == {
        "settings_path",
        "backup_path",
        "events_installed",
        "warnings",
        "refused_reason",
    }

    inspected = payload("inspect_hooks", {"settings_path": str(settings)})
    assert inspected["installed"] is True
    assert set(inspected) == {
        "installed",
        "managed_entries",
        "foreign_entries",
        "pre_existing_breakage",
        "command_matches_current_host",
    }

    removed = payload("uninstall_hooks", {"settings_path": str(settings)})
    assert removed["refused_reason"] is None
    assert json.loads(settings.read_text(encoding="utf-8")) == {}


def test_install_hooks_honours_dry_run(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    result = payload("install_hooks", {"settings_path": str(settings), "dry_run": True})
    assert result["refused_reason"] is None
    assert settings.read_text(encoding="utf-8") == "{}"


def test_fleet_summary_shows_an_anomaly_it_did_not_expect(store: Store) -> None:
    """BLOCKER T14-3: the page shows what was *counted*, not what was expected.

    A reader that asks for one key per `AnomalyKind` member can only ever see
    the kinds it already knew about — the opposite of principle 5, where an
    unknown is counted *and shown*. `Store.list_anomaly_counts()` enumerates the
    `anomaly.*` keys, so a kind this build has no member for still reaches the
    page rather than vanishing into the database.
    """
    store.bump_anomaly("unknown_registry_status")
    store.bump_anomaly("a_kind_from_a_newer_build")

    anomalies = payload("fleet_summary", {})["anomalies"]
    assert isinstance(anomalies, dict)
    assert anomalies["unknown_registry_status"] == 1
    assert anomalies["a_kind_from_a_newer_build"] == 1
    # …and every kind this build *does* know is still present, at zero.
    assert anomalies["malformed_payload"] == 0
