"""T4-2 — M3's verbs are reachable from `Store`, and only through the plumbing.

`store/sessions.py` and `store/mailbox.py` were fully tested before this file
existed and still nothing above `store/` could reach them: `Store` did not
expose them, and `Store` is the single name a caller imports (D33). The hole was
invisible to both verb suites, because each holds its own connection — exactly
the reach-through this suite refuses on every caller's behalf.

The seam is the same one `test_verbs.py` uses: the public `Store` surface over a
real SQLite file in `tmp_path`. Two properties are asserted here that a verb
suite cannot see:

* every delegated **write** crosses ADR-7's one writer thread, never the calling
  thread — a verb wired to `self._reader()` would still return the right answer
  on a read-write database and quietly give D37 a second writer;
* every delegated verb is refused once the store is closed, which is only true
  if it went through `_write`/`_read` rather than opening a connection of its
  own.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import threading
import typing
from pathlib import Path

import pytest

import shepherd.store
from shepherd.core.fold_types import FoldDelta
from shepherd.core.mailbox import MailboxCounts, MailboxMessage, MailboxOrigin
from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
from shepherd.store import db, models, writes
from shepherd.store.db import Store, open_store

HANDLE = RunnerHandle(runner="tmux", socket="shepherd-runner", session_name="shepherd_01A")
PARENT = "01PARENT00000000000000000"[:26]
CHILD = "01CHILD000000000000000000"[:26]


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    opened.create_project(name="shepherd", description=None)
    try:
        yield opened
    finally:
        opened.close()


def workspace_id(store: Store) -> str:
    return next(w for w in store.list_workspaces() if w.name == "shepherd").id


def spawn(
    store: Store,
    session_id: str = PARENT,
    *,
    engine_session_id: str | None = "eng-1",
    origin: Origin = Origin.ORCHESTRATOR,
    parent_session_id: str | None = None,
    depth: int = 0,
    ephemeral: bool = False,
    handle: RunnerHandle | None = HANDLE,
) -> object:
    return store.create_owned_session(
        session_id=session_id,
        engine_session_id=engine_session_id,
        workspace_id=workspace_id(store),
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T10:00:00Z",
        origin=origin,
        parent_session_id=parent_session_id,
        depth=depth,
        ephemeral=ephemeral,
        title="ship it",
        title_source="brief",
        handle=handle,
        model="opus",
        effort="high",
    )


def note(identifier: str, *, key: str = "key-1", session_id: str = PARENT) -> MailboxMessage:
    return MailboxMessage(
        id=identifier,
        session_id=session_id,
        idempotency_key=key,
        body="ship it",
        origin=MailboxOrigin.ORCHESTRATOR,
        queued_at="2026-09-17T10:00:00Z",
        delivered_at=None,
        delivery_attempts=0,
        last_refusal=None,
    )


# ----- the owned-session verbs ----------------------------------------------


def test_an_owned_session_spawned_through_the_store_is_readable_through_it(
    store: Store,
) -> None:
    """The whole of T4-2: a caller that only has a `Store` can spawn and read back."""
    created = spawn(store)

    assert created.ownership is Ownership.OWNED
    assert created.origin is Origin.ORCHESTRATOR
    assert created.runner_handle == HANDLE
    assert created.state is SessionState.STARTING
    assert store.get_owned_session(PARENT) == created
    # …and the M1 read verb sees the same row, so this is one `session` table.
    assert store.get_session(PARENT) == created
    assert store.owned_session_counts() == (1, 0)


def test_the_store_binds_an_unbound_fork_row_exactly_once(store: Store) -> None:
    """T4-1's rowcount survives the delegation: the second binder is told `0`."""
    spawn(store, engine_session_id=None, origin=Origin.ASK_FORK, ephemeral=True)

    assert store.bind_engine_session_id(PARENT, "eng-fork") == 1
    assert store.bind_engine_session_id(PARENT, "eng-other") == 0

    bound = store.get_owned_session(PARENT)
    assert bound is not None
    assert bound.engine_session_id == "eng-fork"


