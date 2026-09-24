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

`effective_socket` (pure, no tmux is run) is the **one** judge of which socket a
tmux argv reaches, by tmux 3.6a's own getopt rules (clustered flags, the last
`-L`, `-S` over `-L`, `$TMUX` only when neither is given). `argv_violation`
applies it for this run; the runner's post-lane Z2 scan, Z2's `tmux.argv`,
`tmux.kill_server_ours_only` and `tmux.pane_argv_effective_socket`, and the
wave-4 argv clauses all use it, and the logging shim (`shims/tmux.sh.in`)
implements the same rules and **refuses** — exits 97 without exec — any argv
whose effective socket is not this run's (a guard proves the shim and this
function agree on a planted battery, against a fake binary). The real engine
queries its own pane (`display-message -p`, `show -gv …`) with no `-L`, and
tmux resolves that through the pane's `$TMUX`; the shim logs those, with
`$TMUX`, to `run.pane_tmux_argv_log`.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
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


#: tmux 3.6a's own getopt string, read from the binary (`strings /opt/homebrew/bin/tmux`):
#: `2c:CDdf:hlL:NqS:T:uUvV`. The letters followed by `:` take a value.
TMUX_GETOPT: str = "2c:CDdf:hlL:NqS:T:uUvV"
_VALUED: frozenset[str] = frozenset(TMUX_GETOPT[i - 1] for i, ch in enumerate(TMUX_GETOPT) if ch == ":")
_FLAGS: frozenset[str] = frozenset(ch for ch in TMUX_GETOPT if ch != ":") - _VALUED
#: Options tmux handles inside its getopt loop by printing and exiting: no server is contacted.
_EXITS_IN_GETOPT: frozenset[str] = frozenset("Vh")
#: The prefix of every value `effective_socket` returns for an argv tmux itself would refuse.
INVALID = "<invalid"


def _socket_name(path: str) -> str:
    """A socket path's name if it lives in this uid's tmux socket dir, else the path itself."""
    directory = os.path.dirname(path)
    if directory and os.path.realpath(directory) == os.path.realpath(paths.TMUX_SOCKET_DIR):
        return os.path.basename(path)
    return path


def _words(argv: Sequence[str]) -> list[str]:
    """The argv without its program word (`tmux`, or any path ending in `/tmux`)."""
    if argv and (argv[0] == "tmux" or argv[0].endswith("/tmux")):
        return list(argv[1:])
    return list(argv)


def effective_socket(argv: Sequence[str], tmux_env: str | None) -> str | None:
    """The socket a tmux client would contact, by tmux 3.6a's own rules.

    tmux parses its global options with BSD `getopt(TMUX_GETOPT)`: flags may be
    clustered (`-2uL name`, `-uLname`), a valued option takes the rest of its
    word or else the next word (even one starting with `-`), parsing stops at
    the first non-option word or after `--`. `-S` and `-L` each keep their
    **last** value; `-S` (a path) beats `-L` (a name) whatever their order;
    `$TMUX` (`<path>,<pid>,<session>`) is read **only when neither** was given;
    else `default`. `-V` and `-h` print and exit inside the getopt loop, so an
    argv that reaches one of them contacts no server: `None`.

    A path in this uid's socket dir comes back as its name; any other path
    comes back whole (no socket pattern matches it). An argv tmux would refuse
    (an unknown option, a valued option with no value) comes back as
    `"<invalid: …>"`, which no pattern matches either.
    """
    words = _words(argv)
    label: str | None = None
    path: str | None = None
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--" or not word.startswith("-") or word == "-":
            break
        position = 1
        while position < len(word):
            letter = word[position]
            if letter in _VALUED:
                value = word[position + 1:]
                if not value:
                    index += 1
                    if index >= len(words):
                        return f"{INVALID}: -{letter} without a value>"
                    value = words[index]
                if letter == "L":
                    label = value
                elif letter == "S":
                    path = value
                break
            if letter in _EXITS_IN_GETOPT:
                return None
            if letter not in _FLAGS:
                return f"{INVALID}: unknown option -{letter}>"
            position += 1
        index += 1
    if path is not None:
        return _socket_name(path)
    if label is not None:
        return label
    if tmux_env and not tmux_env.startswith(","):
        return _socket_name(tmux_env.split(",", 1)[0])
    return "default"


def argv_violation(argv: Sequence[str], tmux_env: str | None, run_pid: int) -> str | None:
    """Why this tmux argv is not allowed for run `run_pid`, or `None` when it is.

    Allowed: exactly `tmux -V`, or an argv whose effective socket is one of this
    run's `shepherd-m3-q6<pid>-<k>`. Everything else is a violation — including
    an argv that would contact no server by another spelling (`-uV`, `-h`):
    the product never emits one, so it is flagged, never excused.
    """
    words = _words(argv)
    if words == ["-V"]:
        return None
    socket = effective_socket(argv, tmux_env)
    if socket is None:
        return f"contacts no server, but is not exactly `tmux -V`: {words!r}"
    if socket_allowed(socket, run_pid):
        return None
    return f"effective socket {socket!r} is not this run's shepherd-m3-q6{run_pid}-<k>"


def pane_argv_violations(entries: Sequence[Mapping[str, object]], run_pid: int) -> list[dict[str, object]]:
    """In-pane tmux calls (`{"argv", "tmux"}` records) whose effective socket is not this run's."""
    found: list[dict[str, object]] = []
    for entry in entries:
        raw = entry.get("argv")
        argv = [str(word) for word in raw] if isinstance(raw, list) else []
        tmux_env = entry.get("tmux")
        env_value = tmux_env if isinstance(tmux_env, str) else None
        why = argv_violation(argv, env_value, run_pid)
        if why is not None:
            found.append({"argv": argv, "tmux": tmux_env, "effective_socket": effective_socket(argv, env_value),
                          "why": why})
    return found


def product_argv_violations(lines: Sequence[Sequence[str]], run_pid: int) -> list[list[str]]:
    """Product (no `$TMUX`) argv lines whose effective socket is not this run's."""
    return [list(argv) for argv in lines if argv_violation(argv, None, run_pid) is not None]


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
    argv = [str(paths.TMUX_BIN), "-L", socket, *words]
    why = argv_violation(argv, None, run_pid)
    if why is not None:
        raise Blocked(f"refusing tmux argv {argv!r}: {why}")
    return argv


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


#: What tmux 3.6a prints when there is no server behind a socket (its only "not running" answers).
NO_SERVER_TEXT: tuple[str, ...] = ("no server running", "error connecting", "no such file")


def server_running(socket: str, run_pid: int) -> bool:
    """True/False only when tmux said so; any other failure is unknown (`Blocked`), never "not running"."""
    done = run(socket, run_pid, "list-sessions", "-F", "#{session_name}", check=False)
    if done.returncode == 0:
        return True
    if any(text in done.stderr.lower() for text in NO_SERVER_TEXT):
        return False
    raise Blocked(f"unknown tmux server state on {socket}: list-sessions exited {done.returncode}: {done.stderr.strip()!r}")


def sessions(socket: str, run_pid: int) -> list[str]:
    done = run(socket, run_pid, "list-sessions", "-F", "#{session_name}", check=False)
    if done.returncode != 0:
        if any(text in done.stderr.lower() for text in NO_SERVER_TEXT):
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
