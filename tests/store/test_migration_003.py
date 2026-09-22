"""T3 — migration 003, the seventh table (DP3), over a real 002-shaped database.

M2's lesson, re-applied: a migration test that asserts the new table exists
proves almost nothing. 003 adds a table and touches nothing, so what has to be
proved is the *nothing*: every `session` column, type, NOT NULL flag and default
byte-identical across the migration, both of 002's indexes still present **and
still enforcing**, and a pre-existing row readable cell by cell afterwards.

Integration seam: a real SQLite file under `tmp_path`, the same seam
`test_migration_002.py` uses. There is no `sqlite3` CLI on this host
(§Runtime toolchain), so every check goes through the module.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from shepherd.core.mailbox import MailboxOrigin
from shepherd.store.migrate import (
    EXPECTED_SCHEMA_VERSION,
    MIGRATIONS_DIR,
    MigrationRefused,
    migrate,
    read_schema_version,
)

#: The session row written before 003 and read back after. Literal values, not
#: generated from the schema: a migration that drops a column has to be
#: *caught*, and a generated expectation would move with it.
FULL_SESSION: dict[str, object] = {
    "id": "01SESSION",
    "owner_id": "local",
    "engine_session_id": "eng-full",
    "workspace_id": "ws1",
    "repo_id": None,
    "work_item_id": "wi-1",
    "work_item_ref": "wi/1",
    "parent_session_id": None,
    "origin": "external",
    "ownership": "attached",
    "ephemeral": 0,
    "depth": 2,
    "retry_of": None,
    "attempt": 3,
    "brief": "a brief that must survive",
    "cwd": "/tmp/work",
    "worktree_path": "/tmp/wt",
    "runner_handle": "handle-1",
    "engine": "claude_code",
    "provider": "anthropic",
    "model": "claude-opus-4",
    "effort": "high",
    "credential_ref": "cred-1",
    "runner": "tmux",
    "started_at": "2026-09-16T00:00:00Z",
    "title": "a title",
    "title_source": "engine",
    "title_synced_at": "2026-09-16T00:00:01Z",
    "state": "stopped",
    "last_event_at": "2026-09-16T00:00:02Z",
    "needs_you_reason": "a reason",
    "tasks_done": 4,
    "tasks_total": 7,
    "active_subagents": 2,
    "repos_touched": '["a", "b"]',
    "pr_url": "https://example.invalid/pr/1",
    "observed_at": "2026-09-16T00:00:03Z",
    "live_subagent_ids": '["sub-1"]',
    "created_task_ids": '["t-1", "t-2"]',
    "completed_task_ids": '["t-1"]',
    "pid": 4110260,
    "proc_start": "12345678",
    "stop_reason": "derailed",
    "outcome": "unfinished",
    "why": "wandered off",
    "confidence": 0.5,
    "decided_by": "heuristic",
    "next_actions": '[{"text": "Review the diff", "kind": "review"}]',
    "ended_at": "2026-09-16T00:00:04Z",
    "exit_code": None,
    "auto_compact_at": "2026-09-16T00:00:05Z",
    "quota_notice_at": "2026-09-16T00:00:06Z",
}

#: The ten columns the plan's *Schema, exactly* block names, in order.
MAILBOX_COLUMNS = (
    "id",
    "owner_id",
    "session_id",
    "idempotency_key",
    "body",
    "origin",
    "queued_at",
    "delivered_at",
    "delivery_attempts",
    "last_refusal",
)


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


def through_002(tmp_path: Path) -> Path:
    """A migrations directory holding 001 and 002 — a database as M2 left it."""
    directory = tmp_path / "m2_only"
    directory.mkdir()
    for name in ("001_m1_foundation.sql", "002_m2_stop_verdicts.sql"):
        shutil.copy(MIGRATIONS_DIR / name, directory)
    return directory


def build_002_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=through_002(tmp_path)) == 2
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspace (id, name, created_at)"
            " VALUES ('ws1', 'w', '2026-09-16T00:00:00Z')"
        )
        names = ", ".join(FULL_SESSION)
        marks = ", ".join("?" for _ in FULL_SESSION)
        connection.execute(
            f"INSERT INTO session ({names}) VALUES ({marks})", list(FULL_SESSION.values())
        )
    return db_path


def session_column_spec(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
    """Name, type, NOT NULL, default and pk for every `session` column, in order.

    The default is included deliberately: a rebuild that copies values but not
    `DEFAULT`s breaks the *next* insert, not this one.
    """
    return [
        (row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in connection.execute("PRAGMA table_info(session)")
    ]


def index_spec(connection: sqlite3.Connection, table: str) -> dict[str, object]:
    """Every index on `table`, each mapped to (unique?, its columns in order)."""
    spec: dict[str, object] = {}
    for row in connection.execute(f"PRAGMA index_list({table})"):
        columns = tuple(
            entry["name"] for entry in connection.execute(f"PRAGMA index_info({row['name']})")
        )
        spec[str(row["name"])] = (int(row["unique"]), columns)
    return spec


def insert_message(connection: sqlite3.Connection, **overrides: object) -> None:
    columns: dict[str, object] = {
        "id": "01MSG",
        "session_id": "01SESSION",
        "idempotency_key": "k-1",
        "body": "ship it",
        "origin": "orchestrator",
        "queued_at": "2026-09-17T00:00:00Z",
    }
    columns.update(overrides)
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO mailbox_message ({names}) VALUES ({marks})", list(columns.values())
    )


def test_migrate_expected_version_matches_the_highest_file() -> None:
    """§7 rule 3's failure mode: a migration file added without the bump leaves
    `sessiond` waiting for a version `controld` never reports.

    Goes red on 004 landing without the constant moving — and on the constant
    moving without the file.
    """
    versions = sorted(int(path.name.split("_", 1)[0]) for path in MIGRATIONS_DIR.glob("*.sql"))
    assert versions == [1, 2, 3, 4]
    assert EXPECTED_SCHEMA_VERSION == 4
    assert (MIGRATIONS_DIR / "003_m3_mailbox.sql").is_file()


def test_003_applies_over_002_and_changes_nothing_that_was_there(tmp_path: Path) -> None:
    """Acceptance clause 5, at 003: every row, every column spec, every index.

    Goes red if 003 ever touches `session` — a rebuild, a widened `CHECK`, an
    added column — and goes red if the pre-existing row or either index is lost.
    """
    db_path = build_002_database(tmp_path)

    with connect(db_path) as connection:
        before_columns = session_column_spec(connection)
        before_indexes = index_spec(connection, "session")
    assert len(before_columns) == len(FULL_SESSION)  # 52 columns, all of them written above

    assert migrate(db_path) == 4
    assert read_schema_version(db_path) == 4

    with connect(db_path) as connection:
        assert session_column_spec(connection) == before_columns
        assert index_spec(connection, "session") == before_indexes

        row = connection.execute("SELECT * FROM session WHERE id = '01SESSION'").fetchone()
        assert row is not None
        for column, expected in FULL_SESSION.items():
            assert row[column] == expected, column
        assert connection.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 1

        # the unique index is not just present, it still *enforces* — a name in
        # `sqlite_master` proves nothing about the constraint behind it.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO session (id, engine_session_id, workspace_id, origin, ownership,"
                " engine, started_at, state)"
                " VALUES ('02', 'eng-full', 'ws1', 'external', 'attached', 'claude_code',"
                " '2026-09-16T00:00:00Z', 'running')"
            )

        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        # four applied migrations, and 001/002's bookkeeping rows untouched
        assert connection.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 4


def test_003_leaves_every_session_default_alone(tmp_path: Path) -> None:
    """The column spec above compares `DEFAULT` text; this proves the defaults
    still *apply*. Goes red if 003 rebuilds `session` and drops one."""
    db_path = build_002_database(tmp_path)
    migrate(db_path)

    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at, state)"
            " VALUES ('bare', 'ws1', 'external', 'attached', 'claude_code',"
            " '2026-09-16T00:00:00Z', 'running')"
        )
        row = connection.execute("SELECT * FROM session WHERE id = 'bare'").fetchone()
    assert row["owner_id"] == "local"
    assert row["ephemeral"] == 0
    assert row["depth"] == 0
    assert row["attempt"] == 1
    assert row["title_source"] == "brief"
    assert row["tasks_done"] == 0
    assert row["tasks_total"] == 0
    assert row["active_subagents"] == 0
    assert row["repos_touched"] == "[]"
    assert row["next_actions"] == "[]"
    assert row["live_subagent_ids"] == "[]"
    assert row["created_task_ids"] == "[]"
    assert row["completed_task_ids"] == "[]"


def test_the_mailbox_table_has_exactly_the_columns_the_plan_names(tmp_path: Path) -> None:
    """Goes red on a column added, dropped, renamed or reordered against DP3's
    schema block — the drift `store/mailbox.py` (T4) would then have to guess at."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        info = [row for row in connection.execute("PRAGMA table_info(mailbox_message)")]
    assert tuple(row["name"] for row in info) == MAILBOX_COLUMNS

    spec = {row["name"]: row for row in info}
    assert spec["id"]["pk"] == 1
    for column in ("owner_id", "session_id", "idempotency_key", "body", "origin", "queued_at"):
        assert spec[column]["notnull"] == 1, column
        assert spec[column]["type"] == "TEXT", column
    for column in ("delivered_at", "last_refusal"):
        assert spec[column]["notnull"] == 0, column
    assert spec["delivery_attempts"]["type"] == "INTEGER"
    assert spec["delivery_attempts"]["notnull"] == 1


