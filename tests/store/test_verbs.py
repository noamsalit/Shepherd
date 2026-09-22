"""T6: the verb surface (D33) and its threading model (ADR-7).

Integration seam: a real SQLite database under `tmp_path`, plus one threaded
case for P18. Nothing here writes SQL — that is the point of the suite.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import inspect
import re
import sqlite3
import threading
import typing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shepherd.core.clock import stamp
from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
from shepherd.store import models, projects, reads, writes
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
        (name, text)
        for name, text in assignments
        # `projects.py` since T3.4: `upsert_repo` moved there with the rest of
        # D57's family when `writes.py` hit the 600-line ceiling.
        if name in {"projects.py", "writes.py", "reads.py"}
    )
    # Arrival before absence: the scan really did read the write that sets it.
    assert sql == [("projects.py", "active = 1")], sql
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
    parent_session_id: str | None = None,
    retry_of: str | None = None,
    ownership: Ownership = Ownership.ATTACHED,
    runner_handle: str | None = None,
) -> None:
    """A session row, including the two columns `session` points at itself with.

    `parent_session_id` and `retry_of` are parameters because the fixture could
    not express them, and a shape a fixture cannot express is a shape its
    matrix cannot reach: `test_delete_is_total_over_its_matrix` called itself
    total while the input that made the cascade abort — a surviving child of a
    deleted parent — was unreachable from here.

    `ownership` and `runner_handle` are parameters for the same reason one rung
    up. They were hardcoded to `attached`/null, and the real kill path answers
    `no_pane(session_id)` — a kill that cannot land — for exactly a session with
    no runner handle. So the fixture could only express the session production
    *cannot* kill, while the matrix's KILL cells were driven by a callable that
    returned `True` and touched no row: a claim with no store effect, the one
    input the commit half must refuse.
    """
    connection.execute(
        "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at,"
        " state, last_event_at, ended_at, parent_session_id, retry_of, runner_handle)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            workspace_id,
            str(Origin.EXTERNAL.value),
            str(ownership.value),
            "claude_code",
            started_at,
            str(SessionState.STOPPED.value if ended_at else SessionState.RUNNING.value),
            last_event_at,
            ended_at,
            parent_session_id,
            retry_of,
            runner_handle,
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
    # Stamped through `core.clock.stamp`, and **inside one second**. The MAX is
    # lexical, and the fixture used to plant `"2026-01-01T00:00:00Z"` — a
    # spelling no writer in this system produces: `stamp()` is millisecond
    # precision, always, and `discovery_loop._seconds` says of these same
    # stamps that `"…:56Z"` sorts *after* `"…:56.789Z"` as text, which would
    # invert it. A fixture in a format production never writes cannot tell a
    # lexical MAX from a temporal one, and two events inside one second are
    # ordinary.
    base = datetime(2026, 3, 1, 12, 0, 0, 100_000, tzinfo=UTC)
    earlier = stamp(base)
    later = stamp(base + timedelta(milliseconds=250))
    assert earlier < later and earlier[:19] == later[:19]
    plant_session(
        connection, "s-old", "w-api", started_at=stamp(base - timedelta(days=60)),
        last_event_at=earlier,
    )
    plant_session(connection, "s-new", "w-api", started_at=later)

    assert reads.project_last_activity(connection) == {"w-api": later}


def test_workspace_carries_no_column_the_store_never_writes() -> None:
    """RD-3, applied the whole way.

    `project_last_activity` derives the value correctly — and `rows.workspace`
    went on mapping the dead `workspace.last_activity_at` column into the
    dataclass, where it is now **permanently `None`** behind a field docstring
    saying it is *"derived at read time"*. A page author who believes the
    docstring renders "never" for every project, and nothing goes red.

    So the field is gone from `Workspace`, and `project_last_activity` is the
    only way to ask. The **column stays in the schema** (004 does not drop it):
    dropping it is a table rebuild, and an unread column costs nothing.
    """
    fields = {field.name for field in dataclasses.fields(models.Workspace)}
    assert "last_activity_at" not in fields
    assert fields == {"id", "owner_id", "name", "description", "created_at"}


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


def never_kills(session_id: str) -> bool:
    raise AssertionError(f"the kill path was reached for {session_id!r} and must not have been")


def kills_cleanly(session_id: str) -> bool:
    """A kill that lands. It answers **whether it did** — the thing the old
    `Callable[[str], None]` could not, while the real kill path returns
    `no_pane(session_id)` for any session without a runner handle."""
    return True


def delete_project(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    on_running: models.OnRunning,
    kill: typing.Callable[[str], bool] = never_kills,
) -> models.DeleteOutcome:
    """What a caller of the two halves does — and the only place these tests
    put a kill.

    Decide (a read), stop what the decision named (**outside** any
    transaction), commit (a write). The store is never handed the kill: a
    callable on a write verb runs on the writer thread inside `BEGIN
    IMMEDIATE`, where the real kill path's own first store write can never be
    reached, and where an effect that leaves the process cannot be rolled back
    with the rows.
    """
    plan = reads.plan_project_delete(
        connection, workspace_id=workspace_id, on_running=on_running
    )
    if plan.refusal is not None:
        return plan.refusal
    killed = (
        tuple(session_id for session_id in plan.running if kill(session_id))
        if on_running is models.OnRunning.KILL
        else ()
    )
    return projects.commit_project_delete(connection, plan=plan, killed=killed)


def test_two_projects_may_share_a_name(connection: sqlite3.Connection) -> None:
    """E1 — `/work/api` and `/personal/api` are two projects, not one.

    **Shown red against today's code first.** `upsert_workspace`'s body is
    keyed by `name` (`SELECT * FROM workspace WHERE name = ?`), so the second
    call returned the first row's id and overwrote its `root_path` — measured,
    against a 001→003 database, before this landed:
    `same id? True | rows named api: 1 | /work/api root became: /personal/api`.
    Identity is `workspace.id`; names are labels (D57).
    """
    work = projects.create_project(connection, name="api", description="the work one")
    personal = projects.create_project(connection, name="api", description=None)

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
        projects.rename_project(
            connection, workspace_id=models.UNASSIGNED_PROJECT_ID, name="Inbox"
        )
    still = reads.get_workspace(connection, models.UNASSIGNED_PROJECT_ID)
    assert still is not None and still.name == "Unassigned"

    project = projects.create_project(connection, name="api", description=None)
    renamed = projects.rename_project(connection, workspace_id=project.id, name="payments-api")
    assert renamed is not None and renamed.name == "payments-api"
    # A project that does not exist is absent, not forbidden: `None`, no raise.
    assert projects.rename_project(connection, workspace_id="w-nope", name="x") is None


def test_set_project_description_writes_and_clears_it(
    connection: sqlite3.Connection,
) -> None:
    """GAP 3 — a description was **write-once at creation**.

    `create_project` takes one and `rename_project` takes `name` only, so a
    person who mistyped a description had no verb that could change it and
    Shepherd's answer was "delete the project". A separate verb rather than a
    widened `rename_project`: a verb called *rename* that edits a description
    is a verb whose name is wrong, and one that takes both fields has to invent
    a spelling for "leave this one alone" — absent-means-unchanged against
    null-means-clear, at the only surface where clearing is a real intent.

    Here `None` **clears** it, because the field is nullable and that is the
    whole of what the caller can mean by sending nothing.

    The two negative answers keep this family's two spellings: the reserved
    project is forbidden and raises (E8, as `rename_project` does), a project
    that does not exist is absent and answers `None`.
    """
    project = projects.create_project(connection, name="api", description="the work one")

    changed = projects.set_project_description(
        connection, workspace_id=project.id, description="the payments api"
    )
    assert changed is not None and changed.description == "the payments api"
    # …and the name is untouched, which is the half a widened rename risks.
    assert changed.name == "api"

    cleared = projects.set_project_description(
        connection, workspace_id=project.id, description=None
    )
    assert cleared is not None and cleared.description is None

    assert (
        projects.set_project_description(connection, workspace_id="w-nope", description="x")
        is None
    )
    with pytest.raises(StoreError):
        projects.set_project_description(
            connection, workspace_id=models.UNASSIGNED_PROJECT_ID, description="Inbox"
        )
    reserved = reads.get_workspace(connection, models.UNASSIGNED_PROJECT_ID)
    assert reserved is not None and reserved.description != "Inbox"


def test_unassigned_refuses_add_repo(connection: sqlite3.Connection) -> None:
    """E7, and it is §13's allowlist that makes it a refusal rather than a
    preference: every discovered repo binds to `unassigned` (D59), so letting
    repos be *registered* there would make its allowlist every repo the machine
    has ever seen.
    """
    with pytest.raises(StoreError):
        projects.add_repo(
            connection,
            workspace_id=models.UNASSIGNED_PROJECT_ID,
            root_path="/srv/api",
            name="api",
            git_common_dir="/srv/api/.git",
            vcs_remote=None,
        )
    assert reads.list_repos(connection, models.UNASSIGNED_PROJECT_ID) == []

    project = projects.create_project(connection, name="api", description=None)
    added = projects.add_repo(
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
    outcome = delete_project(
        connection,
        workspace_id=models.UNASSIGNED_PROJECT_ID,
        on_running=models.OnRunning.REFUSE,
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
    first = projects.create_project(connection, name="api", description=None)
    repo_row = projects.add_repo(
        connection,
        workspace_id=first.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote=None,
    )
    assert projects.remove_repo(connection, workspace_id=first.id, repo_id=repo_row.id) is True
    # The repo row is **kept** — orphaned, not deleted, or D48's identity would
    # be minted afresh and every historical session would lose its repo.
    assert reads.find_repo_by_common_dir(connection, "/srv/api/.git") is not None
    assert reads.projects_for_repo(connection, repo_row.id) == []

    second = projects.create_project(connection, name="payments", description=None)
    again = projects.add_repo(
        connection,
        workspace_id=second.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote="github.com/example-org/api",
    )
    assert again.id == repo_row.id
    assert again.vcs_remote == "github.com/example-org/api"
    assert projects.remove_repo(connection, workspace_id=second.id, repo_id="r-nope") is False


def test_delete_refuses_by_default_and_names_the_running_sessions(
    connection: sqlite3.Connection,
) -> None:
    """E13 — a delete while a session is mid-turn. The refusal carries the ids,
    because the page builds the three choices out of *this record* rather than
    going back and asking a second question that can disagree with the first.
    """
    project = projects.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", project.id, started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )

    outcome = delete_project(
        connection, workspace_id=project.id, on_running=models.OnRunning.REFUSE
    )
    assert outcome.deleted is False
    assert outcome.running == ("s-live",)
    assert outcome.refused is not None and "1" in outcome.refused
    assert reads.get_workspace(connection, project.id) is not None


def test_the_refusing_plan_says_what_the_delete_would_take(
    connection: sqlite3.Connection,
) -> None:
    """`DeletePlan.doomed` on the refusal, which is the only place it is useful.

    Its own docstring says it exists *"so the dialog can say what it is about to
    take **before** the button"* — and the refusal **is** before the button. It
    was computed after the refusing return, so a plan that refuses carried an
    empty tuple and a page could say "2 sessions are still running" and could
    not say "and four hundred finished ones go with the project". The page that
    shipped derived that count itself, out of a second read: a copy of a store
    derivation, which is the thing that drifts.

    `doomed` under a refusal is every session row in the project — what goes if
    the caller proceeds. The orphan case is that list minus `running`, which the
    caller has in the same record.
    """
    project = projects.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", project.id, started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )

    plan = reads.plan_project_delete(
        connection, workspace_id=project.id, on_running=models.OnRunning.REFUSE
    )

    assert plan.refusal is not None
    assert plan.running == ("s-live",)
    # `ORDER BY started_at, id`, which is the plan's own ordering: the two
    # sessions share a start, so the ids break the tie.
    assert plan.doomed == ("s-done", "s-live")
    # The control: a plan that does not refuse was already saying this, and
    # still does — the fix moved the derivation, it did not add a second one.
    ok = reads.plan_project_delete(
        connection, workspace_id=project.id, on_running=models.OnRunning.ORPHAN
    )
    assert ok.refusal is None
    assert ok.doomed == ("s-done",)


def test_delete_with_kill_stops_them_then_cascades(connection: sqlite3.Connection) -> None:
    """D61 — the kill happens **through the caller's kill path**, between the
    two halves. `store/` never learns about runners.

    The kill here **stops the session** (`apply_stop_verdict`, which writes
    `ended_at`), because that is the only kill production makes. It used to
    only append to a list and return `True`, and the commit half accepted the
    claim: this test passed over a world where the agent was still running and
    its row was deleted anyway.
    """
    project = projects.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    connection.execute(
        "INSERT INTO mailbox_message (id, session_id, idempotency_key, body, origin, queued_at)"
        " VALUES ('m-1', 's-live', 'k1', 'hi', 'user_ui', '2026-01-01T00:00:00Z')"
    )
    killed: list[str] = []
    stop = a_landed_kill(connection)

    def kill(session_id: str) -> bool:
        killed.append(session_id)
        return stop(session_id)

    outcome = delete_project(
        connection,
        workspace_id=project.id,
        on_running=models.OnRunning.KILL,
        kill=kill,
    )
    assert (outcome.deleted, outcome.killed) == (True, ("s-live",))
    assert killed == ["s-live"]
    assert outcome.destroyed == ("s-live",)
    assert reads.get_workspace(connection, project.id) is None
    assert connection.execute("SELECT COUNT(*) FROM mailbox_message").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 0


def test_delete_with_orphan_moves_them_to_unassigned(connection: sqlite3.Connection) -> None:
    """D61's third choice. The sessions **survive and stay visible**: `fleet()`
    is an INNER JOIN on `workspace`, so a session left pointing at a deleted
    project would vanish from Flock without a trace (P2).
    """
    project = projects.create_project(connection, name="api", description=None)
    plant_session(connection, "s-live", project.id, started_at="2026-01-01T00:00:00Z")
    plant_session(
        connection, "s-done", project.id, started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
    )

    outcome = delete_project(
        connection,
        workspace_id=project.id,
        on_running=models.OnRunning.ORPHAN,
    )
    assert (outcome.deleted, outcome.orphaned) == (True, ("s-live",))
    # M2: the *ended* sessions are named too. A dialog that reports only
    # `orphaned=('s-live',)` does not tell a person that every finished session
    # in the project went with it.
    assert outcome.destroyed == ("s-done",)
    assert reads.get_workspace(connection, project.id) is None
    survivors = reads.running_sessions_for(connection, models.UNASSIGNED_PROJECT_ID)
    assert [s.id for s in survivors] == ["s-live"]
    # The *ended* session went with the project: `orphan` is about what is
    # still running, and a stopped row has nothing left to keep alive.
    assert connection.execute("SELECT COUNT(*) FROM session WHERE id='s-done'").fetchone()[0] == 0


#: The fourth axis. `session` references itself twice (001:58,64), and a
#: surviving row pointing into the doomed cohort is what made the cascade abort
#: — an input the old three-axis product could not express, because
#: `plant_session` had no parameter for either column.
#: The two are **not** exclusive — a retry of a session that also had a parent
#: sets both columns on the one row, and the old `None | parent | retry`
#: spelling could not reach that cell. It is the shape that severs twice, and
#: the only one that exercises `_sever_lineage`'s loop as a loop.
LINEAGE_SHAPES: tuple[tuple[str, ...], ...] = (
    (),
    ("parent_session_id",),
    ("retry_of",),
    ("parent_session_id", "retry_of"),
)


def test_delete_is_total_over_its_matrix(connection: sqlite3.Connection) -> None:
    """P1 — every `(exists, has_running, lineage, on_running)` cell has a
    defined outcome and none of them is silent. The product is built at test
    time, so a branch removed from the delete cannot hide in an unwritten cell.

    **Total over the axes it enumerates, and it was short one.** Seven of nine
    `(lineage, on_running)` cells passed on the old code; the two that did not
    were `orphan` with a surviving child, which raised `IntegrityError` and left
    the project permanently undeletable. The axis is here now, and so is
    `PRAGMA foreign_key_check` after **every** cell — asserted until now only
    after the migration, never after the verb that carries the cascade, which is
    the check that would have found this for free.

    **And the KILL cells were driven by a kill that cannot happen.** They used
    `kills_cleanly`, which returns `True` and touches no row — a claim with no
    store effect, which is the one input the commit half must now refuse. Every
    KILL cell therefore certified a state production never produces. The kill
    here is `a_landed_kill`: it writes `ended_at` through `apply_stop_verdict`,
    the way `orchestration/lifecycle.py` does, and the session it stops carries
    a `runner_handle` because a session without one is the case the real kill
    path answers `no_pane` to. The *did-not-land* branch is driven by
    `test_the_commit_half_reports_only_kills_the_store_saw_land`, which keeps
    `kills_cleanly` as its negative control.
    """
    import itertools

    for index, (exists, has_running, lineage, choice) in enumerate(
        itertools.product((True, False), (True, False), LINEAGE_SHAPES, tuple(models.OnRunning))
    ):
        if exists:
            project = projects.create_project(connection, name=f"p{index}", description=None)
            workspace_id = project.id
        else:
            workspace_id = f"w-nope-{index}"
        if exists and has_running:
            if lineage:
                # The ancestor has **ended**, so it is not in the running set:
                # the cascade deletes it outright while the live row survives.
                plant_session(
                    connection, f"anc-{index}", workspace_id,
                    started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T01:00:00Z",
                )
            plant_session(
                connection, f"s-{index}", workspace_id,
                started_at="2026-01-01T00:00:00Z",
                parent_session_id=f"anc-{index}" if "parent_session_id" in lineage else None,
                retry_of=f"anc-{index}" if "retry_of" in lineage else None,
                ownership=Ownership.OWNED,
                runner_handle=f"pane-{index}",
            )

        outcome = delete_project(
            connection,
            workspace_id=workspace_id,
            on_running=choice,
            kill=a_landed_kill(connection),
        )

        cell = (exists, has_running, lineage, choice)
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

        # `killed` names the sessions the store **saw stop**, and only under
        # KILL. It used to name the ones whose kill had *not* landed.
        assert outcome.killed == (
            (f"s-{index}",)
            if exists and has_running and choice is models.OnRunning.KILL
            else ()
        ), cell

        # The severing is reported, never silent — and only where a row
        # actually survived the cascade still pointing into it. Under KILL the
        # live row is now ended, so the cascade takes it and nothing survives.
        survives = exists and has_running and bool(lineage) and (
            choice is models.OnRunning.ORPHAN
        )
        assert outcome.severed == (
            tuple(
                models.SeveredLink(session_id=f"s-{index}", column=column)
                for column in projects.LINEAGE_COLUMNS
                if column in lineage
            )
            if survives
            else ()
        ), cell

        orphans = connection.execute(
            "SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)"
        ).fetchone()[0]
        assert orphans == 0, cell  # P2, after every cell of P1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == [], cell


def test_no_session_ever_points_at_a_deleted_project(connection: sqlite3.Connection) -> None:
    """P2, and AC-4's second half — split out of the matrix on purpose.

    It used to live only as two lines at the bottom of
    `test_delete_is_total_over_its_matrix`, where a P1 failure masks it. That is
    not hypothetical: the cell P1 raised on is exactly a cell where the delete
    half-ran, and the property nobody got to check was this one. AC-4 names this
    node id and, run verbatim, the command exited 4 — *"no tests ran"* — which is
    the shape M4's verification caught: a clause whose command names a test
    nobody built.

    Every surviving session points at a workspace that exists, under all three
    choices, and the referential net (`PRAGMA foreign_key_check`) is empty.
    """
    for choice in models.OnRunning:
        project = projects.create_project(connection, name=f"api-{choice.value}", description=None)
        other = projects.create_project(connection, name=f"kept-{choice.value}", description=None)
        plant_session(
            connection, f"live-{choice.value}", project.id, started_at="2026-01-01T00:00:00Z"
        )
        plant_session(
            connection, f"done-{choice.value}", project.id,
            started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T01:00:00Z",
        )
        # A session in *another* project descended from one in this one: the
        # cross-project link fails the same way under any choice.
        plant_session(
            connection, f"cousin-{choice.value}", other.id,
            started_at="2026-01-01T00:02:00Z", parent_session_id=f"done-{choice.value}",
        )

        outcome = delete_project(
            connection, workspace_id=project.id, on_running=choice, kill=kills_cleanly
        )
        assert outcome.refused is not None or outcome.deleted is True, choice

        dangling = connection.execute(
            "SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)"
        ).fetchone()[0]
        assert dangling == 0, choice
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == [], choice
        if outcome.deleted:
            assert reads.get_workspace(connection, project.id) is None, choice
            # The cousin survives in its own project, having forgotten a parent
            # that no longer exists — and the outcome says so.
            assert outcome.severed == (
                models.SeveredLink(
                    session_id=f"cousin-{choice.value}", column="parent_session_id"
                ),
            ), choice
            cousin = reads.get_session(connection, f"cousin-{choice.value}")
            assert cousin is not None and cousin.parent_session_id is None, choice


def test_a_fresh_install_holds_exactly_the_unassigned_project(tmp_path: Path) -> None:
    """E21/N1, and AC-6 names this node id — which, run verbatim against the
    code as shipped, exited 4: no test of that name existed.

    A fresh database is no longer *empty* of projects: 004 seeds the reserved
    `unassigned` row (D59), which is what every discovered session binds to. The
    two "the store starts with no projects" assertions this milestone had to
    change were changed against this statement, so it is written down rather
    than living in the diff of the two that were edited.
    """
    db_path = tmp_path / "fresh" / "shepherd.db"
    db_path.parent.mkdir(parents=True)
    migrate(db_path)
    opened = sqlite3.connect(db_path)
    opened.row_factory = sqlite3.Row
    try:
        projects = reads.list_workspaces(opened)
        assert [(w.id, w.name) for w in projects] == [
            (models.UNASSIGNED_PROJECT_ID, "Unassigned")
        ]
        assert projects[0].description == "Work that matched no declared project."
        # ...and nothing hangs off it: a seeded project with a seeded session
        # would be a second surprise hiding behind the first.
        assert reads.running_sessions_for(opened, models.UNASSIGNED_PROJECT_ID) == []
        assert reads.repo_counts(opened) == {}
        assert reads.project_last_activity(opened) == {}
    finally:
        opened.close()


def test_no_store_verb_takes_a_callable_the_caller_must_run() -> None:
    """Rule 4, and it is the deadlock T1's remediation removed.

    `Store._write` enqueues onto the single writer thread and blocks on
    `done.wait()` with no timeout, **after** `BEGIN IMMEDIATE`. A callable
    parameter on a verb is therefore run by the writer thread while it holds
    SQLite's exclusive write lock — and the one caller this system has for such
    a parameter, the kill path, opens with `store.set_app_state(...)`
    (`orchestration/lifecycle.py`: write the record, *then* kill, because that
    is what survives a crash mid-way). That inner write queues behind a writer
    that can never reach it, and every subsequent write in the process hangs
    for good: the writer is a daemon thread and nothing times out.

    The second failure is the one that survives even when the callback does not
    write: an effect that leaves the process cannot be rolled back, so a later
    failure in the same transaction undoes the row deletes while the panes stay
    dead, and `running_sessions_for` answers with a session whose process was
    destroyed.

    So the shape, not a patch: the decision is a read, the commit is a write,
    and the caller kills **between** them. Re-entrancy detection in `_write`
    was considered and refused — it converts the hang into a raise, and
    `delete_project` documents *"Never raises"*.
    """
    offenders: list[str] = []
    for name, member in public_verbs():
        hints = typing.get_type_hints(member)
        for parameter, annotation in hints.items():
            if parameter == "return":
                continue
            origin = typing.get_origin(annotation) or annotation
            if origin is collections.abc.Callable or annotation is collections.abc.Callable:
                offenders.append(f"Store.{name} accepts {parameter!r}, a callable")
    assert offenders == []


def a_landed_kill(connection: sqlite3.Connection) -> typing.Callable[[str], bool]:
    """The only kind of kill production makes — one that writes `ended_at`.

    `orchestration/lifecycle.py` stops a session through
    `store.apply_stop_verdict(...)`, whose single statement sets `ended_at`. So
    after a kill that landed the store can see for **itself** that the session
    stopped: `running_sessions_for` is `ended_at IS NULL`, and the row is no
    longer in it.

    `kills_cleanly` returns `True` and touches no row. That is a *claim*, and a
    claim with no store effect is exactly the state the commit half must refuse
    — so every KILL cell driven by it was certifying a world production never
    produces. It survives as the **negative control**: see
    `test_the_commit_half_reports_only_kills_the_store_saw_land`, whose second
    half drives the did-not-land branch with precisely that.
    """

    def kill(session_id: str) -> bool:
        writes.apply_stop_verdict(
            connection,
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
        return True

    return kill


def test_the_commit_half_reports_only_kills_the_store_saw_land(
    connection: sqlite3.Connection,
) -> None:
    """`killed` was populated exactly when the kill did **not** land.

    The filter was `session_id in killed` over `fresh.running`, a set
    re-derived *after* the caller went away to kill things. A session genuinely
    killed has `ended_at` written, so it is not in `fresh.running` and was
    filtered **out** of the report; a session the caller only *claimed* to have
    killed is still running, so it survived the filter and was reported. Two
    harms from one line: the dialog told a person nothing was killed after
    their sessions' rows were destroyed, and the survivor gate —
    `fresh.running - killed` — took the caller's word over the store's own
    fact, so a mistaken caller could talk the one safety check on the one verb
    that destroys data out of firing.

    Both branches are driven here, because a gate not seen to fail is not a
    gate. **Landed** (`a_landed_kill`, the production path) must be reported.
    **Not landed** (`kills_cleanly`, a bare `True` over an untouched row) must
    refuse the delete and leave the row alive, whatever the caller says.
    """
    landed = projects.create_project(connection, name="landed", description=None)
    plant_session(connection, "s-landed", landed.id, started_at="2026-01-01T00:00:00Z")

    outcome = delete_project(
        connection,
        workspace_id=landed.id,
        on_running=models.OnRunning.KILL,
        kill=a_landed_kill(connection),
    )
    assert (outcome.deleted, outcome.killed) == (True, ("s-landed",))
    assert outcome.destroyed == ("s-landed",)
    assert reads.get_workspace(connection, landed.id) is None

    # The other branch. The caller says it killed the session; the store can
    # see that `ended_at` is still null, and the store's own fact wins.
    lying = projects.create_project(connection, name="lying", description=None)
    plant_session(connection, "s-lying", lying.id, started_at="2026-01-01T00:00:00Z")

    refused = delete_project(
        connection,
        workspace_id=lying.id,
        on_running=models.OnRunning.KILL,
        kill=kills_cleanly,
    )
    assert refused.deleted is False
    assert refused.running == ("s-lying",)
    assert refused.killed == ()
    assert refused.refused is not None
    assert reads.get_workspace(connection, lying.id) is not None
    assert [s.id for s in reads.running_sessions_for(connection, lying.id)] == ["s-lying"]


def test_lineage_columns_is_every_self_reference_the_schema_declares(
    connection: sqlite3.Connection,
) -> None:
    """`LINEAGE_COLUMNS` was a hand copy of the FK graph with nothing asserting it.

    The constant exists because *"a cascade that knows one and not the other is
    exactly the defect this constant exists to close"* — and nothing closed the
    **third** one. Add a `REFERENCES session(id)` column the cascade does not
    know and `commit_project_delete` raises `IntegrityError: FOREIGN KEY
    constraint failed`, in a verb documented *"Never raises"*, leaving the
    project permanently undeletable. The per-cell `PRAGMA foreign_key_check`
    cannot catch that: the transaction aborts before the assertion runs.

    So the expected set is **derived from the migrated schema** rather than
    restated — the same instinct as pinning a constant by parsing the document
    that states it. It fails closed: a migration that adds a self-reference
    turns this red before the cascade ever meets it.
    """
    declared = {
        str(row["from"])
        for row in connection.execute("PRAGMA foreign_key_list(session)")
        if str(row["table"]) == "session"
    }
    assert declared == set(projects.LINEAGE_COLUMNS)
    # The cascade iterates the constant, so the count has to agree too: a
    # duplicated entry would pass a set comparison and sever twice.
    assert len(projects.LINEAGE_COLUMNS) == len(set(projects.LINEAGE_COLUMNS)) == len(declared)
