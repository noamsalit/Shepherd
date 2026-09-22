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
from enum import StrEnum
from typing import Final

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership, SessionState, TitleSource
from shepherd.core.stops import NextAction

__all__ = [
    "DEFAULT_ENGINE",
    "SESSION_COLUMNS",
    "UNASSIGNED_PROJECT_ID",
    "DeleteOutcome",
    "DeletePlan",
    "FleetRow",
    "OnRunning",
    "Repo",
    "ReplayTarget",
    "Session",
    "SeveredLink",
    "StopCounts",
    "StoreError",
    "SubagentRollup",
    "TitleSource",
    "Workspace",
]

#: The engine M1 observes. §7 has no default for it, so the verb supplies one.
DEFAULT_ENGINE = "claude_code"

#: The reserved project (ADR-P2, §3 D57), seeded by `004_projects.sql`. Work
#: that matched no declared project lands here rather than minting one.
#:
#: **The one definition site.** A literal rather than a ULID because a sentinel
#: that reads as itself in a log beats one nobody can recognise, and it lives
#: here rather than beside each guard because a reserved id spelled twice is a
#: reserved id that will eventually be spelled two ways.
UNASSIGNED_PROJECT_ID: Final[str] = "unassigned"


class OnRunning(StrEnum):
    """What `delete_project` does about sessions that are still running.

    The default is `REFUSE`: the page renders the other two choices *from the
    refusal*, so the destructive answers are ones a human picked rather than
    ones a default picked for them.
    """

    REFUSE = "refuse"
    KILL = "kill_sessions"
    """Spelled `kill_sessions`, not `kill`, and the reason is a real one.

    `tests/boundaries/test_tmux_blast_radius.py` refuses any string constant in
    `src/` that `runner.tmux_cmd.is_server_teardown` answers `True` for, and a
    bare `kill` is one: tmux resolves an unambiguous command-name **prefix**, so
    `kill` reaches `kill-server`, and the guard refuses ambiguous prefixes on
    purpose. That guard exists because a spike's `kill-server` destroyed three
    live sessions on 2026-09-12, and because M3 later found the first version of
    it was a *spelling* that `kill-serv` walked straight through.

    The word is not lost: `kill_sessions` is what D61 means, it is what the page
    says, and it matches the `kill_session` tool that has shipped since M3 — which
    is itself a string constant in `src/` that this same guard already accepts.
    The value was the collision, not the vocabulary.
    """
    ORPHAN = "orphan"


@dataclass(frozen=True)
class SeveredLink:
    """One lineage reference the delete had to null, and which column it was.

    `session` references itself twice — `parent_session_id` and `retry_of`
    (001:58,64) — and `PRAGMA foreign_keys` is ON. A session that survives the
    cascade (orphaned, or living in another project) while the row it points at
    is deleted would abort the whole statement, so the reference is severed
    first. D61 says a delete **forgets**: a surviving child whose parent was
    forgotten honestly has no parent. Refusing instead would mean telling
    someone *"you cannot delete this project because a session in it once
    spawned a child"*, which is not a thing to say to a person.

    Nulling **silently** is the part that is not acceptable, which is why this
    record exists and rides back on `DeleteOutcome.severed`.
    """

    session_id: str
    column: str
    """`"parent_session_id"` or `"retry_of"` — the two self-references."""


@dataclass(frozen=True)
class DeleteOutcome:
    """What the delete's commit half answers with — never a bare bool.

    A refusal has to carry *why* and *which sessions*, because E13's dialog is
    built from this record: a caller that only learns `False` has to go and ask
    a second question to render anything, and the second question can disagree
    with the first.
    """

    deleted: bool
    refused: str | None = None
    running: tuple[str, ...] = ()
    """Session ids that stopped the delete, when `on_running` was `REFUSE`."""
    killed: tuple[str, ...] = ()
    """The sessions the **caller reports it actually killed**, not the ones it
    was asked to kill.

    The verb used to take a `Callable[[str], None]` and report every id it had
    called it with. That callable could not report failure, while the real kill
    path answers `no_pane(session_id)` as a returned dict for any session
    without a runner handle — which is every *attached* session. So the field
    said "killed" over sessions that were still running. The caller kills
    between the two halves and now knows which kills landed; this is that."""
    orphaned: tuple[str, ...] = ()
    """Sessions moved to `UNASSIGNED_PROJECT_ID`. They stay visible on Flock —
    `Store.fleet()` is an INNER JOIN, so a session pointing at a deleted
    workspace would vanish without trace (P2)."""
    severed: tuple[SeveredLink, ...] = ()
    """Lineage links nulled on **surviving** sessions so the cascade could run."""
    destroyed: tuple[str, ...] = ()
    """Session rows the cascade deleted — every ended session in the project,
    plus the running ones under `KILL`. A person told `orphaned=('s-live',)`
    and nothing else is not told that four hundred finished sessions went with
    the project; `DeletePlan.doomed` is the same list **before** the button."""


@dataclass(frozen=True)
class DeletePlan:
    """The delete's decision half: a pure read, and the whole of the refusal.

    The verb is two halves because the middle of it — stopping the running
    sessions — is a subprocess, and `Store._write` runs its callable on the one
    writer thread inside `BEGIN IMMEDIATE`. The caller reads this plan, kills
    what it decides to kill *outside* any transaction, and hands the plan back
    to `commit_project_delete`. D33's line ("no runner behind a
    `sqlite3.Connection`") is then structural rather than a promise.

    `refusal` is the whole answer when it is not `None`: the page renders its
    three choices out of that record.
    """

    workspace_id: str
    on_running: OnRunning
    running: tuple[str, ...] = ()
    """What is alive in the project **now** — what the caller must kill under
    `KILL`, and what is moved out under `ORPHAN`."""
    doomed: tuple[str, ...] = ()
    """Session rows this delete would destroy, so the dialog can say what it is
    about to take **before** the button rather than in the outcome."""
    refusal: DeleteOutcome | None = None

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
    description: str | None
    created_at: str
    """`workspace.last_activity_at` is **not** here. The column exists in the
    schema and nothing writes it (ADR-P4/RD-3): the value is derived per
    project by `reads.project_last_activity`, and a field mapped off the dead
    column would be permanently `None` under a docstring promising otherwise —
    a page that believed it would render "never" for every project with no test
    going red. The column stays in 001; dropping it is a table rebuild for a
    field nothing reads."""


@dataclass(frozen=True)
class Repo:
    """§7 `repo`, plus D48's binding key."""

    id: str
    owner_id: str
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
