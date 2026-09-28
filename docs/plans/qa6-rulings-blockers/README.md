# qa6 rulings — integration record (P13)

Plan: `docs/plans/2026-09-27-qa6-rulings-plan.md` (revision 4). Rulings:
`docs/plans/2026-09-27-qa6-owner-rulings.md`. Branch `fix/qa6-rulings`, local only, never pushed.
Integrated tree: `6988c80` plus P13's uncommitted diff (see `P13.md`). P14 (SD-09, ruling 22's
build half) is **deferred by the owner** and not built; its whole content is in
`docs/backlog/2026-09-27-sd09-session-tool-channel.md`. Verification against the qa6 comparison
set is P15's.

## Ruling → phase → commit → ledger

Merge commits are on `fix/qa6-rulings` (first parent); phase commits are on `fix/qa6r-P<n>`.

| Ruling | Item | Phase | Phase commits | Merged by | Ledger |
|---|---|---|---|---|---|
| 1 | BC-05 (CLI → controld RPC socket) | P10 (on P8) | `bff09b5`, `f0d46dc` (REM-FIX 1) | `647b5b8` | `P10.md` |
| 2, 3, 4 | BC-06 a/b/c (one step per tool; events on `#shepherd-event`; no repeated final text) | P3 | `b1bef67`, `7376ab9` (REM-FIX 1) | `bcdf654` | `P3.md` |
| 5 | BC-14 (level 3 wakes the master) | P6 | `ee9333b`, `93f0af9` (REM-FIX 1) | `0696767` | `P6.md` |
| 6 | BC-15 (declared `retry_of`) | P5 (on P4) | `05080b8`, `2618255` (REM-FIX 1) | `b175550` | `P5.md` |
| 7 | BC-20 (the backup keeps the first pre-install image) | P2 | `a1edf6a`, `25fda95` (REM-FIX 1) | `1e2e01a` | `P2.md` |
| 8 | BC-21 C7 (bind before the store; frozen before serving) | P8 | `75f5fb4`, `6197873` (REM-FIX 1) | `647b5b8` (via P10) | `P8.md` |
| 9 | BC-28 (a refused start ends its row `refused`; migration 005) | P4 | `b62f7ae`, `5526e95` (REM-FIX 1) | `b175550` (via P5) | `P4.md` |
| 10 | BC-37 residual (kill verdict after a finished turn) | P7 | `d81cafb`, `31b991a` (REM-FIX 1) | `b3fb486` | `P7.md` |
| 11 | BC-32 (declared `server.py` edit; parked fix `9aa9f11`) | P9 | `4d82b68` (merge of `9aa9f11`), `0778217`, `ba08abb` (REM-FIX 1) | `6988c80` (via P12, `e1b31b9`) | `P9.md` |
| 12 | H3 (`master_failed` counted and audited) | P6 | as ruling 5 | `0696767` | `P6.md` |
| 13 | H1-lock (lifetime `flock` claim) | P8 | as ruling 8 | `647b5b8` (via P10) | `P8.md` |
| 14, 15, 16, 17 (docs), 24, 25, 26, 28 | SD-01, SD-02, SD-03, SD-04, M9, O8, L4, INC-3 (oracle/doc rulings) | P1 | `f5b048d`, `d26aabe` (REM-FIX 1) | `04fde2e` | `P1.md` |
| 17 (oracle) | SD-04 U27/U28 oracle | P3 | as rulings 2–4 | `bcdf654` | `P3.md` |
| 18 | SD-05 (terminal input) | P12 (P11 + P9) | `789933b`, `1b1e5a8` (REM-FIX 1) | `6988c80` | `P12.md` |
| 19 | SD-06 (clickable decision-card choices) | P11 | `0815cb7`, `c83aa16` (REM-FIX 1) | `6988c80` (via P12) | `P11.md` |
| 20, 21 | SD-07 (pane-less send refused), SD-08 (`from_fork_of` is our id) | P7 | as ruling 10 | `b3fb486` | `P7.md` |
| 22 | SD-09 | P1 (README "not yet" line only); P14 **deferred** | `f5b048d` | `04fde2e` | `P1.md`; backlog note |
| 23 | SD-10 (spec text P1; H5 oracle P2) | P1, P2 | as P1, P2 | `04fde2e`, `1e2e01a` | `P1.md`, `P2.md` |
| 27 | L5 (`trusted: false` until known) | P4 | as ruling 9 | `b175550` (via P5) | `P4.md` |
| — | D68–D79 spec rows, ADR-7 §4 and ADR-M4-7 amendments | P1 | `f5b048d`, `d26aabe` | `04fde2e` | `P1.md` |
| — | integration (manifest, retired ids, import table, one test) | P13 | `72fce99` | — | `P13.md` |
| — | polish + doc-sync (deferred review items: permission digest required on the web route, RD-2 wording, doctor `fleet:` line, 1011 reader sentence, `dd bs=1`; stale comments) | P13b (router remfix) | uncommitted | — | `P13b.md` |

