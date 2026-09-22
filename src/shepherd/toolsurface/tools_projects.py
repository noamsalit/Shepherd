"""D57's project lifecycle, as one implementation the master and `web/` share (D58).

**This module is not pure, and that is the point of it** (F5, the purity map).
`writes.add_repo` requires `git_common_dir`, `name` and `vcs_remote`; the route
declares only `root_path`. The three are answered here, by `signals/binding.py`'s
`probe_repo`, `repo_root` and `resolve_remote` — **a git subprocess**. The
`toolsurface -> signals` import edge already exists (`tools_m1.py:33`) and is
permitted: `signals` is layer 2 and `toolsurface` is layer 4, and the rule
forbids *upward* imports only.

**Why the probe is here rather than guessed.** `git_common_dir` is D48's binding
key. A repo registered through the UI with a guessed or empty value never
matches `find_repo_by_common_dir`, so a session started in it later binds to
`Unassigned` — silently, and in exactly the flow the Projects page exists to
make work. A path that does not probe as a repo is therefore **refused and says
so**; it is never registered with a placeholder.

**Path canonicalization is here too** (E10), for the reason the purity map
gives: `store/` takes a `sqlite3.Connection` and does no filesystem I/O at all,
so the only honest place to learn whether a path exists is the layer that is
already allowed to look.

**One refusal shape for the whole family.** `store/`'s five verbs carry three
conventions — `rename_project` raises `StoreError` for the reserved project and
answers `None` for a missing one, `add_repo` raises for both, `delete_project`
returns a record for both. At this layer every one of them becomes the same
record: a boolean that says whether it happened and a `refused` string that says
why not. A consumer that has to branch on three shapes for one family of verbs
will eventually branch on two and crash on the third, and a raised `StoreError`
reaches a page as `request failed` (`registry.py:69`) — which is not a reason
anything can draw.

**`delete_project` kills between two store calls, and never inside one.**
The verb it was blocked on took a `kill` callable and ran it from inside the
lambda `Store._write` executes on the single writer thread after
`BEGIN IMMEDIATE`, while the shipped kill path's *first* statement is itself a
store write (`orchestration/lifecycle.py:126`) whose write-before-kill order is
what survives a crash — so the job enqueued behind the writer that was waiting
for it, and the writer has no timeout. Phase 1's remediation withdrew that verb.
What replaced it is two halves: `Store.plan_project_delete` decides (a pure
read, carrying the whole refusal) and `Store.commit_project_delete` deletes,
re-deriving the decision inside its own transaction so a session that arrived
while the caller was killing is refused rather than deleted out from under.

The kill therefore happens **here**, between the two, on the calling thread and
inside no transaction. It is injected at registration rather than reached for,
because this module must not import `orchestration` and because the one thing a
test of this verb has to be able to do is program what the kill *did*:
`DeleteOutcome.killed` is what the caller reports it actually killed, which is
why the callable answers `bool` where the withdrawn one answered `None`.

**The module is split** (T3.3): `tools_projects_reads.py` holds the two reads,
the projections and the shared schema vocabulary, because the seventh verb does
not fit under the 450-line cap. Both halves are named on that cap's line.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from shepherd.core.clock import utc_now
from shepherd.signals.binding import probe_repo, repo_root, resolve_remote
from shepherd.store.db import Store
from shepherd.store.models import DeleteOutcome, OnRunning, StoreError
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.tools_m1 import project_workspace
from shepherd.toolsurface.tools_projects_reads import (
    PROJECT_ID,
    STRING,
    Clock,
    build_project_read_tools,
    object_schema,
    project_repo_row,
)
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolDef,
    arg_optional_str,
    arg_str,
)

__all__ = [
    "PROJECT_TOOL_NAMES",
    "KillSession",
    "add_repo",
    "build_project_tools",
    "create_project",
    "delete_project",
    "delete_outcome",
    "on_running_schema",
    "register_project_tools",
    "remove_repo",
    "rename_project",
]

#: Stop one session, and answer **whether the kill landed**.
#:
#: `bool`, not `None`: `DeleteOutcome.killed` is what the caller reports it
#: actually killed, and the shipped kill path answers `no_pane(session_id)` for
#: any session it has no runner handle for — which is every *attached* one. A
#: callable that cannot report failure makes "killed" a list of sessions that
#: may still be running.
KillSession = Callable[[str], bool]

#: Spelled here **and** in `tools_projects_reads.py`, rather than imported from
#: it. `tests/boundaries/test_session_audience.py` reads every `ToolDef`'s
#: audiences statically, resolving a bare name through that module's **own**
#: top-level bindings — it cannot follow an import, and a tool it cannot read is
#: reported as unread rather than passing quietly. A guard that reads both
#: halves is worth one repeated two-element literal.
MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})

#: The names `web/routes.py` resolves the Projects page's calls to, in the
#: plan's order. The constant lists what is registered rather than what was
#: planned, because a name in here that `registered_tools()` does not hold is a
#: promise a consumer can read and cannot call.
PROJECT_TOOL_NAMES: tuple[str, ...] = (
    "create_project",
    "rename_project",
    "delete_project",
    "add_repo",
    "remove_repo",
    "list_repos",
    "get_project",
)


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


def _refused(key: str, reason: str, absent: str) -> dict[str, object]:
    """The one negative shape: what did not happen, why, and a null in the slot
    the caller would have read on success."""
    return {key: False, absent: None, "refused": reason}


# ----- handlers ---------------------------------------------------------------


def create_project(store: Store, *, name: str, description: str | None) -> dict[str, object]:
    """A project, declared. **Never keyed by name** (E1) — `/work/api` and
    `/personal/api` are two projects, and the verb this replaced made them one
    row where the second registration overwrote the first."""
    created = store.create_project(name=name, description=description)
    return {
        "created": True,
        "project": project_workspace(created, repo_count=0, last_activity_at=None),
        "refused": None,
    }


def rename_project(store: Store, *, project_id: str, name: str) -> dict[str, object]:
    """A new label. Both negative answers become one record (see the module
    docstring): the reserved project raises and a missing one answers `None`."""
    try:
        renamed = store.rename_project(workspace_id=project_id, name=name)
    except StoreError as refusal:
        return _refused("renamed", str(refusal), "project")
    if renamed is None:
        return _refused(
            "renamed", f"there is no project {project_id!r} to rename", "project"
        )
    return {
        "renamed": True,
        "project": project_workspace(renamed, repo_count=0, last_activity_at=None),
        "refused": None,
    }


def delete_outcome(outcome: DeleteOutcome) -> dict[str, object]:
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
    }


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
        return delete_outcome(plan.refusal)
    killed = (
        tuple(session_id for session_id in plan.running if kill(session_id))
        if choice is OnRunning.KILL
        else ()
    )
    return delete_outcome(store.commit_project_delete(plan=plan, killed=killed))


def add_repo(store: Store, *, project_id: str, root_path: str) -> dict[str, object]:
    """Register a repo to a project — D22's *"adding a repo widens the
    allowlist"*, which is why the tool is `local_destructive`.

    Three things happen here that `store/` cannot do: the path is canonicalized
    (E10), git is probed for D48's binding key (E23), and the repo's **own
    root** is resolved — `repo_root`, the same helper `bind_cwd_to_repo` uses,
    so a person who types a subdirectory registers the tree rather than giving
    one `git_common_dir` two `repo` rows under `ux_repo_path`.

    The path is checked before the project is, so a typo in a path is reported
    as a path rather than as a missing project.
    """
    try:
        resolved = Path(root_path).expanduser().resolve(strict=True)
    except OSError:
        return _refused(
            "added", f"{root_path!r} is not a path that exists on this machine", "repo"
        )
    if not resolved.is_dir():
        return _refused("added", f"{root_path!r} is not a directory", "repo")

    probe = probe_repo(str(resolved))
    if probe.failure is not None or probe.git_common_dir is None:
        return _refused(
            "added",
            f"{root_path!r} is not a git repository, so it has no git-common-dir to "
            f"bind sessions on (D48); register the repository itself",
            "repo",
        )
    if probe.is_bare:
        return _refused(
            "added",
            f"{root_path!r} is a bare repository: it has no working tree, so no "
            f"session can run in it",
            "repo",
        )

    root = repo_root(str(resolved), probe.git_common_dir) or str(
        Path(probe.git_common_dir).parent
    )
    # A repo with no remote, or with several and no `origin`, is a normal thing
    # to register: the anomaly kind is `bind_cwd_to_repo`'s to count, because
    # there it explains a *binding* nobody asked for. Here a person asked.
    remote, _ = resolve_remote(str(resolved))
    try:
        registered = store.add_repo(
            workspace_id=project_id,
            root_path=root,
            name=Path(root).name or "local",
            git_common_dir=probe.git_common_dir,
            vcs_remote=remote,
        )
    except StoreError as refusal:
        return _refused("added", str(refusal), "repo")
    return {"added": True, "repo": project_repo_row(registered), "refused": None}


def remove_repo(store: Store, *, project_id: str, repo_id: str) -> dict[str, object]:
    """Drop the project↔repo edge. **The `repo` row is kept** — orphaned, not
    deleted — so re-adding the same path rebinds the same row (E6)."""
    return {"removed": store.remove_repo(workspace_id=project_id, repo_id=repo_id)}


# ----- the definitions --------------------------------------------------------


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


def build_project_tools(
    store: Store, kill: KillSession = refuses_every_kill, now: Clock = utc_now
) -> tuple[ToolDef, ...]:
    """The definitions, with the store and the kill closed over, so a consumer
    names a capability and never a dependency (D32)."""
    return (
        ToolDef(
            name="create_project",
            description="Declare a project (D22: a project is a workspace).",
            input_schema=object_schema({"name": STRING, "description": STRING}, ["name"]),
            # `local_destructive`, with `add_repo`, because a project is the
            # thing §13's allowlist is keyed by: creating one creates a scope
            # that repos can be added to.
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: create_project(
                store,
                name=arg_str(args, "name"),
                description=arg_optional_str(args, "description"),
            ),
            audiences=MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="rename_project",
            description="Relabel a project. Identity is the id; a name is a label (D57).",
            input_schema=object_schema(
                {PROJECT_ID: STRING, "name": STRING}, [PROJECT_ID, "name"]
            ),
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: rename_project(
                store,
                project_id=arg_str(args, PROJECT_ID),
                name=arg_str(args, "name"),
            ),
            audiences=MASTER_AND_HUMAN,
        ),
        ToolDef(
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
        ),
        ToolDef(
            name="add_repo",
            description="Register a repo to a project. Widens §13's spawn allowlist (D22).",
            input_schema=object_schema(
                {PROJECT_ID: STRING, "root_path": STRING}, [PROJECT_ID, "root_path"]
            ),
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: add_repo(
                store,
                project_id=arg_str(args, PROJECT_ID),
                root_path=arg_str(args, "root_path"),
            ),
            audiences=MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="remove_repo",
            description="Unregister a repo from a project. The repo row is kept (E6).",
            input_schema=object_schema(
                {PROJECT_ID: STRING, "repo_id": STRING}, [PROJECT_ID, "repo_id"]
            ),
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: remove_repo(
                store,
                project_id=arg_str(args, PROJECT_ID),
                repo_id=arg_str(args, "repo_id"),
            ),
            audiences=MASTER_AND_HUMAN,
        ),
        # The read half lives in `tools_projects_reads.py` (T3.3's split) and is
        # concatenated here, so the registration stays one loop over one tuple
        # and the split cannot lose a verb.
        *build_project_read_tools(store, now),
    )


def register_project_tools(*, store: Store, kill: KillSession, now: Clock = utc_now) -> None:
    """Register the lifecycle, before the composition root freezes the registry.

    `kill` is the plan's injection, and it arrives now that there is a verb that
    uses it. It is **never handed to a `store/` verb**: `delete_project` calls
    it between the two halves, on this thread, inside no transaction.

    **Required, with no default**, while `build_project_tools` has one. A
    process that registers this verb can be asked to kill, and the composition
    root is the only place that knows how; `refuses_every_kill` is a safe answer
    for a caller that only wants to read the schemas, and a silent one for a
    composition that forgot. Here mypy refuses the omission instead.
    """
    for tool in build_project_tools(store, kill, now):
        register(tool)
