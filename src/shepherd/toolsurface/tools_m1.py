"""M1's read tools — enough for `web/` (T15), the fleet page (T16) and `cli/` (T17).

Two rules shape every function here:

* **§13's response rule.** A handler projects an explicit field whitelist. It
  never returns a store dataclass, and never spreads one — so a column added to
  `session` tomorrow cannot appear on the wire by accident, and `owner_id`, the
  pid and the engine's own session id never leave the process.
* **Principle 5.** A session that is not there, a transcript that was announced
  and never written, a discovery status no scan has published yet — each comes
  back as a *value* a page can render, never as an exception and never as a
  silent empty.

The tools are registered with the store and the transcript root **closed over**,
so a consumer names a capability and never a dependency (D32). M4 adds the gate
and the audit log behind `invoke()`, which is why nothing here knows about them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import utc_now as _utc_now
from shepherd.core.states import FLEET_STATE_ORDER, SessionState
from shepherd.core.stops import BUCKET_ORDER, NextAction
from shepherd.engines.claude_code.transcript import (
    SubagentRow,
    locate_transcript,
    read_subagents,
)
from shepherd.signals.ordering import (
    bucket_of,
    effective_state,
    fleet_bucket_sort_key,
)
from shepherd.store.db import Store
from shepherd.store.models import FleetRow, Session, Workspace
from shepherd.toolsurface.approvals import Approval
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolDef,
    arg_optional_str,
    arg_str,
)

Clock = Callable[[], str]

#: §12's third rail source, as a **seam rather than an import-down** (D2 of the
#: M1-M4 QA pass). `ApprovalStore` and this module are both L4, so the question
#: is not layering but composition: `compose_tool_surface` owns the one approval
#: store this process gates through, and handing its `pending` here is how the
#: rail sees the same cards the gate does. A second store would be a second set
#: of cards, which `M4Wiring`'s own docstring already refuses.
PendingApprovals = Callable[[], Sequence[Approval]]

#: The key `run_discovery_loop` publishes its status under. Named here rather
#: than imported: `signals/discovery_loop.py` owns the scan cadence and T7b's
#: one-module assertion, and one shared string is not worth breaking it over.
DISCOVERY_STATUS_KEY = "discovery_status"

#: Principle 5: before the first scan, the status is *unknown* — not "absent",
#: which is a thing we would have had to observe.
UNKNOWN = "unknown"

_HUMAN_AND_MASTER = frozenset({Audience.MASTER, Audience.HUMAN})
_EVERY_AUDIENCE = frozenset({Audience.MASTER, Audience.SESSION, Audience.HUMAN})

_NO_ARGS: Mapping[str, object] = {"type": "object", "properties": {}}


def utc_now() -> str:
    """The `now` every read tool compares `last_event_at` against (`core.clock`)."""
    return _utc_now()


# ----- projections (§13: an explicit whitelist at every response sink) --------


def project_action(action: NextAction) -> dict[str, object]:
    """One of D21's items, as the four keys §12 draws (DP5).

    The same four reach the fleet row and `get_session`, because §12's rule is
    that the master reads the *identical* items rather than re-reasoning about a
    stop it can already see classified.
    """
    return {
        "text": action.text,
        "kind": str(action.kind.value),
        "target": action.target,
        "source": str(action.source.value),
    }


def project_session(session: Session, *, bucket: str | None) -> dict[str, object]:
    """§13's whitelist, M1's seventeen plus M2's stop group (T13).

    `bucket` is a **parameter and not a column**: §4's bucket is a read-time
    derivation over `state`, `last_event_at` and `outcome` (`signals.bucket_of`),
    and a stored row on its own cannot say whether a `running` session has gone
    silent. A caller that has no fleet row to derive it from passes `None`,
    which renders as *not determined here* rather than as a bucket nobody
    computed (principle 5).
    """
    return {
        "bucket": bucket,
        "stop_reason": session.stop_reason,
        "outcome": session.outcome,
        "why": session.why,
        "confidence": session.confidence,
        "decided_by": session.decided_by,
        "next_actions": [project_action(action) for action in session.next_actions],
        "exit_code": session.exit_code,
        "ended_at": session.ended_at,
        "session_id": session.id,
        "workspace_id": session.workspace_id,
        "repo_id": session.repo_id,
        "origin": str(session.origin.value),
        "ownership": str(session.ownership.value),
        "engine": session.engine,
        "title": session.title,
        "state": str(session.state.value),
        "brief": session.brief,
        "cwd": session.cwd,
        "started_at": session.started_at,
        "last_event_at": session.last_event_at,
        "needs_you_reason": session.needs_you_reason,
        "model": session.model,
        "tasks_done": session.tasks_done,
        "tasks_total": session.tasks_total,
        "active_subagents": session.active_subagents,
    }


def project_fleet_row(row: FleetRow, session: Session, now: str) -> dict[str, object]:
    """The fleet's row: the session's whitelist with the two read-time facts.

    `state` carries §8's demotion and `bucket` carries §12's palette slot, and
    both are computed in L2 — which is the half `web/` could never do for
    itself, because the comparison is against the liveness window and a consumer
    may not import `shepherd.signals` (D19/D35).
    """
    return project_session(session, bucket=str(bucket_of(row, now).value)) | {
        "state": str(effective_state(row, now).value)
    }


def project_workspace(
    workspace: Workspace, *, repo_count: int, last_activity_at: str | None
) -> dict[str, object]:
    """D22: a project **is** a workspace, so the consumer-facing key is `project_id`.

    `root_path` is gone with the column (D57) — a project has no path, its
    repos do — and `repo_count` and `last_activity_at` arrive as **arguments**
    rather than being fetched here. That is what keeps the list one query each
    (M4/RD-3): a projection that reached for a store would be an N+1 the moment
    it was called in a loop, which is exactly how it is called.
    """
    return {
        "project_id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "repo_count": repo_count,
        "last_activity_at": last_activity_at,
    }


#: How many pending approvals one rail row stands for. A row **per card**, so
#: the rail's count is the number of things a person has to answer; an aggregate
#: row reading "1 needs you" over a five-card backlog is the silence principle 5
#: refuses. §12's mock line is therefore per-row and always says `1`.
_ONE_APPROVAL = "1 approval pending"


def project_needs_you(row: FleetRow) -> dict[str, object]:
    """One blocked session, as §12's rail reads it."""
    return {
        "session_id": row.session_id,
        "title": row.title,
        "workspace_name": row.workspace_name,
        "needs_you_reason": row.needs_you_reason,
        "last_event_at": row.last_event_at,
    }


