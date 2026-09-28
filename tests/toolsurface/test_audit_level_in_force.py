"""BC-22: the audit record states the autonomy level the gate read (T6-3).

Integration seam: `invoke()`, with the **shipped** chokepoint — `build_authorizer`
over a real `ApprovalStore` — and the **shipped** sink, `build_audit_sink` over a
real `RotatingJsonlLog`, read back through `read_audit_records`. Nothing here
constructs an `AuditRecord` or calls the authorizer directly: the claim is about
the line on disk, and the line on disk is written by `invoke()` alone.

The level is `3` (and `2` on the card path) rather than the default so a record
that invented `2` cannot pass, and neither is `UNREPORTED_AUTONOMY_LEVEL`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from shepherd.core.clock import utc_now
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import date_of
from shepherd.toolsurface.approvals import ApprovalOutcome, ApprovalStore, build_authorizer
from shepherd.toolsurface.audit import AUDIT_PREFIX, build_audit_sink, read_audit_records
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import install_chokepoint, invoke, register
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolDef,
    ToolResult,
)

MASTER = CallerContext(audience=Audience.MASTER, caller_id="mst_01", correlation_id="cid-lvl")

OBJECT_SCHEMA: Mapping[str, object] = {"type": "object", "properties": {}}

WAIT_S = 5.0


def a_tool(name: str, blast_class: BlastClass) -> ToolDef:
    def echo(args: ToolArgs, ctx: CallerContext) -> object:
        return {"ran": name}

    return ToolDef(
        name=name,
        description=f"a {blast_class.value} capability",
        input_schema=OBJECT_SCHEMA,
        blast_class=blast_class,
        handler=echo,
        audiences=frozenset({Audience.MASTER}),
    )


@pytest.fixture()
def audit_log(tmp_path: Path) -> Iterator[RotatingJsonlLog]:
    log = RotatingJsonlLog(tmp_path, AUDIT_PREFIX)
    try:
        yield log
    finally:
        log.close()


def install_shipped_chokepoint(
    log: RotatingJsonlLog, store: ApprovalStore, level: AutonomyLevel
) -> None:
    install_chokepoint(
        build_authorizer(
            store=store,
            level=lambda: level,
            publish=lambda event: 0,
            bump=lambda kind: None,
            now=utc_now,
        ),
        build_audit_sink(log, lambda kind: None, date_of),
    )


def levels_on_disk(log: RotatingJsonlLog, root: Path) -> dict[object, object]:
    log.close()
    return {record["tool"]: record["autonomy_level"] for record in read_audit_records(root, 10)}


def test_the_audit_record_carries_the_level_the_gate_read(
    audit_log: RotatingJsonlLog, tmp_path: Path
) -> None:
    """Level 3: one gated call and one read call, both allowed without a card,
    and both records say `3` — the level `level()` answered, not a placeholder."""
    install_shipped_chokepoint(audit_log, ApprovalStore(), AutonomyLevel.LEVEL_3)
    register(a_tool("gated_kill", BlastClass.LOCAL_DESTRUCTIVE))
    register(a_tool("fleet_read", BlastClass.LOCAL_READ))

    assert invoke("gated_kill", {}, MASTER).ok is True
    assert invoke("fleet_read", {}, MASTER).ok is True

    assert levels_on_disk(audit_log, tmp_path) == {"gated_kill": 3, "fleet_read": 3}


def test_a_carded_call_records_the_level_it_was_carded_at(
    audit_log: RotatingJsonlLog, tmp_path: Path
) -> None:
    """Level 2: the master's destructive call raises a card; a click approves
    it. The second `AuthzOutcome` site — the one after the card — carries the
    level too, so the record says `2`."""
    store = ApprovalStore()
    install_shipped_chokepoint(audit_log, store, AutonomyLevel.LEVEL_2)
    register(a_tool("gated_kill", BlastClass.LOCAL_DESTRUCTIVE))
    answers: list[ToolResult] = []
    worker = threading.Thread(target=run_into(answers, "gated_kill"), daemon=True)
    worker.start()

    carded = wait_for_card(store)
    assert store.decide(carded, ApprovalOutcome.APPROVED) is True
    worker.join(WAIT_S)

    assert [answer.ok for answer in answers] == [True]
    assert levels_on_disk(audit_log, tmp_path) == {"gated_kill": 2}


def run_into(answers: list[ToolResult], name: str) -> Callable[[], None]:
    def call() -> None:
        answers.append(invoke(name, {}, MASTER))

    return call


def wait_for_card(store: ApprovalStore) -> str:
    """The card's id, once `authorize()` has raised it. Polls `pending()` on
    a short interval: the store has no public "a card was raised" signal."""
    for _ in range(int(WAIT_S / 0.01)):
        pending = store.pending()
        if pending:
            return pending[0].id
        time.sleep(0.01)
    raise AssertionError("no card was raised")
