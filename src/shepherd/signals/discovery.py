"""`discover_repos(root)` — where a workspace starts looking (§7 `workspace.root_path`).

A `.git` **file** is a repo marker just as much as a `.git` directory: linked
worktrees and submodules both have one, so a walk that tests `isdir('.git')`
misses exactly the layouts D48 exists for (E14).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from shepherd.signals.binding import probe_repo, resolve_remote

GIT_MARKER = ".git"


@dataclass(frozen=True)
class DiscoveredRepo:
    root_path: Path
    git_common_dir: str
    name: str
    vcs_remote: str | None
    is_worktree: bool


def discover_repos(root: Path) -> list[DiscoveredRepo]:
    """Every repo, worktree and submodule checkout under `root`.

    The walk stops descending at each repo it finds: repos nested *inside* a
    working tree are that repo's business, while a linked worktree is a sibling
    and is still reached. A directory git refuses to read (dubious ownership,
    E15) is skipped rather than guessed at.
    """
    if not root.is_dir():
        return []

    found: list[DiscoveredRepo] = []
    for current, dirnames, filenames in os.walk(root):
        has_marker = GIT_MARKER in dirnames or GIT_MARKER in filenames
        if GIT_MARKER in dirnames:
            dirnames.remove(GIT_MARKER)
        if not has_marker:
            continue
        dirnames[:] = []

        probe = probe_repo(current)
        if probe.failure is not None or probe.git_common_dir is None or probe.is_bare:
            continue
        path = Path(current)
        remote, _ = resolve_remote(current)
        found.append(
            DiscoveredRepo(
                root_path=path,
                git_common_dir=probe.git_common_dir,
                name=path.name,
                vcs_remote=remote,
                is_worktree=(
                    probe.git_dir is not None
                    and probe.git_dir != probe.git_common_dir
                    and "/worktrees/" in probe.git_dir
                ),
            )
        )
    return sorted(found, key=lambda repo: repo.root_path)
