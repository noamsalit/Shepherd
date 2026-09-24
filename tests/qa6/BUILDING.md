# Building on tests/qa6 (STAGE B guide)

STAGE A built the shared harness and waves 1-3 (56 scenarios). STAGE B added
waves 4-9 **as new test modules only**. The re-qa-build remfix (after INC-1)
then changed shared files once, on the three STAGE B builders' requests: host
safety (SI-1, §9), the real-engine resolution (§5, §9), `ToolCallingMaster`
payloads and multi-text turns (§4), `browser.pump/settle` (§4), the ledger
names (SI-2, §6), wave-8 mutations (SI-3, §4) and the shim's `-p` JSON (§5).
Nothing below otherwise requires editing a shared file. If you believe one must
change, that is a finding to report, not an edit to make.

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
* **A failed clause outranks whatever interrupts the body afterwards** — a
  helper's `Blocked`, a skip, a harness exception, a missing `finish()`
  (`verdict.classify_outcome`, remfix 2 / H1): the record is FAIL.
* A product socket failure from `Client.request` (refused, reset,
  `RemoteDisconnected`, a garbled status line, a timeout) is raised as a
  `verdict.ProductUnreachable` subclass of the original type (so `except
  ConnectionRefusedError` still works). With no failed clause it is **FAIL**
  when that same client answered earlier in the scenario (a timeout: FAIL(bound)
  only when it is >= 10x that answer's latency), else **BLOCKED** (remfix 3,
  hunter N2). Raw sockets you open yourself are not covered: classify them.
* An unexpected exception with no failed clause is **FAIL(harness_error)**;
  the gate reads it as INCOMPLETE, never RED. A runner crash is RED when a
  product FAIL was recorded (crash first in the reasons), else INCOMPLETE
  (remfix 3, hunter N3).
* Every JSONL reader goes through `jsonl.read_objects`: a torn line is a
  published problem, never an exception and never dropped (remfix 3, N1/N5). A scenario that does not take
  `rec` is BLOCKED (and a guard fails the build).
