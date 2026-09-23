"""Every tmux invocation this harness makes, and the guard that shapes them.

Copied from `tests/qa5/tmuxctl.py` (re-proved by the planted mutation
`fixtures/mutations/tmuxctl.json`, env-plan §4 step 1a) and changed in three
ways, each forced by the qa6 topology:

1. **The socket is a parameter, and it must match this run's pattern.** qa5
   used one fixed `shepherd-qa`; qa6 has one socket per controld instance,
   `shepherd-m3-q6<pid>-<k>` (Difference 7), plus W5's `…-0`. `_argv` refuses
   any socket that does not match `^shepherd-m3-q6<run pid>-\\d+$`, so the
   user's `shepherd` socket and `default` are unreachable by construction.
2. **The binary is absolute** (`/opt/homebrew/bin/tmux`), so the harness's own
   calls never pass through the logging shim, and Z2 reads the shim log as
   exactly what the product ran.
3. **`kill-server` exists here, on our sockets only** (env-plan §9 step 5): the
   product's `^shepherd-m3-` pattern permits it and teardown needs a backstop
   for a server the product left behind. Every other spelling of the teardown
   verb (tmux prefix-resolves command names, so `kill-serv` reaches it) is
   still refused through the product's own `is_server_teardown`.

`tmux -V` is the one argv without `-L`; it contacts no server.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from shepherd.runner.tmux_cmd import is_server_teardown

from . import paths
from .verdict import Blocked

TIMEOUT_S = 15.0
PANE_COLS, PANE_ROWS = 160, 45


@dataclass(frozen=True)
class TmuxResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def socket_allowed(socket: str, run_pid: int) -> bool:
    """True only for this run's `shepherd-m3-q6<pid>-<k>` sockets."""
    return re.fullmatch(paths.runner_socket_pattern(run_pid).pattern, socket) is not None


def _argv(socket: str, run_pid: int, *words: str, allow_kill_server: bool = False) -> list[str]:
    """`<abs tmux> -L <socket> <words>`, with every refusal made at construction."""
    if not words:
        raise Blocked("a tmux invocation with no command")
    if not socket_allowed(socket, run_pid):
        raise Blocked(f"refusing tmux socket {socket!r}: only this run's shepherd-m3-q6{run_pid}-<k> sockets")
    fused = [word for word in words if word.startswith("-L") or word.startswith("-S")]
    if fused:
        raise Blocked(f"the socket is set here, once; -L/-S in the words is refused: {fused!r}")
    if words[0].startswith("-"):
        raise Blocked(f"the tmux command name must lead: {words!r}")
    if is_server_teardown(words[0]):
        if not (allow_kill_server and words == ("kill-server",)):
            raise Blocked(f"{words[0]!r} spells kill-server; only kill_server() may, on our socket")
    return [str(paths.TMUX_BIN), "-L", socket, *words]


#: The environment a harness-started tmux server gets: nothing inherited from
#: the runner (which runs inside Claude Code), and never `TMUX`.
MINIMAL_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "TERM": "xterm-256color",
    "HOME": "/nonexistent-qa6-tmux-home", "SHELL": "/bin/sh",
}


def run(
    socket: str,
    run_pid: int,
    *words: str,
    check: bool = True,
    timeout_s: float = TIMEOUT_S,
    env: Mapping[str, str] | None = None,
) -> TmuxResult:
    argv = _argv(socket, run_pid, *words)
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False,
                          env=dict(env) if env is not None else dict(MINIMAL_ENV))
    result = TmuxResult(tuple(argv), done.returncode, done.stdout, done.stderr)
    if check and done.returncode != 0:
        raise Blocked(f"{argv!r} exited {done.returncode}: {done.stderr.strip()!r}")
    return result


def run_bytes(socket: str, run_pid: int, *words: str) -> bytes:
    argv = _argv(socket, run_pid, *words)
    done = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, check=False, env=dict(MINIMAL_ENV))
    if done.returncode != 0:
        raise Blocked(f"{argv!r} exited {done.returncode}: {done.stderr!r}")
    return done.stdout


def version() -> str:
    done = subprocess.run([str(paths.TMUX_BIN), "-V"], capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    if done.returncode != 0:
        raise Blocked(f"tmux -V exited {done.returncode}")
    return done.stdout.strip()


def _check_name(name: str) -> str:
    if ":" in name:
        raise Blocked(f"a tmux session name may not contain ':': {name!r}")
    return name


def target(name: str) -> str:
    """The exact-session target form `=<name>:` (never a prefix match)."""
    return f"={_check_name(name)}:"


def server_running(socket: str, run_pid: int) -> bool:
    done = run(socket, run_pid, "list-sessions", "-F", "#{session_name}", check=False)
    return done.returncode == 0


def sessions(socket: str, run_pid: int) -> list[str]:
    done = run(socket, run_pid, "list-sessions", "-F", "#{session_name}", check=False)
    if done.returncode != 0:
        lowered = done.stderr.lower()
        if "no server running" in lowered or "error connecting" in lowered or "no such file" in lowered:
            return []
        raise Blocked(f"list-sessions exited {done.returncode}: {done.stderr.strip()!r}")
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def kill_server(socket: str, run_pid: int) -> TmuxResult:
    """Teardown backstop: `kill-server` on **our** socket only (env-plan §9 step 5)."""
    argv = _argv(socket, run_pid, "kill-server", allow_kill_server=True)
    done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False, env=dict(MINIMAL_ENV))
    return TmuxResult(tuple(argv), done.returncode, done.stdout, done.stderr)


def socket_file(socket: str) -> str:
    return str(paths.TMUX_SOCKET_DIR / socket)
