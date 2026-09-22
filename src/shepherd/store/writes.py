"""The M1/M2 write verbs — every `INSERT` and `UPDATE` `Store` performs (D33).

A **sibling** of `db.py` for the reason `reads.py`, `sessions.py`, `mailbox.py`,
`rows.py` and `stops.py` are siblings of it, and the second half of the split
`reads.py` began (blockers T4-2, T4-3). Task 4's own words are the target:
*"`db.py` — delegating methods only"*. The ~300 lines below are what kept it from
being that.

`db.py` keeps the verb **surface** — `Store` is still the only name a caller
imports, and no caller's import line changed — and hands every function here the
`sqlite3.Connection` its writer thread owns (ADR-7). Nothing here opens a
connection, and nothing here opens a transaction: `Store._write` does both, so
D33 rule 3 holds exactly and the connection never leaves `store/`.

**One writer, one rule set (D37).** `apply_stop_verdict` is still the only writer
of the nine stop columns — it delegates to `stops.write_verdict`, the single
statement that writes them — and M2 asserts that over `src/`. Moving the verb
from `db.py` to this module moves the body, not the rule: there is one caller of
`write_verdict` here and none anywhere else.
"""

from __future__ import annotations

import json
import sqlite3

from shepherd.core.clock import utc_now
from shepherd.core.fold_types import FoldDelta
from shepherd.core.ids import new_ulid
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import Verdict
from shepherd.store.models import (
    DEFAULT_ENGINE,
    SESSION_COLUMNS,
    UNASSIGNED_PROJECT_ID,
    DeleteOutcome,
    DeletePlan,
    OnRunning,
    Repo,
    Session,
    SeveredLink,
    StoreError,
    Workspace,
)
from shepherd.store.reads import ANOMALY_KEY_PREFIX, get_workspace, plan_project_delete
from shepherd.store.rows import repo, session, workspace
from shepherd.store.stops import write_verdict

#: The three `FoldDelta` fields stored as a JSON array rather than a scalar.
SET_COLUMNS: frozenset[str] = frozenset(
    {"live_subagent_ids", "created_task_ids", "completed_task_ids"}
)

#: `FoldDelta` field -> `session` column. Total over `FoldDelta` since the four
#: fold-state columns landed (`test_delta_fields_are_all_known_to_the_store`).
DELTA_COLUMNS: tuple[str, ...] = (
    "last_event_at",
    "state",
    "needs_you_reason",
    "brief",
    "cwd",
    "repo_id",
    "model",
    "tasks_total",
    "tasks_done",
    "active_subagents",
    "repos_touched",
    "title",
    "title_source",
    "ended_at",
    "pid",
    "proc_start",
    "auto_compact_at",
    "quota_notice_at",
    "observed_at",
    "live_subagent_ids",
    "created_task_ids",
    "completed_task_ids",
)


def _now() -> str:
    return utc_now()


def _delta_values(delta: FoldDelta) -> dict[str, object]:
    """The delta's set fields as columns. `None` means *untouched*, never *cleared*."""
    values: dict[str, object] = {}
    for column in DELTA_COLUMNS:
        value = getattr(delta, column)
        if value is None:
            continue
        if column == "repos_touched":
            values[column] = json.dumps(list(value))
        elif column in SET_COLUMNS:
            # Sorted, so the same set is the same bytes on every write — a
            # replayed row has to be byte-identical run to run (T12).
            values[column] = json.dumps(sorted(value))
        elif column == "state":
            values[column] = str(SessionState(value).value)
        else:
            values[column] = value
    return values


# ----- workspace and repo ----------------------------------------------------


def create_project(
    connection: sqlite3.Connection, *, name: str, description: str | None
) -> Workspace:
    """A project, declared. **Never keyed by name** (E1).

    `upsert_workspace`, which this replaces, selected by `name` — so `/work/api`
    and `/personal/api` were one row, and the second registration silently
    overwrote the first's path. Identity is `workspace.id` and a name is a
    label (D57).
    """
    workspace_id = new_ulid()
    connection.execute(
        "INSERT INTO workspace (id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (workspace_id, name, description, _now()),
    )
    fresh = connection.execute(
        "SELECT * FROM workspace WHERE id = ?", (workspace_id,)
    ).fetchone()
    return workspace(fresh)


