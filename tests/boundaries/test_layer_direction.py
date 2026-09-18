"""§5.0's general rule, not just the L5 case (F5, P21).

`orchestrator-platform.md:225-227`: dependencies point down only. Revision 2's
ADR-4 had `signals/` (L2) publishing into `toolsurface/` (L4) with no test to
catch it; this is that test.

**Imports are resolved through `all_imports`, not `module_imports`** (QA-prep,
§T7-3). An upward import is upward whichever node class carries it, and
`importlib.import_module("shepherd.toolsurface.stream")` is an `ast.Call` the
bare helper never walked. The walker itself is unchanged; it is still read below,
in the assertion that keeps this rule's premise honest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    LAYER_OF,
    MISSING_MODULE,
    all_imports,
    fixture,
    in_package,
    iter_modules,
    module_imports,
)


def layer_of_module(package: str) -> int | None:
    for candidate, layer in LAYER_OF.items():
        if in_package(package, candidate):
            return layer
    return None  # testkit/ and `shepherd` itself are not layers.


def direction_violations(path: Path, package: str) -> list[str]:
    own_layer = layer_of_module(package)
    if own_layer is None:
        return []
    found: list[str] = []
    for imported in sorted(all_imports(path)):
        if not in_package(imported, "shepherd"):
            continue
        target_layer = layer_of_module(imported)
        if target_layer is not None and target_layer > own_layer:
            found.append(f"{package} (L{own_layer}) imports {imported} (L{target_layer})")
    return found


def test_layer_direction_is_downward_only() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in direction_violations(module.path, module.package)
    ]
    assert violations == []

    # The map is the ADR-1 table, read as data.
    assert LAYER_OF["shepherd.core"] == 1
    assert LAYER_OF["shepherd.signals"] == 2
    assert LAYER_OF["shepherd.toolsurface"] == 4
    assert LAYER_OF["shepherd.daemons"] == 6

    with pytest.raises(FileNotFoundError):
        direction_violations(MISSING_MODULE, "shepherd.signals")

    # self-check: L2 publishing into L4 is the exact miss this test exists for.
    # The reported set is written out rather than asserted non-empty, because this
    # rule was **widened** in the QA-prep pass and a widening is only safe if what
    # it caught before is still caught in the same words.
    upward = fixture("signals_imports_toolsurface.py")
    assert direction_violations(upward, "shepherd.signals") == [
        "shepherd.signals (L2) imports shepherd.toolsurface.stream (L4)",
        "shepherd.signals (L2) imports shepherd.toolsurface.stream.publish (L4)",
    ]
    # …and the same import from the composition root is legitimate — silenced by
    # the layer, not by an unread file (B1): the fixture fires two lines above.
    assert direction_violations(upward, "shepherd.daemons") == []
    assert "shepherd.toolsurface.stream" in module_imports(upward)

    # …and the **call-shaped** spelling, which is the half the bare helper never
    # saw. Swap `all_imports` back to `module_imports` and this is the line that
    # goes red while the statement form above stays green.
    dynamic = fixture("signals_imports_toolsurface_dynamically.py")
    assert direction_violations(dynamic, "shepherd.signals") == [
        "shepherd.signals (L2) imports shepherd.toolsurface.stream (L4)"
    ]
    assert not [
        name for name in module_imports(dynamic) if name.startswith("shepherd.")
    ], sorted(module_imports(dynamic))
    assert direction_violations(dynamic, "shepherd.daemons") == []
