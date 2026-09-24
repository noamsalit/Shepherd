#!/usr/bin/env python3
"""The qa6 run entry: preflight → baseline → guards → waves in order → teardown → report.

    .venv/bin/python tests/qa6/run.py                 # every wave
    .venv/bin/python tests/qa6/run.py --preflight-only
    .venv/bin/python tests/qa6/run.py --wave 1 --wave 2
    .venv/bin/python tests/qa6/run.py --wave 2 --lane unit
    .venv/bin/python tests/qa6/run.py --mutation PP14-D2   # one scenario mutation proof

One pytest process per (wave, lane), each `-p no:randomly`, over
`tests/qa6/<lane>/test_wave<N>_*.py`, in `stopifs.WAVE_LANES` order. After
each lane process the runner re-checks the real settings sha (a change stops
the run, U2), compares the user's `~/.local/bin/claude` against its run-START
state (a change stops the run: INC-1, realclaude.py) and scans the tmux shim
log for a Z2-class argv (stops the run);
after each wave it applies the plan's stop-ifs by writing `blocked.json`,
which the next processes' conftest reads.

At the end every planned id without a record gets a BLOCKED record naming why
(not implemented in this build, wave not selected, or the stop-if), the run
roots are removed and leak-checked, and the report is published by
`report.write_report` — GREEN only on 161 PASS, every lane exit 0 and a clean
teardown.

Progress lines go to stderr through `logging` (this repo has no project logger; the
harness never uses `print` for its own diagnostics).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    # Run as a script: import this directory as the `qa6` package, and drop the
    # script directory itself so none of its modules can shadow a stdlib name.
    _here = str(Path(__file__).resolve().parent)
    sys.path[:] = [entry for entry in sys.path if os.path.realpath(entry or ".") != _here]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qa6 import bootstrap, hostprobe, paths, preflight, realclaude, teardown, tmuxctl  # noqa: E402
from qa6.catalog import SCENARIOS  # noqa: E402
from qa6.report import LaneExit, append_record, build_record, load_records, record_path, write_report  # noqa: E402
from qa6.sandbox import (  # noqa: E402
    ENV_BLOCKED_FILE,
    ENV_LANE,
    ENV_REPORT_DIR,
    ENV_RUN_DIR,
    ENV_RUN_ID,
    ENV_RUN_PID,
    ENV_WAVE,
    RunContext,
    pytest_process_env,
)
from qa6.stopifs import BACKGROUND_LANES, STOP_IFS, WAVE_LANES  # noqa: E402

LOG = logging.getLogger("qa6.run")
HOST_WAVE = 9
LANE_TIMEOUT_S = 3600.0
GUARDS = paths.QA6_DIR / "test_harness_guards.py"


def lane_files(wave: int, lane: str) -> list[Path]:
    return sorted((paths.QA6_DIR / lane).glob(f"test_wave{wave}_*.py"))


def pytest_argv(files: list[Path], extra: list[str] | None = None) -> list[str]:
    return [
        str(paths.PYTEST), "-p", "no:randomly", "-p", "no:cacheprovider",
        "-m", "qa6 or qa6live", "-rA", *(extra or []), *[str(f.relative_to(paths.REPO)) for f in files],
    ]


def lane_env(run: RunContext, report_dir: Path, wave: int | str, lane: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    knobs = {
        ENV_RUN_PID: str(run.pid), ENV_RUN_ID: run.run_id, ENV_RUN_DIR: str(run.run_dir),
        ENV_REPORT_DIR: str(report_dir), ENV_LANE: lane, ENV_WAVE: str(wave),
        ENV_BLOCKED_FILE: str(run.run_dir / "blocked.json"),
        "QA6_REAL_TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        **(extra or {}),
    }
    mode_file = run.run_dir / "live_auth_mode.json"
    if mode_file.exists():
        decoded = json.loads(mode_file.read_text(encoding="utf-8"))
        if isinstance(decoded, dict) and isinstance(decoded.get("LIVE_AUTH_MODE"), str):
            knobs["QA6_LIVE_AUTH_MODE"] = decoded["LIVE_AUTH_MODE"]
    return pytest_process_env(os.environ, knobs)


def run_pytest(argv: list[str], env: dict[str, str], log_path: Path, timeout_s: float = LANE_TIMEOUT_S) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as log:
        process = subprocess.Popen(argv, env=env, cwd=str(paths.REPO), stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            LOG.error("lane process %s exceeded %ss; terminating its process group", process.pid, timeout_s)
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=30)
            return 124


def ledger_copies(run: RunContext) -> list[tuple[Path, str]]:
    """(source, name under `<run_dir>/ledgers/`). Unique names: the product's tmux log and
    the unseeded instances' tmux log are both `tmux-argv.log` in their shim dirs (SI-2)."""
    return [
        (run.tmux_argv_log, "tmux-argv.log"),
        (run.unseeded_tmux_argv_log, "unseeded-tmux-argv.log"),
        (run.pane_tmux_argv_log, "pane-tmux-argv.log"),
        (run.claude_argv_log, "claude-argv.log"),
        (run.pid_ledger, run.pid_ledger.name),
        (run.controld_argv_ledger, run.controld_argv_ledger.name),
        (run.port_refusals, run.port_refusals.name),
    ]


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def records_by_id(run: RunContext) -> dict[str, dict[str, object]]:
    return {str(record.get("id")): record for record in load_records(run.run_dir)}