def project_pending_approval(card: Approval) -> dict[str, object]:
    """One pending card, as §12's third row kind (D2 of the M1-M4 QA pass).

    §12 draws it as `1 approval pending · work_item_set_status`, and `rail.js`
    renders `titleOf(row) · askOf(row)` — so the mock line *is* this projection's
    `title` and `needs_you_reason`, and no file in `web/` changes. The ask is the
    **tool that is waiting**, never a category: §12 forbids "session needs
    attention" and a row saying only "an approval" is the same defect spelled
    politely.

    **The key set is `project_needs_you`'s, exactly**, so the rail carries one row
    shape and `rail.js` never branches on which kind it was handed — it composes
    nothing by design. `session_id` is `None` because an approval is not a
    session: a value rather than an omission, so a consumer reading it gets
    *there is no session here* rather than a plausible wrong one.

    **No card id travels, and that is deliberate.** `rail.js` reads neither id;
    adding one would have put a key on all 50 `needs_you` rows of a 200-session
    fleet and taken `fleet_summary` from 12 927 B to 13 877 B —
    `test_the_master_read_tools_size_does_not_regress` measured it. G-M4-8 is
    already open on this projection's bound, and paying 950 B for a field no
    consumer reads would be answering an open finding by making it worse. With no
    card pending this repair costs **zero** bytes.
    """
    return {
        "session_id": None,
        "title": _ONE_APPROVAL,
        "workspace_name": None,
        "needs_you_reason": card.tool,
        "last_event_at": card.created_at,
    }


