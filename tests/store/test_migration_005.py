"""P4 — migration 005, `refused` in `stop_reason`'s CHECK (§3 D73, ADR-QR-6).

The rebuild runs over a **populated v4 database**: a parent and a child
session linked by `parent_session_id` and `retry_of`, a mailbox row for each
(one delivered, one pending) and a `project_repo` row. 002's rebuild alone is
refused on exactly that shape, because `mailbox_message.session_id REFERENCES
session(id)` (`003:37`) and `DROP TABLE session`'s implicit `DELETE` orphans
every mailbox row; the negative control below keeps that reason visible.

Integration seam: the real `migrate()` over a real SQLite file under
`tmp_path`, the seam `test_migration_002.py` … `test_migration_004.py` use. The
owner's real database is never opened.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from shepherd.store.migrate import (
    EXPECTED_SCHEMA_VERSION,
    MIGRATIONS_DIR,
    MigrationRefused,
    migrate,
    read_schema_version,
)

MIGRATION_005 = "005_refused_stop_reason.sql"

#: The v4 chain, as the owner's database holds it today.
THROUGH_004 = (
    "001_m1_foundation.sql",
    "002_m2_stop_verdicts.sql",
    "003_m3_mailbox.sql",
    "004_projects.sql",
)

#: The parent row, every one of its 52 columns written. Literal values, not
#: generated from the schema: a copy step that drops or swaps a column has to
#: be *caught*, and a generated expectation would move with it.
FULL_SESSION: dict[str, object] = {
    "id": "01PARENT",
    "owner_id": "local",
    "engine_session_id": "eng-parent",
    "workspace_id": "ws1",
    "repo_id": "r1",
    "work_item_id": "wi-1",
    "work_item_ref": "wi/1",
    "parent_session_id": None,
    "origin": "orchestrator",
    "ownership": "owned",
    "ephemeral": 0,
    "depth": 0,
    "retry_of": None,
    "attempt": 1,
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
    "stop_reason": "killed",
    "outcome": "unfinished",
    "why": "the operator killed it",
    "confidence": 1.0,
    "decided_by": "declared",
    "next_actions": '[{"text": "Re-spawn", "kind": "respawn"}]',
    "ended_at": "2026-09-16T00:00:04Z",
    "exit_code": 143,
    "auto_compact_at": "2026-09-16T00:00:05Z",
    "quota_notice_at": "2026-09-16T00:00:06Z",
}

#: The child: the parent's retry *and* its child, so both self-references
#: (`parent_session_id`, `retry_of`) have a row to resolve after the rename.
CHILD_SESSION: dict[str, object] = {
    **FULL_SESSION,
    "id": "01CHILD",
    "engine_session_id": "eng-child",
    "parent_session_id": "01PARENT",
    "retry_of": "01PARENT",
    "depth": 1,
    "attempt": 2,
    "state": "running",
    "stop_reason": None,
    "outcome": None,
    "why": None,
    "confidence": None,
    "decided_by": None,
    "ended_at": None,
    "exit_code": None,
}

#: One mailbox row per session, one delivered and one pending, every column set.
#: In `id` order, the order `rows_of` reads them back in.
MAILBOX_ROWS: tuple[dict[str, object], ...] = (
    {
        "id": "01MSGCHILD",
        "owner_id": "local",
        "session_id": "01CHILD",
        "idempotency_key": "k-child",
        "body": "and test it",
        "origin": "user_ui",
        "queued_at": "2026-09-16T00:11:00Z",
        "delivered_at": None,
        "delivery_attempts": 2,
        "last_refusal": "busy: a turn is running",
    },
    {
        "id": "01MSGPARENT",
        "owner_id": "local",
        "session_id": "01PARENT",
        "idempotency_key": "k-parent",
        "body": "ship it",
        "origin": "orchestrator",
        "queued_at": "2026-09-16T00:10:00Z",
        "delivered_at": "2026-09-16T00:10:05Z",
        "delivery_attempts": 1,
        "last_refusal": None,
    },
)


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


def through_004(tmp_path: Path) -> Path:
    """A migrations directory holding 001–004 — a database as it stands today."""
    directory = tmp_path / "v4_only"
    directory.mkdir(parents=True)
    for name in THROUGH_004:
        shutil.copy(MIGRATIONS_DIR / name, directory)
    return directory


def insert(connection: sqlite3.Connection, table: str, row: dict[str, object]) -> None:
    names = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    connection.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(row.values()))


def build_004_database(tmp_path: Path) -> Path:
    """001→004 applied, then the seed the rebuild has to carry across."""
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=through_004(tmp_path)) == 4
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspace (id, name, created_at)"
            " VALUES ('ws1', 'shepherd', '2026-09-16T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO repo (id, name, root_path, git_common_dir, added_at)"
            " VALUES ('r1', 'shepherd', '/work/shepherd', '/work/shepherd/.git',"
            " '2026-09-16T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO project_repo (workspace_id, repo_id, added_at)"
            " VALUES ('ws1', 'r1', '2026-09-16T00:00:00Z')"
        )
        insert(connection, "session", FULL_SESSION)
        insert(connection, "session", CHILD_SESSION)
        for message in MAILBOX_ROWS:
            insert(connection, "mailbox_message", message)
    return db_path


def rows_of(connection: sqlite3.Connection, table: str) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]


def index_spec(connection: sqlite3.Connection, table: str) -> dict[str, object]:
    """Every index on `table`: unique?, partial?, its columns in order, its SQL."""
    spec: dict[str, object] = {}
    for row in connection.execute(f"PRAGMA index_list({table})"):
        columns = tuple(
            entry["name"] for entry in connection.execute(f"PRAGMA index_info({row['name']})")
        )
        declared = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (row["name"],)
        ).fetchone()
        sql = None if declared is None else declared["sql"]
        spec[str(row["name"])] = (int(row["unique"]), int(row["partial"]), columns, sql)
    return spec


def column_spec(connection: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return [
        (row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]


def without_the_stash(sql: str) -> str:
    """ADR-QR-6 option 1: 005's own text with every stash statement removed —
    002's rebuild alone. Built from the file so the control cannot drift from
    the migration it is the control for."""
    kept = [
        statement
        for statement in sql.split(";")
        if "mailbox" not in "\n".join(line.split("--", 1)[0] for line in statement.splitlines())
    ]
    return ";".join(kept)


def test_every_session_row_and_column_survives_005(tmp_path: Path) -> None:
    """Cell by cell, both rows, and the column spec (types, NOT NULL, defaults)."""
    db_path = build_004_database(tmp_path)
    with connect(db_path) as connection:
        before_columns = column_spec(connection, "session")
    assert len(before_columns) == len(FULL_SESSION)

    assert migrate(db_path) == EXPECTED_SCHEMA_VERSION == 5

    with connect(db_path) as connection:
        assert column_spec(connection, "session") == before_columns
        assert rows_of(connection, "session") == [CHILD_SESSION, FULL_SESSION]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_every_mailbox_row_survives_005_and_still_references_its_session(
    tmp_path: Path,
) -> None:
    """Every column of every row, and every reference resolves (PP8)."""
    db_path = build_004_database(tmp_path)
    with connect(db_path) as connection:
        assert rows_of(connection, "mailbox_message") == list(MAILBOX_ROWS)

    migrate(db_path)

    with connect(db_path) as connection:
        assert rows_of(connection, "mailbox_message") == list(MAILBOX_ROWS)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        joined = connection.execute(
            "SELECT m.id, s.id FROM mailbox_message m JOIN session s ON s.id = m.session_id"
            " ORDER BY m.id"
        ).fetchall()
    assert [tuple(row) for row in joined] == [
        ("01MSGCHILD", "01CHILD"),
        ("01MSGPARENT", "01PARENT"),
    ]


def test_both_tables_keep_every_index_after_005(tmp_path: Path) -> None:
    """`session`'s two and `mailbox_message`'s two, spec for spec, and the
    unique ones still enforce."""
    db_path = build_004_database(tmp_path)
    with connect(db_path) as connection:
        before = {table: index_spec(connection, table) for table in ("session", "mailbox_message")}

    migrate(db_path)

    with connect(db_path) as connection:
        after = {table: index_spec(connection, table) for table in ("session", "mailbox_message")}
        assert {"ix_session_fleet", "ux_session_engine_id"} <= set(after["session"])
        with pytest.raises(sqlite3.IntegrityError):
            insert(connection, "session", {**FULL_SESSION, "id": "01DUPLICATE"})
        with pytest.raises(sqlite3.IntegrityError):
            insert(connection, "mailbox_message", {**MAILBOX_ROWS[1], "id": "01MSGDUP"})
    assert after == before


def test_refused_is_accepted_and_a_bogus_reason_is_still_rejected(tmp_path: Path) -> None:
    """D73's value is admitted; the CHECK is still a CHECK, not a dropped one."""
    db_path = build_004_database(tmp_path)
    with connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE session SET stop_reason = 'refused' WHERE id = '01CHILD'")

    migrate(db_path)

    with connect(db_path) as connection:
        connection.execute("UPDATE session SET stop_reason = 'refused' WHERE id = '01CHILD'")
        for column, bad in (
            ("stop_reason", "gave_up"),
            ("decided_by", "vibes"),
            ("outcome", "great"),
            ("state", "sleeping"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"UPDATE session SET {column} = ? WHERE id = '01CHILD'", (bad,))


def test_005_leaves_foreign_keys_enforced(tmp_path: Path) -> None:
    """An orphan mailbox row, an orphan parent and an orphan retry all refused."""
    db_path = build_004_database(tmp_path)
    migrate(db_path)
    with connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            insert(
                connection,
                "mailbox_message",
                {**MAILBOX_ROWS[0], "id": "01ORPHAN", "session_id": "no-such-session"},
            )
        for column in ("parent_session_id", "retry_of"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"UPDATE session SET {column} = 'no-such-session' WHERE id = '01CHILD'"
                )


def test_005_leaves_no_stash_table_behind(tmp_path: Path) -> None:
    db_path = build_004_database(tmp_path)
    migrate(db_path)
    with connect(db_path) as connection:
        for catalogue in ("sqlite_master", "sqlite_temp_master"):
            names = {
                str(row["name"]) for row in connection.execute(f"SELECT name FROM {catalogue}")
            }
            assert "mailbox_stash" not in names, catalogue
            assert "session_new" not in names, catalogue


def test_a_v5_database_refuses_a_v4_binary_by_rule_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Irreversibility, read through the migrate reader: once 005 is applied, a
    binary that expects 4 refuses to start on it (§7 rule 2)."""
    from shepherd.store import migrate as migrate_module

    db_path = build_004_database(tmp_path)
    migrate(db_path)
    assert read_schema_version(db_path) == 5

    monkeypatch.setattr(migrate_module, "EXPECTED_SCHEMA_VERSION", 4)
    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path, migrations_dir=through_004(tmp_path / "old-binary"))
    message = str(excinfo.value)
    assert "5" in message and "4" in message
    assert read_schema_version(db_path) == 5


def test_the_002_rebuild_alone_fails_on_a_database_with_mailbox_rows(tmp_path: Path) -> None:
    """PP16, the negative control: the stash is load-bearing.

    ADR-QR-6 option 1 (005 with its stash statements removed) against the same
    seeded database is refused, and the whole transaction rolls back. Inert SQL
    in `tmp_path`, never a mutation of a shipped file.
    """
    db_path = build_004_database(tmp_path)
    directory = through_004(tmp_path / "control")
    real = (MIGRATIONS_DIR / MIGRATION_005).read_text(encoding="utf-8")
    control = without_the_stash(real)
    assert "mailbox_stash" not in control and "session_new" in control
    (directory / MIGRATION_005).write_text(control, encoding="utf-8")

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path, migrations_dir=directory)
    assert "FOREIGN KEY" in str(excinfo.value)
    assert read_schema_version(db_path) == 4
    with connect(db_path) as connection:
        assert rows_of(connection, "mailbox_message") == list(MAILBOX_ROWS)


def test_005_holds_no_trigger_and_no_semicolon_inside_a_string_literal() -> None:
    """The runner splits a migration on `;` rather than parsing it
    (`migrate.py:76-83`), so both of those would silently truncate a statement.
    And no `writable_schema` (ADR-QR-6 option 4, rejected)."""
    sql = (MIGRATIONS_DIR / MIGRATION_005).read_text(encoding="utf-8")
    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    assert "TRIGGER" not in body.upper()
    assert "WRITABLE_SCHEMA" not in body.upper()
    for statement in body.split(";"):
        assert statement.count("'") % 2 == 0, statement
    for literal in re.findall(r"'([^']*)'", body):
        assert ";" not in literal and "--" not in literal, literal
