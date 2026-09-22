"""T3.1: the project verbs, reached the only way a consumer may reach them.

**Two seams, both the plan's.** The schemas are read off `build_project_tools()`
directly — a schema is a *value*, and a consumer's binding reads it before any
call is made — and every behavioural assertion goes through `invoke()` with the
shipped chokepoint installed, exactly as `web/` and `cli/` do (D19, D32, D35).
A tool that works when its handler is called directly and is unregistered,
mis-audienced or schema-mangled is red here rather than in a browser.

**`delete_project` is here now, and the seam it waited for is the reason.**
It shipped absent at T3.1: `writes.delete_project` took a `kill` callable and
called it from inside the lambda `Store._write` runs on the single writer thread
after `BEGIN IMMEDIATE`, while the real kill path's first statement is itself a
store write (`orchestration/lifecycle.py:126`). Phase 1's remediation withdrew
that verb and replaced it with two halves — `Store.plan_project_delete` (a pure
read, carrying the whole refusal) and `Store.commit_project_delete` (the commit,
which re-derives the decision inside its own transaction). The kill happens
**between** them, in this layer, against a callable injected at registration and
never handed to a `store/` verb.
`test_the_kill_runs_outside_the_store_transaction` is the load-bearing statement
of that: its killer writes to the store, which is exactly what the shipped kill
path does first, and which is what used to hang the process for good.

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
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint
from signals.conftest import git_env

from shepherd.core.runner import RunnerHandle, RunnerRefusal
from shepherd.core.states import Origin, Ownership
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
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


class Killer:
    """The injected kill, as a thing a test can both program and read back.

    It answers **whether the kill landed** — `Callable[[str], bool]`, the same
    shape `store/`'s own tests use — because the field it feeds
    (`DeleteOutcome.killed`) is *what the caller reports it actually killed*.
    The verb this replaced took `Callable[[str], None]`, which could not say,
    while the real kill path answers `no_pane(session_id)` for any session
    without a runner handle — which is every attached one.

    **A kill that returns `True` and touches no row is a claim, not an effect**,
    and the commit half refuses exactly that. So the default *lands* the kill
    the way production does — through `apply_stop_verdict`, whose single
    statement writes `ended_at` — and the store can then see for itself that
    the session stopped, because `running_sessions_for` is `ended_at IS NULL`.

    Set `lands` to a predicate returning `False` to drive the did-not-land
    branch; that is the negative control, and
    `test_delete_project_keeps_the_project_when_a_kill_does_not_land` uses it.
    The previous default returned `True` and wrote nothing, which made every
    KILL case here certify a world production never produces.
    """

    def __init__(self, store: Store | None = None) -> None:
        self.asked: list[str] = []
        self.store = store
        self.lands: Callable[[str], bool] = lambda _session_id: True

    def __call__(self, session_id: str) -> bool:
        self.asked.append(session_id)
        landed = self.lands(session_id)
        if landed and self.store is not None:
            self.store.apply_stop_verdict(
                session_id,
                Verdict(
                    stop_reason=StopReason.USER_EXITED,
                    bucket=Bucket.FINISHED,
                    why="the delete stopped it",
                    confidence=1.0,
                    decided_by=DecidedBy.MECHANICAL,
                    next_actions=(),
                    waiting_on=None,
                    missing=(),
                ),
                "2026-01-01T02:00:00Z",
                None,
            )
        return landed


@pytest.fixture()
def killer(store: Store) -> Killer:
    return Killer(store)


@pytest.fixture()
def registered(store: Store, killer: Killer) -> Store:
    """One registration per test, behind the shipped gate.

    `install_test_chokepoint` installs `build_authorizer` over a real
    `ApprovalStore` at `LEVEL_3` — the shipped gate, not a permissive stub — so
    the `local_destructive` verbs below cross the same authoriser production
    puts in front of them.
    """
    install_test_chokepoint()
    register_project_tools(
        store=store, kill=killer, publish=lambda event: None, now=lambda: NOW
    )
    return store


def running_session(store: Store, project_id: str, engine_session_id: str) -> str:
    """A session that is alive by the only definition `store/` uses:
    `ended_at IS NULL`, never `state = 'running'`."""
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=project_id,
        repo_id=None,
        cwd="/tmp",
        started_at=NOW,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    ).id


def ended_session(store: Store, project_id: str, engine_session_id: str) -> str:
    """One finished session, so `destroyed` is a measurement of the cascade
    rather than a list the running rows happen to fill."""
    session_id = running_session(store, project_id, engine_session_id)
    store.apply_stop_verdict(
        session_id=session_id,
        verdict=Verdict(
            stop_reason=StopReason.COMPLETED,
            bucket=Bucket.FINISHED,
            why="done",
            confidence=1.0,
            decided_by=DecidedBy.HEURISTIC,
            next_actions=(),
            waiting_on=None,
            missing=(),
        ),
        ended_at="2026-09-22T11:00:00.000Z",
        exit_code=0,
    )
    return session_id


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
    lines so a ninth verb is a failure here and not a silent addition — which
    is exactly how `set_project_description` arrived: the eighth, admitted.
    """
    assert PROJECT_TOOL_NAMES == (
        "create_project",
        "rename_project",
        "set_project_description",
        "delete_project",
        "add_repo",
        "remove_repo",
        "list_repos",
        "get_project",
    )
    tools = registered_tools()
    assert {name: tools[name].blast_class for name in PROJECT_TOOL_NAMES} == {
        "create_project": BlastClass.LOCAL_DESTRUCTIVE,
        "rename_project": BlastClass.LOCAL_WRITE,
        "set_project_description": BlastClass.LOCAL_WRITE,
        "delete_project": BlastClass.LOCAL_DESTRUCTIVE,
        "add_repo": BlastClass.LOCAL_DESTRUCTIVE,
        "remove_repo": BlastClass.LOCAL_WRITE,
        "list_repos": BlastClass.LOCAL_READ,
        "get_project": BlastClass.LOCAL_READ,
    }
    assert all(
        tools[name].audiences == frozenset({Audience.MASTER, Audience.HUMAN})
        for name in PROJECT_TOOL_NAMES
    )


