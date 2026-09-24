"""BC-29 — killing a pane that is gone is a refusal value, and leaves nothing.

**Seam: `invoke("kill_session")`**, the way `web/` reaches it, over a real
`Store` and the shipped `ScriptedRunner`. qa6 O6 killed a session a second time:
`record_and_terminate` wrote `kill.<id>`, `terminate` raised `RunnerRefusal`,
and the page got the generic 400.

**"Gone" is the runner's listing, never `ended_at`.** Every turn end stamps
`ended_at` on a live session and nothing clears it, so a refusal keyed on it
would refuse to kill every session that ever finished a turn. The last test here
is the guard against exactly that discriminator.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.core.fold_types import FoldDelta
from shepherd.core.runner import ProcState, RunnerHandle
from shepherd.core.states import Origin, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.dialog_keys import SidecarState
from shepherd.orchestration.lifecycle import KILL_RECORD_PREFIX
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.tools_m3 import register_m3_tools
from shepherd.toolsurface.tools_terminal import kill_landed
from shepherd.toolsurface.types import Audience, CallerContext

NOW = "2026-09-24T03:58:00.000Z"
TURN_ENDED = "2026-09-24T03:56:00.000Z"
SESSION_ID = "01M38RWEFCX8Y6EJBTFHKQTTP9"
PANE_NAME = f"shepherd_{SESSION_ID}"
HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="web", correlation_id="cid-bc29")
PROC = ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def owned_row(store: Store) -> None:
    """A real owned row with a handle, through the store's own verb."""
    store.create_owned_session(
        session_id=SESSION_ID,
        engine_session_id="11111111-2222-3333-4444-555555555555",
        workspace_id=store.create_project(name="qa6", description=None).id,
        repo_id=None,
        cwd="/tmp",
        started_at=NOW,
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=RunnerHandle(runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=PANE_NAME),
        model=None,
        effort=None,
    )


def registered(store: Store, tmp_path: Path, *, pane_listed: bool) -> ScriptedRunner:
    """M3's set over a runner that does, or does not, still list the pane."""
    panes = (
        (PaneRef(session_name=PANE_NAME, session_id=SESSION_ID, pane_pid=4041880, dead=False),)
        if pane_listed
        else ()
    )
    runner = ScriptedRunner(panes=(), proc=PROC, screen=b"", owned_panes=panes)
    install_test_chokepoint()
    register_m3_tools(
        store=store,
        runner=runner,
        now=lambda: NOW,
        sleep=lambda seconds: None,
        publish=_drop,
        ensure_server=lambda: None,
        engine_config_home=tmp_path / "engine-home",
        run_fork=_no_fork,
        binary="claude",
        projects_root=tmp_path / "projects",
        can_fork=False,
        read_sidecar=lambda engine_session_id: SidecarState.WAITING,
    )
    return runner


def _drop(event: StreamEvent) -> None:
    return None


def _no_fork(argv: list[str], *, timeout_ms: int) -> object:
    raise AssertionError("no test here forks")


def kill_answer() -> dict[str, object]:
    result = invoke("kill_session", {"session_id": SESSION_ID}, HUMAN)
    assert result.ok, (result.error, result.failure)
    assert isinstance(result.data, dict)
    return result.data


def test_killing_a_pane_that_is_gone_is_a_refusal_value(store: Store, tmp_path: Path) -> None:
    """O6's second kill: the row has a handle, tmux has no such session.

    Goes red if the handler reaches `record_and_terminate` for a pane the runner
    does not list: `terminate` raises and `kill.<id>` is left behind.
    """
    owned_row(store)
    runner = registered(store, tmp_path, pane_listed=False)

    answer = kill_answer()

    assert "list_owned_panes" in runner.calls, "arrival: the listing was asked"
    assert answer == {
        "session_id": SESSION_ID,
        "ok": False,
        "killed": False,
        "reason": f"{SESSION_ID}: its pane is gone — nothing to kill",
    }
    assert kill_landed(answer) is False
    assert store.get_app_state(f"{KILL_RECORD_PREFIX}{SESSION_ID}") is None
    assert "terminate" not in runner.calls
    assert "probe" not in runner.calls


def test_a_live_session_that_finished_a_turn_can_still_be_killed(
    store: Store, tmp_path: Path
) -> None:
    """`ended_at` is set by the turn; the pane is listed and alive. Killable.

    Passes before BC-29 as well: it is the guard against the `ended_at`
    discriminator the plan's review rejected.
    """
    owned_row(store)
    store.apply_fold_delta(
        SESSION_ID,
        FoldDelta(state=SessionState.STOPPED, ended_at=TURN_ENDED, last_event_at=TURN_ENDED),
    )
    runner = registered(store, tmp_path, pane_listed=True)

    answer = kill_answer()

    assert answer["killed"] is True
    assert kill_landed(answer) is True
    assert runner.calls.count("terminate") == 1