Branch heads at integration: `fix/qa6r-P1` `d26aabe`, `-P2` `25fda95`, `-P3` `7376ab9`, `-P4`
`5526e95`, `-P5` `2618255`, `-P6` `93f0af9`, `-P7` `31b991a`, `-P8` `6197873`, `-P9` `ba08abb`,
`-P10` `f0d46dc`, `-P11` `c83aa16`, `-P12` `1b1e5a8`.

Merge conflicts: none in `src/` except P12's merge (`6988c80`): `toolsurface/tools_m3.py` (import
packing: P5 packed the `tools_terminal` import for the 450-line cap, P11 split it) and
`tests/orchestration/test_degradation.py` (`POPULATION`: P4 `declared_verdicts`, P5
`retry_target`, P11 `dialog_digest`); both resolved by keeping both sides, giving 14 modules and 30
functions. The declared shared qa6 files (`test_wave1_boot.py`, `test_wave2_1_cli_status.py`,
`test_wave8_1_live.py`) merged with both phases' hunks present.

## Every changed existing assertion (node ids kept unless listed under retired ids)

- **P2** `tests/engines/test_hooks_install.py::test_install_is_idempotent`: the backup is the
  pre-install image, not the first install's output (ruling 7).
- **P3** `tests/web/test_chat_qa6_live.py::test_no_step_renders_object_object`: 4 bodies → 3; the
  first result merges into its call's step (ruling 2).
- **P4** schema pins read `EXPECTED_SCHEMA_VERSION` (`test_migration_002.py`, `test_migration_003.py`,
  `test_migration_004.py`, `test_migrations.py`, `tests/cli/test_commands.py`); the one literal head
  pin is `test_migrate_expected_version_matches_the_highest_file` (`[1..5]`, `5`);
  `test_future_schema_refuses_to_start` uses `EXPECTED + 1`; `test_future_schema_refuses_to_start_at_five`
  renamed `…_at_six` (not frozen); `test_stop_rules.py:33` 20 → 21; golden coverage gains gap
  G-QR-1 for `refused`; `test_spawn.py::test_an_ensure_server_that_refuses_is_a_refusal_not_a_traceback`
  asserts the ended `refused` row; `test_degradation.py` population +`declared_verdicts`.
- **P5** `test_degradation.py` population +`retry_target` (two callables); the P5-new retry tests
  re-shaped by REM-FIX D70-R3/R4 (a human sibling retry; stopped predecessors).
- **P6** `tests/test_core_types.py::test_every_anomaly_member_is_unique_and_appended`: post-M4
  members `["MASTER_FAILED", "WAKE_TICK_FAILED"]`; `tests/toolsurface/test_tools_master.py`
  `FLEET_SUMMARY_BYTES_AT_200` 12927 → 12966 (+18 +21 bytes, one zero row per new anomaly member).
