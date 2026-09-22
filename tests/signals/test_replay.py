"""`shepherd replay` — the engine (T12, D3, D24, D25, RD7/RD8).

D3's claim is the thing under test: *a missed case is fixed by editing a rule
and replaying history, not by waiting for it to recur*. So the central test
**edits a rule** (a heuristic vocabulary row, which is what M2 lets a human
tune) and asserts the stored verdict moves when the history is replayed.

Seam: `replay(...)` — the engine function, driven against a real `Store` and a
real stop log written by `StopLog`. Nothing here mocks the classifier: the
rules that run are the shipped ones.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from shepherd.core.states import Origin, Ownership
from shepherd.core.stops import (
    STOP_RECORD_VERSION,
    Bucket,
    DecidedBy,
    StopEvidence,
    StopReason,
    TranscriptTail,
    TurnEnding,
    Verdict,
)
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.replay import format_replay_diff
from shepherd.logs.stops import StopLog
from shepherd.signals import heuristics
from shepherd.signals.heuristics import split_completeness
from shepherd.signals.replay import ReplayReport, SinceIsNotADate, replay
from shepherd.signals.verdict import classify
from shepherd.store.db import Store, open_store

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: The two stamps every fixture record uses. Handed in, never read from a clock.
DAY = "2026-09-17"
STAMP = f"{DAY}T01:04:18.671Z"
LATER = f"{DAY}T02:04:18.671Z"

#: A phrase no capture contains, so patching it in is unambiguously "a rule was
#: edited" rather than "a rule already matched".
NEW_WAITING_PHRASE = "waiting on the release train"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


@pytest.fixture()
def diff_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "replay"


def tail(text: str | None = None, ending: TurnEnding = TurnEnding.ENDED_TURN) -> TranscriptTail:
    return TranscriptTail(
        ending=ending,
        last_assistant_text=text,
        entry_count=4,
        tool_uses=(),
        failures=(),
        promise_followed_by_tool_use=None,
        skipped_lines=0,
        truncated=False,
    )


def evidence(
    session_id: str,
    *,
    text: str | None = None,
    mechanical: StopReason | None = None,
    ending: TurnEnding = TurnEnding.ENDED_TURN,
    received_at: str = STAMP,
) -> StopEvidence:
    return StopEvidence(
        record_version=STOP_RECORD_VERSION,
        session_id=session_id,
        engine_session_id=f"engine-{session_id}",
        received_at=received_at,
        mechanical=mechanical,
        mechanical_detail=None if mechanical is None else "the adapter decided",
        tail=tail(text, ending),
        tasks_total=0,
        tasks_done=0,
        brief="ship the thing",
        auto_compact_pending=False,
        quota_notice=False,
        process_exit_observed=False,
        exit_code=None,
    )


def stored(reason: StopReason) -> Verdict:
    """A verdict as some earlier build wrote it into the columns."""
    return Verdict(
        stop_reason=reason,
        bucket=Bucket.FINISHED,
        why="what the rules said at the time",
        confidence=0.5,
        decided_by=DecidedBy.HEURISTIC,
        next_actions=(),
        waiting_on=None,
        missing=(),
    )


def seed(store: Store, session_id_hint: str, verdict: Verdict, at: str = STAMP) -> str:
    """One stopped session carrying a verdict, as the live lane leaves it."""
    workspace = store.create_project(name=session_id_hint, description=None)
    session = store.register_session(
        engine_session_id=f"engine-{session_id_hint}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=f"/tmp/{session_id_hint}",
        started_at=at,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    store.apply_stop_verdict(session.id, verdict, at, None)
    return session.id


def write_log(log_dir: Path, *records: tuple[StopEvidence, Verdict]) -> None:
    log = StopLog(RotatingJsonlLog(log_dir, "stops"))
    for record, verdict in records:
        assert log.append(record, verdict) is True
    log.close()


def reasons(store: Store) -> dict[str, str | None]:
    return {row.session_id: row.stop_reason for row in store.sessions_for_replay(None)}


def diff_text(report: ReplayReport) -> str:
    return report.diff_path.read_text(encoding="utf-8")


#: Reader functions that open a transcript. Matched against the **origin** of a
#: binding, never against the local spelling, so `import … as rt` is the same
#: reach as `read_tail`.
TRANSCRIPT_READERS = frozenset({"read_tail", "locate_transcript", "build_stop_evidence"})

#: The package a transcript lives behind. A replay may not import *any* of it:
#: ADR-M2-1's claim is about the whole engine adapter, not about three names.
ENGINE_PACKAGE = "shepherd.engines"


def transcript_reaches(source: str) -> list[str]:
    """Every way this source could reach a transcript — by property, not spelling.

    Two rules, both on the **origin** of a name rather than on how the module
    happens to spell it locally:

    * it imports nothing from `shepherd.engines`, which is where every
      transcript reader lives. An import is the only way to reach one, and an
      alias cannot hide the module it came from;
    * no binding it introduces originates in a transcript reader.
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        origins: list[str] = []
        if isinstance(node, ast.Import):
            origins = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            origins = [prefix, *(f"{prefix}.{alias.name}" for alias in node.names)]
        for origin in origins:
            if origin == ENGINE_PACKAGE or origin.startswith(ENGINE_PACKAGE + "."):
                found.append(f"imports {origin}")
            elif origin.rsplit(".", 1)[-1] in TRANSCRIPT_READERS:
                found.append(f"imports {origin}")
    return found


