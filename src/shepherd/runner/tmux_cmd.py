"""K6 made mechanical: one argv builder, and one predicate that refuses.

**Pure.** No `subprocess`, no `os`, no clock, no network — argv in, argv out, and
argv in, refusal or nothing out. The one place in `src/` that starts a tmux
process is `runner/local.py` (T8), and the callable it hands out runs
`check_tmux_argv` first.

## Why the guarantee lives at runtime and not in a lint

This repo has an incident behind it. On 2026-09-12 a bare `tmux kill-server` in
an M3 spike destroyed three live sessions including the one that issued it
(`docs/specs/orchestrator-platform.md` §18, and CLAUDE.md). Revision 1 of the M3
plan defended that with three AST rules, and two independent reviews found all
three were *spellings, not properties*: `["tm" + "ux", ...]` names no `tmux`,
`f"kill-{verb}"` names no `kill-server`, and `from .tmux_cmd import TMUX_BIN`
names neither — while producing an argv with **no `-L`**, which resolves against
the inherited `$TMUX` and is exactly the incident's blast radius.

`tests/boundaries/_taint.py` is in this tree because two earlier rules died the
same way, and its docstring is the finding: *a rule about a value has to follow
the value*. The argv is the value, so the check sits where the argv is a value —
at the exec site, on the real list, after every concatenation and alias has been
resolved by the interpreter itself.

## Refuse, never repair

`check_tmux_argv` raises. It never inserts a missing `-L`, never rewrites a
target, never substitutes a socket. A repair hides the bug that produced the
malformed argv, and it cannot know *which* socket was intended — and a wrong
guess here is the incident.

## The binary is recognised by basename, not by spelling (T8-2)

Clause 1 requires the guarantee to be *"on the argv, not on a spelling"*, and
`argv[0] == "tmux"` is a spelling: against the shipped guard,
`["/usr/bin/tmux", "-L", "shepherd", "kill-server"]` passed both checks at the
exec site. `_is_binary` compares the **basename**, and both gates use it — this
module's early return and `local.py`'s `_tmux_tail` scan. A recognised argv is
re-presented under the canonical name before the socket / `-t` / `kill-server`
rules run, so those rules never learn that a binary can be spelled more than one
way. The `-V` allowance keeps its equality match **on the flags**, so widening
recognition does not widen the one exception into a prefix match.

## K6-a: the one relaxation, and its bound

`kill-server` is permitted on a socket matching `THROWAWAY_SOCKET_RE` and nowhere
else. CLAUDE.md bans the verb *without* `-L`, and its rule 2 gives
`tmux -L shepherd-spike …` "teardown included" as the correct pattern; banning
the verb outright would be stricter than the rule it enforces, and that extra
strictness has a direction — a builder whose "assert no server" teardown fails,
forbidden the one idiom every shipped probe used, is pushed toward the **bare**
form that caused 2026-09-12. A rule that makes the safe idiom unavailable
manufactures pressure toward the unsafe one. The socket predicate is what keeps
the blast radius at a throwaway: `^shepherd-m3-` can never be `shepherd`, and can
never be `shepherd-runner`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from shepherd.core.runner import RunnerRefusal

#: D49. The product's own socket — never the user's.
DEFAULT_SOCKET = "shepherd-runner"

#: The user's own socket. Never permitted, by any configuration, on any argv, for
#: any verb. **The socket is the invariant; the session names on it are not** —
#: they were `aivisor`/`main`/`spike` until 2026-09-17 and are whatever the user
#: has open now, so nothing here or in any check names them (CLAUDE.md).
FORBIDDEN_SOCKET = "shepherd"

#: The one argv allowed without a socket: it contacts no server. Matched by
#: **list equality, never by prefix** — a prefix match would readmit
#: `["tmux", "-V", ";", <anything>]`.
VERSION_ARGV: tuple[str, ...] = ("tmux", "-V")

#: Spikes, probes and the live lane. The only sockets a server-wide teardown may
#: name (K6-a).
THROWAWAY_SOCKET_RE = r"^shepherd-m3-[A-Za-z0-9_-]+$"

#: §18's verb, canonically. **Read off this host's manual** (tmux 3.4,
#: `man tmux`), not remembered: `kill-server` takes no options and — unlike
#: `kill-pane` (`killp`), `kill-window` (`killw`) or `list-sessions` (`ls`) —
#: carries **no alias**, so its own name and its prefixes are the whole set of
#: words that reach it. `kill-session`, the verb `terminate` really issues, has
#: no alias either and is **not** a prefix of this one.
KILL_SERVER = "kill-server"

#: Empty, and empty as a **measurement**: the manual's `kill-server` entry has no
#: `(alias: …)` line. A tuple rather than nothing at all, because the day a tmux
#: version gives the verb an alias, this is the one place that fact goes.
KILL_SERVER_ALIASES: tuple[str, ...] = ()

#: The exact target form. `-t name` matches by prefix (so `shepherd_x` hits
#: `shepherd_x2`) and `-t name:0` addresses a window; both can resolve to a
#: different session than the caller meant (CLAUDE.md rule 4).
TARGET_RE = r"^=[A-Za-z0-9_-]+:$"

#: What a program on the command allow-list may be called: one basename, no
#: path separator, no shell metacharacter. `permitted_commands` refuses anything
#: else, so a refusal message can never carry an unreadable value.
COMMAND_NAME_RE = r"^[A-Za-z0-9_.-]+$"

#: What a **shell-executing verb's command argument** may contain, end to end.
#: The same mechanism `SINK_PATH_RE` already applies to `pipe-pane`'s sink
#: (`runner/local.py`), generalised to every verb that hands a string to
#: `/bin/sh`: `>` is here because the one command this product composes is
#: `cat >> <sink>`, and `;`, `&`, `|`, `$`, a backtick, a quote, a bracket and a
#: newline are **not**, because each of them turns one allow-listed program into
#: a second unlisted one. Positive, like `SINK_PATH_RE`: a deny-list of
#: metacharacters is a list of the ones its author thought of.
COMMAND_ARG_RE = r"^[A-Za-z0-9_./ >=:,+-]*$"

#: What a socket name and a session name may contain. The complement of this set
#: is what CLAUDE.md rule 4 is about: `:` is tmux's `session:window` separator and
#: `.` its `window.pane` one, so a name carrying either silently addresses
#: something else.
NAME_RE = r"^[A-Za-z0-9_-]+$"

SESSION_PREFIX = "shepherd_"
SOCKET_FLAG = "-L"
TARGET_FLAG = "-t"

_THROWAWAY = re.compile(THROWAWAY_SOCKET_RE)
_TARGET = re.compile(TARGET_RE)
_NAME = re.compile(NAME_RE)
_COMMAND_NAME = re.compile(COMMAND_NAME_RE)
_COMMAND_ARG = re.compile(COMMAND_ARG_RE)

#: tmux's own command separator, measured on this host (tmux 3.4) rather than
#: recalled: a word that **is** `;` starts a new command, and so does a word that
#: **ends** in `;` (the `;` is stripped and the rest stays with the current one).
#: A `;` in the middle of a word does not, and `\;` is a literal argument. So a
#: verb this module has never looked at can sit behind one, which is why the
#: scan below runs over every segment and not only the first.
COMMAND_SEPARATOR = ";"


@dataclass(frozen=True)
class _ShellVerb:
    """One tmux command that runs a shell command, and how to find its argument.

    `value_flags` is the set of option letters that consume a word, read off this
    host's own manual synopsis — getopt semantics, so `-ds foo` is `-d` plus
    `-s foo` and `-sfoo` is `-s foo`. Under-declaring a letter costs a false
    refusal on a verb this product never builds; over-declaring one would let the
    real command argument be skipped, so the table is copied from the synopsis
    rather than remembered.

    `command_flag` names the option that carries the command where it is not the
    first operand — `detach-client -E <shell-command>` is the only such verb.
    """

    alias: str
    value_flags: str
    command_flag: str | None = None


#: Every tmux command whose synopsis takes an `Ar shell-command`, enumerated from
#: **this host's own manual** (tmux 3.4, `/usr/share/man/man1/tmux.1.gz`) — the
#: command is recorded in `docs/plans/2026-09-17-m3-BLOCKERS.md` under T8-3. The
#: same enumeration also matched `copy-command`, `default-command`, `editor` and
#: `lock-command`, which are **options** rather than commands: their value is a
#: shell command executed later, by `set-option`. That is a different class and
#: it is written down as a named gap, not silently folded in here.
SHELL_COMMAND_VERBS: dict[str, _ShellVerb] = {
    "detach-client": _ShellVerb("detach", "Est", command_flag="E"),
    "display-popup": _ShellVerb("popup", "bcdehsStTwxy"),
    "if-shell": _ShellVerb("if", "t"),
    "new-session": _ShellVerb("new", "ceFfnstxy"),
    "new-window": _ShellVerb("neww", "ceFnt"),
    "pipe-pane": _ShellVerb("pipep", "t"),
    "respawn-pane": _ShellVerb("respawnp", "cet"),
    "respawn-window": _ShellVerb("respawnw", "cet"),
    "run-shell": _ShellVerb("run", "cdt"),
    "split-window": _ShellVerb("splitw", "celtF"),
}

#: The server options that take a value, from the same manual page's first
#: synopsis. `-c` is `tmux -c shell-command`: a shell command in the *server*
#: region, before any verb, which is the one that hides in plain sight.
SERVER_VALUE_FLAGS = "cfLST"
SERVER_COMMAND_FLAG = "c"

#: Every refusal carries it. A reader who has not read CLAUDE.md is one grep from
#: the reason, and a reader who has is reminded which rule they just hit.
WHY = (
    "CLAUDE.md rules 1-4 and §18's incident of 2026-09-12, when a bare "
    "tmux server-wide teardown destroyed three live sessions including the one "
    "that issued it"
)


def _refuse(reason: str) -> RunnerRefusal:
    return RunnerRefusal(f"{reason} — see {WHY}")


def _is_binary(word: str) -> bool:
    """Is `word` a way of naming the tmux binary? By **basename**, never by spelling.

    T8-2. `argv[0] == "tmux"` is a spelling, and clause 1 requires the guarantee
    to be on the argv: `["/usr/bin/tmux", "-L", "shepherd", "kill-server"]` is the
    same process, the same blast radius, and a different string. Nothing in `src/`
    resolves tmux to a path today, but **C1** (`implementation-constraints.md`)
    says a systemd unit calling a bare name exits 127 and to "use an absolute
    path" — and DP5's `DetachedLaunch` is that systemd wrapper. The one
    documented constraint most likely to be applied to this code path is the one
    that would silently disarm the guard.

    Lexical: `PurePosixPath` touches no filesystem, so the predicate stays pure
    and cannot be changed by what happens to exist on this host. Widening
    *recognition* is the safe direction — the guard polices more argvs, never
    fewer — which is why an absolute path is recognised rather than refused
    outright, leaving C1's own remedy available to the runner.
    """
    return PurePosixPath(word).name == VERSION_ARGV[0]


def _segments(words: list[str]) -> list[list[str]]:
    """Split one tmux argv's tail into the commands tmux will read it as.

    Measured, not assumed (see `COMMAND_SEPARATOR`). Splitting never refuses
    anything by itself: it only means a verb that follows a separator is looked
    at too, instead of being invisible behind a first verb this module allows.
    """
    found: list[list[str]] = []
    current: list[str] = []
    for word in words:
        if word == COMMAND_SEPARATOR:
            found.append(current)
            current = []
        elif word.endswith(COMMAND_SEPARATOR) and not word.endswith("\\" + COMMAND_SEPARATOR):
            current.append(word[:-1])
            found.append(current)
            current = []
        else:
            current.append(word)
    found.append(current)
    return [segment for segment in found if segment]


def _take_value(
    word: str, index: int, words: list[str], value_flags: str
) -> tuple[str | None, str | None, int]:
    """getopt over one flag word: `(letter, value, new index)`.

    `-ds foo` is `-d` plus `-s foo`; `-sfoo` is `-s foo`. The first letter that
    takes a value ends the cluster, which is what getopt does and therefore what
    tmux does.
    """
    for position, letter in enumerate(word[1:], start=1):
        if letter in value_flags:
            inline = word[position + 1 :]
            if inline:
                return letter, inline, index
            if index + 1 < len(words):
                return letter, words[index + 1], index + 1
            return letter, None, index
    return None, None, index


def _server_region(words: list[str]) -> tuple[dict[str, str], list[str]]:
    """The flags before the verb, and the verb onward.

    Stops at the first word that is not a flag: that word is the command name,
    and everything after it is the command's own business. Walking past it with
    the *server's* flag table would read `new-session … -c <cwd>` as
    `tmux -c <shell-command>` and refuse an ordinary spawn.
    """
    values: dict[str, str] = {}
    index = 0
    while index < len(words) and len(words[index]) > 1 and words[index].startswith("-"):
        if words[index] == "--":
            index += 1
            break
        letter, value, index = _take_value(words[index], index, words, SERVER_VALUE_FLAGS)
        if letter is not None and value is not None:
            values[letter] = value
        index += 1
    return values, words[index:]


def _options(words: list[str], value_flags: str) -> tuple[dict[str, str], list[str]]:
    """getopt over one command's words: the values it took, and its operands."""
    values: dict[str, str] = {}
    operands: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            operands.extend(words[index + 1 :])
            break
        if len(word) > 1 and word.startswith("-"):
            letter, value, index = _take_value(word, index, words, value_flags)
            if letter is not None and value is not None:
                values[letter] = value
            index += 1
            continue
        operands.append(word)
        index += 1
    return values, operands


