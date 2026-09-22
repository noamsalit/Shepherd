"""D57's project lifecycle, as write verbs — every `INSERT` and `UPDATE` a
project, its repos and its delete perform.

**A split out of `writes.py`** (T3.4), which reached 623 lines against the
600-line ceiling `test_store_stops_is_the_only_new_sql_site` holds every file in
`src/` to, on the day `set_project_description` landed. The cut is the one the
package already uses: `sessions.py` and `stops.py` are siblings of `writes.py`
for the same reason, and this is D57's family — the project, its repos, and the
commit half of its delete.

Nothing here opens a connection and nothing here opens a transaction:
`Store._write` does both, so D33 rule 3 holds exactly and the connection never
leaves `store/`.
"""

from __future__ import annotations

import sqlite3

from shepherd.core.clock import utc_now
from shepherd.core.ids import new_ulid
from shepherd.store.models import (
    UNASSIGNED_PROJECT_ID,
    DeleteOutcome,
    DeletePlan,
    OnRunning,
    Repo,
    SeveredLink,
    StoreError,
    Workspace,
)
from shepherd.store.reads import get_workspace, plan_project_delete
from shepherd.store.rows import repo, workspace

__all__ = [
    "LINEAGE_COLUMNS",
    "add_repo",
    "commit_project_delete",
    "create_project",
    "remove_repo",
    "rename_project",
    "set_project_description",
    "upsert_repo",
]


def _now() -> str:
    """The row clock, spelled as `writes._now` spells it — one format (ADR-3)."""
    return utc_now()


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


def set_project_description(
    connection: sqlite3.Connection, *, workspace_id: str, description: str | None
) -> Workspace | None:
    """A new description on an existing project.

    **A verb of its own rather than a widened `rename_project`** (GAP 3). A
    description was write-once at creation: `create_project` took one and no
    verb could change it, so a mistyped one meant deleting the project. Folding
    it into `rename_project` would leave a verb called *rename* editing a
    description, and a two-field verb has to invent a spelling for "leave this
    one alone" — absent-means-unchanged beside null-means-clear, at the one
    surface where clearing is a real intent.

    `None` **clears** it: the column is nullable and that is the whole of what
    sending nothing can mean.

    The two negative answers are this family's two, spelled as
    `rename_project` spells them: the reserved project is forbidden and raises
    (E8), a project that does not exist is absent and answers `None`.
    """
    _refuse_reserved(workspace_id, "described")
    changed = connection.execute(
        "UPDATE workspace SET description = ? WHERE id = ?", (description, workspace_id)
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

    **`killed` is a claim; `ended_at` is the fact, and the fact decides.** Under
    `KILL` the re-derived running set is the gate, *unconditionally* — not
    `running - killed`, which let a caller's word overrule the store's own
    observation and talk the one safety check on the one destructive verb out of
    firing. `DeleteOutcome.killed` reports the caller's claim intersected with
    what the store saw **change** (`plan.running - fresh.running`), never with
    what remains: the old intersection-with-what-remains inverted the field's
    meaning, reporting exactly the kills that did not land.

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
    # What the store **observed stop**, which is not what the caller claims.
    # `killed` used to be intersected with `running` — a set re-derived after
    # the caller went away to kill things, and *running* is `ended_at IS NULL`
    # while the real kill path (`apply_stop_verdict`) writes `ended_at`. So a
    # kill that landed was filtered out of the report and a kill that did not
    # was filtered in: the field was populated exactly when it was wrong.
    #
    # Intersect with what **changed** (`plan.running - fresh.running`), never
    # with what remains.
    reported = tuple(
        session_id
        for session_id in plan.running
        if session_id in set(killed) and session_id not in set(running)
    )
    orphaned: tuple[str, ...] = ()
    if plan.on_running is OnRunning.KILL:
        if running:
            # Unconditional, and on the store's own fact rather than the
            # caller's word. Two kinds of row are here and neither may be
            # deleted: a session that arrived while the caller was killing, and
            # a session whose kill did not land however it was reported. The
            # gate used to be `running - killed`, which made the one safety
            # check on the one verb that destroys data argue-out-able by the
            # caller it exists to protect against.
            return DeleteOutcome(
                deleted=False,
                refused=(
                    f"{len(running)} session(s) in this project are still running and "
                    f"were not stopped; nothing was deleted"
                ),
                running=running,
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
