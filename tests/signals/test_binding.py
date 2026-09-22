"""T7: cwd → repo binding through `--git-common-dir` (D48).

Integration seam: real `git` against throwaway repos under `tmp_path`. The one
case prefix matching cannot do — a linked worktree, which is a *sibling* of the
repo — is `test_bind_worktree_to_main_repo`.
"""

from __future__ import annotations

import typing
from pathlib import Path

import pytest
from signals.conftest import GitWorld, git

from shepherd.core.anomalies import AnomalyKind
from shepherd.signals.binding import bind_cwd_to_repo
from shepherd.store.db import Store, open_store
from shepherd.store.models import UNASSIGNED_PROJECT_ID


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def test_bind_plain_repo(store: Store, git_world: GitWorld) -> None:
    binding = bind_cwd_to_repo(store, str(git_world.main))

    assert binding.anomaly is None
    assert binding.repo_id is not None
    assert binding.git_common_dir == str(git_world.main / ".git")
    assert binding.workspace_id != ""

    repo = store.find_repo_by_common_dir(str(git_world.main / ".git"))
    assert repo is not None
    assert repo.id == binding.repo_id
    assert repo.root_path == str(git_world.main)
    assert repo.name == "main"
    # A discovered repo is registered to no project (D59/F10), so the binding's
    # project is the reserved one and the repo row carries no project at all.
    assert binding.workspace_id == UNASSIGNED_PROJECT_ID
    assert store.projects_for_repo(repo.id) == []
    # `origin` here is a local path, returned verbatim by `get-url`.
    assert repo.vcs_remote == str(git_world.root / "origin-src")


def test_bind_subdirectory(store: Store, git_world: GitWorld) -> None:
    first = bind_cwd_to_repo(store, str(git_world.main))
    from_subdir = bind_cwd_to_repo(store, str(git_world.subdir))

    assert from_subdir.repo_id == first.repo_id
    assert from_subdir.anomaly is None
    # N1: a fresh database already holds the seeded `unassigned` project, and
    # binding creates none — so the count is the seed, and only the seed.
    assert [w.id for w in store.list_workspaces()] == [UNASSIGNED_PROJECT_ID]


def test_bind_worktree_to_main_repo(git_world: GitWorld, store: Store) -> None:
    """E11 — the case longest-prefix matching returns null for."""
    assert not str(git_world.worktree).startswith(str(git_world.main) + "/")
    assert (git_world.worktree / ".git").is_file()

    main_binding = bind_cwd_to_repo(store, str(git_world.main))
    worktree_binding = bind_cwd_to_repo(store, str(git_world.worktree))

    assert worktree_binding.repo_id == main_binding.repo_id
    assert worktree_binding.git_common_dir == str(git_world.main / ".git")
    assert worktree_binding.anomaly is None


def test_bind_submodule_resolves_to_submodule(store: Store, git_world: GitWorld) -> None:
    main_binding = bind_cwd_to_repo(store, str(git_world.main))
    sub_binding = bind_cwd_to_repo(store, str(git_world.submodule))

    assert sub_binding.repo_id is not None
    assert sub_binding.repo_id != main_binding.repo_id
    assert sub_binding.git_common_dir == str(git_world.main / ".git" / "modules" / "mods" / "sub")

    repo = store.find_repo_by_common_dir(str(sub_binding.git_common_dir))
    assert repo is not None
    assert repo.root_path == str(git_world.submodule)


def test_bind_symlinked_path_matches_physical(store: Store, git_world: GitWorld) -> None:
    physical = bind_cwd_to_repo(store, str(git_world.main))
    through_link = bind_cwd_to_repo(store, str(git_world.symlink / "src"))

    assert through_link.repo_id == physical.repo_id
    assert through_link.git_common_dir == str(git_world.main / ".git")


def test_bind_nested_repo_resolves_innermost(store: Store, git_world: GitWorld) -> None:
    outer = bind_cwd_to_repo(store, str(git_world.main))
    inner = bind_cwd_to_repo(store, str(git_world.nested))

    assert inner.repo_id is not None
    assert inner.repo_id != outer.repo_id
    assert inner.git_common_dir == str(git_world.nested / ".git")


