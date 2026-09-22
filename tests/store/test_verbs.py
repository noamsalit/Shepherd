"""T6: the verb surface (D33) and its threading model (ADR-7).

Integration seam: a real SQLite database under `tmp_path`, plus one threaded
case for P18. Nothing here writes SQL — that is the point of the suite.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import sqlite3
import threading
import typing
from pathlib import Path

import pytest

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.store import models, reads, writes
from shepherd.store.db import Store, StoreError, open_store
from shepherd.store.migrate import migrate

SQL_ISH_PARAMETERS = frozenset({"sql", "query", "statement", "where", "order_by", "params"})
SQL_ISH_VERBS = frozenset({"query", "execute", "executemany", "cursor", "connection", "transaction"})


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def public_verbs() -> list[tuple[str, object]]:
    return [
        (name, member)
        for name, member in inspect.getmembers(Store, inspect.isfunction)
        if not name.startswith("_")
    ]


def seeded_session(store: Store, engine_session_id: str = "eng-1") -> models.Session:
    workspace = store.create_project(name="shepherd", description=None)
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )


def test_no_verb_accepts_sql() -> None:
    """Rule 1 — expose verbs, not queries."""
    offenders: list[str] = []
    for name, member in public_verbs():
        if name in SQL_ISH_VERBS:
            offenders.append(f"Store.{name} is a query, not a verb")
        parameters = set(inspect.signature(member).parameters) & SQL_ISH_PARAMETERS
        offenders.extend(f"Store.{name} accepts {p!r}" for p in sorted(parameters))
    assert offenders == []
    assert "apply_fold_delta" in dict(public_verbs())


def test_no_verb_returns_a_driver_row() -> None:
    """Rule 2 — return dataclasses, never driver rows."""
    allowed_leaves = {str, int, float, bool, type(None), object, bytes}
    offenders: list[str] = []
    for name, member in public_verbs():
        hints = typing.get_type_hints(member)
        annotation = hints.get("return", type(None))
        for leaf in _leaf_types(annotation):
            if leaf in allowed_leaves or dataclasses.is_dataclass(leaf):
                continue
            offenders.append(f"Store.{name} returns {leaf!r}")
    assert offenders == []

    # …and the returns are really dataclasses, not a str-typed escape hatch.
    for verb in ("snapshot", "create_project", "upsert_repo", "register_session", "fleet"):
        leaves = _leaf_types(typing.get_type_hints(getattr(Store, verb))["return"])
        assert any(dataclasses.is_dataclass(leaf) for leaf in leaves), verb
    assert sqlite3.Row not in {
        leaf
        for _, member in public_verbs()
        for leaf in _leaf_types(typing.get_type_hints(member).get("return", type(None)))
    }


def _leaf_types(annotation: object) -> list[type]:
    origin = typing.get_origin(annotation)
    if origin is None:
        return [annotation] if isinstance(annotation, type) else []
    return [leaf for argument in typing.get_args(annotation) for leaf in _leaf_types(argument)]


def test_register_session_is_idempotent(store: Store) -> None:
    """P8 — one `session` row per engine session id, whoever saw it first."""
    first = seeded_session(store)
    second = seeded_session(store)
    assert second.id == first.id
    assert len(store.list_sessions()) == 1
    assert store.get_session_by_engine_id("eng-1") == first
    assert store.get_session_by_engine_id("eng-missing") is None


def test_register_session_fills_not_null_columns(store: Store) -> None:
    """F16 — an M1 caller never has to know §7's NOT NULL columns exist."""
    session = seeded_session(store)
    assert session.owner_id == "local"
    assert session.ephemeral is False
    assert session.depth == 0
    assert session.attempt == 1
    assert session.engine == "claude_code"
    assert session.origin is Origin.EXTERNAL
    assert session.ownership is Ownership.ATTACHED
    assert session.state is SessionState.STARTING
    assert session.tasks_done == 0
    assert session.tasks_total == 0
    assert session.active_subagents == 0
    assert session.repos_touched == ()
    assert session.title_source == "brief"


def test_apply_fold_delta_is_atomic(store: Store) -> None:
    session = seeded_session(store)

    updated = store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=SessionState.NEEDS_YOU,
            needs_you_reason="permission: Bash(git push)",
            last_event_at="2026-09-16T10:01:00Z",
            tasks_done=2,
            tasks_total=5,
            active_subagents=3,
            repos_touched=("repo-a", "repo-b"),
        ),
    )
    assert updated.state is SessionState.NEEDS_YOU
    assert updated.needs_you_reason == "permission: Bash(git push)"
    assert updated.tasks_done == 2
    assert updated.tasks_total == 5
    assert updated.repos_touched == ("repo-a", "repo-b")

    # None means *untouched*, never *cleared*.
    touched = store.apply_fold_delta(session.id, FoldDelta(model="claude-opus-4"))
    assert touched.needs_you_reason == "permission: Bash(git push)"
    assert touched.model == "claude-opus-4"

    # A delta that cannot be written leaves the row exactly as it was.
    with pytest.raises(StoreError):
        store.apply_fold_delta(session.id, FoldDelta(repo_id="no-such-repo", brief="half"))
    after = store.get_session(session.id)
    assert after is not None
    assert after.repo_id is None
    assert after.brief is None
    assert after.state is SessionState.NEEDS_YOU


