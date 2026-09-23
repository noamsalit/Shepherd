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
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import paths

TIMEOUT_S = 15.0


def run(argv: list[str], timeout_s: float = TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False)


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
    done = run([str(paths.PGREP_BIN), "-fl", pattern])
    found: list[tuple[int, str]] = []
    for line in done.stdout.splitlines():
        head, _, rest = line.partition(" ")
        if head.isdigit() and int(head) != os.getpid():
            found.append((int(head), rest))
    return found


def pgrep_exact(name: str) -> list[int]:
    done = run([str(paths.PGREP_BIN), "-x", name])
    return [int(line) for line in done.stdout.split() if line.isdigit()]


def port_listener_pids(port: int) -> list[int]:
    """Pids listening on TCP `port`, read with `lsof` (no connect)."""
    done = run([str(paths.LSOF_BIN), "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return sorted({int(line) for line in done.stdout.split() if line.isdigit()})


def listen_addresses(pid: int) -> list[str]:
    """`lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN` → the NAME column values."""
    done = run([str(paths.LSOF_BIN), "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"])
    return [line[1:] for line in done.stdout.splitlines() if line.startswith("n")]


def open_files(pid: int) -> list[str]:
    """Every NAME `lsof -p <pid> -Fn` reports (regular files, sockets, dirs)."""
    done = run([str(paths.LSOF_BIN), "-nP", "-p", str(pid), "-Fn"])
    return [line[1:] for line in done.stdout.splitlines() if line.startswith("n")]


def process_cwd(pid: int) -> str | None:
    done = run([str(paths.LSOF_BIN), "-a", "-d", "cwd", "-p", str(pid), "-Fn"])
    for line in done.stdout.splitlines():
        if line.startswith("n"):
            return os.path.realpath(line[1:])
    return None


def process_env(pid: int) -> dict[str, str]:
    """`ps eww -o command= -p <pid>`: the argv followed by `NAME=value` words.

    macOS prints the environment after the command on one line; values with
    spaces are ambiguous, so the parse takes each `NAME=` token as the start of
    a variable and reads to the next such token.
    """
    done = run([str(paths.PS_BIN), "eww", "-o", "command=", "-p", str(pid)])
    line = done.stdout.strip()
    found: dict[str, str] = {}
    for match in re.finditer(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=(.*?)(?=\s[A-Za-z_][A-Za-z0-9_]*=|$)", line):
        found[match.group(1)] = match.group(2)
    return found


def process_args(pid: int) -> str | None:
    done = run([str(paths.PS_BIN), "-o", "args=", "-p", str(pid)])
    text = done.stdout.strip()
    return text or None


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
    port_owner_pids: list[int]
    shepherd_daemons: list[tuple[int, str]]

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
            "port_owner_pids": self.port_owner_pids,
            "shepherd_daemons": [[pid, cmd] for pid, cmd in self.shepherd_daemons],
        }


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
        port_owner_pids=port_listener_pids(paths.FORBIDDEN_PORT),
        shepherd_daemons=pgrep("shepherd-controld|shepherd-sessiond"),
    )


def write_baseline(path: Path, baseline: Baseline) -> None:
    path.write_text(json.dumps(baseline.as_json(), indent=1, sort_keys=True), encoding="utf-8")


def read_baseline(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} is not a JSON object")
    return {str(key): value for key, value in decoded.items()}
