"""P-M3-14/K3: Shepherd reads `~/.claude`. It never writes there.

Claude Code owns every byte under its own configuration directory — the
`settings.json` the user's rule is absolute about, the session sidecars discovery
reads, the transcripts the evidence builder parses. Shepherd's whole posture
toward it is *observer*: the engine's own bookkeeping changes that directory
constantly, and a Shepherd write into it is either a race with the engine or a
silent edit of the user's configuration.

`tests/conftest.py` already makes the **outcome** an observation — it hashes the
real `settings.json` before the suite and asserts the digest afterwards. That
catches a write when the test that performs it runs. This catches the write when
it is *typed*, over `src/` and `tests/` both, whether or not anything runs it.

**The rule follows the path value, not a spelling of it.** A name bound to
`Path.home() / ".claude"`, to `$CLAUDE_CONFIG_DIR`, or to the return of one of the
functions that computes the directory is tainted; so is anything derived from it
by `/`. Reading is untouched — `read_text`, `iterdir`, `exists` and `stat` are the
entire point of the directory. Only the write verbs are refused.

**And the config *file*, not only the directory (T10-R2).** `~/.claude.json` is a
**sibling** of `~/.claude`, so none of the directory literals ever matched it: a
`path.write_text(path.read_text())` planted at the top of `trust_state` passed
the entire boundary suite while it sat live on disk and wrote the user's real
97 KB config on every default test run (T10-R1). Reproduced here on 2026-09-17 —
**39 passed, exit 0, with the write on disk** — and it now fails, naming the file
and the line. The proof is the planted write, not the fixture: a fixture alone
proves only that the rule sees the shape its author typed into the fixture.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import FIXTURE_DIR, REPO_ROOT, SRC_ROOT, fixture
from _parse import parsed

TESTS_ROOT = REPO_ROOT / "tests"
SCAN_ROOTS: tuple[Path, ...] = (SRC_ROOT, TESTS_ROOT)

CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"

#: The directory's own names, and the **full** path of the config file, matched
#: against string constants.
CONFIG_DIR_LITERALS: tuple[str, ...] = (".claude", "~/.claude", "~/.claude.json")

#: Functions whose return value *is* the directory or the config file. Three
#: spellings of the directory, because the product's
#: (`registry.claude_config_dir`) and the suite's (`conftest`'s two) are separate
#: definitions by design — `tests/` is not allowed to import the product's
#: answer for a rule that polices the product — and four of the file, added at
#: T10-R2 because `trust.config_file` was the resolver the planted write went
#: through.
CONFIG_DIR_CALLS: frozenset[str] = frozenset(
    {
        "claude_config_dir",
        "real_config_dir",
        "config_dir",
        "engine_config_dir",
        "config_file",
        "_config_file",
        "engine_config_file",
        "claude_config_file",
    }
)

#: The config **file**'s own name. `~/.claude.json` is a *sibling* of `~/.claude`
#: and not inside it, so no directory literal ever matched it — which is exactly
#: why a planted `path.write_text(path.read_text())` in `trust_state` passed all
#: 35 boundary tests while it sat live on disk (T10-R1), and passed 39 of them
#: when the probe was reproduced on 2026-09-17.
#:
#: A bare `.claude.json` is **not** tainted on its own: `tmp_path / ".claude.json"`
#: is what every trust fixture legitimately writes. It is tainted only when it
#: hangs off a config **home** — `Path.home()`, `expanduser`, or
#: `$CLAUDE_CONFIG_DIR` — which is the difference between the user's file and a
#: throwaway one with the same name.
CONFIG_FILE_LITERALS: tuple[str, ...] = (".claude.json", "~/.claude.json")

#: Calls that answer "the home the engine's config hangs off".
CONFIG_HOME_CALLS: frozenset[str] = frozenset({"home", "expanduser"})

#: `Path` write verbs. Everything absent from this set — `read_text`,
#: `read_bytes`, `iterdir`, `glob`, `exists`, `stat`, `is_dir` — is a read, and a
#: read is what Shepherd does here.
WRITE_METHODS: frozenset[str] = frozenset(
    {
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "chmod",
        "symlink_to",
        "hardlink_to",
    }
)

#: Module-level write functions, matched on the attribute name so `shutil.rmtree`
#: and a `from shutil import rmtree` both land.
WRITE_FUNCTIONS: frozenset[str] = frozenset(
    {"remove", "rmtree", "makedirs", "mkdir", "unlink", "symlink", "link", "move", "copy",
     "copy2", "copyfile", "copytree", "rename", "renames", "replace", "mknod", "truncate"}
)

#: A mode with any of these characters writes. `"r"` and `"rb"` have none.
WRITE_MODES = "wax+"


class _Taint:
    """One taint analysis for the whole module, to a fixpoint.

    There used to be **two** `is_tainted` functions here, one inside
    `_tainted_names` and a narrower one inside `write_violations`, and they had
    already drifted: only the first understood `BoolOp`, `IfExp` and `Subscript`.
    A rule whose two halves disagree is a rule with a hole, so there is now one.

    Three name sets, each a fixpoint over assignments (the shape `_taint.py` uses,
    and for the same reason: a rule that only sees the expression at its
    definition site is one assignment wide):

    * `dirs`  — names holding the config directory **or** the config file;
    * `homes` — names holding the *home* the config file hangs off;
    * `files` — names holding the config file's bare **name**.

    `<home> / <file name>` is the config file. That product is what catches
    `~/.claude.json` without catching `tmp_path / ".claude.json"`.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.dirs: set[str] = set()
        self.homes: set[str] = set()
        self.files: set[str] = set()
        for _ in range(4):
            before = (set(self.dirs), set(self.homes), set(self.files))
            for target, value in _assignments(tree):
                if self.is_tainted(value):
                    self.dirs.add(target)
                elif self.is_config_home(value):
                    self.homes.add(target)
                elif self.is_config_filename(value):
                    self.files.add(target)
            if before == (self.dirs, self.homes, self.files):
                break

    # ----- the three predicates ---------------------------------------------

    def is_config_filename(self, node: ast.expr | None) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value in CONFIG_FILE_LITERALS
        return isinstance(node, ast.Name) and node.id in self.files

    def is_config_home(self, node: ast.expr | None) -> bool:
        """`Path.home()`, `expanduser(...)`, `$CLAUDE_CONFIG_DIR`, or a name."""
        if isinstance(node, ast.Name):
            return node.id in self.homes
        if isinstance(node, ast.Subscript):  # `os.environ["CLAUDE_CONFIG_DIR"]`
            return _names_the_env_var(node.slice) and _is_environ(node.value)
        if isinstance(node, (ast.BoolOp, ast.IfExp)):
            return any(self.is_config_home(part) for part in _branches(node))
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name in CONFIG_HOME_CALLS:
                return True
            if name in {"get", "getenv"} and any(
                _names_the_env_var(argument) for argument in node.args
            ):
                return True
            if name in {"Path", "str"}:
                return any(self.is_config_home(argument) for argument in node.args)
        return False

    def is_tainted(self, node: ast.expr | None) -> bool:
        """Is this expression a path under — or *at* — the engine's config?"""
        if node is None:
            return False
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value in CONFIG_DIR_LITERALS
        if isinstance(node, ast.Name):
            return node.id in self.dirs
        if isinstance(node, ast.BinOp):  # `<dir> / "settings.json"`, `a or b`
            if self.is_tainted(node.left) or self.is_tainted(node.right):
                return True
            return self.is_config_home(node.left) and self.is_config_filename(node.right)
        if isinstance(node, (ast.BoolOp, ast.IfExp)):
            return any(self.is_tainted(part) for part in _branches(node))
        if isinstance(node, ast.Subscript):
            return self.is_tainted(node.value) or self.is_tainted(node.slice)
        if isinstance(node, ast.Attribute):
            return self.is_tainted(node.value)
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name in CONFIG_DIR_CALLS:
                return True
            if name in {"Path", "str", "get", "getenv", "environ"}:
                return any(self.is_tainted(argument) for argument in node.args) or self.is_tainted(
                    node.func
                )
            if name in {"joinpath", "resolve", "absolute", "with_name"} and isinstance(
                node.func, ast.Attribute
            ):
                if self.is_tainted(node.func.value):
                    return True
                return self.is_config_home(node.func.value) and any(
                    self.is_config_filename(argument) for argument in node.args
                )
        return False