def test_a_queued_message_defaults_to_local_undelivered_and_untried(tmp_path: Path) -> None:
    """D2's `owner_id` default, and principle 5 on the row: no stamp, no
    refusal, no attempts. Goes red if `delivery_attempts` loses its default,
    which would make the count NULL and every increment a no-op."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        seed_session(connection)
        insert_message(connection)
        row = connection.execute("SELECT * FROM mailbox_message WHERE id = '01MSG'").fetchone()
    assert row["owner_id"] == "local"
    assert row["delivery_attempts"] == 0
    assert row["delivered_at"] is None
    assert row["last_refusal"] is None


def seed_session(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO workspace (id, name, created_at)"
        " VALUES ('ws1', 'w', '2026-09-16T00:00:00Z')"
    )
    connection.execute(
        "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at, state)"
        " VALUES ('01SESSION', 'ws1', 'orchestrator', 'owned', 'claude_code',"
        " '2026-09-16T00:00:00Z', 'running')"
    )


def test_a_duplicate_idempotency_key_is_rejected_by_the_index(tmp_path: Path) -> None:
    """D12: "a retrying caller never double-delivers" — by construction, not by
    an application check-then-insert.

    Goes red if `ux_mailbox_idem` is dropped, made non-unique, or has its
    columns reordered to `(idempotency_key, session_id)`: the pair check below
    passes under a reorder, so the *third* insert is what catches it.
    """
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        seed_session(connection)
        connection.execute(
            "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at, state)"
            " VALUES ('02SESSION', 'ws1', 'orchestrator', 'owned', 'claude_code',"
            " '2026-09-16T00:00:00Z', 'running')"
        )
        insert_message(connection, id="01MSG", idempotency_key="k-1")

        with pytest.raises(sqlite3.IntegrityError):
            insert_message(connection, id="02MSG", idempotency_key="k-1")

        # the same key against a *different* session is a different message
        insert_message(connection, id="03MSG", session_id="02SESSION", idempotency_key="k-1")
        # …and a different key against the same session is too
        insert_message(connection, id="04MSG", idempotency_key="k-2")
        assert connection.execute("SELECT COUNT(*) FROM mailbox_message").fetchone()[0] == 3

    with connect(db_path) as connection:
        assert index_spec(connection, "mailbox_message") == {
            # SQLite's own index behind `id TEXT PRIMARY KEY` — listed so this
            # stays an equality and a *third* hand-written index cannot appear
            # unnoticed.
            "sqlite_autoindex_mailbox_message_1": (1, ("id",)),
            "ux_mailbox_idem": (1, ("session_id", "idempotency_key")),
            "ix_mailbox_pending": (0, ("session_id", "delivered_at")),
        }


def test_the_pending_lookup_uses_its_index(tmp_path: Path) -> None:
    """`pending_for(session_id)` (T4) is the mailbox's hot read. Goes red if
    `ix_mailbox_pending` is dropped or its columns reordered, which turns every
    sweep into a full scan of a table that keeps delivered rows for retention."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        plan = " ".join(
            str(row["detail"])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM mailbox_message"
                " WHERE session_id = ? AND delivered_at IS NULL",
                ("01SESSION",),
            )
        )
    assert "ix_mailbox_pending" in plan, plan
    assert "SCAN" not in plan, plan


