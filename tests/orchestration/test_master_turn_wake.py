"""qa6 rulings P6 / BC-14 (ruling 5, D69, ADR-QR-5) — level 3 wakes the master.

**The seam is the orchestration seam**: `TurnDriver` and `LevelThreeWaker`
driven through their public verbs over a real `Store` in `tmp_path`, with
`test_master_turn.py`'s own `RecordingMaster` double — imported rather than
restated, so the two files cannot drift on what a runtime double is.

**Ticks are driven by the test, never by time** (the plan's validation
level): the 2 s sweep is the production caller of `tick()`, and a check that
waited for it would be sampling. Every "a turn is running" is a
synchronisation on the runtime's own `entered` event.

PP9 is the property: at most one unprompted turn per drained set, and never
while the slot is held.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from shepherd.core.master import MasterRuntime
from shepherd.core.states import Origin
from shepherd.core.stops import (
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopReason,
    Verdict,
)
from shepherd.orchestration import wake
from shepherd.orchestration.master_turn import TurnDriver, TurnStarted
from shepherd.store.db import Store

from .test_master_turn import (  # noqa: F401 — `recorder` and `store` are fixtures
    ARRIVAL_TIMEOUT_S,
    Recorder,
    RecordingMaster,
    an_event,
    finish,
    recorder,
    store,
    wait_for,
)

#: The clock's readings. The driver stamps `master_last_turn_at` with whatever
#: `now()` says when a turn opens, so a stop is only "since the last turn" when
#: it is later than the stamp — the checks move this clock by hand.
T0 = "2026-09-27T09:00:00.000Z"
T1 = "2026-09-27T09:10:00.000Z"
T2 = "2026-09-27T09:20:00.000Z"
T3 = "2026-09-27T09:30:00.000Z"

#: Sentences only this file could have produced, so a summary that re-derived
#: a row instead of reading it cannot reproduce them.
WHY = "QA6-P6 promised the migration and never ran it"
TITLE = "QA6-P6 lineage head"

#: The anomaly counter's wire values, typed from the spec (D31, D79).
CAP_REACHED = "wake_retry_cap_reached"


def sid(label: str) -> str:
    return (label + "0" * 26)[:26]


@dataclass
class Clock:
    now: str = T0

    def __call__(self) -> str:
        return self.now


@dataclass
class Rig:
    """One driver, one waker, over one store and a scripted queue of runtimes."""

    store: Store
    driver: TurnDriver
    waker: wake.LevelThreeWaker
    clock: Clock
    level: list[int]
    built: list[str]
    masters: list[RecordingMaster]
    failures: list[tuple[str, str]] = field(default_factory=list)


def a_rig(store: Store, recorder: Recorder, *masters: RecordingMaster, level: int = 3) -> Rig:
    queue = list(masters)
    built: list[str] = []
    failures: list[tuple[str, str]] = []
    clock = Clock()
    levels = [level]

    def build(turn_id: str) -> MasterRuntime:
        assert queue, "the driver asked for more runtimes than the check scripted"
        built.append(turn_id)
        runtime: MasterRuntime = queue.pop(0)
        return runtime

    driver = TurnDriver(
        store=store,
        build_master=build,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=clock,
        record_failure=lambda turn_id, error_class: failures.append((turn_id, error_class)),
    )
    waker = wake.LevelThreeWaker(
        store,
        level=lambda: levels[0],
        open_wake=driver.wake_turn,
        bump=store.bump_anomaly,
    )
    return Rig(store, driver, waker, clock, levels, built, list(masters), failures)


def workspace_id(store: Store) -> str:
    return next(w for w in store.list_workspaces() if w.name == "shepherd").id


def plant_session(store: Store, session_id: str, title: str) -> None:
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=f"eng-{session_id}",
        workspace_id=workspace_id(store),
        repo_id=None,
        cwd="/root/Shepherd",
        started_at=T0,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=title,
        title_source="brief",
        handle=None,
        model="opus",
        effort="high",
    )


def stop(store: Store, session_id: str, bucket: Bucket, why: str, at: str) -> None:
    store.apply_stop_verdict(
        session_id,
        Verdict(
            stop_reason=StopReason.INCOMPLETE,
            bucket=bucket,
            why=why,
            confidence=0.9,
            decided_by=DecidedBy.HEURISTIC,
            next_actions=(
                NextAction(
                    text="re-run",
                    kind=NextActionKind.RETRY,
                    target=None,
                    source=ActionSource.HEURISTIC,
                ),
            ),
            waiting_on=None,
            missing=(),
        ),
        at,
        None,
    )


def plant_a_stop(
    store: Store, label: str, at: str, bucket: Bucket = Bucket.UNFINISHED, why: str = WHY
) -> str:
    session_id = sid(label)
    plant_session(store, session_id, TITLE)
    stop(store, session_id, bucket, why, at)
    return session_id


def peeked(store: Store) -> list[str]:
    return [item.session_id for item in wake.peek(store)]


def tick_many(waker: wake.LevelThreeWaker, times: int = 5) -> list[bool]:
    return [waker.tick() for _ in range(times)]


def ended(rig: Rig) -> None:
    assert rig.driver.wait_for_turn(ARRIVAL_TIMEOUT_S), "the wake turn never ended"


# ----- level 3 opens a turn ---------------------------------------------------


def test_level_3_opens_an_unprompted_turn_with_the_summary_alone(
    store: Store, recorder: Recorder
) -> None:
    """D69: the only input is the wake summary — no user text beneath it.

    Arrival first: the set is asserted non-empty before the tick, so "a turn
    opened" cannot be satisfied by a waker that opens on an empty set. Then
    PP9's "at most one per drained set": the next ticks open nothing.
    """
    waking = plant_a_stop(store, "01P6WAKES", T1)
    master = RecordingMaster(events=(an_event("turn_ended"),))
    rig = a_rig(store, recorder, master)
    rig.clock.now = T2
    assert peeked(store) == [waking]
    try:
        assert rig.waker.tick() is True
        ended(rig)

        assert len(rig.built) == 1, "the runtime factory was not called for the wake"
        assert len(master.sent) == 1
        prompt = master.sent[0]
        assert prompt.startswith("while you were away —"), prompt[:200]
        assert WHY in prompt and TITLE in prompt
        # The summary alone: `_opening_text` puts a blank line between the
        # summary and the user's text, and the summary itself has none.
        assert "\n\n" not in prompt, prompt
        assert peeked(store) == [], "the wake turn did not drain the set"

        # PP9: the drained set opens nothing more, however many sweeps pass.
        assert tick_many(rig.waker) == [False] * 5
        assert len(rig.built) == 1
    finally:
        finish(rig.driver)
    assert rig.failures == []


def test_a_wake_while_a_turn_runs_opens_after_that_turn_ends(
    store: Store, recorder: Recorder
) -> None:
    """ADR-QR-5: queued behind a running turn, never dropped, never concurrent.

    The user turn is observably holding the slot (the runtime's own `entered`)
    before the stop is planted, so the user turn's drain cannot have taken it.
    """
    entered, release = threading.Event(), threading.Event()
    user_turn = RecordingMaster(entered=entered, release=release)
    wake_turn = RecordingMaster(events=(an_event("turn_ended"),))
    rig = a_rig(store, recorder, user_turn, wake_turn)
    try:
        rig.clock.now = T1
        assert isinstance(rig.driver.send_turn("the user's turn"), TurnStarted)
        wait_for(entered, "the user turn's runtime")
        waking = plant_a_stop(store, "01P6QUEUED", T2)
        rig.clock.now = T3
        assert peeked(store) == [waking], "arrival: the stop is in the set"

        # PP9's second half: never while the slot is held.
        assert tick_many(rig.waker) == [False] * 5
        assert len(rig.built) == 1, "a second runtime was built while a turn ran"
        # Queued, not dropped: the set is untouched while the slot is held.
        assert peeked(store) == [waking]

        release.set()
        ended(rig)
        assert not rig.driver.is_running()

        assert rig.waker.tick() is True
        ended(rig)
    finally:
        release.set()
        finish(rig.driver)

    assert user_turn.sent == ["the user's turn"]
    assert len(wake_turn.sent) == 1
    assert wake_turn.sent[0].startswith("while you were away —")
    assert WHY in wake_turn.sent[0]
    assert rig.failures == []


# ----- RD-3: the cap ----------------------------------------------------------


def test_a_wake_for_a_lineage_at_the_cap_opens_no_turn_and_counts_once_across_many_ticks(
    store: Store, recorder: Recorder
) -> None:
    """RD-3: a stop whose lineage is at `MAX_MASTER_ATTEMPTS` (2) opens nothing,
    bumps `wake_retry_cap_reached` once per session, and waits for the next
    user turn — the level-2 behaviour."""
    head, retry = sid("01P6HEAD"), sid("01P6RETRY")
    plant_session(store, head, "the first attempt, still running")
    plant_session(store, retry, TITLE)
    store.link_retry(session_id=retry, retry_of=head)
    stop(store, retry, Bucket.UNFINISHED, WHY, T1)
    assert store.retry_chain_depth(retry) == 2, "arrival: the lineage is at the cap"
    assert peeked(store) == [retry], "arrival: the capped stop is in the set"

    user_turn = RecordingMaster(events=(an_event("turn_ended"),))
    rig = a_rig(store, recorder, user_turn)
    rig.clock.now = T2
    try:
        assert tick_many(rig.waker, 7) == [False] * 7
        assert rig.built == [], "a wake opened for a lineage at the cap"
        assert store.list_anomaly_counts().get(CAP_REACHED) == 1
        # Waits for the next user turn, which drains it into its own summary.
        assert peeked(store) == [retry]
        assert isinstance(rig.driver.send_turn("what happened?"), TurnStarted)
        ended(rig)
    finally:
        finish(rig.driver)
    assert WHY in user_turn.sent[0] and user_turn.sent[0].endswith("what happened?")
    assert store.list_anomaly_counts().get(CAP_REACHED) == 1


# ----- what never wakes -------------------------------------------------------


def test_level_2_never_opens_an_unprompted_turn(store: Store, recorder: Recorder) -> None:
    """D31's level 2: the stop waits for your next turn. Arrival first: the set
    holds the stop, and the same rig at level 3 then opens a turn for it."""
    waking = plant_a_stop(store, "01P6LEVEL2", T1)
    master = RecordingMaster(events=(an_event("turn_ended"),))
    rig = a_rig(store, recorder, master, level=2)
    rig.clock.now = T2
    try:
        assert peeked(store) == [waking]
        assert tick_many(rig.waker) == [False] * 5
        assert rig.built == []
        assert peeked(store) == [waking], "level 2 consumed the set"

        rig.level[0] = 3
        assert rig.waker.tick() is True, "the control: level 3 does wake"
        ended(rig)
    finally:
        finish(rig.driver)
    assert len(rig.built) == 1


def test_a_wake_turn_that_finds_the_set_already_drained_opens_nothing(
    store: Store, recorder: Recorder
) -> None:
    """E-QR-7: a user turn drained the set between the waker's look and the
    wake's own drain. The wake opens nothing, closes the runtime it built, and
    frees the slot; the waker's next look finds nothing at all."""
    plant_a_stop(store, "01P6DRAINED", T1)
    user_turn = RecordingMaster(events=(an_event("turn_ended"),))
    unused = RecordingMaster(events=(an_event("turn_ended"),))
    rig = a_rig(store, recorder, user_turn, unused)
    rig.clock.now = T2
    try:
        assert isinstance(rig.driver.send_turn("hello"), TurnStarted)
        ended(rig)
        assert WHY in user_turn.sent[0], "arrival: the user turn drained the stop"

        assert rig.driver.wake_turn() is None
        assert unused.sent == [], "a wake with an empty set reached the runtime"
        assert unused.closed == 1, "the runtime built for an empty wake was never closed"
        assert not rig.driver.is_running(), "an empty wake kept the slot"

        assert tick_many(rig.waker) == [False] * 5
        assert len(rig.built) == 2
    finally:
        finish(rig.driver)
    assert rig.failures == []


def test_needs_you_never_wakes_the_master_at_level_3(store: Store, recorder: Recorder) -> None:
    """D31's rail: `needs_you` is the human's. Arrival first: the row landed with
    that outcome and is the newest stop there is."""
    needs_you = plant_a_stop(store, "01P6NEEDSYOU", T1, bucket=Bucket.NEEDS_YOU)
    row = store.get_session(needs_you)
    assert row is not None and row.outcome == Bucket.NEEDS_YOU.value
    rig = a_rig(store, recorder)
    rig.clock.now = T2
    assert tick_many(rig.waker) == [False] * 5
    assert rig.built == []
    assert store.list_anomaly_counts().get(CAP_REACHED, 0) == 0
