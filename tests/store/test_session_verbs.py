"""T4 — the owned-session verbs (D33), over a real SQLite file in `tmp_path`.

The seam is the verb, as it is for `test_verbs.py` and `test_stop_verbs.py`:
nothing above `store/` sees SQL, a cursor or a `sqlite3.Row`. These tests hold
the connection directly because the verbs take the one `db.py`'s writer thread
owns (ADR-7), and because two of the claims — the pre-registration race
(C-M3-7) and binding an unbound `ask_fork` row — are **concurrency** claims
that a single-writer harness would settle by ordering rather than by the index.
"""

from __future__ import annotations

import dataclasses
import itertools
import sqlite3
import threading
import typing
from pathlib import Path

import pytest

from shepherd.core.runner import (
    MAX_CHILDREN_PER_SESSION,
    MAX_TOTAL_OWNED_SESSIONS,
    RunnerHandle,
)
from shepherd.core.states import TITLE_SOURCE_RANK, Origin, Ownership, SessionState, TitleSource
from shepherd.store import models, sessions
from shepherd.store.db import StoreError, open_store
from shepherd.store.migrate import migrate
from shepherd.store.models import Session

HANDLE = RunnerHandle(runner="tmux", socket="shepherd-runner", session_name="shepherd_01A")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "shepherd.db"
    migrate(path)
    opened = connect(path)
    try:
        opened.execute(
            "INSERT INTO workspace (id, name, root_path, created_at)"
            " VALUES ('ws-1', 'shepherd', '/root/Shepherd', '2026-09-17T10:00:00Z')"
        )
        opened.commit()
    finally:
        opened.close()
    return path


def connect(path: Path) -> sqlite3.Connection:
    opened = sqlite3.connect(path, isolation_level=None)
    opened.row_factory = sqlite3.Row
    opened.execute("PRAGMA journal_mode=WAL")
    opened.execute("PRAGMA foreign_keys=ON")
    opened.execute("PRAGMA busy_timeout=5000")
    return opened


@pytest.fixture()
def connection(db_path: Path) -> typing.Iterator[sqlite3.Connection]:
    opened = connect(db_path)
    try:
        yield opened
    finally:
        opened.close()


def create(
    connection: sqlite3.Connection,
    session_id: str = "01SESSION0000000000000000",
    *,
    engine_session_id: str | None = "eng-1",
    origin: Origin = Origin.ORCHESTRATOR,
    parent_session_id: str | None = None,
    depth: int = 0,
    ephemeral: bool = False,
    title: str | None = "ship it",
    title_source: TitleSource = "brief",
    handle: RunnerHandle | None = HANDLE,
) -> Session:
    return sessions.create_owned_session(
        connection,
        session_id=session_id,
        engine_session_id=engine_session_id,
        workspace_id="ws-1",
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T10:00:00Z",
        origin=origin,
        parent_session_id=parent_session_id,
        depth=depth,
        ephemeral=ephemeral,
        title=title,
        title_source=title_source,
        handle=handle,
        model="opus",
        effort="high",
    )


def end(connection: sqlite3.Connection, session_id: str) -> None:
    """Stop a row the way M2's stop verb does, without importing its lane."""
    connection.execute(
        "UPDATE session SET state = 'stopped', ended_at = '2026-09-17T11:00:00Z'"
        " WHERE id = ?",
        (session_id,),
    )


# ----- creation: ownership, origin, handle ----------------------------------


def test_create_owned_session_sets_ownership_origin_and_handle(
    connection: sqlite3.Connection,
) -> None:
    """An owned row is owned because the verb says so, never by a default.

    D1's two classes are the whole of M3: a spawn that landed as `attached`
    would be invisible to every owned-session code path and terminable by none.
    """
    created = create(connection, origin=Origin.USER_UI)

    assert created.ownership is Ownership.OWNED
    assert created.origin is Origin.USER_UI
    assert created.runner_handle == HANDLE
    assert created.state is SessionState.STARTING
    assert created.model == "opus"
    assert created.title == "ship it"
    assert created.title_source == "brief"

    stored = sessions.get_owned_session(connection, created.id)
    assert stored == created


