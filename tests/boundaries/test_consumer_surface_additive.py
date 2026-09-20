"""Gate B (DP1) — the pre-M4 consumer surface is **structurally** unchanged.

Gate A is byte-level and is re-based once, at T24, because the chat page is a
file in `web/`. The moment it is re-based it stops being able to answer the
question D38 is really about — *did the shape of the consumer surface change?* —
for everything that came before. Gate B answers that one, and it is permanent:

* **Every pre-M4 `(route template → tool name)` pair is still there, pointing at
  the same tool.** A subset assertion, so T24's five additions are permitted;
  an equality would make the milestone that adds the chat page fail its own
  gate. What may **not** happen is a pre-M4 route quietly resolving somewhere
  else, which is the change D38's sentence is about and which a byte gate over a
  re-based manifest can no longer see.
* **`web/`'s and `cli/`'s module-import sets are additive-only, and every
  addition is named here.** Not "small", not "reviewed" — *named*, as a literal,
  compared by equality against what actually moved.
* **`web/server.py` is byte-unchanged**, which is T24's Exit Criteria stated as
  a digest rather than as a promise.

**Both comparisons ship with negative controls** (P-M4-5), and the controls
drive the *same* functions the live assertions do — a control that exercised a
parallel implementation would prove the control.

**The scope controls come first, for the reason Gate A's do:** a frozen set that
points at nothing is a subset of anything, and every assertion below would pass
on an empty file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path

import _imports as boundary

from shepherd.web import routes

FROZEN = Path(__file__).resolve().parent / "pre_m4_routes.json"

#: Routes that existed before M4 and are what D38's sentence is about. Written
#: out for the same reason `KNOWN_CONSUMER_PATHS` is: a frozen table that lost
#: its contents would make every comparison below vacuous.
KNOWN_PRE_M4_ROUTES: Mapping[str, str] = {
    "/api/fleet": "fleet_summary",
    "/api/sessions/{session_id}": "get_session",
    "/api/sessions/{session_id}/kill": "kill_session",
}

#: **T24's declared additions to the consumer import sets: none.** The chat page
#: is `chat.js`, some static markup and five entries in a path→name table, and a
#: route table is a mapping — it imports nothing to add a route. This is an
#: equality below, not a subset, so an import that arrives here without being
#: named is a failing build, and an entry named here that never arrived is one
#: too (a declaration nobody checks is the thing this file exists to refuse).
T24_ADDED_IMPORTS: Mapping[str, frozenset[str]] = {}

#: …and no new module under `web/` or `cli/` either: the page is static assets,
#: which are not Python and are Gate A's business.
T24_ADDED_MODULES: frozenset[str] = frozenset()


def frozen_surface() -> dict[str, object]:
    loaded = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), FROZEN
    return loaded


#: How an import set is read. A **parameter with a default** rather than a call
#: written into the loop, so the widened reader can be pointed at a planted
#: fixture and proved to bite — a reader nothing can exercise is the shape of the
#: defect Gate B exists to prevent.
ImportReader = Callable[[Path], frozenset[str]]


def live_imports(read: ImportReader = boundary.all_imports) -> dict[str, frozenset[str]]:
    """Every import of the live consumer trees, keyed the way the freeze is.

    **`all_imports`, not `module_imports`** (QA-prep, §T7-3). The freeze was
    recorded with the bare walker, which walks `ast.Import`/`ast.ImportFrom`
    only; a consumer that acquired `importlib.import_module("shepherd.store.db")`
    would have been *additive-nothing* to this gate while the store was loaded.
    Measured on the tree at the swap: the two readers agree on every consumer
    module, so the freeze is unchanged and the gate is strictly stronger.
    """
    found: dict[str, frozenset[str]] = {}
    for root in boundary.CONSUMER_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            found[path.relative_to(boundary.SRC_ROOT).as_posix()] = read(path)
    return found


def mapping_drift(
    frozen: Mapping[str, str], live: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    """Two distinct failures: a pre-M4 route **removed**, and one whose tool **moved**.

    Separate answers rather than one boolean, for `digest_drift`'s reason: which
    of the two happened is the whole diagnostic value of the gate.
    """
    removed = sorted(path for path in frozen if path not in live)
    moved = sorted(
        f"{path}: {frozen[path]} -> {live[path]}"
        for path in frozen
        if path in live and frozen[path] != live[path]
    )
    return removed, moved


def import_drift(
    frozen: Mapping[str, frozenset[str]], live: Mapping[str, frozenset[str]]
) -> tuple[list[str], list[str], list[str]]:
    """**gone** modules, **dropped** imports, and **added** imports, in that order."""
    gone = sorted(module for module in frozen if module not in live)
    dropped = sorted(
        f"{module}: {name}"
        for module, names in frozen.items()
        if module in live
        for name in sorted(names - live[module])
    )
    added = sorted(
        f"{module}: {name}"
        for module, names in live.items()
        for name in sorted(names - frozen.get(module, frozenset()))
    )
    return gone, dropped, added


def declared_additions() -> list[str]:
    return sorted(
        f"{module}: {name}"
        for module, names in T24_ADDED_IMPORTS.items()
        for name in sorted(names)
    )


def scope_violations(frozen: Mapping[str, object]) -> list[str]:
    """Gate B's scope controls, as a function so they can be proved to bite.

    Written inline they would be asserts nothing could exercise: the live tree
    always satisfies them, so their failure path would ship untested — which is
    the shape of the defect they exist to prevent.
    """
    found: list[str] = []
    api = frozen.get("api_routes")
    post = frozen.get("post_routes")
    imports = frozen.get("imports")
    if not isinstance(api, dict) or not api:
        found.append("the frozen GET table is empty — a comparison against nothing passes")
    if not isinstance(post, dict) or not post:
        found.append("the frozen POST table is empty — a comparison against nothing passes")
    if not isinstance(imports, dict) or not imports:
        found.append("the frozen import sets are empty")
    # The known-routes control runs **whatever** the tables turned out to be: a
    # freeze that is missing, empty or malformed is exactly the case where "it
    # contains the routes D38 is about" must fail, and a control that skipped
    # itself on a broken file would be silent in the one case it exists for.
    both = {**(api if isinstance(api, dict) else {}), **(post if isinstance(post, dict) else {})}
    missing = {
        path: tool for path, tool in KNOWN_PRE_M4_ROUTES.items() if both.get(path) != tool
    }
    if missing:
        found.append(f"the freeze is missing known pre-M4 routes: {sorted(missing)}")
    return found


def test_the_pre_m4_route_mappings_are_unchanged() -> None:
    frozen = frozen_surface()
    assert scope_violations(frozen) == []

    api = frozen["api_routes"]
    post = frozen["post_routes"]
    assert isinstance(api, dict) and isinstance(post, dict)

    removed, moved = mapping_drift(api, routes.API_ROUTES)
    assert removed == [], f"a pre-M4 read route is gone: {removed}"
    assert moved == [], f"a pre-M4 read route now names another tool: {moved}"

    removed, moved = mapping_drift(post, routes.POST_ROUTES)
    assert removed == [], f"a pre-M4 mutation route is gone: {removed}"
    assert moved == [], f"a pre-M4 mutation route now names another tool: {moved}"

    # Arrival: the comparison really ran over the pre-M4 surface, not over a
    # table that had shrunk to the routes T24 added.
    assert len(api) == 8 and len(post) == 7, (len(api), len(post))
    assert set(api) < set(routes.API_ROUTES)
    assert set(post) < set(routes.POST_ROUTES)


def test_the_route_comparison_bites() -> None:
    """P-M4-5's shape: the gate is only a gate if the two changes trip it.

    Literal tables, so the expected answer comes from this file rather than from
    the thing under test — a control built by re-running the comparison over the
    live tables would agree with it by construction.
    """
    was = {"/api/fleet": "fleet_summary", "/api/sessions": "list_sessions"}
    assert mapping_drift(was, was) == ([], [])
    assert mapping_drift(was, {**was, "/api/audit": "get_audit_log"}) == ([], [])

    repointed = {**was, "/api/fleet": "fleet_tree"}
    assert mapping_drift(was, repointed) == ([], ["/api/fleet: fleet_summary -> fleet_tree"])

    dropped = {"/api/sessions": "list_sessions"}
    assert mapping_drift(was, dropped) == (["/api/fleet"], [])


def test_the_consumer_import_sets_are_additive_only() -> None:
    frozen = frozen_surface()
    recorded = frozen["imports"]
    assert isinstance(recorded, dict)
    was = {module: frozenset(names) for module, names in recorded.items()}
    live = live_imports()

    assert was, "the frozen import sets are empty"
    assert len(live) >= 9, sorted(live)
    assert "web/server.py" in live and "cli/main.py" in live, sorted(live)

    gone, dropped, added = import_drift(was, live)
    assert gone == [], f"a consumer module disappeared: {gone}"
    assert dropped == [], f"a consumer module lost an import: {dropped}"
    assert added == declared_additions(), {
        "undeclared": sorted(set(added) - set(declared_additions())),
        "declared but absent": sorted(set(declared_additions()) - set(added)),
    }
    assert set(live) - set(was) == T24_ADDED_MODULES, sorted(set(live) - set(was))


def test_the_widened_reader_is_the_one_the_gate_runs_on() -> None:
    """§T7-3, at Gate B: a call-shaped import is an addition like any other.

    The reader is exercised on a **planted fixture** rather than on the live
    tree, because no consumer spells a dynamic import today — which is exactly
    when the branch would otherwise ship untested. Arrival first: the bare walker
    is shown to be blind to the same file, so the comparison below is about the
    widening and not about the fixture.
    """
    # The reader the gate actually runs on — its **default**, which is the wiring
    # and not a re-implementation of it. A widened helper that the gate does not
    # call is the "no caller" register's failure mode, one file over.
    assert live_imports.__defaults__ is not None
    reader = live_imports.__defaults__[0]
    assert reader is boundary.all_imports

    dynamic = boundary.FIXTURE_DIR / "consumer_imports_store_dynamically.py"
    assert "shepherd.store.db" in reader(dynamic)
    assert not [
        name for name in boundary.module_imports(dynamic) if name.startswith("shepherd.")
    ], sorted(boundary.module_imports(dynamic))
    assert "shepherd.store.db" in boundary.all_imports(dynamic)

    was = {"web/server.py": frozenset({"json"})}
    live = {"web/server.py": boundary.all_imports(dynamic)}
    gone, dropped, added = import_drift(was, live)
    assert gone == [] and dropped == ["web/server.py: json"]
    assert "web/server.py: shepherd.store.db" in added

    # …and the reader the gate actually runs on is the widened one: the same two
    # readers over the live trees agree today, which is *why* the swap changed no
    # frozen byte, and the equality says so rather than leaving it to a comment.
    assert live_imports() == live_imports(boundary.module_imports)


def test_the_import_comparison_bites() -> None:
    """The same three answers, on literals: an addition, a removal, a lost module."""
    was = {"web/server.py": frozenset({"json", "shepherd.web.routes"})}
    assert import_drift(was, was) == ([], [], [])
    assert import_drift(was, {}) == (["web/server.py"], [], [])

    widened = {"web/server.py": was["web/server.py"] | {"shepherd.store.db"}}
    assert import_drift(was, widened) == ([], [], ["web/server.py: shepherd.store.db"])

    narrowed = {"web/server.py": frozenset({"json"})}
    assert import_drift(was, narrowed) == ([], ["web/server.py: shepherd.web.routes"], [])


def test_web_server_is_byte_unchanged() -> None:
    """T24's Exit Criteria as a digest. `server.py` gains nothing: the chat page
    is a route table and static assets, and a handler body in `web/` is the
    drift ADR-M4-7 names."""
    frozen = frozen_surface()
    recorded = frozen["server_sha256"]
    assert isinstance(recorded, str) and len(recorded) == 64, recorded
    live = boundary.SRC_ROOT / "web" / "server.py"
    assert live.is_file(), live
    assert hashlib.sha256(live.read_bytes()).hexdigest() == recorded

    # …and it is the same digest Gate A's never-rewritten baseline holds, so the
    # two gates cannot disagree about which bytes they were frozen on.
    baseline = boundary.manifest_block(boundary.consumer_manifest(), "baseline")
    assert baseline["web/server.py"] == recorded


def test_the_scope_controls_refuse_a_freeze_that_points_at_nothing() -> None:
    """A frozen set that points at nothing is a subset of anything.

    Every assertion above would pass on an empty freeze — that is the failure
    mode DP1 added Gate A's three scope controls for at revision 2, and it
    applies unchanged here.
    """
    assert len(scope_violations({})) == 4
    assert scope_violations({"api_routes": {}, "post_routes": {}, "imports": {}}) != []

    filled = frozen_surface()
    emptied = {**filled, "api_routes": {}}
    messages = scope_violations(emptied)
    assert any("frozen GET table is empty" in message for message in messages), messages
    assert any("missing known pre-M4 routes" in message for message in messages), messages

    # …and a freeze whose tables are full but point at the wrong tools is caught
    # by the known-routes control rather than by the comparison it precedes.
    repointed = {**filled, "post_routes": {"/api/sessions/{session_id}/kill": "get_session"}}
    assert any(
        "missing known pre-M4 routes" in message for message in scope_violations(repointed)
    )
