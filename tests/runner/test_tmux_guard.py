"""ADR-M3-8: the blast-radius invariant, at the one place the argv is a value.

This is the **load-bearing** net. The three AST rules in
`tests/boundaries/test_tmux_blast_radius.py` are a cheap second net that catches
the honest mistake at edit time; `check_tmux_argv` catches the dishonest one at
exec time, because by then no amount of concatenation, aliasing or f-string
assembly can hide what is about to be handed to the operating system.

**Why the binary and the verb are assembled from halves here.** This module is
inside the tree the AST rules scan, and a test that proves a refusal has to
*write down* the argv being refused. Spelling `"tmux"` and `"kill-server"` as
literals would make this file its own first violation — and a boundary rule that
cries wolf gets an exemption added to it, which is the death ADR-1 describes,
reached from the other side. The assembly is also the point: it is precisely the
one-liner that defeats an AST rule and does not defeat this one.

**No tmux process is started by this module, and no socket is contacted.** The
predicate is pure: argv in, refusal or nothing out.
"""

from __future__ import annotations

import pytest

from shepherd.core.runner import RunnerRefusal
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    SHELL_COMMAND_VERBS,
    FORBIDDEN_SOCKET,
    TARGET_RE,
    THROWAWAY_SOCKET_RE,
    VERSION_ARGV,
    check_tmux_argv,
    permitted_commands,
    permitted_sockets,
)

#: Assembled from halves — see the module docstring. `TMUX` carries the value
#: `tmux` and leaves no string constant equal to it anywhere in this file.
TMUX = "tm" + "ux"
KILL_SERVER = "kill" + "-server"

THROWAWAY = "shepherd-m3-live"
PERMITTED = permitted_sockets(DEFAULT_SOCKET, THROWAWAY)

#: T8-3's command allow-list for this exec site. `cat` is the runner's own
#: (`pipe-pane -o -t <target> 'cat >> <sink>'`) and is the only program this
#: product composes into a tmux command argument.
COMMANDS = permitted_commands("cat")


def argv(*words: str) -> list[str]:
    """One tmux argv, headed by the assembled binary name."""
    return [TMUX, *words]


def refusal(candidate: list[str], *, permitted: frozenset[str] = PERMITTED) -> str:
    """Assert `candidate` is refused **and not repaired**; return the reason."""
    before = list(candidate)
    with pytest.raises(RunnerRefusal) as raised:
        check_tmux_argv(candidate, permitted=permitted, commands=COMMANDS)
    assert candidate == before, "check_tmux_argv repaired the argv instead of refusing it"
    return raised.value.reason


def test_an_argv_without_L_is_refused_at_the_exec_site() -> None:
    """CLAUDE.md rule 3: `-L` on the session is not enough, it goes on every call.

    An argv with no `-L` resolves against `$TMUX` — the inherited socket — which
    is exactly 2026-09-12's blast radius. The three shapes below are the three
    ways it happens: no flag at all, the flag somewhere other than first, and the
    flag present but with nothing after it.
    """
    for candidate in (
        argv("list-sessions"),
        argv("ls"),
        argv("kill-session", "-t", "=shepherd_x:"),
        argv("-f", "/dev/null", "-L", THROWAWAY, "ls"),
        argv("-L"),
        [TMUX],
    ):
        reason = refusal(candidate)
        assert "CLAUDE.md" in reason and "18" in reason, reason

    # …and the refusal is a refusal, never a repair: nothing in this module can
    # produce an argv that acquired a `-L` on its way through the predicate.
    candidate = argv("list-sessions")
    with pytest.raises(RunnerRefusal):
        check_tmux_argv(candidate, permitted=PERMITTED, commands=COMMANDS)
    assert "-L" not in candidate


def test_the_socket_shepherd_is_never_permitted() -> None:
    """The user's live sessions are on `shepherd`. Nothing may name it.

    Two halves, because either alone is defeatable: `permitted_sockets` refuses
    to *build* a set containing it, and `check_tmux_argv` refuses the socket
    itself even when handed a raw `frozenset` that was never built here — K16's
    "whatever configuration says".
    """
    with pytest.raises(RunnerRefusal) as raised:
        permitted_sockets(DEFAULT_SOCKET, FORBIDDEN_SOCKET)
    assert FORBIDDEN_SOCKET in raised.value.reason

    reason = refusal(
        argv("-L", FORBIDDEN_SOCKET, "ls"),
        permitted=frozenset({FORBIDDEN_SOCKET}),  # smuggled past the constructor
    )
    assert FORBIDDEN_SOCKET in reason

    # An unpermitted socket that is not the user's is refused too — the rule is
    # an allow-list, not a deny-list of one name.
    assert refusal(argv("-L", "shepherd-somewhere-else", "ls")) != ""

    # …and the permitted ones are allowed, so the test is not vacuously red.
    check_tmux_argv(argv("-L", DEFAULT_SOCKET, "ls"), permitted=PERMITTED, commands=COMMANDS)
    check_tmux_argv(argv("-L", THROWAWAY, "ls"), permitted=PERMITTED, commands=COMMANDS)


