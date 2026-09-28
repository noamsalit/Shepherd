"""Wave 2, SUB lane: the HTTP envelope and its refusals — A1-A8.

One instance for the module (A-scenarios never restart the daemon). Every
"nothing happened" clause (no frame, no audit row, no DB change) is read
against a positive control on the same channel: the SSE liveness control
(`sse_rig.run_control`, two frames and two audit rows, run last) and a
before/after read of the DB or the audit file.

Clause names: A1's per-route clauses start `route.` — the wave-2 stop-if
counts them (`stopifs.py`: A1 failing on >= 3 routes stops waves 3-7).
"""

from __future__ import annotations

import json
import re
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from shepherd.toolsurface.registry import GENERIC_ERROR

from .. import hostprobe, paths
from ..auditprobe import AuditProbe
from ..httpclient import ENVELOPE_KEYS, Client, Response, as_dict, generic_error_problems
from ..instance import Controld, db_rows
from ..pool import InstancePool
from ..scenario import scenario
from ..sse_rig import Refusal, Subscriber, open_stream, run_control, subscribe
from ..verdict import Recorder
from ..wsclient import NO_ORIGIN, upgrade

BODY_LIMIT = 1 << 20
MISMATCH_BOUND_S = 5.0


@dataclass
class Http:
    controld: Controld
    client: Client
    audit: AuditProbe
    stream: Subscriber


@pytest.fixture(scope="module")
def http(pool: InstancePool) -> Iterator[Http]:
    controld = pool.ready()
    stream = subscribe("A", controld.port)
    try:
        yield Http(controld=controld, client=controld.client, audit=AuditProbe.for_instance(controld.root), stream=stream)
    finally:
        stream.close()


def project_count(controld: Controld) -> int:
    rows = db_rows(controld.db, "SELECT COUNT(*) AS n FROM workspace")
    value = rows[0]["n"]
    return int(value) if isinstance(value, int) else -1


def autonomy_level(client: Client) -> object:
    return client.get("/api/autonomy").data().get("level")


# ----- A1 ------------------------------------------------------------------------


@scenario("A1")
def test_a1_every_session_free_get_answers_the_envelope(http: Http, rec: Recorder) -> None:
    created = http.client.create_project("QA6-A1")
    project = as_dict(created.get("project"))
    pid = str(project["project_id"])
    routes = ["/api/fleet", "/api/fleet/tree", "/api/projects", "/api/sessions", "/api/mailbox", "/api/approvals",
              "/api/audit", "/api/autonomy", f"/api/projects/{pid}", f"/api/projects/{pid}/repos"]
    mark = http.audit.mark()
    seen: list[str] = []
    for index, path in enumerate(routes, start=1):
        response = http.client.get(path)
        problems: list[str] = []
        if response.status != 200:
            problems.append(f"status {response.status}")
        if not response.headers.get("content-type", "").startswith("application/json"):
            problems.append(f"content-type {response.headers.get('content-type')!r}")
        try:
            body = response.json()
        except AssertionError as error:
            body, problems = {}, [*problems, str(error)]
        if set(body) != ENVELOPE_KEYS:
            problems.append(f"keys {sorted(body)}")
        if body.get("ok") is not True:
            problems.append(f"ok={body.get('ok')!r}")
        if body.get("error") is not None:
            problems.append(f"error={body.get('error')!r}")
        correlation = body.get("correlation_id")
        if not (isinstance(correlation, str) and correlation):
            problems.append(f"correlation_id={correlation!r}")
        elif correlation in seen:
            problems.append("correlation_id repeated")
        else:
            seen.append(correlation)
        rec.check(f"route.{index}.{path.split('/api/')[1].split('/')[0]}", not problems,
                  f"GET {path}: 200 JSON envelope, ok, error null, a fresh correlation_id", problems or "ok")
    rows = http.audit.since(mark)
    for index, correlation in enumerate(seen, start=1):
        matching = [row for row in rows if row.get("correlation_id") == correlation]
        shape_ok = len(matching) == 1 and matching[0].get("blast_class") == "local_read" \
            and matching[0].get("actor_kind") == "human" and matching[0].get("decision") == "allow" \
            and matching[0].get("approved_by") == "policy"
        rec.check(f"logs.audit_{index}", shape_ok,
                  "one local_read row, actor_kind human, decision allow, approved_by policy",
                  [{k: row.get(k) for k in ("tool", "blast_class", "actor_kind", "decision", "approved_by")} for row in matching])
    deleted = http.client.delete_project(pid)
    rec.equal("cleanup.project_deleted", True, deleted.get("deleted"))
    rec.finish()


