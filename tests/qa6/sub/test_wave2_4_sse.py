"""Wave 2, SUB lane: the SSE stream — E1-E6.

E1-E4 and E6 share one instance; E5 restarts its daemon, so it gets its own
and runs last. Frame counts are read against the liveness control
(`sse_rig.run_control`): frames are ordered, so once the control's two frames
have arrived, anything the product should have sent before them is in the
interior or was never sent — a FAIL, not a timing question.

Clause names: E1's framing clauses start `framing.` — the wave-2 stop-if reads
them; its keep-alive clause (`keepalive.`) is a predicted product FAIL and
stops nothing (test-plan §3 wave 2).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from ..auditprobe import AuditProbe, MUTATION_TOOLS
from ..httpclient import Client, as_dict
from ..mutations import active
from ..instance import Controld
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import run_control, run_control_on, subscribe
from ..verdict import Blocked, Recorder, observe

FRAME_KEYS = {"seq", "at", "type", "session_id", "project_id", "data"}
RING = 4096
#: E1's keep-alive bracket (product-contract sse.py IDLE_TIMEOUT_S = 15.0).
QUIET_S, BY_S, OBSERVE_S = 13.0, 17.0, 35.0


@dataclass
class Sse:
    controld: Controld
    client: Client
    audit: AuditProbe


@pytest.fixture(scope="module")
def sse(pool: InstancePool) -> Iterator[Sse]:
    controld = pool.ready()
    yield Sse(controld=controld, client=controld.client, audit=AuditProbe.for_instance(controld.root))


def project_id(created: dict[str, object]) -> str:
    return str(as_dict(created.get("project"))["project_id"])


# ----- E1 ------------------------------------------------------------------------


@scenario("E1")
def test_e1_framing_headers_and_keep_alive(sse: Sse, rec: Recorder) -> None:
    sub = subscribe("E1", sse.controld.port)
    try:
        rec.check("framing.content_type", sub.headers.get("content-type", "").startswith("text/event-stream"),
                  "text/event-stream", sub.headers.get("content-type"))
        rec.check("framing.first_bytes_open", sub.first_bytes.startswith(b": open"), "': open'", sub.first_bytes[:12])
        mark_audit = sse.audit.mark()
        response = sse.client.post("/api/projects", {"name": "QA6-E1"})
        rec.equal("api.post_200", 200, response.status)
        pid = project_id(response.data())
        frames = sub.await_frames(lambda fs: any(f.project_id == pid for f in fs), 10.0, "the project.created frame",
                                  None)
        frame = next(f for f in frames if f.project_id == pid)
        rec.equal("framing.fields_id_and_data_only", ["data", "id"], sorted(frame.raw_fields))
        rec.check("framing.no_event_no_retry", not frame.has_event_name and "retry" not in frame.raw_fields,
                  "no event: and no retry: line", sorted(frame.raw_fields))
        rec.equal("framing.json_keys", sorted(FRAME_KEYS), sorted(frame.body_keys))
        body = json.loads(frame.raw_fields["data"])
        rec.equal("framing.seq_equals_id", int(frame.raw_fields["id"]), body.get("seq"))
        rec.equal("framing.type", "project.created", frame.kind)
        rec.equal("logs.audit_create_project", ["create_project"],
                  [t for t in sse.audit.tools_since(mark_audit) if t in MUTATION_TOOLS])

        def keep_alive_after_frame() -> float | None:
            for comment in sub.comment_snapshot():
                if comment.received_at > frame.received_at and "keep-alive" in comment.text:
                    return comment.received_at - frame.received_at
            return None

        first, _ = observe(keep_alive_after_frame, OBSERVE_S)
        rec.record("keepalive.first_comment_after_frame_s", round(first, 2) if first is not None else f"none in {OBSERVE_S}s")
        rec.check("keepalive.none_in_first_13s", first is None or first >= QUIET_S, f"no keep-alive before {QUIET_S}s", first)
        rec.check("keepalive.one_by_17s", first is not None and first <= BY_S,
                  f"at least one keep-alive by {BY_S}s (sse.py IDLE_TIMEOUT_S=15.0)", first)
        sse.client.delete_project(pid)
    finally:
        sub.close()
    rec.finish()


# ----- E2 ------------------------------------------------------------------------


@scenario("E2")
def test_e2_two_clients_same_ordered_stream(sse: Sse, rec: Recorder) -> None:
    first, second = subscribe("E2a", sse.controld.port), subscribe("E2b", sse.controld.port)
    try:
        marks = (first.mark(), second.mark())
        mark_audit = sse.audit.mark()
        barrier = threading.Barrier(2)
        errors: list[str] = []

        def writer(tag: str) -> None:
            client = Client(sse.controld.port, refusals_log=sse.controld.run.port_refusals)
            barrier.wait(timeout=10)
            for index in range(5):
                try:
                    pid = project_id(client.create_project(f"QA6-E2-{tag}-{index}"))
                    client.delete_project(pid)
                except AssertionError as error:
                    errors.append(f"{tag}{index}: {error}")

        threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("x", "y")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        rec.equal("api.writers_ok", [], errors)
        writer_rows = [t for t in sse.audit.tools_since(mark_audit) if t in ("create_project", "delete_project")]
        control_a, control_b = run_control_on([(first, marks[0]), (second, marks[1])], sse.client, "E2")
        tape_a = [(f.seq, f.kind, f.project_id) for f in control_a.interior]
        tape_b = [(f.seq, f.kind, f.project_id) for f in control_b.interior]
        rec.equal("stream.twenty_frames", 20, len(tape_a))
        rec.check("stream.same_frames_same_order", tape_a == tape_b, "both clients identical", {"a": tape_a[:4], "b": tape_b[:4]})
        seqs = [seq for seq, _kind, _pid in tape_a]
        rec.check("stream.seq_strictly_plus_one", all(b - a == 1 for a, b in zip(seqs, seqs[1:])), "+1 each", seqs)
        rec.equal("stream.no_duplicates", len(seqs), len(set(seqs)))
        rec.equal("logs.twenty_audit_rows", 20, len(writer_rows))
    finally:
        first.close()
        second.close()
    rec.finish()


# ----- E3 ------------------------------------------------------------------------


@scenario("E3")
def test_e3_last_event_id_resumes_exactly_within_the_ring(sse: Sse, rec: Recorder) -> None:
    reader = subscribe("E3-read", sse.controld.port)
    try:
        mark = reader.mark()
        seed = project_id(sse.client.create_project("QA6-E3-k"))
        k_frame = reader.await_frames(lambda fs: any(f.project_id == seed for f in fs), 10.0, "the k frame", None, mark)
        k = next(f.seq for f in k_frame if f.project_id == seed)
    finally:
        reader.close()
    for index in range(5):
        sse.client.rename_project(seed, f"QA6-E3-{index}")
    resume_from = k
    if active("PP10-E3-lastid"):
        resume_from = k + 1
        rec.note(f"QA6 MUTATION PP10-E3-lastid APPLIED: resumed with Last-Event-ID {resume_from}, not {k}")
    resumed = subscribe("E3-resumed", sse.controld.port, last_event_id=str(resume_from))
    try:
        replay, _ = observe(lambda: resumed.snapshot() if len(resumed.snapshot()) >= 5 else None, 10.0)
        first_five = [f.seq for f in (replay or resumed.snapshot())[:5]]
        rec.equal("stream.first_five_are_k_plus_1_to_5", [k + i for i in range(1, 6)], first_five)
        mark_live = resumed.mark()
        control = run_control(resumed, sse.client, "E3", mark_live)
        rec.check("stream.live_frames_continue", len(control.control_frames) == 2 and control.control_frames[0].seq > k + 5,
                  "live frames after the replay", [f.seq for f in control.control_frames])
        rec.record("given.k", k)
    finally:
        resumed.close()
    sse.client.delete_project(seed)
    rec.finish()


# ----- E4 ------------------------------------------------------------------------


@scenario("E4")
def test_e4_client_behind_the_ring_is_told(sse: Sse, rec: Recorder) -> None:
    reader = subscribe("E4-read", sse.controld.port)
    try:
        mark = reader.mark()
        target = project_id(sse.client.create_project("QA6-E4-a"))
        frames = reader.await_frames(lambda fs: any(f.project_id == target for f in fs), 10.0, "the k frame", None, mark)
        k = next(f.seq for f in frames if f.project_id == target)
    finally:
        reader.close()
    statuses: dict[int, int] = {}
    total = RING + 4
    for index in range(total):
        response = sse.client.post(f"/api/projects/{target}/rename", {"name": "QA6-E4-b" if index % 2 == 0 else "QA6-E4-a"})
        statuses[response.status] = statuses.get(response.status, 0) + 1
    rec.equal("api.all_renames_200", {200: total}, statuses)
    resumed = subscribe("E4-resumed", sse.controld.port, last_event_id=str(k))
    try:
        got, _ = observe(lambda: resumed.snapshot() if len(resumed.snapshot()) >= 3 else None, 15.0)
        tape = got or resumed.snapshot()
        rec.equal("stream.first_frame_is_gap", "stream.gap", tape[0].kind if tape else None)
        rest = tape[1:]
        rec.check("stream.then_seq_beyond_k_plus_4", bool(rest) and all(f.seq > k + 4 for f in rest),
                  f"frames continue with seq > {k + 4}", [f.seq for f in rest[:5]])
        rec.record("stream.gap_frame", {"seq": tape[0].seq, "data": tape[0].data} if tape else None)
    finally:
        resumed.close()
    sse.client.delete_project(target)
    rec.finish()


# ----- E6 (before E5: E5 restarts its own daemon) --------------------------------------


@scenario("E6")
def test_e6_project_frames_carry_the_project_id(sse: Sse, qa6_run: RunContext, rec: Recorder) -> None:
    sub = subscribe("E6", sse.controld.port)
    try:
        mark, mark_audit = sub.mark(), sse.audit.mark()
        pid = project_id(sse.client.create_project("QA6-E6"))
        sse.client.rename_project(pid, "QA6-E6-renamed")
        sse.client.describe_project(pid, "described")
        added = sse.client.add_repo(pid, str(qa6_run.repos / "beta"))
        repo = as_dict(added.get("repo")) if isinstance(added.get("repo"), dict) else {}
        repo_id = repo.get("repo_id") or repo.get("id")
        sse.client.remove_repo(pid, str(repo_id))
        sse.client.delete_project(pid)
        control = run_control(sub, sse.client, "E6", mark)
        mine = [f for f in control.interior if f.kind.startswith("project.")]
        rec.equal("stream.six_in_order",
                  ["project.created", "project.renamed", "project.described", "project.repo_added", "project.repo_removed",
                   "project.deleted"], [f.kind for f in mine])
        rec.check("stream.project_id_top_level", all(f.project_id == pid for f in mine), f"project_id == {pid}",
                  [f.project_id for f in mine])
        rec.check("stream.session_id_null", all(f.session_id is None for f in mine), "session_id null",
                  [f.session_id for f in mine])
        rec.equal("logs.six_rows_in_order",
                  ["create_project", "rename_project", "set_project_description", "add_repo", "remove_repo", "delete_project"],
                  [t for t in sse.audit.tools_since(mark_audit) if t in MUTATION_TOOLS][:6])
        rec.record("given.add_repo_answer", added)
    finally:
        sub.close()
    rec.finish()


# ----- E5 --------------------------------------------------------------------------


@scenario("E5")
def test_e5_last_event_id_across_a_daemon_restart(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    first = pool.ready()
    port = first.port
    reader = subscribe("E5-read", port)
    try:
        mark = reader.mark()
        for index in range(11):
            pid = project_id(first.client.create_project(f"QA6-E5-{index}"))
            first.client.delete_project(pid)
        tape, _ = observe(lambda: reader.since(mark) if len(reader.since(mark)) >= 22 else None, 10.0)
        k = (tape or reader.since(mark))[-1].seq if (tape or reader.since(mark)) else -1
    finally:
        reader.close()
    rec.check("given.k_at_least_20", k >= 20, "k >= 20", k)
    code = first.stop()
    rec.equal("given.first_stopped_cleanly", 0, code)
    second = pool.start(first.root, port=port, name="controld-restart")
    try:
        second.wait_ready()
    except Blocked as error:  # the OS would not re-bind the port: BLOCKED, never FAIL (env-plan §1)
        rec.block("given.restart_on_same_port", f"{type(error).__name__}: {error}")
        rec.finish()
        return
    rec.equal("given.same_port", port, second.port)
    resumed = subscribe("E5-resumed", port, last_event_id=str(k))
    fresh = subscribe("E5-fresh", port)
    try:
        started = time.monotonic()
        names = [f"QA6-E5-after-{index}" for index in range(3)]
        ids = [project_id(second.client.create_project(name)) for name in names]
        control, control_latency = observe(lambda: fresh.snapshot() if sum(1 for f in fresh.snapshot() if f.project_id in ids) >= 3 else None, 10.0)
        rec.check("stream.control_fresh_subscriber_gets_three", control is not None,
                  "a fresh subscriber without Last-Event-ID receives the 3 events", len(fresh.snapshot()))
        wanted, elapsed = observe(
            lambda: resumed.snapshot() if (sum(1 for f in resumed.snapshot() if f.project_id in ids) >= 3
                                           or any(f.kind == "stream.gap" for f in resumed.snapshot())) else None,
            max(0.1, 10.0 - (time.monotonic() - started)))
        if wanted is not None:
            rec.check("stream.resumed_gets_three_or_gap", True, "3 new events or stream.gap within 10 s", f"{elapsed:.2f}s")
        elif control is not None:
            rec.fail_bound("stream.resumed_gets_three_or_gap", "the resumed client receives the 3 new events (or stream.gap)",
                           10.0, f"a fresh subscriber received them in {control_latency:.2f}s; resumed got "
                           f"{[(f.seq, f.kind) for f in resumed.snapshot()]}")
        else:
            rec.block("stream.resumed_gets_three_or_gap", "the fresh-subscriber control did not receive the events either")
        rec.equal("api.three_mutations_200", 3, len(ids))
        for pid in ids:
            second.client.delete_project(pid)
    finally:
        resumed.close()
        fresh.close()
    second.stop()
    rec.finish()
