"""`MacHost` — D55's second driver, written and **unverified** (T4).

Written at M1 with no capture behind any of it (gap G1): every value below
carries an annotation saying where it came from, and a static test
(`test_machost_constants_are_annotated`) fails the build if a literal ever
appears here without one. Two markers exist and they are not
interchangeable — `UNVERIFIED (no capture)` cites D55 for a value that was
reasoned to, and `VERIFIED (docs/probes/…)` names the capture that measured
it.

**Three of G1's five items closed on 2026-09-20**, on a real Mac (macOS 26.6.2,
arm64): the `sun_path` budget, the netcat flag set, and the `TMPDIR`-derived
runtime dir. Their values are unchanged — D55 guessed them right — but they are
now *measured*, and their annotations say so and name the capture
(`docs/probes/2026-09-20-macos-g1-capture.md`). Every literal in this module
still carries one marker or the other, and
`test_machost_constants_are_annotated` fails the build if one ever does not.

`verified()` still returns False, and that is not a formality: it reports on the
driver, and two of its seven members remain unmeasured — `launchctl print
gui/<uid>`'s output shape, and `ps -o lstart=` / `LOCAL_PEERCRED`. Those still
refuse or answer `None` rather than guessing. Where this module used to refuse
`hook_dispatch()` outright it now probes the host like `LinuxHost` does, because
the flag set it was refusing over has been measured against a real listening
socket.
"""

from __future__ import annotations

import os
import shutil
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


#: `sun_path` is 104 bytes including the NUL, so 103 bind and 104 raise
#: `OSError: AF_UNIX path too long` — measured at every length from 100 to 107
#: on this host. D55's value was right; it is no longer a guess.
MAC_SOCKET_PATH_BUDGET = 103  # VERIFIED (docs/probes/2026-09-20-macos-g1-capture.md §1) — D55
MAC_SOCKET_DIR_MODE = 0o700  # UNVERIFIED (no capture) — D55: same 0700 rule assumed
MAC_SOCKET_MODE = 0o600  # UNVERIFIED (no capture) — D55: same 0600 rule assumed
MAC_APP_DIR_NAME = "Shepherd"  # UNVERIFIED (no capture) — D55: macOS bundle-style directory name
MAC_DATA_PARENT = "Library/Application Support"  # UNVERIFIED (no capture) — D55
MAC_CONFIG_PARENT = "Library/Preferences"  # UNVERIFIED (no capture) — D55
#: `$TMPDIR` is 47 bytes on a real Mac (`/var/folders/<2>/<28>/T/`), so the
#: socket it composes is 69 bytes against the 103-byte budget — it fits, with 34
#: bytes to spare. A host whose `DARWIN_USER_TEMP_DIR` is materially longer is
#: refused by `plan_socket()` before bind, which is the honest failure.
MAC_RUNTIME_ENV = "TMPDIR"  # VERIFIED (docs/probes/2026-09-20-macos-g1-capture.md §3) — D55
MAC_RUNTIME_FALLBACK = "/tmp"  # UNVERIFIED (no capture) — D55: TMPDIR is normally set on macOS
MAC_PLATFORM = "darwin"  # VERIFIED (docs/probes/2026-09-20-macos-g1-capture.md §Host) — D55

