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

#: **Post-M4 declared additions** (ruling 11, extended from bytes to imports):
#: the imports and modules a consumer gained *after* M4 closed, when a ruling
#: authorised the move. T24's tables above stay T24's; these are a second,
#: separate declaration, and every module path named here must also carry a
#: `post_milestone.edits` entry in the consumer manifest, so an import cannot
#: arrive without the same named reason a byte change needs. Filled by the
#: rulings plan's P13, from the phase ledgers.
POST_M4_ADDED_IMPORTS: Mapping[str, frozenset[str]] = {}

#: …and the post-M4 modules under `web/` or `cli/`, declared the same way.
POST_M4_ADDED_MODULES: frozenset[str] = frozenset()


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


def flattened(table: Mapping[str, frozenset[str]]) -> list[str]:
    return sorted(f"{module}: {name}" for module, names in table.items() for name in sorted(names))


def declared_additions() -> list[str]:
    return flattened(T24_ADDED_IMPORTS)


def addition_violations(
    added: list[str],
    new_modules: frozenset[str],
    post_m4_imports: Mapping[str, frozenset[str]],
    post_m4_modules: frozenset[str],
    manifest: Mapping[str, object],
) -> list[str]:
    """Gate B's additive-only rule, as a function so the controls drive it.

    `added` must equal T24's declared additions plus the post-M4 ones, and
    `new_modules` T24's declared modules plus the post-M4 ones — equalities, so
    a declaration that never arrived fails as surely as an arrival nobody
    declared. Every post-M4 module path must also carry a `post_milestone`
    entry in `manifest`: the named reason a byte change needs (ruling 11).
    """
    found: list[str] = []
    declared = set(declared_additions()) | set(flattened(post_m4_imports))
    modules = T24_ADDED_MODULES | post_m4_modules
    for label, names in (
        ("undeclared", set(added) - declared),
        ("declared but absent", declared - set(added)),
        ("undeclared modules", new_modules - modules),
        ("declared modules absent", modules - new_modules),
    ):
        if names:
            found.append(f"{label}: {sorted(names)}")
    unexplained = (set(post_m4_imports) | post_m4_modules) - boundary.post_milestone_paths(manifest)
    found.extend(
        f"{path}: a post-M4 addition with no post_milestone entry" for path in sorted(unexplained)
    )
    return found


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
    new_modules = frozenset(set(live) - set(was))
    assert addition_violations(
        added,
        new_modules,
        POST_M4_ADDED_IMPORTS,
        POST_M4_ADDED_MODULES,
        boundary.consumer_manifest(),
    ) == []


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


SERVER_PATH = "web/server.py"


def server_digest_violations(
    live: str, recorded: str, manifest: Mapping[str, object]
) -> list[str]:
    """The `server.py` digest pin, as a function so the controls drive it.

    Passes when `live` is the pinned digest, **or** (ruling 11) when `manifest`
    declares a `post_milestone.edits` entry for `web/server.py` and its `files`
    block holds exactly `live`. The pin stays: an undeclared edit, or a
    declaration whose `files` digest is stale, still fails.
    """
    if live == recorded:
        return []
    if SERVER_PATH not in boundary.post_milestone_paths(manifest):
        return [f"{SERVER_PATH} moved from the pinned digest with no post_milestone entry"]
    files = manifest.get("files")
    declared = files.get(SERVER_PATH) if isinstance(files, dict) else None
    if declared != live:
        return [f"{SERVER_PATH} is declared but files holds {declared}, not the live {live}"]
    return []


