"""T6 — `StopEvidence` assembly: the one place the three sources meet.

Stop metadata, the session's folded counters, and the neutral tail become one
immutable record (ADR-M2-1). The record is what goes to the log verbatim and
what `replay` reads back, so it has to be **complete at assembly**: a field a
rule wants later is a visible change to the record and its version, never a
silent new read.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.fold_types import SessionSnapshot
from shepherd.core.signals import Signal, SignalKind
from shepherd.core.states import SessionState
from shepherd.core.stops import STOP_RECORD_VERSION, StopEvidence, StopReason, TurnEnding
from shepherd.engines.claude_code import evidence as evidence_module
from shepherd.engines.claude_code.evidence import build_stop_evidence
from shepherd.signals.heuristics import is_promise

REPO_ROOT = Path(__file__).resolve().parents[2]
COPIES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "transcripts" / "copies"
A_REAL_TRANSCRIPT = COPIES / "-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl"

RECEIVED_AT = "2026-09-17T12:00:00Z"
ENGINE_SESSION_ID = "7c27bb7f-5390-48b0-8b2e-cf4004113d09"

#: The 33 engine event names and the engine field names this record must never
#: carry as a *value* (C-M2-5, P-M2-6).
ENGINE_WORDS = (
    "Stop",
    "StopFailure",
    "SessionEnd",
    "PreCompact",
    "PostCompact",
    "Notification",
    "hook_event_name",
    "stop_reason",
    "error_type",
    "end_reason",
    "start_reason",
    "transcript_path",
)


def projects_root(tmp_path: Path, transcript: Path | None = A_REAL_TRANSCRIPT) -> Path:
    """A `projects/<slug>/<sessionId>.jsonl` tree holding one real transcript."""
    root = tmp_path / "projects"
    directory = root / "-a-lossy-slug"
    directory.mkdir(parents=True, exist_ok=True)
    if transcript is not None:
        (directory / f"{ENGINE_SESSION_ID}.jsonl").write_bytes(transcript.read_bytes())
    return root


def snapshot(**overrides: object) -> SessionSnapshot:
    fields: dict[str, object] = {
        "session_id": "01SESSION",
        "engine_session_id": ENGINE_SESSION_ID,
        "state": SessionState.RUNNING,
        "last_event_at": "2026-09-17T11:59:00Z",
        "observed_at": None,
        "needs_you_reason": None,
        "brief": "make the fleet page honest",
        "cwd": "/root/Shepherd",
        "repo_id": None,
        "model": "claude-haiku-4-5-20251001",
        "tasks_total": 7,
        "tasks_done": 4,
        "active_subagents": 0,
        "repos_touched": (),
        "live_subagent_ids": frozenset(),
        "created_task_ids": frozenset(),
        "completed_task_ids": frozenset(),
        "title": None,
        "title_source": "brief",
        "pid": None,
        "proc_start": None,
        "ended_at": None,
        "auto_compact_at": None,
        "quota_notice_at": None,
    }
    fields.update(overrides)
    return SessionSnapshot(**fields)  # type: ignore[arg-type]


def signal(kind: SignalKind = SignalKind.SESSION_STOPPED, **fields: object) -> Signal:
    return Signal(
        kind=kind,
        engine_session_id=ENGINE_SESSION_ID,
        cwd="/root/Shepherd",
        transcript_path="",
        received_at=RECEIVED_AT,
        fields=fields,
        raw_kind="Stop",
    )


def build(tmp_path: Path, **overrides: object) -> tuple[StopEvidence, tuple[object, ...]]:
    arguments: dict[str, object] = {
        "signal": signal(),
        "prior": snapshot(),
        # Built only when the caller did not supply one, so a test that wants
        # an *absent* transcript does not race a default that created it.
        "projects_root": overrides.get("projects_root") or projects_root(tmp_path),
        "received_at": RECEIVED_AT,
        "end_reason": None,
        "auto_compact_pending": False,
        "quota_notice": False,
        # T8-3: the caller injects the vocabulary. `signals/heuristics.py`
        # exports `is_promise` for exactly this, and the default here is the
        # same one the production call site passes.
        "promise": is_promise,
    }
    arguments.update(overrides)
    return build_stop_evidence(**arguments)  # type: ignore[arg-type]


# ----- the record ------------------------------------------------------------


def test_record_version_is_stamped(tmp_path: Path) -> None:
    """ADR-M2-6: a reader months from now has to know what it is holding."""
    record, _ = build(tmp_path)
    assert record.record_version == STOP_RECORD_VERSION == 1


def test_the_three_sources_meet_exactly_once(tmp_path: Path) -> None:
    """Stop metadata, folded counters, neutral tail — one record, all three."""
    record, _ = build(tmp_path)

    assert record.session_id == "01SESSION"           # the store's identity
    assert record.engine_session_id == ENGINE_SESSION_ID
    assert record.received_at == RECEIVED_AT
    assert record.tasks_total == 7 and record.tasks_done == 4   # the fold's
    assert record.brief == "make the fleet page honest"
    assert record.tail.ending is TurnEnding.ENDED_TURN          # the transcript's
    assert record.tail.last_assistant_text == "FORKED"


def test_counters_come_from_the_snapshot_not_the_tail(tmp_path: Path) -> None:
    """DP3 / heuristic 1: §8's other heuristics want per-event history D24
    forbids storing, so the counts are the **folded columns** — which is the
    only place they survive a restart."""
    record, _ = build(tmp_path, prior=snapshot(tasks_total=99, tasks_done=1))
    assert record.tasks_total == 99
    assert record.tasks_done == 1
    # …and the tail is not consulted for them: the same transcript, different
    # counts, so the number cannot be coming from the file.
    other, _ = build(tmp_path, prior=snapshot(tasks_total=2, tasks_done=2))
    assert (other.tasks_total, other.tasks_done) == (2, 2)
    assert other.tail.ending is record.tail.ending


def test_the_mechanical_reason_is_resolved_at_assembly(tmp_path: Path) -> None:
    """The record carries the verdict's *inputs*, resolved once — so `replay`
    never needs the transcript again (C-M2-7)."""
    record, _ = build(tmp_path, signal=signal(failure_note="rate_limit"))
    assert record.mechanical is StopReason.RATE_LIMITED
    assert record.mechanical_detail is not None and "rate_limit" in record.mechanical_detail


def test_a_finished_turn_leaves_the_mechanical_reason_unset(tmp_path: Path) -> None:
    """`mechanical is None` means the adapter deferred to the completeness
    split. It is a handover, not a failure, and it carries no anomaly."""
    record, anomalies = build(tmp_path)
    assert record.mechanical is None
    assert not [a for a in anomalies if a.kind is AnomalyKind.STOP_UNMAPPED_VALUE]


def test_missing_transcript_is_an_absent_tail_not_a_crash(tmp_path: Path) -> None:
    """E-M2-12: `end_turn` cannot be established, so the split does not run and
    the verdict is `unknown` — counted. The observer never harms the observed."""
    record, anomalies = build(tmp_path, projects_root=projects_root(tmp_path, transcript=None))

    assert record.tail.ending is TurnEnding.ABSENT
    assert record.mechanical is StopReason.UNKNOWN
    kinds = {anomaly.kind for anomaly in anomalies}
    assert AnomalyKind.TRANSCRIPT_TAIL_ABSENT in kinds


def test_the_tails_anomalies_reach_the_caller(tmp_path: Path) -> None:
    """A tail that degraded has to say so *through* the assembly, or the count
    dies where nobody is looking (principle 5)."""
    root = projects_root(tmp_path)
    target = root / "-a-lossy-slug" / f"{ENGINE_SESSION_ID}.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "assistant", "message": {"id": "torn"')

    record, anomalies = build(tmp_path, projects_root=root)
    assert record.tail.skipped_lines == 1
    assert AnomalyKind.MALFORMED_PAYLOAD in {anomaly.kind for anomaly in anomalies}


def test_evidence_carries_no_engine_spelling(tmp_path: Path) -> None:
    """C-M2-5 / P-M2-6: the record crosses into `signals/`, so neither its
    field names nor its values may be the engine's words."""
    record, _ = build(tmp_path, signal=signal(failure_note="model_not_found"))

    names = {field.name for field in dataclasses.fields(record)}
    for word in ENGINE_WORDS:
        assert word not in names, word

    rendered = json.dumps(_as_plain(record))
    for word in ("hook_event_name", "StopFailure", "SessionEnd", "PreCompact"):
        assert word not in rendered, word
    # …and the fixture really did carry an engine word in, so the assertion is
    # about the projection rather than about an empty record (B3).
    assert "model_not_found" in rendered


