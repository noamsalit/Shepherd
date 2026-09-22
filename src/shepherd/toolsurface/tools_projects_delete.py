"""D61's project delete: plan, kill **between**, commit — and the kill's own errors.

**A split out of `tools_projects.py`** (T3.4), which shipped at 441 lines
against the 450-line cap and could not absorb the blocking fix below. The cut
is where the plan already drew it: this is the one verb in D57's family that
issues an **effect outside the process**, and the only one whose handler takes
an injected callable. Everything else in that module rearranges arguments and
calls one store verb.

**The fix this module was cut for.** `kill` is allowed to raise and the shipped
one does — `runner/local.py` raises `RunnerRefusal` for a stale handle, which is
a row whose `ended_at` is still NULL while its pane is gone, and `plan.running`
*is* `ended_at IS NULL`. The loop used to be a generator expression, so the
second session's refusal escaped the verb **after the first session was already
dead**: `commit_project_delete` never ran, `registry.py` flattened the escape to
`GENERIC_ERROR`, and a page rendered "request failed" for a call that had just
stopped a live agent, with no record of which.

`store/` holds *"never raises, every negative answer is a record"* on both
halves of this verb. Moving the kill out of the transaction moved it out of that
layer's error contract too, so **this layer re-states it**: `_kill_running`
catches per session, counts the unknown, names it on the record, and lets the
store's own `ended_at` fact decide the delete.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from shepherd.core.anomalies import AnomalyKind
from shepherd.store.db import Store
from shepherd.store.models import DeleteOutcome, DeletePlan, OnRunning
from shepherd.toolsurface.tools_projects_reads import PROJECT_ID, STRING, object_schema
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolDef,
    arg_optional_str,
    arg_str,
)

__all__ = [
    "KillFailure",
    "KillSession",
    "build_delete_tool",
    "delete_outcome",
    "delete_project",
    "on_running_schema",
    "refuses_every_kill",
]

#: Stop one session, and answer **whether the kill landed**.
#:
#: `bool`, not `None`: `DeleteOutcome.killed` is what the caller reports it
#: actually killed, and the shipped kill path answers `no_pane(session_id)` for
#: any session it has no runner handle for — which is every *attached* one. A
#: callable that cannot report failure makes "killed" a list of sessions that
#: may still be running.
KillSession = Callable[[str], bool]

#: One session whose kill did not land **because it raised**, and the reason.
#: Reported on the record beside `killed`, so a refusal that says "1 session is
#: still running" can also say why the stop did not take.
KillFailure = tuple[str, str]

#: Spelled here rather than imported, for the reason the other two halves spell
#: it: `tests/boundaries/test_session_audience.py` resolves a `ToolDef`'s
#: `audiences=` through the defining module's **own** top-level bindings, cannot
#: follow an import, and reports a tool it cannot read as unread.
MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})


def on_running_schema() -> Mapping[str, object]:
    """D61's three-way choice, **derived from `OnRunning`** and never typed out.

    The plan carried `["refuse", "kill", "orphan"]` for five revisions while the
    enum's middle member had become `kill_sessions` — a bare `kill` is a tmux
    command-name prefix that resolves to `kill-server`, which
    `tests/boundaries/test_tmux_blast_radius.py` refuses in `src/`. A
    hand-written list is exactly how that drifts again.

    **No `default` key.** Default-refuse has to be unskippable by omission, and
    a schema default is a value a caller is handed without asking for it; the
    fallback belongs in the handler, where a request cannot edit it out.
    """
    return {"type": "string", "enum": [member.value for member in OnRunning]}


def delete_outcome(
    outcome: DeleteOutcome,
    *,
    plan: DeletePlan | None = None,
    kill_failures: Sequence[KillFailure] = (),
) -> dict[str, object]:
    """D61's record, projected whole — every field, on refusals too.

    Phase 9's dialog renders from these four lists and not from a second read:
    `killed` (what the caller reports it actually stopped), `orphaned` (moved to
    Unassigned, still on Flock), `severed` (lineage links nulled on sessions
    that *survived*, which D61 says a person is owed) and `destroyed` (the
    session rows the cascade took — a person told `orphaned=('s-live',)` and
    nothing else is not told that four hundred finished sessions went with the
    project).

    `deleted`/`refused` are the same two keys the other verbs in this family
    carry, so one consumer branch covers all of them.
    """
    return {
        "deleted": outcome.deleted,
        "refused": outcome.refused,
        "running": list(outcome.running),
        "killed": list(outcome.killed),
        "orphaned": list(outcome.orphaned),
        "severed": [
            {"session_id": link.session_id, "column": link.column} for link in outcome.severed
        ],
        "destroyed": list(outcome.destroyed),
        # The plan's three, projected on refusals as well as on outcomes —
        # which is the whole point of them. `doomed` is what this delete would
        # take if the caller proceeds, so a dialog can say it **before** the
        # button instead of counting sessions itself out of a second read; the
        # split of `running` is what lets it gray a choice that cannot work
        # rather than discovering that by click. `plan` is `None` only for the
        # refusal that happens before there is a plan (an `on_running` outside
        # the enum), where the honest answer to all three is "nothing known".
        "doomed": list(plan.doomed) if plan is not None else [],
        "killable": list(plan.killable) if plan is not None else [],
        "unkillable": list(plan.unkillable) if plan is not None else [],
        # Not a `store/` fact and deliberately not on `DeleteOutcome`: the
        # store never saw the raise, and a record of what the *caller's* kill
        # did belongs to the layer that called it.
        "kill_failures": [
            {"session_id": session_id, "reason": reason}
            for session_id, reason in kill_failures
        ],
    }


def _kill_running(
    store: Store, kill: KillSession, running: Sequence[str]
) -> tuple[tuple[str, ...], tuple[KillFailure, ...]]:
    """Ask for every session, and let no kill escape the verb.

    **`kill` is allowed to raise, and the shipped one does.**
    `orchestration/lifecycle.py` states that contract deliberately — a failed
    kill's `RunnerRefusal` propagates rather than answering "killed" over a
    session that is still alive — and `runner/local.py` raises it for a stale
    handle: a row whose `ended_at` is still NULL while its pane is gone, which
    is the orphan case Shepherd exists to notice. `plan.running` **is**
    `ended_at IS NULL`, so such a row is exactly what this loop is handed.

    An escape here is the worst shape available: the sessions before it are
    already dead, `commit_project_delete` never runs, and `registry.py`
    flattens the exception to `GENERIC_ERROR` — a page told "request failed"
    for a call that just stopped a live agent, with no record of which.

    **`store/` holds "never raises, every negative answer is a record" on both
    halves of this verb; the kill moved out of that layer, so this one
    re-states it** rather than inheriting it. A raise is a kill that
    *did not land* — not swallowed: it is counted (principle 5, and
    `stop_failed` is already the kind for a stop that did not) and named on the
    record, and the delete is then decided by the store's own `ended_at` fact
    inside `commit_project_delete`, which refuses and says which sessions
    survived.

    `stop_failed` is reused rather than a new member minted: the kind means *a
    stop that failed*, which is what this is, and the member set is append-only
    with a seeded zero row per member in `doctor`.
    """
    killed: list[str] = []
    failures: list[KillFailure] = []
    for session_id in running:
        try:
            landed = kill(session_id)
        except Exception as refusal:  # noqa: BLE001 — an unknown is counted, never raised
            store.bump_anomaly(AnomalyKind.STOP_FAILED.value)
            failures.append((session_id, f"{type(refusal).__name__}: {refusal}"))
            continue
        if landed:
            killed.append(session_id)
    return tuple(killed), tuple(failures)


def delete_project(
    store: Store, kill: KillSession, *, project_id: str, on_running: str | None
) -> dict[str, object]:
    """Plan, kill **between**, commit.

    The middle step is the whole reason this verb is three calls rather than
    one: stopping a session issues subprocesses, and `Store._write` runs its
    callable on the single writer thread inside `BEGIN IMMEDIATE`. So the kill
    happens here, on the calling thread, holding no lock — and
    `commit_project_delete` re-derives the decision in its own transaction, so a
    session that started while the killing was going on refuses the delete
    rather than being deleted out from under.

    **`on_running` defaults to `REFUSE` here rather than in the schema** (D61,
    E13): a schema default is a value a caller is handed without asking for it,
    and default-refuse has to be unskippable by omission. A value outside the
    enum is refused as a value — JSON Schema's `enum` is not something a binding
    is guaranteed to carry through unchanged (D53), and the one fallback this
    must never take is a destructive member.
    """
    try:
        choice = OnRunning.REFUSE if on_running is None else OnRunning(on_running)
    except ValueError:
        return delete_outcome(
            DeleteOutcome(
                deleted=False,
                refused=(
                    f"{on_running!r} is not one of "
                    f"{', '.join(member.value for member in OnRunning)}"
                ),
            )
        )

    plan = store.plan_project_delete(workspace_id=project_id, on_running=choice)
    if plan.refusal is not None:
        # The **plan**, not only its refusal: `doomed` and the killable split
        # are read before the button, and the handler used to discard the one
        # record that carries them.
        return delete_outcome(plan.refusal, plan=plan)
    killed, failures = (
        _kill_running(store, kill, plan.running) if choice is OnRunning.KILL else ((), ())
    )
    return delete_outcome(
        store.commit_project_delete(plan=plan, killed=killed),
        plan=plan,
        kill_failures=failures,
    )


def refuses_every_kill(session_id: str) -> bool:
    """The default injection: a kill that reports it did **not** land.

    Not a no-op returning `True`. A `delete_project` registered without a real
    kill path can still be *asked* to kill, and answering "yes" would let
    `commit_project_delete` delete the rows of sessions that are still running.
    Answering "no" makes the commit half refuse and say which sessions are
    still alive, which is the only safe thing a process with no kill path can
    say. `compose.py` injects the real one.
    """
    return False


def build_delete_tool(store: Store, kill: KillSession) -> ToolDef:
    """The one definition this module owns, with the store and the kill closed
    over — concatenated into `build_project_tools`'s tuple, so the registration
    stays one loop over one tuple and the split cannot lose a verb."""
    return ToolDef(
        name="delete_project",
        description=(
            "Forget a project and everything in it (D61). Sessions still running "
            "refuse the delete unless the caller chooses otherwise."
        ),
        input_schema=object_schema(
            {PROJECT_ID: STRING, "on_running": on_running_schema()}, [PROJECT_ID]
        ),
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=lambda args, ctx: delete_project(
            store,
            kill,
            project_id=arg_str(args, PROJECT_ID),
            # Absent, never defaulted in the schema: `arg_optional_str`
            # answers `None`, and `None` is what the handler turns into
            # `REFUSE`. A request cannot edit that out.
            on_running=arg_optional_str(args, "on_running"),
        ),
        audiences=MASTER_AND_HUMAN,
    )
