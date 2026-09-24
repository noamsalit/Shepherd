"""Run-level teardown, leak checks, and the pre-run sweep of dead runs.

Every step verifies its own result and reports a problem instead of swallowing
it (a run that leaks is a passing run **plus a leak**, and a leak blocks GREEN;
env-plan §9). Signals go only to pids this run recorded in its ledger **and**
whose current start token (the product's `MacHost.process_liveness`) equals the
one recorded at spawn (`signal_decision`): a reused pid, or an entry with no
recorded token, is never signalled. `kill-server` goes only through `tmuxctl.kill_server`, which refuses
any socket outside this run's pattern.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.host.mac import MacHost

from . import hostprobe, paths, tmuxctl
from .pool import close_tmux_socket
from .sandbox import TMP_CANONICAL, RunContext
from .verdict import Blocked

RUN_DIR_RE = re.compile(rf"^{re.escape(paths.RUN_ROOT_PREFIX)}(\d+)-(\d+)$")
Q6_SOCKET_RE = re.compile(r"^shepherd-m3-q6(\d+)-(\d+)$")


@dataclass
class LeakReport:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def ledger_entries(pid_ledger: Path) -> list[dict[str, object]]:
    if not pid_ledger.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in pid_ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, dict):
                entries.append({str(k): v for k, v in decoded.items()})
    return entries


def recorded_pids(run: RunContext) -> list[dict[str, object]]:
    return ledger_entries(run.pid_ledger)


def current_token(pid: int) -> str | None:
    """The product's start token for `pid` now (`None` = not alive). Reads the process table only."""
    return MacHost().process_liveness(pid, None).start_token


def signal_decision(entry: Mapping[str, object], token_now: str | None) -> str | None:
    """Why this ledger entry may NOT be signalled, or `None` when it is provably ours and alive.

    Pure (review finding 4): ours means the pid's current start token equals the
    one recorded at spawn, exactly. An argv substring is never evidence — it
    over-matches (any `python`, `claude` or `sleep`) and under-matches (a
    console script shows as `…/python3 …/shepherd-controld`).
    """
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid in (0, 1, -1):
        return f"not a signallable pid: {pid!r}"
    recorded = entry.get("start_token")
    if not isinstance(recorded, str) or not recorded:
        return "no start token was recorded at spawn"
    if token_now is None:
        return "not alive"
    if token_now != recorded:
        return f"pid reused: start token now {token_now!r}, recorded {recorded!r}"
    return None


def _still_ours(entry: Mapping[str, object]) -> bool:
    pid = entry.get("pid")
    return isinstance(pid, int) and signal_decision(entry, current_token(pid)) is None


