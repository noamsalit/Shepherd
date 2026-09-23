"""Wave 3, SUB lane: discovery and liveness — D1-D11 and D13 (no sessiond anywhere here).

One instance holds D1-D8, D11 and D13 (their seeds are additive; each scenario
uses its own helper processes and sidecars). D9 and D10 get their own
instances (D9 needs `<cfg>/sessions/` absent and the counting `claude`; D10
restarts its daemon) — env-plan §5.

Order is load-bearing and is the file order: D1 first (its API clause asserts
`registry_sessions == 1` on a fresh instance), then D6 and D8 (next to D1's
still-running session), then D7 (whose (c) rewrites D1 to `sdk-cli`), then the
independent ones. D4 terminates its **own** D1-shaped session, because D7(c)
has made D1's row ephemeral by then (a departure from "from D1's state",
recorded in the record).

Every sidecar is a harness-shaped input (sessions.py; G5). Waits for a state
are **product** waits bounded by two scan passes of the sourced 2.0 s cadence
(`Sourced`), so a state that never arrives is FAIL(bound), not BLOCKED.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from .. import shims
from ..auditprobe import AuditProbe
from ..mutations import active
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld, Helper, db_rows, last_scan_at
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sessions import await_session, now_ms, session_row, sidecar, write_sidecar
from ..sse_rig import Frame, Subscriber, run_control, subscribe
from ..verdict import Blocked, Recorder, Sourced, await_env, observe

#: Two scan passes plus the pass in flight (discovery_loop.py REGISTRY_SCAN_INTERVAL_S = 2.0).
TWO_PASSES = Sourced(6.0, "two passes of discovery_loop.REGISTRY_SCAN_INTERVAL_S = 2.0 s (+1 in flight)")
IDLE_REASON = "idle — waiting for your next instruction"
WAITING_REASON = "waiting for you"


@dataclass
class Disc:
    controld: Controld
    client: Client
    stream: Subscriber
    audit: AuditProbe
    run: RunContext
    pool: InstancePool
    d1: dict[str, object]


@pytest.fixture(scope="module")
def disc(pool: InstancePool, qa6_run: RunContext) -> Iterator[Disc]:
    controld = pool.ready()
    stream = subscribe("D", controld.port)
    try:
        yield Disc(controld=controld, client=controld.client, stream=stream, audit=AuditProbe.for_instance(controld.root),
                   run=qa6_run, pool=pool, d1={})
    finally:
        stream.close()


def state_of(controld: Controld, engine_id: str) -> str | None:
    row = session_row(controld, engine_id)
    value = row.get("state") if row else None
    return str(value) if value is not None else None


def await_state(controld: Controld, engine_id: str, state: str, bound: Sourced = TWO_PASSES) -> dict[str, object] | None:
    """The row once it is in `state`, or `None` after the sourced bound."""
    row, _ = observe(lambda: (r if (r := session_row(controld, engine_id)) and r.get("state") == state else None),
                     bound.seconds)
    return row


def frames_for(frames: list[Frame], session_id: str, kind: str = "session.state") -> list[Frame]:
    return [f for f in frames if f.session_id == session_id and f.kind == kind]


def counts(client: Client) -> dict[str, object]:
    return as_dict(client.fleet().get("counts"))


def discovery(client: Client) -> dict[str, object]:
    return as_dict(client.fleet().get("discovery"))


def anomaly(client: Client, name: str) -> int:
    value = as_dict(client.fleet().get("anomalies")).get(name)
    return int(value) if isinstance(value, int) else -1


def tree_placement(client: Client, session_id: str) -> str | None:
    for workspace in as_list(client.fleet_tree().get("workspaces")):
        entry = as_dict(workspace)
        for session in as_list(entry.get("sessions")):
            if as_dict(session).get("session_id") == session_id:
                return str(entry.get("project_id"))
    return None


def seed(
    disc: Disc,
    *,
    status: str = "busy",
    cwd: Path | None = None,
    status_age_s: float = 0.0,
    started_age_s: float = 0.0,
    name: str | None = "QA6 session",
    name_source: str | None = "derived",
    entrypoint: str = "cli",
    waiting_for: str | None = None,
) -> tuple[Helper, dict[str, object]]:
    """A helper process and its sidecar (a harness-shaped input, sessions.py)."""
    helper = disc.pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(cwd or disc.run.repos / "loose"),
                   status=status, status_age_s=status_age_s, started_age_s=started_age_s, name=name,
                   name_source=name_source, entrypoint=entrypoint, waiting_for=waiting_for)
    write_sidecar(disc.controld.root.sessions, body)
    return helper, body


def rewrite(disc: Disc, body: dict[str, object], **changes: object) -> dict[str, object]:
    """A newer sidecar for the same process (a real writer bumps its stamps)."""
    updated = dict(body)
    updated.update(changes)
    stamp = now_ms()
    updated["updatedAt"] = stamp
    updated["statusUpdatedAt"] = stamp
    write_sidecar(disc.controld.root.sessions, updated)
    return updated


# ----- D1 ----------------------------------------------------------------------------


@scenario("D1")
def test_d1_busy_sidecar_registers_running_attached(disc: Disc, rec: Recorder) -> None:
    mark = disc.stream.mark()
    status = "busy"
    if active("PP14-D1-status"):
        status = "waiting"
        rec.note("QA6 MUTATION PP14-D1-status APPLIED: the D1 sidecar was written with status 'waiting', not 'busy'")
    helper, body = seed(disc, status=status, name="QA6 loose", name_source="derived")
    engine = str(body["sessionId"])
    row = await_state(disc.controld, engine, "running")
    rec.check("db.running", row is not None, "state running within two passes", state_of(disc.controld, engine))
    if row is None:
        rec.finish()
        return
    rec.equal("db.origin", "external", row.get("origin"))
    rec.equal("db.ownership", "attached", row.get("ownership"))
    rec.equal("db.pid", helper.pid, row.get("pid"))
    rec.equal("db.proc_start", helper.start_token, row.get("proc_start"))
    sid = str(row["id"])
    rec.equal("api.running_count_1", 1, counts(disc.client).get("running"))
    rec.equal("api.registry_sessions_1", 1, discovery(disc.client).get("registry_sessions"))
    rec.equal("api.tree_under_unassigned", "unassigned", tree_placement(disc.client, sid))
    control = run_control(disc.stream, disc.client, "D1", mark)
    states = [f.data for f in frames_for(control.interior, sid)]
    rec.check("stream.session_state_running", {"state": "running", "source": "registry"} in states,
              "session.state {state: running, source: registry}", states)
    disc.d1.update(helper=helper, body=body, sid=sid, engine=engine)
    rec.finish()


def require_d1(disc: Disc) -> tuple[Helper, dict[str, object], str, str]:
    helper = disc.d1.get("helper")
    body = disc.d1.get("body")
    if not isinstance(helper, Helper) or not isinstance(body, dict):
        raise Blocked("D1's running session is not available (D1 did not register)")
    return helper, body, str(disc.d1["sid"]), str(disc.d1["engine"])


# ----- D6 ----------------------------------------------------------------------------


@scenario("D6")
def test_d6_malformed_and_unreadable_sidecars_are_counted(disc: Disc, rec: Recorder) -> None:
    _helper, _body, sid, engine = require_d1(disc)
    sessions_dir = disc.controld.root.sessions
    before_rows = {str(r["engine_session_id"]) for r in db_rows(disc.controld.db, "SELECT engine_session_id FROM session")}
    mark = disc.stream.mark()
    base = anomaly(disc.client, "malformed_payload")
    (sessions_dir / "bad.json").write_text('{"sessionId":', encoding="utf-8")
    locked = sessions_dir / "locked.json"
    locked.write_text('{"sessionId": "QA6-LOCKED"}', encoding="utf-8")
    locked.chmod(0)
    try:
        first_scan = last_scan_at(disc.controld.db)
        risen, _ = observe(lambda: (n if (n := anomaly(disc.client, "malformed_payload")) - base >= 2 else None),
                           TWO_PASSES.seconds)
        rec.check("api.malformed_rises_by_2", risen is not None, "malformed_payload rises by 2 within two passes",
                  anomaly(disc.client, "malformed_payload") - base)
        # Per-pass accounting: two bad files → +2 each pass that reads them.
        scan_a = last_scan_at(disc.controld.db)
        count_a = anomaly(disc.client, "malformed_payload")
        await_env(lambda: (v if (v := last_scan_at(disc.controld.db)) != scan_a else None), 5.0, "the next scan pass")
        per_pass = anomaly(disc.client, "malformed_payload") - count_a
        rec.record("api.malformed_per_pass", per_pass)
        rec.check("db.last_scan_advancing", (last_scan_at(disc.controld.db) or "") > (first_scan or ""),
                  "last_scan_at keeps advancing", (first_scan, last_scan_at(disc.controld.db)))
        rec.equal("db.d1_still_running", "running", state_of(disc.controld, engine))
        after_rows = {str(r["engine_session_id"]) for r in db_rows(disc.controld.db, "SELECT engine_session_id FROM session")}
        rec.equal("db.no_row_for_bad_files", set(), after_rows - before_rows)
        control = run_control(disc.stream, disc.client, "D6", mark)
        strangers = [f.session_id for f in control.interior if f.kind == "session.state" and f.session_id != sid]
        rec.equal("stream.no_frame_for_bad_files", [], strangers)
    finally:
        locked.chmod(0o600)
        locked.unlink()
        (sessions_dir / "bad.json").unlink()
    rec.finish()


# ----- D8 ----------------------------------------------------------------------------


@scenario("D8")
def test_d8_unknown_status_keeps_prior_state(disc: Disc, rec: Recorder) -> None:
    _helper, body, sid, engine = require_d1(disc)
    base_anomaly = anomaly(disc.client, "unknown_registry_status")
    mark = disc.stream.mark()
    updated = rewrite(disc, body, status="thinking-hard")
    seen, _ = observe(lambda: (d if (d := discovery(disc.client)).get("unknown_status") == 1 else None), TWO_PASSES.seconds)
    rec.check("api.unknown_status_plus_1", seen is not None, "discovery.unknown_status +1",
              discovery(disc.client).get("unknown_status"))
    rec.equal("api.anomaly_plus_1", base_anomaly + 1, anomaly(disc.client, "unknown_registry_status"))
    rec.equal("db.state_stays_running", "running", state_of(disc.controld, engine))
    control = run_control(disc.stream, disc.client, "D8", mark)
    rec.equal("stream.no_state_change_frame", [], [f.data for f in frames_for(control.interior, sid)])
    disc.d1["body"] = rewrite(disc, updated, status="busy")
    rec.finish()


# ----- D7 ----------------------------------------------------------------------------


@scenario("D7")
def test_d7_sdk_cli_and_other_entrypoints_skipped_and_counted(disc: Disc, rec: Recorder) -> None:
    _helper, body, sid, engine = require_d1(disc)
    before_rows = {str(r["engine_session_id"]) for r in db_rows(disc.controld.db, "SELECT engine_session_id FROM session")}
    mark = disc.stream.mark()
    _ha, sdk = seed(disc, entrypoint="sdk-cli", name="QA6 D7 sdk")
    seen, _ = observe(lambda: (d if (d := discovery(disc.client)).get("sdk_cli_skipped") == 1 else None), TWO_PASSES.seconds)
    rec.check("api.sdk_cli_skipped_plus_1", seen is not None, "discovery.sdk_cli_skipped == 1",
              discovery(disc.client).get("sdk_cli_skipped"))
    _hb, other = seed(disc, entrypoint="vscode", name="QA6 D7 vscode")
    seen, _ = observe(lambda: (d if (d := discovery(disc.client)).get("skipped_other") == 1 else None), TWO_PASSES.seconds)
    rec.check("api.skipped_other_plus_1", seen is not None, "discovery.skipped_other == 1",
              discovery(disc.client).get("skipped_other"))
    after_rows = {str(r["engine_session_id"]) for r in db_rows(disc.controld.db, "SELECT engine_session_id FROM session")}
    rec.equal("db.no_rows_for_a_b", set(), after_rows - before_rows)
    rewrite(disc, body, entrypoint="sdk-cli")
    gone, _ = observe(lambda: tree_placement(disc.client, sid) is None or None, TWO_PASSES.seconds)
    rec.check("api.c_disappears_from_tree", gone is not None, "D1's session leaves fleet_tree", tree_placement(disc.client, sid))
    row = session_row(disc.controld, engine)
    rec.equal("db.c_ephemeral", 1, row.get("ephemeral") if row else None)
    control = run_control(disc.stream, disc.client, "D7", mark)
    new_ids = {f.session_id for f in control.interior if f.kind == "session.state"} - {sid, None}
    rec.equal("stream.no_new_session_frames", set(), new_ids)
    for helper_body in (sdk, other):
        (disc.controld.root.sessions / f"{helper_body['pid']}.json").unlink()
    rec.finish()


# ----- D2 ----------------------------------------------------------------------------


@scenario("D2")
def test_d2_idle_threshold_bracketed_and_crossed(disc: Disc, rec: Recorder) -> None:
    mark = disc.stream.mark()
    _hx, x = seed(disc, status="idle", status_age_s=50.0, started_age_s=120.0, name="QA6 D2 X")
    _hy, y = seed(disc, status="idle", status_age_s=61.0, started_age_s=120.0, name="QA6 D2 Y")
    wrote = time.monotonic()
    x_id, y_id = str(x["sessionId"]), str(y["sessionId"])
    row_x = await_session(disc.controld, x_id, 6.0)
    await_session(disc.controld, y_id, 6.0)
    await_env(lambda: state_of(disc.controld, x_id) in ("running", "needs_you") and
              state_of(disc.controld, y_id) in ("running", "needs_you") or None, 6.0, "both rows classified")
    first_x, first_y = session_row(disc.controld, x_id), session_row(disc.controld, y_id)
    first_counts = counts(disc.client)
    rec.equal("db.first_x_running", "running", first_x.get("state") if first_x else None)
    rec.equal("db.first_y_needs_you", "needs_you", first_y.get("state") if first_y else None)
    rec.equal("db.first_y_reason", IDLE_REASON, first_y.get("needs_you_reason") if first_y else None)
    rec.record("given.first_read_after_s", round(time.monotonic() - wrote, 2))
    time.sleep(max(0.0, 14.0 - (time.monotonic() - wrote)))  # "read again 14 s later" (D2 When) — an observation window
    second_x = session_row(disc.controld, x_id)
    rec.equal("db.second_x_needs_you", "needs_you", second_x.get("state") if second_x else None)
    rec.equal("db.second_x_reason", IDLE_REASON, second_x.get("needs_you_reason") if second_x else None)
    second_counts = counts(disc.client)
    rec.record("api.counts_first_second", {"first": first_counts, "second": second_counts})
    rec.check("api.counts_match_db", isinstance(second_counts.get("needs_you"), int) and int(str(second_counts.get("needs_you"))) >= 2,
              "fleet needs_you counts X and Y at the second read", second_counts)
    control = run_control(disc.stream, disc.client, "D2", mark)
    row_y = session_row(disc.controld, y_id) or {}
    sid_x, sid_y = str(row_x["id"]), str(row_y.get("id"))
    order = [(f.session_id, f.data.get("state")) for f in control.interior if f.kind == "session.state" and f.session_id in (sid_x, sid_y)]
    y_needs = [i for i, (s, st) in enumerate(order) if s == sid_y and st == "needs_you"]
    x_needs = [i for i, (s, st) in enumerate(order) if s == sid_x and st == "needs_you"]
    rec.check("stream.y_then_x_needs_you", bool(y_needs) and bool(x_needs) and y_needs[0] < x_needs[0],
              "session.state needs_you for Y, then for X", order)
    rec.finish()


# ----- D3 ----------------------------------------------------------------------------


@scenario("D3")
def test_d3_waiting_carries_the_ask_verbatim(disc: Disc, rec: Recorder) -> None:
    mark = disc.stream.mark()
    _h1, first = seed(disc, status="waiting", waiting_for="permission: Bash(git push)", name="QA6 D3 ask")
    _h2, second = seed(disc, status="waiting", name="QA6 D3 bare")
    a, b = str(first["sessionId"]), str(second["sessionId"])
    row_a = await_state(disc.controld, a, "needs_you")
    row_b = await_state(disc.controld, b, "needs_you")
    rec.equal("db.a_reason", "permission: Bash(git push)", row_a.get("needs_you_reason") if row_a else None)
    rec.equal("db.b_reason", WAITING_REASON, row_b.get("needs_you_reason") if row_b else None)
    if row_a is not None:
        api = as_dict(disc.client.session(str(row_a["id"])).get("session"))
        rec.equal("api.session_reason", "permission: Bash(git push)", api.get("needs_you_reason"))
        needs = [as_dict(n) for n in as_list(disc.client.fleet().get("needs_you"))]
        carried = [n for n in needs if n.get("session_id") == row_a["id"]]
        rec.check("api.fleet_needs_you_carries_it", any("permission: Bash(git push)" in json.dumps(n) for n in carried),
                  "fleet_summary.needs_you row carries the reason", carried)
    rewrite(disc, first, status="busy")
    row_a2 = await_state(disc.controld, a, "running")
    rec.equal("db.after_flip_running", "running", row_a2.get("state") if row_a2 else state_of(disc.controld, a))
    rec.check("db.after_flip_reason_cleared", row_a2 is not None and not row_a2.get("needs_you_reason"),
              "reason cleared", row_a2.get("needs_you_reason") if row_a2 else None)
    control = run_control(disc.stream, disc.client, "D3", mark)
    if row_a is not None:
        states = [f.data.get("state") for f in frames_for(control.interior, str(row_a["id"]))]
        rec.check("stream.a_per_change", "needs_you" in states and "running" in states, "session.state per change", states)
    rec.finish()


# ----- D4 ----------------------------------------------------------------------------


@scenario("D4")
def test_d4_process_exit_is_stopped_with_end_time(disc: Disc, rec: Recorder) -> None:
    rec.note("D4 uses its own D1-shaped session: D7(c) has made D1's row ephemeral by now")
    helper, body = seed(disc, status="busy", name="QA6 D4")
    engine = str(body["sessionId"])
    row = await_state(disc.controld, engine, "running")
    if row is None:
        raise Blocked("D4's session never reached running (D1's shape)")
    running_before = counts(disc.client).get("running")
    mark = disc.stream.mark()
    helper.end()
    stopped = await_state(disc.controld, engine, "stopped")
    rec.check("db.stopped", stopped is not None, "stopped within two passes", state_of(disc.controld, engine))
    rec.check("db.ended_at", stopped is not None and bool(stopped.get("ended_at")), "ended_at set",
              stopped.get("ended_at") if stopped else None)
    running_after = counts(disc.client).get("running")
    rec.check("api.running_minus_1", isinstance(running_before, int) and running_after == running_before - 1,
              "fleet running count -1", (running_before, running_after))
    control = run_control(disc.stream, disc.client, "D4", mark)
    rec.check("stream.stopped", any(f.data.get("state") == "stopped" for f in frames_for(control.interior, str(row["id"]))),
              "session.state stopped", [f.data for f in frames_for(control.interior, str(row["id"]))])
    (disc.controld.root.sessions / f"{body['pid']}.json").unlink()
    rec.finish()


# ----- D5 ----------------------------------------------------------------------------


@scenario("D5")
def test_d5_live_pid_wrong_start_token_is_not_that_session(disc: Disc, rec: Recorder) -> None:
    mark = disc.stream.mark()
    helper = disc.pool.helper()
    body = sidecar(pid=helper.pid, proc_start="Mon Jan  1 00:00:00 2001", cwd=str(disc.run.repos / "loose"), name="QA6 D5")
    write_sidecar(disc.controld.root.sessions, body)
    engine = str(body["sessionId"])
    registered, _ = observe(lambda: session_row(disc.controld, engine), TWO_PASSES.seconds)
    time.sleep(2.5)  # one more scan pass: "never running" must hold across passes (an observation window)
    row = session_row(disc.controld, engine)
    if row is None:
        rec.check("db.never_running", True, "stopped, or never running", "no row")
    else:
        rec.equal("db.stopped", "stopped", row.get("state"))
        rec.check("db.ended_at", bool(row.get("ended_at")), "ended_at set", row.get("ended_at"))
    running = [as_dict(s).get("state") for s in as_list(disc.client.get("/api/sessions?state=running").data().get("sessions"))
               if row is not None and as_dict(s).get("session_id") == row.get("id")]
    rec.equal("api.not_counted_running", [], running)
    control = run_control(disc.stream, disc.client, "D5", mark)
    if row is not None:
        states = {f.data.get("state") for f in frames_for(control.interior, str(row["id"]))}
        rec.check("stream.stopped_only", states <= {"stopped"}, "if a row was created, its session.state is stopped", states)
    rec.record("given.registered", registered is not None)
    (disc.controld.root.sessions / f"{body['pid']}.json").unlink()
    rec.finish()


# ----- D11 ---------------------------------------------------------------------------


@scenario("D11")
def test_d11_title_ratchet_user_title_never_overwritten(disc: Disc, rec: Recorder) -> None:
    _helper, body = seed(disc, status="busy", name="engine A", name_source="derived")
    engine = str(body["sessionId"])
    row = await_state(disc.controld, engine, "running")
    rec.equal("db.title_engine_a", ("engine A", "engine"), (row.get("title"), row.get("title_source")) if row else None)
    if row is None:
        rec.finish()
        return
    sid = str(row["id"])
    mark = disc.audit.mark()
    response = disc.client.post(f"/api/sessions/{sid}/rename", {"title": "user title"})
    data = response.data()
    rec.equal("api.rename_answer", {"renamed": True, "title": "user title", "local_only": True},
              {k: data.get(k) for k in ("renamed", "title", "local_only")})
    after = session_row(disc.controld, engine)
    rec.equal("db.after_rename", ("user title", "user"), (after.get("title"), after.get("title_source")) if after else None)
    updated = rewrite(disc, body, name="engine B")
    scan = last_scan_at(disc.controld.db)
    await_env(lambda: (v if (v := last_scan_at(disc.controld.db)) != scan else None), 5.0, "a pass after engine B")
    await_env(lambda: (v if (v := last_scan_at(disc.controld.db)) != scan else None), 5.0, "a second pass")
    rec.equal("db.after_engine_b", "user title", (session_row(disc.controld, engine) or {}).get("title"))
    rewrite(disc, updated, name="engine C", nameSource="weird")
    scan = last_scan_at(disc.controld.db)
    await_env(lambda: (v if (v := last_scan_at(disc.controld.db)) != scan else None), 5.0, "a pass after engine C")
    rec.equal("db.after_engine_c", ("user title", "user"),
              tuple((session_row(disc.controld, engine) or {}).get(k) for k in ("title", "title_source")))
    rows = disc.audit.records_for(mark, "rename_session")
    rec.check("logs.rename_audit", len(rows) == 1 and rows[0].get("decision") == "allow" and rows[0].get("approved_by") == "policy"
              and rows[0].get("blast_class") == "local_write", "rename_session allow, policy, local_write",
              [{k: r.get(k) for k in ("decision", "approved_by", "blast_class")} for r in rows])
    rec.finish()


# ----- D13 ---------------------------------------------------------------------------


@scenario("D13")
def test_d13_cwd_binds_to_the_project_owning_the_repo(disc: Disc, rec: Recorder) -> None:
    alpha, worktree, loose = disc.run.repos / "alpha", disc.run.repos / "alpha-wt", disc.run.repos / "loose"
    project = as_dict(disc.client.create_project("Alpha").get("project"))
    pid = str(project["project_id"])
    added = disc.client.add_repo(pid, str(alpha))
    rec.equal("given.alpha_added", True, added.get("added"))
    mark = disc.stream.mark()
    placements: dict[str, str | None] = {}
    rows: dict[str, dict[str, object]] = {}
    for label, cwd in (("alpha_sub", alpha / "sub"), ("worktree", worktree), ("loose", loose)):
        _helper, body = seed(disc, status="busy", cwd=cwd, name=f"QA6 D13 {label}")
        row = await_state(disc.controld, str(body["sessionId"]), "running")
        if row is not None:
            rows[label] = row
            placements[label] = tree_placement(disc.client, str(row["id"]))
    rec.equal("api.alpha_sub_under_alpha", pid, placements.get("alpha_sub"))
    rec.equal("api.worktree_under_alpha", pid, placements.get("worktree"))
    rec.equal("api.loose_under_unassigned", "unassigned", placements.get("loose"))
    rec.equal("db.binding_agrees", {"alpha_sub": pid, "worktree": pid, "loose": "unassigned"},
              {label: row.get("workspace_id") for label, row in rows.items()})
    control = run_control(disc.stream, disc.client, "D13", mark)
    carried = {label: [f.project_id for f in frames_for(control.interior, str(row["id"]))] for label, row in rows.items()}
    rec.check("stream.frames_carry_project_id",
              all(ids and all(p == (pid if label != "loose" else "unassigned") for p in ids) for label, ids in carried.items()),
              "session.state frames carry the project_id", carried)
    rec.finish()


# ----- D9 (own instance) -------------------------------------------------------------


@scenario("D9")
def test_d9_discovery_never_forks_agents_on_a_timer(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    log = shims.forks_log(qa6_run)
    before = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    controld = pool.ready(path_mode="d9", sessions_dir=False)
    rec.check("given.sessions_absent", not controld.root.sessions.exists(), "<cfg>/sessions/ absent", controld.root.sessions)
    time.sleep(10.0)  # D9 When: "observe for 10 s after readiness" — an observation window, not readiness
    lines = log.read_text(encoding="utf-8").splitlines()[before:] if log.exists() else []
    rec.record("files.forks_logged", len(lines))
    rec.check("files.forks_at_most_1", len(lines) <= 1, "forks.log has <= 1 line", len(lines))
    rec.equal("api.registry_sessions_0", 0, discovery(controld.client).get("registry_sessions"))
    rec.equal("db.no_rows", [], db_rows(controld.db, "SELECT id FROM session"))
    controld.stop()
    rec.finish()


# ----- D10 (own instance) ------------------------------------------------------------


@scenario("D10")
def test_d10_liveness_survives_a_controld_restart(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    first = pool.ready()
    helper = pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(qa6_run.repos / "loose"), name="QA6 D10")
    write_sidecar(first.root.sessions, body)
    engine = str(body["sessionId"])
    running, _ = observe(lambda: state_of(first, engine) == "running" or None, TWO_PASSES.seconds)
    if running is None:
        raise Blocked("D10's session never reached running")
    first.stop()
    rec.equal("logs.first_stop_line", "controld stopped: 3 threads exited · store closed", first.stop_line)
    helper.end()
    second = pool.start(first.root, name="controld-restart")
    second.wait_ready()
    stream = subscribe("D10", second.port, last_event_id="0")
    try:
        stopped = await_state(second, engine, "stopped")
        rec.check("db.stopped_after_restart", stopped is not None and bool(stopped.get("ended_at")),
                  "stopped, ended_at set within two passes after restart", session_row(second, engine))
        rec.equal("api.running_0", 0, counts(second.client).get("running"))
        sid = str((session_row(second, engine) or {}).get("id"))
        control = run_control(stream, second.client, "D10", 0)
        rec.check("stream.new_instance_stopped", any(f.data.get("state") == "stopped" for f in frames_for(control.interior, sid)),
                  "the new instance's session.state stopped", [f.data for f in frames_for(control.interior, sid)])
    finally:
        stream.close()
    second.stop()
    rec.finish()
