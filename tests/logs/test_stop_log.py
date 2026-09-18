"""The versioned stop record and its codec (T5, `logs/stops.py`).

D25 makes this log the truth `replay` reads, for 90 days, across rule changes
and code changes — so the record is **versioned**, and a reader meeting a
version it does not know **skips and counts** rather than parsing optimistically
(ADR-M2-6 / E-M2-21). Half-parsing an old record produces a confident wrong
verdict, which is worse than no verdict at all.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

from shepherd.core.stops import (
    STOP_RECORD_VERSION,
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopEvidence,
    StopReason,
    ToolFailure,
    ToolUseRef,
    TranscriptTail,
    TurnEnding,
    Verdict,
)
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import (
    StopLog,
    date_of,
    decode_stop_evidence,
    decode_verdict,
    encode_stop_record,
    read_stop_records,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: T5-5. `tests/boundaries/` is a rootdir-relative package-less directory, so
#: `_imports` is importable there and nowhere else by default. This is the one
#: import of it from outside, and it is deliberate: the alternative is a second
#: implementation of DP3's rule, which is what this file used to hold.
_BOUNDARY_DIR = Path(__file__).resolve().parents[1] / "boundaries"


def _boundary_rules() -> ModuleType:
    if str(_BOUNDARY_DIR) not in sys.path:
        sys.path.insert(0, str(_BOUNDARY_DIR))
    return importlib.import_module("_imports")

FULL_TAIL = TranscriptTail(
    ending=TurnEnding.ENDED_TURN,
    last_assistant_text="I'll run the tests now.",
    entry_count=17,
    tool_uses=(ToolUseRef("toolu_01", "Bash", 3), ToolUseRef("toolu_02", "Write", 9)),
    failures=(ToolFailure("toolu_01", "Bash", 4), ToolFailure(None, None, 11)),
    promise_followed_by_tool_use=False,
    skipped_lines=2,
    truncated=True,
)

EMPTY_TAIL = TranscriptTail(
    ending=TurnEnding.ABSENT,
    last_assistant_text=None,
    entry_count=0,
    tool_uses=(),
    failures=(),
    promise_followed_by_tool_use=None,
    skipped_lines=0,
    truncated=False,
)

EVIDENCE = StopEvidence(
    record_version=STOP_RECORD_VERSION,
    session_id="01JBXQ8Z5V",
    engine_session_id="e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
    received_at="2026-09-17T01:04:18.671Z",
    mechanical=StopReason.RATE_LIMITED,
    mechanical_detail="the engine reported 'rate_limit'",
    tail=FULL_TAIL,
    tasks_total=3,
    tasks_done=1,
    brief="write the migration",
    auto_compact_pending=True,
    quota_notice=False,
    process_exit_observed=True,
    exit_code=None,
)

BARE = StopEvidence(
    record_version=STOP_RECORD_VERSION,
    session_id="01BARE",
    engine_session_id=None,
    received_at="2026-09-17T01:04:18.671Z",
    mechanical=None,
    mechanical_detail=None,
    tail=EMPTY_TAIL,
    tasks_total=0,
    tasks_done=0,
    brief=None,
    auto_compact_pending=False,
    quota_notice=False,
    process_exit_observed=False,
    exit_code=7,
)

VERDICT = Verdict(
    stop_reason=StopReason.INCOMPLETE,
    bucket=Bucket.UNFINISHED,
    why="tasks still open at the stop",
    confidence=0.8,
    decided_by=DecidedBy.HEURISTIC,
    next_actions=(
        NextAction("Requeue: tasks still open", NextActionKind.REQUEUE, None, ActionSource.HEURISTIC),
        NextAction("Chase it", NextActionKind.EXTERNAL, "https://x.invalid", ActionSource.HEURISTIC),
    ),
    waiting_on=None,
    missing=("tasks still open at the stop",),
)

BARE_VERDICT = Verdict(
    stop_reason=StopReason.COMPLETED,
    bucket=Bucket.FINISHED,
    why="no open tasks",
    confidence=0.5,
    decided_by=DecidedBy.HEURISTIC,
    next_actions=(),
    waiting_on=None,
    missing=(),
)


def test_the_version_is_the_first_key(tmp_path: Path) -> None:
    """ADR-M2-6 — a reader must be able to decide *before* it parses."""
    record = encode_stop_record(EVIDENCE, VERDICT)
    assert next(iter(record)) == "record_version"
    assert record["record_version"] == STOP_RECORD_VERSION
    assert json.dumps(record).startswith('{"record_version":')


def test_record_roundtrips() -> None:
    """Field by field, never `==` on a dict: a dict comparison passes while a
    field silently changes type, and `replay` reads these months later."""
    for evidence, verdict in ((EVIDENCE, VERDICT), (BARE, BARE_VERDICT)):
        record = json.loads(json.dumps(encode_stop_record(evidence, verdict)))
        back = decode_stop_evidence(record)

        assert back.record_version == evidence.record_version
        assert back.session_id == evidence.session_id
        assert back.engine_session_id == evidence.engine_session_id
        assert back.received_at == evidence.received_at
        assert back.mechanical == evidence.mechanical
        assert back.mechanical_detail == evidence.mechanical_detail
        assert back.tasks_total == evidence.tasks_total
        assert back.tasks_done == evidence.tasks_done
        assert back.brief == evidence.brief
        assert back.auto_compact_pending is evidence.auto_compact_pending
        assert back.quota_notice is evidence.quota_notice
        assert back.process_exit_observed is evidence.process_exit_observed
        assert back.exit_code == evidence.exit_code

        assert back.tail.ending is evidence.tail.ending
        assert back.tail.last_assistant_text == evidence.tail.last_assistant_text
        assert back.tail.entry_count == evidence.tail.entry_count
        assert back.tail.tool_uses == evidence.tail.tool_uses
        assert back.tail.failures == evidence.tail.failures
        assert (
            back.tail.promise_followed_by_tool_use
            is evidence.tail.promise_followed_by_tool_use
        )
        assert back.tail.skipped_lines == evidence.tail.skipped_lines
        assert back.tail.truncated is evidence.tail.truncated
        assert back == evidence

        restored = decode_verdict(record)
        assert restored.stop_reason is verdict.stop_reason
        assert restored.bucket is verdict.bucket
        assert restored.why == verdict.why
        assert restored.confidence == verdict.confidence
        assert restored.decided_by is verdict.decided_by
        assert restored.waiting_on == verdict.waiting_on
        assert restored.missing == verdict.missing
        assert restored.next_actions == verdict.next_actions
        assert restored == verdict


def test_an_empty_tuple_is_not_a_none(tmp_path: Path) -> None:
    """The two say different things — "no failures" and "we never looked" —
    and a codec that folds them loses the only distinction principle 5 has."""
    record = json.loads(json.dumps(encode_stop_record(BARE, BARE_VERDICT)))
    assert decode_stop_evidence(record).tail.failures == ()
    assert decode_stop_evidence(record).tail.promise_followed_by_tool_use is None


def test_a_written_record_is_read_back(tmp_path: Path) -> None:
    log = StopLog(RotatingJsonlLog(tmp_path, "stops"))
    assert log.append(EVIDENCE, VERDICT)
    assert log.append(BARE, BARE_VERDICT)
    log.close()

    found, stats = read_stop_records(tmp_path)
    assert [item.session_id for item in found] == ["01JBXQ8Z5V", "01BARE"]
    assert stats.records == 2
    assert stats.skipped_malformed == 0
    assert stats.skipped_version == 0


def test_the_daily_file_is_named_from_the_records_own_stamp(tmp_path: Path) -> None:
    """The date is **derived from the record**, never read from a clock: that
    is what makes two runs of the golden lane byte-identical."""
    assert date_of("2026-09-17T01:04:18.671Z") == "2026-09-17"
    assert date_of("not a stamp") is None

    log = StopLog(RotatingJsonlLog(tmp_path, "stops"))
    log.append(EVIDENCE, VERDICT)
    log.close()
    assert [path.name for path in (tmp_path / "stops").iterdir()] == ["2026-09-17.jsonl.gz"]


def test_a_record_with_an_unreadable_stamp_is_still_written(tmp_path: Path) -> None:
    """Losing the line would be the worse failure (C-M2-6). It goes to a file
    named for the unknown, so it is visible rather than silently dropped."""
    from dataclasses import replace

    log = StopLog(RotatingJsonlLog(tmp_path, "stops"))
    assert log.append(replace(EVIDENCE, received_at="???"), VERDICT)
    log.close()
    found, stats = read_stop_records(tmp_path)
    assert stats.records == 1
    assert found[0].received_at == "???"


def test_unknown_record_version_is_skipped_and_counted(tmp_path: Path) -> None:
    """E-M2-21 — never parsed optimistically. A future version may have
    re-meant a field this build would read with its old meaning.

    A record with **no** `record_version` is a different fact and gets the other
    counter: it is corruption, not skew. `47 unknown version` sends a human
    looking for a decoder to write; `47 malformed` sends them to triage, and
    only one of those is the work.
    """
    (tmp_path / "stops").mkdir(parents=True)
    good = encode_stop_record(EVIDENCE, VERDICT)
    future = dict(encode_stop_record(BARE, BARE_VERDICT))
    future["record_version"] = STOP_RECORD_VERSION + 1
    missing_version = dict(encode_stop_record(BARE, BARE_VERDICT))
    del missing_version["record_version"]
    not_a_version = dict(encode_stop_record(BARE, BARE_VERDICT))
    not_a_version["record_version"] = "1"
    (tmp_path / "stops" / "2026-09-17.jsonl").write_text(
        "\n".join(
            json.dumps(record) for record in (good, future, missing_version, not_a_version)
        )
        + "\n",
        encoding="utf-8",
    )

    found, stats = read_stop_records(tmp_path)
    assert [item.session_id for item in found] == ["01JBXQ8Z5V"]
    assert stats.records == 1
    assert stats.skipped_version == 1
    assert stats.skipped_malformed == 2


def test_a_malformed_line_is_skipped_and_counted_separately(tmp_path: Path) -> None:
    """Two different work items: a torn write, and a record from a build that
    knows something this one does not. One number for both tells `doctor`
    nothing it can act on."""
    (tmp_path / "stops").mkdir(parents=True)
    good = json.dumps(encode_stop_record(EVIDENCE, VERDICT))
    (tmp_path / "stops" / "2026-09-17.jsonl").write_text(
        good + '\n{"record_version": 1, "half', encoding="utf-8"
    )
    found, stats = read_stop_records(tmp_path)
    assert len(found) == 1
    assert stats.skipped_malformed == 1
    assert stats.skipped_version == 0


def test_a_record_whose_shape_is_wrong_is_counted_not_guessed(tmp_path: Path) -> None:
    """A version this build knows but a body it cannot read is still a skip:
    the alternative is a decoder inventing a `TurnEnding`."""
    (tmp_path / "stops").mkdir(parents=True)
    (tmp_path / "stops" / "2026-09-17.jsonl").write_text(
        json.dumps({"record_version": STOP_RECORD_VERSION, "evidence": {"tail": 3}}) + "\n",
        encoding="utf-8",
    )
    found, stats = read_stop_records(tmp_path)
    assert found == []
    assert stats.skipped_malformed == 1


def test_write_failure_never_loses_the_verdict(tmp_path: Path) -> None:
    """C-M2-6 — the log may never raise into the column write. The failure is
    injected with a parent that is a file, because these tests run as root and
    root ignores the mode bits a `chmod` would set."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    log = StopLog(RotatingJsonlLog(blocker / "under-a-file", "stops"))
    assert log.append(EVIDENCE, VERDICT) is False
    log.close()