def test_kill_server_is_refused_off_a_throwaway_socket() -> None:
    """K6-a's relaxation, bounded: `^shepherd-m3-` and nothing else.

    `shepherd-runner` is the product's own socket (D49) and is **permitted for
    every other verb** — which is what makes this assertion about the verb rather
    than about the socket.
    """
    reason = refusal(argv("-L", DEFAULT_SOCKET, KILL_SERVER))
    assert KILL_SERVER in reason and DEFAULT_SOCKET in reason

    # The relaxation itself: the same verb on a throwaway socket is allowed.
    check_tmux_argv(argv("-L", THROWAWAY, KILL_SERVER), permitted=PERMITTED, commands=COMMANDS)

    # A socket that merely *starts like* a throwaway is not one.
    for near_miss in ("shepherd-m3", "shepherd-m3-", "xshepherd-m3-live"):
        with pytest.raises(RunnerRefusal):
            check_tmux_argv(
                argv("-L", near_miss, KILL_SERVER), permitted=frozenset({near_miss}), commands=COMMANDS
            )

    # …and the verb is caught wherever in the argv it sits, not only last.
    assert refusal(argv("-L", DEFAULT_SOCKET, KILL_SERVER, ";", "ls")) != ""


def test_the_teardown_verb_is_caught_by_every_prefix_tmux_resolves_to_it() -> None:
    """The verb is a **property of tmux's command table**, not a spelling.

    Measured on this host (tmux 3.4, socket `shepherd-m3-verify`, torn down):
    `tmux -L <sock> kill-serv` returns `rc=0` and the server is gone. tmux
    resolves an unambiguous command-name prefix, so `"kill-server" in argv`
    was a membership test over one spelling of a verb that has eleven — the
    same class of mistake as `argv[0] == "tmux"` (T8-2), and the one
    `_shell_verb` already refused to make for the shell-executing verbs while
    §18's own verb kept it.

    Blast radius, exactly: `shepherd` is unreachable by every spelling because
    the socket rule runs first. What a prefix reached is `shepherd-runner` —
    the product's own server, i.e. **every owned session at once**.
    """
    # Every prefix, ambiguous ones included: `kill-s` is also a prefix of
    # `kill-session`, so tmux would call it ambiguous and refuse — refusing it
    # here too costs an argv tmux would reject anyway, and the predicate does
    # not have to mirror tmux's command table to stay safe.
    spellings = [KILL_SERVER[:n] for n in range(1, len(KILL_SERVER) + 1)]
    assert "kill-serv" in spellings and "kill-serve" in spellings and "kill-s" in spellings
    for spelling in spellings:
        reason = refusal(argv("-L", DEFAULT_SOCKET, spelling))
        assert spelling in reason and KILL_SERVER in reason, reason

    # Behind tmux's own command separator, where a first allowed verb hides it.
    assert refusal(argv("-L", DEFAULT_SOCKET, "list-sessions", ";", "kill-serv")) != ""

    # K6-a is unchanged: the relaxation is about the socket, so every spelling
    # of the verb is still allowed on a throwaway one.
    for spelling in ("kill-serv", "kill-serve", KILL_SERVER):
        check_tmux_argv(argv("-L", THROWAWAY, spelling), permitted=PERMITTED, commands=COMMANDS)


def test_no_verb_this_product_issues_is_a_prefix_of_the_teardown_verb() -> None:
    """The negative control, and the reason the rule can be this wide.

    `kill-session` is the verb `terminate` builds and is **not** a prefix of
    `kill-server`; nor is any other verb `runner/local.py` issues. Read off the
    code rather than remembered: a guard with false positives on ordinary work
    gets turned off (T8-3), so the list is the product's own.
    """
    issued = (
        "has-session", "new-session", "kill-session", "send-keys", "capture-pane",
        "pipe-pane", "set-option", "display-message", "list-sessions", "ls",
    )
    for verb in issued:
        assert not KILL_SERVER.startswith(verb), verb
        check_tmux_argv(argv("-L", DEFAULT_SOCKET, verb), permitted=PERMITTED, commands=COMMANDS)

    # And the other direction: a word that merely *contains* the verb is not a
    # command-name position. `spawn_argv` puts the operator's brief in an argv
    # word, and a session briefed "kill the server" is ordinary work (T8-3's
    # explicitly rejected rule, still rejected).
    check_tmux_argv(
        argv("-L", DEFAULT_SOCKET, "send-keys", "-t", "=shepherd_01J:", "kill", "kill-serv"),
        permitted=PERMITTED,
        commands=COMMANDS,
    )


