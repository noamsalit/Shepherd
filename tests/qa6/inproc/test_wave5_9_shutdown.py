"""Wave 5, INP #1: M19 — shutdown withdraws a pending card and says so. **Last in its process.**

The file sorts last in `inproc/`, so every other INP #1 scenario has run. M19
calls `controld.stop(running)` — the function `main()` calls after SIGTERM —
on the composition itself, with one card pending. The lane's `inp` finaliser
then calls `stop` again, which is idempotent on a stopped composition (the
threads are joined and `Store.close` returns early), and restores the process
environment and kills this composition's tmux server as usual.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from shepherd.daemons import controld as controld_module

from ..inp import Inp
from ..inproc.master import Call, Turn
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Blocked, Recorder
from .test_wave5_1_support import Master, audit_file_view, card, open_master, send, set_level, spawn_user

#: test-plan M19, verbatim.
EXPECTED_LINE = "3 threads exited · store closed · 1 approvals withdrawn"
STOP_BOUND_S = 10.0  # plan M19: "stop returns within 10 s" (the product's join timeout, JOIN_TIMEOUT_S)


@pytest.fixture(scope="module")
def z(inp: Inp, qa6_run: RunContext) -> Iterator[Master]:
    master = open_master(inp, qa6_run, "Z19")
    try:
        yield master
    finally:
        master.stream.close()


@scenario("M19")
def test_m19_shutdown_withdraws_a_pending_card_and_says_so(z: Master, rec: Recorder) -> None:
    set_level(z, 2)
    sid = spawn_user(z, "QA6 M19")
    mark = z.stream.mark()
    answer = send(z, Turn(says="QA6 M19", calls=[Call("kill_session", {"session_id": sid})]), "QA6 M19")
    pending = card(z, mark, "kill_session")
    if pending is None:
        raise Blocked(f"M19 given: no card pending (send answered {answer!r})")
    audit_root = z.audit.root
    z.stream.close()
    outcome: dict[str, object] = {}

    def stopper() -> None:
        outcome["value"] = controld_module.stop(z.inp.running)

    started = time.monotonic()
    thread = threading.Thread(target=stopper, name="qa6-m19-stop", daemon=True)
    thread.start()
    thread.join(STOP_BOUND_S + 20.0)
    elapsed = time.monotonic() - started
    rec.check("proc.stop_within_10s", not thread.is_alive() and elapsed <= STOP_BOUND_S,
              f"stop returns within {STOP_BOUND_S}s", f"{elapsed:.2f}s alive={thread.is_alive()}")
    rec.equal("logs.stop_line", EXPECTED_LINE, str(outcome.get("value")))
    approval_id = str(pending.data.get("approval_id"))
    records, _text = audit_file_view(audit_root)
    rows = [r for r in records if r.get("approval_id") == approval_id]
    rec.check("logs.withdrawn_row", len(rows) == 1 and rows[0].get("approved_by") == "withdrawn"
              and rows[0].get("decision") == "deny", "the card's audit row: deny, approved_by withdrawn",
              [{k: r.get(k) for k in ("tool", "decision", "approved_by")} for r in rows])
    rec.finish()
