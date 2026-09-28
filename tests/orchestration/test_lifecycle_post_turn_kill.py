"""Ruling 10 (BC-37 residual): a kill after a finished turn is recorded `killed`.

Every turn end stamps `ended_at` and writes the turn's verdict. Before ruling 10
the kill wrote its verdict only when `ended_at` was empty, so an owned session
killed between turns kept its last turn's verdict and read as merely finished.

Ruling 10 is about **a live session between turns** (REM-FIX 1). `killed` is
written only when (a) no session end arrived during the kill — the row's
**verdict** (`stop_reason`/`decided_by`) is the same across it, so the liveness
sweep's bare `ended_at` stamp is not one — and (b) the row had no ending or the
pre-kill probe saw a live pane. A dead pane with an ending keeps its verdict.
The seam is `record_and_terminate` with a runner double whose `terminate` can
land a session ending mid-kill (E-QR-13).
"""

from __future__ import annotations

import pytest

from orchestration.test_lifecycle import (
    HANDLE,
    LATER,
    NOW,
    SESSION_ID,
    anomaly,
    driver,
    owned_row,
    runner_of,
    store,
    workspace_id,
)
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import SessionState
from shepherd.core.stops import DecidedBy, StopReason, Verdict
from shepherd.orchestration.lifecycle import record_and_terminate
from shepherd.signals.stop_rules import BUCKET_OF, default_actions
from shepherd.store.db import Store

__all__ = ["store", "workspace_id"]

#: The session-ending hook's stamp, strictly between the turn end and the kill.
DURING = "2026-09-17T10:04:59.000Z"


def verdict(reason: StopReason, why: str) -> Verdict:
    """A stop written the way the stop lane writes one — through M2's tables."""
    return Verdict(
        stop_reason=reason,
        bucket=BUCKET_OF[reason],
        why=why,
        confidence=0.9,
        decided_by=DecidedBy.MECHANICAL,
        next_actions=default_actions(reason, confidence=0.9, missing=(), waiting_on=None),
        waiting_on=None,
        missing=(),
    )


def finished_turn(store: Store, workspace_id: str) -> None:
    """An owned row whose last turn ended at `NOW` with a `completed` verdict."""
    owned_row(store, workspace_id)
    store.apply_stop_verdict(SESSION_ID, verdict(StopReason.COMPLETED, "turn ended"), NOW, None)


def kill(store: Store, *, during: bool) -> None:
    def session_end() -> None:
        store.apply_stop_verdict(
            SESSION_ID, verdict(StopReason.USER_EXITED, "session ended"), DURING, 0
        )

    record_and_terminate(
        store=store,
        # A session between turns: the pane is live before the kill.
        runner=runner_of(
            driver(exit_code=None, alive=True, during_kill=session_end if during else None)
        ),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=lambda event: None,
    )


def test_a_kill_after_a_finished_turn_records_killed(store: Store, workspace_id: str) -> None:
    """Ruling 10's first half. The turn's ending is older than the kill, so the
    kill is the session's end: the declared `killed` verdict replaces the turn's,
    at the kill's time, with the live pane's (absent) exit code read before the
    kill, and the kill is counted because no session ending of its own followed it.

    Goes red on the pre-ruling guard (`ended_at is None`), which kept `completed`.
    """
    finished_turn(store, workspace_id)
    kill(store, during=False)

    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.stop_reason == str(StopReason.KILLED.value)
    assert row.decided_by == str(DecidedBy.DECLARED.value)
    assert row.ended_at == LATER
    assert row.exit_code is None, "a live pane has no exit status yet"
    assert row.state is SessionState.STOPPED
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 1


@pytest.mark.parametrize("turn_finished_first", [True, False], ids=["after-a-turn", "mid-turn"])
def test_a_session_end_during_the_kill_keeps_its_own_verdict(
    store: Store, workspace_id: str, turn_finished_first: bool
) -> None:
    """Ruling 10's second half. A session ending that lands **during** the kill
    changes the verdict, so it is the evidence and the kill writes nothing over it:
    the hook's verdict and stamp stay, and nothing is counted. Asserted from a
    finished turn and from a row that never ended, so the comparison — not the
    emptiness of the column — is what decides.
    """
    if turn_finished_first:
        finished_turn(store, workspace_id)
    else:
        owned_row(store, workspace_id)
    kill(store, during=True)

    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.stop_reason == str(StopReason.USER_EXITED.value)
    assert row.ended_at == DURING
    assert row.exit_code == 0
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 0


def test_a_kill_of_a_dead_pane_keeps_its_crashed_verdict(store: Store, workspace_id: str) -> None:
    """REM-FIX 1 decision 1. The session already ended — `crashed`, its pane dead
    and holding the status — so a kill ends nothing: the real verdict, stamp and
    exit code stay, and no `KILL_WITHOUT_SESSION_END` is counted.

    Goes red on P7's `ended_at`-only comparison, which re-killed it.
    """
    owned_row(store, workspace_id)
    store.apply_stop_verdict(SESSION_ID, verdict(StopReason.CRASHED, "engine died"), NOW, 1)
    record_and_terminate(
        store=store,
        runner=runner_of(driver(exit_code=1)),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=lambda event: None,
    )

    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.stop_reason == str(StopReason.CRASHED.value)
    assert row.ended_at == NOW
    assert row.exit_code == 1
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 0


def test_a_liveness_sweep_during_a_mid_turn_kill_still_records_killed(
    store: Store, workspace_id: str
) -> None:
    """REM-FIX 1 decision 2. The liveness sweep ends a gone process with a bare
    `FoldDelta` — `ended_at` and no verdict (`discovery_loop.liveness_sweep`). Its
    stamp landing during the kill is not a session end, so the kill still writes
    `killed` and is counted.

    Goes red on P7's `ended_at`-only comparison, which read the stamp as an ending.
    """
    owned_row(store, workspace_id)

    def sweep() -> None:
        store.apply_fold_delta(
            SESSION_ID,
            FoldDelta(state=SessionState.STOPPED, ended_at=DURING, observed_at=DURING),
        )

    record_and_terminate(
        store=store,
        runner=runner_of(driver(exit_code=None, alive=True, during_kill=sweep)),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=lambda event: None,
    )

    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.stop_reason == str(StopReason.KILLED.value)
    assert row.ended_at == LATER
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 1
