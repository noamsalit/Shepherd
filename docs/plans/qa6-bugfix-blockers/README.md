# qa6 bugfix: integration ledger (P16)

Plan: `docs/plans/2026-09-24-qa6-bugfix-plan.md` (rev 4). Branch `fix/qa6-bugfix`, base `6c70cd3`
(plan rev 3 + the P0 baseline). Every phase was merged `--no-ff` with no conflicts: P1–P10, then
P12 (which already contains P11, since its branch was cut from `fix/qa6-P11`), then P13–P15. There
is one ledger per phase in this directory, and `P0-baseline.md` holds the reference red sets.

## BC → phase → commit → ledger

| BC | Phase | Commit (merge) | Ledger |
|---|---|---|---|
| BC-01 macOS liveness token in UTC | P1 | `87f304f` (`098efa9`) | `P1.md` |
| BC-02 one delivery at a time; `CLEAR_THEN_SEND` reported | P2 | `c29a600` (`2188822`) | `P2.md` |
| BC-03 stream ids survive a restart | P3 | `be489c8` (`d298174`) | `P3.md` |
| BC-30 `close_master` counts the master's own card | P3 | `be489c8` (`d298174`) | `P3.md` |
| BC-04 idle crosses to `needs_you` on an unchanged stamp | P4 | `3ab3f1d` (`f5176c6`) | `P4.md` |
| BC-17 agents fallback consulted once per loop | P4 | `3ab3f1d` (`f5176c6`) | `P4.md` |
| BC-27 a bad sidecar counted once while it persists | P4 | `3ab3f1d` (`f5176c6`) | `P4.md` |
| BC-34 `session.state` frames carry `project_id` | P4 | `3ab3f1d` (`f5176c6`) | `P4.md` |
| BC-07 an `is_error` master result ends the turn as `error` | P5 | `62a31ab` (`d754ccb`) | `P5.md` |
| BC-08 a failed open keeps the wake summary, shows no internals | P5 | `62a31ab` (`d754ccb`) | `P5.md` |
| BC-09 a terminal stream ends when its pane dies | P6 | `840ecc1` (`d96ccaa`) | `P6.md` |
| BC-37 a killed row ends `stopped` | P7 | `de6534c` (`d467cad`) | `P7.md` |
| BC-29 killing a pane that is gone is a refusal value | P7 | `de6534c` (`d467cad`) | `P7.md` |
| BC-22 the audit records the autonomy level in force | P8 | `34fef94` (`4f9f3d2`) | `P8.md` |
| BC-31 blank project names are refused | P8 | `34fef94` (`4f9f3d2`) | `P8.md` |
| BC-16 a live socket is never stolen; a probe harms nothing | P9 | `57965a0` (`82e1dc0`) | `P9.md` |
| BC-21 (C10) a newer DB is a refusal | P9 | `57965a0` (`82e1dc0`) | `P9.md` |
| BC-20 (unreadable half) an unreadable settings file is a refusal | P9 | `57965a0` (`82e1dc0`) | `P9.md` |
| BC-23 integer query args reach handlers as ints | P10 | `588a75c` (`108eb43`) | `P10.md` |
| BC-33 a keep-alive follows every ended subscription | P10 | `588a75c` (`108eb43`) | `P10.md` |
| BC-32 body read timeout | P10: **not merged, owner decision** | `9aa9f11` on `fix/qa6-P10-bc32-owner` | `P10.md` §Router decision |
| BC-11 a dead daemon is not an empty fleet | P11 | `fb8bd14` (via P12 merge `e260f1b`) | `P11.md` |
| BC-19 the shell is keyboard-reachable | P11 | `fb8bd14` (via `e260f1b`) | `P11.md` |
| BC-18 (Flock half) card focus survives an event | P11 | `fb8bd14` (via `e260f1b`) | `P11.md` |
| BC-13 the header follows state | P12 | `114432e` (`e260f1b`) | `P12.md` |
| BC-36 a killed session opens no terminal | P12 | `114432e` (`e260f1b`) | `P12.md` |
| BC-25 (rename half) Escape / double-Enter | P12 | `114432e` (`e260f1b`) | `P12.md` |
| BC-12 R3 rename reply race | P12 | `114432e` (`e260f1b`) | `P12.md` |
| BC-12 R2/R4/R5 UI races | P13 | `459478c` (`4d19d55`) | `P13.md` |
| BC-18 (Projects half) row focus | P13 | `459478c` (`4d19d55`) | `P13.md` |
| BC-24 refusals shown; retries do not resend | P13 | `459478c` (`4d19d55`) | `P13.md` |
| BC-06 (step-body half) no step renders `[object Object]` | P14 | `62eb02d` (`ac9bc29`) | `P14.md` |
| BC-25 (composer half) blank text and IME Enter ignored | P14 | `62eb02d` (`ac9bc29`) | `P14.md` |
| BC-26 one card per approval | P14 | `62eb02d` (`ac9bc29`) | `P14.md` |
| BC-10 the terminal snapshot opens readable | P15 | `5b9095e` (`5b5f025`) | `P15.md` |
| BC-35 a refused stream reads `unreadable` | P15 | `5b9095e` (`5b5f025`) | `P15.md` |