def write_blocked(run: RunContext, blocked: dict[str, str]) -> None:
    (run.run_dir / "blocked.json").write_text(json.dumps(blocked, indent=1, sort_keys=True), encoding="utf-8")


def z2_violations(run: RunContext) -> list[str]:
    """Any product tmux argv that is not exactly `tmux -V` and not `-L <our socket>`, and any
    in-pane (engine) tmux call whose effective socket (`-S`, `-L`, else `$TMUX`) is not ours."""
    violations: list[str] = []
    log = run.tmux_argv_log
    pattern = paths.runner_socket_pattern(run.pid)
    for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []):
        if not line.strip():
            continue
        argv = json.loads(line)
        if argv == ["tmux", "-V"]:
            continue
        if not (isinstance(argv, list) and len(argv) >= 3 and argv[1] == "-L" and pattern.fullmatch(str(argv[2]))):
            violations.append(line[:300])
    pane_log = run.pane_tmux_argv_log
    entries: list[dict[str, object]] = []
    for line in (pane_log.read_text(encoding="utf-8").splitlines() if pane_log.exists() else []):
        if line.strip():
            decoded: object = json.loads(line)
            entries.append({str(k): v for k, v in decoded.items()} if isinstance(decoded, dict) else {"argv": decoded})
    violations.extend(f"in-pane: {json.dumps(v)[:300]}" for v in tmuxctl.pane_argv_violations(entries, run.pid))
    return violations


def fill_missing(run: RunContext, selected_waves: set[int], blocked: dict[str, str], implemented: set[str]) -> None:
    have = records_by_id(run)
    path = record_path(run.run_dir, "runner", "all")
    for scenario in SCENARIOS:
        if scenario.id in have:
            continue
        if scenario.id in blocked:
            reason = f"stop-if: {blocked[scenario.id]}"
        elif scenario.id not in implemented:
            reason = "not implemented in this build of tests/qa6 (no test carries this id)"
        elif scenario.wave not in selected_waves:
            reason = "its wave was not selected for this run"
        else:
            reason = "no record was written (its lane process crashed or was deselected)"
        append_record(path, build_record(scenario.id, verdict="BLOCKED", fail_kind=None, reason=reason,
                                         clauses=[], evidence=[], node="", lane_process="runner-wall",
                                         duration_s=0.0))


def implemented_ids() -> set[str]:
    rc, out = preflight._run([str(paths.PYTEST), "--collect-only", "-m", "qa6 or qa6live", "tests/qa6",
                              "-p", "no:randomly", "-p", "no:cacheprovider"], 120, cwd=paths.REPO)
    _unknown, _dups, found = preflight.collected_ids(out)
    return set(found)


def snapshot_host(run: RunContext, label: str) -> None:
    """A read-only host snapshot after each lane process, for Z1 (test-plan Z1 When)."""
    target = run.run_dir / "host-after"
    target.mkdir(parents=True, exist_ok=True)
    hostprobe.write_baseline(target / f"{label}.json", hostprobe.snapshot())


def settings_ok() -> bool:
    return hostprobe.sha256(paths.REAL_SETTINGS) == paths.EXPECTED_SETTINGS_SHA


