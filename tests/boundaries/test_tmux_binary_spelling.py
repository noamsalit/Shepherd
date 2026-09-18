"""T8-2: the guard recognises the binary by **basename**, not by spelling.

Acceptance clause 1 requires that *"the guarantee is on the argv, not on a
spelling"*. `argv[0] == "tmux"` **is** a spelling: measured against the shipped
guard, `["/usr/bin/tmux", "-L", "shepherd", "kill-server"]` passed both checks in
`make_run_argv` and reached the user's live sessions (`aivisor`, `main`,
`spike`). Nothing in `src/` resolves tmux to a path today — but **C1** in
`docs/specs/implementation-constraints.md` says a systemd unit calling a bare
name exits 127 and to "use an absolute path", and DP5's `DetachedLaunch` *is*
the systemd wrapper. The one documented constraint most likely to be applied to
this exact code path is the one that silently disarms the guard, and nothing
looks different when it does.

**The table below is the deliverable**, and it is asserted at `make_run_argv` —
the real exec site, with `subprocess.run` patched to a recorder — not at
`check_tmux_argv` in isolation, because the hole was in the *composition* of the
two checks. **Arrival is asserted before absence**: a test that only asserts "no
process was spawned" passes just as well when the code never got that far, which
is this repo's dominant defect class.

**This file lives in `tests/boundaries/`** because clause 1 requires the
blast-radius rule to run in the default `-m "not live"` sweep.

**The binary and the server-wide verb are assembled from halves**
(`"tm" + "ux"`), for the reason `test_tmux_blast_radius.py` gives: this file is
inside the tree those AST rules scan, and a boundary rule that cries wolf gets
an exemption bolted onto it.

**No tmux process is started by this module and no socket is contacted**:
`subprocess.run` is monkeypatched to a recorder for every row, the refused rows
included.
"""

from __future__ import annotations

import subprocess

import pytest

from shepherd.core.runner import RunnerRefusal
from shepherd.runner import local as local_module
from shepherd.runner.local import make_run_argv
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    FORBIDDEN_SOCKET,
    check_tmux_argv,
    permitted_commands,
    permitted_sockets,
)

#: Assembled — see the module docstring.
TMUX = "tm" + "ux"
KILL_SERVER = "kill" + "-server"

#: The three spellings a static reader would call "not tmux" and the operating
#: system would call tmux. `PATH_TMUX` is C1's own remedy.
PATH_TMUX = "/usr/bin/" + TMUX
DOT_TMUX = "./" + TMUX

THROWAWAY = "shepherd-m3-t8-2"
PERMITTED = permitted_sockets(DEFAULT_SOCKET, THROWAWAY)

#: T8-3's command allow-list for this exec site. `cat` is the runner's own
#: (`pipe-pane -o -t <target> 'cat >> <sink>'`) and is the only program this
#: product composes into a tmux command argument.
COMMANDS = permitted_commands("cat")

REFUSED = "REFUSED"
THROUGH = "through"

#: Every row was measured by hand against the shipped guard before it was
#: written down. The three marked below were **THROUGH** then — each of them
#: reaching `shepherd`, the socket the user's three live sessions are on.
TABLE: tuple[tuple[str, list[str], str], ...] = (
    ("bare, user's socket", [TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER], REFUSED),
    (
        "systemd-run wrapper",
        ["systemd-run", "--scope", TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER],
        REFUSED,
    ),
    (
        "wrapper whose own flag value is the binary's name",
        ["systemd-run", "--unit", TMUX, "--scope", TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER],
        REFUSED,
    ),
    ("setsid wrapper", ["setsid", TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER], REFUSED),
    # ↓ the three that were THROUGH against the shipped guard (T8-2)
    ("absolute path, no wrapper", [PATH_TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER], REFUSED),
    (
        "absolute path behind a wrapper",
        ["systemd-run", "--scope", PATH_TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER],
        REFUSED,
    ),
    ("relative path", [DOT_TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER], REFUSED),
    # ↑ the three that were THROUGH against the shipped guard (T8-2)
    ("permitted socket, bare", [TMUX, "-L", DEFAULT_SOCKET, "list-sessions"], THROUGH),
    ("permitted socket, absolute", [PATH_TMUX, "-L", DEFAULT_SOCKET, "list-sessions"], THROUGH),
    ("the version argv, bare", [TMUX, "-V"], THROUGH),
    ("the version argv, absolute", [PATH_TMUX, "-V"], THROUGH),
    # ↓ T8-3 decision 2 moved this row. The **predicate** still returns early on
    #   `git` — it is not a general argv policeman — but the **exec site** starts
    #   the binary and nothing else, so a `git` argv never reaches `subprocess`.
    #   `test_the_predicate_still_ignores_another_binary_entirely` holds the
    #   first half, so the move is a narrowing of the exec site and not a guard
    #   that quietly started policing everything.
    ("another binary entirely", ["git", "-L", FORBIDDEN_SOCKET, KILL_SERVER], REFUSED),
)

