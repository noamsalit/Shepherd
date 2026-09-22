"""The read half of D57's project lifecycle, and the vocabulary both halves share.

**A split, not a new module** (T3.3). `tools_projects.py` shipped at 408 lines
against the 450-line cap that `test_every_tool_module_is_under_the_cap`
holds it to, and the seventh verb — `delete_project`, with D61's three-way
choice and its four projected outcome fields — does not fit under it. The plan
authorises exactly this split, and **both halves are named on that line**,
because a split that escapes the enumeration is a split that hides the growth
the cap exists to expose.

**Why the cut is here.** The two read verbs and the projections they produce are
the half with no store write, no subprocess and no refusal record: `list_repos`
and `get_project` answer with a population and a value, and `project_repo_row` /
`project_detail` are pure rearrangements of their arguments. That leaves the
other half holding exactly the verbs that change something.

This module is the **lower** of the two: `tools_projects.py` imports from it and
it imports nothing back, so the cut cannot become a cycle. The shared schema
vocabulary (`PROJECT_ID`, `STRING`, `object_schema`, `MASTER_AND_HUMAN`) lives
here for that reason — spelled once, in the half that does not depend on the
other.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from shepherd.store.db import Store
from shepherd.store.models import Repo, Workspace
from shepherd.toolsurface.tools_m1 import fleet_buckets, project_session, project_workspace
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef, arg_str

__all__ = [
    "MASTER_AND_HUMAN",
    "PROJECT_ID",
    "STRING",
    "Clock",
    "build_project_read_tools",
    "get_project",
    "list_repos",
    "object_schema",
    "project_detail",
    "project_repo_row",
]

Clock = Callable[[], str]

#: Spelled here **and** in `tools_projects.py`, rather than in one of them and
#: imported by the other. `tests/boundaries/test_session_audience.py` resolves a
#: `ToolDef`'s `audiences=` through the defining module's own top-level
#: bindings: it cannot follow an import, and it reports a tool it cannot read as
#: *unread* rather than letting it pass. One repeated two-element literal is the
#: price of both halves staying readable to that guard.
MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})

#: The one spelling of the project key on every consumer-facing surface (M1).
#: `project_workspace` already emits it and the route templates already use it;
#: the route gate checks `BODY_ARGS` alone and **never** path parameters, so a
#: schema that said `workspace_id` would pass every gate here and 400 at runtime.
PROJECT_ID = "project_id"

STRING: Mapping[str, object] = {"type": "string"}


def object_schema(
    properties: Mapping[str, object], required: Sequence[str]
) -> Mapping[str, object]:
    return {"type": "object", "properties": dict(properties), "required": list(required)}


# ----- projections (§13's explicit whitelist) --------------------------------


def project_repo_row(repo: Repo, projects: Sequence[str] = ()) -> dict[str, object]:
    """One registered repo, as the Projects page reads it.

    `git_common_dir` is on the wire deliberately: it is the key that decides
    which project a discovered session lands in, and a page that cannot show it
    cannot explain why a session bound where it did. `owner_id` is not — §13's
    whitelist keeps it inside the process.

    **`projects` is D60 made readable.** The row says *"a repo path may belong
    to more than one project"* and no answer on the wire said which, so the page
    could not show it at all. It carries **every** holder, this project
    included: "shared with" is the page's word for the rest of the list, and a
    projection that pre-subtracted the current project would make one list mean
    two things in two places. The caller reads the whole map once
    (`store.projects_by_repo()`) rather than asking per row, which is the N+1
    these projections exist to avoid.
    """
    return {
        "repo_id": repo.id,
        "name": repo.name,
        "root_path": repo.root_path,
        "git_common_dir": repo.git_common_dir,
        "vcs_remote": repo.vcs_remote,
        "active": repo.active,
        "added_at": repo.added_at,
        "projects": list(projects),
    }


def project_detail(
    workspace: Workspace,
    repos: Sequence[Repo],
    sessions: Sequence[Mapping[str, object]],
    last_activity_at: str | None,
    holders: Mapping[str, Sequence[str]] | None = None,
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
        "repos": [
            project_repo_row(row, () if holders is None else holders.get(row.id, ()))
            for row in repos
        ],
        "sessions": list(sessions),
    }


# ----- handlers ---------------------------------------------------------------


def list_repos(store: Store, *, project_id: str) -> dict[str, object]:
    """§13's allowlist for one project, as a population a page can show.

    The holders map is read **once** for the whole list (D60); asking per repo
    is the N+1 the projections were shaped to avoid.
    """
    holders = store.projects_by_repo()
    return {
        "repos": [
            project_repo_row(row, holders.get(row.id, ()))
            for row in store.list_repos(project_id)
        ]
    }


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
            found,
            repos,
            sessions,
            store.project_last_activity().get(project_id),
            store.projects_by_repo(),
        ),
    }


def build_project_read_tools(store: Store, now: Clock) -> tuple[ToolDef, ...]:
    """The two `local_read` definitions, with the store closed over — the same
    shape `build_project_tools` returns, so the registration stays one loop
    over one tuple and a split cannot lose a verb."""
    return (
        ToolDef(
            name="list_repos",
            description="The repos registered to one project — §13's allowlist.",
            input_schema=object_schema({PROJECT_ID: STRING}, [PROJECT_ID]),
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: list_repos(store, project_id=arg_str(args, PROJECT_ID)),
            audiences=MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="get_project",
            description="One project with its repos and its sessions.",
            input_schema=object_schema({PROJECT_ID: STRING}, [PROJECT_ID]),
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: get_project(
                store, now, project_id=arg_str(args, PROJECT_ID)
            ),
            audiences=MASTER_AND_HUMAN,
        ),
    )
