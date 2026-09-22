"""The M1/M2 read verbs — every `SELECT` `Store` answers, as functions (D33).

A **sibling** of `db.py` for the reason `rows.py`, `stops.py`, `sessions.py` and
`mailbox.py` are siblings of it: `db.py` stood at 599 of ADR-1's 600 lines with
M3's sixteen verbs still to wire onto `Store` (blocker T4-2), and the cap is the
signal that a file is doing too much rather than a number to raise. `db.py` keeps
the verb **surface** — `Store` is still the only name a caller imports, and no
caller's import line changed — and hands every function here the
`sqlite3.Connection` it owns (ADR-7). The connection never leaves `store/`, so
D33 is preserved exactly: callers get verbs on the store, never a connection.

`SESSION_COLUMNS`, `DEFAULT_ENGINE` and `StoreError` were parked here by T4-2 to
break that cycle — a name both sides of a delegation need cannot live on the
delegating side — and T4-3 moved them to `models.py`, which every module here
already imports and which has no connection dependency of its own. This module
is reads, and nothing else.
"""

from __future__ import annotations

import json
import sqlite3

from shepherd.core.fold_types import SessionSnapshot
from shepherd.core.states import FLEET_STATE_ORDER, Origin, SessionState
from shepherd.core.stops import CONFIDENT_ENOUGH, Bucket, StopReason
from shepherd.store.models import (
    SESSION_COLUMNS,
    UNASSIGNED_PROJECT_ID,
    DeleteOutcome,
    DeletePlan,
    FleetRow,
    OnRunning,
    Repo,
    ReplayTarget,
    Session,
    StopCounts,
    Workspace,
)
from shepherd.store.rows import fleet_row, id_set, repo, session, workspace
from shepherd.store.stops import (
    COUNTS_SQL,
    REPLAY_SINCE_SQL,
    REPLAY_SQL,
    UNCLASSIFIED_SQL,
    read_counts,
    replay_target,
)

#: `app_state` key namespace for the anomaly counters, so they can be enumerated
#: rather than asked for one expected member at a time (BLOCKER T14-3).
ANOMALY_KEY_PREFIX = "anomaly."

#: The fold's own prior state, kept off `SESSION_COLUMNS` on purpose: `Session`
#: is the row a consumer reads, and these four are the fold talking to its own
#: next call (BLOCKER-T6-1, plan gap M16).
FOLD_STATE_COLUMNS = (
    "observed_at, live_subagent_ids, created_task_ids, completed_task_ids"
)


def _fleet_order_clause() -> str:
    cases = " ".join(
        f"WHEN '{state.value}' THEN {index}" for index, state in enumerate(FLEET_STATE_ORDER)
    )
    return f"CASE s.state {cases} ELSE {len(FLEET_STATE_ORDER)} END"


def _rows(
    connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...] = ()
) -> list[sqlite3.Row]:
    return list(connection.execute(sql, parameters).fetchall())


# ----- workspace and repo ---------------------------------------------------


def find_repo_by_common_dir(connection: sqlite3.Connection, git_common_dir: str) -> Repo | None:
    """D48's binding key: the repo whose `.git` directory this is.

    `ORDER BY root_path` for the reason `list_repos` two functions below says
    out loud — an unordered read is a test that passes on one SQLite build and
    not on the next — and the stakes went up with D57: two worktrees of one
    clone share a `git_common_dir`, and the **project** a discovered session
    lands in is now derived from whichever row this returns.
    """
    rows = _rows(
        connection,
        "SELECT * FROM repo WHERE git_common_dir = ? ORDER BY root_path",
        (git_common_dir,),
    )
    return repo(rows[0]) if rows else None


def list_repos(connection: sqlite3.Connection, workspace_id: str) -> list[Repo]:
    """Every repo registered to one workspace — §13's allowlist, as a population.

    D22 ties the spawn allowlist to **registered repo paths**: *"`add_repo` is
    `local_destructive` because §13 validates every spawn against the registered
    allowlist — adding a repo widens that allowlist."* `find_repo_by_common_dir`
    cannot answer that: it is D48's *binding* key, one directory at a time, and
    binding and admission are two questions (blocker T11-1).

    Ordered by `root_path` so the caller's longest-prefix match is over a stable
    list; the order is asserted, because an unordered read is a test that passes
    on one SQLite build and not on the next.

    The edge is `project_repo` since 004 (D57): a repo may be registered to two
    projects, so it cannot be a column on `repo`. The signature and the ordering
    are unchanged — only the join is.
    """
    rows = _rows(
        connection,
        "SELECT r.* FROM repo r JOIN project_repo pr ON pr.repo_id = r.id"
        " WHERE pr.workspace_id = ? ORDER BY r.root_path",
        (workspace_id,),
    )
    return [repo(row) for row in rows]


