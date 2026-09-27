"""qa6 rulings P13 — a refused master spawn at level 3 opens no wake turn (§3 D73, D69).

**The seam is the L4 composition**: `compose_tool_surface`, wired as
`daemons/plane.py` wires it, with a scripted runner in place of the one
`LocalRunner` and the shipped plane's counting master factory
(`test_compose_m4.World.built_for`). The sweep the root hands its 2 s loop is
driven directly (`wiring.sweep()`), never by waiting on the timer.

This is the P4 × P6 seam neither phase can test alone (plan finding B5a): P4
ends a refused start's row `refused` and keeps it out of `wake_candidates`; P6
makes level 3 open an unprompted turn for whatever is in that set. Without
P4's exclusion, a refused master spawn would wake the master, which could
spawn again and be refused again — a loop RD-3's lineage cap never sees,
because a fresh spawn declares no `retry_of`.

The positive control is the same wiring with a start that succeeds and is
then killed: one sweep opens exactly one wake turn (PP9), and later sweeps
add nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.mailbox import MailboxCounts
from shepherd.core.runner import RunnerHandle, RunnerRefusal, SessionSpec
from shepherd.core.states import Origin, SessionState
from shepherd.core.stops import StopReason
from shepherd.orchestration import wake
from shepherd.orchestration.master_turn import TurnDriver
from shepherd.store.db import Store
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.toolsurface import compose
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.tools_master import AUTONOMY_LEVEL_KEY
from shepherd.toolsurface.types import Audience, CallerContext

from .test_compose_m4 import ARRIVAL_TIMEOUT_S, World, world  # noqa: F401 — `world` is a fixture
from .test_tools_m3 import PROC, READY_CAPTURE, ready_pane

#: Sweeps after the spawn: more than one, so "however many sweeps" (E-QR-17)
#: is observed rather than assumed from a single pass.
SWEEPS = 3

#: What the scripted runner answers a refused start with.
REFUSAL = "QA6-P13 the runner refused the start"

WAKE_CAP = str(AnomalyKind.WAKE_RETRY_CAP_REACHED.value)

MASTER = CallerContext(audience=Audience.MASTER, caller_id="master", correlation_id="c-p13-m")
HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="you", correlation_id="c-p13-h")


class ServerlessRunner:
    """The scripted runner, wrapped rather than subclassed (§14.2: a `Scripted*`
    is a concrete peer, and `test_scripted_runner_is_not_a_base_class` reads
    `ScriptedRunner.__subclasses__()` process-wide). The driver's own
    `ensure_server` is a no-op so nothing here can start a tmux server
    (`test_controld.py`'s precedent), and `start` refuses when told to; every
    other member is the scripted runner's own."""

    def __init__(self, inner: ScriptedRunner, *, refuse_start: bool) -> None:
        self.inner = inner
        self.refuse_start = refuse_start

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)

    def ensure_server(self) -> None:
        return None

    def start(self, spec: SessionSpec) -> RunnerHandle:
        if self.refuse_start:
            self.inner.calls.append("start")
            raise RunnerRefusal(REFUSAL)
        return self.inner.start(spec)


@dataclass(frozen=True)
class Composed:
    """One composition at level 3, and what the assertions read back."""

    world: World
    wiring: compose.M4Wiring
    runner: ServerlessRunner
    workspace_id: str
    cwd: Path

    @property
    def store(self) -> Store:
        return self.world.store

    def spawn_as_master(self) -> dict[str, object]:
        answered = invoke(
            "spawn_session", {"workspace_id": self.workspace_id, "cwd": str(self.cwd)}, MASTER
        )
        assert answered.ok, (answered.error, answered.failure)
        assert isinstance(answered.data, dict)
        return answered.data

    def sweep(self) -> None:
        assert isinstance(self.wiring.sweep(), MailboxCounts)

    def cap_count(self) -> int:
        return self.store.list_anomaly_counts().get(WAKE_CAP, 0)


def compose_at_level_3(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, refuse_start: bool
) -> Composed:
    runner = ServerlessRunner(
        ScriptedRunner(panes=(ready_pane(),), proc=PROC, screen=READY_CAPTURE),
        refuse_start=refuse_start,
    )
    monkeypatch.setattr(compose, "build_runner", lambda store, host: runner)
    root = tmp_path / "work"
    (root / "repo").mkdir(parents=True)
    project = world.store.create_project(name="shepherd", description=None)
    world.store.add_repo(
        workspace_id=project.id,
        root_path=str(root),
        name="work",
        git_common_dir=str(root / ".git"),
        vcs_remote=None,
    )
    wiring = world.compose()
    world.store.set_app_state(AUTONOMY_LEVEL_KEY, int(AutonomyLevel.LEVEL_3))
    return Composed(world, wiring, runner, project.id, root / "repo")


def the_driver() -> TurnDriver:
    installed = compose.master_plane()
    assert installed is not None, "the composition installed no master plane"
    return installed.driver


def test_a_refused_master_spawn_at_level_3_opens_no_wake_turn(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """C-QR-5 / E-QR-17: the refusal is the spawn call's own result, so a wake
    would tell the master nothing new; however many sweeps run, none opens."""
    composed = compose_at_level_3(world, monkeypatch, tmp_path, refuse_start=True)
    store = composed.store
    driver = the_driver()
    try:
        cap_before = composed.cap_count()
        stamp_before = store.get_app_state(wake.MASTER_LAST_TURN_KEY)

        answered = composed.spawn_as_master()

        assert answered["spawned"] is False, answered
        assert REFUSAL in str(answered["refusal"]), answered
        assert composed.runner.inner.calls.count("start") == 1, "arrival: the start was really asked"
        refused = [row for row in store.list_sessions() if row.stop_reason == StopReason.REFUSED]
        assert len(refused) == 1, store.list_sessions()
        row = refused[0]
        assert row.state is SessionState.STOPPED and row.origin is Origin.ORCHESTRATOR, row

        for _ in range(SWEEPS):
            composed.sweep()

        assert world.built_for == [], "a refused master spawn woke the master"
        assert composed.cap_count() == cap_before
        assert store.get_app_state(wake.MASTER_LAST_TURN_KEY) == stamp_before
        assert wake.peek(store) == (), "the refused row is in the wake set"
    finally:
        driver.close()


def test_a_killed_master_spawn_at_level_3_opens_one_wake_turn(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive control over the same wiring (PP9): a master spawn that
    started and was then killed stops `killed` → `unfinished`, which is in D31's
    wake set, so one sweep opens exactly one turn and the next ones add none."""
    composed = compose_at_level_3(world, monkeypatch, tmp_path, refuse_start=False)
    store = composed.store
    driver = the_driver()
    try:
        answered = composed.spawn_as_master()
        assert answered["spawned"] is True, answered
        session_id = answered["session_id"]
        assert isinstance(session_id, str)

        killed = invoke("kill_session", {"session_id": session_id}, HUMAN)
        assert killed.ok, (killed.error, killed.failure)
        row = store.get_session(session_id)
        assert row is not None and row.stop_reason == StopReason.KILLED, row
        assert world.built_for == [], "arrival: nothing woke before the sweep"

        composed.sweep()
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S), "the wake turn never ended"
        assert len(world.built_for) == 1, "the killed master spawn opened no wake turn"
        assert wake.peek(store) == (), "the wake turn did not drain the set"

        for _ in range(SWEEPS - 1):
            composed.sweep()
            assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
        assert len(world.built_for) == 1, "a drained set woke the master again"
    finally:
        driver.close()