def stop_entries(entries: list[dict[str, object]], label: str) -> tuple[list[str], list[str]]:
    """SIGTERM (then SIGKILL) every entry that is provably ours and alive. (problems, notes)."""
    problems: list[str] = []
    notes: list[str] = []
    for entry in entries:
        pid = entry.get("pid")
        if not isinstance(pid, int):
            continue
        token_now = current_token(pid)
        why_not = signal_decision(entry, token_now)
        if why_not is not None:
            if token_now is not None and why_not != "not alive":
                notes.append(f"{label} pid {pid} ({entry.get('kind')}) alive but not signalled: {why_not}")
            continue
        problems.append(f"{label} {entry.get('kind')} pid {pid} still alive at teardown (start token matched)")
        _signal(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _still_ours(entry):
            time.sleep(0.1)
        if _still_ours(entry):
            _signal(pid, signal.SIGKILL)
            if _still_ours(entry):
                problems.append(f"{label} {entry.get('kind')} pid {pid} survived SIGKILL")
    return problems, notes


def _signal(pid: int, signum: signal.Signals) -> None:
    """Signal a pid `signal_decision` just cleared; one that exited in between is not an error (H6)."""
    try:
        os.kill(pid, signum)
    except ProcessLookupError:
        return


def stop_recorded(run: RunContext) -> tuple[list[str], list[str]]:
    """Every recorded child still alive and still ours (by start token). Each is a leak."""
    return stop_entries(recorded_pids(run), "recorded")


def our_tmux_sockets(run: RunContext) -> list[str]:
    found: list[str] = []
    for name in hostprobe.tmux_socket_listing():
        match = Q6_SOCKET_RE.match(name)
        if match and int(match.group(1)) == run.pid:
            found.append(name)
    return sorted(found)


def run_roots(run: RunContext) -> list[Path]:
    return sorted(TMP_CANONICAL.glob(f"{paths.RUN_ROOT_PREFIX}{run.pid}-*"))


def teardown_run(run: RunContext, *, remove_roots: bool = True) -> LeakReport:
    """Stop leftovers, kill our tmux servers, remove the roots, then check for leaks."""
    report = LeakReport()
    stopped, notes = stop_recorded(run)
    report.problems.extend(stopped)
    report.notes.extend(notes)
    for socket in our_tmux_sockets(run):
        report.notes.append(f"backstop: tmux server/socket {socket} present at run teardown")
        try:
            report.problems.extend(close_tmux_socket(run, socket))
        except Blocked as unknown:  # tmux could not say whether a server runs: a problem, and carry on
            report.problems.append(f"tmux socket {socket}: {unknown.reason}")
    report.problems.extend(leak_check(run, check_roots=False))
    if remove_roots:
        for root in run_roots(run):
            shutil.rmtree(root)
        left = run_roots(run)
        if left:
            report.problems.append(f"run roots not removed: {left}")
    return report


def leak_check(run: RunContext, *, check_roots: bool = True) -> list[str]:
    """env-plan §9 "Leak check": processes, tmux sockets, listening ports, roots."""
    problems: list[str] = []
    for spelling in paths.TMP_SPELLINGS:
        pattern = f"{spelling}/{paths.RUN_ROOT_PREFIX}{run.pid}-"
        try:
            hits = [(pid, cmd) for pid, cmd in hostprobe.pgrep(pattern) if "pgrep" not in cmd]
        except hostprobe.ProbeUnknown as error:
            problems.append(f"leak probe for {pattern} could not answer (unknown is not clean): {error}")
            continue
        if hits:
            problems.append(f"processes still reference {pattern}: {hits[:10]}")
    left = our_tmux_sockets(run)
    if left:
        problems.append(f"tmux sockets of this run still present: {left}")
    for port in printed_ports(run):
        try:
            listening = hostprobe.port_listener_pids(port)
        except hostprobe.ProbeUnknown as error:
            problems.append(f"port probe for {port} could not answer (unknown is not clean): {error}")
            continue
        if listening:
            problems.append(f"port {port} (printed by a controld of this run) is still listening")
    if check_roots:
        roots = run_roots(run)
        if roots:
            problems.append(f"run roots still present: {roots}")
    return problems


def printed_ports(run: RunContext) -> list[int]:
    """Every port a controld of this run printed, from the instance logs."""
    ports: set[int] = set()
    for root in run_roots(run):
        logs = root / "logs"
        if not logs.exists():
            continue
        for log in logs.glob("controld*.out"):
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"^controld: http://127\.0\.0\.1:(\d+) · ", line)
                if match:
                    ports.add(int(match.group(1)))
    return sorted(ports)


@dataclass
class SweepResult:
    removed_roots: list[str] = field(default_factory=list)
    removed_sockets: list[str] = field(default_factory=list)
    live_owners: list[str] = field(default_factory=list)
    orphans_stopped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def pid_alive(pid: int) -> bool:
    return hostprobe.process_args(pid) is not None


def sweep_dead_runs() -> SweepResult:
    """Pre-run: remove `shq6-*` roots and `shepherd-m3-q6*` sockets whose owner is dead.

    A root or socket whose owning pid is **alive** is left alone and reported
    (another run, or ours): env-plan §3 makes that BLOCKED, not ours to judge.
    Only dead owners' state is touched, and a dead owner's tmux server (if any
    still runs) is killed on its own socket only — through the pattern check
    with *that* pid.
    """
    result = SweepResult()
    for root in sorted(TMP_CANONICAL.glob(f"{paths.RUN_ROOT_PREFIX}*")):
        match = RUN_DIR_RE.match(root.name)
        if not match:
            continue
        owner = int(match.group(1))
        if pid_alive(owner):
            result.live_owners.append(str(root))
            continue
        if match.group(2) == "0":
            # A dead run's children can outlive it (a crashed runner, H6): stop exactly the ones
            # its own ledger recorded and whose start token still matches, before its root goes.
            stopped, notes = stop_entries(ledger_entries(root / "pids.jsonl"), f"orphan of dead run {owner}:")
            result.orphans_stopped.extend(stopped)
            result.notes.extend(notes)
        shutil.rmtree(root)
        result.removed_roots.append(str(root))
    for name in hostprobe.tmux_socket_listing():
        match = Q6_SOCKET_RE.match(name)
        if not match:
            continue
        owner = int(match.group(1))
        if pid_alive(owner):
            result.live_owners.append(f"tmux:{name}")
            continue
        if tmuxctl.server_running(name, owner):
            tmuxctl.kill_server(name, owner)
        socket_path = paths.TMUX_SOCKET_DIR / name
        if socket_path.exists():
            socket_path.unlink()
        result.removed_sockets.append(name)
    return result