def _refuse_reserved(workspace_id: str, verb: str) -> None:
    if workspace_id == UNASSIGNED_PROJECT_ID:
        raise StoreError(
            f"the Unassigned project cannot be {verb}: it is the reserved landing place "
            f"for work that matched no declared project, and every discovered session "
            f"binds to it (D59)"
        )


def rename_project(
    connection: sqlite3.Connection, *, workspace_id: str, name: str
) -> Workspace | None:
    """A new label on an existing project.

    The two negative answers are different things and are spelled differently:
    the reserved project is **forbidden** and raises (E8), while a project that
    does not exist is **absent** and answers `None`. Collapsing them would tell
    a caller that deleting the row first would have worked.
    """
    _refuse_reserved(workspace_id, "renamed")
    changed = connection.execute(
        "UPDATE workspace SET name = ? WHERE id = ?", (name, workspace_id)
    ).rowcount
    if not changed:
        return None
    fresh = connection.execute(
        "SELECT * FROM workspace WHERE id = ?", (workspace_id,)
    ).fetchone()
    return workspace(fresh)


#: The two columns `session` uses on itself (001:58,64), both
#: `REFERENCES session(id)`. Named once because a cascade that knows one and
#: not the other is exactly the defect this constant exists to close.
LINEAGE_COLUMNS: tuple[str, ...] = ("parent_session_id", "retry_of")


def _sever_lineage(
    connection: sqlite3.Connection, workspace_id: str
) -> tuple[SeveredLink, ...]:
    """Null every reference into the doomed cohort from a session outside it.

    `DELETE FROM session WHERE workspace_id = ?` is safe only while every
    referrer is *inside* the cohort. Under `ORPHAN` the running rows are moved
    out first — so a survivor points at a row the next statement deletes, and
    `PRAGMA foreign_keys=ON` aborts the whole transaction. A cross-project
    parent does it under any choice. The reachable case needs nothing exotic: a
    spawned child still running while its parent has stopped, and the user
    picks *"move them to Unassigned"* — the dialog asks for the one answer that
    threw, and the project became permanently undeletable.

    The links are **nulled and reported** (`DeleteOutcome.severed`), not
    silently dropped: D61 says a delete forgets, and a child whose parent was
    forgotten honestly has no parent, but a person is owed the fact.
    """
    severed: list[SeveredLink] = []
    for column in LINEAGE_COLUMNS:
        predicate = (
            f"workspace_id <> ? AND {column} IN"
            " (SELECT id FROM session WHERE workspace_id = ?)"
        )
        rows = connection.execute(
            f"SELECT id FROM session WHERE {predicate} ORDER BY id",
            (workspace_id, workspace_id),
        ).fetchall()
        if not rows:
            continue
        connection.execute(
            f"UPDATE session SET {column} = NULL WHERE {predicate}",
            (workspace_id, workspace_id),
        )
        severed.extend(SeveredLink(session_id=str(row["id"]), column=column) for row in rows)
    return tuple(severed)


