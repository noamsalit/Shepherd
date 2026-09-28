"""Attached-session fixtures: engine sidecars in the captured shape, plus waits on discovery.

**A harness-shaped input** (test-plan §6 "Attached sessions"; G5). The key set
is read from the captured sidecar
`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/03-sidecar-after-stop.json`
(a **Linux** capture, read-only) and every value that identifies a process or
a moment is substituted: `pid` is the harness's own `/bin/sleep 3600` child,
`procStart` is the token the **product's** macOS liveness function reports for
it (never the capture's numeric Linux token), stamps are epoch milliseconds
computed from now (or from the past, for the idle threshold — there is no clock
seam, T5). Parity with the real macOS writer is L5's job; if L5 is BLOCKED these
fixtures prove self-consistency only.

Sidecars are written atomically (`<pid>.json.tmp` then rename): the product's
glob is `*.json`, and a half-written file would be counted as malformed.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

from . import paths
from .httpclient import Client, as_dict, as_list
from .instance import Controld, db_rows
from .verdict import await_env


def capture_keys() -> tuple[str, ...]:
    decoded: object = json.loads(paths.SIDECAR_CAPTURE.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError("the captured sidecar is not a JSON object")
    return tuple(str(key) for key in decoded)


def now_ms(offset_s: float = 0.0) -> int:
    return int((time.time() + offset_s) * 1000)


def sidecar(
    *,
    pid: int,
    proc_start: str,
    cwd: str,
    session_id: str | None = None,
    status: str = "busy",
    status_age_s: float = 0.0,
    started_age_s: float = 0.0,
    name: str | None = "QA6 session",
    name_source: str | None = "derived",
    entrypoint: str = "cli",
    kind: str = "interactive",
    waiting_for: str | None = None,
    extra: Mapping[str, object] | None = None,
    drop: tuple[str, ...] = (),
) -> dict[str, object]:
    """One sidecar body with the capture's key set and substituted values."""
    captured: object = json.loads(paths.SIDECAR_CAPTURE.read_text(encoding="utf-8"))
    if not isinstance(captured, dict):
        raise AssertionError("the captured sidecar is not a JSON object")
    body: dict[str, object] = {str(k): v for k, v in captured.items()}
    started = now_ms(-started_age_s)
    stamp = now_ms(-status_age_s)
    body.update(
        pid=pid,
        sessionId=session_id or str(uuid.uuid4()),
        cwd=cwd,
        startedAt=started,
        procStart=proc_start,
        kind=kind,
        entrypoint=entrypoint,
        status=status,
        updatedAt=stamp,
        statusUpdatedAt=stamp,
        nameSince=started,
        tmux=None,
        messagingSocketPath=f"/nonexistent-qa6/{pid}.sock",
    )
    if name is None:
        body.pop("name", None)
    else:
        body["name"] = name
    if name_source is None:
        body.pop("nameSource", None)
    else:
        body["nameSource"] = name_source
    if waiting_for is not None:
        body["waitingFor"] = waiting_for
    if extra:
        body.update(extra)
    for key in drop:
        body.pop(key, None)
    return body


def write_sidecar(sessions_dir: Path, body: Mapping[str, object], filename: str | None = None) -> Path:
    """Atomic write of `<sessions>/<pid>.json` (or `filename`)."""
    name = filename or f"{body['pid']}.json"
    target = sessions_dir / name
    temporary = sessions_dir / f".{name}.tmp"
    temporary.write_text(json.dumps(dict(body)), encoding="utf-8")
    os.replace(temporary, target)
    return target


def session_row(controld: Controld, engine_session_id: str) -> dict[str, object] | None:
    rows = db_rows(controld.db, "SELECT * FROM session WHERE engine_session_id = ?", (engine_session_id,))
    return rows[0] if rows else None


def await_session(controld: Controld, engine_session_id: str, bound_s: float = 6.0,
                  state: str | None = None) -> dict[str, object]:
    """Wait (environment liveness) until discovery registered the row (and state)."""
    def seen() -> dict[str, object] | None:
        row = session_row(controld, engine_session_id)
        if row is None:
            return None
        if state is not None and row.get("state") != state:
            return None
        return row

    return await_env(seen, bound_s, f"session {engine_session_id} registered{f' in {state}' if state else ''}")


def fleet_sessions(client: Client) -> list[dict[str, object]]:
    payload = client.get("/api/sessions").data()
    return [as_dict(row) for row in as_list(payload.get("sessions"))]
