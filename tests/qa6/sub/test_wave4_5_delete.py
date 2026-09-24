"""Wave 4, SUB lane: P7 and P8 — the project deletes that need an owned pane (moved here at r3).

One instance. P7(a) and P8 use owned shim sessions spawned into their own
projects' repos; P7(b) uses a D1-shaped attached session whose cwd is inside a
repo registered **only** to its project (so the binding is that project, not
Unassigned — P5's shared-repo rule). Every "no frame" clause is read against the
SSE liveness control.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from ..httpclient import as_dict, as_list
from ..instance import db_rows
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import run_control
from ..verdict import Recorder, observe
from .test_wave4_0_support import (
    Owned,
    attached,
    end_attached,
    kill,
    open_owned,
    owned_panes,
    pane_alive,
    post_json,
    session_db_row,
    spawn_ok,
)


@pytest.fixture(scope="module")
def pdel(pool: InstancePool, qa6_run: RunContext) -> Iterator[Owned]:
    env = open_owned(pool, qa6_run, "P78")
    try:
        yield env
    finally:
        env.stream.close()


def new_project(env: Owned, name: str, repo: str) -> str:
    project_id = str(as_dict(env.client.create_project(name).get("project")).get("project_id"))
    added = env.client.add_repo(project_id, os.path.realpath(env.run.repos / repo))
    if added.get("added") is not True:
        raise AssertionError(f"given: add_repo({repo}) to {name} did not land: {added!r}")
    return project_id


def delete(env: Owned, project_id: str, on_running: str | None = None) -> tuple[int, dict[str, object]]:
    body: dict[str, object] = {} if on_running is None else {"on_running": on_running}
    answer = post_json(env.client, f"/api/projects/{project_id}/delete", body)
    return answer.status, (answer.data() if answer.status == 200 else {})


def delete_rows(env: Owned, mark: int, *project_ids: str) -> list[dict[str, object]]:
    """`delete_project` audit rows for these projects only (the SSE control deletes one of its own)."""
    return [dict(r) for r in env.audit.records_for(mark, "delete_project")
            if as_dict(r.get("args")).get("project_id") in project_ids]


def workspace_exists(env: Owned, project_id: str) -> bool:
    return bool(db_rows(env.controld.db, "SELECT id FROM workspace WHERE id = ?", (project_id,)))


@scenario("P7")
def test_p7_running_sessions_refuse_the_delete_kill_sessions_resolves_owned_not_attached(pdel: Owned, rec: Recorder) -> None:
    env = pdel
    owned_project = new_project(env, "QA6-P7a", "beta")
    sid = spawn_ok(env, "QA6 P7a", workspace_id=owned_project, cwd=os.path.realpath(env.run.repos / "beta"))
    mark, amark = env.stream.mark(), env.audit.mark()
    status, first = delete(env, owned_project)
    rec.check("api.a_first_refused_running", status == 200 and first.get("deleted") is False and bool(first.get("refused"))
              and first.get("running") == [sid] and sid in as_list(first.get("killable")),
              f"200 {{deleted:false, refused, running:[{sid}]}}, the session killable", (status, first))
    status, second = delete(env, owned_project, "kill_sessions")
    rec.check("api.a_kill_sessions_deleted", status == 200 and second.get("deleted") is True
              and second.get("kill_failures") == [], "200 {deleted:true, kill_failures:[]}", (status, second))
    gone, _ = observe(lambda: (not pane_alive(env, sid)) or None, 5.0)
    rec.check("tmux.a_pane_gone", bool(gone), "the pane is gone", owned_panes(env))
    rec.equal("db.a_project_gone", False, workspace_exists(env, owned_project))
    kinds = [f.kind for f in env.stream.since(mark)
             if (f.kind == "session.killed" and f.session_id == sid) or (f.kind == "project.deleted" and f.project_id == owned_project)]
    rec.equal("stream.a_killed_then_deleted", ["session.killed", "project.deleted"], kinds)

    attached_project = new_project(env, "QA6-P7b", "my repo")
    other = attached(env, env.run.repos / "my repo", "QA6 P7b attached")
    rec.check("given.b_bound_to_its_project", (session_db_row(env, other.session_id) or {}).get("workspace_id")
              == attached_project, f"the attached session is bound to {attached_project}",
              (session_db_row(env, other.session_id) or {}).get("workspace_id"))
    mark_b = env.stream.mark()
    try:
        answers = [delete(env, attached_project), delete(env, attached_project, "kill_sessions")]
        for label, (status, data) in zip(("default", "kill_sessions"), answers, strict=True):
            rec.check(f"api.b_{label}_refused", status == 200 and data.get("deleted") is False and bool(data.get("refused")),
                      "200 {deleted:false, refused}", (status, data))
        rec.check("db.b_project_and_session_intact", workspace_exists(env, attached_project)
                  and (session_db_row(env, other.session_id) or {}).get("ended_at") is None,
                  "the project and the running attached session are intact",
                  (workspace_exists(env, attached_project), session_db_row(env, other.session_id)))
        control = run_control(env.stream, env.client, "P7b", mark_b)
        rec.equal("stream.b_no_project_deleted", [],
                  [f.kind for f in control.interior if f.kind == "project.deleted" and f.project_id == attached_project])
        rec.equal("logs.a_row_per_call", 4, len(delete_rows(env, amark, owned_project, attached_project)))
    finally:
        end_attached(env, other)
    stopped, _ = observe(lambda: (session_db_row(env, other.session_id) or {}).get("ended_at") or None, 8.0)
    status, cleanup = delete(env, attached_project)
    rec.check("cleanup.b_deleted_after_the_helper_stopped", bool(stopped) and cleanup.get("deleted") is True,
              "the helper stopped and (b) deletes", (stopped, status, cleanup))
    rec.finish()


@scenario("P8")
def test_p8_orphan_moves_running_sessions_to_unassigned(pdel: Owned, rec: Recorder) -> None:
    env = pdel
    project = new_project(env, "QA6-P8", "beta")
    sid = spawn_ok(env, "QA6 P8", workspace_id=project, cwd=os.path.realpath(env.run.repos / "beta"))
    mark, amark = env.stream.mark(), env.audit.mark()
    status, data = delete(env, project, "orphan")
    rec.check("api.deleted", status == 200 and data.get("deleted") is True and sid in as_list(data.get("orphaned")),
              "200 {deleted:true} with the session orphaned", (status, data))
    placed, row_state = None, None
    for workspace in as_list(env.client.fleet_tree().get("workspaces")):
        entry = as_dict(workspace)
        for session in as_list(entry.get("sessions")):
            if as_dict(session).get("session_id") == sid:
                placed, row_state = entry.get("project_id"), as_dict(session).get("state")
    rec.check("api.tree_under_unassigned_still_running", placed == "unassigned" and row_state not in (None, "stopped"),
              "fleet_tree shows it under Unassigned, not stopped", (placed, row_state))
    rec.check("tmux.pane_alive", pane_alive(env, sid), "the pane is alive", owned_panes(env))
    row = session_db_row(env, sid) or {}
    rec.check("db.project_is_unassigned", row.get("workspace_id") == "unassigned" and row.get("ended_at") is None,
              "workspace_id unassigned, not ended", {k: row.get(k) for k in ("workspace_id", "ended_at", "state")})
    control = run_control(env.stream, env.client, "P8", mark)
    rec.check("stream.project_deleted", any(f.kind == "project.deleted" and f.project_id == project for f in control.interior),
              "project.deleted", [f.kind for f in control.interior])
    rec.record("stream.frames", [(f.kind, f.session_id) for f in control.interior])
    rows = delete_rows(env, amark, project)
    rec.check("logs.delete_row", len(rows) == 1 and rows[0].get("approved_by") == "claimed_human",
              "one delete_project row, claimed_human", [r.get("approved_by") for r in rows])
    kill(env, sid)
    rec.finish()