def test_stop_evidence_has_no_mapping_field() -> None:
    """K12 has nothing to fire on because there is no mapping to read."""
    for field in dataclasses.fields(StopEvidence):
        assert "Mapping" not in str(field.type)
        assert "dict" not in str(field.type)


def test_reads_named_signal_fields_one_at_a_time() -> None:
    """K12 — the taint scan in `tests/boundaries/` is the real gate; this is the
    readable assertion beside it.

    `dict(signal.fields)`, `{**fields}`, `.keys()`, iteration and passing the
    mapping to a callee are all build failures inside `signals/`; this module
    is in `engines/`, and it holds itself to the same rule anyway because the
    record it produces is what crosses the boundary.
    """
    tree = ast.parse(Path(evidence_module.__file__).read_text(encoding="utf-8"))
    # A module-level `NAME = "literal"` is still a named literal key; the rule
    # is about *computed* keys and whole-mapping reads, not about spelling the
    # string twice.
    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    def literal(node: ast.expr) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in constants:
            return constants[node.id]
        raise AssertionError(f"fields read by a computed key: {ast.dump(node)}")

    keys: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _is_fields(node.value):
            keys.append(literal(node.slice))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _is_fields(node.func.value)
        ):
            assert node.func.attr == "get", node.func.attr
            assert node.args
            keys.append(literal(node.args[0]))
    assert keys, "the module reads no neutral field at all — it must read one"
    assert set(keys) <= {"failure_note"}