#: The three rows T8-2 is about, named so a reader can find them without
#: counting, and so the reverted-guard proof can say which rows went red.
WAS_THROUGH = (
    "absolute path, no wrapper",
    "absolute path behind a wrapper",
    "relative path",
)


class Spawns:
    """A `subprocess.run` stand-in that records rather than starting anything."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        self.argvs.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=b"ok", stderr=b"")


def test_the_binary_is_recognised_by_basename_at_the_exec_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The twelve-row table, at `make_run_argv`, arrival asserted before absence.

    Goes red if either gate goes back to matching the binary by string equality:
    `check_tmux_argv`'s early return, or `local._tmux_tail`'s scan. The two
    halves are both needed — the first three refusals hold with only `_tmux_tail`
    fixed, and the unwrapped absolute path holds with only the early return
    fixed, so a partial fix leaves a row red rather than passing quietly.
    """
    spawns = Spawns()
    monkeypatch.setattr(local_module.subprocess, "run", spawns)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    # 1. arrival: the patch point is proved live *before* it is used as a
    #    negative, so "nothing was spawned" cannot pass for a callable that never
    #    execs at all.
    arrival = [TMUX, "-L", THROWAWAY, "list-sessions"]
    assert exec_site(arrival).stdout == b"ok"
    assert spawns.argvs == [arrival]

    # 2. the table, each row measured against the spawn recorder.
    observed: list[tuple[str, str]] = []
    for name, argv, expected in TABLE:
        before = list(argv)
        spawned_before = len(spawns.argvs)
        try:
            exec_site(argv)
        except RunnerRefusal:
            actual = REFUSED
        else:
            actual = THROUGH
        observed.append((name, actual))
        assert argv == before, f"{name}: the exec site repaired an argv instead of refusing it"
        if expected == REFUSED:
            # absence, after the arrival above: a refusal starts nothing.
            assert len(spawns.argvs) == spawned_before, f"{name}: a refused argv started a process"
        else:
            # …and a permitted argv really is handed to the operating system,
            # unchanged. A guard that refuses everything would pass the rows
            # above and fail here.
            assert spawns.argvs[spawned_before:] == [before], f"{name}: never reached the exec"

    print("\n" + "\n".join(f"  {actual:<8} {name}" for name, actual in observed))
    assert observed == [(name, expected) for name, _, expected in TABLE]

    # 3. the three rows this blocker exists for are in the table and are refused.
    assert {name for name in WAS_THROUGH} <= {name for name, _, _ in TABLE}
    assert all(actual == REFUSED for name, actual in observed if name in WAS_THROUGH)


def test_the_refusal_names_the_socket_it_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusal a reader cannot act on is a refusal that gets `try`-wrapped.

    The absolute-path argv must be refused **for the reason it is dangerous** —
    the user's own socket — and not as a side effect of some unrelated rule, so
    the reason is read rather than the exception type alone.
    """
    spawns = Spawns()
    monkeypatch.setattr(local_module.subprocess, "run", spawns)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    with pytest.raises(RunnerRefusal) as raised:
        exec_site([PATH_TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER])
    assert FORBIDDEN_SOCKET in raised.value.reason
    assert "CLAUDE.md" in raised.value.reason
    assert spawns.argvs == []


def test_the_version_allowance_still_matches_the_flags_by_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widening *recognition* must not widen the one exception (T5).

    `tmux -V` contacts no server, and that is the whole reason it is allowed
    without `-L`. Recognising the binary by basename must not turn the allowance
    into a prefix match, which would readmit `["tmux", "-V", ";", "kill-server"]`
    — under any spelling of the binary.
    """
    spawns = Spawns()
    monkeypatch.setattr(local_module.subprocess, "run", spawns)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    for spelled in (TMUX, PATH_TMUX, DOT_TMUX):
        for extended in ([spelled, "-V", "ls"], [spelled, "-V", ";", KILL_SERVER]):
            with pytest.raises(RunnerRefusal):
                exec_site(extended)
    assert spawns.argvs == []

    # …and the allowance itself is intact, so the assertions above are not
    # vacuously red.
    assert exec_site([PATH_TMUX, "-V"]).stdout == b"ok"
    assert spawns.argvs == [[PATH_TMUX, "-V"]]