def get_workspace(connection: sqlite3.Connection, workspace_id: str) -> Workspace | None:
    rows = _rows(connection, "SELECT * FROM workspace WHERE id = ?", (workspace_id,))
    return workspace(rows[0]) if rows else None


def list_workspaces(connection: sqlite3.Connection) -> list[Workspace]:
    """Every project, by name.

    **Unchanged by D57's migration, deliberately.** The `ORDER BY name` below
    predates it, and under BINARY collation the seeded `"Unassigned"` sorts
    ahead of every lower-case name — so `list_workspaces()[0]` is the reserved
    project and not the caller's (N2, E22). The repair belongs at the call
    sites, which select the project **by the id the fixture captured** — not by
    name, because names are not unique (E1: `/work/api` and `/personal/api` are
    two projects, there is no unique index, and `create_project(name=
    "Unassigned")` mints a second row that reads as the reserved one). A
    tiebreak added here would read as a fix while changing nothing.
    """
    return [
        workspace(row) for row in _rows(connection, "SELECT * FROM workspace ORDER BY name")
    ]


def projects_for_repo(connection: sqlite3.Connection, repo_id: str) -> list[str]:
    """Which projects hold this repo — D60's input.

    A discovered session cannot be asked which project it meant, so
    `bind_cwd_to_repo` reads the length of this list: exactly one is
    unambiguous, and anything else is `UNASSIGNED_PROJECT_ID`.
    """
    rows = _rows(
        connection,
        "SELECT workspace_id FROM project_repo WHERE repo_id = ? ORDER BY workspace_id",
        (repo_id,),
    )
    return [str(row["workspace_id"]) for row in rows]


def projects_by_repo(connection: sqlite3.Connection) -> dict[str, list[str]]:
    """`{repo_id: every project holding it}`, for **every** repo, in one
    statement — D60 made readable.

    `projects_for_repo` answers this for one repo and `bind_cwd_to_repo` asks it
    one repo at a time, which is right there: a discovered session has exactly
    one `cwd`. A **page** has a list, and asking per row is the N+1 that
    `repo_counts` exists here rather than in the projection to avoid. Same
    shape, same reason.

    A repo no project holds is **absent** rather than present with an empty
    list: the projection reads a missing key as none, and two spellings of
    nothing is how a consumer comes to branch on one of them.
    """
    rows = _rows(
        connection,
        "SELECT repo_id, workspace_id FROM project_repo ORDER BY repo_id, workspace_id",
    )
    found: dict[str, list[str]] = {}
    for row in rows:
        found.setdefault(str(row["repo_id"]), []).append(str(row["workspace_id"]))
    return found


def project_last_activity(connection: sqlite3.Connection) -> dict[str, str]:
    """The latest activity per project, derived from its sessions (ADR-P4).

    `workspace.last_activity_at` is a column nothing writes, and keeping it
    written would need a writer on every session update — wrong the first time
    one was missed. A project with no session is **absent** from this mapping
    rather than present with a null: the projection renders "never" from the
    absence, and a null in a `dict[str, str]` would be a second spelling of it.
    """
    rows = _rows(
        connection,
        "SELECT workspace_id, MAX(COALESCE(last_event_at, started_at)) AS latest"
        " FROM session GROUP BY workspace_id",
    )
    return {
        str(row["workspace_id"]): str(row["latest"])
        for row in rows
        if row["latest"] is not None
    }


def repo_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """`{workspace_id: registered repo count}` for **every** project, in one
    statement (M4).

    The Projects page needs one number per row. Asking `list_repos` per project
    is an N+1 whose cost is invisible until a person has thirty projects, and
    the shape of the fix is the whole reason this verb exists rather than a
    loop in the projection. A project with no repo is absent; the projection
    reads a missing key as zero.
    """
    rows = _rows(
        connection,
        "SELECT workspace_id, COUNT(*) AS n FROM project_repo GROUP BY workspace_id",
    )
    return {str(row["workspace_id"]): int(row["n"]) for row in rows}


def running_sessions_for(connection: sqlite3.Connection, workspace_id: str) -> list[Session]:
    """The project's sessions that have not ended — what `delete_project`
    refuses on, and what `kill` and `orphan` act over.

    *Running* is `ended_at IS NULL` rather than `state = 'running'`: a session
    in `starting` or `needs_you` is just as alive, and `state` is a fold's
    opinion while `ended_at` is the fact.
    """
    rows = _rows(
        connection,
        f"SELECT {SESSION_COLUMNS} FROM session"
        " WHERE workspace_id = ? AND ended_at IS NULL ORDER BY started_at, id",
        (workspace_id,),
    )
    return [session(row) for row in rows]