def project_subagent(row: SubagentRow) -> dict[str, object]:
    return {
        "agent_id": row.agent_id,
        "agent_type": row.agent_type,
        "description": row.description,
        "started_at": row.started_at,
        "last_activity_at": row.last_activity_at,
        "state": str(row.state),
        "source": str(row.source),
    }


def project_discovery(raw: object) -> dict[str, object]:
    """`app_state["discovery_status"]`, whitelisted — or its unknown shape (F16)."""
    stored = raw if isinstance(raw, dict) else {}
    hooks = stored.get("hooks")
    return {
        "hooks": hooks if isinstance(hooks, str) else UNKNOWN,
        "registry_sessions": _count(stored.get("registry_sessions")),
        "sdk_cli_skipped": _count(stored.get("sdk_cli_skipped")),
        # T19-1/DP2: the denominator's two halves travel with it. `reconciled`
        # alone would read as coverage the reconcile has not earned.
        "sdk_cli_reconciled": _count(stored.get("sdk_cli_reconciled")),
        "sdk_cli_missed": _count(stored.get("sdk_cli_missed")),
        "skipped_other": _count(stored.get("skipped_other")),
        "unknown_status": _count(stored.get("unknown_status")),
        "scan_interval_s": stored.get("scan_interval_s") if stored else None,
        "last_scan_at": stored.get("last_scan_at") if stored else None,
    }


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


# ----- the five read tools ----------------------------------------------------


def fleet_summary(
    store: Store, clock: Clock, pending_approvals: PendingApprovals
) -> dict[str, object]:
    """Counts per live state, the `needs_you` list, and what discovery can see.

    The counts use T11's read-time backstop, so a session that has been silent
    past the liveness window is not counted as running (§8) — no event says so,
    because silence emits nothing.

    **`pending_approvals` is D2's repair and it is injected, not imported.**
    §12's rail has three sources and this projection saw two; the third is
    `ApprovalStore.pending()`, which lives in the same layer but belongs to the
    process's composition rather than to M1's reads. A reader closed over by
    `compose_tool_surface` keeps `tools_m1.py` free of the gate it is not part of
    and keeps *"a second `ApprovalStore` is a second set of cards"* (M4Wiring)
    true by construction.

    **This makes G-M4-8 worse and that is said out loud.** §11 promises ~40 lines
    regardless of fleet size; this projection was already 85 at one session, and
    `needs_you` — the unbounded term — now grows with pending cards as well as
    with blocked sessions. The added term is bounded by the number of callers
    parked on the gate at once, which is far smaller than the fleet, and it is
    the term a person most needs; the projection's bound stays the open design
    decision G-M4-8 records, not something this repair closes.
    """
    now = clock()
    rows = store.fleet()
    counts = {str(state.value): 0 for state in FLEET_STATE_ORDER}
    # Built in §12's display order, because the page renders the order it was
    # handed and never re-derives one (M1's `test_the_page_does_not_re_derive_
    # the_order`, extended to the buckets at T14).
    by_bucket = {str(bucket.value): 0 for bucket in BUCKET_ORDER}
    needs_you: list[dict[str, object]] = []
    for row in rows:
        state = effective_state(row, now)
        counts[str(state.value)] = counts.get(str(state.value), 0) + 1
        by_bucket[str(bucket_of(row, now).value)] += 1
        if state is SessionState.NEEDS_YOU:
            needs_you.append(project_needs_you(row))
    needs_you.extend(project_pending_approval(card) for card in pending_approvals())
    stops = store.stop_verdict_counts()
    return {
        "counts": counts,
        "by_bucket": by_bucket,
        # Three numbers, three different meanings, and none folded into another
        # (ADR-M2-5, DP10): *we could not map this stop*, *we never saw this
        # stop*, and *the turn ended cleanly and no heuristic could tell us
        # whether it finished*. The last is the largest cohort — D34 starts a
        # clean stop as `completed` at 0.5, and `finished` is green whatever the
        # confidence — so leaving it uncounted would show a green chip claiming
        # a verification nobody performed, and would delete D34's own stated
        # trigger for building the model lane from the product.
        "unknown_rate": (stops.unknown / stops.classified) if stops.classified else 0.0,
        "unknown": stops.unknown,
        "classified": stops.classified,
        "unclassified": stops.unclassified,
        "completed_low_confidence": stops.completed_low_confidence,
        "needs_you": needs_you,
        "session_count": len(rows),
        # Every kind this build knows, at zero, plus every kind actually
        # counted — including one this build has no member for (BLOCKER T14-3).
        # Asking per member can only ever show the kinds we already expected.
        "anomalies": {str(kind.value): 0 for kind in AnomalyKind}
        | store.list_anomaly_counts(),
        "discovery": project_discovery(store.get_app_state(DISCOVERY_STATUS_KEY)),
        "now": now,
    }


