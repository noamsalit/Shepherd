"""T3.1: the project verbs, reached the only way a consumer may reach them.

**Two seams, both the plan's.** The schemas are read off `build_project_tools()`
directly — a schema is a *value*, and a consumer's binding reads it before any
call is made — and every behavioural assertion goes through `invoke()` with the
shipped chokepoint installed, exactly as `web/` and `cli/` do (D19, D32, D35).
A tool that works when its handler is called directly and is unregistered,
mis-audienced or schema-mangled is red here rather than in a browser.

**`delete_project` is deliberately absent, and it is not an oversight.**
`writes.delete_project` calls its injected `kill` from inside the lambda
`Store._write` runs on the single writer thread after `BEGIN IMMEDIATE`
(`store/writes.py:207`), and the real kill path's first statement is itself a
store write (`orchestration/lifecycle.py:126`) whose write-before-kill order is
what survives a crash. Wiring the shipped kill path into that callable enqueues
a job the blocked writer can never reach, and the writer thread has no timeout —
so every later write in the process hangs permanently. Phase 1's suite is green
only because every test there passes an inert stub, and a callback under test is
a stub under test. The verb is blocked on the store-side split (decide → kill
outside the transaction → commit) and is written up in
`docs/plans/projects-ui-blockers/t3-1.md`.

**The git probe is real.** `add_repo` runs `git` in a subprocess because
`git_common_dir` is D48's binding key (F5/E23): a repo registered through the UI
with a guessed or empty value never matches `find_repo_by_common_dir`, so a
session started in it would bind to `Unassigned` silently. Proving that against
a fake probe would prove the fake. The trees here are throwaway ones under
`tmp_path`, with global and system git config pinned to `/dev/null` by
`signals.conftest.git_env`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint
from signals.conftest import git_env

from shepherd.signals.binding import bind_cwd_to_repo
from shepherd.store.db import Store, open_store
from shepherd.store.models import UNASSIGNED_PROJECT_ID, OnRunning
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_projects import (
    PROJECT_TOOL_NAMES,
    build_project_tools,
    register_project_tools,
)
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext, ToolResult

NOW = "2026-09-22T10:00:00.000Z"

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="web", correlation_id="cid-h")
SESSION = CallerContext(audience=Audience.SESSION, caller_id="sess", correlation_id="cid-s")


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def registered(store: Store) -> Store:
    """One registration per test, behind the shipped gate.

    `install_test_chokepoint` installs `build_authorizer` over a real
    `ApprovalStore` at `LEVEL_3` — the shipped gate, not a permissive stub — so
    the `local_destructive` verbs below cross the same authoriser production
    puts in front of them.
    """
    install_test_chokepoint()
    register_project_tools(store=store, now=lambda: NOW)
    return store


def call(name: str, args: dict[str, object], ctx: CallerContext = HUMAN) -> ToolResult:
    return invoke(name, args, ctx)


def data(result: ToolResult) -> dict[str, object]:
    assert result.ok, (result.error, result.failure)
    assert isinstance(result.data, dict)
    return result.data


def make_repo(root: Path) -> Path:
    """A throwaway working tree with a real `.git`, and nothing else."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=root,
        env=git_env(),
        capture_output=True,
        check=True,
    )
    return root


def made(registered: Store, name: str = "payments") -> str:
    created = data(call("create_project", {"name": name}))
    project = created["project"]
    assert isinstance(project, dict)
    return str(project["project_id"])


# ----- the surface, read off the definitions ---------------------------------


