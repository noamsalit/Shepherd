"""The two facts `doctor` could not reach for itself (BLOCKER T17-1, T17-2).

`cli/` is an L5 consumer: `tests/boundaries/test_consumer_boundary.py` forbids it
importing `shepherd.store` or `shepherd.engines`, so before these tools existed
`doctor` printed *unknown* for the schema version and the engine version — and
said why, rather than rendering a blank. The capability was missing from the tool
surface, and a consumer may not go around it (D19, D32, D35).

Both are projections. `schema_status` reads `store/migrate.read_schema_version`,
which is the same function `migrate()` itself trusts; `engine_version` reads the
engine adapter. Neither computes anything, and neither invents a value: an
absent database is version `0`, an engine that is not installed is `None`, and a
drift check nobody has run on this host is `unchecked` — never `clean`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from shepherd.engines.claude_code.version import (
    DRIFT_RECORD_NAME,
    PINNED_ENGINE_VERSION,
    VERDICT_UNCHECKED,
    engine_version as read_engine_version,
    read_drift_record,
)
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION, read_schema_version
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef

__all__ = ["DB_NAME", "build_engine_tools", "register_engine_tools", "register_engine_tools_for"]

#: The database file inside `HostDirs.data_dir` (ADR-2). Named here rather than
#: in `store/` because the consumers that need to *locate* it — `cli/` at L5 —
#: may not import `store/` at all, and a path spelled twice is a path that
#: eventually differs.
DB_NAME = "shepherd.db"

VersionReader = Callable[[], str | None]

_HUMAN_AND_MASTER = frozenset({Audience.MASTER, Audience.HUMAN})

_NO_ARGS: Mapping[str, object] = {"type": "object", "properties": {}}


def schema_status(db_path: Path) -> dict[str, object]:
    """§7 migration rules 1-2, as a line a human can read."""
    return {
        "schema_version": read_schema_version(db_path),
        "expected_version": EXPECTED_SCHEMA_VERSION,
        "database_exists": db_path.exists(),
    }


def engine_status(drift_record_path: Path, version_reader: VersionReader) -> dict[str, object]:
    """G12's line: what is running, what the captures are pinned to, and when the
    drift gate last ran here — with its verdict, because a date alone says
    nothing about whether it passed."""
    record = read_drift_record(drift_record_path)
    return {
        "version": version_reader(),
        "pinned_version": PINNED_ENGINE_VERSION,
        "drift_checked_at": None if record is None else record.checked_at,
        "drift_verdict": VERDICT_UNCHECKED if record is None else record.verdict,
        "drift_detail": "" if record is None else record.detail,
    }


def build_engine_tools(
    db_path: Path,
    drift_record_path: Path,
    version_reader: VersionReader = read_engine_version,
) -> tuple[ToolDef, ...]:
    return (
        ToolDef(
            name="schema_status",
            description="The applied schema version, what this build expects, and"
            " whether the database exists at all.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: schema_status(db_path),
            audiences=_HUMAN_AND_MASTER,
        ),
        ToolDef(
            name="engine_version",
            description="The running engine version, the version the captured"
            " schemas are pinned to, and the last drift check on this host.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: engine_status(drift_record_path, version_reader),
            audiences=_HUMAN_AND_MASTER,
        ),
    )


def register_engine_tools(
    db_path: Path,
    drift_record_path: Path,
    version_reader: VersionReader = read_engine_version,
) -> None:
    """Called by the composition root at startup, before `freeze_registry()`."""
    for tool in build_engine_tools(db_path, drift_record_path, version_reader):
        register(tool)


def register_engine_tools_for(data_dir: Path) -> None:
    """Register both tools for a process that knows only its data directory.

    Neither tool opens the store: `schema_status` reads the migration table on a
    short-lived read connection and `engine_version` reads a file and asks the
    engine binary its version. That is what makes it safe in a `shepherd` process
    the control daemon did not start — §7 migration rule 3 keeps migration to
    `controld`, and nothing here migrates or writes.
    """
    register_engine_tools(
        db_path=data_dir / DB_NAME, drift_record_path=data_dir / DRIFT_RECORD_NAME
    )
