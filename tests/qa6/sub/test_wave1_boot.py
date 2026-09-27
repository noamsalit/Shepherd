"""Wave 1, SUB lane: W1 (ready by four signals), W2 (isolated), W3 (a real browser
renders it live), W4 (SIGTERM stops it cleanly). One instance for the module:
W1 starts it, W2 and W3 use it, W4 stops it (test-plan §4 W1-W4 Cleanup rows).

Each later scenario first re-checks the instance: if W1 never made it ready, W2
to W4 are BLOCKED (not FAIL) — a scenario that could not run has not failed.
"""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.host.mac import MacHost

from .. import hostprobe, paths
from ..browser import BrowserSession, visible_roots
from ..instance import (
    SCAN_INTERVAL_S,
    START_LINE,
    Controld,
    app_state,
    db_connect_ro,
    db_rows,
    last_scan_at,
    schema_version,
    seed_db,
)
from ..pool import InstancePool
from ..sandbox import RunContext, mint_instance
from ..scenario import scenario
from ..sse_rig import Refusal, open_stream
from ..verdict import Blocked, Recorder, await_env, observe

#: W3's live-status bound (test-plan W3 UI row: "within 10 s"); a harness bound,
#: FAIL(bound) only with the page's own /api/events 200 as the same-channel control.
STREAM_LIVE_BOUND_S = 10.0
W4_STOP_LINE = "controld stopped: 3 threads exited · store closed"


class Boot:
    """The module's single instance, and what W1 learned about it."""

    def __init__(self, controld: Controld) -> None:
        self.controld = controld
        self.ready = False

    def require_ready(self) -> Controld:
        if not self.ready:
            raise Blocked("W1 did not bring the instance up; this scenario cannot run on it")
        if not self.controld.child.alive():
            raise Blocked(f"the W1 instance is not running: {self.controld.child.tail()}")
        return self.controld


@pytest.fixture(scope="module")
def boot(qa6_run: RunContext, pool: InstancePool) -> Iterator[Boot]:
    root = mint_instance(qa6_run)
    seed_db(root, runner_socket=qa6_run.runner_socket(root.k))
    controld = pool.start(root)
    yield Boot(controld)


@scenario("W1")
def test_w1_controld_ready_by_four_signals(boot: Boot, qa6_run: RunContext, rec: Recorder) -> None:
    controld = boot.controld
    root = controld.root
    match = controld.start_line(15.0)
    rec.check("logs.start_line", match is not None, "controld: http://127.0.0.1:<port> · <sock> within 15 s",
              controld.child.lines("stdout")[:3])
    if match is None:
        rec.finish()
        return
    rec.check("logs.start_line_while_alive", controld.start_line_while_alive,
              "the line is read while Popen.poll() is None (PYTHONUNBUFFERED)", controld.start_line_while_alive)
    strict = re.fullmatch(r"controld: http://127\.0\.0\.1:(\d+) · (/\S+/controld\.sock)", match.group(0))
    rec.check("logs.start_line_shape", strict is not None, START_LINE.pattern, match.group(0))
    port = int(match.group(1))
    controld.port = port
    controld.socket_path = Path(match.group(2))
    rec.check("logs.port", port not in (0, paths.FORBIDDEN_PORT), "not 0 and not the forbidden port", port)
    sock = controld.socket_path
    # controld.start returns only once the socket is bound (controld.py), so the
    # file must exist the moment the line is printed.
    exists = sock.exists()
    rec.check("files.socket_exists", exists, "exists when the start line is printed", sock)
    if exists:
        rec.equal("files.socket_mode", 0o600, stat.S_IMODE(os.stat(sock).st_mode))
        rec.equal("files.socket_dir_mode", 0o700, stat.S_IMODE(os.stat(sock.parent).st_mode))
    real_sock, real_tmp = os.path.realpath(sock), os.path.realpath(root.tmpdir)
    rec.check("files.socket_under_tmpdir", real_sock.startswith(real_tmp + os.sep),
              f"realpath under {real_tmp}", real_sock)
    product_path = MacHost(environ={"HOME": str(root.home), "TMPDIR": str(root.tmpdir)}).control_socket("controld").path
    rec.equal("files.product_path_is_printed_path", str(product_path), str(sock))
    size = len(str(product_path).encode("utf-8"))
    rec.check("files.socket_budget", size <= 103, "<= 103 bytes", size)

    fleet = controld.client.get("/api/fleet")
    body = fleet.json()
    rec.equal("api.fleet_status", 200, fleet.status)
    rec.equal("api.fleet_ok", True, body.get("ok"))
    data = body.get("data")
    rec.check("api.fleet_discovery", isinstance(data, dict) and "discovery" in data, "data.discovery present",
              sorted(data) if isinstance(data, dict) else data)

    first = await_env(lambda: last_scan_at(controld.db), 5.0, "a first discovery pass")
    first_read = time.monotonic()
    time.sleep(SCAN_INTERVAL_S)  # the two reads must be >= 2.0 s apart (§0 row 1)
    second = last_scan_at(controld.db)
    apart = time.monotonic() - first_read
    if second == first:
        second = await_env(lambda: (v if (v := last_scan_at(controld.db)) != first else None), SCAN_INTERVAL_S * 2,
                           "last_scan_at advancing")
    rec.check("db.last_scan_at_advances", second is not None and second > first and apart >= SCAN_INTERVAL_S,
              "strictly increases across reads >= 2.0 s apart", f"{first} -> {second} ({apart:.2f}s)")
    runner = app_state(controld.db, "runner_socket")
    rec.equal("db.runner_socket", qa6_run.runner_socket(root.k), runner)
    rec.record("db.instance_k", root.k)
    rec.equal("db.schema_version", 4, schema_version(controld.db))

    stream = open_stream("W1", port)
    if isinstance(stream, Refusal):
        rec.check("stream.open", False, "200 and ': open'", stream.status)
    else:
        try:
            await_env(lambda: stream.first_bytes or None, 5.0, "the stream's first bytes")
            rec.check("stream.first_bytes", stream.first_bytes.startswith(b": open"), "': open'", stream.first_bytes[:20])
        finally:
            stream.close()
    boot.ready = not rec.failed and controld.child.alive()
    rec.finish()


