"""`LinuxHost` — D55's verified driver (T3).

Every value here has a real capture behind it, cited inline. This module and
`host/mac.py` are the only places in the system where `/proc`, `systemctl`,
`loginctl`, `/run/user`, `XDG_` or the hook-side `nc` command line may appear
(D55; `tests/boundaries/test_platform_branching.py`).

Impure by design (env, `/proc`, read-only subprocess probes) and kept thin: the
arithmetic that matters — XDG defaults, the socket path budget — is pure and
lives in `host/base.py` or in a module function here, so the contract suite can
exercise it without a host.
"""

from __future__ import annotations

import os
import shutil
import socket
import struct
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.core.clock import utc_now
from shepherd.host.base import (
    SUPERVISION_KIND_SYSTEMD_USER,
    DetachedLaunch,
    HookDispatchPlan,
    HostDirs,
    Liveness,
    LoginPersistence,
    SocketPlan,
    Supervision,
    SupervisionKind,
    plan_socket,
)

#: E19: `sun_path` holds at most 107 bytes plus NUL — 107 binds, 108 raises
#: `OSError: AF_UNIX path too long` (data-schemas §"Unix domain socket at mode
#: 0600 + SO_PEERCRED", probe capture `socket.txt` §4).
LINUX_SOCKET_PATH_BUDGET = 107

#: §15 l.2219 (`$XDG_RUNTIME_DIR/shepherd/` mode 0700) and §13 l.2044 (both
#: Unix sockets at 0600). E20: the mode must be set by `umask` *before*
#: `bind()` — there is no chmod window — which is the binder's job; the seam
#: only says what the modes are.
SOCKET_DIR_MODE = 0o700
SOCKET_MODE = 0o600

#: The subdirectory Shepherd owns inside each XDG base (spec l.2303–2305).
APP_DIR_NAME = "shepherd"

#: How long a read-only host probe may take before we treat it as absent.
PROBE_TIMEOUT_S = 2.0

#: E34, `docs/probes/2026-09-16-hookd-latency.md` Result 1b: measured 3.2 ms
#: with `-q0` and 253.6 ms without, because without it `nc` never shuts down
#: its write side at stdin EOF — and it still delivers, so the bug is silent.
#: `timeout` bounds a hung `sessiond` (spec l.312); `|| true` keeps the hook's
#: exit status 0 (principle 4, C-1).
DISPATCH_REQUIREMENTS: tuple[str, ...] = ("timeout", "nc")
DISPATCH_TIMEOUT_S = "0.25"

#: DP5/D55, `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/`:
#: a tmux server started **inside** a user unit inherits its cgroup, and under
#: the default `KillMode=control-group` a `systemctl --user` stop leaves
#: `tmux-server 4054473: dead`, `pane-claude 4054474: dead`, `no server running`
#: (`q1-cgstop.txt`; `q1-cgrestart.txt` shows the same for restart). Started
#: through `systemd-run --user --scope` the same stop leaves `tmux-server
#: 4054726: alive(tmux: server)` and `pane-claude 4054727: alive(claude)`
#: (`q1-scopestop.txt`). `--` terminates the wrapper's own options so the
#: wrapped argv is never re-parsed as flags.
DETACHED_LAUNCH_BIN = "systemd-run"
DETACHED_LAUNCH_PREFIX: tuple[str, ...] = (DETACHED_LAUNCH_BIN, "--user", "--scope", "--")
DETACH_MECHANISM = "systemd-run --user --scope"
NO_DETACH_MECHANISM = "none"
NO_DETACH_DETAIL = "no systemd user manager: nothing captures what we launch, so the argv is bare"
UNRESOLVED_DETACH_DETAIL = (
    "a systemd user manager is reachable but systemd-run does not resolve on PATH: "
    "the argv is left bare rather than wrapped in a binary that is not there"
)
DETACH_DETAIL = (
    "wrapped so what we launch leaves this unit's cgroup: q1-cgstop.txt records "
    "tmux-server 4054473: dead under the default KillMode, q1-scopestop.txt records "
    "tmux-server 4054726: alive(tmux: server) through the scope"
)


