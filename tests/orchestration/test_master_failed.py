"""qa6 rulings P6 / H3 (ruling 12, D79, ADR-QR-3) — a failed master turn is
counted and audited.

**Two seams, both the plan's.** The orchestration seam drives `TurnDriver`
over a real `Store` in `tmp_path`, with a `record_failure` double that bumps the
real counter the way the composition's recorder does — so "counted once" is
read off `list_anomaly_counts()`, not off the double. The L4 seam drives
`registry.audit_master_failure` against an installed chokepoint whose sink
records, with the shipped `master_send` `ToolDef` registered by the shipped
registrar, so the record's blast class is that tool's own and not a literal.

PP10 is the property: `master_failed` is bumped exactly once per failed turn.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytest

from shepherd.core.master import MasterRuntime
from shepherd.orchestration.master_turn import TurnDriver, TurnRefused, TurnStarted
from shepherd.store.db import Store
from shepherd.toolsurface import registry
from shepherd.toolsurface.approvals import ApprovalStore
from shepherd.toolsurface.tools_master import register_master_tools
from shepherd.toolsurface.types import (
    ActorKind,
    AuditRecord,
    AuthzOutcome,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolDef,
)

from .test_master_turn import (  # noqa: F401 — `recorder` and `store` are fixtures
    ARRIVAL_TIMEOUT_S,
    TURN_OPENED,
    Recorder,
    RecordingMaster,
    an_event,
    finish,
    plant_a_waking_stop,
    recorder,
    store,
)

#: D79's wire value, typed from the spec rather than read off the enum.
MASTER_FAILED = "master_failed"

#: A message only this file could have produced. It must reach nothing: an
#: exception message can carry prompt text or a credential (D79).
SECRET = "QA6-P6-SECRET-sk-ant-THE-PROMPT-TEXT"


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    registry.reset_registry()
    yield
    registry.reset_registry()


@dataclass
class FailureLog:
    """The composition's recorder, in miniature: it bumps the real counter."""

    store: Store
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, turn_id: str, error_class: str) -> None:
        self.calls.append((turn_id, error_class))
        self.store.bump_anomaly(MASTER_FAILED)


def counted(store: Store) -> int:
    return store.list_anomaly_counts().get(MASTER_FAILED, 0)


def a_driver(
    store: Store, recorder: Recorder, log: FailureLog, *script: RecordingMaster | Exception
) -> TurnDriver:
    """The n-th turn gets the n-th entry; an exception entry is raised by the factory."""
    queue = list(script)

    def build(_turn_id: str) -> MasterRuntime:
        entry = queue.pop(0)
        if isinstance(entry, Exception):
            raise entry
        runtime: MasterRuntime = entry
        return runtime

    return TurnDriver(
        store=store,
        build_master=build,
        publish=recorder.publish,
        withdraw_turn_approvals=recorder.withdraw,
        now=lambda: TURN_OPENED,
        record_failure=log,
    )


# ----- the orchestration seam -------------------------------------------------