def _shell_verb(word: str) -> _ShellVerb | None:
    """Is `word` a way of naming a shell-executing command? By tmux's own rule.

    tmux resolves an **unambiguous prefix** of a command name, and it accepts
    each command's alias, so `new-s`, `neww` and `new` are all ways of spelling a
    verb that runs a shell command. Matching the full name alone would be the
    same class of mistake as `argv[0] == "tmux"` (T8-2): a spelling, not a
    property. Recognising *more* argvs is the safe direction — the cost of a
    prefix that tmux would itself call ambiguous is that its command argument is
    checked too.
    """
    if not word or word.startswith("-"):
        return None
    for name, verb in SHELL_COMMAND_VERBS.items():
        if name.startswith(word) or verb.alias.startswith(word):
            return verb
    return None


def is_server_teardown(word: str) -> bool:
    """Would tmux, reading `word` in a command-name position, reach `kill-server`?

    **The property, not the spelling.** `"kill-server" in argv` was a membership
    test over one of eleven words that run the command §18 is about: measured on
    this host, `tmux -L <socket> kill-serv` returns `rc=0` and the server is
    gone, because tmux resolves an unambiguous command-name **prefix**. That is
    the same mistake as `argv[0] == "tmux"` (T8-2), and `_shell_verb` already
    declined to make it for the shell-executing verbs — this module knew the rule
    and had not applied it to the one verb the incident was about.

    **Ambiguous prefixes are refused too, on purpose.** `kill-s` is also a prefix
    of `kill-session`, so tmux would answer `ambiguous command` and do nothing.
    Refusing it costs an argv tmux would have rejected anyway, and the
    alternative is mirroring tmux's whole command table in here — a copy that
    goes stale silently, which is how a guard stops guarding. Refusing is the
    safe direction; being wrong in it costs a refusal, and being wrong in the
    other direction costs every owned session at once.

    **Public on purpose.** `tests/boundaries/test_tmux_blast_radius.py`'s
    edit-time rule reads this same function, so the two nets cannot drift into
    disagreeing about which words are the verb. A second definition of a
    property is the way a property becomes two spellings.

    **Position matters, and is the caller's job.** This answers about a word in a
    command-name position, which is the only place tmux prefix-resolves. A word
    that merely *contains* the verb is not one: `spawn_argv` puts the operator's
    brief in an argv word, and "no argv word may name the teardown" is the rule
    T8-3 rejected out loud, because a session briefed *"fix the kill-server bug"*
    would be refused and a guard with false positives on ordinary work gets
    turned off.
    """
    if not word:
        return False
    return KILL_SERVER.startswith(word) or any(
        alias.startswith(word) for alias in KILL_SERVER_ALIASES
    )


