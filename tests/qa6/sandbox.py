"""The run root, per-instance roots, and the sandboxed environment every child gets.

Layout (env-plan §1, §5, §7; test-plan §6):

* `/private/tmp/shq6-<pid>-0/` — the shared run root (`run0`): shims, the git
  fixture repos, H1's artifact, the pid/port/argv ledgers. `k = 0` is also W5's
  harness-owned tmux socket suffix.
* `/private/tmp/shq6-<pid>-<k>/` for k >= 1 — one per controld instance, with
  `home/`, `t/` (TMPDIR), `cfg/sessions/` (CLAUDE_CONFIG_DIR), `xdg/*`, `logs/`.

`<pid>` is the runner's pid (`QA6_RUN_PID`), so every pytest process in a run
shares one namespace and teardown can sweep exactly this run. `k` is allocated
through a lock file so two lane processes never mint the same instance.

The child environment is built from an **allow-list**, not by scrubbing a copy
of ours: the runner itself runs inside Claude Code and inherits a dozen
`CLAUDE*`/`AI_AGENT*` variables (setup.md §2), and a deny-list that missed one
would leak it into every pane. `TMUX` can never be inherited this way.

**Host safety (INC-1, SI-1).** Every env built here carries
`DISABLE_AUTOUPDATER=1`, and an env that carries the user's **real** HOME
carries **no** `XDG_*` variable at all: a real-HOME engine resolves its install
from the XDG data home but writes its launcher link under the real HOME, so a
sandboxed `XDG_DATA_HOME` once made it re-point the user's `~/.local/bin/claude`
into a run root (which teardown then deleted). `host_safety_problems` is the
one check; every builder here refuses an env it fails, and
`test_harness_guards.py::test_proof_host_safe_envs` proves the check bites.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from . import paths

#: Canonical `/tmp` (on macOS a symlink to `/private/tmp`). Instance paths are
#: built on the canonical form so every prefix comparison is like-for-like.
TMP_CANONICAL: Final[Path] = Path(os.path.realpath("/tmp"))

ENV_RUN_PID: Final[str] = "QA6_RUN_PID"
ENV_RUN_ID: Final[str] = "QA6_RUN_ID"
ENV_RUN_ROOT: Final[str] = "QA6_RUN_ROOT"
ENV_REPORT_DIR: Final[str] = "QA6_REPORT_DIR"
ENV_RUN_DIR: Final[str] = "QA6_RUN_DIR"
ENV_LANE: Final[str] = "QA6_LANE"
ENV_WAVE: Final[str] = "QA6_WAVE"
ENV_BLOCKED_FILE: Final[str] = "QA6_BLOCKED_FILE"
ENV_LIVE_AUTH_MODE: Final[str] = "QA6_LIVE_AUTH_MODE"

#: Prefixes the child env must never carry (env-plan §2 "Flags that must be OFF").
SCRUBBED_PREFIXES: Final[tuple[str, ...]] = ("CLAUDE", "ANTHROPIC", "AI_AGENT", "TMUX")

#: SI-1: what every env built here carries (the engine never self-updates in a run).
HOST_SAFETY_ENV: Final[dict[str, str]] = {"DISABLE_AUTOUPDATER": "1"}
#: SI-1: what a real-HOME env additionally carries (no installer repair of the user's link).
REAL_HOME_SAFETY_ENV: Final[dict[str, str]] = {"DISABLE_INSTALLATION_CHECKS": "1"}
#: SI-1: no env carrying the real HOME may carry a variable with this prefix.
XDG_PREFIX: Final[str] = "XDG_"

PathMode = Literal["shims", "live", "d9", "bare", "unseeded"]


@dataclass(frozen=True)
class RunContext:
    """One run: its pid namespace, its shared root and its report directory."""

    pid: int
    run_id: str
    run0: Path
    run_dir: Path

    @property
    def shims(self) -> Path:
        return self.run0 / "shims"

    @property
    def shims_live(self) -> Path:
        return self.run0 / "shims-live"

    @property
    def shims_d9(self) -> Path:
        return self.run0 / "shims-d9"

    @property
    def shims_unseeded(self) -> Path:
        """PATH head for instances started WITHOUT the pre-seeded DB (C7).

        An unseeded DB has no `runner_socket`, so the product's startup
        reconcile runs `tmux -L shepherd-runner …` (compose.py `_reconcile`).
        Those argvs are logged here, apart from the product log Z2 reads, and
        the scenario records them; they are never hidden.
        """
        return self.run0 / "shims-unseeded"

    @property
    def unseeded_tmux_argv_log(self) -> Path:
        return self.shims_unseeded / "tmux-argv.log"

    @property
    def real_claude_bin_dir(self) -> Path:
        """`<run0>/bin`: holds only `claude`, a symlink to the resolved real engine (realclaude.py)."""
        return self.run0 / "bin"

    @property
    def real_claude(self) -> Path:
        """The run-scoped real engine every live exec uses (never the user's `~/.local/bin/claude`)."""
        return self.real_claude_bin_dir / "claude"

    @property
    def artifacts(self) -> Path:
        return self.run0 / "artifacts"

    @property
    def repos(self) -> Path:
        return self.run0 / "repos"

    @property
    def tmux_argv_log(self) -> Path:
        return self.shims / "tmux-argv.log"

    @property
    def pane_tmux_argv_log(self) -> Path:
        """tmux calls made from inside a pane (`$TMUX` set): the engine's, never the product's."""
        return self.shims / "pane-tmux-argv.log"

    @property
    def claude_argv_log(self) -> Path:
        return self.shims / "claude-argv.log"

    @property
    def pid_ledger(self) -> Path:
        return self.run0 / "pids.jsonl"

    @property
    def controld_argv_ledger(self) -> Path:
        return self.run0 / "controld-argv.jsonl"

    @property
    def port_refusals(self) -> Path:
        return self.run0 / "port-refusals.log"

    @property
    def teardown_problems(self) -> Path:
        return self.run_dir / "teardown-problems.jsonl"

    def instance_root(self, k: int) -> Path:
        return TMP_CANONICAL / f"{paths.RUN_ROOT_PREFIX}{self.pid}-{k}"

    def runner_socket(self, k: int) -> str:
        return paths.runner_socket_name(self.pid, k)

    def allocate_k(self) -> int:
        """The next instance number for this run, unique across lane processes."""
        counter = self.run0 / "k.counter"
        with open(counter, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            text = handle.read().strip()
            current = int(text) if text else 0
            nxt = current + 1
            handle.seek(0)
            handle.truncate()
            handle.write(str(nxt))
            handle.flush()
            fcntl.flock(handle, fcntl.LOCK_UN)
        return nxt

    def ledger(self, path: Path, entry: Mapping[str, object]) -> None:
        """Append one JSON line to a run ledger (single write, O_APPEND)."""
        line = json.dumps(dict(entry), sort_keys=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def record_pid(self, pid: int, kind: str, argv: list[str]) -> None:
        self.ledger(self.pid_ledger, {"pid": pid, "kind": kind, "argv": argv, "at": time.time()})

    def teardown_problem(self, where: str, problem: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ledger(self.teardown_problems, {"where": where, "problem": problem, "at": time.time()})


def context_from_env(environ: Mapping[str, str]) -> RunContext | None:
    """The runner's context, if this process was started by `run.py`."""
    pid = environ.get(ENV_RUN_PID)
    run_id = environ.get(ENV_RUN_ID)
    run_dir = environ.get(ENV_RUN_DIR)
    if not pid or not run_id or not run_dir:
        return None
    run0 = TMP_CANONICAL / f"{paths.RUN_ROOT_PREFIX}{int(pid)}-0"
    return RunContext(pid=int(pid), run_id=run_id, run0=run0, run_dir=Path(run_dir))


def mint_run(pid: int, run_id: str, run_dir: Path) -> RunContext:
    """Create the shared run root `shq6-<pid>-0` (0700) and its ledgers."""
    run0 = TMP_CANONICAL / f"{paths.RUN_ROOT_PREFIX}{pid}-0"
    run0.mkdir(mode=0o700, parents=False, exist_ok=False)
    for sub in ("shims", "shims-live", "shims-d9", "shims-unseeded", "artifacts", "repos", "bin"):
        (run0 / sub).mkdir(mode=0o700)
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(pid=pid, run_id=run_id, run0=run0, run_dir=run_dir)


@dataclass(frozen=True)
class InstanceRoot:
    """One instance's private tree. Nothing in it is shared with another k."""

    k: int
    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def tmpdir(self) -> Path:
        return self.root / "t"

    @property
    def cfg(self) -> Path:
        return self.root / "cfg"

    @property
    def sessions(self) -> Path:
        return self.cfg / "sessions"

    @property
    def xdg(self) -> Path:
        return self.root / "xdg"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def cwd(self) -> Path:
        return self.root / "cwd"

    @property
    def data_dir(self) -> Path:
        """Where MacHost puts Shepherd's data for this HOME (mac.py `dirs()`)."""
        return self.home / "Library" / "Application Support" / "Shepherd"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "shepherd.db"

    @property
    def runtime_dir(self) -> Path:
        return self.tmpdir / "Shepherd"

    @property
    def controld_socket(self) -> Path:
        return self.runtime_dir / "controld.sock"

    @property
    def sessiond_socket(self) -> Path:
        return self.runtime_dir / "sessiond.sock"


def mint_instance(run: RunContext, *, sessions_dir: bool = True) -> InstanceRoot:
    """A fresh instance root for the next k. `sessions_dir=False` is D9's shape."""
    k = run.allocate_k()
    root = run.instance_root(k)
    root.mkdir(mode=0o700, exist_ok=False)
    instance = InstanceRoot(k=k, root=root)
    for directory in (instance.home, instance.tmpdir, instance.cfg, instance.logs, instance.cwd):
        directory.mkdir(mode=0o700)
    for name in ("data", "config", "state", "cache", "runtime"):
        (instance.xdg / name).mkdir(mode=0o700, parents=True)
    if sessions_dir:
        instance.sessions.mkdir(mode=0o700)
    return instance


def child_path(run: RunContext, mode: PathMode) -> str:
    """`PATH` for a child (env-plan §2). Shims first; the real `claude` only in LIVE."""
    tail = [str(paths.VENV_BIN), "/opt/homebrew/bin", "/usr/bin", "/bin"]
    if mode == "shims":
        head = [str(run.shims)]
    elif mode == "d9":
        head = [str(run.shims_d9)]
    elif mode == "unseeded":
        head = [str(run.shims_unseeded)]
    elif mode == "live":
        head = [str(run.shims_live), str(run.real_claude_bin_dir)]
    else:
        head = [str(run.shims_live)]
    return ":".join([*head, *tail])


def is_real_home(home: str | None) -> bool:
    """True when `home` names the user's real home (any spelling of it)."""
    return home is not None and os.path.realpath(home) == os.path.realpath(paths.REAL_HOME)


def host_safety_problems(env: Mapping[str, str]) -> list[str]:
    """SI-1: why `env` is unsafe for a child that may run the real engine (empty = safe)."""
    problems: list[str] = []
    for name, value in HOST_SAFETY_ENV.items():
        if env.get(name) != value:
            problems.append(f"{name} is {env.get(name)!r}, not {value!r}")
    if is_real_home(env.get("HOME")):
        xdg = sorted(name for name in env if name.startswith(XDG_PREFIX))
        if xdg:
            problems.append(f"the env carries the real HOME and {xdg}")
        for name, value in REAL_HOME_SAFETY_ENV.items():
            if env.get(name) != value:
                problems.append(f"the env carries the real HOME and {name} is {env.get(name)!r}, not {value!r}")
    return problems


def refuse_unsafe(env: Mapping[str, str], what: str) -> None:
    problems = host_safety_problems(env)
    if problems:
        raise ValueError(f"refusing {what}: host-unsafe (SI-1): {problems}")


def sandbox_env(
    run: RunContext,
    instance: InstanceRoot,
    *,
    path_mode: PathMode = "shims",
    tmpdir: Path | None = None,
    home: Path | None = None,
    config_dir: Path | None | Literal["unset"] = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The allow-listed environment for a controld/sessiond/CLI child.

    `config_dir="unset"` omits `CLAUDE_CONFIG_DIR` (the `needs_real_home` shape).
    A real `home` gets no `XDG_*` at all (SI-1); prefer `real_home_env`.
    """
    home_value = str(home if home is not None else instance.home)
    env: dict[str, str] = {
        "HOME": home_value,
        "TMPDIR": str(tmpdir if tmpdir is not None else instance.tmpdir),
        "PATH": child_path(run, path_mode),
        "PYTHONUNBUFFERED": "1",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "SHELL": "/bin/sh",
        "USER": os.environ.get("USER", "qa6"),
        "LOGNAME": os.environ.get("LOGNAME", os.environ.get("USER", "qa6")),
        **HOST_SAFETY_ENV,
    }
    if is_real_home(home_value):
        env.update(REAL_HOME_SAFETY_ENV)
    else:
        env.update(sandboxed_xdg(instance))
    if config_dir != "unset":
        env["CLAUDE_CONFIG_DIR"] = str(config_dir if config_dir is not None else instance.cfg)
    if extra:
        env.update(extra)
    leaked = [name for name in env if name.startswith(SCRUBBED_PREFIXES) and name != "CLAUDE_CONFIG_DIR"]
    if leaked:
        raise ValueError(f"refusing a child env carrying scrubbed variables: {leaked}")
    refuse_unsafe(env, "a child env")
    return env


def sandboxed_xdg(instance: InstanceRoot) -> dict[str, str]:
    """The instance's own XDG dirs — only ever for a sandboxed HOME."""
    return {
        "XDG_DATA_HOME": str(instance.xdg / "data"),
        "XDG_CONFIG_HOME": str(instance.xdg / "config"),
        "XDG_STATE_HOME": str(instance.xdg / "state"),
        "XDG_CACHE_HOME": str(instance.xdg / "cache"),
        "XDG_RUNTIME_DIR": str(instance.xdg / "runtime"),
    }


def real_home_env(
    run: RunContext,
    instance: InstanceRoot,
    *,
    path_mode: PathMode = "live",
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The one builder for a child that carries the user's real HOME (`needs_real_home`).

    Real `HOME`, `CLAUDE_CONFIG_DIR` unset, the instance's `TMPDIR`, no `XDG_*`,
    `DISABLE_AUTOUPDATER=1` and `DISABLE_INSTALLATION_CHECKS=1`. Shepherd's own
    dirs stay sandboxed by injection (the launcher's `MacHost(environ=...)`).
    """
    return sandbox_env(run, instance, path_mode=path_mode, home=paths.REAL_HOME, config_dir="unset", extra=extra)


def pytest_process_env(base: Mapping[str, str], extra: Mapping[str, str]) -> dict[str, str]:
    """The env for a lane's pytest process: ours, scrubbed, plus the run's knobs.

    The pytest process keeps the **real** HOME on purpose: `tests/conftest.py`'s
    settings guard then protects the user's real `~/.claude/settings.json`
    during qa6 too. Every product child gets `sandbox_env` instead. Because it
    carries the real HOME, it carries no `XDG_*` and the SI-1 opt-outs.
    """
    env = {
        name: value
        for name, value in base.items()
        if not name.startswith(SCRUBBED_PREFIXES) and not name.startswith("QA6_") and not name.startswith(XDG_PREFIX)
    }
    env.update(HOST_SAFETY_ENV)
    env.update(REAL_HOME_SAFETY_ENV)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(paths.BROWSERS_PATH)
    env["PYTHONUNBUFFERED"] = "1"
    env["LANG"] = "en_US.UTF-8"
    env["LC_ALL"] = "en_US.UTF-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    refuse_unsafe(env, "a lane process env")
    return env