def test_every_mailbox_origin_is_accepted_by_the_check(tmp_path: Path) -> None:
    """The `CHECK` and `core.mailbox.MailboxOrigin` are one vocabulary or
    neither is. Goes red on an enum member the column rejects — the write that
    fails on the first message from a new origin — and on the `CHECK` being
    dropped, which is how `origin` becomes free text."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        seed_session(connection)
        for index, origin in enumerate(MailboxOrigin):
            insert_message(
                connection,
                id=f"msg-{index}",
                idempotency_key=f"k-{index}",
                origin=str(origin.value),
            )
        assert connection.execute("SELECT COUNT(*) FROM mailbox_message").fetchone()[0] == 5

        for bad in ("ask_fork", "channel", "ORCHESTRATOR", ""):
            with pytest.raises(sqlite3.IntegrityError):
                insert_message(connection, id=f"bad-{bad}", idempotency_key=f"bad-{bad}", origin=bad)


def test_a_message_cannot_be_queued_for_a_session_that_does_not_exist(tmp_path: Path) -> None:
    """`session_id TEXT NOT NULL REFERENCES session(id)`. Goes red if the
    foreign key is dropped, which would let a delete leave an undeliverable row
    the sweep retries forever."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            insert_message(connection, session_id="no-such-session")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO mailbox_message (id, session_id, idempotency_key, body, origin,"
                " queued_at) VALUES ('m', NULL, 'k', 'b', 'orchestrator', '2026-09-17T00:00:00Z')"
            )