def _check_command_arg(value: str, *, spelled: list[str], commands: frozenset[str]) -> None:
    """The command a tmux verb will hand to `/bin/sh`, constrained two ways.

    C4: *"a single command string is run through `sh -c`"*, and `sh` will run
    whatever that string says. So the string must name a program **this exec
    site permits** — by basename, as T8-2 recognises the tmux binary — and must
    carry no operator that could introduce a second one.
    """
    words = value.split()
    if not words:
        return  # no command: `pipe-pane` with no argument closes the pipe
    if not _COMMAND_ARG.fullmatch(value):
        raise _refuse(
            f"a tmux shell-executing verb runs its command argument through sh -c, so the "
            f"argument is confined to {COMMAND_ARG_RE}: {value!r} in {spelled!r}"
        )
    program = PurePosixPath(words[0]).name
    if program not in commands:
        raise _refuse(
            f"{program!r} is not one of this exec site's permitted commands "
            f"({sorted(commands)}), and a tmux shell-executing verb runs its command "
            f"argument through sh -c: {value!r} in {spelled!r}"
        )


def _check_segment(words: list[str], *, spelled: list[str], commands: frozenset[str]) -> None:
    """One tmux command out of the argv: find its verb, then its command argument."""
    server, rest = _server_region(words)
    if SERVER_COMMAND_FLAG in server:
        _check_command_arg(server[SERVER_COMMAND_FLAG], spelled=spelled, commands=commands)
    if not rest:
        return
    verb = _shell_verb(rest[0])
    if verb is None:
        return
    values, operands = _options(rest[1:], verb.value_flags)
    if verb.command_flag is not None:
        if verb.command_flag in values:
            _check_command_arg(values[verb.command_flag], spelled=spelled, commands=commands)
        return
    if operands:
        _check_command_arg(operands[0], spelled=spelled, commands=commands)


