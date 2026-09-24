"""Wave 5, INP-long: M17 — an unanswered approval times out at 600 s (C-21).

Its own pytest process and composition (the runner starts this lane in the
background at wave 5's start and joins it before wave 9), because the card
holds the turn slot for the whole window. The 630 s wait is the plan's own
observation window (BUILDING §2) and the 600 s is a sourced product constant
(`policy.APPROVAL_TIMEOUT_S`, which the authorizer waits for whatever the
injected `timeout_s` says — T6), so a missing `timed_out` is FAIL(bound).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from ..inp import Inp
from ..inproc.master import Call, Turn
from ..inproc.test_wave5_1_support import (
    Master,
    anomaly,
    await_end,
    card,
    decide,
    decided,
    kill_http,
    open_master,
    pane_alive,
    rows_for,
    send,
    shape,
    spawn_user,
)
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Blocked, Recorder, Sourced

TIMEOUT = Sourced(600.0, "toolsurface/policy.py APPROVAL_TIMEOUT_S = 600.0 (the authorizer's wait, T6/C-21)")
WINDOW_S = 630.0  # test-plan M17: "do nothing for 630 s"
TIMED_OUT_TEXT = "approval timed out — proceed without it or ask me directly"  # plan M17, verbatim


@pytest.fixture(scope="module")
def long(inp: Inp, qa6_run: RunContext) -> Iterator[Master]:
    master = open_master(inp, qa6_run, "M17")
    try:
        yield master
    finally:
        master.stream.close()


@scenario("M17")
def test_m17_an_unanswered_approval_times_out_at_600_s(long: Master, rec: Recorder) -> None:
    m = long
    sid = spawn_user(m, "QA6 M17")
    before = anomaly(m, "approval_timed_out")
    mark, amark = m.stream.mark(), m.audit.mark()
    turn_id = str(send(m, Turn(says="QA6 M17", calls=[Call("kill_session", {"session_id": sid})]), "QA6 M17").get("turn_id"))
    pending = card(m, mark, "kill_session")
    if pending is None:
        raise Blocked("M17 given: no approval.created")
    approval_id = str(pending.data.get("approval_id"))
    created_at = pending.received_at
    rec.note(f"M17: card {approval_id} created; observing up to {WINDOW_S}s for approval.decided")
    frame = decided(m, mark, approval_id, bound_s=WINDOW_S - (time.monotonic() - created_at))
    arrived = (frame.received_at - created_at) if frame is not None else None
    if frame is None:
        rec.fail_bound("stream.timed_out_600_to_630", "approval.decided timed_out", WINDOW_S, TIMEOUT.source)
    else:
        rec.check("stream.timed_out_600_to_630", frame.data.get("outcome") == "timed_out" and arrived is not None
                  and TIMEOUT.seconds <= arrived <= WINDOW_S,
                  "approval.decided timed_out between 600 s and 630 s after creation",
                  {"outcome": frame.data.get("outcome"), "after_s": round(arrived or -1.0, 2)})
    remaining = WINDOW_S - (time.monotonic() - created_at)
    if remaining > 0:
        time.sleep(remaining)  # the plan's window: "do nothing for 630 s; then approve"
    late = decide(m, approval_id, "approve")
    rec.equal("api.late_approve_not_decided", (200, False), (late[0], late[1].get("decided")))
    done = await_end(turn_id, 30.0)
    text = done.results[0].text if done.results else ""
    rec.check("files.timed_out_text", TIMED_OUT_TEXT in text, f"the adapter's tool-result text contains {TIMED_OUT_TEXT!r}",
              text)
    kills = rows_for(m, amark, "kill_session", turn_id)
    rec.check("logs.deny_timeout", len(kills) == 1 and kills[0].get("decision") == "deny"
              and kills[0].get("approved_by") == "timeout", "kill_session: deny, approved_by timeout",
              shape(kills, "decision", "approved_by"))
    rec.equal("api.anomaly_timed_out_plus_one", before + 1, anomaly(m, "approval_timed_out"))
    rec.check("tmux.pane_alive", pane_alive(m, sid), "the pane is alive", pane_alive(m, sid))
    rec.record("stream.deadline_at", pending.data.get("deadline_at"))
    kill_http(m, sid)
    rec.finish()
