"""T2 — the three stop verbs (D33), over a real SQLite file in `tmp_path`.

M1 created the eight stop columns and never wrote them. These are the verbs
that write and read them, and the seam is the verb: nothing above `store/` ever
sees SQL, a cursor or a `sqlite3.Row`.
"""

from __future__ import annotations

import ast
import json
import sqlite3
import typing
from pathlib import Path

import pytest

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.core.stops import (
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopReason,
    Verdict,
)
from shepherd.store import models
from shepherd.store.db import Store, open_store

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "shepherd.db"


@pytest.fixture()
def store(db_path: Path) -> typing.Iterator[Store]:
    opened = open_store(db_path)
    try:
        yield opened
    finally:
        opened.close()


def seed(store: Store, engine_session_id: str = "eng-1") -> models.Session:
    workspace = store.upsert_workspace("shepherd", "/root/Shepherd")
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )


def verdict(
    reason: StopReason = StopReason.RATE_LIMITED,
    bucket: Bucket = Bucket.PAUSED,
    confidence: float = 1.0,
    decided_by: DecidedBy = DecidedBy.MECHANICAL,
) -> Verdict:
    return Verdict(
        stop_reason=reason,
        bucket=bucket,
        why="the API asked us to slow down",
        confidence=confidence,
        decided_by=decided_by,
        next_actions=(
            NextAction(
                text="Wait for the limit to clear",
                kind=NextActionKind.RETRY,
                target=None,
                source=ActionSource.HEURISTIC,
            ),
            NextAction(
                text="Open the session",
                kind=NextActionKind.INSPECT,
                target="session:01",
                source=ActionSource.HEURISTIC,
            ),
        ),
        waiting_on=None,
        missing=("a tail",),
    )


def test_apply_stop_verdict_writes_all_eight_columns(store: Store) -> None:
    """§16 item 4: M1 created these columns and never wrote one of them."""
    session = seed(store)

    written = store.apply_stop_verdict(
        session_id=session.id,
        verdict=verdict(),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )

    assert written.stop_reason == "rate_limited"
    assert written.outcome == "paused"
    assert written.why == "the API asked us to slow down"
    assert written.confidence == 1.0
    assert written.decided_by == "mechanical"
    assert written.ended_at == "2026-09-17T11:00:00Z"
    assert written.exit_code is None
    assert len(written.next_actions) == 2

    # …and the value is durable, not just returned.
    reread = store.get_session(session.id)
    assert reread is not None
    assert reread.stop_reason == "rate_limited"
    assert reread.next_actions == written.next_actions


def test_apply_stop_verdict_records_an_exit_code_when_there_is_one(store: Store) -> None:
    """`exit_code` stays null for an attached session (C13) — but the column is
    written by this verb and nothing else, so it is tested here."""
    session = seed(store)
    written = store.apply_stop_verdict(
        session_id=session.id,
        verdict=verdict(StopReason.USER_EXITED, Bucket.FINISHED),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=0,
    )
    assert written.exit_code == 0


def test_next_actions_roundtrips_as_a_whole_value(store: Store, db_path: Path) -> None:
    """§7's JSON rule: read back whole, never queried into."""
    session = seed(store)
    store.apply_stop_verdict(
        session_id=session.id,
        verdict=verdict(),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )

    reread = store.get_session(session.id)
    assert reread is not None
    first, second = reread.next_actions
    assert isinstance(first, NextAction)
    assert first.text == "Wait for the limit to clear"
    assert first.kind is NextActionKind.RETRY
    assert first.target is None
    assert first.source is ActionSource.HEURISTIC
    assert second.target == "session:01"

    # The stored form is one JSON array, not columns the caller could query.
    raw = _raw_cell(db_path, session.id, "next_actions")
    decoded = json.loads(str(raw))
    assert isinstance(decoded, list) and len(decoded) == 2
    assert set(decoded[0]) == {"text", "kind", "target", "source"}


