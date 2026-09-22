"""cwd → repo binding (D48) and remote normalisation (D50).

**The key is `git rev-parse --path-format=absolute --git-common-dir`, not
longest-prefix matching of `cwd`.** A linked worktree lives *beside* the repo it
belongs to (`<repo>-wt/<KEY>/`), so prefix matching returns null for exactly the
sessions that need binding, while the common dir returns the same key from the
repo root, from inside `.git`, and from the worktree.

**The remote is stripped of URL userinfo before it is stored.**
`git remote get-url` hands back credentials verbatim
(`https://oauth2:<token>@host/…`), and §13's redaction looks for secret-shaped
*keys* — a URL is not one, so a raw remote would carry a token into the
database, the UI and the agent's context.

Impure/pure split (the plan's purity map): `run_git` runs the subprocess;
`parse_git_output`, `parse_worktree_list` and `normalise_remote_url` are pure
and unit-tested. Every call is an argv list — never `shell=True` (§13).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.store.db import Store
from shepherd.store.models import UNASSIGNED_PROJECT_ID

GIT_TIMEOUT_S = 10.0

#: The one interrogation: three flags, each of which always prints a line
#: inside a repo, so line positions are stable.
REV_PARSE_ARGS: tuple[str, ...] = (
    "rev-parse",
    "--path-format=absolute",
    "--git-common-dir",
    "--git-dir",
    "--is-bare-repository",
)

_UNREADABLE_RC = 127


@dataclass(frozen=True)
class GitResult:
    rc: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class GitProbe:
    """What one `rev-parse` says about a directory."""

    git_common_dir: str | None
    git_dir: str | None
    is_bare: bool
    failure: AnomalyKind | None
    detail: str


@dataclass(frozen=True)
class RepoBinding:
    repo_id: str | None
    workspace_id: str
    git_common_dir: str | None
    anomaly: Anomaly | None


def run_git(args: list[str], cwd: str) -> GitResult:
    """Run `git` in `cwd`. Impure, and the only subprocess in this module."""
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        # `ValueError` is not decoration and not defensive: `subprocess.run`
        # raises it — not `OSError`, not `SubprocessError` — for a `cwd`
        # carrying an embedded NUL, and it walked straight out of a verb whose
        # contract is *"Never raises"*. `admission.py` already refuses that
        # exact input by name ("a cwd carrying a NUL byte … is refused, never
        # guessed at") while `hook_lane._with_foreign_repos` feeds this
        # function text derived from the engine's JSONL. The degradation path
        # below is unchanged: `_UNREADABLE_RC`, and the anomaly is counted.
        return GitResult(rc=_UNREADABLE_RC, stdout="", stderr=str(error))
    return GitResult(rc=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def parse_git_output(rc: int, stdout: str, stderr: str) -> GitProbe:
    """Pure: the `rev-parse` result, including the three captured failures."""
    if rc != 0:
        first = stderr.strip().splitlines()[0] if stderr.strip() else f"git exited {rc}"
        kind = (
            AnomalyKind.GIT_DUBIOUS_OWNERSHIP
            if "dubious ownership" in stderr
            else AnomalyKind.GIT_NOT_A_REPO
        )
        return GitProbe(
            git_common_dir=None, git_dir=None, is_bare=False, failure=kind, detail=first
        )

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) < 3:
        return GitProbe(
            git_common_dir=None,
            git_dir=None,
            is_bare=False,
            failure=AnomalyKind.GIT_NOT_A_REPO,
            detail=f"unexpected rev-parse output: {stdout!r}",
        )
    return GitProbe(
        git_common_dir=lines[0],
        git_dir=lines[1],
        is_bare=lines[2] == "true",
        failure=None,
        detail="",
    )


def parse_worktree_list(stdout: str) -> str | None:
    """Pure: the first `worktree` record — the main tree, which git lists first."""
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree ") :].strip()
    return None


def normalise_remote_url(raw: str) -> str | None:
    """Pure: one spelling per remote, with any URL userinfo removed (D50).

    The seven captured spellings of one GitHub/GitLab remote collapse to
    `host/org/repo`; a local path (a `clone --bare` origin) stays a path.
    Returns `None` when there is nothing to store.
    """
    text = raw.strip()
    if not text:
        return None
    if "://" in text:
        _, _, rest = text.partition("://")
        authority, _, path = rest.partition("/")
        return _host_and_path(authority, path)
    if ":" in text and not text.startswith(("/", ".", "~")):
        authority, _, path = text.partition(":")
        return _host_and_path(authority, path)
    return text


def _host_and_path(authority: str, path: str) -> str:
    host = authority.rpartition("@")[2].lower()
    trimmed = path.strip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    return f"{host}/{trimmed}" if trimmed else host


def probe_repo(cwd: str) -> GitProbe:
    result = run_git(list(REV_PARSE_ARGS), cwd)
    return parse_git_output(result.rc, result.stdout, result.stderr)


def repo_root(cwd: str, git_common_dir: str) -> str | None:
    """The repo's own root: the first record of `worktree list --porcelain`.

    git lists the main tree first, so a session inside a linked worktree still
    names the repo. **Except in a submodule**, where that record is the git dir
    itself (`…/.git/modules/mods/sub`) rather than the checkout — there
    `--show-toplevel` is the honest answer.
    """
    listed = run_git(["worktree", "list", "--porcelain"], cwd)
    first = parse_worktree_list(listed.stdout) if listed.rc == 0 else None
    if first is not None and not first.startswith(git_common_dir):
        return first
    toplevel = run_git(["rev-parse", "--path-format=absolute", "--show-toplevel"], cwd)
    if toplevel.rc == 0 and toplevel.stdout.strip():
        return toplevel.stdout.strip().splitlines()[0]
    return first


def resolve_remote(cwd: str) -> tuple[str | None, AnomalyKind | None]:
    """`origin` when there is one, the only remote when there is exactly one.

    Several remotes and no `origin` is ambiguous — git has no notion of which is
    canonical — so nothing is stored and the case is counted (C19).
    """
    listed = run_git(["remote"], cwd)
    names = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if listed.rc != 0 or not names:
        return None, AnomalyKind.GIT_NO_REMOTE
    if "origin" in names:
        chosen = "origin"
    elif len(names) == 1:
        chosen = names[0]
    else:
        return None, AnomalyKind.GIT_AMBIGUOUS_REMOTE
    url = run_git(["remote", "get-url", chosen], cwd)
    if url.rc != 0:
        return None, AnomalyKind.GIT_NO_REMOTE
    return normalise_remote_url(url.stdout), None


def _counted(store: Store, kind: AnomalyKind, detail: str) -> Anomaly:
    store.bump_anomaly(kind.value)
    return Anomaly(kind=kind, detail=detail, engine_session_id=None)


def _resolve_project(store: Store, repo_id: str) -> str:
    """D59/D60: which project a **discovered** session's repo belongs to.

    Exactly one project is the only unambiguous answer. More than one is D60 —
    a discovered session cannot be asked which it meant — and none is D59. Both
    land on the reserved project, where a person can move them, rather than on
    a guess a person would have to notice in order to correct.
    """
    projects = store.projects_for_repo(repo_id)
    return projects[0] if len(projects) == 1 else UNASSIGNED_PROJECT_ID


def bind_cwd_to_repo(store: Store, cwd: str) -> RepoBinding:
    """Turn a session's `cwd` into a repo and a workspace. Never raises.

    An unresolvable directory is counted and reported (principle 5), and the
    session still lands in a workspace so the fleet page can show it.

    **It creates no project** (D59). Before the `project_repo` join table this
    verb called `upsert_workspace(basename(cwd), cwd)` on three of its four
    branches, so every stray directory minted a project named after itself.
    Work that matches no declared project now lands in the reserved one.

    The repo row is still written, by `upsert_repo` and **not** `add_repo`:
    `add_repo` attaches a repo to a project, and attaching every discovered
    repo to the reserved one would widen `_registered_roots("unassigned")` to
    every repo this machine has ever seen — a §13 allowlist that grows by
    discovery (F10).
    """
    probe = probe_repo(cwd)

    if probe.failure is not None or probe.git_common_dir is None:
        kind = probe.failure or AnomalyKind.GIT_NOT_A_REPO
        return RepoBinding(
            repo_id=None,
            workspace_id=UNASSIGNED_PROJECT_ID,
            git_common_dir=None,
            anomaly=_counted(store, kind, probe.detail or cwd),
        )

    if probe.is_bare:
        return RepoBinding(
            repo_id=None,
            workspace_id=UNASSIGNED_PROJECT_ID,
            git_common_dir=probe.git_common_dir,
            anomaly=_counted(store, AnomalyKind.GIT_BARE_REPO, cwd),
        )

    known = store.find_repo_by_common_dir(probe.git_common_dir)
    if known is not None:
        return RepoBinding(
            repo_id=known.id,
            workspace_id=_resolve_project(store, known.id),
            git_common_dir=probe.git_common_dir,
            anomaly=None,
        )

    root = repo_root(cwd, probe.git_common_dir) or str(Path(probe.git_common_dir).parent)
    remote, remote_kind = resolve_remote(cwd)
    repo = store.upsert_repo(
        root_path=root,
        name=Path(root).name or "local",
        vcs_remote=remote,
        git_common_dir=probe.git_common_dir,
    )
    anomaly = None if remote_kind is None else _counted(store, remote_kind, root)
    return RepoBinding(
        repo_id=repo.id,
        workspace_id=_resolve_project(store, repo.id),
        git_common_dir=probe.git_common_dir,
        anomaly=anomaly,
    )
