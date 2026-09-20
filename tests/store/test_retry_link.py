"""T10 — `retry_of` gets a writer, and it is the **only** one (D31, D33, D37).

Nothing in this tree wrote `retry_of` before this file existed. The column has
been in `001_m1_foundation.sql:64` since M1, T8 put it on the `Session`
dataclass and gave `reads.retry_chain_depth` a chain to walk, and no verb
anywhere could create a link for that walk to find. A cap read off a column no
code writes is a cap that passes every test over hand-planted rows and never
fires in production — which is the defect this milestone exists to refuse, not
an omission to be tidied later.

**The seam is `Store`**, the single name a caller imports (D33). The verb's
body lives in `store/writes.py` beside the other `UPDATE`s, and `db.py` holds
the delegation only — so the connection never leaves `store/` and the write
crosses ADR-7's one writer thread, which is asserted here rather than assumed.

**One writer, one rule set (D37).** `link_retry` is asserted to be the only
place in `src/` that writes the column, by parsing the SQL out of `store/` the
way `test_store_delegation.py` does — the same property `apply_stop_verdict`
holds for the nine stop columns.
"""

from __future__ import annotations

import ast
import sqlite3
import threading
import typing
from pathlib import Path

import pytest

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin
from shepherd.store import writes
from shepherd.store.db import Store, StoreError, open_store
from shepherd.store.models import Session

SRC = Path(__file__).resolve().parents[2] / "src" / "shepherd"

HANDLE = RunnerHandle(runner="tmux", socket="shepherd-runner", session_name="shepherd_01A")


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    opened.upsert_workspace("shepherd", "/root/Shepherd")
    try:
        yield opened
    finally:
        opened.close()


def attempt(store: Store, session_id: str, *, engine: str | None = None) -> str:
    """One owned, master-spawned session row, created by the shipped verb."""
    workspace = store.list_workspaces()[0]
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=engine if engine is not None else f"eng-{session_id}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T12:00:00Z",
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=HANDLE,
        model=None,
        effort=None,
    )
    return session_id


ROOT = "01ROOT000000000000000000"
SECOND = "01SECOND00000000000000000"[:24]
THIRD = "01THIRD000000000000000000"[:24]


def test_the_link_the_verb_writes_is_the_link_the_chain_walk_reads(store: Store) -> None:
    """Arrival first: the lineage is 1 deep before the link and 2 after it.

    This is the property the whole task rests on — `retry_chain_depth` walks
    `retry_of`, and until this verb existed nothing could put a value there for
    it to walk. The depth is asserted **before** the write as well as after, so
    a walk that returned 2 for every row would fail here rather than pass by
    accident.
    """
    attempt(store, ROOT)
    attempt(store, SECOND)
    assert store.retry_chain_depth(SECOND) == 1

    linked = store.link_retry(session_id=SECOND, retry_of=ROOT)

    assert linked.retry_of == ROOT
    assert store.get_session(SECOND) is not None
    assert store.retry_chain_depth(SECOND) == 2
    assert store.retry_chain_depth(ROOT) == 1


def test_a_lineage_is_written_once_and_never_rewritten(store: Store) -> None:
    """D31's cap is computed from this column, so it is not a field to correct.

    A relink is refused by the statement itself (`AND retry_of IS NULL`), not by
    the read above it: two writers racing one row would both pass a `SELECT`
    and the second would silently shorten the lineage — which is the direction
    that turns a guard off.
    """
    attempt(store, ROOT)
    attempt(store, SECOND)
    attempt(store, THIRD)
    store.link_retry(session_id=SECOND, retry_of=ROOT)

    with pytest.raises(StoreError) as refused:
        store.link_retry(session_id=SECOND, retry_of=THIRD)

    assert "written once" in str(refused.value)
    assert ROOT in str(refused.value), "the refusal does not name the link it kept"
    after = store.get_session(SECOND)
    assert after is not None and after.retry_of == ROOT


def test_a_link_that_would_close_a_loop_is_refused(store: Store) -> None:
    """A loop makes the lineage finite and **wrong**, which is worse than long.

    `retry_chain_depth` stops on the first repeat, so a cycle does not hang the
    daemon — it reports a depth that is a property of where the walk started.
    The writer is where a loop can still be refused, because it is the one place
    that knows both ends of the edge being written.
    """
    attempt(store, ROOT)
    attempt(store, SECOND)
    store.link_retry(session_id=SECOND, retry_of=ROOT)

    with pytest.raises(StoreError) as refused:
        store.link_retry(session_id=ROOT, retry_of=SECOND)

    assert "close a loop" in str(refused.value)
    root_row = store.get_session(ROOT)
    assert root_row is not None and root_row.retry_of is None


