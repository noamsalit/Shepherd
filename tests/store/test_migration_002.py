"""T2 — migration 002, and §7's three migration rules getting their first real
exercise (ADR-M2-4).

M1 twice amended `001_m1_foundation.sql` in place, justified by "it has never
been applied anywhere but a dev database" *within that milestone*. 002 is the
first migration to run **over an existing schema**, so the forward-only rule is
finally executed rather than asserted.

Integration seam: a real SQLite file under `tmp_path`. There is no `sqlite3` CLI
on this host (§Runtime toolchain), so every check goes through the module.
"""

from __future__ import annotations

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

#: The full session row this test writes before migrating and reads back after.
#: Literal values, not generated from the schema: a copy step that drops a
#: column has to be *caught*, and a generated expectation would move with it.
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
    "stop_reason": "rate_limited",
    "outcome": "paused",
    "why": "the API said slow down",
    "confidence": 1.0,
    "decided_by": "mechanical",
    "next_actions": '[{"text": "Wait", "kind": "retry"}]',
    "ended_at": "2026-09-16T00:00:04Z",
    "exit_code": None,
}


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


def only_001(tmp_path: Path) -> Path:
    """A migrations directory holding nothing but 001 — a database as M1 left it."""
    directory = tmp_path / "m1_only"
    directory.mkdir()
    shutil.copy(MIGRATIONS_DIR / "001_m1_foundation.sql", directory)
    return directory


def build_001_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=only_001(tmp_path)) == 1
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


def test_002_is_still_a_separate_migration_file() -> None:
    """ADR-M2-4: a second migration, not a third edit of the first.

    The constant moved to 3 when M3 added the mailbox (DP3), so what M2 owns
    here is the *file*: this goes red if 002 is ever folded back into 001.
    """
    assert EXPECTED_SCHEMA_VERSION >= 2
    assert (MIGRATIONS_DIR / "002_m2_stop_verdicts.sql").is_file()