* `rec.fail_bound(name, what, bound_s, control, actual=…)`: pass what WAS
  observed instead, so the record tells "closed with the wrong code" from
  "never closed".
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
`instance.wait_restart_ready(second)`: `Blocked` **only** when the child printed
the product's port refusal with EADDRINUSE; any other non-ready restart raises
`RestartFailed` (an AssertionError: record it as a failed clause — E5, O11,
D10 and U39 show the shape; remfix 2 / H2).

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
  received_at)`. A product frame that does not parse makes `snapshot()`/
  `since()` raise AssertionError (FAIL); a server EOF after a green control on
  that subscriber is FAIL, before one it is `Blocked` (remfix 2 / H5). **Every "no frame" clause needs `run_control(sub, client,
  name, mark)`** (or `run_control_on([(sub, mark), …], client, name)` for
  several clients — two sequential controls pollute each other's windows).
* **Hang guards** — `Client.post_guarded(path, body, headers, timeout_s)`: a
  blown timeout is FAIL(bound) when a same-client control (`GET /api/fleet`)
  answers in under a tenth of the guard, else BLOCKED (remfix 2 / H3). Never
  turn a `TimeoutError` into `Blocked` by hand.
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
  array per line). A tmux call made **inside a pane** (`$TMUX` set — the real
  engine queries its own pane with `display-message -p` / `show -gv …` and no
  `-L`) goes to `run.pane_tmux_argv_log` as `{"argv", "tmux": $TMUX}` instead;
  `effective_socket(argv, tmux_env)` is the ONE judge of the socket tmux would
  contact, by tmux 3.6a's getopt (`2c:CDdf:hlL:NqS:T:uUvV`): clustered flags,
  the last `-L`, `-S` over `-L`, `$TMUX` only when neither; `argv_violation`,
  `product_argv_offenders` and `pane_argv_offenders` apply it for this run,
  in the runner's post-lane scan, Z2 (`tmux.argv`, `tmux.kill_server_ours_only`,
  `tmux.pane_argv_effective_socket`) and the wave-4 `socket_ok`. Never read a
  socket from a fixed argv position.
* **browser.py waits** — `pump(page)` and `settle(predicate, bound_s=UI_BOUND_S,
  page=None) -> (value | None, elapsed)`. **Sync Playwright dispatches page
  events (request, response, console, websocket) only while a Playwright call
  is running**: a predicate that reads a `PageLog` while the harness only
  sleeps polls a list that never grows. `settle(..., page=page)` pumps before
  every poll; a predicate that queries the DOM through a locator is itself a
  Playwright call and needs no `page`. `sub/test_wave6_0_uikit.py` re-exports
  both (and `UI_BOUND_S`) from here.
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
  `says` is a `str` or a `Sequence[str]` (one `master.text` per entry). Payloads
  match `master/projection.py`: `tool_call` detail `{"tool_use_id", "input"}`,
  `tool_result` detail `{"tool_use_id", "is_error", "text"}` (and the result
  text as the event text), `tool_use_id = qa6-toolu-<turn_id>-<n>` (`n` from 1
  per turn; `master.tool_use_id(turn_id, n)`);
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
  `runs/mutations/<id>/mutation-result.json`). A **wave-8** mutation first runs
  S0 in its own process without the mutation and hands the mode it bound to
  the mutated node as `QA6_LIVE_AUTH_MODE` (SI-3; `mutations.prerequisite_nodes`).
* **sandbox.py env builders** — `sandbox_env(...)` (sandboxed HOME: the
  instance's `XDG_*`), `real_home_env(run, root, path_mode="live")` (the one
  builder for a child carrying the real HOME), `instance.launcher_env`,
  `host_safety_problems(env)`; see §9.
* **realclaude.py** — `resolve(environ)`, `install(run, resolution)` (called by
  `bootstrap.mint`), `load(run)`, `require(run)`, `link_state()`,
  `record_link_start(run_dir)`, `link_change(run_dir)`, `compare(start, now)`,
  `REPAIR_MESSAGE`; see §9.

## 5. Shims

* Fake `claude` (`<run0>/shims/claude`): marker line, the captured macOS
  prompt-ready frame, then `cat` (proven PROMPT_READY by W5). Modes via the
  file `$HOME/.qa6-shim-mode` in the instance's sandbox home (the product's tmux
  server inherits `HOME`): `default`, `dialog` (U14: frame, 2 s, clear, the p4
  permission dialog — W5 measured it classifies PERMISSION_DIALOG on macOS),
  `catv` (O7: `cat -v`), `bare`. `-p/--print` before `--` prints the engine's
  captured `-p --output-format json` result object — `{"type":"result",
  "subtype":"success","is_error":false,"result":"QA6-FORK-ANSWER",
  "session_id":<its --session-id>}` — and exits (O10; the product's
  `parse_fork_result` reads it; O10's STAGE B wrapper is gone). Argv logged as
  JSON objects to `run.claude_argv_log`.
* D9's counting `claude`: `shims-d9/`, log `shims.forks_log(run)`.
* **The tmux shim REFUSES** (`shims/tmux.sh.in`, perl; env-plan §0 item 3, r3
  post-review harness amendment): it logs the argv first and fails CLOSED
  (exit 98, no exec) if it cannot, then exits 97 without exec for any argv that
  is not exactly `tmux -V` and whose effective socket is not this run's
  `shepherd-m3-q6<pid>-<k>` — the user's `default`/`shepherd` servers are never
  reached, whatever the product or engine emits. `test_proof_tmux_shim_refuses`
  proves it agrees with `tmuxctl.argv_violation` against a fake binary;
  `shims.selftest_refusal` proves the production-rendered file at mint.
* `path_mode="live"`: logging tmux + `<run0>/bin/claude`, a run-scoped symlink to
  the real engine (never the user's `~/.local/bin/claude`; §9). Any direct exec
  of the real engine uses `run.real_claude` / `realclaude.require(run)` (BLOCKED
  when the run has none).
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
  `<run_dir>/ledgers/{tmux-argv.log, unseeded-tmux-argv.log, pane-tmux-argv.log, claude-argv.log,
  pids.jsonl, controld-argv.jsonl, port-refusals.log}` (SI-2: the product log
  and the unseeded log are distinct files; `run.ledger_copies` names them),
  `<run_dir>/teardown-problems.jsonl`, `<run_dir>/real-claude.json` (which engine
  and why) and `<run_dir>/claude-link-start.json` (§9).
* Real `~/.claude/projects` gains `-private-tmp-shq6-<pid>-<k>-cwd` entries under
  `needs_real_home` (S0(b)/(d) create them; G18). Z1 allows only names carrying
  this run's slug.

## 7. Rules that bind every module

* Never bind, connect to, or signal the forbidden port (`paths.FORBIDDEN_PORT`);
  a guard greps for the literal.
* Never run a tmux client command on `default` or `shepherd`; never `kill-server`
  outside `tmuxctl.kill_server`.
* Signals only to pids you spawned and recorded (`Popen`); never by name.
  Teardown and the pre-run sweep signal a ledgered pid only when its current
  start token (the product's `MacHost.process_liveness`) equals the one
  `record_pid` stored at spawn (`teardown.signal_decision`).
* Every `Popen`/`run` of a product or engine child passes its env through
  `sandbox.checked_env(env, what)` at the spawn site (`spawn_drained` does it
  for you): a dict edited after its builder is re-checked where it is used.
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

## 9. Host safety after INC-1 (SI-1) — binds every module

**INC-1 (2026-09-24, unrepaired, not the harness's to repair).** A STAGE B smoke
run gave a real-HOME `claude` TUI pane a sandboxed `XDG_DATA_HOME`; the engine's
auto-updater installed itself under the run root and re-pointed the user's
`~/.local/bin/claude` there; teardown deleted the root, and the user's link now
dangles. Nothing in this package may modify anything under `~/.local`,
`~/.claude/settings.json` or any other user file.

* **Envs.** Every env built by `sandbox.py` carries `DISABLE_AUTOUPDATER=1`. An
  env carrying the **real** HOME carries **no `XDG_*`** and also
  `DISABLE_INSTALLATION_CHECKS=1`: `real_home_env` (S0's real probes, the
  launcher via `instance.launcher_env`, wave 8's `real_home_engine_env`), the
  preflight's `claude --version` env, and the lane pytest processes
  (`pytest_process_env`). Every builder refuses an env that fails
  `host_safety_problems`. Never build a child env by hand: the guard
  `test_guard_no_ad_hoc_real_home_env` fails on an `XDG_*` literal or a
  `home=REAL_HOME` outside `sandbox.py`, and on `REAL_CLAUDE_BIN` used anywhere
  but in a message. `test_proof_host_safe_envs` checks every builder
  independently of the checker, and is re-proved by three planted mutations of
  `sandbox.py` (`fixtures/mutations/sandbox_{xdg,checker,autoupdater}.json`).
* **The engine.** `realclaude.resolve`: `QA6_REAL_CLAUDE` if set (an invalid
  value resolves to nothing — never guessed past), else `shutil.which("claude")`
  if it resolves to an existing executable, else the newest
  `~/.local/share/claude/versions/*` executable (the INC-1 fallback; the record
  says so). A candidate inside a qa6 run root is refused. `bootstrap.mint`
  exposes it as `<run0>/bin/claude` and writes `real-claude.json` to the run
  root and the run dir; the runner puts it in the report (`real_claude`). The
  preflight T1 row "real claude resolves" records the path and why.
* **The link guard.** The runner writes `<run_dir>/claude-link-start.json` (the
  user's link: lstat + readlink + realpath, reads only) before its preflight;
  `bootstrap.mint` writes it for standalone and mutation runs. It is compared
  against that run-START state — never against "healthy" (it is dangling now).
  The runner stops the run on a change after any lane and records a teardown
  problem at the end; `live/conftest.py` makes every live module and every live
  scenario BLOCKED (`realclaude.REPAIR_MESSAGE`) if it changed; Z1's
  `files.claude_bin_link_unchanged` asserts the run left it as it found it.
* **The ~/.local tree guard** (remfix 2, review finding 3). `hostprobe.local_tree`
  records names, kinds, mtimes and link targets under `~/.local/bin`,
  `~/.local/share/claude` and `~/.local/state/claude` (lstat/readlink only) in
  the baseline and after every lane; the runner stops on any change
  (`local_tree_changes`; a lock file of a version other than this run's engine
  is the user's own session and is attributed, not counted), and Z1's
  `files.local_tree_unchanged` asserts it. Z1 also compares the user's real
  Shepherd data dir and real `$TMPDIR/Shepherd`, and Z3 the user's Shepherd
  daemons and tmux pids, baseline vs `after-teardown.json` (H7).
* **The runner always finishes** (H6): a crash in the waves still tears down,
  runs wave 9 and publishes INCOMPLETE with the exception; a preflight-blocked
  run leaves a history line; the pre-run sweep stops a dead run's ledgered
  children whose start token still matches.
