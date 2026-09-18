"""T27 — `orchestration/master_turn.py`: one turn, one slot, one loop.

**Two seams, both named in the plan.** The integration seam is `TurnDriver`'s
public interface driven against a real `Store` in `tmp_path` and a
`MasterRuntime` double; the boundary seam is an AST rule over `src/` asserting
that exactly one module calls `.send(` (P-M4-21).

**The double is this file's own, and that is a plan-vs-tree fact rather than a
shortcut.** T27's Dependencies name T17's `ScriptedMaster`; `src/shepherd/
testkit/scripted_master.py` does not exist on this tree yet (T17 is live in
another builder's hands). `RecordingMaster` below satisfies the same
`MasterRuntime` Protocol — `mypy --strict` checks that by assigning it to a
`MasterRuntime`-annotated name — and the swap is one line when T17 lands. See
`docs/plans/m4-blockers/t27.md` §T27-1.

Three disciplines this file keeps, each because the repo has been bitten:

* **arrival before absence, and arrival is a synchronisation.** The refusal
  check waits on an `Event` the runtime's own `send()` sets from inside the
  turn's loop before it asserts the second turn refused. `Thread.is_alive()`
  after `start()` is true whether or not the work began (§T10-7's survivor,
  one suit over), so no check here samples a thread.
* **no literal count.** `MASTER_EVENT_KINDS` is enumerated at test time and
  compared as a set; the enumeration rule is written into the check.
* **no recomputed expectation.** The published kinds are compared against the
  projection rule stated here once, not against whatever the driver produced.

Nothing in this file executes a planted violation: the single-caller rule's
negative control is the **inert fixture**
`tests/boundaries/fixtures/second_master_send_caller.py`, read as text and
parsed as an AST, never imported (CLAUDE.md, "Mutations").
"""

from __future__ import annotations

import ast
import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.master import (
    MASTER_EVENT_KINDS,
    MasterCapabilities,
    MasterEvent,
    MasterRuntime,
)
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
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.master_turn import (
    MASTER_SESSION_KEY,
    STREAM_KIND_PREFIX,
    TurnDriver,
    TurnRefused,
    TurnStarted,
    project_to_stream,
)
from shepherd.orchestration.wake import MASTER_LAST_TURN_KEY
from shepherd.store.db import Store, open_store

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
BOUNDARY_FIXTURES = REPO_ROOT / "tests" / "boundaries" / "fixtures"

#: The one module the single-caller rule permits, spelled relative to `src/`.
THE_ONLY_CALLER = "shepherd/orchestration/master_turn.py"

#: Long enough that a check waiting on it has really hung rather than raced.
ARRIVAL_TIMEOUT_S = 5.0

MOMENT = "2026-09-17T12:00:00.000Z"
TURN_OPENED = "2026-09-17T12:05:00.000Z"
STOPPED = "2026-09-17T11:00:00.000Z"

WAKING_ID = ("01T27WAKES" + "0" * 26)[:26]
#: A sentence only this fixture could have produced, so a summary that
#: re-classified the row instead of reading it cannot reproduce it.
WAKE_WHY = "promised the specs and never ran them"
WAKE_TITLE = "OXDEV-81711 resolver"


# ----- the runtime double ------------------------------------------------------