## Consumer manifest (`tests/boundaries/consumer_manifest.json`)

`baseline` and `rebase` are untouched. `files` holds the live digest of each of the twelve `web/`
paths that moved. `post_milestone.edits` has one entry per path. Entries on already-declared paths
were rewritten, because the reader allows one entry per path, so each entry has to describe the
path's whole divergence from the step-0b baseline.

- **New:** `web/sse.py` (BC-33), `web/static/sse.js` (BC-35). `web/server.py` has no entry
  because it did not move: BC-32 is parked, and `git diff --stat 6c70cd3 -- src/shepherd/web/server.py`
  is empty.
- **Rewritten:** `web/static/flock.js` (BC-11, BC-18 Flock), `projects.js` (BC-12 R4/R5, BC-18
  Projects, BC-24), `session.js` (BC-13, BC-36, BC-25 rename, BC-12 R3), `settings.js` (BC-12 R2,
  BC-24), `terminal.js` (BC-10).
- **Re-based paths (only their `files` digest changed):** the test forbids these in
  `post_milestone`, so their edits are recorded here instead:
  - `web/routes.py`: BC-23, `QUERY_ARGS["/api/audit"] = ("limit",)`, `INTEGER_QUERY_ARGS` and `_query_value` (P10).
  - `web/static/app.js`: BC-11 `view.fleetReadable`, BC-19 `#mark` keyboard expand (P11); BC-13
    `refreshOpenSession()` (P12).
  - `web/static/index.html`: BC-19 `#mark` `role`/`tabindex`/`aria-label`; BC-11 `#fleet-unknown` slot (P11).
  - `web/static/app.css`: BC-19, the closed phone drawer is `visibility: hidden` (P11).
  - `web/static/chat.js`: BC-06 `stepBody`, BC-25 blank/IME guard, BC-26 `shown(id)` dedupe (P14).
- `moved_paths(baseline, files) == regenerated_paths ∪ post_milestone paths` holds exactly, and the
  two sets are disjoint.
- `src/shepherd/cli` is unchanged from both `6c70cd3` and `be9db6f`, so the `cli/` freeze held.
- `tests/boundaries/test_collected_node_ids.py` was not edited. Its check is subset-only, so the new
  test ids need no entry. No frozen node id disappeared: a `--collect-only` with `--ignore=tests/qa5`
  gives `subset_violations(...) == []`. No phase retired a test.

## Changed existing assertions (all declared; every node id kept)

Plan rev 2/3:
- `tests/orchestration/test_mailbox.py:576` (`test_clear_then_send_re_reads_the_pane_before_the_text`),
  P2: `WriteDecision.SEND_NOW` → `WriteDecision.CLEAR_THEN_SEND`. The old value pinned the misreport
  that BC-02 fixes: a send after a clear was reported as a plain send.
- `tests/toolsurface/test_compose.py:258` (`test_compose_publishes_every_event_of_a_fold_result`),
  P3: the expected list gains a leading `"stream.gap"`. BC-03 starts the composed ring above every
  earlier process's seqs, so cursor 0 is behind the ring and the existing gap path answers first.
- `tests/web/test_routes_m3.py:290` (`test_no_declared_field_shadows_a_path_parameter`), P10:
  `len(routes.QUERY_ARGS) == 3` → `4`. BC-23 declares `/api/audit`'s `limit`, which shadows no path
  parameter.

Plan rev 4:
- `tests/toolsurface/test_policy.py:188` (`test_the_caller_context_field_is_defaulted`), P8: the
  `AuthzOutcome` field set gains `"autonomy_level"`. BC-22's plan-required field has to be named in the pin.
