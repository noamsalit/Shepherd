"""T11-1: §13's allowlist is the **registered repos**, not the workspace root.

`admission.admit()` is the seam. The sequence's own suite
(`test_spawn.py::test_spawn_refuses_an_unregistered_directory` and its two
siblings) drives the same rule through `spawn_owned_session`, and those tests
stay exactly as they are — they are still right. What they could not see is the
population the rule is evaluated over.

**The defect this file closed.** `_canonical_cwd` read `workspace.root_path`,
and the schema's own note on that column said it was only where a scanner
started looking — repos may live anywhere (D22, `orchestrator-platform.md`
l.647). D22 ties the allowlist to repos in as many words: *"`add_repo` is
`local_destructive` because §13 validates every spawn against the registered
allowlist — adding a repo **widens that allowlist**."* So a repo registered
outside its workspace's root — the normal case for any repo not nested under it
— was refused a spawn, and a workspace whose `root_path` was `NULL` refused
everything. Refusing is the safe direction, which is why this was availability
and not authority, and why it was recorded rather than hot-fixed.

**And the column is now gone (§3 D57).** Migration 004 drops
`workspace.root_path` entirely, so the population below is the project's
registered repo paths *alone*: there is no second half left to keep. Four of
this file's frozen tests named that half and are retired with successors in
this module; the other eleven kept their names and had their bodies rewritten.

**Longest prefix, innermost wins (D22's own words), and it is observable.**
`Admitted` carries the root that admitted the cwd. A yes/no admission cannot
distinguish "some root matched" from "the innermost root matched", so an
`Admitted` that did not carry it would leave the interesting half of the rule
asserted by reading the source — which is not an assertion.

**Note on D48, because it looks like it decides this.** D48 revises how a
session *binds* to a repo (`git rev-parse --git-common-dir`, not longest-prefix
match). It does not revise what §13's allowlist is made of. Binding and
admission are two questions.

Nothing here starts a process: the runner is a stub that answers
`list_owned_panes` and nothing else, which is the only member `admit` touches.
"""

from __future__ import annotations

import sqlite3
import typing
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.runner import (
    MAX_CHILDREN_PER_SESSION,
    MAX_SESSION_DEPTH,
    MAX_TOTAL_OWNED_SESSIONS,
    RunnerHandle,
)
from shepherd.core.states import Origin
from shepherd.orchestration import admission
from shepherd.orchestration.admission import (
    CAP_CHILDREN,
    CAP_DEPTH,
    CAP_RETRY,
    CAP_TOTAL,
    MASTER_ORIGIN,
    MAX_MASTER_ATTEMPTS,
    Admitted,
    Retry,
    SpawnRefused,
    admit,
)
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store, open_store
from shepherd.store.models import UNASSIGNED_PROJECT_ID


class NoPanes:
    """A runner with an empty socket. `list_owned_panes` is all `admit` calls."""

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        return ()


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def world(tmp_path: Path) -> Path:
    """A real directory tree, so every `resolve()` in the rule is a real one."""
    for relative in ("work/api/src", "elsewhere/frontend/src", "elsewhere/frontend/vendor/inner"):
        (tmp_path / relative).mkdir(parents=True)
    return tmp_path


def register(store: Store, workspace_id: str, root: Path, name: str) -> None:
    """Register a repo to a project — D22's widening verb, which is what §13's
    allowlist is made of after D57."""
    store.add_repo(
        workspace_id=workspace_id,
        root_path=str(root),
        name=name,
        git_common_dir=str(root / ".git"),
        vcs_remote=None,
    )


def ask(store: Store, workspace_id: str, cwd: Path | str) -> Admitted | SpawnRefused:
    return admit(
        store=store,
        runner=typing.cast(typing.Any, NoPanes()),  # noqa: ANN401 - the Runner seam
        workspace_id=workspace_id,
        cwd=str(cwd),
        parent_session_id=None,
    )


# ----- the case that was broken ----------------------------------------------


# ----- longest prefix, innermost wins (D22) -----------------------------------