def seed_unclassified(store: Store, session_id_hint: str, at: str = STAMP) -> str:
    """E-M2-4's cohort: the fold moved the row to `stopped` and no verdict ever
    arrived, so `stop_reason` is NULL. Never green, never red — and the cohort
    `replay` exists to fix."""
    workspace = store.create_project(name=session_id_hint, description=None)
    session = store.register_session(
        engine_session_id=f"engine-{session_id_hint}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=f"/tmp/{session_id_hint}",
        started_at=at,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    return session.id


# --- D3's claim ---------------------------------------------------------------


def test_a_never_classified_session_is_reclassified_not_reported_as_orphaned(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """The cohort `replay` exists to fix was the one cohort it could not reach.

    `orphaned` means *a record whose session is no longer in the store* — a
    purge. A session the fold moved to `stopped` with no verdict was counted as
    one, so a never-classified session and a purged one were reported as one
    number, and no rule edit could reach either.
    """
    session_id = seed_unclassified(store, "s1")
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))

    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert (report.orphaned, report.reclassified) == (0, 1)
    assert [(change.before, change.after) for change in report.changes] == [(None, "completed")]
    assert reasons(store)[session_id] == "completed"
    # `before is None` is reachable and real, so the diff's fallback is not dead code
    assert "no verdict → completed" in diff_text(report)