def plan_project_delete(
    connection: sqlite3.Connection, *, workspace_id: str, on_running: OnRunning
) -> DeletePlan:
    """D61's state machine, decided — and nothing written.

    **The first of two halves, and the reason for the split.** The middle of a
    project delete is *stopping the sessions*, which issues subprocesses. The
    verb used to take that as a `kill` callable, and `Store._write` runs its
    callable on the single writer thread inside `BEGIN IMMEDIATE`: the real
    kill path's first statement is `store.set_app_state(...)`, so it enqueued
    behind the writer that was waiting for it and the process hung for good.
    Even when the callback did not write, an irreversible effect inside a
    transaction that can roll back leaves the panes dead and the rows restored.

    So: this half decides, the caller kills **between**, and
    `writes.commit_project_delete` deletes. `refusal` is the whole answer when
    it is not `None`.

    **Never raises.** Every negative answer is a `DeleteOutcome` on `refusal`,
    because the page renders the three choices out of the refusal itself and an
    exception is not something a card can draw.
    """
    if workspace_id == UNASSIGNED_PROJECT_ID:
        return DeletePlan(
            workspace_id=workspace_id,
            on_running=on_running,
            refusal=DeleteOutcome(
                deleted=False, refused="the Unassigned project cannot be deleted"
            ),
        )
    if get_workspace(connection, workspace_id) is None:
        return DeletePlan(
            workspace_id=workspace_id,
            on_running=on_running,
            refusal=DeleteOutcome(
                deleted=False, refused=f"there is no project {workspace_id!r} to delete"
            ),
        )

    alive = running_sessions_for(connection, workspace_id)
    running = tuple(s.id for s in alive)
    # D61's choice is only offerable over the sessions a kill can reach: the
    # shipped kill path asks `handle_for`, which is this column, and answers
    # `no_pane(...)` for the rest. Split here rather than at the caller, because
    # the rows are already read and asking per session is an N+1 (M4).
    killable = tuple(s.id for s in alive if s.runner_handle is not None)
    unkillable = tuple(s.id for s in alive if s.runner_handle is None)
    # **Before the refusing return, not after it.** `doomed` exists so the
    # dialog can say what the delete is about to take *before* the button, and
    # the refusal is what a page has before the button. Computed after it, a
    # refusing plan carried an empty tuple: the page could say "2 sessions are
    # still running" and could not say that four hundred finished ones go with
    # the project, so the page that shipped derived that count itself — a copy
    # of this derivation, which is the thing that drifts.
    survivors = frozenset(running) if on_running is OnRunning.ORPHAN else frozenset()
    doomed = tuple(
        str(row["id"])
        for row in _rows(
            connection,
            "SELECT id FROM session WHERE workspace_id = ? ORDER BY started_at, id",
            (workspace_id,),
        )
        if str(row["id"]) not in survivors
    )
    if running and on_running is OnRunning.REFUSE:
        return DeletePlan(
            workspace_id=workspace_id,
            on_running=on_running,
            running=running,
            killable=killable,
            unkillable=unkillable,
            # Every row, including the running ones: under `REFUSE` nothing
            # survives if the caller proceeds. The orphan case is this list
            # minus `running`, which the caller holds in the same record.
            doomed=doomed,
            refusal=DeleteOutcome(
                deleted=False,
                refused=(
                    f"{len(running)} session(s) are still running in this project; "
                    f"choose whether to stop them or move them to Unassigned"
                ),
                running=running,
            ),
        )

    return DeletePlan(
        workspace_id=workspace_id,
        on_running=on_running,
        running=running,
        killable=killable,
        unkillable=unkillable,
        doomed=doomed,
    )


# ----- sessions --------------------------------------------------------------


def get_session(connection: sqlite3.Connection, session_id: str) -> Session | None:
    rows = _rows(
        connection, f"SELECT {SESSION_COLUMNS} FROM session WHERE id = ?", (session_id,)
    )
    return session(rows[0]) if rows else None


def get_session_by_engine_id(
    connection: sqlite3.Connection, engine_session_id: str
) -> Session | None:
    rows = _rows(
        connection,
        f"SELECT {SESSION_COLUMNS} FROM session WHERE engine_session_id = ?",
        (engine_session_id,),
    )
    return session(rows[0]) if rows else None


