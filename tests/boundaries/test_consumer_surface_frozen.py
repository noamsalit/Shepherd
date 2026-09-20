"""Gate A (DP1) — completing L4 changed no byte of `web/` or `cli/` (D38).

D38 is a sentence: *"if M4 changes a file in `web/` or `cli/`, the placeholder
had the wrong shape."* This module is the failing build that sentence asks for.

**Three scope controls run before the comparison, and they are the point.** If
the enumeration ever points at nothing — a moved root, a typo, a `Path` that
does not exist — the live set is empty, the manifest is empty, they match, and
even the negative control below still passes on its own fixture. So the roots
are asserted to be directories, the live enumeration is asserted **non-empty**,
and it is asserted to **contain** a written-out set of known paths. A scan of
nothing finds nothing.

**What is checkable here and what is not.** That the manifest matches is
checkable. That it was frozen *before* the registry work is **not provable in
this tree**: `git log -- docs/plans/` is empty, everything is untracked on one
baseline commit, and no ordering of edits is recoverable. The manifest carries
`generated_at` / `generated_by` and that claim is transcript evidence, recorded
as such (M3 clause 16 is the precedent).

**Edits after the milestone are a third block, not a second re-base (2026-09-20).**
D38's sentence is about *completing L4*: "if M4 changes a file in `web/` or
`cli/`, the placeholder had the wrong shape." M4 is closed and verified, so a
later edit made for an unrelated reason is outside what that sentence claims —
but it still may not pass unnoticed. `post_milestone.edits` names each one with
a path, a date, an agent and a reason; its paths must be disjoint from
`rebase.regenerated_paths`, so it can never relaunder a path T24 already moved;
and the drift equality now covers both lists, so an unrelated change still
cannot ride along. `rebase` remains T24's, spent exactly once, and `baseline` is
still never rewritten.

**This test is never deleted.** T24 re-bases the manifest exactly once, by name,
writing its declared paths into the `rebase` block; `baseline` is the step-0b
freeze and is never rewritten, which is what makes
`test_a_rebase_declares_every_path_whose_digest_moved` able to catch a later
regeneration that quietly absorbs an unrelated change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import _imports as boundary
from _parse import parsed


def scope_violations(roots: tuple[Path, ...], live: frozenset[tuple[str, str]]) -> list[str]:
    """Gate A's three scope controls, as a function **so they can be proved to bite**.

    Written inline they would be three asserts nothing could ever exercise: the
    live tree always satisfies them, so their failure path would ship untested —
    which is the same shape as the defect they exist to prevent.
    """
    found: list[str] = []
    for root in roots:
        if not root.is_dir():
            found.append(f"consumer root is not a directory: {root}")
    if not live:
        found.append("the consumer enumeration found nothing — a scan of nothing finds nothing")
    missing = boundary.KNOWN_CONSUMER_PATHS - {path for path, _ in live}
    if missing:
        found.append(f"the enumeration is missing known consumer paths: {sorted(missing)}")
    return found


def test_completing_l4_changed_no_consumer_byte() -> None:
    live = boundary.consumer_digest_set()
    assert scope_violations(boundary.CONSUMER_ROOTS, live) == []

    manifest = boundary.consumer_manifest()
    recorded = frozenset(manifest["files"].items())
    added, removed, changed = boundary.digest_drift(recorded, live)
    assert added == [], f"files added under web/ or cli/ since the freeze: {added}"
    assert removed == [], f"files removed from web/ or cli/ since the freeze: {removed}"
    assert changed == [], f"files changed under web/ or cli/ since the freeze: {changed}"


def test_the_manifest_comparison_detects_a_single_byte() -> None:
    """P-M4-5 — the negative control, without which the gate is decorative."""
    tree = boundary.fixture("consumer_manifest_drift")
    recorded = frozenset(boundary.drift_fixture_manifest()["files"].items())
    live = boundary.digest_set((tree,), tree)
    assert live, "the fixture enumeration found nothing"
    added, removed, changed = boundary.digest_drift(recorded, live)
    assert added == []
    assert removed == []
    assert changed == ["one_byte_from_its_digest.py"]


def test_gate_a_refuses_a_scan_that_points_at_nothing(tmp_path: Path) -> None:
    """The scope control, proved to bite — the half revision 1 of the plan missed.

    A moved root, a typo or a `Path` that does not exist makes the live set
    empty; the manifest it is compared against would then be empty too, they
    would match, and `test_the_manifest_comparison_detects_a_single_byte` would
    still pass on its own fixture. All three controls are exercised here against
    a root that is not there.
    """
    moved = tmp_path / "web-that-moved"
    empty = boundary.digest_set((moved,), tmp_path)
    assert empty == frozenset()
    messages = scope_violations((moved,), empty)
    assert len(messages) == 3, messages
    assert any("not a directory" in message for message in messages)
    assert any("scan of nothing" in message for message in messages)
    assert any("missing known consumer paths" in message for message in messages)

    # …and a root that IS a directory but holds nothing still fails the other two.
    moved.mkdir()
    assert [m for m in scope_violations((moved,), boundary.digest_set((moved,), tmp_path))
            if "not a directory" not in m] != []


def test_a_rebase_declares_every_path_whose_digest_moved() -> None:
    """T24's one permitted re-base is checkable, or it is not a gate (DP1).

    `baseline` is the step-0b freeze and is never rewritten; `files` is what Gate
    A compares against. So after T24 re-bases, the set of paths whose digests
    moved is still computable — and it must equal the set T24 declares. A
    re-base that quietly absorbs an unrelated change is caught rather than
    blessed.
    """
    manifest = boundary.consumer_manifest()
    baseline = boundary.manifest_block(manifest, "baseline")
    files = boundary.manifest_block(manifest, "files")
    assert baseline, "the baseline block is empty — nothing to re-base against"

    rebase = manifest["rebase"]
    assert isinstance(rebase, dict)
    declared = rebase["regenerated_paths"]
    assert isinstance(declared, list)

    # Edits made AFTER M4 closed are declared separately — see the module
    # docstring. They are NOT a second re-base: `rebase` is still T24's.
    later = boundary.post_milestone_paths(manifest)

    # Nothing may move without appearing in exactly one of the two lists.
    assert boundary.moved_paths(baseline, files) == frozenset(declared) | later

    # A post-milestone entry may never relaunder a path T24 already moved:
    # were the lists allowed to overlap, a second edit to a re-based file
    # would satisfy the equality above while naming no new path at all.
    assert later.isdisjoint(frozenset(declared)), sorted(later & frozenset(declared))

    # Exactly one re-base is permitted, and only T24 may take it.
    assert rebase["regenerated_by"] in (None, "T24"), rebase["regenerated_by"]

    # The companion assertion, proved to bite on literals rather than trusted:
    # an undeclared move is caught, and a declared path that did not move is too.
    was = {"web/routes.py": "aa", "cli/main.py": "bb"}
    absorbed = {"web/routes.py": "cc", "cli/main.py": "dd"}
    assert boundary.moved_paths(was, absorbed) != frozenset({"web/routes.py"})
    assert boundary.moved_paths(was, absorbed) == frozenset({"web/routes.py", "cli/main.py"})
    assert boundary.moved_paths(was, was) == frozenset()
    assert boundary.moved_paths(was, {**was, "web/chat.js": "ee"}) == frozenset({"web/chat.js"})

    # …and the post-milestone reader, on literals, so IT is proved to bite too:
    # a missing field, an empty field and a duplicate path each raise.
    ok = {"post_milestone": {"edits": [
        {"path": "web/a.js", "at": "t", "by": "b", "why": "w"},
        {"path": "cli/b.py", "at": "t", "by": "b", "why": "w"},
    ]}}
    assert boundary.post_milestone_paths(ok) == frozenset({"web/a.js", "cli/b.py"})
    assert boundary.post_milestone_paths({}) == frozenset()
    for bad in (
        {"post_milestone": {"edits": [{"path": "web/a.js", "at": "t", "by": "b"}]}},
        {"post_milestone": {"edits": [{"path": "web/a.js", "at": "", "by": "b", "why": "w"}]}},
        {"post_milestone": {"edits": [
            {"path": "web/a.js", "at": "t", "by": "b", "why": "w"},
            {"path": "web/a.js", "at": "t", "by": "b", "why": "w2"},
        ]}},
    ):
        with pytest.raises(AssertionError):
            boundary.post_milestone_paths(bad)


def test_the_drift_fixture_tree_is_inert() -> None:
    """Two files, nothing imported, nothing called at module level (CLAUDE.md).

    Asserted by **AST**, never by a text search for `import`: the docstrings in
    that tree say the word `import` while explaining why the files have none,
    and a text search would read that prose as the defect. M3 shipped one of
    those.
    """
    tree = boundary.fixture("consumer_manifest_drift")
    members = sorted(path for path in tree.rglob("*") if path.is_file())
    assert [path.name for path in members] == [
        "at_its_recorded_digest.py",
        "one_byte_from_its_digest.py",
    ], members
    for path in members:
        tree_ast = parsed(path)
        assert [
            node for node in ast.walk(tree_ast) if isinstance(node, (ast.Import, ast.ImportFrom))
        ] == [], path
        assert [node for node in tree_ast.body if isinstance(node, ast.Expr)
                and not isinstance(node.value, ast.Constant)] == [], path
        assert [node for node in ast.iter_child_nodes(tree_ast)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))] == [], path
        # `import` appears in the prose of both files, which is exactly why the
        # assertion above is an AST walk and this one is here to say so.
        assert "import" in path.read_text(encoding="utf-8")

    # It is never on an import path the suite executes.
    assert not (tree / "__init__.py").exists()
    assert not (boundary.FIXTURE_DIR / "__init__.py").exists()


def test_the_manifest_reader_raises_rather_than_returning_empty(tmp_path: Path) -> None:
    """B1 — a manifest reader that cannot raise on a missing path never opened one."""
    with pytest.raises(FileNotFoundError):
        boundary._read_manifest(tmp_path / "no_such_manifest.json")
