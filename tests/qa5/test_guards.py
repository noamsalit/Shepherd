"""The harness's own guards, exercised — because an unreached guard is a claim.

`grep -rn "pytest.raises" tests/qa5/` returned nothing before this file existed.
Every refusal this package writes — `_argv`'s three, `_check_name`'s `:`,
`_alive`'s pid floor, `sweep`'s live-pid stop — was unreached code in every run,
and two of them were **wrong**: `"kill-server" in words` waved `kill-serv`
through, and `any(word == "-L")` waved `-Lshepherd` through. A guard nothing
drives is indistinguishable from a guard that does not work, which is the same
property this harness asserts about the product.

**Every check here is pure.** No run root, no daemon, no browser, no tmux
server: the guards refuse at construction, which is the whole point of putting
them there. The `pure` marker is what keeps the session fixture from dragging
the environment up behind a file that needs none of it.

**Nothing planted here is executable harm.** The refusal cases are *strings*
handed to a function that raises before any `subprocess` exists — `_argv`
returns a list or raises, and this file never runs what it builds. The one
liveness probe uses `os.getppid()`, a pid that is already alive, and `_alive`
delivers signal 0, which delivers nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from . import runroot, tmuxctl
from .constants import PANES, QA_SOCKET
from .runroot import HarnessBlocked

pytestmark = pytest.mark.pure


# ----- _argv: the teardown verb, at every spelling tmux resolves --------------
#
# tmux 3.4 on this host resolves an unambiguous command-name **prefix**, so all
# four of these reach `kill-server`. The first is the only one a membership test
# ever caught; `tmux -L <socket> kill-serv` returns rc=0 and the server is gone.
@pytest.mark.parametrize("spelling", ["kill-server", "kill-serve", "kill-serv", "kill-ser"])
def test_argv_refuses_every_prefix_that_reaches_kill_server(spelling: str) -> None:
    with pytest.raises(HarnessBlocked, match="kill-server"):
        tmuxctl._argv(spelling)


def test_argv_refuses_the_fused_socket_option() -> None:
    """`-Lshepherd` is one word. An equality test against `"-L"` does not see it,
    and the word it does not see is the user's own socket."""
    with pytest.raises(HarnessBlocked, match="socket is set here"):
        tmuxctl._argv("-Lshepherd", "list-sessions")


def test_argv_refuses_the_separate_socket_option() -> None:
    with pytest.raises(HarnessBlocked, match="socket is set here"):
        tmuxctl._argv("-L", "shepherd", "list-sessions")


def test_argv_refuses_an_empty_invocation() -> None:
    with pytest.raises(HarnessBlocked, match="no command"):
        tmuxctl._argv()


def test_argv_requires_the_command_name_to_lead() -> None:
    """The teardown predicate answers about a *command-name position*. If an
    option could lead, the position would be unknown and the guard would be
    reading the wrong word."""
    with pytest.raises(HarnessBlocked, match="command name must lead"):
        tmuxctl._argv("-d", "new-session")


def test_argv_accepts_an_ordinary_invocation_and_pins_the_socket() -> None:
    """The negative control. A guard that refuses everything is not a guard, and
    the three refusals above would pass just as happily against one."""
    assert tmuxctl._argv("list-sessions", "-F", "#{session_name}") == [
        "tmux",
        "-L",
        QA_SOCKET,
        "list-sessions",
        "-F",
        "#{session_name}",
    ]
    # `kill-session` is not `kill-server` at any prefix, and refusing it would
    # take teardown's only tool away.
    assert tmuxctl._argv("kill-session", "-t", f"={PANES[0]}:")[3] == "kill-session"
    # A payload that merely *begins* like the verb is not in a command-name
    # position and must not be refused: a guard with false positives on ordinary
    # work is a guard somebody turns off.
    assert tmuxctl._argv("send-keys", "-t", f"={PANES[0]}:", "kill the build", "Enter")[-2] == (
        "kill the build"
    )


