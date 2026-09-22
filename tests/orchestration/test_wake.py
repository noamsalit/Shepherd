"""T9 — D31's wake set at the `orchestration/wake.py` seam.

The seam is integration: a real SQLite file in `tmp_path` behind the public
`Store` verbs, and the projection under test on top of it. Nothing here is
handed a cursor, and **every fixture row is planted through a verb** — there is
no raw SQL in this module. `retry_of` has no writer in this tree (T8) and this
task needs no lineage, so the one fixture T8 had to plant by hand is not needed
here.

Three things this file refuses to do, each because the repo has been bitten by
it:

* **no absence without an arrival.** Every "is not in the wake set" assertion is
  preceded by an assertion that the row *landed* and that the wake set is
  non-empty. An exclusion asserted over an empty set is satisfied by any
  implementation, including one that returns nothing at all.
* **no literal count.** Populations are enumerated at test time and compared as
  sets; where a count is unavoidable it is `len()` of the enumeration.
* **no recomputed expectation.** The wake set is named by id, and the projected
  `why` and action are compared against the sentences the fixture wrote, not
  against whatever the projection produced.

The fixture is inert: it writes rows into a `tmp_path` database and executes no
code of its own (CLAUDE.md, "Mutations").
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.states import Origin
from shepherd.core.stops import (
    ActionSource,
    Bucket,
    DecidedBy,
    NextAction,
    NextActionKind,
    StopReason,
    Verdict,
)
from shepherd.orchestration.wake import (
    MASTER_LAST_TURN_KEY,
    WakeSummary,
    drain,
    peek,
    render_wake_text,
)
from shepherd.store.db import Store, open_store

#: Stamps in `core.clock`'s one spelling. `NEWEST` belongs to the `needs_you`
#: row on purpose: if the exclusion were ever implemented as "the newest row
#: wins" or as a recency window, this fixture is the one that catches it.
STOPPED = "2026-09-17T10:00:00.000Z"
NEWEST = "2026-09-17T10:30:00.000Z"

#: The clock's readings, in call order. They are far apart so that *which*
#: reading is stamped is observable: an implementation that reads the clock
#: after the rows stamps a later instant, and a stop that landed during the read
#: is then lost for good (`test_a_stop_that_lands_during_a_drain_is_not_lost`).
FIRST_TURN = "2026-09-17T10:15:00.000Z"
SECOND_TURN = "2026-09-17T11:00:00.000Z"

#: A stop that lands *while* the first drain is reading, and the instant the
#: wall clock reaches once it has landed. A drain that reads its clock after the
#: rows stamps `AFTER_THE_LATE_STOP` and loses that stop.
DURING_THE_DRAIN = "2026-09-17T10:20:00.000Z"
AFTER_THE_LATE_STOP = "2026-09-17T10:25:00.000Z"


def sid(name: str) -> str:
    return (name + "0" * 26)[:26]


@dataclass(frozen=True)
class Row:
    """One fixture row, and the single reason it is in the wake set or out."""

    session_id: str
    outcome: str
    ended_at: str
    title: str
    why: str
    actions: tuple[NextAction, ...]
    kind: str


def action(text: str, kind: NextActionKind) -> NextAction:
    return NextAction(text=text, kind=kind, target=None, source=ActionSource.HEURISTIC)


#: §12's own two rows, plus the two kinds that must not wake anything. Every
#: `why` is a sentence **only this fixture** could have produced — a projection
#: that re-classified a row instead of reading it cannot reproduce them.
FLEET: tuple[Row, ...] = (
    Row(
        session_id=sid("01WAKEUNFINISHED"),
        outcome=Bucket.UNFINISHED.value,
        ended_at=STOPPED,
        title="PROJ-81711 resolver",
        why="promised specs, never ran them",
        actions=(action("re-run", NextActionKind.RETRY), action("logs", NextActionKind.INSPECT)),
        kind="wakes",
    ),
    Row(
        session_id=sid("01WAKEERROR"),
        outcome=Bucket.ERROR.value,
        ended_at=STOPPED,
        title="frontend lint",
        why="exit 1 during Edit",
        actions=(action("logs", NextActionKind.INSPECT),),
        kind="wakes",
    ),
    Row(
        session_id=sid("01NEEDSYOU"),
        outcome=Bucket.NEEDS_YOU.value,
        ended_at=NEWEST,
        title="payments-api",
        why="wants permission to push",
        actions=(action("answer it", NextActionKind.ESCALATE),),
        kind="the human's rail",
    ),
    Row(
        session_id=sid("01FINISHED"),
        outcome=Bucket.FINISHED.value,
        ended_at=STOPPED,
        title="billing-api",
        why="ran the specs and they passed",
        actions=(),
        kind="nothing wakes",
    ),
)

#: D31's two rows, **named** rather than filtered out of `FLEET` with the
#: query's own predicate: a set recomputed by the rule under test agrees with
#: any rule that agrees with itself.
WAKES = frozenset({sid("01WAKEUNFINISHED"), sid("01WAKEERROR")})

BY_ID = {row.session_id: row for row in FLEET}


class Clock:
    """The injected clock, reading a scripted sequence. It refuses to run off
    the end rather than repeating its last reading: a test that called `now()`
    once more than it meant to would otherwise still pass."""

    def __init__(self, *moments: str) -> None:
        self._moments = list(moments)
        self.readings: list[str] = []

    def __call__(self) -> str:
        assert self._moments, "the clock was read more times than the test scripted"
        moment = self._moments.pop(0)
        self.readings.append(moment)
        return moment


class WallClock:
    """A clock that **advances with events rather than with calls**, because a
    call-counting double cannot tell the two orderings apart.

    `Clock` hands out its next scripted reading whenever it is called, so
    `now()` before the read and `now()` after it return the same string and a
    test built on it is green either way — this is exactly the survivor
    MUT-3 exposed. Here the fixture moves `current` forward when the late stop
    lands, so the reading a drain gets *is* a function of when it read.
    """

    def __init__(self, current: str) -> None:
        self.current = current
        self.readings: list[str] = []

    def __call__(self) -> str:
        self.readings.append(self.current)
        return self.current


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    opened.create_project(name="shepherd", description=None)
    try:
        yield opened
    finally:
        opened.close()


def spawn(store: Store, session_id: str, title: str) -> None:
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=f"eng-{session_id}",
        workspace_id=next(w for w in store.list_workspaces() if w.name == "shepherd").id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-17T09:00:00.000Z",
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=title,
        title_source="brief",
        handle=None,
        model="opus",
        effort="high",
    )


def stop(store: Store, row: Row) -> None:
    store.apply_stop_verdict(
        row.session_id,
        Verdict(
            stop_reason=StopReason.INCOMPLETE,
            bucket=Bucket(row.outcome),
            why=row.why,
            confidence=0.9,
            decided_by=DecidedBy.HEURISTIC,
            next_actions=row.actions,
            waiting_on=None,
            missing=(),
        ),
        row.ended_at,
        None,
    )


def plant(store: Store, rows: tuple[Row, ...] = FLEET) -> None:
    for row in rows:
        spawn(store, row.session_id, row.title)
        stop(store, row)


def landed(store: Store, rows: tuple[Row, ...] = FLEET) -> set[str]:
    """Arrival. Every row asserted absent from a wake set is asserted present
    in the database first — otherwise "excluded" and "never written" are the
    same observation."""
    return {row.session_id for row in rows if store.get_session(row.session_id) is not None}


def ids(summary: WakeSummary) -> set[str]:
    return {item.session_id for item in summary.items}


# ----- the drain -------------------------------------------------------------


def test_draining_twice_yields_nothing_the_second_time(store: Store) -> None:
    """Arrival first: the first drain is asserted to be exactly D31's rows
    before the second is asserted empty.

    Goes red if the stamp is never written (the second drain repeats the set),
    and red if the drain filters on something other than the stamp.
    """
    plant(store)
    assert landed(store) == {row.session_id for row in FLEET}
    assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

    clock = Clock(FIRST_TURN, SECOND_TURN)
    first = drain(store, clock)
    assert ids(first) == WAKES
    assert first.drained_at == FIRST_TURN
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == FIRST_TURN

    second = drain(store, clock)
    assert second.items == ()
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == SECOND_TURN


def test_an_empty_drain_still_moves_the_stamp(store: Store) -> None:
    """E-M4-18. Two halves, because the stamp can be made conditional in two
    places: an empty *first* drain still stamps, and an empty *second* drain
    moves the stamp on again.

    Goes red if the stamp is written only when the set is non-empty, which
    would let a stop that happened during the gap be attributed to an earlier
    turn — or re-drained forever.
    """
    quiet = tuple(row for row in FLEET if row.session_id not in WAKES)
    plant(store, quiet)
    assert landed(store, quiet) == {row.session_id for row in quiet}, "arrival: the fleet landed"

    clock = Clock(FIRST_TURN, SECOND_TURN)
    first = drain(store, clock)
    assert first.items == ()
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == FIRST_TURN

    second = drain(store, clock)
    assert second.items == ()
    assert store.get_app_state(MASTER_LAST_TURN_KEY) == SECOND_TURN


def test_a_stop_that_lands_during_a_drain_is_not_lost(store: Store) -> None:
    """The window the ordering exists to close.

    A session stops **while the drain is reading**. The wall clock moves with
    that event, so the instant a drain stamps depends on whether it read the
    clock before the rows or after them:

    * read before → the stamp is `FIRST_TURN`, earlier than the late stop, and
      the late row arrives on the next drain;
    * read after  → the stamp is `AFTER_THE_LATE_STOP`, later than the late
      stop, and that row never wakes anything again.

    The late arrival is planted through the store's own verbs from inside a
    wrapper around `wake_candidates` — the wrapper is the fixture's, the verb it
    calls is the real one.
    """
    plant(store)
    late = Row(
        session_id=sid("01LATESTOP"),
        outcome=Bucket.ERROR.value,
        ended_at=DURING_THE_DRAIN,
        title="late stop",
        why="stopped while the master was reading",
        actions=(action("re-run", NextActionKind.RETRY),),
        kind="wakes",
    )
    clock = WallClock(FIRST_TURN)
    real = store.wake_candidates
    planted: list[str] = []

    def wake_candidates_then_a_late_stop(since: str | None) -> tuple[object, ...]:
        found = real(since)
        if not planted:
            planted.append(late.session_id)
            spawn(store, late.session_id, late.title)
            stop(store, late)
            clock.current = AFTER_THE_LATE_STOP
        return found

    store.wake_candidates = wake_candidates_then_a_late_stop  # type: ignore[method-assign]
    first = drain(store, clock)
    store.wake_candidates = real  # type: ignore[method-assign]

    assert planted == [late.session_id], "arrival: the late stop was planted during the read"
    assert store.get_session(late.session_id) is not None
    assert ids(first) == WAKES, "the late row was not in the set the first drain read"
    assert first.drained_at == FIRST_TURN, (
        "the drain stamped an instant later than the stop that landed while it"
        " was reading; that stop is now unreachable forever"
    )

    second = drain(store, clock)
    assert ids(second) == {late.session_id}


def test_peek_reports_the_wake_set_and_moves_nothing(store: Store) -> None:
    """`peek` is the same projection without the stamp — level 2 and level 3
    differ in *when* `drain` is called, never in what is returned."""
    plant(store)
    assert {item.session_id for item in peek(store)} == WAKES
    assert store.get_app_state(MASTER_LAST_TURN_KEY) is None

    clock = Clock(FIRST_TURN)
    drain(store, clock)
    assert peek(store) == ()


# ----- the exclusion ---------------------------------------------------------


def test_needs_you_never_wakes_the_master(store: Store) -> None:
    """D31's rail. The `needs_you` row is present, is the **newest** stop in the
    fleet, and is still absent from the wake set — while the set itself is
    non-empty, so the exclusion is not an empty-set tautology.

    Goes red if the outcome filter is widened.
    """
    plant(store)
    needs_you = BY_ID[sid("01NEEDSYOU")]
    row = store.get_session(needs_you.session_id)
    assert row is not None, "arrival: the needs_you row landed"
    assert row.outcome == Bucket.NEEDS_YOU.value
    waking_stops = {found.id: found.ended_at for found in store.wake_candidates(None)}
    assert set(waking_stops) == WAKES, "arrival: the rows recency is compared against"
    assert all(row.ended_at is not None and row.ended_at > stop_at for stop_at in waking_stops.values()), (
        "the needs_you row is no longer strictly the newest stop, and this"
        " fixture's whole point is that recency cannot rescue it — compared"
        " against the stamps the database holds, not against the constants"
        " above, so the comparison cannot move with the fixture"
    )

    clock = Clock(FIRST_TURN)
    summary = drain(store, clock)
    assert ids(summary) == WAKES
    assert needs_you.session_id not in ids(summary)


def test_the_wake_set_is_exactly_the_rows_d31_names(store: Store) -> None:
    """Every excluded kind in the fixture is asserted to be excluded *by name*,
    against the enumeration of the fleet rather than a count."""
    plant(store)
    assert landed(store) == {row.session_id for row in FLEET}

    clock = Clock(FIRST_TURN)
    summary = drain(store, clock)
    assert ids(summary) == WAKES
    assert {row.session_id for row in FLEET} - ids(summary) == {
        row.session_id for row in FLEET if row.kind != "wakes"
    }


# ----- the projection --------------------------------------------------------


def test_the_summary_carries_the_rows_own_classification(store: Store) -> None:
    """§12: the master re-reads a classification it can already see.

    The projected `why`, title, bucket and first action are compared against the
    **stored row** and against the sentences the fixture wrote. Goes red if the
    projection calls a classifier: no classifier in this tree produces
    "promised specs, never ran them", and none would keep `[re-run]` first.
    """
    plant(store)
    clock = Clock(FIRST_TURN)
    summary = drain(store, clock)
    assert ids(summary) == WAKES

    # Fixture coverage, asserted rather than assumed: unless some waking row
    # carries **more than one** action, "the first" and "the last" are the same
    # value and this test cannot tell a projection that takes either. MUT-11.
    assert any(len(BY_ID[session_id].actions) > 1 for session_id in WAKES), (
        "no waking row carries two actions any more; first and last have become"
        " indistinguishable and this assertion is now vacuous"
    )
    stored = {session_id: store.get_session(session_id) for session_id in WAKES}
    assert all(row is not None for row in stored.values()), "arrival: the waking rows landed"
    assert any(len(row.next_actions) > 1 for row in stored.values() if row is not None), (
        "the stored rows carry at most one action each, so the round trip"
        " cannot show which end of the list the projection read"
    )

    projected = {item.session_id: item for item in summary.items}
    for session_id in WAKES:
        fixture = BY_ID[session_id]
        row = store.get_session(session_id)
        assert row is not None
        item = projected[session_id]
        assert item.why == fixture.why == row.why
        assert item.title == fixture.title == row.title
        assert item.bucket is Bucket(fixture.outcome)
        assert item.first_action == (fixture.actions[0] if fixture.actions else None)
        assert item.first_action == (row.next_actions[0] if row.next_actions else None)


def test_the_rendered_summary_is_section_twelves_shape(store: Store) -> None:
    """One line per item, each carrying §4's glyph for the row's own bucket, the
    title, the `why` and the first action as a button. Compared against the
    fixture's sentences, and the line population is enumerated, never counted."""
    plant(store)
    clock = Clock(FIRST_TURN)
    text = render_wake_text(drain(store, clock))

    assert text.startswith("while you were away —")
    for session_id in WAKES:
        fixture = BY_ID[session_id]
        glyph = {
            Bucket.UNFINISHED: "◑",
            Bucket.ERROR: "✕",
        }[Bucket(fixture.outcome)]
        line = next(
            (found for found in text.splitlines() if fixture.title in found),
            None,
        )
        assert line is not None, f"{fixture.title} is missing from the rendered summary"
        assert glyph in line
        assert fixture.why in line
        assert f"[{fixture.actions[0].text}]" in line

    for session_id, fixture in BY_ID.items():
        if session_id in WAKES:
            continue
        assert fixture.title not in text


def test_an_empty_summary_renders_nothing_to_prepend(store: Store) -> None:
    """A turn with nothing behind it opens with the human's words, not with an
    empty header (§12: the summary opens the first turn where **anything**
    stopped)."""
    clock = Clock(FIRST_TURN)
    summary = drain(store, clock)
    assert summary.items == ()
    assert render_wake_text(summary) == ""


def test_the_key_is_the_one_the_spec_names() -> None:
    """§7 `app_state` and D31 name this key; `store/` has no constant for it, so
    the spelling lives here and is asserted rather than assumed."""
    assert MASTER_LAST_TURN_KEY == "master_last_turn_at"


def test_wake_names_no_engine_or_vendor_word() -> None:
    """K13 at this file's own surface — `orchestration/` is L3 and speaks the
    domain's words. The boundary suite owns the general rule; this is the
    local one, over the shipped text."""
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "shepherd"
        / "orchestration"
        / "wake.py"
    ).read_text(encoding="utf-8")
    for word in ("claude", "anthropic", "tmux", "ClaudeAgentOptions", "mcp__", "can_use_tool"):
        assert word.lower() not in source.lower(), f"{word} is vendor vocabulary (K13)"