def test_a_verdict_with_no_actions_stores_an_empty_array(store: Store, db_path: Path) -> None:
    """`completed` is the one verdict that may carry nothing to do."""
    session = seed(store)
    done = Verdict(
        stop_reason=StopReason.COMPLETED,
        bucket=Bucket.FINISHED,
        why="the model ended its turn with every task done",
        confidence=1.0,
        decided_by=DecidedBy.HEURISTIC,
        next_actions=(),
        waiting_on=None,
        missing=(),
    )
    written = store.apply_stop_verdict(
        session_id=session.id, verdict=done, ended_at="2026-09-17T11:00:00Z", exit_code=None
    )
    assert written.next_actions == ()
    assert _raw_cell(db_path, session.id, "next_actions") == "[]"


def test_a_second_verdict_overwrites_the_first(store: Store) -> None:
    """E-M2-5: S18 has two `Stop`s in one session; the later verdict wins."""
    session = seed(store)
    store.apply_stop_verdict(
        session_id=session.id,
        verdict=verdict(),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )
    store.apply_stop_verdict(
        session_id=session.id,
        verdict=verdict(StopReason.COMPLETED, Bucket.FINISHED, 0.5, DecidedBy.HEURISTIC),
        ended_at="2026-09-17T12:00:00Z",
        exit_code=None,
    )
    reread = store.get_session(session.id)
    assert reread is not None
    assert reread.stop_reason == "completed"
    assert reread.decided_by == "heuristic"
    assert reread.ended_at == "2026-09-17T12:00:00Z"


def test_apply_stop_verdict_refuses_an_unknown_session(store: Store) -> None:
    """A verdict for a row that is not there is a bug, not a silent no-op."""
    from shepherd.store.db import StoreError

    with pytest.raises(StoreError):
        store.apply_stop_verdict(
            session_id="no-such-session",
            verdict=verdict(),
            ended_at="2026-09-17T11:00:00Z",
            exit_code=None,
        )


def test_stop_verdict_counts_separates_unknown_from_unclassified(store: Store) -> None:
    """ADR-M2-5: `unknown` is a reason we wrote; `unclassified` is a row with no
    verdict at all (E-M2-4). Folding them together hides the tuning backlog."""
    classified = seed(store, "eng-classified")
    unknown = seed(store, "eng-unknown")
    lost = seed(store, "eng-never-classified")
    # E-M2-4: a `StopFailure` lost at `-p` shutdown leaves a row the fold moved
    # to `stopped` and no verdict ever reached. That is the unclassified cohort.
    store.apply_fold_delta(lost.id, FoldDelta(state=SessionState.STOPPED))
    # …and a session that is still running is neither classified nor unclassified.
    seed(store, "eng-still-running")

    store.apply_stop_verdict(
        session_id=classified.id,
        verdict=verdict(),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )
    store.apply_stop_verdict(
        session_id=unknown.id,
        verdict=verdict(StopReason.UNKNOWN, Bucket.UNFINISHED, 0.0),
        ended_at="2026-09-17T11:01:00Z",
        exit_code=None,
    )

    counts = store.stop_verdict_counts()
    assert counts.classified == 2
    assert counts.unknown == 1
    assert counts.unclassified == 1
    assert counts.by_reason == {"rate_limited": 1, "unknown": 1}


def test_stop_verdict_counts_reports_low_confidence_completions(store: Store) -> None:
    """DP10 / r3 BLOCKING 4 — the residue D34 wants counted. Revision 2 rendered
    it as a green chip and counted it nowhere."""
    heuristic = seed(store, "eng-heuristic")
    certain = seed(store, "eng-certain")

    store.apply_stop_verdict(
        session_id=heuristic.id,
        verdict=verdict(StopReason.COMPLETED, Bucket.FINISHED, 0.5, DecidedBy.HEURISTIC),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )
    store.apply_stop_verdict(
        session_id=certain.id,
        verdict=verdict(StopReason.COMPLETED, Bucket.FINISHED, 1.0, DecidedBy.DECLARED),
        ended_at="2026-09-17T11:01:00Z",
        exit_code=None,
    )

    counts = store.stop_verdict_counts()
    assert counts.completed_low_confidence == 1
    assert counts.by_reason == {"completed": 2}


def test_stop_verdict_counts_on_an_empty_store(store: Store) -> None:
    counts = store.stop_verdict_counts()
    assert counts.classified == 0
    assert counts.unclassified == 0
    assert counts.unknown == 0
    assert counts.completed_low_confidence == 0
    assert counts.by_reason == {}


