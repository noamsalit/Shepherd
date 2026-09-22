"""T1.1 — migration 004, the projects migration, over a real 001→003 database.

The design rehearsed this migration against the real schema with real rows
before the plan was written (A1). This module re-proves it as a test rather
than trusting the rehearsal, because a rehearsal is not a gate.

Integration seam: a real SQLite file under `tmp_path`, the same seam
`test_migration_002.py` and `test_migration_003.py` use. There is no `sqlite3`
CLI on this host, so every check goes through the module.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from shepherd.store.migrate import (
    EXPECTED_SCHEMA_VERSION,
    MIGRATIONS_DIR,
    migrate,
    read_schema_version,
)

#: A2's probe was taken on SQLite 3.45.1: `ALTER TABLE repo DROP COLUMN
#: workspace_id` succeeds on the FK-*referencing* side. `DROP COLUMN` itself
#: arrived in 3.35. A host below that would fail this migration in a way that
#: reads as a migration bug rather than as a toolchain one.
MINIMUM_SQLITE = (3, 35, 0)


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


def through_003(tmp_path: Path) -> Path:
    """A migrations directory holding 001–003 — a database as M3 left it."""
    directory = tmp_path / "m3_only"
    directory.mkdir()
    for name in (
        "001_m1_foundation.sql",
        "002_m2_stop_verdicts.sql",
        "003_m3_mailbox.sql",
    ):
        shutil.copy(MIGRATIONS_DIR / name, directory)
    return directory


def build_003_database(tmp_path: Path) -> Path:
    """001→003 applied, with rows in `workspace`, `repo`, `session` **and**
    `mailbox_message` — exit criterion (a). A migration proved against empty
    tables has not been proved at all: the backfill, the two `DROP COLUMN`s and
    `foreign_key_check` all only say something when there are rows to say it
    about.
    """
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=through_003(tmp_path)) == 3
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspace (id, name, root_path, created_at)"
            " VALUES ('ws1', 'shepherd', '/work/shepherd', '2026-09-16T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO workspace (id, name, root_path, created_at)"
            " VALUES ('ws2', 'api', '/work/api', '2026-09-16T00:00:01Z')"
        )
        connection.execute(
            "INSERT INTO repo (id, workspace_id, name, root_path, git_common_dir,"
            " vcs_remote, added_at) VALUES ('r1', 'ws1', 'shepherd', '/work/shepherd',"
            " '/work/shepherd/.git', 'git@example.invalid:s.git', '2026-09-16T00:01:00Z')"
        )
        connection.execute(
            "INSERT INTO repo (id, workspace_id, name, root_path, git_common_dir,"
            " vcs_remote, added_at) VALUES ('r2', 'ws2', 'api', '/work/api',"
            " '/work/api/.git', NULL, '2026-09-16T00:02:00Z')"
        )
        connection.execute(
            "INSERT INTO session (id, engine_session_id, workspace_id, repo_id, cwd,"
            " started_at, origin, ownership, engine, state)"
            " VALUES ('s1', 'eng-1', 'ws1', 'r1', '/work/shepherd',"
            " '2026-09-16T00:03:00Z', 'external', 'attached', 'claude_code', 'running')"
        )
        connection.execute(
            "INSERT INTO mailbox_message (id, session_id, idempotency_key, body, origin,"
            " queued_at) VALUES ('m1', 's1', 'k-1', 'ship it', 'orchestrator',"
            " '2026-09-16T00:04:00Z')"
        )
    return db_path


def test_the_host_sqlite_supports_drop_column() -> None:
    """Exit criterion (g). A2's probe applies here or it applies nowhere.

    Asserted rather than assumed so a host that regresses says *that*, instead
    of reporting the migration as broken.
    """
    version = tuple(int(part) for part in sqlite3.sqlite_version.split("."))
    assert version >= MINIMUM_SQLITE, sqlite3.sqlite_version


def test_migration_004_applies_over_a_populated_003_database(tmp_path: Path) -> None:
    """Exit criterion (a), plus the shape 004 is supposed to leave behind."""
    db_path = build_003_database(tmp_path)

    assert migrate(db_path) == 4
    assert read_schema_version(db_path) == 4
    assert EXPECTED_SCHEMA_VERSION == 4

    with connect(db_path) as connection:
        workspace_columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(workspace)")
        }
        repo_columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(repo)")
        }
        project_repo_columns = [
            str(row["name"]) for row in connection.execute("PRAGMA table_info(project_repo)")
        ]
        indexes = {
            str(row["name"]) for row in connection.execute("PRAGMA index_list(repo)")
        }

    assert "description" in workspace_columns
    assert "root_path" not in workspace_columns
    assert "workspace_id" not in repo_columns
    assert project_repo_columns == ["workspace_id", "repo_id", "added_at"]
    assert "ix_repo_common_dir" in indexes
    # `session` is **not** rebuilt (the design's load-bearing finding): the
    # pre-existing row is still readable, cell for cell, on the same table.
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM session WHERE id = 's1'").fetchone()
    assert row is not None
    assert str(row["workspace_id"]) == "ws1"
    assert str(row["repo_id"]) == "r1"


def test_migration_004_leaves_foreign_key_check_empty(tmp_path: Path) -> None:
    """P3, and exit criterion (b).

    The mutation this is here to redden is *dropping the `project_repo`
    backfill*: without it the join table is empty, which `foreign_key_check`
    would not notice — so the backfill is asserted in the test below and this
    one holds the FK graph.
    """
    db_path = build_003_database(tmp_path)
    assert migrate(db_path) == 4
    with connect(db_path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_every_pre_existing_repo_keeps_one_project_row_with_its_added_at(
    tmp_path: Path,
) -> None:
    """Exit criterion (c) — the backfill, asserted row by row.

    `added_at` is copied from the `repo` row rather than stamped `now`: the
    join row records when the repo joined the project, and that already
    happened.
    """
    db_path = build_003_database(tmp_path)
    assert migrate(db_path) == 4
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT workspace_id, repo_id, added_at FROM project_repo ORDER BY repo_id"
        ).fetchall()
    assert [tuple(str(cell) for cell in row) for row in rows] == [
        ("ws1", "r1", "2026-09-16T00:01:00Z"),
        ("ws2", "r2", "2026-09-16T00:02:00Z"),
    ]


def test_the_unassigned_project_is_seeded_with_the_schema_default_owner(
    tmp_path: Path,
) -> None:
    """Exit criterion (d), and A10.

    The expected `owner_id` is read from `PRAGMA table_info` rather than typed
    a second time. 004's INSERT **omits** the column so `001:30`'s
    `NOT NULL DEFAULT 'local'` applies; hard-coding `'local'` in the migration
    would make it a second definition site of a value the schema already owns,
    and hard-coding it *here* would make this test agree with that mistake.
    """
    db_path = build_003_database(tmp_path)
    assert migrate(db_path) == 4
    with connect(db_path) as connection:
        default = [
            row["dflt_value"]
            for row in connection.execute("PRAGMA table_info(workspace)")
            if str(row["name"]) == "owner_id"
        ][0]
        row = connection.execute(
            "SELECT id, owner_id, name, description FROM workspace WHERE id = 'unassigned'"
        ).fetchone()
    assert row is not None
    assert str(default) == f"'{row['owner_id']}'"
    assert str(row["name"]) == "Unassigned"
    assert row["description"] is not None


def test_migration_004_is_idempotent_across_two_runs(tmp_path: Path) -> None:
    """E2, and exit criterion (e). The second run writes nothing.

    A second `INSERT` of the seeded row would collide on the primary key; a
    second backfill would double `project_repo`. Both are asserted rather than
    inferred from "it did not raise".
    """
    db_path = build_003_database(tmp_path)
    assert migrate(db_path) == 4
    assert migrate(db_path) == 4
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM project_repo").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM workspace WHERE id = 'unassigned'"
            ).fetchone()[0]
            == 1
        )


def test_the_recorded_checksums_of_001_to_003_are_unchanged(tmp_path: Path) -> None:
    """E3, and exit criterion (f) — 004 is append-only.

    The digests recorded in the database by the 001→003 run are compared with
    the digests of the files **after** 004 landed. If 004's author edited an
    applied migration instead of adding one, the runner's own §7 rule 1 would
    already have refused — so this asserts the files, which is the fact rule 1
    is derived from.
    """
    db_path = build_003_database(tmp_path)
    with connect(db_path) as connection:
        before = {
            int(row["version"]): str(row["checksum"])
            for row in connection.execute("SELECT version, checksum FROM schema_migration")
        }
    assert migrate(db_path) == 4
    with connect(db_path) as connection:
        after = {
            int(row["version"]): str(row["checksum"])
            for row in connection.execute("SELECT version, checksum FROM schema_migration")
        }
    assert {version: after[version] for version in (1, 2, 3)} == before
    for version, name in (
        (1, "001_m1_foundation.sql"),
        (2, "002_m2_stop_verdicts.sql"),
        (3, "003_m3_mailbox.sql"),
    ):
        digest = hashlib.sha256((MIGRATIONS_DIR / name).read_bytes()).hexdigest()
        assert after[version] == digest, name


def test_004_holds_no_trigger_and_no_semicolon_inside_a_string_literal() -> None:
    """The runner splits a migration on `;` rather than parsing it
    (`migrate.py:76-83`), so both of those would silently truncate a statement.
    """
    sql = (MIGRATIONS_DIR / "004_projects.sql").read_text(encoding="utf-8")
    assert "TRIGGER" not in sql.upper()
    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    for statement in body.split(";"):
        assert statement.count("'") % 2 == 0, statement