def test_since_is_passed_through(tmp_path: Path) -> None:
    from dataclasses import replace

    log = StopLog(RotatingJsonlLog(tmp_path, "stops"))
    log.append(replace(EVIDENCE, received_at="2026-09-15T01:00:00.000Z"), VERDICT)
    log.append(EVIDENCE, VERDICT)
    log.close()
    found, stats = read_stop_records(tmp_path, since="2026-09-17")
    assert len(found) == 1
    assert stats.records == 1


def test_no_read_tool_touches_a_log_path() -> None:
    """P-M2-10 — D25's guardrail, and the one property that keeps the log a
    *log*. Nothing the UI renders may read one: the fleet page reads columns,
    `replay` reads the log, and the two never swap. Asserted at the import
    graph, which is the only place it cannot be worked around by a helper.

    **T5-5: the import half is no longer implemented here.** DP3 widened this
    rule to D25's own text — *exactly one* `toolsurface` module may import
    `shepherd.logs`, discovered by property as the module defining
    `build_audit_sink` — and T7 shipped that widening in
    `tests/boundaries/_imports.logs_importer_violations`, naming the single
    function it had widened *"so a later builder does not loosen two"*. It did
    not know this file held a **second, independent** copy of the same scan, so
    the copy stayed at M2's strictness and M4's audit writer failed it.

    Widening the copy would have been the second loosening T7 warned about, and
    two spellings of one boundary is the defect this milestone exists to refuse.
    So the copy is **deleted** and this check now calls the single
    implementation. The `read_stop_records` / `read_records` **call** half has
    no equivalent there and stays here, unchanged.
    """
    boundary = _boundary_rules()
    permitted = boundary.audit_writer_paths()
    # Arrival before absence: the discovery found a real module, and the scan
    # really does reach the three packages. An emptiness over a corpus of
    # nothing is the defect this repo keeps shipping.
    assert permitted, "no toolsurface module defines build_audit_sink"
    consumers = ("toolsurface", "web", "cli")
    offenders: list[str] = []
    scanned = 0
    for package in consumers:
        for path in sorted((SRC_ROOT / package).rglob("*.py")):
            scanned += 1
            offenders += boundary.logs_importer_violations(
                path, f"shepherd.{package}", permitted=permitted
            )
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else func.attr if isinstance(func, ast.Attribute) else ""
                    )
                    if name in {"read_stop_records", "read_records"}:
                        offenders.append(f"{package}/{path.name} calls {name}")
    assert scanned > 5
    assert offenders == []
    # …and the delegated half still bites, on the fixture T7 froze for it.
    leak = boundary.fixture("toolsurface_second_logs_importer.py")
    assert boundary.logs_importer_violations(
        leak, "shepherd.toolsurface", permitted=permitted
    ) != []
    assert boundary.logs_importer_violations(leak, "shepherd.web", permitted=permitted) != []


def test_the_read_tool_scan_knows_where_to_look() -> None:
    """The negative half: those three packages exist and were actually read."""
    scanned = [
        path for package in ("toolsurface", "web", "cli")
        for path in (SRC_ROOT / package).rglob("*.py")
    ]
    assert len(scanned) > 5
