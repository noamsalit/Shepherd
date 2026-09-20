"""The two tools `cli/doctor` was blocked on (BLOCKER T17-1, T17-2).

Seam: `invoke()`. `doctor` is an L5 consumer and may not import `store/` or
`engines/` (D19, D35) — which is why it printed *unknown* for the schema version
and the engine version, and was right to. These are the capabilities that make
the unknowns knowable without widening the consumer boundary.

Principle 5 is the whole shape of these two: an engine binary that is not on
this host, and a drift check nobody has run here, are **values** — never a
guessed version and never a reassuring "clean".
"""

from __future__ import annotations

import json
from pathlib import Path

from shepherd.engines.claude_code.version import PINNED_ENGINE_VERSION
from shepherd.store.db import open_store
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from shepherd.toolsurface.registry import invoke, registered_tools
from shepherd.toolsurface.tools_engine import register_engine_tools
from shepherd.toolsurface.types import Audience, BlastClass, CallerContext

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="cli", correlation_id="cid")


def payload(name: str) -> dict[str, object]:
    result = invoke(name, {}, HUMAN)
    assert result.ok is True, result.error
    assert isinstance(result.data, dict)
    return result.data


def test_schema_status_reports_a_database_that_does_not_exist(tmp_path: Path) -> None:
    """F16: the first run. `0` is the version an absent database has, not an error."""
    register_engine_tools(
        db_path=tmp_path / "never" / "shepherd.db",
        drift_record_path=tmp_path / "never" / "drift.json",
        version_reader=lambda: None,
    )
    data = payload("schema_status")
    assert data == {
        "schema_version": 0,
        "expected_version": EXPECTED_SCHEMA_VERSION,
        "database_exists": False,
    }


def test_schema_status_reports_the_applied_version(tmp_path: Path) -> None:
    """§7 migration rules 1-2 get a line of their own, from the real database."""
    db_path = tmp_path / "data" / "shepherd.db"
    store = open_store(db_path)
    try:
        register_engine_tools(
            db_path=db_path,
            drift_record_path=tmp_path / "drift.json",
            version_reader=lambda: None,
        )
        data = payload("schema_status")
    finally:
        store.close()
    assert data["schema_version"] == EXPECTED_SCHEMA_VERSION
    assert data["database_exists"] is True


def test_engine_version_is_unknown_rather_than_guessed(tmp_path: Path) -> None:
    """No engine binary, no drift record: two honest unknowns (principle 5)."""
    register_engine_tools(
        db_path=tmp_path / "shepherd.db",
        drift_record_path=tmp_path / "drift.json",
        version_reader=lambda: None,
    )
    data = payload("engine_version")
    assert data["version"] is None
    assert data["pinned_version"] == PINNED_ENGINE_VERSION
    assert data["drift_checked_at"] is None
    assert data["drift_verdict"] == "unchecked"


def test_engine_version_reports_a_recorded_drift_check(tmp_path: Path) -> None:
    """G12's line: the running version, what the captures are pinned to, and when
    the drift gate last ran here — with its verdict, not just its date."""
    record = tmp_path / "drift.json"
    record.write_text(
        json.dumps(
            {
                "checked_at": "2026-09-17T08:00:00Z",
                "engine_version": "2.1.273",
                "pinned_version": PINNED_ENGINE_VERSION,
                "verdict": "clean",
                "detail": "33 event names + 4 enums unchanged",
            }
        ),
        encoding="utf-8",
    )
    register_engine_tools(
        db_path=tmp_path / "shepherd.db",
        drift_record_path=record,
        version_reader=lambda: "2.1.273",
    )
    data = payload("engine_version")
    assert data["version"] == "2.1.273"
    assert data["pinned_version"] == PINNED_ENGINE_VERSION
    assert data["drift_checked_at"] == "2026-09-17T08:00:00Z"
    assert data["drift_verdict"] == "clean"
    assert data["drift_detail"] == "33 event names + 4 enums unchanged"


def test_a_torn_drift_record_is_unchecked_not_clean(tmp_path: Path) -> None:
    """A record we cannot read is not a pass. Silence must not read as green."""
    record = tmp_path / "drift.json"
    record.write_text("{not json", encoding="utf-8")
    register_engine_tools(
        db_path=tmp_path / "shepherd.db",
        drift_record_path=record,
        version_reader=lambda: "2.1.273",
    )
    data = payload("engine_version")
    assert data["drift_verdict"] == "unchecked"
    assert data["drift_checked_at"] is None


def test_both_tools_are_local_read_and_human_readable(tmp_path: Path) -> None:
    register_engine_tools(
        db_path=tmp_path / "shepherd.db",
        drift_record_path=tmp_path / "drift.json",
        version_reader=lambda: None,
    )
    tools = registered_tools()
    assert set(tools) == {"schema_status", "engine_version"}
    for tool in tools.values():
        assert tool.blast_class is BlastClass.LOCAL_READ
        assert Audience.HUMAN in tool.audiences