def test_the_project_verbs_register_with_the_blast_classes_d58_assigns(
    registered: Store,
) -> None:
    """D58's table, as values the M4 gate will read.

    The two that widen §13's allowlist are `local_destructive` — D22:
    *"adding a repo widens that allowlist"*, and creating a project creates a
    thing that can hold one; the two that relabel or narrow are `local_write`;
    the two reads are `local_read`. Asserted as a mapping rather than as six
    lines so a seventh verb is a failure here and not a silent addition.
    """
    assert PROJECT_TOOL_NAMES == (
        "create_project",
        "rename_project",
        "add_repo",
        "remove_repo",
        "list_repos",
        "get_project",
    )
    tools = registered_tools()
    assert {name: tools[name].blast_class for name in PROJECT_TOOL_NAMES} == {
        "create_project": BlastClass.LOCAL_DESTRUCTIVE,
        "rename_project": BlastClass.LOCAL_WRITE,
        "add_repo": BlastClass.LOCAL_DESTRUCTIVE,
        "remove_repo": BlastClass.LOCAL_WRITE,
        "list_repos": BlastClass.LOCAL_READ,
        "get_project": BlastClass.LOCAL_READ,
    }
    assert all(
        tools[name].audiences == frozenset({Audience.MASTER, Audience.HUMAN})
        for name in PROJECT_TOOL_NAMES
    )


def test_delete_project_is_not_registered_and_the_reason_is_the_writer_thread(
    registered: Store,
) -> None:
    """The blocked verb, asserted as absent rather than left to be noticed.

    A phase that ships six of seven and says so in prose is a phase whose gap
    lives in a document; this is the same fact where a consumer can trip over
    it. It goes red the moment the verb is wired, which is the point: the next
    builder has to come back here, read why it was absent, and delete this
    test deliberately.
    """
    assert "delete_project" not in registered_tools()
    assert "delete_project" not in PROJECT_TOOL_NAMES


def test_a_session_audience_cannot_reach_any_project_verb(registered: Store) -> None:
    """The control for the audience assertion above — one branch of two.

    `{MASTER, HUMAN}` is only a restriction if the third audience is refused,
    and §13 says the refusal must be indistinguishable from *no such tool*, so
    the check is on the absence of data and never on the text.
    """
    for name in PROJECT_TOOL_NAMES:
        refused = call(name, {"name": "x", "project_id": "x", "root_path": "/x"}, SESSION)
        assert refused.ok is False, name
        assert refused.data is None, name


def test_every_project_schema_spells_project_id_and_never_workspace_id(
    registered: Store,
) -> None:
    """M1: the consumer-facing key is `project_id`, in every verb that takes one.

    `project_workspace` already emits `project_id` and the route templates
    already spell it that way. `registry._argument_problem` rejects an unknown
    argument, and the route gate checks `BODY_ARGS` alone — **it never checks
    path parameters** — so a schema saying `workspace_id` passes every gate this
    repo has and 400s at runtime. This line is what makes that impossible.
    """
    schemas = {tool.name: tool.input_schema for tool in build_project_tools(registered)}
    assert set(schemas) == set(PROJECT_TOOL_NAMES)
    for name, schema in schemas.items():
        properties = schema["properties"]
        required = schema["required"]
        assert isinstance(properties, dict)
        assert isinstance(required, list)
        assert "workspace_id" not in properties, name
        if name == "create_project":
            assert required == ["name"]
            continue
        assert "project_id" in properties, name
        assert "project_id" in required, name


def test_the_on_running_enum_is_on_running_itself() -> None:
    """The enum a `delete_project` schema must carry **is** `OnRunning`'s values.

    Typing the three strings is exactly how the plan's `["refuse", "kill",
    "orphan"]` went stale against `OnRunning.KILL == "kill_sessions"`, so this
    reads the enum on both sides. That makes it tautological about the
    *spelling* — it cannot tell you what the values are — and load-bearing about
    the *link*: it is the only thing that can tell you the schema and the enum
    have come apart.

    It is asserted against the **helper**, not against a registered tool,
    because the verb is blocked (see this module's docstring). The derivation
    ships now so the split's builder inherits it rather than re-deriving it, and
    the helper is used by nothing else — which this line also states.
    """
    from shepherd.toolsurface.tools_projects import on_running_schema

    schema = on_running_schema()
    assert schema["enum"] == [member.value for member in OnRunning]
    # D61: **no schema default.** Default-refuse must be unskippable by
    # omission, and a schema default is a value a caller can be handed without
    # asking for it. The fallback belongs in the handler, where a request
    # cannot edit it out.
    assert "default" not in schema


