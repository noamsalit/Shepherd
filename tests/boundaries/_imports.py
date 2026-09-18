"""Shared AST walker for the boundary tests (T2).

Every scan here is **AST-based, never textual** (r3 F4). Two separate node
classes are inspected and never mixed: `ast.Constant` **string values**, and
`ast.Attribute`/`ast.Name` **identifiers**. That is what keeps a field named
`socket_path_budget` from ever tripping a rule about the path literal
`sun_path`, and it is why no scan needs an exemption.

Nothing here imports the modules under test: a module that fails to import must
still be analysable.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from _parse import parsed

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "shepherd"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DOCTOR_CAPTURE = (
    REPO_ROOT
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "hooks"
    / "live"
    / "R03_config_unknown_event_name"
    / "doctor.txt"
)

#: ADR-1's layer map. `testkit/` is deliberately absent: §14.2 ships it with the
#: package but it is not a layer, so it is neither an importer nor a target here.
LAYER_OF: dict[str, int] = {
    "shepherd.core": 1,
    "shepherd.store": 1,
    "shepherd.logs": 1,
    "shepherd.host": 2,
    "shepherd.engines": 2,
    "shepherd.signals": 2,
    "shepherd.runner": 2,
    "shepherd.providers": 2,
    "shepherd.orchestration": 3,
    "shepherd.toolsurface": 4,
    "shepherd.web": 5,
    "shepherd.cli": 5,
    "shepherd.master": 5,
    "shepherd.daemons": 6,
}

#: What no L5 consumer may import (D19, D35) — and `shepherd.logs` with them
#: (P-M2-10, D25's guardrail): nothing the UI renders may come to read a log.
#: Three product docstrings cited that rule as enforced while nothing enforced
#: it, which is how the next builder is misled.
FORBIDDEN_BELOW_L4: frozenset[str] = frozenset(
    {
        "shepherd.store",
        "shepherd.signals",
        "shepherd.logs",
        "shepherd.engines",
        "shepherd.runner",
        "shepherd.providers",
        "shepherd.orchestration",
    }
)

CONSUMER_PACKAGES: tuple[str, ...] = ("shepherd.web", "shepherd.cli", "shepherd.master")
#: L4. Not a consumer — it imports `signals/` and `store/` by design — but it is
#: bound by P-M2-10's log rule, which is scanned over it separately.
TOOLSURFACE_PACKAGE = "shepherd.toolsurface"
LOG_PACKAGE = "shepherd.logs"
STORE_PACKAGE = "shepherd.store"
DAEMONS_PACKAGE = "shepherd.daemons"
ENGINE_PACKAGE = "shepherd.engines.claude_code"
SIGNALS_PACKAGE = "shepherd.signals"
HOST_ONLY_PACKAGE = "shepherd.host"

DB_DRIVERS: frozenset[str] = frozenset(
    {"sqlite3", "aiosqlite", "psycopg", "psycopg2", "asyncpg", "pymysql", "MySQLdb", "sqlalchemy"}
)

#: The ONE declared structural exclusion (ADR-6, F4): the value of a field named
#: `evidence` in a `FoldRule` construction. Named once, here.
EVIDENCE_FIELD_NAME = "evidence"
EVIDENCE_OWNER_CALL = "FoldRule"

#: D55, made mechanical. The two sets are matched against different node classes.
PLATFORM_PATH_LITERALS: tuple[str, ...] = (
    "/proc",
    "systemctl",
    "loginctl",
    "launchctl",
    "/run/user",
    "XDG_",
    "nc -U",
)
#: **ORIGIN** symbols, matched only after alias resolution (r6). A local spelling
#: is never in this set — `import sys as s; s.platform` resolves to `sys.platform`
#: before it is matched, exactly as `module_imports` already resolves imports.
#:
#: `os.name`, `platform.machine` and `sysconfig.get_platform` are here because
#: D55's claim is "nothing else may branch on platform" and `os.name` is one of
#: the two most common ways to do it in Python. Widening the set is the whole
#: point: a rule that names only the spellings its author thought of is a rule
#: its defeater has never met.
PLATFORM_IDENTIFIERS: tuple[str, ...] = (
    "sys.platform",
    "platform.system",
    "platform.machine",
    "os.uname",
    "os.name",
    "sysconfig.get_platform",
)

#: The dispatch command's literals. One definition *package* — `host/` — but two
#: drivers, so `host/linux.py` and `host/mac.py` each carry their own (r4 A4).
DISPATCH_LITERALS: tuple[str, ...] = ("nc", "-q0")

MAX_SOURCE_LINES = 600
MAX_DAEMON_LINES = 150


@dataclass(frozen=True)
class Module:
    path: Path
    package: str


def package_of(path: Path) -> str:
    """The dotted package a source file belongs to, e.g. `shepherd.engines.claude_code`."""
    relative = path.resolve().relative_to(SRC_ROOT.parent)
    parts = list(relative.parts[:-1])
    return ".".join(parts) if parts else "shepherd"


def iter_modules() -> Iterator[Module]:
    """Every product source file, with its package. Tests are never scanned."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        yield Module(path=path, package=package_of(path))


