# Building on tests/qa6 (STAGE B guide)

STAGE A built the shared harness and waves 1-3 (56 scenarios). STAGE B adds
waves 4-9 **as new test modules only**. Nothing below requires editing a shared
file: the runner, the stop-ifs (every wave's), the lanes, the manifest, the
catalog of all 161 ids and every helper already exist. If you believe a shared
file must change, that is a finding to report, not an edit to make.

Plan: `.cc10x/qa/wf-20260923T182839Z-9adb11fc/test-plan.md` (r3) and
`env-plan.md` (r3). Setup record: `.cc10x/qa/env/Shepherd-macos/setup.md`.

## 1. Where a module goes, and what it is called

```
tests/qa6/<lane>/test_wave<N>_<order>_<topic>.py
```

| lane dir | runs | process |
| --- | --- | --- |
| `sub/` | SUB controld subprocesses (+ browser) | one pytest per wave |
| `unit/` | module seams in-process, no composition | one pytest per wave |
| `cli/` | `shepherd` CLI with no daemon | one pytest per wave |
| `inproc/` | INP #1 (wave 5: M1-M14, M16, M18, M19, P10) and INP #2 (wave 7: U25-U32, U46) | one composition per process |
| `inproc_long/` | M17 only (background at wave 5 start, joined before wave 9) | own process |
| `live/` | real `claude` / SDK master (`@live_scenario`, marker `qa6live`) | wave 1 (S0) and wave 8 |
| `host/` | Z1-Z3 (read-only, **after** teardown) | wave 9 |

Order inside a wave: files sort by name (use the `<order>` digit); inside a
file, tests run in definition order. Lane order per wave is `stopifs.WAVE_LANES`
(wave 4: sub; 5: inproc_long, inproc, unit; 6: sub; 7: sub, inproc; 8: live; 9: host).

A scenario test:

```python
from ..scenario import scenario          # or live_scenario for LIVE
from ..verdict import Recorder

@scenario("O1")                           # a test-plan id; implemented exactly once
def test_o1_spawn_owned_session(pool: InstancePool, rec: Recorder) -> None:
    ...
    rec.check("tmux.argv", ok, expected, actual)   # soft clauses
    rec.finish()                                   # MUST be called; decides the verdict
```

The function name **must** start `test_<id lower>_` (the runner and the guard
read ids from names). `test_harness_guards.py` fails if an id is unknown,
implemented twice, in the wrong wave's file, or a module is outside a lane dir.

## 2. Verdicts (never invent a third way)

* `rec.check / equal` → a failed clause → **FAIL(assert)**.
* `rec.fail_bound(name, what, bound_s, control)` → **FAIL(bound)**, only when a
  same-channel positive control in this run qualified the bound (Difference 1).
* `rec.block(name, reason)` or `raise Blocked(reason)` → **BLOCKED** (the
  environment, or an unreachable clause). A setup error is always BLOCKED.
* `rec.record(name, value)` → a measurement the plan says to record.
* FAIL outranks BLOCKED; a scenario with no clause is BLOCKED; a test that
  returns without `rec.finish()` is recorded BLOCKED.
* Waits: `await_env(pred, s, what)` (liveness → Blocked), `await_product(pred,
  bound, what, control_latency_s)` / `observe(pred, s)` (a product wait you
  classify), `Sourced(seconds, source)` for a cited product constant (the 2.0 s
  scan, 15 s keep-alive, 60 s idle, 600 s approval, 0.25 s alarm).
* `sleep` is never readiness. The plan's observation windows (E1's 35 s, D2's
  14 s, M17's 630 s, U38's 31 s, L5's 70 s) are the only fixed waits.

Clause-name conventions the stop-ifs read (`stopifs.CLAUSE_CONVENTIONS`):
`route.` (A1), `framing.` (E1), `files.settings_sha` (S0), evidence line
`LIVE_AUTH_MODE=<v>` (S0). Name O-/Z2 argv clauses `tmux.argv`.

## 3. Fixtures (tests/qa6/conftest.py)

| fixture | scope | gives |
| --- | --- | --- |
| `qa6_run` | session | `sandbox.RunContext`: `pid`, `run0` (shared root), `run_dir` (records/report dir), `shims`, `repos` (alpha, beta, `my repo`, loose, alpha-wt, alpha/vendor-beta), `artifacts`, ledgers |
| `rec` | function | `verdict.Recorder` for the scenario id |
| `pool` | module | `pool.InstancePool` — everything it starts is stopped and verified at module end |
| `browser_session` | module | `browser.BrowserSession` (Playwright per **module**, never session: W7.1) |
| `inp` | session (inproc lanes only) | `inp.Inp` — the one INP composition of the process |

`InstancePool`:

```python
pool.ready(path_mode="shims"|"live"|"d9"|"bare"|"unseeded", sessions_dir=True,
           master_model=None, configure=None) -> instance.Controld   # minted, seeded, 4 signals
pool.start(root, port=0, path_mode=..., env=None, extra_args=(), name="controld") -> Controld  # no wait
pool.adopt(controld)        # e.g. a launcher instance, so teardown covers it
pool.helper() -> instance.Helper            # /bin/sleep 3600 + the product's start token
pool.sessiond(controld) -> instance.SessiondManager
```

`Controld`: `.port`, `.socket_path`, `.root` (`sandbox.InstanceRoot`: `home`,
`tmpdir`, `cfg`, `sessions`, `db_path`, `data_dir`, `controld_socket`,
`sessiond_socket`, `logs`, `cwd`), `.env` (the child env; reuse it for CLI/
sessiond children), `.client` (`httpclient.Client`), `.db`, `.wait_ready()`,
`.healthcheck()`, `.stop()` (SIGTERM → `.stop_code`, `.stop_line`),
`.child.lines("stdout"|"stderr")`, `.child.alive()`.

Restarts on the same HOME/TMPDIR: `pool.start(first.root, port=first.port)` then
`.wait_ready()`; a failed re-bind is BLOCKED (E5 shows the shape).

## 4. Helpers you should reuse

* **instance.py** — `seed_db(root, runner_socket=, master_model=)`,
  `db_rows(db, sql, params)` (read-only), `app_state(db, key)`,
  `last_scan_at(db)`, `schema_version(db)`, `start_launcher(run, root)` (the
  `needs_real_home` launcher, `launch_controld.py`: real HOME, sandboxed
  Shepherd, `engine_config_dir=<root>/cfg`), `SessiondManager.start(name,
  schema=4)` (refuses if the socket exists or a recorded sessiond lives),
  `.stop(run)` → `SessiondRun.counts()` from the stop line.
* **hookrig.py** — `dispatch_argv(controld)` (the product installs a sandbox
  settings file; returns the argv of the first half of the command),
  `captured(dir, event, index)`, `frame(payload, session_id=, cwd=,
  transcript_path=, **overrides)`, `copy_transcript(cfg, engine_id)` (an
  `end_turn` transcript), `send(argv, env, payload)` → `Sent(rc, elapsed_s,
  stderr, signalled)`, `start_ready_sessiond(manager, name, argv=,
  target_engine_id=, target_cwd=, schema=4)` → `(run, probe_latency)`. **Every
  `delivered=` oracle subtracts the one probe.** SD-W6 (wave 6) and SD-L4
  (wave 8) use exactly this.
* **sessions.py** — `sidecar(pid=, proc_start=, cwd=, session_id=, status=,
  status_age_s=, started_age_s=, name=, name_source=, entrypoint=, kind=,
  waiting_for=, extra=, drop=)` (the captured key set; a harness-shaped input,
  G5), `write_sidecar(sessions_dir, body)` (atomic), `await_session(controld,
  engine_id, bound, state=)`, `session_row(controld, engine_id)`. A real writer
  bumps `statusUpdatedAt` on change: rewrite with a newer stamp (see
  `sub/test_wave3_1_discovery.py::rewrite`).
* **sse_rig.py** — `subscribe(name, port, last_event_id=)` (waits for `: open`),
  `open_stream(...)` (a refusal comes back as `Refusal`), `Subscriber.mark()` /
  `.since(mark)` / `.await_frames(pred, bound, what, control_latency, mark)`,
  `Frame(seq, kind, project_id, session_id, data, body_keys, raw_fields,
  received_at)`. **Every "no frame" clause needs `run_control(sub, client,
  name, mark)`** (or `run_control_on([(sub, mark), …], client, name)` for
  several clients — two sequential controls pollute each other's windows).
* **httpclient.py** — `Client(port, refusals_log=, allow_master_send=False)`:
  refuses the forbidden port and, unless allowed, `POST /api/master/send`
  (only INP and LIVE may). `.get/.post/.request(method, path, body=,
  headers=)`, project verbs, `.fleet()`, `.fleet_tree()`, `.session(id)`;
  `generic_error_problems(response, status)`, `as_dict`, `as_list`.
* **auditprobe.py** — `AuditProbe.for_instance(root)`: `.mark()`,
  `.since(mark)`, `.tools_since`, `.records_for(mark, tool)`,
  `.by_correlation`; `shape_problems(records)`. Reads are audited too (one
  `local_read` row per GET): count mutations or match by `correlation_id`.
* **wsclient.py** — `upgrade(port, path, origin=None|NO_ORIGIN|"...", host=,
  want_frames=)`, `read_to_close(port, path, bound_s=)` (T4), `mask_frame(opcode,
  payload)` (T3 keystrokes), `decode`.
* **tmuxctl.py** — every call takes `(socket, run.pid, *words)` and refuses any
  socket but this run's `shepherd-m3-q6<pid>-<k>` (`run.runner_socket(k)`);
  absolute binary (never in the shim log). `sessions`, `run`, `run_bytes`,
  `target(name)`, `kill_server` (teardown backstop only). The product's own
  tmux calls go through `<run0>/shims/tmux` → `run.tmux_argv_log` (one JSON
  array per line).
* **browser.py** — `with browser_session.context("U1", viewport=(w, h),
  has_touch=, is_mobile=, java_script_enabled=, abort_master_send=True,
  color_scheme=) as (context, log):` listeners attached before `goto`;
  `log.console_errors()`, `log.page_errors`, `log.requests_to(path, method)`,
  `log.status_of(path)`, `log.master_send_aborts` (env-plan §2 expected: U35
  exactly 1; U38 passes `abort_master_send=False`; everyone else 0). Input
  only through `click / press / type_text / tap / hover` (Playwright). **No JS
  click and no JS `dialog.close()`**; a guard fails the build if an
  `evaluate` string contains `.click(`, `.close(`, `dispatchEvent`, `.submit(`
  or `.focus(` outside a function named `js_*` (and a `js_*` must be labelled
  in its scenario). U40: `BrowserSession(artifacts, launch_args=["--host-resolver-rules=MAP qa6.test 127.0.0.1"])`.
  Re-query locators after every SSE event (the UI rebuilds lists).
* **fetchshim.py** — `install(page, pattern)`, `held_count`, `delivered`
  (the positive control), `release_all`, `release_first`, `set_holding`.
  Network timing only; label the scenario.
* **constants.py** — `load()` → `Breakpoints(sheet=600, panes2=760, shell=760,
  herd=900)` parsed from the served app.css; `VIEWPORTS`, `PHONE`, `DESKTOP`.
  Never spell a width literal in a module.
* **inproc/master.py** + **inp.py** — `inp.send_turn(Turn(says=, calls=[Call(name,
  args_or_fn)], ends=), text=)` pushes onto `BOOK` and posts `/api/master/send`;
  `Call.args` may be `lambda results: {...}` over the earlier `CallResult`s of
  the same turn (P10). `BOOK.records` (per turn: `results`, `interrupted`,
  `ended`), `BOOK.resumed`, `BOOK.configured_tools`. `inp.client` is allowed to
  send only while `inp.patched()`; `inp.root`, `inp.port`, `inp.subscribe(name)`.
  An empty book ends the turn with `error` (`EMPTY_BOOK`): that scenario is
  BLOCKED. `interrupt_master` has no route: call the product's
  `invoke()` with a HUMAN `CallerContext` in-process (M6, U46).
* **hostprobe.py** / **teardown.py** — `snapshot()`, `sha256`, `listing`,
  `pgrep`, `pgrep_exact`, `port_listener_pids`, `listen_addresses`,
  `open_files`, `process_env`, `process_cwd`; `teardown.leak_check(run)`,
  `our_tmux_sockets(run)`, `printed_ports(run)`.
* **mutations.py** — `active(name)`: the one-input sabotage hook for a scenario
  mutation. The §2c floor for STAGE B's waves is one `assertion_falsified` per
  flagged property they cover: PP-1 (M3/M4/P10/U27/L2), PP-2 (M5/U29/U46),
  PP-6 (M14/M15), PP-7 (Z2/O1/O5/O11), PP-11 (R1-R7), PP-20 (M10/L10).
  Register one by **adding** `fixtures/mutations/scenarios/<name>.json`
  (`name, prop, scenario, node, failing_clause, what`), wire `active(<name>)`
  at one input in your scenario with a `rec.note("QA6 MUTATION <name> APPLIED:
  …")`, and prove it with `run.py --mutation <name>` (the result lands in
  `runs/mutations/<id>/mutation-result.json`).

## 5. Shims

* Fake `claude` (`<run0>/shims/claude`): marker line, the captured macOS
  prompt-ready frame, then `cat` (proven PROMPT_READY by W5). Modes via the
  file `$HOME/.qa6-shim-mode` in the instance's sandbox home (the product's tmux
  server inherits `HOME`): `default`, `dialog` (U14: frame, 2 s, clear, the p4
  permission dialog — W5 measured it classifies PERMISSION_DIALOG on macOS),
  `catv` (O7: `cat -v`), `bare`. `-p/--print` before `--` prints
  `QA6-FORK-ANSWER` and exits (O10). Argv logged as JSON objects to
  `run.claude_argv_log`.
* D9's counting `claude`: `shims-d9/`, log `shims.forks_log(run)`.
* `path_mode="live"`: logging tmux + the real `~/.local/bin/claude`.
* `path_mode="unseeded"`: only for an instance started WITHOUT `seed_db` (its
  reconcile names the default socket `shepherd-runner`); its tmux argv go to
  `run.unseeded_tmux_argv_log`, never to the log Z2 reads.

## 6. What the runner hands wave 8 and wave 9

* `<run_dir>/live_auth_mode.json` — S0's binding (`needs_real_home` measured on
  this host: sandboxed HOME → "Not logged in"; real HOME → ok for CLI and
  master). Wave 8's lane gets `QA6_LIVE_AUTH_MODE`; **its conftest must refuse
  to run without it**. Under `needs_real_home` use `instance.start_launcher`.
  The master auth failure under a sandboxed HOME arrives as `master.text` +
  `master.turn_ended` ("Not logged in · Please run /login"), not `master.error`.