# ----- the lifecycle, through `invoke()` --------------------------------------


def test_create_then_get_project_round_trips_through_the_registry(
    registered: Store,
) -> None:
    created = data(call("create_project", {"name": "payments", "description": "the api"}))
    assert created["created"] is True
    project = created["project"]
    assert isinstance(project, dict)
    assert project["name"] == "payments"
    assert project["description"] == "the api"
    assert project["repo_count"] == 0
    assert project["last_activity_at"] is None

    fetched = data(call("get_project", {"project_id": project["project_id"]}))
    assert fetched["found"] is True
    detail = fetched["project"]
    assert isinstance(detail, dict)
    assert detail["project_id"] == project["project_id"]
    assert detail["name"] == "payments"
    assert detail["repos"] == []
    assert detail["sessions"] == []


def test_two_projects_may_share_a_name(registered: Store) -> None:
    """E1: `/work/api` and `/personal/api` are two projects, not one row.

    `upsert_workspace`, which D57 deleted, selected by `name` — so the second
    registration silently overwrote the first. Identity is `workspace.id`; a
    name is a label.
    """
    first = made(registered, "api")
    second = made(registered, "api")

    assert first != second
    assert {first, second} <= {row.id for row in registered.list_workspaces()}


def test_get_project_answers_a_missing_project_as_a_value(registered: Store) -> None:
    """Principle 5: absence is a field a page renders, never an exception."""
    assert data(call("get_project", {"project_id": "nope"})) == {
        "found": False,
        "project": None,
    }


def test_rename_project_relabels_and_a_missing_one_is_refused_as_a_value(
    registered: Store,
) -> None:
    """The three refusal conventions in `store/` are adapted to one here.

    `rename_project` raises `StoreError` for the reserved project and returns
    `None` for a missing one; `add_repo` raises for both. At this layer all of
    them become the same record — `{"...": False, "refused": "<why>"}` — because
    a consumer that has to branch on three shapes for one family of verbs will
    eventually branch on two of them and crash on the third. A raised
    `StoreError` would reach a page as `request failed` (`registry.py:69`),
    which is not a reason anything can render.
    """
    project_id = made(registered, "old")

    renamed = data(call("rename_project", {"project_id": project_id, "name": "new"}))
    assert renamed["renamed"] is True
    fresh = renamed["project"]
    assert isinstance(fresh, dict)
    assert fresh["name"] == "new"
    assert fresh["project_id"] == project_id

    absent = data(call("rename_project", {"project_id": "nope", "name": "new"}))
    assert absent["renamed"] is False
    assert absent["project"] is None
    assert "nope" in str(absent["refused"])


# ----- the reserved project refuses, and says so ------------------------------


def test_unassigned_refuses_rename(registered: Store) -> None:
    """E8, and the refusal is a value: `StoreError` would reach the consumer as
    `request failed`, and a page cannot draw a reason out of that."""
    answer = data(
        call("rename_project", {"project_id": UNASSIGNED_PROJECT_ID, "name": "mine"})
    )

    assert answer["renamed"] is False
    assert "Unassigned" in str(answer["refused"])
    reserved = registered.get_workspace(UNASSIGNED_PROJECT_ID)
    assert reserved is not None
    assert reserved.name != "mine"


def test_unassigned_refuses_add_repo(registered: Store, tmp_path: Path) -> None:
    """E7. The reserved project's allowlist may never be widened by hand:
    `_registered_roots("unassigned")` is what every *discovered* session's spawn
    is validated against, and D59 lands every unmatched session there."""
    repo = make_repo(tmp_path / "work" / "api")

    answer = data(
        call("add_repo", {"project_id": UNASSIGNED_PROJECT_ID, "root_path": str(repo)})
    )

    assert answer["added"] is False
    assert "Unassigned" in str(answer["refused"])
    assert registered.list_repos(UNASSIGNED_PROJECT_ID) == []