def test_the_innermost_registered_root_wins(store: Store, world: Path) -> None:
    """Three nested roots, one cwd, and the answer is the deepest of them.

    git resolves a nested repo to the innermost toplevel
    (`data-schemas.md`, `git rev-parse` §Variants: *"Nested repo: innermost
    toplevel wins"*), and D22 says the allowlist match does the same. A rule
    that returned the first or the shortest match would still admit this cwd,
    which is exactly why the matched root is part of the answer.
    """
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "elsewhere" / "frontend", "frontend")
    register(store, workspace.id, world / "elsewhere" / "frontend" / "vendor" / "inner", "inner")

    deep = ask(store, workspace.id, world / "elsewhere" / "frontend" / "vendor" / "inner")
    assert isinstance(deep, Admitted), deep
    assert deep.root == (world / "elsewhere" / "frontend" / "vendor" / "inner").resolve()

    # One level out of the inner repo, the next root out wins — the match moves
    # with the cwd rather than being fixed by the order the repos were added.
    outer = ask(store, workspace.id, world / "elsewhere" / "frontend" / "src")
    assert isinstance(outer, Admitted), outer
    assert outer.root == (world / "elsewhere" / "frontend").resolve()

    # …and outside every repo nothing admits it: the project root that used to
    # be the outermost permitted root is gone with the column (D57).
    plain = ask(store, workspace.id, world / "elsewhere")
    assert isinstance(plain, SpawnRefused), plain


# ----- what must still refuse -------------------------------------------------


def test_a_repo_registered_to_another_workspace_admits_nothing_here(
    store: Store, world: Path
) -> None:
    """The allowlist is per workspace. A repo next door is not a way in.

    `list_repos` takes a `workspace_id` for this reason; a tree-wide
    `registered_roots()` would have made every project a permitted root of
    every other.
    """
    mine = store.create_project(name="mine", description=None)
    theirs = store.create_project(name="theirs", description=None)
    register(store, theirs.id, world / "elsewhere" / "frontend", "frontend")

    result = ask(store, mine.id, world / "elsewhere" / "frontend" / "src")
    assert isinstance(result, SpawnRefused), result
    assert result.cap is None, "an unregistered directory is not a cap refusal"


#: Every shape an unregistered directory arrives in, now that a **repo** is one
#: of the roots. The count is asserted below, because a parametrize list that
#: shrinks to one case still passes and shrinks to zero in silence.
ESCAPES: tuple[str, ...] = (
    "sibling_of_the_repo",
    "repo_name_is_a_string_prefix",
    "traversal_out_of_the_repo",
    "symlink_out_of_the_repo",
    "the_repos_parent",
)


def test_the_escape_cases_are_the_five_shapes_they_claim_to_be() -> None:
    assert len(ESCAPES) == len(set(ESCAPES)) == 5


@pytest.mark.parametrize("case", ESCAPES)
def test_a_directory_outside_every_registered_repo_is_refused(
    store: Store, world: Path, case: str
) -> None:
    """The repo roots are a longest-prefix allowlist, not a substring one.

    `frontend-scratch` is the case a `str.startswith` over paths admits and a
    `Path.parents` comparison refuses, and it is the one an attacker — or an
    ordinary `mkdir` — reaches first.
    """
    workspace = store.create_project(name="rootless", description=None)
    register(store, workspace.id, world / "elsewhere" / "frontend", "frontend")
    (world / "elsewhere" / "frontend-scratch").mkdir()
    (world / "elsewhere" / "frontend" / "escape").symlink_to(world / "work")

    cwds = {
        "sibling_of_the_repo": world / "work" / "api",
        "repo_name_is_a_string_prefix": world / "elsewhere" / "frontend-scratch",
        "traversal_out_of_the_repo": Path(f"{world}/elsewhere/frontend/../../work/api"),
        "symlink_out_of_the_repo": world / "elsewhere" / "frontend" / "escape",
        "the_repos_parent": world / "elsewhere",
    }

    result = ask(store, workspace.id, cwds[case])
    assert isinstance(result, SpawnRefused), f"{case}: {result}"
    assert result.cap is None


def test_the_refusal_names_every_registered_root_it_was_measured_against(
    store: Store, world: Path
) -> None:
    """§11's rule for caps applied to §13: an error a caller can reason about.

    "outside every registered root" with no list is a message that sends a
    human to read the database. The roots are what the operator has to change.
    """
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "elsewhere" / "frontend", "frontend")

    register(store, workspace.id, world / "work" / "api", "api")

    result = ask(store, workspace.id, world / "elsewhere" / "frontend-scratch")
    assert isinstance(result, SpawnRefused), result
    assert str((world / "work" / "api").resolve()) in result.reason
    assert str((world / "elsewhere" / "frontend").resolve()) in result.reason


