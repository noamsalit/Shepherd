"""Wave 5 support (no scenarios): the INP master scenarios' shared moves.

Named `test_wave5_1_*` only because STAGE B's write surface is `test_wave5_*.py`;
it defines **no test**. The M-/P10 modules import the helpers below by name.

Every scripted turn goes through `Inp.send_turn`'s shape — push one `Turn` on
the process-global `BOOK`, then `POST /api/master/send` — and every observation
is the product's own: the SSE ring (`master.*`, `approval.*`), the audit JSONL,
the DB, the real tmux server on the composition's runner socket. The one
harness-side reading of product state is `master_plane().driver.is_running()`,
used only as a readiness gate ("the turn slot is free again") between turns,
never as an oracle.

**A refused send must not leave a scripted turn behind**: the next turn would
pop it. `send()` therefore pushes only for a send expected to start, and
clears the book if the product refused it.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from shepherd.logs.jsonl import scan_records
from shepherd.runner.local import OWNED_SESSION_RE
from shepherd.runner.tmux_cmd import SESSION_PREFIX
from shepherd.toolsurface.compose import master_plane

from .. import tmuxctl
from ..auditprobe import AuditProbe
from ..httpclient import Client, Response, as_dict
from ..inp import Inp
from ..inproc.master import BOOK, Call, CallResult, Turn, TurnRecord
from ..instance import app_state, db_rows
from ..sandbox import RunContext
from ..sse_rig import Frame, Subscriber, subscribe
from ..verdict import Blocked, await_env, observe

SPAWN_HANG_GUARD_S = 75.0
TURN_BOUND_S = 30.0
CARD_BOUND_S = 10.0
WAKE_HEADER = "while you were away —"  # test-plan M11/M13/M18, verbatim


@dataclass
class Master:
    inp: Inp
    run: RunContext
    stream: Subscriber
    audit: AuditProbe
    project_id: str
    alpha: Path

    @property
    def client(self) -> Client:
        return self.inp.client

    @property
    def socket(self) -> str:
        return self.run.runner_socket(self.inp.root.k)

    @property
    def db(self) -> Path:
        return self.inp.root.db_path


def open_master(inp: Inp, run: RunContext, name: str) -> Master:
    client = inp.client
    project_id = str(as_dict(client.create_project(f"QA6-{name}-Alpha").get("project")).get("project_id"))
    alpha = Path(os.path.realpath(run.repos / "alpha"))
    if client.add_repo(project_id, str(alpha)).get("added") is not True:
        raise Blocked(f"{name}: add_repo(alpha) did not land")
    return Master(inp=inp, run=run, stream=subscribe(name, inp.port), audit=AuditProbe.for_instance(inp.root),
                  project_id=project_id, alpha=alpha)


def post(m: Master, path: str, body: Mapping[str, object], timeout_s: float = 20.0) -> Response:
    client = m.client
    headers = {"Host": client.host, "Origin": client.origin, "Content-Type": "application/json"}
    # A blown hang guard is qualified by a same-client control: FAIL(bound) or BLOCKED (hunter H3).
    return client.post_guarded(path, json.dumps(dict(body)).encode("utf-8"), headers, timeout_s)


def data_of(response: Response) -> dict[str, object]:
    return response.data() if response.status == 200 else {}


# ----- turns -------------------------------------------------------------------------


def slot_free() -> bool:
    plane = master_plane()
    return plane is not None and not plane.driver.is_running()


def send(m: Master, turn: Turn | None, text: str) -> dict[str, object]:
    """Push `turn` (if any) and post the send. A refused send clears what it pushed."""
    if turn is not None:
        if BOOK.pending():
            raise Blocked(f"harness: {BOOK.pending()} scripted turn(s) left in the book before this send")
        BOOK.push(turn)
    answer = data_of(post(m, "/api/master/send", {"text": text}))
    if turn is not None and answer.get("started") is not True:
        BOOK.clear()
    return answer


def record(turn_id: object) -> TurnRecord | None:
    return next((r for r in BOOK.records if r.turn_id == turn_id), None)


def await_end(turn_id: object, bound_s: float = TURN_BOUND_S) -> TurnRecord:
    """Environment: the scripted turn ended and the product released its slot."""
    return await_env(lambda: (r if (r := record(turn_id)) is not None and r.ended and slot_free() else None),
                     bound_s, f"turn {turn_id} ended and the slot released")


def run_turn(m: Master, turn: Turn, text: str) -> tuple[str, TurnRecord]:
    answer = send(m, turn, text)
    turn_id = answer.get("turn_id")
    if answer.get("started") is not True or not isinstance(turn_id, str):
        raise Blocked(f"precondition: a scripted turn did not start: {answer!r}")
    return turn_id, await_end(turn_id)


def drain(m: Master, label: str) -> TurnRecord:
    """A no-op user turn: consumes (and so records) whatever wake set is pending."""
    _turn_id, done = run_turn(m, Turn(says=f"QA6-DRAIN {label}"), f"QA6 drain {label}")
    return done


def result_json(result: CallResult) -> dict[str, object]:
    try:
        decoded: object = json.loads(result.text)
    except json.JSONDecodeError:
        return {}
    return {str(k): v for k, v in decoded.items()} if isinstance(decoded, dict) else {}


def earlier(results: Sequence[CallResult], index: int) -> CallResult:
    """A computed argument's source (P10's shape); a missing one aborts the turn loudly."""
    if len(results) <= index:
        raise AssertionError(f"no earlier result #{index}: {[r.name for r in results]}")
    return results[index]


def project_id_from(results: Sequence[CallResult]) -> str:
    return str(as_dict(result_json(earlier(results, 0)).get("project")).get("project_id"))


def spawn_call(m: Master, title: str, brief: str | None = None) -> Call:
    args: dict[str, object] = {"workspace_id": m.project_id, "cwd": str(m.alpha), "title": title}
    if brief is not None:
        args["brief"] = brief
    return Call("spawn_session", args)


# ----- the stream --------------------------------------------------------------------


def frames(m: Master, mark: int, kind: str) -> list[Frame]:
    return [f for f in m.stream.since(mark) if f.kind == kind]


def turn_frames(m: Master, mark: int, turn_id: object) -> list[Frame]:
    return [f for f in m.stream.since(mark) if f.kind.startswith("master.") and f.data.get("turn_id") == turn_id]


def card(m: Master, mark: int, tool: str, bound_s: float = CARD_BOUND_S, skip: int = 0) -> Frame | None:
    """The (skip+1)-th `approval.created` for `tool` after `mark`, or None."""
    found, _ = observe(lambda: (c[skip] if len(c := [f for f in frames(m, mark, "approval.created")
                                                      if f.data.get("tool") == tool]) > skip else None), bound_s)
    return found


def decided(m: Master, mark: int, approval_id: str, bound_s: float = CARD_BOUND_S) -> Frame | None:
    found, _ = observe(lambda: next((f for f in frames(m, mark, "approval.decided")
                                     if f.data.get("approval_id") == approval_id), None), bound_s)
    return found


def decide(m: Master, approval_id: str, choice: str) -> tuple[int, dict[str, object]]:
    answer = post(m, f"/api/approvals/{approval_id}", {"choice": choice})
    return answer.status, data_of(answer)


def set_level(m: Master, level: int) -> dict[str, object]:
    return data_of(post(m, "/api/autonomy", {"level": level}))


def tool_result(m: Master, mark: int, turn_id: object, tool: str, bound_s: float = CARD_BOUND_S) -> Frame | None:
    found, _ = observe(lambda: next((f for f in turn_frames(m, mark, turn_id)
                                     if f.kind == "master.tool_result" and f.data.get("tool_name") == tool), None),
                       bound_s)
    return found


def detail(frame: Frame | None) -> dict[str, object]:
    value = frame.data.get("detail") if frame is not None else None
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


# ----- sessions, tmux, DB --------------------------------------------------------------


def spawn_user(m: Master, title: str) -> str:
    """A HUMAN spawn over HTTP (origin user_ui: never in the wake set)."""
    answer = data_of(post(m, "/api/sessions", {"workspace_id": m.project_id, "cwd": str(m.alpha), "title": title},
                          timeout_s=SPAWN_HANG_GUARD_S))
    sid = answer.get("session_id")
    if answer.get("spawned") is not True or not isinstance(sid, str):
        raise Blocked(f"precondition: HTTP spawn {title!r} failed: {answer!r}")
    return sid


def kill_http(m: Master, session_id: str) -> dict[str, object]:
    return data_of(post(m, f"/api/sessions/{session_id}/kill", {}))


def owned_panes(m: Master) -> list[str]:
    return sorted(n for n in tmuxctl.sessions(m.socket, m.run.pid) if OWNED_SESSION_RE.fullmatch(n))


def pane_alive(m: Master, session_id: str) -> bool:
    return f"{SESSION_PREFIX}{session_id}" in owned_panes(m)


def await_gone(m: Master, session_id: str, bound_s: float = 5.0) -> bool:
    gone, _ = observe(lambda: (not pane_alive(m, session_id)) or None, bound_s)
    return bool(gone)


def session_row(m: Master, session_id: str) -> dict[str, object]:
    rows = db_rows(m.db, "SELECT * FROM session WHERE id = ?", (session_id,))
    return rows[0] if rows else {}


def await_stopped(m: Master, session_id: str, bound_s: float = 6.0) -> dict[str, object]:
    return await_env(lambda: (r if (r := session_row(m, session_id)).get("ended_at") else None), bound_s,
                     f"session {session_id} ended")


def last_turn_at(m: Master) -> str | None:
    value = app_state(m.db, "master_last_turn_at")
    return value if isinstance(value, str) else None


def anomaly(m: Master, name: str) -> int:
    value = as_dict(m.client.fleet().get("anomalies")).get(name)
    return int(value) if isinstance(value, int) else -1


def rows_for(m: Master, mark: int, tool: str, correlation_id: str | None = None) -> list[dict[str, object]]:
    return [dict(r) for r in m.audit.records_for(mark, tool)
            if correlation_id is None or r.get("correlation_id") == correlation_id]


def shape(rows: Sequence[Mapping[str, object]], *keys: str) -> list[dict[str, object]]:
    return [{k: r.get(k) for k in keys} for r in rows]


def monotonic_now() -> float:
    return time.monotonic()


def audit_file_view(root: Path) -> tuple[list[dict[str, object]], str]:
    """Every audit record in the product's partition order (key order kept), and the files' raw text.

    The day rolls over mid-run on this host's UTC clock, and the product gzips a
    finished day (`logs/jsonl.py`), so the text is read through `gzip` for a
    `.jsonl.gz` part; the records come from the product's own `scan_records`.
    """
    found, stats = scan_records(root.parent, root.name)
    if stats.skipped_malformed or stats.unreadable_files:
        raise AssertionError(f"audit scan skipped lines/files: {stats}")
    records = [{str(k): v for k, v in record.items()} for record, _line in found]
    text = ""
    for path in sorted(p for p in root.glob("*") if p.is_file()):
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                text += handle.read()
        else:
            text += path.read_text(encoding="utf-8")
    return records, text