def test_add_repo_refuses_a_project_that_does_not_exist(
    registered: Store, tmp_path: Path
) -> None:
    """The second `StoreError` branch of the same verb, adapted to the same
    record — so "reserved" and "absent" are two reasons in one shape rather
    than one raise and one crash."""
    repo = make_repo(tmp_path / "work" / "api")

    answer = data(call("add_repo", {"project_id": "nope", "root_path": str(repo)}))

    assert answer["added"] is False
    assert answer["repo"] is None
    assert "nope" in str(answer["refused"])


# ----- `add_repo`: canonicalization, the probe, and D48's key -----------------


def test_add_repo_refuses_a_path_that_does_not_canonicalize(
    registered: Store, tmp_path: Path
) -> None:
    """E10. `store/` takes a connection and does no filesystem I/O, so this is
    the tool's job — and the refusal **names the path**, because a refusal a
    person cannot act on is the silence principle 5 refuses.

    Checked before the project is, so a typo in a path is reported as a path.
    """
    missing = tmp_path / "nowhere" / "api"

    answer = data(call("add_repo", {"project_id": "whatever", "root_path": str(missing)}))

    assert answer["added"] is False
    assert answer["repo"] is None
    assert str(missing) in str(answer["refused"])


def test_add_repo_refuses_a_path_that_is_not_a_repo_rather_than_storing_a_placeholder(
    registered: Store, tmp_path: Path
) -> None:
    """E23's refusal branch, and the reason it has to be a refusal.

    `git_common_dir` is D48's binding key. A directory that does not probe as a
    repo has none, and storing an empty one would register a row
    `find_repo_by_common_dir` can never match — so a session started there later
    binds to `Unassigned`, silently, in exactly the flow the next test asserts
    works. This is the branch that proves the guard bites; the next test is the
    branch that proves the happy path.
    """
    project_id = made(registered)
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    answer = data(call("add_repo", {"project_id": project_id, "root_path": str(plain)}))

    assert answer["added"] is False
    assert answer["repo"] is None
    assert str(plain) in str(answer["refused"])
    assert registered.list_repos(project_id) == []
    assert registered.find_repo_by_common_dir(str(plain / ".git")) is None


def test_add_repo_refuses_a_bare_repository(registered: Store, tmp_path: Path) -> None:
    """A bare repo has no working tree, so no session can have it as a `cwd`.
    `bind_cwd_to_repo` counts it as an anomaly and binds to `Unassigned`;
    registering one would put a path in §13's allowlist that nothing can spawn
    into."""
    project_id = made(registered)
    bare = tmp_path / "bare.git"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "-q", "--bare"],
        cwd=bare,
        env=git_env(),
        capture_output=True,
        check=True,
    )

    answer = data(call("add_repo", {"project_id": project_id, "root_path": str(bare)}))

    assert answer["added"] is False
    assert str(bare) in str(answer["refused"])
    assert registered.list_repos(project_id) == []


def test_a_ui_registered_repo_binds_a_discovered_session_to_that_project(
    registered: Store, tmp_path: Path
) -> None:
    """E23, end to end: the key `add_repo` probes is the key D48 binds on.

    The registration goes through `invoke()` and the binding goes through the
    shipped `bind_cwd_to_repo`; **nothing here passes a `git_common_dir` between
    them.** If the tool guessed the value, or stored the path it was handed
    instead of probing for it, this lands on `UNASSIGNED_PROJECT_ID` — the
    silent failure the refusal above exists to prevent.

    This is also the end of the inter-phase state in which every spawn is
    refused: until this verb existed nothing could register a repo, so
    `_registered_roots` was empty for every project.
    """
    project_id = made(registered)
    tree = make_repo(tmp_path / "work" / "payments-api")
    (tree / "src").mkdir()

    added = data(call("add_repo", {"project_id": project_id, "root_path": str(tree)}))
    assert added["added"] is True
    repo = added["repo"]
    assert isinstance(repo, dict)
    assert repo["git_common_dir"] == str(tree / ".git")

    binding = bind_cwd_to_repo(registered, str(tree / "src"))

    assert binding.workspace_id == project_id
    assert binding.repo_id == repo["repo_id"]
    assert binding.anomaly is None


