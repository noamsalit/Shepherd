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

**`delete_project` is absent, and it is blocked rather than forgotten.**
`writes.delete_project` calls its injected `kill` from inside the lambda
`Store._write` runs on the single writer thread after `BEGIN IMMEDIATE`
(`writes.py:207`), while the shipped kill path's *first* statement is itself a
store write (`orchestration/lifecycle.py:126`) whose write-before-kill order is
what survives a crash. Handing that path in enqueues a job the blocked writer
can never reach, and the writer thread has no timeout: every later write in the
process hangs permanently. The verb needs the store-side split — decide, kill
outside the transaction, then commit — and is written up in
`docs/plans/projects-ui-blockers/t3-1.md`. `on_running_schema()` below is the
one piece that could be built without it, and it ships now so the split's
builder inherits the derivation rather than re-typing the three strings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from shepherd.core.clock import utc_now
from shepherd.signals.binding import probe_repo, repo_root, resolve_remote
from shepherd.store.db import Store
from shepherd.store.models import OnRunning, Repo, StoreError, Workspace
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.tools_m1 import fleet_buckets, project_session, project_workspace
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolDef,
    arg_optional_str,
    arg_str,
)

__all__ = [
    "PROJECT_TOOL_NAMES",
    "add_repo",
    "build_project_tools",
    "create_project",
    "get_project",
    "list_repos",
    "on_running_schema",
    "project_detail",
    "project_repo_row",
    "register_project_tools",
    "remove_repo",
    "rename_project",
]

Clock = Callable[[], str]

#: The names `web/routes.py` resolves the Projects page's calls to.
#:
#: **Six, not the plan's seven.** `delete_project` is blocked on the writer-thread
#: split; see this module's docstring. The constant lists what is registered
#: rather than what was planned, because a name in here that `registered_tools()`
#: does not hold is a promise a consumer can read and cannot call.
PROJECT_TOOL_NAMES: tuple[str, ...] = (
    "create_project",
    "rename_project",
    "add_repo",
    "remove_repo",
    "list_repos",
    "get_project",
)

_MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})

#: The one spelling of the project key on every consumer-facing surface (M1).
#: `project_workspace` already emits it and the route templates already use it;
#: the route gate checks `BODY_ARGS` and **never** path parameters, so a schema
#: that said `workspace_id` would pass every gate here and 400 at runtime.
_PROJECT_ID = "project_id"


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


# ----- projections (§13's explicit whitelist) --------------------------------


def project_repo_row(repo: Repo) -> dict[str, object]:
    """One registered repo, as the Projects page reads it.

    `git_common_dir` is on the wire deliberately: it is the key that decides
    which project a discovered session lands in, and a page that cannot show it
    cannot explain why a session bound where it did. `owner_id` is not — §13's
    whitelist keeps it inside the process.
    """
    return {
        "repo_id": repo.id,
        "name": repo.name,
        "root_path": repo.root_path,
        "git_common_dir": repo.git_common_dir,
        "vcs_remote": repo.vcs_remote,
        "active": repo.active,
        "added_at": repo.added_at,
    }


def project_detail(
    workspace: Workspace,
    repos: Sequence[Repo],
    sessions: Sequence[Mapping[str, object]],
    last_activity_at: str | None,
) -> dict[str, object]:
    """One project with everything its page draws, over `project_workspace`.

    The list projection is **reused rather than restated**, so the row on the
    Projects list and the header on its detail carry one key set and cannot
    disagree about a name. `repo_count` is `len(repos)` for the same reason:
    derived from the repos actually listed here, it is a count of this answer
    rather than a second read that can be one write behind it.

    `sessions` arrive already projected. The bucket in `project_session` is a
    read-time derivation over the liveness window (`signals.bucket_of`), and
    this function has no clock — so the handler, which does, computes them, and
    this stays a pure rearrangement of its arguments.
    """
    return project_workspace(
        workspace, repo_count=len(repos), last_activity_at=last_activity_at
    ) | {
        "repos": [project_repo_row(row) for row in repos],
        "sessions": list(sessions),
    }


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


