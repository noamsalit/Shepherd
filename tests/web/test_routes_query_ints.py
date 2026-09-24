"""BC-23: an integer query argument reaches `invoke()` as an integer.

Seam: `routes.resolve` (pure), plus one HTTP call through the real server. A
query string is text, and every tool that declares an integer argument refuses
a string: `GET /api/audit?limit=0` used to arrive as `{}` (the key was not
declared) and `?scrollback=10` as `{"scrollback": "10"}` (declared, never
converted). A value that is not an integer is **dropped**, so the tool's own
default applies — it is never forwarded as a string (E14).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from web.conftest import Client, MasterDoubles

from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.toolsurface.audit import AUDIT_PREFIX, build_audit_sink
from shepherd.toolsurface.types import ActorKind, AuditRecord, BlastClass
from shepherd.web import routes

AUDIT = "/api/audit"
OUTPUT = "/api/sessions/s-1/output"


def test_limit_is_forwarded_as_an_integer() -> None:
    resolved = routes.resolve(AUDIT, {"limit": ["0"]})
    assert resolved is not None
    assert resolved.tool == "get_audit_log"
    assert resolved.args == {"limit": 0}


def test_scrollback_is_forwarded_as_an_integer() -> None:
    resolved = routes.resolve(OUTPUT, {"scrollback": ["10"]})
    assert resolved is not None
    assert resolved.args == {"scrollback": 10, "session_id": "s-1"}


@pytest.mark.parametrize("raw", ["abc", "", "1.5", "10abc"])
def test_a_non_integer_value_is_dropped(raw: str) -> None:
    """E14: the tool's default applies, and no string reaches the handler."""
    resolved = routes.resolve(AUDIT, {"limit": [raw]})
    assert resolved is not None
    assert resolved.args == {}


def test_a_string_argument_is_still_forwarded_as_text() -> None:
    """The conversion is keyed on the name, not applied to every value."""
    resolved = routes.resolve("/api/mailbox", {"session_id": ["42"]})
    assert resolved is not None
    assert resolved.args == {"session_id": "42"}


def _plant(root: Path) -> None:
    """One real record, through the shipped writer, so `[]` means the limit."""
    sink = build_audit_sink(
        log=RotatingJsonlLog(root, AUDIT_PREFIX),
        bump=lambda kind: pytest.fail(f"the audit line was lost: {kind}"),
        date_of=lambda at: at[:10],
    )
    sink(
        AuditRecord(
            at="2026-09-16T10:00:30Z",
            correlation_id="c-1",
            actor_kind=ActorKind.HUMAN,
            actor_id="web",
            tool="spawn_session",
            blast_class=BlastClass.LOCAL_WRITE,
            args={},
            autonomy_level=0,
            decision="allow",
            approved_by=None,
            approval_id=None,
            result="ok",
            failure=None,
            duration_ms=1,
        )
    )


def test_limit_zero_over_http_returns_no_records(
    client: Client, master_doubles: MasterDoubles
) -> None:
    _plant(master_doubles.audit_root)
    everything = client.request(AUDIT).json()
    assert everything["ok"] is True, everything
    data = everything["data"]
    assert isinstance(data, dict)
    assert len(data["records"]) == 1

    limited = client.request(f"{AUDIT}?limit=0").json()
    assert limited["ok"] is True, limited
    limited_data = limited["data"]
    assert isinstance(limited_data, dict)
    assert limited_data["records"] == []
    assert limited_data["limit"] == 0
