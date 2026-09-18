"""T7: `vcs_remote` normalisation (D50, P9, E12, E13, C19).

`normalise_remote_url` is pure, so the seven captured spellings are asserted as
literals against
`docs/specs/data-schemas.md` §"`git remote get-url` forms". The two null cases
run through the binder, because *which* remote is chosen is a binder decision.
"""

from __future__ import annotations

import typing
from pathlib import Path

import pytest
from signals.conftest import GitWorld, git

from shepherd.core.anomalies import AnomalyKind
from shepherd.signals.binding import bind_cwd_to_repo, normalise_remote_url
from shepherd.store.db import Store, open_store


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def test_vcs_remote_strips_userinfo() -> None:
    """P9/E13 — `get-url` returns credentials verbatim; §13's redaction never sees a key."""
    raw = "https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git"

    normalised = normalise_remote_url(raw)

    assert normalised == "gitlab.com/example-org/example-repo"
    assert normalised is not None
    assert "FAKE_TOKEN_NOT_REAL" not in normalised
    assert "@" not in normalised
    assert normalise_remote_url("ssh://git@github.com/example-org/example-repo.git") == (
        "github.com/example-org/example-repo"
    )


def test_vcs_remote_normalises_all_seven_forms() -> None:
    """All seven captured spellings of one remote, plus the local-path form."""
    assert normalise_remote_url("git@github.com:example-org/example-repo.git") == (
        "github.com/example-org/example-repo"
    )
    assert normalise_remote_url("ssh://git@github.com/example-org/example-repo.git") == (
        "github.com/example-org/example-repo"
    )
    assert normalise_remote_url("https://github.com/example-org/example-repo.git") == (
        "github.com/example-org/example-repo"
    )
    assert normalise_remote_url("https://gitlab.com/example-org/sub-group/example-repo") == (
        "gitlab.com/example-org/sub-group/example-repo"
    )
    assert normalise_remote_url(
        "https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git"
    ) == "gitlab.com/example-org/example-repo"
    # `insteadOf` is expanded by git itself, so what arrives is the scp-like form.
    assert normalise_remote_url("git@github.com:example-org/example-repo.git") == (
        "github.com/example-org/example-repo"
    )
    # A local path (a `clone --bare` origin) stays a path.
    assert normalise_remote_url("/tmp/shp-lpg-git.YD7ktR/origin-src") == (
        "/tmp/shp-lpg-git.YD7ktR/origin-src"
    )
    # Host case is not identity.
    assert normalise_remote_url("https://GitHub.com/Example-Org/example-repo.git") == (
        "github.com/Example-Org/example-repo"
    )
    assert normalise_remote_url("   ") is None


def test_vcs_remote_null_when_no_remote(store: Store, git_world: GitWorld) -> None:
    """E12 — `git remote get-url origin` exits 2; `/root/Shepherd` itself is such a repo."""
    binding = bind_cwd_to_repo(store, str(git_world.noremote))

    assert binding.repo_id is not None
    repo = store.find_repo_by_common_dir(str(git_world.noremote / ".git"))
    assert repo is not None
    assert repo.vcs_remote is None
    assert binding.anomaly is not None
    assert binding.anomaly.kind is AnomalyKind.GIT_NO_REMOTE
    assert store.get_app_state("anomaly.git_no_remote") == 1


def test_vcs_remote_null_when_ambiguous(store: Store, git_world: GitWorld) -> None:
    """C19 — several remotes, none named `origin`; git has no canonical one."""
    ambiguous = git_world.noremote
    git(ambiguous, "remote", "add", "upstream", "https://github.com/example-org/a.git")
    git(ambiguous, "remote", "add", "fork", "https://github.com/someone/a.git")

    binding = bind_cwd_to_repo(store, str(ambiguous))

    repo = store.find_repo_by_common_dir(str(ambiguous / ".git"))
    assert repo is not None
    assert repo.vcs_remote is None
    assert binding.anomaly is not None
    assert binding.anomaly.kind is AnomalyKind.GIT_AMBIGUOUS_REMOTE
    assert store.get_app_state("anomaly.git_ambiguous_remote") == 1


def test_single_unnamed_remote_is_used(store: Store, git_world: GitWorld) -> None:
    only = git_world.noremote
    git(only, "remote", "add", "upstream", "https://github.com/example-org/a.git")

    bind_cwd_to_repo(store, str(only))

    repo = store.find_repo_by_common_dir(str(only / ".git"))
    assert repo is not None
    assert repo.vcs_remote == "github.com/example-org/a"


def test_origin_wins_over_the_other_remotes(store: Store, git_world: GitWorld) -> None:
    bind_cwd_to_repo(store, str(git_world.main))

    repo = store.find_repo_by_common_dir(str(git_world.main / ".git"))
    assert repo is not None
    assert repo.vcs_remote == str(git_world.root / "origin-src")
