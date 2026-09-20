"""`shepherd replay` — the engine (T12, D3, D24, D25).

D3's claim in one function: *"storing raw signals means a missed case is fixed
by editing a rule and replaying history, not by waiting for it to recur"*, and
D24 narrows *raw signals* to the **stop log** — kilobytes per session, not
gigabytes per day.

**What it reads, and what it may not.** The stop log, and nothing else
(ADR-M2-1): the record is the truth, the transcript may be gone, and a replay
that opened one would be replaying *this* machine's `~/.claude` rather than the
history. `test_replay_never_reads_a_transcript` holds that with an AST scan and
an instrumented reader.

**The diff is written on every run; the columns change only with `--apply`.**
§8's example implies a write, and a command that silently overwrote 412
verdicts because a rule was mid-edit is the one way `replay` can do damage. The
diff exists precisely so a human reads it first (RD7).

**And it is written *first*.** The apply loop used to run inside the pass that
built the report, so a failure to write the diff left every verdict rewritten
with no artefact to review — RD7 inverted, in exactly the way it exists to
prevent. Two passes: the report and the diff, then the columns.

**The `unknown` rate is the headline number** — it *is* the tuning backlog
(principle 5, D34), which is why the report carries it before and after rather
than only the count of rows that moved.

**No clock.** The diff's daily file is named for the newest record the run
read, sliced out of that record's own canonical stamp (`logs/stops.date_of`,
which only slices after `core/clock.parse_stamp` has confirmed the spelling).
A run that read nothing has no date to claim and says so, rather than asking a
clock this module is not allowed to read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from shepherd.core.clock import DATE_EXAMPLE, parse_date
from shepherd.core.stops import StopEvidence, StopReason, Verdict
from shepherd.logs.replay import REPLAY_PREFIX, write_replay_diff
from shepherd.logs.stops import UNKNOWN_DATE, date_of, read_stop_records
from shepherd.signals.verdict import WHY_UNREADABLE, classify
from shepherd.store.db import Store
from shepherd.store.models import ReplayTarget
from shepherd.store.stops import REPLAYED_COLUMNS

__all__ = [
    "DIFF_DIRNAME",
    "ReplayReport",
    "SinceIsNotADate",
    "VerdictChange",
    "moved_columns",
    "replay",
]


class SinceIsNotADate(ValueError):
    """`--since` was not a date, so this run refused to start.

    `"2026-09-17" < "30d"` is `True`. Unvalidated, the plan's own §8 example —
    `shepherd replay --since 30d` — filtered every file out, read zero records,
    wrote a diff saying `read 0 records` and exited 0. A narrowing nobody can
    express is not an empty history, and the difference is the whole of what
    the operator is looking at.
    """

#: The diff's subdirectory name, re-exported from the writer that owns it.
#:
#: The composition root has to resolve `<data>/logs/replay/` and **may not
#: import a log module to learn the name**: P-M2-10 (D25's guardrail) forbids
#: `toolsurface/`, `web/` and `cli/` from importing `shepherd.logs` at all, so
#: that nothing the UI renders can come to read a log. This lane already
#: imports the writer, so it is the honest place for the name to cross — one
#: spelling, owned by `logs/replay.py`, never a second literal.
DIFF_DIRNAME = REPLAY_PREFIX


@dataclass(frozen=True)
class VerdictChange:
    """One row the current rules disagree with the stored columns about.

    `before` is `None` for a session the store has no verdict for — which is a
    different fact from "the verdict was `unknown`", and the diff says so. That
    case is reachable: the replay read includes the never-classified (T12-3).

    `columns` names **every** stop column whose value moved, not only
    `stop_reason`. `--apply` writes eight in one statement (D33), so a row whose
    reason is unchanged can still have its `why`, `confidence` and
    `next_actions` rewritten — and `confidence` is what DP10/D34 read as the
    trigger for the LLM lane. A change block that showed one of eight was a
    review artefact a human could not review.
    """

    session_id: str
    before: str | None
    after: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ReplayReport:
    """What one run read, re-derived, and would change — or did.

    A counter per work item rather than one number for all of them: a torn
    line, a record from a build that knows something this one does not, a
    record whose session is no longer in the store, a file the read had to
    abandon, a partition a narrowed run could not place, and a record the
    classifier crashed on are six different work items and a human fixes each
    differently (E-M2-21/22, E-M2-25, P-M2-2).

    `orphaned` means **purged** and nothing else: the never-classified are
    reachable now and are reclassified, not counted here (T12-3).
    """

    read: int
    skipped_malformed: int
    skipped_version: int
    orphaned: int
    reclassified: int
    changes: tuple[VerdictChange, ...]
    unknown_rate_before: float
    unknown_rate_after: float
    applied: bool
    unreadable_files: int
    """Files the read had to abandon — a torn archive, a corrupt deflate stream,
    a `.gz` whose magic is wrong. Every record after the tear is gone, and
    without this number `read 6 records (0 malformed)` is byte-indistinguishable
    from a log that only ever held six."""

    skipped_undated: int
    """Partitions a narrowed run left unread because their date is unreadable.
    An unknown date is not evidence of being inside the window (principle 5)."""

    classifier_failures: int
    """Records `classify`'s boundary guard caught (P-M2-2). Counted apart from
    `unknown` and kept out of the rate: the `unknown` rate **is** the tuning
    backlog (D34, principle 5), and a crashed rule is a bug, not a rule gap a
    rule edit can close."""

    diff_path: Path
    """Where the before/after diff was written. Every run writes one, which is
    why this is not optional: a report whose diff a human cannot open is the
    review artefact missing. (The plan's Produces block omits this field; see
    the blocker file, T12-1.)"""

    date: str
    """The daily partition the diff was written under — the newest record's own
    date, or `unknown-date` when the run read nothing."""


def replay(
    *, store: Store, log_dir: Path, since: str | None, apply: bool, diff_dir: Path
) -> ReplayReport:
    """Re-run the **current** classifier over the stop log. Writes the diff.

    The log is read in write order, so a session with two stops (E-M2-5) ends
    on the verdict its *later* record earns — the same rule the live lane
    follows, because a replay that disagreed with the lane about ordering would
    produce a history no run could reproduce.
    """
    if since is not None and parse_date(since) is None:
        raise SinceIsNotADate(
            f"--since must be a date spelled {DATE_EXAMPLE} (YYYY-MM-DD); {since!r} is not one"
        )
    records, stats = read_stop_records(log_dir, since)
    targets = {target.session_id: target for target in store.sessions_for_replay(since)}

    final: dict[str, tuple[StopEvidence, Verdict]] = {}
    orphaned = 0
    for evidence in records:
        if evidence.session_id not in targets:
            orphaned += 1
            continue
        final[evidence.session_id] = (evidence, classify(evidence))

    changes: list[VerdictChange] = []
    unknown_before = 0
    unknown_after = 0
    readable = 0
    crashed = 0
    for session_id, (evidence, verdict) in final.items():
        target = targets[session_id]
        if _crashed(verdict):
            crashed += 1
        else:
            readable += 1
            unknown_before += int(target.stop_reason == StopReason.UNKNOWN.value)
            unknown_after += int(str(verdict.stop_reason.value) == StopReason.UNKNOWN.value)
        moved = moved_columns(target, verdict, evidence)
        if moved:
            changes.append(
                VerdictChange(
                    session_id=session_id,
                    before=target.stop_reason,
                    after=str(verdict.stop_reason.value),
                    columns=moved,
                )
            )

    date = _date(records)
    report = ReplayReport(
        read=stats.records,
        skipped_malformed=stats.skipped_malformed,
        skipped_version=stats.skipped_version,
        orphaned=orphaned,
        reclassified=len(final),
        changes=tuple(changes),
        unknown_rate_before=_rate(unknown_before, readable),
        unknown_rate_after=_rate(unknown_after, readable),
        applied=apply,
        unreadable_files=stats.unreadable_files,
        skipped_undated=stats.skipped_undated,
        classifier_failures=crashed,
        diff_path=diff_dir,  # the directory until the writer names the file
        date=date,
    )
    # **The diff first, the columns second.** RD7 is the module's one safety
    # property and the order is the whole of it: a diff-write failure must
    # leave the columns as it found them, never every verdict rewritten with no
    # artefact to review. `final` already holds every (evidence, verdict) pair,
    # so the second pass needs nothing the first one did not have.
    path = write_replay_diff(report, diff_dir, date)
    if apply:
        for session_id, (evidence, verdict) in final.items():
            store.apply_stop_verdict(session_id, verdict, evidence.received_at, evidence.exit_code)
    return replace(report, diff_path=path)


def moved_columns(
    target: ReplayTarget, verdict: Verdict, evidence: StopEvidence
) -> tuple[str, ...]:
    """Which of the eight written columns this replay would change, in write order.

    Compared as **values**, not as stored text: `next_actions` is one JSON array
    on disk and two encodings of the same actions are the same value. The order
    is `REPLAYED_COLUMNS`, which is the order the one `UPDATE` writes them, so a
    reader of the diff and a reader of the SQL see the same list.
    """
    after: dict[str, object] = {
        "stop_reason": str(verdict.stop_reason.value),
        "outcome": str(verdict.bucket.value),
        "why": verdict.why,
        "confidence": verdict.confidence,
        "decided_by": str(verdict.decided_by.value),
        "next_actions": verdict.next_actions,
        "ended_at": evidence.received_at,
        "exit_code": evidence.exit_code,
    }
    before: dict[str, object] = {
        "stop_reason": target.stop_reason,
        "outcome": target.outcome,
        "why": target.why,
        "confidence": target.confidence,
        "decided_by": target.decided_by,
        "next_actions": target.next_actions,
        "ended_at": target.ended_at,
        "exit_code": target.exit_code,
    }
    return tuple(column for column in REPLAYED_COLUMNS if before[column] != after[column])


def _crashed(verdict: Verdict) -> bool:
    """Did `classify`'s boundary guard produce this verdict? (P-M2-2)

    The guard is correct — one unreadable record out of 412 may not kill a
    replay. What is wrong is counting its outcome as an ordinary `unknown`: the
    unknown rate is the *tuning* backlog, and no rule edit closes a crash. The
    fact is already in `why`; this reads it rather than adding a second channel.
    """
    return verdict.stop_reason is StopReason.UNKNOWN and verdict.why == WHY_UNREADABLE


def _rate(part: int, whole: int) -> float:
    """A rate over an empty population is `0.0`, and the count beside it is `0`.

    Not `None`: every reader of this number divides it into a percentage, and
    the report already says how many rows it is measured over — a rate with no
    population is not an unknown, it is an empty set.
    """
    return 0.0 if whole == 0 else part / whole


def _date(records: list[StopEvidence]) -> str:
    """The newest record's own date — the day the replayed history ends.

    Deliberately not "today": this module may not read a clock, and naming the
    file after the history makes two runs over the same log produce the same
    file, which is what `test_replay_is_idempotent` observes.
    """
    dates = [date_of(record.received_at) for record in records]
    readable = sorted(date for date in dates if date is not None)
    return readable[-1] if readable else UNKNOWN_DATE
