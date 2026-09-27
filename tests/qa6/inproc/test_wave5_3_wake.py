"""Wave 5, INP #1: D31's wake set and the turn failures around it — M11, M12, M13, M14, M18.

**The wake set is process state**, so this module is careful with it: it opens
with a drain turn (whatever the earlier modules left is consumed and recorded),
and every scenario that leaves a stopped master-spawned session behind ends
with a drain, so the next scenario starts from an empty set. A drain is an
ordinary user turn (`Turn(says="QA6-DRAIN …")`); its input text is recorded.

The master's sessions are spawned **by the master** (a scripted
`spawn_session` call → origin `orchestrator`, the only origin D31 selects);
the harness kills them over HTTP, which is how a session stops `killed` /
`unfinished` here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence

import pytest

from shepherd.host.mac import MacHost

from .. import tmuxctl
from ..httpclient import as_dict
from ..inp import Inp
from ..inproc import master as master_module
from ..inproc.master import BOOK, Call, CallResult, Turn
from ..sandbox import RunContext
from ..scenario import scenario
from ..instance import db_rows, start_helper
from ..sessions import sidecar, write_sidecar
from ..verdict import CONTROL_MULTIPLE, Blocked, Recorder, await_env, observe
from .test_wave5_1_support import (
    WAKE_HEADER,
    Master,
    anomaly,
    await_end,
    await_stopped,
    drain,
    kill_http,
    last_turn_at,
    open_master,
    pane_alive,
    record,
    result_json,
    rows_for,
    run_turn,
    send,
    session_row,
    set_level,
    shape,
    slot_free,
    spawn_call,
    spawn_user,
    turn_frames,
)

UNFINISHED_GLYPH = "◑"  # test-plan M11, verbatim
M12_BOUND_S = 30.0  # test-plan M12: "within 30 s of the kill — FAIL(bound)"
BOOM = "QA6-BUILD-BOOM"


@pytest.fixture(scope="module")
def w(inp: Inp, qa6_run: RunContext) -> Iterator[Master]:
    master = open_master(inp, qa6_run, "W")
    try:
        set_level(master, 2)
        drain(master, "wake-module-start")
        yield master
    finally:
        set_level(master, 2)
        master.stream.close()


def spawned_id(result: CallResult) -> str | None:
    value = result_json(result).get("session_id")
    return value if isinstance(value, str) else None


def master_spawn(m: Master, title: str, brief: str | None = None) -> str:
    """A master-spawned (origin orchestrator) session, or BLOCKED."""
    _turn_id, done = run_turn(m, Turn(says=f"QA6 spawn {title}", calls=[spawn_call(m, title, brief)]), f"spawn {title}")
    sid = spawned_id(done.results[0]) if done.results else None
    if sid is None:
        raise Blocked(f"precondition: the master's spawn_session({title!r}) did not spawn: "
                      f"{[r.text[:200] for r in done.results]}")
    return sid


def kill_and_wait(m: Master, sid: str) -> dict[str, object]:
    kill_http(m, sid)
    return await_stopped(m, sid)


# ----- M11 -----------------------------------------------------------------------------


@scenario("M11")
def test_m11_the_wake_summary_opens_the_next_turn_at_level_2(w: Master, rec: Recorder) -> None:
    amark = w.audit.mark()
    stamps = [last_turn_at(w)]
    sid = master_spawn(w, "QA6 W")
    stamps.append(last_turn_at(w))
    row = kill_and_wait(w, sid)
    rec.check("given.w_killed_unfinished", row.get("stop_reason") == "killed" and row.get("outcome") == "unfinished",
              "W stopped killed / unfinished", {k: row.get(k) for k in ("stop_reason", "outcome")})
    mark = w.stream.mark()
    turn2, done2 = run_turn(w, Turn(says="QA6 M11 turn 2"), "back")
    stamps.append(last_turn_at(w))
    turn3, done3 = run_turn(w, Turn(says="QA6 M11 turn 3"), "again")
    stamps.append(last_turn_at(w))
    text2 = done2.text
    lines = text2.splitlines()
    w_line = next((line for line in lines if "QA6 W" in line), "")
    rec.check("files.turn2_opens_with_header", text2.startswith(WAKE_HEADER), f"turn 2 input starts with {WAKE_HEADER!r}",
              text2[:300])
    rec.check("files.turn2_names_w_glyph_and_why", UNFINISHED_GLYPH in w_line and len([p for p in w_line.split("   ") if p.strip()]) >= 3,
              f"a line naming 'QA6 W' with {UNFINISHED_GLYPH} and a why", w_line)
    rec.check("files.turn2_blank_line_then_back", text2.endswith("\n\nback"), "…a blank line, then 'back'", text2[-80:])
    rec.equal("files.turn3_exactly_again", "again", done3.text)
    rec.equal("db.w_origin_orchestrator", "orchestrator", session_row(w, sid).get("origin"))
    rec.check("db.last_turn_at_moves_each_turn", all(a is not None and b is not None and b > a
                                                     for a, b in zip(stamps, stamps[1:], strict=False)),
              "master_last_turn_at strictly later at each turn", stamps)
    rec.check("stream.turns_2_and_3_stream", bool(turn_frames(w, mark, turn2)) and bool(turn_frames(w, mark, turn3)),
              "master.* frames for turns 2 and 3", (len(turn_frames(w, mark, turn2)), len(turn_frames(w, mark, turn3))))
    spawns = [r for r in rows_for(w, amark, "spawn_session") if r.get("actor_kind") == "master"]
    kills = [r for r in rows_for(w, amark, "kill_session") if as_dict(r.get("args")).get("session_id") == sid]
    rec.check("logs.spawn_and_kill_audited", len(spawns) == 1 and len(kills) == 1 and kills[0].get("actor_kind") == "human",
              "one master spawn_session row, one human kill_session row", (shape(spawns, "actor_kind"), shape(kills, "actor_kind")))
    rec.finish()


# ----- M12 -----------------------------------------------------------------------------


@scenario("M12")
def test_m12_level_3_a_stopped_master_spawned_session_wakes_the_master_immediately(w: Master, rec: Recorder) -> None:
    set_level(w, 3)
    try:
        runtimes = BOOK.runtimes
        sent_at = time.monotonic()
        answer = send(w, Turn(says="QA6 M12 turn 1", calls=[spawn_call(w, "QA6 W2")]), "QA6 M12 turn 1")
        await_env(lambda: BOOK.runtimes > runtimes or None, 10.0, "the factory for M12's user turn")
        control = max(time.monotonic() - sent_at, 1e-3)
        rec.record("files.control_user_turn_factory_latency_s", round(control, 3))
        done = await_end(answer.get("turn_id"))
        sid = spawned_id(done.results[0]) if done.results else None
        if sid is None:
            raise Blocked(f"M12 given: W2 was not spawned: {[r.text[:200] for r in done.results]}")
        known = {r.turn_id for r in BOOK.records}
        before_stamp = last_turn_at(w)
        mark = w.stream.mark()
        runtimes = BOOK.runtimes
        kill_and_wait(w, sid)
        woke, elapsed = observe(lambda: BOOK.runtimes > runtimes or None, M12_BOUND_S)
        if woke:
            rec.check("files.factory_invoked_for_a_new_turn", True, f"a new turn within {M12_BOUND_S}s", f"{elapsed:.2f}s")
        elif M12_BOUND_S >= CONTROL_MULTIPLE * control:
            rec.fail_bound("files.factory_invoked_for_a_new_turn", "the master factory invoked for a new turn after "
                           "W2's stop, with no user message", M12_BOUND_S, f"M12's user-triggered turn: {control:.3f}s")
        else:
            rec.block("files.factory_invoked_for_a_new_turn", f"no new turn within {M12_BOUND_S}s and the control "
                      f"({control:.3f}s) does not qualify the bound")
        new_turns = {str(f.data.get("turn_id")) for f in w.stream.since(mark) if f.kind.startswith("master.")} - known
        if new_turns:
            rec.check("stream.master_events_new_turn", True, "master.* for a new turn id", sorted(new_turns))
        elif M12_BOUND_S >= CONTROL_MULTIPLE * control:
            rec.fail_bound("stream.master_events_new_turn", "master.* events for a new turn id", M12_BOUND_S,
                           f"M12's user-triggered turn: {control:.3f}s")
        after_stamp = last_turn_at(w)
        rec.check("db.last_turn_at_moves", after_stamp is not None and before_stamp is not None and after_stamp > before_stamp,
                  "master_last_turn_at moves without a user turn", (before_stamp, after_stamp))
    finally:
        set_level(w, 2)
    leftover = drain(w, "after-M12")
    rec.record("files.drain_after_m12_input", leftover.text[:400])
    rec.finish()


# ----- M13 -----------------------------------------------------------------------------


def pane_pid(m: Master, session_id: str) -> int | None:
    done = tmuxctl.run(m.socket, m.run.pid, "list-panes", "-t", tmuxctl.target(f"shepherd_{session_id}"),
                       "-F", "#{pane_pid}", check=False)
    lines = done.stdout.strip().splitlines()
    return int(lines[0]) if done.returncode == 0 and lines and lines[0].isdigit() else None


@scenario("M13")
def test_m13_the_wake_set_excludes_what_the_spec_excludes(w: Master, rec: Recorder) -> None:
    rec.note("M13's needs_you state is a fixture for the state: a waiting sidecar for the master-spawned session's "
             "engine id, pid = its pane pid (fixture-fiction for the state; the exclusion is the oracle)")
    needs = master_spawn(w, "QA6 M13 needs")
    row = session_row(w, needs)
    pid = pane_pid(w, needs)
    liveness = MacHost().process_liveness(pid, None) if pid is not None else None
    if pid is not None and liveness is not None and liveness.start_token is not None:
        body = sidecar(pid=pid, proc_start=liveness.start_token, cwd=str(w.alpha), session_id=str(row.get("engine_session_id")),
                       status="waiting", waiting_for="QA6 M13 permission?", name="QA6 M13 needs")
        write_sidecar(w.inp.root.sessions, body)
    reached, _ = observe(lambda: session_row(w, needs).get("state") == "needs_you" or None, 8.0)
    if not reached:
        rec.block("given.master_session_needs_you", f"the master-spawned session never read needs_you "
                  f"(state {session_row(w, needs).get('state')!r}); the needs_you exclusion is unexercised")
    user = spawn_user(w, "QA6 M13 user")
    kill_and_wait(w, user)
    helper = start_helper(w.run)
    attached_body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(w.run.repos / "loose"), name="QA6 M13 att")
    write_sidecar(w.inp.root.sessions, attached_body)
    engine = str(attached_body["sessionId"])
    registered = await_env(lambda: session_row_by_engine(w, engine), 8.0, "the attached session registered")
    helper.end()
    (w.inp.root.sessions / f"{attached_body['pid']}.json").unlink()
    await_stopped(w, str(registered.get("id")), 8.0)
    stamps = [last_turn_at(w)]
    _t1, first = run_turn(w, Turn(says="QA6 M13 turn 1"), "QA6 M13 turn 1")
    stamps.append(last_turn_at(w))
    _t2, second = run_turn(w, Turn(says="QA6 M13 turn 2"), "QA6 M13 turn 2")
    stamps.append(last_turn_at(w))
    rec.check("files.neither_turn_has_the_header", WAKE_HEADER not in first.text and WAKE_HEADER not in second.text,
              f"neither input contains {WAKE_HEADER!r}", (first.text[:300], second.text[:300]))
    rec.check("db.last_turn_at_moves_both_turns", all(a is not None and b is not None and b > a
                                                      for a, b in zip(stamps, stamps[1:], strict=False)),
              "master_last_turn_at moves at both turns", stamps)
    sidecar_file = w.inp.root.sessions / f"{pid}.json" if pid is not None else None
    if sidecar_file is not None and sidecar_file.exists():
        sidecar_file.unlink()
    kill_and_wait(w, needs)
    drain(w, "after-M13")
    rec.finish()


def session_row_by_engine(m: Master, engine: str) -> dict[str, object] | None:
    rows = db_rows(m.db, "SELECT * FROM session WHERE engine_session_id = ?", (engine,))
    return rows[0] if rows else None


# ----- M14 -----------------------------------------------------------------------------


RETRY_BRIEF = "QA6 retry brief"


def retry_call(m: Master, title: str, retry_of: Callable[[Sequence[CallResult]], str]) -> Call:
    """A master `spawn_session` that **declares** what it retries (§3 D70); the target may be
    an earlier call's answer in the same turn, so the args are computed when the call runs."""
    def args(results: Sequence[CallResult]) -> Mapping[str, object]:
        return {"workspace_id": m.project_id, "cwd": str(m.alpha), "title": title, "brief": RETRY_BRIEF,
                "retry_of": retry_of(results)}
    return Call("spawn_session", args)