class RecordingMaster:
    """A `MasterRuntime` that records what it was asked and streams a script.

    `entered` is set **from inside the running loop**, which is what makes every
    "the first turn is holding the slot" assertion a synchronisation rather than
    a sample. `release` is how a check keeps a turn open for as long as it needs
    to observe something about it.
    """

    def __init__(
        self,
        events: tuple[MasterEvent, ...] = (),
        *,
        entered: threading.Event | None = None,
        release: threading.Event | None = None,
        raises: BaseException | None = None,
        order: list[str] | None = None,
    ) -> None:
        self.events = events
        self.entered = entered
        self.release = release
        self.raises = raises
        self.order = order
        self.sent: list[str] = []
        self.interrupts = 0
        self.resumed: list[str] = []
        self.closed = 0
        #: `id()` of every loop this runtime was iterated on — empty until a
        #: turn runs, and that emptiness is what "no loop at boot" means here.
        self.loop_ids: set[int] = set()

    def configure(self, tools: tuple[object, ...], system_prompt: str) -> None:
        raise AssertionError("the driver must not configure the runtime (T25 owns that)")

    def send(self, text: str) -> AsyncIterator[MasterEvent]:
        return self._stream(text)

    async def _stream(self, text: str) -> AsyncIterator[MasterEvent]:
        self.sent.append(text)
        self.loop_ids.add(id(asyncio.get_running_loop()))
        if self.entered is not None:
            self.entered.set()
        while self.release is not None and not self.release.is_set():
            await asyncio.sleep(0.005)
        if self.raises is not None:
            raise self.raises
        for event in self.events:
            yield event

    def resume(self, master_session_id: str) -> None:
        self.resumed.append(master_session_id)

    def interrupt(self) -> None:
        self.interrupts += 1
        if self.order is not None:
            self.order.append("interrupt")

    def capabilities(self) -> MasterCapabilities:
        return MasterCapabilities(
            billing_mode="seat",
            owns_history=True,
            owns_compaction=True,
            supports_parallel_tool_calls=False,
            context_window=200000,
        )

    def close(self) -> None:
        self.closed += 1


def an_event(kind: str, **payload: object) -> MasterEvent:
    return MasterEvent(
        kind=kind,  # type: ignore[arg-type]
        text=f"{kind} text",
        tool_name="fleet_summary" if kind.startswith("tool") else None,
        payload=payload,
        occurred_at=MOMENT,
    )


@dataclass
class Recorder:
    """The two injected L4 callables, recorded in call order across both."""

    published: list[StreamEvent]
    withdrawals: list[str]
    order: list[str]

    def publish(self, event: StreamEvent) -> int:
        self.published.append(event)
        self.order.append("publish")
        return len(self.published)

    def withdraw(self, turn_id: str) -> int:
        self.withdrawals.append(turn_id)
        self.order.append("withdraw")
        return 1


@pytest.fixture()
def recorder() -> Recorder:
    return Recorder(published=[], withdrawals=[], order=[])


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    opened.upsert_workspace("shepherd", "/root/Shepherd")
    try:
        yield opened
    finally:
        opened.close()


def plant_a_waking_stop(store: Store) -> None:
    """One master-owned session that stopped `unfinished`, planted through the
    public verbs — no raw SQL, as T9's own fixture does it."""
    store.create_owned_session(
        session_id=WAKING_ID,
        engine_session_id=f"eng-{WAKING_ID}",
        workspace_id=store.list_workspaces()[0].id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T10:00:00.000Z",
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=WAKE_TITLE,
        title_source="brief",
        handle=None,
        model="opus",
        effort="high",
    )
    store.apply_stop_verdict(
        WAKING_ID,
        Verdict(
            stop_reason=StopReason.INCOMPLETE,
            bucket=Bucket.UNFINISHED,
            why=WAKE_WHY,
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
        STOPPED,
        None,
    )


def a_driver(
    store: Store,
    recorder: Recorder,
    *masters: RecordingMaster,
    now: str = TURN_OPENED,
) -> TurnDriver:
    """One driver over a queue of runtimes: the n-th turn gets the n-th double.

    A queue rather than a single double because `build_master` is called **per
    turn** — a driver that built one runtime at construction and reused it would
    otherwise pass every check here.
    """
    queue = [master for master in masters]

    def build(_turn_id: str) -> MasterRuntime:
        assert queue, "the driver asked for more runtimes than the check scripted"
        runtime: MasterRuntime = queue.pop(0)  # mypy --strict: the double is a §6 Protocol
        return runtime

    return TurnDriver(
        store=store,
        build_master=build,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: now,
    )


def wait_for(event: threading.Event, what: str) -> None:
    assert event.wait(ARRIVAL_TIMEOUT_S), f"{what} never arrived within {ARRIVAL_TIMEOUT_S}s"


def finish(driver: TurnDriver) -> None:
    driver.close()
    assert not driver.is_running(), "the driver still holds the slot after close()"


# ----- P-M4-21: the AST single-caller rule ------------------------------------


def modules_that_call_send(root: Path) -> frozenset[str]:
    """Every module under `root` containing a call of the form `<x>.send(...)`.

    **The rule, written down so a future reader can tell a narrowed scan from a
    changed tree:** every `*.py` file under `root` is parsed with `ast.parse`,
    and a module is in the set when it holds an `ast.Call` whose `func` is an
    `ast.Attribute` named `send`. Attribute-named, not name-resolved: a
    type-directed scan would miss `getattr(runtime, "send")` and would go quiet
    the moment a second driver stopped annotating its variable, which is the
    opposite of what P-M4-21 is for. The cost is that any `.send(` in `src/`
    is reported — and that is the intended blast radius, because this tree
    contains exactly one.
    """
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "send"
            ):
                found.add(path.relative_to(root).as_posix())
    return frozenset(found)