# ----- A2 ------------------------------------------------------------------------


@scenario("A2")
def test_a2_refusal_in_400_shape_leaks_no_reason(http: Http, rec: Recorder) -> None:
    mark_stream = http.stream.mark()
    mark_audit = http.audit.mark()
    cases: list[tuple[str, Response]] = [
        ("level_5", http.client.post("/api/autonomy", {"level": 5})),
        ("level_string", http.client.post("/api/autonomy", {"level": "3"})),
        ("choice_maybe", http.client.post("/api/approvals/01M3QA6000000000000000000A", {"choice": "maybe"})),
    ]
    for name, response in cases:
        problems = generic_error_problems(response, 400)
        rec.check(f"api.{name}_generic_400", not problems, f"400 with error == {GENERIC_ERROR!r}", problems or response.text)
    rec.equal("db.autonomy_still_2", 2, autonomy_level(http.client))
    rows = http.audit.since(mark_audit)
    by_correlation = {str(r.get("correlation_id")): r for r in rows}
    correlations = [str(response.json().get("correlation_id")) for _name, response in cases]
    first = by_correlation.get(correlations[0])
    rec.check("logs.level_5_row", first is not None and first.get("tool") == "set_autonomy_level" and first.get("result") == "refused",
              "one set_autonomy_level row, result refused", first)
    rec.check("logs.level_string_no_row", correlations[1] not in by_correlation, "no row (schema failures are not audited)",
              by_correlation.get(correlations[1]))
    third = by_correlation.get(correlations[2])
    rec.check("logs.choice_maybe_row",
              third is not None and third.get("tool") == "decide_approval" and third.get("decision") == "allow"
              and third.get("approved_by") == "claimed_human" and third.get("result") == "refused",
              "one decide_approval row: allow, claimed_human, refused", third)
    control = run_control(http.stream, http.client, "A2", mark_stream)
    rec.equal("stream.no_frames", [], [f.kind for f in control.interior])
    rec.finish()


# ----- A3 ------------------------------------------------------------------------


@scenario("A3")
def test_a3_unknown_paths_and_non_shipped_static_are_404(http: Http, rec: Recorder) -> None:
    pyproject = (paths.REPO / "pyproject.toml").read_bytes()
    license_bytes = (paths.REPO / "src/shepherd/web/static/vendor/LICENSE").read_bytes()
    needles = [pyproject[:40], license_bytes[:40]]
    mark = http.audit.mark()
    cases = [("GET", "/api/nope"), ("POST", "/api/nope"), ("GET", "/static/vendor/LICENSE"), ("GET", "/static/app.js.map"),
             ("GET", "/static/../pyproject.toml"), ("GET", "/static/%2e%2e/pyproject.toml")]
    for method, path in cases:
        if method == "POST":
            response = http.client.post(path, {})
        else:
            response = http.client.get(path)
        leaked = [needle for needle in needles if needle in response.body]
        rec.check(f"api.{method}_{path}", response.status == 404 and not leaked,
                  "404, no bytes of pyproject.toml or the LICENSE", {"status": response.status, "leaked": bool(leaked)})
    rec.equal("logs.no_audit_row", [], http.audit.tools_since(mark))
    rec.finish()


# ----- A4 ------------------------------------------------------------------------