def fleet_tree(store: Store, clock: Clock) -> dict[str, object]:
    """§16's ordered tree: workspace → session → the rollup the row carries.

    This is the tool BLOCKER T16-1 was waiting for, and it is a **projection**,
    not new logic: `Store.fleet()` supplies the rows, `effective_state` supplies
    §8's read-time demotion and `fleet_bucket_sort_key` supplies §12's bucket
    order — a **refinement** of §16's four-state order, not a replacement, so
    `needs_you` still leads and a silent `running` row is still demoted. All three
    already live in L2/L4. The page renders the order it is handed and never
    re-derives it — which is what `web/` could not do for itself, because the
    demotion compares `last_event_at` against the liveness window and `web/` may
    not import `shepherd.signals` (the consumer boundary, and it is right to).

    Workspaces appear in the order of their best-ranked session, so the project
    holding a `needs_you` session is the first block on the page.
    """
    now = clock()
    ordered = sorted(store.fleet(), key=lambda row: fleet_bucket_sort_key(row, now))
    by_id = {session.id: session for session in store.list_sessions()}
    names = {workspace.id: workspace.name for workspace in store.list_workspaces()}
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in ordered:
        session = by_id.get(row.session_id)
        if session is None:
            # A row that vanished between the two reads is not an error and not
            # a blank: it is simply not in this tree (principle 5).
            continue
        grouped.setdefault(row.workspace_id, []).append(
            project_fleet_row(row, session, now)
        )
    return {
        "workspaces": [
            {
                "project_id": workspace_id,
                "name": names.get(workspace_id, UNKNOWN),
                "sessions": sessions,
            }
            for workspace_id, sessions in grouped.items()
        ],
        "session_count": len(ordered),
        "now": now,
    }


def list_projects(store: Store) -> dict[str, object]:
    """Three reads for the whole list, whatever its length: the projects, the
    repo counts, and the derived last activity (M4)."""
    counts = store.repo_counts()
    activity = store.project_last_activity()
    return {
        "projects": [
            project_workspace(
                row,
                repo_count=counts.get(row.id, 0),
                last_activity_at=activity.get(row.id),
            )
            for row in store.list_workspaces()
        ]
    }


def fleet_buckets(store: Store, now: str) -> dict[str, str]:
    """Each fleet row's §4 bucket, by session id.

    One pass over the same rows `fleet_tree` orders, so a session reached by id
    and the same session on the page carry the *same* bucket rather than two
    derivations that can disagree. A session the fleet does not carry — an
    ephemeral one — is simply absent, and the projection says `None`.
    """
    return {row.session_id: str(bucket_of(row, now).value) for row in store.fleet()}


def list_sessions(
    store: Store,
    clock: Clock,
    project_id: str | None = None,
    state: str | None = None,
) -> dict[str, object]:
    """§11's filters. An unrecognised state is refused rather than ignored."""
    wanted = SessionState(state) if state is not None else None
    rows = store.list_sessions(workspace_id=project_id, state=wanted)
    buckets = fleet_buckets(store, clock())
    return {
        "sessions": [
            project_session(row, bucket=buckets.get(row.id)) for row in rows
        ]
    }


