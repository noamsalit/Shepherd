"""T8 — D31's wake set and the retry-chain depth, at the `Store` verb seam.

The seam is the one `test_verbs.py` and `test_store_delegation.py` use: the
public `Store` surface over a real SQLite file in `tmp_path`. Nothing here is
handed a cursor, and the two reads under test are verbs (D33).

Two things are planted with SQL rather than with a verb, and both are recorded
as findings rather than smuggled in:

* `retry_of` has **no writer** anywhere in this tree — no task in the M4 plan
  produces one — so the lineage is planted directly. The *reads* are verbs;
  the fixture is not a caller.
* a stopped row carrying **no verdict** (E-M2-4's `unclassified` cohort) cannot
  be made through `apply_stop_verdict`, which always writes an outcome.

Both fixtures are inert: they write rows into a `tmp_path` database and execute
no code of their own (CLAUDE.md, "Mutations").
"""

from __future__ import annotations

import re
import sqlite3
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.states import Origin
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
from shepherd.store.db import Store, open_store

#: The three stamps the `since` clause is read against. `SINCE` sits between
#: them so that "already drained" and "stopped since you left" differ by
#: `ended_at` **alone** — a row excluded for two reasons at once cannot tell
#: you which clause did the excluding.
BEFORE = "2026-09-17T09:00:00Z"
SINCE = "2026-09-17T10:00:00Z"
AFTER = "2026-09-17T11:00:00Z"


def sid(name: str) -> str:
    return (name + "0" * 26)[:26]


@dataclass(frozen=True)
class Row:
    """One fixture row: what it is, and the single reason it is in or out."""

    session_id: str
    outcome: str | None
    origin: Origin
    ended_at: str
    kind: str


#: The fleet. Every allowed `outcome` value appears at least once, plus the
#: no-verdict row, plus the two kinds excluded by something other than their
#: outcome: a session the master does not own, and one it has already drained.
FLEET: tuple[Row, ...] = (
    Row(sid("01WAKEUNFINISHED"), Bucket.UNFINISHED.value, Origin.ORCHESTRATOR, AFTER, "wakes"),
    Row(sid("01WAKEERROR"), Bucket.ERROR.value, Origin.ORCHESTRATOR, AFTER, "wakes"),
    Row(sid("01NEEDSYOU"), Bucket.NEEDS_YOU.value, Origin.ORCHESTRATOR, AFTER, "outcome"),
    Row(sid("01FINISHED"), Bucket.FINISHED.value, Origin.ORCHESTRATOR, AFTER, "outcome"),
    Row(sid("01PAUSED"), Bucket.PAUSED.value, Origin.ORCHESTRATOR, AFTER, "outcome"),
    Row(sid("01BLOCKED"), Bucket.BLOCKED.value, Origin.ORCHESTRATOR, AFTER, "outcome"),
    Row(sid("01RUNNING"), Bucket.RUNNING.value, Origin.ORCHESTRATOR, AFTER, "outcome"),
    Row(sid("01NOVERDICT"), None, Origin.ORCHESTRATOR, AFTER, "no verdict"),
    Row(sid("01QUEUEOWNED"), Bucket.UNFINISHED.value, Origin.QUEUE_WORKER, AFTER, "not master"),
    Row(sid("01DRAINED"), Bucket.UNFINISHED.value, Origin.ORCHESTRATOR, BEFORE, "drained"),
)

#: D31's two rows, named rather than recomputed. Recomputing this set from
#: `FLEET` with the query's own predicate would be satisfied by construction:
#: it would agree with any query that agreed with itself.
WAKES = frozenset({sid("01WAKEUNFINISHED"), sid("01WAKEERROR")})

#: The lineage, root first. Its length is the population this test enumerates;
#: the depths asserted below are positions in it, never typed-in counts.
LINEAGE = (sid("01LINEAGEROOT"), sid("01LINEAGERETRY1"), sid("01LINEAGERETRY2"))


