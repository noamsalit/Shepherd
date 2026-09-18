"""The replay diff — the artefact a human reads before `--apply` (T12, RD7/RD8).

`replay` writes this on **every** run, including the ones that change nothing.
That is the whole safety property: a command that silently overwrote 412
verdicts because a rule was mid-edit is the one way `replay` can do damage, and
the diff is what makes the damage reviewable *first*.

Three things this file says that a count of changed rows would not:

* **the before/after pair for every row**, session by session, and the census
  of those pairs. "37 changed" tells a tuner nothing; "unknown → stalled
  (31)" is the work item;
* **the `unknown` rate on both sides.** It *is* the tuning backlog (principle
  5, D34), so it is the headline, not a footnote;
* **what it does not know.** §8's example shows `--classifier h-8`; M2 has no
  rule-set versioning, so the flag is not implemented and this header says the
  classifier version is **not recorded** rather than printing a number that
  would imply a comparison nobody made (RD8).

**It reads no clock and resolves no path.** The date is the caller's — sliced
off the newest record's own stamp — and the directory is handed in (ADR-M2-6).
Appending rather than overwriting: two runs on one day are two decisions, and a
file that keeps only the last one cannot answer "what did the run before this
one say?".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from shepherd.core.stops import STOP_RECORD_VERSION

__all__ = [
    "REPLAY_PREFIX",
    "ReplayChange",
    "ReplaySummary",
    "format_replay_diff",
    "write_replay_diff",
]


class ReplayChange(Protocol):
    """One before/after pair, structurally.

    `logs/` is L1 and `signals/` is L2, so this module may not import
    `ReplayReport` — the boundary scan fails the build on an upward import, and
    rightly: a log writer that knew the classifier's types could not be reused
    by M4's audit log. What it needs is a *shape*, and a `Protocol` states the
    shape without owning the type or naming its owner.
    """

    @property
    def session_id(self) -> str: ...

    @property
    def before(self) -> str | None: ...

    @property
    def after(self) -> str: ...

    @property
    def columns(self) -> Sequence[str]: ...


class ReplaySummary(Protocol):
    """What one run has to be able to say about itself, structurally."""

    @property
    def read(self) -> int: ...

    @property
    def skipped_malformed(self) -> int: ...

    @property
    def skipped_version(self) -> int: ...

    @property
    def orphaned(self) -> int: ...

    @property
    def reclassified(self) -> int: ...

    @property
    def changes(self) -> Sequence[ReplayChange]: ...

    @property
    def unknown_rate_before(self) -> float: ...

    @property
    def unknown_rate_after(self) -> float: ...

    @property
    def applied(self) -> bool: ...

    @property
    def unreadable_files(self) -> int: ...

    @property
    def skipped_undated(self) -> int: ...

    @property
    def classifier_failures(self) -> int: ...


#: The log's own subdirectory name, so the composition root and the tests spell
#: it once. A sibling of `stops/`, never interleaved with it.
REPLAY_PREFIX = "replay"

#: ADR-2's mode: a replay diff names sessions, briefs and verdicts.
DIRECTORY_MODE = 0o700

#: RD8, in the words a reader needs. Naming the absence is the point: a header
#: that printed a version nobody records would imply a comparison that did not
#: happen.
NO_CLASSIFIER_VERSION = (
    "classifier version: not recorded — this build has no rule-set versioning,"
    " so nothing here can say which rules wrote the 'before' column"
    " (--classifier is not implemented)"
)

APPLIED = "mode: applied — the stop columns below were overwritten"
DRY_RUN = "mode: dry run — no column was written; pass --apply to write them"


def format_replay_diff(report: ReplaySummary, date: str) -> str:
    """One run, as the block that gets appended. Pure — no path, no clock."""
    lines = [
        f"shepherd replay — {date}",
        f"  record version: {STOP_RECORD_VERSION}"
        " (the only stop-record version this build reads)",
        f"  {NO_CLASSIFIER_VERSION}",
        f"  {APPLIED if report.applied else DRY_RUN}",
        f"  read {report.read} records ({_skips(report)})",
        f"  reclassified {report.reclassified} sessions",
        f"  changed {len(report.changes)}:",
    ]
    for pair, count in _census(report).items():
        lines.append(f"    {pair} ({count})")
    for change in report.changes:
        lines.append(
            f"    {change.session_id} {change.before or 'no verdict'} → {change.after}"
            f"  [{', '.join(change.columns)}]"
        )
    lines.append(
        f"  unknown rate: {_percent(report.unknown_rate_before)}"
        f" → {_percent(report.unknown_rate_after)}"
        f" (over {report.reclassified - report.classifier_failures} readable records)"
    )
    lines.append(f"  classifier failures: {report.classifier_failures}")
    return "\n".join(lines) + "\n"


def write_replay_diff(report: ReplaySummary, diff_dir: Path, date: str) -> Path:
    """Append this run's block to `<diff_dir>/<date>.log` and return the path.

    A failure to write it is **not** swallowed the way a lost stop-log line is
    (C-M2-6): the stop log is the second consumer of a verdict a column already
    holds, while this file is the only record of what a replay decided. A
    caller that could not write it has to know.
    """
    diff_dir.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    path = diff_dir / f"{date}.log"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(format_replay_diff(report, date))
    return path


def _skips(report: ReplaySummary) -> str:
    """One number per work item, never one number for all of them (E-M2-21/22/25).

    A torn line, a record from a build that knows something this one does not, a
    record whose session is gone, a **file** the read had to abandon, and a
    partition a narrowed run could not place are five different fixes. The last
    two are the ones whose absence made a lossy read look like a small log:
    every counter at zero while 44 of 50 records were gone.
    """
    return (
        f"{report.skipped_malformed} malformed,"
        f" {report.skipped_version} unknown version,"
        f" {report.orphaned} orphaned,"
        f" {report.unreadable_files} unreadable files,"
        f" {report.skipped_undated} undated partitions skipped"
    )


def _census(report: ReplaySummary) -> Mapping[str, int]:
    """`unknown → stalled_pending_tool (31)` — §8's own shape, in first-seen
    order so the block is byte-identical for byte-identical runs."""
    counted: dict[str, int] = {}
    for change in report.changes:
        pair = f"{change.before or 'no verdict'} → {change.after}"
        counted[pair] = counted.get(pair, 0) + 1
    return counted


def _percent(rate: float) -> str:
    return f"{rate * 100:.1f}%"