@scenario("W2")
def test_w2_instance_is_isolated(boot: Boot, qa6_run: RunContext, rec: Recorder) -> None:
    controld = boot.require_ready()
    root = controld.root
    pid = controld.child.pid
    env = hostprobe.process_env(pid)
    run_root = os.path.realpath(str(qa6_run.instance_root(0)))[: -len("-0")]
    for name in ("HOME", "TMPDIR", "CLAUDE_CONFIG_DIR"):
        value = os.path.realpath(env.get(name, "")) if env.get(name) else ""
        rec.check(f"proc.env.{name}", value.startswith(run_root + "-"), f"under {run_root}-*", env.get(name))
    rec.check("proc.env.no_tmux", "TMUX" not in env, "no TMUX variable", sorted(k for k in env if k.startswith("TMUX")))
    leaked = sorted(name for name in env if name.startswith(("CLAUDECODE", "ANTHROPIC", "AI_AGENT")) or
                    (name.startswith("CLAUDE_") and name != "CLAUDE_CONFIG_DIR"))
    rec.check("proc.env.scrubbed", not leaked, "no CLAUDE*/ANTHROPIC*/AI_AGENT* besides CLAUDE_CONFIG_DIR", leaked)

    names = [name for name in hostprobe.open_files(pid) if name.startswith("/")]
    allowed = (run_root + "-", str(paths.VENV_BIN.parent) + os.sep, str(paths.REPO / "src") + os.sep,
               str(paths.VENV_BIN.parent.resolve()) + os.sep)
    forbidden_roots = (str(paths.REAL_CLAUDE_DIR), str(paths.REAL_SHEPHERD_DATA), os.path.realpath(str(hostprobe.real_tmpdir())))
    offenders: list[str] = []
    outside: list[str] = []
    for name in names:
        real = os.path.realpath(name)
        if real.startswith(forbidden_roots) or name.startswith(forbidden_roots):
            offenders.append(real)
        elif real.startswith(str(paths.REAL_HOME) + os.sep) and not real.startswith(allowed):
            offenders.append(real)
        elif not real.startswith(allowed):
            outside.append(real)
    rec.check("files.lsof_nothing_of_the_user", not offenders,
              "no open file under the real ~/.claude, real Shepherd data, real $TMPDIR, or elsewhere in the real home",
              offenders[:10])
    rec.record("files.lsof_system_paths", sorted(set(outside))[:30])
    rec.check("files.sandbox_db", root.db_path.exists(), "the sandbox shepherd.db exists", root.db_path)

    baseline_path = qa6_run.run_dir / "baseline.json"
    if baseline_path.exists():
        baseline = hostprobe.read_baseline(baseline_path)
        now = hostprobe.snapshot()
        rec.equal("files.real_shepherd_data_unchanged", baseline.get("shepherd_data"), now.shepherd_data)
        rec.equal("files.real_tmpdir_shepherd_unchanged", baseline.get("real_tmpdir_shepherd"), now.real_tmpdir_shepherd)
        start_sessions = baseline.get("claude_sessions")
        start_sessions = start_sessions if isinstance(start_sessions, dict) else {}
        user_pids = hostprobe.user_session_pids(set(start_sessions) | set(now.claude_sessions), run_root + "-")
        changes, attributed = hostprobe.claude_session_changes(start_sessions, now.claude_sessions, user_pids)
        rec.check("files.real_claude_sessions_unchanged", not changes,
                  "no ~/.claude/sessions entry changed, except a live user session's own state file", changes)
        rec.record("files.real_claude_sessions_attributed", attributed)
    else:
        rec.block("files.real_dirs_vs_baseline", "no run baseline.json (standalone run without the runner)")
    workspaces = [str(row["id"]) for row in db_rows(controld.db, "SELECT id FROM workspace ORDER BY id")]
    rec.equal("db.one_workspace", ["unassigned"], workspaces)
    rec.finish()


