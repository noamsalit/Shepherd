"""Wave 4, SUB lane: O11 — owned panes survive a controld restart and stay killable.

Its own instance: the scenario SIGTERMs its daemon (our recorded child only),
leaves the panes in the instance's tmux server, and restarts the console
script on the **same** HOME/TMPDIR and port (BUILDING §3; a failed re-bind is
BLOCKED). The first instance's SSE subscriber is closed before the stop — a
stream the server ends is a reader fault, not a frame.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from ..auditprobe import AuditProbe
from ..httpclient import as_dict
from ..instance import Controld, RestartFailed, wait_restart_ready
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..sse_rig import subscribe
from ..verdict import Blocked, Recorder, observe
from .test_wave4_0_support import (
    Owned,
    argvs_naming,
    await_frame,
    kill,
    open_owned,
    owned_panes,
    pane_alive,
    session_db_row,
    socket_ok,
    spawn_ok,
    tmux_argvs,
)


@dataclass
class Restart:
    env: Owned
    second: Owned | None = None


@pytest.fixture(scope="module")
def restart(pool: InstancePool, qa6_run: RunContext) -> Iterator[Restart]:
    state = Restart(env=open_owned(pool, qa6_run, "O11"))
    try:
        yield state
    finally:
        for env in (state.env, state.second):
            if env is not None:
                env.stream.close()
        if state.second is not None:
            # Stopped here, before the pool's teardown: both instances share one
            # root, so the first's "left its socket" check would otherwise read
            # the second's live socket (E5/D10 stop theirs in-scenario too).
            state.second.controld.stop()


def restarted(first: Owned) -> Owned:
    old: Controld = first.controld
    second = first.pool.start(old.root, port=old.port, name="controld-restart")
    try:
        wait_restart_ready(second)
    except Blocked as blocked:  # EADDRINUSE only (H2)
        second.stop()
        raise Blocked(f"O11: the OS would not re-bind port {old.port}: {blocked.reason}") from blocked
    except RestartFailed:
        second.stop()
        raise
    return Owned(controld=second, run=first.run, pool=first.pool, stream=subscribe("O11-after", second.port),
                 audit=AuditProbe.for_instance(second.root), project_id=first.project_id, alpha=first.alpha)


@scenario("O11")
def test_o11_owned_panes_survive_a_controld_restart_and_stay_killable(restart: Restart, rec: Recorder) -> None:
    env = restart.env
    one = spawn_ok(env, "QA6 O11 one")
    two = spawn_ok(env, "QA6 O11 two")
    env.stream.close()
    code = env.controld.stop()
    rec.record("proc.first_stop", {"code": code, "line": env.controld.stop_line})
    rec.check("tmux.both_panes_after_stop", pane_alive(env, one) and pane_alive(env, two),
              "both panes present while controld is down", owned_panes(env))
    tmark = len(tmux_argvs(env.run))
    try:
        second = restarted(env)
    except RestartFailed as failed:  # the product did not come back on its own root: FAIL, not BLOCKED (H2)
        rec.check("proc.restart_ready", False, "the restarted controld is ready on the same root and port", str(failed))
        rec.finish()
        return
    restart.second = second
    rec.check("tmux.both_panes_after_restart", pane_alive(second, one) and pane_alive(second, two),
              "both panes present after the restart", owned_panes(second))
    rows = {sid: session_db_row(second, sid) or {} for sid in (one, two)}
    rec.check("db.both_owned_after_restart", all(r.get("ownership") == "owned" for r in rows.values()),
              "both rows still owned", {sid: r.get("ownership") for sid, r in rows.items()})
    anomalies = as_dict(second.client.fleet().get("anomalies"))
    rec.record("db.anomalies_after_reconcile", {k: v for k, v in anomalies.items() if v})
    listing = argvs_naming(tmux_argvs(env.run)[tmark:], "list-sessions")
    rec.check("tmux.argv", bool(listing) and all(socket_ok(argv, second.socket) for argv in listing),
              f"the reconcile's list-sessions argv on -L {second.socket} after the restart", listing[:3])
    mark = second.stream.mark()
    answer = kill(second, one)
    data = answer.data() if answer.status == 200 else {}
    rec.equal("api.kill_after_restart", True, data.get("killed"))
    gone, _ = observe(lambda: (not pane_alive(second, one)) or None, 5.0)
    rec.check("tmux.one_gone_after_kill", bool(gone) and pane_alive(second, two), "one pane gone, the other present",
              owned_panes(second))
    other = as_dict(second.client.session(two).get("session"))
    rec.equal("api.other_still_owned", "owned", other.get("ownership"))
    rec.check("stream.session_killed", await_frame(second.stream, mark, "session.killed", one, 5.0) is not None,
              "session.killed for the killed one", [f.kind for f in second.stream.since(mark)])
    kill(second, two)
    rec.finish()