def test_a_self_link_is_refused(store: Store) -> None:
    """The one-element loop, which the lineage walk would read as depth 1 forever."""
    attempt(store, ROOT)

    with pytest.raises(StoreError) as refused:
        store.link_retry(session_id=ROOT, retry_of=ROOT)

    assert "retry of itself" in str(refused.value)


def test_an_unknown_session_and_an_unknown_target_both_refuse_as_a_value(
    store: Store,
) -> None:
    """`StoreError`, never the driver's `IntegrityError` (D33).

    `retry_of` is `REFERENCES session(id)` and `PRAGMA foreign_keys` is ON, so an
    unchecked target would surface a `sqlite3.IntegrityError` above `store/` —
    a driver exception escaping the package the import rule exists to contain.
    """
    attempt(store, ROOT)

    with pytest.raises(StoreError) as no_session:
        store.link_retry(session_id=THIRD, retry_of=ROOT)
    assert "to record a retry against" in str(no_session.value)

    with pytest.raises(StoreError) as no_target:
        store.link_retry(session_id=ROOT, retry_of=THIRD)
    assert "to be a retry of" in str(no_target.value)


# ----- the plumbing, and the one-writer property -----------------------------


def test_the_link_crosses_the_one_writer_thread_and_dies_with_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-7/D37: a verb wired to the reader answers correctly and still gives D37
    a second writer.

    The ident is read **from inside the verb**, not from the store afterwards: an
    earlier `create_owned_session` on the same store already put the writer
    thread's ident in that set, so `writer_thread_idents()` alone is green whether
    this verb crossed the thread or not. That was a survivor at the first pass of
    this suite's mutation ledger (MUT-12), and it is the shape of a check that
    reports success without checking.
    """
    ran_on: list[int] = []
    inner = writes.link_retry

    def recording(connection: sqlite3.Connection, session_id: str, retry_of: str) -> Session:
        ran_on.append(threading.get_ident())
        return inner(connection, session_id, retry_of)

    monkeypatch.setattr(writes, "link_retry", recording)

    opened = open_store(tmp_path / "data" / "shepherd.db")
    opened.upsert_workspace("shepherd", "/root/Shepherd")
    attempt(opened, ROOT)
    attempt(opened, SECOND)
    opened.link_retry(session_id=SECOND, retry_of=ROOT)

    idents = opened.writer_thread_idents()
    assert len(idents) == 1, f"ADR-7 says one writer thread, saw {len(idents)}"
    assert ran_on == list(idents), (ran_on, idents)
    assert threading.get_ident() not in ran_on, "the link ran on the calling thread"

    opened.close()
    with pytest.raises(Exception):  # noqa: B017 - the closed-store refusal, whatever it is
        opened.link_retry(session_id=SECOND, retry_of=ROOT)


def retry_of_writers() -> dict[str, list[str]]:
    """module -> the non-docstring statement literals in it that write `retry_of`.

    Docstrings are excluded for the M1 reason: prose naming a column is not a
    write, and a scan that cannot tell them apart makes every explanation a
    violation. `SESSION_COLUMNS` is not matched either — a `SELECT` list naming
    the column is a reader.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(
                node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            )
        }
        writes = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
            and "retry_of" in node.value
            and ("UPDATE" in node.value or "INSERT" in node.value)
        ]
        if writes:
            found[str(path.relative_to(SRC))] = writes
    return found


def test_link_retry_is_the_only_writer_of_the_lineage_column(store: Store) -> None:
    """D37, and the defect this task was given: **nothing** wrote this column.

    `retry_of` occurred in `src/` only in the migrations, the row mapping and a
    docstring — so the cap D31 asks for could pass every test over a chain
    planted with raw SQL and never fire once in production. This scan is what
    keeps the writer present and singular: it goes red if the verb is deleted
    (no writer again) and red if a second `UPDATE`/`INSERT` of the column
    appears anywhere else in `src/`.

    Arrival before absence: the scan is asserted to find something first, so a
    scan that matches nothing cannot report the property by finding no
    violations.
    """
    writers = retry_of_writers()
    assert writers, "the scan found no writer of retry_of anywhere — the scan is broken"
    assert set(writers) == {"store/writes.py"}, writers

    # …and the one it found is reachable through the store surface, not merely
    # present as a literal.
    attempt(store, ROOT)
    attempt(store, SECOND)
    assert store.link_retry(session_id=SECOND, retry_of=ROOT).retry_of == ROOT
