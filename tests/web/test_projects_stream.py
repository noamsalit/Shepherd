"""D7 (QA run 4): a project mutation reaches a **second client**, or it did not happen.

**The seam is the wire, not the function.** QA run 4 enumerated all sixteen
`POST_ROUTES` first, drove the six project mutations against a live server, and
counted the `/api/events` frames a second client received: six 200s and **zero
frames**, with a `publish()` probe on the same reader proving the reader was not
blind. The consumer had been waiting the whole time — `app.js`'s `refreshAll()`
re-reads the tree on *any* envelope and says so in a comment — so the missing
half was the producer, and a test at the handler's return value would never have
found it.

So every assertion here goes through `web.conftest.Client`: a real socket to the
real handler for the POST, and a second real socket reading `/api/events` with
`Last-Event-ID: 0` for the frames. That header is what makes the reader a second
*client* rather than a second thread — `sse.stream` replays the ring's backlog
after the cursor, so the frames counted here are the frames a tab that connected
a moment earlier would have been handed.

**The probe that keeps a zero honest** (run 4's own discipline, kept):
`test_the_reader_is_not_blind` publishes one event directly into the ring and
reads it back over the same path, so a `0` anywhere else in this file is a real
`0` and not a reader that never worked.

**`set_autonomy_level` is deliberately not here.** It is run 4's seventh silent
mutation and it lives in `tools_master.py`, which this remediation's file set
does not contain; it is recorded as still-silent in
`docs/plans/projects-ui-blockers/qa-remfix-4-lane-b.md` rather than fixed
quietly or left unsaid.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from signals.conftest import git_env
from web.conftest import Client

from shepherd.core.stream import StreamEvent
from shepherd.store.db import Store
from shepherd.toolsurface.stream import publish

#: The six mutations the Projects page issues, in `POST_ROUTES` order. Spelled
#: out rather than read off the table under test: a list derived from the thing
#: being checked agrees with it whatever it says.
MUTATIONS = (
    "create_project",
    "rename_project",
    "set_project_description",
    "delete_project",
    "add_repo",
    "remove_repo",
)


def _frames(client: Client, count: int) -> list[dict[str, str]]:
    """What a second tab holding `/api/events` open has been handed so far."""
    return client.frames(
        "/api/events", count=count, headers={"Last-Event-ID": "0"}, read_timeout=5.0
    )


def _types(client: Client, count: int) -> list[str]:
    import json

    return [str(json.loads(frame["data"])["type"]) for frame in _frames(client, count)]


def _project_ids(client: Client, count: int) -> list[str | None]:
    import json

    out: list[str | None] = []
    for frame in _frames(client, count):
        body = json.loads(frame["data"])
        value = body["project_id"]
        out.append(str(value) if isinstance(value, str) else None)
    return out


def _made(client: Client, name: str = "payments") -> str:
    response = client.post("/api/projects", {"name": name})
    assert response.status == 200, response.body
    data = response.json()["data"]
    assert isinstance(data, dict)
    project = data["project"]
    assert isinstance(project, dict)
    return str(project["project_id"])


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=root,
        env=git_env(),
        capture_output=True,
        check=True,
    )
    return root


def test_the_reader_is_not_blind(client: Client) -> None:
    """Run 4's probe, kept as a test: a `0` below must be a real `0`.

    Without this, every assertion in this file could be satisfied by a reader
    that never receives anything at all — which is precisely the observation
    error the verification discipline says to suspect before the system.
    """
    publish(
        StreamEvent(
            kind="qa4.probe",
            session_id=None,
            payload={"n": 1},
            occurred_at="2026-09-16T10:00:30Z",
        )
    )
    assert _types(client, 1) == ["qa4.probe"]


def test_creating_a_project_tells_a_second_client(client: Client) -> None:
    _made(client)
    assert _types(client, 1) == ["project.created"]


def test_renaming_a_project_tells_a_second_client(client: Client) -> None:
    project_id = _made(client)
    assert client.post(f"/api/projects/{project_id}/rename", {"name": "ledger"}).status == 200
    assert _types(client, 2)[1] == "project.renamed"


def test_describing_a_project_tells_a_second_client(client: Client) -> None:
    project_id = _made(client)
    posted = client.post(f"/api/projects/{project_id}/description", {"description": "api"})
    assert posted.status == 200
    assert _types(client, 2)[1] == "project.described"


def test_deleting_a_project_tells_a_second_client(client: Client) -> None:
    """Run 4's user-visible case: tab B deletes, tab A is still listing it."""
    project_id = _made(client)
    deleted = client.post(f"/api/projects/{project_id}/delete", {})
    assert deleted.status == 200
    data = deleted.json()["data"]
    assert isinstance(data, dict) and data["deleted"] is True, data
    assert _types(client, 2)[1] == "project.deleted"


def test_adding_and_removing_a_repo_tells_a_second_client(
    client: Client, store: Store, tmp_path: Path
) -> None:
    project_id = _made(client)
    tree = _repo(tmp_path / "tree")
    added = client.post(f"/api/projects/{project_id}/repos/add", {"root_path": str(tree)})
    assert added.status == 200
    data = added.json()["data"]
    assert isinstance(data, dict) and data["added"] is True, data
    repo = data["repo"]
    assert isinstance(repo, dict)
    removed = client.post(
        f"/api/projects/{project_id}/repos/remove", {"repo_id": str(repo["repo_id"])}
    )
    assert removed.status == 200
    assert _types(client, 3)[1:] == ["project.repo_added", "project.repo_removed"]


def test_every_project_frame_names_the_project_it_is_about(client: Client) -> None:
    """§12 promotes `project_id` out of the payload into the envelope.

    A refresh-everything consumer does not need it today; a frame that cannot
    say which project changed is one that can never be narrowed later, and the
    envelope already has the slot.
    """
    project_id = _made(client)
    assert client.post(f"/api/projects/{project_id}/rename", {"name": "ledger"}).status == 200
    assert _project_ids(client, 2) == [project_id, project_id]


def test_a_refused_mutation_tells_nobody(client: Client) -> None:
    """Nothing changed, so there is nothing to announce.

    The counter-case matters as much as the six: a producer that fires on every
    call teaches the page that an envelope means a change, and then the first
    thing a stale tab does with a refusal is re-read a tree that is identical.
    """
    refused = client.post("/api/projects/01MISSING/rename", {"name": "ledger"})
    assert refused.status == 200
    data = refused.json()["data"]
    assert isinstance(data, dict) and data["renamed"] is False, data
    # One frame is asked for and the reader waits `read_timeout` for it: the
    # assertion is that none arrives, so this cannot pass by reading too early.
    assert _types(client, 1) == []


@pytest.mark.parametrize("tool", MUTATIONS)
def test_every_project_mutation_is_covered_by_a_test_above(tool: str) -> None:
    """The closed list: a seventh mutation added to the family without a frame
    fails here rather than being discovered by a second QA run."""
    from shepherd.web import routes

    named = {
        name
        for template, name in routes.POST_ROUTES.items()
        if template.startswith("/api/projects")
    }
    assert tool in named
    assert named == set(MUTATIONS)