def test_a_loose_target_is_refused_at_the_exec_site() -> None:
    """CLAUDE.md rule 4 made mechanical, from the other end.

    `-t name` matches by prefix and `-t name:0` addresses a window, so both can
    resolve to a *different* session than the caller meant. Only the exact
    `=name:` form is accepted.
    """
    for loose in ("shepherd_x", "shepherd_x:0", "=shepherd_x", "shepherd_x:", "=shepherd_x:0"):
        reason = refusal(argv("-L", DEFAULT_SOCKET, "send-keys", "-t", loose, "hi"))
        assert loose in reason, reason

    check_tmux_argv(
        argv("-L", DEFAULT_SOCKET, "send-keys", "-t", "=shepherd_01J:", "hi"),
        permitted=PERMITTED, commands=COMMANDS,
    )
    # Every `-t` is checked, not just the first.
    assert (
        refusal(
            argv(
                "-L", DEFAULT_SOCKET, "swap-pane", "-t", "=shepherd_a:", "-t", "shepherd_b"
            )
        )
        != ""
    )


def test_tmux_V_is_the_only_argv_allowed_without_a_socket_and_it_matches_by_equality() -> None:
    """`tmux -V` contacts no server, so it is the one socket-less argv allowed.

    Matched by **list equality, never by prefix**: a prefix match would readmit
    `["tmux", "-V", ";", "kill-server"]`, and the exception would then be the
    hole the rule exists to close.
    """
    assert VERSION_ARGV == (TMUX, "-V")
    check_tmux_argv(list(VERSION_ARGV), permitted=PERMITTED, commands=COMMANDS)

    # The empty permitted set proves the allowance does not come from the socket.
    check_tmux_argv(list(VERSION_ARGV), permitted=frozenset(), commands=COMMANDS)

    for extended in ([*VERSION_ARGV, "ls"], [*VERSION_ARGV, ";", KILL_SERVER]):
        assert refusal(extended) != ""


def test_a_non_tmux_argv_passes_through_untouched() -> None:
    """The guard is about one binary. It never becomes a general argv policeman.

    A rule that starts refusing `git` gets turned off, and the thing that gets
    turned off with it is the one that matters.

    **`/usr/bin/tmux` moved out of this list in T8-2 and it moved *down*, not
    away.** It was asserted here as innocent, and it is not: it is the same
    binary, on the same socket, with the same blast radius, spelled differently —
    which is acceptance clause 1's "the guarantee is on the argv, not on a
    spelling" failing inside the test that was supposed to guard it. The binary
    is now recognised by basename, so the row is asserted as a **refusal**;
    `tests/boundaries/test_tmux_binary_spelling.py` carries the full table at the
    exec site.
    """
    for innocent in (
        ["git", "status"],
        ["claude", "--version"],
        [],
        ["screen", "-L", FORBIDDEN_SOCKET, KILL_SERVER],
        ["my" + TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER],  # a different program
    ):
        check_tmux_argv(innocent, permitted=PERMITTED, commands=COMMANDS)

    # …and the binary under any spelling is **not** innocent, whatever the
    # `argv[0]` string says. The refusal names the socket, so it is the
    # blast-radius rule that fired and not some incidental one.
    reason = refusal(["/usr/bin/" + TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER])
    assert FORBIDDEN_SOCKET in reason and "/usr/bin/" + TMUX in reason, reason
    assert refusal(["./" + TMUX, "-L", FORBIDDEN_SOCKET, KILL_SERVER]) != ""


def test_permitted_sockets_refuses_a_name_that_is_not_a_socket_name() -> None:
    """The allow-list is built from names, not from arbitrary strings.

    A socket name carrying a `:`, a space or a shell metacharacter is never a
    thing this repo owns, and admitting one would put an unreadable value in
    every later refusal message.
    """
    for bad in ("shepherd:runner", "shepherd runner", "", "shepherd/runner", "../shepherd"):
        with pytest.raises(RunnerRefusal):
            permitted_sockets(bad)
    with pytest.raises(RunnerRefusal):
        permitted_sockets()

    assert permitted_sockets(DEFAULT_SOCKET) == frozenset({DEFAULT_SOCKET})


