"""§5.0's storage boundary (D26) — `store/` is the only DB importer.

The scan reads the file before it consults the package (B1): it used to return
early on `shepherd.store` above the open, and its negative self-check passed
that exact package, so it returned `[]` for a nonexistent path.

**Imports are resolved through `all_imports`, not `module_imports`** (QA-prep,
§T7-3). `__import__("sqlite3")` is an `ast.Call` and leaves no import node at
all: the bare helper reported this file clean while the driver was loaded and
`connect` was one attribute away. `module_imports` itself is unchanged — the
fifteen bare users were swapped, not the walker — and it is still read here, in
the assertion that keeps this rule's premise honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    DB_DRIVERS,
    MISSING_MODULE,
    STORE_PACKAGE,
    all_imports,
    fixture,
    in_package,
    iter_modules,
    module_imports,
)


def storage_violations(path: Path, package: str) -> list[str]:
    found = [
        f"{package} imports {imported}"
        for imported in sorted(all_imports(path))
        if imported.split(".")[0] in DB_DRIVERS
    ]
    return [] if in_package(package, STORE_PACKAGE) else found


def test_storage_boundary() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in storage_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        storage_violations(MISSING_MODULE, STORE_PACKAGE)

    # self-check: sqlite3 anywhere but store/ fails the build…  The reported set
    # is written out rather than asserted non-empty, because this rule was
    # **widened** from `module_imports` to `all_imports` in the QA-prep pass, and
    # a widening is only safe if what it caught before is still caught in the
    # same words (a non-emptiness assertion cannot tell one finding from another).
    leak = fixture("storage_sqlite_outside_store.py")
    assert storage_violations(leak, "shepherd.signals") == [
        "shepherd.signals imports sqlite3"
    ]
    # …and inside store/ it is exactly what is expected. The clean half is only
    # meaningful because the same file fires above (B1): the exemption silences
    # a real finding rather than an unread file.
    assert storage_violations(leak, STORE_PACKAGE) == []
    assert "sqlite3" in module_imports(leak)

    # …and the **call-shaped** spelling, which is the half the bare helper never
    # saw: `__import__("sqlite3")` leaves no import node anywhere in the file, so
    # a rule walking `ast.Import` alone reports it clean while the driver is
    # loaded (§T7-3). Drop `all_imports` back to `module_imports` and this line
    # is the one that goes red.
    dynamic = fixture("storage_sqlite_outside_store_dynamically.py")
    assert storage_violations(dynamic, "shepherd.signals") == [
        "shepherd.signals imports sqlite3"
    ]
    assert "sqlite3" not in module_imports(dynamic), (
        "module_imports has been widened — §T7-3's premise needs re-reading"
    )
    assert storage_violations(dynamic, STORE_PACKAGE) == []
