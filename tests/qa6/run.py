#!/usr/bin/env python3
"""The qa6 run entry: preflight → baseline → guards → waves in order → teardown → report.

    .venv/bin/python tests/qa6/run.py                 # every wave
    .venv/bin/python tests/qa6/run.py --preflight-only
    .venv/bin/python tests/qa6/run.py --wave 1 --wave 2
    .venv/bin/python tests/qa6/run.py --wave 2 --lane unit
    .venv/bin/python tests/qa6/run.py --mutation PP14-D2   # one scenario mutation proof

One pytest process per (wave, lane), each `-p no:randomly`, over
`tests/qa6/<lane>/test_wave<N>_*.py`, in `stopifs.WAVE_LANES` order. The real
settings sha is measured ONCE, at run start before preflight and before any
lane, and exported to every lane as `QA6_RUN_SETTINGS_SHA` (`capture_settings_sha`);
after each lane process the runner re-checks the real settings sha against that
run-start value (a change stops the run, U2; a run-start value other than the
owner's is a published preflight WARN, INC-3), compares the user's `~/.local/bin/claude` against its run-START
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
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

if __package__ in (None, ""):
    # Run as a script: import this directory as the `qa6` package, and drop the
    # script directory itself so none of its modules can shadow a stdlib name.
    _here = str(Path(__file__).resolve().parent)
    sys.path[:] = [entry for entry in sys.path if os.path.realpath(entry or ".") != _here]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qa6 import bootstrap, hostprobe, paths, preflight, realclaude, report, teardown, tmuxctl  # noqa: E402
from qa6.catalog import SCENARIOS  # noqa: E402
from qa6.jsonl import read_objects  # noqa: E402
from shepherd.runner.tmux_cmd import DEFAULT_SOCKET  # noqa: E402
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
#: An instance started WITHOUT the seeded DB runs `list-sessions` on the product's default socket in
#: its reconcile (C7; sandbox.RunContext.shims_unseeded). The shim refuses it like any other foreign
#: socket (it never reaches tmux), and it is recorded; it does not stop the run. Any OTHER verb on that
#: socket, and any other socket, does (review N3: excused by socket AND verb, `tmuxctl.unseeded_excused`).
UNSEEDED_DEFAULT_SOCKET: str = DEFAULT_SOCKET
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
        paths.ENV_RUN_SETTINGS_SHA: paths.expected_settings_sha(),
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


TREE_FILE = "tree.json"
#: The paths a run executes: a change under any of them is a different tree.
TREE_PATHS: tuple[str, ...] = ("tests/qa6", "src", "pyproject.toml")


def tree_identity() -> dict[str, object]:
    """`{"head", "dirty"}`: the commit this run executes and every uncommitted path under TREE_PATHS."""
    head = subprocess.run([str(paths.GIT_BIN), "-C", str(paths.REPO), "rev-parse", "HEAD"], capture_output=True,
                          text=True, timeout=30, check=False)
    status = subprocess.run([str(paths.GIT_BIN), "-C", str(paths.REPO), "status", "--porcelain",
                             "--untracked-files=all", "--", *TREE_PATHS], capture_output=True, text=True,
                            timeout=30, check=False)
    return {
        "head": head.stdout.strip() if head.returncode == 0 else f"unknown (git exited {head.returncode}: "
                                                                   f"{head.stderr.strip()[:200]})",
        "dirty": ([line for line in status.stdout.splitlines() if line.strip() and "__pycache__" not in line]
                  if status.returncode == 0 else [f"unknown (git status exited {status.returncode})"]),
        "paths": list(TREE_PATHS),
    }


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def records_by_id(run: RunContext) -> dict[str, dict[str, object]]:
    return {str(record.get("id")): record for record in load_records(run.run_dir)}


def write_blocked(run: RunContext, blocked: dict[str, str]) -> None:
    (run.run_dir / "blocked.json").write_text(json.dumps(blocked, indent=1, sort_keys=True), encoding="utf-8")


def z2_offenders(run: RunContext) -> list[str]:
    """Every logged tmux argv whose effective socket (tmux's own rules: `tmuxctl.effective_socket`)
    is not this run's, product and in-pane alike; `tmux -V` alone is allowed. A line that is not
    a JSON argv is itself a violation: an unreadable log proves nothing clean."""
    violations: list[str] = []
    for log, excusable in ((run.tmux_argv_log, False), (run.unseeded_tmux_argv_log, True)):
        for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []):
            if not line.strip():
                continue
            try:
                decoded: object = json.loads(line)
            except json.JSONDecodeError:
                violations.append(f"unparseable line in {log}: {line[:300]}")
                continue
            argv = [str(word) for word in decoded] if isinstance(decoded, list) else None
            why = tmuxctl.argv_violation(argv, None, run.pid) if argv is not None else "not a JSON argv"
            if why is not None and not (excusable and argv is not None
                                        and tmuxctl.unseeded_excused(argv, UNSEEDED_DEFAULT_SOCKET)):
                violations.append(f"{log}: {why}: {line[:300]}")
    pane_log = run.pane_tmux_argv_log
    entries: list[dict[str, object]] = []
    for line in (pane_log.read_text(encoding="utf-8").splitlines() if pane_log.exists() else []):
        if not line.strip():
            continue
        try:
            decoded_entry: object = json.loads(line)
        except json.JSONDecodeError:
            violations.append(f"unparseable line in {pane_log.name}: {line[:300]}")
            continue
        entries.append({str(k): v for k, v in decoded_entry.items()} if isinstance(decoded_entry, dict)
                       else {"argv": decoded_entry})
    violations.extend(f"in-pane: {json.dumps(v)[:300]}" for v in tmuxctl.pane_argv_offenders(entries, run.pid))
    return violations


def fill_missing(run: RunContext, selected_waves: set[int], blocked: dict[str, str], implemented: set[str],
                 lane_exits: list[LaneExit] | None = None, crash: str | None = None) -> None:
    have = records_by_id(run)
    path = record_path(run.run_dir, "runner", "all")
    exits = {int(lane.wave): lane for lane in (lane_exits or []) if lane.wave.isdigit() and lane.exit_code not in (0, 1)}
    for scenario in SCENARIOS:
        if scenario.id in have:
            continue
        if scenario.id in blocked:
            reason = f"stop-if: {blocked[scenario.id]}"
        elif scenario.id not in implemented:
            reason = "not implemented in this build of tests/qa6 (no test carries this id)"
        elif scenario.wave not in selected_waves:
            reason = "its wave was not selected for this run"
        elif scenario.wave in exits:
            lane = exits[scenario.wave]
            reason = (f"its wave's {lane.lane} lane process "
                      f"{'timed out (exit 124)' if lane.exit_code == 124 else f'crashed (exit {lane.exit_code})'} "
                      "before writing this record")
        elif crash is not None:
            reason = f"the runner crashed before this scenario ran: {crash.splitlines()[0][:300]}"
        else:
            reason = "no record was written (its lane process crashed or was deselected)"
        append_record(path, build_record(scenario.id, verdict="BLOCKED", fail_kind=None, reason=reason,
                                         clauses=[], evidence=[], node="", lane_process="runner-wall",
                                         duration_s=0.0))


def implemented_ids() -> set[str]:
    """The ids a collection finds. A collection that fails is a runner error, never "0 implemented" (L1)."""
    rc, out = preflight._run([str(paths.PYTEST), "--collect-only", "-m", "qa6 or qa6live", "tests/qa6",
                              "-p", "no:randomly", "-p", "no:cacheprovider"], 120, cwd=paths.REPO)
    if rc != 0:
        raise RuntimeError(f"pytest --collect-only exited {rc}: {out[-1500:]}")
    _unknown, _dups, found = preflight.collected_ids(out)
    return set(found)


def snapshot_host(run: RunContext, label: str) -> hostprobe.Baseline | None:
    """A read-only host snapshot after each lane process, for Z1 (test-plan Z1 When).

    A probe that cannot answer (`ProbeUnknown`) is a teardown problem and writes
    `{"unknown": …}`: an unknown host state is never recorded as a clean one.
    """
    target = run.run_dir / "host-after"
    target.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = hostprobe.snapshot()
    except hostprobe.ProbeUnknown as error:
        run.teardown_problem("runner", f"host snapshot {label} unknown: {error}")
        (target / f"{label}.json").write_text(json.dumps({"unknown": str(error)}), encoding="utf-8")
        return None
    hostprobe.write_baseline(target / f"{label}.json", snapshot)
    return snapshot


SETTINGS_START_FILE = "settings-start.json"


def capture_settings_sha() -> str:
    """Measure the real settings sha ONCE, at run start, and export it for this process and every lane.

    Unconditional: a value inherited from the caller's environment is replaced by
    the measurement, so the invariant is always "unchanged since THIS run began".
    Read-only (`hostprobe.sha256` opens the file for reading).
    """
    sha = hostprobe.sha256(paths.REAL_SETTINGS)
    os.environ[paths.ENV_RUN_SETTINGS_SHA] = sha
    return sha


def write_settings_start(run_dir: Path, sha: str) -> None:
    (run_dir / SETTINGS_START_FILE).write_text(json.dumps(
        {"run_start": sha, "owner": paths.OWNER_SETTINGS_SHA, "differs_from_owner": sha != paths.OWNER_SETTINGS_SHA},
        indent=1, sort_keys=True), encoding="utf-8")


def settings_ok() -> bool:
    """The U2 guard: the real settings sha is still what it was at run start (the harness never writes it)."""
    return hostprobe.sha256(paths.REAL_SETTINGS) == paths.expected_settings_sha()


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

    settings_start = capture_settings_sha()
    LOG.info("run-start sha of %s: %s (owner-named U2: %s)", paths.REAL_SETTINGS, settings_start,
             "same" if settings_start == paths.OWNER_SETTINGS_SHA else f"DIFFERS, {paths.OWNER_SETTINGS_SHA}")
    if args.mutation:
        from qa6 import mutations
        return mutations.run_scenario_mutation(args.mutation, args.report_dir)

    run_id = time.strftime("qa6-%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = args.report_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_settings_start(run_dir, settings_start)
    # Tree identity (verification: evidence names the revision it ran): HEAD and every
    # uncommitted path under the code the run executes, measured before anything runs.
    (run_dir / TREE_FILE).write_text(json.dumps(tree_identity(), indent=1, sort_keys=True), encoding="utf-8")
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


@dataclass
class Background:
    lane: str
    wave: str
    process: subprocess.Popen[bytes]
    argv: list[str]
    handle: BinaryIO


@dataclass
class RunState:
    """Everything the waves learn that the finalizer must still publish if they crash (H6)."""

    args: argparse.Namespace
    run: RunContext
    baseline: hostprobe.Baseline
    reached: str
    selected: set[int]
    #: The preflight's non-stopping WARN lines (`preflight.warnings`): published in the report.
    warnings: list[str] = field(default_factory=list)
    lane_exits: list[LaneExit] = field(default_factory=list)
    blocked: dict[str, str] = field(default_factory=dict)
    implemented: set[str] = field(default_factory=set)
    background: list[Background] = field(default_factory=list)
    stopped: str | None = None
    leak_notes: list[str] = field(default_factory=list)
    runner_errors: list[str] = field(default_factory=list)


def preflight_blocked(report_dir: Path, run_id: str, reasons: list[str], warnings: list[str] | None = None) -> int:
    """A run that never minted still leaves a history line (H6): nothing is invisible."""
    report.append_history(report_dir, {"run_id": run_id, "status": "INCOMPLETE", "stage": "preflight",
                                       "counts": {}, "reasons": reasons[:20], "warnings": list(warnings or [])})
    LOG.error("the run is BLOCKED before any wave: %s", "; ".join(reasons)[:1500])
    return 3


def _run(args: argparse.Namespace, run_id: str, run_dir: Path) -> int:
    report_dir: Path = args.report_dir
    checks, reached = preflight.run_tiers(include_t4=not args.skip_t4)
    warned = preflight.warnings(checks)
    (run_dir / "preflight.json").write_text(json.dumps({"reached": reached, "checks": [c.as_json() for c in checks],
                                                        "warnings": warned}, indent=1), encoding="utf-8")
    failed = [c for c in checks if not c.ok]
    for check in failed:
        LOG.error("preflight %s %s: expected %s, got %s", check.tier, check.name, check.expected, check.actual[:300])
    for line in warned:
        LOG.warning("WARN (non-stopping) %s", line)
    if args.preflight_only:
        LOG.info("preflight reached %s with %d failure(s) and %d warning(s)", reached, len(failed), len(warned))
        return 0 if not failed else 3
    if failed:
        return preflight_blocked(report_dir, run_id, [f"preflight {c.tier} {c.name}: {c.actual[:200]}" for c in failed],
                                 warned)
    try:
        sweep = teardown.sweep_dead_runs()
        if sweep.live_owners:
            return preflight_blocked(report_dir, run_id, [f"live owners hold qa6 state (another run?): {sweep.live_owners}"],
                                     warned)
        for line in sweep.orphans_stopped:
            LOG.warning("pre-run sweep: %s", line)
        baseline = hostprobe.snapshot()
        hostprobe.write_baseline(run_dir / "baseline.json", baseline)
        run = bootstrap.mint(os.getpid(), run_id, run_dir)
    except Exception as error:  # noqa: BLE001 - recorded, never swallowed: the history says why
        return preflight_blocked(report_dir, run_id, [f"before mint: {type(error).__name__}: {error}",
                                                      traceback.format_exc()[-1500:]], warned)
    LOG.info("run %s minted at %s", run_id, run.run0)
    state = RunState(args=args, run=run, baseline=baseline, reached=reached,
                     selected=set(args.wave) if args.wave else set(WAVE_LANES), warnings=warned)
    for line in [*sweep.orphans_stopped, *sweep.problems]:
        run.teardown_problem("pre-run sweep", line)
    return guarded(lambda: _waves(state), lambda crash: _finish(state, run_id, crash))


def guarded(body: Callable[[], None], finish: Callable[[str | None], int]) -> int:
    """Run the waves; ALWAYS finish (teardown, wave 9, publish), with the crash if there was one.

    H6: a runner exception used to skip teardown and publication, leaving
    `qa6-latest.json` on the previous run and the run's processes orphaned.
    `KeyboardInterrupt` is published too, then re-raised.
    """
    crash: str | None = None
    interrupted: BaseException | None = None
    try:
        body()
    except Exception as error:  # noqa: BLE001 - published as the run's INCOMPLETE reason
        crash = f"{type(error).__name__}: {error}\n{traceback.format_exc()[-3000:]}"
    except KeyboardInterrupt as error:
        crash = "KeyboardInterrupt"
        interrupted = error
    code = finish(crash)
    if interrupted is not None:
        raise interrupted
    return code


def _waves(state: RunState) -> None:
    run, args = state.run, state.args
    report_dir: Path = args.report_dir
    guard_rc = run_pytest(pytest_argv([GUARDS]), lane_env(run, report_dir, "guards", "guards"),
                          run.run_dir / "logs" / "guards.log", 900)
    state.lane_exits.append(LaneExit("guards", "0", guard_rc, tuple(pytest_argv([GUARDS]))))
    state.implemented = implemented_ids()
    if guard_rc != 0:
        state.stopped = f"harness guards failed (exit {guard_rc}); see logs/guards.log"
        LOG.error(state.stopped)
    for wave in sorted(w for w in WAVE_LANES if w != HOST_WAVE):
        if state.stopped is not None:
            for sid in (s.id for s in SCENARIOS if s.wave == wave):
                state.blocked.setdefault(sid, state.stopped)
            continue
        if wave not in state.selected:
            continue
        write_blocked(run, state.blocked)
        for lane in WAVE_LANES[wave]:
            if args.lane and lane not in args.lane:
                continue
            files = lane_files(wave, lane)
            if not files:
                continue
            argv = pytest_argv(files)
            env = lane_env(run, report_dir, wave, lane)
            log = run.run_dir / "logs" / f"{lane}-w{wave}.log"
            if lane in BACKGROUND_LANES:
                log.parent.mkdir(parents=True, exist_ok=True)
                handle = open(log, "wb")
                process = subprocess.Popen(argv, env=env, cwd=str(paths.REPO), stdout=handle, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                state.background.append(Background(lane, str(wave), process, argv, handle))
                LOG.info("wave %d lane %s started in the background (pid %d)", wave, lane, process.pid)
                continue
            LOG.info("wave %d lane %s: %d module(s)", wave, lane, len(files))
            code = run_pytest(argv, env, log)
            state.lane_exits.append(LaneExit(lane, str(wave), code, tuple(argv)))
            LOG.info("wave %d lane %s exited %d", wave, lane, code)
            state.stopped = after_lane_stop(state, wave, lane)
            if state.stopped is not None:
                LOG.error(state.stopped)
                break
        records = records_by_id(run)
        for rule in STOP_IFS:
            if rule.after_wave != wave or not rule.fires(records):
                continue
            LOG.warning("stop-if after wave %d: %s", wave, rule.description)
            for sid in rule.blocks(records):
                if sid not in records:
                    state.blocked.setdefault(sid, rule.description)
            if rule.stops_run:
                state.stopped = rule.description
        write_blocked(run, state.blocked)
        if wave == 1:
            _publish_auth_mode(run, records)


def after_lane_stop(state: RunState, wave: int, lane: str) -> str | None:
    """The host checks after every lane process; any one of them stops the run."""
    run = state.run
    snapshot = snapshot_host(run, f"{lane}-w{wave}")
    where = f"after wave {wave} lane {lane}"
    if not settings_ok():
        return (f"the real settings sha changed during wave {wave} lane {lane} (U2: it is no longer its run-start "
                f"value {paths.expected_settings_sha()}): the run is stopped")
    link_changed = realclaude.link_change(run.run_dir)
    if link_changed is not None:
        return f"{where}: {link_changed}"
    tree = local_tree_problem(run, state.baseline, snapshot)
    if tree is not None:
        return f"{where}: {tree}"
    violations = z2_offenders(run)
    if violations:
        return f"Z2-class tmux argv {where}: {violations[:3]}"
    return None


def engine_version(run: RunContext) -> str | None:
    """The version name of this run's real engine (`…/versions/<v>`), for lock attribution."""
    resolved = realclaude.load(run).path
    return os.path.basename(resolved) if resolved else None


def local_tree_problem(run: RunContext, baseline: hostprobe.Baseline, snapshot: hostprobe.Baseline | None) -> str | None:
    """Review finding 3: any change under ~/.local/{bin, share/claude, state/claude} since run start."""
    if snapshot is None:
        return "the host snapshot could not be taken, so ~/.local could not be compared (unknown is not clean)"
    changes, attributed = hostprobe.local_tree_changes(baseline.local_tree, snapshot.local_tree, engine_version(run))
    if attributed:
        LOG.info("~/.local changes attributed to the user's own sessions: %s", attributed)
    if changes:
        return (f"~/.local changed since run start (INC-1 guard; the harness never writes there and no live "
                f"scenario may run until a human has looked): {json.dumps(changes)[:1200]}")
    return None


def _finish(state: RunState, run_id: str, crash: str | None) -> int:
    """Teardown → wave 9 → publish. Each step's own failure is recorded and the next still runs."""
    run, args = state.run, state.args
    errors = state.runner_errors
    if crash is not None:
        errors.append(f"runner crashed: {crash}")
        LOG.error("runner crashed; tearing down and publishing (RED if a product FAIL was recorded, else "
                  "INCOMPLETE): %s", crash[:600])

    def step(name: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as error:  # noqa: BLE001 - every finalizer step's failure is published
            errors.append(f"finalizer step {name!r} failed: {type(error).__name__}: {error}")
            LOG.error("finalizer step %s failed: %s", name, error)

    step("join background lanes", lambda: _join_background(state.background, state.lane_exits))
    step("copy ledgers", lambda: _copy_ledgers(run))
    step("remove worktree", lambda: _remove_worktree(run))
    step("teardown run", lambda: _teardown(state))
    step("post-teardown host checks", lambda: _post_teardown_checks(state))
    if HOST_WAVE in state.selected:
        step("wave 9", lambda: _host_wave(state))
    step("fill missing records", lambda: fill_missing(run, state.selected, state.blocked, state.implemented,
                                                      state.lane_exits, crash))
    try:
        decision = _publish(state, run_id, crash)
    except Exception as error:  # noqa: BLE001 - the last resort below publishes it, with the crash
        publish_error = f"{type(error).__name__}: {error}\n{traceback.format_exc()[-3000:]}"
        LOG.error("publication failed; writing the last-resort INCOMPLETE record: %s", publish_error[:600])
        _publish_last_resort(args.report_dir, run_id, crash, publish_error, errors)
        return 1
    LOG.info("report %s: %s — %s", run_id, decision.status, "; ".join(decision.reasons)[:1500])
    for line in state.warnings:
        LOG.warning("report %s WARN (non-stopping) %s", run_id, line)
    return 0 if decision.status == "GREEN" else 1


def _publish(state: RunState, run_id: str, crash: str | None) -> report.Decision:
    run, args = state.run, state.args
    teardown_problems = _read_teardown_problems(run)
    harness_problems = [*_read_problem_file(run.run_dir / "harness-problems.jsonl"), *state.runner_errors]
    return write_report(args.report_dir, run_id, run.run_dir, state.lane_exits, teardown_problems,
                        extra={"preflight_reached": state.reached, "leak_notes": state.leak_notes,
                               "runner_crash": crash, "tree": read_json(run.run_dir / TREE_FILE),
                               "real_claude": read_json(run.run_dir / realclaude.RESOLUTION_FILE),
                               "claude_link": {"start": realclaude.start_link_state(run.run_dir),
                                               "end": realclaude.link_state()},
                               "settings_sha": read_json(run.run_dir / SETTINGS_START_FILE)},
                        harness_problems=harness_problems, runner_crash=crash, warnings=state.warnings)


def _publish_last_resort(report_dir: Path, run_id: str, crash: str | None, publish_error: str,
                         errors: list[str]) -> None:
    """Hunter N1 / review N4: publication itself failed. Write an INCOMPLETE run file and a history
    line that carry BOTH exceptions, so no run is ever invisible. Reads nothing that could be torn.

    The run file is immutable: when the normal path already wrote it (and failed later), this
    writes `<run_id>.last-resort.json` beside it instead of replacing it.
    """
    reasons = [f"publication failed: {publish_error.splitlines()[0][:600]}"]
    if crash is not None:
        reasons.append(f"the runner crashed: {crash.splitlines()[0][:600]}")
    payload: dict[str, object] = {
        "run_id": run_id, "status": "INCOMPLETE", "stage": "publish", "reasons": reasons,
        "publish_error": publish_error, "runner_crash": crash, "runner_errors": list(errors),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / f"{run_id}.json"
    if target.exists():
        target = report_dir / f"{run_id}.last-resort.json"
    target.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    target.chmod(0o444)
    report.append_history(report_dir, {"run_id": run_id, "status": "INCOMPLETE", "stage": "publish",
                                       "counts": {}, "reasons": reasons, "last_resort_file": target.name})


def _copy_ledgers(run: RunContext) -> None:
    """The ledgers the Z-scenarios read, copied out of the run root before teardown removes it."""
    ledgers = run.run_dir / "ledgers"
    ledgers.mkdir(exist_ok=True)
    for source, name in ledger_copies(run):
        if source.exists():
            (ledgers / name).write_bytes(source.read_bytes())


def _remove_worktree(run: RunContext) -> None:
    for problem in bootstrap.remove_worktree(run):
        run.teardown_problem("runner", problem)


def _teardown(state: RunState) -> None:
    leak = teardown.teardown_run(state.run)
    state.leak_notes.extend(leak.notes)
    (state.run.run_dir / teardown.SIGNALLED_FILE).write_text(
        json.dumps({"signalled": leak.signalled}, sort_keys=True), encoding="utf-8")
    for problem in leak.problems:
        state.run.teardown_problem("runner", problem)


def _post_teardown_checks(state: RunState) -> None:
    run = state.run
    if not settings_ok():
        run.teardown_problem("runner", "the real ~/.claude/settings.json sha changed since run start (U2)")
    link_changed = realclaude.link_change(run.run_dir)
    if link_changed is not None:
        run.teardown_problem("runner", link_changed)
    snapshot = snapshot_host(run, "after-teardown")
    tree = local_tree_problem(run, state.baseline, snapshot)
    if tree is not None:
        run.teardown_problem("runner", tree)


def _host_wave(state: RunState) -> None:
    """Wave 9 runs even when earlier waves stopped or crashed (test-plan §3): it is the host check."""
    run, args = state.run, state.args
    write_blocked(run, {})
    for lane in WAVE_LANES[HOST_WAVE]:
        files = lane_files(HOST_WAVE, lane)
        if not files or (args.lane and lane not in args.lane):
            continue
        argv = pytest_argv(files)
        code = run_pytest(argv, lane_env(run, args.report_dir, HOST_WAVE, lane),
                          run.run_dir / "logs" / f"{lane}-w{HOST_WAVE}.log")
        state.lane_exits.append(LaneExit(lane, str(HOST_WAVE), code, tuple(argv)))
        LOG.info("wave %d lane %s exited %d", HOST_WAVE, lane, code)


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


def _join_background(background: list[Background], lane_exits: list[LaneExit]) -> None:
    """Join every background lane: wait, else SIGTERM its group and WAIT, else SIGKILL (L5)."""
    while background:
        lane = background.pop()
        try:
            code = lane.process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            os.killpg(lane.process.pid, signal.SIGTERM)
            try:
                lane.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(lane.process.pid, signal.SIGKILL)
                lane.process.wait(timeout=30)
            code = 124
        finally:
            lane.handle.close()
        lane_exits.append(LaneExit(lane.lane, lane.wave, code, tuple(lane.argv)))


def _read_problem_file(path: Path) -> list[str]:
    """`where: problem` per line; a torn line is itself a problem, never an exception (hunter N1)."""
    read = read_objects(path)
    return [*(f"{row.get('where')}: {row.get('problem')}" for row in read.rows),
            *(f"malformed problem line: {problem}" for problem in read.problems)]


def _read_teardown_problems(run: RunContext) -> list[str]:
    return _read_problem_file(run.teardown_problems)


if __name__ == "__main__":
    raise SystemExit(main())
