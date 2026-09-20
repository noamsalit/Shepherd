"""Throwaway git worlds for T7, built under `tmp_path` by the test itself.

Every layout here mirrors a captured case in
`docs/specs/data-schemas.md` §"`git rev-parse` outputs for cwd → repo binding",
§"`git remote get-url` forms" and §"`git worktree list --porcelain`".
No network, and nothing touches this repo's own git state: global and system
config are pinned to `/dev/null` and identity is passed per invocation.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

#: The seven captured spellings of one remote (§"`git remote get-url` forms").
REMOTE_FORMS: dict[str, str] = {
    "gh-ssh": "git@github.com:example-org/example-repo.git",
    "gh-sshurl": "ssh://git@github.com/example-org/example-repo.git",
    "gh-https": "https://github.com/example-org/example-repo.git",
    "gl-https-noext": "https://gitlab.com/example-org/sub-group/example-repo",
    "with-cred": "https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git",
}


def git_env() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
        GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="shepherd-test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="shepherd-test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
    )
    return environment


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@dataclass(frozen=True)
class GitWorld:
    root: Path
    main: Path
    subdir: Path
    worktree: Path
    submodule: Path
    nested: Path
    bare: Path
    symlink: Path
    plain: Path
    noremote: Path


@pytest.fixture()
def git_world(tmp_path: Path) -> GitWorld:
    root = tmp_path / "world"
    root.mkdir()

    origin_src = root / "origin-src"
    origin_src.mkdir()
    git(origin_src, "init", "-q", "-b", "main")
    (origin_src / "README.md").write_text("origin\n", encoding="utf-8")
    git(origin_src, "add", "-A")
    git(origin_src, "commit", "-qm", "initial")

    main = root / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    (main / "README.md").write_text("main\n", encoding="utf-8")
    (main / "src").mkdir()
    (main / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(main, "add", "-A")
    git(main, "commit", "-qm", "initial")
    git(main, "remote", "add", "origin", str(origin_src))
    for name, url in REMOTE_FORMS.items():
        git(main, "remote", "add", name, url)

    # a linked worktree — a *sibling* of the repo, which is why prefix
    # matching of cwd cannot bind it (D48)
    git(main, "worktree", "add", "-q", "-b", "feat/PROJ-1", str(root / "main-wt" / "PROJ-1"))

    # a submodule: its own common dir under .git/modules/
    git(
        main,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "--quiet",
        "add",
        str(origin_src),
        "mods/sub",
    )

    # a nested plain repo: innermost toplevel wins
    nested = main / "vendor" / "inner"
    nested.mkdir(parents=True)
    git(nested, "init", "-q", "-b", "main")

    bare = root / "bare.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")

    symlink = root / "link-to-main"
    symlink.symlink_to(main)

    plain = root / "plain" / "dir"
    plain.mkdir(parents=True)

    noremote = root / "noremote"
    noremote.mkdir()
    git(noremote, "init", "-q", "-b", "main")

    return GitWorld(
        root=root,
        main=main,
        subdir=main / "src",
        worktree=root / "main-wt" / "PROJ-1",
        submodule=main / "mods" / "sub",
        nested=nested,
        bare=bare,
        symlink=symlink,
        plain=plain,
        noremote=noremote,
    )


#: The uid/gid `git` must see as "not yours" for `safe.directory` to fire.
#: `nobody` on both platforms; the numbers are what `os.chown` takes.
FOREIGN_UID = 65534
FOREIGN_GID = 65534


@pytest.fixture()
def foreign_owned_repo(git_world: GitWorld) -> Path:
    """A repo owned by another uid, or an explicit skip — never a silent one.

    `git`'s "dubious ownership" refusal (E15) is the only anomaly in this suite
    that cannot be built by an ordinary user: producing it needs `os.chown` to a
    uid that is not ours, and that is `CAP_CHOWN`, i.e. root. This tree was
    built and verified on a Linux host running as root, where it simply worked,
    so the `chown` sat in `git_world`, and the first run as a normal user turned
    every test that reaches `git_world` into a `PermissionError` error. Counted
    2026-09-20: 26 tests depend on it, and 24 of them have nothing to do with
    ownership.

    Splitting it out is what keeps those 24 running. The two that genuinely need
    root — `test_bind_dubious_ownership_is_counted` and
    `test_discovery_skips_a_repo_it_cannot_read` — skip, loudly, naming the
    privilege they need. The skip is as narrow as the fact: it fires only when
    the `chown` itself is refused, so on a host that *can* build the case —
    every root CI runner, the Linux host this was written on — they run and a
    regression in dubious-ownership handling still goes red.
    """
    foreign = git_world.root / "foreign"
    foreign.mkdir()
    git(foreign, "init", "-q", "-b", "main")
    try:
        for path in [foreign, *foreign.rglob("*")]:
            os.chown(path, FOREIGN_UID, FOREIGN_GID)
    except PermissionError as refused:
        pytest.skip(
            "needs root: building git's dubious-ownership case requires chown to "
            f"uid {FOREIGN_UID}, which this user may not do ({refused})"
        )
    return foreign