def peercred(sock: socket.socket) -> int | None:
    """The pid the kernel says is on the other end, or `None` (BLOCKER T10 (c)).

    `SO_PEERCRED` returns `struct ucred {pid_t pid; uid_t uid; gid_t gid;}` —
    three native ints — captured by the kernel at `connect()` time (E21), which
    is what makes it spoof-resistant and also what makes it only a *second*
    opinion: by the time we read it the hook may already have exited, so the
    frame's own `CLAUDE_PID` stays authoritative.

    A socket that has no peer credentials (the wrong family, an unconnected
    socket) is an unknown, not an error: principle 5, and this value is never
    load-bearing at M1.
    """
    try:
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    except OSError:
        return None
    pid, _uid, _gid = struct.unpack("3i", raw)
    return pid if pid > 0 else None


def supervision_probe_argv() -> tuple[str, ...]:
    """The read-only supervision probe. Never a mutating verb (T3 scope)."""
    return ("systemctl", "--user", "is-system-running")


def login_persistence_argv(uid: int) -> tuple[str, ...]:
    """The read-only lingering probe: `show-user`, never a linger flip."""
    return ("loginctl", "show-user", str(uid), "--property=Linger")


def dispatch_command(socket_path: Path) -> str:
    """The one definition site of the Linux hook-side dispatch command (P20)."""
    return f"timeout {DISPATCH_TIMEOUT_S} nc -U -q0 {socket_path} || true"


def start_ticks_from_stat(raw: str) -> str:
    """Field 22 (`starttime`) of `/proc/<pid>/stat` — the pid-reuse guard.

    C13/E31: this equals the live-session registry's `procStart` in 24/24
    captured hook deliveries. `comm` can contain spaces and parentheses, so the
    fields after it are found with `rindex(")")`, never `split()`
    (data-schemas §`/proc/<pid>/stat`).
    """
    after_comm = raw[raw.rindex(")") + 1 :].split()
    return after_comm[19]


def detached_launch_for(kind: SupervisionKind, systemd_run_path: str | None) -> DetachedLaunch:
    """The pure half of the seventh member: kind + resolution → wrapper (DP5).

    Pure so the four combinations are checkable without a live supervision
    experiment. The wrapper is applied for **one** kind and only when the
    binary actually resolves; every other host hands the argv back untouched,
    because a container has no systemd user manager to escape from.
    """
    if kind != SUPERVISION_KIND_SYSTEMD_USER:
        return DetachedLaunch(
            prefix=(),
            mechanism=NO_DETACH_MECHANISM,
            detail=NO_DETACH_DETAIL,
            verified=True,
        )
    if systemd_run_path is None:
        return DetachedLaunch(
            prefix=(),
            mechanism=NO_DETACH_MECHANISM,
            detail=UNRESOLVED_DETACH_DETAIL,
            verified=True,
        )
    return DetachedLaunch(
        prefix=DETACHED_LAUNCH_PREFIX,
        mechanism=DETACH_MECHANISM,
        detail=DETACH_DETAIL,
        verified=True,
    )


