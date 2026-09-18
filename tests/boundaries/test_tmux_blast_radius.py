"""K6/K16's second net: the tmux argvs this tree can be read to contain.

**This is the cheap net, not the guarantee.** The guarantee is
`shepherd.runner.tmux_cmd.check_tmux_argv`, which runs at the one process-exec
site on the real argv (ADR-M3-8, `tests/runner/test_tmux_guard.py`). The rules
here catch the honest mistake at edit time — someone types `["tmux", "ls"]` into
a new module — and they are *known* to be defeated by three one-liners, each of
which ships as a fixture below. `test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime`
asserts exactly that asymmetry, and it is the only test in the repo that can show
the two nets catch different things.

**Every rule here follows the argv, not a spelling of it** as far as a static
reader can. An argv is a sequence display headed by the binary's name that goes
somewhere — into a call, or out of a function. A tuple of words that is only ever
iterated (`tests/test_core_runner.py`'s `RUNNER_WORDS`) is a word list, not an
argv, and a rule that fired on it would be a rule with an exemption bolted on by
the next reader. Equally, `fields.get("tmux")` in `engines/claude_code/registry.py`
reads a **field name out of the engine's own registry sidecar**; it builds
nothing. `tests/boundaries/_taint.py:5-9` is in this repo because two rules were
written as syntactic forms and one line defeated each: *a rule about a value has
to follow the value.*

**Why this module spells the binary and the verb in halves.** It is inside the
tree it scans. A literal here would make the rule's own definition its first
violation, and a boundary test that cries wolf gets an exemption added to it —
ADR-1's death, reached from the other side. The shipped
`tests/e2e/test_live_attached_session.py` used the same assembly for the same
reason before this module replaced its rule.
"""

from __future__ import annotations

import ast
import importlib.util
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from _imports import FIXTURE_DIR, REPO_ROOT, SRC_ROOT, fixture, modules_defining
from _parse import parsed

from shepherd.core.runner import RunnerRefusal
from shepherd.runner import local as local_module
from shepherd.runner.local import make_run_argv
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    FORBIDDEN_SOCKET,
    TARGET_RE,
    THROWAWAY_SOCKET_RE,
    VERSION_ARGV,
    check_tmux_argv,
    is_server_teardown,
    permitted_commands,
    permitted_sockets,
    session_name,
    target,
    tmux_argv,
)

#: Assembled — see the module docstring.
TMUX = "tm" + "ux"
KILL_SERVER = "kill" + "-server"
SOCKET_FLAG = "-L"
TARGET_FLAG = "-t"

TESTS_ROOT = REPO_ROOT / "tests"
PROBES_ROOT = REPO_ROOT / "docs" / "probes"
SCAN_ROOTS: tuple[Path, ...] = (SRC_ROOT, TESTS_ROOT, PROBES_ROOT)

#: The date on which K6-a's `^shepherd-m3-` rule starts applying to probe
#: folders. Folders dated before it are **frozen evidence**: they are never
#: re-run, their captures are what M3 reads, and re-running them would invalidate
#: those captures. Their teardowns (`tmux -L shepherd-probe kill-server`) are
#: correct under CLAUDE.md and simply predate the throwaway-socket convention.
FROZEN_BEFORE = "2026-09-17"
_DATED_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2})")

_TARGET = re.compile(TARGET_RE)
_THROWAWAY = re.compile(THROWAWAY_SOCKET_RE)


# ----- the walker -------------------------------------------------------------


def _is_boundary_fixture(path: Path) -> bool:
    """`tests/boundaries/fixtures/` is the planted-violation corpus.

    Every file in it exists to *be* a violation; scanning it would mean the suite
    reports its own evidence as a finding. The exclusion is stated, and
    `test_the_scan_scope_is_what_it_claims` asserts the excluded set is exactly
    this directory and that each of the seven files is named by a self-check in
    this module — so it cannot grow quietly.
    """
    return FIXTURE_DIR in path.parents


def _frozen_probe_folder(path: Path) -> Path | None:
    """The dated `docs/probes/<folder>` this file sits under, if it predates K6-a.

    Computed **from the path**, never from a name list: a list is a set of
    exemptions with a date written on it.
    """
    if PROBES_ROOT not in path.parents:
        return None
    folder = path.relative_to(PROBES_ROOT).parts[0]
    matched = _DATED_FOLDER.match(folder)
    if matched is None or matched.group(1) >= FROZEN_BEFORE:
        return None
    return PROBES_ROOT / folder