- `tests/toolsurface/test_approvals.py:275` (`test_an_unanswered_approval_times_out_and_counts`),
  `:607` (`test_a_withdrawal_denies_the_blocked_call_and_counts`) and `:660`
  (`test_a_click_is_the_only_thing_that_produces_user_and_the_declared_denial`), P8: each expected
  outcome gains `autonomy_level=int(AutonomyLevel.LEVEL_2)`. Each card path now reports the level
  read before the card. The change is additive, so each assertion pins strictly more.
- `tests/web/test_settings_page.py:337-339` (`REQUIRED_SETTINGS_ASSIGNMENTS`), P13: adds
  `autonomy.intent = level`, `autonomy.sending = true` and `autonomy.sending = false`. These are
  BC-12 R2's intent bookkeeping; the whole-set pin asks for every new assignment to be declared.
- `tests/web/test_session_wiring.py:254-258` (`REQUIRED_ASSIGNMENTS`), P12: adds `shownTitle = title`
  (BC-25) and `banner.textContent = KILLED_BANNER` (BC-36). The `row.title` `input.value` entry is
  replaced by the `shownTitle` form, because the old entry encoded BC-25's stale pre-fill.

## Siblings left open (collected from the phase ledgers)

- **P1:** `mac.py`'s module docstring and `verified()` still say `ps -o lstart=` liveness is
  unmeasured. `LC_TIME` locale spelling of `lstart` is out of scope.
- **P2:** `rename.py`'s own typing path does not take `DELIVERY_LOCK` (the rename typing race).
  `DELIVERY_LOCK` is process-wide, not per session.
- **P3:** E6 (ring overflow behind a live client) is unchanged. `web/sse.py` and `sse.js` id formats are unchanged.
- **P4:** `liveness_sweep`'s `session.state` frames still carry no `project_id`.
  `unknown_registry_status` is still bumped once per pass per entry.
- **P5:** an unrecognised subtype flagged `is_error` still renders `turn_ended/unknown` (G-M4-5's
  pin). The exception detail behind `OPEN_FAILED_REASON` now surfaces nowhere (no logger, no new
  `AnomalyKind`). A `Thread.start()` failure after the drain still consumes the summary.
- **P6:** if the tmux binary vanishes mid-stream, `RunnerRefusal` escapes `chunks()` into the WS
  handler, which catches only `OSError`. This is a `web/server.py` concern. The WS read loop (T19-c)
  is untouched.
- **P7:** a pane-gone owned row with `ended_at` NULL cannot be deleted under
  `delete_project(on_running=kill_sessions)` after BC-29. The kill is refused, nothing marks the
  row stopped, and the delete refuses. `orphan` still works. The BC-37 residual (below) also applies.
  `lifecycle.py:46` imports `RunnerRefusal` twice (pre-existing).
- **P8:** name normalisation, UI validation and `tools_master.py` are out of scope.
  `set_project_description` accepts a blank value by design.
- **P9:** see E16 below. A live listener with a full accept backlog may refuse the probe and be read
  as stale. `uninstall_hooks` shares `_load`, so it now refuses an unreadable file too.
- **P10:** `BODY_READ_TIMEOUT_S` would be a per-`recv` idle window, not a total deadline (on the
  parked branch). `int()` accepts `" 10"`, `"+5"`, `"1_0"` and negatives. A negative `scrollback`
  reaches the runner.
- **P11:** the Flock projects column (`renderProjects`) still rebuilds with `replaceChildren()`, so
  focus on a project button is lost on every event. `renderEmptyState` can still write `registry: 0`
  for a readable fleet without `discovery.registry_sessions`. Focus is not moved to `#mark` after
  `#collapse`.
- **P12:** the BC-37 residual has a BC-36 consequence. A session killed *after* a turn keeps that
  turn's `stop_reason`, so it still opens a terminal socket that 404s. An open session killed on
  screen keeps its terminal element until the next `renderSession`. The decision card does not
  follow a refresh into `needs_you` (SD-06).
- **P13:** `openProjectDialog` does not clear `#p-paths` before the new read. A double click on Add
  posts twice (U18). The pre-existing `UNREACHABLE` settings note is not cleared by a later success.
- **P14:** BC-06's owner half (see below). `loadShepherd` still replaces `state.approvals` with the
  read list, so a stream-only approval drops out of `state`, but its DOM card stays.
