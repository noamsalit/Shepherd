"""Mint a run: the shared root, the shims, and the git fixture repos (env-plan §4 step 3).

Used by `run.py` for a real run and by `conftest.qa6_run` when a qa6 module is
run directly under pytest (standalone), in which case this process's pid names
the run and its teardown runs at session end.

Git fixtures are built with `/usr/bin/git`, `GIT_CONFIG_GLOBAL=/dev/null`, a
fixed author and a fixed date, inside the run root only (test-plan §6):
`alpha` (one commit), `beta`, `my repo` (a space), `loose` (not a repo), the
linked worktree `alpha-wt`, and a submodule `alpha/vendor-beta` of beta.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import hostprobe, paths, realclaude, shims, teardown
from .sandbox import (
    ENV_RUN_DIR,
    ENV_RUN_ID,
    ENV_RUN_PID,
    RunContext,
    mint_run,
)

FIXED_DATE = "2026-09-01T12:00:00Z"
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "QA6",
    "GIT_AUTHOR_EMAIL": "qa6@example.invalid",
    "GIT_COMMITTER_NAME": "QA6",
    "GIT_COMMITTER_EMAIL": "qa6@example.invalid",
    "GIT_AUTHOR_DATE": FIXED_DATE,
    "GIT_COMMITTER_DATE": FIXED_DATE,
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent-qa6-git-home",
    "LANG": "en_US.UTF-8",
}


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(
        [str(paths.GIT_BIN), *args], cwd=str(cwd) if cwd else None, env=GIT_ENV,
        capture_output=True, text=True, timeout=30, check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {args} failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout


def _repo(path: Path, marker: str) -> None:
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", str(path))
    (path / "README.md").write_text(f"{marker}\n", encoding="utf-8")
    git("-C", str(path), "add", "README.md")
    git("-C", str(path), "commit", "-q", "-m", f"{marker}: initial")


def seed_repos(run: RunContext) -> dict[str, Path]:
    repos = run.repos
    alpha, beta, spaced, loose = repos / "alpha", repos / "beta", repos / "my repo", repos / "loose"
    _repo(alpha, "alpha")
    _repo(beta, "beta")
    _repo(spaced, "my repo")
    loose.mkdir()
    (alpha / "sub").mkdir()
    git("-C", str(alpha), "worktree", "add", "-q", str(repos / "alpha-wt"))
    git("-C", str(alpha), "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(beta), "vendor-beta")
    git("-C", str(alpha), "commit", "-q", "-m", "alpha: add the beta submodule")
    for name, path in (("alpha", alpha), ("beta", beta), ("my repo", spaced)):
        if not (path / ".git").exists():
            raise RuntimeError(f"fixture repo {name} has no .git")
    return {
        "alpha": alpha, "beta": beta, "spaced": spaced, "loose": loose,
        "alpha_wt": repos / "alpha-wt", "submodule": alpha / "vendor-beta",
    }


def remove_worktree(run: RunContext) -> list[str]:
    """env-plan §9 step 7: `git -C alpha worktree remove --force alpha-wt`, verified."""
    alpha, wt = run.repos / "alpha", run.repos / "alpha-wt"
    if not wt.exists():
        return []
    git("-C", str(alpha), "worktree", "remove", "--force", str(wt))
    listing = git("-C", str(alpha), "worktree", "list")
    return [f"worktree still listed: {listing.strip()}"] if "alpha-wt" in listing else []


def mint(pid: int, run_id: str, run_dir: Path) -> RunContext:
    """The shared root, the shims, the repos, and the run-scoped real engine.

    The user's `~/.local/bin/claude` state is recorded first (if the runner has
    not already done so at its own start), then the real engine is resolved and
    exposed as `<run0>/bin/claude` (realclaude.py; INC-1).
    """
    link = realclaude.record_link_start(run_dir)
    collision = f"/{paths.RUN_ROOT_PREFIX}{pid}-"
    if any(collision in str(link.get(key)) for key in ("target", "resolved")):
        raise RuntimeError(f"refusing to mint run pid {pid}: the user's {paths.REAL_CLAUDE_BIN} points into this "
                           f"run's namespace ({link}); the harness would create files where the user's link points")
    run = mint_run(pid, run_id, run_dir)
    shims.write_shims(run)
    shims.selftest(run)
    seed_repos(run)
    realclaude.install(run, realclaude.resolve(os.environ))
    return run


def standalone_run() -> RunContext:
    pid = os.getpid()
    run_id = time.strftime("qa6-standalone-%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = paths.DEFAULT_REPORT_DIR / run_id
    os.environ[ENV_RUN_PID] = str(pid)
    os.environ[ENV_RUN_ID] = run_id
    os.environ[ENV_RUN_DIR] = str(run_dir)
    run = mint(pid, run_id, run_dir)
    hostprobe.write_baseline(run_dir / "baseline.json", hostprobe.snapshot())
    return run


def standalone_teardown(run: RunContext) -> None:
    problems = remove_worktree(run)
    report = teardown.teardown_run(run)
    problems.extend(report.problems)
    for problem in problems:
        run.teardown_problem("standalone", problem)
