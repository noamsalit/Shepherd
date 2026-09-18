"""The fold's input and output shapes, defined at L1 (F9).

`signals/fold.py` re-exports these; it does not define them. That is what lets
`store/` (T6) and the registry scan (T7b) take the types without depending on
the fold.
"""

from __future__ import annotations

from dataclasses import dataclass

from shepherd.core.anomalies import Anomaly
from shepherd.core.states import SessionState, TitleSource
from shepherd.core.stream import StreamEvent

#: How a delta says "this column is now empty". `None` means *untouched*
#: (`store/rows.py`'s writer skips it), so a clear needs a value, and an empty
#: reason is the honest one: there is nothing left to act on.
#:
#: **One constant, imported by both lanes.** The hook lane and the registry lane
#: each arrived at `""` independently (BLOCKER T7b-4, T11-6); agreeing by
#: coincidence is not the same as agreeing by construction, and a reader that
#: tests `reason is None` rather than `not reason` renders a stale-looking
#: empty reason either way.
CLEARED = ""

#: The same value, under the name the *timestamp* columns use. `auto_compact_at`
#: and `quota_notice_at` are stamps, and `""` is not a stamp: a reader doing
#: `if row.auto_compact_at:` is correct either way, but a reader *parsing* it is
#: not. One alias, declared here beside `CLEARED`, so both lanes agree by
#: construction rather than by coincidence — which is the lesson BLOCKER T11-6
#: recorded when two lanes reached `""` independently.
CLEARED_STAMP = CLEARED


@dataclass(frozen=True)
class FoldDelta:
    """Every field optional; `None` means *untouched*, never *cleared*."""

    last_event_at: str | None = None
    state: SessionState | None = None
    needs_you_reason: str | None = None
    brief: str | None = None
    cwd: str | None = None
    repo_id: str | None = None
    model: str | None = None
    tasks_total: int | None = None
    tasks_done: int | None = None
    active_subagents: int | None = None
    repos_touched: tuple[str, ...] | None = None
    title: str | None = None
    title_source: TitleSource | None = None
    """§7.1's pair, written together or not at all. D29's ratchet is applied by
    whoever *proposes* the title (it needs the prior's rank); the delta carries
    only the decision (BLOCKER T7b-3)."""
    ended_at: str | None = None
    auto_compact_at: str | None = None
    """When auto-compaction started and had not finished. D24 discards the
    events that prove it, so the fact has to survive as a column or the
    `context_exhausted` bound can never be evaluated at the stop (T10)."""
    quota_notice_at: str | None = None
    """When a quota notice last arrived — the other fact D24 would discard."""
    pid: int | None = None
    proc_start: str | None = None
    observed_at: str | None = None
    """Recency key for RD8's per-field rule."""
    live_subagent_ids: frozenset[str] | None = None
    created_task_ids: frozenset[str] | None = None
    completed_task_ids: frozenset[str] | None = None
    """The fold's identity sets, carried so they survive a `controld` restart
    (BLOCKER-T6-1/T11-4). They are **whole-value** fields: the delta says what
    the set now is, never what to add, so an empty set is a real clear and
    `None` still means *untouched*. D37 only holds if the sets go through the
    same one writer as the counts they are computed from."""


@dataclass(frozen=True)
class SessionSnapshot:
    """The fold's prior-state input. Read-only: the fold never mutates it."""

    session_id: str
    engine_session_id: str | None
    state: SessionState
    last_event_at: str | None
    observed_at: str | None
    needs_you_reason: str | None
    brief: str | None
    cwd: str | None
    repo_id: str | None
    model: str | None
    tasks_total: int
    tasks_done: int
    active_subagents: int
    repos_touched: tuple[str, ...]
    live_subagent_ids: frozenset[str]
    created_task_ids: frozenset[str]
    completed_task_ids: frozenset[str]
    title: str | None
    title_source: TitleSource
    pid: int | None
    proc_start: str | None
    ended_at: str | None
    auto_compact_at: str | None
    quota_notice_at: str | None
    """The two marks, read back by the stop lane. Empty (`CLEARED_STAMP`) and
    `None` both mean "no mark", which is why every reader tests them for truth
    rather than for `is None`."""


@dataclass(frozen=True)
class IdentitySets:
    """The id sets a fold step leaves behind. Persisted since BLOCKER-T6-1 was
    closed; still returned so a pure in-memory replay needs no store."""

    live_subagent_ids: frozenset[str]
    created_task_ids: frozenset[str]
    completed_task_ids: frozenset[str]


EMPTY_SETS = IdentitySets(frozenset(), frozenset(), frozenset())


@dataclass(frozen=True)
class FoldResult:
    """What **either** writer lane returns: the delta to persist, the events to
    publish, the unknowns to count.

    It lives here, beside `FoldDelta`, for the reason F9 already put `FoldDelta`
    here: two lanes (`signals/fold.py` for hooks, `signals/discovery_loop.py`
    for the registry) must return the *same* type or D37's "one writer, one rule
    set" is a coincidence, and T18's single `on_result` callback can name only
    one of them (BLOCKER T7b-1).
    """

    delta: FoldDelta
    events: tuple[StreamEvent, ...]
    anomalies: tuple[Anomaly, ...]
    sets: IdentitySets = EMPTY_SETS
    """The delta already carries the sets; this is the same value at the pure
    seam, for a caller replaying in memory with no store. The registry lane
    pairs nothing and leaves it at its empty value."""