def test_002_applies_over_001(tmp_path: Path) -> None:
    """The riskiest statement in M2: every row, every index, every default.

    SQLite cannot alter a `CHECK`, so 002 rebuilds `session`. A rebuild that
    drops a column, reorders a copy or loses an index is silent until a verb
    reads the wrong cell, which is why this asserts cell by cell.
    """
    db_path = build_001_database(tmp_path)

    assert migrate(db_path) == 4
    assert read_schema_version(db_path) == 4

    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM session WHERE id = '01SESSION'").fetchone()
        assert row is not None
        for column, expected in FULL_SESSION.items():
            assert row[column] == expected, column

        # the two new columns exist and default to NULL for a pre-existing row
        assert row["auto_compact_at"] is None
        assert row["quota_notice_at"] is None

        # both indexes survive the drop-and-rename
        indexes = {
            str(name)
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='session'"
            )
        }
        assert {"ix_session_fleet", "ux_session_engine_id"} <= indexes

        # …and they still *work*, which a name alone does not prove.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO session (id, engine_session_id, workspace_id, origin, ownership,"
                " engine, started_at, state)"
                " VALUES ('02', 'eng-full', 'ws1', 'external', 'attached', 'claude_code',"
                " '2026-09-16T00:00:00Z', 'running')"
            )

        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 1
        # the rebuild's scratch table is gone
        tables = {
            str(name)
            for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "session_new" not in tables


def test_002_preserves_column_defaults(tmp_path: Path) -> None:
    """A rebuild that copies values but not DEFAULTs breaks the *next* insert."""
    db_path = build_001_database(tmp_path)
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


def test_002_widens_both_checks(tmp_path: Path) -> None:
    """DP1 and DP2 — four completeness reasons and `heuristic`, rejected before."""
    db_path = build_001_database(tmp_path)

    with connect(db_path) as connection:
        for column, value in (
            ("stop_reason", "derailed"),
            ("stop_reason", "completed"),
            ("stop_reason", "incomplete"),
            ("stop_reason", "blocked_external"),
            ("decided_by", "heuristic"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"UPDATE session SET {column} = ? WHERE id = '01SESSION'", (value,)
                )

    migrate(db_path)

    with connect(db_path) as connection:
        for column, value in (
            ("stop_reason", "derailed"),
            ("stop_reason", "completed"),
            ("stop_reason", "incomplete"),
            ("stop_reason", "blocked_external"),
            ("decided_by", "heuristic"),
        ):
            connection.execute(f"UPDATE session SET {column} = ? WHERE id = '01SESSION'", (value,))
        # …and the constraint is still a constraint, not a dropped one (ADR-M2-4:
        # "a TEXT column with no constraint is how `stop_reason` becomes free-text").
        for column, bad in (
            ("stop_reason", "gave_up"),
            ("decided_by", "vibes"),
            ("outcome", "great"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"UPDATE session SET {column} = ? WHERE id = '01SESSION'", (bad,))


def test_002_adds_the_two_fold_marks(tmp_path: Path) -> None:
    """D24 discards the events that prove `context_exhausted` and `quota_paused`,
    so the marks have to persist as columns (gap N13)."""
    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        info = {row[1]: row for row in connection.execute("PRAGMA table_info(session)")}
        for column in ("auto_compact_at", "quota_notice_at"):
            assert info[column][2] == "TEXT", column
            assert info[column][3] == 0, column  # nullable


def test_checksum_mismatch_on_002_refuses_to_start(tmp_path: Path) -> None:
    """§7 rule 1, over a *real* second migration — history was edited."""
    directory = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, directory)
    db_path = tmp_path / "shepherd.db"
    assert migrate(db_path, migrations_dir=directory) == 4

    target = directory / "002_m2_stop_verdicts.sql"
    target.write_text(target.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")

    with pytest.raises(MigrationRefused) as excinfo:
        migrate(db_path, migrations_dir=directory)
    assert "checksum" in str(excinfo.value)
    assert "002" in str(excinfo.value)


def test_future_schema_refuses_to_start(tmp_path: Path) -> None:
    """§7 rule 2 — a database one version ahead of the binary.

    004 landed (§3 D57), so the version from the future moved from 4 to 5.
    The name carries no version, so this is a body rewrite and the node id is
    kept; `test_migration_003.py`'s sibling named *at_four* could not be, which
    is the whole argument for not putting a number in a test name.
    `tests/store/test_migration_003.py` re-runs this rule at its own version.
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


def test_001_is_untouched_by_m2(tmp_path: Path) -> None:
    """ADR-M2-4's whole point: a dev database that applied 001 still starts."""
    db_path = build_001_database(tmp_path)
    # No checksum refusal on the way up — 001's bytes are as M1 left them.
    assert migrate(db_path) == 4


def test_every_stop_reason_is_accepted_by_the_check(tmp_path: Path) -> None:
    """The CHECK and `core.stops.StopReason` are one vocabulary or neither is.

    A column that accepts 20 values while the enum has 21 is a write that fails
    at 3 a.m. on the one session that finally hit the new reason.
    """
    from shepherd.core.stops import Bucket, DecidedBy, StopReason

    db_path = tmp_path / "shepherd.db"
    migrate(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspace (id, name, created_at)"
            " VALUES ('ws1', 'w', '2026-09-16T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO session (id, workspace_id, origin, ownership, engine, started_at, state)"
            " VALUES ('s1', 'ws1', 'external', 'attached', 'claude_code',"
            " '2026-09-16T00:00:00Z', 'stopped')"
        )
        for reason in StopReason:
            connection.execute(
                "UPDATE session SET stop_reason = ? WHERE id = 's1'", (str(reason.value),)
            )
        for decided in DecidedBy:
            connection.execute(
                "UPDATE session SET decided_by = ? WHERE id = 's1'", (str(decided.value),)
            )
        # …and `unclassified` is deliberately NOT an `outcome` value: it is the
        # absence of a verdict, so the column stays NULL (E-M2-4).
        for bucket in Bucket:
            if bucket is Bucket.UNCLASSIFIED:
                with pytest.raises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE session SET outcome = ? WHERE id = 's1'", (str(bucket.value),)
                    )
                continue
            connection.execute(
                "UPDATE session SET outcome = ? WHERE id = 's1'", (str(bucket.value),)
            )