def keep_awake() -> subprocess.Popen[bytes] | None:
    if not paths.CAFFEINATE_BIN.exists():
        return None
    return subprocess.Popen([str(paths.CAFFEINATE_BIN), "-dimsu", "-w", str(os.getpid())],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tests/qa6/run.py")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--wave", type=int, action="append", default=[])
    parser.add_argument("--lane", action="append", default=[])
    parser.add_argument("--report-dir", type=Path, default=paths.DEFAULT_REPORT_DIR)
    parser.add_argument("--skip-t4", action="store_true", help="skip the T4 preflight tier (debugging only)")
    parser.add_argument("--mutation", default=None, help="run one scenario mutation proof (fixtures/mutations/scenarios.json)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s qa6 %(levelname)s %(message)s", stream=sys.stderr)

    if args.mutation:
        from qa6 import mutations
        return mutations.run_scenario_mutation(args.mutation, args.report_dir)

    run_id = time.strftime("qa6-%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = args.report_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    # INC-1: the user's link is measured before anything else runs, and every
    # later check compares against THIS state (it may already be damaged).
    link_start = realclaude.record_link_start(run_dir)
    LOG.info("run-start state of %s: %s", paths.REAL_CLAUDE_BIN, link_start)
    awake = keep_awake()
    try:
        return _run(args, run_id, run_dir)
    finally:
        if awake is not None and awake.poll() is None:
            awake.terminate()
            awake.wait(timeout=5)


def _run(args: argparse.Namespace, run_id: str, run_dir: Path) -> int:
    report_dir: Path = args.report_dir
    checks, reached = preflight.run_tiers(include_t4=not args.skip_t4)
    (run_dir / "preflight.json").write_text(json.dumps({"reached": reached, "checks": [c.as_json() for c in checks]}, indent=1),
                                            encoding="utf-8")
    failed = [c for c in checks if not c.ok]
    for check in failed:
        LOG.error("preflight %s %s: expected %s, got %s", check.tier, check.name, check.expected, check.actual[:300])
    if args.preflight_only:
        LOG.info("preflight reached %s with %d failure(s)", reached, len(failed))
        return 0 if not failed else 3
    if failed:
        LOG.error("preflight failed: the run is BLOCKED and no wave starts")
        return 3

    sweep = teardown.sweep_dead_runs()
    if sweep.live_owners:
        LOG.error("live owners hold qa6 state: %s — BLOCKED (another run?)", sweep.live_owners)
        return 3
    baseline = hostprobe.snapshot()
    hostprobe.write_baseline(run_dir / "baseline.json", baseline)
    run = bootstrap.mint(os.getpid(), run_id, run_dir)
    LOG.info("run %s minted at %s", run_id, run.run0)

    lane_exits: list[LaneExit] = []
    guard_rc = run_pytest(pytest_argv([GUARDS]), lane_env(run, report_dir, "guards", "guards"), run_dir / "logs" / "guards.log", 900)
    lane_exits.append(LaneExit("guards", "0", guard_rc, tuple(pytest_argv([GUARDS]))))
    implemented = implemented_ids()
    blocked: dict[str, str] = {}
    selected = set(args.wave) if args.wave else set(WAVE_LANES)
    stopped: str | None = None
    if guard_rc != 0:
        stopped = f"harness guards failed (exit {guard_rc}); see logs/guards.log"
        LOG.error(stopped)
    background: list[tuple[str, str, subprocess.Popen[bytes], list[str]]] = []

    for wave in sorted(w for w in WAVE_LANES if w != HOST_WAVE):
        if stopped is not None:
            for sid in (s.id for s in SCENARIOS if s.wave == wave):
                blocked.setdefault(sid, stopped)
            continue
        if wave not in selected:
            continue
        write_blocked(run, blocked)
        for lane in WAVE_LANES[wave]:
            if args.lane and lane not in args.lane:
                continue
            files = lane_files(wave, lane)
            if not files:
                continue
            argv = pytest_argv(files)
            env = lane_env(run, report_dir, wave, lane)
            log = run_dir / "logs" / f"{lane}-w{wave}.log"
            if lane in BACKGROUND_LANES:
                handle = open(log, "wb")
                process = subprocess.Popen(argv, env=env, cwd=str(paths.REPO), stdout=handle, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                background.append((lane, str(wave), process, argv))
                LOG.info("wave %d lane %s started in the background (pid %d)", wave, lane, process.pid)
                continue
            LOG.info("wave %d lane %s: %d module(s)", wave, lane, len(files))
            code = run_pytest(argv, env, log)
            lane_exits.append(LaneExit(lane, str(wave), code, tuple(argv)))
            LOG.info("wave %d lane %s exited %d", wave, lane, code)
            snapshot_host(run, f"{lane}-w{wave}")
            if not settings_ok():
                stopped = f"the real settings sha changed during wave {wave} lane {lane} (U2): the run is stopped"
                LOG.error(stopped)
                break
            link_changed = realclaude.link_change(run_dir)
            if link_changed is not None:
                stopped = f"after wave {wave} lane {lane}: {link_changed}"
                LOG.error(stopped)
                break
            violations = z2_violations(run)
            if violations:
                stopped = f"Z2-class tmux argv after wave {wave} lane {lane}: {violations[:3]}"
                LOG.error(stopped)
                break
        records = records_by_id(run)
        for rule in STOP_IFS:
            if rule.after_wave != wave or not rule.fires(records):
                continue
            LOG.warning("stop-if after wave %d: %s", wave, rule.description)
            for sid in rule.blocks(records):
                if sid not in records:
                    blocked.setdefault(sid, rule.description)
            if rule.stops_run:
                stopped = rule.description
        write_blocked(run, blocked)
        if wave == 1:
            _publish_auth_mode(run, records)

    _join_background(background, lane_exits)

    # Teardown (env-plan §9) BEFORE wave 9: Z1-Z3 observe the host the run left
    # behind (Z3 asserts the run root is removed). The ledgers the Z-scenarios
    # read are copied out of the run root first.
    ledgers = run_dir / "ledgers"
    ledgers.mkdir(exist_ok=True)
    for source, name in ledger_copies(run):
        if source.exists():
            (ledgers / name).write_bytes(source.read_bytes())
    problems = bootstrap.remove_worktree(run)
    leak = teardown.teardown_run(run)
    problems.extend(leak.problems)
    for problem in problems:
        run.teardown_problem("runner", problem)
    if not settings_ok():
        run.teardown_problem("runner", "the real ~/.claude/settings.json sha changed (U2)")
    link_changed = realclaude.link_change(run_dir)
    if link_changed is not None:
        run.teardown_problem("runner", link_changed)
    snapshot_host(run, "after-teardown")

    # Wave 9 runs even when earlier waves stopped (test-plan §3): it is the host check.
    if HOST_WAVE in selected:
        write_blocked(run, {})
        for lane in WAVE_LANES[HOST_WAVE]:
            files = lane_files(HOST_WAVE, lane)
            if not files or (args.lane and lane not in args.lane):
                continue
            argv = pytest_argv(files)
            code = run_pytest(argv, lane_env(run, report_dir, HOST_WAVE, lane), run_dir / "logs" / f"{lane}-w{HOST_WAVE}.log")
            lane_exits.append(LaneExit(lane, str(HOST_WAVE), code, tuple(argv)))
            LOG.info("wave %d lane %s exited %d", HOST_WAVE, lane, code)
    fill_missing(run, selected, blocked, implemented)
    teardown_problems = _read_teardown_problems(run)
    decision = write_report(report_dir, run_id, run_dir, lane_exits, teardown_problems,
                            extra={"preflight_reached": "T4", "leak_notes": leak.notes,
                                   "real_claude": read_json(run_dir / realclaude.RESOLUTION_FILE),
                                   "claude_link": {"start": realclaude.start_link_state(run_dir),
                                                   "end": realclaude.link_state()}})
    LOG.info("report %s: %s — %s", run_id, decision.status, "; ".join(decision.reasons)[:1500])
    return 0 if decision.status == "GREEN" else 1


def _publish_auth_mode(run: RunContext, records: dict[str, dict[str, object]]) -> None:
    record = records.get("S0")
    evidence = record.get("evidence") if record else None
    mode = "unavailable"
    if isinstance(evidence, list):
        for line in evidence:
            if isinstance(line, str) and line.startswith("LIVE_AUTH_MODE="):
                mode = line.split("=", 1)[1].split()[0]
                break
    target = run.run_dir / "live_auth_mode.json"
    if not target.exists():
        target.write_text(json.dumps({"LIVE_AUTH_MODE": mode, "source": "S0 record"}), encoding="utf-8")


def _join_background(background: list[tuple[str, str, subprocess.Popen[bytes], list[str]]], lane_exits: list[LaneExit]) -> None:
    while background:
        lane, wave, process, argv = background.pop()
        try:
            code = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            code = 124
        lane_exits.append(LaneExit(lane, wave, code, tuple(argv)))


def _read_teardown_problems(run: RunContext) -> list[str]:
    path = run.teardown_problems
    if not path.exists():
        return []
    problems: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                problems.append(f"{decoded.get('where')}: {decoded.get('problem')}")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
