"""The dataclasses `store/` hands back (D33 rule 2), and the vocabulary every
module in the package shares.

A caller never sees a driver row, a cursor, or a connection. These types are
the only shape that crosses the package boundary, which is what makes D2's
engine swap a rewrite of one package rather than of its callers.

`StoreError`, `SESSION_COLUMNS` and `DEFAULT_ENGINE` live here for the reason
this module has no connection dependency and everything else in `store/` imports
it. T4-2 parked them in `reads.py` to break an import cycle — `sessions.py` needs
names `db.py` also needs, and a name both sides of a delegation need cannot live
on the delegating side — and said at the time that the placement was the one
thing it was unhappy with. It was right: an exception `reads.py`, `writes.py`,
`sessions.py` and `db.py`'s own plumbing all raise does not belong to the module
named *reads*, and a column list `writes.py` selects by is not a read-only fact.
No fourth module was invented for them (T4-3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState, TitleSource
from shepherd.core.stops import NextAction

__all__ = [
    "DEFAULT_ENGINE",
    "SESSION_COLUMNS",
    "FleetRow",
    "Repo",
    "ReplayTarget",
    "Session",
    "StopCounts",
    "StoreError",
    "SubagentRollup",
    "TitleSource",
    "Workspace",
]

#: The engine M1 observes. §7 has no default for it, so the verb supplies one.
DEFAULT_ENGINE = "claude_code"

SESSION_COLUMNS = (
    "id, owner_id, engine_session_id, workspace_id, repo_id, origin, ownership, ephemeral,"
    " depth, attempt, engine, brief, cwd, started_at, title, title_source, state,"
    " last_event_at, needs_you_reason, model, tasks_done, tasks_total, active_subagents,"
    " repos_touched, pid, proc_start, ended_at, runner_handle, title_synced_at, parent_session_id,"
    # M2's stop group: written by one verb, read by every consumer (T2).
    " stop_reason, outcome, why, confidence, decided_by, next_actions, exit_code,"
    " auto_compact_at, quota_notice_at,"
    # M4's lineage link: an M1 column (001:64) nothing selected until D31's cap
    # needed it. No migration — the column has been there since the first table.
    " retry_of"
)


class StoreError(Exception):
    """A write the store refused. Driver exceptions never escape the package."""


@dataclass(frozen=True)
class Workspace:
    """§7 `workspace`. The consumer-facing word for this row is *project* (D22)."""

    id: str
    owner_id: str
    name: str
    root_path: str | None
    created_at: str
    last_activity_at: str | None


@dataclass(frozen=True)
class Repo:
    """§7 `repo`, plus D48's binding key."""

    id: str
    owner_id: str
    workspace_id: str
    name: str
    root_path: str
    git_common_dir: str | None
    vcs_remote: str | None
    active: bool
    added_at: str


@dataclass(frozen=True)
class Session:
    """§7 `session` — the M1 columns plus M2's stop group.

    Every stop field carries a default, which is not laziness: `Session` is
    constructed by `rows.session()` alone, and a defaulted field is what lets
    M2 widen the row without touching a single M1 caller.
    """

    id: str
    owner_id: str
    engine_session_id: str | None
    workspace_id: str
    repo_id: str | None
    origin: Origin
    ownership: Ownership
    ephemeral: bool
    depth: int
    attempt: int
    engine: str
    brief: str | None
    cwd: str | None
    started_at: str
    title: str | None
    title_source: TitleSource
    state: SessionState
    last_event_at: str | None
    needs_you_reason: str | None
    model: str | None
    tasks_done: int
    tasks_total: int
    active_subagents: int
    repos_touched: tuple[str, ...]
    pid: int | None
    proc_start: str | None
    ended_at: str | None

    # ----- the stop group (M2, T2) ----------------------------------------
    stop_reason: str | None = None
    outcome: str | None = None
    why: str | None = None
    confidence: float | None = None
    decided_by: str | None = None
    next_actions: tuple[NextAction, ...] = ()
    exit_code: int | None = None
    """Null for an attached session: C13 gives an exit *time* and never a code."""
    auto_compact_at: str | None = None
    """C12's mark. The events that prove `context_exhausted` are discarded
    after folding (D24), so the mark has to be a column."""
    quota_notice_at: str | None = None
    """G-M2-1's mark, for the same reason."""

    # ----- the owned-session group (M3, T4) -------------------------------
    runner_handle: RunnerHandle | None = None
    """Where the pane lives (§6). `None` on an attached row — and on an **owned**
    row it is an orphan: a pane nothing can terminate (T11, T12)."""
    title_synced_at: str | None = None
    """D29: set only when the engine accepted the title now on the row."""
    parent_session_id: str | None = None
    """§11's tree, with `depth`. Written before a fork even starts (E-M3-33)."""

    # ----- the lineage link (M4, T8) --------------------------------------
    retry_of: str | None = None
    """The session this one is a retry of — D31's lineage, walked rather than
    counted. `attempt` is a column a caller writes and can reset; the chain is
    the fact, which is why the cap reads this and not that. Present in the
    schema since `001_m1_foundation.sql:64` and simply never selected."""


