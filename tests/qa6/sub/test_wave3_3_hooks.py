"""Wave 3, SUB lane: the hooks module — D12 → H6 → C6 → C4, one instance (test-plan §3).

The instance's seeded target is a sidecar-registered session `QA6-HOOK-TARGET`
in D1's shape; every readiness probe names it, so the probe changes no count
another scenario asserts. Its sessiond instances are started and stopped at
named points, never two on one socket (env-plan §1 "sessiond instances"):

    SD-D12 (D12's 19 frames) → SD-H6 (H6(a)'s one frame; (b)/(c) run with none)
    → SD-C6b (three frames) → SD-C6c (`--expected-schema-version 3`, one frame)
    → C4 runs with no sessiond.

Every `delivered=` oracle subtracts its instance's single probe frame.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import threading
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from .. import hostprobe, paths
from ..hookrig import captured, copy_transcript, dispatch_argv, frame, last_event_at, send, start_ready_sessiond
from ..httpclient import Client, as_dict
from ..mutations import active
from ..instance import Controld, Helper, SessiondManager
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sessions import await_session, session_row, sidecar, write_sidecar
from ..sse_rig import Subscriber, run_control, subscribe
from ..verdict import Blocked, Recorder, observe

TARGET = "QA6-HOOK-TARGET"
VERDICT_MULTIPLE = 10.0
#: H6's harness margin over the sourced 0.25 s hook alarm (mac.py MAC_DISPATCH_TIMEOUT_S).
ALARM_MARGIN_S = 1.0


@dataclass
class Hooks:
    controld: Controld
    client: Client
    manager: SessiondManager
    argv: list[str]
    target_cwd: str
    run: RunContext
    pool: InstancePool
    stream: Subscriber
    notes: dict[str, object] = field(default_factory=dict)


@pytest.fixture(scope="module")
def hooks(pool: InstancePool, qa6_run: RunContext) -> Iterator[Hooks]:
    controld = pool.ready()
    helper = pool.helper()
    cwd = str(qa6_run.repos / "loose")
    write_sidecar(controld.root.sessions,
                  sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=cwd, session_id=TARGET, name="QA6 hook target"))
    await_session(controld, TARGET, 6.0, state="running")
    argv, _settings = dispatch_argv(controld)
    stream = subscribe("hooks", controld.port)
    try:
        yield Hooks(controld=controld, client=controld.client, manager=pool.sessiond(controld), argv=argv,
                    target_cwd=cwd, run=qa6_run, pool=pool, stream=stream)
    finally:
        stream.close()


# ----- D12 ---------------------------------------------------------------------------

#: (case, event, capture dir, substituted field or None, expected stop_reason, expected bucket)
D12_CASES: tuple[tuple[str, str, str, dict[str, object], str | None, str | None], ...] = (
    ("rate_limit", "StopFailure", "S08_mock_http429", {}, "rate_limited", "paused"),
    ("overloaded", "StopFailure", "S08_mock_http429", {"error": "overloaded"}, "rate_limited", "paused"),
    ("authentication_failed", "StopFailure", "S08_mock_http401", {}, "auth_failed", "error"),
    ("oauth_org_not_allowed", "StopFailure", "S08_mock_http429", {"error": "oauth_org_not_allowed"}, "auth_failed", "error"),
    ("account_on_hold", "StopFailure", "S08_mock_http429", {"error": "account_on_hold"}, "account_blocked", "error"),
    ("billing_error", "StopFailure", "S08_mock_http429", {"error": "billing_error"}, "account_blocked", "error"),
    ("invalid_request", "StopFailure", "S08_mock_prompt_too_long", {}, "bad_request", "error"),
    ("model_not_found", "StopFailure", "S08_mock_http429", {"error": "model_not_found"}, "bad_request", "error"),
    ("server_error", "StopFailure", "S08_mock_http500", {}, "server_error", "error"),
    ("max_output_tokens", "StopFailure", "S08_mock_max_tokens", {}, "truncated", "unfinished"),
    ("unknown", "StopFailure", "S08_mock_http400", {}, "unknown", None),
    ("verification_required", "StopFailure", "S08_mock_http429", {"error": "verification_required"}, "unknown", None),
    ("cloud_credential_error", "StopFailure", "S08_mock_http429", {"error": "cloud_credential_error"}, "unknown", None),
    ("prompt_input_exit", "SessionEnd", "S06_clear", {"reason": "prompt_input_exit"}, "user_exited", "unfinished"),
    ("clear", "SessionEnd", "S06_clear", {}, "cleared", "unfinished"),
    ("resume", "SessionEnd", "S06_clear", {"reason": "resume"}, "resumed_elsewhere", "unfinished"),
    ("logout", "SessionEnd", "S06_clear", {"reason": "logout"}, "logged_out", "error"),
    ("other", "SessionEnd", "S01_startup_tools", {}, "unknown", None),
    ("stop_completed", "Stop", "S01_startup_tools", {}, None, "finished"),
)
SUBSTITUTED = frozenset(name for name, _e, _d, sub, _r, _b in D12_CASES if sub)


def verdict_of(client: Client, session_id: str) -> dict[str, object]:
    return as_dict(client.session(session_id).get("session"))


@scenario("D12")
def test_d12_mechanical_stop_evidence_maps_to_spec_reason_and_bucket(hooks: Hooks, rec: Recorder) -> None:
    controld = hooks.controld
    sessions: dict[str, tuple[Helper, str, str]] = {}
    for name, *_rest in D12_CASES:
        helper = hooks.pool.helper()
        body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=hooks.target_cwd, name=f"QA6 D12 {name}")
        write_sidecar(controld.root.sessions, body)
        sessions[name] = (helper, str(body["sessionId"]), "")
    for name, (helper, engine, _sid) in list(sessions.items()):
        row = await_session(controld, engine, 10.0, state="running")
        sessions[name] = (helper, engine, str(row["id"]))
    sd, probe_latency = start_ready_sessiond(hooks.manager, "SD-D12", argv=hooks.argv, target_engine_id=TARGET,
                                             target_cwd=hooks.target_cwd)
    rec.record("given.probe_latency_s", round(probe_latency, 3))
    mark = hooks.stream.mark()
    verdict_bound = max(5.0, VERDICT_MULTIPLE * probe_latency)
    sent_ok = 0
    for name, event, directory, substitution, reason, bucket in D12_CASES:
        helper, engine, sid = sessions[name]
        transcript = copy_transcript(controld.root.cfg, engine)
        if name == "rate_limit" and active("PP15-D12-frame"):
            substitution = {"error": "server_error"}
            rec.note("QA6 MUTATION PP15-D12-frame APPLIED: the rate_limit case's StopFailure carried error 'server_error'")
        payload = frame(captured(directory, event), session_id=engine, cwd=hooks.target_cwd,
                        transcript_path=str(transcript), **substitution)
        sent = send(hooks.argv, controld.env, payload)
        sent_ok += int(sent.rc == 0)
        def decided(sid: str = sid) -> dict[str, object] | None:
            answer = verdict_of(hooks.client, sid)
            return answer if answer.get("decided_by") else None

        got, elapsed = observe(decided, verdict_bound)
        helper.end()
        source = "captured" if name not in SUBSTITUTED else "substituted"
        if got is None:
            rec.fail_bound(f"verdict.{name}", f"a verdict for {name} ({source})", verdict_bound,
                           f"the readiness probe on the same channel landed in {probe_latency:.3f}s")
            continue
        if reason is not None:
            rec.equal(f"verdict.{name}.stop_reason", reason, got.get("stop_reason"))
        else:
            rec.record(f"verdict.{name}.stop_reason", got.get("stop_reason"))
        if bucket is not None:
            rec.equal(f"verdict.{name}.bucket", bucket, got.get("bucket"))
        else:
            rec.record(f"verdict.{name}.bucket", got.get("bucket"))
        rec.equal(f"verdict.{name}.mechanical_1_0", (1.0, "mechanical"), (got.get("confidence"), got.get("decided_by")))
        rec.note(f"{name} ({source}): {got.get('stop_reason')}/{got.get('bucket')} in {elapsed:.2f}s — {got.get('why')}")
    rec.equal("proc.every_dispatch_rc_0", len(D12_CASES), sent_ok)
    buckets: Counter[str] = Counter()
    unknowns = 0
    for name, (_helper, engine, sid) in sessions.items():
        api = verdict_of(hooks.client, sid)
        row = session_row(controld, engine) or {}
        buckets[str(api.get("bucket"))] += 1
        unknowns += int(api.get("stop_reason") == "unknown")
        rec.check(f"db.{name}_agrees_with_api",
                  (row.get("stop_reason"), row.get("outcome"), row.get("confidence"), row.get("decided_by"))
                  == (api.get("stop_reason"), api.get("outcome"), api.get("confidence"), api.get("decided_by")),
                  "the DB verdict columns agree with the API", (row.get("stop_reason"), api.get("stop_reason")))
    fleet = hooks.client.fleet()
    by_bucket = as_dict(fleet.get("by_bucket"))
    target_bucket = str(verdict_of(hooks.client, str((session_row(controld, TARGET) or {}).get("id"))).get("bucket"))
    expected = Counter(buckets)
    expected[target_bucket] += 1
    mismatched = {b: (by_bucket.get(b), n) for b, n in expected.items() if by_bucket.get(b) != n}
    rec.check("api.by_bucket_agrees", not mismatched, "fleet_summary.by_bucket equals the per-session buckets", mismatched)
    rec.record("api.fleet_unknown", {"unknown": fleet.get("unknown"), "by_stop_reason_unknown": unknowns})
    rec.check("api.unknown_counted", isinstance(fleet.get("unknown"), int) and int(str(fleet.get("unknown"))) >= unknowns,
              "every unknown stop_reason counted in the fleet unknown figures", (fleet.get("unknown"), unknowns))
    stop_log = sorted((controld.root.data_dir / "logs" / "stops").glob("*.jsonl"))
    named: Counter[str] = Counter()
    for path in stop_log:
        for line in path.read_text(encoding="utf-8").splitlines():
            record: object = json.loads(line)
            evidence = record.get("evidence") if isinstance(record, dict) else None
            if isinstance(evidence, dict):
                named[str(evidence.get("session_id"))] += 1
    missing = [name for name, (_h, _e, sid) in sessions.items() if named.get(sid, 0) < 1]
    rec.equal("files.stop_log_record_per_session", [], missing)
    control = run_control(hooks.stream, hooks.client, "D12", mark)
    no_stop_frame = [name for name, (_h, _e, sid) in sessions.items()
                     if not any(f.session_id == sid and f.kind == "session.state" and f.data.get("state") == "stopped"
                                for f in control.interior)]
    rec.equal("stream.session_state_stopped_per_session", [], no_stop_frame)
    arrived = sorted({f.kind for name, (_h, _e, sid) in sessions.items() for f in control.interior if f.session_id == sid})
    rec.record("stream.kinds_that_did_arrive_for_the_19", arrived)
    hooks.manager.stop(sd)
    counts = sd.counts()
    rec.check("logs.sd_d12_delivered_minus_probe_19", counts is not None and counts["delivered"] - 1 == 19,
              "sessiond stopped: delivered − 1 probe = 19", sd.stop_line)
    hooks.notes["stop_log_records"] = sum(named.values())
    rec.finish()


# ----- H6 ----------------------------------------------------------------------------


@scenario("H6")
def test_h6_dispatch_delivers_and_cannot_hang_an_agent(hooks: Hooks, rec: Recorder) -> None:
    controld = hooks.controld
    payload = frame(captured("S01_startup_tools", "SessionStart"), session_id=TARGET, cwd=hooks.target_cwd)
    sd, _latency = start_ready_sessiond(hooks.manager, "SD-H6", argv=hooks.argv, target_engine_id=TARGET,
                                        target_cwd=hooks.target_cwd)
    before = last_event_at(controld, TARGET)
    sent = send(hooks.argv, controld.env, payload)
    rec.equal("proc.a_exit_0", 0, sent.rc)
    changed, _ = observe(lambda: last_event_at(controld, TARGET) != before or None, 5.0)
    rec.check("db.a_target_hook_columns_change", changed is not None, "the D1-shaped session's hook-folded columns change",
              (before, last_event_at(controld, TARGET)))
    hooks.manager.stop(sd)
    counts = sd.counts()
    rec.check("logs.a_delivered_2", counts is not None and counts["delivered"] - 1 == 1,
              "SD-H6 stop line delivered=2 (− 1 probe = 1)", sd.stop_line)

    socket_path = hooks.manager.socket
    rec.check("given.b_socket_absent", not socket_path.exists() and not any(r.child.alive() for r in hooks.manager.history),
              "SD-H6 exited and the socket is absent", socket_path.exists())
    sent_b = send(hooks.argv, controld.env, payload)
    rec.check("proc.b_returns_within_1s", sent_b.elapsed_s <= ALARM_MARGIN_S, f"returns within {ALARM_MARGIN_S}s",
              f"{sent_b.elapsed_s:.3f}s")
    rec.record("proc.b_rc", sent_b.rc)

    wedge = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    accepted: list[socket.socket] = []
    wedge.bind(str(socket_path))
    wedge.listen(1)

    def accept_and_never_read() -> None:
        try:
            connection, _ = wedge.accept()
            accepted.append(connection)
        except OSError:
            return  # the listener was closed before a client came: nothing to hold

    holder = threading.Thread(target=accept_and_never_read, daemon=True)
    holder.start()
    try:
        big = json.dumps(dict(payload, qa6_padding="x" * (1 << 20))).encode("utf-8")
        sent_c = send(hooks.argv, controld.env, big, timeout_s=10.0)
        rec.check("proc.c_alarm_within_1s", sent_c.elapsed_s <= ALARM_MARGIN_S, f"terminated within {ALARM_MARGIN_S}s",
                  f"{sent_c.elapsed_s:.3f}s")
        rec.check("proc.c_terminated_by_the_alarm", sent_c.signalled == signal.SIGALRM, "SIGALRM (the 0.25 s alarm)",
                  {"rc": sent_c.rc, "signal": sent_c.signalled})
    finally:
        for connection in accepted:
            connection.close()
        wedge.close()
        socket_path.unlink(missing_ok=True)
        holder.join(timeout=5)
    rec.check("cleanup.wedge_gone", not socket_path.exists(), "the wedged listener closed and its path unlinked",
              socket_path.exists())
    rec.finish()


# ----- C6 ----------------------------------------------------------------------------


@scenario("C6")
def test_c6_sessiond_required_flag_relay_schema_mismatch_stop_line(hooks: Hooks, rec: Recorder) -> None:
    controld = hooks.controld
    bare = subprocess.run([str(paths.SESSIOND_BIN)], env=controld.env, capture_output=True, text=True, timeout=15, check=False)
    rec.equal("proc.a_exit_2", 2, bare.returncode)
    rec.check("logs.a_names_the_flag", "--expected-schema-version" in bare.stderr, "stderr names --expected-schema-version",
              bare.stderr[-200:])

    sd_b, _latency = start_ready_sessiond(hooks.manager, "SD-C6b", argv=hooks.argv, target_engine_id=TARGET,
                                          target_cwd=hooks.target_cwd)
    socket_path = hooks.manager.socket
    rec.equal("files.b_socket_mode", 0o600, stat.S_IMODE(os.stat(socket_path).st_mode))
    before = last_event_at(controld, TARGET)
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
        sent = send(hooks.argv, controld.env, frame(captured("S01_startup_tools", event), session_id=TARGET,
                                                    cwd=hooks.target_cwd))
        rec.equal(f"proc.b_{event}_rc_0", 0, sent.rc)
    changed, _ = observe(lambda: last_event_at(controld, TARGET) != before or None, 5.0)
    rec.check("db.b_target_columns_change", changed is not None, "QA6-HOOK-TARGET's hook-folded columns change",
              (before, last_event_at(controld, TARGET)))
    hooks.manager.stop(sd_b)
    rec.equal("proc.b_exit_0", 0, sd_b.stop_code)
    rec.equal("logs.b_stop_line", "sessiond stopped: delivered=4 buffered=0 overflowed=0 schema_mismatch=0", sd_b.stop_line)
    rec.check("files.b_socket_removed", not socket_path.exists(), "removed after the stop", socket_path.exists())

    sd_c = hooks.manager.start("SD-C6c", schema=3)
    hooks.manager.wait_socket(sd_c)
    before_c = session_row(controld, TARGET) or {}
    sent = send(hooks.argv, controld.env, frame(captured("S01_startup_tools", "UserPromptSubmit"), session_id=TARGET,
                                                cwd=hooks.target_cwd))
    rec.record("proc.c_dispatch_rc", sent.rc)
    time.sleep(1.0)  # the window in which a relayed frame would have landed (an observation window)
    after_c = session_row(controld, TARGET) or {}
    rec.equal("db.c_no_change", before_c.get("last_event_at"), after_c.get("last_event_at"))
    hooks.manager.stop(sd_c)
    rec.equal("proc.c_exit_0", 0, sd_c.stop_code)
    counts = sd_c.counts()
    rec.check("logs.c_delivered_0_mismatch", counts is not None and counts["delivered"] == 0 and counts["schema_mismatch"] >= 1,
              "delivered=0 and schema_mismatch >= 1", sd_c.stop_line)
    rec.record("logs.c_stop_line", sd_c.stop_line)
    rec.check("files.c_socket_removed", not socket_path.exists(), "removed after the stop", socket_path.exists())
    rec.finish()


# ----- C4 ----------------------------------------------------------------------------


@scenario("C4")
def test_c4_uninstall_replay_recompute_from_the_cli(hooks: Hooks, rec: Recorder) -> None:
    controld = hooks.controld
    if any(run.child.alive() for run in hooks.manager.history) or hooks.manager.socket.exists():
        raise Blocked("a sessiond is still running on the hooks instance; C4 needs none")
    artifact = hooks.run.artifacts / "h1-settings.json"
    if not artifact.exists():
        raise Blocked("H1's artifact is absent (wave 2's unit lane did not run in this run)")
    target = controld.root.root / "hooks" / "c4-settings.json"
    target.write_bytes(artifact.read_bytes())

    def cli(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(paths.SHEPHERD_BIN), *args], env=controld.env, cwd=str(controld.root.cwd),
                              capture_output=True, text=True, timeout=60, check=False)

    dry = cli("uninstall-hooks", "--settings", str(target))
    rec.note(f"uninstall dry: rc={dry.returncode} out={dry.stdout!r} err={dry.stderr!r}")
    rec.equal("proc.uninstall_dry_exit_0", 0, dry.returncode)
    rec.check("proc.uninstall_dry_would_remove", "would remove" in dry.stdout, "'would remove'", dry.stdout[:200])
    rec.equal("logs.uninstall_dry_stderr_empty", "", dry.stderr)
    yes = cli("uninstall-hooks", "--settings", str(target), "--yes")
    rec.note(f"uninstall --yes: rc={yes.returncode} out={yes.stdout!r} err={yes.stderr!r}")
    rec.equal("proc.uninstall_yes_exit_0", 0, yes.returncode)
    rec.check("proc.uninstall_yes_removed", "removed" in yes.stdout and "of our entries" in yes.stdout,
              "'removed N of our entries'", yes.stdout[:200])
    rec.check("files.no_managed_entry_after_yes", "_shepherd_managed" not in target.read_text(encoding="utf-8"),
              "no _shepherd_managed entry", "")
    for label, args in (("replay_since", ("replay", "--since", "2026-09-01")), ("replay_apply", ("replay", "--apply")),
                        ("recompute", ("recompute",))):
        ran = cli(*args)
        rec.note(f"{label}: rc={ran.returncode} out={ran.stdout[:300]!r} err={ran.stderr[:300]!r}")
        rec.equal(f"proc.{label}_exit_0", 0, ran.returncode)
        rec.equal(f"logs.{label}_stderr_empty", "", ran.stderr)
        if label != "replay_apply":
            count = next((line for line in ran.stdout.splitlines() if line.startswith("read ") and " records" in line), "")
            number = int(count.split()[1]) if count.split()[1:2] and count.split()[1].isdigit() else 0
            rec.check(f"proc.{label}_read_n_records", number > 0, "'read N records' with N > 0", count or ran.stdout[:120])
            rec.check(f"proc.{label}_changed_no_column",
                      "this run changed no column. Pass --apply to overwrite them." in ran.stdout,
                      "the no-change sentence", ran.stdout[-200:])
    rec.equal("files.real_settings_sha", paths.EXPECTED_SETTINGS_SHA, hostprobe.sha256(paths.REAL_SETTINGS))
    rec.finish()
