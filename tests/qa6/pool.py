"""A module's instances, helpers and sessionds, and the teardown that checks itself.

`InstancePool` is what the `pool` module fixture yields. Everything a scenario
starts through it is stopped at module end, in order: sessionds (SIGTERM, ≤5 s),
controlds (SIGTERM, ≤15 s, then SIGKILL **recorded as a teardown problem**),
helpers, and finally each instance's own tmux server on its own socket — only if
the socket file exists, and only through `tmuxctl.kill_server`, which refuses
any socket outside this run's `shepherd-m3-q6<pid>-<k>` pattern. Each step
verifies its own result; a failure is a teardown problem, never swallowed.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from . import paths, tmuxctl
from .instance import (
    Controld,
    Helper,
    SessiondManager,
    ready_instance,
    start_controld,
    start_helper,
)
from .sandbox import InstanceRoot, PathMode, RunContext


class InstancePool:
    def __init__(self, run: RunContext, owner: str) -> None:
        self.run = run
        self.owner = owner
        self.controlds: list[Controld] = []
        self.helpers: list[Helper] = []
        self.sessiond_managers: list[SessiondManager] = []
        self.sockets: set[str] = set()

    # ----- starting --------------------------------------------------------
    def ready(
        self,
        *,
        path_mode: PathMode = "shims",
        sessions_dir: bool = True,
        master_model: str | None = None,
        configure: Callable[[InstanceRoot], None] | None = None,
    ) -> Controld:
        controld = ready_instance(
            self.run, path_mode=path_mode, sessions_dir=sessions_dir,
            master_model=master_model, configure=configure,
        )
        self.adopt(controld)
        return controld

    def start(
        self,
        root: InstanceRoot,
        *,
        port: int = 0,
        path_mode: PathMode = "shims",
        env: Mapping[str, str] | None = None,
        extra_args: Sequence[str] = (),
        name: str = "controld",
    ) -> Controld:
        """Start a controld on an already-minted root, without a readiness wait."""
        controld = start_controld(
            self.run, root, port=port, path_mode=path_mode, env=env, extra_args=extra_args, name=name
        )
        self.adopt(controld)
        return controld

    def adopt(self, controld: Controld) -> None:
        self.controlds.append(controld)
        self.sockets.add(self.run.runner_socket(controld.root.k))

    def helper(self) -> Helper:
        helper = start_helper(self.run)
        self.helpers.append(helper)
        return helper

    def sessiond(self, controld: Controld) -> SessiondManager:
        manager = SessiondManager(controld)
        self.sessiond_managers.append(manager)
        return manager

    # ----- teardown ----------------------------------------------------------
    def close(self) -> list[str]:
        problems: list[str] = []
        for manager in self.sessiond_managers:
            for run in manager.history:
                if run.child.alive():
                    manager.stop(run)
                if run.child.alive():
                    problems.append(f"sessiond {run.name} pid {run.child.pid} still alive after stop")
        for controld in self.controlds:
            controld.stop()
            if controld.child.alive():
                problems.append(f"controld k={controld.root.k} pid {controld.child.pid} still alive after stop")
            if controld.socket_path is not None and controld.socket_path.exists():
                problems.append(f"controld k={controld.root.k} left its socket {controld.socket_path}")
        for helper in self.helpers:
            helper.end()
            if helper.popen.poll() is None:
                problems.append(f"helper pid {helper.pid} still alive")
        for socket in sorted(self.sockets):
            problems.extend(close_tmux_socket(self.run, socket))
        for problem in problems:
            self.run.teardown_problem(self.owner, problem)
        return problems


def close_tmux_socket(run: RunContext, socket: str) -> list[str]:
    """Kill our server on `socket` if one exists; verify it and its file are gone."""
    problems: list[str] = []
    socket_path = Path(tmuxctl.socket_file(socket))
    if not socket_path.exists():
        return problems
    if tmuxctl.server_running(socket, run.pid):
        tmuxctl.kill_server(socket, run.pid)
    if tmuxctl.server_running(socket, run.pid):
        problems.append(f"tmux server on {socket} still running after kill-server")
    if socket_path.exists():
        # tmux leaves the socket file behind when the server exits; ours to remove.
        os.unlink(socket_path)
    if socket_path.exists():
        problems.append(f"tmux socket file {socket_path} could not be removed")
    return problems


def socket_is_ours(run: RunContext, name: str) -> bool:
    return paths.runner_socket_pattern(run.pid).fullmatch(name) is not None