# ----- T23's handoff: a reachable input that raised instead of refusing -------

#: The strings `Path(...).resolve()` will not canonicalize. `\x00` is the one
#: T23 measured escaping `admit` as `ValueError: embedded null byte`, reachable
#: from `POST /api/sessions`; the others are the same shape at the same call.
UNCANONICAL = ("/tmp/a\x00b", "\x00", "/tmp/\x00/api")


def test_a_cwd_that_will_not_canonicalize_is_refused_rather_than_raised(
    store: Store, world: Path
) -> None:
    """P-M3-9: every degradation returns a value; **none raises** (T23's handoff).

    `Path("/tmp/a\\x00b").resolve()` raises `ValueError: embedded null byte`, and
    that string reaches `admit` from outside — `POST /api/sessions` carries the
    caller's `cwd` straight through `spawn_session`. A raise there is flattened
    by `invoke()` into `Failure.FAILED` + `"ValueError"`, which is exactly the
    "a page cannot tell a refusal from a crash" outcome principle 5 forbids and
    the one thing `SpawnRefused` exists to prevent.

    Arrival before absence: the same workspace admits a real directory first, so
    a refusal here cannot pass by the rule never having been reached.
    """
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "work" / "api", "api")

    # Arrival: this workspace really does admit something.
    assert isinstance(ask(store, workspace.id, world / "work" / "api" / "src"), Admitted)

    for cwd in UNCANONICAL:
        result = ask(store, workspace.id, cwd)
        assert isinstance(result, SpawnRefused), (cwd, result)
        assert result.cap is None
        # The refusal names the caller's own argument back to them, escaped —
        # a message carrying a raw NUL is a message a log cannot print.
        assert repr(cwd)[1:-1] in result.reason, (cwd, result.reason)
        # …and it is **this** refusal, not the allowlist's. A `_canonical` that
        # repaired the string into some directory would still hand back a
        # `SpawnRefused` here (the repaired path is outside every root), and a
        # test reading only the type would call that a pass. Refuse, never
        # repair — the same rule `check_tmux_argv` keeps one layer down.
        assert "does not canonicalize" in result.reason, (cwd, result.reason)


def test_a_registered_root_that_will_not_canonicalize_refuses_and_names_itself(
    store: Store, world: Path
) -> None:
    """The other side of the same `resolve()`, and it is reachable too.

    `add_repo` stores a `root_path` containing a NUL without complaint
    (sqlite is happy to hold one), and `add_repo` is a registered tool. The
    allowlist is then a list this rule **cannot evaluate**, so it refuses and
    names the row to fix. Dropping the bad root instead would quietly narrow
    §13's allowlist and then report "no registered repo", which is false of the
    database — an allowlist that shrinks silently is the failure this file was
    written to close in the other direction.
    """
    workspace = store.create_project(name="rootless", description=None)
    register(store, workspace.id, world / "work" / "api", "api")
    store.add_repo(
        workspace_id=workspace.id,
        root_path="/tmp/a\x00b",
        name="corrupt",
        git_common_dir="/tmp/a/.git",
        vcs_remote=None,
    )

    result = ask(store, workspace.id, world / "work" / "api" / "src")
    assert isinstance(result, SpawnRefused), result
    assert result.cap is None
    assert "/tmp/a\\x00b" in result.reason, result.reason


# ----- T10: D31's retry cap, beside §11's three ------------------------------
#
# *"Capped at 2 master-initiated attempts per lineage"* (D31). The cap is a
# property of the **lineage**, so it is read by walking `retry_of` rather than
# off the `attempt` column a caller writes — and the lineage in every test below
# is built by the shipped writer (`Store.link_retry`), never planted with SQL.
# A cap proved only against hand-planted rows is a cap that has never met the
# code that would trigger it.


