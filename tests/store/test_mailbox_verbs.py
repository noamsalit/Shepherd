"""T4 — the mailbox verbs (D12, D33), over a real SQLite file in `tmp_path`.

The seam is the verb: nothing above `store/` sees SQL, a cursor or a
`sqlite3.Row`. These tests open their own connections because the three claims
D12 makes are **concurrency** claims, and a single-writer harness cannot tell a
working unique index from a lucky ordering:

* **enqueue is idempotent** — `ux_mailbox_idem(session_id, idempotency_key)`;
* **delivery happens once** — the claim is conditional on `delivered_at IS NULL`
  and reports how many rows *it* moved, so two sweeps racing the same pending
  set cannot both deliver it;
* **coalescing loses nothing** — a message enqueued between the read and the
  mark stays pending instead of being marked delivered without ever having been
  in the coalesced body.

Those are three separate claims, and each test below fails if only the other
two hold.
"""

from __future__ import annotations

import sqlite3
import threading
import typing
from pathlib import Path

import pytest

from shepherd.core.mailbox import MailboxCounts, MailboxMessage, MailboxOrigin
from shepherd.store import mailbox
from shepherd.store.migrate import migrate

SESSION_ID = "01SESSION0000000000000000"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "shepherd.db"
    migrate(path)
    connection = connect(path)
    try:
        connection.execute(
            "INSERT INTO workspace (id, name, created_at)"
            " VALUES ('ws-1', 'shepherd', '2026-09-17T10:00:00Z')"
        )
        connection.execute(
            "INSERT INTO session (id, engine_session_id, workspace_id, cwd, started_at,"
            " origin, ownership, engine, state)"
            " VALUES (?, 'eng-1', 'ws-1', '/root/Shepherd', '2026-09-17T10:00:00Z',"
            " 'orchestrator', 'owned', 'claude_code', 'running')",
            (SESSION_ID,),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


@pytest.fixture()
def connection(db_path: Path) -> typing.Iterator[sqlite3.Connection]:
    opened = connect(db_path)
    try:
        yield opened
    finally:
        opened.close()


def message(
    identifier: str,
    *,
    body: str = "ship it",
    idempotency_key: str = "key-1",
    session_id: str = SESSION_ID,
    queued_at: str = "2026-09-17T10:00:00Z",
) -> MailboxMessage:
    return MailboxMessage(
        id=identifier,
        session_id=session_id,
        idempotency_key=idempotency_key,
        body=body,
        origin=MailboxOrigin.ORCHESTRATOR,
        queued_at=queued_at,
        delivered_at=None,
        delivery_attempts=0,
        last_refusal=None,
    )


def run_together(work: typing.Callable[[int], None], workers: int) -> None:
    """Run `work` on `workers` threads released from one barrier."""
    barrier = threading.Barrier(workers)
    failures: list[BaseException] = []

    def body(index: int) -> None:
        barrier.wait()
        try:
            work(index)
        except BaseException as error:  # noqa: BLE001 - reported, not swallowed
            failures.append(error)

    threads = [threading.Thread(target=body, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == [], f"a worker raised: {failures}"


# ----- claim 1: enqueue is idempotent ---------------------------------------


def test_enqueue_is_idempotent(connection: sqlite3.Connection) -> None:
    """A retrying caller never double-queues (D12), and gets the row that won."""
    first = mailbox.enqueue(connection, message("msg-1", body="ship it"))
    second = mailbox.enqueue(connection, message("msg-2", body="ship it twice"))

    assert first.id == "msg-1"
    assert second.id == "msg-1", "the second call must return the stored row, not its own"
    assert second.body == "ship it"
    assert [row.id for row in mailbox.pending_for(connection, SESSION_ID)] == ["msg-1"]


def test_concurrent_enqueues_of_one_key_leave_exactly_one_row(db_path: Path) -> None:
    """The unique index is the mechanism — eight callers, one row."""
    workers = 8

    def enqueue(index: int) -> None:
        own = connect(db_path)
        try:
            mailbox.enqueue(own, message(f"msg-{index}", body=f"body-{index}"))
        finally:
            own.close()

    run_together(enqueue, workers)

    reader = connect(db_path)
    try:
        pending = mailbox.pending_for(reader, SESSION_ID)
    finally:
        reader.close()
    assert len(pending) == 1


def test_a_different_key_is_a_different_message(connection: sqlite3.Connection) -> None:
    """Idempotency is on `(session_id, idempotency_key)` — not on the body."""
    mailbox.enqueue(connection, message("msg-1", idempotency_key="key-1", body="same"))
    mailbox.enqueue(connection, message("msg-2", idempotency_key="key-2", body="same"))

    assert len(mailbox.pending_for(connection, SESSION_ID)) == 2


# ----- claim 2: delivery happens once ---------------------------------------


def test_concurrent_deliveries_move_each_row_exactly_once(db_path: Path) -> None:
    """Six sweeps race the same pending set; between them they deliver it once.

    `mark_delivered` reports the rows **it** moved, so the sum over racing
    callers is the number of pending rows — never `workers * rows`, which is
    what an unconditional `UPDATE ... WHERE id IN (...)` would report.
    """
    seed = connect(db_path)
    try:
        for index in range(5):
            mailbox.enqueue(seed, message(f"msg-{index}", idempotency_key=f"key-{index}"))
        ids = tuple(row.id for row in mailbox.pending_for(seed, SESSION_ID))
    finally:
        seed.close()

    claimed: list[int] = []
    workers = 6

    def deliver(index: int) -> None:
        own = connect(db_path)
        try:
            own.execute("BEGIN IMMEDIATE")
            moved = mailbox.mark_delivered(own, ids, "2026-09-17T10:05:00Z")
            own.execute("COMMIT")
        finally:
            own.close()
        claimed.append(moved)

    run_together(deliver, workers)

    assert sum(claimed) == 5, f"each row moves once, not {sum(claimed)} times"
    assert sorted(claimed, reverse=True)[0] == 5, "one sweep claims the whole batch"

    reader = connect(db_path)
    try:
        assert mailbox.pending_for(reader, SESSION_ID) == []
        counts = mailbox.mailbox_counts(reader)
    finally:
        reader.close()
    assert counts == MailboxCounts(pending=0, delivered=5, deferred=0)


def test_a_delivered_row_is_never_pending_again(connection: sqlite3.Connection) -> None:
    """Restart-safety: `pending_for` reads the column, not a memory of the sweep."""
    mailbox.enqueue(connection, message("msg-1"))
    assert mailbox.mark_delivered(connection, ("msg-1",), "2026-09-17T10:05:00Z") == 1

    assert mailbox.pending_for(connection, SESSION_ID) == []
    assert mailbox.sessions_with_pending(connection) == []
    assert mailbox.mark_delivered(connection, ("msg-1",), "2026-09-17T10:06:00Z") == 0


# ----- claim 3: coalescing loses nothing ------------------------------------


def test_a_message_queued_after_the_read_is_not_marked_delivered(
    connection: sqlite3.Connection,
) -> None:
    """The coalesced body carries the batch that was read; the mark carries the
    same batch. A message that arrived in between is still pending, because it
    was in no body — marking it would lose it silently."""
    mailbox.enqueue(connection, message("msg-1", idempotency_key="key-1", body="first"))
    batch = tuple(row.id for row in mailbox.pending_for(connection, SESSION_ID))
    mailbox.enqueue(connection, message("msg-2", idempotency_key="key-2", body="late"))

    assert mailbox.mark_delivered(connection, batch, "2026-09-17T10:05:00Z") == 1

    still_pending = mailbox.pending_for(connection, SESSION_ID)
    assert [row.id for row in still_pending] == ["msg-2"]
    assert [row.body for row in still_pending] == ["late"]


def test_pending_for_hands_over_every_body_in_queue_order(
    connection: sqlite3.Connection,
) -> None:
    """Five queued notes become one message with five bullets (D12) — so the
    read that feeds the coalescer must carry all five texts, in the order they
    were queued, with nothing deduplicated."""
    for index, body in enumerate(["alpha", "beta", "beta", "gamma", "delta"]):
        mailbox.enqueue(
            connection,
            message(
                f"msg-{index}",
                idempotency_key=f"key-{index}",
                body=body,
                queued_at=f"2026-09-17T10:0{index}:00Z",
            ),
        )

    assert [row.body for row in mailbox.pending_for(connection, SESSION_ID)] == [
        "alpha",
        "beta",
        "beta",
        "gamma",
        "delta",
    ]


# ----- the rest of the surface ----------------------------------------------


def test_pending_is_per_session(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO session (id, engine_session_id, workspace_id, cwd, started_at,"
        " origin, ownership, engine, state)"
        " VALUES ('01OTHER00000000000000000', 'eng-2', 'ws-1', '/root/Shepherd',"
        " '2026-09-17T10:00:00Z', 'orchestrator', 'owned', 'claude_code', 'running')"
    )
    mailbox.enqueue(connection, message("msg-1"))
    mailbox.enqueue(connection, message("msg-2", session_id="01OTHER00000000000000000"))

    assert [row.id for row in mailbox.pending_for(connection, SESSION_ID)] == ["msg-1"]
    assert mailbox.sessions_with_pending(connection) == [
        "01OTHER00000000000000000",
        SESSION_ID,
    ]


def test_a_refusal_is_recorded_on_the_row_and_leaves_it_pending(
    connection: sqlite3.Connection,
) -> None:
    """Principle 5 on the write path: a message that keeps deferring says why."""
    mailbox.enqueue(connection, message("msg-1"))
    mailbox.record_refusal(connection, ("msg-1",), "refuse_input_not_empty")

    pending = mailbox.pending_for(connection, SESSION_ID)
    assert [row.last_refusal for row in pending] == ["refuse_input_not_empty"]
    assert [row.delivery_attempts for row in pending] == [1]
    assert mailbox.mailbox_counts(connection) == MailboxCounts(
        pending=1, delivered=0, deferred=1
    )


def test_a_deferred_row_stops_being_deferred_once_it_is_delivered(
    connection: sqlite3.Connection,
) -> None:
    """`deferred` is not `pending - delivered`: it is a pending row the write
    policy refused, so a delivered row leaves the deferred count."""
    mailbox.enqueue(connection, message("msg-1"))
    mailbox.record_refusal(connection, ("msg-1",), "refuse_dialog")
    mailbox.mark_delivered(connection, ("msg-1",), "2026-09-17T10:05:00Z")

    assert mailbox.mailbox_counts(connection) == MailboxCounts(
        pending=0, delivered=1, deferred=0
    )


def test_no_verb_touches_a_row_of_another_session(connection: sqlite3.Connection) -> None:
    """`mark_delivered` and `record_refusal` name rows by id, and an id that is
    not pending is not a row they may move."""
    mailbox.enqueue(connection, message("msg-1"))
    assert mailbox.mark_delivered(connection, ("does-not-exist",), "2026-09-17T10:05:00Z") == 0
    mailbox.record_refusal(connection, ("does-not-exist",), "refuse_dialog")

    assert [row.delivery_attempts for row in mailbox.pending_for(connection, SESSION_ID)] == [0]


def test_empty_id_tuples_are_a_no_op(connection: sqlite3.Connection) -> None:
    """A sweep with nothing to deliver must not emit `... WHERE id IN ()`."""
    mailbox.enqueue(connection, message("msg-1"))
    assert mailbox.mark_delivered(connection, (), "2026-09-17T10:05:00Z") == 0
    mailbox.record_refusal(connection, (), "refuse_dialog")

    assert len(mailbox.pending_for(connection, SESSION_ID)) == 1


def test_the_hot_reads_use_migration_003s_indexes(connection: sqlite3.Connection) -> None:
    """RD4: an empty mailbox costs one indexed query, not a scan of the
    retention window. Asserted on the planner, not on a comment."""
    pending_plan = " ".join(
        str(row["detail"])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT id FROM mailbox_message WHERE session_id = ? AND delivered_at IS NULL",
            (SESSION_ID,),
        )
    )
    assert "ix_mailbox_pending" in pending_plan

    idem_plan = " ".join(
        str(row["detail"])
        for row in connection.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT id FROM mailbox_message WHERE session_id = ? AND idempotency_key = ?",
            (SESSION_ID, "key-1"),
        )
    )
    assert "ux_mailbox_idem" in idem_plan


def test_a_message_for_an_unknown_session_is_refused(connection: sqlite3.Connection) -> None:
    """The foreign key migration 003 declares, proved rather than assumed."""
    with pytest.raises(Exception):
        mailbox.enqueue(connection, message("msg-1", session_id="01NOSUCHSESSION000000000"))