def _called_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _branches(node: ast.BoolOp | ast.IfExp) -> list[ast.expr]:
    return list(node.values) if isinstance(node, ast.BoolOp) else [node.body, node.orelse]


def _names_the_env_var(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == CONFIG_DIR_ENV


def _is_environ(node: ast.expr) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id == "environ"
    )


def _assignments(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.NamedExpr):
            targets, value = [node.target], node.value
        if value is None:
            continue
        found += [(t.id, value) for t in targets if isinstance(t, ast.Name)]
    return found


def config_dir_env_reads(tree: ast.Module) -> bool:
    """Does the module read `$CLAUDE_CONFIG_DIR` at all?"""
    return any(
        isinstance(node, ast.Constant) and node.value == CONFIG_DIR_ENV for node in ast.walk(tree)
    )


def write_violations(path: Path) -> list[str]:
    """Every write this module performs on a path derived from the config dir.

    Reads the file before anything else (B1): a scan that cannot raise on a
    missing path is a scan that never opened one.
    """
    tree = parsed(path)
    taint = _Taint(tree)

    def writes_mode(node: ast.Call) -> bool:
        positional = node.args[1] if len(node.args) > 1 else None
        keyword = next((k.value for k in node.keywords if k.arg == "mode"), None)
        mode = positional if positional is not None else keyword
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            return any(character in mode.value for character in WRITE_MODES)
        return mode is not None  # a computed mode is a mode a reader cannot check

    is_tainted = taint.is_tainted
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = _called_name(node)
        where = f"{path}:{node.lineno}"
        if isinstance(func, ast.Attribute) and name in WRITE_METHODS and is_tainted(func.value):
            found.append(f"{where}: {name}() on a path under the engine's config dir")
        elif isinstance(func, ast.Attribute) and name == "open" and is_tainted(func.value):
            if writes_mode(node):
                found.append(f"{where}: open() for writing under the engine's config dir")
        elif name == "open" and node.args and is_tainted(node.args[0]) and writes_mode(node):
            found.append(f"{where}: open() for writing under the engine's config dir")
        elif name in WRITE_FUNCTIONS and any(is_tainted(a) for a in node.args):
            found.append(f"{where}: {name}() on a path under the engine's config dir")
    return found


