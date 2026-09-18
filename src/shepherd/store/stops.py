"""The stop columns' SQL and their row mapping (T2, D33).

Split out of `db.py` for the reason `rows.py` was: `db.py` sits at 535 of
ADR-1's 600 lines, and the three stop verbs plus their row mapping would push
it over. The split follows the same seam — `db.py` owns *what the store can be
asked to do*, this module owns *how the stop group is written and counted*.

`db.py` hands every function here the connection its writer thread owns
(ADR-7). Nothing in this module opens one, resolves a path or reads a clock.

**One writer for the stop columns.** `apply_stop_verdict` holds the only
`UPDATE session SET stop_…` in `src/`, asserted by
`test_apply_stop_verdict_is_the_only_stop_writer`. Eight columns written in one
statement is what makes C-M2-7 — "a verdict is always reconstructible" —
something a reader can check rather than hope for.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from shepherd.core.stops import (
    ActionSource,
    NextAction,
    NextActionKind,
    Verdict,
)
from shepherd.store.models import ReplayTarget, StopCounts

#: The stop group, as `models.py`'s `SESSION_COLUMNS` names it. Kept here so the
#: column list and the SQL that writes it move together.
STOP_COLUMNS = (
    "stop_reason, outcome, why, confidence, decided_by, next_actions, exit_code,"
    " auto_compact_at, quota_notice_at"
)

#: The one stop write. Eight columns plus `ended_at`, in a single statement, so
#: a verdict is never half-applied.
_UPDATE = (
    "UPDATE session SET stop_reason = ?, outcome = ?, why = ?, confidence = ?,"
    " decided_by = ?, next_actions = ?, ended_at = ?, exit_code = ?"
    " WHERE id = ?"
)


#: The `unknown` rate's inputs in one grouped pass. `low_confidence` rides
#: along rather than costing a second query — DP10's residue is needed on the
#: same page as the rate it qualifies.
COUNTS_SQL = (
    "SELECT stop_reason, COUNT(*) AS n,"
    " SUM(CASE WHEN stop_reason = ? AND confidence < ? THEN 1 ELSE 0 END) AS low_confidence"
    " FROM session WHERE stop_reason IS NOT NULL"
    " GROUP BY stop_reason ORDER BY stop_reason"
)

#: E-M2-4's cohort: the fold moved the row to `stopped` and no verdict ever
#: arrived. Never green, never red, always counted.
UNCLASSIFIED_SQL = "SELECT COUNT(*) AS n FROM session WHERE stop_reason IS NULL AND state = ?"

#: Every session `replay` may rewrite — **including the never-classified**.
#:
#: This read used to say `WHERE stop_reason IS NOT NULL`, two lines below
#: `UNCLASSIFIED_SQL`, which defines E-M2-4's cohort as exactly the rows that
#: clause excludes. A session the fold moved to `stopped` with no verdict was
#: therefore absent from `targets` and its record came back counted as
#: `orphaned` — whose documented meaning is "the session is no longer in the
#: store". A never-classified session and a purged one were one number, and
#: `replay` could not classify an unclassified session at all, which is the
#: whole of what D3 promises it does. (Decision: blocker file, T12-3.)
#: The eight columns `apply_stop_verdict` writes, as a replay reads them back to
#: say which of them moved. One spelling, beside the `UPDATE` that writes them.
REPLAYED_COLUMNS = (
    "stop_reason",
    "outcome",
    "why",
    "confidence",
    "decided_by",
    "next_actions",
    "ended_at",
    "exit_code",
)

_REPLAY_SELECT = (
    "SELECT id, engine_session_id, stop_reason, outcome, why, confidence, decided_by,"
    " next_actions, ended_at, exit_code FROM session"
)
REPLAY_SQL = f"{_REPLAY_SELECT} ORDER BY ended_at, id"
REPLAY_SINCE_SQL = f"{_REPLAY_SELECT} WHERE ended_at >= ? ORDER BY ended_at, id"


def encode_actions(actions: tuple[NextAction, ...]) -> str:
    """One JSON array, read back whole and never queried into (§7).

    Sorted keys and a fixed separator, so the same verdict is the same bytes on
    every write — a replayed row has to be byte-identical run to run (T12).
    """
    return json.dumps(
        [
            {
                "text": action.text,
                "kind": str(action.kind.value),
                "target": action.target,
                "source": str(action.source.value),
            }
            for action in actions
        ],
        separators=(", ", ": "),
    )


def decode_actions(raw: str) -> tuple[NextAction, ...]:
    """The inverse. A record we cannot read degrades to *no actions*, never to
    a raise: a row that will not render is worse than a row with none."""
    try:
        decoded: object = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(decoded, list):
        return ()
    actions: list[NextAction] = []
    for item in decoded:
        if not isinstance(item, Mapping):
            continue
        text = item.get("text")
        kind = item.get("kind")
        target = item.get("target")
        source = item.get("source")
        if not isinstance(text, str) or not isinstance(kind, str):
            continue
        if kind not in {member.value for member in NextActionKind}:
            continue
        actions.append(
            NextAction(
                text=text,
                kind=NextActionKind(kind),
                target=target if isinstance(target, str) else None,
                source=(
                    ActionSource(source)
                    if isinstance(source, str)
                    and source in {member.value for member in ActionSource}
                    else ActionSource.HEURISTIC
                ),
            )
        )
    return tuple(actions)


def write_verdict(
    connection: sqlite3.Connection,
    session_id: str,
    verdict: Verdict,
    ended_at: str,
    exit_code: int | None,
) -> int:
    """The eight columns, one statement. Returns the number of rows changed."""
    cursor = connection.execute(
        _UPDATE,
        (
            str(verdict.stop_reason.value),
            str(verdict.bucket.value),
            verdict.why,
            verdict.confidence,
            str(verdict.decided_by.value),
            encode_actions(verdict.next_actions),
            ended_at,
            exit_code,
            session_id,
        ),
    )
    return int(cursor.rowcount)


def read_counts(rows: list[sqlite3.Row], stopped_without_a_verdict: int) -> StopCounts:
    """Fold the one grouped query into the shape the fleet page needs.

    Enough for the caller to compute the `unknown` rate, show the
    `unclassified` count and see DP10's residue **without a second query**, and
    deliberately not enough for the caller to reconstruct a query.
    """
    by_reason: dict[str, int] = {}
    classified = 0
    low_confidence = 0
    for row in rows:
        reason = str(row["stop_reason"])
        count = int(row["n"])
        by_reason[reason] = by_reason.get(reason, 0) + count
        classified += count
        low_confidence += int(row["low_confidence"])
    return StopCounts(
        by_reason=by_reason,
        classified=classified,
        unclassified=stopped_without_a_verdict,
        unknown=by_reason.get("unknown", 0),
        completed_low_confidence=low_confidence,
    )


def replay_target(row: sqlite3.Row) -> ReplayTarget:
    """One row, as the eight columns a replay may move — decoded, never raw.

    `next_actions` is decoded here rather than compared as JSON text: the
    caller is asking *did this column's value move*, and two encodings of the
    same actions are the same value.
    """
    raw_actions = row["next_actions"]
    return ReplayTarget(
        session_id=str(row["id"]),
        engine_session_id=(
            None if row["engine_session_id"] is None else str(row["engine_session_id"])
        ),
        stop_reason=None if row["stop_reason"] is None else str(row["stop_reason"]),
        outcome=None if row["outcome"] is None else str(row["outcome"]),
        why=None if row["why"] is None else str(row["why"]),
        confidence=None if row["confidence"] is None else float(row["confidence"]),
        decided_by=None if row["decided_by"] is None else str(row["decided_by"]),
        next_actions=() if raw_actions is None else decode_actions(str(raw_actions)),
        ended_at=None if row["ended_at"] is None else str(row["ended_at"]),
        exit_code=None if row["exit_code"] is None else int(row["exit_code"]),
    )
