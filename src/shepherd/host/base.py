"""D55's seam: the seven questions a platform answers, and nothing else (ADR-5).

Seven methods, each returning a frozen record that answers a whole question, so a
caller learns one call and gets everything that question implies. Every other
module in the system reads platform facts through this interface;
`tests/boundaries/test_platform_branching.py` makes that mechanical.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

#: `Supervision.kind`. Three deployment shapes, not two (D55): a macOS package,
#: a Linux host under the systemd user manager, and a Linux **container** with
#: no systemd, no `loginctl` and often no D-Bus — where supervision is "run in
#: the foreground and let the container runtime restart us".
SupervisionKind = Literal["systemd_user", "launchd", "foreground"]

#: The one kind whose supervisor **captures what we launch** into its own
#: cgroup (D55, DP5). Named here, beside the type it belongs to, so a driver
#: compares a kind against a value this layer defines rather than against a
#: string literal of its own — the form `tests/boundaries` requires of every
#: `.kind` in the tree.
SUPERVISION_KIND_SYSTEMD_USER: SupervisionKind = "systemd_user"


class SocketPathTooLong(ValueError):
    """A control-socket path that does not fit the platform's byte budget.

    E19: 107 bytes bind on Linux and 108 fail (`AF_UNIX path too long`); D55
    records 103 for macOS, for which no capture exists. The budget is a seam
    value rather than a constant precisely because a path that binds on one
    platform can fail on the other — so it is checked here, before bind and
    before install, rather than at the bind site.
    """

    def __init__(self, path: Path, budget: int) -> None:
        size = len(str(path).encode("utf-8"))
        super().__init__(f"control socket path is {size} bytes, budget is {budget}: {path}")
        self.path = path
        self.budget = budget


@dataclass(frozen=True)
class HostDirs:
    """State, config and runtime directories, with the platform's rules applied."""

    data_dir: Path
    config_dir: Path
    runtime_dir: Path


@dataclass(frozen=True)
class SocketPlan:
    """Everything a binder needs: where, at what modes, within what budget."""

    path: Path
    dir_mode: int
    sock_mode: int
    socket_path_budget: int


@dataclass(frozen=True)
class HookDispatchPlan:
    """The shell one-liner a non-Python hook client uses to reach the socket.

    The sixth seam member (Decision pressure 2). `host/` is its one definition
    package; every consumer reads it from here rather than spelling it again.
    """

    command: str
    requires: tuple[str, ...]
    available: bool
    reason: str


@dataclass(frozen=True)
class DetachedLaunch:
    """How to wrap an argv so what it starts escapes the caller's supervision.

    The seventh seam member (D55, M3 plan DP5). A tmux server first started
    *inside* a systemd user unit stays in that unit's cgroup, so the default
    `KillMode=control-group` kills the server **and every owned pane** on both
    `stop` and `restart` — the opposite of the guarantee tmux was chosen for.

    `prefix` is an **argv fragment, never a command line**: `[*prefix, *argv]`
    is the launch, so there is no place for a shell to enter (K5). `()` means
    no wrapper is needed, which is an answer and not an absence.
    """

    prefix: tuple[str, ...]
    mechanism: str
    detail: str
    verified: bool


@dataclass(frozen=True)
class Supervision:
    """How — or whether — a long-lived process is supervised on this host."""

    kind: SupervisionKind
    detail: str
    manageable: bool
    start_limit_note: str


@dataclass(frozen=True)
class Liveness:
    """Whether a pid is alive, guarded against pid reuse by its start token."""

    alive: bool
    start_token: str | None
    observed_at: str


@dataclass(frozen=True)
class LoginPersistence:
    """Whether our processes survive logout, and by what mechanism."""

    enabled: bool | None
    mechanism: str
    detail: str


class HostPlatform(Protocol):
    """The seam. Seven members, plus whether this driver was ever verified."""

    def dirs(self) -> HostDirs: ...

    def control_socket(self, name: str) -> SocketPlan: ...

    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan: ...

    def supervision(self) -> Supervision: ...

    def process_liveness(self, pid: int, start_token: str | None) -> Liveness: ...

    def login_persistence(self) -> LoginPersistence: ...

    def detached_launch(self) -> DetachedLaunch: ...

    def verified(self) -> bool: ...


def plan_socket(
    runtime_dir: Path,
    name: str,
    dir_mode: int,
    sock_mode: int,
    socket_path_budget: int,
) -> SocketPlan:
    """Compose a control-socket plan, refusing a path that exceeds the budget.

    Pure: no I/O, no clock. Shared by every driver so the budget is checked the
    same way everywhere and the contract suite exercises one arithmetic.
    """
    path = runtime_dir / f"{name}.sock"
    if len(str(path).encode("utf-8")) > socket_path_budget:
        raise SocketPathTooLong(path, socket_path_budget)
    return SocketPlan(
        path=path,
        dir_mode=dir_mode,
        sock_mode=sock_mode,
        socket_path_budget=socket_path_budget,
    )
