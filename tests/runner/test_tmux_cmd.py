"""The pure half of T5: one argv shape, one name shape, one target shape.

Nothing here starts a process or contacts a socket. `tmux_cmd` is argv-in /
argv-out by construction, and `test_tmux_cmd_imports_no_process_module` is what
keeps it that way.
"""

from __future__ import annotations

import ast
import random
from pathlib import Path

import pytest

from shepherd.core.ids import new_ulid
from shepherd.core.runner import RunnerRefusal
from shepherd.runner import tmux_cmd
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    FORBIDDEN_SOCKET,
    SESSION_PREFIX,
    check_tmux_argv,
    permitted_commands,
    permitted_sockets,
    session_name,
    target,
    tmux_argv,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: Assembled from halves: this module is inside the tree the AST rules scan, and
#: a literal here would make the file its own first violation. See
#: `tests/runner/test_tmux_guard.py`'s docstring for the full reason.
TMUX = "tm" + "ux"


def test_the_default_socket_is_not_the_users() -> None:
    """D49. `shepherd` is where `aivisor`, `main` and `spike` live.

    Both halves matter: the default is not the user's socket, and it is the only
    default in `src/` — a second one somewhere else is a second answer to "which
    socket does the product use", and the wrong one is the incident.
    """
    assert DEFAULT_SOCKET != FORBIDDEN_SOCKET
    assert not DEFAULT_SOCKET.startswith(FORBIDDEN_SOCKET + "/")
    assert FORBIDDEN_SOCKET == "shepherd"

    defining = [
        path
        for path in sorted(SRC_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id in {"DEFAULT_SOCKET", "FORBIDDEN_SOCKET"}
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert {path.name for path in defining} == {"tmux_cmd.py"}, defining


def test_a_session_name_never_contains_a_target_separator() -> None:
    """CLAUDE.md rule 4, over 10 000 real ids.

    tmux reserves `:` as the `session:window` separator and `.` as
    `window.pane`: a name carrying either is silently rewritten, and `-t name:win`
    then resolves to a *different* session. The generated ids are the ones
    `session_id` actually carries (§7 ULIDs), so this is the population the rule
    will meet.
    """
    for _ in range(10_000):
        name = session_name(new_ulid())
        assert ":" not in name and "." not in name, name
        assert name.startswith(SESSION_PREFIX)
        # …and the name is addressable exactly, which is the point of the charset.
        assert target(name) == f"={name}:"

    # The refusal half: an id that would smuggle a separator through is refused,
    # never sanitised — a sanitised name addresses a session the caller did not
    # ask for, which is the same failure one step later.
    for bad in ("01J:0", "01J.0", "01J 0", "01J/0", "", "01J$(x)"):
        with pytest.raises(RunnerRefusal) as raised:
            session_name(bad)
        assert "CLAUDE.md" in raised.value.reason


def test_every_target_uses_the_exact_form() -> None:
    """`=name:` — never a bare name, never `name:0`, never a prefix.

    `-t shepherd_x` is a prefix match, so it hits `shepherd_x2`; the `=` anchors
    it and the trailing `:` keeps it addressing the session rather than a window.
    """
    assert target("shepherd_x") == "=shepherd_x:"
    assert target("shepherd_x") != "shepherd_x"
    assert not target("shepherd_x").endswith(":0")

    # Two names that differ only by a suffix get two different exact targets —
    # the prefix collision the form exists to prevent.
    assert target("shepherd_x") != target("shepherd_x2")

    for bad in ("shepherd_x:0", "shepherd:x", "shepherd.x", "", "shepherd x"):
        with pytest.raises(RunnerRefusal):
            target(bad)


def test_every_argv_the_builder_produces_survives_the_guard() -> None:
    """1 000 generated calls: the builder and the predicate agree, by construction.

    This is the property that makes the predicate usable rather than merely
    strict — if the one builder in `src/` could emit an argv its own exec site
    refuses, the pressure would be to widen the predicate.
    """
    rng = random.Random(20260917)
    verbs = ("ls", "list-sessions", "send-keys", "capture-pane", "display-message", "new-session")
    permitted = permitted_sockets(DEFAULT_SOCKET, "shepherd-m3-live")
    COMMANDS = permitted_commands("cat")
    for index in range(1_000):
        socket = DEFAULT_SOCKET if index % 2 else "shepherd-m3-live"
        words: list[str] = [rng.choice(verbs)]
        if index % 3 == 0:
            words += ["-t", target(session_name(new_ulid()))]
        if index % 7 == 0 and socket.startswith("shepherd-m3-"):
            words = ["kill-server"]
        argv = tmux_argv(socket, *words)
        assert argv[0] == TMUX and argv[1] == "-L" and argv[2] == socket
        check_tmux_argv(argv, permitted=permitted, commands=COMMANDS)

    # …and the builder cannot be talked into the user's socket: the guard refuses
    # the argv even though the builder happily shaped it.
    with pytest.raises(RunnerRefusal):
        check_tmux_argv(tmux_argv(FORBIDDEN_SOCKET, "ls"), permitted=permitted, commands=COMMANDS)


def test_tmux_cmd_imports_no_process_module() -> None:
    """The predicate is pure: the exec site is one layer up (T8, `runner/local.py`).

    Walked over the module's whole first-party import closure, not just its own
    header: a helper that imports `subprocess` and is imported here puts the
    process module in this module's reach, which is the thing being forbidden.
    """
    forbidden = {"subprocess", "os", "shutil", "signal", "socket", "multiprocessing", "pty"}
    seen: set[Path] = set()
    frontier = [Path(tmux_cmd.__file__)]
    while frontier:
        path = frontier.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in forbidden, (path, name)
                if name.startswith("shepherd."):
                    candidate = SRC_ROOT.parent / Path(*name.split(".")).with_suffix(".py")
                    if candidate.exists():
                        frontier.append(candidate)

    assert len(seen) >= 2, seen  # the module and at least `core/runner.py`
    assert Path(tmux_cmd.__file__) in seen
