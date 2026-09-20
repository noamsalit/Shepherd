"""T7: `discover_repos` — where a workspace starts looking (§7 `workspace.root_path`)."""

from __future__ import annotations

from pathlib import Path

from signals.conftest import GitWorld

from shepherd.signals.discovery import discover_repos


def test_discovery_finds_worktree_with_dotgit_file(git_world: GitWorld) -> None:
    """E14 — a walk that tests `isdir('.git')` misses worktrees and submodules."""
    assert (git_world.worktree / ".git").is_file()

    found = {repo.root_path: repo for repo in discover_repos(git_world.root)}

    assert git_world.worktree in found
    worktree = found[git_world.worktree]
    assert worktree.is_worktree is True
    assert worktree.git_common_dir == str(git_world.main / ".git")
    assert worktree.name == "PROJ-1"

    assert git_world.main in found
    assert found[git_world.main].is_worktree is False
    assert found[git_world.main].git_common_dir == str(git_world.main / ".git")
    assert found[git_world.main].vcs_remote == str(git_world.root / "origin-src")


def test_discovery_skips_non_repo_directories(git_world: GitWorld) -> None:
    found = {repo.root_path for repo in discover_repos(git_world.root)}

    assert git_world.plain not in found
    assert git_world.plain.parent not in found
    assert git_world.noremote in found


def test_discovery_skips_a_repo_it_cannot_read(
    git_world: GitWorld, foreign_owned_repo: Path
) -> None:
    """A repo owned by someone else is skipped, not guessed at.

    Split out of `test_discovery_skips_non_repo_directories` — not dropped from
    it — because the only way to build the case is `chown` to another uid, which
    needs root. The assertion is unchanged; what changed is that the three
    non-repo cases above no longer need the privilege this one does.
    """
    found = {repo.root_path for repo in discover_repos(git_world.root)}

    assert foreign_owned_repo not in found
    assert git_world.noremote in found


def test_discovery_of_a_directory_with_no_repos_is_empty(tmp_path: Path) -> None:
    empty = tmp_path / "nothing" / "here"
    empty.mkdir(parents=True)

    assert discover_repos(tmp_path / "nothing") == []
    assert discover_repos(tmp_path / "missing") == []
