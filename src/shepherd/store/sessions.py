"""The owned-session verbs — what M3 adds to `session` (T4, D33).

A **sibling** of `db.py` rather than a section of it: `db.py` is at ADR-1's
600-line cap, and the seam `rows.py` and `stops.py` were split along holds here —
`db.py` owns *what the store can be asked to do*, this module owns *how an owned
session is created, bound, titled and counted*. `db.py` hands every function here
the connection its writer thread owns (ADR-7); nothing here opens a connection,
resolves a path or reads a clock, so a replay is byte-identical run to run.

**M1's `register_session` is not widened, it is joined.** That verb registers
what discovery *found* — an `attached` row, engine-bound by definition; this one
creates what Shepherd *started*: `ownership='owned'`, a `runner_handle`, a parent
and a depth. Both are idempotent on `ux_session_engine_id`, and that is C-M3-7 —
the row exists before the process does, so a sweep racing a spawn finds the
pre-registered row instead of making a second one.

**The one stop writer is still `apply_stop_verdict`.** Nothing here writes a
stop column; a rebind is explicitly *not* a stop (C14).
"""

from __future__ import annotations

import sqlite3

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import TITLE_SOURCE_RANK, Origin, Ownership, SessionState, TitleSource
from shepherd.store.models import DEFAULT_ENGINE, SESSION_COLUMNS, Session, StoreError
from shepherd.store.rows import session as session_row

#: The columns a spawn writes. `owner_id` is left to D2's column default.
_INSERT = (
    "INSERT INTO session (id, engine_session_id, workspace_id, repo_id, parent_session_id,"
    " origin, ownership, ephemeral, depth, cwd, runner_handle, runner, engine, model, effort,"
    " started_at, title, title_source, state)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    # The partial unique index settles the pre-registration race; a prior
    # SELECT would race it (C-M3-7, and `register_session`'s P8).
    " ON CONFLICT(engine_session_id) WHERE engine_session_id IS NOT NULL DO NOTHING"
)

#: An owned session that has not ended holds a slot under §11's total cap. The
#: second number is the **handle-less** cohort, which is why T11 counts panes.
_OWNED_COUNTS = (
    "SELECT COUNT(*) AS owned,"
    " SUM(CASE WHEN runner_handle IS NULL THEN 1 ELSE 0 END) AS handle_less"
    " FROM session WHERE ownership = ? AND ended_at IS NULL"
)

#: §11's per-parent cap counts *concurrent* children: an ended child released
#: its slot, and counting it would retire a parent after five spawns.
_CHILDREN = "SELECT COUNT(*) AS n FROM session WHERE parent_session_id = ? AND ended_at IS NULL"


def _read(connection: sqlite3.Connection, session_id: str) -> Session | None:
    row = connection.execute(
        f"SELECT {SESSION_COLUMNS} FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    return None if row is None else session_row(row)


def _require(connection: sqlite3.Connection, session_id: str) -> Session:
    found = _read(connection, session_id)
    if found is None:
        raise StoreError(f"no session {session_id!r}")
    return found


def _update(connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...]) -> None:
    if int(connection.execute(sql, parameters).rowcount) == 0:
        raise StoreError(f"no session {parameters[-1]!r}")