def owned(
    store: Store, session_id: str, *, depth: int = 0, parent: str | None = None
) -> str:
    """One owned, master-spawned row through the shipped verb."""
    # By name, never by position: BINARY collation puts the seeded
    # `"Unassigned"` first, so `[0]` is the reserved project (N2/E22). The row
    # only needs *a* project to point at — the cap is about the lineage.
    named = [w for w in store.list_workspaces() if w.name == "lineage"]
    workspace = named[0] if named else store.create_project(
        name="lineage", description=None
    )
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=f"eng-{session_id}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T12:00:00Z",
        origin=Origin.ORCHESTRATOR,
        parent_session_id=parent,
        depth=depth,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=RunnerHandle(
            runner="tmux", socket="shepherd-runner", session_name=f"shepherd_{session_id}"
        ),
        model=None,
        effort=None,
    )
    return session_id


def a_lineage(store: Store, ids: tuple[str, ...]) -> tuple[str, ...]:
    """`ids[0]` is the first attempt; each later id is a retry of the one before.

    Every link goes through `Store.link_retry`, which is the only writer of
    `retry_of` in the tree. That is the point of this helper: the chain the cap
    refuses is a chain production code can actually create.
    """
    for session_id in ids:
        owned(store, session_id)
    for earlier, later in zip(ids, ids[1:], strict=False):
        store.link_retry(session_id=later, retry_of=earlier)
    return ids


def anomaly_count(store: Store, kind: AnomalyKind) -> int:
    return store.list_anomaly_counts().get(str(kind.value), 0)


def workspace_admitting(store: Store, world: Path) -> str:
    """A workspace whose allowlist admits `world/work/api` — so that a refusal
    below is the retry cap's and not §13's."""
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "work" / "api", "api")
    return workspace.id


def ask_retry(
    store: Store,
    workspace_id: str,
    cwd: Path | str,
    retry: Retry | None,
    panes: tuple[PaneRef, ...] = (),
) -> Admitted | SpawnRefused:
    class Panes:
        def list_owned_panes(self) -> tuple[PaneRef, ...]:
            return panes

    return admit(
        store=store,
        runner=typing.cast(typing.Any, Panes()),  # noqa: ANN401 - the Runner seam
        workspace_id=workspace_id,
        cwd=str(cwd),
        parent_session_id=None,
        retry=retry,
    )


FIRST = "01FIRST000000000000000000"[:24]
RETRY = "01RETRY000000000000000000"[:24]


def test_a_third_master_attempt_is_refused(store: Store, world: Path) -> None:
    """P-M4-13 / D31, over a lineage the shipped writer built.

    Two attempts stand in the lineage — the first and its retry — so a third
    **master-initiated** one is refused. The refusal is asserted by name: M3's
    `_canonical` survivor is the lesson that a test reading only
    `isinstance(result, SpawnRefused)` cannot tell refuse from repair, and here
    it could not tell the cap from §13's allowlist either.

    The counter is the operator's half and the refusal is the agent's, so both
    are asserted, and the counter is read **before** the call as well as after:
    a bump asserted only afterwards passes against a counter that was already
    at one.
    """
    workspace_id = workspace_admitting(store, world)
    chain = a_lineage(store, (FIRST, RETRY))
    assert store.retry_chain_depth(chain[-1]) == MAX_MASTER_ATTEMPTS

    before = anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED)
    result = ask_retry(
        store,
        workspace_id,
        world / "work" / "api",
        Retry(of=chain[-1], initiated_by=MASTER_ORIGIN),
    )

    assert isinstance(result, SpawnRefused), result
    assert result.cap == CAP_RETRY, result
    assert str(MAX_MASTER_ATTEMPTS) in result.reason, result.reason
    assert chain[-1] in result.reason, result.reason
    assert anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED) == before + 1


def test_a_second_master_attempt_is_admitted(store: Store, world: Path) -> None:
    """The negative control: one attempt in the lineage, so a retry may run.

    An over-tight cap is a guard that is off — it refuses the retry D31 exists
    to allow, and every later test of the refusal still passes. Nothing is
    counted here either: an anomaly raised on a permitted spawn is noise in the
    one place an operator is meant to be able to trust.
    """
    workspace_id = workspace_admitting(store, world)
    owned(store, FIRST)
    assert store.retry_chain_depth(FIRST) == 1

    before = anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED)
    result = ask_retry(
        store, workspace_id, world / "work" / "api", Retry(of=FIRST, initiated_by=MASTER_ORIGIN)
    )

    assert isinstance(result, Admitted), result
    assert result.root == (world / "work" / "api").resolve()
    assert anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED) == before


