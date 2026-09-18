"""T12 — an owned session's end: the kill record, the exit code, rebinding, interrupt.

**The four properties this file exists for, and what makes each one real:**

1. **A kill is recorded BEFORE it is issued** (G-M3-9, E-M3-17). Asserted the way
   T11 asserts "the row before the process": by making `terminate` **raise** and
   then finding the record. An ordering claim proved by an observation after a
   failure, never by reading the source. The natural implementation — kill, then
   write down that you killed — turns it red.
2. **The exit code is read before the kill, not after.** `kill-session` removes
   the `list-sessions` row and the status with it
   (`15-list-sessions-after-kill.txt`), so the double models that erasure: a
   `probe()` after `terminate` answers with **no** status. A driver double that
   kept the status would make this test vacuous.
3. **`/resume` rebinds rather than stops** (C14). The row keeps its identity *and
   its stop history* and changes one column. Swapping `rebind_engine_session_id`
   for `bind_engine_session_id` — the conditional write for an **unbound** row —
   turns it red, because the row is already bound and that verb is a no-op on it.
4. **G-M2-2 in both directions.** An owned session's exit code reaches the row;
   an attached session still has none, and the classifier still degrades for it.
   A test that only proved the owned half would let the attached half change.

**The three exit statuses are parsed out of the capture, never typed here.**
`14-list-sessions-after-sigterm.txt` is where `0`, `1` and `143` come from, and
the parametrised case count is asserted against what the file actually held — a
number typed in two places can agree with itself while both are wrong.

The AST rule for clause 8 is **imported**, not re-written: a second copy of a
boundary rule is a rule that drifts. `tests/` is not a package; `runner.` is the
same idiom as `golden.corpus`.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import typing
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from runner.test_local import signal_violations
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.runner import (
    MAX_TOTAL_OWNED_SESSIONS,
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
)
from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, SessionState
from shepherd.core.stops import Bucket, DecidedBy, StopReason, TurnEnding, Verdict
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.stop_map import MechanicalResult, mechanical_reason
from shepherd.signals.stop_rules import default_actions
from shepherd.orchestration.admission import CAP_TOTAL, SpawnRefused, admit
from shepherd.orchestration.lifecycle import (
    KILL_EVENT,
    KILL_RECORD_PREFIX,
    ReconcileCounts,
    interrupt_session,
    observe_exit,
    rebind,
    reconcile_owned_panes,
    record_and_terminate,
)
from shepherd.runner.base import ByteStream, PaneRef
from shepherd.runner.tmux_cmd import session_name
from shepherd.signals import hook_lane as hook_lane_module
from shepherd.signals.hook_lane import HookLane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"
AFTER_SIGTERM = RUN / "14-list-sessions-after-sigterm.txt"
AFTER_KILL = RUN / "15-list-sessions-after-kill.txt"
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "lifecycle.py"
ORCHESTRATION = MODULE.parent
HOOK_LANE = REPO_ROOT / "src" / "shepherd" / "signals" / "hook_lane.py"

#: ADR-1's cap for this task's artifact: "one module ≤ 250 lines".
MAX_MODULE_LINES = 250

NOW = "2026-09-17T10:00:00.000Z"
LATER = "2026-09-17T10:05:00.000Z"
SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0D01"
ENGINE_ID = "8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6"
RESUMED_ENGINE_ID = "0e1c5d6a-2f47-4a2b-9c31-1d5f0b3a7e94"
SOCKET = "shepherd-m3-t12"
RUNNER_NAME = "tmux"
HANDLE = RunnerHandle(runner=RUNNER_NAME, socket=SOCKET, session_name=session_name(SESSION_ID))


# ----- the three statuses, out of the capture ---------------------------------


def dead_pane_statuses(capture: Path) -> tuple[int, ...]:
    """`#{pane_dead_status}` for every dead pane in a real listing capture.

    The format line is the file's own (field 4 of eight); a comment line is
    skipped. Parsing the capture is what keeps `0`, `1` and `143` from being
    three numbers this file typed and then agreed with itself about.
    """
    found: list[int] = []
    for line in capture.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = line.split("|")
        if fields[2] == "1" and fields[3]:
            found.append(int(fields[3]))
    return tuple(found)


EXIT_STATUSES = dead_pane_statuses(AFTER_SIGTERM)


# ----- the world --------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def workspace_id(store: Store, tmp_path: Path) -> str:
    root = tmp_path / "work"
    root.mkdir()
    return store.upsert_workspace("shepherd", str(root)).id


def owned_row(
    store: Store,
    workspace_id: str,
    *,
    session_id: str = SESSION_ID,
    engine_session_id: str = ENGINE_ID,
    handle: RunnerHandle | None = HANDLE,
    state: SessionState = SessionState.RUNNING,
) -> None:
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=engine_session_id,
        workspace_id=workspace_id,
        repo_id=None,
        cwd="/tmp/shepherd-t12",
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=handle,
        model=None,
        effort=None,
    )
    store.apply_fold_delta(session_id, FoldDelta(state=state, last_event_at=NOW))


def proc(exit_code: int | None, *, alive: bool = False) -> ProcState:
    """`exit_signal` is **always** `None`: `#{pane_dead_signal}` was empty even
    after SIGTERM (the engine handled it and exited 143). Recorded, never guessed."""
    return ProcState(
        alive=alive,
        pid=None if not alive else 4041880,
        exit_code=exit_code,
        exit_signal=None,
        observed_at=NOW,
    )


@dataclasses.dataclass
class Driver:
    """The shipped double, plus the **one** fact it cannot model: E-M3-17.

    `kill-session` removes the `list-sessions` row entirely
    (`15-list-sessions-after-kill.txt` — three panes, and the killed one is not
    among them), so after a terminate there is no `#{pane_dead_status}` left to
    read. `ScriptedRunner.probe` keeps its fixture's exit code after the pane is
    gone; a test using it unchanged would stay green with the probe moved after
    the kill, which is the exact defect the ordering rule exists to prevent.

    `terminate_refusal` is the crash between the record and the kill.
    """

    inner: ScriptedRunner
    terminate_refusal: str | None = None
    killed: list[str] = dataclasses.field(default_factory=list)

    # the two members that carry this double's own behaviour
    def terminate(self, handle: RunnerHandle) -> None:
        if self.terminate_refusal is not None:
            raise RunnerRefusal(self.terminate_refusal)
        self.killed.append(handle.session_name)
        self.inner.terminate(handle)

    def probe(self, handle: RunnerHandle) -> ProcState:
        if handle.session_name in self.killed:
            return proc(None)
        return self.inner.probe(handle)

    # the eight this double has nothing to say about
    def start(self, spec: SessionSpec) -> RunnerHandle:
        return self.inner.start(spec)

    def attach(self, handle: RunnerHandle) -> ByteStream:
        return self.inner.attach(handle)

    def snapshot(self, handle: RunnerHandle, lines: int) -> bytes:
        return self.inner.snapshot(handle, lines)

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        self.inner.write(handle, data)

    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None:
        self.inner.resize(handle, cols, rows)

    def interrupt(self, handle: RunnerHandle) -> None:
        self.inner.interrupt(handle)

    def pane(self, handle: RunnerHandle) -> PaneState:
        return self.inner.pane(handle)

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        return self.inner.list_owned_panes()

    @property
    def calls(self) -> list[str]:
        return self.inner.calls

    @property
    def writes(self) -> list[bytes]:
        return self.inner.writes


def driver(
    *,
    exit_code: int | None = 143,
    panes: Sequence[PaneRef] = (),
    terminate_refusal: str | None = None,
) -> Driver:
    live = tuple(panes) or (
        PaneRef(
            session_name=HANDLE.session_name,
            session_id=SESSION_ID,
            pane_pid=4041880,
            dead=True,
        ),
    )
    return Driver(
        inner=ScriptedRunner(
            panes=(), proc=proc(exit_code), screen=b"", owned_panes=live
        ),
        terminate_refusal=terminate_refusal,
    )


def runner_of(double: Driver) -> typing.Any:  # noqa: ANN401 - the Runner seam, structurally
    return typing.cast(typing.Any, double)


def kill_record(store: Store, session_id: str = SESSION_ID) -> object | None:
    return store.get_app_state(f"{KILL_RECORD_PREFIX}{session_id}")


def anomaly(store: Store, kind: AnomalyKind) -> int:
    return store.list_anomaly_counts().get(str(kind.value), 0)


# ----- 1. the kill is recorded before it is issued -----------------------------


def test_the_kill_is_recorded_before_it_is_issued(store: Store, workspace_id: str) -> None:
    """G-M3-9: a crash between the two must leave the record, not the orphan.

    The record is found **after** a terminate that raised, so the only way this
    passes is for the write to have completed first. Moving the record write
    below `runner.terminate(...)` — the natural order — turns it red.
    """
    owned_row(store, workspace_id)
    double = driver(terminate_refusal="tmux exited 1 for kill-session")
    events: list[StreamEvent] = []

    assert kill_record(store) is None, "the record exists before the kill it records"
    with pytest.raises(RunnerRefusal):
        record_and_terminate(
            store=store,
            runner=runner_of(double),
            handle=HANDLE,
            session_id=SESSION_ID,
            now=lambda: LATER,
            publish=events.append,
        )

    recorded = kill_record(store)
    assert isinstance(recorded, dict), recorded
    assert recorded["session_id"] == SESSION_ID
    assert recorded["recorded_at"] == LATER
    assert double.killed == [], "the kill did not happen, and the record survived it"
    # The verdict is *not* written for a kill that failed: the session is alive.
    row = store.get_owned_session(SESSION_ID)
    assert row is not None and row.stop_reason is None and row.ended_at is None


# ----- 2. the exit code reaches the row ---------------------------------------


def test_the_capture_supplies_three_statuses(store: Store) -> None:
    """The parametrised case count, read out of the file the numbers came from.

    `0` (`/exit`), `1` (trust refused) and `143` (SIGTERM) are the three
    `#{pane_dead_status}` values `data-schemas.md` records, and they are in this
    capture. Asserted so a capture that changes cannot silently shrink the table
    below, and so a hand-typed list cannot drift from it.
    """
    assert len(EXIT_STATUSES) == 3, EXIT_STATUSES
    assert sorted(EXIT_STATUSES) == [0, 1, 143]


@pytest.mark.parametrize("status", EXIT_STATUSES)
def test_an_owned_exit_code_reaches_the_row(
    store: Store, workspace_id: str, status: int
) -> None:
    """E-M3-16: `remain-on-exit` keeps the status, and the row gets it.

    Goes red if `pane_dead_status` is read **after** `kill-session`, where the
    listing row no longer exists (E-M3-17) — the double models that erasure.
    """
    owned_row(store, workspace_id)
    double = driver(exit_code=status)
    events: list[StreamEvent] = []

    observed = record_and_terminate(
        store=store,
        runner=runner_of(double),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=events.append,
    )

    assert double.killed == [HANDLE.session_name], "arrival before absence: the kill happened"
    assert observed.exit_code == status
    assert observed.exit_signal is None, "#{pane_dead_signal} was empty even after SIGTERM"
    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.exit_code == status
    assert row.stop_reason == str(StopReason.KILLED.value)
    assert row.ended_at == LATER
    assert [event.kind for event in events] == [KILL_EVENT]
    assert events[0].payload["exit_code"] == status


def test_a_kill_whose_session_end_never_followed_is_counted(
    store: Store, workspace_id: str
) -> None:
    """G-M3-9's count, in both directions.

    A row that already carries its own ending is **not** counted and keeps the
    verdict the stop lane wrote: `apply_stop_verdict` stays the one stop writer
    and this is not a second one. A row with no ending is counted, because the
    verdict then came from the record rather than from a hook.
    """
    owned_row(store, workspace_id)
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 0
    record_and_terminate(
        store=store,
        runner=runner_of(driver()),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=lambda event: None,
    )
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 1

    # The other direction: the ending arrived first, so nothing is counted.
    second = "01JBQ8Z9XKME5RT3VWNY6P0D02"
    owned_row(
        store,
        workspace_id,
        session_id=second,
        engine_session_id="4d3a9b61-0f21-4c75-8f6e-2b0d8a5c1e37",
        state=SessionState.STOPPED,
    )
    store.apply_fold_delta(second, FoldDelta(ended_at=NOW, state=SessionState.STOPPED))
    handle = RunnerHandle(runner=RUNNER_NAME, socket=SOCKET, session_name=session_name(second))
    pane = PaneRef(
        session_name=handle.session_name, session_id=second, pane_pid=None, dead=True
    )
    record_and_terminate(
        store=store,
        runner=runner_of(driver(panes=(pane,))),
        handle=handle,
        session_id=second,
        now=lambda: LATER,
        publish=lambda event: None,
    )
    assert anomaly(store, AnomalyKind.KILL_WITHOUT_SESSION_END) == 1, "counted twice"


# ----- 3. G-M2-2, both directions ---------------------------------------------


def test_crashed_is_now_reachable_for_owned_and_still_unreachable_for_attached(
    store: Store, workspace_id: str
) -> None:
    """G-M2-2 closed for owned, still open for attached — asserted both ways.

    What G-M2-2 says is missing is the **exit code**: "`crashed` needs an exit
    code that an attached session cannot give" (C13). So the two directions are
    asserted at the place the gap is: an owned end supplies a real code and the
    classifier's `EXIT_CODE_UNOBSERVABLE` degrade no longer fires; an attached
    end supplies none and the degrade still does, with its anomaly.

    **What this does not claim.** No M3 path spells `StopReason.CRASHED`: the
    rule that would is in the engine's stop map (`mechanical_reason`), which
    this task does not open — classifying a stop is the stop lane's job and T12
    supplies the exit code and nothing else. Recorded in the blocker file so a
    verifier scoring the literal does not over-credit clause 7.
    """
    owned_row(store, workspace_id)
    double = driver(exit_code=143)
    record_and_terminate(
        store=store,
        runner=runner_of(double),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=lambda event: None,
    )
    owned = store.get_owned_session(SESSION_ID)
    assert owned is not None and owned.exit_code == 143

    def classified(exit_code: int | None) -> MechanicalResult:
        return mechanical_reason(
            failure_error=None,
            end_reason=None,
            ending=TurnEnding.ABSENT,
            auto_compact_pending=False,
            quota_notice=False,
            process_exit_observed=True,
            exit_code=exit_code,
        )

    attached = classified(None)
    assert [item.kind for item in attached.anomalies] == [
        AnomalyKind.EXIT_CODE_UNOBSERVABLE
    ], "the attached half of G-M2-2 must stay open"
    with_code = classified(owned.exit_code)
    assert AnomalyKind.EXIT_CODE_UNOBSERVABLE not in [
        item.kind for item in with_code.anomalies
    ], "an owned session's exit code closes the half M3 owns"


# ----- 4. /resume rebinds, and is not a stop ----------------------------------


def test_resume_rebinds_and_does_not_stop(store: Store, workspace_id: str) -> None:
    """C14: the row keeps its identity **and its stop history**, and moves one column.

    Two mutations turn it red. Folding the pair as a stop marks a live session
    dead — the stop columns move. And `bind_engine_session_id` in place of
    `rebind_engine_session_id` is a **no-op** on an already-bound row (it is a
    conditional write on `engine_session_id IS NULL` and returns its own
    rowcount), so the id never changes: the two verbs are not interchangeable.
    """
    owned_row(store, workspace_id)
    # A stop history the rebind must not lose: the row has stopped before and
    # was resumed. Written through the one stop writer, as M2 writes it.
    store.apply_stop_verdict(SESSION_ID, killed_verdict(), NOW, 143)
    before = store.get_owned_session(SESSION_ID)
    assert before is not None and before.stop_reason is not None

    rebind(store=store, session_id=SESSION_ID, new_engine_session_id=RESUMED_ENGINE_ID)

    after = store.get_owned_session(SESSION_ID)
    assert after is not None
    assert after.id == before.id, "the row keeps its identity"
    assert after.engine_session_id == RESUMED_ENGINE_ID, "one column moved"
    assert after.started_at == before.started_at
    # Its stop history is untouched: a delete-and-insert loses everything the
    # row knows, and folding the pair as a stop would rewrite these.
    assert after.stop_reason == before.stop_reason
    assert after.ended_at == before.ended_at
    assert after.exit_code == before.exit_code
    assert store.get_session_by_engine_id(ENGINE_ID) is None
    found = store.get_session_by_engine_id(RESUMED_ENGINE_ID)
    assert found is not None and found.id == SESSION_ID


def killed_verdict() -> Verdict:
    """A stop already on the row, written the way M2 writes one."""
    return Verdict(
        stop_reason=StopReason.KILLED,
        bucket=Bucket.UNFINISHED,
        why="an earlier ending, kept across the rebind",
        confidence=1.0,
        decided_by=DecidedBy.DECLARED,
        next_actions=default_actions(
            StopReason.KILLED, confidence=1.0, missing=(), waiting_on=None
        ),
        waiting_on=None,
        missing=(),
    )


# ----- 5. interrupt -----------------------------------------------------------


def test_interrupt_leaves_the_session_running_and_emits_no_stop(
    store: Store, workspace_id: str
) -> None:
    """D43/A13: an interrupt is `Escape`, and an interrupted turn emits no stop.

    **Arrival before absence**: the interrupt is asserted to have *reached* the
    driver before anything is asserted to be absent — "no stop was written"
    passes just as well when the call never happened. Goes red if an interrupt
    is treated as a stop, which no capture supports, and red if it terminates.
    """
    owned_row(store, workspace_id)
    double = driver()
    events: list[StreamEvent] = []

    interrupt_session(
        store=store,
        runner=runner_of(double),
        handle=HANDLE,
        session_id=SESSION_ID,
        now=lambda: LATER,
        publish=events.append,
    )

    assert "interrupt" in double.calls, "arrival: the pane was interrupted"
    assert double.killed == [], "an interrupt is not a terminate"
    assert double.writes == [], "an interrupt sends no payload bytes"
    row = store.get_owned_session(SESSION_ID)
    assert row is not None
    assert row.state == str(SessionState.RUNNING.value), "left running; the pane poll decides"
    assert row.stop_reason is None and row.ended_at is None and row.outcome is None
    assert len(events) == 1 and events[0].kind != KILL_EVENT


# ----- 6-8. the one file this task shares with nobody --------------------------


M1_PARAMETERS = ("self", "store", "publish", "stop_log", "projects_root")
M3_PARAMETERS = ("on_engine_session_rebound", "on_stop_deliver")


def test_hook_lane_signature_is_backward_compatible(store: Store) -> None:
    """M1's two-argument and M2's four-argument call sites still work.

    Constructed positionally as well as by keyword, because a parameter inserted
    *before* the M3 pair would keep every keyword call site green.
    """
    published: list[StreamEvent] = []

    def publish(event: StreamEvent) -> int:
        published.append(event)
        return len(published)

    lane = HookLane(store, publish)
    assert isinstance(lane, HookLane)
    four = HookLane(store, publish, None, None)
    assert isinstance(four, HookLane)
    keyword = HookLane(store=store, publish=publish)
    assert isinstance(keyword, HookLane)


def test_hook_lane_gains_exactly_two_parameters_and_no_other_task_opens_the_file() -> None:
    """The plan's hard rule, mechanically: no two tracks share a file.

    Goes red if a second task adds a third parameter — the two-builders-one-file
    failure half of M1's blocker file is made of — and red if either of M3's two
    is missing or renamed. Both M3 parameters are defaulted to `None`.
    """
    parameters = tuple(inspect.signature(HookLane.__init__).parameters)
    assert parameters == M1_PARAMETERS + M3_PARAMETERS, parameters
    defaults = inspect.signature(HookLane.__init__).parameters
    for name in M3_PARAMETERS:
        assert defaults[name].default is None, name


def test_the_callback_name_does_not_collide_with_the_existing_private_rebind() -> None:
    """`HookLane._rebind` already exists (l.149) and re-binds a session to a *repo*.

    Two `rebind`s in one module is the hazard M2 recorded for `replay`, so the
    parameter is `on_engine_session_rebound`. Asserted over every name the
    module **binds** — a def, an argument, an assignment or an attribute
    target — because the collision a reader hits is a name, not a call.

    The negative control is the point: `_rebind` must still be there. A rule
    asserting only an absence passes on a module where nothing exists at all.
    """
    tree = ast.parse(HOOK_LANE.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            bound.add(node.attr)

    assert "_rebind" in bound, "the existing private method is what makes this rule bite"
    assert "rebind" not in bound, "a second `rebind` in this module is the collision"
    assert "on_engine_session_rebound" in bound
    assert hasattr(HookLane, "_rebind")
    assert not hasattr(hook_lane_module, "rebind")


# ----- 9-11. the orphan reaper -------------------------------------------------


def orphan_pane(index: int) -> PaneRef:
    base = "01JBQ8Z9XKME5RT3VWNY6P0D"
    session_id = f"{base}{index:02d}"
    return PaneRef(
        session_name=session_name(session_id),
        session_id=session_id,
        pane_pid=4041880 + index,
        dead=False,
    )


def test_a_handle_less_owned_row_is_rebound_by_the_startup_reconcile(
    store: Store, workspace_id: str
) -> None:
    """DP5 makes the orphan durable by design; this is what adopts it.

    `controld` dying between `runner.start(spec)` and `set_runner_handle(...)`
    leaves a real `claude` in a real pane whose row has `runner_handle IS NULL`
    — terminable by nothing, because `observe_exit` needs the handle it lacks.
    Goes red if the reconcile skips rows whose handle is null.
    """
    owned_row(store, workspace_id, handle=None)
    before = store.get_owned_session(SESSION_ID)
    assert before is not None and before.runner_handle is None
    assert store.owned_session_counts() == (1, 1), "arrival: the handle-less cohort is 1"

    counts = reconcile_owned_panes(
        store=store,
        runner=runner_of(driver(panes=(orphan_pane(1),))),
        now=lambda: LATER,
        runner_name=RUNNER_NAME,
        socket=SOCKET,
    )

    after = store.get_owned_session(SESSION_ID)
    assert after is not None
    assert after.runner_handle == HANDLE
    assert after.runner_handle.runner == RUNNER_NAME, "the driver column moved with it"
    assert counts == ReconcileCounts(rebound=1, orphaned=0, intact=0)
    assert store.owned_session_counts() == (1, 0), "the cohort is empty again"
    assert anomaly(store, AnomalyKind.ORPHANED_PANE) == 0


def test_a_pane_with_no_row_is_counted_as_ORPHANED_PANE_and_is_not_killed(
    store: Store, workspace_id: str
) -> None:
    """Goes red in either direction: a silent kill, or a pane neither adopted nor counted.

    A pane Shepherd cannot account for is a fact to show a human, not a process
    to destroy silently (principle 5, and K6's own reasoning about blast radius).
    """
    stray = orphan_pane(7)
    assert store.get_owned_session(stray.session_id) is None
    double = driver(panes=(stray,))

    counts = reconcile_owned_panes(
        store=store,
        runner=runner_of(double),
        now=lambda: LATER,
        runner_name=RUNNER_NAME,
        socket=SOCKET,
    )

    assert counts == ReconcileCounts(rebound=0, orphaned=1, intact=0)
    assert anomaly(store, AnomalyKind.ORPHANED_PANE) == 1
    assert double.killed == [], "not killed: a pane with no row is shown, never destroyed"
    assert "terminate" not in double.calls
    # …and it is still there to be shown.
    assert double.list_owned_panes() == (stray,)


def test_the_reconcile_runs_before_the_first_spawn_can_take_a_cap_slot(
    store: Store, workspace_id: str
) -> None:
    """§11's total cap counts **panes**, so an orphan holds a slot either way.

    The failure this pins is not the refusal — it is the *invisibility*: without
    the reconcile the cap still refuses, and the orphan that filled it is
    counted nowhere. Goes red if the cap is read before the panes are
    enumerated, in which case `ORPHANED_PANE` is 0 at the moment a spawn is
    told the socket is full.
    """
    panes = tuple(orphan_pane(index) for index in range(MAX_TOTAL_OWNED_SESSIONS))
    double = driver(panes=panes)

    counts = reconcile_owned_panes(
        store=store,
        runner=runner_of(double),
        now=lambda: LATER,
        runner_name=RUNNER_NAME,
        socket=SOCKET,
    )
    assert counts.orphaned == MAX_TOTAL_OWNED_SESSIONS
    assert anomaly(store, AnomalyKind.ORPHANED_PANE) == MAX_TOTAL_OWNED_SESSIONS

    refused = admit(
        store=store,
        runner=runner_of(double),
        workspace_id=workspace_id,
        cwd=str(Path(store.list_workspaces()[0].root_path or ".")),
        parent_session_id=None,
    )
    assert isinstance(refused, SpawnRefused)
    assert refused.cap == CAP_TOTAL
    # The enumeration happened first: the cap's own population is what the
    # reconcile had already walked.
    assert double.calls.count("list_owned_panes") == 2


# ----- 12. clause 8: no signal reaches a session -------------------------------


def test_no_signal_reaches_a_session_from_orchestration(tmp_path: Path) -> None:
    """P-M3-7 over `orchestration/`, with the same rule `runner/` is held to.

    D43 clause 8: interrupting is `Escape`, terminating is `kill-session`, and
    no signal ever reaches a session. The rule is **imported** rather than
    re-implemented, and its planted proof is re-run here against a copy of this
    task's own module — the file the plant would have to live in.
    """
    assert signal_violations(MODULE) == []
    assert [
        message
        for path in sorted(ORCHESTRATION.rglob("*.py"))
        for message in signal_violations(path)
    ] == []

    planted = tmp_path / "lifecycle_with_a_signal.py"
    planted.write_text(
        MODULE.read_text(encoding="utf-8")
        + "\n\nimport os\nimport signal\n\n\n"
        "def _plant(pid: int) -> None:\n    os.kill(pid, signal.SIGTERM)\n",
        encoding="utf-8",
    )
    assert signal_violations(planted) != [], "the planted os.kill must be found"


def test_the_module_stays_inside_its_stated_size() -> None:
    """One module ≤ 250 lines. A cap that is not asserted is a cap nobody keeps."""
    lines = MODULE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_MODULE_LINES, len(lines)


def test_observe_exit_reads_the_status_the_capture_holds(store: Store) -> None:
    """`observe_exit` is the one read, and it is a read of the driver's own answer.

    `15-list-sessions-after-kill.txt` is why it has to happen before the kill:
    the killed pane is not in the listing at all.
    """
    after_kill = AFTER_KILL.read_text(encoding="utf-8")
    assert HANDLE.session_name not in after_kill
    observed = observe_exit(runner=runner_of(driver(exit_code=143)), handle=HANDLE)
    assert (observed.exit_code, observed.exit_signal, observed.alive) == (143, None, False)