def test_the_store_rebinds_a_resumed_session_and_keeps_the_row(store: Store) -> None:
    """C14: `/resume` moves the engine id in the same pane; the row survives."""
    spawn(store)
    store.rebind_engine_session_id(PARENT, "eng-2")

    moved = store.get_owned_session(PARENT)
    assert moved is not None
    assert moved.id == PARENT
    assert moved.engine_session_id == "eng-2"
    assert store.get_session_by_engine_id("eng-1") is None


def test_the_store_ratchets_the_title_and_stamps_a_confirmed_one(store: Store) -> None:
    """D29 through the delegation: `user` wins, `engine` never overwrites it."""
    spawn(store)

    assert store.apply_title(PARENT, "renamed by hand", "user").title == "renamed by hand"
    assert store.apply_title(PARENT, "engine guess", "engine").title == "renamed by hand"

    store.set_title_synced_at(PARENT, "2026-09-17T11:00:00Z")
    stamped = store.get_owned_session(PARENT)
    assert stamped is not None
    assert stamped.title_synced_at == "2026-09-17T11:00:00Z"


def test_the_store_sets_the_handle_the_ephemeral_flag_and_counts_children(
    store: Store,
) -> None:
    """The three remaining owned-session verbs, each observed through a read."""
    spawn(store, handle=None)
    assert store.owned_session_counts() == (1, 1), "a handle-less row is the second number"

    store.set_runner_handle(PARENT, HANDLE)
    handled = store.get_owned_session(PARENT)
    assert handled is not None
    assert handled.runner_handle == HANDLE
    assert store.owned_session_counts() == (1, 0)

    assert store.children_of(PARENT) == 0
    spawn(
        store,
        CHILD,
        engine_session_id="eng-child",
        origin=Origin.ASK_FORK,
        parent_session_id=PARENT,
        depth=1,
    )
    assert store.children_of(PARENT) == 1

    assert {row.session_id for row in store.fleet()} == {PARENT, CHILD}
    store.set_ephemeral(CHILD, True)
    assert [row.session_id for row in store.fleet()] == [
        PARENT
    ], "DP2: an ephemeral fork leaves the page"


# ----- the mailbox verbs ----------------------------------------------------


def test_the_store_enqueues_idempotently_and_delivers_once(store: Store) -> None:
    """D12's two claims, reached from `Store` rather than from a connection."""
    spawn(store)

    first = store.enqueue(note("01MSG10000000000000000000"))
    again = store.enqueue(note("01MSG20000000000000000000"))
    assert again.id == first.id, "the stored row wins, not the one offered"

    assert [message.id for message in store.pending_for(PARENT)] == [first.id]
    assert store.sessions_with_pending() == [PARENT]

    assert store.mark_delivered((first.id,), "2026-09-17T11:00:00Z") == 1
    assert store.mark_delivered((first.id,), "2026-09-17T11:00:01Z") == 0
    assert store.pending_for(PARENT) == []
    assert store.sessions_with_pending() == []


def test_the_store_records_a_refusal_and_counts_the_mailbox(store: Store) -> None:
    """A refusal is a deferral: the row stays pending and says why (principle 5)."""
    spawn(store)
    queued = store.enqueue(note("01MSG10000000000000000000"))
    delivered = store.enqueue(note("01MSG30000000000000000000", key="key-2"))
    assert store.mark_delivered((delivered.id,), "2026-09-17T11:00:00Z") == 1

    store.record_refusal((queued.id,), "pane is mid-turn")

    deferred = store.pending_for(PARENT)
    assert [(message.id, message.last_refusal) for message in deferred] == [
        (queued.id, "pane is mid-turn")
    ]
    assert store.mailbox_counts() == MailboxCounts(pending=1, delivered=1, deferred=1)


# ----- the plumbing the delegation must use ---------------------------------


def test_every_delegated_write_crosses_the_one_writer_thread(store: Store) -> None:
    """ADR-7/D37: a verb wired to the reader would answer correctly and still
    hand D37 a second writer. The idents say which thread executed the SQL."""
    spawn(store)
    store.set_runner_handle(PARENT, HANDLE)
    store.apply_title(PARENT, "renamed", "user")
    store.set_title_synced_at(PARENT, "2026-09-17T11:00:00Z")
    store.set_ephemeral(PARENT, False)
    store.rebind_engine_session_id(PARENT, "eng-2")
    queued = store.enqueue(note("01MSG10000000000000000000"))
    store.record_refusal((queued.id,), "not now")
    store.mark_delivered((queued.id,), "2026-09-17T11:00:00Z")

    idents = store.writer_thread_idents()
    assert len(idents) == 1, f"ADR-7 says one writer thread, saw {len(idents)}"
    assert threading.get_ident() not in idents, "a write ran on the calling thread"


