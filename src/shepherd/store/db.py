"""The verb surface (D33) — the only place SQL lives.

Three rules make D2's engine swap a rewrite of this package rather than of its
callers: verbs instead of queries, dataclasses instead of driver rows, and
transactions that stay inside.

ADR-7's threading model is part of that surface, not an implementation detail.
`controld` drives these verbs from three concurrent producers (a
`ThreadingHTTPServer`, the fold of relayed frames, and the 2.0 s registry scan),
so:

* every **write** crosses one serialising writer thread that owns the single
  read-write connection, created *on that thread* — so `check_same_thread`
  stays at its default and the failure it guards cannot occur;
* every **read** uses a `threading.local()` read-only connection under WAL, so
  a request thread never queues behind the writer;
* `open_store()` starts that thread and `close()` drains, joins and closes it.

The **implementations** live in sibling modules — `reads.py` and `writes.py`
(M1/M2), `sessions.py` and `mailbox.py` (M3's owned-session and mailbox verbs),
`stops.py` (M2's one stop statement) — and every method below is a delegation
that hands one of them the connection this module owns. That is blockers T4-2
and T4-3's split: the cap said this file was doing too much, so the file was
emptied rather than the cap raised, and Task 4's own words — *"delegating
methods only"* — are what "emptied" means. `Store` is still the single name a
caller imports, no caller's import line changed, and the connection never leaves
`store/` (D33).
"""

from __future__ import annotations

import queue
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from shepherd.core.fold_types import FoldDelta, SessionSnapshot
from shepherd.core.mailbox import MailboxCounts, MailboxMessage
from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState, TitleSource
from shepherd.core.stops import Verdict
from shepherd.store import mailbox as mailbox_verbs
from shepherd.store import reads
from shepherd.store import sessions as session_verbs
from shepherd.store import writes
from shepherd.store.migrate import migrate
from shepherd.store.models import (
    DeleteOutcome,
    FleetRow,
    OnRunning,
    Repo,
    ReplayTarget,
    Session,
    StopCounts,
    Workspace,
)

#: Re-exported explicitly (`--no-implicit-reexport`) because `StoreError` is the
#: name a caller catches and `db` is the module a caller imports: four test
#: modules and every consumer say `from shepherd.store.db import StoreError`.
#: Its home is `models.py` (T4-3); this line is the surface, not a second home.
from shepherd.store.models import StoreError as StoreError

#: Two more names T4-3 moved to `writes.py` that consumers reach for through
#: `db`, which is the module a caller imports: `DELTA_COLUMNS` carries D37's
#: totality (`test_delta_fields_are_all_known_to_the_store`,
#: `test_every_delta_field_reaches_a_store_column`) and `_now` is the store's row
#: clock, which `test_every_production_stamp_writer_emits_the_one_format` calls
#: expecting **the real writer**. Both are aliases, never copies — a second
#: `_now()` body here would stay green while the writer drifted, the BLOCKING-1
#: shape — and `test_the_reexports_are_aliases_not_copies` pins the identity.
from shepherd.store.writes import DELTA_COLUMNS as DELTA_COLUMNS
from shepherd.store.writes import _now as _now

T = TypeVar("T")

_Job = Callable[[sqlite3.Connection], None]