@dataclass(frozen=True)
class StopCounts:
    """What the fleet page needs to show the `unknown` rate honestly (ADR-M2-5).

    `unknown` is a reason a rule *wrote*; `unclassified` is a stopped row no
    verdict ever reached (E-M2-4). They are different work items and a single
    number would hide both.
    """

    by_reason: Mapping[str, int]
    classified: int
    unclassified: int
    unknown: int
    completed_low_confidence: int
    """DP10 — the cohort D34 calls the residue: a `completed` the heuristics
    were not confident about. Revision 2 rendered it as a green chip and
    counted it nowhere."""


@dataclass(frozen=True)
class ReplayTarget:
    """One row `shepherd replay` may overwrite, as it stands *before* the run.

    **All eight stop columns**, because `apply_stop_verdict` writes all eight in
    one statement (D33) and a diff that showed one hid seven: a run reporting
    `changed 0` could still rewrite `why`, `next_actions` and `confidence`, and
    `confidence` is what feeds `completed_low_confidence` — DP10/D34's trigger
    for the LLM lane. What a caller can see is what a caller can review.
    """

    session_id: str
    engine_session_id: str | None
    stop_reason: str | None
    outcome: str | None
    why: str | None
    confidence: float | None
    decided_by: str | None
    next_actions: tuple[NextAction, ...]
    ended_at: str | None
    exit_code: int | None


@dataclass(frozen=True)
class SubagentRollup:
    """The fleet tree's third tier, as a count (§7 "subagent rows" are not stored).

    The expanded list is read from the transcript on demand (T13); this is what
    the row itself carries.
    """

    session_id: str
    active: int
    tasks_done: int
    tasks_total: int


@dataclass(frozen=True)
class FleetRow:
    """One row of §16's fleet page: the session joined to its workspace and repo."""

    session_id: str
    engine_session_id: str | None
    workspace_id: str
    workspace_name: str
    repo_name: str | None
    state: SessionState
    title: str | None
    brief: str | None
    needs_you_reason: str | None
    tasks_done: int
    tasks_total: int
    active_subagents: int
    last_event_at: str | None
    cwd: str | None

    # ----- the stop group the fleet page renders (M2, T2) -----------------
    stop_reason: str | None = None
    outcome: str | None = None
    why: str | None = None
    confidence: float | None = None
    decided_by: str | None = None
    next_actions: tuple[NextAction, ...] = ()
    exit_code: int | None = None

    # ----- the owned-session group the fleet tree renders (M3, T4) --------
    runner_handle: RunnerHandle | None = None
    """An owned row with no handle is an orphan the page must not present as a
    session it can drive (T11, T12)."""
    title_synced_at: str | None = None
    """D29's `local only` marker is `title_source == 'user'` with this null."""
    parent_session_id: str | None = None
    depth: int = 0