@scenario("W3")
def test_w3_real_browser_renders_live(boot: Boot, browser_session: BrowserSession, rec: Recorder) -> None:
    controld = boot.require_ready()
    port = controld.port
    with browser_session.context("W3", viewport=(1280, 900)) as (context, log):
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
        page.wait_for_selector("#page-shepherd", state="attached", timeout=10_000)
        roots = visible_roots(page)
        rec.equal("ui.one_root_visible", ["page-shepherd"], roots)
        current = page.locator("#nav-chat").get_attribute("aria-current")
        rec.equal("ui.nav_chat_current", "page", current)

        status = page.locator("#stream-status")

        def is_live() -> bool:
            return status.inner_text().strip() == "live"

        live, elapsed = observe(is_live, STREAM_LIVE_BOUND_S)
        if live:
            rec.check("ui.stream_status_live", True, "live within 10 s", f"live after {elapsed:.2f}s")
        elif 200 in log.status_of("/api/events"):
            # Difference 1(b): the page's own EventSource answered 200 — same channel.
            rec.fail_bound("ui.stream_status_live", "#stream-status reads 'live'", STREAM_LIVE_BOUND_S,
                           f"/api/events answered 200; status reads {status.inner_text().strip()!r}")
        else:
            rec.block("ui.stream_status_live",
                      f"status {status.inner_text().strip()!r} and no 200 for /api/events in the network log")
        approvals = log.requests_to("/api/approvals", "GET")
        rec.equal("api.approvals_read_once", 1, len(approvals))
        static = [(entry.get("url"), entry.get("status")) for entry in log.responses
                  if isinstance(entry.get("url"), str) and "/static/" in str(entry.get("url"))]
        rec.check("api.static_all_200", bool(static) and all(code == 200 for _url, code in static),
                  "every /static/* 200 (and at least one)", [s for s in static if s[1] != 200] or len(static))
        foreign = [entry["url"] for entry in log.requests if not entry["url"].startswith(f"http://127.0.0.1:{port}/")
                   and not entry["url"].startswith("data:")]
        rec.check("api.no_other_origin", not foreign, "no request to any other port or host", foreign[:10])
        events = log.requests_to("/api/events")
        rec.equal("stream.one_eventsource", 1, len(events))
        rec.equal("logs.console_errors", [], log.console_errors())
        rec.equal("logs.page_errors", [], log.page_errors)
        rec.equal("api.master_send_aborts", 0, log.master_send_aborts)
    rec.finish()


@scenario("W4")
def test_w4_sigterm_stops_cleanly(boot: Boot, rec: Recorder) -> None:
    controld = boot.require_ready()
    port = controld.port
    started = time.monotonic()
    code = controld.stop(15.0)
    elapsed = time.monotonic() - started
    rec.equal("proc.exit_code", 0, code)
    rec.check("proc.exit_within_15s", elapsed <= 15.0, "<= 15 s", f"{elapsed:.2f}s")
    rec.equal("logs.stop_line", W4_STOP_LINE, controld.stop_line)
    sock = controld.socket_path
    rec.check("files.socket_gone", sock is not None and not sock.exists(), "controld.sock no longer exists", sock)
    connection = db_connect_ro(controld.db)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    rec.equal("files.db_integrity", "ok", integrity)
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(2.0)
    try:
        probe.connect(("127.0.0.1", port))
        refused = False
    except ConnectionRefusedError:
        refused = True
    finally:
        probe.close()
    rec.check("api.port_refused", refused, "a TCP connect to the port is refused", refused)
    rec.note(json.dumps({"stop_line": controld.stop_line, "elapsed_s": round(elapsed, 3)}))
    rec.finish()