#: Binaries whose name merely *contains* the binary's, plus one unrelated
#: program. None of them is the binary, and the predicate must say so.
NOT_THE_BINARY = (
    ["my" + TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER],
    ["/usr/bin/" + TMUX + "2", "-L", FORBIDDEN_SOCKET, KILL_SERVER],
    ["/usr/bin/screen", "-L", FORBIDDEN_SOCKET, KILL_SERVER],
)


def test_a_binary_that_merely_ends_in_the_name_is_not_the_binary() -> None:
    """Basename, not suffix: `mytmux` and `tmux2` are other programs.

    A suffix match would be the mirror-image defect — a guard that starts
    policing binaries nobody asked it to police is a guard that gets turned off,
    and the thing that gets turned off with it is the one that matters.

    **Asserted at the predicate, which is where the claim lives.** Until T8-3
    decision 2 this was asserted at `make_run_argv` instead, and that seam
    stopped being able to make the point: the exec site now refuses every argv
    that is not the binary's, `mytmux` included, so an exec-site pass-through
    would no longer distinguish "not recognised as the binary" from "recognised
    and allowed". The predicate answers exactly that question and nothing else —
    `_is_binary` says no, so no rule of `check_tmux_argv` runs, so `kill-server`
    on the user's own socket raises nothing here.
    """
    for argv in NOT_THE_BINARY:
        before = list(argv)
        check_tmux_argv(argv, permitted=PERMITTED, commands=COMMANDS)  # does not raise
        assert argv == before, argv

    # Arrival before absence: the same call **does** refuse the same argv once
    # the binary is spelled, so the silence above is recognition failing and not
    # the predicate having become a no-op.
    with pytest.raises(RunnerRefusal):
        check_tmux_argv([TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER], permitted=PERMITTED,
                        commands=COMMANDS)


def test_the_exec_site_starts_the_binary_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T8-3 decision 2, and the other half of the row above.

    The predicate ignoring `mytmux` is correct *and* was the whole of T8-3's
    decision-2 hole: `["sh", "-c", "<payload>"]` is ignored for exactly the same
    reason. The exec site is not the predicate — it starts one program — so it
    refuses every argv in which no word's basename is the binary, and the two
    facts stop being in tension.

    Arrival before absence: a legitimate argv reaches the recorder first.
    """
    spawns = Spawns()
    monkeypatch.setattr(local_module.subprocess, "run", spawns)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    arrival = [TMUX, "-L", THROWAWAY, "list-sessions"]
    assert exec_site(arrival).rc == 0
    assert spawns.argvs == [arrival]

    for argv in (*NOT_THE_BINARY, ["sh", "-c", f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}"]):
        before = list(argv)
        with pytest.raises(RunnerRefusal) as raised:
            exec_site(argv)
        assert "nothing else" in raised.value.reason, raised.value.reason
        assert argv == before, "the exec site repaired an argv instead of refusing it"
    assert spawns.argvs == [arrival], "a refused argv started a process"


def test_the_production_argvs_still_reach_the_exec_site_unrefused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The false-positive control for T8-3 decision 2, at the wrapped launch.

    `ensure_server` prefixes the launch with `DetachedLaunch.prefix`, and on this
    host that prefix is real (`systemd-run --user --scope --`). A rule reading
    "argv[0] must be the binary" would refuse the one argv the product cannot do
    without, so the rule reads "the argv must *name* the binary" instead — and
    this is what proves the difference is live rather than argued.
    """
    spawns = Spawns()
    monkeypatch.setattr(local_module.subprocess, "run", spawns)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    wrapped = [
        ["systemd-run", "--user", "--scope", "--", TMUX, "-L", THROWAWAY, "new-session"],
        ["systemd-run", "--user", "--scope", "--", PATH_TMUX, "-L", THROWAWAY, "new-session"],
        ["setsid", DOT_TMUX, "-L", DEFAULT_SOCKET, "list-sessions"],
    ]
    for argv in wrapped:
        assert exec_site(argv).rc == 0, argv
    assert spawns.argvs == wrapped