class Store:
    """The verbs. Construct through `open_store()`, which starts the writer."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._local = threading.local()
        self._readers: list[sqlite3.Connection] = []
        self._readers_lock = threading.Lock()
        self._writer_idents: set[int] = set()
        self._closed = False
        self._close_lock = threading.Lock()
        self._writer = threading.Thread(target=self._writer_loop, name="store-writer", daemon=True)
        self._ready = threading.Event()
        self._writer.start()
        self._ready.wait()

    # ----- lifecycle -------------------------------------------------------

    def _writer_loop(self) -> None:
        connection = sqlite3.connect(self._db_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        self._ready.set()
        try:
            while True:
                job = self._queue.get()
                if job is None:
                    return
                self._writer_idents.add(threading.get_ident())
                job(connection)
        finally:
            connection.close()

    def close(self) -> None:
        """Drain the queue, join the writer, close every connection (F15)."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(None)
        self._writer.join()
        own: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if own is not None:
            own.close()
        with self._readers_lock:
            # A read connection may only be closed by the thread that opened it
            # (`check_same_thread`), so the rest are released by dropping the
            # last reference to them: the driver closes on collection, and the
            # threads that own them — HTTP request threads — are gone by then.
            self._readers.clear()
        self._local = threading.local()

    def writer_is_alive(self) -> bool:
        return self._writer.is_alive()

    def writer_thread_idents(self) -> frozenset[int]:
        """Every thread that has executed a write. ADR-7 says exactly one."""
        return frozenset(self._writer_idents)

    def reader_connection_id(self) -> int:
        """Identity of *this* thread's read connection (ADR-7's thread-locality)."""
        return id(self._reader())

    # ----- plumbing --------------------------------------------------------

    def _reader(self) -> sqlite3.Connection:
        existing: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if existing is not None:
            return existing
        connection = sqlite3.connect(
            f"file:{self._db_path}?mode=ro", uri=True, check_same_thread=True
        )
        connection.row_factory = sqlite3.Row
        self._local.connection = connection
        with self._readers_lock:
            self._readers.append(connection)
        return connection

    def _read(self) -> sqlite3.Connection:
        """This thread's read connection, refused once the store is closed.

        The connection is handed to a verb module and never to a caller: D33's
        line is that callers get verbs on the store, never a connection.
        """
        if self._closed:
            raise RuntimeError("store is closed")
        return self._reader()

    def _write(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Enqueue `work` onto the writer thread and block on its result.

        The transaction is opened and closed here, so no caller ever writes
        `with store.transaction():` (D33 rule 3).
        """
        if self._closed:
            raise RuntimeError("store is closed")
        result: list[T] = []
        failure: list[BaseException] = []
        done = threading.Event()

        def run(connection: sqlite3.Connection) -> None:
            try:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    result.append(work(connection))
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
                connection.execute("COMMIT")
            except sqlite3.Error as error:
                failure.append(StoreError(str(error)))
            except BaseException as error:  # pragma: no cover - defensive
                failure.append(error)
            finally:
                done.set()

        self._queue.put(run)
        done.wait()
        if failure:
            raise failure[0]
        return result[0]

    # ----- workspace and repo ---------------------------------------------

    def create_project(self, *, name: str, description: str | None) -> Workspace:
        return self._write(lambda c: writes.create_project(c, name=name, description=description))

    def rename_project(self, *, workspace_id: str, name: str) -> Workspace | None:
        return self._write(
            lambda c: writes.rename_project(c, workspace_id=workspace_id, name=name)
        )

    def delete_project(
        self, *, workspace_id: str, on_running: OnRunning, kill: Callable[[str], None]
    ) -> DeleteOutcome:
        return self._write(
            lambda c: writes.delete_project(
                c, workspace_id=workspace_id, on_running=on_running, kill=kill
            )
        )

    def add_repo(
        self,
        *,
        workspace_id: str,
        root_path: str,
        name: str,
        git_common_dir: str,
        vcs_remote: str | None,
    ) -> Repo:
        return self._write(
            lambda c: writes.add_repo(
                c,
                workspace_id=workspace_id,
                root_path=root_path,
                name=name,
                git_common_dir=git_common_dir,
                vcs_remote=vcs_remote,
            )
        )

    def remove_repo(self, *, workspace_id: str, repo_id: str) -> bool:
        return self._write(
            lambda c: writes.remove_repo(c, workspace_id=workspace_id, repo_id=repo_id)
        )

    def upsert_repo(
        self,
        root_path: str,
        name: str,
        vcs_remote: str | None,
        git_common_dir: str,
    ) -> Repo:
        """The **unattached** repo row (F10) — what discovery writes. `add_repo`
        is the verb that also registers it to a project."""
        return self._write(
            lambda c: writes.upsert_repo(c, root_path, name, vcs_remote, git_common_dir)
        )

    def find_repo_by_common_dir(self, git_common_dir: str) -> Repo | None:
        return reads.find_repo_by_common_dir(self._read(), git_common_dir)

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return reads.get_workspace(self._read(), workspace_id)

    def list_repos(self, workspace_id: str) -> list[Repo]:
        return reads.list_repos(self._read(), workspace_id)

    def list_workspaces(self) -> list[Workspace]:
        return reads.list_workspaces(self._read())

    def projects_for_repo(self, repo_id: str) -> list[str]:
        return reads.projects_for_repo(self._read(), repo_id)

    def project_last_activity(self) -> dict[str, str]:
        return reads.project_last_activity(self._read())

    def repo_counts(self) -> dict[str, int]:
        return reads.repo_counts(self._read())

    def running_sessions_for(self, workspace_id: str) -> list[Session]:
        return reads.running_sessions_for(self._read(), workspace_id)

    # ----- sessions --------------------------------------------------------

    def register_session(
        self,
        engine_session_id: str,
        workspace_id: str,
        repo_id: str | None,
        cwd: str,
        started_at: str,
        origin: Origin,
        ownership: Ownership,
        now: float | None = None,
    ) -> Session:
        return self._write(
            lambda c: writes.register_session(
                c,
                engine_session_id,
                workspace_id,
                repo_id,
                cwd,
                started_at,
                origin,
                ownership,
                now,
            )
        )

    def apply_fold_delta(self, session_id: str, delta: FoldDelta) -> Session:
        return self._write(lambda c: writes.apply_fold_delta(c, session_id, delta))

    def get_session(self, session_id: str) -> Session | None:
        return reads.get_session(self._read(), session_id)

    def get_session_by_engine_id(self, engine_session_id: str) -> Session | None:
        return reads.get_session_by_engine_id(self._read(), engine_session_id)

    def list_sessions(
        self, workspace_id: str | None = None, state: SessionState | None = None
    ) -> list[Session]:
        return reads.list_sessions(self._read(), workspace_id, state)

    def snapshot(self, session_id: str) -> SessionSnapshot | None:
        return reads.snapshot(self._read(), session_id)

    def sessions_with_liveness_inputs(self) -> list[tuple[str, int, str]]:
        return reads.sessions_with_liveness_inputs(self._read())

    def fleet(self) -> list[FleetRow]:
        return reads.fleet(self._read())

    # ----- owned sessions (M3, T4) -----------------------------------------

    def create_owned_session(
        self,
        *,
        session_id: str,
        engine_session_id: str | None,
        workspace_id: str,
        repo_id: str | None,
        cwd: str,
        started_at: str,
        origin: Origin,
        parent_session_id: str | None,
        depth: int,
        ephemeral: bool,
        title: str | None,
        title_source: TitleSource,
        handle: RunnerHandle | None,
        model: str | None,
        effort: str | None,
    ) -> Session:
        return self._write(
            lambda connection: session_verbs.create_owned_session(
                connection,
                session_id=session_id,
                engine_session_id=engine_session_id,
                workspace_id=workspace_id,
                repo_id=repo_id,
                cwd=cwd,
                started_at=started_at,
                origin=origin,
                parent_session_id=parent_session_id,
                depth=depth,
                ephemeral=ephemeral,
                title=title,
                title_source=title_source,
                handle=handle,
                model=model,
                effort=effort,
            )
        )

    def get_owned_session(self, session_id: str) -> Session | None:
        return session_verbs.get_owned_session(self._read(), session_id)

    def set_runner_handle(self, session_id: str, handle: RunnerHandle) -> None:
        self._write(lambda c: session_verbs.set_runner_handle(c, session_id, handle))

    def bind_engine_session_id(self, session_id: str, engine_session_id: str) -> int:
        return self._write(
            lambda c: session_verbs.bind_engine_session_id(c, session_id, engine_session_id)
        )

    def rebind_engine_session_id(self, session_id: str, engine_session_id: str) -> None:
        self._write(
            lambda c: session_verbs.rebind_engine_session_id(c, session_id, engine_session_id)
        )

    def apply_title(self, session_id: str, title: str, source: TitleSource) -> Session:
        return self._write(lambda c: session_verbs.apply_title(c, session_id, title, source))

    def set_title_synced_at(self, session_id: str, synced_at: str) -> None:
        self._write(lambda c: session_verbs.set_title_synced_at(c, session_id, synced_at))

    def set_ephemeral(self, session_id: str, ephemeral: bool) -> None:
        self._write(lambda c: session_verbs.set_ephemeral(c, session_id, ephemeral))

    def owned_session_counts(self) -> tuple[int, int]:
        return session_verbs.owned_session_counts(self._read())

    def children_of(self, session_id: str) -> int:
        return session_verbs.children_of(self._read(), session_id)

    # ----- the mailbox (M3, T4) --------------------------------------------

    def enqueue(self, message: MailboxMessage) -> MailboxMessage:
        return self._write(lambda c: mailbox_verbs.enqueue(c, message))

    def pending_for(self, session_id: str) -> list[MailboxMessage]:
        return mailbox_verbs.pending_for(self._read(), session_id)

    def sessions_with_pending(self) -> list[str]:
        return mailbox_verbs.sessions_with_pending(self._read())

    def mark_delivered(self, ids: tuple[str, ...], delivered_at: str) -> int:
        return self._write(lambda c: mailbox_verbs.mark_delivered(c, ids, delivered_at))

    def record_refusal(self, ids: tuple[str, ...], refusal: str) -> None:
        self._write(lambda c: mailbox_verbs.record_refusal(c, ids, refusal))

    def mailbox_counts(self) -> MailboxCounts:
        return mailbox_verbs.mailbox_counts(self._read())

    # ----- the stop group (M2, T2) ----------------------------------------

    def apply_stop_verdict(
        self, session_id: str, verdict: Verdict, ended_at: str, exit_code: int | None
    ) -> Session:
        """The only writer of the nine stop columns, asserted over `src/` (D37)."""
        return self._write(
            lambda c: writes.apply_stop_verdict(c, session_id, verdict, ended_at, exit_code)
        )

    def stop_verdict_counts(self) -> StopCounts:
        return reads.stop_verdict_counts(self._read())

    def sessions_for_replay(self, since: str | None) -> list[ReplayTarget]:
        return reads.sessions_for_replay(self._read(), since)

    # ----- the master's wake set and its lineage cap (M4, T8) --------------

    def wake_candidates(self, since: str | None) -> tuple[Session, ...]:
        """D31's wake set — master-owned rows that stopped `unfinished` or
        `error` since `since`. `None` asks for all of them."""
        return reads.wake_candidates(self._read(), since)

    def link_retry(self, session_id: str, retry_of: str) -> Session:
        """Record that `session_id` is a retry of `retry_of` — the only writer
        of the column D31's cap is computed from (T10)."""
        return self._write(lambda c: writes.link_retry(c, session_id, retry_of))

    def retry_chain_depth(self, session_id: str) -> int:
        """The size of this session's `retry_of` lineage, **walked**. D31's cap
        is a property of the lineage, not of the `attempt` column (T10)."""
        return reads.retry_chain_depth(self._read(), session_id)

    # ----- app state -------------------------------------------------------

    def get_app_state(self, key: str) -> object | None:
        return reads.get_app_state(self._read(), key)

    def set_app_state(self, key: str, value: object) -> None:
        self._write(lambda c: writes.set_app_state(c, key, value))

    def list_anomaly_counts(self) -> dict[str, int]:
        return reads.list_anomaly_counts(self._read())

    def bump_anomaly(self, kind: str) -> None:
        self._write(lambda c: writes.bump_anomaly(c, kind))


def open_store(db_path: Path) -> Store:
    """Create the data dir, apply migrations, start the writer thread (ADR-2)."""
    migrate(db_path)
    return Store(db_path)