def test_evidence_takes_its_clock_as_a_parameter() -> None:
    """The purity map's rule: `received_at` is always a parameter.

    A format owned by a reader and no writer is exactly the bug that failed
    M1's verification — every `running` session silently demoted, 444 tests
    green. So this module reads no clock at all.
    """
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {
                "now",
                "utcnow",
                "today",
                "isoformat",
                "strftime",
                "fromisoformat",
            }, node.attr
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "datetime" not in imported and "time" not in imported


def test_assembly_is_deterministic(tmp_path: Path) -> None:
    """Same inputs -> byte-identical record, twice, **and in two processes**.

    One process proves the function has no hidden state; two prove it has no
    hidden *environment*, which is what makes the golden lane reproducible.
    """
    first, _ = build(tmp_path)
    second, _ = build(tmp_path)
    assert first == second

    root = projects_root(tmp_path / "subprocess-run")
    rendered = _in_a_fresh_process(root)
    assert rendered == json.dumps(_as_plain(first), sort_keys=True)


def test_an_observed_exit_is_recorded_on_the_record(tmp_path: Path) -> None:
    """C13 — the record says the exit was *seen* and the code was not."""
    record, anomalies = build(tmp_path, process_exit_observed=True, exit_code=None)
    assert record.process_exit_observed is True
    assert record.exit_code is None
    assert AnomalyKind.EXIT_CODE_UNOBSERVABLE in {anomaly.kind for anomaly in anomalies}


def test_the_compaction_and_quota_marks_must_be_supplied(tmp_path: Path) -> None:
    """They are **required** keyword arguments, not defaulted ones.

    The fold columns that carry them land with T10. Defaulting them here would
    mean `context_exhausted` and `quota_paused` silently never fire — a tested
    seam that never runs, which is precisely the defect the r3 review found in
    the stop path. A required argument turns that into a type error at the one
    call site that has to thread it.
    """
    import inspect

    parameters = inspect.signature(build_stop_evidence).parameters
    for name in ("end_reason", "auto_compact_pending", "quota_notice"):
        assert parameters[name].default is inspect.Parameter.empty, name
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, name

    record, _ = build(tmp_path, auto_compact_pending=True, end_reason="other")
    assert record.auto_compact_pending is True
    assert record.mechanical is StopReason.CONTEXT_EXHAUSTED


def test_the_transcript_is_found_by_the_session_id(tmp_path: Path) -> None:
    """Never by reversing the slug — it is lossy and hash-suffixed past 200
    UTF-16 units, so two cwds can share one project directory."""
    root = projects_root(tmp_path)
    record, _ = build(tmp_path, projects_root=root)
    assert record.tail.entry_count > 0

    elsewhere, _ = build(
        tmp_path,
        projects_root=root,
        prior=snapshot(engine_session_id="not-a-session"),
        signal=_signal_for("not-a-session"),
    )
    assert elsewhere.tail.ending is TurnEnding.ABSENT


def test_the_module_writes_nothing(tmp_path: Path) -> None:
    """C-M2-6: M2 reads the engine's transcript and writes only under its own
    data directory. Not here, and never into `~/.claude`."""
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"write_text", "write_bytes", "mkdir", "unlink"}
    assert "settings.json" not in source


def _signal_for(engine_session_id: str) -> Signal:
    return Signal(
        kind=SignalKind.SESSION_STOPPED,
        engine_session_id=engine_session_id,
        cwd="/root/Shepherd",
        transcript_path="",
        received_at=RECEIVED_AT,
        fields={},
        raw_kind="Stop",
    )


def _is_fields(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "fields"


def _as_plain(record: StopEvidence) -> dict[str, object]:
    """The record as JSON-able data — which is what the stop log stores."""
    return json.loads(json.dumps(dataclasses.asdict(record), default=str, sort_keys=True))


def _in_a_fresh_process(root: Path) -> str:
    """Assemble the same record in a new interpreter (no `shell=True`, §13)."""
    script = f"""
import dataclasses, json, sys
sys.path.insert(0, {str(REPO_ROOT / "src")!r})
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_evidence import build_stop_evidence, is_promise, signal, snapshot, RECEIVED_AT
record, _ = build_stop_evidence(
    signal=signal(), prior=snapshot(), projects_root=__import__("pathlib").Path({str(root)!r}),
    received_at=RECEIVED_AT, end_reason=None, auto_compact_pending=False, quota_notice=False,
    promise=is_promise,
)
print(json.dumps(json.loads(json.dumps(dataclasses.asdict(record), default=str, sort_keys=True)),
                 sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.mark.parametrize("kind", [SignalKind.SESSION_STOPPED, SignalKind.STOP_FAILED])
def test_assembly_never_raises_for_either_stop_kind(tmp_path: Path, kind: SignalKind) -> None:
    record, _ = build(tmp_path, signal=signal(kind))
    assert isinstance(record, StopEvidence)