def commit_project_delete(
    connection: sqlite3.Connection,
    *,
    plan: DeletePlan,
    killed: tuple[str, ...] = (),
) -> DeleteOutcome:
    """The second half of D61's delete: the rows, and only the rows.

    The first half is `reads.plan_project_delete`, a pure read. Between the two
    the caller stops whatever it decided to stop — **outside** this transaction,
    because `Store._write` runs its work on the one writer thread inside
    `BEGIN IMMEDIATE`, and a kill issued from there both deadlocks against its
    own first statement and cannot be rolled back with the rows. `killed` is
    what the caller reports it *actually* killed, which is a thing the old
    `Callable[[str], None]` could not say.

    The decision is re-derived here, against the same connection and inside the
    same transaction, because the plan was read before the caller went away to
    kill things: a project that acquired a session in the meantime is refused
    rather than deleted out from under it.

    The cascade order is `mailbox_message -> session -> project_repo ->
    workspace`, preceded by the lineage severing. `repo` rows are **kept**:
    they carry D48's binding identity under `ux_repo_path`, and minting them
    afresh would orphan every historical session's `repo_id`.

    **Never raises.** Every answer is a `DeleteOutcome`.
    """
    workspace_id = plan.workspace_id
    fresh = plan_project_delete(
        connection, workspace_id=workspace_id, on_running=plan.on_running
    )
    if fresh.refusal is not None:
        return fresh.refusal

    running = fresh.running
    reported = tuple(session_id for session_id in running if session_id in set(killed))
    orphaned: tuple[str, ...] = ()
    if plan.on_running is OnRunning.KILL:
        survived = tuple(session_id for session_id in running if session_id not in set(killed))
        if survived:
            # Not the plan's running set — *this* one. A session that arrived
            # while the caller was killing was never killed, and deleting its
            # row would leave a live agent with nothing to show for it.
            return DeleteOutcome(
                deleted=False,
                refused=(
                    f"{len(survived)} session(s) in this project are still running and "
                    f"were not stopped; nothing was deleted"
                ),
                running=survived,
                killed=reported,
            )
    elif plan.on_running is OnRunning.ORPHAN and running:
        # Before the cascade, so the rows this moves are not the rows it
        # deletes. P2: no session may be left pointing at a workspace that is
        # about to go, because `fleet()` is an INNER JOIN and it would vanish.
        connection.executemany(
            "UPDATE session SET workspace_id = ? WHERE id = ?",
            [(UNASSIGNED_PROJECT_ID, session_id) for session_id in running],
        )
        orphaned = running

    severed = _sever_lineage(connection, workspace_id)
    destroyed = tuple(
        str(row["id"])
        for row in connection.execute(
            "SELECT id FROM session WHERE workspace_id = ? ORDER BY started_at, id",
            (workspace_id,),
        ).fetchall()
    )
    connection.execute(
        "DELETE FROM mailbox_message WHERE session_id IN"
        " (SELECT id FROM session WHERE workspace_id = ?)",
        (workspace_id,),
    )
    connection.execute("DELETE FROM session WHERE workspace_id = ?", (workspace_id,))
    connection.execute("DELETE FROM project_repo WHERE workspace_id = ?", (workspace_id,))
    connection.execute("DELETE FROM workspace WHERE id = ?", (workspace_id,))
    return DeleteOutcome(
        deleted=True,
        killed=reported if plan.on_running is OnRunning.KILL else (),
        orphaned=orphaned,
        severed=severed,
        destroyed=destroyed,
    )


def upsert_repo(
    connection: sqlite3.Connection,
    root_path: str,
    name: str,
    vcs_remote: str | None,
    git_common_dir: str,
) -> Repo:
    """The repo row, by path identity, attached to **no project** (F10).

    This is what a discovered session's repo becomes: `ux_repo_path` is the
    identity, so the same directory is the same row forever and D48's
    `git_common_dir` binding survives every project it is or is not in.
    Attaching here instead would widen `_registered_roots("unassigned")` to
    every repo the machine has ever seen — a §13 allowlist growing by discovery.
    """
    row = connection.execute("SELECT * FROM repo WHERE root_path = ?", (root_path,)).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO repo (id, name, root_path, git_common_dir,"
            " vcs_remote, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_ulid(), name, root_path, git_common_dir, vcs_remote, _now()),
        )
    else:
        connection.execute(
            "UPDATE repo SET name = ?, git_common_dir = ?, vcs_remote = ?, active = 1"
            " WHERE id = ?",
            (name, git_common_dir, vcs_remote, row["id"]),
        )
    fresh = connection.execute("SELECT * FROM repo WHERE root_path = ?", (root_path,)).fetchone()
    return repo(fresh)