def test_sessions_for_replay_returns_dataclasses(store: Store) -> None:
    """D33 rule 2 — no `sqlite3.Row` escapes the package."""
    import dataclasses

    first = seed(store, "eng-1")
    second = seed(store, "eng-2")
    store.apply_stop_verdict(
        session_id=first.id,
        verdict=verdict(),
        ended_at="2026-09-17T11:00:00Z",
        exit_code=None,
    )
    store.apply_stop_verdict(
        session_id=second.id,
        verdict=verdict(StopReason.COMPLETED, Bucket.FINISHED),
        ended_at="2026-09-17T13:00:00Z",
        exit_code=None,
    )

    targets = store.sessions_for_replay(None)
    assert [type(target) for target in targets] == [models.ReplayTarget] * 2
    assert all(dataclasses.is_dataclass(target) for target in targets)
    assert {target.stop_reason for target in targets} == {"rate_limited", "completed"}
    assert {target.engine_session_id for target in targets} == {"eng-1", "eng-2"}

    # `since` narrows by the stop's own time, not by the row's.
    later = store.sessions_for_replay("2026-09-17T12:00:00Z")
    assert [target.engine_session_id for target in later] == ["eng-2"]

    # A session with no verdict **is** a replay target, carrying `stop_reason
    # None`. It is E-M2-4's cohort — the fold moved the row on and no verdict
    # ever arrived — and excluding it is what made `replay` report a
    # never-classified session as `orphaned`, a word that means "purged".
    # Nothing is written for it unless the stop log holds a record naming it.
    seed(store, "eng-3")
    everyone = store.sessions_for_replay(None)
    assert [target.engine_session_id for target in everyone] == ["eng-3", "eng-1", "eng-2"]
    assert [target.stop_reason for target in everyone] == [None, "rate_limited", "completed"]


def test_apply_stop_verdict_is_the_only_stop_writer() -> None:
    """One writer for the stop columns, found by what the source *contains*."""
    offenders = [
        str(path.relative_to(SRC_ROOT))
        for path in sorted(SRC_ROOT.rglob("*.py"))
        for source in [path.read_text(encoding="utf-8")]
        if "UPDATE session SET stop_" in source or "UPDATE session SET\n" in source
        if path.name != "stops.py"
    ]
    assert offenders == []
    # …and the scan is real: the one legitimate writer is found by it.
    writer = (SRC_ROOT / "store" / "stops.py").read_text(encoding="utf-8")
    assert "UPDATE session SET stop_" in writer


def test_store_stops_is_the_only_new_sql_site() -> None:
    """`db.py` was at 535/600 lines; the SQL lives next door so it stays there."""
    db_source = (SRC_ROOT / "store" / "db.py").read_text(encoding="utf-8")
    assert len(db_source.splitlines()) < 600
    for path in sorted(SRC_ROOT.rglob("*.py")):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 600, path


def test_stop_counts_carry_no_query_material() -> None:
    """`StopCounts` is enough to compute the `unknown` rate and not enough to
    reconstruct a query — the D33 line between a verb and a view."""
    import dataclasses

    names = {field.name for field in dataclasses.fields(models.StopCounts)}
    assert names == {
        "by_reason",
        "classified",
        "unclassified",
        "unknown",
        "completed_low_confidence",
    }


def test_no_verb_takes_sql_shaped_arguments() -> None:
    """The three new verbs obey D33 rule 1, checked at the signature."""
    import inspect

    for name in ("apply_stop_verdict", "stop_verdict_counts", "sessions_for_replay"):
        parameters = set(inspect.signature(getattr(Store, name)).parameters)
        assert parameters & {"sql", "query", "where", "order_by", "params"} == set(), name


def test_store_stops_module_opens_no_connection() -> None:
    """ADR-7: the connection is the writer thread's, handed in (`db.py` owns it)."""
    tree = ast.parse((SRC_ROOT / "store" / "stops.py").read_text(encoding="utf-8"))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "connect" not in calls


def _raw_cell(db_path: Path, session_id: str, column: str) -> object:
    """Read one cell behind the verbs, to prove the *stored* shape (not the API)."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            f"SELECT {column} FROM session WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        connection.close()
    return row[0]