def test_every_delegated_verb_is_refused_once_the_store_is_closed(tmp_path: Path) -> None:
    """Proof the verb went through `_write`/`_read` and not its own connection."""
    closed = open_store(tmp_path / "data" / "shepherd.db")
    closed.create_project(name="shepherd", description=None)
    spawn(closed)
    closed.close()

    refused: list[typing.Callable[[], object]] = [
        lambda: spawn(closed, "01OTHER000000000000000000", engine_session_id="eng-9"),
        lambda: closed.get_owned_session(PARENT),
        lambda: closed.set_runner_handle(PARENT, HANDLE),
        lambda: closed.bind_engine_session_id(PARENT, "eng-3"),
        lambda: closed.rebind_engine_session_id(PARENT, "eng-3"),
        lambda: closed.apply_title(PARENT, "late", "user"),
        lambda: closed.set_title_synced_at(PARENT, "2026-09-17T11:00:00Z"),
        lambda: closed.set_ephemeral(PARENT, True),
        lambda: closed.owned_session_counts(),
        lambda: closed.children_of(PARENT),
        lambda: closed.enqueue(note("01MSG10000000000000000000")),
        lambda: closed.pending_for(PARENT),
        lambda: closed.sessions_with_pending(),
        lambda: closed.mark_delivered(("01MSG10000000000000000000",), "2026-09-17T11:00:00Z"),
        lambda: closed.record_refusal(("01MSG10000000000000000000",), "late"),
        lambda: closed.mailbox_counts(),
        lambda: closed.list_repos("01WORKSPACE00000000000000"),
    ]
    for verb in refused:
        with pytest.raises(RuntimeError):
            verb()


# ----- T4-3: where the write implementations and the shared vocabulary live --


SQL_STATEMENT_WORDS = ("INSERT", "UPDATE ", "SELECT")

MOVED_WRITES = (
    "create_project",
    "upsert_repo",
    "register_session",
    "apply_fold_delta",
    "apply_stop_verdict",
    "set_app_state",
    "bump_anomaly",
)

SHARED_VOCABULARY = ("StoreError", "SESSION_COLUMNS", "DEFAULT_ENGINE")

#: A real verdict, in `test_stop_verbs.py`'s shape — the eight columns one write.
DONE = Verdict(
    stop_reason=StopReason.COMPLETED,
    bucket=Bucket.FINISHED,
    why="the model ended its turn with every task done",
    confidence=1.0,
    decided_by=DecidedBy.HEURISTIC,
    next_actions=(),
    waiting_on=None,
    missing=(),
)


def store_source(module: str) -> str:
    return (Path(shepherd.store.__file__).parent / f"{module}.py").read_text(encoding="utf-8")


def statement_literals(module: str) -> list[str]:
    """Every string literal in `module` that spells a statement over a table.

    Docstrings are excluded — a docstring naming `SELECT` is prose, and a scan
    that cannot tell the two apart makes every explanatory comment a violation
    (the M1 lesson). `BEGIN`/`COMMIT`/`ROLLBACK`/`PRAGMA` are transaction and
    connection control, which is `db.py`'s own job under ADR-7.
    """
    tree = ast.parse(store_source(module))
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
        and any(word in node.value for word in SQL_STATEMENT_WORDS)
    ]


def imported_from(module: str, source_module: str) -> set[str]:
    """The names `module` imports `from source_module`."""
    tree = ast.parse(store_source(module))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == source_module
        for alias in node.names
    }


