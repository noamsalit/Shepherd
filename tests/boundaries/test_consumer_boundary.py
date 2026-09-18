"""§5.0's consumer boundary (D19, D35) — the first of the two double lines.

The scan reads the file before it consults the package (B1): an exemption
applied above the open makes a check that passes for a file that is not there.

**`consumer_violations` now resolves imports through `all_imports`** (QA-prep,
§T7-3). It was one of the fifteen bare users of `module_imports`, which walks
`ast.Import`/`ast.ImportFrom` only: `importlib.import_module("shepherd.store.db")`
is an `ast.Call`, and a consumer spelling its store import that way was reported
clean while the store was loaded and reachable. `log_reader_violations` already
read `all_imports` — the widening brings the *second* line of this file up to the
first. The walker itself is unchanged, and it is still read below, in the
assertions that keep this rule's premise honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    CONSUMER_PACKAGES,
    MISSING_MODULE,
    DB_DRIVERS,
    FORBIDDEN_BELOW_L4,
    all_imports,
    audit_writer_paths,
    fixture,
    in_package,
    iter_modules,
    logs_importer_violations,
    module_imports,
)

#: DP3 widened this rule to D25's own text, and **this name is the only widening**:
#: exactly one `toolsurface` module — the one defining the audit sink factory,
#: found by property — may import `shepherd.logs`; `web/`, `cli/` and `master/`
#: stay at zero. The implementation moved to `_imports` so there is one function
#: rather than two that can drift apart, and `test_l4_import_rules` asserts this
#: name **is** that object. `consumer_violations` below was deliberately not
#: touched: it never bound L4 at all.
log_reader_violations = logs_importer_violations


def consumer_violations(path: Path, package: str) -> list[str]:
    found: list[str] = []
    for imported in sorted(all_imports(path)):
        root = imported.split(".")[0]
        if root in DB_DRIVERS or any(
            in_package(imported, forbidden) for forbidden in FORBIDDEN_BELOW_L4
        ):
            found.append(f"{package} imports {imported}")
    is_consumer = any(in_package(package, consumer) for consumer in CONSUMER_PACKAGES)
    return found if is_consumer else []


def test_no_consumer_and_no_tool_surface_reads_a_log() -> None:
    """P-M2-10 — the property that keeps a log a *log* (D25's guardrail)."""
    violations = [
        message
        for module in iter_modules()
        for message in log_reader_violations(
            module.path, module.package, permitted=audit_writer_paths()
        )
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        log_reader_violations(MISSING_MODULE, "shepherd.web", permitted=frozenset())

    leak = fixture("consumer_imports_a_log.py")
    assert log_reader_violations(leak, "shepherd.web", permitted=frozenset()) != []
    assert log_reader_violations(leak, "shepherd.toolsurface", permitted=frozenset()) != []
    # …and the L4 exception is the *only* thing the widening buys: the same file
    # declared as the audit writer is still a violation for a consumer (DP3).
    assert log_reader_violations(leak, "shepherd.web", permitted=frozenset({leak})) != []
    # …and silenced only by the layer, not by an unread file (B1).
    assert log_reader_violations(leak, "shepherd.signals", permitted=frozenset()) == []
    assert "shepherd.logs.stops" in module_imports(leak)


def test_consumer_boundary() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in consumer_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        consumer_violations(MISSING_MODULE, "shepherd.core")

    # self-check: the same scan on a violating module must bite… The reported sets
    # are written out rather than asserted non-empty, because this rule was
    # **widened** in the QA-prep pass and a widening is only safe if what it
    # caught before is still caught in the same words.
    store_leak = fixture("consumer_imports_store.py")
    sqlite_leak = fixture("consumer_opens_sqlite.py")
    assert consumer_violations(store_leak, "shepherd.web") == [
        "shepherd.web imports shepherd.store",
        "shepherd.web imports shepherd.store.open_store",
    ]
    assert consumer_violations(sqlite_leak, "shepherd.cli") == [
        "shepherd.cli imports sqlite3"
    ]
    # P-M2-10 rides in the same set: no consumer imports `shepherd.logs`.
    log_leak = fixture("consumer_imports_a_log.py")
    assert consumer_violations(log_leak, "shepherd.cli") != []
    # …and be silenced only by the layer, not by an unread file (B1).
    assert consumer_violations(store_leak, "shepherd.signals") == []
    assert "shepherd.store" in module_imports(store_leak)

    # …and the **call-shaped** spelling, which is the half the bare helper never
    # saw. Swap `all_imports` back to `module_imports` and this is the line that
    # goes red while every statement-form assertion above stays green — which is
    # what makes this a widening and not a rewrite.
    dynamic = fixture("consumer_imports_store_dynamically.py")
    assert consumer_violations(dynamic, "shepherd.web") == [
        "shepherd.web imports shepherd.store.db"
    ]
    assert not [
        name for name in module_imports(dynamic) if name.startswith("shepherd.")
    ], sorted(module_imports(dynamic))
    assert consumer_violations(dynamic, "shepherd.signals") == []