def test_a_human_retry_is_not_capped(store: Store, world: Path) -> None:
    """D31 caps *master-initiated* attempts. A human pressing `[re-run]` a third
    time is the human's call — the same asymmetry as DP2.

    The lineage here is the one the previous test refuses, so this test is red
    the moment the audience branch is dropped: same chain, same depth, opposite
    answer, and the only difference is who asked.
    """
    workspace_id = workspace_admitting(store, world)
    chain = a_lineage(store, (FIRST, RETRY))
    assert store.retry_chain_depth(chain[-1]) >= MAX_MASTER_ATTEMPTS

    before = anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED)
    result = ask_retry(
        store,
        workspace_id,
        world / "work" / "api",
        Retry(of=chain[-1], initiated_by=Origin.USER_UI),
    )

    assert isinstance(result, Admitted), result
    assert anomaly_count(store, AnomalyKind.WAKE_RETRY_CAP_REACHED) == before


def test_the_cap_is_not_read_off_the_attempt_column(
    store: Store, world: Path, tmp_path: Path
) -> None:
    """`attempt` is a column a caller writes; the lineage is the fact (D31).

    The row's `attempt` is set to a number far past the cap while the lineage
    holds one attempt. A cap reading the column refuses here; a cap walking the
    chain admits. Nothing in `src/` writes `attempt` either, which is exactly
    why a cap resting on it would be a cap that never fires.
    """
    workspace_id = workspace_admitting(store, world)
    owned(store, FIRST)
    raw = sqlite3.connect(tmp_path / "data" / "shepherd.db")
    try:
        raw.execute("UPDATE session SET attempt = 9 WHERE id = ?", (FIRST,))
        raw.commit()
    finally:
        raw.close()

    result = ask_retry(
        store, workspace_id, world / "work" / "api", Retry(of=FIRST, initiated_by=MASTER_ORIGIN)
    )

    assert isinstance(result, Admitted), result


def test_the_cap_and_the_wake_set_agree_on_which_origin_is_the_master(
    store: Store, world: Path
) -> None:
    """One master, one origin. The wake set selects rows on it (`WAKE_ORIGIN`)
    and the cap decides who is capped by it; two spellings of *the master* would
    let the wake set hand back a session the cap then treats as a human's."""
    from shepherd.store.reads import WAKE_ORIGIN

    assert str(MASTER_ORIGIN.value) == WAKE_ORIGIN


#: Each of `admission`'s caps, with the arrangement that reaches it. The keys
#: are compared against the module's own `CAP_*` constants below rather than
#: counted, so a cap added without a scenario — or displaced by the new one —
#: fails here instead of going untested.
def cap_scenarios(store: Store, world: Path) -> dict[str, Admitted | SpawnRefused]:
    workspace_id = workspace_admitting(store, world)
    here = world / "work" / "api"

    owned(store, "01DEEP000000000000000000"[:24], depth=MAX_SESSION_DEPTH - 1)
    deep = admit(
        store=store,
        runner=typing.cast(typing.Any, NoPanes()),  # noqa: ANN401 - the Runner seam
        workspace_id=workspace_id,
        cwd=str(here),
        parent_session_id="01DEEP000000000000000000"[:24],
    )

    parent = owned(store, "01PARENT00000000000000000"[:24])
    for index in range(MAX_CHILDREN_PER_SESSION):
        owned(store, f"01CHILD{index}00000000000000"[:24], depth=1, parent=parent)
    children = admit(
        store=store,
        runner=typing.cast(typing.Any, NoPanes()),  # noqa: ANN401 - the Runner seam
        workspace_id=workspace_id,
        cwd=str(here),
        parent_session_id=parent,
    )

    full = tuple(
        PaneRef(
            session_name=f"shepherd_{index}", session_id=str(index), pane_pid=None, dead=False
        )
        for index in range(MAX_TOTAL_OWNED_SESSIONS)
    )
    total = ask_retry(store, workspace_id, here, None, panes=full)

    chain = a_lineage(store, (FIRST, RETRY))
    retry = ask_retry(
        store, workspace_id, here, Retry(of=chain[-1], initiated_by=MASTER_ORIGIN)
    )

    return {CAP_DEPTH: deep, CAP_CHILDREN: children, CAP_TOTAL: total, CAP_RETRY: retry}