def test_the_turn_driver_is_the_only_caller_of_send() -> None:
    """P-M4-21: exactly one component in `src/` calls `send()`.

    Goes red if a second driver appears — including one improvised into
    `toolsurface/compose.py`, which is the hole revision 1 left open.
    """
    callers = modules_that_call_send(SRC)

    # Arrival before equality: the scan really found the driver's own call…
    assert THE_ONLY_CALLER in callers, "the scan found no caller at all — the scan is broken"
    # …and it found nobody else.
    assert callers == frozenset({THE_ONLY_CALLER}), sorted(callers - {THE_ONLY_CALLER})


def test_the_single_caller_rule_detects_a_second_caller() -> None:
    """The negative control, against an **inert fixture** nothing imports.

    `second_master_send_caller.py` lives under `tests/boundaries/fixtures/`, is
    read as text and parsed as an AST, and is never on an import path the suite
    executes (CLAUDE.md). Goes red if the scan stops seeing an added caller,
    which is the only way `test_the_turn_driver_is_the_only_caller_of_send`
    could pass vacuously.
    """
    fixture = BOUNDARY_FIXTURES / "second_master_send_caller.py"
    assert fixture.exists(), "the negative control's fixture is missing"

    assert modules_that_call_send(BOUNDARY_FIXTURES) == frozenset(
        {"second_master_send_caller.py"}
    )


# ----- the slot ---------------------------------------------------------------


def test_a_second_turn_is_refused_while_one_is_live(store: Store, recorder: Recorder) -> None:
    """RD7: one turn at a time, refused readably, never queued.

    **Arrival first, and the arrival is a synchronisation**: `entered` is set by
    the runtime from inside the turn's own loop, so the first turn is observably
    holding the slot before the second is asserted refused. A check that only
    asserted the second refusal would pass against a driver that never took the
    slot at all.
    """
    entered, release = threading.Event(), threading.Event()
    master = RecordingMaster(entered=entered, release=release)
    driver = a_driver(store, recorder, master)
    try:
        first = driver.send_turn("the first turn")
        assert isinstance(first, TurnStarted)
        wait_for(entered, "the first turn's runtime")
        assert driver.is_running()

        second = driver.send_turn("the second turn")

        assert isinstance(second, TurnRefused)
        # Readable: it says what happened and it names the turn still running.
        assert first.turn_id in second.reason
        assert second.reason.strip() == second.reason and len(second.reason.split()) >= 5
        # Not queued: the runtime was asked for one turn and one only.
        assert master.sent == ["the first turn"]
    finally:
        release.set()
        finish(driver)

    # The slot came back once the turn ended, so a third turn is accepted.
    assert master.sent == ["the first turn"]