# ----- _check_name: the separator tmux silently rewrites ----------------------
def test_check_name_refuses_a_colon() -> None:
    """tmux reserves `:` as the `session:window` separator, rewrites the name,
    and `-t name:win` then resolves to a *different* session."""
    with pytest.raises(HarnessBlocked, match="may not contain"):
        tmuxctl._check_name("shepherd_r5a:0")


def test_check_name_accepts_the_names_this_harness_mints() -> None:
    for pane in PANES:
        assert tmuxctl._check_name(pane) == pane


# ----- _alive: the pid floor -------------------------------------------------
@pytest.mark.parametrize("pid", [1, 0, -1])
def test_alive_refuses_the_pids_a_signal_must_never_reach(pid: int) -> None:
    """`0`, `1` and `-1` are the process group, init, and every process. Signal
    0 delivers nothing, so this refusal cannot itself cause what it prevents —
    the same property `tests/test_signal_guard.py` proves of the runtime net."""
    with pytest.raises(HarnessBlocked, match="refusing to probe pid"):
        runroot._alive(pid)


def test_alive_answers_true_for_a_pid_that_is_running() -> None:
    """The negative control: without it the refusals above are satisfied by a
    function that raises unconditionally."""
    assert runroot._alive(os.getpid()) is True


def test_alive_answers_false_for_a_pid_that_is_not() -> None:
    """A pid above the system maximum cannot exist, so no live process can be
    probed by accident and no signal is delivered to a stranger."""
    ceiling = Path("/proc/sys/kernel/pid_max")
    unused = int(ceiling.read_text().strip()) + 1 if ceiling.exists() else 2**30
    assert runroot._alive(unused) is False


# ----- sweep: the concurrent run it must not delete --------------------------
def test_sweep_stops_at_a_run_root_belonging_to_a_live_pid(tmp_path: Path) -> None:
    """A survivor whose pid is **alive** is a concurrent run, not a leak.

    The live pid used is this process's own parent — already running, never
    signalled, and nothing is started to produce it. The assertion that matters
    is the second one: the directory is still there. A sweep that raised *after*
    deleting would satisfy `pytest.raises` and have destroyed the other run's
    evidence anyway.

    The raise happens in the `session_scratch` pass, which is first, so `/tmp`
    is never reached and no real leftover is touched by this test.
    """
    live = os.getppid()
    assert live > 1, "this test needs a real parent pid to stand in for a concurrent run"
    victim = tmp_path / f"qa5-{live}"
    victim.mkdir()
    (victim / "evidence.txt").write_text("a concurrent run's run root", encoding="utf-8")

    with pytest.raises(HarnessBlocked, match=f"belongs to live pid {live}"):
        runroot.sweep(tmp_path, live_pid=os.getpid())

    assert victim.is_dir(), "sweep must STOP, not delete and then complain"
    assert (victim / "evidence.txt").exists()


def test_sweep_removes_a_run_root_whose_pid_is_gone(tmp_path: Path) -> None:
    """The negative control, and the behaviour the guard above must not break.

    Only `/tmp` is globbed for `shq5-` and this run root is under `tmp_path`, so
    the removal proved here is of a directory this test made and named.
    """
    ceiling = Path("/proc/sys/kernel/pid_max")
    dead = int(ceiling.read_text().strip()) + 7 if ceiling.exists() else 2**30 + 7
    leaked = tmp_path / f"qa5-{dead}"
    leaked.mkdir()
    # A name that matches neither glob must survive: never remove an entry you
    # did not name.
    bystander = tmp_path / "somebody-elses-directory"
    bystander.mkdir()

    removed = runroot.sweep(tmp_path, live_pid=os.getpid())

    assert str(leaked) in removed, removed
    assert not leaked.exists()
    assert bystander.is_dir(), "sweep removed an entry it did not name"
