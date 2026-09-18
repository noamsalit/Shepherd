"""The mailbox verbs — D12's one delivery path, as SQL (T4, D33).

A **sibling** of `db.py` rather than a section of it: `db.py` is at ADR-1's
600-line cap, and the same seam `rows.py` and `stops.py` were split along holds
here — `db.py` owns *what the store can be asked to do*, this module owns *how a
queued message is written, claimed and counted*.

`db.py` hands every function here the connection its writer thread owns
(ADR-7). Nothing in this module opens a connection, resolves a path, or reads a
clock: `queued_at` and `delivered_at` arrive from the caller, so a replay is
byte-identical run to run.

**The three claims, and the mechanism behind each** (P-M3-13):

1. *Enqueue is idempotent.* `INSERT … ON CONFLICT DO NOTHING` against
   `ux_mailbox_idem(session_id, idempotency_key)`, then a read of whichever row
   won. A check-then-insert races; the index does not, and the caller gets the
   **stored** row rather than the one it offered.
2. *Delivery happens once.* The claim is conditional — `WHERE … AND
   delivered_at IS NULL` — and `mark_delivered` returns the number of rows **it**
   moved. Two sweeps racing one pending set therefore report `5 + 0`, never
   `5 + 5`, and the second has the information it needs to know it delivered
   nothing.
3. *Coalescing loses nothing.* The batch is named by id, so a message queued
   between the read that built the coalesced body and the mark that retires it
   stays pending instead of being stamped delivered without ever having been
   sent.

Delivered rows are **kept** for the retention window (migration 003): deleting
one frees its `idempotency_key` for reuse, and the stamp is what lets a
duplicate still be refused.
"""

from __future__ import annotations

import sqlite3

from shepherd.core.mailbox import MAILBOX_TABLE, MailboxCounts, MailboxMessage, MailboxOrigin

#: Every column of `mailbox_message` a `MailboxMessage` carries. `owner_id` is
#: deliberately absent — D2's default lives on the column (T3).
MESSAGE_COLUMNS = (
    "id, session_id, idempotency_key, body, origin, queued_at, delivered_at,"
    " delivery_attempts, last_refusal"
)

#: `ux_mailbox_idem` settles the race rather than a prior `SELECT` (D12).
_INSERT = (
    f"INSERT INTO {MAILBOX_TABLE}"
    " (id, session_id, idempotency_key, body, origin, queued_at, delivery_attempts)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT(session_id, idempotency_key) DO NOTHING"
)

#: The sweep's hot read, shaped to `ix_mailbox_pending(session_id, delivered_at)`.
_PENDING = (
    f"SELECT {MESSAGE_COLUMNS} FROM {MAILBOX_TABLE}"
    " WHERE session_id = ? AND delivered_at IS NULL ORDER BY queued_at, id"
)

#: RD4: one indexed query tells a whole sweep there is nothing to do.
_SESSIONS_WITH_PENDING = (
    f"SELECT DISTINCT session_id FROM {MAILBOX_TABLE}"
    " WHERE delivered_at IS NULL ORDER BY session_id"
)

#: `deferred` is a *pending* row the write policy refused this pass, so a
#: delivered row leaves the count (T3's note on `MailboxCounts`).
_COUNTS = (
    "SELECT"
    " SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) AS pending,"
    " SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered,"
    " SUM(CASE WHEN delivered_at IS NULL AND last_refusal IS NOT NULL THEN 1 ELSE 0 END)"
    " AS deferred"
    f" FROM {MAILBOX_TABLE}"
)


def _message(row: sqlite3.Row) -> MailboxMessage:
    """Driver row → dataclass. The only place a `sqlite3.Row` is read here."""
    return MailboxMessage(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        idempotency_key=str(row["idempotency_key"]),
        body=str(row["body"]),
        origin=MailboxOrigin(str(row["origin"])),
        queued_at=str(row["queued_at"]),
        delivered_at=None if row["delivered_at"] is None else str(row["delivered_at"]),
        delivery_attempts=int(row["delivery_attempts"]),
        last_refusal=None if row["last_refusal"] is None else str(row["last_refusal"]),
    )


def _placeholders(ids: tuple[str, ...]) -> str:
    return ", ".join("?" for _ in ids)


def enqueue(connection: sqlite3.Connection, message: MailboxMessage) -> MailboxMessage:
    """Queue a message, or hand back the one already queued under its key.

    Returns the **stored** row, which on a retry is the first caller's message:
    a retrying caller that got a different id back would believe it had queued
    a second note.
    """
    connection.execute(
        _INSERT,
        (
            message.id,
            message.session_id,
            message.idempotency_key,
            message.body,
            str(MailboxOrigin(message.origin).value),
            message.queued_at,
            message.delivery_attempts,
        ),
    )
    row = connection.execute(
        f"SELECT {MESSAGE_COLUMNS} FROM {MAILBOX_TABLE}"
        " WHERE session_id = ? AND idempotency_key = ?",
        (message.session_id, message.idempotency_key),
    ).fetchone()
    return _message(row)


def pending_for(connection: sqlite3.Connection, session_id: str) -> list[MailboxMessage]:
    """Every undelivered message for one session, oldest first.

    Queue order is the coalescer's input order (D12's five bullets), and the
    order is `queued_at, id` rather than insertion order so a restart reads the
    same sequence.
    """
    return [_message(row) for row in connection.execute(_PENDING, (session_id,))]


def sessions_with_pending(connection: sqlite3.Connection) -> list[str]:
    """The only sessions worth a `capture-pane` this pass (RD4)."""
    return [str(row["session_id"]) for row in connection.execute(_SESSIONS_WITH_PENDING)]


def mark_delivered(
    connection: sqlite3.Connection, ids: tuple[str, ...], delivered_at: str
) -> int:
    """Retire the named rows, and report how many **this** call moved.

    Conditional on `delivered_at IS NULL`, which is what makes a second sweep
    over the same batch a counted no-op rather than a second delivery.
    """
    if not ids:
        return 0
    cursor = connection.execute(
        f"UPDATE {MAILBOX_TABLE} SET delivered_at = ?,"
        " delivery_attempts = delivery_attempts + 1"
        f" WHERE id IN ({_placeholders(ids)}) AND delivered_at IS NULL",
        (delivered_at, *ids),
    )
    return int(cursor.rowcount)


def record_refusal(
    connection: sqlite3.Connection, ids: tuple[str, ...], refusal: str
) -> None:
    """Say *why* a pending message was not delivered, on the row (principle 5).

    Leaves the rows pending: a refusal is a deferral, and `doctor` counts the
    ones that keep deferring.
    """
    if not ids:
        return
    connection.execute(
        f"UPDATE {MAILBOX_TABLE} SET last_refusal = ?,"
        " delivery_attempts = delivery_attempts + 1"
        f" WHERE id IN ({_placeholders(ids)}) AND delivered_at IS NULL",
        (refusal, *ids),
    )


def mailbox_counts(connection: sqlite3.Connection) -> MailboxCounts:
    """What `doctor` prints (T14, T20). Three facts, none derived from another."""
    row = connection.execute(_COUNTS).fetchone()
    return MailboxCounts(
        pending=int(row["pending"] or 0),
        delivered=int(row["delivered"] or 0),
        deferred=int(row["deferred"] or 0),
    )