def list_sessions(
    connection: sqlite3.Connection,
    workspace_id: str | None = None,
    state: SessionState | None = None,
) -> list[Session]:
    clauses: list[str] = []
    parameters: list[object] = []
    if workspace_id is not None:
        clauses.append("workspace_id = ?")
        parameters.append(workspace_id)
    if state is not None:
        clauses.append("state = ?")
        parameters.append(str(SessionState(state).value))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _rows(
        connection,
        f"SELECT {SESSION_COLUMNS} FROM session{where} ORDER BY started_at, id",
        tuple(parameters),
    )
    return [session(row) for row in rows]


def snapshot(connection: sqlite3.Connection, session_id: str) -> SessionSnapshot | None:
    """The fold's prior input, including the fold's own carried state.

    `observed_at` and the three identity sets come out of the four columns
    §7 was widened by (plan gap M16): RD8's recency rule and subagent
    pairing are only real if they survive a `controld` restart, which D37
    expects to happen freely (BLOCKER-T6-1, T7b-5, T11-4).
    """
    found = get_session(connection, session_id)
    if found is None:
        return None
    state = _rows(
        connection, f"SELECT {FOLD_STATE_COLUMNS} FROM session WHERE id = ?", (session_id,)
    )[0]
    return SessionSnapshot(
        session_id=found.id,
        engine_session_id=found.engine_session_id,
        state=found.state,
        last_event_at=found.last_event_at,
        observed_at=(None if state["observed_at"] is None else str(state["observed_at"])),
        needs_you_reason=found.needs_you_reason,
        brief=found.brief,
        cwd=found.cwd,
        repo_id=found.repo_id,
        model=found.model,
        tasks_total=found.tasks_total,
        tasks_done=found.tasks_done,
        active_subagents=found.active_subagents,
        repos_touched=found.repos_touched,
        live_subagent_ids=id_set(state, "live_subagent_ids"),
        created_task_ids=id_set(state, "created_task_ids"),
        completed_task_ids=id_set(state, "completed_task_ids"),
        title=found.title,
        title_source=found.title_source,
        pid=found.pid,
        proc_start=found.proc_start,
        ended_at=found.ended_at,
        auto_compact_at=found.auto_compact_at,
        quota_notice_at=found.quota_notice_at,
    )


def sessions_with_liveness_inputs(
    connection: sqlite3.Connection,
) -> list[tuple[str, int, str]]:
    """`(session_id, pid, proc_start)` for every live session that has both."""
    rows = _rows(
        connection,
        "SELECT id, pid, proc_start FROM session"
        " WHERE pid IS NOT NULL AND proc_start IS NOT NULL AND ended_at IS NULL"
        " ORDER BY id",
    )
    return [(str(row["id"]), int(row["pid"]), str(row["proc_start"])) for row in rows]


def fleet(connection: sqlite3.Connection) -> list[FleetRow]:
    rows = _rows(
        connection,
        "SELECT s.id, s.engine_session_id, s.workspace_id, w.name AS workspace_name,"
        " r.name AS repo_name, s.state, s.title, s.brief, s.needs_you_reason,"
        " s.tasks_done, s.tasks_total, s.active_subagents, s.last_event_at, s.cwd,"
        " s.stop_reason, s.outcome, s.why, s.confidence, s.decided_by, s.next_actions,"
        " s.exit_code, s.runner_handle, s.title_synced_at, s.parent_session_id, s.depth"
        " FROM session s JOIN workspace w ON w.id = s.workspace_id"
        " LEFT JOIN repo r ON r.id = s.repo_id"
        " WHERE s.ephemeral = 0"
        f" ORDER BY {_fleet_order_clause()},"
        " COALESCE(s.last_event_at, s.started_at) DESC, s.id",
    )
    return [fleet_row(row) for row in rows]


# ----- the master's wake set and its lineage cap (M4, T8) --------------------

#: D31's sentence as a population: *"only `unfinished` and `error` outcomes on
#: master-owned sessions wake anything."* Named here rather than inlined in the
#: SQL so the clause and the enum can be compared by a test.
WAKE_OUTCOMES = (Bucket.UNFINISHED.value, Bucket.ERROR.value)

#: The origin the master spawns under. `needs_you` is excluded by the outcome
#: clause above and not by a second rule — that is the human's rail (D31), and
#: it is asserted with a row rather than left to the enum.
WAKE_ORIGIN = Origin.ORCHESTRATOR.value

_WAKE_SQL = (
    f"SELECT {SESSION_COLUMNS} FROM session"
    " WHERE origin = ? AND ended_at IS NOT NULL"
    f" AND outcome IN ({', '.join('?' for _ in WAKE_OUTCOMES)})"
)


