"""`ScriptedHost` — the seam's `Scripted*` double (§14.2, D9).

A **concrete peer** of the real drivers, never a base class: nothing inherits
from it, and it answers every question from the seven frozen records it was
constructed with. That is what makes the contract suite a real second caller of
`HostPlatform`, and what lets the rest of M1 be tested without a host.

Ships with the package (§14.2) and lives in `testkit/`, which is deliberately
not a layer in ADR-1's map.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from shepherd.host.base import (
    DetachedLaunch,
    HookDispatchPlan,
    HostDirs,
    Liveness,
    LoginPersistence,
    SocketPlan,
    Supervision,
    plan_socket,
)


#: The default seventh answer: a scripted launch wraps nothing and says so.
#: `verified=False` because a fixture is not a capture.
SCRIPTED_DETACHED_LAUNCH = DetachedLaunch(
    prefix=(),
    mechanism="none",
    detail="scripted fixture: nothing wraps a scripted launch",
    verified=False,
)


@dataclass(frozen=True)
class ScriptedHost:
    """Constructed from seven frozen records; every answer comes from a fixture."""

    host_dirs: HostDirs
    socket_plan: SocketPlan
    dispatch: HookDispatchPlan
    supervision_plan: Supervision
    login: LoginPersistence
    liveness_by_pid: Mapping[int, Liveness] = field(default_factory=dict)
    detached: DetachedLaunch = SCRIPTED_DETACHED_LAUNCH
    observed_at: str = "1970-01-01T00:00:00+00:00"
    is_verified: bool = False

    def dirs(self) -> HostDirs:
        return self.host_dirs

    def control_socket(self, name: str) -> SocketPlan:
        """Composes the named socket under the scripted runtime directory.

        The budget arithmetic is the shared one, so a scripted host refuses an
        over-long path exactly as a real driver does — a double that could not
        refuse would let a caller pass a test the real host fails.
        """
        return plan_socket(
            runtime_dir=self.host_dirs.runtime_dir,
            name=name,
            dir_mode=self.socket_plan.dir_mode,
            sock_mode=self.socket_plan.sock_mode,
            socket_path_budget=self.socket_plan.socket_path_budget,
        )

    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan:
        return self.dispatch

    def supervision(self) -> Supervision:
        return self.supervision_plan

    def process_liveness(self, pid: int, start_token: str | None) -> Liveness:
        """Fixture liveness, with the same pid-reuse rule as a real driver."""
        scripted = self.liveness_by_pid.get(pid)
        if scripted is None:
            return Liveness(alive=False, start_token=None, observed_at=self.observed_at)
        if start_token is not None and scripted.start_token != start_token:
            return Liveness(
                alive=False,
                start_token=scripted.start_token,
                observed_at=scripted.observed_at,
            )
        return scripted

    def login_persistence(self) -> LoginPersistence:
        return self.login

    def detached_launch(self) -> DetachedLaunch:
        return self.detached

    def verified(self) -> bool:
        return self.is_verified
