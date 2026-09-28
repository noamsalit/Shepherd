"""Wave 3, SUB lane: the projects backend — P1-P6 and P9 (P7/P8 need an owned pane: wave 4).

One instance. Refusals take the §0 row 2 shape (b): **200 with a negative
record**, audited `result: ok` (review pass 1 finding 2). Every "frames only for
what changed" clause is read against the SSE liveness control.

P1's two `Payments` projects are left in place (test-plan P1 Cleanup: "kept
for U15 via the module seed" — U15 builds its own seed in wave 6; here they are
simply left in this instance, which dies with the module).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from ..auditprobe import AuditProbe
from ..bootstrap import git
from ..httpclient import Client, as_dict, as_list
from ..instance import Controld, db_rows
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sessions import sidecar, write_sidecar
from ..sse_rig import Subscriber, run_control, subscribe
from ..verdict import Recorder, observe

RESERVED_REFUSAL = "the Unassigned project cannot be"


@dataclass
class Proj:
    controld: Controld
    client: Client
    stream: Subscriber
    audit: AuditProbe
    run: RunContext
    pool: InstancePool
    fixtures: Path


@pytest.fixture(scope="module")
def proj(pool: InstancePool, qa6_run: RunContext) -> Iterator[Proj]:
    controld = pool.ready()
    fixtures = qa6_run.run0 / "p-fixtures"
    fixtures.mkdir(exist_ok=True)
    stream = subscribe("P", controld.port)
    try:
        yield Proj(controld=controld, client=controld.client, stream=stream, audit=AuditProbe.for_instance(controld.root),
                   run=qa6_run, pool=pool, fixtures=fixtures)
    finally:
        stream.close()


def pid_of(created: dict[str, object]) -> str:
    return str(as_dict(created.get("project"))["project_id"])


def get_project(client: Client, project_id: str) -> dict[str, object]:
    return client.get(f"/api/projects/{project_id}").data()


def repos_of(client: Client, project_id: str) -> list[dict[str, object]]:
    return [as_dict(r) for r in as_list(client.get(f"/api/projects/{project_id}/repos").data().get("repos"))]


def audit_results(audit: AuditProbe, mark: int, tools: set[str]) -> list[tuple[str, object]]:
    return [(str(r.get("tool")), r.get("result")) for r in audit.since(mark) if r.get("tool") in tools]


# ----- P1 ----------------------------------------------------------------------------


@scenario("P1")
def test_p1_create_list_get_duplicate_names_are_two_projects(proj: Proj, rec: Recorder) -> None:
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    before = {str(r["id"]) for r in db_rows(proj.controld.db, "SELECT id FROM workspace")}
    first = pid_of(proj.client.create_project("Payments", "d"))
    second = pid_of(proj.client.create_project("Payments", "d"))
    rec.check("api.two_distinct_ids", first != second, "two distinct project_ids", (first, second))
    listed = {str(p.get("project_id")) for p in proj.client.projects()}
    rec.check("api.list_holds_both_and_unassigned", {first, second, "unassigned"} <= listed, "both + unassigned", sorted(listed))
    for label, project_id in (("first", first), ("second", second)):
        got = get_project(proj.client, project_id)
        project = as_dict(got.get("project")) if isinstance(got.get("project"), dict) else {}
        rec.check(f"api.get_{label}", got.get("found") is True and project.get("name") == "Payments"
                  and project.get("description") == "d", "found:true, name Payments, description d", got)
    rows = [r for r in proj.audit.records_for(mark_audit, "create_project")]
    rec.check("logs.two_create_rows_claimed_human", len(rows) == 2 and all(r.get("approved_by") == "claimed_human" for r in rows),
              "two create_project rows, claimed_human", [r.get("approved_by") for r in rows])
    after = {str(r["id"]) for r in db_rows(proj.controld.db, "SELECT id FROM workspace")}
    rec.equal("db.two_workspace_rows", {first, second}, after - before)
    control = run_control(proj.stream, proj.client, "P1", mark)
    rec.equal("stream.two_created", 2, len([f for f in control.interior if f.kind == "project.created" and f.project_id in (first, second)]))
    rec.finish()


# ----- P2 ----------------------------------------------------------------------------


@scenario("P2")
def test_p2_rename_describe_clear_and_unassigned_refuses(proj: Proj, rec: Recorder) -> None:
    p = pid_of(proj.client.create_project("QA6-P2"))
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    calls: list[tuple[str, str, dict[str, object]]] = [
        ("rename", f"/api/projects/{p}/rename", {"name": "Payments2"}),
        ("rename_whitespace", f"/api/projects/{p}/rename", {"name": "   "}),
        ("describe", f"/api/projects/{p}/description", {"description": "x"}),
        ("describe_clear", f"/api/projects/{p}/description", {}),
        ("unassigned_rename", "/api/projects/unassigned/rename", {"name": "Nope"}),
        ("unassigned_describe", "/api/projects/unassigned/description", {"description": "nope"}),
        ("unassigned_delete", "/api/projects/unassigned/delete", {}),
        ("unassigned_repos_add", "/api/projects/unassigned/repos/add", {"root_path": str(proj.run.repos / "beta")}),
    ]
    answers: dict[str, dict[str, object]] = {}
    for name, path, body in calls:
        response = proj.client.post(path, body)
        rec.equal(f"api.{name}_200", 200, response.status)
        answers[name] = response.data() if response.status == 200 else {}
    rec.equal("api.rename", {"renamed": True, "refused": None}, {k: answers["rename"].get(k) for k in ("renamed", "refused")})
    ws = answers["rename_whitespace"]
    rec.check("api.whitespace_rename_refused", ws.get("renamed") is False and bool(ws.get("refused")),
              "{renamed:false, refused:<non-empty>} (derived oracle: the API refuses what the UI refuses)", ws)
    rec.equal("api.describe", True, answers["describe"].get("described"))
    rec.equal("api.describe_clear", True, answers["describe_clear"].get("described"))
    project = as_dict(get_project(proj.client, p).get("project"))
    rec.check("api.cleared_description", not project.get("description"), "get shows no description", project.get("description"))
    for name, verb in (("unassigned_rename", "renamed"), ("unassigned_describe", "described"),
                       ("unassigned_delete", "deleted"), ("unassigned_repos_add", "added")):
        answer = answers[name]
        rec.check(f"api.{name}_negative_record", answer.get(verb) is False and RESERVED_REFUSAL in str(answer.get("refused")),
                  f"{{{verb}:false, refused naming '{RESERVED_REFUSAL}'}}", answer)
    unassigned = as_dict(get_project(proj.client, "unassigned").get("project"))
    rec.equal("db.unassigned_unchanged", ("Unassigned", "Work that matched no declared project."),
              (unassigned.get("name"), unassigned.get("description")))
    rec.check("db.name_not_whitespace", str(project.get("name", "")).strip() != "", "P's name is not whitespace", project.get("name"))
    tools = {"rename_project", "set_project_description", "delete_project", "add_repo"}
    results = audit_results(proj.audit, mark_audit, tools)
    rec.check("logs.every_call_audited_ok", len(results) == len(calls) and all(r == "ok" for _t, r in results),
              f"{len(calls)} rows, result ok", results)
    control = run_control(proj.stream, proj.client, "P2", mark)
    changed = [f.kind for f in control.interior if f.kind.startswith("project.")]
    expected = ["project.renamed", *(["project.renamed"] if ws.get("renamed") else []), "project.described", "project.described"]
    rec.equal("stream.frames_only_for_changes", expected, changed)
    proj.client.delete_project(p)
    rec.finish()


# ----- P3 ----------------------------------------------------------------------------


@scenario("P3")
def test_p3_add_repo_path_classes(proj: Proj, rec: Recorder) -> None:
    repos = proj.run.repos
    alpha, beta = repos / "alpha", repos / "beta"
    link = proj.fixtures / "beta-link"
    if not link.exists():
        os.symlink(beta, link)
    a_file = proj.fixtures / "a-file.txt"
    a_file.write_text("not a repo\n", encoding="utf-8")
    nonrepo = proj.fixtures / "not-a-repo"
    nonrepo.mkdir(exist_ok=True)
    p = pid_of(proj.client.create_project("QA6-P3"))
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    cases: list[tuple[str, str]] = [
        ("valid", str(alpha)), ("non_repo", str(nonrepo)), ("nonexistent", str(proj.fixtures / "no-such-dir")),
        ("relative", "repos/alpha"), ("dotdot_beta", f"{alpha}/../beta"), ("symlink_beta", str(link)),
        ("duplicate", str(alpha)), ("file", str(a_file)), ("space", str(repos / "my repo")),
        ("worktree", str(repos / "alpha-wt")), ("submodule", str(alpha / "vendor-beta")),
    ]
    answers: dict[str, dict[str, object]] = {}
    for name, path in cases:
        response = proj.client.post(f"/api/projects/{p}/repos/add", {"root_path": path})
        rec.equal(f"api.{name}_200", 200, response.status)
        answers[name] = response.data() if response.status == 200 else {}
    rec.equal("api.valid_added", True, answers["valid"].get("added"))
    for name, path in cases:
        if name in ("non_repo", "nonexistent", "relative", "file"):
            answer = answers[name]
            refused = str(answer.get("refused") or "")
            rec.check(f"api.{name}_refused_naming_path", answer.get("added") is False and bool(refused) and
                      (path in refused or os.path.basename(path) in refused),
                      "{added:false, refused naming the path}", answer)
    beta_real = os.path.realpath(beta)
    for name in ("dotdot_beta", "symlink_beta"):
        answer = answers[name]
        repo = as_dict(answer.get("repo")) if isinstance(answer.get("repo"), dict) else {}
        rec.check(f"api.{name}_canonical_or_refused", (answer.get("added") is False and bool(answer.get("refused")))
                  or repo.get("root_path") == beta_real, f"stored root_path {beta_real} (or refused)", answer)
    stored = repos_of(proj.client, p)
    roots = [str(r.get("root_path")) for r in stored]
    rec.equal("db.duplicate_no_second_row", 1, roots.count(os.path.realpath(alpha)))
    space = as_dict(answers["space"].get("repo")) if isinstance(answers["space"].get("repo"), dict) else {}
    rec.check("api.space_verbatim", answers["space"].get("added") is True and str(space.get("root_path", "")).endswith("my repo"),
              "the space path stored verbatim", answers["space"])
    wt = answers["worktree"]
    wt_repo = as_dict(wt.get("repo")) if isinstance(wt.get("repo"), dict) else {}
    rec.check("api.worktree_resolves_to_alpha", wt_repo.get("git_common_dir") == os.path.realpath(alpha / ".git")
              or wt_repo.get("root_path") == os.path.realpath(alpha) or wt.get("added") is False,
              "the worktree resolves to alpha's repo identity (D48)", wt)
    rec.record("api.submodule", answers["submodule"])
    rec.record("api.worktree", wt)
    db_repos = db_rows(proj.controld.db, "SELECT r.root_path FROM repo r JOIN project_repo pr ON pr.repo_id = r.id WHERE pr.workspace_id = ?", (p,))
    rec.equal("db.rows_match_api", sorted(roots), sorted(str(r["root_path"]) for r in db_repos))
    accepted = [name for name, answer in answers.items() if answer.get("added") is True]
    results = audit_results(proj.audit, mark_audit, {"add_repo"})
    rec.check("logs.one_row_per_call_ok", len(results) == len(cases) and all(r == "ok" for _t, r in results),
              f"{len(cases)} add_repo rows, result ok", results)
    control = run_control(proj.stream, proj.client, "P3", mark)
    rec.equal("stream.one_repo_added_per_accepted", len(accepted),
              len([f for f in control.interior if f.kind == "project.repo_added" and f.project_id == p]))
    for repo in repos_of(proj.client, p):
        proj.client.remove_repo(p, str(repo.get("repo_id")))
    proj.client.delete_project(p)
    rec.finish()


# ----- P4 ----------------------------------------------------------------------------


@scenario("P4")
def test_p4_remove_repo(proj: Proj, rec: Recorder) -> None:
    p = pid_of(proj.client.create_project("QA6-P4"))
    added = proj.client.add_repo(p, str(proj.run.repos / "beta"))
    repo_id = str(as_dict(added.get("repo")).get("repo_id"))
    before = len(repos_of(proj.client, p))
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    first = proj.client.post(f"/api/projects/{p}/repos/remove", {"repo_id": repo_id})
    again = proj.client.post(f"/api/projects/{p}/repos/remove", {"repo_id": repo_id})
    unknown = proj.client.post(f"/api/projects/{p}/repos/remove", {"repo_id": "01M3QA6NOSUCHREPO000000000"})
    rec.equal("api.first_removed", True, first.data().get("removed") if first.status == 200 else first.status)
    for name, response in (("again", again), ("unknown", unknown)):
        ok = response.status == 400 or (response.status == 200 and response.data().get("removed") is False)
        rec.check(f"api.{name}_not_removed", ok, "removed:false or 400", (response.status, response.text[:200]))
    rec.equal("db.list_shrinks_once", before - 1, len(repos_of(proj.client, p)))
    results = audit_results(proj.audit, mark_audit, {"remove_repo"})
    rec.equal("logs.one_row_per_call", 3, len(results))
    control = run_control(proj.stream, proj.client, "P4", mark)
    removed_frames = [f for f in control.interior if f.kind == "project.repo_removed"]
    # The plan row says "one frame … per call"; a refusal changes nothing, and
    # P2/E6's rule is "frames only for the verbs that changed something", so the
    # frame count is read as one per call that removed a repo.
    rec.equal("stream.one_frame_for_the_change", 1, len(removed_frames))
    proj.client.delete_project(p)
    rec.finish()


# ----- P5 ----------------------------------------------------------------------------


@scenario("P5")
def test_p5_repo_shared_by_two_projects_sends_sessions_to_unassigned(proj: Proj, rec: Recorder) -> None:
    alpha = proj.run.repos / "alpha"
    a = pid_of(proj.client.create_project("QA6-P5-A"))
    b = pid_of(proj.client.create_project("QA6-P5-B"))
    added_a, added_b = proj.client.add_repo(a, str(alpha)), proj.client.add_repo(b, str(alpha))
    rec.equal("api.both_added", (True, True), (added_a.get("added"), added_b.get("added")))
    rec.check("api.both_list_alpha", any(str(r.get("root_path")).endswith("/alpha") for r in repos_of(proj.client, a))
              and any(str(r.get("root_path")).endswith("/alpha") for r in repos_of(proj.client, b)), "both projects list alpha", "")
    helper = proj.pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(alpha / "sub"), name="QA6 P5")
    write_sidecar(proj.controld.root.sessions, body)
    engine = str(body["sessionId"])
    row, _ = observe(lambda: (r[0] if (r := db_rows(proj.controld.db, "SELECT * FROM session WHERE engine_session_id = ?",
                                                      (engine,))) and r[0].get("state") == "running" else None), 6.0)
    rec.check("given.registered", row is not None, "the session registered", row)
    if row is not None:
        rec.equal("db.binding_unassigned", "unassigned", row.get("workspace_id"))
        placed = None
        for workspace in as_list(proj.client.fleet_tree().get("workspaces")):
            entry = as_dict(workspace)
            if any(as_dict(s).get("session_id") == row["id"] for s in as_list(entry.get("sessions"))):
                placed = entry.get("project_id")
        rec.equal("api.tree_under_unassigned", "unassigned", placed)
    repo_b = [r for r in repos_of(proj.client, b) if str(r.get("root_path")).endswith("/alpha")]
    if repo_b:
        proj.client.remove_repo(b, str(repo_b[0].get("repo_id")))
    helper.end()
    (proj.controld.root.sessions / f"{body['pid']}.json").unlink()
    rec.finish()


# ----- P6 ----------------------------------------------------------------------------


@scenario("P6")
def test_p6_delete_with_nothing_running_forgets_project_and_sessions(proj: Proj, rec: Recorder) -> None:
    gamma = proj.fixtures / "gamma"
    if not gamma.exists():
        gamma.mkdir()
        git("init", "-q", "-b", "main", str(gamma))
        (gamma / "README.md").write_text("gamma\n", encoding="utf-8")
        git("-C", str(gamma), "add", "README.md")
        git("-C", str(gamma), "commit", "-q", "-m", "gamma: initial")
    c = pid_of(proj.client.create_project("QA6-P6-C"))
    proj.client.add_repo(c, str(gamma))
    helper = proj.pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(gamma), name="QA6 P6")
    write_sidecar(proj.controld.root.sessions, body)
    engine = str(body["sessionId"])
    running, _ = observe(lambda: (r[0] if (r := db_rows(proj.controld.db, "SELECT * FROM session WHERE engine_session_id = ?",
                                                          (engine,))) and r[0].get("state") == "running" else None), 6.0)
    rec.check("given.session_in_c", running is not None and running.get("workspace_id") == c, "a session bound to C",
              running.get("workspace_id") if running else None)
    helper.end()
    (proj.controld.root.sessions / f"{body['pid']}.json").unlink()
    stopped, _ = observe(lambda: (r[0] if (r := db_rows(proj.controld.db, "SELECT * FROM session WHERE engine_session_id = ?",
                                                          (engine,))) and r[0].get("state") == "stopped" else None), 6.0)
    rec.check("given.session_stopped", stopped is not None, "the session is stopped", stopped)
    sid = str((stopped or running or {}).get("id"))
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    answer = proj.client.delete_project(c)
    rec.equal("api.deleted", True, answer.get("deleted"))
    rec.equal("api.project_found_false", False, get_project(proj.client, c).get("found"))
    rec.equal("api.session_found_false", False, proj.client.session(sid).get("found"))
    rows = proj.audit.records_for(mark_audit, "delete_project")
    rec.check("logs.delete_claimed_human", len(rows) == 1 and rows[0].get("approved_by") == "claimed_human",
              "delete_project, claimed_human", [r.get("approved_by") for r in rows])
    rec.equal("db.no_rows_for_c", [], db_rows(proj.controld.db, "SELECT id FROM workspace WHERE id = ?", (c,)))
    rec.equal("db.no_rows_for_session", [], db_rows(proj.controld.db, "SELECT id FROM session WHERE id = ?", (sid,)))
    control = run_control(proj.stream, proj.client, "P6", mark)
    rec.equal("stream.project_deleted", ["project.deleted"],
              [f.kind for f in control.interior if f.project_id == c and f.kind.startswith("project.")])
    rec.finish()


# ----- P9 ----------------------------------------------------------------------------


@scenario("P9")
def test_p9_invalid_delete_requests_change_nothing(proj: Proj, rec: Recorder) -> None:
    keep = pid_of(proj.client.create_project("QA6-P9-keep"))
    twice = pid_of(proj.client.create_project("QA6-P9-twice"))
    mark, mark_audit = proj.stream.mark(), proj.audit.mark()
    calls = [
        ("banana", keep, {"on_running": "banana"}),
        ("unassigned", "unassigned", {}),
        ("unknown", "01M3QA6NOSUCHPROJECT000000", {}),
        ("twice_first", twice, {}),
        ("twice_second", twice, {}),
    ]
    answers: dict[str, dict[str, object]] = {}
    for name, target, body in calls:
        response = proj.client.post(f"/api/projects/{target}/delete", body)
        rec.equal(f"api.{name}_200", 200, response.status)
        answers[name] = response.data() if response.status == 200 else {}
    rec.equal("api.twice_first_deleted", True, answers["twice_first"].get("deleted"))
    for name in ("banana", "unassigned", "unknown", "twice_second"):
        answer = answers[name]
        rec.check(f"api.{name}_refused", answer.get("deleted") is False and bool(answer.get("refused")),
                  "{deleted:false, refused:<non-empty>}", answer)
    ids = {str(r["id"]) for r in db_rows(proj.controld.db, "SELECT id FROM workspace")}
    rec.check("db.nothing_beyond_the_first", keep in ids and "unassigned" in ids and twice not in ids,
              "only the first of the pair deleted", sorted(ids))
    results = audit_results(proj.audit, mark_audit, {"delete_project"})
    rec.check("logs.row_per_call_ok", len(results) == len(calls) and all(r == "ok" for _t, r in results),
              f"{len(calls)} rows, result ok", results)
    control = run_control(proj.stream, proj.client, "P9", mark)
    rec.equal("stream.one_deleted_total", 1, len([f for f in control.interior if f.kind == "project.deleted"]))
    proj.client.delete_project(keep)
    rec.finish()