def scanned_files() -> list[Path]:
    return [
        path
        for root in SCAN_ROOTS
        for path in sorted(root.rglob("*.py"))
        if FIXTURE_DIR not in path.parents
    ]


def test_nothing_writes_under_the_engine_config_dir() -> None:
    """The rule, over `src/` and `tests/` both, recursively."""
    assert [message for path in scanned_files() for message in write_violations(path)] == []

    with pytest.raises(FileNotFoundError):
        write_violations(FIXTURE_DIR / "this_module_does_not_exist.py")

    # …and the rule bites on the planted write.
    violations = write_violations(fixture("src_writes_under_claude_home.py"))
    assert violations != [], "the scan does not see a write it was written to see"
    assert any("write_text" in message for message in violations), violations


def test_reading_the_config_dir_is_untouched() -> None:
    """The negative half, with its content asserted rather than assumed (B3).

    `tests/conftest.py` hashes the real `settings.json` and lists its siblings —
    the one contact P13 itself prescribes — and this rule must stay silent on it,
    or the next reader silences the rule instead.
    """
    conftest = TESTS_ROOT / "conftest.py"
    assert write_violations(conftest) == []
    tree = parsed(conftest)
    assert config_dir_env_reads(tree)  # it really does resolve the real directory
    source = conftest.read_text(encoding="utf-8")
    assert "read_bytes" in source and "iterdir" in source  # …and really does read it

    registry = SRC_ROOT / "engines" / "claude_code" / "registry.py"
    assert write_violations(registry) == []
    assert config_dir_env_reads(parsed(registry))


def test_the_scan_covers_both_trees() -> None:
    """Stated scope, checked. `src/` alone would miss every test helper."""
    walked = {path.parts[len(REPO_ROOT.parts)] for path in scanned_files()}
    assert walked == {"src", "tests"}
    assert len(scanned_files()) > 100


def test_the_rule_covers_the_config_file_and_not_only_the_directory() -> None:
    """`~/.claude.json` is a **sibling** of `~/.claude`, so the directory
    literals never matched it — and a write planted in `trust_state` therefore
    passed all 35 boundary tests while it sat live on disk (T10-R1). Reproduced
    on 2026-09-17: 39 passed, exit 0, with the write on disk.

    Four spellings, because a rule tested only against the form its author had
    in mind is untested against the form its defeater will use: through the
    resolver function, through the bare literal, through a module constant, and
    through `$CLAUDE_CONFIG_DIR`.
    """
    violations = write_violations(fixture("src_writes_the_engine_config_file.py"))
    lines = {int(message.split(":")[1]) for message in violations}
    functions = {
        "a_round_trip_through_the_resolver": "write_text",
        "a_literal_sibling_of_the_config_dir": "write_text",
        "the_filename_through_a_module_constant": "write_text",
        "through_the_environment_variable": "open",
    }
    source = fixture("src_writes_the_engine_config_file.py").read_text(encoding="utf-8")
    numbered = source.splitlines()
    for name, verb in functions.items():
        start = next(i for i, line in enumerate(numbered, 1) if line.startswith(f"def {name}"))
        hit = [n for n in lines if n > start and n <= start + 6]
        assert hit != [], f"{name}: the scan does not see its {verb}"

    # …and the rule stays quiet on the reads and on a same-named file that is
    # **not** the engine's: a negative control proving it does not over-match.
    assert write_violations(fixture("tests_write_a_claude_json_under_tmp_path.py")) == []
