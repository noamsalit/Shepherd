"""Wave 4, SUB lane: owned sessions on the private tmux socket — O1, T1-T4, O2, O4-O9, O12.

One instance for the module, a project `QA6-O-Alpha` holding the fixture repo
`alpha`, and one SSE subscriber. **O1 runs first** (test-plan §3 intra-wave
order; its record gates every other SHIM-DEPENDENT through the wave-4 stop-if).
O1's session is kept for T1 and T3 (the plan: "kept for T1/T4/O5-O8"); T4, O5,
O7 and O8 spawn their own, because T4 and O5 each end the session they act on
and O7/O8 need a pristine prompt-ready pane (T1/T3 type into O1's).

Every "no frame" clause is read against `run_control` on the same stream; every
harness time bound is Difference 1's (`bounded`): FAIL(bound) only when a
same-channel control measured in the same scenario qualifies it, else BLOCKED.

Mutation PP-7 (`w4_PP7-O1-unlogged-tmux`): the module's instance is started
with the **real** tmux ahead of the logging shim on `PATH`. Spawning still
works (the fake `claude` still resolves), but the shim sees no argv, and O1's
`tmux.argv` clause must go false — the proof that the clause reads what the
product ran rather than passing on an empty log.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

from shepherd.core.runner import TMUX_COMMAND_LIMIT_B, RunnerRefusal, SessionSpec, command_size
from shepherd.engines.claude_code.spawn import spawn_argv
from shepherd.runner.local import DEFAULT_COLS, DEFAULT_ROWS

from .. import hostprobe, paths, wsclient
from ..httpclient import CORRELATION_ID, ENVELOPE_KEYS, as_dict, as_list, generic_error_problems
from ..instance import Controld, db_rows, last_scan_at, seed_db
from ..mutations import active
from ..pool import InstancePool
from ..sandbox import RunContext, mint_instance, sandbox_env
from ..scenario import scenario
from ..sse_rig import run_control
from ..verdict import Blocked, Recorder, await_env, observe
from .test_wave4_0_support import (
    Attached,
    Owned,
    WsTap,
    app_state_rows,
    argvs_naming,
    attached,
    await_attach,
    await_frame,
    bounded,
    capture,
    capture_latency,
    claude_argvs,
    end_attached,
    fleet_anomaly,
    frames,
    kill,
    open_owned,
    owned_panes,
    pane_alive,
    pane_pid,
    post_json,
    send_keys,
    session_count,
    session_db_row,
    socket_ok,
    spawn,
    spawn_ok,
    tmux_argvs,
    tmux_name,
)

MUT_PP7 = "w4_PP7-O1-unlogged-tmux"
UNKNOWN_SESSION = "01M3QA6NOSUCHSESSION000000"
FOREIGN_ORIGIN = "http://qa6-foreign.example"
SPAWNED_KEYS = frozenset({"cwd", "engine_session_id", "state", "detail", "exit_code", "pane_kind", "trusted",
                          "trust_source"})
#: T3/O7: "within 3 s" (plan); T4 "within 5 s"; T1 has no stated bound, so 10 s.
T3_BOUND_S, O7_BOUND_S, T4_BOUND_S, T1_BOUND_S = 3.0, 3.0, 5.0, 10.0


@dataclass
class Mod:
    env: Owned
    shared: dict[str, str] = field(default_factory=dict)
    attached_one: Attached | None = None

    def attached(self) -> Attached:
        """One D1-shaped attached session for T2, O6, O9 (lazily; a harness-shaped input)."""
        if self.attached_one is None:
            self.attached_one = attached(self.env, self.env.run.repos / "loose", "QA6 O-attached")
        return self.attached_one

    def o1_session(self) -> str:
        """O1's session (the plan's Given), or a fresh one if O1 produced none in this process."""
        found = self.shared.get("o1")
        if found is not None and pane_alive(self.env, found):
            return found
        made = spawn_ok(self.env, "QA6 one (standalone)", "hello")
        self.shared["o1"] = made
        return made


def ready_with_path(pool: InstancePool, run: RunContext, path: str) -> Controld:
    """`pool.ready()` with an explicit PATH (the PP-7 mutation's one input)."""
    root = mint_instance(run)
    seed_db(root, runner_socket=run.runner_socket(root.k))
    child_env = sandbox_env(run, root, path_mode="shims")
    child_env["PATH"] = path
    controld = pool.start(root, env=child_env)
    try:
        controld.wait_ready()
    except Blocked:
        controld.stop()
        raise
    return controld


@pytest.fixture(scope="module")
def mod(pool: InstancePool, qa6_run: RunContext) -> Iterator[Mod]:
    controld: Controld | None = None
    notes: list[str] = []
    if active(MUT_PP7):
        path = ":".join([str(paths.VENV_BIN), str(paths.TMUX_BIN.parent), str(qa6_run.shims), "/usr/bin", "/bin"])
        controld = ready_with_path(pool, qa6_run, path)
        notes.append(f"QA6 MUTATION {MUT_PP7} APPLIED: controld PATH={path} (real tmux before the logging shim)")
    env = open_owned(pool, qa6_run, "O", controld=controld)
    env.notes.extend(notes)
    state = Mod(env=env)
    try:
        yield state
    finally:
        if state.attached_one is not None:
            end_attached(env, state.attached_one)
        env.stream.close()


def envelope_problems(body: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if set(body) != ENVELOPE_KEYS:
        problems.append(f"keys {sorted(body)}")
    if body.get("ok") is not True:
        problems.append(f"ok={body.get('ok')!r}")
    correlation = body.get("correlation_id")
    if not (isinstance(correlation, str) and CORRELATION_ID.match(correlation)):
        problems.append(f"correlation_id={correlation!r}")
    return problems


# ----- O1 ------------------------------------------------------------------------------


@scenario("O1")
def test_o1_spawn_an_owned_session_in_a_registered_repo(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    for note in env.notes:
        rec.note(note)
    run = env.run
    mark, amark = env.stream.mark(), env.audit.mark()
    tmark, cmark = len(tmux_argvs(run)), len(claude_argvs(run))
    unreadable_before = fleet_anomaly(env.client, "pane_unreadable")
    made = spawn(env, title="QA6 one", brief="hello")
    rec.record("api.spawn_latency_s", round(made.latency_s, 3))
    sid = made.session_id
    rec.check("api.spawned", made.status == 200 and made.spawned and sid is not None,
              "HTTP 200 {spawned:true, session_id}", (made.status, made.data))
    rec.check("api.not_the_60s_needs_you", made.data.get("state") != "needs_you"
              and "unreadable after" not in str(made.data.get("detail")),
              "not state needs_you / 'pane state unreadable after 60s' (spawn.py:143-149)", made.data)
    if sid is None:
        rec.finish()
        return
    mod.shared["o1"] = sid
    for suffix in ("", "/subagents", "/output", "/decision"):
        response = env.client.get(f"/api/sessions/{sid}{suffix}")
        body = response.json() if response.status == 200 else {}
        problems = envelope_problems(body) if response.status == 200 else [f"status {response.status}"]
        rec.check(f"api.get{suffix or '/'}envelope", not problems, "200, the A1 envelope, ok", problems or "ok")
    row = session_db_row(env, sid) or {}
    rec.equal("db.ownership", "owned", row.get("ownership"))
    rec.equal("db.origin", "user_ui", row.get("origin"))
    rec.equal("db.state", "starting", row.get("state"))
    rec.check("db.runner_handle_names_socket", env.socket in str(row.get("runner_handle")),
              f"runner_handle naming {env.socket}", row.get("runner_handle"))
    rec.equal("db.no_pane_unreadable", unreadable_before, fleet_anomaly(env.client, "pane_unreadable"))
    rec.check("tmux.pane_on_runner_socket", pane_alive(env, sid), f"{tmux_name(sid)} on -L {env.socket}",
              owned_panes(env))
    engine = str(row.get("engine_session_id"))
    shim = [argv for argv in claude_argvs(run)[cmark:] if engine in argv]
    rec.check("tmux.shim_argv_session_id", any(argv[argv.index("--session-id") + 1] == engine
                                               for argv in shim if "--session-id" in argv[:-1]),
              f"the shim's argv carries --session-id {engine}", shim)
    rec.check("tmux.shim_argv_ends_with_brief", any(argv[-2:] == ["--", "hello"] for argv in shim),
              "the shim's argv ends with `-- hello`", shim)
    news = argvs_naming(tmux_argvs(run)[tmark:], "new-session", tmux_name(sid))
    rec.check("tmux.argv", bool(news) and all(socket_ok(argv, env.socket) for argv in news),
              f"a logged new-session argv for {tmux_name(sid)} with argv[1..2] = -L {env.socket}", news[:2])
    frame = await_frame(env.stream, mark, "session.spawned", sid, 5.0)
    rec.check("stream.spawned_keys", frame is not None and set(frame.data) == SPAWNED_KEYS,
              sorted(SPAWNED_KEYS), sorted(frame.data) if frame else None)
    rec.check("stream.pane_kind_prompt_ready", frame is not None and str(frame.data.get("pane_kind")).upper()
              == "PROMPT_READY", "pane_kind PROMPT_READY", frame.data.get("pane_kind") if frame else None)
    rows = env.audit.records_for(amark, "spawn_session")
    rec.check("logs.spawn_audit", len(rows) == 1 and rows[0].get("decision") == "allow"
              and rows[0].get("approved_by") == "policy", "one spawn_session row, allow, approved_by policy",
              [{k: r.get(k) for k in ("decision", "approved_by", "result")} for r in rows])
    rec.finish()


# ----- T1 ------------------------------------------------------------------------------


@scenario("T1")
def test_t1_terminal_stream_snapshot_then_live_chunks(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    sid = mod.o1_session()
    amark, tmark = env.audit.mark(), len(tmux_argvs(env.run))
    started = time.monotonic()
    tap = WsTap(env.controld.port, f"/api/sessions/{sid}/terminal")
    try:
        rec.equal("api.101", 101, tap.status)
        first_latency = tap.wait(lambda: bool(tap.snapshot()), 5.0)
        snapshot = tap.snapshot()
        first = snapshot[0] if snapshot else None
        rec.check("stream.first_frame_has_marker", first is not None and first.opcode == wsclient.OP_BINARY
                  and b"QA6-FAKE-CLAUDE" in first.payload, "the first binary frame contains QA6-FAKE-CLAUDE",
                  first.payload[:120] if first else None)
        if first is None:
            rec.finish()
            return
        control = max(first.at - started, 1e-3)
        rec.record("stream.first_frame_latency_s", round(first_latency or -1.0, 3))
        await_attach(env.run, sid, tmark)
        count = len(tap.snapshot())
        send_keys(env, sid, "QA6-ECHO", "Enter")
        seen = tap.wait(lambda: "QA6-ECHO" in tap.binary_text(count), T1_BOUND_S)
        mod.shared["ws_echo_latency"] = f"{seen}" if seen is not None else ""
        bounded(rec, "stream.later_frame_has_echo", seen is not None, "a later WS frame containing QA6-ECHO",
                T1_BOUND_S, control, "the snapshot frame after the upgrade", tap.binary_text(count)[-200:])
        rec.check("tmux.capture_has_echo", "QA6-ECHO" in capture(env, sid), "capture-pane -p shows QA6-ECHO",
                  capture(env, sid)[-300:])
        rows = env.audit.records_for(amark, "terminal_stream")
        rec.check("logs.terminal_stream_row", len(rows) == 1 and rows[0].get("decision") == "allow"
                  and rows[0].get("result") == "ok", "one terminal_stream read row (allow, ok)",
                  [{k: r.get(k) for k in ("decision", "result", "blast_class")} for r in rows])
    finally:
        tap.close()
    rec.finish()


# ----- T2 ------------------------------------------------------------------------------


@scenario("T2")
def test_t2_terminal_refusals_happen_before_the_upgrade(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    other = mod.attached()
    cases = [
        ("foreign_origin", mod.o1_session(), FOREIGN_ORIGIN, 403, 0),
        ("no_origin", mod.o1_session(), wsclient.NO_ORIGIN, 403, 0),
        ("attached_id", other.session_id, None, 404, 1),
        ("unknown_id", UNKNOWN_SESSION, None, 404, 1),
    ]
    for name, target, origin, status, rows_expected in cases:
        amark = env.audit.mark()
        answer = wsclient.upgrade(env.controld.port, f"/api/sessions/{target}/terminal", origin=origin,
                                  want_frames=1, read_timeout=5.0)
        rec.equal(f"api.{name}_status", status, answer.status)
        rec.check(f"api.{name}_no_upgrade_no_frame", answer.status != 101 and answer.frames == [],
                  "no 101, no frame", (answer.status, len(answer.frames)))
        rows = env.audit.records_for(amark, "terminal_stream")
        shaped = all(r.get("decision") == "allow" and r.get("result") == "ok" for r in rows)
        rec.check(f"logs.{name}_terminal_stream_rows", len(rows) == rows_expected and shaped,
                  f"{rows_expected} terminal_stream row(s)" + (" (allow, ok)" if rows_expected else ""),
                  [{k: r.get(k) for k in ("decision", "result")} for r in rows])
    rec.finish()


# ----- T3 ------------------------------------------------------------------------------


@scenario("T3")
def test_t3_keystrokes_typed_into_the_terminal_reach_the_pane(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    # Its own pane, never attached before: a second `pipe-pane -o` on a pane whose
    # earlier stream the server has not yet noticed closing *toggles the pipe off*
    # (measured while building this module on O1's pane after T1), which would make
    # the echo clause about re-attach rather than about keystrokes.
    sid = spawn_ok(env, "QA6 T3")
    tmark = len(tmux_argvs(env.run))
    tap = WsTap(env.controld.port, f"/api/sessions/{sid}/terminal")
    try:
        rec.equal("given.101", 101, tap.status)
        if tap.wait(lambda: bool(tap.snapshot()), 5.0) is None:
            raise Blocked("T3: no snapshot frame after the upgrade")
        await_attach(env.run, sid, tmark)
        count = len(tap.snapshot())
        tap.send(wsclient.mask_frame(wsclient.OP_TEXT, b"QA6-INJECT\r"))
        tap.send(wsclient.mask_frame(wsclient.OP_BINARY, b"QA6-INJECT\r"))
        in_pane, _ = observe(lambda: "QA6-INJECT" in capture(env, sid) or None, T3_BOUND_S)
        in_stream = "QA6-INJECT" in tap.binary_text(count)
        # The positive controls, after the window: one harness keystroke burst,
        # timed on both channels the two clauses read (capture-pane, the WS).
        ws_mark, sent_at = len(tap.snapshot()), time.monotonic()
        pane_control = capture_latency(env, sid, "QA6-T3-CTRL")
        ws_control = ws_latency(tap, ws_mark, "QA6-T3-CTRL", sent_at, T1_BOUND_S)
        bounded(rec, "tmux.inject_reaches_pane", bool(in_pane), "QA6-INJECT in capture-pane", T3_BOUND_S,
                pane_control, "harness send-keys seen by capture-pane", capture(env, sid)[-200:])
        bounded(rec, "stream.echo_in_later_frame", in_stream, "the QA6-INJECT echo in a later WS frame", T3_BOUND_S,
                ws_control, "harness keystrokes seen on the WS", tap.binary_text(count)[-200:])
    finally:
        tap.close()
    kill(env, sid)
    rec.finish()


def ws_latency(tap: WsTap, mark: int, marker: str, sent_at: float, bound_s: float) -> float | None:
    """Seconds from `sent_at` to the first WS frame after `mark` that carries `marker`."""
    if tap.wait(lambda: marker in tap.binary_text(mark), bound_s) is None:
        return None
    text, arrived = "", sent_at
    for frame in tap.snapshot()[mark:]:
        text += frame.payload.decode("utf-8", "replace")
        if marker in text:
            arrived = frame.at
            break
    return max(arrived - sent_at, 1e-3)


# ----- T4 ------------------------------------------------------------------------------


@scenario("T4")
def test_t4_a_dying_pane_closes_the_stream_normally(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    sid = spawn_ok(env, "QA6 T4")
    tmark, amark, mark = len(tmux_argvs(env.run)), env.audit.mark(), env.stream.mark()
    tap = WsTap(env.controld.port, f"/api/sessions/{sid}/terminal")
    try:
        rec.equal("given.101", 101, tap.status)
        if tap.wait(lambda: bool(tap.snapshot()), 5.0) is None:
            raise Blocked("T4: no snapshot frame after the upgrade")
        await_attach(env.run, sid, tmark)
        count, sent_at = len(tap.snapshot()), time.monotonic()
        send_keys(env, sid, "QA6-T4-CTRL", "Enter")
        control = ws_latency(tap, count, "QA6-T4-CTRL", sent_at, T1_BOUND_S)
        before_kill = len(tap.snapshot())
        answer = kill(env, sid)
        data = answer.data() if answer.status == 200 else {}
        rec.equal("api.killed", True, data.get("killed"))
        closed = tap.wait(lambda: tap.close_code() is not None or tap.eof, T4_BOUND_S)
        bounded(rec, "stream.close_1000", closed is not None and tap.close_code() == 1000,
                "a close frame with code 1000", T4_BOUND_S, control, "harness keystrokes seen on the WS",
                {"close_code": tap.close_code(), "eof": tap.eof, "frames": len(tap.snapshot())})
        rec.record("stream.final_chunks", len([f for f in tap.snapshot()[before_kill:] if f.opcode == wsclient.OP_BINARY]))
        gone, _ = observe(lambda: (not pane_alive(env, sid)) or None, 5.0)
        rec.check("tmux.pane_gone", bool(gone), "the pane is gone", owned_panes(env))
        row = session_db_row(env, sid) or {}
        rec.check("db.as_o5", row.get("ended_at") is not None and row.get("stop_reason") == "killed"
                  and row.get("outcome") == "unfinished", "ended_at set, killed, unfinished",
                  {k: row.get(k) for k in ("ended_at", "stop_reason", "outcome")})
        rows = env.audit.records_for(amark, "kill_session")
        rec.check("logs.as_o5", len(rows) == 1 and rows[0].get("approved_by") == "claimed_human",
                  "kill_session, claimed_human", [r.get("approved_by") for r in rows])
        rec.check("stream.session_killed", bool(frames(env.stream, mark, "session.killed", sid)),
                  "session.killed", [f.kind for f in env.stream.since(mark)])
    finally:
        tap.close()
    rec.finish()


# ----- O2 ------------------------------------------------------------------------------


@scenario("O2")
def test_o2_admission_refuses_paths_outside_the_allowlist(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    link = env.alpha / "qa6-o2-link-out"
    if not link.is_symlink():
        os.symlink(env.run.artifacts, link)
    empty = str(as_dict(env.client.create_project("QA6-O2-empty").get("project")).get("project_id"))
    cases: list[tuple[str, dict[str, str]]] = [
        ("outside_tmp", {"cwd": "/tmp/qa6-outside"}),
        ("dotdot_beta", {"cwd": f"{env.alpha}/../beta"}),
        ("symlink_out", {"cwd": str(link)}),
        ("unknown_workspace", {"workspace_id": "01M3QA6NOSUCHPROJECT000000"}),
        ("project_no_repos", {"workspace_id": empty}),
        ("nul_byte", {"cwd": f"{env.alpha}/a\x00b"}),
    ]
    panes, count = owned_panes(env), session_count(env)
    mark, amark = env.stream.mark(), env.audit.mark()
    try:
        for name, override in cases:
            made = spawn(env, title=f"QA6 O2 {name}", **override)
            rec.check(f"api.{name}_refused", made.status == 200 and made.data.get("spawned") is False
                      and bool(made.data.get("refusal")) and made.data.get("cap") is None,
                      "{spawned:false, refusal:<non-empty>, cap:null}", (made.status, made.data))
    finally:
        link.unlink()
    rec.equal("tmux.panes_unchanged", panes, owned_panes(env))
    rec.equal("db.session_count_unchanged", count, session_count(env))
    rows = env.audit.records_for(amark, "spawn_session")
    rec.equal("logs.one_row_each", len(cases), len(rows))
    control = run_control(env.stream, env.client, "O2", mark)
    rec.equal("stream.no_session_spawned", [], [f.kind for f in control.interior if f.kind == "session.spawned"])
    env.client.delete_project(empty)
    rec.finish()


# ----- O4 ------------------------------------------------------------------------------


def brief_over_limit(env: Owned, over: int) -> str:
    """A brief sized from `TMUX_COMMAND_LIMIT_B` so the command is `over` bytes past it.

    The size is computed with the product's own pure `command_size`/`spawn_argv`
    (no process is started), over the exact words `LocalRunner.start` prepends,
    so the arithmetic is the product's: the `spawn_argv` check below proves the
    brief is refused by exactly the named margin and admitted one byte shorter.
    """
    binary = os.path.realpath(env.run.shims / "claude")
    prefix = ["new-session", "-d", "-s", tmux_name("0" * 26), "-c", str(env.alpha),
              "-x", str(DEFAULT_COLS), "-y", str(DEFAULT_ROWS)]
    frame = command_size(prefix) + 1
    base = command_size([binary, "--session-id", "0" * 36, "--", ""]) + frame
    length = TMUX_COMMAND_LIMIT_B + over - base

    def spec(brief: str) -> SessionSpec:
        return SessionSpec(session_id="0" * 26, engine_session_id="0" * 36, cwd=str(env.alpha), brief=brief,
                           title=None, model=None, effort=None, engine="claude_code", runner="unknown", env={})

    try:
        spawn_argv(spec("x" * (length - over)), binary, frame_bytes=frame)
    except RunnerRefusal as refusal:
        raise Blocked(f"O4 sizing: a brief at the limit is already refused: {refusal.reason}") from refusal
    try:
        spawn_argv(spec("x" * length), binary, frame_bytes=frame)
    except RunnerRefusal:
        return "x" * length
    raise Blocked("O4 sizing: the over-limit brief is not refused by the product's own spawn_argv")


@scenario("O4")
def test_o4_a_spawn_the_runner_refuses_leaves_no_session_behind(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    brief = brief_over_limit(env, 1)
    rec.record("given.brief_bytes", len(brief))
    before_rows = {str(r["id"]) for r in db_rows(env.controld.db, "SELECT id FROM session")}
    before_count = env.client.fleet().get("session_count")
    panes = owned_panes(env)
    mark = env.stream.mark()
    made = spawn(env, brief=brief)
    refusal = str(made.data.get("refusal") or "")
    rec.check("api.refused_naming_bytes", made.data.get("spawned") is False
              and str(TMUX_COMMAND_LIMIT_B + 1) in refusal and str(TMUX_COMMAND_LIMIT_B) in refusal,
              f"spawned:false, the refusal naming {TMUX_COMMAND_LIMIT_B + 1} and {TMUX_COMMAND_LIMIT_B} bytes",
              (made.status, {k: v for k, v in made.data.items() if k != "refusal"}, refusal[:300]))
    after_rows = {str(r["id"]) for r in db_rows(env.controld.db, "SELECT id FROM session")}
    rec.equal("db.no_new_session_row", [], sorted(after_rows - before_rows))
    rec.equal("api.session_count_unchanged", before_count, env.client.fleet().get("session_count"))
    rec.equal("tmux.no_new_pane", panes, owned_panes(env))
    control = run_control(env.stream, env.client, "O4", mark)
    rec.equal("stream.no_session_spawned", [], [f.kind for f in control.interior if f.kind == "session.spawned"])
    rec.finish()


# ----- O5 ------------------------------------------------------------------------------


@scenario("O5")
def test_o5_kill_an_owned_session(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    sid = spawn_ok(env, "QA6 O5")
    mark, amark, tmark = env.stream.mark(), env.audit.mark(), len(tmux_argvs(env.run))
    answer = kill(env, sid)
    data = answer.data() if answer.status == 200 else {}
    rec.check("api.killed", data.get("killed") is True and {"exit_code", "exit_signal", "observed_at"} <= set(data),
              "{killed:true, exit_code, exit_signal, observed_at}", (answer.status, data))
    gone, _ = observe(lambda: (not pane_alive(env, sid)) or None, 5.0)
    rec.check("tmux.pane_gone", bool(gone), "the pane is gone", owned_panes(env))
    kills = argvs_naming(tmux_argvs(env.run)[tmark:], "kill-session")
    ours = [argv for argv in kills if tmuxctl_target(sid) in argv]
    rec.check("tmux.argv", bool(ours) and all(socket_ok(argv, env.socket) for argv in kills),
              f"the kill-session argv with -L {env.socket}", kills[:3])
    row = session_db_row(env, sid) or {}
    rec.check("db.ended_killed_unfinished", row.get("ended_at") is not None and row.get("stop_reason") == "killed"
              and row.get("outcome") == "unfinished", "ended_at set; verdict killed; bucket unfinished",
              {k: row.get(k) for k in ("ended_at", "stop_reason", "outcome")})
    records = {key: value for key, value in app_state_rows(env).items() if sid in key}
    live = {key: value for key, value in records.items() if json.loads(str(value)) is not None}
    rec.check("db.no_kill_record_remains", not live, "no app_state kill record for the session remains (null or absent)",
              records)
    frame = await_frame(env.stream, mark, "session.killed", sid, 5.0)
    rec.check("stream.session_killed", frame is not None, "session.killed", [f.kind for f in env.stream.since(mark)])
    rows = env.audit.records_for(amark, "kill_session")
    rec.check("logs.kill_claimed_human", len(rows) == 1 and rows[0].get("decision") == "allow"
              and rows[0].get("approved_by") == "claimed_human", "kill_session, allow, claimed_human",
              [{k: r.get(k) for k in ("decision", "approved_by")} for r in rows])
    mod.shared["o5_killed"] = sid
    rec.finish()


def tmuxctl_target(session_id: str) -> str:
    return f"={tmux_name(session_id)}:"


# ----- O6 ------------------------------------------------------------------------------


def watched(env: Owned, ids: list[str]) -> dict[str, object]:
    """The DB state O6 must not change: the targets' rows and any app_state key naming them."""
    snapshot: dict[str, object] = {}
    for sid in ids:
        row = session_db_row(env, sid)
        snapshot[sid] = None if row is None else {k: row.get(k) for k in ("state", "ended_at", "stop_reason", "outcome")}
    snapshot["app_state"] = {k: v for k, v in app_state_rows(env).items() if any(sid in k for sid in ids)}
    return snapshot


@scenario("O6")
def test_o6_kill_refusals(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    other = mod.attached()
    dead = mod.shared.get("o5_killed")
    if dead is None:
        dead = spawn_ok(env, "QA6 O6 already-killed")
        if kill(env, dead).status != 200:
            raise Blocked("O6 given: the first kill of the already-killed target did not answer 200")
    targets = [("attached", other.session_id), ("unknown", UNKNOWN_SESSION), ("already_killed", dead)]
    panes = owned_panes(env)
    before = watched(env, [sid for _n, sid in targets])
    mark, amark = env.stream.mark(), env.audit.mark()
    for name, sid in targets:
        row_mark = env.audit.mark()
        answer = kill(env, sid)
        rows = env.audit.records_for(row_mark, "kill_session")
        if answer.status == 200:
            data = answer.data()
            refused = data.get("killed") is not True and data.get("ok") is False and bool(data.get("reason"))
            shape = data
        else:
            refused = not generic_error_problems(answer, 400) and bool(rows) and rows[-1].get("result") == "refused"
            shape = {"status": answer.status, "audit_result": rows[-1].get("result") if rows else None}
        rec.check(f"api.{name}_refused", refused,
                  "refused: 200 {ok:false, reason (no_pane / not found)} or a 400 audited result refused; killed not true",
                  shape)
    rec.equal("tmux.other_panes_unchanged", panes, owned_panes(env))
    rec.equal("db.no_state_change", before, watched(env, [sid for _n, sid in targets]))
    rec.equal("logs.one_row_each", len(targets), len(env.audit.records_for(amark, "kill_session")))
    control = run_control(env.stream, env.client, "O6", mark)
    rec.equal("stream.no_session_killed", [], [f.session_id for f in control.interior if f.kind == "session.killed"])
    rec.finish()


# ----- O7 ------------------------------------------------------------------------------


@scenario("O7")
def test_o7_interrupt_delivers_escape_to_the_pane(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    mode = env.root.home / ".qa6-shim-mode"
    mode.write_text("catv", encoding="utf-8")
    try:
        sid = spawn_ok(env, "QA6 O7 catv")
    finally:
        mode.unlink()
    control = capture_latency(env, sid, "QA6-O7-CTRL")
    send_keys(env, sid, "Enter")
    mark, amark = env.stream.mark(), env.audit.mark()
    answer = post_json(env.client, f"/api/sessions/{sid}/interrupt", {})
    data = answer.data() if answer.status == 200 else {}
    rec.check("api.200_interrupted", answer.status == 200 and data.get("interrupted") is True,
              "200 {interrupted:true}", (answer.status, data))
    seen, _ = observe(lambda: "^[" in capture(env, sid) or None, O7_BOUND_S)
    bounded(rec, "tmux.escape_shown", bool(seen), "capture-pane -p shows ^[", O7_BOUND_S, control,
            "harness send-keys seen by capture-pane", capture(env, sid)[-200:])
    frame = await_frame(env.stream, mark, "session.interrupted", sid, 5.0)
    rec.check("stream.session_interrupted", frame is not None, "session.interrupted",
              [f.kind for f in env.stream.since(mark)])
    rows = env.audit.records_for(amark, "interrupt_session")
    rec.check("logs.interrupt_claimed_human", len(rows) == 1 and rows[0].get("approved_by") == "claimed_human",
              "interrupt_session, claimed_human", [r.get("approved_by") for r in rows])
    row = session_db_row(env, sid) or {}
    rec.check("db.nothing_else", row.get("ended_at") is None and pane_alive(env, sid),
              "the session is not ended and its pane lives", {k: row.get(k) for k in ("state", "ended_at")})
    kill(env, sid)
    rec.finish()


# ----- O8 ------------------------------------------------------------------------------


def mailbox_rows(env: Owned, sid: str) -> list[dict[str, object]]:
    return db_rows(env.controld.db, "SELECT idempotency_key, origin, delivered_at, last_refusal FROM mailbox_message "
                                    "WHERE session_id = ? ORDER BY queued_at", (sid,))


@scenario("O8")
def test_o8_the_mailbox_is_idempotent_and_validates_the_origin_label(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    sid = spawn_ok(env, "QA6 O8")
    amark = env.audit.mark()
    path = f"/api/sessions/{sid}/send"
    first = post_json(env.client, path, {"body": "QA6 MSG", "idempotency_key": "k1"})
    again = post_json(env.client, path, {"body": "QA6 MSG", "idempotency_key": "k1"})
    one = first.data() if first.status == 200 else {}
    two = again.data() if again.status == 200 else {}
    rec.check("api.k1_same_message_id", one.get("message_id") is not None and one.get("message_id") == two.get("message_id"),
              "the two k1 calls return the same message_id", (one.get("message_id"), two.get("message_id")))
    delivered = one.get("delivered")
    rec.check("api.k1_send_now_delivered", str(one.get("decision")).upper() == "SEND_NOW"
              and (delivered is True or (isinstance(delivered, int) and delivered >= 1)),
              "decision SEND_NOW, delivered (true / a count >= 1)", one)
    martian_mark = env.audit.mark()
    martian = post_json(env.client, path, {"body": "x", "idempotency_key": "k2", "origin": "martian"})
    martian_rows = env.audit.records_for(martian_mark, "send_to_session")
    rec.check("api.martian_400_refused", not generic_error_problems(martian, 400)
              and [r.get("result") for r in martian_rows] == ["refused"],
              "400 generic; audit result refused", (martian.status, [r.get("result") for r in martian_rows]))
    third = post_json(env.client, path, {"body": "y", "idempotency_key": "k3"})
    k3 = third.data() if third.status == 200 else {}
    rec.record("api.k3_decision", {k: k3.get(k) for k in ("decision", "reason", "delivered", "deferred")})
    first_scan = last_scan_at(env.controld.db)
    await_env(lambda: (v if (v := last_scan_at(env.controld.db)) and first_scan and v > first_scan else None), 8.0,
              "one discovery pass after the sends")
    second_scan = last_scan_at(env.controld.db)
    await_env(lambda: (v if (v := last_scan_at(env.controld.db)) and second_scan and v > second_scan else None), 8.0,
              "a second discovery pass (two mailbox sweeps)")
    rec.check("tmux.capture_has_msg", "QA6 MSG" in capture(env, sid), "capture-pane -p shows QA6 MSG",
              capture(env, sid)[-300:])
    rows = mailbox_rows(env, sid)
    keys = [str(r["idempotency_key"]) for r in rows]
    rec.check("db.mailbox_table_k1_once_k3_once", keys.count("k1") == 1 and keys.count("k3") == 1 and "k2" not in keys,
              "mailbox_message rows: k1 once, k3 once, no k2", keys)
    k3_rows = [r for r in rows if r["idempotency_key"] == "k3"]
    rec.check("db.k3_origin_user_ui", bool(k3_rows) and k3_rows[0].get("origin") == "user_ui", "k3 origin user_ui",
              k3_rows)
    listing = env.client.get(f"/api/mailbox?session_id={sid}").data()
    listed = [as_dict(m).get("id") for m in as_list(listing.get("messages"))]
    rec.check("api.mailbox_lists_k1_once_and_k3_once", listed.count(one.get("message_id")) == 1
              and listed.count(k3.get("message_id")) == 1,
              "GET /api/mailbox?session_id= lists k1 once and k3 once", listing)
    sends = env.audit.records_for(amark, "send_to_session")
    args = [as_dict(r.get("args")).get("idempotency_key") for r in sends]
    rec.check("logs.idempotency_key_recorded", len(sends) == 4 and all(a is not None for a in args),
              "four send_to_session rows, each recording an idempotency_key argument", args)
    rec.record("logs.idempotency_key_values", args)
    kill(env, sid)
    rec.finish()


# ----- O9 ------------------------------------------------------------------------------


@scenario("O9")
def test_o9_the_mailbox_refuses_sessions_it_cannot_own(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    other = mod.attached()
    mark, amark = env.stream.mark(), env.audit.mark()
    for name, sid in (("attached", other.session_id), ("unknown", UNKNOWN_SESSION)):
        answer = post_json(env.client, f"/api/sessions/{sid}/send", {"body": "QA6 O9", "idempotency_key": f"o9-{name}"})
        data = answer.data() if answer.status == 200 else {}
        rec.check(f"api.{name}_not_queued", answer.status == 200 and data.get("queued") is False and bool(data.get("reason")),
                  "{queued:false} with a reason", (answer.status, data))
        rec.equal(f"db.{name}_no_mailbox_row", [], mailbox_rows(env, sid))
    rec.equal("logs.one_row_each", 2, len(env.audit.records_for(amark, "send_to_session")))
    control = run_control(env.stream, env.client, "O9", mark)
    rec.equal("stream.nothing_else", [], [f.kind for f in control.interior])
    rec.finish()


# ----- O12 -----------------------------------------------------------------------------


def names_shepherd_channel(env: Owned, argv: list[str], environ: dict[str, str]) -> list[str]:
    """Any channel from a session to the tool surface: an MCP config or a named endpoint."""
    found: list[str] = []
    for index, word in enumerate(argv):
        if word == "--mcp-config" and index + 1 < len(argv) and "shepherd" in argv[index + 1].lower():
            found.append(f"argv --mcp-config {argv[index + 1]}")
    endpoints = (str(env.root.controld_socket), str(env.root.sessiond_socket), f"127.0.0.1:{env.controld.port}")
    for name, value in environ.items():
        if "SHEPHERD" in name.upper() or any(point in value for point in endpoints):
            found.append(f"env {name}={value[:120]}")
    return found


@scenario("O12")
def test_o12_no_path_exists_by_which_a_session_can_call_a_shepherd_tool(mod: Mod, rec: Recorder) -> None:
    env = mod.env
    sid = mod.o1_session()
    row = session_db_row(env, sid) or {}
    engine = str(row.get("engine_session_id"))
    argvs = [argv for argv in claude_argvs(env.run) if engine in argv]
    pid = pane_pid(env, sid)
    if not argvs or pid is None:
        raise Blocked(f"O12 given: no shim argv for {engine} ({len(argvs)}) or no pane pid ({pid})")
    environ = hostprobe.process_env(pid)
    rec.record("proc.pane_env_names", sorted(environ))
    channels = names_shepherd_channel(env, argvs[-1], environ)
    rec.check("proc.session_has_tool_channel", bool(channels),
              "an --mcp-config naming a Shepherd server, or an env var naming a Shepherd socket/endpoint",
              {"argv": argvs[-1], "channels": channels})
    kinds = sorted({str(r.get("actor_kind")) for r in env.audit.records()})
    rec.check("api.every_http_row_stamps_human", kinds == ["human"], "every HTTP audit row actor_kind human", kinds)
    rec.finish()