def test_the_two_regexes_are_anchored_at_both_ends() -> None:
    """An unanchored `TARGET_RE` or `THROWAWAY_SOCKET_RE` is the whole defect.

    Read off the pattern strings themselves, because the predicate is not the
    only consumer: T8 and T24 read these constants too.
    """
    for pattern in (TARGET_RE, THROWAWAY_SOCKET_RE):
        assert pattern.startswith("^") and pattern.endswith("$"), pattern


# ----- T8-3: the command-bearing arguments ------------------------------------


#: The command this product actually composes into a tmux argv, and the only
#: member of `COMMANDS` above: `LocalRunner.attach` builds
#: `pipe-pane -o -t <target> 'cat >> <sink>'` (`runner/local.py`), and the sink
#: is already confined by `SINK_PATH_RE` for exactly the reason this rule
#: exists — C4 says the string is re-read by a shell.
SINK_COMMAND = "cat >> /var/lib/shepherd/panes/shepherd_01J.pipe"

#: What `sh -c` would be handed if the hole were still open. Rides a socket that
#: is **permitted**, so no other rule in the predicate has anything to say.
PAYLOAD = f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}"


def test_a_shell_executing_verb_refuses_a_command_it_does_not_recognise() -> None:
    """T8-3, class 1: the guard scanned argv *elements*, so `sh -c` was invisible.

    `"kill-server" in argv` is a membership test over **elements**; a payload
    word *containing* the verb never matches it, and neither does the socket
    rule, which reads `argv[2]` and finds a socket that is genuinely permitted.
    Every row below was measured THROUGH against the shipped guard (T8-3's
    table, reproduced by the router).
    """
    for candidate in (
        argv("-L", DEFAULT_SOCKET, "run-shell", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "new-session", "-d", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "new-session", "-d", "sh", "-c", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "new-session", "-d", "-s", "shepherd_01J", "-c", "/tmp", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "if-shell", PAYLOAD, "ls"),
        argv("-L", DEFAULT_SOCKET, "pipe-pane", "-o", "-t", "=shepherd_01J:", PAYLOAD),
        # The command inside the *server* region, before any verb at all.
        argv("-L", DEFAULT_SOCKET, "-c", PAYLOAD),
    ):
        reason = refusal(candidate)
        assert "sh -c" in reason, reason


def test_the_command_is_recognised_behind_every_spelling_of_its_verb() -> None:
    """A verb matched by full name only is `argv[0] == "tmux"` again (T8-2).

    tmux resolves an unambiguous **prefix** and accepts each command's **alias**,
    so `neww`, `new-s` and `run` all reach a shell. And a verb can sit behind
    tmux's command separator, which this host was measured on: a word that is
    `;`, or that *ends* in `;`, starts a new command.
    """
    for spelling in ("run-shell", "run", "new-session", "new", "new-s", "neww", "splitw"):
        assert refusal(argv("-L", DEFAULT_SOCKET, spelling, PAYLOAD)) != "", spelling

    for separated in (
        argv("-L", DEFAULT_SOCKET, "list-sessions", ";", "run-shell", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "list-sessions;", "run-shell", PAYLOAD),
        argv("-L", DEFAULT_SOCKET, "send-keys", "-t", "=shepherd_01J:", "hi", ";", "run", PAYLOAD),
    ):
        assert refusal(separated) != ""


def test_the_allow_list_is_matched_by_basename_and_admits_no_second_program() -> None:
    """Two constraints, because either alone is walked past.

    The first token names the program, by **basename** — `/bin/sh` is `sh`, the
    same lesson T8-2 learned about the tmux binary from the other end. The whole
    argument is then confined to `COMMAND_ARG_RE`, because `cat >> x; <anything>`
    passes an `argv[0]` allow-list by construction: one permitted program in
    front of an unlisted one.
    """
    check_tmux_argv(
        argv("-L", DEFAULT_SOCKET, "pipe-pane", "-o", "-t", "=shepherd_01J:", SINK_COMMAND),
        permitted=PERMITTED,
        commands=COMMANDS,
    )
    for refused in (
        "/bin/sh -c ls",
        "sh",
        "bash -c ls",
        "env cat",
        SINK_COMMAND + "; " + PAYLOAD,
        SINK_COMMAND + " && " + PAYLOAD,
        SINK_COMMAND + " | " + PAYLOAD,
        "$(" + PAYLOAD + ")",
        "cat $(id)",
        "CAT=1 cat /x",
    ):
        assert refusal(argv("-L", DEFAULT_SOCKET, "run-shell", refused)) != "", refused

    # …and an absolute spelling of an allow-listed program is the same program.
    check_tmux_argv(
        argv("-L", DEFAULT_SOCKET, "run-shell", "/bin/cat /x"),
        permitted=PERMITTED,
        commands=COMMANDS,
    )
    # …while a program whose name merely ends in one is not (T8-2's lesson).
    assert refusal(argv("-L", DEFAULT_SOCKET, "run-shell", "mycat /x")) != ""