- **P15:** SD-05 (terminal input; U10 stays FAIL). The real cursor position of an alternate-screen
  snapshot is not carried on the socket. Every non-retried `EventSource` failure reads `unreadable`.

## Owner decisions (unchanged from the plan, plus BC-32)

- **BC-05** (C1–C5): the CLI↔daemon transport, plus a declared `cli/` edit.
- **BC-06 rendering half:** one step or two for a call and its result; how `turn_ended` and
  `rate_limit` appear; whether the final `result` text is rendered.
- **BC-14** (M12): what level 3's unprompted wake sends, and its queueing and cap.
- **BC-15** (M14): whether a master retry is declared (`retry_of`) or inferred.
- **BC-20 backup / byte-reversible uninstall** (H4): whether to keep the first or the latest
  pre-image, and whether to restore it byte-for-byte or re-serialise.
- **BC-21 (C7):** whether ADR-7 §4 can say "frozen before the server *serves*", so the port binds
  before the DB opens.
- **BC-28** (O4): delete the pre-written row on a refused start, or keep it with a verdict.
- **BC-37 residual:** the verdict for a kill after a finished turn, and what marks "a session end
  arrived during the kill".
- **BC-32** (plan rev 4): the body read timeout needs `web/server.py`, which
  `tests/boundaries/test_consumer_surface_additive.py::test_web_server_is_byte_unchanged` pins by
  digest (in `pre_m4_routes.json` and in the manifest's never-rewritten `baseline`) under ADR-M4-7.
  The fix and its tests (`tests/web/test_server_short_body.py`) are ready on
  **`fix/qa6-P10-bc32-owner` @ `9aa9f11`** and are not merged. The options are: (a) re-pin, with
  the test comparing the manifest `files` entry; (b) the test accepts a declared
  `post_milestone.edits` entry; (c) withdraw BC-32.

## Residual E16 (accepted, not fixed; P9)

A second owner can bind the control socket after `claim_socket` (`controld.py:71`) and before the
ingest thread's `bind_listener`. The thread then raises `SocketInUse`, `start()` raises
`TimeoutError` after `BIND_TIMEOUT_S`, and `main`'s `except OSError` prints "port N is not
available". The text is misleading, but only on a narrow race, and the result is still a refusal
with no theft. `sessiond` has the same shape: `serve_ingest`'s `bind_listener` raises `SocketInUse`
uncaught after the up-front claim.

## P15 review note

`terminal.js`'s new `snapshotForEmulator(capture)` names its parameter `capture` rather than
`bytes`. `tests/web/test_session_page.py::test_pty_bytes_never_reach_innerHTML` treats `bytes` as
the pane-byte token and has no allowed shape for a function declaration header. So this pure
transform sits **outside** that scan's pty-token view. The scan still reads its one caller, which
hands the result to `term.write`, and the function has no sink. A future edit that gives
`snapshotForEmulator` a DOM sink would not be caught by that scan. Widening `_ALLOWED_PTY_LINE` to
admit a declaration header would close the gap, but that is a test-file change outside P15.

## Integration checks (P16, tree `5b5f025` + this README + the manifest edit)

- `pytest -p no:randomly tests/boundaries`: 102 passed, 3 errors. The 3 errors are exactly
  `BASELINE_BOUNDARY_FAILS` (`test_collected_node_ids.py` ×3, qa5 collection). Before the manifest
  edit, `test_completing_l4_changed_no_consumer_byte` failed and listed the twelve moved paths.
- `mypy --strict src`: 2 errors, the baseline pair (`linux.py:104`, `detect.py:29`).
- `git diff --stat 6c70cd3 -- src/shepherd/cli` and `be9db6f -- src/shepherd/cli`: both empty.
  `git diff --stat 6c70cd3 -- src/shepherd/web/server.py`: empty.
- Default lane `--ignore=tests/qa5`: `BASELINE_DEFAULT_FAILS` exactly (4 FAILED + 3 ERROR), plus
  `tests/qa/test_s7_shutdown_in_flight.py::test_clause_20_holds_on_every_run_and_the_branch_is_recorded`
  (`refused×5` vs the pinned `{raised}`). That test also fails alone. It fails identically on
  **base `6c70cd3` source** (`git archive 6c70cd3 src` into a scratch dir, with `PYTHONPATH` pointed
  there), so it is a host-timing characterisation pin independent of this plan, as P3 recorded. It
  is not a regression.