def test_add_repo_from_a_subdirectory_registers_the_repo_root(
    registered: Store, tmp_path: Path
) -> None:
    """The path a person types is not always the repo.

    `repo_root` is what `bind_cwd_to_repo` resolves with, and registering the
    typed subdirectory instead would give one tree two `repo` rows under
    `ux_repo_path` — two identities for one `git_common_dir`.
    """
    project_id = made(registered)
    tree = make_repo(tmp_path / "work" / "payments-api")
    (tree / "src").mkdir()

    added = data(
        call("add_repo", {"project_id": project_id, "root_path": str(tree / "src")})
    )

    repo = added["repo"]
    assert isinstance(repo, dict)
    assert repo["root_path"] == str(tree)
    assert repo["name"] == "payments-api"


def test_list_repos_and_remove_repo_keep_the_repo_row(
    registered: Store, tmp_path: Path
) -> None:
    """E6: removing drops the project↔repo edge and **keeps** the row, so
    re-adding the same path rebinds the same id rather than minting a second."""
    project_id = made(registered)
    tree = make_repo(tmp_path / "work" / "payments-api")

    added = data(call("add_repo", {"project_id": project_id, "root_path": str(tree)}))
    repo = added["repo"]
    assert isinstance(repo, dict)
    repo_id = str(repo["repo_id"])

    rows = data(call("list_repos", {"project_id": project_id}))["repos"]
    assert isinstance(rows, list)
    assert [row["repo_id"] for row in rows] == [repo_id]
    assert rows[0]["root_path"] == str(tree)

    removed = data(call("remove_repo", {"project_id": project_id, "repo_id": repo_id}))
    assert removed["removed"] is True
    assert data(call("list_repos", {"project_id": project_id}))["repos"] == []
    assert registered.find_repo_by_common_dir(str(tree / ".git")) is not None

    again = data(call("add_repo", {"project_id": project_id, "root_path": str(tree)}))
    repeated = again["repo"]
    assert isinstance(repeated, dict)
    assert repeated["repo_id"] == repo_id


def test_removing_an_edge_that_is_not_there_is_false_and_not_a_crash(
    registered: Store,
) -> None:
    """The other branch of `remove_repo`, so the `True` above is a measurement
    rather than the only value the verb can return."""
    project_id = made(registered)

    answer = data(call("remove_repo", {"project_id": project_id, "repo_id": "nope"}))

    assert answer["removed"] is False


def test_get_project_carries_its_repos_and_its_sessions(
    registered: Store, tmp_path: Path
) -> None:
    """The detail the Projects page draws a row from, in one call.

    `repo_count` is a count of the repos this same answer carries, so the number
    in the header and the list beneath it cannot disagree — a second read could
    be one write behind. The key set is `project_workspace`'s, reused rather
    than restated, so the Projects list and this detail agree on a name.
    """
    from shepherd.core.states import Origin, Ownership

    project_id = made(registered)
    tree = make_repo(tmp_path / "work" / "payments-api")
    data(call("add_repo", {"project_id": project_id, "root_path": str(tree)}))
    session = registered.register_session(
        engine_session_id="eng-1",
        workspace_id=project_id,
        repo_id=None,
        cwd=str(tree),
        started_at=NOW,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )

    detail = data(call("get_project", {"project_id": project_id}))["project"]

    assert isinstance(detail, dict)
    assert detail["repo_count"] == 1
    repos = detail["repos"]
    sessions = detail["sessions"]
    assert isinstance(repos, list)
    assert isinstance(sessions, list)
    assert [row["root_path"] for row in repos] == [str(tree)]
    assert [row["session_id"] for row in sessions] == [session.id]
    assert detail["last_activity_at"] == NOW
