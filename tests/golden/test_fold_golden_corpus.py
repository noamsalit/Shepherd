"""§14 lane 1 — 429 real events through `parse_hook_payload` → `fold` → `Store`.

No mocking of Claude Code: the fixtures ARE Claude Code. Every assertion here is
against a capture, and when the fold and a capture disagree the fold is wrong.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from golden.corpus import (  # the golden lane's loader, replay harness and table
    CorpusEvent,
    EXPECTED_EVENT_COUNT,
    EXPECTED_SCENARIOS_WITH_EVENTS,
    EXPECTED_SESSION_COUNT,
    corpus_digest,
    load_corpus,
    load_expected,
    parse,
    replay,
    scenario_files,
    sequential_order,
    session_table,
    write_expected,
)

from shepherd.core.signals import MalformedPayload, Signal, SignalKind
from shepherd.store.db import Store

CORPUS = load_corpus()
SEQUENTIAL = sequential_order(CORPUS)


# ----- the corpus itself ---------------------------------------------------


def test_corpus_loads_429_events_0_malformed() -> None:
    assert len(CORPUS) == EXPECTED_EVENT_COUNT
    assert len(scenario_files()) == EXPECTED_SCENARIOS_WITH_EVENTS
    assert all(event.payload for event in CORPUS)
    assert all(event.epoch > 0 for event in CORPUS)


def test_corpus_has_50_sessions() -> None:
    assert len({event.session_id for event in CORPUS}) == EXPECTED_SESSION_COUNT


def test_the_harness_label_is_not_a_hook_event_name() -> None:
    """`UserPromptSubmit__from_settings_json` (6) is the probe's own label."""
    labelled = [event for event in CORPUS if "__" in event.label]
    assert len(labelled) == 6
    assert {event.event for event in labelled} == {"UserPromptSubmit"}
    assert len({event.event for event in CORPUS}) == 31


def test_every_payload_parses() -> None:
    """P2: 429 captures, zero malformed, zero raises."""
    malformed = [event for event in CORPUS if isinstance(parse(event), MalformedPayload)]
    assert malformed == []
    assert all(isinstance(parse(event), Signal) for event in CORPUS)


def _kind(event: CorpusEvent) -> SignalKind:
    signal = parse(event)
    assert isinstance(signal, Signal)
    return signal.kind


def test_no_captured_event_is_unknown_to_the_normaliser() -> None:
    assert {event.event for event in CORPUS if _kind(event) is SignalKind.UNKNOWN} == set()


# ----- the replay ----------------------------------------------------------


def test_replay_produces_50_session_rows(store: Store) -> None:
    """P8: 429 events, 50 rows — and 53 of the 54 scenarios are `-p` runs, so
    this is the proof that the hook path registers headless sessions (D47)."""
    stats = replay(SEQUENTIAL, store)
    assert stats.events == EXPECTED_EVENT_COUNT
    assert stats.malformed == 0
    assert stats.registrations == EXPECTED_SESSION_COUNT
    assert len(store.list_sessions()) == EXPECTED_SESSION_COUNT


def test_registers_on_first_event_of_any_kind(store: Store) -> None:
    """D47: a session already running when hooks were installed never fires a
    start event again — so the first event of ANY kind has to register it."""
    first_by_session: dict[str, str] = {}
    for event in SEQUENTIAL:
        first_by_session.setdefault(event.session_id, event.event)
    assert set(first_by_session.values()) - {"SessionStart"}, "no non-start opener in the corpus"

    replay(SEQUENTIAL, store)
    for engine_id in first_by_session:
        assert store.get_session_by_engine_id(engine_id) is not None, engine_id


def test_replay_matches_expected_state(store: Store, request: pytest.FixtureRequest) -> None:
    stats = replay(SEQUENTIAL, store)
    table = session_table(store, stats)
    if bool(request.config.getoption("--update-golden")):
        write_expected(table)
        pytest.skip("golden table rewritten")
    assert table == load_expected()