def test_the_m1_and_m2_write_implementations_live_in_store_writes(store: Store) -> None:
    """Task 4's own words: `db.py` is delegating methods only.

    The seven writes are the ~300 lines T4-2 was not authorised to move. They
    take the connection `db.py` owns, exactly as `reads.py`, `sessions.py` and
    `mailbox.py` already do, and `db.py` keeps nothing but the delegation.
    """
    assert (
        importlib.util.find_spec("shepherd.store.writes") is not None
    ), "store/writes.py does not exist"
    writes = importlib.import_module("shepherd.store.writes")

    missing = [verb for verb in MOVED_WRITES if not callable(getattr(writes, verb, None))]
    assert missing == [], f"store/writes.py does not hold {missing}"
    assert statement_literals("db") == [], "db.py still spells SQL over a table"

    # …and the surface is unchanged: the same call, through the same name.
    assert [w.name for w in store.list_workspaces()] == ["Unassigned", "shepherd"]
    store.set_app_state("m3.probe", {"n": 1})
    assert store.get_app_state("m3.probe") == {"n": 1}


def test_the_shared_vocabulary_lives_in_models(store: Store) -> None:
    """`StoreError` is raised by reads, writes, sessions and the plumbing.

    T4-2 parked it in `reads.py` to break an import cycle and flagged the
    placement as wrong. `models.py` is the shared-vocabulary module: imported by
    everyone, and the only store module with no connection dependency.
    """
    for name in SHARED_VOCABULARY:
        assert hasattr(models, name), f"{name} does not live in store/models.py"

    for module in ("db", "reads", "sessions", "writes"):
        assert imported_from(module, "shepherd.store.reads") & set(SHARED_VOCABULARY) == set(), (
            f"{module}.py still takes the shared vocabulary from reads.py"
        )

    # The re-export four test modules depend on, still resolving (`--no-implicit-reexport`).
    assert db.StoreError is models.StoreError
    with pytest.raises(models.StoreError):
        store.apply_fold_delta("01NOSUCHSESSION0000000000", FoldDelta(state=SessionState.RUNNING))