#: A path that is never allowed to exist. Every rule asserts that scanning it
#: **raises** rather than returning `[]` (B1): five negative self-checks used to
#: early-return on their exempt package *before opening the file*, and each was
#: handed that exact exempt package — so they passed for a nonexistent path, and
#: emptying a fixture to `X = 1` left its test green. Every scan below therefore
#: reads the file first and applies the package exemption to the result.
MISSING_MODULE = FIXTURE_DIR / "this_module_does_not_exist.py"


def fixture(name: str) -> Path:
    path = FIXTURE_DIR / name
    assert path.exists(), f"missing boundary fixture {name!r} under {FIXTURE_DIR}"
    return path



# ----- Gate A: the consumer surface, frozen byte-for-byte (DP1, D38) ----------

#: D38's two consumer trees. The enumeration is `rglob("*")` over these with
#: `__pycache__` excluded — never a hand-written list (K19).
CONSUMER_ROOTS: tuple[Path, ...] = (SRC_ROOT / "web", SRC_ROOT / "cli")

#: Gate A's scope control, and it is the half revision 1 of the plan missed. A
#: digest comparison between two *empty* sets passes, and the negative control
#: still passes on its own fixture, so a moved root or a typo would make the
#: gate green by pointing at nothing. The live enumeration is asserted to
#: **contain** these four before anything is compared. They are written out on
#: purpose: they are the files D38's sentence is actually about.
KNOWN_CONSUMER_PATHS: frozenset[str] = frozenset(
    {"web/server.py", "web/routes.py", "cli/main.py", "cli/commands.py"}
)

#: Generated once, at step 0b, before any M4 code. Re-based **exactly once**, by
#: T24, which declares the paths it moved in the `rebase` block. No other task
#: may touch it: a manifest regenerable by whoever it inconveniences is not a
#: gate.
CONSUMER_MANIFEST = Path(__file__).resolve().parent / "consumer_manifest.json"
#: The negative control's own manifest, beside its tree rather than inside it —
#: a manifest inside the tree would be a file the enumeration digests.
DRIFT_FIXTURE_MANIFEST = FIXTURE_DIR / "consumer_manifest_drift.json"


