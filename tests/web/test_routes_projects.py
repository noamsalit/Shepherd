"""T4.2: the Projects page's eight routes (seven at T4.2, plus T3.4's description), and the two things a table can get
wrong that nothing else catches.

**Two seams, both the plan's.** `resolve` / `resolve_post` are read over literal
paths — a route table is a value, and resolution is the whole of its behaviour —
and the end-to-end line goes through `tests/web/conftest.py::Client`, a real
socket to a real handler, because that is the only surface a browser has.

The two failures this file exists for:

1. **`/api/projects` read as `/api/projects/{project_id}`.** Two segments and
   three; `_ordered` puts static templates first, and if it did not, the list
   route would resolve as a detail whose id is the empty string.
2. **A body field that shadows a path parameter** (P13/M1). The route gate in
   `test_routes_m3.py` checks `BODY_ARGS` against the tool's schema and never
   looks at path parameters, so `project_id` declared as a body field would pass
   every gate in this repo and disagree with the URL at run time.
"""

from __future__ import annotations

import pytest

from shepherd.web import routes

from web.conftest import Client

#: The seven, spelled out rather than read off `PROJECT_TOOL_NAMES`: a list
#: built from the thing under test agrees with it no matter which routes exist.
PROJECT_ROUTES: dict[str, str] = {
    "/api/projects": "list_projects",
    "/api/projects/{project_id}": "get_project",
    "/api/projects/{project_id}/repos": "list_repos",
}
PROJECT_POST_ROUTES: dict[str, str] = {
    "/api/projects": "create_project",
    "/api/projects/{project_id}/rename": "rename_project",
    "/api/projects/{project_id}/description": "set_project_description",
    "/api/projects/{project_id}/delete": "delete_project",
    "/api/projects/{project_id}/repos/add": "add_repo",
    "/api/projects/{project_id}/repos/remove": "remove_repo",
}


def test_the_projects_tables_name_the_projects_tools() -> None:
    """The table, as a mapping a reader can check against the plan by eye."""
    for template, tool in PROJECT_ROUTES.items():
        assert routes.API_ROUTES[template] == tool
    for template, tool in PROJECT_POST_ROUTES.items():
        assert routes.POST_ROUTES[template] == tool


def test_the_project_list_is_never_read_as_a_project_detail() -> None:
    """Two segments, never three — the exit criterion, both ways.

    `_ordered` sorts static templates ahead of templated ones, so this would
    still pass if `_match` counted segments loosely; the second half is the one
    that bites, because a detail path must not fall back to the list either.
    """
    listed = routes.resolve("/api/projects", {})
    assert listed is not None
    assert listed.tool == "list_projects"
    assert listed.args == {}

    detail = routes.resolve("/api/projects/w-pay", {})
    assert detail is not None
    assert detail.tool == "get_project"
    assert detail.args == {"project_id": "w-pay"}

    # …and a trailing slash is still the **list**, never a detail whose id is
    # the empty string. `_segments` drops empty parts, so `/api/projects/` has
    # two segments and the three-segment template cannot match it at all — the
    # measured behaviour, written down here because the first version of this
    # line asserted a 404 and was wrong about which safe answer it gets.
    trailing = routes.resolve("/api/projects/", {})
    assert trailing is not None
    assert trailing.tool == "list_projects"
    assert trailing.args == {}


def test_the_project_post_routes_carry_their_declared_bodies() -> None:
    """Each mutation's body, as the plan declares it — and `project_id` in none
    of them, because it is the path parameter."""
    assert routes.BODY_ARGS["/api/projects"] == ("name", "description")
    assert routes.BODY_ARGS["/api/projects/{project_id}/rename"] == ("name",)
    # A path suffix, like every other mutation here: the table maps a path to a
    # tool name, and a second HTTP verb would put a second dimension into a
    # lookup that is deliberately one.
    assert routes.BODY_ARGS["/api/projects/{project_id}/description"] == ("description",)
    assert routes.BODY_ARGS["/api/projects/{project_id}/delete"] == ("on_running",)
    assert routes.BODY_ARGS["/api/projects/{project_id}/repos/add"] == ("root_path",)
    assert routes.BODY_ARGS["/api/projects/{project_id}/repos/remove"] == ("repo_id",)


def test_an_undeclared_body_field_is_dropped_before_invoke() -> None:
    """The declared-field rule, on the route that would hurt most.

    `delete_project` forwards `on_running` and nothing else. A caller that adds
    a field is not smuggling it past `invoke()`'s schema check into a handler
    that happens to accept it (D53) — the table drops it here.
    """
    resolved = routes.resolve_post(
        "/api/projects/w-pay/delete",
        {"on_running": "orphan", "confirm": True, "force": "yes"},
    )
    assert resolved is not None
    assert resolved.tool == "delete_project"
    assert resolved.args == {"project_id": "w-pay", "on_running": "orphan"}


def test_the_path_parameter_wins_over_a_body_that_names_another_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P13's positive half: the merge order, declared and watched.

    `test_no_declared_field_shadows_a_path_parameter` says no route declares
    `project_id` as a body field **today**; that is the braces. This is the
    belt: declare it for one route and watch the path win anyway, so reversing
    the merge inside `resolve_post` turns this red rather than surviving on the
    fact that the field was never declared.

    The route driven is `delete`, deliberately: it is the one where reading the
    body instead of the URL destroys the wrong project.
    """
    widened = dict(routes.BODY_ARGS)
    widened["/api/projects/{project_id}/delete"] = ("on_running", "project_id")
    monkeypatch.setattr(routes, "BODY_ARGS", widened)

    resolved = routes.resolve_post(
        "/api/projects/wanted/delete",
        {"project_id": "somebody-elses", "on_running": "orphan"},
    )
    assert resolved is not None
    assert resolved.tool == "delete_project"
    assert resolved.args == {"project_id": "wanted", "on_running": "orphan"}


def test_create_project_through_http(client: Client) -> None:
    """The one end-to-end line: a socket, the real handler, `invoke()`, a store.

    It is here rather than in Phase 9 because what it proves is that the *route*
    reaches the tool — the body field arrives under the name the schema wants,
    and the answer comes back as the projection. That no **page** calls it is
    Phase 9's to prove; this file cannot.
    """
    response = client.post("/api/projects", {"name": "payments", "description": "the api"})

    assert response.status == 200, response.body
    created = response.json()["data"]
    assert isinstance(created, dict)
    assert created["created"] is True
    project = created["project"]
    assert isinstance(project, dict)
    assert project["name"] == "payments"
    assert project["description"] == "the api"

    # …and the project is reachable by the path the detail route names, which is
    # the half that says `/api/projects/{project_id}` resolves to a real call.
    fetched = client.request(f"/api/projects/{project['project_id']}")
    assert fetched.status == 200, fetched.body
    detail = fetched.json()["data"]
    assert isinstance(detail, dict)
    assert detail["found"] is True
    assert isinstance(detail["project"], dict)
    assert detail["project"]["name"] == "payments"