def test_replay_uses_the_current_rules(
    store: Store, log_dir: Path, diff_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit a rule, replay history: the missed case is fixed without recurrence.

    The stop happened before the vocabulary row existed, so the column says
    `completed`. Adding the row is the whole fix — no session is re-run.
    """
    session_id = seed(store, "s1", stored(StopReason.COMPLETED))
    record = evidence(session_id, text=f"All done for now, {NEW_WAITING_PHRASE}.")
    write_log(log_dir, (record, stored(StopReason.COMPLETED)))

    monkeypatch.setattr(
        heuristics, "WAITING_PHRASES", (*heuristics.WAITING_PHRASES, NEW_WAITING_PHRASE)
    )
    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert [(change.before, change.after) for change in report.changes] == [
        ("completed", "blocked_external")
    ]
    assert reasons(store)[session_id] == "blocked_external"


def test_replay_overwrites_the_stop_columns(store: Store, log_dir: Path, diff_dir: Path) -> None:
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))

    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert report.applied is True
    assert reasons(store)[session_id] == "completed"


def test_replay_without_apply_writes_the_diff_and_no_column(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """RD7: the diff is the review artefact, so it is written on **every** run."""
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)

    assert report.applied is False
    assert report.changes and report.changes[0].after == "completed"
    assert reasons(store)[session_id] == "unknown"
    assert report.diff_path.is_file()
    assert "--apply" in diff_text(report)


def test_replay_is_idempotent(store: Store, log_dir: Path, diff_dir: Path) -> None:
    """P-M2-9: running twice changes nothing the second time."""
    first = seed(store, "s1", stored(StopReason.UNKNOWN))
    second = seed(store, "s2", stored(StopReason.COMPLETED))
    write_log(
        log_dir,
        (evidence(first, text="fine"), stored(StopReason.UNKNOWN)),
        (evidence(second, mechanical=StopReason.RATE_LIMITED), stored(StopReason.COMPLETED)),
    )

    # two dry runs over the same log: both *change* things, so the census loop
    # actually runs. Comparing two empty change blocks compared nothing — the
    # docstring's "first-seen order so the block is byte-identical" was true and
    # unobserved, and inverting the census ordering survived the suite.
    dry_one = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)
    dry_two = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)
    block = format_replay_diff(dry_one, dry_one.date)
    assert len(dry_one.changes) == 2
    assert block.count("→") >= 4, "the census block must not be empty"
    assert block == format_replay_diff(dry_two, dry_two.date)

    one = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)
    after_one = reasons(store)
    two = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)
    three = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert len(one.changes) == 2
    assert two.changes == () and three.changes == ()
    assert reasons(store) == after_one
    assert format_replay_diff(two, two.date) == format_replay_diff(three, three.date)


def test_replay_never_writes_a_verdict_it_did_not_derive(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """**All eight** written columns equal `classify()` of that record.

    Eight, not three: `--apply` writes `stop_reason, outcome, why, confidence,
    decided_by, next_actions, ended_at, exit_code` in one statement (D33), and a
    mutation that dropped `exit_code` from that write survived the suite because
    every fixture set it to `None`. So this record carries a non-null
    `exit_code` and a verdict with a non-empty `next_actions`.
    """
    session_id = seed(store, "s1", stored(StopReason.CRASHED))
    record = replace(
        evidence(session_id, mechanical=StopReason.AUTH_FAILED),
        exit_code=137,
        received_at=LATER,
    )
    # a stored verdict that disagrees with the evidence: only the evidence counts
    write_log(log_dir, (record, stored(StopReason.DERAILED)))

    replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    session = store.get_session(session_id)
    assert session is not None
    derived = classify(record)
    assert derived.next_actions != (), "the fixture must exercise the next_actions column"
    assert session.stop_reason == str(derived.stop_reason.value)
    assert session.outcome == str(derived.bucket.value)
    assert session.why == derived.why
    assert session.confidence == derived.confidence
    assert session.decided_by == str(derived.decided_by.value)
    assert session.next_actions == derived.next_actions
    assert session.ended_at == record.received_at
    assert session.exit_code == 137


def test_the_diff_names_every_column_whose_value_moved(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """`--apply` writes eight columns; a diff that showed one hid seven.

    A run reporting `changed 0` could still rewrite `why`, `next_actions` and
    `confidence` — and `confidence` is what feeds `completed_low_confidence`,
    which DP10/D34 read as the trigger for the LLM lane.
    """
    session_id = seed(store, "s1", stored(StopReason.COMPLETED))
    record = evidence(session_id, text="fine")
    write_log(log_dir, (record, stored(StopReason.COMPLETED)))

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)

    derived = classify(record)
    assert derived.stop_reason is StopReason.COMPLETED, "the reason must NOT move"
    assert [change.session_id for change in report.changes] == [session_id]
    change = report.changes[0]
    assert (change.before, change.after) == ("completed", "completed")
    assert set(change.columns) == {"why", "next_actions"}
    body = diff_text(report)
    assert "changed 1" in body
    for column in change.columns:
        assert column in body


def test_a_diff_that_cannot_be_written_leaves_every_column_untouched(
    store: Store, log_dir: Path, tmp_path: Path
) -> None:
    """RD7, the one safety property this module states about itself.

    The diff exists precisely so a human reads it before the columns move. When
    `--apply` ran first, a diff-write failure left every verdict rewritten with
    no review artefact — the inversion of the property, in the one way `replay`
    can do damage.
    """
    occupied = tmp_path / "logs" / "replay"
    occupied.parent.mkdir(parents=True, exist_ok=True)
    occupied.write_text("something is already here\n", encoding="utf-8")
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))

    with pytest.raises(OSError):
        replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=occupied)

    assert reasons(store)[session_id] == "unknown", "a column moved with no diff to review"


def test_every_skip_kind_is_counted_as_itself(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """One fixture, every skip kind at once.

    Each counter was only ever tested alone, so a mutation folding `orphaned`
    into `skipped_malformed` survived the whole suite. Asserted together, the
    tuple kills that mutation class.
    """
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(
        log_dir,
        (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)),
        (evidence("01NOSUCHSESSION", text="fine"), stored(StopReason.UNKNOWN)),
    )
    (log_dir / "stops" / f"{DAY}.1.jsonl").write_text(
        "{not json\n" + json.dumps({"record_version": 99, "evidence": {}, "verdict": {}}) + "\n",
        encoding="utf-8",
    )
    (log_dir / "stops" / f"{DAY}.2.jsonl.gz").write_bytes(b"not gzip at all\n" * 100)

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)

    assert (
        report.read,
        report.skipped_malformed,
        report.skipped_version,
        report.orphaned,
        report.unreadable_files,
    ) == (2, 1, 1, 1, 1)
    body = diff_text(report)
    assert "1 malformed" in body
    assert "1 unknown version" in body
    assert "1 orphaned" in body
    assert "1 unreadable" in body


def test_the_unknown_rate_is_a_fraction_of_the_sessions_replayed(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """The headline number, at a value that is not a terminal one.

    Every existing assertion pinned it at `0.0` or `1.0`, so hardcoding
    `unknown_rate_after = 0.0` survived the suite — and `_percent` formats
    `.1f`, whose rounding nothing observed at all.
    """
    first = seed(store, "s1", stored(StopReason.UNKNOWN))
    second = seed(store, "s2", stored(StopReason.COMPLETED))
    third = seed(store, "s3", stored(StopReason.COMPLETED))
    write_log(
        log_dir,
        (evidence(first, text="fine"), stored(StopReason.UNKNOWN)),
        (evidence(second, ending=TurnEnding.ABSENT), stored(StopReason.COMPLETED)),
        (evidence(third, ending=TurnEnding.ABSENT), stored(StopReason.COMPLETED)),
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert report.unknown_rate_before == pytest.approx(1 / 3)
    assert report.unknown_rate_after == pytest.approx(2 / 3)
    assert "unknown rate: 33.3% → 66.7%" in diff_text(report)


def test_a_classifier_crash_is_counted_and_kept_out_of_the_unknown_rate(
    store: Store, log_dir: Path, diff_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed rule is not a rule gap, and the tuning backlog is rule gaps.

    `classify`'s guard is correct — one unreadable record out of 412 may not
    kill the run. What was wrong is that its outcome entered the headline
    `unknown` rate, where it reads as work a rule edit could close and no rule
    edit can.
    """
    first = seed(store, "s1", stored(StopReason.UNKNOWN))
    second = seed(store, "s2", stored(StopReason.UNKNOWN))
    crashing = evidence(second, text="fine")

    def explode(evidence_in: StopEvidence) -> object:
        if evidence_in.session_id == second:
            raise RuntimeError("a rule crashed")
        return split_completeness(evidence_in)

    monkeypatch.setattr("shepherd.signals.verdict.classify_end_turn", explode)
    write_log(
        log_dir,
        (evidence(first, text="fine"), stored(StopReason.UNKNOWN)),
        (crashing, stored(StopReason.UNKNOWN)),
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)

    assert report.classifier_failures == 1
    assert report.reclassified == 2
    # one readable session, and it moved off `unknown`: the backlog is empty
    assert report.unknown_rate_before == 1.0
    assert report.unknown_rate_after == 0.0
    assert "classifier failures: 1" in diff_text(report)


def test_columns_equal_the_replayed_log(store: Store, log_dir: Path, diff_dir: Path) -> None:
    """P-M2-8 over a many-record log, including a session with two stops."""
    ids = [seed(store, f"s{index}", stored(StopReason.UNKNOWN)) for index in range(5)]
    records = [
        (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)) for session_id in ids
    ]
    # E-M2-5: a second stop for one session, later, and it is the one that wins
    records.append(
        (
            evidence(ids[0], mechanical=StopReason.RATE_LIMITED, received_at=LATER),
            stored(StopReason.UNKNOWN),
        )
    )
    write_log(log_dir, *records)

    replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    found = reasons(store)
    assert found[ids[0]] == "rate_limited"
    assert all(found[session_id] == "completed" for session_id in ids[1:])