def test_fleet_query_orders_by_state(store: Store) -> None:
    """§16: needs_you first, then running, then starting, then stopped."""
    workspace = store.create_project(name="shepherd", description=None)
    wanted: dict[str, SessionState] = {
        "eng-stopped": SessionState.STOPPED,
        "eng-needs": SessionState.NEEDS_YOU,
        "eng-starting": SessionState.STARTING,
        "eng-running": SessionState.RUNNING,
    }
    for engine_session_id, state in wanted.items():
        session = store.register_session(
            engine_session_id=engine_session_id,
            workspace_id=workspace.id,
            repo_id=None,
            cwd="/root/Shepherd",
            started_at="2026-09-16T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )
        store.apply_fold_delta(session.id, FoldDelta(state=state))

    rows = store.fleet()
    assert [row.state for row in rows] == [
        SessionState.NEEDS_YOU,
        SessionState.RUNNING,
        SessionState.STARTING,
        SessionState.STOPPED,
    ]
    assert rows[0].engine_session_id == "eng-needs"
    assert rows[0].workspace_name == "shepherd"

    assert [s.engine_session_id for s in store.list_sessions(state=SessionState.RUNNING)] == [
        "eng-running"
    ]
    assert len(store.list_sessions(workspace_id=workspace.id)) == 4
    assert store.list_sessions(workspace_id="nope") == []


def test_repo_root_path_is_unique(store: Store) -> None:
    store.create_project(name="shepherd", description=None)
    first = store.upsert_repo(
        root_path="/root/Shepherd",
        name="Shepherd",
        vcs_remote=None,
        git_common_dir="/root/Shepherd/.git",
    )
    again = store.upsert_repo(
        root_path="/root/Shepherd",
        name="Shepherd",
        vcs_remote="github.com/example-org/shepherd",
        git_common_dir="/root/Shepherd/.git",
    )
    assert again.id == first.id
    assert again.vcs_remote == "github.com/example-org/shepherd"

    assert store.find_repo_by_common_dir("/root/Shepherd/.git") == again
    assert store.find_repo_by_common_dir("/elsewhere/.git") is None

    # Two projects may share a name now (E1), so the list is read by name and
    # the seeded `Unassigned` leads it under BINARY collation (N2/E22).
    store.create_project(name="shepherd", description=None)
    assert [w.name for w in store.list_workspaces()] == ["Unassigned", "shepherd", "shepherd"]


def test_app_state_roundtrips_json(store: Store) -> None:
    store.set_app_state("autonomy_level", 2)
    store.set_app_state("master_session_id", "01JABCDEF")
    store.set_app_state("next_actions", [{"text": "retry", "kind": "retry"}])

    assert store.get_app_state("autonomy_level") == 2
    assert store.get_app_state("master_session_id") == "01JABCDEF"
    assert store.get_app_state("next_actions") == [{"text": "retry", "kind": "retry"}]
    assert store.get_app_state("never_set") is None

    store.set_app_state("autonomy_level", 3)
    assert store.get_app_state("autonomy_level") == 3

    store.bump_anomaly("git_no_remote")
    store.bump_anomaly("git_no_remote")
    store.bump_anomaly("git_bare_repo")
    assert store.get_app_state("anomaly.git_no_remote") == 2
    assert store.get_app_state("anomaly.git_bare_repo") == 1


def test_liveness_sweep_returns_sessions_with_a_pid(store: Store) -> None:
    """Decision pressure 7's read side — both inputs to `process_liveness`."""
    with_pid = seeded_session(store, "eng-live")
    without_pid = seeded_session(store, "eng-hooked")
    store.apply_fold_delta(with_pid.id, FoldDelta(pid=4110260, proc_start="900123"))

    assert store.sessions_with_liveness_inputs() == [(with_pid.id, 4110260, "900123")]

    # An ended session is no longer swept.
    store.apply_fold_delta(
        with_pid.id, FoldDelta(state=SessionState.STOPPED, ended_at="2026-09-16T11:00:00Z")
    )
    assert store.sessions_with_liveness_inputs() == []
    assert store.get_session(without_pid.id) is not None


def test_store_writes_are_serialised_under_threads(store: Store) -> None:
    """P18 — 20 threads x 50 deltas, one writer thread, no OperationalError."""
    session = seeded_session(store)
    errors: list[BaseException] = []

    def hammer(worker: int) -> None:
        try:
            for index in range(50):
                store.apply_fold_delta(
                    session.id,
                    FoldDelta(last_event_at=f"2026-09-16T10:{worker:02d}:{index:02d}Z"),
                )
        except BaseException as error:  # noqa: BLE001 - the test is about there being none
            errors.append(error)

    threads = [threading.Thread(target=hammer, args=(worker,)) for worker in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(store.writer_thread_idents()) == 1
    assert store.writer_thread_idents() != {threading.get_ident()}
    assert len(store.list_sessions()) == 1


def test_reads_use_a_thread_local_connection(store: Store) -> None:
    """ADR-7 — an HTTP thread never queues behind the writer."""
    seeded_session(store)
    # Keyed by a caller-supplied index, never by threading.get_ident(): CPython
    # recycles idents once a short-lived thread has been joined, so two workers
    # that never coexist can report the same ident and silently collapse two
    # observations into one. That made this assertion fail ~1 run in 6 while
    # `Store` was correct throughout (BLOCKER-T6-2).
    seen: dict[int, int] = {}
    worker_count = 4
    # The barrier is the other half of the fix: it forces all workers to be alive
    # at the same moment, so "one connection per thread" is actually exercised
    # concurrently rather than being satisfied by threads that ran one at a time.
    gate = threading.Barrier(worker_count)

    def read(index: int, *, wait: bool) -> None:
        if wait:
            gate.wait(timeout=10)
        assert len(store.list_sessions()) == 1
        seen[index] = store.reader_connection_id()

    read(0, wait=False)
    threads = [
        threading.Thread(target=read, args=(index,), kwargs={"wait": True})
        for index in range(1, worker_count + 1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == worker_count + 1
    assert len(set(seen.values())) == worker_count + 1
    # The same thread keeps its connection.
    before = store.reader_connection_id()
    assert len(store.list_sessions()) == 1
    assert store.reader_connection_id() == before


def test_close_drains_and_joins_the_writer(tmp_path: Path) -> None:
    """F15 — daemon teardown needs exactly this."""
    opened = open_store(tmp_path / "data" / "shepherd.db")
    workspace = opened.create_project(name="shepherd", description=None)
    for index in range(25):
        opened.register_session(
            engine_session_id=f"eng-{index}",
            workspace_id=workspace.id,
            repo_id=None,
            cwd="/root/Shepherd",
            started_at="2026-09-16T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        )

    opened.close()

    assert opened.writer_is_alive() is False
    with pytest.raises(RuntimeError):
        opened.create_project(name="late", description=None)
    opened.close()  # idempotent

    reopened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        assert len(reopened.list_sessions()) == 25
    finally:
        reopened.close()


def test_snapshot_roundtrips_the_fold_identity_fields(store: Store) -> None:
    """BLOCKER-T6-1, closed: `observed_at` makes RD8's per-field recency rule
    live at runtime instead of only at the pure seam, and the three identity
    sets make subagent pairing and the task-id intersection survive a restart.
    §7 is widened by four columns (plan gap M16)."""
    session = seeded_session(store)
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            observed_at="2026-09-16T10:05:00Z",
            live_subagent_ids=frozenset({"a2", "a1"}),
            created_task_ids=frozenset({"t1", "t2", "t3"}),
            completed_task_ids=frozenset({"t2"}),
        ),
    )
    snapshot = store.snapshot(session.id)
    assert snapshot is not None
    assert snapshot.observed_at == "2026-09-16T10:05:00Z"
    assert snapshot.live_subagent_ids == frozenset({"a1", "a2"})
    assert snapshot.created_task_ids == frozenset({"t1", "t2", "t3"})
    assert snapshot.completed_task_ids == frozenset({"t2"})

    # An empty set is a real value, not "untouched": a subagent's stop empties
    # the live set, and that has to be what the next reader sees.
    store.apply_fold_delta(session.id, FoldDelta(live_subagent_ids=frozenset()))
    reread = store.snapshot(session.id)
    assert reread is not None
    assert reread.live_subagent_ids == frozenset()
    assert reread.created_task_ids == frozenset({"t1", "t2", "t3"})


def test_snapshot_is_the_folds_prior_input(store: Store) -> None:
    session = seeded_session(store)
    assert store.snapshot("no-such-session") is None

    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=SessionState.RUNNING,
            brief="ship M1",
            repos_touched=("repo-a",),
            last_event_at="2026-09-16T10:02:00Z",
        ),
    )
    snapshot = store.snapshot(session.id)
    assert snapshot is not None
    assert snapshot.session_id == session.id
    assert snapshot.engine_session_id == "eng-1"
    assert snapshot.state is SessionState.RUNNING
    assert snapshot.brief == "ship M1"
    assert snapshot.repos_touched == ("repo-a",)
    assert snapshot.title_source == "brief"
    assert snapshot.live_subagent_ids == frozenset()


def test_register_session_mints_its_id_from_an_injected_clock(store: Store) -> None:
    """BLOCKER-T12-2: the ulid was the one value in a replayed row that could
    not be byte-identical run to run, because `register_session` always took
    the wall clock. With `now` threaded through, the id's 10-character time
    component is the injected millisecond, so a golden fixture can assert the
    decoded prefix instead of keying the table on the engine's session id.

    `01M2G8CJX7` is Crockford base32 of 1789399550887 ms — the `_epoch` of a
    real captured event, encoded independently of `core/ids.py`.
    """
    workspace = store.create_project(name="shepherd", description=None)
    session = store.register_session(
        engine_session_id="eng-replay",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-14T15:25:50.887Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
        now=1789399550.887,
    )

    assert session.id[:10] == "01M2G8CJX7"
    assert len(session.id) == 26

    # No clock injected is still the wall-clock lane, and still sorts later.
    wall = store.register_session(
        engine_session_id="eng-now",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    assert wall.id > session.id


def test_anomaly_counts_are_enumerated_not_guessed_at(store: Store) -> None:
    """BLOCKER T14-3: a reader that asks for one key per `AnomalyKind` member
    can only ever see the kinds it already expected. Principle 5 says an unknown
    is counted *and shown*, so the store enumerates what was actually counted."""
    assert store.list_anomaly_counts() == {}

    store.bump_anomaly("unknown_registry_status")
    store.bump_anomaly("unknown_registry_status")
    store.bump_anomaly("tool_blocked_by_hook")
    store.set_app_state("discovery_status", {"hooks": "absent"})

    assert store.list_anomaly_counts() == {
        "tool_blocked_by_hook": 1,
        "unknown_registry_status": 2,
    }


def test_list_repos_enumerates_one_workspaces_registered_repos(store: Store) -> None:
    """T11-1: §13's allowlist is a population of **repos**, so a verb must enumerate it.

    `find_repo_by_common_dir` answers "which repo is this one directory", which
    is D48's *binding* question. Admission asks D22's other one — *what is
    registered at all* — and no verb answered it, so `admission.py` fell back to
    `workspace.root_path`, the one column the schema says is "only where
    the removed scanner started looking; repos may live anywhere (D22)".

    The repo below that lives **outside** its workspace root is the case that
    matters: it is the normal case for any repo not nested under the root, and
    it is invisible to every other read verb.
    """
    inside = store.create_project(name="inside", description=None)
    other = store.create_project(name="other", description=None)
    for workspace_id, root_path, name in (
        (inside.id, "/srv/work/api", "api"),
        (inside.id, "/elsewhere/frontend", "frontend"),
        (other.id, "/srv/other/tools", "tools"),
    ):
        store.add_repo(
            workspace_id=workspace_id,
            root_path=root_path,
            name=name,
            git_common_dir=f"{root_path}/.git",
            vcs_remote=None,
        )

    assert [repo.root_path for repo in store.list_repos(inside.id)] == [
        "/elsewhere/frontend",
        "/srv/work/api",
    ]
    assert [repo.name for repo in store.list_repos(other.id)] == ["tools"]
    assert store.list_repos("no-such-workspace") == []

    # The rows are whole `Repo` records, not paths: the verb returns the
    # dataclass every other read verb returns (D33), `active` included.
    (frontend,) = [r for r in store.list_repos(inside.id) if r.name == "frontend"]
    assert frontend.root_path == "/elsewhere/frontend" and frontend.active is True


def test_nothing_deactivates_a_repo_so_list_repos_needs_no_active_filter() -> None:
    """Why `list_repos` returns **every** registered repo, and what would change it.

    §13's allowlist ought to narrow when a repo is removed, and `repo.active`
    is the column for it — but no verb in `store/` ever clears it. `upsert_repo`
    sets `active = 1` and nothing anywhere writes `0`, so an `active = 1` filter
    inside `list_repos` would be a branch **no test can reach**: D33 leaves a
    caller no connection to reach past the verb surface and set it. An
    unreachable check is this repo's dominant defect wearing a safety jacket —
    it reports success without ever having been asked a question.

    This test is therefore the tripwire rather than the filter: the day a verb
    can write `active = 0`, it goes red and names what to do about it.
    """
    package = Path(models.__file__).parent
    assignments = [
        (path.name, match.group(0))
        for path in sorted(package.glob("*.py"))
        for match in re.finditer(r"active\s*=\s*(\d+)", path.read_text(encoding="utf-8"))
    ]
    sql = sorted(
        (name, text) for name, text in assignments if name in {"writes.py", "reads.py"}
    )
    # Arrival before absence: the scan really did read the write that sets it.
    assert sql == [("writes.py", "active = 1")], sql
    assert all(text.endswith("1") for _, text in assignments), assignments


# ----- T1.2: the project vocabulary (§3 D57) --------------------------------


def test_the_reserved_project_id_has_one_definition_site() -> None:
    """ADR-P2. `store.models` is the one place the literal is written.

    `tests/boundaries/test_one_definition_site.py` is the rule; this is the
    name that rule protects.
    """
    assert models.UNASSIGNED_PROJECT_ID == "unassigned"


def test_on_running_names_the_three_choices_the_page_offers() -> None:
    """The delete state machine's third axis, as an enum rather than a string.

    The tool schema puts these in an `enum`, so a fourth spelling is refused
    before the handler; this asserts the three the schema will be built from.
    """
    assert [choice.value for choice in models.OnRunning] == [
        "refuse",
        # Not a bare `"kill"`: tmux resolves an unambiguous command-name prefix,
        # so `kill` reaches `kill-server`, and
        # `tests/boundaries/test_tmux_blast_radius.py` refuses any string
        # constant in `src/` that `is_server_teardown` answers True for. The
        # value was the collision, not the vocabulary — `kill_session` has been
        # a string constant in `src/` since M3 and the same guard accepts it.
        "kill_sessions",
        "orphan",
    ]


def test_a_delete_outcome_carries_every_field_the_refusal_needs() -> None:
    """`delete_project` answers with one frozen record, never a bare bool.

    The Projects page renders the three choices *from the refusal* (E13), so
    `refused` and `running` are part of the answer and not a log line.
    """
    outcome = models.DeleteOutcome(
        deleted=False, refused="a reason", running=("s1",), killed=(), orphaned=()
    )
    assert (outcome.deleted, outcome.refused, outcome.running) == (False, "a reason", ("s1",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.deleted = True  # type: ignore[misc]


def test_a_workspace_carries_a_description_and_no_root_path() -> None:
    """D57: a project is a label plus a description; paths belong to repos."""
    fields = {field.name for field in dataclasses.fields(models.Workspace)}
    assert "description" in fields
    assert "root_path" not in fields


def test_a_repo_no_longer_carries_the_project_it_belongs_to() -> None:
    """The join table owns that edge now, and a repo may sit in two projects."""
    fields = {field.name for field in dataclasses.fields(models.Repo)}
    assert "workspace_id" not in fields


# ----- T1.3: the project read verbs, at the connection seam ------------------
#
# These read tests take a `sqlite3.Connection` directly rather than a `Store`,
# because that is the interface `reads.py` presents (ADR-7): the connection
# never leaves `store/`, and a read verb's contract is "rows in, dataclasses
# out". Rows are planted with literal SQL rather than through `writes.py` so
# the expected values come from an independent source of truth — a fixture
# built by the write verbs would recompute the answer the way the read verb
# does.


@pytest.fixture()
def connection(tmp_path: Path) -> typing.Iterator[sqlite3.Connection]:
    db_path = tmp_path / "reads" / "shepherd.db"
    db_path.parent.mkdir(parents=True)
    migrate(db_path)
    opened = sqlite3.connect(db_path)
    opened.row_factory = sqlite3.Row
    opened.execute("PRAGMA foreign_keys=ON")
    try:
        yield opened
    finally:
        opened.close()


def plant_project(connection: sqlite3.Connection, workspace_id: str, name: str) -> None:
    connection.execute(
        "INSERT INTO workspace (id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (workspace_id, name, None, "2026-09-21T00:00:00Z"),
    )


def plant_repo(
    connection: sqlite3.Connection, repo_id: str, root_path: str, *, in_projects: tuple[str, ...]
) -> None:
    connection.execute(
        "INSERT INTO repo (id, name, root_path, git_common_dir, added_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (repo_id, Path(root_path).name, root_path, f"{root_path}/.git", "2026-09-21T00:00:00Z"),
    )
    for workspace_id in in_projects:
        connection.execute(
            "INSERT INTO project_repo (workspace_id, repo_id, added_at) VALUES (?, ?, ?)",
            (workspace_id, repo_id, "2026-09-21T00:00:00Z"),
        )


def plant_session(
    connection: sqlite3.Connection,
    session_id: str,
    workspace_id: str,
    *,
    started_at: str,
    last_event_at: str | None = None,
    ended_at: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at,"
        " state, last_event_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            workspace_id,
            str(Origin.EXTERNAL.value),
            str(Ownership.ATTACHED.value),
            "claude_code",
            started_at,
            str(SessionState.STOPPED.value if ended_at else SessionState.RUNNING.value),
            last_event_at,
            ended_at,
        ),
    )


def test_get_workspace_answers_one_row_or_none(connection: sqlite3.Connection) -> None:
    plant_project(connection, "w-api", "api")

    found = reads.get_workspace(connection, "w-api")
    assert found is not None
    assert (found.id, found.name, found.description) == ("w-api", "api", None)

    # The negative control: an id nobody planted answers `None` rather than
    # raising or handing back the first row it found.
    assert reads.get_workspace(connection, "w-nope") is None

    seeded = reads.get_workspace(connection, models.UNASSIGNED_PROJECT_ID)
    assert seeded is not None and seeded.name == "Unassigned"


def test_list_repos_reads_the_join_table_and_not_a_column(
    connection: sqlite3.Connection,
) -> None:
    """A repo belongs to a project through `project_repo` now, and may belong
    to two. The negative control is the third repo: it is registered to `w-web`
    alone, so a join that lost its `WHERE` would return it here.
    """
    plant_project(connection, "w-api", "api")
    plant_project(connection, "w-web", "web")
    plant_repo(connection, "r-shared", "/srv/shared", in_projects=("w-api", "w-web"))
    plant_repo(connection, "r-api", "/srv/api", in_projects=("w-api",))
    plant_repo(connection, "r-web", "/srv/web", in_projects=("w-web",))

    assert [r.root_path for r in reads.list_repos(connection, "w-api")] == [
        "/srv/api",
        "/srv/shared",
    ]
    assert [r.root_path for r in reads.list_repos(connection, "w-web")] == [
        "/srv/shared",
        "/srv/web",
    ]
    assert reads.list_repos(connection, models.UNASSIGNED_PROJECT_ID) == []


def test_projects_for_repo_names_every_project_holding_it(
    connection: sqlite3.Connection,
) -> None:
    plant_project(connection, "w-api", "api")
    plant_project(connection, "w-web", "web")
    plant_repo(connection, "r-shared", "/srv/shared", in_projects=("w-web", "w-api"))
    plant_repo(connection, "r-lonely", "/srv/lonely", in_projects=())

    assert reads.projects_for_repo(connection, "r-shared") == ["w-api", "w-web"]
    # D59's input: a repo in no project at all, which is not an error.
    assert reads.projects_for_repo(connection, "r-lonely") == []
    assert reads.projects_for_repo(connection, "r-nope") == []


def test_project_last_activity_is_derived_from_sessions(
    connection: sqlite3.Connection,
) -> None:
    """ADR-P4: the column exists and nothing writes it, so the answer is read
    off the sessions. The later of the two rows wins, and `last_event_at` beats
    `started_at` — the negative control is `w-quiet`, which has no session and
    is therefore **absent** rather than present with a null.
    """
    plant_project(connection, "w-api", "api")
    plant_project(connection, "w-quiet", "quiet")
    plant_session(
        connection, "s-old", "w-api", started_at="2026-01-01T00:00:00Z",
        last_event_at="2026-01-02T00:00:00Z",
    )
    plant_session(connection, "s-new", "w-api", started_at="2026-03-01T00:00:00Z")

    assert reads.project_last_activity(connection) == {"w-api": "2026-03-01T00:00:00Z"}


def test_repo_counts_answers_every_project_in_one_statement(
    connection: sqlite3.Connection,
) -> None:
    """M4: the Projects page's `repo_count` is one `GROUP BY`, never an N+1
    loop over `list_repos`. Counted through a tracing connection, because
    "one query" is a claim no assertion on the *result* can make.
    """
    plant_project(connection, "w-api", "api")
    plant_project(connection, "w-web", "web")
    plant_project(connection, "w-quiet", "quiet")
    plant_repo(connection, "r-shared", "/srv/shared", in_projects=("w-api", "w-web"))
    plant_repo(connection, "r-api", "/srv/api", in_projects=("w-api",))

    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        counts = reads.repo_counts(connection)
    finally:
        connection.set_trace_callback(None)

    assert counts == {"w-api": 2, "w-web": 1}
    assert len(statements) == 1, statements


def test_running_sessions_for_returns_only_the_unfinished_ones(
    connection: sqlite3.Connection,
) -> None:
    """What `delete_project` refuses on. The negative control is `s-done`: it
    has an `ended_at`, so a verb that forgot the clause would name it as a
    reason to refuse a delete that should have gone through.
    """
    plant_project(connection, "w-api", "api")
    plant_project(connection, "w-web", "web")
    plant_session(connection, "s-live", "w-api", started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", "w-api", started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )
    plant_session(connection, "s-elsewhere", "w-web", started_at="2026-01-01T00:00:00Z")

    assert [s.id for s in reads.running_sessions_for(connection, "w-api")] == ["s-live"]
    assert reads.running_sessions_for(connection, models.UNASSIGNED_PROJECT_ID) == []


def test_unassigned_leads_the_ordered_project_list(connection: sqlite3.Connection) -> None:
    """E22/N2 — the measured fact, pinned so the next reader meets it as a
    documented consequence rather than as a surprise.

    `list_workspaces` already carries `ORDER BY name` (`reads.py:102`) and is
    **unchanged** by this plan. Under BINARY collation an upper-case `U` sorts
    before every lower-case letter, so the seeded `"Unassigned"` leads the list
    and `list_workspaces()[0]` is the reserved project — never the one the
    caller meant. A tiebreak would repair nothing; selecting by name or by a
    captured id is the repair (T1.5).
    """
    for workspace_id, name in (("w-api", "api"), ("w-pay", "payments-api"), ("w-shep", "shepherd")):
        plant_project(connection, workspace_id, name)

    assert [w.name for w in reads.list_workspaces(connection)] == [
        "Unassigned",
        "api",
        "payments-api",
        "shepherd",
    ]


# ----- T1.4: the project lifecycle writes -----------------------------------


def running_ids(connection: sqlite3.Connection, workspace_id: str) -> list[str]:
    return [
        str(row["id"])
        for row in connection.execute(
            "SELECT id FROM session WHERE workspace_id = ? AND ended_at IS NULL", (workspace_id,)
        )
    ]


def never_kills(session_id: str) -> None:
    raise AssertionError(f"the kill path was reached for {session_id!r} and must not have been")


def test_two_projects_may_share_a_name(connection: sqlite3.Connection) -> None:
    """E1 — `/work/api` and `/personal/api` are two projects, not one.

    **Shown red against today's code first.** `upsert_workspace`'s body is
    keyed by `name` (`SELECT * FROM workspace WHERE name = ?`), so the second
    call returned the first row's id and overwrote its `root_path` — measured,
    against a 001→003 database, before this landed:
    `same id? True | rows named api: 1 | /work/api root became: /personal/api`.
    Identity is `workspace.id`; names are labels (D57).
    """
    work = writes.create_project(connection, name="api", description="the work one")
    personal = writes.create_project(connection, name="api", description=None)

    assert work.id != personal.id
    assert (work.name, personal.name) == ("api", "api")
    assert work.description == "the work one" and personal.description is None
    assert sorted(w.id for w in reads.list_workspaces(connection) if w.name == "api") == sorted(
        [work.id, personal.id]
    )


def test_unassigned_refuses_rename(connection: sqlite3.Connection) -> None:
    """E8. The negative control is the second half: an ordinary project renames,
    so the refusal is the reserved id and not a rename verb that never works.
    """
    with pytest.raises(StoreError):
        writes.rename_project(
            connection, workspace_id=models.UNASSIGNED_PROJECT_ID, name="Inbox"
        )
    still = reads.get_workspace(connection, models.UNASSIGNED_PROJECT_ID)
    assert still is not None and still.name == "Unassigned"

    project = writes.create_project(connection, name="api", description=None)
    renamed = writes.rename_project(connection, workspace_id=project.id, name="payments-api")
    assert renamed is not None and renamed.name == "payments-api"
    # A project that does not exist is absent, not forbidden: `None`, no raise.
    assert writes.rename_project(connection, workspace_id="w-nope", name="x") is None


def test_unassigned_refuses_add_repo(connection: sqlite3.Connection) -> None:
    """E7, and it is §13's allowlist that makes it a refusal rather than a
    preference: every discovered repo binds to `unassigned` (D59), so letting
    repos be *registered* there would make its allowlist every repo the machine
    has ever seen.
    """
    with pytest.raises(StoreError):
        writes.add_repo(
            connection,
            workspace_id=models.UNASSIGNED_PROJECT_ID,
            root_path="/srv/api",
            name="api",
            git_common_dir="/srv/api/.git",
            vcs_remote=None,
        )
    assert reads.list_repos(connection, models.UNASSIGNED_PROJECT_ID) == []

    project = writes.create_project(connection, name="api", description=None)
    added = writes.add_repo(
        connection,
        workspace_id=project.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote=None,
    )
    assert [r.id for r in reads.list_repos(connection, project.id)] == [added.id]


def test_unassigned_refuses_delete(connection: sqlite3.Connection) -> None:
    """E9 — and it answers with a `DeleteOutcome`, never a raise: the page
    renders the refusal, and an exception is not something a card can draw.
    """
    outcome = writes.delete_project(
        connection,
        workspace_id=models.UNASSIGNED_PROJECT_ID,
        on_running=models.OnRunning.REFUSE,
        kill=never_kills,
    )
    assert outcome.deleted is False
    assert outcome.refused is not None and "Unassigned" in outcome.refused
    assert reads.get_workspace(connection, models.UNASSIGNED_PROJECT_ID) is not None


def test_re_adding_an_orphaned_path_rebinds_the_same_repo_row(
    connection: sqlite3.Connection,
) -> None:
    """E6 — `ux_repo_path` is the identity, so a repo removed from a project and
    added again is the **same row**, and D48's binding key survives with it.

    This is what `test_upsert_workspace_updates_a_moved_root_path` used to
    protect, on the verb that replaced it.
    """
    first = writes.create_project(connection, name="api", description=None)
    repo_row = writes.add_repo(
        connection,
        workspace_id=first.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote=None,
    )
    assert writes.remove_repo(connection, workspace_id=first.id, repo_id=repo_row.id) is True
    # The repo row is **kept** — orphaned, not deleted, or D48's identity would
    # be minted afresh and every historical session would lose its repo.
    assert reads.find_repo_by_common_dir(connection, "/srv/api/.git") is not None
    assert reads.projects_for_repo(connection, repo_row.id) == []

    second = writes.create_project(connection, name="payments", description=None)
    again = writes.add_repo(
        connection,
        workspace_id=second.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote="github.com/example-org/api",
    )
    assert again.id == repo_row.id
    assert again.vcs_remote == "github.com/example-org/api"
    assert writes.remove_repo(connection, workspace_id=second.id, repo_id="r-nope") is False


def test_delete_refuses_by_default_and_names_the_running_sessions(
    connection: sqlite3.Connection,
) -> None:
    """E13 — a delete while a session is mid-turn. The refusal carries the ids,
    because the page builds the three choices out of *this record* rather than
    going back and asking a second question that can disagree with the first.
    """
    project = writes.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", project.id, started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )

    outcome = writes.delete_project(
        connection, workspace_id=project.id, on_running=models.OnRunning.REFUSE, kill=never_kills
    )
    assert outcome.deleted is False
    assert outcome.running == ("s-live",)
    assert outcome.refused is not None and "1" in outcome.refused
    assert reads.get_workspace(connection, project.id) is not None


def test_delete_with_kill_stops_them_then_cascades(connection: sqlite3.Connection) -> None:
    """D61 — the kill happens **through the caller's kill path**, before the
    cascade. `store/` does not learn about runners; it is handed a callable.
    """
    project = writes.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    connection.execute(
        "INSERT INTO mailbox_message (id, session_id, idempotency_key, body, origin, queued_at)"
        " VALUES ('m-1', 's-live', 'k1', 'hi', 'user_ui', '2026-01-01T00:00:00Z')"
    )
    killed: list[str] = []

    outcome = writes.delete_project(
        connection,
        workspace_id=project.id,
        on_running=models.OnRunning.KILL,
        kill=killed.append,
    )
    assert (outcome.deleted, outcome.killed) == (True, ("s-live",))
    assert killed == ["s-live"]
    assert reads.get_workspace(connection, project.id) is None
    assert connection.execute("SELECT COUNT(*) FROM mailbox_message").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 0


def test_delete_with_orphan_moves_them_to_unassigned(connection: sqlite3.Connection) -> None:
    """D61's third choice. The sessions **survive and stay visible**: `fleet()`
    is an INNER JOIN on `workspace`, so a session left pointing at a deleted
    project would vanish from Flock without a trace (P2).
    """
    project = writes.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", project.id, started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )

    outcome = writes.delete_project(
        connection,
        workspace_id=project.id,
        on_running=models.OnRunning.ORPHAN,
        kill=never_kills,
    )
    assert (outcome.deleted, outcome.orphaned) == (True, ("s-live",))
    assert reads.get_workspace(connection, project.id) is None
    survivors = reads.running_sessions_for(connection, models.UNASSIGNED_PROJECT_ID)
    assert [s.id for s in survivors] == ["s-live"]
    # The *ended* session went with the project: `orphan` is about what is
    # still running, and a stopped row has nothing left to keep alive.
    assert connection.execute("SELECT COUNT(*) FROM session WHERE id='s-done'").fetchone()[0] == 0


def test_delete_is_total_over_its_matrix(connection: sqlite3.Connection) -> None:
    """P1 — every `(exists, has_running, on_running)` triple has a defined
    outcome and none of them is silent. The product is built at test time, so a
    branch removed from `delete_project` cannot hide in an unwritten cell.
    """
    import itertools

    for index, (exists, has_running, choice) in enumerate(
        itertools.product((True, False), (True, False), tuple(models.OnRunning))
    ):
        if exists:
            project = writes.create_project(connection, name=f"p{index}", description=None)
            workspace_id = project.id
        else:
            workspace_id = f"w-nope-{index}"
        if exists and has_running:
            plant_session(
                connection, f"s-{index}", workspace_id, started_at="2026-01-01T00:00:00Z"
            )

        outcome = writes.delete_project(
            connection, workspace_id=workspace_id, on_running=choice, kill=lambda _: None
        )

        cell = (exists, has_running, choice)
        if not exists:
            assert outcome == models.DeleteOutcome(
                deleted=False, refused=outcome.refused
            ), cell
            assert outcome.refused is not None and workspace_id in outcome.refused, cell
        elif has_running and choice is models.OnRunning.REFUSE:
            assert (outcome.deleted, outcome.running) == (False, (f"s-{index}",)), cell
            assert outcome.refused is not None, cell
        else:
            assert outcome.deleted is True and outcome.refused is None, cell
        # Never silent: every cell says either *why not* or *what it did*.
        assert outcome.refused is not None or outcome.deleted is True, cell

        orphans = connection.execute(
            "SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)"
        ).fetchone()[0]
        assert orphans == 0, cell  # P2, after every cell of P1
