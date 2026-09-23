"""Run-level teardown, leak checks, and the pre-run sweep of dead runs.

Every step verifies its own result and reports a problem instead of swallowing
it (a run that leaks is a passing run **plus a leak**, and a leak blocks GREEN;
env-plan §9). Signals go only to pids this run recorded in its ledger **and**
whose current argv still matches what was recorded (a reused pid is never
signalled). `kill-server` goes only through `tmuxctl.kill_server`, which refuses
any socket outside this run's pattern.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import hostprobe, paths, tmuxctl
from .pool import close_tmux_socket
from .sandbox import TMP_CANONICAL, RunContext

RUN_DIR_RE = re.compile(rf"^{re.escape(paths.RUN_ROOT_PREFIX)}(\d+)-(\d+)$")
Q6_SOCKET_RE = re.compile(r"^shepherd-m3-q6(\d+)-(\d+)$")


@dataclass
class LeakReport:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def recorded_pids(run: RunContext) -> list[dict[str, object]]:
    if not run.pid_ledger.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in run.pid_ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, dict):
                entries.append({str(k): v for k, v in decoded.items()})
    return entries


def _still_ours(pid: int, argv: object) -> bool:
    """The pid is alive AND its argv still starts with what we recorded."""
    current = hostprobe.process_args(pid)
    if current is None:
        return False
    if isinstance(argv, list) and argv:
        return current.startswith(str(argv[0])) or os.path.basename(str(argv[0])) in current.split(" ")[0]
    return False


def stop_recorded(run: RunContext) -> list[str]:
    """SIGTERM (then SIGKILL) any recorded child still alive. Each is a leak."""
    problems: list[str] = []
    for entry in recorded_pids(run):
        pid = entry.get("pid")
        if not isinstance(pid, int) or pid in (0, 1, -1):
            continue
        if not _still_ours(pid, entry.get("argv")):
            continue
        problems.append(f"recorded {entry.get('kind')} pid {pid} still alive at run teardown")
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _still_ours(pid, entry.get("argv")):
            time.sleep(0.1)
        if _still_ours(pid, entry.get("argv")):
            os.kill(pid, signal.SIGKILL)
    return problems


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
    report.problems.extend(stop_recorded(run))
    for socket in our_tmux_sockets(run):
        report.notes.append(f"backstop: tmux server/socket {socket} present at run teardown")
        report.problems.extend(close_tmux_socket(run, socket))
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
        hits = [(pid, cmd) for pid, cmd in hostprobe.pgrep(pattern) if "pgrep" not in cmd]
        if hits:
            problems.append(f"processes still reference {pattern}: {hits[:10]}")
    left = our_tmux_sockets(run)
    if left:
        problems.append(f"tmux sockets of this run still present: {left}")
    for port in printed_ports(run):
        if hostprobe.port_listener_pids(port):
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