def raw(db_path: Path) -> sqlite3.Connection:
    """A connection the *fixture* holds. No verb under test is reached through
    it, and it never crosses into `src/`."""
    opened = sqlite3.connect(db_path, isolation_level=None)
    opened.row_factory = sqlite3.Row
    opened.execute("PRAGMA foreign_keys=ON")
    opened.execute("PRAGMA busy_timeout=5000")
    return opened


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "shepherd.db"


@pytest.fixture()
def store(db_path: Path) -> typing.Iterator[Store]:
    opened = open_store(db_path)
    opened.create_project(name="shepherd", description=None)
    try:
        yield opened
    finally:
        opened.close()


def spawn(store: Store, session_id: str, origin: Origin) -> None:
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=f"eng-{session_id}",
        workspace_id=next(w for w in store.list_workspaces() if w.name == "shepherd").id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at=BEFORE,
        origin=origin,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title="ship it",
        title_source="brief",
        handle=None,
        model="opus",
        effort="high",
    )


def verdict(bucket: str) -> Verdict:
    return Verdict(
        stop_reason=StopReason.INCOMPLETE,
        bucket=Bucket(bucket),
        why="the row's own sentence",
        confidence=0.9,
        decided_by=DecidedBy.HEURISTIC,
        next_actions=(),
        waiting_on=None,
        missing=(),
    )


def plant_fleet(store: Store, db_path: Path) -> None:
    for row in FLEET:
        spawn(store, row.session_id, row.origin)
        if row.outcome is None:
            # No verb writes a stop with no verdict (E-M2-4's cohort).
            connection = raw(db_path)
            try:
                connection.execute(
                    "UPDATE session SET state = 'stopped', ended_at = ? WHERE id = ?",
                    (row.ended_at, row.session_id),
                )
            finally:
                connection.close()
        else:
            store.apply_stop_verdict(row.session_id, verdict(row.outcome), row.ended_at, None)


def allowed_outcomes(db_path: Path) -> frozenset[str]:
    """The population the `outcome` column may hold, read out of the schema the
    migrations actually applied — not a list typed into this test. A migration
    that widens the column makes the coverage assertion below go red instead of
    leaving a new kind silently untested."""
    connection = raw(db_path)
    try:
        declaration = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'session'"
            ).fetchone()["sql"]
        )
    finally:
        connection.close()
    match = re.search(r"outcome\s+TEXT\s+CHECK\s*\([^)]*?IN\s*\(([^)]*)\)", declaration, re.S)
    assert match is not None, "the session table no longer declares an outcome CHECK"
    return frozenset(re.findall(r"'([a-z_]+)'", match.group(1)))


# ----- P-M4-12: the wake set -------------------------------------------------


def test_wake_candidates_is_exactly_the_unfinished_and_error_rows(
    store: Store, db_path: Path
) -> None:
    """D31's sentence, as a **set of ids** over a fleet holding one row of every
    excluded kind.

    Three assertions, in order, because the last one is meaningless without the
    first two:

    1. **arrival** — every planted row is readable, so "not in the wake set" is
       an exclusion and not a row that never landed;
    2. **coverage** — the fixture spans every value `outcome` may hold, checked
       against the enumerated population rather than a list typed here, so the
       fixture cannot quietly stop containing an excluded kind;
    3. the wake set equals D31's two rows.
    """
    plant_fleet(store, db_path)

    landed = {row.session_id for row in FLEET if store.get_session(row.session_id) is not None}
    assert landed == {row.session_id for row in FLEET}, "a fixture row never landed"

    allowed = allowed_outcomes(db_path)
    assert allowed == {bucket.value for bucket in Bucket} - {Bucket.UNCLASSIFIED.value}, (
        "`Bucket` and the `outcome` CHECK have drifted apart; one of them is now"
        " a population this fixture does not cover"
    )
    assert {row.outcome for row in FLEET} == allowed | {None}, (
        "the fixture no longer holds a row of every outcome the column allows"
    )

    assert {found.id for found in store.wake_candidates(SINCE)} == WAKES


