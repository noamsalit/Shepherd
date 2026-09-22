"""T15's route half: every API body is a `ToolResult` from `invoke()` (D19, D35).

Seam: HTTP. The AST checks below are the exception, and they exist because
"`web/` only ever calls `invoke()`" is a structural claim a request cannot make
— a handler that reached past L4 would still answer 200.
"""

from __future__ import annotations

import ast
from pathlib import Path

from web.conftest import Client, seed

from shepherd.store.db import Store
from shepherd.toolsurface.registry import registered_tools
from shepherd.toolsurface.tools_replay import REPLAY_TOOL
from shepherd.web import routes

WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web"

#: The only names `web/` may *call* on the other side of the seam.
CALLABLE_ACROSS_THE_SEAM = frozenset({"invoke", "subscribe", "CallerContext", "Audience"})

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
        # M2's stop group (T13) — the whitelist grew by nine named keys, which
        # is the point: §13's rule is that the list is explicit, not that it is
        # short. No assertion below changed.
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


def web_modules() -> list[Path]:
    return sorted(path for path in WEB_ROOT.glob("*.py"))


def imported_from_shepherd(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("shepherd."):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def called_names(tree: ast.Module) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


# ----- the route table --------------------------------------------------------


def test_every_api_route_names_a_registered_tool() -> None:
    """A path that names a tool the registry does not have is a 500 waiting."""
    available = set(registered_tools())
    assert set(routes.API_ROUTES.values()) <= available
    assert set(routes.API_ROUTES) == {
        "/api/fleet",
        "/api/fleet/tree",
        "/api/projects",
        "/api/sessions",
        "/api/sessions/{session_id}",
        "/api/sessions/{session_id}/subagents",
        # M3 (T18). Task 18's exit criteria say "M1's and M2's route tests pass
        # **unchanged**" and its `Produces` says `API_ROUTES` gains these two —
        # both cannot be literally true, and the property the criterion protects
        # is that no M1 or M2 *behaviour* changed, which holds: every assertion
        # in this file below is untouched and green. This is a closed-set literal
        # that has to be widened for the same reason acceptance clause 14's
        # "seven" became ten (T-ACC-14), and it is widened rather than deleted so
        # that the next route still has to be declared here.
        "/api/sessions/{session_id}/output",
        "/api/mailbox",
        # M4 (T24), and widened for the same reason and in the same way M3's two
        # were: this is a closed-set literal, so the next route still has to be
        # declared here rather than appearing unnoticed. `/api/autonomy` is a
        # read as well as a write (§12: the level is visible at all times) and
        # is recorded as a deviation in `docs/plans/m4-blockers/t24.md` §T24-1.
        "/api/approvals",
        "/api/audit",
        "/api/autonomy",
        # The Projects page (T4.1), widened by hand for the third time and for
        # the third time on purpose: this is a **closed set**, so the fourteenth
        # route — Phase 8's — still has to be declared here rather than arriving
        # unnoticed. Two reads; the project's own detail and its registered
        # repos. `/api/projects` above is unchanged and still names
        # `list_projects`: two segments, never three.
        "/api/projects/{project_id}",
        "/api/projects/{project_id}/repos",
    }


def test_every_api_route_calls_invoke() -> None:
    """§5.0's invariant, asserted structurally: nothing else is reachable."""
    offenders: list[str] = []
    for path in web_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        across = imported_from_shepherd(tree)
        for name in sorted(across & called_names(tree)):
            if name not in CALLABLE_ACROSS_THE_SEAM:
                offenders.append(f"{path.name} calls {name}")
    assert offenders == []
    # self-check: the scan bites on a module that reaches past L4.
    leak = ast.parse("from shepherd.store.db import open_store\nopen_store('x')\n")
    assert "open_store" in imported_from_shepherd(leak) & called_names(leak)


def test_fleet_route_answers_through_the_tool_surface(client: Client) -> None:
    response = client.request("/api/fleet")
    assert response.status == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert isinstance(data, dict)
    assert data["session_count"] == 0
    assert data["counts"] == {"needs_you": 0, "running": 0, "starting": 0, "stopped": 0}


def test_session_routes_resolve_the_path_parameter(client: Client, store: Store) -> None:
    session = seed(store)
    body = client.request(f"/api/sessions/{session.id}").json()
    data = body["data"]
    assert isinstance(data, dict)
    assert data["found"] is True

    subagents = client.request(f"/api/sessions/{session.id}/subagents").json()
    rollup = subagents["data"]
    assert isinstance(rollup, dict)
    assert rollup["session_id"] == session.id
    assert rollup["transcript_found"] is False


def test_query_arguments_reach_the_tool(client: Client, store: Store) -> None:
    session = seed(store)
    listed = client.request(f"/api/sessions?project_id={session.workspace_id}").json()
    data = listed["data"]
    assert isinstance(data, dict)
    sessions = data["sessions"]
    assert isinstance(sessions, list)
    assert len(sessions) == 1

    empty = client.request("/api/sessions?project_id=nope").json()
    other = empty["data"]
    assert isinstance(other, dict)
    assert other["sessions"] == []


def test_response_never_contains_a_raw_row(client: Client, store: Store) -> None:
    """§13 API responses: an explicit whitelist, never a row and never a spread."""
    seed(store)
    data = client.request("/api/sessions").json()["data"]
    assert isinstance(data, dict)
    sessions = data["sessions"]
    assert isinstance(sessions, list)
    row = sessions[0]
    assert isinstance(row, dict)
    assert set(row) == SESSION_FIELDS
    assert "engine_session_id" not in row
    assert "owner_id" not in row
    assert "ephemeral" not in row


def test_replay_is_not_reachable_from_any_api_route(client: Client) -> None:
    """D25 holds — but by the route table, not by the audience set.

    `tools_replay.py` said "the audience set is the gate", and it is not:
    `web/server.py` supplies `Audience.HUMAN` for every browser request, so
    `audiences={HUMAN}` excludes nothing the web layer does. What actually
    holds the line is this fixed whitelist, and until now nothing asserted it.
    """
    assert REPLAY_TOOL not in set(routes.API_ROUTES.values())
    assert not any(REPLAY_TOOL in path for path in routes.API_ROUTES)
    # …and the server refuses the path rather than resolving it to the tool.
    assert routes.resolve(f"/api/{REPLAY_TOOL}", {}) is None
    assert client.request(f"/api/{REPLAY_TOOL}").status == 404


def test_no_polling_endpoint_exists() -> None:
    """§12: the stream is the only liveness path — no `/api/poll`, no `?since=`."""
    assert routes.SSE_PATH == "/api/events"
    assert not any("poll" in path for path in routes.API_ROUTES)
    assert routes.SSE_PATH not in routes.API_ROUTES