def test_every_existing_admission_refusal_still_fires(store: Store, world: Path) -> None:
    """The set of caps, enumerated from the module at test time and driven.

    A new refusal that displaced an old one — the same `SpawnRefused` reached by
    a rule that now runs first — is invisible to a suite that only asserts the
    new one. So every cap the module declares must still be reachable, and the
    set the scenarios reach must be exactly the set the module declares: a cap
    added without a scenario fails here rather than shipping untested.
    """
    declared = {
        value
        for name, value in vars(admission).items()
        if name.startswith("CAP_") and isinstance(value, str)
    }
    reached = cap_scenarios(store, world)

    assert set(reached) == declared, (set(reached), declared)
    for cap, result in reached.items():
        assert isinstance(result, SpawnRefused), (cap, result)
        assert result.cap == cap, (cap, result)
        assert cap in result.reason or cap == CAP_RETRY, (cap, result.reason)


# ----- T1.9: the allowlist is the repo paths alone (D57) ---------------------


def test_a_registered_repo_admits_a_spawn(store: Store, world: Path) -> None:
    """The successor to `test_a_repo_registered_outside_its_workspace_root_is
    _admitted`, whose premise — a repo *outside* the workspace root — stopped
    meaning anything when the root column was dropped. Every repo is now
    "outside" it, because there is no it.
    """
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "elsewhere" / "frontend", "frontend")

    result = ask(store, workspace.id, world / "elsewhere" / "frontend" / "src")
    assert isinstance(result, Admitted), result
    assert result.root == (world / "elsewhere" / "frontend").resolve()

    root_itself = ask(store, workspace.id, world / "elsewhere" / "frontend")
    assert isinstance(root_itself, Admitted), root_itself


def test_add_repo_widens_the_allowlist(store: Store, world: Path) -> None:
    """D22 in as many words: *"adding a repo widens that allowlist"* — which is
    why the tool is `local_destructive`. Measured across the one call.

    The first half is the negative control: before the `add_repo`, the very
    same cwd is refused, so the admission below is the registration and not a
    rule that admits everything.
    """
    workspace = store.create_project(name="shepherd", description=None)
    before = ask(store, workspace.id, world / "work" / "api" / "src")
    assert isinstance(before, SpawnRefused), before

    register(store, workspace.id, world / "work" / "api", "api")

    after = ask(store, workspace.id, world / "work" / "api" / "src")
    assert isinstance(after, Admitted), after
    assert after.root == (world / "work" / "api").resolve()


def test_a_project_with_no_repo_refuses_everything(store: Store, world: Path) -> None:
    """E11 — the empty allowlist is empty, not universal.

    The successor to `test_a_workspace_with_neither_a_root_nor_a_repo_refuses
    _everything`: there is no "root" half of that sentence any more, and the
    property it protected is the whole of this one.
    """
    workspace = store.create_project(name="empty", description=None)

    result = ask(store, workspace.id, world / "work" / "api")
    assert isinstance(result, SpawnRefused), result
    assert "no registered repo" in result.reason
    assert str(world / "work" / "api") in result.reason
    # …and the reserved project is no exception: nothing is registered to it.
    reserved = ask(store, UNASSIGNED_PROJECT_ID, world / "work" / "api")
    assert isinstance(reserved, SpawnRefused), reserved


def test_every_registered_path_is_either_admitted_or_named_in_the_refusal(
    store: Store, world: Path
) -> None:
    """P5 — **the allowlist never silently narrows.**

    A stored root that will not canonicalize makes the allowlist unevaluable,
    and the rule says so by name rather than dropping the row and reporting
    "no registered repo" — which would be false of the database. Replacing the
    refusal at `admission.py:141-143` with a `continue` reddens this.

    The control is the two branches, run in one test: with **only** the good
    repo the cwd under it is admitted, and with the bad row added the same cwd
    is refused *and the bad path is in the message*. One branch alone would
    leave "names it" or "refuses" unproved.
    """
    workspace = store.create_project(name="shepherd", description=None)
    register(store, workspace.id, world / "work" / "api", "api")
    good = ask(store, workspace.id, world / "work" / "api" / "src")
    assert isinstance(good, Admitted), good

    register(store, workspace.id, Path(f"{world}/work/nul\x00path"), "bad")

    refused = ask(store, workspace.id, world / "work" / "api" / "src")
    assert isinstance(refused, SpawnRefused), refused
    assert "nul" in refused.reason, refused.reason
    assert refused.cap is None