def tmux_argv(socket: str, *args: str) -> list[str]:
    """The one argv shape: the binary, `-L`, the socket, then the command."""
    return ["tmux", SOCKET_FLAG, socket, *args]


def session_name(session_id: str) -> str:
    """`shepherd_<session_id>`, refusing any id tmux would silently re-address.

    CLAUDE.md rule 4 made mechanical, and widened from the two characters it
    names to the whole charset: `:` and `.` are the separators, but a space or a
    `$` in a session name is a different unreadable failure, and the ids this is
    ever called with are ULIDs, which contain neither.
    """
    name = f"{SESSION_PREFIX}{session_id}"
    # The id is matched as well as the name: an empty id yields the bare prefix,
    # which is a perfectly legal tmux name addressing nothing anyone asked for.
    if not _NAME.fullmatch(session_id) or not _NAME.fullmatch(name):
        raise _refuse(
            f"a tmux session name may not contain ':' or '.' or any character "
            f"outside {NAME_RE}: {name!r}"
        )
    return name


def target(name: str) -> str:
    """`=<name>:` — the exact form, so no target ever matches by prefix."""
    candidate = f"={name}:"
    if not _TARGET.fullmatch(candidate):
        raise _refuse(f"{name!r} is not a tmux session name, so it has no exact target")
    return candidate


