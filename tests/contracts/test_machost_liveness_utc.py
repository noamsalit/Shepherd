"""BC-01: `MacHost`'s liveness token is spelled in UTC, as the engine's is.

Claude Code writes `procStart` into its sidecar as `ps -o lstart=` read in UTC
(`docs/probes/2026-09-24-macos-procstart-utc.md`). `ps` spells `lstart` in the
*caller's* timezone, so on a Mac off UTC the product's token and the engine's
differed by the UTC offset and every real session was judged dead. The fix pins
the child `ps`'s `TZ`; these two tests hold it there.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from shepherd.host.mac import MAC_LIVENESS_TZ, MacHost, mac_liveness_env


def test_mac_liveness_env_pins_utc() -> None:
    environ = {"TZ": "Asia/Jerusalem", "HOME": "/Users/someone", "LANG": "en_US.UTF-8"}
    before = dict(environ)

    env = mac_liveness_env(environ)

    assert MAC_LIVENESS_TZ == "UTC"
    assert env == {"TZ": "UTC", "HOME": "/Users/someone", "LANG": "en_US.UTF-8"}
    assert environ == before
    # E2: an environment already on UTC comes back unchanged.
    assert mac_liveness_env({"TZ": "UTC"}) == {"TZ": "UTC"}
    assert mac_liveness_env({}) == {"TZ": "UTC"}


@pytest.mark.skipif(sys.platform != "darwin", reason="real `ps` on macOS only")
def test_liveness_token_is_utc_whatever_the_process_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    # No `time.tzset()`: only the child `ps`'s environment matters, and
    # `monkeypatch` restores `TZ`, so nothing leaks into later tests.
    monkeypatch.setenv("TZ", "Asia/Jerusalem")
    pid = os.getpid()
    oracle = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "TZ": "UTC"},
    ).stdout.strip()

    liveness = MacHost().process_liveness(pid, oracle)

    assert liveness.start_token == oracle
    assert liveness.alive is True