#: **There is no `timeout` on a stock Mac.** Neither `timeout` nor `gtimeout`
#: exists (that is `coreutils`, which is a `brew install`), so the Linux
#: command's outer bound has to come from somewhere else — and it cannot simply
#: be dropped: with a `sessiond` that accepts and never reads, a frame larger
#: than `net.local.stream.sendspace` (8192) blocks the writer in `write()`,
#: where no netcat flag reaches it. Measured: unbounded, 30 s and counting.
#:
#: Apple's `nc` is not OpenBSD's. It has **no `-q`**, and its `-N` takes an
#: argument (`--apple-tcp-adp-wtimo`), so `nc -N -U` dies and delivers nothing.
#: `-w 0` is the trap D55 was right to refuse over: it looks like `-q0`, bounds
#: the hung case at 27 ms, delivers small frames 10/10 — and **truncates a 40 KB
#: frame to ~16 KB, 3 runs out of 3**. That is E34's silent-delivery failure one
#: flag to the left, and no assertion about a string can see it.
#:
#: `/usr/bin/perl` is stock, `Time::HiRes` is core (so the bound can be
#: sub-second, where `alarm`'s integer seconds could not), an `alarm` timer
#: survives `execve` (so it bounds `nc`, not perl's start-up), and `exec @ARGV`
#: with a list is `execvp` — no second shell parses the socket path. Measured
#: here: 15.8 ms median, both frame sizes complete 15/15, and 264-324 ms against
#: a peer that never reads. `or exit 0` and the trailing `|| true` keep the
#: hook's exit status 0 whether the exec fails or `SIGALRM` kills `nc`
#: (principle 4, C-1).
MAC_DISPATCH_REQUIREMENTS = (  # VERIFIED (docs/probes/…§2) — D55
    "perl",  # VERIFIED (docs/probes/…§2) — D55: /usr/bin/perl, the stock `timeout`
    "nc",  # VERIFIED (docs/probes/…§2) — D55: /usr/bin/nc, Apple build, no -q
)
MAC_DISPATCH_TIMEOUT_S = "0.25"  # VERIFIED (docs/probes/2026-09-20-macos-g1-capture.md §2)
MAC_DISPATCH_REASON = (  # VERIFIED (docs/probes/…§2) — D55
    "Apple netcat has no -q0 and -w 0 truncates: bounded "  # VERIFIED (docs/probes/…§2)
    "instead by a Time::HiRes alarm through stock "  # VERIFIED (docs/probes/…§2)
    "/usr/bin/perl — measured 15.8 ms per invocation, 40 KB "  # VERIFIED (docs/probes/…§2)
    "complete, 264-324 ms against a wedged sessiond "  # VERIFIED (docs/probes/…§2)
    "(docs/probes/2026-09-20-macos-g1-capture.md §2, G2, E34)"  # VERIFIED (docs/probes/…§2)
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


def mac_dispatch_missing_reason(missing: tuple[str, ...]) -> str:
    """The refusal a host without `perl` or `nc` gets, naming what is absent.

    Same spelling as `LinuxHost`'s, because it is the same fact about a
    different PATH: a binary that does not resolve means no hook is written.
    """
    return f"missing on this host: {', '.join(missing)}"  # VERIFIED (docs/probes/…§2) — D55


def mac_dispatch_command(socket_path: Path) -> str:
    """The one definition site of the macOS hook-side dispatch command (P20).

    `perl` is the bound `timeout` would be on Linux, not a second dispatcher:
    it sets an alarm and `exec`s straight into `nc`, so exactly one process
    writes to the socket and the socket path is never re-parsed by a shell.
    """
    return (  # VERIFIED (docs/probes/…§2) — D55
        f"perl -MTime::HiRes=alarm -e "  # VERIFIED (docs/probes/…§2) — D55
        f"'alarm {MAC_DISPATCH_TIMEOUT_S}; exec @ARGV or exit 0' "  # VERIFIED (docs/probes/…§2)
        f"nc -U {socket_path} || true"  # VERIFIED (docs/probes/…§2) — D55
    )


def _now() -> str:
    return utc_now()


@dataclass(frozen=True)
class MacHost:
    """The macOS driver: written, annotated, and honest about being unverified."""

    # Injected so the pure half of the seam is testable without touching the
    # process environment — and defaulted to the **real** environment, as
    # `LinuxHost` is. Defaulting to `{}` meant `detect_host()` handed back a
    # driver that could not see `HOME` or `TMPDIR` at all: `dirs()` fell through
    # to `Path.home()` and the shared `/tmp`, so every caller on this platform
    # got the same two global paths no matter what environment it was given.
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    uid: int = field(default_factory=os.getuid)

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
        """The sixth seam member — probed, now that the flag set is measured.

        This used to return `available=False` unconditionally: the honest answer
        while G2 was open. It is no longer the honest answer, so the refusal
        moves to where `LinuxHost` keeps it — a binary that does not resolve on
        *this* host, reported by name. A missing `perl` or `nc` still means no
        hook is written, which is the behaviour the gate was protecting.
        """
        missing = tuple(
            name for name in MAC_DISPATCH_REQUIREMENTS if shutil.which(name) is None
        )
        available = missing == ()
        reason = MAC_DISPATCH_REASON if available else mac_dispatch_missing_reason(missing)
        return HookDispatchPlan(
            command=mac_dispatch_command(plan.path),
            requires=MAC_DISPATCH_REQUIREMENTS,
            available=available,
            reason=reason,
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
        """Still False: `launchctl` and `ps`/`LOCAL_PEERCRED` have no capture.

        Three of G1's five items closed on 2026-09-20 (budget, netcat flags,
        runtime dir). This flag reports on the *driver*, not on any one value,
        and two of its seven members are still written rather than measured — so
        raising it would be the guess the flag exists to prevent (D41).
        """
        return False  # UNVERIFIED (no capture) — D55: launchd and ps liveness remain unmeasured
