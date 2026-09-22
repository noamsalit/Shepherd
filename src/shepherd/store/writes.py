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
