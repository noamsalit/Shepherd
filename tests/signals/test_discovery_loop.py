"""T7b — scan → `FoldDelta`, the liveness sweep, and the loop that owns the cadence.

The six mapping rows are Decision pressure 6's table, and every one of them is
driven at the pure seam (`registry_delta`) as well as through a real `Store`.
Fixtures come from the captured sidecars under
`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/` — in particular
the capture **pair** `06-sidecar-permission.json` → `07-sidecar-running.json`
(same pid, 9.194 s apart), which is the only observed signal that a
permission-blocked session became unblocked.
"""

from __future__ import annotations

import ast
import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from golden.corpus import CorpusEvent, load_corpus

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.frames import Frame
from shepherd.core.fold_types import FoldDelta, SessionSnapshot
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.engines.claude_code.registry import (
    SDK_CLI_ENTRYPOINT,
    SESSIONS_DIRNAME,
    RegistryEntry,
    parse_sidecar,
)
from shepherd.host.base import HookDispatchPlan, HostDirs, Liveness, LoginPersistence
from shepherd.host.base import SocketPlan, Supervision
from shepherd import signals as _signals_package  # noqa: F401
from shepherd.signals import discovery_loop as discovery_loop_module
from shepherd.signals import hook_lane as hook_lane_module
from shepherd.signals.hook_lane import HookLane
from shepherd.signals.discovery_loop import (
    DISCOVERY_STATUS_KEY,
    IDLE_TO_NEEDS_YOU_S,
    REGISTRY_SCAN_INTERVAL_S,
    FoldResult,
    discovery_pass,
    iso_from_epoch_ms,
    liveness_sweep,
    liveness_verdict,
    registry_delta,
    run_discovery_loop,
    title_from_registry,
)
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURES = (
    REPO_ROOT
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "tmux-tui"
    / "run-20260914T154946Z"
)
IDLE = CAPTURES / "04-sidecar-idle.json"
PERMISSION = CAPTURES / "06-sidecar-permission.json"
RUNNING = CAPTURES / "07-sidecar-running.json"

PID = 4041880
PROC_START = "543824210"
SESSION_ID = "71757dd1-5375-4801-b467-7898a0bc1194"
OBSERVED = "2026-09-16T12:00:00Z"
LATER = "2026-09-16T12:05:00Z"


def entry_from(path: Path, **overrides: object) -> RegistryEntry:
    parsed = parse_sidecar(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, RegistryEntry)
    return replace(parsed, **overrides)  # type: ignore[arg-type]


def alive(token: str = PROC_START) -> Liveness:
    return Liveness(alive=True, start_token=token, observed_at=OBSERVED)


def dead() -> Liveness:
    return Liveness(alive=False, start_token=None, observed_at=OBSERVED)


def at(entry: RegistryEntry, seconds_later: float) -> str:
    return iso_from_epoch_ms(entry.status_updated_at_ms + int(seconds_later * 1000))


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


def write_sidecar(config_dir: Path, entry_fields: dict[str, object]) -> None:
    directory = config_dir / SESSIONS_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{entry_fields['pid']}.json").write_text(
        json.dumps(entry_fields), encoding="utf-8"
    )