def test_replay_is_idempotent(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Determinism is the point: replay twice, get the same rows."""
    from shepherd.store.db import open_store

    tables = []
    for run in range(2):
        opened = open_store(tmp_path_factory.mktemp(f"run{run}") / "shepherd.sqlite3")
        try:
            stats = replay(SEQUENTIAL, opened)
            tables.append(session_table(opened, stats))
        finally:
            opened.close()
    assert tables[0] == tables[1]
    assert json.dumps(tables[0], sort_keys=True) == json.dumps(tables[1], sort_keys=True)


# ----- the probed facts, over the whole corpus -----------------------------


def test_subagent_count_never_negative_over_corpus(store: Store) -> None:
    """C10/P1: the negative case is in the real data — 2 starts, 4 stops."""
    starts = sum(1 for event in CORPUS if event.event == "SubagentStart")
    stops = sum(1 for event in CORPUS if event.event == "SubagentStop")
    assert (starts, stops) == (2, 4)

    stats = replay(SEQUENTIAL, store)
    assert stats.min_active_subagents == 0
    assert all(session.active_subagents >= 0 for session in store.list_sessions())
    assert stats.anomalies.get("subagent_underflow", 0) == 2


def test_tasks_done_never_exceeds_total_over_corpus(store: Store) -> None:
    replay(SEQUENTIAL, store)
    for session in store.list_sessions():
        assert 0 <= session.tasks_done <= session.tasks_total


def test_repos_touched_never_from_filechanged_alone(
    store: Store, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """C9: the watch event never reports a file the agent edited.

    Two halves, both read off the corpus: the watch-path captures and the
    agent's own edit paths are disjoint, and dropping the watch signals changes
    exactly the one session whose only path evidence was a declared watch path.
    """
    from shepherd.store.db import open_store

    watched = {
        str(event.payload.get("file_path"))
        for event in CORPUS
        if event.event == "FileChanged"
    }
    edited = {
        str(tool_input.get("file_path"))
        for event in CORPUS
        if event.event == "PostToolUse"
        for tool_input in [event.payload.get("tool_input")]
        if isinstance(tool_input, dict) and tool_input.get("file_path")
    }
    assert watched
    assert watched & edited == set()

    full = replay(SEQUENTIAL, store)
    full_table = session_table(store, full)
    other = open_store(tmp_path_factory.mktemp("nowatch") / "shepherd.sqlite3")
    try:
        dropped = replay(SEQUENTIAL, other, drop=frozenset({SignalKind.FILES_CHANGED.value}))
        dropped_table = session_table(other, dropped)
    finally:
        other.close()

    differing = {
        engine_id
        for engine_id, row in full_table.items()
        if row["repos_touched"] != dropped_table[engine_id]["repos_touched"]
    }
    watch_sessions = {event.session_id for event in CORPUS if event.event == "FileChanged"}
    assert differing <= watch_sessions


def test_brief_never_starts_with_task_notification(store: Store) -> None:
    """C11: the injected XML is in the corpus (S18) and must not become a brief."""
    injected = [
        event
        for event in CORPUS
        if event.event == "UserPromptSubmit"
        and str(event.payload.get("prompt", "")).startswith("<task-notification>")
    ]
    assert len(injected) == 1

    stats = replay(SEQUENTIAL, store)
    for session in store.list_sessions():
        assert session.brief is None or not session.brief.startswith("<task-notification>")
    polluted = injected[0].session_id
    assert stats.briefs.get(polluted, "") != str(injected[0].payload.get("prompt"))


def test_received_at_comes_from_epoch_not_the_clock(store: Store) -> None:
    """C8: no payload carries a timestamp, so the receipt time must be `_epoch`."""
    stats = replay(SEQUENTIAL, store)
    latest: dict[str, float] = {}
    for event in CORPUS:
        latest[event.session_id] = max(latest.get(event.session_id, 0.0), event.epoch)

    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for engine_id, session_id in stats.sessions.items():
        session = store.get_session(session_id)
        assert session is not None
        expected = datetime.fromtimestamp(latest[engine_id], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert session.last_event_at == expected
        assert session.last_event_at != now


def test_the_corpus_is_read_only(corpus_is_read_only: str) -> None:
    """The captures are evidence (T12). The session-scoped guard in `conftest`
    hashes them before and after the whole lane; this asserts it is not vacuous."""
    assert corpus_digest() == corpus_is_read_only
    assert len(corpus_is_read_only) == 64


# ----- T10's regression gate ------------------------------------------------


def test_golden_table_is_unchanged_for_every_existing_kind(store: Store) -> None:
    """The Stop/SessionEnd split (r3 BLOCKING 1) is one cell wide.

    Every `Stop` in the 429-event corpus changes `SignalKind` — and **no**
    session column may move, because both rules set `state` and `ended_at`
    identically. The expected table on disk is the M1 one, byte for byte: the
    two columns T10 adds are not in it, so a diff here means the split was done
    wrong rather than that the table needs regenerating.
    """
    stops = [event for event in CORPUS if event.event == "Stop"]
    assert stops, "no Stop in the corpus"
    assert {_kind(event) for event in stops} == {SignalKind.TURN_STOPPED}
    assert {_kind(event) for event in CORPUS if event.event == "SessionEnd"} <= {
        SignalKind.SESSION_STOPPED
    }

    stats = replay(SEQUENTIAL, store)
    assert session_table(store, stats) == load_expected()


def test_the_two_new_columns_survive_the_replay(store: Store) -> None:
    """D24 discards the events; the marks have to outlive them or the
    `context_exhausted` bound can never be evaluated at a stop."""
    compacts = [event for event in CORPUS if event.event in ("PreCompact", "PostCompact")]
    assert compacts, "no compaction in the corpus"
    stats = replay(SEQUENTIAL, store)
    marked = [
        store.get_session(session_id) for session_id in sorted(stats.sessions.values())
    ]
    # Every compaction in the corpus is a `manual` one (S05), so every mark is
    # cleared rather than standing — and `""` is `CLEARED_STAMP`, not a stamp.
    assert {session.auto_compact_at for session in marked if session is not None} <= {
        None,
        "",
    }
    # The corpus holds zero quota notices, so no session may carry a *stamp* —
    # but since BLOCKER T10-2 was applied, a turn ending clears that mark too,
    # so a session whose turns ended carries `CLEARED_STAMP` exactly as the
    # compaction mark above does. `""` is still "no notice ever arrived".
    assert {session.quota_notice_at for session in marked if session is not None} <= {
        None,
        "",
    }