def test_the_slot_is_released_when_a_turn_raises(store: Store, recorder: Recorder) -> None:
    """A slot released only on success is a chat that wedges on the first error.

    Arrival first: the raising turn is asserted to have **reached** the runtime
    before the release is asserted, so "released" cannot mean "never taken".
    """
    entered = threading.Event()
    boom = RecordingMaster(entered=entered, raises=RuntimeError("the runtime fell over"))
    second = RecordingMaster(events=(an_event("turn_ended"),))
    driver = a_driver(store, recorder, boom, second)
    try:
        assert isinstance(driver.send_turn("the turn that raises"), TurnStarted)
        wait_for(entered, "the raising turn's runtime")
        assert boom.sent == ["the turn that raises"]
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)

        assert not driver.is_running(), "an exception wedged the slot"

        # And the next turn really runs, which is the thing the release is for.
        assert isinstance(driver.send_turn("the turn after the error"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
        assert second.sent == ["the turn after the error"]
    finally:
        finish(driver)

    # The error reached the ring rather than being swallowed.
    kinds = [event.kind for event in recorder.published]
    assert f"{STREAM_KIND_PREFIX}error" in kinds, kinds


# ----- the wake summary -------------------------------------------------------


def test_a_turn_opens_with_the_wake_summary(store: Store, recorder: Recorder) -> None:
    """§12's "while you were away —" opens the turn, and the stamp then moves.

    Arrival first: `peek()` is asserted non-empty **before** anything is sent,
    so "the summary was prepended" cannot be satisfied by an empty summary.
    """
    from shepherd.orchestration.wake import peek

    plant_a_waking_stop(store)
    assert [item.session_id for item in peek(store)] == [WAKING_ID]
    assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

    master = RecordingMaster(events=(an_event("turn_ended"),))
    driver = a_driver(store, recorder, master)
    try:
        assert isinstance(driver.send_turn("what happened?"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    assert len(master.sent) == 1
    text = master.sent[0]
    # The fixture's own sentences, not a recomputed rendering.
    assert "while you were away —" in text
    assert WAKE_WHY in text and WAKE_TITLE in text
    # The user's text survives, and it comes after the summary.
    assert text.endswith("what happened?")
    assert text.index("while you were away —") < text.index("what happened?")
    # The stamp moved, and the set is consumed: a second peek is empty.
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == TURN_OPENED
    assert peek(store) == ()


def test_an_empty_wake_set_still_opens_a_turn(store: Store, recorder: Recorder) -> None:
    """No rows means no header and no blank line — and the turn still runs."""
    master = RecordingMaster(events=(an_event("turn_ended"),))
    driver = a_driver(store, recorder, master)
    try:
        assert isinstance(driver.send_turn("hello"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    assert master.sent == ["hello"]
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == TURN_OPENED


# ----- the projection ---------------------------------------------------------


def test_every_master_event_kind_is_published(store: Store, recorder: Recorder) -> None:
    """Every kind reaches the ring, over `MASTER_EVENT_KINDS` enumerated here.

    **The enumeration rule:** the kinds are read from `core.master`'s own
    frozenset at test time, never listed beside it. A kind added to the domain
    and dropped by the driver would be a class of output the chat page silently
    misses; a kind removed from the domain and still driven here would be a
    check testing a word that no longer exists. Set equality catches both.
    """
    kinds = sorted(MASTER_EVENT_KINDS - {"turn_ended"}) + ["turn_ended"]
    master = RecordingMaster(events=tuple(an_event(kind) for kind in kinds))
    driver = a_driver(store, recorder, master)
    try:
        started = driver.send_turn("say everything")
        assert isinstance(started, TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    published = {event.kind for event in recorder.published}
    assert published == {f"{STREAM_KIND_PREFIX}{kind}" for kind in MASTER_EVENT_KINDS}
    # Every published event carries the turn it belongs to.
    assert {event.payload["turn_id"] for event in recorder.published} == {started.turn_id}


def test_the_projection_keeps_our_words_and_the_events_own_time() -> None:
    """`project_to_stream` is total and lossless at the seam the page reads.

    **Every expected value is a literal typed here**, never read back off the
    event: an expectation built from `event.payload` is recomputed the way the
    projection computes it and passes whatever the fixture holds — which is
    exactly how MUT-11 survived the first form of this check.
    """
    event = MasterEvent(
        kind="tool_call",
        text="calling fleet_summary",
        tool_name="fleet_summary",
        payload={"detail": "a payload key the projection must not lose"},
        occurred_at=MOMENT,
    )

    projected = project_to_stream(event, "01TURN")

    assert projected == StreamEvent(
        kind="master.tool_call",
        session_id=None,
        payload={
            "turn_id": "01TURN",
            "text": "calling fleet_summary",
            "tool_name": "fleet_summary",
            "detail": {"detail": "a payload key the projection must not lose"},
        },
        occurred_at=MOMENT,
    )


def test_the_master_session_id_is_persisted_from_the_first_event_that_carries_one(
    store: Store, recorder: Recorder
) -> None:
    """D10: one continuous conversation, so the id survives a restart mid-turn.

    The **first** carrier wins: a later event re-stating a different id must not
    overwrite a session the store is already continuing.
    """
    master = RecordingMaster(
        events=(
            an_event("text"),
            an_event("tool_call", **{MASTER_SESSION_KEY: "ses-first"}),
            an_event("turn_ended", **{MASTER_SESSION_KEY: "ses-second"}),
        )
    )
    driver = a_driver(store, recorder, master)
    try:
        assert store.get_app_state(MASTER_SESSION_KEY) is None
        assert isinstance(driver.send_turn("go"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)

    assert store.get_app_state(MASTER_SESSION_KEY) == "ses-first"


# ----- the interrupt ----------------------------------------------------------


def test_an_interrupt_withdraws_before_it_interrupts(store: Store, recorder: Recorder) -> None:
    """ADR-M4-3's order, on a recording double. Reversed, it leaves a worker
    blocked until the 600 s timeout — which is the defect DP5 is about."""
    entered, release = threading.Event(), threading.Event()
    master = RecordingMaster(entered=entered, release=release, order=recorder.order)
    driver = a_driver(store, recorder, master)
    try:
        started = driver.send_turn("act")
        assert isinstance(started, TurnStarted)
        wait_for(entered, "the interrupted turn's runtime")
        recorder.order.clear()

        assert driver.interrupt_master() is True

        assert recorder.withdrawals == [started.turn_id]
        assert master.interrupts == 1
        # Order at the seam, not merely "both happened".
        assert recorder.order.index("withdraw") < recorder.order.index("interrupt")
    finally:
        release.set()
        finish(driver)

    # Nothing to interrupt once the turn is over, and it says so.
    assert driver.interrupt_master() is False


@dataclass
class Approval:
    """One pending approval, as much of T4's card as P-M4-22 needs.

    T4's `toolsurface/approvals.py` is not on this tree (§T27-1), so the store
    the withdrawal acts on is this file's own. The property is unchanged: the
    release is caused by the withdrawal and observed while `deadline_at` is
    still in the future.
    """

    deadline_at: float
    outcome: str | None = None
    resolved_at: float | None = None


class InjectedClock:
    """Monotonic seconds, advanced only when a check says so."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


def test_an_interrupt_withdraws_before_the_timeout(store: Store, recorder: Recorder) -> None:
    """P-M4-22: the release is the **withdrawal**, not the timeout in disguise.

    An injected clock that never advances past the deadline: if the only thing
    that could resolve the approval were the 600 s timeout, the outcome would
    still be `None` here.
    """
    clock = InjectedClock()
    pending = Approval(deadline_at=clock() + 600.0)
    released = threading.Event()

    def withdraw(turn_id: str) -> int:
        if pending.outcome is None:
            pending.outcome = "withdrawn"
            pending.resolved_at = clock()
            released.set()
            return 1
        return 0

    entered, release = threading.Event(), threading.Event()
    master = RecordingMaster(entered=entered, release=release)
    runtime: MasterRuntime = master
    driver = TurnDriver(
        store=store,
        build_master=lambda _turn_id: runtime,
        publish=recorder.publish,
        withdraw_turn_approvals=withdraw,
        now=lambda: TURN_OPENED,
    )
    try:
        assert isinstance(driver.send_turn("do the destructive thing"), TurnStarted)
        wait_for(entered, "the turn holding the approval")
        clock.seconds = 1.5  # a turn's worth of wall time, nowhere near 600 s
        # Read into a local: narrowing the attribute would make the assertions
        # after the interrupt unreachable under `mypy --strict`.
        outcome_before = pending.outcome
        assert outcome_before is None, "the approval resolved before anything asked it to"

        assert driver.interrupt_master() is True
        wait_for(released, "the withdrawal")
    finally:
        release.set()
        finish(driver)

    resolved_at = pending.resolved_at
    assert pending.outcome == "withdrawn"
    assert resolved_at is not None
    assert resolved_at < pending.deadline_at, (resolved_at, pending.deadline_at)
    # And the clock never reached the deadline at all, so "it timed out" is not
    # an available explanation for the release.
    assert clock() < pending.deadline_at


# ----- no loop, no thread, at boot --------------------------------------------


def test_the_driver_starts_no_loop_until_a_turn_runs(store: Store, recorder: Recorder) -> None:
    """ADR-M4-10: one loop per turn, on a thread torn down with the turn.

    Threads are compared as a **set of identities** taken before and after, so a
    thread that outlives the turn is red even when the count happens to match.
    """
    before = {thread.ident for thread in threading.enumerate()}

    entered, release = threading.Event(), threading.Event()
    master = RecordingMaster(entered=entered, release=release, events=(an_event("turn_ended"),))
    driver = a_driver(store, recorder, master)

    # Construction alone: no thread, no loop, and the runtime was never built.
    assert {thread.ident for thread in threading.enumerate()} == before
    assert master.loop_ids == set()
    assert master.sent == []
    assert not driver.is_running()

    try:
        assert isinstance(driver.send_turn("run"), TurnStarted)
        wait_for(entered, "the turn's runtime")
        during = {thread.ident for thread in threading.enumerate()}
        # Arrival: exactly one new thread, and it is running exactly one loop.
        assert len(during - before) == 1, sorted(str(ident) for ident in during - before)
        assert len(master.loop_ids) == 1
    finally:
        release.set()
        finish(driver)

    assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    assert {thread.ident for thread in threading.enumerate()} == before
    assert master.closed >= 1


def test_the_factory_is_handed_the_turn_it_is_building_for(
    store: Store, recorder: Recorder
) -> None:
    """RD-T4-2 / §T20-1 / §T21-1: the turn id reaches the thing that builds the
    runtime, so the approval key the runtime hands `invoke()` is the key
    `interrupt_master()` and `close()` withdraw by.

    **A wrong key fails silently** — every blocked handler rides its full 600 s
    while every test stays green — so this asserts the *identity* against the
    driver's own answer rather than against a shape. The alternative T21
    rejected (a `current_turn_id()` reader answering `str | None`) is what makes
    this the argument: a factory that is handed the id cannot be handed `None`.
    """
    asked: list[str] = []
    master = RecordingMaster()
    runtime: MasterRuntime = master

    def build(turn_id: str) -> MasterRuntime:
        asked.append(turn_id)
        return runtime

    driver = TurnDriver(
        store=store,
        build_master=build,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: TURN_OPENED,
    )

    started = driver.send_turn("go")

    assert isinstance(started, TurnStarted)
    finish(driver)
    # Identity, not shape: the id the driver reports is the id the factory saw,
    # and it saw exactly one — the factory is called once per turn.
    assert asked == [started.turn_id]