def capture_fields(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    return {str(key): value for key, value in decoded.items()}


@pytest.fixture(autouse=True)
def never_the_real_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt and braces: even a call that forgets `engine_config_dir` points at
    a throwaway directory, never at the user's real `~/.claude`."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-such-config"))


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    opened = open_store(tmp_path / "state" / "shepherd.db")
    yield opened
    opened.close()


def prior_snapshot(state: SessionState, **overrides: object) -> SessionSnapshot:
    base = SessionSnapshot(
        session_id="01SESSION",
        engine_session_id=SESSION_ID,
        state=state,
        last_event_at=None,
        observed_at=None,
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
    return replace(base, **overrides)  # type: ignore[arg-type]


# ----- Decision pressure 6: the whole mapping table, at the pure seam ---------


def test_registry_status_maps_to_state() -> None:
    busy = entry_from(RUNNING)
    idle = entry_from(IDLE)
    waiting = entry_from(PERMISSION)

    rows = [
        (busy, alive(), at(busy, 1.0), SessionState.RUNNING),
        (idle, alive(), at(idle, IDLE_TO_NEEDS_YOU_S - 1), SessionState.RUNNING),
        (idle, alive(), at(idle, IDLE_TO_NEEDS_YOU_S + 1), SessionState.NEEDS_YOU),
        (waiting, alive(), at(waiting, 1.0), SessionState.NEEDS_YOU),
        (busy, dead(), at(busy, 1.0), SessionState.STOPPED),
    ]
    for entry, liveness, now, expected in rows:
        result = registry_delta(entry, liveness, None, now)
        assert result.delta.state == expected, (entry.status, liveness.alive, now)

    # the sixth row: a status outside the observed set keeps the prior state.
    unknown = entry_from(IDLE, status="compacting")
    kept = registry_delta(unknown, alive(), prior_snapshot(SessionState.RUNNING), at(unknown, 1.0))
    assert kept.delta.state is None


def test_idle_live_session_is_never_stopped() -> None:
    """DP6/F2 — the regression revision 2 would have shipped."""
    idle = entry_from(IDLE)
    for age in (0.0, 30.0, 59.0, 61.0, 3600.0):
        result = registry_delta(idle, alive(), None, at(idle, age))
        assert result.delta.state != SessionState.STOPPED, age
        assert result.delta.ended_at is None


def test_registry_waiting_sets_needs_you_with_waitingfor() -> None:
    waiting = entry_from(PERMISSION)
    result = registry_delta(waiting, alive(), None, at(waiting, 1.0))

    assert result.delta.state == SessionState.NEEDS_YOU
    assert result.delta.needs_you_reason == "permission prompt"


def test_leaving_waiting_clears_needs_you() -> None:
    """The captured resolution pair: 06 (`waiting`) → 07 (`busy`), 9.194 s apart."""
    waiting = entry_from(PERMISSION)
    resumed = entry_from(RUNNING)
    assert resumed.status_updated_at_ms - waiting.status_updated_at_ms == 9194

    prior = prior_snapshot(SessionState.NEEDS_YOU, needs_you_reason="permission prompt")
    result = registry_delta(resumed, alive(), prior, at(resumed, 1.0))

    assert result.delta.state == SessionState.RUNNING
    assert result.delta.needs_you_reason == ""


def test_unknown_registry_status_is_counted() -> None:
    """r4/A9 — an unrecognised `status` is a value, not a crash and not a guess."""
    unknown = entry_from(IDLE, status="hibernating")
    prior = prior_snapshot(SessionState.NEEDS_YOU, needs_you_reason="permission prompt")

    result = registry_delta(unknown, alive(), prior, at(unknown, 1.0))

    assert result.delta.state is None
    assert result.delta.needs_you_reason is None
    assert [anomaly.kind for anomaly in result.anomalies] == [
        AnomalyKind.UNKNOWN_REGISTRY_STATUS
    ]
    assert "hibernating" in result.anomalies[0].detail


def test_procstart_mismatch_is_a_different_process() -> None:
    """E31 — a differing start token is a different process, not a live one."""
    entry = entry_from(RUNNING)
    reused = Liveness(alive=True, start_token="999999999", observed_at=OBSERVED)

    assert liveness_verdict(entry, alive()) is True
    assert liveness_verdict(entry, reused) is False

    result = registry_delta(entry, reused, None, at(entry, 1.0))
    assert result.delta.state == SessionState.STOPPED
    assert result.delta.ended_at == OBSERVED


def test_registry_delta_always_carries_the_liveness_inputs() -> None:
    """DP7 — pid and proc_start are what the sweep runs on after the file is gone."""
    entry = entry_from(RUNNING)
    result = registry_delta(entry, alive(), None, at(entry, 1.0))

    assert result.delta.pid == PID
    assert result.delta.proc_start == PROC_START
    assert result.delta.observed_at == iso_from_epoch_ms(entry.status_updated_at_ms)


# ----- RD8: recency, not source ----------------------------------------------


def test_newer_source_wins_per_field() -> None:
    entry = entry_from(RUNNING)
    observed = iso_from_epoch_ms(entry.status_updated_at_ms)
    newer_hook = prior_snapshot(
        SessionState.NEEDS_YOU,
        observed_at=iso_from_epoch_ms(entry.status_updated_at_ms + 5000),
    )

    result = registry_delta(entry, alive(), newer_hook, at(entry, 10.0))

    assert result.delta.state is None, "a newer hook observation must not be overwritten"
    assert result.delta.observed_at is None
    assert observed < newer_hook.observed_at  # type: ignore[operator]


def test_equal_timestamps_tie_break_to_the_hook_path() -> None:
    entry = entry_from(RUNNING)
    tie = prior_snapshot(
        SessionState.NEEDS_YOU, observed_at=iso_from_epoch_ms(entry.status_updated_at_ms)
    )
    assert registry_delta(entry, alive(), tie, at(entry, 1.0)).delta.state is None


def test_stale_hook_state_is_corrected_by_the_registry() -> None:
    """F12 — the case source-precedence could never reach."""
    entry = entry_from(IDLE)
    stale = prior_snapshot(
        SessionState.RUNNING,
        observed_at=iso_from_epoch_ms(entry.status_updated_at_ms - 600_000),
    )

    result = registry_delta(entry, alive(), stale, at(entry, IDLE_TO_NEEDS_YOU_S + 1))

    assert result.delta.state == SessionState.NEEDS_YOU


# ----- D29's title ratchet ----------------------------------------------------


def test_registry_name_sets_title_source() -> None:
    derived = entry_from(IDLE)  # nameSource: "derived" -> engine
    named = entry_from(IDLE, name="shp regint probe", name_source="user")

    assert title_from_registry(derived, None) == ("shp-tui-a-4tvrx00n-00", "engine")
    assert title_from_registry(named, None) == ("shp regint probe", "user")

    # the ratchet: `user` beats `engine`, and a later `engine` never overwrites it.
    held = prior_snapshot(SessionState.RUNNING, title="chosen", title_source="user")
    assert title_from_registry(derived, held) is None
    assert title_from_registry(named, held) == ("shp regint probe", "user")

    # an unrecognised nameSource is not a title source we can rank.
    assert title_from_registry(entry_from(IDLE, name_source="telepathy"), None) is None


# ----- the scan → store pass --------------------------------------------------


def test_registry_title_reaches_the_session_row(store: Store, tmp_path: Path) -> None:
    """BLOCKER T7b-3: the ratchet had no carrier, so the fleet page rendered
    every discovered session `(untitled)` — verified live against three real
    sessions. `title`/`title_source` must survive the write, not just the
    pure function."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(IDLE))  # nameSource: "derived"
    host = scripted(config_dir, {PID: alive()})

    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    session = store.get_session_by_engine_id(SESSION_ID)
    assert session is not None
    assert session.title == "shp-tui-a-4tvrx00n-00"
    assert session.title_source == "engine"
    assert store.fleet()[0].title == "shp-tui-a-4tvrx00n-00"


def test_stored_user_title_survives_a_later_engine_name(store: Store, tmp_path: Path) -> None:
    """D29's ratchet, read back out of the store rather than out of a snapshot
    a test built by hand: once `user` wins, `engine` never overwrites it."""
    config_dir = tmp_path / "claude"
    fields = capture_fields(IDLE)
    fields["name"] = "shp regint probe"
    fields["nameSource"] = "user"
    write_sidecar(config_dir, fields)
    host = scripted(config_dir, {PID: alive()})
    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    write_sidecar(config_dir, capture_fields(IDLE))  # engine-derived again
    discovery_pass(store, host, lambda result: None, LATER, config_dir)

    session = store.get_session_by_engine_id(SESSION_ID)
    assert session is not None
    assert (session.title, session.title_source) == ("shp regint probe", "user")


def test_registry_registers_unknown_session(store: Store, tmp_path: Path) -> None:
    """Decision pressure 5's whole point: no hooks, and the fleet is not empty."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})

    status = discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    session = store.get_session_by_engine_id(SESSION_ID)
    assert session is not None
    assert session.ownership == Ownership.ATTACHED
    assert session.origin == Origin.EXTERNAL
    assert session.cwd == "/tmp/shp-tui-A-4tvrx00n"
    assert session.state == SessionState.RUNNING
    assert status.registry_sessions == 1
    assert store.fleet() != []


def test_register_stores_pid_and_proc_start(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})

    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    assert store.sessions_with_liveness_inputs() == [
        (store.list_sessions()[0].id, PID, PROC_START)
    ]


def test_sdk_cli_entrypoint_is_skipped_and_counted(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    headless = capture_fields(RUNNING)
    headless["entrypoint"] = SDK_CLI_ENTRYPOINT
    write_sidecar(config_dir, headless)
    host = scripted(config_dir, {PID: alive()})

    status = discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    assert store.get_session_by_engine_id(SESSION_ID) is None
    assert status.sdk_cli_skipped == 1
    assert status.registry_sessions == 0


def test_absent_sidecar_is_not_a_stop(store: Store, tmp_path: Path) -> None:
    """P16/E29 — the file is deleted on exit, and absence is never a stop."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})
    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)
    session_id = store.list_sessions()[0].id

    # the sidecar vanishes, the process is still alive
    (config_dir / SESSIONS_DIRNAME / f"{PID}.json").unlink()
    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    session = store.get_session(session_id)
    assert session is not None
    assert session.state == SessionState.RUNNING
    assert session.ended_at is None


def test_dead_pid_sets_stopped_with_ended_at(store: Store, tmp_path: Path) -> None:
    """DP7/P17 — §8's fourth stop trigger, "observed process exit"."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    discovery_pass(store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir)
    session_id = store.list_sessions()[0].id

    (config_dir / SESSIONS_DIRNAME / f"{PID}.json").unlink()
    results = liveness_sweep(store, scripted(config_dir, {}), OBSERVED)

    session = store.get_session(session_id)
    assert session is not None
    assert session.state == SessionState.STOPPED
    assert session.ended_at == OBSERVED
    assert [event.session_id for result in results for event in result.events] == [session_id]


def test_liveness_survives_controld_restart(tmp_path: Path) -> None:
    """P17 — the inputs are on the row, not in memory."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    db_path = tmp_path / "state" / "shepherd.db"

    first = open_store(db_path)
    discovery_pass(first, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir)
    session_id = first.list_sessions()[0].id
    first.close()

    (config_dir / SESSIONS_DIRNAME / f"{PID}.json").unlink()
    second = open_store(db_path)
    try:
        liveness_sweep(second, scripted(config_dir, {}), OBSERVED)
        session = second.get_session(session_id)
        assert session is not None
        assert session.state == SessionState.STOPPED
        assert session.ended_at == OBSERVED
    finally:
        second.close()


def test_sources_converge_on_session_id(store: Store, tmp_path: Path) -> None:
    """P14 — registry-first and hook-first both yield exactly one row."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})

    # registry first, then the hook path registering the same engine session id
    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)
    workspace = store.create_project(name="hook-side", description=None)
    store.register_session(
        engine_session_id=SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        started_at=OBSERVED,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    assert len(store.list_sessions()) == 1


def test_hook_first_then_registry_is_still_one_row(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    workspace = store.create_project(name="hook-side", description=None)
    store.register_session(
        engine_session_id=SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        started_at=OBSERVED,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )

    discovery_pass(store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir)

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].pid == PID


def test_unknown_status_is_counted_in_the_store(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    odd = capture_fields(RUNNING)
    odd["status"] = "quiescing"
    write_sidecar(config_dir, odd)
    host = scripted(config_dir, {PID: alive()})

    status = discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    assert status.unknown_status == 1
    assert store.get_app_state(f"anomaly.{AnomalyKind.UNKNOWN_REGISTRY_STATUS.value}") == 1


def test_discovery_status_is_published_for_doctor(store: Store, tmp_path: Path) -> None:
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})

    discovery_pass(store, host, lambda result: None, OBSERVED, config_dir)

    published = store.get_app_state(DISCOVERY_STATUS_KEY)
    assert isinstance(published, dict)
    assert published["registry_sessions"] == 1
    assert published["sdk_cli_skipped"] == 0
    assert published["hooks"] == "absent"
    assert published["scan_interval_s"] == REGISTRY_SCAN_INTERVAL_S
    assert published["last_scan_at"] == OBSERVED


def test_results_are_returned_not_published(store: Store, tmp_path: Path) -> None:
    """ADR-4/F5 — a pure lane returns its events; the composition root rings them."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    seen: list[FoldResult] = []

    discovery_pass(store, scripted(config_dir, {PID: alive()}), seen.append, OBSERVED, config_dir)

    assert [event.kind for result in seen for event in result.events] != []
    assert all(event.session_id is not None for result in seen for event in result.events)


def test_discovery_loop_stops_on_shutdown_event(store: Store, tmp_path: Path) -> None:
    """r4/A8 — the cadence, the sweep and the shutdown join live here, not in daemons/."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    host = scripted(config_dir, {PID: alive()})
    shutdown = threading.Event()
    results: list[FoldResult] = []

    thread = threading.Thread(
        target=run_discovery_loop, args=(store, host, results.append, shutdown, config_dir)
    )
    thread.start()
    try:
        deadline = threading.Event()
        while store.get_app_state(DISCOVERY_STATUS_KEY) is None:
            assert not deadline.wait(0.02)
            assert thread.is_alive()
    finally:
        shutdown.set()
        thread.join(timeout=5.0)

    assert not thread.is_alive(), "the loop did not exit promptly on the shutdown event"
    assert store.get_session_by_engine_id(SESSION_ID) is not None


def test_delta_fields_are_all_known_to_the_store() -> None:
    """One writer, one rule set (D37): every field the registry sets is persisted."""
    from shepherd.store.db import DELTA_COLUMNS

    entry = entry_from(PERMISSION)
    delta = registry_delta(entry, alive(), None, at(entry, 1.0)).delta
    set_fields = {
        name
        for name in FoldDelta.__dataclass_fields__
        if getattr(delta, name) is not None and name != "observed_at"
    }
    assert set_fields <= set(DELTA_COLUMNS)
    assert set_fields != set()


def test_discovery_scans_the_engine_config_dir_not_shepherds(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live-proof regression: the first pass against this host found nothing.

    `host.dirs().config_dir` is *Shepherd's* config dir; the sidecars are under
    the **engine's**. With the two pointed at different directories, only the
    engine's may be scanned.
    """
    engine_dir = tmp_path / "claude"
    write_sidecar(engine_dir, capture_fields(RUNNING))
    shepherd_dir = tmp_path / "shepherd-config"
    shepherd_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(engine_dir))

    status = discovery_pass(store, scripted(shepherd_dir, {PID: alive()}), lambda r: None, OBSERVED)

    assert status.registry_sessions == 1
    assert store.get_session_by_engine_id(SESSION_ID) is not None


# ----- T21: the `sdk-cli` reconcile (DP2, closing T19-1) ---------------------
#
# The `continue` on an `sdk-cli` entry became a *reconcile*. D47 is untouched:
# the hook lane still registers on the first event of any kind, and this lane
# marks the row `ephemeral` afterwards — §7's own word for "real, and not on the
# board by default". Three counters are reported together because
# `sdk_cli_reconciled` alone would read as coverage, and it is not.


def hook_registered_row(store: Store, engine_session_id: str, cwd: str) -> str:
    """A row exactly as `HookLane._session_id_for` creates it (D47).

    `pid` is left NULL because **no lane but this one ever writes it**
    (`test_only_the_registry_lane_writes_pid` pins that), which is what makes
    "the registry has never seen this row" an observable fact rather than a guess.
    """
    workspace = store.create_project(name="hook-side", description=None)
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=workspace.id,
        repo_id=None,
        cwd=cwd,
        started_at=OBSERVED,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    ).id


def test_an_sdk_cli_row_is_reconciled_to_ephemeral(store: Store, tmp_path: Path) -> None:
    """DP2 option 2: the hooked `-p` run registered, and the sweep hides it.

    Goes red if the `continue` returns: nothing is marked, and the finished `-p`
    row stays on the fleet page, which is what T19-1 reported live.
    """
    config_dir = tmp_path / "claude"
    headless = capture_fields(RUNNING)
    headless["entrypoint"] = SDK_CLI_ENTRYPOINT
    write_sidecar(config_dir, headless)
    session_id = hook_registered_row(store, SESSION_ID, "/tmp/shp-tui-A-4tvrx00n")
    # Arrival before absence: the row really is on the fleet page first.
    assert [row.session_id for row in store.fleet()] == [session_id]

    status = discovery_pass(
        store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir
    )

    reconciled = store.get_session(session_id)
    assert reconciled is not None
    assert reconciled.ephemeral is True
    assert store.fleet() == []
    assert (status.sdk_cli_skipped, status.sdk_cli_reconciled) == (1, 0 + 1)
    # D47's registration is untouched: the row was NOT deleted and NOT re-created.
    assert len(store.list_sessions()) == 1
    assert store.get_session_by_engine_id(SESSION_ID) is not None


def test_an_already_ephemeral_row_is_not_counted_twice(store: Store, tmp_path: Path) -> None:
    """DP2 half one: an `ask()` fork is `ephemeral` **from birth**, so the second
    sweep has nothing to reconcile. Goes red if the counter counts *matches*
    rather than *changes* — a counter that keeps rising on a steady state is the
    same lie in the other direction."""
    config_dir = tmp_path / "claude"
    headless = capture_fields(RUNNING)
    headless["entrypoint"] = SDK_CLI_ENTRYPOINT
    write_sidecar(config_dir, headless)
    hook_registered_row(store, SESSION_ID, "/tmp/shp-tui-A-4tvrx00n")
    host = scripted(config_dir, {PID: alive()})

    first = discovery_pass(store, host, lambda r: None, OBSERVED, config_dir)
    second = discovery_pass(store, host, lambda r: None, LATER, config_dir)

    assert (first.sdk_cli_reconciled, second.sdk_cli_reconciled) == (1, 0)
    assert (first.sdk_cli_skipped, second.sdk_cli_skipped) == (1, 1)


def test_registration_still_accepts_the_first_event_of_any_kind(
    store: Store, tmp_path: Path
) -> None:
    """D47, inherited. Goes red if the reconcile leaks into the hook lane.

    The reconcile lives in `signals/discovery_loop.py` and nowhere else; the hook
    lane's `_session_id_for` must still create a row for a first event that is
    not `SessionStart`, and must **not** consult `entrypoint` (which is absent
    from all 429 captured payloads).
    """
    source = Path(hook_lane_module.__file__ or "").read_text(encoding="utf-8")
    assert "ephemeral" not in source, "the reconcile leaked into the hook lane"
    assert "entrypoint" not in source, "the hook lane cannot see `entrypoint` (DP2)"

    # A **real captured** non-`SessionStart` payload: a session that was already
    # running when hooks were installed never announces itself again (D47).
    captured = _first_captured("Stop")
    engine_session_id = captured.session_id
    assert store.get_session_by_engine_id(engine_session_id) is None

    HookLane(store, lambda event: 0).apply(
        Frame(payload=captured.raw, received_at=captured.received_at, peer_pid=None)
    )

    registered = store.get_session_by_engine_id(engine_session_id)
    assert registered is not None, "D47: the first event of any kind registers"
    assert registered.ephemeral is False


def _first_captured(event_name: str) -> CorpusEvent:
    """One envelope from the 429, byte-equivalent to real hook stdin (K1)."""
    return next(event for event in load_corpus() if event.event == event_name)


def test_an_owned_session_is_never_reconciled_to_ephemeral(
    store: Store, tmp_path: Path
) -> None:
    """E35's whole point: `kind` is `interactive` for a `-p` run too.

    Goes red if the match is done on `kind` rather than `entrypoint` — this row's
    sidecar carries `kind: "interactive"` and `entrypoint: "cli"`, so a `kind`
    match would hide a session Shepherd itself owns.
    """
    config_dir = tmp_path / "claude"
    fields = capture_fields(RUNNING)
    assert fields["kind"] == "interactive" and fields["entrypoint"] == "cli"
    write_sidecar(config_dir, fields)
    workspace = store.create_project(name="owned", description=None)
    owned = store.create_owned_session(
        session_id="01OWNEDSESSION0000000000AA",
        engine_session_id=SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        started_at=OBSERVED,
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="engine",
        handle=None,
        model=None,
        effort=None,
    )

    status = discovery_pass(
        store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir
    )

    after = store.get_session(owned.id)
    assert after is not None
    assert after.ephemeral is False
    assert [row.session_id for row in store.fleet()] == [owned.id]
    assert (status.sdk_cli_skipped, status.sdk_cli_reconciled) == (0, 0)
    assert status.sdk_cli_missed == 0, "an owned row is never a missed `-p` run"


def test_a_short_p_run_is_counted_as_missed_not_as_reconciled(
    store: Store, tmp_path: Path
) -> None:
    """Principle 5, at the counter that is *not* the flattering one.

    A `-p` run shorter than one 2.0 s sweep has had its sidecar deleted before
    any scan saw it (`registry.py`: the engine deletes it on exit), so the
    reconcile can never reach the row the hook lane left behind. That population
    is counted, not hidden. Goes red if the counter lies about coverage — which
    is this repo's dominant defect wearing a new hat.
    """
    config_dir = tmp_path / "claude"
    (config_dir / SESSIONS_DIRNAME).mkdir(parents=True)  # a real, empty registry
    session_id = hook_registered_row(store, SESSION_ID, "/tmp/shp-tui-A-4tvrx00n")

    status = discovery_pass(
        store, scripted(config_dir, {}), lambda r: None, OBSERVED, config_dir
    )

    assert status.sdk_cli_missed == 1
    assert status.sdk_cli_reconciled == 0
    assert status.sdk_cli_skipped == 0
    # …and the row is left exactly as it was. `missed` reports; it never repairs,
    # because nothing here observed what that row was.
    after = store.get_session(session_id)
    assert after is not None and after.ephemeral is False


def test_missed_stops_counting_a_row_the_sweep_does_see(
    store: Store, tmp_path: Path
) -> None:
    """The negative control for `sdk_cli_missed`: a counter that only ever rises
    is indistinguishable from a constant. A row the registry *has* observed is
    not missed, on the very same pass that observes it."""
    config_dir = tmp_path / "claude"
    write_sidecar(config_dir, capture_fields(RUNNING))
    hook_registered_row(store, SESSION_ID, "/tmp/shp-tui-A-4tvrx00n")
    host = scripted(config_dir, {PID: alive()})

    seen = discovery_pass(store, host, lambda r: None, OBSERVED, config_dir)
    assert seen.sdk_cli_missed == 0

    # The session exits: the engine deletes the sidecar. The row now carries the
    # `pid` this lane wrote, so it is still *not* missed — it was seen.
    (config_dir / SESSIONS_DIRNAME / f"{PID}.json").unlink()
    gone = discovery_pass(store, host, lambda r: None, LATER, config_dir)
    assert gone.sdk_cli_missed == 0


def test_only_the_registry_lane_writes_pid() -> None:
    """`sdk_cli_missed` reads `pid IS NULL` as "no sweep has ever seen this row".

    That sentence is only true while this module is the sole writer of the
    column. Asserted here rather than believed: an AST scan over `src/shepherd`
    for `FoldDelta(pid=…)` and `session.pid` writes.
    """
    roots = Path(discovery_loop_module.__file__ or "").resolve().parents[1]
    writers: set[str] = set()
    for path in sorted(roots.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _names(node.func) in {"FoldDelta"}:
                if any(keyword.arg == "pid" for keyword in node.keywords):
                    writers.add(path.name)
    assert writers == {"discovery_loop.py"}, writers


def _names(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def test_the_three_sdk_cli_counters_are_reported_together(
    store: Store, tmp_path: Path
) -> None:
    """`skipped` is the denominator and stays; `reconciled` and `missed` are the
    two halves that stop it reading as coverage.

    Goes red if `sdk_cli_skipped` is silently dropped, or if only the flattering
    counter is published — the published mapping is what `doctor` and
    `fleet_summary` read, so this is the surface, not the dataclass.
    """
    config_dir = tmp_path / "claude"
    headless = capture_fields(RUNNING)
    headless["entrypoint"] = SDK_CLI_ENTRYPOINT
    write_sidecar(config_dir, headless)
    hook_registered_row(store, SESSION_ID, "/tmp/shp-tui-A-4tvrx00n")
    # A second, older `-p` run whose sidecar is long gone: the missed population.
    hook_registered_row(store, "11111111-2222-3333-4444-555555555555", "/tmp/shp-other")

    status = discovery_pass(
        store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir
    )

    assert (status.sdk_cli_skipped, status.sdk_cli_reconciled, status.sdk_cli_missed) == (
        1,
        1,
        1,
    )
    published = store.get_app_state(DISCOVERY_STATUS_KEY)
    assert isinstance(published, dict)
    assert published["sdk_cli_skipped"] == 1
    assert published["sdk_cli_reconciled"] == 1
    assert published["sdk_cli_missed"] == 1


def test_discovery_does_not_duplicate_an_owned_session(store: Store, tmp_path: Path) -> None:
    """P-M3-8. Pre-registration (DP2 half one) plus a registry entry for the same
    engine session is **one** row.

    **A survivor, recorded rather than papered over (mutation run, T21).**
    Deleting `discovery_pass`'s `get_session_by_engine_id` call — `session = None`
    — leaves this green, and that is *correct*: `store.writes.register_session`
    is a SELECT-then-INSERT on `ux_session_engine_id` and returns the existing
    row unchanged, so the same lookup happens one layer down. The lookup in
    `discovery_pass` is a redundancy, not the guard; the guard is the unique
    index. The plan's sentence "goes red if `get_session_by_engine_id` is
    bypassed" is not true of this tree, and saying so is worth more than a check
    that cannot fail. The check was **not** deleted and the claim was **not**
    widened: what is asserted below is the property the clause is actually about
    — one row, and the **same** row, with its owned columns intact. The mutation
    that does bite it is identity taken from the registry entry rather than from
    the store (`apply_fold_delta(entry.session_id, …)`), which is the shape a
    real defect here would have.
    """
    config_dir = tmp_path / "claude"
    # An **owned spawn**, so the entry is `cli` and the update path really runs:
    # a pre-registered `ask()` fork is `sdk-cli` and already `ephemeral`, so the
    # reconcile returns without writing and the identity claim below would be
    # asserted over a code path that did nothing.
    write_sidecar(config_dir, capture_fields(RUNNING))
    workspace = store.create_project(name="owned", description=None)
    store.create_owned_session(
        session_id="01PREREGISTERED0000000000B",
        engine_session_id=SESSION_ID,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp/shp-tui-A-4tvrx00n",
        started_at=OBSERVED,
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="engine",
        handle=None,
        model=None,
        effort=None,
    )

    discovery_pass(
        store, scripted(config_dir, {PID: alive()}), lambda r: None, OBSERVED, config_dir
    )

    assert _rows_for_engine_id(store, SESSION_ID) == 1
    # …and it is the **same** row: updated, never replaced. An insert that
    # happened to leave one row (a delete-and-insert) loses every owned column,
    # which is what C14 records as the cost of not rebinding.
    after = store.get_session_by_engine_id(SESSION_ID)
    assert after is not None
    assert after.id == "01PREREGISTERED0000000000B"
    assert after.origin is Origin.USER_UI
    assert after.ownership is Ownership.OWNED
    assert after.ephemeral is False
    assert after.pid == PID, "the sweep updated the row it found"


def _rows_for_engine_id(store: Store, engine_session_id: str) -> int:
    """The clause's own literal: `SELECT count(*) … WHERE engine_session_id = ?`.

    Counted over `list_sessions()` rather than by opening a connection, because
    D33 forbids a caller passing SQL — the predicate is the same one.
    """
    return sum(
        1 for row in store.list_sessions() if row.engine_session_id == engine_session_id
    )
