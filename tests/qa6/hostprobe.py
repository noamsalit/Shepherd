"""Read-only probes of the real host: hashes, listings, processes, ports.

Everything here is an argv list with a bounded timeout; nothing writes, and
nothing contacts the user's tmux servers (`default`, `shepherd`) — their state
is read from the socket directory listing and `pgrep`, never from a client
command (setup.md §4 correction 2). The forbidden port (R1) is read with `lsof` only; no
connect, no bind.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import paths

TIMEOUT_S = 15.0


class ProbeUnknown(RuntimeError):
    """A probe that could not answer. Never read as "nothing found" (hunter M3)."""


def run(argv: list[str], timeout_s: float = TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False)


def run_listing(argv: list[str]) -> str:
    """stdout of a `pgrep`/`lsof` listing. Exit 0 = found; exit 1 with an empty stderr = none
    (both tools' measured "no match" answer on this host); anything else is `ProbeUnknown`."""
    done = run(argv)
    if done.returncode == 0:
        return done.stdout
    if done.returncode == 1 and not done.stderr.strip() and not done.stdout.strip():
        return ""
    raise ProbeUnknown(f"{argv!r} exited {done.returncode}: stdout={done.stdout[:200]!r} stderr={done.stderr[:300]!r}")


def run_pid_probe(argv: list[str]) -> str | None:
    """stdout of a `ps -p <pid>` / `lsof -p <pid>` probe, `None` when the pid is gone (hunter N6).

    Measured on this host: `ps -o args= -p <dead pid>` and `lsof … -p <dead pid>` both exit 1 with
    empty stdout AND empty stderr. That, and only that, is "gone"; any other failure (an invalid
    pid, a timeout, a tool error on stderr) is `ProbeUnknown`, never read as "gone" or as clean.
    """
    try:
        done = run(argv)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProbeUnknown(f"{argv!r} could not run: {type(error).__name__}: {error}") from error
    if done.returncode == 0:
        return done.stdout
    if done.returncode == 1 and not done.stdout.strip() and not done.stderr.strip():
        return None
    raise ProbeUnknown(f"{argv!r} exited {done.returncode}: stdout={done.stdout[:200]!r} stderr={done.stderr[:300]!r}")


def sha256(path: Path) -> str:
    """The file's sha256, or `"absent"`. Opens read-only."""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except FileNotFoundError:
        return "absent"


def listing(directory: Path) -> dict[str, float]:
    """name → mtime for each direct child, or `{}` when absent."""
    try:
        return {child.name: child.lstat().st_mtime for child in directory.iterdir()}
    except FileNotFoundError:
        return {}


def mtime(path: Path) -> float | None:
    try:
        return path.lstat().st_mtime
    except FileNotFoundError:
        return None


def pgrep(pattern: str) -> list[tuple[int, str]]:
    """`pgrep -fl <pattern>` → (pid, command line), excluding this process."""
    found: list[tuple[int, str]] = []
    for line in run_listing([str(paths.PGREP_BIN), "-fl", pattern]).splitlines():
        head, _, rest = line.partition(" ")
        if head.isdigit() and int(head) != os.getpid():
            found.append((int(head), rest))
    return found


def pgrep_exact(name: str) -> list[int]:
    return [int(line) for line in run_listing([str(paths.PGREP_BIN), "-x", name]).split() if line.isdigit()]


def port_listener_pids(port: int) -> list[int]:
    """Pids listening on TCP `port`, read with `lsof` (no connect)."""
    listed = run_listing([str(paths.LSOF_BIN), "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return sorted({int(line) for line in listed.split() if line.isdigit()})


def listen_addresses(pid: int) -> list[str]:
    """`lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN` → the NAME column values."""
    listed = run_listing([str(paths.LSOF_BIN), "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"])
    return [line[1:] for line in listed.splitlines() if line.startswith("n")]


def open_files(pid: int) -> list[str]:
    """Every NAME `lsof -p <pid> -Fn` reports (regular files, sockets, dirs); `[]` = gone/unseen.
    A probe error is `ProbeUnknown` (hunter N6)."""
    listed = run_pid_probe([str(paths.LSOF_BIN), "-nP", "-p", str(pid), "-Fn"]) or ""
    return [line[1:] for line in listed.splitlines() if line.startswith("n")]


def process_cwd(pid: int) -> str | None:
    """The pid's cwd, `None` = gone/unseen. A probe error is `ProbeUnknown` (hunter N6)."""
    listed = run_pid_probe([str(paths.LSOF_BIN), "-a", "-d", "cwd", "-p", str(pid), "-Fn"]) or ""
    for line in listed.splitlines():
        if line.startswith("n"):
            return os.path.realpath(line[1:])
    return None


def process_env(pid: int) -> dict[str, str]:
    """`ps eww -o command= -p <pid>`: the argv followed by `NAME=value` words.

    macOS prints the environment after the command on one line; values with
    spaces are ambiguous, so the parse takes each `NAME=` token as the start of
    a variable and reads to the next such token.
    """
    line = (run_pid_probe([str(paths.PS_BIN), "eww", "-o", "command=", "-p", str(pid)]) or "").strip()
    found: dict[str, str] = {}
    for match in re.finditer(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=(.*?)(?=\s[A-Za-z_][A-Za-z0-9_]*=|$)", line):
        found[match.group(1)] = match.group(2)
    return found


def process_args(pid: int) -> str | None:
    """The pid's argv, `None` = gone (`ps` answered so). A probe error is `ProbeUnknown` (hunter N6),
    never "gone": a Z3 attribution or a sweep's "dead owner" must not rest on a failed `ps`."""
    text = (run_pid_probe([str(paths.PS_BIN), "-o", "args=", "-p", str(pid)]) or "").strip()
    return text or None


def process_table() -> str:
    """`ps -A -o pid=,ppid=,comm=` (comm LAST, so it is not truncated), through the checked runner."""
    listed = run_pid_probe([str(paths.PS_BIN), "-A", "-o", "pid=,ppid=,comm="])
    if listed is None:
        raise ProbeUnknown("ps -A answered nothing")
    return listed


def tmux_servers_from_table(table: str) -> list[int]:
    """Pids of tmux SERVERS in a `process_table` listing: a process named `tmux` whose parent is
    launchd (pid 1). Measured on this host (3.6a, macOS): a server daemonises to ppid 1; a client
    (`tmux attach`, `tmux ls`, the product's `new-session` call) has its caller as parent. Review N5:
    Z3 compares servers, never every tmux client the user opens or closes during a run."""
    servers: list[int] = []
    for line in table.splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        if os.path.basename(fields[2].strip()) == "tmux" and int(fields[1]) == 1:
            servers.append(int(fields[0]))
    return sorted(servers)


def tmux_server_pids() -> list[int]:
    return tmux_servers_from_table(process_table())


def signalled_baseline_pids(signalled: list[object], baseline: Mapping[str, object]) -> list[int]:
    """Pids a teardown signalled that were alive at baseline — the user's processes (review N5). Pure."""
    at_baseline: set[int] = set()
    for key in ("tmux_pids", "tmux_server_pids", "shepherd_daemons", "port_owner_pids"):
        values = baseline.get(key)
        for value in values if isinstance(values, list) else []:
            head = value[0] if isinstance(value, list) and value else value
            if isinstance(head, int):
                at_baseline.add(head)
    return sorted(pid for pid in signalled if isinstance(pid, int) and pid in at_baseline)


def tmux_socket_listing() -> dict[str, float]:
    return listing(paths.TMUX_SOCKET_DIR)


@dataclass(frozen=True)
class Baseline:
    """The host snapshot the run compares its teardown against (env-plan §4 step 2)."""

    settings_sha: str
    claude_projects: dict[str, float]
    claude_sessions: dict[str, float]
    shepherd_data: dict[str, float]
    real_tmpdir_shepherd: dict[str, float]
    claude_json_mtime: float | None
    tmux_dir: dict[str, float]
    tmux_user_sockets_present: dict[str, bool]
    tmux_pids: list[int]
    tmux_server_pids: list[int]
    port_owner_pids: list[int]
    shepherd_daemons: list[tuple[int, str]]
    local_tree: dict[str, list[object]]

    def as_json(self) -> dict[str, object]:
        return {
            "settings_sha": self.settings_sha,
            "claude_projects": self.claude_projects,
            "claude_sessions": self.claude_sessions,
            "shepherd_data": self.shepherd_data,
            "real_tmpdir_shepherd": self.real_tmpdir_shepherd,
            "claude_json_mtime": self.claude_json_mtime,
            "tmux_dir": self.tmux_dir,
            "tmux_user_sockets_present": self.tmux_user_sockets_present,
            "tmux_pids": self.tmux_pids,
            "tmux_server_pids": self.tmux_server_pids,
            "port_owner_pids": self.port_owner_pids,
            "shepherd_daemons": [[pid, cmd] for pid, cmd in self.shepherd_daemons],
            "local_tree": self.local_tree,
        }


#: INC-1 (review finding 3): the trees a real-HOME engine's installer and updater write. Read
#: with lstat/readlink only; their state at run START is the baseline (the dangling
#: `~/.local/bin/claude` is that state, not a change).
LOCAL_TREES: tuple[Path, ...] = (
    paths.REAL_HOME / ".local" / "bin",
    paths.REAL_HOME / ".local" / "share" / "claude",
    paths.REAL_HOME / ".local" / "state" / "claude",
)
LOCAL_TREE_CAP = 20000
#: Lock files the user's OWN running `claude` sessions create and remove under
#: `~/.local/state/claude/locks/<version>.lock` (measured: one per running version).
LOCK_DIR = ".local/state/claude/locks/"


def local_tree(roots: tuple[Path, ...] = LOCAL_TREES) -> dict[str, list[object]]:
    """`path relative to the real HOME` -> `[kind, mtime, link target]`, never following a link.

    A directory's own mtime is not recorded (the user's own sessions bump the
    lock directory's by creating and removing lock files); its entries are. A
    root that is absent is recorded as `["absent", None, None]`.
    """
    found: dict[str, list[object]] = {}
    pending = [root for root in roots]
    home = str(paths.REAL_HOME) + "/"
    while pending:
        current = pending.pop()
        name = str(current)[len(home):] if str(current).startswith(home) else str(current)
        try:
            info = current.lstat()
        except FileNotFoundError:
            found[name] = ["absent", None, None]
            continue
        if stat.S_ISLNK(info.st_mode):
            found[name] = ["link", info.st_mtime, os.readlink(current)]
        elif stat.S_ISDIR(info.st_mode):
            found[name] = ["dir", None, None]
            pending.extend(sorted(current.iterdir()))
        else:
            found[name] = ["file", info.st_mtime, None]
        if len(found) > LOCAL_TREE_CAP:
            raise ProbeUnknown(f"more than {LOCAL_TREE_CAP} entries under {roots}")
    return found


def local_tree_changes(start: Mapping[str, object], now: Mapping[str, object],
                       engine_version: str | None) -> tuple[dict[str, object], dict[str, object]]:
    """(changes, attributed) between two `local_tree` snapshots.

    A lock file `locks/<v>.lock` added or removed for a version other than this
    run's engine (`engine_version`) is the user's own running session and is
    `attributed`, not a change; every other difference (a name added or
    removed, a kind, an mtime, a link target) is a change.
    """
    changes: dict[str, object] = {}
    attributed: dict[str, object] = {}
    for name in sorted(set(start) | set(now)):
        before, after = start.get(name), now.get(name)
        if before == after:
            continue
        lock_version = name[len(LOCK_DIR):-len(".lock")] if name.startswith(LOCK_DIR) and name.endswith(".lock") else None
        if lock_version is not None and lock_version != engine_version and (before is None or after is None):
            attributed[name] = {"before": before, "after": after, "why": "the user's own session's lock"}
            continue
        changes[name] = {"before": before, "after": after}
    return changes, attributed


def real_tmpdir() -> Path:
    """The user's real `$TMPDIR` (the runner's own, before any redirect)."""
    return Path(os.environ.get("QA6_REAL_TMPDIR") or os.environ.get("TMPDIR") or "/tmp")


def snapshot() -> Baseline:
    return Baseline(
        settings_sha=sha256(paths.REAL_SETTINGS),
        claude_projects=listing(paths.REAL_CLAUDE_DIR / "projects"),
        claude_sessions=listing(paths.REAL_CLAUDE_DIR / "sessions"),
        shepherd_data=listing(paths.REAL_SHEPHERD_DATA),
        real_tmpdir_shepherd=listing(real_tmpdir() / "Shepherd"),
        claude_json_mtime=mtime(paths.REAL_CLAUDE_JSON),
        tmux_dir=tmux_socket_listing(),
        tmux_user_sockets_present={
            name: (paths.TMUX_SOCKET_DIR / name).exists() for name in paths.USER_TMUX_SOCKETS
        },
        tmux_pids=pgrep_exact("tmux"),
        tmux_server_pids=tmux_server_pids(),
        port_owner_pids=port_listener_pids(paths.FORBIDDEN_PORT),
        shepherd_daemons=pgrep("shepherd-controld|shepherd-sessiond"),
        local_tree=local_tree(),
    )


def write_baseline(path: Path, baseline: Baseline) -> None:
    path.write_text(json.dumps(baseline.as_json(), indent=1, sort_keys=True), encoding="utf-8")


def read_baseline(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} is not a JSON object")
    return {str(key): value for key, value in decoded.items()}


# ----- pure comparisons Z1/Z3 make between the baseline and the after-teardown snapshot (H7) ---------


SESSION_NAME = re.compile(r"^(\d+)\.")


def session_pid(name: str) -> int | None:
    """The pid a `~/.claude/sessions` entry (`<pid>.json`, `<pid>.<hash>.key`) is named for."""
    match = SESSION_NAME.match(name)
    return int(match.group(1)) if match else None


def claude_session_changes(start: Mapping[str, object], now: Mapping[str, object],
                           user_pids: set[int]) -> tuple[dict[str, object], dict[str, object]]:
    """(changes, attributed) between two `~/.claude/sessions` listings.

    An entry named for a pid in `user_pids` (a live claude the run did not
    start) is the user's own session writing its state file, and is
    `attributed`; every other difference is a change.
    """
    changes: dict[str, object] = {}
    attributed: dict[str, object] = {}
    for name in sorted(set(start) | set(now)):
        was, is_now = start.get(name), now.get(name)
        if was == is_now:
            continue
        if session_pid(name) in user_pids:
            attributed[name] = {"before": was, "after": is_now, "why": "the user's own live session"}
            continue
        changes[name] = {"before": was, "after": is_now}
    return changes, attributed


def user_session_pids(names: set[str], run_root: str) -> set[int]:
    """Pids named in `names` that are alive with a readable env outside `run_root`.

    A pid whose env cannot be read, or whose HOME / CLAUDE_CONFIG_DIR sits
    under the run root, is not the user's and stays a change.
    """
    found: set[int] = set()
    for pid in {pid for pid in map(session_pid, names) if pid is not None}:
        try:
            env = process_env(pid)
        except ProbeUnknown:
            continue
        if not env:
            continue
        homes = [os.path.realpath(env[key]) for key in ("HOME", "CLAUDE_CONFIG_DIR") if env.get(key)]
        if homes and not any(home.startswith(run_root) for home in homes):
            found.add(pid)
    return found


def listing_delta(before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
    """Names added, names removed, and names whose mtime moved, between two `listing`s."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    moved = {name: [before[name], after[name]] for name in sorted(set(before) & set(after)) if before[name] != after[name]}
    return {"added": added, "removed": removed, "mtime_moved": moved}


def pid_delta(before: list[object], after: list[object]) -> dict[str, list[int]]:
    """Pids present at baseline and gone after, and pids new after (from `[pid, …]` or `[[pid, cmd], …]`)."""
    def pids(values: list[object]) -> set[int]:
        found: set[int] = set()
        for value in values:
            head = value[0] if isinstance(value, list) and value else value
            if isinstance(head, int):
                found.add(head)
        return found

    was, now = pids(before), pids(after)
    return {"gone": sorted(was - now), "new": sorted(now - was)}