def kill_through_the_wake(m: Master, sid: str, rec: Recorder) -> None:
    """Kill `sid` at level 3 with the wake it opens **scripted, not raced** (B5b).

    The kill ends `killed` / `unfinished`, so level 3 opens an unprompted turn for it, which
    pops the book like any turn. The no-op wake turn is pushed first, and the scenario waits
    until it ran and the slot is free, so the retry script cannot be taken by the wake. A wake
    that never arrives is BLOCKED here, never a FAIL: M12 owns that clause.
    """
    if BOOK.pending():
        raise Blocked(f"harness: {BOOK.pending()} scripted turn(s) left in the book before M14's wake")
    BOOK.push(Turn(says="QA6 M14 wake"))
    before = last_turn_at(m)
    kill_and_wait(m, sid)
    await_env(lambda: (BOOK.pending() == 0 and slot_free() and (last_turn_at(m) or "") > (before or "")) or None,
              M12_BOUND_S, "X's level-3 wake turn opened and ended")
    woke = BOOK.records[-1] if BOOK.records else None
    rec.record("stream.x_stop_woke_the_master", {"last_turn_at": last_turn_at(m),
                                                 "wake_input": woke.text[:300] if woke is not None else None})


@scenario("M14")
def test_m14_the_retry_cap_refuses_a_third_master_retry_end_to_end(w: Master, rec: Recorder) -> None:
    rec.note("M14: a retry is declared with spawn_session's retry_of (§3 D70), and only a stopped attempt is retried. "
             "The cap counts attempts including the original (t10.md §T10-2), so X and its retry r1 fill the lineage "
             "and a retry of r1 is the refused third; a second retry of X is refused by RD-2, naming r1, and at a full "
             "lineage that is the cap too (D70 refinement: cap retry_cap_reached, counted, the human named)")
    drain(w, "before-M14")
    set_level(w, 3)
    spawned: list[str] = []
    amark = w.audit.mark()
    try:
        cap_before = anomaly(w, "wake_retry_cap_reached")
        x = master_spawn(w, "QA6 X", RETRY_BRIEF)
        spawned.append(x)
        kill_through_the_wake(w, x, rec)
        _turn, done = run_turn(w, Turn(says="QA6 M14 retry", calls=[retry_call(w, "QA6 X retry 1", lambda _results: x)]),
                               "QA6 M14 retry")
        first = (([result_json(r) for r in done.results]) or [{}])[0]
        r1 = first.get("session_id")
        if first.get("spawned") is not True or not isinstance(r1, str):
            raise Blocked(f"precondition: the master's retry of X did not spawn: {first!r}")
        spawned.append(r1)
        set_level(w, 2)  # r1 must be stopped to be retried; at level 2 its stop opens no wake and bumps nothing (RD-3)
        kill_and_wait(w, r1)
        drain(w, "M14-r1")
        set_level(w, 3)
        retries = Turn(says="QA6 M14 retries", calls=[retry_call(w, "QA6 X retry of r1", lambda _results: r1),
                                                      retry_call(w, "QA6 X retry 2", lambda _results: x)])
        _turn, done = run_turn(w, retries, "QA6 M14 retries")
        answers = [result_json(r) for r in done.results] + [{}, {}]
        capped, sibling = answers[0], answers[1]
        spawned.extend(str(a.get("session_id")) for a in answers[:2] if a.get("spawned") is True)
        rec.check("api.retry_of_the_retry_refused_at_the_cap",
                  capped.get("spawned") is False and capped.get("cap") == "retry_cap_reached",
                  "{spawned:false, cap:'retry_cap_reached'}", capped)
        rec.equal("api.anomaly_retry_cap_plus_two", cap_before + 2, anomaly(w, "wake_retry_cap_reached"))
        refusal = str(sibling.get("refusal"))
        rec.check("api.second_retry_of_x_refused_naming_r1",
                  sibling.get("spawned") is False and sibling.get("cap") == "retry_cap_reached"
                  and "already retried" in refusal and r1 in refusal and "human" in refusal,
                  "{spawned:false, cap:'retry_cap_reached'}, a reason naming r1 ('already retried') and the human",
                  {"r1": r1, "answer": sibling})
        rec.equal("db.r1_retry_of_is_x", x, session_row(w, r1).get("retry_of"))
        spawn_rows = rows_for(w, amark, "spawn_session")
        rec.check("logs.spawns_audited", len(spawn_rows) == 4 and all(r.get("actor_kind") == "master" for r in spawn_rows),
                  "four master spawn_session rows (X plus three)", shape(spawn_rows, "actor_kind", "result"))
    finally:
        set_level(w, 2)  # before the kills: a stop at level 2 opens no wake and bumps nothing (RD-3)
        for sid in spawned:
            if pane_alive(w, sid):
                kill_and_wait(w, sid)
        BOOK.clear()
    drain(w, "after-M14")
    rec.finish()


