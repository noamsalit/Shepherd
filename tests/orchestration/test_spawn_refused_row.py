"""P4 / BC-28 — a start the runner refuses ends its row `refused` (§3 D73).

C-M3-7 still holds: the row is written before the process, so a refused start
leaves exactly one row. What changed is its ending. Before D73 the row was left
live (`starting`, no verdict), which qa6 O4 saw as a ghost session; now it is
`stopped` with a declared `refused` verdict, bucket `error`, and no handle.

**Seam: `spawn_owned_session`** over a real `Store` in `tmp_path`, with the
`test_spawn` helpers (the scripted runner, the injected clock, the recorded
publisher). Both refusal sites are driven: `runner.start` and `ensure_server`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shepherd.core.states import SessionState
from shepherd.core.stops import Bucket, DecidedBy, NextActionKind, StopReason, Verdict
from shepherd.orchestration.spawn import SPAWN_EVENT, SpawnRefused
from shepherd.signals.ordering import bucket_of
from shepherd.store import writes
from shepherd.store.db import Store
from shepherd.store.models import StoreError

from .test_spawn import (  # noqa: F401 — `store`, `root` and `workspace_id` are fixtures
    ExplodingRunner,
    Spawned,
    ready_pane,
    root,
    scripted,
    spawn,
    store,
    workspace_id,
)

#: `ExplodingRunner.start`'s own words, so the `why` is traced to the refusal.
START_REFUSAL = "the pane could not be created"
SERVER_REFUSAL = "no server on the socket, and none could be started"


def test_a_refused_start_ends_the_row_refused_and_not_live(
    store: Store, workspace_id: str, root: Path
) -> None:
    """C-QR-4 / PP7: one row, `stopped`, `refused`/`error`/`declared`, ended at
    the injected clock's stamp, with no handle."""
    world = Spawned()
    stamp = world.clock()
    result, _ = spawn(
        store=store,
        runner=ExplodingRunner(),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=world,
    )

    assert isinstance(result, SpawnRefused), result
    assert result.reason == START_REFUSAL
    rows = store.list_sessions(workspace_id=workspace_id)
    assert len(rows) == 1, "C-M3-7: the attempt stays visible as exactly one row"
    row = rows[0]
    assert row.state is SessionState.STOPPED
    assert row.stop_reason == StopReason.REFUSED.value == "refused"
    assert row.outcome == Bucket.ERROR.value
    assert row.decided_by == DecidedBy.DECLARED.value
    assert row.why == START_REFUSAL
    assert row.confidence == 1.0
    assert row.ended_at == stamp, "stamped by the injected clock, never the wall clock"
    assert row.last_event_at == stamp
    assert row.exit_code is None
    assert row.runner_handle is None


def test_an_ensure_server_refusal_ends_the_row_refused(
    store: Store, workspace_id: str, root: Path
) -> None:
    """E-QR-6: the other refusal site ends the row the same way."""
    world = Spawned(ensure_server_refusal=SERVER_REFUSAL)
    runner = scripted(panes=[ready_pane()])
    result, _ = spawn(
        store=store, runner=runner, workspace_id=workspace_id, cwd=str(root / "repo"), world=world
    )

    assert isinstance(result, SpawnRefused), result
    assert "start" not in runner.calls
    rows = store.list_sessions(workspace_id=workspace_id)
    assert len(rows) == 1
    assert rows[0].state is SessionState.STOPPED
    assert rows[0].stop_reason == "refused"
    assert rows[0].why == SERVER_REFUSAL
    assert rows[0].ended_at is not None
    assert rows[0].runner_handle is None


def test_a_refused_row_buckets_error_with_a_respawn_action(
    store: Store, workspace_id: str, root: Path
) -> None:
    """The fleet projection reads it as an `error` row with something to do:
    start it again first, then read why."""
    world = Spawned()
    spawn(
        store=store,
        runner=ExplodingRunner(),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=world,
    )

    (fleet_row,) = store.fleet()
    assert bucket_of(fleet_row, world.clock()) is Bucket.ERROR
    kinds = [action.kind for action in fleet_row.next_actions]
    assert kinds == [NextActionKind.RESPAWN, NextActionKind.INSPECT]
    assert all(action.text for action in fleet_row.next_actions)


def test_a_refused_start_publishes_no_spawn_event(
    store: Store, workspace_id: str, root: Path
) -> None:
    """Nothing started, so nothing says `session.spawned` (the refusal travels
    as the call's synchronous result)."""
    for world, runner in (
        (Spawned(), ExplodingRunner()),
        (Spawned(ensure_server_refusal=SERVER_REFUSAL), scripted(panes=[ready_pane()])),
    ):
        result, _ = spawn(
            store=store, runner=runner, workspace_id=workspace_id, cwd=str(root / "repo"),
            world=world,
        )
        assert isinstance(result, SpawnRefused), result
        assert [event.kind for event in world.events if event.kind == SPAWN_EVENT] == []
        assert world.events == []


def test_a_failed_refused_ending_still_returns_the_runners_refusal(
    store: Store, workspace_id: str, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REM-FIX 1: the ending is ONE store verb, and a `StoreError` from it is
    still a `SpawnRefused` carrying the runner's own words — never a raise out
    of `spawn_owned_session` (its "every failure is a `SpawnRefused`" contract).
    """
    calls: list[str] = []

    def failing(session_id: str, verdict: Verdict, ended_at: str) -> None:
        calls.append(session_id)
        raise StoreError("disk I/O error")

    monkeypatch.setattr(store, "end_refused", failing, raising=False)
    result, _ = spawn(
        store=store,
        runner=ExplodingRunner(),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=Spawned(),
    )

    assert len(calls) == 1, "the refused ending is written through `end_refused`, once"
    assert isinstance(result, SpawnRefused), result
    assert result.reason == START_REFUSAL
    (row,) = store.list_sessions(workspace_id=workspace_id)
    assert row.state is SessionState.STARTING, "untouched: no half of the ending landed"
    assert row.stop_reason is None


def test_the_refused_ending_is_all_or_nothing(
    store: Store, workspace_id: str, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomicity: a failure injected *inside* the verb's transaction, after the
    state fold and at the stop write, rolls the fold back too. The row is
    either fully ended or untouched — never `stopped` with no verdict."""

    def stop_write_fails(
        connection: sqlite3.Connection,
        session_id: str,
        verdict: Verdict,
        ended_at: str,
        exit_code: int | None,
    ) -> None:
        raise StoreError("database is locked")

    monkeypatch.setattr(writes, "apply_stop_verdict", stop_write_fails)
    result, _ = spawn(
        store=store,
        runner=ExplodingRunner(),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        world=Spawned(),
    )

    assert isinstance(result, SpawnRefused), result
    assert result.reason == START_REFUSAL
    (row,) = store.list_sessions(workspace_id=workspace_id)
    assert row.state is SessionState.STARTING, "the fold rolled back with the stop write"
    assert row.stop_reason is None
    assert row.ended_at is None
