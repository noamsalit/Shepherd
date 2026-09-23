"""The run root, the short runtime dir, and the sweep that never guesses.

**B20, and it is the whole of this module.** The session scratchpad handed to
this workflow is long-lived and *shared*: it holds hundreds of prior artefacts
and, decisively, `macwt` — a **registered git worktree of the repo under test**,
whose registry entry is `/root/Shepherd/.git/worktrees/macwt/gitdir`. An earlier
revision of the env plan said `rm -rf $SCRATCH` meaning that directory. It would
have destroyed a checkout of the repo under test, corrupted the registry, **and
still reported `git status --porcelain src/ tools/ docs/probes/` empty** — a
teardown that breaks the repo and certifies itself clean.

So: the run mints `$SESSION_SCRATCH/qa5-<pid>` and removes **only that**. The
implemented form is the **run-root** form, recorded in `setup.md` §7 as this
builder's answer to B20.

**B9/P4, the socket budget, computed with the product's own arithmetic.**
`XDG_RUNTIME_DIR` cannot live under the run root: the suffix
`/shepherd/controld.sock` is 23 bytes against a 107-byte `AF_UNIX` budget, so
the ceiling on the directory is 84 and the run root is past it. `/tmp/shq5-<pid>`
spends 17. The number is never re-derived here — `assert_socket_budget` calls
`plan_socket` itself, so a product change to either constant moves this check
with it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME
from shepherd.host.base import plan_socket
from shepherd.host.linux import (
    APP_DIR_NAME,
    LINUX_SOCKET_PATH_BUDGET,
    SOCKET_DIR_MODE,
    SOCKET_MODE,
)

REPO_ROOT = Path("/root/Shepherd")

#: The subdirectories the run root carries. `tmp` is here because §7 sets
#: `TMPDIR` into it, and an earlier revision set the variable without creating
#: the directory.
RUN_ROOT_DIRS: tuple[str, ...] = (
    "xdg_data",
    "xdg_config",
    "xdg_state",
    "xdg_cache",
    "home",
    "tmp",
    "engine-config/sessions",
    "work",
    "shots",
    "repo",
)


class HarnessBlocked(AssertionError):
    """An environment verdict. Never a product verdict.

    Raised where the harness could not be built or torn down. `qa-execute` reads
    this as `BLOCKED`; a product failure raises a plain `AssertionError`.
    """


@dataclass(frozen=True)
class RunRoot:
    """The two directories this run owns, and nothing else."""

    session_scratch: Path
    root: Path
    runtime_dir: Path
    worktree_baseline: str

    def sub(self, name: str) -> Path:
        return self.root / name


def _pid_of(path: Path, prefix: str) -> int | None:
    tail = path.name[len(prefix) :]
    return int(tail) if tail.isdigit() else None


def _alive(pid: int) -> bool:
    """Is a process with this pid still running?

    `os.kill(pid, 0)` delivers nothing — it is a permission-and-existence probe.
    It is still refused for pids 0, 1 and -1 by `tests/conftest.py`'s runtime
    net, and this function never reaches those: a swept directory's suffix is a
    pid this harness wrote, and the guard below refuses anything else outright.
    """
    if pid <= 1:
        raise HarnessBlocked(f"refusing to probe pid {pid}: not a pid this harness ever minted")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def sweep(session_scratch: Path, live_pid: int) -> list[str]:
    """Remove abandoned run roots and runtime dirs — **by our own pattern only**.

    This is the rule `macwt` exists to teach: never remove an entry you did not
    name. The two globs match `qa5-<digits>` and `shq5-<digits>` and nothing
    else, a survivor whose pid is **alive** is a concurrent run and is left
    alone, and every removal is returned so the run reports what it did rather
    than deleting silently.
    """
    removed: list[str] = []
    for parent, prefix in ((session_scratch, "qa5-"), (Path("/tmp"), "shq5-")):
        if not parent.is_dir():
            continue
        for candidate in sorted(parent.glob(f"{prefix}[0-9]*")):
            pid = _pid_of(candidate, prefix)
            if pid is None or pid == live_pid:
                continue
            if _alive(pid):
                raise HarnessBlocked(
                    f"{candidate} belongs to live pid {pid}: a concurrent run, not a leak. "
                    "Stop; do not delete it."
                )
            shutil.rmtree(candidate, ignore_errors=False)
            removed.append(str(candidate))
    return removed


def worktree_list() -> str:
    """The teardown baseline: `git worktree list`, captured at bring-up."""
    done = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "list"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if done.returncode != 0:
        raise HarnessBlocked(f"git worktree list failed: {done.stderr.strip()}")
    return done.stdout


def assert_socket_budget(runtime_dir: Path) -> int:
    """The budget, as an integer, through the product's own `plan_socket`.

    Returns the number of bytes spent. Raises `SocketPathTooLong` from the
    product if the directory is too long — which is the point: this harness
    never re-derives 107, 23 or 84.
    """
    plan = plan_socket(
        runtime_dir / APP_DIR_NAME,
        CONTROL_SOCKET_NAME,
        SOCKET_DIR_MODE,
        SOCKET_MODE,
        LINUX_SOCKET_PATH_BUDGET,
    )
    return len(str(plan.path).encode("utf-8"))


def mint(session_scratch: Path, pid: int) -> RunRoot:
    """§4 steps 1-2: sweep, mint the run root, mint the short runtime dir."""
    if not session_scratch.is_dir():
        raise HarnessBlocked(f"the session scratchpad does not exist: {session_scratch}")
    sweep(session_scratch, pid)
    baseline = worktree_list()
    if not baseline.strip():
        raise HarnessBlocked("git worktree list returned nothing; the baseline would be vacuous")

    root = session_scratch / f"qa5-{pid}"
    if root.exists():
        raise HarnessBlocked(f"the run root already exists before it was minted: {root}")
    for name in RUN_ROOT_DIRS:
        (root / name).mkdir(parents=True)
    for name in RUN_ROOT_DIRS:
        if not (root / name).is_dir():
            raise HarnessBlocked(f"run root subdirectory missing after mkdir: {root / name}")

    runtime_dir = Path(f"/tmp/shq5-{pid}")
    runtime_dir.mkdir(parents=True, exist_ok=False)
    if not os.access(runtime_dir, os.W_OK):
        raise HarnessBlocked(f"the short runtime dir is not writable: {runtime_dir}")
    assert_socket_budget(runtime_dir)
    return RunRoot(
        session_scratch=session_scratch,
        root=root,
        runtime_dir=runtime_dir,
        worktree_baseline=baseline,
    )


def destroy(run: RunRoot) -> list[str]:
    """§9 steps 7-9. Verifies itself, and never touches the session scratchpad.

    Returns the verification lines. A teardown that ignores its own result leaks
    resources silently, so every check below raises rather than logging.
    """
    checks: list[str] = []
    shutil.rmtree(run.runtime_dir, ignore_errors=False)
    if run.runtime_dir.exists():
        raise HarnessBlocked(f"the runtime dir survived its own removal: {run.runtime_dir}")
    checks.append(f"runtime dir removed: {run.runtime_dir}")

    shutil.rmtree(run.root, ignore_errors=False)
    if run.root.exists():
        raise HarnessBlocked(f"the run root survived its own removal: {run.root}")
    checks.append(f"run root removed: {run.root}")

    if not run.session_scratch.is_dir():
        raise HarnessBlocked(
            f"the SHARED session scratchpad is gone: {run.session_scratch}. "
            "This run was never permitted to remove it."
        )
    checks.append(f"session scratchpad intact: {run.session_scratch}")

    status = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "src/", "tools/", "docs/probes/"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise HarnessBlocked(
            "the repo is not as QA found it — src/, tools/ or the frozen "
            f"docs/probes/ evidence moved: {status.stdout.strip()!r}"
        )
    checks.append("src/ tools/ docs/probes/ clean")

    now = worktree_list()
    if now != run.worktree_baseline:
        raise HarnessBlocked(
            "git worktree list changed across the run — a worktree was pruned, "
            f"moved or destroyed.\nbaseline:\n{run.worktree_baseline}\nnow:\n{now}"
        )
    checks.append("git worktree list identical to the bring-up baseline")
    return checks
