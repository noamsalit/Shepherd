"""§5's seed — `n > 1` everywhere, and every element earns its place.

**This is the most load-bearing module in the harness.** Nine of eleven round-1
defects were invisible at `n = 1`: every prior fixture seeded one project and at
most two sessions, **all attached**, so `DeletePlan.killable` was empty in every
test that ever read it, no two projects shared a name, and no path was long
enough to ellipsise.

**Two seams, and the difference is declared rather than blurred.** P1-P7, their
repos and their descriptions are built through the product's **own front door**
(`POST /api/projects`, `…/repos/add`) — a fixture written straight into the
datastore can encode a state the application cannot produce, and then the suite
tests fiction. The **sessions** are seeded through `Store` verbs, because the
only front door that creates one is `spawn_session`, which starts a real
`claude` process and is forbidden in this workflow. That is a real reduction in
fidelity and it earns a known-gap row: a store-seeded owned session *looks*
owned to every reader, and what it does not prove is that the spawn path
produces that shape.

**Timestamps sit ≥2× from every relative-time boundary.** `app.js:115` calls
`Date.now()` directly in `drawFlock`, so the page-level clock is not injectable
in a browser run; a run that takes ten minutes must not be able to walk a seeded
value across a bucket edge. 400 days, 40 days, 40 hours, 40 minutes. The
"just now" (<60 s) class is asserted at the API seam only.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Origin, Ownership
from shepherd.core.stops import Bucket, DecidedBy, StopReason, Verdict
from shepherd.store.db import Store

from .constants import PANES, QA_SOCKET
from .runroot import HarnessBlocked
from .wire import PROJECT_KEY, Client

#: A fixed base instant so two runs seed the same shape. Every offset below is
#: derived from it; nothing reads the wall clock.
BASE = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)

#: The four offsets, each ≥2× from the nearest bucket edge of the relative-time
#: scale. Named so a scenario can say *which* class it is reading.
AGES: dict[str, timedelta] = {
    "ancient": timedelta(days=400),
    "old": timedelta(days=40),
    "recent": timedelta(hours=40),
    "fresh": timedelta(minutes=40),
}

#: P3's repo lives ~12 levels down so its rendered path is long enough to
#: ellipsise. The depth is what makes the `title`-attribute class reachable.
DEEP = "/".join(f"lvl{index:02d}" for index in range(12))


def _at(age: str) -> str:
    return (BASE - AGES[age]).isoformat().replace("+00:00", "Z")


@dataclass
class Seeded:
    """Every id the scenarios name, bound once here."""

    projects: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    repos: dict[str, str] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)

    def project(self, label: str) -> str:
        return self.projects[label]

    def session(self, label: str) -> str:
        return self.sessions[label]


def git_repo(root: Path) -> Path:
    """A real repository on disk. `add_repo` shells out to `git` via
    `probe_repo` with **no stub seam**, so every `add_repo` row needs one."""
    root.mkdir(parents=True, exist_ok=True)
    env = {
        "GIT_AUTHOR_NAME": "qa5",
        "GIT_AUTHOR_EMAIL": "qa5@example.invalid",
        "GIT_COMMITTER_NAME": "qa5",
        "GIT_COMMITTER_EMAIL": "qa5@example.invalid",
        "HOME": str(root),
        "PATH": "/usr/bin:/bin",
    }
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "commit", "-q", "--allow-empty", "-m", "seed"],
    ):
        done = subprocess.run(
            argv, cwd=root, capture_output=True, text=True, env=env, timeout=60, check=False
        )
        if done.returncode != 0:
            raise HarnessBlocked(f"{argv!r} in {root} exited {done.returncode}: {done.stderr!r}")
    return root


def _register(
    store: Store,
    *,
    workspace_id: str,
    engine_session_id: str,
    cwd: Path,
    age: str,
    ownership: Ownership,
) -> str:
    session = store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=workspace_id,
        repo_id=None,
        cwd=str(cwd),
        started_at=_at(age),
        origin=Origin.USER_UI,
        ownership=ownership,
    )
    return session.id


_FINISHED = Verdict(
    stop_reason=StopReason.COMPLETED,
    bucket=Bucket.FINISHED,
    why="seeded finished by the round-5 harness",
    confidence=1.0,
    decided_by=DecidedBy.DECLARED,
    next_actions=(),
    waiting_on=None,
    missing=(),
)


def _finish(store: Store, session_id: str, age: str) -> None:
    store.apply_stop_verdict(session_id, _FINISHED, _at(age), 0)


def seed_world(client: Client, store: Store, work: Path, repo_root: Path) -> Seeded:
    """§5's table, in order. Front door for projects, `Store` for sessions."""
    seeded = Seeded()

    # ----- the fixtures on disk (R1, R2, R3) -------------------------------
    # **R1 is not one of P1's two.** §5 lists R1 as the `add_repo` happy-path
    # fixture and P1 as "2 repos"; seeding R1 *into* P1 makes S32's "add R1's
    # path" a duplicate that `add_repo` refuses, and the draft list never grows
    # — a fixture collision that reads as a page defect.
    r1 = git_repo(repo_root / "plain")
    p1_first = git_repo(repo_root / "p1-first")
    notgit = work / "notgit"
    notgit.mkdir(parents=True, exist_ok=True)
    afile = work / "afile"
    afile.write_text("R3 — a regular file, the non-directory fixture\n", encoding="utf-8")
    deep = git_repo(repo_root / DEEP)
    p1_second = git_repo(repo_root / "p1-second")
    seeded.paths |= {
        "R1": r1,
        "R2": notgit,
        "R3": afile,
        "DEEP": deep,
        "P1_FIRST": p1_first,
        "P1_SECOND": p1_second,
    }

    # ----- P0: the reserved workspace, seeded by migration 004 -------------
    existing = client.projects()
    if len(existing) != 1 or existing[0].get(PROJECT_KEY) != "unassigned":
        raise HarnessBlocked(
            f"a fresh database must hold exactly the reserved workspace; found {existing!r}"
        )
    seeded.projects["P0"] = "unassigned"

    # ----- P1..P7, through the front door ----------------------------------
    def create(label: str, name: str, description: str | None = None) -> str:
        answer = client.create_project(name, description)
        project = answer.get("project")
        if not isinstance(project, dict):
            raise HarnessBlocked(f"create_project({name!r}) answered no project: {answer!r}")
        seeded.projects[label] = str(project[PROJECT_KEY])
        return str(project[PROJECT_KEY])

    p1 = create(
        "P1",
        "Shepherd",
        "The ordinary project: two repositories and a description long enough that the "
        "detail pane has something to lay out, so an n=1 fixture's blank card cannot "
        "stand in for a populated one.",
    )
    # P2 shares P1's name. **Exactly one POST** — `duplicate.armed` is page
    # memory (`projects.js:620`), reset on every dialog open (`:547`), and
    # `store.create_project` is a bare INSERT with no name check. A fixture that
    # "arms and then creates" issues two POSTs and makes two extra workspaces,
    # which breaks S2's eight-rows rollup.
    create("P2", "Shepherd")
    p3 = create("P3", "Flock")
    create("P4", "Doomed")
    create("P5", "Attached-only")
    p6 = create("P6", "Orphan-subject")
    create("P7", "Stale-handle")

    for path in (p1_first, p1_second):
        added = client.add_repo(p1, str(path))
        if added.get("added") is not True:
            raise HarnessBlocked(f"seeding P1's repo {path} failed: {added!r}")
    added = client.add_repo(p3, str(deep))
    if added.get("added") is not True:
        raise HarnessBlocked(f"seeding P3's deep repo failed: {added!r}")

    # ----- the sessions, through `Store` verbs -----------------------------
    handles = {
        "S-own-1": ("P4", PANES[0], "recent"),
        "S-own-2": ("P1", PANES[1], "recent"),
        "S-own-4": ("P7", PANES[2], "recent"),
        "S-own-3": ("P6", PANES[3], "recent"),
    }
    for label, (project_label, pane, age) in handles.items():
        session_id = _register(
            store,
            workspace_id=seeded.project(project_label),
            engine_session_id=f"qa5-{label}",
            cwd=work,
            age=age,
            ownership=Ownership.OWNED,
        )
        store.set_runner_handle(
            session_id, RunnerHandle(runner="local", socket=QA_SOCKET, session_name=pane)
        )
        seeded.sessions[label] = session_id

    attached = {
        "S-att-1": ("P4", "old"),
        "S-att-2": ("P1", "ancient"),
        "S-att-3": ("P1", "old"),
        "S-att-4": ("P3", "fresh"),
        "S-att-5": ("P5", "recent"),
        "S-att-6": ("P5", "old"),
        "S-att-7": ("P6", "fresh"),
    }
    for label, (project_label, age) in attached.items():
        seeded.sessions[label] = _register(
            store,
            workspace_id=seeded.project(project_label),
            engine_session_id=f"qa5-{label}",
            cwd=work,
            age=age,
            ownership=Ownership.ATTACHED,
        )

    finished = {
        "S-fin-1": "P4",
        "S-fin-2": "P4",
        "S-fin-3": "P4",
        "S-fin-4": "P6",
        "S-fin-5": "P6",
        "S-fin-6": "P6",
    }
    for label, project_label in finished.items():
        session_id = _register(
            store,
            workspace_id=seeded.project(project_label),
            engine_session_id=f"qa5-{label}",
            cwd=work,
            age="ancient",
            ownership=Ownership.ATTACHED,
        )
        _finish(store, session_id, "old")
        seeded.sessions[label] = session_id

    # ----- the cross-project lineage link (S13's `severed`) ----------------
    # **Without this the `severed` list is empty in every run and S13's shape
    # assertion over it cannot execute at all.** `_sever_lineage` only emits a
    # `SeveredLink` for a session in *another* workspace whose lineage column
    # points into the deleted one, and nothing here ever set a lineage column —
    # so the loop body was unreachable and the scenario was asserting a shape
    # over a collection that could not be populated.
    #
    # The pair is the reachable case `_sever_lineage`'s own docstring names: *"a
    # spawned child still running while its parent has stopped"*, across a
    # project boundary. `S-att-4` runs in P3; `S-fin-4` has stopped in P6. When
    # S13 orphans P6, P6's *running* rows are moved to Unassigned first, so the
    # parent that is still inside the doomed cohort when `_sever_lineage` runs
    # has to be a finished one — which is exactly what this links to.
    #
    # **`link_retry` is the product's only writer of a lineage column** and it
    # refuses a self-link, an unknown id and a loop, so the fixture cannot write
    # a shape the application could not produce. No row is added: seeding a new
    # session would move counts that four other scenarios assert on.
    store.link_retry(seeded.sessions["S-att-4"], seeded.sessions["S-fin-4"])

    assert_seeded(client, store, seeded, p1=p1, p3=p3, p6=p6)
    return seeded