def list_repos(store: Store, *, project_id: str) -> dict[str, object]:
    """§13's allowlist for one project, as a population a page can show."""
    return {"repos": [project_repo_row(row) for row in store.list_repos(project_id)]}


def get_project(store: Store, clock: Clock, *, project_id: str) -> dict[str, object]:
    """One project with its repos and its sessions.

    A project that is not there is a **value** (principle 5): `found=False` is a
    field the page renders as "no such project", and an exception is not
    something a card can draw.
    """
    found = store.get_workspace(project_id)
    if found is None:
        return {"found": False, "project": None}
    repos = store.list_repos(project_id)
    buckets = fleet_buckets(store, clock())
    sessions = [
        project_session(row, bucket=buckets.get(row.id))
        for row in store.list_sessions(workspace_id=project_id)
    ]
    return {
        "found": True,
        "project": project_detail(
            found, repos, sessions, store.project_last_activity().get(project_id)
        ),
    }


# ----- the definitions --------------------------------------------------------


def _object(properties: Mapping[str, object], required: Sequence[str]) -> Mapping[str, object]:
    return {"type": "object", "properties": dict(properties), "required": list(required)}


_STRING: Mapping[str, object] = {"type": "string"}


def build_project_tools(store: Store, now: Clock = utc_now) -> tuple[ToolDef, ...]:
    """The definitions, with the store closed over, so a consumer names a
    capability and never a dependency (D32)."""
    return (
        ToolDef(
            name="create_project",
            description="Declare a project (D22: a project is a workspace).",
            input_schema=_object({"name": _STRING, "description": _STRING}, ["name"]),
            # `local_destructive`, with `add_repo`, because a project is the
            # thing §13's allowlist is keyed by: creating one creates a scope
            # that repos can be added to.
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: create_project(
                store,
                name=arg_str(args, "name"),
                description=arg_optional_str(args, "description"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="rename_project",
            description="Relabel a project. Identity is the id; a name is a label (D57).",
            input_schema=_object(
                {_PROJECT_ID: _STRING, "name": _STRING}, [_PROJECT_ID, "name"]
            ),
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: rename_project(
                store,
                project_id=arg_str(args, _PROJECT_ID),
                name=arg_str(args, "name"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="add_repo",
            description="Register a repo to a project. Widens §13's spawn allowlist (D22).",
            input_schema=_object(
                {_PROJECT_ID: _STRING, "root_path": _STRING}, [_PROJECT_ID, "root_path"]
            ),
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: add_repo(
                store,
                project_id=arg_str(args, _PROJECT_ID),
                root_path=arg_str(args, "root_path"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="remove_repo",
            description="Unregister a repo from a project. The repo row is kept (E6).",
            input_schema=_object(
                {_PROJECT_ID: _STRING, "repo_id": _STRING}, [_PROJECT_ID, "repo_id"]
            ),
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: remove_repo(
                store,
                project_id=arg_str(args, _PROJECT_ID),
                repo_id=arg_str(args, "repo_id"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="list_repos",
            description="The repos registered to one project — §13's allowlist.",
            input_schema=_object({_PROJECT_ID: _STRING}, [_PROJECT_ID]),
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_repos(
                store, project_id=arg_str(args, _PROJECT_ID)
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="get_project",
            description="One project with its repos and its sessions.",
            input_schema=_object({_PROJECT_ID: _STRING}, [_PROJECT_ID]),
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: get_project(
                store, now, project_id=arg_str(args, _PROJECT_ID)
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
    )


def register_project_tools(*, store: Store, now: Clock = utc_now) -> None:
    """Register the lifecycle, before the composition root freezes the registry.

    **No `kill` injection yet.** The plan's signature takes one, for
    `delete_project`; supplying the shipped kill path to `writes.delete_project`
    deadlocks the store's writer thread (see the module docstring), so the
    parameter arrives with the verb rather than ahead of it. An injected
    dependency with no consumer is a dependency nobody can check.
    """
    for tool in build_project_tools(store, now):
        register(tool)