def test_delete_project_is_registered_and_reachable(registered: Store) -> None:
    """The seventh verb, where T3.1 asserted an absence.

    That test — `test_delete_project_is_not_registered_and_the_reason_is_the
    _writer_thread` — was deleted deliberately rather than left to fail, which
    is what it asked its reader to do. The absence it recorded was real: the
    store verb it needed took a `kill` callable and ran it on the writer thread
    inside `BEGIN IMMEDIATE`. That verb no longer exists. The two halves that
    replaced it are what makes this line true, and the name is **reachable**
    here rather than merely present in a tuple, because `PROJECT_TOOL_NAMES`
    listing a name `registered_tools()` does not hold is a promise a consumer
    can read and cannot call.
    """
    assert "delete_project" in PROJECT_TOOL_NAMES
    assert "delete_project" in registered_tools()
    assert set(PROJECT_TOOL_NAMES) <= set(registered_tools())


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


def test_the_on_running_enum_is_on_running_itself(registered: Store) -> None:
    """The enum a `delete_project` schema must carry **is** `OnRunning`'s values.

    Typing the three strings is exactly how the plan's `["refuse", "kill",
    "orphan"]` went stale against `OnRunning.KILL == "kill_sessions"`, so this
    reads the enum on both sides. That makes it tautological about the
    *spelling* — it cannot tell you what the values are — and load-bearing about
    the *link*: it is the only thing that can tell you the schema and the enum
    have come apart.

    T3.1 asserted this against the **helper**, because the verb was blocked.
    It is now asserted against the schema `delete_project` actually carries —
    the helper's only consumer — because a derivation that is correct and
    unused proves nothing about the tool a binding reads.

    `on_running` is **not required**: omitting it is a thing a caller may do,
    and what it then gets is the handler's `REFUSE`, not a schema default.
    """
    from shepherd.toolsurface.tools_projects import on_running_schema

    definition = {tool.name: tool for tool in build_project_tools(registered)}["delete_project"]
    properties = definition.input_schema["properties"]
    required = definition.input_schema["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    assert required == ["project_id"]
    schema = properties["on_running"]
    assert isinstance(schema, dict)
    assert schema == dict(on_running_schema())
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


# ----- D61's delete: three choices, and the kill between the halves -----------


def test_set_project_description_changes_only_the_description(
    registered: Store,
) -> None:
    """GAP 3 through the registry — the verb that did not exist.

    `create_project` took a description and `rename_project` takes `name` only,
    so a description was write-once: the only way to fix a typo in one was to
    delete the project. A separate verb rather than a widened `rename_project`,
    because a verb called *rename* that edits a description is a verb whose name
    is wrong, and a two-field verb has to invent a spelling for "leave this one
    alone" at the one surface where clearing is a real intent.

    Omitting the field **clears** it. The schema requires `project_id` alone,
    and the handler reads an absent `description` as `None` — the same shape
    `create_project` already accepts for a project declared without one.
    """
    created = data(call("create_project", {"name": "api", "description": "the old one"}))
    project = created["project"]
    assert isinstance(project, dict)
    project_id = str(project["project_id"])

    changed = data(
        call(
            "set_project_description",
            {"project_id": project_id, "description": "the payments api"},
        )
    )
    assert changed["described"] is True
    assert changed["refused"] is None
    described = changed["project"]
    assert isinstance(described, dict)
    assert described["description"] == "the payments api"
    # The name is untouched — the half a widened rename risks.
    assert described["name"] == "api"

    cleared = data(call("set_project_description", {"project_id": project_id}))
    assert cleared["described"] is True
    assert isinstance(cleared["project"], dict)
    assert cleared["project"]["description"] is None


def test_set_project_description_refuses_the_reserved_and_the_missing_as_values(
    registered: Store,
) -> None:
    """Both negative answers in this family's one refusal shape.

    `store/` raises for the reserved project and answers `None` for a missing
    one; a raised `StoreError` reaches a page as "request failed", which is not
    a reason anything can draw (principle 5).
    """
    reserved = data(
        call(
            "set_project_description",
            {"project_id": UNASSIGNED_PROJECT_ID, "description": "Inbox"},
        )
    )
    assert reserved["described"] is False
    assert reserved["project"] is None
    assert "Unassigned" in str(reserved["refused"])

    missing = data(
        call("set_project_description", {"project_id": "w-nope", "description": "x"})
    )
    assert missing["described"] is False
    assert "w-nope" in str(missing["refused"])


def test_delete_project_with_no_on_running_refuses_a_running_project(
    registered: Store, killer: Killer
) -> None:
    """E13's default-refuse, **unskippable by omission**.

    The schema carries no `default`, so a caller that says nothing is not handed
    a value — the handler falls back to `OnRunning.REFUSE`, where a request
    cannot edit it out. The refusal carries the session ids because the dialog
    in Phase 9 renders its other two choices out of this record; a caller told
    only `False` has to ask a second question that can disagree with the first.
    """
    project_id = made(registered)
    live = running_session(registered, project_id, "eng-live")

    answer = data(call("delete_project", {"project_id": project_id}))

    assert answer["deleted"] is False
    assert answer["running"] == [live]
    assert "still running" in str(answer["refused"])
    assert killer.asked == [], "REFUSE must never reach the kill path"
    assert registered.get_workspace(project_id) is not None


def test_a_refused_delete_says_what_it_would_have_taken_and_what_it_can_stop(
    registered: Store, killer: Killer
) -> None:
    """GAP 1 and GAP 2 — the two things the first consumer of this verb needed
    and could not get, on the one record it reads before the button.

    **`doomed`.** `DeletePlan.doomed` never reached anyone: the handler read the
    plan's refusal and discarded the plan, so the dialog could say *"1 session
    is still running"* and could not say *"and the finished ones go with the
    project"*. The page derived that count itself, out of a second read — a copy
    of a store derivation, and a copy is what drifts.

    **`killable` / `unkillable`.** The shipped kill answers `no_pane(...)` for
    any session with no runner handle, which is every *attached* one, so
    `kill_sessions` on a project of discovered sessions **cannot succeed** and
    nothing said so in advance. A dialog that grays the choice needs to know
    before the click, so the split is on the record: `unkillable` is the
    sessions the kill path has no handle for, and it is the reason.
    """
    project_id = made(registered)
    attached = running_session(registered, project_id, "eng-attached")
    done = ended_session(registered, project_id, "eng-done")

    answer = data(call("delete_project", {"project_id": project_id}))

    assert answer["deleted"] is False
    assert answer["running"] == [attached]
    # Everything goes if the caller proceeds — the finished session included.
    assert sorted(str(row) for row in answer["doomed"]) == sorted([attached, done])
    # …and none of it can be stopped, because a registered-but-attached session
    # has no runner handle of ours.
    assert answer["killable"] == []
    assert answer["unkillable"] == [attached]
    assert registered.get_workspace(project_id) is not None


def test_a_session_with_a_pane_is_reported_killable(
    registered: Store, killer: Killer
) -> None:
    """The other branch of the split above, so `unkillable` is a measurement
    rather than a field that is always full.

    Killable is exactly `handle_for`'s question — does this session have a
    runner handle — because that is the one the shipped kill asks before it
    answers `no_pane(...)`.
    """
    project_id = made(registered)
    owned = running_session(registered, project_id, "eng-owned")
    registered.set_runner_handle(owned, RunnerHandle(runner="tmux", socket="shepherd", session_name="shepherd_1"))

    answer = data(call("delete_project", {"project_id": project_id}))

    assert answer["running"] == [owned]
    assert answer["killable"] == [owned]
    assert answer["unkillable"] == []


def test_delete_project_deletes_a_project_with_no_running_sessions(
    registered: Store, killer: Killer
) -> None:
    """The control for the refusal above — the other branch of the same gate.

    Same call, same absent `on_running`; the only difference is that nothing is
    running. Without it, `REFUSE` would be indistinguishable from a verb that
    refuses everything. `destroyed` names the finished session, because a person
    told nothing about the ended rows is not told what the delete took.
    """
    project_id = made(registered)
    done = ended_session(registered, project_id, "eng-done")

    answer = data(call("delete_project", {"project_id": project_id}))

    assert answer["deleted"] is True
    assert answer["refused"] is None
    assert answer["destroyed"] == [done]
    assert answer["killed"] == []
    assert answer["orphaned"] == []
    assert killer.asked == []
    assert registered.get_workspace(project_id) is None


def test_delete_project_kill_sessions_reports_what_the_kill_actually_did(
    registered: Store, killer: Killer
) -> None:
    """`killed` is what the caller **reports it killed**, and the kill is this
    layer's — never a callable handed to a `store/` verb."""
    project_id = made(registered)
    live = running_session(registered, project_id, "eng-live")
    done = ended_session(registered, project_id, "eng-done")

    answer = data(
        call(
            "delete_project",
            {"project_id": project_id, "on_running": OnRunning.KILL.value},
        )
    )

    assert killer.asked == [live]
    assert answer["deleted"] is True
    assert answer["killed"] == [live]
    assert sorted(str(row) for row in answer["destroyed"]) == sorted([live, done])
    assert registered.get_workspace(project_id) is None


def test_delete_project_keeps_the_project_when_a_kill_does_not_land(
    registered: Store, killer: Killer
) -> None:
    """The other branch of `KILL`, and the reason the callable returns a bool.

    A kill that did not land leaves a live agent running; deleting its row would
    leave it with nothing to show for itself. `commit_project_delete` re-derives
    the decision inside its own transaction and refuses — so this is also the
    statement that the commit half does not trust the plan it was handed.
    """
    project_id = made(registered)
    live = running_session(registered, project_id, "eng-live")
    killer.lands = lambda _session_id: False

    answer = data(
        call(
            "delete_project",
            {"project_id": project_id, "on_running": OnRunning.KILL.value},
        )
    )

    assert killer.asked == [live]
    assert answer["deleted"] is False
    assert answer["killed"] == []
    assert answer["running"] == [live]
    assert registered.get_workspace(project_id) is not None


def test_delete_project_treats_a_raising_kill_as_did_not_land(
    registered: Store, killer: Killer
) -> None:
    """A kill that **raises** must not escape the verb after real kills landed.

    `orchestration/lifecycle.py` states the contract deliberately — a failed
    kill's `RunnerRefusal` propagates, because a caller told "killed" over a
    session that is still alive has been told a false thing — and
    `runner/local.py` raises it for a **stale handle**: a row whose `ended_at`
    is still NULL while its pane is gone. That is the orphan case Shepherd
    exists to notice, and `plan.running` is exactly `ended_at IS NULL`, so such
    a row is what this loop hands to `kill`.

    Before the fix the exception left `delete_project` between the two store
    calls: the first session was already dead, `commit_project_delete` never
    ran, and `registry.py` flattened the escape to `GENERIC_ERROR` — a page
    reading "request failed" for a call that had just stopped a live agent,
    with no record of which sessions died.

    So: caught per session, counted (principle 5 — an unknown is counted, and
    `stop_failed` is the kind for a stop that did not), reported by name, and
    the store's own `ended_at` fact decides the delete. Three sessions, the
    second raising: the two that landed are named, the one that did not keeps
    the project.
    """
    project_id = made(registered)
    first = running_session(registered, project_id, "eng-1")
    second = running_session(registered, project_id, "eng-2")
    third = running_session(registered, project_id, "eng-3")

    def lands(session_id: str) -> bool:
        if session_id == second:
            raise RunnerRefusal("tmux refused")
        return True

    killer.lands = lands

    answer = data(
        call(
            "delete_project",
            {"project_id": project_id, "on_running": OnRunning.KILL.value},
        )
    )

    # Every session was asked, including the ones after the raise.
    assert killer.asked == [first, second, third]
    assert answer["deleted"] is False
    assert answer["killed"] == [first, third]
    assert answer["running"] == [second]
    assert answer["kill_failures"] == [
        {"session_id": second, "reason": "RunnerRefusal: tmux refused"}
    ]
    # The project is intact, and the one unknown is counted rather than
    # swallowed.
    assert registered.get_workspace(project_id) is not None
    assert registered.list_anomaly_counts()["stop_failed"] == 1


def test_delete_project_orphan_moves_the_living_and_severs_the_lineage(
    registered: Store, killer: Killer
) -> None:
    """P2 and the severed links, both projected.

    The survivor is a session in **another** project whose `retry_of` points
    into the doomed cohort — one of the two self-references `_sever_lineage`
    covers. `PRAGMA foreign_keys` is ON, so the reference is nulled rather than
    left to abort the cascade — and it is *reported*, because D61 says a delete
    forgets and a person is still owed the fact.
    """
    project_id = made(registered, "doomed")
    elsewhere = made(registered, "safe")
    parent = ended_session(registered, project_id, "eng-parent")
    live = running_session(registered, project_id, "eng-live")
    retry = running_session(registered, elsewhere, "eng-retry")
    registered.link_retry(retry, parent)

    answer = data(
        call(
            "delete_project",
            {"project_id": project_id, "on_running": OnRunning.ORPHAN.value},
        )
    )

    assert killer.asked == [], "ORPHAN moves sessions; it never kills them"
    assert answer["deleted"] is True
    assert answer["orphaned"] == [live]
    assert answer["destroyed"] == [parent]
    assert answer["severed"] == [{"session_id": retry, "column": "retry_of"}]
    survivor = registered.get_session(retry)
    assert survivor is not None
    assert survivor.retry_of is None
    moved = registered.get_session(live)
    assert moved is not None
    assert moved.workspace_id == UNASSIGNED_PROJECT_ID


def test_delete_project_refuses_the_reserved_project_as_a_value(
    registered: Store,
) -> None:
    """E9, in the one refusal shape this whole family carries."""
    answer = data(call("delete_project", {"project_id": UNASSIGNED_PROJECT_ID}))

    assert answer["deleted"] is False
    assert "Unassigned" in str(answer["refused"])
    assert registered.get_workspace(UNASSIGNED_PROJECT_ID) is not None


def test_delete_project_refuses_an_unknown_on_running_rather_than_guessing(
    registered: Store,
) -> None:
    """A value outside `OnRunning` is a refusal a page can draw, not a crash.

    JSON Schema's `enum` is not one of the two things a binding is guaranteed to
    carry through unchanged (D53), so the closed set is enforced at the seam —
    and the one thing it must never do is fall back to a destructive member.
    """
    project_id = made(registered)
    running_session(registered, project_id, "eng-live")

    answer = data(call("delete_project", {"project_id": project_id, "on_running": "kill"}))

    assert answer["deleted"] is False
    assert "kill" in str(answer["refused"])
    assert registered.get_workspace(project_id) is not None


def test_the_kill_runs_outside_the_store_transaction(
    registered: Store, killer: Killer
) -> None:
    """The reason this verb waited a phase, stated as a test that can fail.

    The killer here **writes to the store** — which is precisely what the
    shipped kill path does first (`orchestration/lifecycle.py:126`, where the
    write-before-kill order is what survives a crash). If the kill were reached
    from inside `Store._write`'s callable it would enqueue a job on the writer
    thread that is blocked waiting for it, and the writer has no timeout: the
    call never returns and every later write in the process hangs. So this is
    asserted on a **timeout**, not on an outcome — an assertion that cannot be
    made on the calling thread, because a deadlocked call never reaches it.

    It is the same reproduction the coordinator recorded against the old verb:
    *"DEADLOCK: delete_project did not return within 10s"*.
    """
    project_id = made(registered)
    live = running_session(registered, project_id, "eng-live")
    killer.lands = lambda session_id: bool(
        registered.set_app_state(f"kill.{session_id}", 1) or True
    )

    answer: dict[str, object] = {}

    def run() -> None:
        answer.update(
            data(
                call(
                    "delete_project",
                    {"project_id": project_id, "on_running": OnRunning.KILL.value},
                )
            )
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive(), (
        "delete_project did not return within 10s: the kill ran behind the writer"
    )
    assert answer["deleted"] is True
    assert answer["killed"] == [live]
    assert registered.get_app_state(f"kill.{live}") == 1


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


def test_a_repo_projection_names_every_project_that_holds_it(
    registered: Store, tmp_path: Path
) -> None:
    """GAP 4 — D60 made readable.

    The row says *"a repo path may belong to more than one project"*, and the
    page could not show it: nothing on the wire answered **which** projects hold
    this repo. `reads.projects_for_repo` has existed since T1.6 and had one
    caller, inside `bind_cwd_to_repo`. A page that wanted the answer had to ask
    per repo, which is the N+1 the projections were shaped to avoid — so it is
    read once for every repo and carried on the projection itself.

    Both read verbs carry it, because a detail page and a list are the same
    repo and must not disagree about who it is shared with.
    """
    tree = make_repo(tmp_path / "work" / "payments-api")
    work = made(registered, "work")
    personal = made(registered, "personal")
    for project_id in (work, personal):
        assert data(call("add_repo", {"project_id": project_id, "root_path": str(tree)}))[
            "added"
        ] is True

    listed = data(call("list_repos", {"project_id": work}))["repos"]
    assert isinstance(listed, list) and len(listed) == 1
    row = listed[0]
    assert isinstance(row, dict)
    # Every holder, this project included: "shared with" is the page's word for
    # the rest of the list, and a projection that pre-subtracted the current
    # project would make the same list mean two things in two places.
    assert sorted(str(name) for name in row["projects"]) == sorted([work, personal])

    detail = data(call("get_project", {"project_id": personal}))["project"]
    assert isinstance(detail, dict)
    repos = detail["repos"]
    assert isinstance(repos, list)
    assert sorted(str(name) for name in repos[0]["projects"]) == sorted([work, personal])

    # The control: a repo only one project holds says exactly that, so the
    # field is a measurement rather than a list that is always long.
    alone = make_repo(tmp_path / "work" / "lonely")
    data(call("add_repo", {"project_id": work, "root_path": str(alone)}))
    after = data(call("list_repos", {"project_id": work}))["repos"]
    assert isinstance(after, list)
    lonely = [r for r in after if isinstance(r, dict) and r["name"] == "lonely"][0]
    assert lonely["projects"] == [work]


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