def test_the_shell_executing_verbs_are_the_manuals_own_list() -> None:
    """The population is enumerated, and the count is asserted in the same run.

    A table that silently shrinks is the defect this repo keeps finding, so the
    cases below are **derived from the table** and the number of them is
    compared with the table's own length. The list itself came from this host's
    manual (tmux 3.4) rather than from memory — the enumerating command is in
    `docs/plans/2026-09-17-m3-BLOCKERS.md` under T8-3.
    """
    assert set(SHELL_COMMAND_VERBS) == {
        "detach-client",
        "display-popup",
        "if-shell",
        "new-session",
        "new-window",
        "pipe-pane",
        "respawn-pane",
        "respawn-window",
        "run-shell",
        "split-window",
    }

    checked: set[str] = set()
    for name, verb in SHELL_COMMAND_VERBS.items():
        words = (
            ["-" + verb.command_flag, PAYLOAD]
            if verb.command_flag is not None
            else [PAYLOAD]
        )
        assert refusal(argv("-L", DEFAULT_SOCKET, name, *words)) != "", name
        assert refusal(argv("-L", DEFAULT_SOCKET, verb.alias, *words)) != "", verb.alias
        checked.add(name)
    assert len(checked) == len(SHELL_COMMAND_VERBS) == 10, checked


def test_the_production_argvs_are_not_refused_by_the_new_rule() -> None:
    """The negative control: a guard with false positives on ordinary work gets
    turned off, and what gets turned off with it is the rule that matters.

    These are the argvs `runner/local.py` really builds — `ensure_server`'s
    bootstrap, `start`'s `new-session` with the engine's own words, `attach`'s
    `pipe-pane`, and the verbs that carry no command at all.
    """
    engine = permitted_commands("cat", "claude")
    for allowed in (
        argv("-L", DEFAULT_SOCKET, "has-session", "-t", "=shepherd_01J:"),
        argv("-L", DEFAULT_SOCKET, "new-session", "-d", "-s", "shepherd_01J"),
        argv(
            "-L", DEFAULT_SOCKET, "new-session", "-d", "-s", "shepherd_01J",
            "-c", "/root/my work/repo", "-x", "160", "-y", "45",
            "-e", "SHEPHERD_SESSION_ID=01J", "-e", "PATH=/usr/bin:/bin",
            "claude", "--model", "opus", "--append-system-prompt",
            "fix the tmux bug; then run the tests",
        ),
        argv("-L", DEFAULT_SOCKET, "pipe-pane", "-o", "-t", "=shepherd_01J:", SINK_COMMAND),
        argv("-L", DEFAULT_SOCKET, "pipe-pane", "-t", "=shepherd_01J:"),
        argv("-L", DEFAULT_SOCKET, "send-keys", "-H", "-t", "=shepherd_01J:", "68", "69"),
        argv("-L", DEFAULT_SOCKET, "capture-pane", "-e", "-p", "-t", "=shepherd_01J:"),
        argv("-L", DEFAULT_SOCKET, "set-option", "-w", "-t", "=shepherd_01J:", "remain-on-exit", "on"),
        argv("-L", DEFAULT_SOCKET, "kill-session", "-t", "=shepherd_01J:"),
    ):
        check_tmux_argv(allowed, permitted=PERMITTED, commands=engine)


def test_permitted_commands_refuses_anything_that_is_not_a_program_name() -> None:
    """The allow-list is built from basenames, never from paths or fragments.

    An exec site with **no** permitted command is legitimate and is the
    strictest setting — it may still run every tmux verb that executes nothing —
    so an empty set is a value here, unlike `permitted_sockets()`.
    """
    for bad in ("/bin/cat", "cat /x", "cat;ls", "", "ca*"):
        with pytest.raises(RunnerRefusal):
            permitted_commands(bad)

    assert permitted_commands() == frozenset()
    assert permitted_commands("cat", "claude") == frozenset({"cat", "claude"})

    # An exec site that permits nothing refuses the product's own sink command,
    # which is what makes the allow-list the thing deciding and not the parser.
    with pytest.raises(RunnerRefusal):
        check_tmux_argv(
            argv("-L", DEFAULT_SOCKET, "run-shell", SINK_COMMAND),
            permitted=PERMITTED,
            commands=permitted_commands(),
        )
