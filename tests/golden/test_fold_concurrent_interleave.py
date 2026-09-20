"""G3 — the synthetic interleave, built from real events (T12).

The corpus is 50 near-sequential sessions, so nothing in it exercises the fold
under contention. Rather than invent contention, this lane **re-orders real
events**: all 429 envelopes merge-sorted on `_epoch` across session ids. Three
sessions are genuinely re-entered after another session has produced events, so
the interleave is a different order — and per-session final state must not
depend on the order other sessions' events arrived in.

Genuine concurrency (threads, sockets) is T18's live lane, not this one.
"""

from __future__ import annotations

import pytest
from golden.corpus import load_corpus, replay, sequential_order, session_table

from shepherd.store.db import Store, open_store

CORPUS = load_corpus()
SEQUENTIAL = sequential_order(CORPUS)


def test_the_interleave_is_a_different_order_of_the_same_events() -> None:
    assert len(CORPUS) == len(SEQUENTIAL)
    assert [event.line for event in CORPUS] != [event.line for event in SEQUENTIAL]
    assert sorted(id(event) for event in CORPUS) == sorted(id(event) for event in SEQUENTIAL)

    # the property that makes this worth testing: sessions really do re-enter
    switches = 0
    seen: set[str] = set()
    last = ""
    for event in CORPUS:
        if event.session_id != last and event.session_id in seen:
            switches += 1
        seen.add(event.session_id)
        last = event.session_id
    assert switches == 3


def test_fold_concurrent_interleave(store: Store, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Per-session final state is identical however the sessions interleave."""
    sequential_stats = replay(SEQUENTIAL, store)
    sequential_table = session_table(store, sequential_stats)

    other = open_store(tmp_path_factory.mktemp("interleaved") / "shepherd.sqlite3")
    try:
        interleaved_stats = replay(CORPUS, other)
        interleaved_table = session_table(other, interleaved_stats)
    finally:
        other.close()

    assert set(interleaved_table) == set(sequential_table)
    assert interleaved_table == sequential_table