* Wave 9 runs **after** the runner's teardown (run roots removed; Z3 expects
  that): `<run_dir>/baseline.json` (pre-run host), `<run_dir>/host-after/<lane>-
  w<N>.json` (after every lane) and `after-teardown.json`,
  `<run_dir>/ledgers/{tmux-argv.log, unseeded-tmux-argv.log, claude-argv.log,
  pids.jsonl, controld-argv.jsonl, port-refusals.log}`,
  `<run_dir>/teardown-problems.jsonl`.
* Real `~/.claude/projects` gains `-private-tmp-shq6-<pid>-<k>-cwd` entries under
  `needs_real_home` (S0(b)/(d) create them; G18). Z1 allows only names carrying
  this run's slug.

## 7. Rules that bind every module

* Never bind, connect to, or signal the forbidden port (`paths.FORBIDDEN_PORT`);
  a guard greps for the literal.
* Never run a tmux client command on `default` or `shepherd`; never `kill-server`
  outside `tmuxctl.kill_server`.
* Signals only to pids you spawned and recorded (`Popen`); never by name.
* Mutations are inert fixtures or a single `active()` input switch; never plant
  a signal, kill, or teardown verb into code that runs (CLAUDE.md).
* One sessiond per controld instance at a time (`SessiondManager` enforces it).
* The real `~/.claude/settings.json` sha is checked by the runner after every
  lane; a change stops the run.
* Do not edit `src/`. An untestable seam is a `SCOPE_INCREASES` finding.

## 8. STAGE A departures a later builder should know

* C10 seeds the DB before its first boot (unseeded, the reconcile would name
  `shepherd-runner` in Z2's log); C7 stays unseeded and logs to the unseeded log.
* D4 uses its own D1-shaped session (D7(c) made D1's row ephemeral first).
* P4 reads "one frame per call" as one frame per call that changed something
  (P2/E6's rule); one audit row per call is asserted as written.
* D12 keeps the plan's `session.state stopped` oracle; the hook lane actually
  publishes `session_stopped` and `session.classified` (recorded in the record).