- **P7** `test_lifecycle.py::test_a_kill_whose_session_end_never_followed_is_counted` (directions 2
  and 3, per REM-FIX ruling-10 reading); `test_ask.py::test_from_fork_of_comes_from_our_own_row_not_from_the_transcript`
  and `::test_the_method_is_reported_never_silently_downgraded` (`from_fork_of` is our id, the engine
  id separate); `test_kill_stops_the_row.py::test_a_kill_after_a_turn_leaves_the_row_stopped`
  (`killed`); live `tests/e2e/test_live_ask_fork.py:174`.
- **P8** `tests/daemons/test_controld.py` docstrings "binds" → "serves"; `test_no_new_socket_is_bound`
  filtered to sockets before its retirement; `world` moved to `tests/daemons/world_fixture.py`;
  `test_a_newer_schema_closes_the_port_it_bound` strengthened.
- **P9** `test_consumer_surface_additive.py::test_web_server_is_byte_unchanged` accepts a declared
  `post_milestone` entry with the live `files` digest (ruling 11);
  `::test_the_consumer_import_sets_are_additive_only` checks `addition_violations(...)` (T24 plus
  post-M4 tables, and a manifest entry per post-M4 path).
- **P10** `test_controld.py::test_stop_returns_the_shutdown_outcome_rather_than_nothing` (frozen,
  kept) `["http", "ingest", "rpc", "scan"]`; `::test_the_process_prints_what_shutdown_found`
  (frozen, kept) `"4 threads exited · store closed"`; live `tests/qa/test_s8_status_against_a_daemon.py`
  inability tests became their positive successors (not frozen).
- **P11** `tests/web/test_session_page.py::test_the_card_never_guesses_and_never_answers` (exactly
  one `/api/` literal, the permission route); `tests/web/test_fleet_page.py::test_expansion_reads_no_log_and_no_transcript`
  (`fetch(` 2 → 3); `test_session_wiring.py::REQUIRED_ASSIGNMENTS`; `test_degradation.py`
  population +`dialog_digest`, and `returns_a_value` accepts `None` from an `X | None` callable.
- **P12** `REQUIRED_ASSIGNMENTS` (note carries `FIT_LIMITATION` alone); `test_session_page.py`
  `PTY_TOKENS`/`_ALLOWED_PTY_LINE` gain `onData`; `test_ws.py` decorator renamed and
  `test_the_module_docstring_says_what_this_server_actually_does` re-valued;
  `test_terminal_fit_live.py` one assertion; `test_ws_read_path.py::test_the_parser_tests_outnumber_the_parsers_callers`
  (frozen, kept, body asserts exactly `{pump_input}`); `tests/runner/test_local.py::test_the_module_is_within_its_line_budget`
  ≤ 500 → ≤ 508.
- **P13b** `tests/web/test_session_page.py::test_the_close_code_says_why_input_stopped`: the
  close-handler regex also requires `.reason` (1011 has two causes). Also new tests only; the
  manifest's `files` (7 paths) and four `post_milestone` `why` entries (`P13b.md`). The qa6 L6
  HTTP control (`test_wave8_1_live.py`) now sends `dialog_sha256`; its clauses are unchanged.
- **P13** `tests/boundaries/consumer_manifest.json` (`files`, `post_milestone`),
  `test_collected_node_ids.py::RETIRED_NODE_IDS` (nine entries; the `…_at_four` reason now names
  `…_at_six`), `test_consumer_surface_additive.py::POST_M4_ADDED_IMPORTS` (four paths).

## Retired node ids (in `RETIRED_NODE_IDS`, each with its successor)