def test_replay_reports_skipped_records_separately(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """E-M2-21/22: a torn line and a record from a newer build are not one number."""
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))
    # a second part of the same day: one torn line and one record from a build
    # that knows a version this one does not
    (log_dir / "stops" / f"{DAY}.1.jsonl").write_text(
        "{not json\n" + json.dumps({"record_version": 99, "evidence": {}, "verdict": {}}) + "\n",
        encoding="utf-8",
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)

    assert (report.read, report.skipped_malformed, report.skipped_version) == (1, 1, 1)
    assert "1 malformed" in diff_text(report) and "1 unknown version" in diff_text(report)


def test_orphaned_record_is_counted_not_fatal(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """E-M2-25: the session was purged; the record is counted and skipped."""
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(
        log_dir,
        (evidence("01NOSUCHSESSION", text="fine"), stored(StopReason.UNKNOWN)),
        (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)),
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert (report.read, report.orphaned, report.reclassified) == (2, 1, 1)
    assert reasons(store)[session_id] == "completed"


def test_replay_writes_a_diff_file(store: Store, log_dir: Path, diff_dir: Path) -> None:
    """The before/after pairs, the counts, the unknown-rate delta — and RD8."""
    first = seed(store, "s1", stored(StopReason.UNKNOWN))
    second = seed(store, "s2", stored(StopReason.UNKNOWN))
    write_log(
        log_dir,
        (evidence(first, text="fine"), stored(StopReason.UNKNOWN)),
        (evidence(second, mechanical=StopReason.RATE_LIMITED), stored(StopReason.UNKNOWN)),
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)
    body = diff_text(report)

    assert report.diff_path.name == f"{DAY}.log"
    assert report.unknown_rate_before == 1.0 and report.unknown_rate_after == 0.0
    assert f"{first} unknown → completed" in body
    assert f"{second} unknown → rate_limited" in body
    assert "read 2 records" in body
    assert "changed 2" in body
    assert "unknown rate: 100.0% → 0.0%" in body
    # RD8: the flag is not implemented, and the header says so rather than
    # implying a comparison that never happened.
    assert "classifier version: not recorded" in body
    assert f"record version: {STOP_RECORD_VERSION}" in body


def test_replay_never_reads_a_transcript(
    store: Store, log_dir: Path, diff_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-M2-1: the record is the truth. Two proofs — a scan and an instrument."""
    modules = (SRC_ROOT / "signals" / "replay.py", SRC_ROOT / "logs" / "replay.py")
    for module in modules:
        assert transcript_reaches(module.read_text(encoding="utf-8")) == [], module.name

    # …and the scan bites on the spelling the old one could not see: three
    # literal names matched against `ast.Name`/`ast.Attribute` never inspected
    # `alias.asname`, so a rename defeated it — `patterns.md`'s "a rule keyed on
    # one exact AST spelling", verbatim.
    assert transcript_reaches(
        "from shepherd.engines.claude_code.transcript_tail import read_tail as rt\n"
        "def go() -> None:\n    rt('/x')\n"
    ) != []
    assert transcript_reaches(
        "import shepherd.engines.claude_code.transcript_tail as t\n"
        "def go() -> None:\n    t.read_tail('/x')\n"
    ) != []
    assert transcript_reaches("from shepherd.store.db import Store\n") == []

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay opened a transcript")

    monkeypatch.setattr("shepherd.engines.claude_code.transcript_tail.read_tail", explode)
    monkeypatch.setattr("shepherd.engines.claude_code.transcript_tail.locate_transcript", explode)

    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))
    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)
    assert report.reclassified == 1


def test_replay_narrows_by_since(store: Store, log_dir: Path, diff_dir: Path) -> None:
    """`--since` narrows by the stop's own date, on both sides of the join."""
    old = seed(store, "s1", stored(StopReason.UNKNOWN), at="2026-09-01T00:00:00.000Z")
    new = seed(store, "s2", stored(StopReason.UNKNOWN))
    write_log(
        log_dir,
        (evidence(old, text="fine", received_at="2026-09-01T00:00:00.000Z"), stored(StopReason.UNKNOWN)),
    )
    write_log(log_dir, (evidence(new, text="fine"), stored(StopReason.UNKNOWN)))

    report = replay(store=store, log_dir=log_dir, since=DAY, apply=True, diff_dir=diff_dir)

    assert report.reclassified == 1
    assert reasons(store) == {old: "unknown", new: "completed"}


def test_the_census_is_in_first_seen_order(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """`unknown → stalled_pending_tool (31)` — §8's shape, in the order seen.

    The claim "first-seen order so the block is byte-identical" was true and
    unobserved: inverting the census ordering changed no assertion, because the
    only test that compared two blocks compared two runs that changed nothing.
    Two *different* pairs are what makes an order observable at all.
    """
    first = seed(store, "s1", stored(StopReason.UNKNOWN))
    second = seed(store, "s2", stored(StopReason.COMPLETED))
    third = seed(store, "s3", stored(StopReason.UNKNOWN))
    write_log(
        log_dir,
        (evidence(first, text="fine"), stored(StopReason.UNKNOWN)),
        (evidence(second, mechanical=StopReason.RATE_LIMITED), stored(StopReason.COMPLETED)),
        (evidence(third, text="fine"), stored(StopReason.UNKNOWN)),
    )

    report = replay(store=store, log_dir=log_dir, since=None, apply=False, diff_dir=diff_dir)
    census = [
        line.strip()
        for line in diff_text(report).splitlines()
        if line.strip().endswith(")") and "→" in line and not line.strip().startswith("unknown rate")
    ]

    assert census == ["unknown → completed (2)", "completed → rate_limited (1)"]


def test_a_since_that_is_not_a_date_is_refused_at_the_boundary(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """`--since 30d` — the plan's own §8 example — used to read zero records.

    `"2026-09-17" < "30d"` is `True`, so every file was filtered out, the diff
    said `read 0 records`, and the command exited 0. Nothing validated the
    value at any of the four layers that touch it.
    """
    session_id = seed(store, "s1", stored(StopReason.UNKNOWN))
    write_log(log_dir, (evidence(session_id, text="fine"), stored(StopReason.UNKNOWN)))

    for bad in ("30d", "2026-9-17", "yesterday", ""):
        with pytest.raises(SinceIsNotADate):
            replay(store=store, log_dir=log_dir, since=bad, apply=True, diff_dir=diff_dir)

    assert reasons(store)[session_id] == "unknown"
    assert not diff_dir.exists(), "a refused run has nothing to report"


def test_an_empty_log_is_a_report_not_a_crash(
    store: Store, log_dir: Path, diff_dir: Path
) -> None:
    """Principle 5: nothing to replay is a number, and the rate says so."""
    report = replay(store=store, log_dir=log_dir, since=None, apply=True, diff_dir=diff_dir)

    assert (report.read, report.reclassified, report.changes) == (0, 0, ())
    assert report.unknown_rate_before == 0.0 and report.unknown_rate_after == 0.0
    assert report.diff_path.is_file()
    assert "read 0 records" in diff_text(report)
