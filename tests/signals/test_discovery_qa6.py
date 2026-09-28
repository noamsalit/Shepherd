"""qa6 P4 — the idle crossing, one fallback fork, a steady count, and `project_id`.

Four defects in the hookless discovery lane, each pinned at the lowest seam that
exercises it (`docs/plans/2026-09-24-qa6-bugfix-plan.md` §P4):

* BC-04 — RD8's early return ran before the idle age check, so an idle
  session first seen younger than 60 s never became `needs_you` while its
  stamp stayed unchanged. Pure seam: `registry_delta`.
* BC-17 — with no `sessions/` directory, every 2 s pass forked
  `claude agents --json`, against the registry's own "once, never on a timer".
* BC-27 — one persistent malformed sidecar bumped `malformed_payload` on every
  pass, an unbounded counter for one file.
* BC-34 — `session.state` frames carried no `project_id`, so §12's envelope
  said `null` for a session bound to a project.

The two loop tests count passes through the loop's `sweep` callable, which runs
once per pass whether or not anything was discovered, and that callable sets
`shutdown` itself: the loop stops on its own, with no sleep in the test.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.fold_types import FoldResult, SessionSnapshot
from shepherd.core.mailbox import MailboxCounts
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code import registry as registry_module
from shepherd.engines.claude_code.registry import (
    IDLE_REASON,
    SESSIONS_DIRNAME,
    RegistryEntry,
    parse_sidecar,
)
from shepherd.host.base import HookDispatchPlan, HostDirs, Liveness, LoginPersistence
from shepherd.host.base import SocketPlan, Supervision
from shepherd.signals import discovery_loop as discovery_loop_module
from shepherd.signals.discovery_loop import (
    IDLE_TO_NEEDS_YOU_S,
    discovery_pass,
    iso_from_epoch_ms,
    registry_delta,
    run_discovery_loop,
)
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface.stream import StreamDelivery
from shepherd.web.sse import envelope

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURES = REPO_ROOT / "docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z"
IDLE = CAPTURES / "04-sidecar-idle.json"
RUNNING = CAPTURES / "07-sidecar-running.json"

PID = 4041880
PROC_START = "543824210"
SESSION_ID = "71757dd1-5375-4801-b467-7898a0bc1194"
OBSERVED = "2026-09-16T12:00:00Z"
MALFORMED_COUNTER = f"anomaly.{AnomalyKind.MALFORMED_PAYLOAD.value}"
FAST_INTERVAL_S = 0.01


def captured(path: Path) -> RegistryEntry:
    parsed = parse_sidecar(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, RegistryEntry)
    return parsed


def alive() -> Liveness:
    return Liveness(alive=True, start_token=PROC_START, observed_at=OBSERVED)


def stamp_plus(entry: RegistryEntry, seconds: float) -> str:
    return iso_from_epoch_ms(entry.status_updated_at_ms + int(seconds * 1000))


def running_prior(observed_at: str) -> SessionSnapshot:
    return SessionSnapshot(
        session_id="01SESSION",
        engine_session_id=SESSION_ID,
        state=SessionState.RUNNING,
        last_event_at=observed_at,
        observed_at=observed_at,
        needs_you_reason=None,
        brief=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        repo_id=None,
        model=None,
        tasks_total=0,
        tasks_done=0,
        active_subagents=0,
        repos_touched=(),
        live_subagent_ids=frozenset(),
        created_task_ids=frozenset(),
        completed_task_ids=frozenset(),
        title=None,
        title_source="brief",
        pid=PID,
        proc_start=PROC_START,
        ended_at=None,
        auto_compact_at=None,
        quota_notice_at=None,
    )


def scripted(config_dir: Path, liveness: dict[int, Liveness]) -> ScriptedHost:
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=config_dir / "data",
            config_dir=config_dir,
            runtime_dir=config_dir / "run",
        ),
        socket_plan=SocketPlan(
            path=config_dir / "run" / "x.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(command="true", requires=(), available=True, reason=""),
        supervision_plan=Supervision(
            kind="foreground", detail="", manageable=False, start_limit_note=""
        ),
        login=LoginPersistence(enabled=None, mechanism="none", detail=""),
        liveness_by_pid=liveness,
        observed_at=OBSERVED,
    )


def scripted_sweep(
    shutdown: threading.Event, steps: list[Callable[[], None]]
) -> Callable[[], MailboxCounts]:
    """A `sweep` that runs one scripted step per pass and stops the loop after the last."""
    remaining = list(steps)

    def sweep() -> MailboxCounts:
        remaining.pop(0)()
        if not remaining:
            shutdown.set()
        return MailboxCounts(pending=0, delivered=0, deferred=0)

    return sweep


@pytest.fixture(autouse=True)
def never_the_real_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even a call that forgets `engine_config_dir` never reaches the user's `~/.claude`."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-such-config"))


@pytest.fixture()
def fast_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_loop_module, "REGISTRY_SCAN_INTERVAL_S", FAST_INTERVAL_S)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "state" / "shepherd.db")
    yield opened
    opened.close()


# ----- BC-04: the idle crossing on an unchanged stamp (pure seam) ------------


def test_an_idle_session_crosses_to_needs_you_on_an_unchanged_stamp() -> None:
    idle = captured(IDLE)
    unchanged = iso_from_epoch_ms(idle.status_updated_at_ms)

    result = registry_delta(
        idle, alive(), running_prior(unchanged), stamp_plus(idle, IDLE_TO_NEEDS_YOU_S + 1)
    )

    assert result.delta.state is SessionState.NEEDS_YOU
    assert result.delta.needs_you_reason == IDLE_REASON
    assert result.delta.observed_at == unchanged
    assert [event.payload["state"] for event in result.events] == ["needs_you"]


def test_a_newer_hook_observation_still_wins_over_the_idle_crossing() -> None:
    idle = captured(IDLE)
    newer = stamp_plus(idle, 5.0)

    result = registry_delta(
        idle, alive(), running_prior(newer), stamp_plus(idle, IDLE_TO_NEEDS_YOU_S + 1)
    )

    assert result.delta.state is None
    assert result.delta.needs_you_reason is None
    assert result.events == ()


# ----- BC-17: the agents fallback forks at most once per loop -----------------


def test_the_agents_fallback_is_consulted_once_per_loop(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_loop: None
) -> None:
    config_dir = tmp_path / "claude"
    config_dir.mkdir()
    forks: list[None] = []

    def counting_fallback() -> tuple[list[RegistryEntry], tuple[Anomaly, ...]]:
        forks.append(None)
        return [], ()

    monkeypatch.setattr(registry_module, "agents_json_fallback", counting_fallback)
    shutdown = threading.Event()
    sweep = scripted_sweep(shutdown, [lambda: None] * 3)

    run_discovery_loop(store, scripted(config_dir, {}), lambda r: None, shutdown, config_dir, sweep)

    assert len(forks) == 1


# ----- BC-27: one bad sidecar is counted once while it persists --------------


def test_one_bad_sidecar_is_counted_once_while_it_persists(
    store: Store, tmp_path: Path, fast_loop: None
) -> None:
    config_dir = tmp_path / "claude"
    sidecar = config_dir / SESSIONS_DIRNAME / f"{PID}.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("{truncated", encoding="utf-8")
    counts: list[object] = []

    def record() -> None:
        counts.append(store.get_app_state(MALFORMED_COUNTER))

    def heal() -> None:
        record()
        sidecar.write_text(RUNNING.read_text(encoding="utf-8"), encoding="utf-8")

    def break_again() -> None:
        sidecar.write_text("{truncated", encoding="utf-8")

    shutdown = threading.Event()
    sweep = scripted_sweep(shutdown, [lambda: None, lambda: None, heal, break_again, record])
    host = scripted(config_dir, {PID: alive()})

    run_discovery_loop(store, host, lambda r: None, shutdown, config_dir, sweep)

    assert counts == [1, 2], "three passes over one bad file count once; a re-break counts again"


# ----- BC-34: session.state frames carry the project the row is bound to ------


def test_session_state_frames_carry_the_project_id(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    sidecar = config_dir / SESSIONS_DIRNAME / f"{PID}.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(RUNNING.read_text(encoding="utf-8"), encoding="utf-8")
    project = store.create_project(name="bound", description=None)
    store.register_session(
        engine_session_id=SESSION_ID,
        workspace_id=project.id,
        repo_id=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        started_at=OBSERVED,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    seen: list[FoldResult] = []

    discovery_pass(store, scripted(config_dir, {PID: alive()}), seen.append, OBSERVED, config_dir)

    events: list[StreamEvent] = [event for result in seen for event in result.events]
    assert [event.payload.get("project_id") for event in events] == [project.id]
    body = envelope(StreamDelivery(seq=1, event=events[0]))
    assert body["project_id"] == project.id
    assert body["data"] == {"state": "running", "source": "registry"}