def test_create_owned_session_is_idempotent_on_engine_session_id(
    connection: sqlite3.Connection,
) -> None:
    """C-M3-7's race: the row exists before the process does, and a discovery
    sweep that registers the same engine id must not make a second row."""
    first = create(connection, "01FIRST00000000000000000", engine_session_id="eng-1")
    second = create(connection, "01SECOND0000000000000000", engine_session_id="eng-1")

    assert second.id == first.id, "the pre-registered row wins by existing first"
    assert sessions.owned_session_counts(connection) == (1, 0)


def test_concurrent_creates_of_one_engine_id_leave_exactly_one_row(db_path: Path) -> None:
    """`ux_session_engine_id` is the mechanism, so the claim is tested against
    concurrent callers: eight spawns of one engine id, one row."""
    workers = 8
    failures: list[BaseException] = []
    barrier = threading.Barrier(workers)

    def spawn(index: int) -> None:
        own = connect(db_path)
        barrier.wait()
        try:
            own.execute("BEGIN IMMEDIATE")
            create(own, f"01ROW{index:020d}", engine_session_id="eng-1")
            own.execute("COMMIT")
        except BaseException as error:  # noqa: BLE001 - reported, not swallowed
            failures.append(error)
        finally:
            own.close()

    threads = [threading.Thread(target=spawn, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == [], f"a spawn raised: {failures}"
    reader = connect(db_path)
    try:
        assert sessions.owned_session_counts(reader) == (1, 0)
    finally:
        reader.close()


def test_an_owned_spawn_never_creates_an_unbound_row(connection: sqlite3.Connection) -> None:
    """`engine_session_id=None` is the ask-fork branch **only** (A25).

    A spawn always knows the uuid it passed to `--session-id`, so an unbound
    spawn row would reopen the duplicate-row hole `--session-id` exists to
    close: the discovery sweep would register the engine's own id as a second
    row, and both would claim the same pane.
    """
    for origin in Origin:
        if origin is Origin.ASK_FORK:
            continue
        with pytest.raises(StoreError) as refusal:
            create(
                connection,
                "01UNBOUND000000000000000",
                engine_session_id=None,
                origin=origin,
            )
        assert "ask_fork" in str(refusal.value)

    forked = create(
        connection,
        "01FORK000000000000000000",
        engine_session_id=None,
        origin=Origin.ASK_FORK,
        ephemeral=True,
    )
    assert forked.engine_session_id is None
    assert forked.ephemeral is True


# ----- binding and rebinding -------------------------------------------------


def test_an_unbound_ask_fork_row_binds_and_then_reads_back_that_id(
    connection: sqlite3.Connection,
) -> None:
    """The P2-refused branch: the row is created unbound and bound afterwards
    from the `-p` result object's own `session_id` (A25, T15)."""
    create(connection, "01FORK000000000000000000", engine_session_id=None, origin=Origin.ASK_FORK)

    sessions.rebind_engine_session_id(connection, "01FORK000000000000000000", "fork-1")

    bound = sessions.get_owned_session(connection, "01FORK000000000000000000")
    assert bound is not None
    assert bound.engine_session_id == "fork-1"
    assert bound.origin is Origin.ASK_FORK


def test_an_unbound_ask_fork_row_is_bindable_exactly_once(db_path: Path) -> None:
    """Six forks racing to bind one unbound row: one wins, five are told they lost.

    Silently repointing an already-bound row is the failure this guards — a
    loser would believe its own fork id was on the row while the winner's was.

    This shipped as a strict xfail against blocker T4-1, because one verb
    carrying C14's *move* semantics cannot also refuse a second bind: a
    compare-and-set settles nothing under D37's single writer, since the
    transactions serialise and every caller reads what the previous one
    committed. `bind_engine_session_id` is the split verb, and its guard is the
    mechanism `mark_delivered` already uses — the condition
    (`engine_session_id IS NULL`) is evaluated *inside* the write, so
    serialisation is what makes it correct rather than what defeats it, and the
    write reports its own rowcount.
    """
    seed = connect(db_path)
    try:
        create(seed, "01FORK000000000000000000", engine_session_id=None, origin=Origin.ASK_FORK)
    finally:
        seed.close()

    workers = 6
    barrier = threading.Barrier(workers)
    outcomes: dict[str, int] = {}
    lock = threading.Lock()

    def bind(index: int) -> None:
        own = connect(db_path)
        barrier.wait()
        try:
            own.execute("BEGIN IMMEDIATE")
            changed = sessions.bind_engine_session_id(
                own, "01FORK000000000000000000", f"fork-{index}"
            )
            own.execute("COMMIT")
        finally:
            own.close()
        with lock:
            outcomes[f"fork-{index}"] = changed

    threads = [threading.Thread(target=bind, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    bound = sorted(name for name, changed in outcomes.items() if changed == 1)
    assert sum(outcomes.values()) == 1, f"exactly one bind may win, not {bound}"
    assert len(bound) == 1
    assert sorted(outcomes) == sorted(f"fork-{index}" for index in range(workers))
    reader = connect(db_path)
    try:
        row = sessions.get_owned_session(reader, "01FORK000000000000000000")
    finally:
        reader.close()
    assert row is not None
    assert row.engine_session_id == bound[0], "the winner's id is the one on the row"


def test_bind_refuses_an_already_bound_row_and_says_so(
    connection: sqlite3.Connection,
) -> None:
    """Sequentially, too: the second binder moves nothing and is told it moved nothing.

    The concurrent case above is settled by the same clause, but a caller that
    binds twice by mistake is the likelier bug (T15's P2-refused branch retries),
    and `0` is the answer that lets it notice.
    """
    create(connection, "01FORK000000000000000000", engine_session_id=None, origin=Origin.ASK_FORK)

    assert sessions.bind_engine_session_id(connection, "01FORK000000000000000000", "fork-a") == 1
    assert sessions.bind_engine_session_id(connection, "01FORK000000000000000000", "fork-b") == 0

    bound = sessions.get_owned_session(connection, "01FORK000000000000000000")
    assert bound is not None
    assert bound.engine_session_id == "fork-a", "the first binding is not repointed"


def test_binding_an_unknown_session_binds_nothing(connection: sqlite3.Connection) -> None:
    """No row matched, so no row moved — the same `0` a bound row reports."""
    assert sessions.bind_engine_session_id(connection, "01NOSUCHROW00000000000000", "eng-1") == 0


def test_rebind_moves_the_engine_session_id_and_keeps_the_row(
    connection: sqlite3.Connection,
) -> None:
    """C14: `/resume` ends the old engine id in the same pane. The row keeps its
    identity — and its stop history — and changes one column.

    A delete-and-insert would satisfy "the new id is on a row" and lose every
    prior fact about the session, so the assertions are on the *old* row's
    fields surviving.
    """
    created = create(connection, engine_session_id="eng-old")
    connection.execute(
        "UPDATE session SET stop_reason = 'cleared', why = 'an earlier stop' WHERE id = ?",
        (created.id,),
    )

    sessions.rebind_engine_session_id(connection, created.id, "eng-new")

    rebound = sessions.get_owned_session(connection, created.id)
    assert rebound is not None
    assert rebound.id == created.id
    assert rebound.engine_session_id == "eng-new"
    assert rebound.started_at == created.started_at
    assert rebound.stop_reason == "cleared"
    assert rebound.why == "an earlier stop"
    assert rebound.state is SessionState.STARTING, "a rebind is not a stop"
    assert rebound.ended_at is None


def test_rebinding_to_the_id_already_on_the_row_is_a_no_op(
    connection: sqlite3.Connection,
) -> None:
    """A retrying caller is not a racing caller (D12's lesson, on this column)."""
    created = create(connection, engine_session_id="eng-1")
    sessions.rebind_engine_session_id(connection, created.id, "eng-1")

    rebound = sessions.get_owned_session(connection, created.id)
    assert rebound is not None
    assert rebound.engine_session_id == "eng-1"


def test_rebinding_an_unknown_session_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(StoreError):
        sessions.rebind_engine_session_id(connection, "01NOSUCHROW00000000000000", "eng-1")


def test_set_runner_handle_binds_the_pane_to_the_row(
    connection: sqlite3.Connection,
) -> None:
    """Step 5 of the spawn: the row exists first (C-M3-7), the handle follows."""
    created = create(connection, handle=None)
    assert created.runner_handle is None

    sessions.set_runner_handle(connection, created.id, HANDLE)

    stored = sessions.get_owned_session(connection, created.id)
    assert stored is not None
    assert stored.runner_handle == HANDLE

    with pytest.raises(StoreError):
        sessions.set_runner_handle(connection, "01NOSUCHROW00000000000000", HANDLE)


# ----- the title ratchet (D29) ----------------------------------------------


def test_apply_title_ratchets_and_never_reverts(connection: sqlite3.Connection) -> None:
    """All nine `(prior, incoming)` pairs of `user > engine > brief` (D29).

    The expected outcome comes from the spec's precedence rule, not from
    re-running the store's own comparison: a lower-ranked source never wins, an
    equal or higher one does.
    """
    ranks = TITLE_SOURCE_RANK
    pairs: list[tuple[TitleSource, TitleSource]] = list(
        itertools.product(("user", "engine", "brief"), ("user", "engine", "brief"))
    )
    assert len(pairs) == 9

    for index, (prior, incoming) in enumerate(pairs):
        session_id = f"01TITLE{index:018d}"
        create(
            connection,
            session_id,
            engine_session_id=f"eng-title-{index}",
            title=f"{prior} title",
            title_source=prior,
        )

        updated = sessions.apply_title(connection, session_id, f"{incoming} title", incoming)

        if ranks[incoming] >= ranks[prior]:
            assert updated.title == f"{incoming} title", (prior, incoming)
            assert updated.title_source == incoming, (prior, incoming)
        else:
            assert updated.title == f"{prior} title", (prior, incoming)
            assert updated.title_source == prior, (prior, incoming)


def test_an_engine_title_never_overwrites_a_user_rename(
    connection: sqlite3.Connection,
) -> None:
    """The one pair D29 names outright, asserted on its own so the ratchet
    cannot be weakened to "last writer wins" while the loop above still reads
    as if it covers something."""
    created = create(connection, title="draft", title_source="brief")
    sessions.apply_title(connection, created.id, "my rename", "user")
    after = sessions.apply_title(connection, created.id, "generated title", "engine")

    assert after.title == "my rename"
    assert after.title_source == "user"


def test_apply_title_on_an_unknown_session_is_refused(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(StoreError):
        sessions.apply_title(connection, "01NOSUCHROW00000000000000", "x", "user")


def test_title_synced_at_is_only_set_with_a_confirmation(
    connection: sqlite3.Connection,
) -> None:
    """D29: the stamp records a write-back the engine **accepted**.

    No creation and no rename may stamp it — a stamp written from the send
    would turn `can_set_title`'s honest `local only` marker into the silent
    half-success the decision refuses.
    """
    created = create(connection, title="draft", title_source="brief")
    assert created.title_synced_at is None

    renamed = sessions.apply_title(connection, created.id, "my rename", "user")
    assert renamed.title_synced_at is None

    sessions.set_title_synced_at(connection, created.id, "2026-09-17T10:30:00Z")
    confirmed = sessions.get_owned_session(connection, created.id)
    assert confirmed is not None
    assert confirmed.title_synced_at == "2026-09-17T10:30:00Z"

    again = sessions.apply_title(connection, created.id, "renamed twice", "user")
    assert again.title == "renamed twice"
    assert again.title_synced_at is None, "a new title was never confirmed by the engine"


def test_a_refused_title_leaves_the_confirmation_alone(
    connection: sqlite3.Connection,
) -> None:
    """The ratchet refused the write, so there is nothing new to confirm — and
    clearing the stamp would report a sync that is still true as lost."""
    created = create(connection, title="my rename", title_source="user")
    sessions.set_title_synced_at(connection, created.id, "2026-09-17T10:30:00Z")

    after = sessions.apply_title(connection, created.id, "generated", "engine")
    assert after.title == "my rename"
    assert after.title_synced_at == "2026-09-17T10:30:00Z"


# ----- ephemeral, the caps, and children ------------------------------------


def test_set_ephemeral_moves_a_row_on_and_off_the_fleet_page(
    connection: sqlite3.Connection,
) -> None:
    """DP2: an `ask` fork is ephemeral from birth and never reaches the fleet."""
    created = create(connection, ephemeral=False)
    sessions.set_ephemeral(connection, created.id, True)

    hidden = sessions.get_owned_session(connection, created.id)
    assert hidden is not None
    assert hidden.ephemeral is True

    sessions.set_ephemeral(connection, created.id, False)
    shown = sessions.get_owned_session(connection, created.id)
    assert shown is not None
    assert shown.ephemeral is False

    with pytest.raises(StoreError):
        sessions.set_ephemeral(connection, "01NOSUCHROW00000000000000", True)


def test_owned_session_counts_counts_alive_owned_rows_and_the_handle_less_ones(
    connection: sqlite3.Connection,
) -> None:
    """The population §11's total cap is checked against — and the reason it is
    checked against **panes** instead (T11, T12).

    The size comes from `MAX_TOTAL_OWNED_SESSIONS` rather than from a number
    written here, so a change to §11's cap moves the fixture with it.
    """
    handle_less = 3
    for index in range(MAX_TOTAL_OWNED_SESSIONS):
        create(
            connection,
            f"01OWNED{index:018d}",
            engine_session_id=f"eng-owned-{index}",
            handle=None if index < handle_less else HANDLE,
        )

    # An attached row is not an owned session; a stopped one holds no slot.
    connection.execute(
        "INSERT INTO session (id, engine_session_id, workspace_id, cwd, started_at,"
        " origin, ownership, engine, state)"
        " VALUES ('01ATTACHED000000000000000', 'eng-attached', 'ws-1', '/root/Shepherd',"
        " '2026-09-17T10:00:00Z', 'external', 'attached', 'claude_code', 'running')"
    )
    create(connection, "01ENDED00000000000000000", engine_session_id="eng-ended")
    end(connection, "01ENDED00000000000000000")

    assert sessions.owned_session_counts(connection) == (
        MAX_TOTAL_OWNED_SESSIONS,
        handle_less,
    )


def test_a_handle_less_owned_row_is_counted_apart_from_the_rest(
    connection: sqlite3.Connection,
) -> None:
    """The second number is the orphan cohort: a row whose pane Shepherd cannot
    reach. Folding it into the first would make the count that feeds §11 unable
    to distinguish a session it can terminate from one it cannot."""
    create(connection, "01WITH000000000000000000", engine_session_id="eng-1", handle=HANDLE)
    create(connection, "01WITHOUT0000000000000000", engine_session_id="eng-2", handle=None)

    assert sessions.owned_session_counts(connection) == (2, 1)

    sessions.set_runner_handle(connection, "01WITHOUT0000000000000000", HANDLE)
    assert sessions.owned_session_counts(connection) == (2, 0)


def test_children_of_counts_live_children_of_that_parent(
    connection: sqlite3.Connection,
) -> None:
    """§11's per-parent cap, over the population the cap actually limits.

    Seeded at `MAX_CHILDREN_PER_SESSION` so the assertion is the cap itself
    rather than a number retyped here: at this count `children_of(parent) <
    MAX_CHILDREN_PER_SESSION` is False and the next spawn is refused.
    """
    create(connection, "01PARENT0000000000000000", engine_session_id="eng-parent")
    create(connection, "01OTHER00000000000000000", engine_session_id="eng-other")

    for index in range(MAX_CHILDREN_PER_SESSION):
        create(
            connection,
            f"01CHILD{index:018d}",
            engine_session_id=f"eng-child-{index}",
            parent_session_id="01PARENT0000000000000000",
            depth=1,
        )
    create(
        connection,
        "01COUSIN0000000000000000",
        engine_session_id="eng-cousin",
        parent_session_id="01OTHER00000000000000000",
        depth=1,
    )

    assert sessions.children_of(connection, "01PARENT0000000000000000") == (
        MAX_CHILDREN_PER_SESSION
    )
    assert sessions.children_of(connection, "01OTHER00000000000000000") == 1
    assert sessions.children_of(connection, "01CHILD" + "0" * 18) == 0


def test_a_finished_child_releases_its_slot(connection: sqlite3.Connection) -> None:
    """The cap limits *concurrent* children. Counting ended rows would let a
    parent that spawned five sequential children never spawn again."""
    create(connection, "01PARENT0000000000000000", engine_session_id="eng-parent")
    for index in range(MAX_CHILDREN_PER_SESSION):
        create(
            connection,
            f"01CHILD{index:018d}",
            engine_session_id=f"eng-child-{index}",
            parent_session_id="01PARENT0000000000000000",
            depth=1,
        )
    assert sessions.children_of(connection, "01PARENT0000000000000000") == (
        MAX_CHILDREN_PER_SESSION
    )

    end(connection, f"01CHILD{0:018d}")

    assert sessions.children_of(connection, "01PARENT0000000000000000") == (
        MAX_CHILDREN_PER_SESSION - 1
    )


def test_depth_and_parent_are_stored_as_given(connection: sqlite3.Connection) -> None:
    """§11's depth cap is checked by the caller against the value on the row, so
    the row has to carry it."""
    create(connection, "01PARENT0000000000000000", engine_session_id="eng-parent")
    child = create(
        connection,
        "01CHILD00000000000000000",
        engine_session_id="eng-child",
        parent_session_id="01PARENT0000000000000000",
        depth=2,
    )

    assert child.depth == 2
    assert child.parent_session_id == "01PARENT0000000000000000"


# ----- what the row hands back (D33 rule 2) ---------------------------------


def test_the_four_owned_columns_reach_every_projection(db_path: Path) -> None:
    """`runner_handle`, `title_synced_at`, `parent_session_id` and `depth` are
    M1 columns nothing ever read back. A verb that writes a column no
    projection returns is a write a caller cannot check, so both shapes the
    store hands out — `Session` and the fleet's `FleetRow` — carry them.
    """
    seed = connect(db_path)
    try:
        create(seed, "01PARENT0000000000000000", engine_session_id="eng-parent")
        create(
            seed,
            "01CHILD00000000000000000",
            engine_session_id="eng-child",
            parent_session_id="01PARENT0000000000000000",
            depth=1,
            title="my rename",
            title_source="user",
        )
        sessions.set_title_synced_at(seed, "01CHILD00000000000000000", "2026-09-17T10:30:00Z")
    finally:
        seed.close()

    opened = open_store(db_path)
    try:
        session = opened.get_session("01CHILD00000000000000000")
        rows = {row.session_id: row for row in opened.fleet()}
    finally:
        opened.close()

    assert session is not None
    assert session.runner_handle == HANDLE
    assert session.title_synced_at == "2026-09-17T10:30:00Z"
    assert session.parent_session_id == "01PARENT0000000000000000"
    assert session.depth == 1

    child = rows["01CHILD00000000000000000"]
    assert child.runner_handle == HANDLE
    assert child.title_synced_at == "2026-09-17T10:30:00Z"
    assert child.parent_session_id == "01PARENT0000000000000000"
    assert child.depth == 1
    assert rows["01PARENT0000000000000000"].parent_session_id is None


# ----- M4/T8: the row still round-trips -------------------------------------


def test_the_session_row_still_round_trips(db_path: Path, connection: sqlite3.Connection) -> None:
    """Every field of `Session`, **enumerated at test time**, is a column the
    `SELECT` actually asks for — and `retry_of` arrives with a value.

    This is the exact defect this shape has had before: a field added to the
    dataclass and not to `SESSION_COLUMNS` constructs fine (every M2/M3 field
    carries a default) and then reads back as its default forever. The
    enumeration is over `dataclasses.fields`, so the next field to be added is
    covered by this test on the day it is added rather than on the day someone
    remembers to extend a list.
    """
    declared = {field.name for field in dataclasses.fields(Session)}
    selected = {column.strip() for column in models.SESSION_COLUMNS.split(",")}

    assert declared == selected, (
        "`Session` and `SESSION_COLUMNS` disagree; a field on one side and not the"
        " other is a column that is written and never read, or read and never named"
    )

    create(connection, "01ROOT000000000000000000", engine_session_id="eng-root")
    create(connection, "01RETRY00000000000000000", engine_session_id="eng-retry")
    connection.execute(
        "UPDATE session SET retry_of = '01ROOT000000000000000000' WHERE id = ?",
        ("01RETRY00000000000000000",),
    )

    root = sessions.get_owned_session(connection, "01ROOT000000000000000000")
    retry = sessions.get_owned_session(connection, "01RETRY00000000000000000")

    assert root is not None and retry is not None
    assert retry.retry_of == "01ROOT000000000000000000", (
        "arrival: the value is on the row before its absence means anything"
    )
    assert root.retry_of is None