def _run(argv: tuple[str, ...]) -> tuple[int, str]:
    """Run a read-only probe as an argv list. No `shell=True`, ever (K5)."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError) as error:
        return 127, str(error)
    except subprocess.TimeoutExpired:
        return 124, f"{argv[0]} timed out after {PROBE_TIMEOUT_S}s"
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def _now() -> str:
    return utc_now()


@dataclass(frozen=True)
class LinuxHost:
    """The Linux driver. `environ` and `uid` are injected so the pure half of
    the seam is testable without touching the process environment."""

    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    uid: int = field(default_factory=os.getuid)

    def _home(self) -> Path:
        home = self.environ.get("HOME")
        return Path(home) if home else Path.home()

    def dirs(self) -> HostDirs:
        """C3/E22/G7: `XDG_DATA_HOME` and `XDG_CONFIG_HOME` are **never set**
        on this host, so the XDG defaults must be applied. `XDG_RUNTIME_DIR`
        *is* set (`/run/user/0`) and has **no default** — it is derived from
        `os.getuid()`, never hard-coded to the uid the probes happened to run
        as (data-schemas §"XDG base directories")."""
        home = self._home()
        data_home = self.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
        config_home = self.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
        runtime = self.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{self.uid}"
        return HostDirs(
            data_dir=Path(data_home) / APP_DIR_NAME,
            config_dir=Path(config_home) / APP_DIR_NAME,
            runtime_dir=Path(runtime) / APP_DIR_NAME,
        )

    def control_socket(self, name: str) -> SocketPlan:
        return plan_socket(
            runtime_dir=self.dirs().runtime_dir,
            name=name,
            dir_mode=SOCKET_DIR_MODE,
            sock_mode=SOCKET_MODE,
            socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
        )

    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan:
        """The sixth seam member (Decision pressure 2).

        `nc` is not guaranteed on a minimal container image, so absence is
        reported rather than written into a hook that silently does nothing.
        """
        missing = [name for name in DISPATCH_REQUIREMENTS if shutil.which(name) is None]
        available = missing == []
        reason = (
            "OpenBSD netcat with -q0: measured 3.2 ms per hook invocation "
            "(docs/probes/2026-09-16-hookd-latency.md Result 1b, E34)"
            if available
            else f"missing on this host: {', '.join(missing)}"
        )
        return HookDispatchPlan(
            command=dispatch_command(plan.path),
            requires=DISPATCH_REQUIREMENTS,
            available=available,
            reason=reason,
        )

    def supervision(self) -> Supervision:
        """Three deployment shapes, not two (D55).

        C3/E23: with `XDG_RUNTIME_DIR` unset, `systemctl --user` fails with
        "Failed to connect to bus: No medium found" and there is **no**
        automatic `/run/user/<uid>` fallback. That is the container shape —
        foreground, restarted by whatever runs the container — not an error.
        """
        start_limit_note = (
            "Restart=always alone ends `failed` after StartLimitBurst=5 restarts in "
            "StartLimitIntervalUSec=10s (C2, E24) — set a start-limit policy explicitly. "
            "The user manager's PATH excludes ~/.local/bin, so a unit calling `claude` "
            "exits 127 (C1) — use an absolute path or set Environment=PATH=."
        )
        if not self.environ.get("XDG_RUNTIME_DIR"):
            return Supervision(
                kind="foreground",
                detail=(
                    "XDG_RUNTIME_DIR is unset: `systemctl --user` cannot reach a bus "
                    "(\"No medium found\", C3/E23) and no fallback exists — run in the "
                    "foreground and let the container runtime restart the process"
                ),
                manageable=False,
                start_limit_note=start_limit_note,
            )
        code, output = _run(supervision_probe_argv())
        if code == 127 or "No medium found" in output:
            return Supervision(
                kind="foreground",
                detail=f"no reachable systemd user manager: {output or 'systemctl absent'}",
                manageable=False,
                start_limit_note=start_limit_note,
            )
        return Supervision(
            kind="systemd_user",
            detail=f"systemctl --user is-system-running: {output or 'unknown'} (rc={code})",
            manageable=True,
            start_limit_note=start_limit_note,
        )

    def detached_launch(self) -> DetachedLaunch:
        """The seventh seam member (DP5): escape this unit's cgroup, or not."""
        return detached_launch_for(
            self.supervision().kind,
            shutil.which(DETACHED_LAUNCH_BIN),
        )

    def process_liveness(self, pid: int, start_token: str | None) -> Liveness:
        """E30/E31: file mtime is not liveness; `(pid, start_token)` is.

        A pid whose field-22 start token differs from the stored one is a
        **different** process, so it is reported dead rather than alive.
        """
        observed_at = _now()
        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except (FileNotFoundError, ProcessLookupError, NotADirectoryError, PermissionError):
            return Liveness(alive=False, start_token=None, observed_at=observed_at)
        try:
            observed_token = start_ticks_from_stat(raw)
        except (ValueError, IndexError):
            return Liveness(alive=False, start_token=None, observed_at=observed_at)
        if start_token is not None and observed_token != start_token:
            return Liveness(alive=False, start_token=observed_token, observed_at=observed_at)
        return Liveness(alive=True, start_token=observed_token, observed_at=observed_at)

    def login_persistence(self) -> LoginPersistence:
        """Read-only: does this user linger? Flipping it is M6's business."""
        mechanism = "systemd user lingering"
        code, output = _run(login_persistence_argv(self.uid))
        if code != 0:
            return LoginPersistence(
                enabled=None,
                mechanism=mechanism,
                detail=f"loginctl unavailable or refused (rc={code}): {output or 'no output'}",
            )
        value = output.rsplit("=", 1)[-1].strip().lower()
        if value not in ("yes", "no"):
            return LoginPersistence(
                enabled=None,
                mechanism=mechanism,
                detail=f"unrecognised Linger value: {output!r}",
            )
        return LoginPersistence(
            enabled=value == "yes",
            mechanism=mechanism,
            detail=f"loginctl reports {output}",
        )

    def verified(self) -> bool:
        """Every value in this module has a capture behind it (T3)."""
        return True
