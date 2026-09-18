"""One scripted host for the daemon suite, so a check relocates every path it
writes by handing in a host (ADR-2) rather than by patching a resolver.

`test_controld.py` has carried its own copy since M1; this is the same shape,
offered as a function so T25's two new files do not make it a third.

**Not a `conftest.py`, and that is not a style choice.** `tests/` has no
`__init__.py`, so every test directory is inserted on `sys.path` under its own
name and a second `conftest` module shadows the first: adding one here made
`tests/e2e/test_live_stop_classification.py`'s `from conftest import
SettingsObservation` resolve to *this* directory's file and the whole run died
at collection. A uniquely named module cannot collide that way.
"""

from __future__ import annotations

from pathlib import Path

from shepherd.host.base import HookDispatchPlan, HostDirs, LoginPersistence, SocketPlan, Supervision
from shepherd.testkit.scripted_host import ScriptedHost

OBSERVED_AT = "2026-09-17T10:00:00Z"


def build_scripted_host(root: Path) -> ScriptedHost:
    """A host whose every answer is a fixture, rooted under `root`."""
    runtime_dir = root / "run"
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=root / "data",
            config_dir=root / "config",
            runtime_dir=runtime_dir,
        ),
        socket_plan=SocketPlan(
            path=runtime_dir / "sessiond.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(
            command=f"scripted-send {runtime_dir / 'sessiond.sock'}",
            requires=("scripted-send",),
            available=True,
            reason="scripted fixture",
        ),
        supervision_plan=Supervision(
            kind="foreground",
            detail="no supervisor on this host",
            manageable=False,
            start_limit_note="five restarts in ten seconds then the unit is refused",
        ),
        login=LoginPersistence(
            enabled=None,
            mechanism="none observed",
            detail="no persistence mechanism could be read on this host",
        ),
        observed_at=OBSERVED_AT,
    )