def test_web_server_is_byte_unchanged() -> None:
    """T24's Exit Criteria as a digest. `server.py` gains nothing: the chat page
    is a route table and static assets, and a handler body in `web/` is the
    drift ADR-M4-7 names.

    *Amended by owner ruling 11 (qa6 BC-32) and ADR-M4-7's 2026-09-27
    amendment:* a **declared** `post_milestone.edits` entry for `web/server.py`
    is accepted when the manifest `files` digest equals the live one. The pin
    itself (`server_sha256`, and the never-rewritten `baseline`) is unchanged.
    """
    frozen = frozen_surface()
    recorded = frozen["server_sha256"]
    assert isinstance(recorded, str) and len(recorded) == 64, recorded
    live = boundary.SRC_ROOT / "web" / "server.py"
    assert live.is_file(), live
    digest = hashlib.sha256(live.read_bytes()).hexdigest()
    assert server_digest_violations(digest, recorded, boundary.consumer_manifest()) == []

    # …and it is the same digest Gate A's never-rewritten baseline holds, so the
    # two gates cannot disagree about which bytes they were frozen on.
    baseline = boundary.manifest_block(boundary.consumer_manifest(), "baseline")
    assert baseline["web/server.py"] == recorded


#: Two literal digests, each the 64-hex shape of a real one.
PINNED = "a" * 64
EDITED = "b" * 64


def manifest_with(edits: list[dict[str, str]], files: Mapping[str, str]) -> dict[str, object]:
    return {"files": dict(files), "post_milestone": {"rule": "literal", "edits": edits}}


def declared_edit(path: str) -> dict[str, str]:
    return {"path": path, "at": "2026-09-27T00:00:00Z", "by": "a control", "why": "a literal"}


def test_an_undeclared_server_edit_is_caught() -> None:
    """Ruling 11 keeps the pin: an edit with no `post_milestone` entry fails,
    even when `files` already holds the new digest."""
    assert server_digest_violations(PINNED, PINNED, manifest_with([], {})) == []
    undeclared = manifest_with([declared_edit("web/sse.py")], {SERVER_PATH: EDITED})
    assert server_digest_violations(EDITED, PINNED, undeclared) != []
    assert server_digest_violations(EDITED, PINNED, {"files": {SERVER_PATH: EDITED}}) != []


def test_a_declared_server_edit_with_a_stale_files_digest_is_caught() -> None:
    """A declaration is not a blank cheque: `files` must hold the live digest."""
    stale = manifest_with([declared_edit(SERVER_PATH)], {SERVER_PATH: PINNED})
    assert server_digest_violations(EDITED, PINNED, stale) != []
    missing = manifest_with([declared_edit(SERVER_PATH)], {})
    assert server_digest_violations(EDITED, PINNED, missing) != []


def test_a_declared_server_edit_with_its_live_digest_is_accepted() -> None:
    """The arrival half of ruling 11: declared, and `files` holds the live bytes."""
    declared = manifest_with([declared_edit(SERVER_PATH)], {SERVER_PATH: EDITED})
    assert server_digest_violations(EDITED, PINNED, declared) == []


def test_a_post_m4_import_without_a_manifest_entry_is_caught() -> None:
    """A post-M4 import table entry needs a `post_milestone` entry for its path."""
    imports = {"cli/main.py": frozenset({"shepherd.toolsurface.rpc"})}
    added = ["cli/main.py: shepherd.toolsurface.rpc"]
    bare = manifest_with([], {})
    messages = addition_violations(added, frozenset(), imports, frozenset(), bare)
    assert any("no post_milestone entry" in m and "cli/main.py" in m for m in messages), messages

    module_only = manifest_with([declared_edit("cli/main.py")], {})
    new = frozenset({"cli/new.py"})
    messages = addition_violations([], new, {}, new, module_only)
    assert any("no post_milestone entry" in m and "cli/new.py" in m for m in messages), messages
    # The module half's positive control: the same module, declared, is accepted.
    new_declared = manifest_with([declared_edit("cli/new.py")], {})
    assert addition_violations([], new, {}, new, new_declared) == []

    declared =manifest_with([declared_edit("cli/main.py")], {})
    assert addition_violations(added, frozenset(), imports, frozenset(), declared) == []
    # …and an import the table does not name is still undeclared, manifest or not.
    stray = [*added, "cli/main.py: shepherd.store.db"]
    assert addition_violations(stray, frozenset(), imports, frozenset(), declared) != []


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
