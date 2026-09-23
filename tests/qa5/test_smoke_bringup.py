"""Bring-up's own arrival test — the gate every wave stands on.

It asserts what env-plan §4 steps 1-11 promise, in one place, so a wave that
goes red is never debugging the fixture. A failure here is `BLOCKED`.
"""

from __future__ import annotations

from .conftest import Harness
from .constants import PANES, QA_SOCKET
from . import tmuxctl


def test_bringup_arrived(harness: Harness) -> None:
    assert harness.started.port != 0
    assert harness.run.root.is_dir()
    assert harness.run.runtime_dir.is_dir()
    assert set(PANES) <= set(tmuxctl.sessions())
    assert harness.client.get("/api/fleet").json()["ok"] is True
    assert len(harness.client.projects()) == 8
    assert harness.rig.a.status == 200 and harness.rig.b.status == 200
    assert harness.audit.mark() > 0, "the production audit sink wrote nothing during the seed"
    harness.report.record(
        "BRINGUP",
        "integration",
        "PASS",
        "eleven bring-up steps arrive: run root, runtime dir, env, store, four panes, "
        "controld bound, /api/fleet 200, seed, chromium, rig live, controls green",
        f"port={harness.started.port}, panes={sorted(set(PANES) & set(tmuxctl.sessions()))}, "
        f"socket={QA_SOCKET}, projects=8",
    )
