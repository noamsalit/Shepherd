"""Wave 4, SUB lane: O10 — ask forks the engine and hides the fork (spec O53).

**One harness departure, stated.** The run's fake `claude` answers a `-p`
invocation with the bare line `QA6-FORK-ANSWER`, but the product's `ask()`
parses the engine's `-p --output-format json` **result object**
(`engines/claude_code/fork.py::parse_fork_result`; the captured shape is
`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/03-fork-nsp-with-session-id.stdout.json`),
so against the bare line the product would answer `text:null` for a reason
that is the shim's, not the product's. This module therefore puts a small
wrapper named `claude` ahead of the run's shim on this one instance's `PATH`,
generated at run time inside the instance root (removed with it):

* a `-p` invocation (an option before `--`) runs the run's own shim — which
  logs the argv to the run's claude-argv log exactly as before and prints
  `QA6-FORK-ANSWER` — and re-emits that answer inside the captured result
  object's four read fields (`type`, `subtype`, `is_error`, `result`,
  `session_id` = the `--session-id` it was given, as P2 measured);
* every other invocation `exec`s the run's shim unchanged (spawn fidelity is
  W5's proof and is untouched).

The wrapper carries no signal, kill or teardown verb. The shared shim's gap is
reported as a SCOPE_INCREASE with the diff that would make this unnecessary.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..httpclient import as_dict, as_list
from ..instance import Controld, db_rows, seed_db
from ..pool import InstancePool
from ..sandbox import RunContext, mint_instance, sandbox_env
from ..scenario import scenario
from ..verdict import Blocked, Recorder
from .test_wave4_0_support import Owned, claude_argvs, kill, open_owned, post_json, session_db_row, spawn_ok

WRAPPER = """#!/bin/sh
# QA6 O10 wrapper (tests/qa6/sub/test_wave4_3_ask.py): re-emits the run shim's -p answer
# inside the engine's captured -p JSON result object. No signal, kill or teardown verb.
for arg in "$@"; do
  if [ "$arg" = "--" ]; then break; fi
  if [ "$arg" = "-p" ] || [ "$arg" = "--print" ]; then
    answer=$('@SHIM@' "$@")
    sid=""
    prev=""
    for word in "$@"; do
      if [ "$prev" = "--session-id" ]; then sid="$word"; fi
      prev="$word"
    done
    printf '{"type":"result","subtype":"success","is_error":false,"result":"%s","session_id":"%s"}\\n' "$answer" "$sid"
    exit 0
  fi
done
exec '@SHIM@' "$@"
"""
ASK_HANG_GUARD_S = 150.0  # the product's own ask budget is ASK_TIMEOUT_MS = 120 s


def ready_with_wrapper(pool: InstancePool, run: RunContext) -> Controld:
    root = mint_instance(run)
    seed_db(root, runner_socket=run.runner_socket(root.k))
    bindir = root.root / "o10-bin"
    bindir.mkdir(mode=0o700)
    wrapper = bindir / "claude"
    wrapper.write_text(WRAPPER.replace("@SHIM@", str(run.shims / "claude")), encoding="utf-8")
    wrapper.chmod(0o755)
    child_env = sandbox_env(run, root, path_mode="shims")
    child_env["PATH"] = f"{bindir}:{child_env['PATH']}"
    controld = pool.start(root, env=child_env)
    try:
        controld.wait_ready()
    except Blocked:
        controld.stop()
        raise
    return controld


@pytest.fixture(scope="module")
def ask_env(pool: InstancePool, qa6_run: RunContext) -> Iterator[Owned]:
    env = open_owned(pool, qa6_run, "O10", controld=ready_with_wrapper(pool, qa6_run))
    try:
        yield env
    finally:
        env.stream.close()


def tree_session_ids(env: Owned) -> set[str]:
    found: set[str] = set()
    for workspace in as_list(env.client.fleet_tree().get("workspaces")):
        for session in as_list(as_dict(workspace).get("sessions")):
            found.add(str(as_dict(session).get("session_id")))
    return found


@scenario("O10")
def test_o10_ask_forks_the_engine_and_hides_the_fork(ask_env: Owned, rec: Recorder) -> None:
    env = ask_env
    rec.note("O10 runs with a run-time wrapper that re-emits the shim's -p answer as the captured -p JSON "
             "result object (module docstring); spawns exec the run shim unchanged")
    sid = spawn_ok(env, "QA6 O10 target", "hello")
    parent = session_db_row(env, sid) or {}
    before = {str(r["id"]) for r in db_rows(env.controld.db, "SELECT id FROM session")}
    cmark, amark = len(claude_argvs(env.run)), env.audit.mark()
    answer = post_json(env.client, f"/api/sessions/{sid}/ask", {"question": "Q?"}, timeout_s=ASK_HANG_GUARD_S)
    data = answer.data() if answer.status == 200 else {}
    rec.check("api.text_has_fork_answer", "QA6-FORK-ANSWER" in str(data.get("text")),
              "text contains QA6-FORK-ANSWER", data)
    rec.equal("api.method_fork", "fork", data.get("method"))
    rec.check("api.from_fork_of_is_the_session", data.get("from_fork_of") == sid,
              f"from_fork_of == {sid} (the asked session's id)",
              {"from_fork_of": data.get("from_fork_of"), "engine_session_id": parent.get("engine_session_id")})
    rec.equal("api.refusal_null", None, data.get("refusal"))
    children = [r for r in db_rows(env.controld.db, "SELECT * FROM session") if str(r["id"]) not in before]
    child = children[0] if len(children) == 1 else {}
    rec.check("db.child_row", len(children) == 1 and child.get("origin") == "ask_fork" and child.get("ephemeral") == 1
              and child.get("depth") == (int(str(parent.get("depth", 0))) + 1) and child.get("parent_session_id") == sid,
              "one child row: origin ask_fork, ephemeral, depth parent+1, parent = the asked session",
              [{k: r.get(k) for k in ("origin", "ephemeral", "depth", "parent_session_id", "state")} for r in children])
    child_id = str(child.get("id")) if child else ""
    rec.check("api.child_not_in_fleet_tree", bool(child_id) and child_id not in tree_session_ids(env),
              "the child is absent from fleet_tree", child_id)
    forks = [argv for argv in claude_argvs(env.run)[cmark:] if "-p" in argv]
    rec.check("files.fork_argv_flags", len(forks) == 1 and "--no-session-persistence" in forks[0]
              and "--session-id" in forks[0], "the shim's argv log: one -p fork with --no-session-persistence and "
              "--session-id", forks)
    rows = env.audit.records_for(amark, "ask_session")
    rec.check("logs.ask_session_row", len(rows) == 1 and rows[0].get("decision") == "allow", "one ask_session row, allow",
              [{k: r.get(k) for k in ("decision", "approved_by", "result")} for r in rows])
    kill(env, sid)
    rec.finish()
