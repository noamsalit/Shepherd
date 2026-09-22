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
PROJECT_WRITES = ("create_project", "rename_project", "delete_project", "add_repo", "remove_repo")
PROJECT_READS = (
    "get_workspace",
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
    assert project_store.delete_project(
        workspace_id=project.id, on_running=models.OnRunning.REFUSE, kill=lambda _: None
    ).deleted is True
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
        lambda: closed.delete_project(
            workspace_id=project.id, on_running=models.OnRunning.REFUSE, kill=lambda _: None
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
        lambda: closed.projects_for_repo("r-1"),
        lambda: closed.project_last_activity(),
        lambda: closed.repo_counts(),
        lambda: closed.running_sessions_for(project.id),
    ]
    assert len(refused) == len(PROJECT_WRITES) + len(PROJECT_READS) + 1
    for verb in refused:
        with pytest.raises(RuntimeError):
            verb()