def raw_post(port: int, body: bytes, content_length: int | None, timeout_s: float) -> tuple[int | None, bytes, float]:
    """A POST built by hand, so Content-Length can lie or be absent."""
    head = [f"POST /api/projects HTTP/1.1", f"Host: 127.0.0.1:{port}", f"Origin: http://127.0.0.1:{port}",
            "Content-Type: application/json", "Connection: close"]
    if content_length is not None:
        head.append(f"Content-Length: {content_length}")
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=timeout_s) as sock:
        try:
            sock.sendall(("\r\n".join(head) + "\r\n\r\n").encode("ascii") + body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the server answered and closed before the whole body was sent; read the answer
        raw = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                raw += chunk
        except TimeoutError:
            pass  # no (complete) answer within the bound: the caller decides what that means
        except ConnectionResetError:
            pass  # the answer, if any, is already in `raw`
    elapsed = time.monotonic() - started
    match = re.match(rb"HTTP/1\.[01] (\d{3})", raw)
    return (int(match.group(1)) if match else None), raw, elapsed


@scenario("A4")
def test_a4_body_limits_and_bad_bodies(http: Http, rec: Recorder) -> None:
    port = http.controld.port
    before = project_count(http.controld)
    mark = http.audit.mark()
    valid = json.dumps({"name": "QA6-A4-control"}).encode()
    status, raw, control_latency = raw_post(port, valid, len(valid), 5.0)
    rec.equal("api.control_valid_post_200", 200, status)
    control_id = None
    body_text = raw.split(b"\r\n\r\n", 1)[-1]
    try:
        control_id = as_dict(as_dict(json.loads(body_text).get("data")).get("project")).get("project_id")
    except (ValueError, AssertionError):
        control_id = None
    exact = json.dumps({"name": "a" * (BODY_LIMIT - 12)}).encode()
    over = json.dumps({"name": "a" * (BODY_LIMIT - 11)}).encode()
    rec.equal("given.sizes", (BODY_LIMIT, BODY_LIMIT + 1), (len(exact), len(over)))
    for name, body in (("non_json", b"x"), ("array", b"[]"), ("string", b'"s"'), ("over_1mib", over)):
        status, raw, _ = raw_post(port, body, len(body), 10.0)
        rec.equal(f"api.{name}_400", 400, status)
    status, raw, _ = raw_post(port, b"", None, 10.0)
    rec.equal("api.missing_content_length_400", 400, status)
    status, raw, _ = raw_post(port, exact, len(exact), 20.0)
    rec.check("api.exactly_1mib_not_refused_for_size", status is not None and status != 413,
              "not refused for size (recorded: the handler's answer)", status)
    rec.record("api.exactly_1mib_answer", raw.split(b"\r\n\r\n", 1)[-1][:200])
    status, raw, elapsed = raw_post(port, b'{"name":"x', 100, MISMATCH_BOUND_S)
    if status == 400 and elapsed <= MISMATCH_BOUND_S:
        rec.check("api.content_length_mismatch_400_in_5s", True, "400 within 5 s", f"{elapsed:.2f}s")
    elif status is None and MISMATCH_BOUND_S >= 10 * control_latency:
        rec.fail_bound("api.content_length_mismatch_400_in_5s", "a 400 for Content-Length 100 with 10 bytes sent",
                       MISMATCH_BOUND_S, f"valid-body POST answered in {control_latency:.3f}s; the server held the request")
    else:
        rec.check("api.content_length_mismatch_400_in_5s", False, "400 within 5 s", {"status": status, "elapsed": elapsed})
    after = project_count(http.controld)
    created_by_1mib = after - before - (1 if control_id else 0)
    rec.record("db.projects_created_beyond_control", created_by_1mib)
    rec.check("db.count_unchanged_but_1mib", created_by_1mib in (0, 1), "unchanged except possibly the 1 MiB case",
              created_by_1mib)
    tools = [t for t in http.audit.tools_since(mark) if t == "create_project"]
    rec.check("logs.no_row_for_size_or_shape", len(tools) in (1, 2), "only the control (and possibly 1 MiB) audited",
              tools)
    if isinstance(control_id, str):
        http.client.delete_project(control_id)
    for row in http.client.projects():
        if str(row.get("name", "")).startswith("aaaa"):
            http.client.delete_project(str(row["project_id"]))
    rec.finish()


# ----- A5 ------------------------------------------------------------------------


@scenario("A5")
def test_a5_origin_and_host_checks_pairwise(http: Http, rec: Recorder) -> None:
    port = http.controld.port
    client = http.client
    other = port + 1 if port + 1 != paths.FORBIDDEN_PORT else port + 2
    before_projects, before_level = project_count(http.controld), autonomy_level(client)
    mark_stream, mark_audit = http.stream.mark(), http.audit.mark()
    same = f"http://127.0.0.1:{port}"
    body = json.dumps({"name": "QA6-A5-must-not-exist"}).encode()
    allowed_body = json.dumps({"level": 2}).encode()

    def post(path: str, payload: bytes, headers: dict[str, str]) -> Response:
        return client.request("POST", path, body=payload, headers={"Content-Type": "application/json", **headers})

    posts = [
        ("post_same_origin", "/api/autonomy", allowed_body, {"Host": f"127.0.0.1:{port}", "Origin": same}, 200),
        ("post_no_origin", "/api/autonomy", allowed_body, {"Host": f"127.0.0.1:{port}"}, 200),
        ("post_evil_origin", "/api/projects", body, {"Host": f"127.0.0.1:{port}", "Origin": "http://evil.example"}, 403),
        ("post_null_origin", "/api/projects", body, {"Host": f"127.0.0.1:{port}", "Origin": "null"}, 403),
        ("post_localhost_origin", "/api/projects", body, {"Host": f"127.0.0.1:{port}", "Origin": f"http://localhost:{port}"}, 403),
        ("post_localhost_host", "/api/projects", body, {"Host": f"localhost:{port}", "Origin": same}, 403),
        ("post_other_port_host", "/api/projects", body, {"Host": f"127.0.0.1:{other}", "Origin": same}, 403),
        ("post_evil_host", "/api/projects", body, {"Host": "evil.example", "Origin": same}, 403),
    ]
    for name, path, payload, headers, expected in posts:
        rec.equal(f"api.{name}", expected, post(path, payload, headers).status)
    for name, headers in (("sse_foreign_origin", {"Origin": "http://evil.example"}),
                          ("sse_host_mismatch", {"Host": "evil.example"})):
        opened = open_stream(name, port, headers=headers)
        status = opened.status if isinstance(opened, Refusal) else 200
        if not isinstance(opened, Refusal):
            opened.close()
        rec.equal(f"stream.{name}", 403, status)
    terminal = "/api/sessions/01M3QA6NOSUCHSESSION00000000/terminal"
    foreign_ws = upgrade(port, terminal, origin="http://evil.example").status
    rec.check("ws.foreign_origin_refused_before_upgrade", foreign_ws == 403,
              "refused before the upgrade (403)", foreign_ws)
    rec.equal("ws.no_origin_403", 403, upgrade(port, terminal, origin=NO_ORIGIN).status)
    fleet = client.get("/api/fleet", {"Origin": "http://evil.example"})
    rec.check("api.get_foreign_origin_200_no_acao", fleet.status == 200 and "access-control-allow-origin" not in fleet.headers,
              "200 with no Access-Control-Allow-Origin", {"status": fleet.status, "acao": fleet.headers.get("access-control-allow-origin")})
    evil_host = client.request("GET", "/api/fleet", headers={"Host": "evil.example"})
    rec.record("api.get_evil_host", evil_host.status)
    rec.equal("db.no_project_from_a_403", before_projects, project_count(http.controld))
    rec.equal("db.autonomy_unchanged", before_level, autonomy_level(client))
    tools = http.audit.tools_since(mark_audit)
    rec.equal("logs.audit_only_the_allowed", ["set_autonomy_level", "set_autonomy_level"],
              [t for t in tools if t != "fleet_summary" and t != "get_autonomy_level"])
    control = run_control(http.stream, client, "A5", mark_stream)
    rec.equal("stream.no_frame_from_a_403", [], [f.kind for f in control.interior if f.kind.startswith("project.")])
    rec.finish()


# ----- A6 ------------------------------------------------------------------------


@scenario("A6")
def test_a6_undeclared_fields_dropped_path_parameter_wins(http: Http, rec: Recorder) -> None:
    a = str(as_dict(http.client.create_project("QA6-A6-A").get("project"))["project_id"])
    b = str(as_dict(http.client.create_project("QA6-A6-B").get("project"))["project_id"])
    mark_stream, mark_audit = http.stream.mark(), http.audit.mark()
    response = http.client.post(f"/api/projects/{a}/rename", {"name": "QA6-A2", "project_id": b, "evil": 1})
    rec.equal("api.200", 200, response.status)
    names = {str(row["project_id"]): row.get("name") for row in http.client.projects()}
    rec.equal("db.a_renamed", "QA6-A2", names.get(a))
    rec.equal("db.b_unchanged", "QA6-A6-B", names.get(b))
    rows = http.audit.records_for(mark_audit, "rename_project")
    args = rows[0].get("args") if rows else None
    rec.check("logs.args_declared_only", isinstance(args, dict) and set(args) <= {"project_id", "name"} and args.get("project_id") == a,
              "only declared keys, project_id == A", args)
    # The control runs after the rename: frames are ordered, so a renamed frame
    # that is not in the interior when the control's frames have arrived was
    # never sent (a FAIL, not a timing question).
    control = run_control(http.stream, http.client, "A6", mark_stream)
    renamed = [f for f in control.interior if f.kind == "project.renamed"]
    rec.check("stream.one_renamed_for_a", len(renamed) == 1 and renamed[0].project_id == a,
              "one project.renamed with project_id A", [(f.kind, f.project_id) for f in renamed])
    http.client.rename_project(a, "QA6-A6-A")
    http.client.delete_project(a)
    http.client.delete_project(b)
    rec.finish()


# ----- A7 ------------------------------------------------------------------------


@scenario("A7")
def test_a7_failure_never_leaks_internals(http: Http, rec: Recorder) -> None:
    mark = http.audit.mark()
    response = http.client.get("/api/sessions?state=bogus")
    problems = generic_error_problems(response, 400)
    rec.check("api.generic_400", not problems, "400 generic envelope", problems or response.text)
    for needle in ("Traceback", "/Users/", "ValueError"):
        rec.check(f"api.no_{needle.strip('/').lower()}", needle not in response.text, f"no {needle!r} in the body", response.text[:200])
    rows = http.audit.records_for(mark, "list_sessions")
    failure = rows[0].get("failure") if rows else None
    rec.check("logs.failed_bare_class", bool(rows) and rows[0].get("result") == "failed"
              and isinstance(failure, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", failure) is not None,
              "result failed, failure a bare class name", rows[0] if rows else None)
    rec.finish()


# ----- A8 ------------------------------------------------------------------------


def non_loopback_ipv4() -> str | None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1; UDP connect sends nothing
        address = str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") else address


@scenario("A8")
def test_a8_loopback_only(http: Http, rec: Recorder) -> None:
    port = http.controld.port
    listening = hostprobe.listen_addresses(http.controld.child.pid)
    rec.equal("proc.listens_exactly_loopback", [f"127.0.0.1:{port}"], listening)
    rec.check("proc.nothing_wildcard", not any(a.startswith("*:") or a.startswith("[::]") for a in listening),
              "nothing on * or [::]", listening)
    address = non_loopback_ipv4()
    if address is None:
        rec.block("api.non_loopback_refused", "this host has no non-loopback IPv4 address")
    else:
        refused = False
        try:
            socket.create_connection((address, port), timeout=3.0).close()
        except OSError:
            refused = True
        rec.check("api.non_loopback_refused", refused, f"connect to {address}:{port} refused", refused)
    rec.finish()