def add_repo(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    root_path: str,
    name: str,
    git_common_dir: str,
    vcs_remote: str | None,
) -> Repo:
    """Register a repo to a project — D22's *"adding a repo widens the
    allowlist"*, which is why the tool is `local_destructive`.

    No filesystem call: `root_path` arrives already canonicalized and
    `git_common_dir` already probed (E10, the purity map). `store/` takes a
    connection and nothing else.
    """
    _refuse_reserved(workspace_id, "added to")
    if get_workspace(connection, workspace_id) is None:
        raise StoreError(f"there is no project {workspace_id!r} to add a repo to")
    registered = upsert_repo(
        connection,
        root_path=root_path,
        name=name,
        vcs_remote=vcs_remote,
        git_common_dir=git_common_dir,
    )
    connection.execute(
        "INSERT OR IGNORE INTO project_repo (workspace_id, repo_id, added_at)"
        " VALUES (?, ?, ?)",
        (workspace_id, registered.id, _now()),
    )
    return registered


def remove_repo(connection: sqlite3.Connection, *, workspace_id: str, repo_id: str) -> bool:
    """Drop the project↔repo edge. **The `repo` row is kept** — orphaned, not
    deleted — so re-adding the same path rebinds the same row (E6).
    """
    removed = connection.execute(
        "DELETE FROM project_repo WHERE workspace_id = ? AND repo_id = ?",
        (workspace_id, repo_id),
    ).rowcount
    return bool(removed)


# ----- sessions --------------------------------------------------------------


def register_session(
    connection: sqlite3.Connection,
    engine_session_id: str,
    workspace_id: str,
    repo_id: str | None,
    cwd: str,
    started_at: str,
    origin: Origin,
    ownership: Ownership,
    now: float | None = None,
) -> Session:
    """Idempotent by construction: `ux_session_engine_id` settles the race (P8).

    `now` is the ulid's clock, and the only value in a registered row that is
    otherwise unreproducible: the wall-clock lane makes `session.id` the one
    thing a replay cannot assert on (BLOCKER-T12-2). Injected, it is
    byte-identical across processes; omitted, it is the wall clock, which is what
    every live caller wants.
    """
    row = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE engine_session_id = ?",
        (engine_session_id,),
    ).fetchone()
    if row is not None:
        return session(row)
    connection.execute(
        "INSERT INTO session (id, engine_session_id, workspace_id, repo_id, cwd,"
        " started_at, origin, ownership, engine, state)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            new_ulid(now),
            engine_session_id,
            workspace_id,
            repo_id,
            cwd,
            started_at,
            str(Origin(origin).value),
            str(Ownership(ownership).value),
            DEFAULT_ENGINE,
            str(SessionState.STARTING.value),
        ),
    )
    fresh = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE engine_session_id = ?",
        (engine_session_id,),
    ).fetchone()
    return session(fresh)


def apply_fold_delta(
    connection: sqlite3.Connection, session_id: str, delta: FoldDelta
) -> Session:
    values = _delta_values(delta)
    if values:
        assignments = ", ".join(f"{column} = ?" for column in values)
        connection.execute(
            f"UPDATE session SET {assignments} WHERE id = ?",
            (*values.values(), session_id),
        )
    row = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise StoreError(f"no session {session_id!r}")
    return session(row)


# ----- the stop group (M2, T2) -----------------------------------------------


def apply_stop_verdict(
    connection: sqlite3.Connection,
    session_id: str,
    verdict: Verdict,
    ended_at: str,
    exit_code: int | None,
) -> Session:
    """The eight stop columns, one verb, one transaction (D33).

    The only writer of the group, asserted over `src/`. A second stop
    **overwrites**: S18 has two `Stop`s in one session (E-M2-5) and the later
    verdict is the one that saw the later transcript.
    """
    if write_verdict(connection, session_id, verdict, ended_at, exit_code) == 0:
        raise StoreError(f"no session {session_id!r}")
    row = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    return session(row)