def get_session(store: Store, clock: Clock, session_id: str) -> dict[str, object]:
    """One row plus the subagent rollup the row itself carries (§7 line 609)."""
    session = store.get_session(session_id)
    if session is None:
        return {"found": False, "session": None, "subagents": None}
    return {
        "found": True,
        "session": project_session(
            session, bucket=fleet_buckets(store, clock()).get(session.id)
        ),
        "subagents": {
            "session_id": session.id,
            "active": session.active_subagents,
            "tasks_done": session.tasks_done,
            "tasks_total": session.tasks_total,
        },
    }


def list_subagents(store: Store, projects_root: Path, session_id: str) -> dict[str, object]:
    """The expanded third tier, read from the transcript on demand (T13).

    A session we do not have, one with no engine id yet, and a transcript that
    was announced and never written (E26) are the same answer here: an empty
    list with `transcript_found` false. The page shows a count of zero rather
    than an error, and the anomaly count says whether anything was torn.
    """
    session = store.get_session(session_id)
    engine_session_id = None if session is None else session.engine_session_id
    transcript = (
        None
        if engine_session_id is None
        else locate_transcript(projects_root, engine_session_id)
    )
    if transcript is None:
        return {
            "session_id": session_id,
            "subagents": [],
            "transcript_found": False,
            "anomaly_count": 0,
        }
    rows, anomalies = read_subagents(transcript)
    return {
        "session_id": session_id,
        "subagents": [project_subagent(row) for row in rows],
        "transcript_found": True,
        "anomaly_count": len(anomalies),
    }


# ----- registration -----------------------------------------------------------


def build_read_tools(
    store: Store,
    projects_root: Path,
    clock: Clock = utc_now,
    *,
    pending_approvals: PendingApprovals,
) -> tuple[ToolDef, ...]:
    """The read set, with their dependencies closed over (D32).

    Every schema carries a string `type` **and** a `properties` key, because a
    binding mangles any dict that does not (D53) — and `register()` refuses one
    that does not, so this is checked rather than promised.
    """
    return (
        ToolDef(
            name="fleet_summary",
            description="Counts per live state, the needs-you list, and discovery status.",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: fleet_summary(store, clock, pending_approvals),
            audiences=_HUMAN_AND_MASTER,
        ),
        ToolDef(
            name="fleet_tree",
            description="Workspace -> session -> rollup, ordered by state (§16).",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: fleet_tree(store, clock),
            audiences=_HUMAN_AND_MASTER,
        ),
        ToolDef(
            name="list_projects",
            description="Every project (D22: a project is a workspace).",
            input_schema=_NO_ARGS,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_projects(store),
            audiences=_HUMAN_AND_MASTER,
        ),
        ToolDef(
            name="list_sessions",
            description="Sessions, optionally filtered by project and state.",
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "state": {"type": "string"},
                },
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_sessions(
                store,
                clock,
                project_id=arg_optional_str(args, "project_id"),
                state=arg_optional_str(args, "state"),
            ),
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="get_session",
            description="One session with its subagent rollup.",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: get_session(store, clock, arg_str(args, "session_id")),
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="list_subagents",
            description="The subagents of one session, read from its transcript.",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_subagents(
                store, projects_root, arg_str(args, "session_id")
            ),
            audiences=_HUMAN_AND_MASTER,
        ),
    )


def register_read_tools(
    store: Store,
    projects_root: Path,
    clock: Clock = utc_now,
    *,
    pending_approvals: PendingApprovals,
) -> None:
    """Called by the composition root at startup, before `freeze_registry()`.

    `pending_approvals` is **keyword-only and has no default**. A default of
    *"no cards"* would let a composition root forget §12's third rail source and
    still be green — which is the exact shape of the defect this parameter
    exists to repair.
    """
    for tool in build_read_tools(
        store, projects_root, clock, pending_approvals=pending_approvals
    ):
        register(tool)
