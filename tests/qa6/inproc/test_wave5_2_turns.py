"""Wave 5, INP #1: turns, approvals and the gate — M1-M10 and P10.

One INP composition for the process (`inp`, session-scoped: T3). This module
opens one project holding `alpha` and one SSE subscriber. Every approval
scenario spawns its own HUMAN (origin `user_ui`) shim session, so no kill here
ever enters D31's wake set (the wake module's scenarios depend on that), and
restores autonomy level 2 on the way out.

Three §2c floor mutations live here, each one `active()` input switch:

* `w5_PP1-M3-autonomy3` (PP-1): the level is set to **3** before M3's send, so
  the destructive call runs with no card. M3 samples the pane 2 s after the
  card — or, with no card, 2 s after `master.tool_call` — and its
  `tmux.alive_while_pending` clause must go false.
* `w5_PP2-M5-one-post` (PP-2): M5's second approve on card A is **not sent**
  (the at-risk shape: a second click that never reached the server), and the
  clause that counts A's `decide_approval` POSTs must go false.
* `w5_PP20-M10-in-audience` (PP-20): M10's first call is `get_autonomy_level`
  (in the master's audience) instead of `decide_approval`; the "three
  is_error" clause must go false.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from uuid import uuid4

import pytest

from shepherd.toolsurface.registry import GENERIC_ERROR, invoke
from shepherd.toolsurface.types import Audience, CallerContext

from ..httpclient import as_dict, as_list, generic_error_problems
from ..inp import Inp
from ..inproc.master import Call, Turn
from ..instance import app_state
from ..mutations import active
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import run_control
from ..verdict import Recorder
from .test_wave5_1_support import (
    Master,
    await_end,
    await_gone,
    card,
    decide,
    decided,
    detail,
    frames,
    kill_http,
    last_turn_at,
    open_master,
    pane_alive,
    post,
    project_id_from,
    record,
    rows_for,
    send,
    session_row,
    set_level,
    shape,
    spawn_user,
    tool_result,
    turn_frames,
)

MUT_PP1 = "w5_PP1-M3-autonomy3"
MUT_PP2 = "w5_PP2-M5-one-post"
MUT_PP20 = "w5_PP20-M10-in-audience"
DENIED = "you declined this"  # spec O12 / §11, verbatim
WITHDRAWN = "the request this approval belonged to went away"  # plan M6, verbatim
PENDING_ROW_TITLE = "1 approval pending"  # plan M3, verbatim
SAMPLE_AFTER_S = 2.0  # plan M3: "sample the pane 2 s after approval.created"


@pytest.fixture(scope="module")
def m(inp: Inp, qa6_run: RunContext) -> Iterator[Master]:
    master = open_master(inp, qa6_run, "M")
    try:
        yield master
    finally:
        set_level(master, 2)
        master.stream.close()


def kill_turn(session_id: str, says: str) -> Turn:
    return Turn(says=says, calls=[Call("kill_session", {"session_id": session_id})])


def iso_seconds(stamp: object) -> float | None:
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ----- M1 ------------------------------------------------------------------------------


@scenario("M1")
def test_m1_a_master_turn_streams_its_events(m: Master, rec: Recorder) -> None:
    mark, amark = m.stream.mark(), m.audit.mark()
    before = last_turn_at(m)
    answer = send(m, Turn(says="QA6 hello", calls=[Call("fleet_summary", {})]), "hi")
    turn_id = answer.get("turn_id")
    rec.check("api.started", answer.get("started") is True and isinstance(turn_id, str) and bool(answer.get("started_at"))
              and answer.get("reason") is None and set(answer) == {"started", "turn_id", "started_at", "reason"},
              "{started:true, turn_id:T, started_at, reason:null}", answer)
    if not isinstance(turn_id, str):
        rec.finish()
        return
    await_end(turn_id)
    ours = turn_frames(m, mark, turn_id)
    kinds = [f.kind for f in ours]
    rec.equal("stream.in_order", ["master.text", "master.tool_call", "master.tool_result", "master.turn_ended"], kinds)
    by_kind = {f.kind: f for f in ours}
    rec.equal("stream.text", "QA6 hello", by_kind["master.text"].data.get("text") if "master.text" in by_kind else None)
    call = by_kind.get("master.tool_call")
    call_detail = detail(call)
    rec.equal("stream.tool_call_name", "fleet_summary", call.data.get("tool_name") if call else None)
    if "tool_use_id" in call_detail:
        rec.check("stream.tool_call_tool_use_id", isinstance(call_detail["tool_use_id"], str) and bool(call_detail["tool_use_id"]),
                  "detail.tool_use_id", call_detail)
    else:
        rec.block("stream.tool_call_tool_use_id",
                  "unproven by stub (G3): the scripted ToolCallingMaster (tests/qa6/inproc/master.py) yields "
                  "tool_call with payload=args and no tool_use_id, so the product has none to project; "
                  f"SCOPE_INCREASE filed for the adapter; detail={call_detail!r}")
    rec.equal("stream.tool_call_input_empty", {}, call_detail.get("input", call_detail) if call else None)
    result = by_kind.get("master.tool_result")
    rec.equal("stream.tool_result_not_error", False, detail(result).get("is_error"))
    rec.check("stream.all_carry_turn_and_null_session", bool(ours) and all(f.session_id is None for f in ours),
              "every frame turn_id T and session_id null", [(f.kind, f.session_id) for f in ours])
    rows = rows_for(m, amark, "fleet_summary", turn_id)
    rec.check("logs.fleet_summary_row", len(rows) == 1 and rows[0].get("actor_kind") == "master"
              and rows[0].get("actor_id") == "master" and rows[0].get("decision") == "allow"
              and rows[0].get("approved_by") == "policy",
              "audit fleet_summary: actor master/master, correlation T, allow, policy",
              shape(rows, "actor_kind", "actor_id", "decision", "approved_by"))
    after = last_turn_at(m)
    rec.check("db.master_last_turn_at_later", after is not None and (before is None or after > before),
              "app_state.master_last_turn_at later than before", (before, after))
    following = send(m, Turn(says="QA6 M1 next"), "QA6 M1 next")
    rec.equal("cleanup.slot_released_next_send_starts", True, following.get("started"))
    if following.get("started") is True:
        await_end(following.get("turn_id"))
    rec.finish()


# ----- M2 ------------------------------------------------------------------------------


@scenario("M2")
def test_m2_a_second_send_while_a_turn_is_live_is_refused_not_queued(m: Master, rec: Recorder) -> None:
    sid = spawn_user(m, "QA6 M2")
    mark, amark = m.stream.mark(), m.audit.mark()
    first = send(m, kill_turn(sid, "QA6 M2 first"), "QA6 M2 first")
    turn_id = str(first.get("turn_id"))
    pending = card(m, mark, "kill_session")
    if pending is None:
        rec.block("given.card_pending", "no approval.created for the first turn's kill_session")
        rec.finish()
        return
    mark2 = m.stream.mark()
    second = send(m, None, "QA6 M2 second")
    rec.check("api.second_refused", second.get("started") is False
              and str(second.get("reason", "")).startswith(f"a turn is already running ({turn_id})"),
              f"{{started:false}}, reason beginning 'a turn is already running ({turn_id})'", second)
    status, answer = decide(m, str(pending.data.get("approval_id")), "reject")
    rec.equal("given.rejected", (200, True), (status, answer.get("decided")))
    await_end(turn_id)
    others = [f for f in m.stream.since(mark2) if f.kind.startswith("master.") and f.data.get("turn_id") != turn_id]
    rec.equal("stream.no_second_turn_before_the_third", [], [(f.kind, f.data.get("turn_id")) for f in others])
    third = send(m, Turn(says="QA6 M2 third"), "QA6 M2 third")
    rec.equal("api.third_started", True, third.get("started"))
    if third.get("started") is True:
        await_end(third.get("turn_id"))
    rows = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.as_m4", len(rows) == 1 and rows[0].get("decision") == "deny", "kill_session deny (as M4)",
              shape(rows, "decision", "approved_by", "result"))
    kill_http(m, sid)
    rec.finish()


# ----- M3 ------------------------------------------------------------------------------


@scenario("M3")
def test_m3_level_2_a_destructive_master_call_waits_for_approval_then_runs(m: Master, rec: Recorder) -> None:
    sid = spawn_user(m, "QA6 M3")
    if active(MUT_PP1):
        set_level(m, 3)
        rec.note(f"QA6 MUTATION {MUT_PP1} APPLIED: autonomy level set to 3 before the send "
                 f"(GET /api/autonomy -> {m.client.get('/api/autonomy').data()})")
    mark, amark = m.stream.mark(), m.audit.mark()
    answer = send(m, kill_turn(sid, "QA6 M3"), "QA6 M3")
    turn_id = str(answer.get("turn_id"))
    pending = card(m, mark, "kill_session")
    anchor = pending or next(iter([f for f in turn_frames(m, mark, turn_id) if f.kind == "master.tool_call"]), None)
    if anchor is None:
        rec.block("given.anchor", "neither approval.created nor master.tool_call arrived")
        rec.finish()
        return
    wait = anchor.received_at + SAMPLE_AFTER_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)  # the plan's observation point: 2 s after approval.created
    approval_id = str(pending.data.get("approval_id")) if pending else ""
    listed = [as_dict(a) for a in as_list(m.client.get("/api/approvals").data().get("approvals"))]
    still_pending = any(a.get("approval_id") == approval_id for a in listed) if pending else False
    rec.check("tmux.alive_while_pending", pane_alive(m, sid) and still_pending,
              "at the 2 s sample the card is pending and the pane is alive", {"alive": pane_alive(m, sid),
                                                                               "pending": still_pending})
    set_level(m, 2)
    rec.check("stream.card_created", pending is not None, "approval.created for kill_session", pending.data if pending else None)
    if pending is None:
        await_end(turn_id)
        rec.finish()
        return
    rec.check("stream.card_fields", pending.data.get("tool") == "kill_session" and pending.data.get("turn_id") == turn_id
              and f"session_id={sid}" in str(pending.data.get("summary")),
              f"tool kill_session, turn_id T, summary containing session_id={sid}", pending.data)
    row = next((a for a in listed if a.get("approval_id") == approval_id), {})
    created, deadline = iso_seconds(row.get("created_at")), iso_seconds(pending.data.get("deadline_at"))
    rec.check("stream.deadline_600", created is not None and deadline is not None and abs(deadline - created - 600) <= 5,
              "deadline_at = created + 600 s ± 5 s", (row.get("created_at"), pending.data.get("deadline_at")))
    rec.check("api.list_without_raw_args", bool(row) and "args" not in row
              and set(row) == {"approval_id", "turn_id", "tool", "summary", "created_at", "deadline_at"},
              "GET /api/approvals lists A without raw args", row)
    needs = [as_dict(n) for n in as_list(m.client.fleet().get("needs_you"))]
    rec.check("api.fleet_needs_you_rail_row", any(n.get("session_id") is None and n.get("title") == PENDING_ROW_TITLE
                                                  and n.get("needs_you_reason") == "kill_session" for n in needs),
              "{session_id:null, title:'1 approval pending', needs_you_reason:'kill_session'}", needs)
    status, verdict = decide(m, approval_id, "approve")
    rec.equal("api.decided_approved", (200, True, "approved"), (status, verdict.get("decided"), verdict.get("outcome")))
    outcome = decided(m, mark, approval_id)
    rec.equal("stream.decided_approved", "approved", outcome.data.get("outcome") if outcome else None)
    result = tool_result(m, mark, turn_id, "kill_session")
    rec.equal("stream.tool_result_not_error", False, detail(result).get("is_error"))
    rec.check("tmux.gone_after_the_decision", await_gone(m, sid), "the pane is gone after the approval", pane_alive(m, sid))
    await_end(turn_id)
    kills = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.kill_row", len(kills) == 1 and kills[0].get("decision") == "allow" and kills[0].get("approved_by") == "user"
              and kills[0].get("approval_id") == approval_id and kills[0].get("actor_kind") == "master",
              "kill_session: allow, approved_by user, approval_id A, actor master",
              shape(kills, "decision", "approved_by", "approval_id", "actor_kind"))
    decides = rows_for(m, amark, "decide_approval")
    rec.check("logs.decide_row", len(decides) == 1 and decides[0].get("actor_kind") == "human"
              and decides[0].get("approved_by") == "claimed_human", "decide_approval: actor human, claimed_human",
              shape(decides, "actor_kind", "approved_by"))
    rec.check("db.ended_at", bool(session_row(m, sid).get("ended_at")), "S has ended_at", session_row(m, sid).get("ended_at"))
    rec.finish()


# ----- M4 ------------------------------------------------------------------------------


@scenario("M4")
def test_m4_reject_denies_the_call_and_says_so_to_the_master(m: Master, rec: Recorder) -> None:
    sid = spawn_user(m, "QA6 M4")
    mark, amark = m.stream.mark(), m.audit.mark()
    turn_id = str(send(m, kill_turn(sid, "QA6 M4"), "QA6 M4").get("turn_id"))
    pending = card(m, mark, "kill_session")
    if pending is None:
        rec.block("given.card", "no approval.created")
        rec.finish()
        return
    approval_id = str(pending.data.get("approval_id"))
    rec.check("tmux.alive_while_pending", pane_alive(m, sid), "the pane is alive while pending", pane_alive(m, sid))
    status, verdict = decide(m, approval_id, "reject")
    rec.equal("api.decided_rejected", (200, True, "rejected"), (status, verdict.get("decided"), verdict.get("outcome")))
    outcome = decided(m, mark, approval_id)
    rec.equal("stream.decided_rejected", "rejected", outcome.data.get("outcome") if outcome else None)
    result = tool_result(m, mark, turn_id, "kill_session")
    rec.equal("stream.tool_result_is_error", True, detail(result).get("is_error"))
    done = await_end(turn_id)
    text = done.results[0].text if done.results else ""
    rec.check("files.declined_text", DENIED in text, f"the adapter's tool-result content contains {DENIED!r}", text)
    rec.check("tmux.alive_after_reject", pane_alive(m, sid), "the pane is alive", pane_alive(m, sid))
    kills = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.deny_row", len(kills) == 1 and kills[0].get("decision") == "deny" and kills[0].get("result") == "denied"
              and kills[0].get("approved_by") is None and kills[0].get("approval_id") == approval_id,
              "kill_session: deny, result denied, approved_by null, approval_id A",
              shape(kills, "decision", "result", "approved_by", "approval_id"))
    kill_http(m, sid)
    rec.finish()


# ----- M5 ------------------------------------------------------------------------------


@scenario("M5")
def test_m5_a_second_decision_is_a_noop_bad_decisions_are_refused(m: Master, rec: Recorder) -> None:
    sessions = [spawn_user(m, f"QA6 M5 {label}") for label in ("A", "B", "C")]
    mark, amark = m.stream.mark(), m.audit.mark()
    ids: dict[str, str] = {}
    # card A: approve twice
    turn_a = str(send(m, kill_turn(sessions[0], "QA6 M5 A"), "QA6 M5 A").get("turn_id"))
    a = card(m, mark, "kill_session")
    if a is None:
        rec.block("given.card_a", "no card A")
        rec.finish()
        return
    ids["A"] = str(a.data.get("approval_id"))
    first = decide(m, ids["A"], "approve")
    rec.equal("api.a_first_decided", (200, True), (first[0], first[1].get("decided")))
    if active(MUT_PP2):
        rec.note(f"QA6 MUTATION {MUT_PP2} APPLIED: the second approve on A ({ids['A']}) was not sent")
    else:
        second = decide(m, ids["A"], "approve")
        rec.equal("api.a_second_noop", (200, False), (second[0], second[1].get("decided")))
    await_end(turn_a)
    # card B: two threads decide at the same instant
    turn_b = str(send(m, kill_turn(sessions[1], "QA6 M5 B"), "QA6 M5 B").get("turn_id"))
    b = card(m, mark, "kill_session", skip=1)
    if b is None:
        rec.block("given.card_b", "no card B")
        rec.finish()
        return
    ids["B"] = str(b.data.get("approval_id"))
    barrier = threading.Barrier(2)
    outcomes: dict[str, tuple[int, dict[str, object]]] = {}

    def racer(choice: str) -> None:
        barrier.wait(timeout=10)
        outcomes[choice] = decide(m, ids["B"], choice)

    threads = [threading.Thread(target=racer, args=(choice,)) for choice in ("approve", "reject")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    winners = [choice for choice, (_s, data) in outcomes.items() if data.get("decided") is True]
    rec.equal("api.b_exactly_one_decided", 1, len(winners))
    await_end(turn_b)
    b_frame = decided(m, mark, ids["B"])
    expected_outcome = {"approve": "approved", "reject": "rejected"}.get(winners[0]) if len(winners) == 1 else None
    rec.equal("stream.b_outcome_matches_winner", expected_outcome, b_frame.data.get("outcome") if b_frame else None)
    # a random id
    random_answer = decide(m, "01M3QA6NOSUCHAPPROVAL00000", "approve")
    rec.equal("api.random_id_not_decided", (200, False), (random_answer[0], random_answer[1].get("decided")))
    # card C: a bad choice
    turn_c = str(send(m, kill_turn(sessions[2], "QA6 M5 C"), "QA6 M5 C").get("turn_id"))
    c = card(m, mark, "kill_session", skip=2)
    if c is None:
        rec.block("given.card_c", "no card C")
        rec.finish()
        return
    ids["C"] = str(c.data.get("approval_id"))
    maybe_mark = m.audit.mark()
    maybe = post(m, f"/api/approvals/{ids['C']}", {"choice": "maybe"})
    rec.check("api.maybe_400", not generic_error_problems(maybe, 400), "maybe -> 400 generic", (maybe.status, maybe.text[:200]))
    maybe_rows = rows_for(m, maybe_mark, "decide_approval")
    rec.check("logs.maybe_row_refused", [r.get("result") for r in maybe_rows] == ["refused"],
              "one decide_approval row for maybe, result refused", shape(maybe_rows, "result", "decision"))
    listed = {str(as_dict(x).get("approval_id")) for x in as_list(m.client.get("/api/approvals").data().get("approvals"))}
    rec.check("api.list_a_b_absent_c_listed", ids["A"] not in listed and ids["B"] not in listed and ids["C"] in listed,
              "A and B absent, C listed", sorted(listed))
    decide(m, ids["C"], "reject")
    await_end(turn_c)
    decided_frames = frames(m, mark, "approval.decided")
    per_card = {name: len([f for f in decided_frames if f.data.get("approval_id") == aid]) for name, aid in ids.items()}
    rec.equal("stream.one_decided_per_card", {"A": 1, "B": 1, "C": 1}, per_card)
    decide_rows = rows_for(m, amark, "decide_approval")
    a_rows = [r for r in decide_rows if as_dict(r.get("args")).get("approval_id") == ids["A"]]
    rec.equal("logs.two_decide_rows_for_a", 2, len(a_rows))
    kill_rows = rows_for(m, amark, "kill_session")
    per_kill = {name: len([r for r in kill_rows if r.get("approval_id") == aid]) for name, aid in ids.items()}
    rec.equal("logs.one_kill_row_per_card", {"A": 1, "B": 1, "C": 1}, per_kill)
    for sid in sessions:
        if pane_alive(m, sid):
            kill_http(m, sid)
    rec.finish()


# ----- M6 ------------------------------------------------------------------------------


@scenario("M6")
def test_m6_interrupting_the_master_withdraws_its_pending_card(m: Master, rec: Recorder) -> None:
    rec.note("M6 label: no HTTP or UI path (Difference 3) — interrupt_master is invoked in-process with a HUMAN context")
    sid = spawn_user(m, "QA6 M6")
    withdrawn_before = m.client.fleet()
    before = as_dict(withdrawn_before.get("anomalies")).get("approval_withdrawn")
    mark, amark = m.stream.mark(), m.audit.mark()
    turn_id = str(send(m, kill_turn(sid, "QA6 M6"), "QA6 M6").get("turn_id"))
    pending = card(m, mark, "kill_session")
    if pending is None:
        rec.block("given.card", "no approval.created")
        rec.finish()
        return
    approval_id = str(pending.data.get("approval_id"))
    result = invoke("interrupt_master", {}, CallerContext(audience=Audience.HUMAN, caller_id="qa6-m6",
                                                          correlation_id=uuid4().hex))
    rec.equal("api.interrupted_true", {"interrupted": True}, result.data if result.ok else result.error)
    outcome = decided(m, mark, approval_id)
    rec.equal("stream.decided_withdrawn", "withdrawn", outcome.data.get("outcome") if outcome else None)
    done = await_end(turn_id)
    ends = [f.kind for f in turn_frames(m, mark, turn_id) if f.kind in ("master.error", "master.turn_ended")]
    rec.check("stream.turn_ends", bool(ends), "master.error (interrupted) or master.turn_ended", ends)
    late = decide(m, approval_id, "approve")
    rec.equal("api.late_approve_not_decided", (200, False), (late[0], late[1].get("decided")))
    text = done.results[0].text if done.results else ""
    rec.check("files.withdrawn_text", WITHDRAWN in text, f"the adapter's tool-result content contains {WITHDRAWN!r}", text)
    kills = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.deny_withdrawn", len(kills) == 1 and kills[0].get("decision") == "deny"
              and kills[0].get("approved_by") == "withdrawn", "kill_session: deny, approved_by withdrawn",
              shape(kills, "decision", "approved_by"))
    after = as_dict(m.client.fleet().get("anomalies")).get("approval_withdrawn")
    rec.check("api.anomaly_withdrawn_plus_one", isinstance(before, int) and isinstance(after, int) and after == before + 1,
              "APPROVAL_WITHDRAWN +1", (before, after))
    rec.check("tmux.alive", pane_alive(m, sid), "the pane is alive", pane_alive(m, sid))
    kill_http(m, sid)
    rec.finish()


# ----- M7 ------------------------------------------------------------------------------


@scenario("M7")
def test_m7_level_3_no_card_the_call_runs_and_the_audit_says_level_3(m: Master, rec: Recorder) -> None:
    sid = spawn_user(m, "QA6 M7")
    amark = m.audit.mark()
    level = set_level(m, 3)
    rec.equal("api.autonomy_3_from_2", {"level": 3, "previous": 2}, level)
    mark = m.stream.mark()
    turn_id = str(send(m, kill_turn(sid, "QA6 M7"), "QA6 M7").get("turn_id"))
    await_end(turn_id)
    call = next((f for f in turn_frames(m, mark, turn_id) if f.kind == "master.tool_call"), None)
    window_end = (call.received_at if call else time.monotonic()) + 3.0
    wait = window_end - time.monotonic()
    if wait > 0:
        time.sleep(wait)  # the plan's window: no approval.created within 3 s of master.tool_call
    control = run_control(m.stream, m.client, "M7", mark)
    rec.equal("stream.no_card", [], [f.data.get("tool") for f in control.interior if f.kind == "approval.created"])
    rec.check("tmux.pane_gone", await_gone(m, sid), "the pane is gone", pane_alive(m, sid))
    kills = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.kill_allow_policy", len(kills) == 1 and kills[0].get("decision") == "allow"
              and kills[0].get("approved_by") == "policy", "kill_session: allow, approved_by policy",
              shape(kills, "decision", "approved_by"))
    rec.equal("logs.kill_autonomy_level_3", [3], [r.get("autonomy_level") for r in kills])
    sets = rows_for(m, amark, "set_autonomy_level")
    rec.check("logs.set_level_claimed_human", bool(sets) and sets[0].get("approved_by") == "claimed_human",
              "set_autonomy_level: claimed_human", shape(sets, "approved_by"))
    rec.equal("db.autonomy_level_3", 3, app_state(m.db, "autonomy_level"))
    set_level(m, 2)
    rec.finish()


# ----- M8 ------------------------------------------------------------------------------


@scenario("M8")
def test_m8_a_level_change_between_two_calls_of_one_turn_applies_to_the_second(m: Master, rec: Recorder) -> None:
    one, two = spawn_user(m, "QA6 M8 one"), spawn_user(m, "QA6 M8 two")
    set_level(m, 2)
    mark, amark = m.stream.mark(), m.audit.mark()
    turn = Turn(says="QA6 M8", calls=[Call("kill_session", {"session_id": one}), Call("kill_session", {"session_id": two})])
    turn_id = str(send(m, turn, "QA6 M8").get("turn_id"))
    pending = card(m, mark, "kill_session")
    if pending is None:
        rec.block("given.card", "no card for S1")
        rec.finish()
        return
    set_level(m, 3)
    decide(m, str(pending.data.get("approval_id")), "approve")
    await_end(turn_id)
    cards = frames(m, mark, "approval.created")
    rec.check("stream.one_card_for_s1", len(cards) == 1 and f"session_id={one}" in str(cards[0].data.get("summary")),
              "one approval.created (S1), none for S2", [c.data.get("summary") for c in cards])
    kills = rows_for(m, amark, "kill_session", turn_id)
    by_target = {str(as_dict(r.get("args")).get("session_id")): r.get("approved_by") for r in kills}
    rec.equal("logs.s1_user_s2_policy", {one: "user", two: "policy"}, by_target)
    rec.check("tmux.both_gone", await_gone(m, one) and await_gone(m, two), "both panes gone",
              (pane_alive(m, one), pane_alive(m, two)))
    set_level(m, 2)
    rec.finish()


# ----- M9 ------------------------------------------------------------------------------


@scenario("M9")
def test_m9_the_gate_matrix_every_reachable_cell(m: Master, rec: Recorder) -> None:
    target = str(as_dict(m.client.create_project("QA6-M9-target").get("project")).get("project_id"))
    created: list[str] = []
    mark, amark = m.stream.mark(), m.audit.mark()
    for level in (2, 3):
        set_level(m, level)
        level_mark = m.stream.mark()
        turn = Turn(says=f"QA6 M9 L{level}", calls=[
            Call("fleet_summary", {}),
            Call("rename_project", {"project_id": target, "name": f"QA6-M9-master-renamed-L{level}"}),
            Call("create_project", {"name": f"QA6-M9-master-created-L{level}"}),
        ])
        turn_id = str(send(m, turn, f"QA6 M9 L{level}").get("turn_id"))
        if level == 2:
            pending = card(m, level_mark, "create_project")
            rec.check("stream.l2_card_for_create", pending is not None, "a card for master x create x level 2",
                      pending.data if pending else None)
            if pending is not None:
                decide(m, str(pending.data.get("approval_id")), "approve")
        done = await_end(turn_id)
        for result in done.results:
            if result.name == "create_project" and not result.is_error:
                created.append(project_id_from([result]))
        master_rows = {tool: rows_for(m, amark, tool, turn_id) for tool in ("fleet_summary", "rename_project", "create_project")}
        for tool in ("fleet_summary", "rename_project"):
            rec.check(f"logs.master_{tool}_l{level}", [r.get("decision") for r in master_rows[tool]] == ["allow"]
                      and master_rows[tool][0].get("approved_by") == "policy", "allow / policy",
                      shape(master_rows[tool], "decision", "approved_by"))
        expected_by = "user" if level == 2 else "policy"
        rec.check(f"logs.master_create_project_l{level}", [r.get("approved_by") for r in master_rows["create_project"]]
                  == [expected_by] and master_rows["create_project"][0].get("decision") == "allow",
                  f"allow / {expected_by}", shape(master_rows["create_project"], "decision", "approved_by"))
        human = {
            "fleet_summary": m.client.get("/api/fleet"),
            "rename_project": post(m, f"/api/projects/{target}/rename", {"name": f"QA6-M9-human-renamed-L{level}"}),
            "create_project": post(m, "/api/projects", {"name": f"QA6-M9-human-created-L{level}"}),
        }
        for tool, response in human.items():
            correlation = str(response.json().get("correlation_id"))
            rows = rows_for(m, amark, tool, correlation)
            rec.check(f"logs.human_{tool}_l{level}", len(rows) == 1 and rows[0].get("decision") == "allow"
                      and rows[0].get("approved_by") == "claimed_human", "allow / claimed_human",
                      shape(rows, "decision", "approved_by"))
            if tool == "create_project" and response.status == 200:
                created.append(str(as_dict(response.data().get("project")).get("project_id")))
    cards = frames(m, mark, "approval.created")
    rec.equal("stream.cards_only_master_destructive_l2", ["create_project"], [c.data.get("tool") for c in cards])
    names = {str(p.get("name")) for p in m.client.projects()}
    rec.check("api.renamed_and_created_exist", "QA6-M9-human-renamed-L3" in names
              and {"QA6-M9-master-created-L2", "QA6-M9-master-created-L3", "QA6-M9-human-created-L2",
                   "QA6-M9-human-created-L3"} <= names, "the renamed and created projects exist", sorted(names))
    set_level(m, 2)
    for project_id in [*created, target]:
        m.client.delete_project(project_id)
    rec.finish()


# ----- M10 -----------------------------------------------------------------------------


@scenario("M10")
def test_m10_the_master_cannot_call_a_tool_outside_its_audience(m: Master, rec: Recorder) -> None:
    first = Call("decide_approval", {"approval_id": "01M3QA6NOSUCHAPPROVAL00000", "choice": "approve"})
    if active(MUT_PP20):
        first = Call("get_autonomy_level", {})
        rec.note(f"QA6 MUTATION {MUT_PP20} APPLIED: the first call is get_autonomy_level (in the master's audience)")
    tools = [first.name, "get_audit_log", "no_such_tool"]
    mark, amark = m.stream.mark(), m.audit.mark()
    turn = Turn(says="QA6 M10", calls=[first, Call("get_audit_log", {}), Call("no_such_tool", {})])
    turn_id = str(send(m, turn, "QA6 M10").get("turn_id"))
    done = await_end(turn_id)
    results = [f for f in turn_frames(m, mark, turn_id) if f.kind == "master.tool_result"]
    rec.equal("stream.three_tool_results_is_error", [True, True, True], [detail(f).get("is_error") for f in results])
    literal = f"{GENERIC_ERROR} (correlation_id={turn_id})"
    rec.equal("files.generic_literal_with_turn_id", [literal] * 3, [r.text for r in done.results])
    audit = [dict(r) for r in m.audit.since(amark) if r.get("tool") in tools]
    rec.equal("logs.no_audit_rows", [], shape(audit, "tool", "decision"))
    control = run_control(m.stream, m.client, "M10", mark)
    rec.equal("api.nothing_decided_no_card", [], [f.kind for f in control.interior if f.kind.startswith("approval.")])
    rec.finish()


# ----- P10 -----------------------------------------------------------------------------


@scenario("P10")
def test_p10_the_masters_project_verbs_at_level_2(m: Master, rec: Recorder) -> None:
    set_level(m, 2)
    beta = os.path.realpath(m.run.repos / "beta")
    mark, amark = m.stream.mark(), m.audit.mark()
    turn = Turn(says="QA6 P10", calls=[
        Call("create_project", {"name": "QA6-P10"}),
        Call("add_repo", lambda results: {"project_id": project_id_from(results), "root_path": beta}),
        Call("delete_project", lambda results: {"project_id": project_id_from(results)}),
        Call("rename_project", lambda results: {"project_id": project_id_from(results), "name": "QA6-P10-renamed"}),
        Call("set_project_description", lambda results: {"project_id": project_id_from(results), "description": "QA6"}),
    ])
    turn_id = str(send(m, turn, "QA6 P10").get("turn_id"))
    observed: dict[str, object] = {}
    for index, tool in enumerate(("create_project", "add_repo", "delete_project")):
        pending = card(m, mark, tool)
        rec.check(f"stream.card_{tool}", pending is not None, f"approval.created for {tool}", pending.data if pending else None)
        if pending is None:
            break
        decide(m, str(pending.data.get("approval_id")), "approve")
        tool_result(m, mark, turn_id, tool)
        current = record(turn_id)
        project_id = project_id_from(current.results) if current and current.results else ""
        if index == 0:
            observed["after_create"] = m.client.get(f"/api/projects/{project_id}").data().get("found")
        elif index == 1:
            repos = [str(as_dict(r).get("root_path")) for r in as_list(m.client.get(f"/api/projects/{project_id}/repos")
                                                                        .data().get("repos"))]
            observed["after_add"] = beta in repos
        else:
            observed["after_delete"] = m.client.get(f"/api/projects/{project_id}").data().get("found")
    await_end(turn_id)
    rec.equal("api.exists_holds_gone", {"after_create": True, "after_add": True, "after_delete": False}, observed)
    cards = [c.data.get("tool") for c in frames(m, mark, "approval.created")]
    rec.equal("stream.cards_first_three_only", ["create_project", "add_repo", "delete_project"], cards)
    by_tool = {tool: [r.get("approved_by") for r in rows_for(m, amark, tool, turn_id)]
               for tool in ("create_project", "add_repo", "delete_project", "rename_project", "set_project_description")}
    rec.equal("logs.user_user_user_policy_policy", {"create_project": ["user"], "add_repo": ["user"], "delete_project": ["user"],
                                                   "rename_project": ["policy"], "set_project_description": ["policy"]},
              by_tool)
    rec.finish()