def digest_set(roots: Sequence[Path], base: Path) -> frozenset[tuple[str, str]]:
    """`(posix path relative to `base`, sha256 hex)` for every regular file under `roots`.

    The same function runs over the live consumer trees and over the inert drift
    fixture, so the negative control exercises the comparison the gate uses —
    not a parallel one written to agree with it.
    """
    found: set[tuple[str, str]] = set()
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            found.add((path.relative_to(base).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return frozenset(found)


def consumer_digest_set() -> frozenset[tuple[str, str]]:
    return digest_set(CONSUMER_ROOTS, SRC_ROOT)


def digest_drift(
    recorded: Iterable[tuple[str, str]], live: Iterable[tuple[str, str]]
) -> tuple[list[str], list[str], list[str]]:
    """Three failure modes, three distinct answers: **added**, **removed**, **changed**.

    A single boolean would collapse "somebody added a file" and "somebody edited
    one" into the same message, and D38's diagnosis is the whole value of the
    gate.
    """
    was, now = dict(recorded), dict(live)
    added = sorted(set(now) - set(was))
    removed = sorted(set(was) - set(now))
    changed = sorted(path for path in set(was) & set(now) if was[path] != now[path])
    return added, removed, changed


def moved_paths(baseline: Mapping[str, str], current: Mapping[str, str]) -> frozenset[str]:
    """Every path whose digest differs between two manifest blocks, either direction.

    This is what makes T24's one permitted re-base *checkable*: `baseline` is the
    step-0b freeze and is never rewritten, so the set of paths that moved can
    still be computed after the re-base and compared against the set T24
    declares. Without a retained baseline, "which digests moved?" is
    unanswerable and a re-base could absorb an unrelated change in silence.
    """
    was, now = dict(baseline), dict(current)
    return frozenset(path for path in set(was) | set(now) if was.get(path) != now.get(path))


def _read_manifest(path: Path) -> dict[str, object]:
    """Reads the file first, always (B1): a manifest reader that cannot raise never opened one."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), path
    return loaded


def consumer_manifest() -> dict[str, object]:
    return _read_manifest(CONSUMER_MANIFEST)


def drift_fixture_manifest() -> dict[str, object]:
    return _read_manifest(DRIFT_FIXTURE_MANIFEST)


def manifest_block(manifest: Mapping[str, object], name: str) -> dict[str, str]:
    block = manifest[name]
    assert isinstance(block, dict), (name, type(block))
    return {str(key): str(value) for key, value in block.items()}


def modules_defining(name: str) -> list[Module]:
    """Every product module that binds `name` at module level — by AST, never import.

    Discovery by **property, not filename** (B2). Two rules were permanent
    no-ops behind `if MODULE.exists():`: a genuinely leaking `hookd_command.py`
    failed correctly, and renaming it to `hookd_cmd.py` returned the suite to
    green. A rule that can be switched off with `git mv` is not a rule.
    """
    found: list[Module] = []
    for module in iter_modules():
        for node in ast.iter_child_nodes(parsed(module.path)):
            bound: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound = [node.name]
            elif isinstance(node, ast.Assign):
                bound = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                bound = [node.target.id]
            if name in bound:
                found.append(module)
                break
    return found



# ----- DP3 / DP4: the two L4 import properties, in every spelling -------------

#: The call-shaped import spellings. `importlib.import_module("x")` and
#: `__import__("x")` are **`ast.Call` nodes, not import nodes**: a rule that
#: walks `ast.Import`/`ast.ImportFrom` alone reports both as clean while the
#: module is loaded and the cost is paid identically. Matched after alias
#: resolution, so `from importlib import import_module` is the same rule.
DYNAMIC_IMPORT_CALLS: frozenset[str] = frozenset({"importlib.import_module", "__import__"})

#: DP4. `cli/` imports `toolsurface.registry`, so a vendor import below L5 makes
#: `shepherd status` pay to load a package shipping a 216,677,784-byte binary.
VENDOR_SDK_ROOTS: frozenset[str] = frozenset({"claude_agent_sdk", "mcp"})

#: Derived from `LAYER_OF` at test time, never listed (K19): every layer below
#: L5, plus the two L5 consumers. `shepherd.master` is the one package outside
#: it — D19 names it as the SDK's home. `shepherd.daemons` (L6) is above the
#: rule's own scope; that gap is recorded in the M4 blockers file rather than
#: quietly widened here.
NO_VENDOR_SDK_PACKAGES: frozenset[str] = frozenset(
    package for package, layer in LAYER_OF.items() if layer < 5
) | {"shepherd.web", "shepherd.cli"}

#: DP3's discovery, by **property**: the module that defines the audit sink
#: factory is the single `toolsurface` module permitted to import `shepherd.logs`.
#: Never a filename and never an exemption list — a rule that can be switched off
#: with `git mv` is not a rule.
AUDIT_SINK_FACTORY = "build_audit_sink"

#: The one declared non-layer, and the reason is already in `LAYER_OF`'s own
#: docstring: §14.2 ships `testkit/` with the package, but it is not a layer.
NOT_A_LAYER: frozenset[str] = frozenset({"shepherd.testkit"})

SPEC = REPO_ROOT / "docs" / "specs" / "orchestrator-platform.md"
_SPEC_LAYER_ROW = re.compile(r"^\|\s*\*\*L\d")
_SPEC_MODULE = re.compile(r"`([a-z_]+)/`")


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"` bindings — how a dynamic import names its target."""
    found: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value.value
    return found


def dynamic_import_targets(path: Path) -> frozenset[str]:
    """Modules imported by **call** rather than by statement (r6's lesson, one layer over).

    Resolves the callee through `_alias_origins` — so `from importlib import
    import_module` is seen — and the argument through module-level string
    constants, which is how the idiomatic version of this spelling is actually
    written.
    """
    tree = parsed(path)
    origins = _alias_origins(tree)
    constants = _module_string_constants(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _dotted(node.func)
        if callee is None:
            continue
        head, _, rest = callee.partition(".")
        origin = origins.get(head)
        if origin is not None:
            callee = f"{origin}.{rest}" if rest else origin
        if callee not in DYNAMIC_IMPORT_CALLS:
            continue
        for argument in node.args[:1]:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.add(argument.value)
            elif isinstance(argument, ast.Name) and argument.id in constants:
                found.add(constants[argument.id])
    return frozenset(found)


def all_imports(path: Path) -> frozenset[str]:
    """Every module this file pulls in, by statement **or** by call.

    `module_imports` alone is a spelling. The shipped rules that still use it
    bare are listed in the M4 blockers file as a known gap, not silently changed
    here: widening the walker under fifteen live rules is not this task's to take.
    """
    return module_imports(path) | dynamic_import_targets(path)


def audit_writer_paths() -> frozenset[Path]:
    """DP3's single permitted L4 logs importer, discovered by property."""
    return frozenset(
        module.path
        for module in modules_defining(AUDIT_SINK_FACTORY)
        if in_package(module.package, TOOLSURFACE_PACKAGE)
    )


def logs_importer_violations(
    path: Path, package: str, *, permitted: frozenset[Path]
) -> list[str]:
    """D25, widened from the shipped approximation of it (DP3).

    **This is the single function that was widened.** `consumer_violations` and
    `FORBIDDEN_BELOW_L4` are the other path to the same rule and were left
    alone deliberately: they never bound `toolsurface/` (their `is_consumer`
    guard excludes L4), and the packages they do bind — `web/`, `cli/`,
    `master/` — stay at zero importers forever. A later builder loosening this
    one has loosened one thing; loosening both would take D25 off the board.

    Rejected, out loud, where the temptation is: an exemption list naming
    `shepherd.toolsurface.audit` (K11), and moving the writer to
    `orchestration/` so `toolsurface/` may import it freely — the rule's letter
    survives and its purpose is defeated.

    Reads the file first, always (B1): the package check is applied to the
    result, never above the open.
    """
    imported = sorted(i for i in all_imports(path) if in_package(i, LOG_PACKAGE))
    scanned = (*CONSUMER_PACKAGES, TOOLSURFACE_PACKAGE)
    if not any(in_package(package, candidate) for candidate in scanned):
        return []
    if in_package(package, TOOLSURFACE_PACKAGE) and path in permitted:
        return []
    return [f"{package} imports {name}" for name in imported]


def single_logs_importer_violations(
    modules: Iterable[Module], permitted: frozenset[Path]
) -> list[str]:
    """"Exactly one" is an **equality**, not a licence (P-M4-6).

    Three ways to fail, and all three matter: a second L4 module importing the
    log; a declared writer that imports no log (the discovery found the wrong
    module); and more than one module defining the factory at all.
    """
    importers = {
        module.path
        for module in modules
        if in_package(module.package, TOOLSURFACE_PACKAGE)
        and any(in_package(name, LOG_PACKAGE) for name in all_imports(module.path))
    }
    found: list[str] = []
    if len(permitted) > 1:
        found.append(
            f"more than one toolsurface module defines {AUDIT_SINK_FACTORY}: "
            f"{sorted(path.name for path in permitted)}"
        )
    found += [
        f"{path.name} imports {LOG_PACKAGE} and is not the audit writer"
        for path in sorted(importers - permitted)
    ]
    found += [
        f"{path.name} defines {AUDIT_SINK_FACTORY} but imports no log"
        for path in sorted(permitted - importers)
    ]
    return found


def vendor_scanned(package: str) -> bool:
    return any(in_package(package, candidate) for candidate in NO_VENDOR_SDK_PACKAGES)


def vendor_sdk_violations(path: Path, package: str) -> list[str]:
    """DP4 (P-M4-7). Reads the file first (B1); the package check applies to the result."""
    imported = sorted(
        name for name in all_imports(path) if name.split(".")[0] in VENDOR_SDK_ROOTS
    )
    if not vendor_scanned(package):
        return []
    return [f"{package} imports {name}" for name in imported]


def built_packages() -> frozenset[str]:
    """Every top-level package that actually exists under `src/shepherd/`."""
    return frozenset(
        f"shepherd.{child.name}"
        for child in SRC_ROOT.iterdir()
        if child.is_dir() and child.name != "__pycache__" and any(child.rglob("*.py"))
    )


def spec_layer_packages() -> frozenset[str]:
    """The module names §5.0's layer table declares — read from the spec, not listed here."""
    found: set[str] = set()
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if not _SPEC_LAYER_ROW.match(line):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        found.update(f"shepherd.{name}" for name in _SPEC_MODULE.findall(cells[2]))
    return frozenset(found)


def layer_map_violations(
    layer_keys: frozenset[str], built: frozenset[str], declared: frozenset[str]
) -> list[str]:
    """Both halves of "every layer entry names a real package", as the tree allows.

    The plan asked only for *every key resolves to a package that exists*. That
    is false by design here: step 0b row 4 requires `shepherd.master` in
    `LAYER_OF` **before** `master/` is built, so D19's rule bites the moment it
    appears, and `shepherd.providers` is the same shape. Deleting either entry to
    turn the rule green would switch off the rule the entry exists to arm.

    So: every built package has a layer — an unlayered package escapes
    `direction_violations` and `consumer_violations` entirely — and every layer
    entry with no package on disk is one §5.0's own table declares.
    """
    found = [
        f"{package} is a built package with no entry in LAYER_OF"
        for package in sorted(built - layer_keys - NOT_A_LAYER)
    ]
    found += [
        f"LAYER_OF names {package}, which is neither built nor declared by the spec's layer table"
        for package in sorted(layer_keys - built)
        if package not in declared
    ]
    return found


def in_package(package: str, root: str) -> bool:
    return package == root or package.startswith(root + ".")


def module_imports(path: Path) -> frozenset[str]:
    """Fully qualified module names imported by `path`, relative imports resolved."""
    found: set[str] = set()
    base = package_of(path) if path.resolve().is_relative_to(SRC_ROOT) else ""
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                prefix = node.module or ""
            else:
                anchor = base.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                prefix = ".".join([*anchor, node.module] if node.module else anchor)
            if prefix:
                found.add(prefix)
                found.update(f"{prefix}.{alias.name}" for alias in node.names)
    return frozenset(found)


def _binds_real_fold_rule(tree: ast.Module) -> bool:
    """Does the bare name `FoldRule` in this module mean **our** `FoldRule`? (C6)

    The exclusion used to be keyed on the callee's bare *name*, so a locally
    declared `class FoldRule`, `m.FoldRule(...)` and `a.b.FoldRule(...)` each
    switched the engine-vocabulary scan off. A declared structural exclusion has
    to be anchored to the declared type, or it is an exemption wearing a costume.

    Two ways the name can be real: the module imports it from `shepherd.*`
    (`signals/fold.py` and the rule table's consumers), or the module **is** the
    definition site — ADR-6's `@dataclass(frozen=True) class FoldRule` carrying an
    annotated `evidence` field (`signals/rules.py`). A bare `class FoldRule: ...`
    smuggling event names is neither.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("shepherd"):
            if any(
                alias.asname is None and alias.name == EVIDENCE_OWNER_CALL
                for alias in node.names
            ):
                return True
        if isinstance(node, ast.ClassDef) and node.name == EVIDENCE_OWNER_CALL:
            frozen = any(
                isinstance(decorator, ast.Call)
                and any(
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in decorator.keywords
                )
                for decorator in node.decorator_list
            )
            annotates_evidence = any(
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == EVIDENCE_FIELD_NAME
                for statement in node.body
            )
            if frozen and annotates_evidence:
                return True
    return False


def _is_fold_rule_call(node: ast.AST, real: bool) -> bool:
    """True for a `FoldRule(...)` construction — the one declared exclusion owner.

    A **bare `ast.Name`** only (C6): `m.FoldRule(...)` is some other module's
    type, and the exclusion is one position on one type, not one identifier.
    """
    if not isinstance(node, ast.Call) or not real:
        return False
    func = node.func
    return isinstance(func, ast.Name) and func.id == EVIDENCE_OWNER_CALL


def _docstring_literal_ids(tree: ast.Module) -> set[int]:
    """The `ast` definition of a docstring: the first statement of a body (r6).

    Docstrings are prose, not code. A `cli/` docstring reading `Stop the selected
    session.`, and one reading `Shows a Notification when Setup completes`, are
    ordinary English — and five of the 33 hook event names are ordinary words. A
    docstring cannot branch on a platform and cannot name a socket, so nothing is
    weakened — but a rule that cries wolf gets an exemption added to it, and
    ADR-1 calls that how boundaries die.
    """
    found: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes)):
                found.add(id(value))
    return found


def string_literals(
    path: Path,
    exclude_field: str | None = None,
    include_docstrings: bool = False,
) -> frozenset[str]:
    """Every string constant in `path`, **including `bytes` ones** (C5).

    `bytes` literals used to be invisible to every literal rule
    (`isinstance(node.value, str)`), so `b"/proc/self/stat"`, `b"-q0"` and
    `b"python -m shepherd.hookd"` were all clean. `Frame.payload` is `bytes` and
    the dispatcher is a socket write, so the transport layer is exactly where
    they appear. They are decoded latin-1 — total, never raises — and returned
    alongside the `str` ones so every rule gains the coverage at once.

    Docstrings are excluded unless `include_docstrings` (r6). When
    `exclude_field` is given, string values sitting in the one declared
    structural position — that keyword's value inside a real `FoldRule(...)`
    construction — are omitted. Nothing else is ever omitted.
    """
    tree = parsed(path)
    excluded: set[int] = set() if include_docstrings else _docstring_literal_ids(tree)
    if exclude_field is not None:
        real = _binds_real_fold_rule(tree)
        for node in ast.walk(tree):
            if _is_fold_rule_call(node, real):
                assert isinstance(node, ast.Call)
                for keyword in node.keywords:
                    if keyword.arg == exclude_field and isinstance(keyword.value, ast.Constant):
                        excluded.add(id(keyword.value))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in excluded:
            continue
        if isinstance(node.value, str):
            found.add(node.value)
        elif isinstance(node.value, bytes):
            found.add(node.value.decode("latin-1"))
    return frozenset(found)


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def identifiers(path: Path) -> frozenset[str]:
    """Plain names and dotted attribute chains, e.g. `sys.platform`, `socket_path_budget`."""
    found: set[str] = set()
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
            dotted = _dotted(node)
            if dotted is not None:
                found.add(dotted)
    return frozenset(found)


def _alias_origins(tree: ast.Module) -> dict[str, str]:
    """Local name -> the ORIGIN it was imported from (r6).

    `import sys as s` -> `{"s": "sys"}`; `from sys import platform` ->
    `{"platform": "sys.platform"}`; `from platform import system as sysname` ->
    `{"sysname": "platform.system"}`.
    """
    origins: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                origins[local] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                origins[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return origins


def resolved_identifiers(path: Path) -> frozenset[str]:
    """Dotted chains with their head bound back to its **origin** module (r6).

    This is the identifier half of the alias-proofing `module_imports` has always
    had on the import half. Revision 5 matched three fixed dotted spellings and
    every one of `import sys as s; s.platform`, `from sys import platform`,
    `import platform as pf; pf.system()` and `from os import uname` walked past
    it. The `from x import y` forms are the important half: they leave no dotted
    chain at all, so no amount of dotted-spelling enumeration can ever see them.

    Only resolved chains are returned — never a bare attribute name — so a field
    called `.name` can never be mistaken for `os.name`.

    **A bare-name *call* is the one exception, and it is the QA-prep widening**
    (§T22-3's fourth instance of `module_imports`' blindness, one AST node class
    over). `open(path)` binds no alias and leaves no dotted chain, so it resolved
    to nothing here and a rule reading this helper could not see a capability
    builtin at all — `core_capability_violations` carried a second, inline
    `ast.walk` for exactly that, which is a boundary rule with two halves in two
    places. A **callee** is unambiguous in the way a bare attribute is not: it is
    the thing being invoked, never a field somebody named. So bare names are
    collected when, and only when, they are called.

    Note that `identifiers()` was never blind to this — it collects every
    `ast.Name` id, and `'open' in identifiers(core_grows_io.py)` is `True` on
    this tree. The blindness was `resolved_identifiers`' alone, and the shipped
    comment in `test_master_isolation.py` attributed it to the wrong helper.
    """
    tree = parsed(path)
    origins = _alias_origins(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found.add(origins.get(node.func.id, node.func.id))
        if isinstance(node, ast.Name):
            origin = origins.get(node.id)
            if origin is not None:
                found.add(origin)
        elif isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted is None:
                continue
            head, _, rest = dotted.partition(".")
            origin = origins.get(head)
            found.add(f"{origin}.{rest}" if origin is not None and rest else dotted)
    return frozenset(found)


def mentions_word(literal: str, word: str) -> bool:
    """Whole-word containment — `"§Notification"` mentions `Notification`.

    Word-bounded, never a substring (r6): `/proc` must not match inside
    `/procedure`, and `/procedure` is not a path to anything.
    """
    return re.search(rf"(?<![0-9A-Za-z_]){re.escape(word)}(?![0-9A-Za-z_])", literal) is not None


def mentions_token(literal: str, token: str) -> bool:
    """Word-bounded containment for path and command tokens (r6).

    Unlike `mentions_word` the token may itself contain non-word characters
    (`/proc`, `nc -U`, `XDG_`), so the boundary is asserted only where the token
    actually has a word character to bound.
    """
    prefix = r"(?<![0-9A-Za-z_])" if token[:1].isalnum() or token[:1] == "_" else ""
    suffix = r"(?![0-9A-Za-z_])" if token[-1:].isalnum() or token[-1:] == "_" else ""
    return re.search(rf"{prefix}{re.escape(token)}{suffix}", literal) is not None




@lru_cache(maxsize=1)
def hook_event_names_from_doctor_capture() -> tuple[str, ...]:
    """The 33 names, parsed from the `claude doctor` capture that lists them (G13).

    `hooks/binary/hook-events.json` is empty on disk, so this capture is the only
    source of truth for the list and its order.
    """
    text = DOCTOR_CAPTURE.read_text(encoding="utf-8")
    marker = "Valid events:"
    start = text.index(marker) + len(marker)
    listed = text[start:].strip().splitlines()[0]
    return tuple(name.strip() for name in listed.split(",") if name.strip())


#: Test-package only. Product code never imports this (r4 A7).
CLAUDE_CODE_HOOK_EVENT_NAMES: tuple[str, ...] = hook_event_names_from_doctor_capture()


def hook_event_names_from_events_module(path: Path) -> tuple[str, ...]:
    """Read `ALL_HOOK_EVENT_NAMES` out of a module by AST — never by importing it."""
    for node in ast.walk(parsed(path)):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "ALL_HOOK_EVENT_NAMES":
                if isinstance(value, (ast.Tuple, ast.List)):
                    return tuple(
                        element.value
                        for element in value.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    )
    return ()


# ----- D19's master predicate: ONE definition site (RD-T5-5, §T22-6) ---------

#: The package D19 bounds.
MASTER_PACKAGE = "shepherd.master"

#: D19, as an **allow-list of module prefixes** — moved here from
#: `tests/boundaries/test_master_isolation.py` in the QA-prep pass, because T21
#: had grown a **second** implementation of the same predicate inline in
#: `tests/toolsurface/test_client.py` and *"a rule copied into a second file is a
#: rule that can be widened in one place and keep biting from another"*
#: (RD-T5-5, and §T22-6 which named this exact one-line convergence). The two
#: agreed exactly, which is why the duplication — not either copy — was the
#: defect. `logs_importer_violations` lives here for the same reason.
#:
#: A name is permitted when it is one of these or lives under one, plus the
#: standard library, enumerated from `sys.stdlib_module_names` rather than
#: listed, because a list of stdlib names is a list that is wrong by the next
#: release.
#:
#: `shepherd.toolsurface.client` is the whole of the tool surface the master
#: sees, singular and deliberately. `shepherd.core` is here by **RD-T20-D19** and
#: it is a widening with a condition — `core_capability_violations` asserts the
#: condition. `shepherd.master` is here by **T21-9**: D19 bounds what the master
#: reaches *outside* itself. `claude_agent_sdk` and `anyio` are named in D19's
#: own sentence.
#:
#: **Adding an entry here is a plan change, not an edit** —
#: `test_the_allow_list_is_asserted_whole` compares this set against a literal
#: typed out in the test, so the two cannot be changed in one place.
MASTER_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "shepherd.toolsurface.client",
        "shepherd.core",
        "shepherd.master",
        "claude_agent_sdk",
        "anyio",
    }
)

#: D19's own vocabulary — *"never a direct import of storage, signals, queues, or
#: runners"* — restated as a floor beneath the allow-list. Redundant today, and
#: kept so the next widening is argued against a rule that still says what may
#: never be reached.
MASTER_FORBIDDEN_FLOOR: frozenset[str] = frozenset(
    {
        "shepherd.store",
        "shepherd.logs",
        "shepherd.orchestration",
        "shepherd.daemons",
        "shepherd.web",
        "shepherd.signals",
        "shepherd.runner",
        "shepherd.engines",
        "shepherd.providers",
    }
)


def permitted_master_import(name: str) -> bool:
    """Is `name` a module a `master/` module may pull in?

    Prefix matching on **module boundaries**, never `startswith` on the raw
    string: `shepherd.core` must not permit a package called `shepherd.corestore`.
    """
    if name.split(".")[0] in sys.stdlib_module_names:
        return True
    return any(
        name == allowed or name.startswith(f"{allowed}.")
        for allowed in MASTER_ALLOWED_IMPORTS
    )


def master_import_violations(path: Path, package: str) -> list[str]:
    """Every module `path` pulls in that D19's allow-list does not permit.

    Resolved through `all_imports`, so the rule is not a spelling: statements,
    aliases, from-imports, `importlib.import_module(...)` and `__import__(...)`
    all arrive here as module names (§T7-3).

    **The file is read before the package exemption is applied** (B1): five
    shipped self-checks once early-returned on their exempt package *before*
    opening the file, so they passed for a path that did not exist.

    **The residual, named rather than papered over.** A dynamic import whose
    argument is not a module-level constant — `importlib.import_module(
    name_from_config)` — cannot be resolved statically by this or any AST rule.
    It is caught by the *live* half instead
    (`tests/e2e/test_live_master_isolation.py`), where `system/init` reports what
    the master actually holds rather than what its source appears to ask for.

    **This is the only definition of D19's master predicate in the tree**, and
    `tests/boundaries/test_one_definition_site.py` is what keeps it that way.
    """
    imported = all_imports(path)
    if not in_package(package, MASTER_PACKAGE):
        return []
    return sorted(name for name in imported if not permitted_master_import(name))



#: Re-exported so every boundary rule imports its walker from one place.
from _taint import mapping_read_keys, tainted_attribute_uses  # noqa: E402

__all__ = ["mapping_read_keys", "parsed", "tainted_attribute_uses"]
