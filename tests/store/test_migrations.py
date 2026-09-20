"""T5: the migration runner and migration 001 (§7 "Migrations", three rules).

Integration seam: a real SQLite database under `tmp_path`. There is no `sqlite3`
CLI on this host (§Runtime toolchain), so every check goes through the Python
module.
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from shepherd.store.migrate import (
    EXPECTED_SCHEMA_VERSION,
    MigrationRefused,
    migrate,
    read_schema_version,
)

M1_TABLES = {"workspace", "repo", "session", "app_state"}


def connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def table_names(db_path: Path) -> set[str]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {name for (name,) in rows if not name.startswith("sqlite_")}


def insert_minimal_session(
    conn: sqlite3.Connection,
    session_id: str,
    engine_session_id: str | None,
    **overrides: object,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO workspace (id, name, created_at)"
        " VALUES ('ws1', 'w', '2026-09-16T00:00:00Z')"
    )
    columns: dict[str, object] = {
        "id": session_id,
        "engine_session_id": engine_session_id,
        "workspace_id": "ws1",
        "origin": "external",
        "ownership": "attached",
        "ephemeral": 0,
        "depth": 0,
        "attempt": 1,
        "engine": "claude_code",
        "started_at": "2026-09-16T00:00:00Z",
        "state": "running",
    }
    columns.update(overrides)
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    conn.execute(f"INSERT INTO session ({names}) VALUES ({marks})", list(columns.values()))


def test_migrate_creates_four_tables_and_bookkeeping(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "shepherd.db"

    # M2's 002 and M3's 003 apply on top (ADR-M2-4, DP3); 001's own bookkeeping
    # row is asserted below and is what this test is about.
    assert migrate(db_path) == EXPECTED_SCHEMA_VERSION == 3

    names = table_names(db_path)
    assert M1_TABLES <= names
    assert "schema_migration" in names
    # M5's tables must not exist yet.
    assert {"work_item", "queue"} & names == set()
    assert read_schema_version(db_path) == 3

    with connect(db_path) as conn:
        version, name, checksum, applied_at = conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migration"
            " WHERE version = 1"
        ).fetchone()
    assert version == 1
    assert name == "001_m1_foundation"
    assert len(checksum) == 64
    assert applied_at.endswith("Z")

    # Every table carries owner_id NOT NULL DEFAULT 'local' (§7, D2).
    for table in M1_TABLES:
        with connect(db_path) as conn:
            owner = [row for row in conn.execute(f"PRAGMA table_info({table})") if row[1] == "owner_id"]
        assert owner, f"{table} has no owner_id"
        assert owner[0][3] == 1, f"{table}.owner_id is nullable"
        assert owner[0][4] == "'local'"


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "shepherd.db"
    assert migrate(db_path) == 3
    assert migrate(db_path) == 3
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 3


def test_migrate_creates_missing_data_dir(tmp_path: Path) -> None:
    """F16 — the greenfield first five minutes: nothing has made the data dir."""
    data_dir = tmp_path / "share" / "shepherd"
    assert not data_dir.exists()

    migrate(data_dir / "shepherd.db")

    assert data_dir.is_dir()
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700


def test_checksum_mismatch_refuses_to_start(tmp_path: Path) -> None:
    """Rule 1 — history was edited; guessing is worse than stopping."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE schema_migration SET checksum = 'deadbeef' WHERE version = 1")

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path)
    assert "checksum" in str(excinfo.value)


def test_newer_db_version_refuses_to_start(tmp_path: Path) -> None:
    """Rule 2 — yesterday's binary against tomorrow's schema corrupts quietly."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at)"
            " VALUES (99, '099_from_the_future', 'x', '2026-09-16T00:00:00Z')"
        )

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path)
    message = str(excinfo.value)
    assert "99" in message and str(EXPECTED_SCHEMA_VERSION) in message
    assert read_schema_version(db_path) == 99


def test_migrations_run_in_one_transaction(tmp_path: Path) -> None:
    """A later migration failing leaves nothing from the earlier one behind."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_first.sql").write_text("CREATE TABLE early (id TEXT);\n", encoding="utf-8")
    (migrations / "002_broken.sql").write_text("CREATE TABLE ;\n", encoding="utf-8")
    db_path = tmp_path / "shepherd.db"

    with pytest.raises(MigrationRefused):
        migrate(db_path, migrations_dir=migrations)

    assert table_names(db_path) == set()
    assert read_schema_version(db_path) == 0


def test_wal_is_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0  # per-connection, not stored


def test_enum_check_constraints_reject_bad_values(tmp_path: Path) -> None:
    """§7: enums are TEXT with a CHECK constraint — never ints."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        insert_minimal_session(conn, "s1", "eng-1")

        for column, bad in (
            ("state", "vibing"),
            ("origin", "cron"),
            ("ownership", "class"),
            ("title_source", "guess"),
            ("decided_by", "vibes"),
            ("outcome", "great"),
            ("stop_reason", "gave_up"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE session SET {column} = ? WHERE id = 's1'", (bad,))

        # …and a legal value is accepted.
        conn.execute("UPDATE session SET state = 'needs_you' WHERE id = 's1'")
        assert conn.execute("SELECT state FROM session WHERE id='s1'").fetchone()[0] == "needs_you"


def test_session_has_pid_and_proc_start_columns(tmp_path: Path) -> None:
    """Decision pressure 7 — the sidecar is deleted on exit (E29); these survive it."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        info = {row[1]: row for row in conn.execute("PRAGMA table_info(session)")}
        assert info["pid"][2] == "INTEGER"
        assert info["pid"][3] == 0  # nullable
        assert info["proc_start"][2] == "TEXT"
        assert info["proc_start"][3] == 0

        insert_minimal_session(conn, "s1", "eng-1", pid=4110260, proc_start="12345678")
        assert conn.execute("SELECT pid, proc_start FROM session").fetchone() == (
            4110260,
            "12345678",
        )


def test_duplicate_engine_session_id_is_rejected_by_the_index(tmp_path: Path) -> None:
    """P14 by construction (F14), not by an application check-then-insert."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        insert_minimal_session(conn, "s1", "eng-1")
        with pytest.raises(sqlite3.IntegrityError):
            insert_minimal_session(conn, "s2", "eng-1")


def test_two_null_engine_session_ids_are_allowed(tmp_path: Path) -> None:
    """§7: `engine_session_id` is null until the engine emits it."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        insert_minimal_session(conn, "s1", None)
        insert_minimal_session(conn, "s2", None)
        assert conn.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 2


def test_full_outer_join_is_available(tmp_path: Path) -> None:
    """§18's last row: SQLite ≥ 3.39, asserted on the running interpreter."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as conn:
        recorded = conn.execute(
            "SELECT value FROM app_state WHERE key = 'capability.full_outer_join'"
        ).fetchone()
        assert recorded == ("true",)
        rows = conn.execute(
            "SELECT s.id, w.id FROM session s FULL OUTER JOIN workspace w ON w.id = s.workspace_id"
        ).fetchall()
        assert rows == []