def assert_seeded(
    client: Client, store: Store, seeded: Seeded, *, p1: str, p3: str, p6: str
) -> None:
    """The seed's own assertions (§5). A seed that did not land is `BLOCKED`.

    Arrival before use: every scenario's `Preconditions: as §1` inherits this,
    and a seed nobody checked is how `killable` was empty in four rounds.
    """
    rows = client.projects()
    if len(rows) != 8:
        raise HarnessBlocked(f"expected eight workspaces after the seed, found {len(rows)}")
    shepherds = [row for row in rows if row.get("name") == "Shepherd"]
    if len(shepherds) != 2:
        raise HarnessBlocked(f"two workspaces must share the name 'Shepherd'; found {len(shepherds)}")

    counts = store.repo_counts()
    if counts.get(p1) != 2 or counts.get(p3) != 1:
        raise HarnessBlocked(f"repo counts did not land: P1={counts.get(p1)}, P3={counts.get(p3)}")

    running_p4 = store.running_sessions_for(seeded.project("P4"))
    if len(running_p4) != 2:
        raise HarnessBlocked(f"P4 must hold exactly two running sessions; found {len(running_p4)}")
    with_handle = [row for row in running_p4 if row.runner_handle is not None]
    if len(with_handle) != 1:
        raise HarnessBlocked(
            f"exactly one of P4's running sessions must carry a handle; found {len(with_handle)}"
        )

    running_p5 = store.running_sessions_for(seeded.project("P5"))
    if len(running_p5) != 2 or any(row.runner_handle is not None for row in running_p5):
        raise HarnessBlocked("P5 must be attached-only: two running sessions, no handle on either")

    running_p6 = store.running_sessions_for(p6)
    if len(running_p6) != 2:
        raise HarnessBlocked(f"P6 must hold two running sessions; found {len(running_p6)}")

    # The lineage link arrived, and it really does cross a project boundary and
    # point at a **finished** row. S13's `severed` assertion is unreachable
    # without all three of those, and an unreachable assertion that prints green
    # is the failure this seed check exists to prevent.
    child = store.get_session(seeded.session("S-att-4"))
    parent = store.get_session(seeded.session("S-fin-4"))
    if child is None or parent is None:
        raise HarnessBlocked("the lineage pair did not survive seeding")
    if child.retry_of != parent.id:
        raise HarnessBlocked(
            f"S-att-4.retry_of is {child.retry_of!r}, not S-fin-4 ({parent.id!r}); "
            "S13's severed-link assertion would be vacuous"
        )
    if child.workspace_id == parent.workspace_id:
        raise HarnessBlocked(
            "the lineage pair must cross a project boundary; _sever_lineage only "
            f"reports a referrer OUTSIDE the doomed cohort (both are in "
            f"{child.workspace_id!r})"
        )
    if parent.ended_at is None:
        raise HarnessBlocked(
            "the lineage parent must have STOPPED: under ORPHAN the running rows "
            "leave the cohort before _sever_lineage runs, so a running parent "
            "would be severed from nothing"
        )