def permitted_sockets(*names: str) -> frozenset[str]:
    """Build the allow-list an exec site is constructed with.

    Never a module-level default instance: a default would fix the permitted set
    at import time and make the configured socket (D49, RD1) a lie.
    """
    if not names:
        raise _refuse("an exec site with no permitted socket can start nothing; name one")
    for name in names:
        if name == FORBIDDEN_SOCKET:
            raise _refuse(f"{FORBIDDEN_SOCKET!r} is the user's own socket and is never permitted")
        if not _NAME.fullmatch(name):
            raise _refuse(f"{name!r} is not a socket name ({NAME_RE})")
    return frozenset(names)


def permitted_commands(*names: str) -> frozenset[str]:
    """Build the set of programs a shell-executing tmux verb may name here.

    Never a module-level default: the members are facts the **exec site** holds.
    `cat` is the runner's own (`pipe-pane -o -t <target> 'cat >> <sink>'`), and
    the engine's binary is `engines/`' — `runner/` may not spell it (T8-1), and a
    constant here would fix a second engine's name at import time the same way a
    default socket would fix D49's.

    An exec site with **no** permitted command is legitimate and is the
    strictest setting: it may still run every tmux verb that executes nothing.
    """
    for name in names:
        if not _COMMAND_NAME.fullmatch(name):
            raise _refuse(
                f"{name!r} is not a program name ({COMMAND_NAME_RE}): the allow-list is "
                f"matched against a basename, so a path or a shell fragment can never be a "
                f"member of it"
            )
    return frozenset(names)


