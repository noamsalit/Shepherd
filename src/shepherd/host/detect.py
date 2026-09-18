"""Runtime platform detection — D55, amended 2026-09-16.

D55 makes the platform a **runtime** swap: one build starts on Linux *and* on
macOS and chooses its driver by detection, rather than being compiled for one.
This is the only module that answers "which driver"; everything else takes a
`HostPlatform` and never asks.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Callable

from shepherd.host.base import HostPlatform
from shepherd.host.linux import LinuxHost, peercred as linux_peercred
from shepherd.host.mac import MacHost, peercred as mac_peercred


def detect_host() -> HostPlatform:
    """The driver for the platform this process is running on.

    A Linux container with no systemd is still `LinuxHost`: the third
    deployment shape is expressed by `supervision()` returning `foreground`
    (D55), not by a third driver.
    """
    if sys.platform == "darwin":
        return MacHost()
    return LinuxHost()


def detect_peercred() -> Callable[[socket.socket], int | None]:
    """The peer-credential reader for this platform (BLOCKER T10, option (c)).

    Not a seventh `HostPlatform` member: D55 fixes the seam at six and Decision
    pressure 2 already spent the sixth on `hook_dispatch`. It is a module
    function per platform, chosen here — the one module that answers "which
    driver" — so the composition root injects a callable and never names a
    socket option. On macOS there is no capture for `LOCAL_PEERCRED` (G1), so
    the reader answers `None`: an unknown, never a guessed pid.
    """
    return mac_peercred if sys.platform == "darwin" else linux_peercred