def wake_candidates(
    connection: sqlite3.Connection, since: str | None
) -> tuple[Session, ...]:
    """D31's wake set: the master-owned sessions that stopped `unfinished` or
    `error` since the master last looked.

    `since` is the master's own last turn, so a row it has already drained
    stays drained; `None` asks for the lineage-wide set, which is what a first
    turn and `peek` want. The caller decides about `ephemeral` — a `WHERE`
    clause nobody can reach through the verb surface is worse than a tripwire
    the caller can assert (M3's `repo.active` precedent).

    Ordered oldest stop first so the tuple is stable across SQLite builds. The
    order is **not** part of what this verb promises: the wake set is a set,
    and a test that asserted this ordering would be asserting the `ORDER BY`
    against itself.
    """
    parameters: list[object] = [WAKE_ORIGIN, *WAKE_OUTCOMES]
    clause = ""
    if since is not None:
        clause = " AND ended_at > ?"
        parameters.append(since)
    rows = _rows(connection, f"{_WAKE_SQL}{clause} ORDER BY ended_at, id", tuple(parameters))
    return tuple(session(row) for row in rows)


def retry_chain_depth(connection: sqlite3.Connection, session_id: str) -> int:
    """How many sessions stand in this one's `retry_of` lineage, itself
    included — 1 for a first attempt, 2 for its retry, and so on. 0 for a
    session that does not exist.

    **Walked, never read off `attempt`.** D31 caps *attempts per lineage*;
    `attempt` is a column a caller writes, and a column can be stale, reset, or
    written by a second writer. The chain is the fact, so the cap is read from
    the chain (T10).

    `retry_of` is a self-reference, and SQLite is happy to let a hand edit close
    one into a loop. The walk keeps the ids it has seen and stops on the first
    repeat: a read verb that hangs takes the daemon with it, and D33 promises a
    caller an answer rather than a connection to debug.
    """
    seen: set[str] = set()
    current: str | None = session_id
    while current is not None and current not in seen:
        rows = _rows(connection, "SELECT retry_of FROM session WHERE id = ?", (current,))
        if not rows:
            break
        seen.add(current)
        current = None if rows[0]["retry_of"] is None else str(rows[0]["retry_of"])
    return len(seen)


# ----- the stop group (M2, T2) ----------------------------------------------


def stop_verdict_counts(connection: sqlite3.Connection) -> StopCounts:
    """The `unknown` rate's inputs (principle 5, ADR-M2-5).

    `unknown` is a reason a rule wrote; `unclassified` is a stopped row no
    verdict reached (E-M2-4). Both counted, neither hidden.
    """
    rows = _rows(connection, COUNTS_SQL, (str(StopReason.COMPLETED.value), CONFIDENT_ENOUGH))
    stopped = _rows(connection, UNCLASSIFIED_SQL, (str(SessionState.STOPPED.value),))
    return read_counts(rows, int(stopped[0]["n"]))


def sessions_for_replay(
    connection: sqlite3.Connection, since: str | None
) -> list[ReplayTarget]:
    """Every session `replay` may rewrite, oldest stop first — **including
    the ones carrying no verdict** (E-M2-4, blocker T12-3). `since` narrows
    by the stop's own time, so a row with no `ended_at` stays out of a
    narrowed run.
    """
    rows = (
        _rows(connection, REPLAY_SQL)
        if since is None
        else _rows(connection, REPLAY_SINCE_SQL, (since,))
    )
    return [replay_target(row) for row in rows]


# ----- app state -------------------------------------------------------------


def get_app_state(connection: sqlite3.Connection, key: str) -> object | None:
    rows = _rows(connection, "SELECT value FROM app_state WHERE key = ?", (key,))
    if not rows:
        return None
    decoded: object = json.loads(str(rows[0]["value"]))
    return decoded


def list_anomaly_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Every `anomaly.*` counter, keyed by kind. Enumerated, not asked for.

    A reader that instead asks for one key per `AnomalyKind` member can only
    ever see the kinds it already expected, which is the opposite of
    principle 5 — an unknown is counted *and shown* (BLOCKER T14-3).
    """
    rows = _rows(
        connection,
        "SELECT key, value FROM app_state WHERE key LIKE ? ORDER BY key",
        (f"{ANOMALY_KEY_PREFIX}%",),
    )
    counts: dict[str, int] = {}
    for row in rows:
        decoded: object = json.loads(str(row["value"]))
        if isinstance(decoded, int):
            counts[str(row["key"])[len(ANOMALY_KEY_PREFIX) :]] = decoded
    return counts
