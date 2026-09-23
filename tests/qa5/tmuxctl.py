"""Every tmux invocation this harness makes, and the guard that shapes them.

**`-L shepherd-qa` is `argv[1]` on every call.** Not a habit — `argv` is built
here and nowhere else, and `_argv` refuses to emit a command that does not carry
it. `tmux -V` is the single exception and it contacts no server.

**There is no `kill-server` in this harness at any blast radius** (router
decision RD-QA5-1). Teardown kills panes by name and then *asserts the socket is
empty*, which proves the same property and cannot be copied into a context where
the `-L` is missing. The verb that cost three live sessions on 2026-09-12 is not
written down here even correctly.

**The user's own socket is never named**, never passed to a command, and never
enumerated — not even as a gate. A check written as "`tmux -L <theirs> ls` shows
exactly N names" goes red the next time they open a terminal.

**No session name contains `:`.** tmux reserves it as the `session:window`
separator and silently rewrites the name, after which `-t name:win` resolves to a
*different* session.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from shepherd.runner.tmux_cmd import is_server_teardown

from .constants import PANE_COLS, PANE_ROWS, QA_SOCKET
from .runroot import HarnessBlocked

TIMEOUT_S = 15.0


@dataclass(frozen=True)
class TmuxResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def _argv(*words: str) -> list[str]:
    """`tmux -L shepherd-qa <words>`, with both refusals made at construction.

    **The teardown verb is refused by the product's own predicate, not by a
    restatement of the rule.** `"kill-server" in words` is a membership test over
    one of eleven spellings: tmux resolves an unambiguous command-name *prefix*,
    so `kill-serv` reaches `kill-server` and a membership test waves it through —
    measured on this host, `rc=0` and the server is gone. `src/shepherd/runner/
    tmux_cmd.py` already found, fixed and documented exactly this defect, and
    `is_server_teardown` is public *because* `tests/boundaries/` reads it too. A
    third copy of the property is how a property becomes three spellings that
    disagree, so this one is imported.

    **Position is the caller's job, and here the caller is this module.** The
    predicate answers about a word in a *command-name* position, which for every
    argv built here is `words[0]`; applying it to every word would refuse a
    `send-keys` payload that happened to begin with `k`, and a guard with false
    positives on ordinary work is a guard somebody turns off. So the command
    name is required to lead, and that requirement is itself asserted.

    **`-L` is refused by prefix too.** `any(word == "-L")` is the same shape of
    mistake one level down: `tmux -Lshepherd ls` is a fused short option and an
    equality test does not see it. The socket is set here, once.
    """
    if not words:
        raise HarnessBlocked("a tmux invocation with no command")
    fused = [word for word in words if word.startswith("-L")]
    if fused:
        raise HarnessBlocked(
            f"the socket is set here, once, and not by the caller — `-L` in any "
            f"spelling, fused or separate, is refused: {fused!r} in {words!r}"
        )
    if words[0].startswith("-"):
        raise HarnessBlocked(
            f"the tmux command name must lead, so the teardown guard can read the "
            f"command-name position: {words!r}"
        )
    if is_server_teardown(words[0]):
        raise HarnessBlocked(
            f"{words[0]!r} is a way of spelling kill-server (tmux prefix-resolves "
            f"command names); it is not available in this harness at any blast "
            f"radius (RD-QA5-1)"
        )
    if QA_SOCKET != "shepherd-qa":
        raise HarnessBlocked(f"refusing an unexpected socket name: {QA_SOCKET!r}")
    return ["tmux", "-L", QA_SOCKET, *words]


def run(*words: str, check: bool = True) -> TmuxResult:
    argv = _argv(*words)
    done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    result = TmuxResult(tuple(argv), done.returncode, done.stdout, done.stderr)
    if check and done.returncode != 0:
        raise HarnessBlocked(f"{argv!r} exited {done.returncode}: {done.stderr.strip()!r}")
    return result


def version() -> str:
    """`tmux -V` — the one argv legal without `-L`; it contacts no server."""
    done = subprocess.run(
        ["tmux", "-V"], capture_output=True, text=True, timeout=TIMEOUT_S, check=False
    )
    if done.returncode != 0:
        raise HarnessBlocked(f"tmux -V exited {done.returncode}")
    return done.stdout.strip()


def _check_name(name: str) -> str:
    if ":" in name:
        raise HarnessBlocked(f"a tmux session name may not contain ':': {name!r}")
    return name


def new_session(name: str) -> None:
    run(
        "new-session",
        "-d",
        "-s",
        _check_name(name),
        "-x",
        str(PANE_COLS),
        "-y",
        str(PANE_ROWS),
    )


def sessions() -> list[str]:
    """Every session on **our** socket. Empty when no server is running.

    A socket with no server is `no server running on ...` on stderr and a
    non-zero exit — a value, not a failure, and the distinction is what lets
    teardown assert emptiness rather than infer it.
    """
    done = run("list-sessions", "-F", "#{session_name}", check=False)
    if done.returncode != 0:
        lowered = done.stderr.lower()
        if "no server running" in lowered or "error connecting" in lowered:
            return []
        raise HarnessBlocked(f"list-sessions exited {done.returncode}: {done.stderr.strip()!r}")
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def kill_session(name: str, *, tolerate_missing: bool = True) -> TmuxResult:
    """`kill-session -t '=<name>:'` — exact match, never a prefix.

    The `=` prefix and the trailing `:` are the exact-session form. Without them
    tmux matches by prefix, and `shepherd_r5a` would match `shepherd_r5ab`.
    """
    done = run("kill-session", "-t", f"={_check_name(name)}:", check=False)
    if done.returncode != 0 and not tolerate_missing:
        raise HarnessBlocked(f"kill-session {name} exited {done.returncode}: {done.stderr!r}")
    if done.returncode != 0 and "can't find session" not in done.stderr.lower():
        if "no server running" not in done.stderr.lower():
            raise HarnessBlocked(f"kill-session {name} failed oddly: {done.stderr!r}")
    return done


def pane_geometry(name: str) -> tuple[int, int]:
    """The pane's own `#{pane_width}`/`#{pane_height}`, read from tmux."""
    done = run(
        "list-panes",
        "-t",
        f"={_check_name(name)}:",
        "-F",
        "#{pane_width} #{pane_height}",
    )
    first = done.stdout.splitlines()[0].split()
    return int(first[0]), int(first[1])


def capture_pane(name: str) -> bytes:
    """The pane's bytes, as `capture-pane -p` produces them."""
    argv = _argv("capture-pane", "-p", "-t", f"={_check_name(name)}:")
    done = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, check=False)
    if done.returncode != 0:
        raise HarnessBlocked(f"capture-pane {name} exited {done.returncode}")
    return done.stdout


def send_keys(name: str, text: str) -> None:
    run("send-keys", "-t", f"={_check_name(name)}:", text, "Enter")
