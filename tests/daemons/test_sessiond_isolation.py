"""T10, D37 and §7 migration rule 3, made mechanical.

`controld` is the only process that writes the database, and `sessiond` never
migrates: it waits for the version over the UDS. Both claims are properties of
the **import closure** of whatever module runs the ingest socket, so that is
what is measured here — discovered by what a module declares (it imports
`ingest_socket`), never by its filename (B2). A rule that can be switched off
with `git mv` is not a rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: What a `sessiond` may never reach, transitively (D37, §7 rule 3).
FORBIDDEN_PACKAGE = "shepherd.store"

#: Every driver `store/` is allowed to import and nothing else ever is (D26).
DB_DRIVERS = frozenset({"sqlite3", "aiosqlite", "psycopg", "psycopg2", "asyncpg", "sqlalchemy"})

#: The ingest listener's module. A module importing it *is* a `sessiond`.
INGEST_MODULE = "shepherd.engines.claude_code.ingest_socket"

#: The accept loop itself. A module that imports **this symbol** runs a
#: `sessiond`; one that merely shares the socket helpers above it does not.
INGEST_ENTRYPOINT = f"{INGEST_MODULE}.serve_ingest"

MIGRATION_NAMES = frozenset({"migrate", "MigrationRefused", "MIGRATIONS_DIR"})


def module_of(path: Path) -> str:
    return ".".join(path.resolve().relative_to(SRC_ROOT.parent).with_suffix("").parts)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imports_of(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def path_of(module: str) -> Path | None:
    candidate = SRC_ROOT.parent / Path(*module.split("."))
    for option in (candidate.with_suffix(".py"), candidate / "__init__.py"):
        if option.exists():
            return option
    return None


def closure(entry: Path) -> dict[str, Path]:
    """Every product module reachable from `entry` by import, `entry` included."""
    found: dict[str, Path] = {module_of(entry): entry}
    pending = [entry]
    while pending:
        for imported in sorted(imports_of(pending.pop())):
            if not imported.startswith("shepherd") or imported in found:
                continue
            path = path_of(imported)
            if path is None:  # a symbol, not a module
                continue
            found[imported] = path
            pending.append(path)
    return found


def sessiond_entrypoints() -> list[Path]:
    """Discovery by property: the modules that run the ingest socket."""
    return [
        path
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if INGEST_ENTRYPOINT in imports_of(path)
    ]


def test_the_rule_has_a_target() -> None:
    """A property with no subject is a green test that proves nothing."""
    entrypoints = sessiond_entrypoints()
    assert entrypoints != [], f"no module imports {INGEST_ENTRYPOINT}"
    assert path_of(FORBIDDEN_PACKAGE) is not None, "the forbidden package must exist to be forbidden"

    # …and the closure walker really walks: the listener reaches `core.frames`.
    reached = closure(SRC_ROOT / "engines" / "claude_code" / "ingest_socket.py")
    assert "shepherd.core.frames" in reached
    assert "shepherd.host.base" in reached


def test_sessiond_never_opens_the_database() -> None:
    """D37: `controld` is the only writer. `sessiond` cannot even reach one."""
    violations: list[str] = []
    for entry in sessiond_entrypoints():
        for module, path in closure(entry).items():
            if module.startswith(FORBIDDEN_PACKAGE):
                violations.append(f"{module_of(entry)} reaches {module}")
            drivers = sorted(imports_of(path) & DB_DRIVERS)
            violations += [f"{module_of(entry)} reaches {module} which imports {d}" for d in drivers]
    assert violations == []


def test_sessiond_never_migrates() -> None:
    """§7 rule 3: it waits for `controld` to report the version over the UDS."""
    violations: list[str] = []
    for entry in sessiond_entrypoints():
        for module, path in closure(entry).items():
            named = sorted(
                node.id
                for node in ast.walk(parse(path))
                if isinstance(node, ast.Name) and node.id in MIGRATION_NAMES
            )
            violations += [f"{module_of(entry)} reaches {module} which names {name}" for name in named]
    assert violations == []
