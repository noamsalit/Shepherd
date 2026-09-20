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
    assert repo.workspace_id == binding.workspace_id
    # `origin` here is a local path, returned verbatim by `get-url`.
    assert repo.vcs_remote == str(git_world.root / "origin-src")


def test_bind_subdirectory(store: Store, git_world: GitWorld) -> None:
    first = bind_cwd_to_repo(store, str(git_world.main))
    from_subdir = bind_cwd_to_repo(store, str(git_world.subdir))

    assert from_subdir.repo_id == first.repo_id
    assert from_subdir.anomaly is None
    assert len(store.list_workspaces()) == 1


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
