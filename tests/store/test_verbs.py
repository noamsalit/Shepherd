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
from shepherd.store import models
from shepherd.store.db import Store, StoreError, open_store

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
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
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
    for verb in ("snapshot", "upsert_workspace", "upsert_repo", "register_session", "fleet"):
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
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
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
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
    first = store.upsert_repo(
        workspace_id=workspace.id,
        root_path="/root/Shepherd",
        name="Shepherd",
        vcs_remote=None,
        git_common_dir="/root/Shepherd/.git",
    )
    again = store.upsert_repo(
        workspace_id=workspace.id,
        root_path="/root/Shepherd",
        name="Shepherd",
        vcs_remote="github.com/example-org/shepherd",
        git_common_dir="/root/Shepherd/.git",
    )
    assert again.id == first.id
    assert again.vcs_remote == "github.com/example-org/shepherd"

    assert store.find_repo_by_common_dir("/root/Shepherd/.git") == again
    assert store.find_repo_by_common_dir("/elsewhere/.git") is None

    # Workspaces are keyed by name, so the repo's workspace is stable too.
    assert store.upsert_workspace("shepherd", "/root/Shepherd").id == workspace.id
    assert [w.name for w in store.list_workspaces()] == ["shepherd"]


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
    workspace = opened.upsert_workspace("shepherd", None)
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
        opened.upsert_workspace("late", None)
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
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
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
    `discover_repos` starts looking; repos may live anywhere (D22)".

    The repo below that lives **outside** its workspace root is the case that
    matters: it is the normal case for any repo not nested under the root, and
    it is invisible to every other read verb.
    """
    inside = store.upsert_workspace("inside", "/srv/work")
    other = store.upsert_workspace("other", "/srv/other")
    store.upsert_repo(
        workspace_id=inside.id,
        root_path="/srv/work/api",
        name="api",
        vcs_remote=None,
        git_common_dir="/srv/work/api/.git",
    )
    store.upsert_repo(
        workspace_id=inside.id,
        root_path="/elsewhere/frontend",
        name="frontend",
        vcs_remote=None,
        git_common_dir="/elsewhere/frontend/.git",
    )
    store.upsert_repo(
        workspace_id=other.id,
        root_path="/srv/other/tools",
        name="tools",
        vcs_remote=None,
        git_common_dir="/srv/other/tools/.git",
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
    assert frontend.workspace_id == inside.id and frontend.active is True


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