| Retired | Successor | Decision | Phase |
|---|---|---|---|
| `tests/orchestration/test_spawn.py::test_an_unknown_trust_verdict_stays_unknown` | `…::test_an_unknown_trust_verdict_is_published_as_not_trusted` | §3 D78 | P4 |
| `tests/test_core_stops.py::test_stop_reason_has_twenty_members` | `…::test_stop_reason_has_twenty_one_members` | §3 D73 | P4 |
| `tests/toolsurface/test_tools_m3.py::test_send_to_a_row_with_no_pane_is_queued_not_lost` | `…::test_send_to_a_row_with_no_pane_is_refused_with_no_row` | §3 D74 | P7 |
| `tests/daemons/test_controld.py::test_the_registry_is_frozen_before_the_server_binds` | `tests/daemons/test_controld_start_order.py::test_the_registry_is_frozen_before_the_server_serves` | §3 D71 | P8 |
| `tests/daemons/test_controld.py::test_the_root_still_wires_exactly_three_threads` | `…::test_the_root_wires_exactly_four_threads` | §3 D68 | P10 |
| `tests/daemons/test_controld.py::test_no_new_socket_is_bound` | `…::test_controld_binds_exactly_its_control_and_rpc_sockets` | §3 D68 | P10 |
| `tests/boundaries/test_ws_read_path.py::test_the_ws_parser_has_no_caller_anywhere_in_src` | `…::test_the_ws_parser_has_exactly_one_caller_the_input_pump` | §3 D76 | P12 |
| `tests/web/test_session_page.py::test_the_keystroke_path_is_absent_and_says_so` | `…::test_the_keystroke_path_is_wired_and_the_page_says_nothing_false` | §3 D76 | P12 |
| `tests/web/test_ws.py::test_every_test_of_the_uncalled_parser_says_it_is_uncalled` | `…::test_every_parser_test_says_the_pump_is_its_one_caller` | §3 D76 | P12 (not in the plan's list) |

`test_ws_read_path.py::test_the_parser_tests_outnumber_the_parsers_callers` still collects (its
name is still true), so it has no entry. The existing `…_at_four` entry's reason now names
`test_future_schema_refuses_to_start_at_six` (plan F9); `…_at_five` was never frozen, so it has no
entry.

## Every changed qa6 clause (old → new, reason) — P15's declared list

| Phase | Scenario | Old → new | Reason |
|---|---|---|---|
| P1 | D12 | `verdict.unknown.mechanical_1_0` → `verdict.unknown.mechanical_0_0` | ruling 14; `UNKNOWN_CONFIDENCE = 0.0` |
| P1 | D12 | `verdict.other.mechanical_1_0` → `verdict.other.heuristic` | ruling 14; `other` defers |
| P1 | D12 | `verdict.stop_completed.mechanical_1_0` → `verdict.stop_completed.heuristic_below_1_0` | §4b plan-oracle error |
| P1 | D12 | `stream.session_state_stopped_per_session` → `stream.session_stopped_per_session` | §4b plan-oracle error |
| P1 | D12 | `verdict.verification_required/cloud_credential_error.stop_reason` (kept) `unknown` → `auth_failed`; `verdict.other.stop_reason` (kept, recorded); new `verdict.unknown.a_rule_answered` | ruling 14; REM-FIX |
| P1 | U7 | `ui.legend_text_colour.<bucket>` (kept) → probe colour; new `ui.legend_probe_resolved.<bucket>` | ruling 15 |
| P1 | U8 | (kept) `11 days ago` → `1 week ago` | ruling 16 |
| P1 | M9 | `logs.human_<tool>_l<level>` (kept) → `approved_by: policy` for `fleet_summary`, `rename_project` | ruling 24 |
| P1 | O8 | `api.mailbox_lists_k1_once_and_k3_once` → `api.mailbox_delivered_count_rose_by_2` | ruling 25 |
| P1 | L4 | `db.row_ephemeral_or_absent` (kept) also accepts a stopped non-ephemeral row | ruling 26 |
| P1 | U2 | owner sha `28067dc4…` → `f99112b6…c52b` | ruling 28 |
| P2 | H4 | `files.clause2_uninstall_restores_bytes` → `files.clause2_uninstall_removes_only_ours` | ruling 7 |
| P2 | H5 | `api.stop_string_refused` → `api.stop_string_installed` (+ `api.stop_string_warning_names_stop`, `api.stop_string_events_installed`) | ruling 23 |
| P2 | H5 | `files.stop_string_bytes_unchanged`, `…_mtime_unchanged`, `…_no_backup` → `files.stop_string_stop_untouched`, `files.stop_string_backup_holds_original` (+ `files.stop_string_managed_on_every_other_event`) | ruling 23 |
| P3 | U26 | new `ui.turn_ended_reaches_the_status_area`, `ui.no_turn_ended_line_in_the_thread`; `ui.frames_render_in_order`, `ui.prose_and_step_before_turn_ended` (kept, re-valued) | rulings 2–4, rev 4 B1 |
| P3 | U27/U28 | `ui.no_element_with_the_id_remains` → `ui.one_inline_card_with_the_outcome` | ruling 17 |
| P3 | L1 | `ui.assistant_grows_in_two_updates` (kept) ≥ 3 → ≥ 2 from a per-`ui_turn` mark, and must include the step | rulings 2–4 |
| P4 | W1 | `db.schema_version` (kept) 4 → `EXPECTED_SCHEMA_VERSION` | ruling 9 |
| P4 | C2 | `logs.database_schema_4` → `logs.database_schema_current` | ruling 9 |
| P4 | C10 | (kept) sentinel 5 → `EXPECTED_SCHEMA_VERSION + 1` | ruling 9 |
| P4 | O4 | `db.no_new_session_row` → `db.refused_row_is_ended`; `api.session_count_unchanged` → `api.session_count_rises_by_1_with_no_live_row` | ruling 9 |
| P5 | M14 | `api.third_retry_refused` → `api.retry_of_the_retry_refused_at_the_cap`; `db.retries_link_to_x` → `db.r1_retry_of_is_x`; new `api.second_retry_of_x_refused_naming_r1` (cap `retry_cap_reached`); `api.anomaly_retry_cap_plus_one` → `api.anomaly_retry_cap_plus_two`; new `stream.x_stop_woke_the_master` (recorded) | ruling 6, D70-R3/R4 |
| P7 | L8 | `api.from_fork_of_engine_id` → `api.from_fork_of_is_the_session` (+ `api.engine_id_carried_separately`) | ruling 21 |
| P10 | W4, D10, M19 | `logs.stop_line`, `logs.first_stop_line`, M19 line (kept) `3 threads exited` → `4 threads exited` (also `qa6-live-harness.json:60`) | ruling 1, D68 |
| P10 | C3 | moved from `tests/qa6/cli/test_wave2_cli.py` to `tests/qa6/sub/test_wave2_1_cli_status.py`, clauses byte-identical | RD-1 |

## Re-based paths whose `files` digest alone moved (in `rebase.regenerated_paths`)

The frozen-surface test forbids these in `post_milestone`, so their edits are recorded here:
- `web/static/chat.js` (P3): rulings 2–4 — one step per tool call (`state.steps`), `turn_ended`
  and non-stopping `rate_limit` on `#shepherd-event`, no repeated final text (`state.lastText`);
  REM-FIX: every SDK ending (incl. `error`) through one handler, the event line cleared on send, a
  failed result marked `error · `, open steps closed at turn end.
- `web/static/index.html` (P3): the `#shepherd-event` element (`aria-live="polite"`) after
  `#shepherd-status`, and its comment.
- `web/routes.py` (P11 REM-FIX): `BODY_ARGS["/api/sessions/{session_id}/permission"]` gains
  `dialog_sha256`.
- `web/static/app.css` (P11 REM-FIX): `.choice[disabled]`, `.decision-status`, and the rewritten
  `.choice-inert` comment.

Post-milestone entries written or rewritten by P13: `cli/commands.py`, `cli/main.py`,
`web/server.py` (one entry: BC-32 P9 + P9 REM-FIX + SD-05 P12 + P12 REM-FIX), `web/ws.py`,
`web/static/vendor/VERSION.txt` (new); `web/static/session.js` (P11 + P12) and
`web/static/terminal.js` (P12) rewritten to their whole divergence.

## Siblings left open (every deferred item from the ledgers)

- **P1**: O8's `GET /api/mailbox?session_id=` counts are fleet-wide; §11 status note typo
  ("shipped., scoped differently").
- **P2**: `tests/qa6/catalog.py` H4/H5 rows keep comparison-set status text (P15).
- **P3**: plan risk row `:2437` stale; `step-time` still renders `—`.
- **P4**: O4's function name reads literally false (kept to keep the qa6 node id); no stream event
  is published for a refusal (`test_a_refused_start_publishes_no_spawn_event` pins that).
- **P5**: a refused link (D70-R2) leaves a live pane for T12's reconcile; the sibling-retry race
  (two concurrent spawns naming one `retry_of`) is wider after D70-R1; `tests/qa6/catalog.py:122`
  M14 metadata (P15).
- **P6**: a capped item stays in the wake set until the next user turn and is counted once more
  after a restart; a user `master_send` during a wake turn is refused "already running"; a turn
  `_claim`ed before `close()` still builds (narrow window); an ad-hoc test order gives
  `RegistryFrozen` errors (pre-existing, not the collected order).
- **P7**: rows queued before D74 to pane-less sessions stay pending (no sweep); a retry under an
  old `idempotency_key` now gets the refusal; a session end landing during a kill with the same
  verdict tuple reads as no change; D-row follow-ups for ruling 10's reading, D74's extension to
  `ask()`'s fallback and D75's early-return ids. (The `session.js:45-47` doc-sync is closed by
  P13b, as are the stale test docstrings at `test_kill_stops_the_row.py:12,146` and
  `test_lifecycle_post_turn_kill.py:111`.)
- **P8**: `tests/qa6/launch_controld.py`'s arm (done by P10); `serve_ingest`'s `finally` skips
  unlink/release when `on_shutdown()` raises; a refused `controld.start` keeps its claim until exit;
  `compose.py:386` "binds" (now reads "serves" on the merged tree; `compose.py:17`'s order
  sentence closed by P13b).
- **P9**: the request header phase has no timeout (needs its own ruling).
- **P10**: `read_to_eof` has no size bound; a timed-out request still runs; the bind→chmod umask
  window; a non-hex `correlation_id` via the seam is refused by the daemon; `BindFailed` leaves
  started threads in-process; `tests/qa6/catalog.py:43` C3 metadata (P15). (Doctor's `fleet:`
  line beside a silent daemon is closed by P13b.)
- **P11**: a cursor move between read and click gives a fail-closed refusal. (The "master's MCP
  `answer_permission` has no digest" item was a misreading: the tool is `HUMAN`-only. P13b made
  the digest required on the web route; the RPC socket can still reach the tool without one. See
  `P13b.md`.)
- **P12**: no browser→pane resize;
  the terminal close is not audited (spec `:1251` drift, pre-existing); the loopback `Origin`
  forgery threat model; a refused key is not counted as an anomaly; `socketserver`
  `ConnectionResetError` noise in `test_an_attached_session_gets_no_reader`. (The T19-c comments
  at `index.html:325` and `app.css:1541`, the inert fixture's docstring, and the 1011
  reader-failure sentence are closed by P13b.)
- **P13**: none new beyond `P13.md`'s deviations.
- **P13b**: the RPC socket's digest-less `answer_permission`; `admission.py:211`'s cap sentence
  wording (accurate, but open to the same misreading).
- **P14 / ruling 22 (SD-09)**: deferred by the owner; O12 stays FAIL; D80 reserved.