def scanned_files(*, frozen_probes: bool) -> list[Path]:
    """Every `.py` under the three roots, recursively.

    `frozen_probes=False` additionally drops the pre-K6-a probe folders; that is
    the only rule-specific narrowing, and it applies to the `kill-server` rule
    alone.
    """
    found: list[Path] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if _is_boundary_fixture(path):
                continue
            if not frozen_probes and _frozen_probe_folder(path) is not None:
                continue
            found.append(path)
    return found


def _docstring_ids(tree: ast.Module) -> set[int]:
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)):
                found.add(id(value))
    return found


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"` bindings — how every probe names its socket."""
    found: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr]
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for entry in targets:
                if isinstance(entry, ast.Name):
                    found[entry.id] = value.value
    return found


def _sequences_that_go_somewhere(tree: ast.Module) -> set[int]:
    """Sequence displays that reach a call argument or leave a function.

    That is what makes a sequence of words an **argv**: something is going to run
    it, or hand it to something that will. A display that is only iterated is a
    word list. The fixpoint follows local names, so `cmd = [...] + list(args)`
    then `subprocess.run(cmd)` — the shipped probes' exact shape — is seen.
    """
    used: set[int] = set()
    used_names: set[str] = set()

    def absorb(node: ast.expr) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, (ast.List, ast.Tuple)):
                used.add(id(sub))
            elif isinstance(sub, ast.Name):
                used_names.add(sub.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for argument in node.args:
                absorb(argument)
            for keyword in node.keywords:
                absorb(keyword.value)
        elif isinstance(node, ast.Return) and node.value is not None:
            absorb(node.value)

    for _ in range(4):  # a fixpoint; deeper nesting than this is not idiomatic
        before = (len(used), len(used_names))
        for node in ast.walk(tree):
            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            if any(isinstance(t, ast.Name) and t.id in used_names for t in targets):
                absorb(value)
        if (len(used), len(used_names)) == before:
            break
    return used


@dataclass(frozen=True)
class ArgvSite:
    """One tmux argv as a static reader can see it. `None` is an element it cannot."""

    lineno: int
    words: tuple[str | None, ...]

    @property
    def socket(self) -> str | None:
        return self.words[2] if len(self.words) > 2 else None


def tmux_argv_sites(path: Path) -> list[ArgvSite]:
    """Every tmux argv display in `path` that goes somewhere."""
    tree = parsed(path)
    constants = _module_constants(tree)
    used = _sequences_that_go_somewhere(tree)

    def word(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return constants.get(node.id)
        return None

    found: list[ArgvSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
            continue
        if id(node) not in used or word(node.elts[0]) != TMUX:
            continue
        found.append(ArgvSite(node.lineno, tuple(word(element) for element in node.elts)))
    return found


def command_word_sites(path: Path, word: str) -> list[int]:
    """Lines where `word` is written as a **command word**, not merely mentioned.

    A command word is a string constant that enters an argv: an element of a
    sequence display, or the value bound to a name. A constant in a comparison
    (`if "kill-server" in argv`) is a *check* and builds nothing; a constant in a
    mapping read (`fields.get("tmux")`, `registry.py:166`) is a key into the
    engine's own sidecar. Docstrings are prose. Following the value is the whole
    difference between this rule and the one revision 1 shipped.
    """
    tree = parsed(path)
    skip = _docstring_ids(tree)
    found: list[int] = []

    def matches(node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == word
            and id(node) not in skip
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            found += [element.lineno for element in node.elts if matches(element)]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if matches(node.value):
                found.append(node.value.lineno)
    return sorted(set(found))


def mentions_literally(path: Path, word: str) -> list[int]:
    """Lines carrying `word` as a non-docstring string constant, anywhere."""
    tree = parsed(path)
    skip = _docstring_ids(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and word in node.value
    )


# ----- the rules --------------------------------------------------------------


def socket_violations(path: Path) -> list[str]:
    """K6: `-L` on every invocation, never the user's socket, exact targets.

    Read before any exemption is consulted (B1): this raises on a missing path
    rather than returning `[]`, because a scan that cannot raise never opened a
    file.
    """
    found: list[str] = []
    for site in tmux_argv_sites(path):
        where = f"{path}:{site.lineno}"
        if site.words == VERSION_ARGV:
            continue  # contacts no server; by equality, never by prefix
        if len(site.words) < 3 or site.words[1] != SOCKET_FLAG:
            found.append(f"{where}: a tmux argv with no explicit {SOCKET_FLAG} socket")
            continue
        if site.socket == FORBIDDEN_SOCKET:
            found.append(f"{where}: a tmux argv on the user's own socket {FORBIDDEN_SOCKET!r}")
        for flag, value in zip(site.words, site.words[1:]):
            if flag == TARGET_FLAG and value is not None and not _TARGET.fullmatch(value):
                found.append(f"{where}: {value!r} is not the exact target form {TARGET_RE}")
    return found


def teardown_mentions(path: Path) -> list[int]:
    """Lines where `path` writes a word tmux would resolve to the teardown verb.

    The **property**, read from `shepherd.runner.tmux_cmd.is_server_teardown` —
    the same predicate the runtime guard refuses on, so an edit that teaches one
    net a new spelling teaches the other. `kill-serv` and `kill-serve` are here;
    `kill-session`, which is what `terminate` really issues, is not.

    Every non-docstring string constant, in **every** position, because in `src/`
    the verb has no legitimate position at all outside the module that defines
    the predicate: `command_word_sites` looks at sequence elements and bound
    names only, and MUT-G4 put the word in a call argument
    (`self._checked("kill-serv")`), which is exactly a position it does not walk.
    Measured over `src/` before this widened: **one** hit, the guard's own
    canonical constant, and nothing else — so the wider scan costs no false
    positive here.
    """
    tree = parsed(path)
    skip = _docstring_ids(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and is_server_teardown(node.value)
    )


def guard_module() -> Path:
    """The one `src/` module that defines `check_tmux_argv` — by property (B2).

    Never a hard-coded path: a rule that can be switched off with `git mv` is
    not a rule, and this package has shipped two of those.
    """
    defining = modules_defining("check_tmux_argv")
    assert len(defining) == 1, f"expected exactly one definition of the guard: {defining}"
    return defining[0].path


def modules_spelling_the_teardown_verb() -> list[Path]:
    """Every module in `src/` that writes a word tmux resolves to the teardown."""
    return [path for path in sorted(SRC_ROOT.rglob("*.py")) if teardown_mentions(path)]


def kill_server_violations(path: Path) -> list[str]:
    """K6-a: a server-wide teardown, and the sockets the file that writes it names.

    In `src/` the verb may not be **named at all**, in any spelling tmux
    resolves, outside the one module that defines the predicate — production
    tears down one session at a time. That module is identified by property
    (`guard_module`) and its count is pinned at one by
    `test_the_teardown_verb_is_spelled_in_exactly_one_module_in_src`, which is
    the shape the binary rule has had since T8-2, not an exemption.

    Outside `src/` the verb is permitted and the bound is the **socket**: every
    tmux socket the file names must match `^shepherd-m3-`. That branch keeps
    keying on the literal, deliberately. The bound there is the socket, the
    socket rule is unchanged and is tested *before* the verb in the runtime
    guard, and widening a literal gate to eleven prefixes over `tests/` and
    `docs/probes/` would pull in files whose only offence is the word `kill` in
    a keystroke list — a guard with false positives on ordinary work gets turned
    off (T8-3).
    """
    if path.resolve().is_relative_to(SRC_ROOT.resolve()):
        if path.resolve() == guard_module().resolve():
            return []
        return [
            f"{path}:{line}: a server-wide teardown has no place in src/, and tmux "
            f"resolves a command-name prefix to one"
            for line in teardown_mentions(path)
        ]
    if not mentions_literally(path, KILL_SERVER):
        return []
    sockets = {site.socket for site in tmux_argv_sites(path) if site.socket is not None}
    return [
        f"{path}: names {KILL_SERVER} and the socket {socket!r}, which is not a throwaway "
        f"({THROWAWAY_SOCKET_RE})"
        for socket in sorted(sockets)
        if not _THROWAWAY.fullmatch(socket)
    ]


def modules_spelling_the_binary() -> list[Path]:
    """Every module in `src/` that writes the binary's name as a command word."""
    return [
        path
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if command_word_sites(path, TMUX)
    ]


# ----- the fixtures, imported so their argv is a value ------------------------


def load_fixture(name: str) -> ModuleType:
    """Import a planted fixture by path and return it.

    The indirection fixtures are asserted to be **refused at runtime**, and the
    only honest way to assert that is to let the fixture build its own argv and
    hand the result to the predicate. Reading the argv out of the AST instead
    would be the test re-implementing the very indirection under test.
    """
    path = fixture(name)
    spec = importlib.util.spec_from_file_location(f"_boundary_fixture_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PERMITTED = permitted_sockets(DEFAULT_SOCKET, "shepherd-m3-live")

#: T8-3's command allow-list for this exec site. `cat` is the runner's own
#: (`pipe-pane -o -t <target> 'cat >> <sink>'`) and is the only program this
#: product composes into a tmux command argument.
COMMANDS = permitted_commands("cat")


# ----- the tests --------------------------------------------------------------


def test_every_tmux_argv_carries_an_explicit_socket() -> None:
    """CLAUDE.md rule 3, over the tree and over 1 000 generated calls.

    The generated half proves the builder cannot produce a socket-less argv; the
    scanned half proves nobody wrote one by hand. Both are needed: the builder is
    only the guarantee for argvs that went through it.
    """
    rng = random.Random(20260917)
    for _ in range(1_000):
        words = [rng.choice(("ls", "send-keys", "capture-pane", "kill-session"))]
        if rng.random() < 0.5:
            words += [TARGET_FLAG, target(session_name("01J" + str(rng.randrange(10 ** 6))))]
        argv = tmux_argv(DEFAULT_SOCKET, *words)
        assert argv[1] == SOCKET_FLAG and argv[2] == DEFAULT_SOCKET, argv

    assert [
        message for path in scanned_files(frozen_probes=True) for message in socket_violations(path)
    ] == []

    # B1: a missing path raises rather than returning `[]`.
    with pytest.raises(FileNotFoundError):
        socket_violations(FIXTURE_DIR / "this_module_does_not_exist.py")

    # …and the rule bites, so it cannot be emptied and stay green.
    assert socket_violations(fixture("runner_bare_tmux_call.py")) != []


def test_a_loose_target_is_caught_by_the_scan_too() -> None:
    """A `-t` that matches by prefix reaches a session nobody named (A5)."""
    violations = socket_violations(fixture("runner_loose_target.py"))
    assert violations != []
    assert any("shepherd_x" in message for message in violations), violations


def test_tmux_is_spelled_in_exactly_one_module() -> None:
    """One builder in `src/`. Tests and probes legitimately spell it; production may not.

    The negative half is asserted with its content read (B3): `registry.py` names
    `tmux` as a **field of the engine's registry sidecar** and builds no argv, so
    the rule stays quiet there — and would not, if it matched spellings rather
    than command-word positions.
    """
    assert [path.name for path in modules_spelling_the_binary()] == ["tmux_cmd.py"]

    registry = SRC_ROOT / "engines" / "claude_code" / "registry.py"
    assert command_word_sites(registry, TMUX) == []
    assert mentions_literally(registry, TMUX) != []  # the content IS read

    # …and a second module naming it as a command word is caught.
    assert command_word_sites(fixture("runner_bare_tmux_call.py"), TMUX) != []


def test_kill_server_is_never_a_command_word_in_src() -> None:
    """Production tears down one session at a time (K6).

    Named for what it checks: `check_tmux_argv` must *test* for the verb, so the
    word appears in `tmux_cmd.py` inside an `in` comparison. A comparison builds
    no argv. The rule is the command-word position, and the position is what a
    reader of this test is owed.
    """
    assert [
        message
        for path in sorted(SRC_ROOT.rglob("*.py"))
        for message in kill_server_violations(path)
    ] == []

    guard = guard_module()
    assert mentions_literally(guard, KILL_SERVER) != []  # the predicate does check for it
    # It *binds* the verb now, as the canonical name `is_server_teardown` tests
    # against — so "never a command word" is no longer the property that holds
    # here, and pretending otherwise would have meant assembling the literal
    # from halves inside the guard: a spelling, which is the defect this whole
    # module exists to refuse. What replaces it is stronger and is the binary
    # rule's own shape: exactly **one** module in `src/` may name the verb, found
    # by property, asserted in
    # `test_the_teardown_verb_is_spelled_in_exactly_one_module_in_src`.
    assert modules_spelling_the_teardown_verb() == [guard]
    assert all(path != guard for path in SRC_ROOT.rglob("*.py") if teardown_mentions(path) and path != guard)

    assert kill_server_violations(fixture("runner_kill_server.py")) != []


def test_the_teardown_verb_is_spelled_in_exactly_one_module_in_src() -> None:
    """MUT-G4: the verb is a **property of tmux's command table**, not a spelling.

    The M3 verifier planted a new `LocalRunner` method issuing
    `self._checked("kill-serv")` — no `tmux` literal, no `kill-server` literal,
    the product's own argv builder — and it survived all 1 470 default tests.
    `kill-serv` is an unambiguous prefix and tmux resolves it; measured on this
    host, it returns `rc=0` and the server is gone.

    So this rule reads `is_server_teardown`, the **same predicate** the runtime
    guard refuses on: one property, two nets, and they cannot drift apart into
    disagreeing about what the verb is.

    In `src/` the verb may be named in exactly one module — the one that
    *defines* `check_tmux_argv`, found by property and not by filename, exactly
    as `test_tmux_is_spelled_in_exactly_one_module` already does for the binary.
    That module has to write the word down to check for it; a second module
    naming it is building an argv.
    """
    spelling = modules_spelling_the_teardown_verb()
    assert [path.name for path in spelling] == ["tmux_cmd.py"], spelling
    assert spelling == [guard_module()], (spelling, guard_module())

    # The one module is the one that defines the predicate — by property.
    assert guard_module().name == "tmux_cmd.py"

    # MUT-G4 itself, as a fixture: a prefix spelled nowhere near `kill-server`,
    # caught by the scan and refused by the runtime guard.
    planted = fixture("runner_kill_server_prefix.py")
    assert mentions_literally(planted, KILL_SERVER) == []  # the literal is genuinely absent
    assert command_word_sites(planted, KILL_SERVER) == []  # …and the old rule saw nothing
    # The new detector does see it — and `modules_spelling_the_teardown_verb`
    # above is the same detector over `src/`, so a module that gains this text
    # joins that list and the equality one assertion up breaks. (The fixture
    # itself sits outside `src/`, where the bound is the socket, so
    # `kill_server_violations` is deliberately quiet on it.)
    assert teardown_mentions(planted) != []
    with pytest.raises(RunnerRefusal) as raised:
        check_tmux_argv(load_fixture(planted.name).argv(), permitted=PERMITTED, commands=COMMANDS)
    assert KILL_SERVER in raised.value.reason, raised.value.reason

    # The negative control: `kill-session` is what `terminate` really issues and
    # is **not** a prefix of the teardown verb, so `runner/local.py` stays quiet.
    assert kill_server_violations(SRC_ROOT / "runner" / "local.py") == []
    assert mentions_literally(SRC_ROOT / "runner" / "local.py", "kill-session") != []


def test_a_server_wide_teardown_is_bounded_to_a_throwaway_socket() -> None:
    """K6-a, over tests and over probe folders dated on or after the relaxation."""
    assert [
        message
        for path in scanned_files(frozen_probes=False)
        for message in kill_server_violations(path)
    ] == []

    violations = kill_server_violations(fixture("runner_kill_server.py"))
    assert any(DEFAULT_SOCKET in message for message in violations), violations


def test_no_tmux_call_in_the_tree_can_reach_the_users_socket() -> None:
    """P-M3-15. The user's own sessions live on `shepherd`. Nothing names it.

    **The socket is the invariant, the session names are not** (CLAUDE.md, after
    2026-09-17): this rule keys on `FORBIDDEN_SOCKET` and never on a list of
    session names, which would go stale the next time the user opens a terminal.

    Recursive over `src/`, `tests/` **and** `docs/probes/`, frozen folders
    included: the blast radius is the same wherever the argv is written, and a
    probe is re-run by hand more often than a test is.
    """
    offenders = [
        f"{path}:{site.lineno}"
        for path in scanned_files(frozen_probes=True)
        for site in tmux_argv_sites(path)
        if site.socket == FORBIDDEN_SOCKET
    ]
    assert offenders == []

    assert socket_violations(fixture("runner_tmux_via_fstring.py")) == []  # see the asymmetry test
    planted = fixture("runner_kill_server.py")
    assert tmux_argv_sites(planted) != []  # the scan really does see argvs in a fixture

    # …and the positive control the rule was missing: a file that really does
    # name the user's socket is **found**, so `offenders == []` above is an
    # emptiness the scan could have broken rather than one it cannot see.
    # Absence needs arrival, and until this fixture existed the arrival was only
    # "the scan sees some argv somewhere".
    forbidden = fixture("runner_forbidden_socket.py")
    caught = [site for site in tmux_argv_sites(forbidden) if site.socket == FORBIDDEN_SOCKET]
    assert caught != [], "the scan cannot see an argv that names the user's own socket"
    assert socket_violations(forbidden) != []
    # The fixture is inert: it starts nothing. Asserted on the **imports**, by
    # AST — the docstring says the word `subprocess` while explaining why the
    # file has none, and a text search would have read that prose as the defect.
    imported = {
        alias.name
        for node in ast.walk(parsed(forbidden))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(parsed(forbidden))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported <= {"annotations", "__future__"}, imported
    with pytest.raises(RunnerRefusal) as raised:
        check_tmux_argv(load_fixture(forbidden.name).argv(), permitted=PERMITTED, commands=COMMANDS)
    assert FORBIDDEN_SOCKET in raised.value.reason


def test_the_scan_scope_is_what_it_claims() -> None:
    """The walked set equals the recursive glob of three directories, minus one.

    Revision 1 of this rule globbed a single directory while claiming the tree —
    M2's acceptance-clause-2 defect, repeated. The claim is checked here rather
    than trusted.
    """
    walked = set(scanned_files(frozen_probes=True))
    expected = {
        path
        for root in SCAN_ROOTS
        for path in root.rglob("*.py")
        if FIXTURE_DIR not in path.parents
    }
    assert walked == expected
    assert {root for root in SCAN_ROOTS} == {SRC_ROOT, TESTS_ROOT, PROBES_ROOT}
    assert {path.parts[len(REPO_ROOT.parts)] for path in walked} == {"src", "tests", "docs"}
    assert len(walked) > 100, len(walked)

    # The one exclusion is exactly the planted-violation corpus, and every file
    # in it is named by a self-check in this module — so it cannot grow quietly.
    excluded = {path for path in FIXTURE_DIR.rglob("*.py")}
    assert excluded and excluded.isdisjoint(walked)
    source = Path(__file__).read_text(encoding="utf-8")
    unnamed = sorted(
        path.name for path in excluded if path.name.startswith("runner_") and path.name not in source
    )
    assert unnamed == [], unnamed


def test_the_frozen_probe_folders_are_exactly_the_dated_ones() -> None:
    """The `kill-server` rule's one narrowing, checked from the path.

    Three assertions, because the first two alone would pass for an empty
    exclusion: the excluded set is **non-empty**, every excluded file sits under a
    folder dated before the relaxation, and at least one of them would actually
    fail the rule — which is what makes the exclusion load-bearing rather than
    decorative.
    """
    wide = set(scanned_files(frozen_probes=True))
    narrow = set(scanned_files(frozen_probes=False))
    excluded = wide - narrow
    assert excluded != set()
    for path in excluded:
        folder = _frozen_probe_folder(path)
        assert folder is not None, path
        matched = _DATED_FOLDER.match(folder.name)
        assert matched is not None and matched.group(1) < FROZEN_BEFORE, path

    would_fail = [path for path in excluded if kill_server_violations(path)]
    assert would_fail != [], "the exclusion excludes nothing the rule would catch"


def test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime() -> None:
    """The asymmetry proof: two nets, catching different things.

    Each of the three fixtures is the one-liner that killed the corresponding
    revision-1 rule. Each is asserted to **pass** every scan in this module — they
    carry no matching literal — and to be **refused** by `check_tmux_argv`, which
    sees the argv the interpreter built. If either half stops holding, one of the
    two nets has stopped doing its job, and no other test in the repo would say so.
    """
    # (fixture, the word it refuses to spell, the refusal the runtime gives).
    # Each fixture is named for the literal it removes, and the third column is
    # what the interpreter sees anyway.
    expectations: tuple[tuple[str, str, str], ...] = (
        ("runner_tmux_via_constant_import.py", TMUX, SOCKET_FLAG),
        ("runner_tmux_via_fstring.py", TMUX, FORBIDDEN_SOCKET),
        ("runner_kill_server_via_fstring.py", KILL_SERVER, KILL_SERVER),
    )
    for name, unspelled, expected_reason in expectations:
        path = fixture(name)
        assert socket_violations(path) == [], name
        assert kill_server_violations(path) == [], name
        # The literal the AST rules key on is genuinely absent — that, and not an
        # emptied file, is why they stay quiet.
        assert mentions_literally(path, unspelled) == [], name
        assert command_word_sites(path, unspelled) == [], name

        built = load_fixture(name).argv()
        assert isinstance(built, list) and built[0] == TMUX, (name, built)
        with pytest.raises(RunnerRefusal) as raised:
            check_tmux_argv(built, permitted=PERMITTED, commands=COMMANDS)
        assert expected_reason in raised.value.reason, (name, raised.value.reason)

    # …and the three direct violations are the mirror image: the scan catches
    # them, so the fixtures above are proving indirection and not emptiness.
    for name in ("runner_bare_tmux_call.py", "runner_kill_server.py", "runner_loose_target.py"):
        assert socket_violations(fixture(name)) or kill_server_violations(fixture(name)), name
        with pytest.raises(RunnerRefusal):
            check_tmux_argv(load_fixture(name).argv(), permitted=PERMITTED, commands=COMMANDS)


# ----- T8-3: the five argvs that were measured THROUGH ------------------------


#: T8-3's table, as it was measured against the shipped guard by the router —
#: five argvs THROUGH and one REFUSED — plus the row T8-3 decision 2's fix
#: **opened**. Five are closed; one is still open, and each row carries which
#: and why, because a survivor is information and a table that quietly drops its
#: survivors is how a gap stops being named and starts being discovered.
#:
#: Rows 3, 4 and 5 were closed by one rule at the exec site (`runner/local.py`,
#: `_names_the_binary`): **this exec site starts the tmux binary and nothing
#: else**, so an argv in which no word's basename is `tmux` is refused before
#: `subprocess.run` sees it. That is a positive rule over the argv, not a
#: deny-list of shells, and it needed nothing injected — which is why it landed
#: without changing `make_run_argv`'s signature under a live caller.
CLOSED = "REFUSED"
OPEN = "through"

#: `class 1` is "the binary inside a single word": both gates scan argv
#: *elements*, so `sh -c "<whole command>"` puts the invocation in one element.
#: Reached through a **permitted** socket, `run-shell` and `new-session` are the
#: same hole with the socket rule satisfied — and those two are what T8-3 closes.
T8_3_TABLE: tuple[tuple[str, list[str], str, str], ...] = (
    (
        "run-shell through a permitted socket",
        [TMUX, SOCKET_FLAG, DEFAULT_SOCKET, "run-shell", f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}"],
        CLOSED,
        "the command argument is allow-listed by its own argv[0] (T8-3)",
    ),
    (
        "new-session through a permitted socket",
        [
            TMUX, SOCKET_FLAG, DEFAULT_SOCKET, "new-session", "-d",
            f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}",
        ],
        CLOSED,
        "the command argument is allow-listed by its own argv[0] (T8-3)",
    ),
    (
        "a shell as argv[0], no tmux argv at all",
        ["sh", "-c", f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}"],
        CLOSED,
        "T8-3 decision 2 — the exec site starts the tmux binary and nothing "
        "else, and no word of this argv names it (by basename)",
    ),
    (
        "a shell behind a wrapper",
        ["systemd-run", "--scope", "sh", "-c", f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}"],
        CLOSED,
        "same rule: a wrapper prefix may precede the binary, but the argv still "
        "has to contain it, and this one never does",
    ),
    (
        "a renamed copy or symlink of the binary",
        ["/usr/local/bin/tm", SOCKET_FLAG, FORBIDDEN_SOCKET, KILL_SERVER],
        CLOSED,
        "T8-3 class 2, closed at the **exec site** and still open in the "
        "predicate: `check_tmux_argv` deliberately returns early on `tm` (it is "
        "not a general argv policeman), but nothing in this product ever execs a "
        "renamed copy, so the exec site refuses to start one. No filesystem "
        "resolution and no lost purity — the rule is still argv in, refusal out",
    ),
    (
        "a shell as argv[0] with a tmux argv trailing it",
        [
            "sh", "-c", f"{TMUX} -L {FORBIDDEN_SOCKET} {KILL_SERVER}",
            TMUX, SOCKET_FLAG, DEFAULT_SOCKET, "list-sessions",
        ],
        OPEN,
        "the residual T8-3 decision 2's fix leaves, named rather than discovered "
        "later: this argv **does** name the binary, so the exec site's rule is "
        "satisfied, and `_tmux_tail` re-presents only the words from the binary "
        "onward — the payload sits in front of it. Closing it means comparing the "
        "words **before** the binary against the exec site's own injected "
        "`DetachedLaunch.prefix`, which is a required argument added at the "
        "composition root (`toolsurface/compose.py`) and therefore a second "
        "builder's file",
    ),
    (
        "T8-2's row, still holding",
        ["/usr/bin/" + TMUX, SOCKET_FLAG, FORBIDDEN_SOCKET, KILL_SERVER],
        CLOSED,
        "the binary is recognised by basename (T8-2)",
    ),
)


def test_the_t8_3_table_is_seven_rows_and_says_which_is_still_open() -> None:
    """The table's own shape, asserted in the run that uses it.

    A row that vanishes takes its gap with it, so the count is compared with the
    number of cases the next test actually exercises. Seven rows and **one**
    survivor: three of T8-3's OPEN rows closed at the exec site, and the fix's
    own residual was appended rather than left for the next reader to find.
    """
    assert len(T8_3_TABLE) == 7
    assert len({name for name, _, _, _ in T8_3_TABLE}) == 7
    assert [verdict for _, _, verdict, _ in T8_3_TABLE].count(OPEN) == 1
    assert all(why for _, _, _, why in T8_3_TABLE)


def test_the_command_bearing_arguments_are_constrained_at_the_exec_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asserted at `make_run_argv`, with `subprocess.run` patched to a recorder.

    At the predicate alone this would prove less than it looks: T8-2's hole was
    in the **composition** of the two checks, and `_tmux_tail` re-presents the
    argv a second time. Arrival is asserted before absence — an allowed argv
    reaches the recorder first, so "no process was started" cannot pass by the
    callable never having exec'd anything.

    **No tmux process is started by this test and no socket is contacted.**
    """
    spawns: list[list[str]] = []

    def record(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        spawns.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(local_module.subprocess, "run", record)
    exec_site = make_run_argv(PERMITTED, COMMANDS)

    arrival = [TMUX, SOCKET_FLAG, DEFAULT_SOCKET, "list-sessions"]
    assert exec_site(arrival).rc == 0
    assert spawns == [arrival], "the recorder is not wired to the exec site"

    seen: list[tuple[str, str]] = []
    for name, candidate, expected, why in T8_3_TABLE:
        before = list(candidate)
        try:
            exec_site(candidate)
            actual = OPEN
        except RunnerRefusal:
            actual = CLOSED
        assert candidate == before, f"{name}: the exec site repaired an argv"
        assert actual == expected, f"{name}: expected {expected}, saw {actual} — {why}"
        seen.append((name, actual))

    assert len(seen) == len(T8_3_TABLE) == 7, seen
    assert spawns == [arrival] + [
        candidate for _, candidate, verdict, _ in T8_3_TABLE if verdict == OPEN
    ], "a refused argv started a process"


def test_the_signal_fixture_is_inert_and_answers_to_the_other_scanner() -> None:
    """`runner_signals_init.py` joins this corpus but not this module's rules.

    It is the 2026-09-17 line, frozen: `os.kill(1, signal.SIGINT)`, planted into
    the shadow tree's live `runner/local.py` and executed by the suite before the
    lint that would have flagged it was reached. `SIGINT` to pid 1 is
    Ctrl+Alt+Del, and the host rebooted.

    Its scanner is `signal_violations` (P-M3-7, `tests/runner/test_local.py`),
    not the tmux blast-radius rules here — but it lives in the same inert corpus,
    so this module has to name it or `test_the_scan_scope_is_what_it_claims` goes
    red. Naming it is the point: the planted-violation corpus cannot grow
    quietly, whichever rule a new member belongs to.
    """
    planted = fixture("runner_signals_init.py")
    assert planted.exists()
    assert planted not in set(scanned_files(frozen_probes=True)), "must stay inert"
    assert tmux_argv_sites(planted) == [], "not a tmux violation — the other scanner owns it"
    assert socket_violations(planted) == []