def check_tmux_argv(
    argv: list[str], *, permitted: frozenset[str], commands: frozenset[str]
) -> None:
    """Refuse — never repair. ADR-M3-8's predicate, in refusal order.

    Raises `RunnerRefusal`; returns `None` on an argv that is allowed to run and
    on an argv that is not tmux's business at all.

    `commands` is the allow-list for the verbs that run a shell command (T8-3).
    It is **required**, because the shape of an optional safety argument is the
    shape of a check that is never asked for (T6-2, and the `capabilities`
    degrade that never fired).
    """
    if not argv or not _is_binary(argv[0]):
        return  # not our binary, not our rule (a guard that polices `git` gets turned off)
    if tuple(argv[1:]) == VERSION_ARGV[1:]:
        return  # contacts no server; the flags by equality, never by prefix
    # Recognised — so the rules below run on the argv **re-presented under the
    # canonical name** (T8-2), and are exactly the rules they were before the
    # binary could be spelled more than one way. The refusal messages carry
    # `spelled`, the argv as the caller actually wrote it: a message that hid
    # `/usr/bin/tmux` behind `tmux` would be a message nobody can act on.
    spelled, argv = argv, [VERSION_ARGV[0], *argv[1:]]
    if argv[1:2] != [SOCKET_FLAG] or len(argv) < 3:
        raise _refuse(
            f"every tmux invocation passes {SOCKET_FLAG} explicitly, as argv[1], because a "
            f"command run inside tmux inherits $TMUX and resolves to that session's own "
            f"socket: {spelled!r}"
        )
    socket = argv[2]
    if socket == FORBIDDEN_SOCKET:
        raise _refuse(f"{socket!r} is the user's own socket and is never permitted: {spelled!r}")
    if socket not in permitted:
        raise _refuse(f"{socket!r} is not one of this exec site's permitted sockets: {spelled!r}")
    for flag, value in zip(argv, argv[1:]):
        if flag == TARGET_FLAG and not _TARGET.fullmatch(value):
            raise _refuse(
                f"{value!r} is not the exact target form {TARGET_RE}, so it can resolve to a "
                f"different session than the caller meant: {spelled!r}"
            )
    segments = _segments(argv[3:])
    if not _THROWAWAY.fullmatch(socket):
        # The verb, by the property (`is_server_teardown`) and in the position
        # tmux resolves it in: the first operand of each command in the argv,
        # after that command's own server-region flags. `_segments` is why a
        # teardown behind `;` is looked at rather than hidden by a first verb
        # this module allows.
        for segment in segments:
            _, rest = _server_region(segment)
            if rest and is_server_teardown(rest[0]):
                raise _refuse(
                    f"{rest[0]!r} is a command-name prefix tmux resolves to {KILL_SERVER!r}, "
                    f"and a server-wide teardown is permitted only on a throwaway socket "
                    f"({THROWAWAY_SOCKET_RE}), never on {socket!r}: {spelled!r}"
                )
        # The literal, anywhere in the argv, as the cheap second layer the rule
        # has always had: it costs nothing and it keeps covering the positions
        # the property above deliberately does not look at.
        if KILL_SERVER in argv:
            raise _refuse(
                f"a server-wide teardown is permitted only on a throwaway socket "
                f"({THROWAWAY_SOCKET_RE}), never on {socket!r}: {spelled!r}"
            )
    # T8-3. Every rule above reads argv **elements**, so a whole command inside
    # one word — `sh -c 'tmux -L shepherd kill-server'`, or `run-shell` with the
    # same string on a socket that is perfectly legal — is invisible to all of
    # them. The command-bearing arguments are the elements that are re-read by a
    # shell, and they are constrained the way `pipe-pane`'s sink already was.
    for segment in segments:
        _check_segment(segment, spelled=spelled, commands=commands)