def create_owned_session(
    connection: sqlite3.Connection,
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
    """The row a spawn creates **before** its process exists (C-M3-7).

    `engine_session_id=None` is the ask-fork branch and nothing else: if
    `--fork-session` refuses `--session-id`, the fork's own id is not knowable
    until the `-p` run returns (A25), so the row is created unbound and bound
    afterwards by `bind_engine_session_id`. A **spawn** always passes the uuid
    it gave `--session-id`; an unbound spawn row would let the discovery sweep
    register the engine's id as a *second* row for one pane — the duplicate-row
    hole `--session-id` exists to close. Idempotent on `engine_session_id`, so a
    sweep that races the spawn finds the pre-registered row.
    """
    if engine_session_id is None and Origin(origin) is not Origin.ASK_FORK:
        raise StoreError(
            f"an owned session with origin {Origin(origin).value!r} must be engine-bound;"
            " only ask_fork may create an unbound row"
        )
    connection.execute(
        _INSERT,
        (
            session_id,
            engine_session_id,
            workspace_id,
            repo_id,
            parent_session_id,
            str(Origin(origin).value),
            str(Ownership.OWNED.value),
            int(ephemeral),
            depth,
            cwd,
            None if handle is None else handle.to_text(),
            None if handle is None else handle.runner,
            DEFAULT_ENGINE,
            model,
            effort,
            started_at,
            title,
            title_source,
            str(SessionState.STARTING.value),
        ),
    )
    if engine_session_id is None:
        return _require(connection, session_id)
    return session_row(
        connection.execute(
            f"SELECT {SESSION_COLUMNS} FROM session WHERE engine_session_id = ?",
            (engine_session_id,),
        ).fetchone()
    )


def get_owned_session(connection: sqlite3.Connection, session_id: str) -> Session | None:
    """The read-back for the verbs below, never a driver row (D33 rule 2)."""
    return _read(connection, session_id)


def set_runner_handle(
    connection: sqlite3.Connection, session_id: str, handle: RunnerHandle
) -> None:
    """Step 5 of the spawn. Until this lands the row is an orphan candidate,
    which is the second number `owned_session_counts` returns."""
    _update(
        connection,
        "UPDATE session SET runner_handle = ?, runner = ? WHERE id = ?",
        (handle.to_text(), handle.runner, session_id),
    )


def bind_engine_session_id(
    connection: sqlite3.Connection, session_id: str, engine_session_id: str
) -> int:
    """Bind an **unbound** row, and report whether **this** call bound it (T15).

    The ask-fork branch's other half: `--fork-session` refusing `--session-id`
    leaves the row created unbound (A25), and the fork's own id arrives from the
    `-p` result object afterwards. Exactly one caller may supply it — a second
    would silently repoint a live row, and its caller would believe its own fork
    id was on the row while the winner's was.

    "Exactly once" is held by the mechanism `mark_delivered` uses for
    delivery-once, not by a compare-and-set: under D37's single writer the
    transactions serialise, so every CAS caller reads what the previous one
    committed and every CAS matches (blocker T4-1's recorded run). Here the
    condition is evaluated *inside* the write, so serialisation is what makes it
    correct rather than what defeats it. The loser updates zero rows and is told
    so, rather than raising: a row that is already bound is not an error, it is
    an answer — and it is the same `0` an unknown id gets.

    **Not** C14's move: `rebind_engine_session_id` changes an existing binding.
    """
    cursor = connection.execute(
        "UPDATE session SET engine_session_id = ?"
        " WHERE id = ? AND engine_session_id IS NULL",
        (engine_session_id, session_id),
    )
    return int(cursor.rowcount)


def rebind_engine_session_id(
    connection: sqlite3.Connection, session_id: str, engine_session_id: str
) -> None:
    """Move the row's engine binding, keeping the row (C14).

    `/resume` ends the old `session_id` **in the same pane**, so the row keeps
    its identity — and its stop history — and changes one column; a
    delete-and-insert would lose everything the row knows. The move is a
    compare-and-set against the binding read in the same call, so a binder whose
    read was invalidated **in flight** is refused rather than silently
    repointing a live row, and re-binding the id already on the row is a no-op.

    It does **not** hold "bindable exactly once", and no longer has to: that is
    `bind_engine_session_id`'s intent and its conditional write (blocker T4-1,
    resolved by splitting the verb — one verb cannot both move a binding and
    forbid moving one).
    """
    current = _require(connection, session_id).engine_session_id
    if current == engine_session_id:
        return
    clause = "engine_session_id IS NULL" if current is None else "engine_session_id = ?"
    held: tuple[object, ...] = () if current is None else (current,)
    changed = connection.execute(
        f"UPDATE session SET engine_session_id = ? WHERE id = ? AND {clause}",
        (engine_session_id, session_id, *held),
    ).rowcount
    if int(changed) == 0:
        raise StoreError(
            f"session {session_id!r} was bound by another caller while this bind was in flight"
        )


def apply_title(
    connection: sqlite3.Connection, session_id: str, title: str, source: TitleSource
) -> Session:
    """D29's one-way ratchet: `user` > `engine` > `brief`.

    A lower-ranked source is refused — once you rename a session the engine's
    own title never overwrites it again — and an equal-ranked one wins: a newer
    engine title is a better engine title. A title that changes clears
    `title_synced_at`: the stamp says *this* text was accepted by the engine,
    and leaving it on new text would claim a write-back that never happened
    (D29's `local only` marker).
    """
    current = _require(connection, session_id)
    if TITLE_SOURCE_RANK[source] < TITLE_SOURCE_RANK[current.title_source]:
        return current
    connection.execute(
        "UPDATE session SET title = ?, title_source = ?, title_synced_at = NULL WHERE id = ?",
        (title, source, session_id),
    )
    return _require(connection, session_id)


def set_title_synced_at(
    connection: sqlite3.Connection, session_id: str, synced_at: str
) -> None:
    """Record that the engine **accepted** the title now on the row (D29).

    The only writer of the column, reached from a read-back and never from a
    send: a stamp written when the write was merely *attempted* is the silent
    half-success D29 refuses.
    """
    _update(
        connection,
        "UPDATE session SET title_synced_at = ? WHERE id = ?",
        (synced_at, session_id),
    )


def set_ephemeral(connection: sqlite3.Connection, session_id: str, ephemeral: bool) -> None:
    """DP2: an `ask` fork is ephemeral from birth and stays off the fleet page."""
    _update(
        connection,
        "UPDATE session SET ephemeral = ? WHERE id = ?",
        (int(ephemeral), session_id),
    )


def owned_session_counts(connection: sqlite3.Connection) -> tuple[int, int]:
    """`(alive owned rows, of which handle-less)` — §11's population and its caveat.

    **Not the total cap on its own.** `MAX_TOTAL_OWNED_SESSIONS` counts *panes*
    (T11, T12): a row whose `runner_handle` is NULL may still have a live pane
    nothing can terminate, so the second number says these rows under-count the
    processes actually running.
    """
    row = connection.execute(_OWNED_COUNTS, (str(Ownership.OWNED.value),)).fetchone()
    return (int(row["owned"] or 0), int(row["handle_less"] or 0))


def children_of(connection: sqlite3.Connection, session_id: str) -> int:
    """How many live children one session has, for §11's per-parent cap."""
    return int(connection.execute(_CHILDREN, (session_id,)).fetchone()["n"])