def test_checksum_mismatch_on_003_refuses_to_start(tmp_path: Path) -> None:
    """§7 rule 1, re-run at version 3 — history was edited."""
    directory = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, directory)
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=directory) == 4

    target = directory / "003_m3_mailbox.sql"
    target.write_text(target.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path, migrations_dir=directory)
    assert "checksum" in str(excinfo.value)
    assert "003" in str(excinfo.value)


def test_future_schema_refuses_to_start_at_five(tmp_path: Path) -> None:
    """§7 rule 2, re-anchored one version up — a database at 5 against a binary
    at 4.

    The successor to `test_future_schema_refuses_to_start_at_four`, retired by
    §3 D57's migration 004. That test built its impossible sentinel by
    inserting version **4**; 004 makes 4 the real current version and
    `schema_migration.version` is `INTEGER PRIMARY KEY` (`001:22`), so the
    insert became a primary-key collision instead of the refusal it asserted.
    The rule itself is unchanged, which is why this is a rename-with-successor
    rather than a deletion.
    """
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at)"
            " VALUES (5, '005_from_the_future', 'x', '2026-09-17T00:00:00Z')"
        )

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path)
    message = str(excinfo.value)
    assert "5" in message and "4" in message
    assert read_schema_version(db_path) == 5


def test_001_and_002_are_untouched_by_m3(tmp_path: Path) -> None:
    """ADR-M2-4's forward-only rule, in the one form that can actually observe it.

    A dev database at 2 reaching 3 is necessary but not sufficient: the
    migration runner hashes the files it is *given*, so an edit to 001 or 002
    made in the same commit as the test would agree with itself. The digests
    below are the recorded bytes of the two shipped migrations — this goes red
    the moment either file is edited, which is exactly what forward-only
    forbids, and the fix is a new numbered file rather than a new digest here.
    """
    assert build_002_database(tmp_path) is not None
    assert migrate(tmp_path / "shepherd.db") == 4

    digests = {
        "001_m1_foundation.sql": (
            "586d8109df15047489f25146e72e9040013a299f61f389e2c1608d50f764d69e"
        ),
        "002_m2_stop_verdicts.sql": (
            "5f9388b27fa164d490c7dddeca5ee83c29ee5d6d653e34f2255e3369e49def64"
        ),
    }
    for name, digest in digests.items():
        assert hashlib.sha256((MIGRATIONS_DIR / name).read_bytes()).hexdigest() == digest, name
