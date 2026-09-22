"""Forward-only numbered migrations, applied in one transaction (§7).

Three rules, each guarding a failure that is hard to debug later:

1. a checksum mismatch on an applied migration refuses to start — history was
   edited, and guessing is worse than stopping;
2. a database version newer than the binary refuses to start — old code reading
   a new schema corrupts quietly;
3. `sessiond` never migrates. Nothing here is reachable from `sessiond`: only
   the `controld` composition root calls `migrate()`, and `sessiond` waits for
   the version over the UDS.

ADR-2: this module receives a `Path`. It knows nothing about XDG, platforms, or
environment variables.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from shepherd.core.clock import utc_now

#: The version this binary understands. Rule 2 compares the database to it.
EXPECTED_SCHEMA_VERSION = 4

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

#: Mode 0700 on first run — the data directory holds session briefs.
DATA_DIR_MODE = 0o700

_FILENAME = re.compile(r"^(\d+)_([0-9A-Za-z_\-]+)\.sql$")


class MigrationRefused(Exception):
    """Refusal to start. Raised instead of leaking a driver exception (D33)."""


class _Migration:
    __slots__ = ("version", "name", "checksum", "sql")

    def __init__(self, version: int, name: str, checksum: str, sql: str) -> None:
        self.version = version
        self.name = name
        self.checksum = checksum
        self.sql = sql


def _now() -> str:
    return utc_now()


def _discover(migrations_dir: Path) -> list[_Migration]:
    found: list[_Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationRefused(f"migration filename is not <version>_<name>.sql: {path.name}")
        body = path.read_bytes()
        found.append(
            _Migration(
                version=int(match.group(1)),
                name=f"{match.group(1)}_{match.group(2)}",
                checksum=hashlib.sha256(body).hexdigest(),
                sql=body.decode("utf-8"),
            )
        )
    versions = [migration.version for migration in found]
    if len(set(versions)) != len(versions):
        raise MigrationRefused(f"duplicate migration version in {migrations_dir}")
    return found


def _statements(sql: str) -> list[str]:
    """Split a migration into statements. Comments are stripped first.

    Migrations are plain DDL — no triggers, no string literals containing a
    semicolon — so this stays a split rather than a parser.
    """
    stripped = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _applied(connection: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migration'"
    ).fetchone()
    if table is None:
        return {}
    rows = connection.execute("SELECT version, name, checksum FROM schema_migration").fetchall()
    return {int(version): (str(name), str(checksum)) for version, name, checksum in rows}


def read_schema_version(db_path: Path) -> int:
    """The highest version recorded in the database; 0 when it has none."""
    if not db_path.exists():
        return 0
    connection = sqlite3.connect(db_path)
    try:
        applied = _applied(connection)
    finally:
        connection.close()
    return max(applied, default=0)


def migrate(db_path: Path, migrations_dir: Path | None = None) -> int:
    """Bring `db_path` up to date and return the version now applied.

    `migrations_dir` defaults to this package's `migrations/` and exists so the
    one-transaction rule can be tested against a deliberately broken migration.
    """
    directory = MIGRATIONS_DIR if migrations_dir is None else migrations_dir
    migrations = _discover(directory)

    db_path.parent.mkdir(parents=True, exist_ok=True, mode=DATA_DIR_MODE)

    connection = _connect(db_path)
    try:
        applied = _applied(connection)
        _refuse_on_edited_history(applied, migrations)
        _refuse_on_future_schema(applied)

        pending = [migration for migration in migrations if migration.version not in applied]
        if pending:
            _apply(connection, pending)
            applied = _applied(connection)
    finally:
        connection.close()
    return max(applied, default=0)


def _refuse_on_edited_history(
    applied: dict[int, tuple[str, str]], migrations: list[_Migration]
) -> None:
    for migration in migrations:
        recorded = applied.get(migration.version)
        if recorded is None:
            continue
        name, checksum = recorded
        if checksum != migration.checksum:
            raise MigrationRefused(
                f"checksum mismatch on applied migration {migration.version} ({name}): "
                f"database has {checksum}, {migration.name}.sql hashes to {migration.checksum}"
            )


def _refuse_on_future_schema(applied: dict[int, tuple[str, str]]) -> None:
    highest = max(applied, default=0)
    if highest > EXPECTED_SCHEMA_VERSION:
        raise MigrationRefused(
            f"database schema version {highest} is newer than this binary's "
            f"{EXPECTED_SCHEMA_VERSION}; refusing to start"
        )


def _apply(connection: sqlite3.Connection, pending: list[_Migration]) -> None:
    """Every pending migration in **one** transaction (§7)."""
    connection.execute("BEGIN")
    try:
        for migration in pending:
            for statement in _statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migration (version, name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, _now()),
            )
        _record_capabilities(connection)
        connection.execute("COMMIT")
    except sqlite3.Error as error:
        connection.execute("ROLLBACK")
        raise MigrationRefused(f"migration failed and was rolled back: {error}") from error


def _record_capabilities(connection: sqlite3.Connection) -> None:
    """§18's last row, asserted on the running interpreter rather than assumed."""
    if connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='app_state'"
    ).fetchone() is None:
        return
    try:
        connection.execute("SELECT 1 FROM (SELECT 1 a) x FULL OUTER JOIN (SELECT 1 b) y ON 1=0")
        available = "true"
    except sqlite3.OperationalError:
        available = "false"
    connection.execute(
        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        ("capability.full_outer_join", available, _now()),
    )
    connection.execute(
        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        ("capability.sqlite_version", f'"{sqlite3.sqlite_version}"', _now()),
    )