def test_every_moved_write_crosses_the_one_writer_thread(store: Store) -> None:
    """ADR-7/D37, for the seven verbs the move relocates.

    A moved write wired to `self._read()` answers correctly on a read-write
    database and quietly gives D37 a second writer. This is the guard that makes
    each delegation load-bearing rather than decorative.
    """
    space = store.create_project(name="moved", description=None)
    store.upsert_repo("/root/Moved/repo", "repo", None, "/root/Moved/repo/.git")
    registered = store.register_session(
        engine_session_id="eng-moved",
        workspace_id=space.id,
        repo_id=None,
        cwd="/root/Moved",
        started_at="2026-09-17T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    store.apply_fold_delta(registered.id, FoldDelta(state=SessionState.RUNNING))
    store.apply_stop_verdict(
        session_id=registered.id,
        verdict=DONE,
        ended_at="2026-09-17T11:00:00Z",
        exit_code=0,
    )
    store.set_app_state("m3.moved", 1)
    store.bump_anomaly("moved")

    assert store.get_app_state("m3.moved") == 1
    assert store.list_anomaly_counts() == {"moved": 1}
    stopped = store.get_session(registered.id)
    assert stopped is not None
    assert stopped.state is SessionState.RUNNING
    assert stopped.ended_at == "2026-09-17T11:00:00Z"

    idents = store.writer_thread_idents()
    assert len(idents) == 1, f"ADR-7 says one writer thread, saw {len(idents)}"
    assert threading.get_ident() not in idents, "a moved write ran on the calling thread"


def test_every_moved_write_is_refused_once_the_store_is_closed(tmp_path: Path) -> None:
    """Proof each moved verb still goes through `_write`, not its own connection."""
    closed = open_store(tmp_path / "data" / "shepherd.db")
    space = closed.create_project(name="shepherd", description=None)
    registered = closed.register_session(
        engine_session_id="eng-closed",
        workspace_id=space.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    closed.close()

    refused: list[typing.Callable[[], object]] = [
        lambda: closed.create_project(name="late", description=None),
        lambda: closed.upsert_repo("/root/Late", "late", None, "/root/Late/.git"),
        lambda: closed.register_session(
            engine_session_id="eng-late",
            workspace_id=space.id,
            repo_id=None,
            cwd="/root/Late",
            started_at="2026-09-17T10:00:00Z",
            origin=Origin.EXTERNAL,
            ownership=Ownership.ATTACHED,
        ),
        lambda: closed.apply_fold_delta(registered.id, FoldDelta(state=SessionState.RUNNING)),
        lambda: closed.apply_stop_verdict(
            session_id=registered.id,
            verdict=DONE,
            ended_at="2026-09-17T11:00:00Z",
            exit_code=0,
        ),
        lambda: closed.set_app_state("m3.late", 1),
        lambda: closed.bump_anomaly("late"),
    ]
    for verb in refused:
        with pytest.raises(RuntimeError):
            verb()


def test_the_reexports_are_aliases_not_copies() -> None:
    """`db.py` keeps three names on its surface; none of them is a second home.

    `StoreError` is what a caller catches, `DELTA_COLUMNS` is what two signals
    tests assert D37's totality over, and `_now` is the store's row clock — which
    `test_every_production_stamp_writer_emits_the_one_format` calls expecting the
    **real** writer. A copy of any of the three would let the original drift
    while every test stayed green, which is the defect this suite exists for.
    """
    assert db.StoreError is models.StoreError
    assert db.DELTA_COLUMNS is writes.DELTA_COLUMNS
    assert db._now is writes._now




# ----- T1.6: the project verbs, delegated ------------------------------------

#: Every verb D57 adds to `Store`. Named once so the two properties below —
#: crosses the one writer thread, refused once closed — are total over the set
#: rather than over whichever verbs someone remembered to list twice.
PROJECT_WRITES = (
    "create_project",
    "rename_project",
    "commit_project_delete",
    "add_repo",
    "remove_repo",
)
PROJECT_READS = (
    "get_workspace",
    "plan_project_delete",
    "projects_by_repo",
    "projects_for_repo",
    "project_last_activity",
    "repo_counts",
    "running_sessions_for",
)


@pytest.fixture()
def project_store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "projects" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def test_every_project_verb_is_on_the_store_surface(project_store: Store) -> None:
    missing = [
        name
        for name in (*PROJECT_WRITES, *PROJECT_READS, "upsert_repo")
        if not hasattr(project_store, name)
    ]
    assert missing == []
    # RD-1: the verb D57 removes is gone from the surface, not merely unused.
    assert not hasattr(project_store, "upsert_workspace")


def test_every_project_write_crosses_the_one_writer_thread(project_store: Store) -> None:
    """ADR-7/D37 for the five lifecycle verbs. A verb wired to `self._read()`
    answers correctly on a read-write database and quietly gives D37 a second
    writer, so the idents are the assertion and the return value is not.
    """
    project = project_store.create_project(name="api", description=None)
    project_store.rename_project(workspace_id=project.id, name="payments-api")
    added = project_store.add_repo(
        workspace_id=project.id,
        root_path="/srv/api",
        name="api",
        git_common_dir="/srv/api/.git",
        vcs_remote=None,
    )
    project_store.upsert_repo(
        root_path="/srv/loose", name="loose", vcs_remote=None, git_common_dir="/srv/loose/.git"
    )
    assert project_store.repo_counts() == {project.id: 1}
    assert project_store.projects_for_repo(added.id) == [project.id]
    assert project_store.remove_repo(workspace_id=project.id, repo_id=added.id) is True
    plan = project_store.plan_project_delete(
        workspace_id=project.id, on_running=models.OnRunning.REFUSE
    )
    assert plan.refusal is None
    assert project_store.commit_project_delete(plan=plan).deleted is True
    assert project_store.get_workspace(project.id) is None

    idents = project_store.writer_thread_idents()
    assert len(idents) == 1, f"ADR-7 says one writer thread, saw {len(idents)}"
    assert threading.get_ident() not in idents, "a project write ran on the calling thread"


def test_every_project_verb_is_refused_once_the_store_is_closed(tmp_path: Path) -> None:
    """Proof each one went through `_write`/`_read` rather than opening a
    connection of its own — the only way this property can be false.
    """
    closed = open_store(tmp_path / "projects" / "shepherd.db")
    project = closed.create_project(name="api", description=None)
    closed.close()

    refused: list[typing.Callable[[], object]] = [
        lambda: closed.create_project(name="late", description=None),
        lambda: closed.rename_project(workspace_id=project.id, name="late"),
        lambda: closed.commit_project_delete(
            plan=models.DeletePlan(
                workspace_id=project.id, on_running=models.OnRunning.REFUSE
            )
        ),
        lambda: closed.add_repo(
            workspace_id=project.id,
            root_path="/srv/late",
            name="late",
            git_common_dir="/srv/late/.git",
            vcs_remote=None,
        ),
        lambda: closed.remove_repo(workspace_id=project.id, repo_id="r-1"),
        lambda: closed.upsert_repo(
            root_path="/srv/late", name="late", vcs_remote=None, git_common_dir="/srv/late/.git"
        ),
        lambda: closed.get_workspace(project.id),
        lambda: closed.plan_project_delete(
            workspace_id=project.id, on_running=models.OnRunning.REFUSE
        ),
        lambda: closed.projects_by_repo(),
        lambda: closed.projects_for_repo("r-1"),
        lambda: closed.project_last_activity(),
        lambda: closed.repo_counts(),
        lambda: closed.running_sessions_for(project.id),
    ]
    assert len(refused) == len(PROJECT_WRITES) + len(PROJECT_READS) + 1
    for verb in refused:
        with pytest.raises(RuntimeError):
            verb()


def test_a_kill_between_the_two_halves_may_write_to_the_store(project_store: Store) -> None:
    """The deadlock the split exists to make unreachable, driven end to end.

    `orchestration/lifecycle.record_and_terminate` opens with
    `store.set_app_state(...)` — write the record, *then* kill, because that is
    the order that survives a crash mid-way, so it cannot be reordered. While
    the delete took a `kill` callable, that write was issued from inside
    `_write`'s job: it enqueued behind the writer thread that was blocked on
    `done.wait()` waiting for the job to finish, and **every subsequent write in
    the process hung, permanently** — a daemon thread and no timeout anywhere.
    Reproduced before the fix as *"DEADLOCK: delete_project did not return
    within 10s"*.

    Run on a thread so the failure is a failed assertion rather than a suite
    that never ends. The `set_app_state` is not decoration: a kill that does not
    touch the store cannot fail this test, and the real one always does.

    The kill also **stops the session** (`apply_stop_verdict`, writing
    `ended_at`) — a second store write from the same between-the-halves window,
    and the only kill production makes. It used to only append the id to a list,
    which the commit half took on trust; it now re-derives the running set and
    would refuse, so this test drives the full two-write sequence the real path
    issues.
    """
    project = project_store.create_project(name="api", description=None)
    session = project_store.register_session(
        engine_session_id="eng-live",
        workspace_id=project.id,
        repo_id=None,
        cwd="/tmp/x",
        started_at="2026-09-21T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )

    answer: list[object] = []

    def run() -> None:
        plan = project_store.plan_project_delete(
            workspace_id=project.id, on_running=models.OnRunning.KILL
        )
        killed: list[str] = []
        for session_id in plan.running:
            # Exactly what the kill path does first, and where it used to hang.
            project_store.set_app_state(f"kill_record.{session_id}", {"recorded": True})
            # ...and then the kill itself, which is a second store write:
            # `apply_stop_verdict` sets `ended_at`, and that — not the id in
            # this list — is what the commit half re-derives its answer from.
            project_store.apply_stop_verdict(
                session_id=session_id,
                verdict=DONE,
                ended_at="2026-09-21T10:01:00Z",
                exit_code=None,
            )
            killed.append(session_id)
        answer.append(
            project_store.commit_project_delete(plan=plan, killed=tuple(killed))
        )

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10.0)
    assert not worker.is_alive(), "the delete did not return within 10s: the writer deadlocked"

    outcome = answer[0]
    assert isinstance(outcome, models.DeleteOutcome)
    assert (outcome.deleted, outcome.killed) == (True, (session.id,))
    assert project_store.get_workspace(project.id) is None
    # The kill's own record survives the delete: it was written in its own
    # transaction, before the one that removed the rows.
    assert project_store.get_app_state(f"kill_record.{session.id}") == {"recorded": True}


def test_the_commit_half_refuses_a_session_that_arrived_after_the_kill(
    project_store: Store,
) -> None:
    """The cost of splitting the verb, named and paid.

    The decision is a read taken before the caller went away to kill things, so
    the world can move underneath it. The commit re-derives the decision inside
    its own transaction and **refuses** rather than deleting a session nobody
    stopped.

    **This test changed with the code, and says so.** Its control used to be
    *"the same call with the newcomer's id in `killed`, which proceeds"* — it
    asserted `(True, (latecomer.id,))` for a session that was **still
    running**, which pinned the inverted behaviour as the specification: the
    caller's claim overruled the store's own `ended_at`, and the row was
    destroyed under a live agent. Naming an id in `killed` is no longer a way
    past this gate, and it must not become one again: the control now *stops*
    the latecomer, and the claim-only call is the second refusal below.
    """
    project = project_store.create_project(name="api", description=None)
    plan = project_store.plan_project_delete(
        workspace_id=project.id, on_running=models.OnRunning.KILL
    )
    assert plan.running == ()

    latecomer = project_store.register_session(
        engine_session_id="eng-late",
        workspace_id=project.id,
        repo_id=None,
        cwd="/tmp/x",
        started_at="2026-09-21T10:05:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )

    refused = project_store.commit_project_delete(plan=plan, killed=())
    assert refused.deleted is False
    assert refused.running == (latecomer.id,)
    assert project_store.get_workspace(project.id) is not None

    # Claiming the kill, without having made it, is still a refusal: the gate
    # is the store's own re-derived running set and nothing the caller says.
    claimed = project_store.commit_project_delete(plan=plan, killed=(latecomer.id,))
    assert claimed.deleted is False
    assert claimed.running == (latecomer.id,)
    assert claimed.killed == ()
    assert project_store.get_workspace(project.id) is not None

    # The control, and the only branch that proceeds: the kill lands, the store
    # sees `ended_at`, and the gate opens on the store's own observation.
    project_store.apply_stop_verdict(
        session_id=latecomer.id,
        verdict=DONE,
        ended_at="2026-09-21T10:06:00Z",
        exit_code=None,
    )
    proceeds = project_store.commit_project_delete(plan=plan, killed=(latecomer.id,))
    assert proceeds.deleted is True
    assert project_store.get_workspace(project.id) is None
    # ...and `killed` is **empty**, deliberately, on a kill that really landed.
    #
    # The report is the caller's claim intersected with what the store saw
    # *change*: `plan.running - fresh.running`. The latecomer was never in
    # `plan.running` — the plan was read before it existed — so the store never
    # observed it running and cannot prove it stopped rather than having ended
    # on its own. The limit is real and it errs the safe way: on the one verb
    # that destroys data, `killed` under-reports rather than asserting a stop
    # nobody watched. `destroyed` still names the row, so the dialog is not
    # silent about what went.
    assert proceeds.killed == ()
    assert proceeds.destroyed == (latecomer.id,)


def test_no_write_hangs_when_close_races_it(tmp_path: Path) -> None:
    """`_write` used to check `self._closed` and *then* enqueue.

    A `close()` landing between the two put its `None` sentinel, the writer
    thread returned, and the job enqueued behind it was never taken — leaving
    the caller on a `done.wait()` with no timeout that nobody would ever set
    (probe P7). The check and the `put` are now one critical section under
    `_close_lock`, so the interleaving cannot be constructed at all: the probe
    that modelled it parked *inside* `put`, and a `queue.Queue` with no maximum
    never blocks there.

    **What this test is and is not.** It is a bound, not a proof of the window:
    eight writers racing a `close()`, every one of which must finish — with a
    result or with `RuntimeError("store is closed")` — and none of which may
    still be alive after five seconds. It would not reliably have gone red
    against the old code, whose window was a few instructions wide; what it
    refuses is a *reintroduced* unbounded wait, which hangs every time.
    """
    store = open_store(tmp_path / "race" / "shepherd.db")
    outcomes: list[object] = []
    started = threading.Barrier(9)

    def write(index: int) -> None:
        started.wait()
        try:
            outcomes.append(store.create_project(name=f"p{index}", description=None))
        except RuntimeError as refusal:
            outcomes.append(refusal)

    writers = [threading.Thread(target=write, args=(index,), daemon=True) for index in range(8)]
    for writer in writers:
        writer.start()
    started.wait()
    store.close()
    for writer in writers:
        writer.join(timeout=5.0)

    alive = [writer.name for writer in writers if writer.is_alive()]
    assert alive == [], f"a write never returned after close(): {alive}"
    assert len(outcomes) == 8
    assert all(
        isinstance(outcome, (models.Workspace, RuntimeError)) for outcome in outcomes
    ), outcomes


def test_close_cannot_land_between_the_closed_check_and_the_enqueue(tmp_path: Path) -> None:
    """The window itself, deterministically — what the bound above is not.

    `test_no_write_hangs_when_close_races_it` races eight writers against a
    `close()` and asserts none of them hangs. Its own docstring concedes it
    *"would not reliably have gone red against the old code"*: the window was a
    few instructions wide and a thread scheduler will not reliably land in it.
    A test that cannot be seen to fail on the defect it names is a bound on
    regression, not a proof of the property.

    This one constructs the interleaving instead of hoping for it. It parks a
    writer **inside** `_queue.put` — the probe that modelled this could not,
    because an unbounded `queue.Queue` never blocks there, so the block is
    injected — and then asserts that `close()` **cannot proceed**: it is parked
    on `_close_lock`, which `_write` is holding across the pair. That is the
    property, stated positively. If the check and the `put` were two operations
    again, `close()` would sail through, set `_closed`, and write its sentinel
    ahead of a job that would then never be taken.

    This reaches past the public surface on purpose: `_close_lock` is an
    *internal* seam and the invariant is about the internal seam. There is no
    way to observe "these two statements are one critical section" from
    outside, and the alternative — a probabilistic race — is the thing being
    replaced.

    **The control drives the other branch**: with nothing parked in `put`, the
    same `close()` on the same store returns well inside the same deadline. So
    the wait below is measuring the lock, not a slow `close()`.
    """
    store = open_store(tmp_path / "window" / "shepherd.db")
    inside_put = threading.Event()
    release_put = threading.Event()
    real_put = store._queue.put

    def parking_put(item: object, *args: object, **kwargs: object) -> None:
        # Only the first real job parks; the `None` sentinel and everything
        # after must pass straight through or `close()` could never finish.
        if item is not None and not inside_put.is_set():
            inside_put.set()
            assert release_put.wait(timeout=5.0), "the test never released the parked put"
        real_put(item, *args, **kwargs)  # type: ignore[arg-type]

    store._queue.put = parking_put  # type: ignore[method-assign]
    written: list[object] = []
    closed = threading.Event()

    def write() -> None:
        try:
            written.append(store.create_project(name="api", description=None))
        except BaseException as error:  # pragma: no cover - reported by assertion
            written.append(error)

    def close() -> None:
        store.close()
        closed.set()

    writer = threading.Thread(target=write, daemon=True)
    closer = threading.Thread(target=close, daemon=True)
    try:
        writer.start()
        assert inside_put.wait(timeout=5.0), "the writer never reached _queue.put"
        closer.start()

        # The assertion. `close()` wants `_close_lock`; `_write` is holding it
        # across the closed-check *and* the put, and the put is parked.
        assert not closed.wait(timeout=1.0), (
            "close() completed while a write was inside _queue.put: the closed-check "
            "and the enqueue are not one critical section"
        )
    finally:
        release_put.set()

    writer.join(timeout=5.0)
    closer.join(timeout=5.0)
    assert not writer.is_alive() and not closer.is_alive()
    assert closed.is_set(), "close() never completed once the put was released"
    assert len(written) == 1 and isinstance(written[0], models.Workspace), written

    # The control: no park, and `close()` clears the same deadline easily —
    # so the wait above timed out on the lock and not on `close()` being slow.
    control = open_store(tmp_path / "control" / "shepherd.db")
    control_closed = threading.Event()

    def close_control() -> None:
        control.close()
        control_closed.set()

    unblocked = threading.Thread(target=close_control, daemon=True)
    unblocked.start()
    assert control_closed.wait(timeout=1.0), "close() on an idle store did not finish in 1s"
    unblocked.join(timeout=5.0)