def test_a_turn_that_fails_to_open_counts_master_failed_once(
    store: Store, recorder: Recorder
) -> None:
    """Arrival first: the counter is zero, and a turn that opens counts nothing.
    Then one failed open is one bump, carrying the class name alone."""
    log = FailureLog(store)
    fine = RecordingMaster(events=(an_event("turn_ended"),))
    driver = a_driver(store, recorder, log, fine, RuntimeError(SECRET))
    try:
        assert counted(store) == 0
        assert isinstance(driver.send_turn("a turn that opens"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
        assert counted(store) == 0, "a turn that ran was counted as failed"

        refused = driver.send_turn("the turn that cannot open")
        assert isinstance(refused, TurnRefused)
    finally:
        finish(driver)

    assert counted(store) == 1
    assert len(log.calls) == 1
    turn_id, error_class = log.calls[0]
    assert turn_id in refused.reason, "the recorded turn is not the one refused"
    assert error_class == "RuntimeError"


def test_a_wake_turn_that_fails_to_open_counts_once_and_frees_the_slot(
    store: Store, recorder: Recorder
) -> None:
    """E-QR-8: the wake's open fails → `master_failed` +1, the slot freed, and
    the set not consumed (the runtime is built before the drain, BC-08)."""
    from shepherd.orchestration.wake import peek

    plant_a_waking_stop(store)
    assert peek(store), "arrival: there is something to wake for"
    log = FailureLog(store)
    driver = a_driver(store, recorder, log, OSError(SECRET))

    assert driver.wake_turn() is None
    assert not driver.is_running(), "a failed wake kept the slot"
    assert counted(store) == 1
    assert [error_class for _, error_class in log.calls] == ["OSError"]
    assert peek(store), "a wake that never opened consumed the set"


def test_a_turn_that_raises_counts_master_failed_once(store: Store, recorder: Recorder) -> None:
    """The mid-run path: the runtime raises inside the turn. Counted before the
    slot is released, so a caller woken by the turn's end reads the count."""
    log = FailureLog(store)
    boom = RecordingMaster(raises=ValueError(SECRET))
    driver = a_driver(store, recorder, log, boom)
    try:
        started = driver.send_turn("the turn that raises")
        assert isinstance(started, TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
        assert boom.sent == ["the turn that raises"], "arrival: the turn really ran"
        assert counted(store) == 1
    finally:
        finish(driver)
    assert log.calls == [(started.turn_id, "ValueError")]
    assert counted(store) == 1


# ----- the L4 seam: the record ------------------------------------------------


def _allow(tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> AuthzOutcome:
    return AuthzOutcome(allowed=True, reason=None, approved_by=None, approval_id=None)


def register_the_shipped_master_tools(store: Store, tmp_path: Path) -> None:
    register_master_tools(
        store=store,
        approvals=ApprovalStore(now=lambda: TURN_OPENED),
        audit_root=tmp_path / "audit",
        send_turn=lambda text: TurnRefused(reason="unused"),
        interrupt_master=lambda: False,
        now=lambda: TURN_OPENED,
    )


def test_the_failure_audit_record_carries_the_class_name_and_no_message(
    store: Store, tmp_path: Path
) -> None:
    """ADR-QR-3's record, field by field, each value typed from the ADR."""
    register_the_shipped_master_tools(store, tmp_path)
    records: list[AuditRecord] = []
    registry.install_chokepoint(_allow, records.append)

    registry.audit_master_failure("01TURNP6FAILED", "RuntimeError")

    assert len(records) == 1
    record = records[0]
    assert record.tool == "master_send"
    assert record.blast_class is BlastClass.LOCAL_WRITE
    assert record.actor_kind is ActorKind.MASTER
    assert record.actor_id == "master"
    assert record.decision == "allow"
    assert record.result == "failed"
    assert record.failure is Failure.FAILED
    assert dict(record.args) == {"turn_id": "01TURNP6FAILED", "error_class": "RuntimeError"}
    assert record.autonomy_level == registry.UNREPORTED_AUTONOMY_LEVEL
    assert record.approved_by is None and record.approval_id is None
    assert record.correlation_id == "01TURNP6FAILED"
    assert record.duration_ms == 0
    assert record.at, "the record is not stamped"


def test_a_raising_turn_hands_the_recorder_no_message(store: Store, recorder: Recorder) -> None:
    """The driver hands on the class name only, so the message never reaches the
    recorder — and therefore never the record built from what it is handed."""
    log = FailureLog(store)
    driver = a_driver(store, recorder, log, RuntimeError(SECRET), RecordingMaster(
        raises=KeyError(SECRET)
    ))
    try:
        assert isinstance(driver.send_turn("open fails"), TurnRefused)
        assert isinstance(driver.send_turn("run fails"), TurnStarted)
        assert driver.wait_for_turn(ARRIVAL_TIMEOUT_S)
    finally:
        finish(driver)
    assert [error_class for _, error_class in log.calls] == ["RuntimeError", "KeyError"]
    assert SECRET not in json.dumps(log.calls)


def test_no_chokepoint_means_no_record_and_no_raise(store: Store, tmp_path: Path) -> None:
    """DP13's shape: no sink, nothing to write to. Arrival first: with the pair
    installed the same call writes one record; cleared, it writes none and
    raises nothing."""
    register_the_shipped_master_tools(store, tmp_path)
    records: list[AuditRecord] = []
    registry.install_chokepoint(_allow, records.append)
    registry.audit_master_failure("01TURNP6ARRIVAL", "RuntimeError")
    assert [asdict(r)["correlation_id"] for r in records] == ["01TURNP6ARRIVAL"]

    registry.reset_registry()
    assert registry.chokepoint() is None

    assert registry.audit_master_failure("01TURNP6NOSINK", "RuntimeError") is None
    assert len(records) == 1
