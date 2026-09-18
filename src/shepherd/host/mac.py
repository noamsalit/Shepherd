"""`MacHost` — D55's second driver, written and **unverified** (T4).

No capture exists for any macOS path, socket budget, `launchctl`, `ps`/kqueue
liveness, `RunAtLoad` persistence or netcat flag set (gap G1). That is the
expected state at M1, not a blocker: every value below carries
`UNVERIFIED (no capture)` and cites D55 for where the value came from, and a
static test (`test_machost_constants_are_annotated`) fails the build if a
literal ever appears here without that marker.

`verified()` returns False. Where the honest answer is "refuse rather than
guess" — the hook-side dispatch command, whose flag set is the exact thing that
differs (`-q0`), and every host probe run off-platform — this module refuses
with a reason instead of returning a value that looks measured.

Closing G1 is a macOS run of `tests/contracts/test_hostplatform_contract.py`
plus captures of `sun_path` overflow, `launchctl print`, `ps -o lstart` and the
macOS netcat flag set. Deferred to M6 by the plan's validation level for T4.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.core.clock import utc_now
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

def peercred(sock: socket.socket) -> int | None:
    """macOS peer credentials — **unverified**, so the answer is `None` (G1).

    macOS spells this `LOCAL_PEERCRED` over `SOL_LOCAL` and returns an `xucred`,
    which carries no pid at all in the documented struct; `LOCAL_PEERPID` is the
    pid-bearing option. Neither is captured on any host we have, and D41 forbids
    typing a shape from memory — so this refuses to invent one and reports the
    unknown it actually is (principle 5). Closing it is one macOS capture, the
    same run that closes the rest of G1.
    """
    return None  # UNVERIFIED (no capture) — D55: unknown, never guessed


MAC_SOCKET_PATH_BUDGET = 103  # UNVERIFIED (no capture) — D55: sun_path is 103 bytes on macOS
MAC_SOCKET_DIR_MODE = 0o700  # UNVERIFIED (no capture) — D55: same 0700 rule assumed
MAC_SOCKET_MODE = 0o600  # UNVERIFIED (no capture) — D55: same 0600 rule assumed
MAC_APP_DIR_NAME = "Shepherd"  # UNVERIFIED (no capture) — D55: macOS bundle-style directory name
MAC_DATA_PARENT = "Library/Application Support"  # UNVERIFIED (no capture) — D55
MAC_CONFIG_PARENT = "Library/Preferences"  # UNVERIFIED (no capture) — D55
MAC_RUNTIME_ENV = "TMPDIR"  # UNVERIFIED (no capture) — D55: runtime dir under TMPDIR
MAC_RUNTIME_FALLBACK = "/tmp"  # UNVERIFIED (no capture) — D55: TMPDIR is normally set on macOS
MAC_PLATFORM = "darwin"  # UNVERIFIED (no capture) — D55: no macOS host has run this code

#: The macOS netcat is a different build and **does not take `-q0`** (G2, E34),
#: which is the single character the two platforms' commands differ on and the
#: reason the dispatch command is a seam member at all.
MAC_DISPATCH_REQUIREMENTS = ("timeout", "nc")  # UNVERIFIED (no capture) — D55
MAC_DISPATCH_TIMEOUT_S = "0.25"  # UNVERIFIED (no capture) — D55
MAC_DISPATCH_REASON = (  # UNVERIFIED (no capture) — D55
    "macOS netcat flag set unverified — no capture; the installer must refuse "  # UNVERIFIED
    "rather than write a hook that costs 250 ms or delivers nothing (G2, E34)"  # UNVERIFIED
)
MAC_SUPERVISION_DETAIL = (  # UNVERIFIED (no capture) — D55
    "launchd user agent assumed; `launchctl print gui/<uid>` output shape "  # UNVERIFIED
    "has never been captured"  # UNVERIFIED (no capture) — D55
)
MAC_START_LIMIT_NOTE = (  # UNVERIFIED (no capture) — D55
    "launchd throttles a respawning agent (ThrottleInterval); the value and "  # UNVERIFIED
    "its failure mode have never been measured on a Mac"  # UNVERIFIED (no capture) — D55
)
MAC_PERSISTENCE_MECHANISM = "launchd RunAtLoad agent"  # UNVERIFIED (no capture) — D55
MAC_PERSISTENCE_DETAIL = (  # UNVERIFIED (no capture) — D55
    "no capture of a RunAtLoad agent exists, so whether persistence is on is "  # UNVERIFIED
    "unknown rather than false (principle 5)"  # UNVERIFIED (no capture) — D55
)
MAC_DETACH_MECHANISM = "none"  # UNVERIFIED (no capture) — D55: launchd has no cgroup to escape
MAC_DETACH_DETAIL = (  # UNVERIFIED (no capture) — D55
    "launchd is not a cgroup manager, so no wrapper is believed to be needed; "  # UNVERIFIED
    "no Mac has ever been observed keeping a tmux server alive across an agent "  # UNVERIFIED
    "reload, so this is written and annotated, never measured (T7)"  # UNVERIFIED
)
MAC_LIVENESS_ARGV_HEAD = ("ps", "-o", "lstart=", "-p")  # UNVERIFIED (no capture) — D55
MAC_OFF_PLATFORM_REASON = (  # UNVERIFIED (no capture) — D55
    "MacHost host probes refuse off-platform: running them here would answer "  # UNVERIFIED
    "about this Linux host, which is the failure D41 forbids"  # UNVERIFIED
)


class UnverifiedHostCapability(RuntimeError):
    """Raised instead of guessing, when no capture backs an answer (D41, G1)."""


def mac_liveness_argv(pid: int) -> tuple[str, ...]:
    """The intended macOS liveness probe. Read-only; never verified."""
    return (*MAC_LIVENESS_ARGV_HEAD, str(pid))  # UNVERIFIED (no capture) — D55


def mac_dispatch_command(socket_path: Path) -> str:
    """The macOS hook-side command — **without** `-q0` (G2, E34).

    Returned so `doctor` and the installer can show what would be written, but
    `hook_dispatch()` reports it unavailable until a Mac run confirms the flags.
    """
    return f"timeout {MAC_DISPATCH_TIMEOUT_S} nc -U {socket_path} || true"  # UNVERIFIED — D55


def _now() -> str:
    return utc_now()


@dataclass(frozen=True)
class MacHost:
    """The macOS driver: written, annotated, and honest about being unverified."""

    environ: Mapping[str, str] = field(default_factory=dict)
    uid: int = 0  # UNVERIFIED (no capture) — D55: no macOS uid has been observed

    def _home(self) -> Path:
        home = self.environ.get("HOME")  # UNVERIFIED (no capture) — D55
        return Path(home) if home else Path.home()

    def _on_platform(self) -> bool:
        return sys.platform == MAC_PLATFORM

    def dirs(self) -> HostDirs:
        """`~/Library/Application Support` and `~/Library/Preferences`, per D55.

        Pure path composition, so it runs in the contract suite everywhere; no
        macOS host has ever confirmed these are the directories Shepherd should
        use, which is what the annotations say.
        """
        home = self._home()
        runtime = self.environ.get(MAC_RUNTIME_ENV) or MAC_RUNTIME_FALLBACK
        return HostDirs(
            data_dir=home / MAC_DATA_PARENT / MAC_APP_DIR_NAME,
            config_dir=home / MAC_CONFIG_PARENT / MAC_APP_DIR_NAME,
            runtime_dir=Path(runtime) / MAC_APP_DIR_NAME,
        )

    def control_socket(self, name: str) -> SocketPlan:
        return plan_socket(
            runtime_dir=self.dirs().runtime_dir,
            name=name,
            dir_mode=MAC_SOCKET_DIR_MODE,
            sock_mode=MAC_SOCKET_MODE,
            socket_path_budget=MAC_SOCKET_PATH_BUDGET,
        )

    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan:
        """Refuses rather than guessing: `available=False`, with the reason."""
        return HookDispatchPlan(
            command=mac_dispatch_command(plan.path),
            requires=MAC_DISPATCH_REQUIREMENTS,
            available=False,  # UNVERIFIED (no capture) — D55: refuse until a Mac run confirms
            reason=MAC_DISPATCH_REASON,
        )

    def supervision(self) -> Supervision:
        if not self._on_platform():
            raise UnverifiedHostCapability(MAC_OFF_PLATFORM_REASON)
        return Supervision(
            kind="launchd",  # UNVERIFIED (no capture) — D55
            detail=MAC_SUPERVISION_DETAIL,
            manageable=False,  # UNVERIFIED (no capture) — D55: nothing has been driven yet
            start_limit_note=MAC_START_LIMIT_NOTE,
        )

    def process_liveness(self, pid: int, start_token: str | None) -> Liveness:
        """`ps`-based liveness (D55). The parse below has never been run."""
        if not self._on_platform():
            raise UnverifiedHostCapability(MAC_OFF_PLATFORM_REASON)
        import subprocess  # UNVERIFIED (no capture) — D55: imported only on the Mac path

        observed_at = _now()
        completed = subprocess.run(
            list(mac_liveness_argv(pid)),
            capture_output=True,
            text=True,
            timeout=2.0,  # UNVERIFIED (no capture) — D55
            check=False,
        )
        observed = completed.stdout.strip()
        if completed.returncode != 0 or not observed:  # UNVERIFIED (no capture) — D55
            return Liveness(alive=False, start_token=None, observed_at=observed_at)
        if start_token is not None and observed != start_token:
            return Liveness(alive=False, start_token=observed, observed_at=observed_at)
        return Liveness(alive=True, start_token=observed, observed_at=observed_at)

    def login_persistence(self) -> LoginPersistence:
        if not self._on_platform():
            raise UnverifiedHostCapability(MAC_OFF_PLATFORM_REASON)
        return LoginPersistence(
            enabled=None,  # UNVERIFIED (no capture) — D55: unknown, never guessed as False
            mechanism=MAC_PERSISTENCE_MECHANISM,
            detail=MAC_PERSISTENCE_DETAIL,
        )

    def detached_launch(self) -> DetachedLaunch:
        """The seventh member: **write and annotate**, never refuse (T7).

        Refusing would leave `MacHost` unable to answer a question every spawn
        asks, which is a broken product rather than an honest one. The record
        carries `verified=False`, so the guess is visible at the call site.
        """
        return DetachedLaunch(
            prefix=(),
            mechanism=MAC_DETACH_MECHANISM,
            detail=MAC_DETACH_DETAIL,
            verified=False,  # UNVERIFIED (no capture) — D55: no Mac has run this
        )

    def verified(self) -> bool:
        """No value in this module has a capture behind it (G1, D41)."""
        return False  # UNVERIFIED (no capture) — D55: this is the whole point of the flag