def test_bind_non_repo_yields_null_repo_id(store: Store, git_world: GitWorld) -> None:
    binding = bind_cwd_to_repo(store, str(git_world.plain))

    assert binding.repo_id is None
    assert binding.git_common_dir is None
    assert binding.anomaly is not None
    assert binding.anomaly.kind is AnomalyKind.GIT_NOT_A_REPO
    assert store.get_app_state("anomaly.git_not_a_repo") == 1
    # Principle 5: the session is still attached to a project.
    assert binding.workspace_id != ""


def test_bind_bare_repo_is_counted(store: Store, git_world: GitWorld) -> None:
    binding = bind_cwd_to_repo(store, str(git_world.bare))

    assert binding.repo_id is None
    assert binding.anomaly is not None
    assert binding.anomaly.kind is AnomalyKind.GIT_BARE_REPO
    assert store.get_app_state("anomaly.git_bare_repo") == 1


def test_bind_dubious_ownership_is_counted(store: Store, foreign_owned_repo: Path) -> None:
    """E15 — reported, never fixed: `safe.directory` is not ours to write.

    Takes `foreign_owned_repo` rather than `git_world` because building the case
    needs root; see that fixture for why the other 24 tests here no longer pay
    for this one's privilege.
    """
    binding = bind_cwd_to_repo(store, str(foreign_owned_repo))

    assert binding.repo_id is None
    assert binding.anomaly is not None
    assert binding.anomaly.kind is AnomalyKind.GIT_DUBIOUS_OWNERSHIP
    assert "dubious ownership" in binding.anomaly.detail
    assert store.get_app_state("anomaly.git_dubious_ownership") == 1


def test_bind_missing_cwd_never_raises(store: Store, git_world: GitWorld) -> None:
    binding = bind_cwd_to_repo(store, str(git_world.root / "does-not-exist"))

    assert binding.repo_id is None
    assert binding.anomaly is not None
    assert binding.workspace_id != ""


def test_bind_repo_with_no_commits_still_binds(store: Store, git_world: GitWorld) -> None:
    """§: a repo with no commits has a working toplevel while `rev-parse HEAD` fails."""
    empty = git_world.root / "empty"
    empty.mkdir()
    git(empty, "init", "-q", "-b", "main")

    binding = bind_cwd_to_repo(store, str(empty))

    assert binding.repo_id is not None
    assert binding.git_common_dir == str(empty / ".git")


# ----- T1.7: binding after the join table (D59, D60) ------------------------


def test_a_non_repo_cwd_binds_to_unassigned_and_counts_the_anomaly(
    store: Store, git_world: GitWorld
) -> None:
    """D59 — the branch that used to mint a project from `Path(cwd).name`.

    A directory that is not a repo is not a project. Minting one gave every
    stray `cd` a row on the Projects page and a name nobody chose, and the
    anomaly counter already said the interesting part.
    """
    plain = git_world.root / "not-a-repo"
    plain.mkdir()

    binding = bind_cwd_to_repo(store, str(plain))

    assert binding.workspace_id == UNASSIGNED_PROJECT_ID
    assert binding.repo_id is None
    assert binding.anomaly is not None and binding.anomaly.kind is AnomalyKind.GIT_NOT_A_REPO
    # The negative control: nothing was created. One project exists and it is
    # the seeded one.
    assert [w.id for w in store.list_workspaces()] == [UNASSIGNED_PROJECT_ID]


def test_the_new_session_lands_in_that_project(store: Store, git_world: GitWorld) -> None:
    """The steady state: a repo registered to exactly one project binds there.

    The repo row is discovered first (unattached), then registered through
    `add_repo` the way the UI will — and the *next* discovered session in the
    same directory resolves the project through `project_repo`.
    """
    first = bind_cwd_to_repo(store, str(git_world.main))
    assert first.workspace_id == UNASSIGNED_PROJECT_ID, "a discovered repo joins no project"
    assert first.repo_id is not None

    project = store.create_project(name="the-one", description=None)
    store.add_repo(
        workspace_id=project.id,
        root_path=str(git_world.main),
        name="main",
        git_common_dir=str(git_world.main / ".git"),
        vcs_remote=None,
    )

    again = bind_cwd_to_repo(store, str(git_world.subdir))
    assert again.repo_id == first.repo_id, "the same directory is the same repo row (D48)"
    assert again.workspace_id == project.id