def test_a_drained_row_returns_only_when_the_since_clause_is_dropped(
    store: Store, db_path: Path
) -> None:
    """The `ended_at > since` clause, proved against the one row that differs
    from a waking row by `ended_at` **alone**: it is absent with a `since` and
    present without one. Arrival first — the row is asserted to exist before it
    is asserted missing."""
    plant_fleet(store, db_path)
    drained = sid("01DRAINED")
    assert store.get_session(drained) is not None

    assert drained not in {found.id for found in store.wake_candidates(SINCE)}
    assert drained in {found.id for found in store.wake_candidates(None)}


def test_the_wake_set_hands_back_sessions_and_never_a_row(
    store: Store, db_path: Path
) -> None:
    """D33 rule 2 at the one new read surface: dataclasses, not driver rows."""
    plant_fleet(store, db_path)
    found = store.wake_candidates(SINCE)

    assert found, "arrival: the wake set is non-empty before its shape is asserted"
    for candidate in found:
        assert not isinstance(candidate, sqlite3.Row)
        assert candidate.origin is Origin.ORCHESTRATOR
        assert candidate.outcome in {Bucket.UNFINISHED.value, Bucket.ERROR.value}


# ----- the retry chain -------------------------------------------------------


def plant_lineage(store: Store, db_path: Path) -> None:
    """Three sessions, each the retry of the one before it — and `attempt`
    tampered flat to 1 on every one of them.

    The tamper is the point. D31 caps *master-initiated attempts per lineage*,
    and `attempt` is a column a caller writes: it can be stale, reset, or
    written by a second writer. The chain is the fact, so the fixture makes the
    column disagree with it.
    """
    for session_id in LINEAGE:
        spawn(store, session_id, Origin.ORCHESTRATOR)
    connection = raw(db_path)
    try:
        for child, parent in zip(LINEAGE[1:], LINEAGE):
            connection.execute(
                "UPDATE session SET retry_of = ? WHERE id = ?", (parent, child)
            )
        connection.execute(
            "UPDATE session SET attempt = 1 WHERE id IN (?, ?, ?)", LINEAGE
        )
    finally:
        connection.close()


def test_retry_chain_depth_walks_the_chain_not_the_column(
    store: Store, db_path: Path
) -> None:
    plant_lineage(store, db_path)

    rows = {session_id: store.get_session(session_id) for session_id in LINEAGE}
    assert all(row is not None for row in rows.values()), "a lineage row never landed"
    assert {row.attempt for row in rows.values() if row is not None} == {1}, (
        "the tamper did not take: reading `attempt` alone must answer 1 for every row"
        " in the lineage, so any depth above 1 can only have come from the chain"
    )
    assert [row.retry_of for row in rows.values() if row is not None] == [
        None,
        *LINEAGE[:-1],
    ], "the chain itself did not land"

    positions = {session_id: place for place, session_id in enumerate(LINEAGE, start=1)}
    assert {
        session_id: store.retry_chain_depth(session_id) for session_id in LINEAGE
    } == positions


def test_retry_chain_depth_of_an_unretried_session_is_one(
    store: Store, db_path: Path
) -> None:
    """The negative control the cap is read against: a first attempt is a
    lineage of one, not of zero. An off-by-one here turns the guard off."""
    plant_fleet(store, db_path)
    assert store.retry_chain_depth(sid("01WAKEERROR")) == 1


def test_retry_chain_depth_of_an_unknown_session_is_zero(store: Store) -> None:
    assert store.retry_chain_depth(sid("01NOSUCHSESSION")) == 0


def test_a_hand_edited_retry_cycle_terminates(store: Store, db_path: Path) -> None:
    """`retry_of` is a self-reference SQLite will happily let a hand edit close
    into a loop. A read verb that hangs is worse than one that answers: the
    walk stops at the first id it has already seen and reports the lineage it
    could see."""
    plant_lineage(store, db_path)
    connection = raw(db_path)
    try:
        connection.execute(
            "UPDATE session SET retry_of = ? WHERE id = ?", (LINEAGE[-1], LINEAGE[0])
        )
    finally:
        connection.close()

    assert store.retry_chain_depth(LINEAGE[-1]) == len(LINEAGE)