# ----- app state -------------------------------------------------------------


def set_app_state(connection: sqlite3.Connection, key: str, value: object) -> None:
    connection.execute(
        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        (key, json.dumps(value), _now()),
    )


def bump_anomaly(connection: sqlite3.Connection, kind: str) -> None:
    """Principle 5: an unknown is counted, never hidden."""
    key = f"{ANOMALY_KEY_PREFIX}{kind}"
    row = connection.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    current: object = 0 if row is None else json.loads(str(row["value"]))
    count = current + 1 if isinstance(current, int) else 1
    connection.execute(
        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        (key, json.dumps(count), _now()),
    )


# ----- the retry lineage (M4, T10) -------------------------------------------

#: The one statement in this tree that writes `retry_of` (D31's lineage, D37).
#: Guarded in the statement as well as above it: `retry_of IS NULL` makes a
#: relink a zero-row update rather than a silent overwrite, so two writers
#: racing one row cannot both win. A lineage the cap is computed from must not
#: be rewritable by whoever asks last.
_LINK_RETRY = "UPDATE session SET retry_of = ? WHERE id = ? AND retry_of IS NULL"


def _lineage(connection: sqlite3.Connection, session_id: str) -> set[str]:
    """Every id in this session's `retry_of` lineage, itself included.

    `reads.retry_chain_depth` walks the same edges and returns their **count**,
    which is the cap's question and not this one: a writer closing a link has to
    know *which* ids are up there. Bounded by `seen` for the reason the read
    verb is — a self-reference SQLite will let a hand edit close into a loop,
    and a write verb that hangs takes the one writer thread with it (ADR-7).
    """
    seen: set[str] = set()
    current: str | None = session_id
    while current is not None and current not in seen:
        row = connection.execute(
            "SELECT retry_of FROM session WHERE id = ?", (current,)
        ).fetchone()
        if row is None:
            break
        seen.add(current)
        current = None if row["retry_of"] is None else str(row["retry_of"])
    return seen


def link_retry(connection: sqlite3.Connection, session_id: str, retry_of: str) -> Session:
    """Record that `session_id` is a retry of `retry_of` (D31). Write-once.

    **The only writer of `retry_of` in this tree**, and it is a verb of its own
    rather than a defaulted parameter on `create_owned_session` for the reason
    the column had no writer at all until M4: a default nobody passes writes
    `NULL` at every call site and no test can go red for it, while a verb with
    no caller is an absence a `grep` finds. The link is therefore written a
    statement after the row, never inside its `INSERT`; that is safe because the
    cap reads the **predecessor's** chain — which is complete before the new row
    exists — and because both statements run on the one writer thread.

    Refuses rather than repairs, four ways: an unknown session, an unknown
    target (the FK would raise a driver error, which D33 does not let out of
    `store/`), a self-link, and a link that closes a loop. A relink is refused
    by the statement itself.
    """
    before = _read_session(connection, session_id)
    if before is None:
        raise StoreError(f"no session {session_id!r} to record a retry against")
    if _read_session(connection, retry_of) is None:
        raise StoreError(f"no session {retry_of!r} for {session_id!r} to be a retry of")
    if session_id == retry_of:
        raise StoreError(f"session {session_id!r} cannot be a retry of itself")
    if session_id in _lineage(connection, retry_of):
        raise StoreError(
            f"{session_id!r} already stands in {retry_of!r}'s retry lineage, so linking them "
            f"would close a loop the cap could not count"
        )
    if int(connection.execute(_LINK_RETRY, (retry_of, session_id)).rowcount) == 0:
        raise StoreError(
            f"session {session_id!r} already records a retry of {before.retry_of!r}; "
            f"a lineage is written once"
        )
    linked = _read_session(connection, session_id)
    if linked is None:  # pragma: no cover - the row was read at the top of this verb
        raise StoreError(f"no session {session_id!r}")
    return linked


def _read_session(connection: sqlite3.Connection, session_id: str) -> Session | None:
    row = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    return None if row is None else session(row)