# ----- M18 -----------------------------------------------------------------------------


class _Boom:
    """The harness factory's failure for one turn: `ToolCallingMaster(...)` raises."""

    def __init__(self, turn_id: str, *_args: object) -> None:
        raise RuntimeError(BOOM)


@scenario("M18")
def test_m18_a_failed_turn_is_reported_without_internals_and_the_slot_is_freed(
    w: Master, rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark = w.stream.mark()
    # (a) a scripted error turn
    turn_a = send(w, Turn(says="x", ends="error"), "QA6 M18 (a)")
    await_end(turn_a.get("turn_id"))
    errors = [f for f in turn_frames(w, mark, turn_a.get("turn_id")) if f.kind == "master.error"]
    rec.check("stream.a_master_error_with_turn_id", len(errors) == 1, "master.error with the turn id",
              [f.kind for f in turn_frames(w, mark, turn_a.get("turn_id"))])
    # (c)'s setup, and (a)'s "the next send starts": the master spawns W, then W is killed
    following = send(w, Turn(says="QA6 M18 spawn", calls=[spawn_call(w, "QA6 M18 W")]), "QA6 M18 spawn")
    rec.equal("api.a_next_send_starts", True, following.get("started"))
    spawn_done = await_end(following.get("turn_id"))
    wsid = spawned_id(spawn_done.results[0]) if spawn_done.results else None
    if wsid is None:
        raise Blocked(f"M18(c) given: the master did not spawn W: {[r.text[:200] for r in spawn_done.results]}")
    kill_and_wait(w, wsid)
    # (b) the factory raises for this turn
    before = last_turn_at(w)
    monkeypatch.setattr(master_module, "ToolCallingMaster", _Boom)
    rec.note(f"M18(b): the harness factory raises RuntimeError({BOOM!r}) for one send (the harness class is patched, "
             "never the product)")
    try:
        refused = send(w, None, "QA6 M18 (b)")
    finally:
        monkeypatch.undo()
    after = last_turn_at(w)
    reason = str(refused.get("reason"))
    rec.check("api.b_not_started_no_internals", refused.get("started") is False and "RuntimeError" not in reason
              and BOOM not in reason and "Error(" not in reason,
              "{started:false}, reason with no RuntimeError, no QA6-BUILD-BOOM, no repr (S8)", refused)
    rec.record("db.b_master_last_turn_at", {"before": before, "after": after})
    # (c) the next normal turn still opens with the summary
    _turn_c, done_c = run_turn(w, Turn(says="QA6 M18 (c)"), "QA6 M18 (c)")
    rec.check("files.c_summary_not_lost", done_c.text.startswith(WAKE_HEADER), f"(c) opens with {WAKE_HEADER!r}",
              done_c.text[:300])
    drain(w, "after-M18")
    rec.finish()
