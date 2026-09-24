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

import os
import re
import shutil
import signal
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.host.mac import MacHost

from . import hostprobe, paths, tmuxctl
from .jsonl import read_objects
from .pool import close_tmux_socket
from .sandbox import TMP_CANONICAL, RunContext
from .verdict import Blocked

RUN_DIR_RE = re.compile(rf"^{re.escape(paths.RUN_ROOT_PREFIX)}(\d+)-(\d+)$")
Q6_SOCKET_RE = re.compile(r"^shepherd-m3-q6(\d+)-(\d+)$")


@dataclass
class LeakReport:
    """Filled IN PLACE as teardown goes (hunter N5): a step that raises keeps what earlier steps found."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: Every pid this teardown sent a signal to (review N5: Z3 fails if one was a baseline pid).
    signalled: list[int] = field(default_factory=list)


#: `<run_dir>/teardown-signalled.json`: the runner's teardown writes every pid it signalled.
SIGNALLED_FILE = "teardown-signalled.json"


def ledger_entries(pid_ledger: Path, problems: list[str]) -> list[dict[str, object]]:
    """The ledger's entries; a torn line (a child killed mid-append) goes to `problems`, never
    raises (hunter N5): one bad line must not orphan every child the other lines name."""
    read = read_objects(pid_ledger)
    problems.extend(f"pid ledger: {problem}" for problem in read.problems)
    return read.rows


def recorded_pids(run: RunContext, problems: list[str]) -> list[dict[str, object]]:
    return ledger_entries(run.pid_ledger, problems)


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


def stop_entries(entries: list[dict[str, object]], label: str, sink: LeakReport) -> None:
    """SIGTERM (then SIGKILL) every entry that is provably ours and alive, recording into `sink`
    as it goes (each leak is appended BEFORE its signal, so nothing found is lost to a later raise)."""
    for entry in entries:
        pid = entry.get("pid")
        if not isinstance(pid, int):
            continue
        token_now = current_token(pid)
        why_not = signal_decision(entry, token_now)
        if why_not is not None:
            if token_now is not None and why_not != "not alive":
                sink.notes.append(f"{label} pid {pid} ({entry.get('kind')}) alive but not signalled: {why_not}")
            continue
        sink.problems.append(f"{label} {entry.get('kind')} pid {pid} still alive at teardown (start token matched)")
        _signal(pid, signal.SIGTERM, sink)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _still_ours(entry):
            time.sleep(0.1)
        if _still_ours(entry):
            _signal(pid, signal.SIGKILL, sink)
            if _still_ours(entry):
                sink.problems.append(f"{label} {entry.get('kind')} pid {pid} survived SIGKILL")


def _signal(pid: int, signum: signal.Signals, sink: LeakReport) -> None:
    """Signal a pid `signal_decision` just cleared; one that exited in between is not an error (H6)."""
    if pid not in sink.signalled:
        sink.signalled.append(pid)
    try:
        os.kill(pid, signum)
    except ProcessLookupError:
        return


def stop_recorded(run: RunContext, sink: LeakReport) -> None:
    """Every recorded child still alive and still ours (by start token). Each is a leak."""
    stop_entries(recorded_pids(run, sink.problems), "recorded", sink)


def our_tmux_sockets(run: RunContext) -> list[str]:
    found: list[str] = []
    for name in hostprobe.tmux_socket_listing():
        match = Q6_SOCKET_RE.match(name)
        if match and int(match.group(1)) == run.pid:
            found.append(name)
    return sorted(found)


def run_roots(run: RunContext) -> list[Path]:
    return sorted(TMP_CANONICAL.glob(f"{paths.RUN_ROOT_PREFIX}{run.pid}-*"))


TeardownStep = tuple[str, Callable[[LeakReport], None]]


def run_steps(report: LeakReport, steps: list[TeardownStep]) -> LeakReport:
    """Run every step against the SAME report (hunter N5): a step that raises is recorded as a
    problem, what it and earlier steps already appended stays, and the next step still runs."""
    for name, action in steps:
        try:
            action(report)
        except Exception as error:  # noqa: BLE001 - recorded as a teardown problem, never swallowed
            report.problems.append(f"teardown step {name!r} raised {type(error).__name__}: {error}")
    return report


def _close_our_sockets(run: RunContext, report: LeakReport) -> None:
    for socket in our_tmux_sockets(run):
        report.notes.append(f"backstop: tmux server/socket {socket} present at run teardown")
        try:
            report.problems.extend(close_tmux_socket(run, socket))
        except Blocked as unknown:  # tmux could not say whether a server runs: a problem, and carry on
            report.problems.append(f"tmux socket {socket}: {unknown.reason}")


def _remove_roots(run: RunContext, report: LeakReport) -> None:
    for root in run_roots(run):
        shutil.rmtree(root)
    left = run_roots(run)
    if left:
        report.problems.append(f"run roots not removed: {left}")


def teardown_run(run: RunContext, *, remove_roots: bool = True) -> LeakReport:
    """Stop leftovers, kill our tmux servers, check for leaks, remove the roots. Never raises."""
    steps: list[TeardownStep] = [
        ("stop recorded children", lambda report: stop_recorded(run, report)),
        ("close our tmux sockets", lambda report: _close_our_sockets(run, report)),
        ("leak check", lambda report: report.problems.extend(leak_check(run, check_roots=False))),
    ]
    if remove_roots:
        steps.append(("remove run roots", lambda report: _remove_roots(run, report)))
    return run_steps(LeakReport(), steps)


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
    #: A torn ledger line of a dead run (the runner records these as teardown problems).
    problems: list[str] = field(default_factory=list)


def pid_alive(pid: int) -> bool:
    """`ps` says alive. A `ps` that cannot answer raises `hostprobe.ProbeUnknown` (hunter N6)."""
    return hostprobe.process_args(pid) is not None


def owner_dead(pid: int) -> tuple[bool, str]:
    """(dead?, why) for a run root's or socket's owner. Only a `ps` that ANSWERED "no such pid" is
    dead; a probe that could not answer is a live owner (hunter N6): the sweep never removes
    state on an unknown."""
    try:
        alive = pid_alive(pid)
    except hostprobe.ProbeUnknown as unknown:
        return False, f"owner {pid} unknown (treated as live): {unknown}"
    return (not alive), ("owner dead" if not alive else f"owner {pid} alive")


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
        dead, why = owner_dead(owner)
        if not dead:
            result.live_owners.append(f"{root} ({why})")
            continue
        if match.group(2) == "0":
            # A dead run's children can outlive it (a crashed runner, H6): stop exactly the ones
            # its own ledger recorded and whose start token still matches, before its root goes.
            sink = LeakReport()
            stop_entries(ledger_entries(root / "pids.jsonl", result.problems), f"orphan of dead run {owner}:", sink)
            result.orphans_stopped.extend(sink.problems)
            result.notes.extend(sink.notes)
        shutil.rmtree(root)
        result.removed_roots.append(str(root))
    for name in hostprobe.tmux_socket_listing():
        match = Q6_SOCKET_RE.match(name)
        if not match:
            continue
        owner = int(match.group(1))
        dead, why = owner_dead(owner)
        if not dead:
            result.live_owners.append(f"tmux:{name} ({why})")
            continue
        if tmuxctl.server_running(name, owner):
            tmuxctl.kill_server(name, owner)
        socket_path = paths.TMUX_SOCKET_DIR / name
        if socket_path.exists():
            socket_path.unlink()
        result.removed_sockets.append(name)
    return result