def test_a_repo_in_two_projects_binds_a_discovered_session_to_unassigned(
    store: Store, git_world: GitWorld
) -> None:
    """E4/D60 — a discovered session cannot be asked which project it meant.

    The negative control is the first assertion: with **one** project the same
    repo binds to it, so the fallback below is ambiguity and not a verb that
    never resolves anything.
    """
    discovered = bind_cwd_to_repo(store, str(git_world.main))
    assert discovered.repo_id is not None
    work = store.create_project(name="work", description=None)
    personal = store.create_project(name="personal", description=None)
    for project in (work, personal):
        store.add_repo(
            workspace_id=project.id,
            root_path=str(git_world.main),
            name="main",
            git_common_dir=str(git_world.main / ".git"),
            vcs_remote=None,
        )
    assert sorted(store.projects_for_repo(discovered.repo_id)) == sorted(
        [work.id, personal.id]
    )

    ambiguous = bind_cwd_to_repo(store, str(git_world.main))
    assert ambiguous.repo_id == discovered.repo_id
    assert ambiguous.workspace_id == UNASSIGNED_PROJECT_ID


def test_an_orphaned_repo_binds_to_unassigned_and_the_repo_row_survives(
    store: Store, git_world: GitWorld
) -> None:
    """E5 — a repo in no project. The repo row is **kept** (D48's identity
    under `ux_repo_path`), so history does not lose its `repo_id`.
    """
    project = store.create_project(name="work", description=None)
    added = store.add_repo(
        workspace_id=project.id,
        root_path=str(git_world.main),
        name="main",
        git_common_dir=str(git_world.main / ".git"),
        vcs_remote=None,
    )
    assert store.remove_repo(workspace_id=project.id, repo_id=added.id) is True

    binding = bind_cwd_to_repo(store, str(git_world.main))

    assert binding.repo_id == added.id
    assert binding.workspace_id == UNASSIGNED_PROJECT_ID
    assert store.find_repo_by_common_dir(str(git_world.main / ".git")) is not None


def test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix(
    store: Store, git_world: GitWorld, tmp_path: Path
) -> None:
    """P4 — the contract in the docstring, over the shapes that could break it.

    `RepoBinding.workspace_id` is non-optional and the verb never raises, so
    every row below has to come back with a real project id. A branch that let
    an `OSError` through would fail here rather than in `controld`, which is
    where it would otherwise surface — one lane, at 2 s intervals, taking the
    daemon with it.
    """
    missing = tmp_path / "gone"
    empty_name = str(tmp_path) + "/"
    matrix = (
        str(git_world.main),
        str(git_world.subdir),
        str(git_world.worktree),
        str(git_world.bare),
        str(missing),
        empty_name,
        "",
        "/",
        str(tmp_path / "with space"),
        # The NUL. `subprocess.run(cwd=...)` answers it with **`ValueError`**,
        # which is neither `OSError` nor `SubprocessError`, so it walked
        # straight through `run_git`'s except clause and out of a verb that
        # documents *"Never raises"*. Four other adversarial cwds return
        # cleanly and counted, which is this row's control. The asymmetry is
        # the tell: `admission.py` guards exactly this input by name — *"a cwd
        # carrying a NUL byte … is refused, never guessed at"* — while
        # `hook_lane._with_foreign_repos` feeds this verb text derived from the
        # engine's JSONL and neither caller wraps it.
        "/tmp\x00evil",
    )
    for cwd in matrix:
        binding = bind_cwd_to_repo(store, cwd)
        assert binding.workspace_id, cwd
        assert isinstance(binding.workspace_id, str), cwd
