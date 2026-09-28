"""BC-37 — a killed owned row is `stopped`, not left at whatever it was.

**Seam: `record_and_terminate`**, over a real `Store` and the shipped
`ScriptedRunner`. The kill path writes the verdict through `apply_stop_verdict`,
which by its own contract does not touch `state` (`ask.py:_finish`'s note), so
before BC-37 nothing set it: qa6 O6's killed row read `starting` with
`stop_reason: killed`, and the fleet page bucketed it `unknown`.

**The residual was decided by the owner (ruling 10, 2026-09-27).** A session
that finished a turn before it was killed used to keep that turn's verdict:
G-M3-9's guard read `ended_at`, and every turn end stamps it (`signals/fold.py`).
The guard now compares the row's **verdict** (`stop_reason`, `decided_by`) across
the kill (P7 REM-FIX 1), so an older turn ending no longer blocks `killed`. The
row ends `stopped` either way — the kill itself is the hard signal.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.fold_types import FoldDelta
from shepherd.core.runner import ProcState, RunnerHandle
from shepherd.core.states import Origin, SessionState
from shepherd.core.stops import PALETTE, Bucket, DecidedBy, StopReason, Verdict
from shepherd.orchestration.lifecycle import record_and_terminate
from shepherd.runner.base import PaneRef
from shepherd.runner.tmux_cmd import session_name
from shepherd.signals.ordering import bucket_of
from shepherd.signals.stop_rules import BUCKET_OF, default_actions
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner

STARTED = "2026-09-24T03:55:00.000Z"
TURN_ENDED = "2026-09-24T03:56:00.000Z"
NEXT_PROMPT = "2026-09-24T03:57:00.000Z"
KILLED_AT = "2026-09-24T03:58:00.000Z"
SESSION_ID = "01M38RWEFCX8Y6EJBTFHKQTTP9"
HANDLE = RunnerHandle(
    runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=session_name(SESSION_ID)
)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def owned_row(store: Store, state: SessionState) -> None:
    """A real owned row through the store's own verb, at `state`."""
    store.create_owned_session(
        session_id=SESSION_ID,
        engine_session_id="8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6",
        workspace_id=store.create_project(name="qa6", description=None).id,
        repo_id=None,
        cwd="/tmp/shepherd-bc37",
        started_at=STARTED,
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=HANDLE,
        model=None,
        effort=None,
    )
    store.apply_fold_delta(SESSION_ID, FoldDelta(state=state, last_event_at=STARTED))


def live_runner() -> ScriptedRunner:
    """The pane is listed and alive: the kill has something to remove."""
    pane = PaneRef(
        session_name=HANDLE.session_name, session_id=SESSION_ID, pane_pid=4041880, dead=False
    )
    proc = ProcState(
        alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=STARTED
    )
    return ScriptedRunner(panes=(), proc=proc, screen=b"", owned_panes=(pane,))


def completed() -> Verdict:
    """The verdict a finished turn leaves behind — what the stop lane writes."""
    return Verdict(
        stop_reason=StopReason.COMPLETED,
        bucket=BUCKET_OF[StopReason.COMPLETED],
        why="the turn ended with its work done",
        confidence=0.9,
        decided_by=DecidedBy.MECHANICAL,
        next_actions=default_actions(
            StopReason.COMPLETED, confidence=0.9, missing=(), waiting_on=None
        ),
        waiting_on=None,
        missing=(),
    )


def kill(store: Store, runner: ScriptedRunner) -> None:
    record_and_terminate(
        store=store,
        runner=runner,
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: KILLED_AT,
        publish=lambda event: None,
    )


def fleet_bucket(store: Store) -> Bucket:
    (row,) = [row for row in store.fleet() if row.session_id == SESSION_ID]
    return bucket_of(row, KILLED_AT)


def test_a_kill_leaves_a_never_turned_row_stopped_and_stranded(store: Store) -> None:
    """O6's and U11's row: spawned, never finished a turn, killed.

    Goes red if the kill path stops writing `state` — the row reads `starting`
    and the page's bucket falls through to `unclassified` ("unknown").
    """
    owned_row(store, SessionState.STARTING)
    runner = live_runner()
    kill(store, runner)

    assert "terminate" in runner.calls, "arrival: the kill was issued"
    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.state is SessionState.STOPPED
    assert row.stop_reason == "killed"
    assert row.ended_at == KILLED_AT
    assert fleet_bucket(store) is Bucket.UNFINISHED
    assert PALETTE[Bucket.UNFINISHED].label == "stranded"


def test_a_kill_after_a_turn_leaves_the_row_stopped(store: Store) -> None:
    """A live session that finished a turn and took a new prompt, then killed.

    `ended_at` is still the turn's (nothing clears it) and the state is
    `running` again, so the kill is the only thing that can say `stopped`.
    Ruling 10 (BC-37 residual, 2026-09-27): the turn's older ending is not a
    session end during the kill (the verdict did not change across it), so the
    verdict is `killed` at the kill's time. This pin used to record the turn's
    `completed` surviving the kill, as the pre-ruling behaviour.
    """
    owned_row(store, SessionState.RUNNING)
    store.apply_fold_delta(
        SESSION_ID,
        FoldDelta(state=SessionState.STOPPED, ended_at=TURN_ENDED, last_event_at=TURN_ENDED),
    )
    store.apply_stop_verdict(SESSION_ID, completed(), TURN_ENDED, None)
    store.apply_fold_delta(
        SESSION_ID, FoldDelta(state=SessionState.RUNNING, last_event_at=NEXT_PROMPT)
    )
    runner = live_runner()
    kill(store, runner)

    assert runner.calls.count("terminate") == 1, "arrival: the kill was issued"
    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.state is SessionState.STOPPED
    # Ruling 10: the kill, not the finished turn, is this session's end.
    assert row.stop_reason == "killed"
    assert row.ended_at == KILLED_AT
