# qa6 owner rulings (28) — build plan

## Metadata

- Created: 2026-09-27. Revised 2026-09-27 (revisions 2, 3 and 4).
- Status: draft, revision 4. Revision 3 is committed at `fix/qa6-rulings` @ `6bf154e`; revision 4 is
  edited in the main checkout and not committed.

  **Revision 4 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap reached). This revision was amended after the last fresh pass and has been checked only by amendment verification (not run); no adversarial pass has read it whole. Sections changed since the last fresh review: Metadata; Revision 3 changes (new); Revision 4 changes (new); Agreement snapshot constraints (logging, host safety); Differences from agreement item 3; What the rulings cost §2; ADR-QR-1 (logging); ADR-QR-2; Expected qa6 outcome; Working method 1, 5a; Parallelism (shared files); P1 (checks, U-entry wording); P3; P4; P8; P10; P13; P15; Critical-path material (C-QR-2, C-QR-11, edge cases, PP19–PP20); Risk matrix; Self-review. (Amendment verification ran on revision 3 and produced the findings revision 4 applies; it has not run on revision 4.)

  Reaching the cap is a stopping point, not closure. A plan that has spent both fresh-review passes and then been amended is *unreviewed at its current revision*, however many passes it accumulated at earlier ones. The router applied fresh pass 2's findings as approved decisions under the owner's autonomy grant.
- Plan mode: `execution_plan`
- Verification rigor: `critical_path`. Reasons: a new owner-only RPC socket that runs tools with the
  HUMAN audience (security), a lifetime `flock` and a new daemon start order (concurrency, start-up
  refusal), a forward-only schema migration (irreversible on the owner's real database), a WebSocket
  read loop that writes into a live pty (concurrency, security), and a master turn opened with no
  user message (a state machine).
- Workflow: `wf-20260927T110316Z-ee74fe07`. Design file (the approved rulings):
  `docs/plans/2026-09-27-qa6-owner-rulings.md`.
- Base: **`fix/qa6-rulings` @ `87c3f4d`** (P0 done: `docs/plans/qa6-rulings-blockers/P0-baseline.md`;
  the baseline equals the qa6-bugfix P0 set plus the known s7 flaky test). `87c3f4d` is `4209fc7` plus
  that ledger. Branched from `qa/round6-full` @ `4209fc7`. Local only. **Never pushed.** (`4209fc7` is
  `5304f83` plus one docs file, `docs/backlog/2026-09-27-sd09-session-tool-channel.md`.
  `git diff --stat 5304f83 4209fc7` shows nothing else, so every `src/` and `tests/` line this
  plan cites, "measured at `5304f83`", is unchanged at `4209fc7`.)
- Evidence: `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md` §4 (`### BC-nn` / `### SD-nn`),
  §4b (plan-oracle errors). Comparison runs: `qa6-20260924T124009Z` (full),
  `qa6-20260927T061932Z` (wave 6), `qa6-20260927T062958Z` (waves 1 + 8), each a
  `<run>.json` record (plus its artefact directory) under
  `.cc10x/qa/wf-20260923T182839Z-9adb11fc/runs/`.
- Prior art: `docs/plans/2026-09-24-qa6-bugfix-plan.md` (rev 4) and its ledgers in
  `docs/plans/qa6-bugfix-blockers/`.
- plan_revision: 4 · last_reviewed_revision: 2 · planning_review_status: revised_after_review ·
  fresh-review passes: 2/2 (cap reached) · amendment_verification: run on revision 3 (findings B1,
  A1–A5), not run on revision 4
- Owner answers recorded since revision 1 (the owner's own words, relayed by the router):
  - migration 005 (ruling 9, `refused`, schema 4 → 5, forward-only): **approved**, "Go ahead -
    fix this now".
  - SD-09 / ruling 22 / P14 / OD-1: **deferred**, "Let's defer this for now". Written up in
    `docs/backlog/2026-09-27-sd09-session-tool-channel.md`. This build ships only ruling 22's
    README "not yet" line (P1).
  - RD-1 … RD-5: accepted as written (router, JUST_GO). Revision 2 changes none of them. It adds
    one related decision (a `refused` row wakes nothing, D73) that closes a loop RD-3 does not
    close. See "Revision 2 changes", finding 5.

## Revision 4 changes (amendment review of revision 3; router-decided)

Each item is a router decision, applied as approved. Lines were re-measured on the main checkout
(`fix/qa6-rulings` @ `6bf154e`).

| # | Finding | Decision applied | Where |
|---|---|---|---|
| B1 | Revision 3's precedence left ruling 3's events **invisible** whenever `#shepherd-status` held a turn id, which is almost always after a send | **The event line.** `turn_ended` and non-stopping `rate_limit` text render in a **new sibling element `#shepherd-event`** (`aria-live="polite"`), directly after `#shepherd-status` in the same status area. It is static markup in `web/static/index.html` (after `:167`) and in `tests/web/fixtures/shell_harness.html` (after `:173`), because `chat.js`'s `slot()` throws on a missing id (`:84-90`). `#shepherd-status` keeps its six writers untouched (`chat.js:141,146,160,165,343,385`), so U25, U27/U28, U46, L2 and `tests/web/test_settings_live.py:312` stay green **by construction**. Revision 3's `setStatus`/`showEvent` precedence, `data-last-event` and `title` are **dropped**: no longer needed. U26's clause reads `#shepherd-event`. `web/static/index.html` is a re-based path (`files` digest only, P13). `REQUIRED_SHEPHERD_ASSIGNMENTS` gains the writer's assignment if it adds one | P1 U-entry; Differences 3; P3; Expected outcome; 5a; P13; C-QR-11; PP19; E-QR-20; risk row; P15 list |
| A1 | L1's `before` mark must cover the retry | `before` is re-taken **immediately before each `ui_turn` call**, including the retry at `test_wave8_1_live.py:901` (the first call is at `:896`) | P3 |
| A2 | "Stale by construction" over-claims | Limited to **newly_locked** claims. A re-entrant claim holds the lock through the in-process owner, so a refused probe there means nothing about staleness | ADR-QR-2 |
| A3 | P13 step 0.3 said the main file "must be byte-unchanged" | A change in the main file's sha (or the `-wal`/`-shm`) is **recorded, not judged**: the owner's live daemon may checkpoint meanwhile. The safety proof is the `mode=ro` connection, not the sha | P13 |
| A4 | A new `shepherd`/`default` tmux socket was a hard stop | Same handling as 8787: we never create those names (ours are `shepherd-m3-*` and `shq6-*`), so a new one is owner activity. **Record it and continue.** Still never connect to it | Agreement constraints; P15 |
| A5 | P13's merge note did not name the rev-3 shared files | P13 "Merges" names `tests/qa6/sub/test_wave1_boot.py` (P4 `:127` / P10 `:46`) and `tests/qa6/live/test_wave8_1_live.py` (P3 L1 `:895-930` / P7 L8 `:1237`) as hand-resolvable disjoint hunks | P13 |

## Revision 3 changes (fresh pass 2 → revision 3; router-decided under the owner's autonomy grant)

Every item below was **decided by the router** and is applied as an approved decision. Every line
cited was re-measured on `fix/qa6-rulings` @ `87c3f4d`.

| # | Finding | Decision applied | Where |
|---|---|---|---|
| F1 | P10's fourth thread `"rpc"` changes the shutdown line. `ShutdownOutcome.__str__` prints `f"{len(self.joined)} threads exited · store closed{released}"` (`src/shepherd/daemons/shutdown.py:69`) | Declared, with every pin that moves. Default lane: `tests/daemons/test_controld.py:959` (`sorted(outcome.joined) == ["http", "ingest", "scan"]` → `["http", "ingest", "rpc", "scan"]`, inside the **frozen** `test_stop_returns_the_shutdown_outcome_rather_than_nothing`, `collected_node_ids.txt:194`; id kept, name still true) and `:1001` (`"3 threads exited"` → `"4 threads exited"`, inside frozen `test_the_process_prints_what_shutdown_found`, `:195`; id kept). `:940-948` builds its own three synthetic threads and is unaffected. qa6: W4 (`tests/qa6/sub/test_wave1_boot.py:46`, used at `:251`), D10 (`tests/qa6/sub/test_wave3_1_discovery.py:522`), M19 (`tests/qa6/inproc/test_wave5_9_shutdown.py:29`, used at `:65`; its comment `:28` says "test-plan M19, verbatim", so the test-plan text is superseded by D68, and the ledger records that), and W4's manifest text `tests/qa6/manifest/qa6-live-harness.json:60` | P10 Files; 5a; Expected outcome; P15 |
| F2 | The claim order must keep the probe on every claim | A re-entrant claim skips **only** the `flock`. The connect-probe runs on every claim, re-entrant or not. A claim that newly took the lock and is then refused by the probe releases it before raising. A re-entrant claim refused by the probe leaves the owner's lock alone. `tests/engines/test_socket_live_owner.py:120-121`, `:148-149` and `:161-176` must stay green unchanged (all three claim in-process against an in-process owner, so they exercise exactly the re-entrant-plus-probe path) | ADR-QR-2; P8; C-QR-2 |
| F3 | P3's status line can overwrite a turn id or an approval word | *(The precedence half is superseded by revision 4, B1: events now go to `#shepherd-event`. The L1 half stands.)* **Precedence:** a `turn_ended` or `rate_limit` status text never overwrites the slot's text while it holds a turn id, a send refusal, an approval word or an error. It writes text only when the slot is empty or last showed an event text. Otherwise it is carried on the slot as `data-last-event` and `title`. This keeps U25 (`test_wave7_1_master_ui.py:194-195`), U27/U28 (`:372-373`), U46 (`:670-671`), L2 (`test_wave8_1_live.py:1667`) and the live `ui_send` loop (`:843-858`) green. **L1's node-count oracle** (`test_wave8_1_live.py:924-930`, `len(this_turn) >= 3` over the last `len(turn.frames)` additions) is corrected, because rulings 2–4 break the one-node-per-frame premise its comment states (`:924`). The new oracle is ≥ 2 Shepherd-side additions (the merged tool step plus one prose line) counted from a mark taken before the send. The clause name is kept, and it is on Differences 3 and P15's list. Re-checked: no other qa6 or `tests/web` assertion counts nodes per frame. U26's own `ui.frames_render_in_order` / `ui.prose_and_step_before_turn_ended` are already P3's | P3; Differences 3; P15 |
| F4 | `rpc.py` cannot log | `src/` has no logger (`grep -rln "import logging" src` is empty), and D25's boundary forbids `toolsurface/` importing `shepherd.logs` (`tests/boundaries/_imports.py:420-446`, `logs_importer_violations`). A refusal is a **returned value** (the reply's `failure`/`error`). The constraint now reads "never `print()`; `src/` has no logger — do not add one" | Agreement constraints; ADR-QR-1; P10 |
| F5 | `core/stops.py` is at its cap: 300 lines, `assert len(source.splitlines()) <= 300` (`tests/test_core_stops.py:230`) | P4 adds `REFUSED` **net-zero** by re-wrapping code (never prose) | P4 |
| F6 | Host-safety comparisons were byte-equal | They are **semantic**: settings sha equal; the `~/.local/bin/claude` symlink target equal; the tmux socket-name **set** loses nothing and gains no `default`/`shepherd`; nothing we started listens on 8787 (P0 recorded a pre-existing listener, `Python 48395` on `127.0.0.1:8787`; it must be the same pid, untouched) | Agreement constraints; P0/P13/P15 |
| F7 | Back up the owner's real database before 005 can reach it | P13, before any merge into `fix/qa6-rulings`: resolve the real path from the host seam (`host/mac.py:70,238`: `~/Library/Application Support/Shepherd`; `controld.py:46,73`: `shepherd.db`). If it exists, take a consistent copy to the sibling `shepherd.db.pre-005.bak` without modifying the original, and record path, size and sha256 in the P13 ledger. If it is absent, record that. At planning time it **exists**: a 102400-byte `shepherd.db` with a 4 MB `-wal` beside it, and the P0 ledger shows a live listener on 8787, so a plain `cp` of the main file alone would miss committed pages. The copy uses SQLite's online backup from a read-only connection (P13) | P13 |
| F8 | P15's comparator misses two regression shapes | It also reports **PASS→BLOCKED**, and any **PASS clause that vanished** without being on the declared rename list. Both stop P15 exactly like PASS→FAIL | P15 |
| F9 | Citations | The P1 decision-count check is `orchestrator-platform.md:34` (the phrase is on `:34`). The P10 S8 instruction is corrected: the fixture uses `a_free_port()` (`tests/qa/test_s8_status_against_a_daemon.py:71`, used at `:217`), not port 0, and its teardown is `terminate()` with a `process.kill()` fallback on its own child only (`_stop`, `:234-248`). The P4 stamp uses the **injected** `now` (`spawn.py:190`), not `utc_now()`. The comparison runs are `.json` files. The `…_at_four` retirement reason (`tests/boundaries/test_collected_node_ids.py:84-93`) names `test_future_schema_refuses_to_start_at_five` as its successor (`:91`), so P13 updates that reason to `…_at_six` (P4's ledger lists it; `test_collected_node_ids.py` is still P13-only) | P1; P4; P10; P13; P15 |
| — | New shared test files surfaced by F1 and F3 | `tests/qa6/sub/test_wave1_boot.py` (P4 `:127`, P10 `:46`) and `tests/qa6/live/test_wave8_1_live.py` (P3 `:918-930`, P7 `:1237`; P1's `:1544-1545` is merged before either branches). Declared in the parallelism table, with the disjoint hunks named | Parallelism; P13 |

## Revision 2 changes (fresh pass 1 → revision 2)

Every finding is accepted. None is rejected.

| # | Finding | Change in revision 2 | Where |
|---|---|---|---|
| B1 | Migration 005's rebuild fails on `mailbox_message.session_id REFERENCES session(id)` (`003_m3_mailbox.sql:37`). `project_repo` was wrongly named | **Rehearsed**, not inferred. The real 001–004 were run on SQLite 3.53.3 (the `.venv`'s), with 2 sessions (parent and retry links) and 2 mailbox rows. 002's pattern alone fails: `MigrationRefused: … FOREIGN KEY constraint failed`. The **stash pattern** passes: mailbox rows go to a TEMP table, are deleted, `session` is rebuilt, and the rows are re-inserted. `foreign_key_check` is empty, FKs are still enforced, integrity is `ok`, and all 6 indexes are present. A lighter mechanism, `writable_schema`, also passed and is **rejected** (ADR-QR-6). Avoiding the CHECK change entirely is not possible, because `stop_reason` is a CHECK list (`002:93-100`) and the owner approved `refused` as a real value. `project_repo` is removed from the wording: only `mailbox_message` references `session` (every `REFERENCES` in `migrations/*.sql`, grepped). P4 gains a seeded-mailbox test and a negative control that proves the stash is load-bearing | What it costs §1; ADR-QR-6; P4; hidden-assumption row; PP8, PP16 |
| B2 | Schema-version pins missing from P4 | All of them re-measured and listed, with each one's treatment. Frozen status checked: `test_future_schema_refuses_to_start_at_five` is **not** in `collected_node_ids.txt`. Its predecessor `…_at_four` (line 1113) is, and it is already in `RETIRED_NODE_IDS` (`test_collected_node_ids.py:84`). The rename to `…_at_six` therefore needs no retirement entry. The ledger still records it | P4 Files, "Schema pins" |
| B3 | Two frozen ids were mislabelled "not frozen" | `tests/test_core_stops.py::test_stop_reason_has_twenty_members` (`collected_node_ids.txt:1231`, P4) and `tests/web/test_session_page.py::test_the_keystroke_path_is_absent_and_says_so` (`:1434`, P12) are now in the 5a table and in P13's `RETIRED_NODE_IDS` list, with reasons | 5a; P4; P12; P13 |
| B4 | The `--since` error text must contain "invalid" (`tests/qa6/cli/test_wave2_cli.py:119-121`) | The text is now `f"{SINCE_FLAG} {value} is an invalid date (expected YYYY-MM-DD)"`, i.e. `--since 2026-13-45 is an invalid date (expected YYYY-MM-DD)`. A unit test asserts both `2026-13-45` and `invalid` in stderr, the `shepherd: ` prefix and an empty stdout | P10 |
| B5a | Refused rows (outcome `error`, origin `orchestrator`) are wake candidates (`store/reads.py:453,460-464`), so refuse → wake → respawn loops | **Decided:** a `refused` row is excluded from `wake_candidates`. The master that asked for the spawn already holds the refusal as that call's tool result, so a wake would tell it nothing new, and a fresh (non-`retry_of`) respawn would escape RD-3. Folded into D73 as a stated refinement of D31. Built in P4 (`_WAKE_SQL`), proved at the store seam, and proved again over P4 + P6 in a new P13 integration test | D73 (P1); P4; P13; C-QR-5; PP17 |
| B5b | M14 runs at level 3 (`test_wave5_3_wake.py:247`) and kills master-spawned X (`:254`). KILLED → UNFINISHED (`stop_rules.py:64`), so after P6 a wake turn races M14's retry turn for the scripted book (`test_wave5_1_support.py:101-129`) | P5's M14 rewrite now treats the wake as part of the scenario. It drains, then goes to level 3, **pushes a scripted no-op turn for the wake**, and kills X. It then waits (`await_env`, `M12_BOUND_S`) until the book is empty, `master_last_turn_at` has moved and the slot is free, and only then sends the retry turn. A wake that never comes is BLOCKED (M12 owns that clause), never a FAIL and never a stolen script. P5 stays based on P4. The rewrite is robust to the waker whether or not P6 is present, and qa6 runs only at P15 on the integrated tree | P5; P13 integration test |
| A6 | Required kwargs break callers the plan did not list | Kept **required** (a default no-op `record_failure` would silently drop H3 in a new composition; `retry_of` follows the `engine_config_home` precedent). Every caller is listed. `TurnDriver(`: `compose.py:477`, `tests/orchestration/test_master_turn.py:274,630,719`, `test_master_turn_failures.py:61,137,181`, `tests/qa/test_s6_restart_continuity.py:123,175`, `tests/qa/test_s2_spawn_stop_wake.py:562`. `spawn_owned_session(`: `tools_m3.py:189`, `tests/orchestration/test_spawn.py:229`, `test_degradation.py:445`, `tests/e2e/test_live_owned_session.py:210` (live lane) | P5; P6 |
| A7 | The lock file is claimed before the socket dir exists (`controld.py:71` runs before `ingest_socket.py:149-151`) | `claim_socket` creates the parent at `plan.dir_mode` (the same `mkdir` + `chmod` `bind_listener` does) before it opens `<path>.lock`. New test with the runtime dir absent | ADR-QR-2; P8 |
| A8 | P4 and P10 both edit `tests/qa6/sub/test_wave2_1_cli_status.py` | Declared in the parallelism table. The hunks are disjoint (P4: the clause at `:103`; P10: an appended C3 function plus imports). P13 merges P5 (which contains P4) before P10, and resolves by hand inside that one file if git cannot | Parallelism; P13 |
| A9 | Ruling 6 says `Store.link_retry` enforces the cap; the plan enforces it in `admit()` | Listed under Differences from agreement (item 7), with the reason | Differences |
| A10 | Host-safety reads were in P15 only | The same before/after reads are now in P0, P13 and P15. They are read-only and **contact no tmux server**: `shasum -a 256 ~/.claude/settings.json`, `readlink ~/.local/bin/claude`, `ls -la /private/tmp/tmux-$(id -u)/` (a directory listing of socket files; `tmux -L shepherd ls` is removed because it contacts that server), and `lsof -nP -iTCP:8787 -sTCP:LISTEN` | P0; P13; P15 |
| A11 | P15's P14 re-run is moot | Removed | P15 |
| A12 | P10 needs unit tests for doctor, uninstall-hooks and replay over RPC | Added: `test_doctor_discovery_and_hooks_lines_come_from_the_daemon`, `test_uninstall_hooks_runs_in_the_daemon`, `test_replay_and_recompute_run_in_the_daemon` | P10 |
| A13 | Wrong citations | The spec's count line is `orchestrator-platform.md:34` ("**67 decisions** (D1–D67, plus D38.1…)") → "79 decisions (D1–D79, …)" in P1. The registry freeze prose is at `registry.py:22` (module docstring), `:203` (error text) and `:211` (docstring), all three named. P9 merges the sha `9aa9f11`, not the branch name | P1; P6; P9 |
| — | Owner: SD-09 deferred | P14 is removed from the build (a DEFERRED stub keeps its id so the numbering holds). OD-1 is gone from this plan and lives in the backlog doc. The README "not yet" line links that doc. O12 stays FAIL by owner deferral. D80 stays reserved and unwritten | Agreement; P1; P14; Expected outcome |

---

# Part 1 — Human layer (what and why)

## Agreement snapshot

- **Goal:** implement all 28 owner rulings of 2026-09-27. Each ruling's qa6 scenario turns PASS, or its
  oracle is corrected with a recorded reason. The final full qa6 run shows **0 PASS→FAIL** against
  `qa6-20260924T124009Z` plus the two 09-27 reruns.
- **Constraints (all are standing, none is new):**
  - Spec §3 is law (§0). A ruling that refines or reverses a D-row gets a **new numbered row** with its
    reasoning (D66 is the worked example). The last row today is **D67**. This plan writes
    **D68–D79** (P1). **D80** stays reserved for SD-09, which is deferred
    (`docs/backlog/2026-09-27-sd09-session-tool-channel.md` "Prerequisites" 3). No phase writes it.
  - Python 3.12. `mypy --strict src` with `disallow_any_explicit` shows **exactly** the two baseline
    errors (`host/linux.py:104`, `host/detect.py:29`). No `Any`. **Logging: never `print()` in new
    library code; `src/` has no logger, and none is added** (no `import logging` anywhere
    in `src/`, and D25's boundary forbids `toolsurface/` importing `shepherd.logs`,
    `tests/boundaries/_imports.py:420-446`). A refusal is a returned value. The two daemon `main()`s
    already print their one status line, and that stays. Small,
    single-purpose functions. argv lists only, never `shell=True`. `store/` exposes domain verbs that
    return dataclasses (D33).
  - Frontend: plain ES modules, no node/npm/tsc on this host. `tools/js_syntax_check.py` is the check.
  - **Byte-frozen consumer surfaces.** `cli/` may change only where ruling 1 authorises it (declared).
    `web/server.py` is digest-pinned under ADR-M4-7 (ruling 11 changes how that pin accepts a declared
    edit, and keeps the pin). In `tests/boundaries/consumer_manifest.json`, **`baseline` and `rebase`
    are never rewritten**. Every moved `web/` or `cli/` path gets exactly one `post_milestone.edits`
    entry, or a `files` digest only if it is in `rebase.regenerated_paths`, and
    `moved_paths(baseline, files) == regenerated_paths ∪ post_milestone` holds exactly. P13 writes
    all of this.
  - `tests/boundaries/collected_node_ids.txt` is a subset floor. A renamed or deleted frozen id
    needs a `RETIRED_NODE_IDS` entry with a reason (P13 writes them).
  - Whole-set assignment pins: `tests/web/test_session_wiring.py::REQUIRED_ASSIGNMENTS`,
    `tests/web/test_settings_page.py::REQUIRED_SETTINGS_ASSIGNMENTS`,
    `tests/web/test_chat_page.py::REQUIRED_SHEPHERD_ASSIGNMENTS`. A new assignment goes into the pin in
    the same phase, and the phase ledger records it.
  - Module caps, read from the tests: every `daemons/*` module ≤ 150 lines. `daemons/controld.py` is
    ≤ 140 (`tests/daemons/test_controld_composition.py:33,41`, `RESERVED_FOR_M2 = 10`, and both
    constants stay unedited). `orchestration/lifecycle.py` ≤ 250 (at 250). `orchestration/mailbox.py`
    ≤ 250 (at 250). `orchestration/spawn.py` and `admission.py` ≤ 300 (at 280 and 300).
    `toolsurface/tools_*.py` ≤ 450 (`tools_m3.py` 449, `tools_terminal.py` 444, `tools_projects.py`
    450). `tools_m1.py` pinned at 574. `tools_master.py` pinned at 505. Every other module ≤ 600
    (`toolsurface/compose.py` 574).
  - **Host safety (every phase, every builder):** never touch the real `~/.claude/settings.json`
    (reading its sha is allowed), port **8787**, the default tmux server, or the tmux socket
    `shepherd`. Tests use only `shepherd-m3-*`, sandbox or `-L <throwaway>` sockets, with `-L` on every
    tmux call. Never touch `~/.local`. CLAUDE.md mutation rules: a planted violation is an inert
    fixture under `tests/boundaries/fixtures/` that nothing imports. Never plant a signal, a `kill` or
    a teardown verb in executable code. Clear `__pycache__` before any mutation run. Never push. No
    bare `git stash`. Quoted heredocs only. Never `tmux kill-server` without `-L`.
  - **Worktree trap.** The shared `.venv` is an editable install of the **main checkout**. A builder in
    `.claude/worktrees/qa6r-P<n>` runs
    `PYTHONPATH=$PWD/src /Users/noamsalit/Git/Shepherd/.venv/bin/pytest …`. `pyproject` `addopts`
    already has `-q` and the `not live and not qa6 and not qa6live` filter, so do not add them again.
    **qa6 subprocesses import the main checkout**, so a qa6 run proves only the tree checked out in
    `/Users/noamsalit/Git/Shepherd`, and that is P15's job.
  - **Host-safety reads** (P0, P13 and P15, before and after; read-only; none contacts a tmux
    server): `shasum -a 256 ~/.claude/settings.json`, `readlink ~/.local/bin/claude`,
    `ls -la /private/tmp/tmux-$(id -u)/` (socket files listed, never connected to), and
    `lsof -nP -iTCP:8787 -sTCP:LISTEN`. **The comparison is semantic, not byte-equal:**
    1. the settings sha is equal
    2. the `~/.local/bin/claude` symlink target is equal
    3. the **set of socket names** in the tmux dir has nothing missing. We never create `default`
       or `shepherd` (our sockets are `shepherd-m3-*` and `shq6-*`), so a **new** `default` or
       `shepherd` socket is owner activity: **record it and continue**, and never connect to it
       (revision 4, A4). A **missing** name is a stop-and-report
    4. nothing **we** started listens on 8787. P0 recorded a pre-existing listener, `Python 48395`
       on `127.0.0.1:8787`, which is the owner's. It must be the same pid afterwards, and nobody
       touches it. A different pid is a stop-and-report, never a "fix"; only the owner restarting
       it explains one.
  - Baseline reds stay exactly as `docs/plans/qa6-bugfix-blockers/P0-baseline.md` records them: 4
    FAILED + 3 ERROR in the default lane (`--ignore=tests/qa5`), 3 ERROR in `tests/boundaries`, and 2
    mypy errors. There is one known flaky test:
    `tests/qa/test_s7_shutdown_in_flight.py::test_clause_20_holds_on_every_run_and_the_branch_is_recorded`.
- **In scope:** 27 rulings ship whole in P1–P13. Ruling 22 ships only its interim half, the
  README "not yet" line (P1), which links the backlog doc. The plan also covers their tests, the
  oracle corrections, the D-rows, the manifest and node-id declarations, the ledgers, and the P15
  verification.
- **Out of scope:**
  - the owner-decisions README's open siblings that no ruling names (P2 rename typing race, P5/P6/P10
    siblings, E6, T15-1);
  - `tests/qa5` collection on macOS;
  - INC-1 (`claude` on `PATH`);
  - M4.5 connector brokering (`ask_orchestrator`);
  - per-project scoping of any tool **not** on SD-09's channel;
  - HANDOFF checklist items other than item 2.
  - **SD-09's channel (ruling 22's build half), deferred by the owner on 2026-09-27.** It moves to
    `docs/backlog/2026-09-27-sd09-session-tool-channel.md` along with OD-1 (how a session is handed
    the channel), the K22 scope property and G-M4-16.
- **Open decisions:** **none.** OD-1 left with SD-09's deferral. Migration 005 is approved. RD-1 …
  RD-5 are accepted.

## Differences from agreement

These are the places where the plan departs from, or adds to, the design file's decomposition and
rulings. Each is also stated in the phase that carries it.

1. **15 built phases, not 10** (P0–P13 and P15; P14 keeps its id as a DEFERRED stub). The design
   file's phase 2 (small fixes) is split by file ownership into P2, P4, P7 and P8, so that parallel
   worktrees share as few files as possible (the one shared file is declared in the parallelism
   table). Its phase 8 (UI) becomes P11 and P12, run sequentially because both touch `session.js`
   and `test_session_wiring.py`. P0 (baseline), P13 (integration) and P15 (verification) are made
   explicit.
2. **Spec text lands early.** All spec §3 rows (D68–D79) and all spec, design and README prose land
   in P1, not with each code phase. Code phases then never conflict on the §3 table. D80 (SD-09)
   stays reserved, and nothing in this build writes it.
3. **Oracle corrections beyond the rulings' literal list, each with its evidence:**
   - D12's two plan-oracle clauses (report §4b): `stop_completed.mechanical_1_0` and
     `session_state_stopped_per_session`. Without them D12 cannot flip.
   - M14's retry chain and count (the declared chain; `t10.md` §T10-2's pinned cap).
   - H4 clause 2 (it follows from ruling 7's "no byte-for-byte restore").
   - U26 and U27/U28 (they follow from rulings 2, 3, 4 and 17). U26's `turn_ended` clause reads
     the new event line `#shepherd-event`, not `#shepherd-status` and not the thread (revision 4,
     B1).
   - L8 (it follows from ruling 21). Without this change it would be a PASS→FAIL.
   - **L1's node count** (`tests/qa6/live/test_wave8_1_live.py:924-930`; it follows from rulings
     2–4). Its premise is "every master.* frame renders one Shepherd node", and rulings 2–4 remove
     that on purpose: a call and its result become one step, `turn_ended` goes to the status slot,
     and a repeated final text is not rendered. The oracle becomes ≥ 2 additions counted from a
     pre-send mark (revision 3, F3).
   - **The shutdown line's thread count**, W4, D10 and M19 (`3 threads exited` → `4 threads
     exited`). It follows from ruling 1's fourth thread (revision 3, F1). M19's expected text is
     the test-plan's verbatim, and D68 supersedes it.
   - W1, C2 and C10 schema-version spellings (they follow from ruling 9's migration).
   - O4 (ruling 9).
4. **C3 moves to a daemon-backed lane (RD-1, accepted by the router).** The ruling routes
   `install-hooks` through the daemon, and C3 had none.
5. **Ruling 9 requires migration 005** (schema 4 → 5, forward-only), as a consequence of the value
   `refused`. **The owner approved it.** Its mechanism is ADR-QR-6's rehearsed stash-and-rebuild.
6. **Gate B gains a declared post-M4 import table (P9).** Rulings 1 and 18 add consumer imports, which
   T24's empty table forbids. This extends ruling 11's "accept a declared edit" rule from bytes to
   imports.
7. **Ruling 6: where the cap is enforced, and RD-2.**
   - The ruling's text says "`Store.link_retry` enforces the cap". **The plan enforces it in
     `admission.admit(retry=Retry(...))`**, which already reads the cap
     (`orchestration/admission.py:197-212`, `_retry_cap`, via `store.retry_chain_depth`) and
     already bumps `WAKE_RETRY_CAP_REACHED`. `link_retry` stays a pure writer of the link.
   - Why: a cap checked inside the link writer runs **after** the row is created
     (`create_owned_session` precedes any link), so a refused retry would leave a row. That breaks
     admission's "no row is written" rule (`admission.py:15-16`). It would also put a second cap
     reader beside `_retry_cap`. The observable behaviour the ruling wants, a declared lineage capped
     at two, is the same. D70 records the reading.
   - RD-2 (refuse a second retry of one attempt) goes beyond ruling 6's text. It closes the sibling
     bypass of the cap that ruling 6 exists to make reachable. The router accepted it.
8. **Ruling 22 is split, and its build half is deferred by the owner.** The README "not yet" line
   lands in P1. The channel is not in this build (backlog doc).
9. **Two scenarios end BLOCKED, not PASS**, on pre-existing blocks: U26 and L4.
10. **A `refused` row wakes nothing (D73, a refinement of D31).** This is not in any ruling's text.
    It follows from ruling 9 (a refused row is an ended `error` row) and ruling 5 (level 3 opens a
    turn for `error` rows). Without it the two rulings together loop: refuse → wake → a fresh
    respawn → refuse. See "Revision 2 changes" B5a.

## What the rulings cost — facts the owner should see before the build

1. **BC-28 needs schema migration 005, and it is forward-only. The owner approved it.** Ruling 9
   names the value `refused`. `stop_reason` is a SQLite `CHECK` list of exactly twenty values
   (`store/migrations/002_m2_stop_verdicts.sql:93-100`), and SQLite cannot alter a CHECK, so the
   `session` table is rebuilt. `EXPECTED_SCHEMA_VERSION` goes from 4 to 5 (`store/migrate.py:27`).
   - **002's pattern alone does not work any more**, and this was rehearsed rather than argued. Since
     003, `mailbox_message.session_id REFERENCES session(id)` (`003_m3_mailbox.sql:37`). It is the
     **only** table outside `session` that references `session`. `project_repo` references
     `workspace` and `repo` only (`004_projects.sql:33-34`).
   - `migrate()` turns `PRAGMA foreign_keys=ON` on at connect (`migrate.py:89`) and runs every
     pending migration inside one `BEGIN` (`migrate.py:167`). Inside a transaction,
     `foreign_keys=OFF` is a no-op. With FKs on, `DROP TABLE session` runs an implicit `DELETE`.
     Every mailbox row it orphans bumps the deferred-violation counter, and the rename does not
     un-bump it.
   - The rehearsal (scratchpad, real 001–004, SQLite 3.53.3, 2 sessions with parent and retry links,
     2 mailbox rows) gives `MigrationRefused: migration failed and was rolled back: FOREIGN KEY
     constraint failed` for 002's pattern alone. The **stash pattern** applies cleanly: copy the
     mailbox rows to a TEMP table, delete them, rebuild `session`, then re-insert them. The results
     were `foreign_key_check` empty, 2 mailbox rows kept, `refused` accepted, a bogus reason still
     rejected, an orphan mailbox insert still rejected, all six indexes present, and
     `integrity_check` = `ok`. ADR-QR-6 records the mechanism and the rejected alternatives.
   - Consequences:
     - The owner's real Shepherd database migrates the next time a new `controld` opens it, and an
       older binary then refuses it (migrate rule 2).
     - Three qa6 oracles that spell `4` move with it (W1 `db.schema_version`, C2
       `logs.database_schema_4`, and C10's fixture version `5`).
     - Every whole-set pin over `StopReason` moves from 20 to 21: `tests/test_core_stops.py:23-26`
       (a **frozen** id, so it is retired with a successor), `tests/signals/test_stop_rules.py:33`, and
       `tests/golden/test_next_actions_coverage.py:93`.
     - About 30 schema-version pins in `tests/store/` and `tests/cli/test_commands.py` move with it.
       Every one is listed in P4 "Schema pins".
     - A `refused` row is an ended `error` row, so it would be a D31 wake candidate
       (`store/reads.py:453,460-464`). D73 excludes it (Differences item 10).
     - No other spelling of "a `refused` verdict" is honest. A `why` string on an existing reason is
       not the value the ruling names.
2. **Ruling 1 adds a second socket that `controld` owns.** Three pins recorded that as out of scope,
   and each is retired with a successor, not bent: `test_no_new_socket_is_bound`,
   `test_the_root_still_wires_exactly_three_threads` (`tests/daemons/test_controld.py:747-777`), and
   the live `tests/qa/test_s8_status_against_a_daemon.py`, whose docstring predicts it.
   - The socket name must be **no longer than `controld`**. C8 (PASS today) crafts a `TMPDIR` in which
     `…/Shepherd/controld.sock` is exactly 103 bytes (`tests/qa6/sub/test_wave2_2_refused_starts.py`,
     `crafted_tmpdir`). A longer name would make `controld` refuse to start there.
   - The name is `rpc`.
   - The fourth thread changes the human-read shutdown line from `3 threads exited · store closed`
     to `4 threads exited · store closed` (`daemons/shutdown.py:69` counts the joined threads).
     Two frozen default-lane tests keep their ids and change a value each, and three qa6 oracles
     (W4, D10, M19) change their expected text (P10).
3. **Ruling 1 does not make `install-hooks` work with no daemon.** C3 runs the CLI with **no**
   `controld` (`tests/qa6/cli/test_wave2_cli.py:1-5`). Under ruling 1 every tool-backed command
   reaches a *running* daemon. Registering the hook installer locally as a fallback would contradict
   `cli/main.py:188-202` ("read-only local projections that … write nothing"). So C3 moves to the
   wave-2 sub lane with the running fleet daemon (RD-1).
4. **Ruling 18 reverses T19-c.** The WebSocket parser gets its first caller. The boundary rule written
   to go red on exactly that day (`tests/boundaries/test_ws_read_path.py`) is retired with a
   successor. D40 is unchanged: opening the terminal is audited, a keystroke is not.
5. **Ruling 22's channel is deferred by the owner (2026-09-27).** What it would have cost stays on
   record in `docs/backlog/2026-09-27-sd09-session-tool-channel.md`: OD-1, the K22 per-caller scope
   property, and G-M4-16. This build's only ruling-22 deliverable is the README "not yet" line, so
   O12 stays FAIL.
6. **Ruling 27 changes a principle-5 reading.** `session.spawned.trusted` becomes `false` whenever
   trust is not known to be granted. `trust.py`'s reader keeps `None` as "unknown", and
   `trust_source` still names the unknown. The frozen test
   `tests/orchestration/test_spawn.py::test_an_unknown_trust_verdict_stays_unknown` is retired with a
   successor. D78 records why.

## Ruling → phase → scenarios → code (measured at `5304f83`; `src/` and `tests/` are identical at `4209fc7`)

| # | Item | Phase | qa6 | Where the code is (file:line, read) |
|---|---|---|---|---|
| 1 | BC-05 | P10 | C1–C5 | `cli/commands.py:51-52`: `Cli.call` → local `invoke()` only. `cli/main.py:188-205` registers local reads only. `cli/main.py:105-143` parses `--since` without validating it. No socket or thread for a CLI in `daemons/controld.py:71-99` |
| 2 | BC-06a | P3 | U26 | `web/static/chat.js:400-403`: every event with a `tool_name` → its own `shepherdStep`. The call and the result are two steps. Pairing is available through `detail.tool_use_id` (`master/projection.py:199-221`) |
| 3 | BC-06b | P3 | U26 | `chat.js:405`: `shepherdSays(eventText(kind, data))` puts `turn_ended` and `rate_limit` in the thread. The status slot exists: `index.html:167` `#shepherd-status`, written only through `fill()` |
| 4 | BC-06c | P3 | U26 | `turn_ended` carries the SDK's final text (`master/projection.py:130-160`), which equals the last `text` event. Rendered twice (report L1) |
| 5 | BC-14 | P6 | M12 | Nothing opens a turn without a user message. `orchestration/master_turn.py:188-230` `send_turn(text)` is the only opener. The wake set drains only there (`:279-288`) |
| 6 | BC-15 | P5 | M14 | `toolsurface/tools_m3.py:329-342`: the schema has no `retry_of`. `orchestration/spawn.py:206-212` calls `admit()` with no `retry`. `Store.link_retry` (`store/db.py:493`) has no caller. `docs/plans/m4-blockers/t10.md` §T10-4 names exactly these two lines. The cap is read in `admission.py:197-212` (`_retry_cap`), which is where it stays (Differences 7). M14 runs at level 3 (`tests/qa6/inproc/test_wave5_3_wake.py:247`) and kills X (`:254`) |
| 7 | BC-20 | P2 | H4 | `engines/claude_code/hooks_config.py:299-301` (install) and `:369-371` (uninstall) overwrite `.shepherd-backup` on every write. The mode-000 half is fixed (P9: `test_hooks_config_unreadable.py`). Verify it |
| 8 | BC-21 C7 | P8 | C7 | `daemons/controld.py:74-77`: `open_store` runs before `create_server` |
| 9 | BC-28 | P4 | O4 | `orchestration/spawn.py:222-256`: the row is created, then `except RunnerRefusal: return SpawnRefused(...)`. The row is left live. `mailbox_message.session_id REFERENCES session(id)` (`003_m3_mailbox.sql:37`) is the one outside reference the rebuild must survive. `_WAKE_SQL` (`store/reads.py:460-464`) would select the ended row |
| 10 | BC-37 residual | P7 | — | `orchestration/lifecycle.py:130-135`: the verdict is written only when `row.ended_at is None`, and `ended_at` is stamped by every turn end. Pin: `tests/orchestration/test_lifecycle.py:372-416` |
| 11 | BC-32 | P9 | A4 | `tests/boundaries/test_consumer_surface_additive.py:280-294` compares the live digest to `pre_m4_routes.json` `server_sha256` and to the manifest `baseline`. The fix is on `fix/qa6-P10-bc32-owner` @ `9aa9f11` (`web/server.py` `_read_body`, `BODY_READ_TIMEOUT_S = 2.0`, plus `tests/web/test_server_short_body.py`). `git merge-tree` shows one add/add conflict, in the ledger `docs/plans/qa6-bugfix-blockers/P10.md` |
| 12 | H3 | P6 | — | `master_turn.py:221-229` (open failure) and `:297-311` (run failure) publish fixed text and record nothing. `core/anomalies.py` has no master-failure kind. `tests/test_core_types.py:425-445` pins M4's members as the **last** ones |
| 13 | H1-lock | P8 | (E16) | `engines/claude_code/ingest_socket.py:115-142`: the claim is a connect-probe (macOS full backlog = `ECONNREFUSED`). The claim→bind race is `controld.py:71` → `control_ingest.py:50`, and `sessiond.py:71` → `ingest_socket.py:240` |
| 14 | SD-01 | P1 | D12 | `engines/claude_code/stop_map.py:100-102,122-124`, `signals/verdict.py:49`. Spec §8 table `orchestrator-platform.md:975-993` |
| 15 | SD-02 | P1 | U7 | `web/static/app.css:834-839` (`--b-text`). Oracle: `tests/qa6/sub/test_wave6_2_flock.py:260`. Stale note: `docs/design/ui-decisions.md:117` ("`color: var(--b)`") |
| 16 | SD-03 | P1 | U8 | `web/static/flock.js:112-119` (week and month units). Oracle: `test_wave6_2_flock.py:295`. Design note: `ui-decisions.md:82` |
| 17 | SD-04 | P1 (docs) + P3 (oracle) | U27, U28 | `chat.js` `settle()` keeps the inline card with its outcome label. HANDOFF item 2 (`HANDOFF.md:177`). Oracle: `tests/qa6/inproc/test_wave7_1_master_ui.py:375` |
| 18 | SD-05 | P12 | T3, U10 | `web/server.py:273-322` never reads the upgraded socket. `terminal.js:80,169` (`INPUT_UNAVAILABLE`, `disableStdin: true`). `tools_terminal.py:207-214` `terminal_write` exists (HUMAN only) |
| 19 | SD-06 | P11 | U14 | `web/static/session.js:522-590`: `choiceRow` builds `.choice-inert`, and `DECISION_INERT`. The route exists: `web/routes.py:103,151` `/permission` → `answer_permission`. Keys: `orchestration/dialog_keys.py:72-76` |
| 20 | SD-07 | P7 | O9 | `toolsurface/tools_messaging.py:141-160`: `queue_message` runs **before** the `handle is None` branch. Pin: `tests/toolsurface/test_tools_m3.py:526-552` |
| 21 | SD-08 | P7 | O10 (and L8) | `orchestration/ask.py:199` `from_fork_of = row.engine_session_id`. `tools_messaging.py:107`. Pins: `tests/orchestration/test_ask.py:810,838`, `tests/e2e/test_live_ask_fork.py:174`, and **L8** `tests/qa6/live/test_wave8_1_live.py:1237` (PASS today) |
| 22 | SD-09 | P1 (README only); the channel is **deferred** | O12 (stays FAIL) | No channel exists. README capability 3 (`README.md:52`). Backlog: `docs/backlog/2026-09-27-sd09-session-tool-channel.md` |
| 23 | SD-10 | P1 (spec) + P2 (oracle) | H5 | `hooks_config.py` warns and leaves `Stop: "x"`. Spec install text `orchestrator-platform.md:2370-2374`. Oracle: `tests/qa6/unit/test_wave2_hooks_config.py:197-230` |
| 24 | M9 | P1 | M9 | Oracle: `tests/qa6/inproc/test_wave5_2_turns.py:529-532`. `toolsurface/policy.py:120-145` (K23) |
| 25 | O8 | P1 | O8 | Oracle: `tests/qa6/sub/test_wave4_1_owned.py:641-645`. `tools_messaging.py:176-203` lists pending messages only |
| 26 | L4 | P1 | L4 | Oracle: `tests/qa6/live/test_wave8_1_live.py:1544-1545` |
| 27 | L5 | P4 | L5 | `orchestration/spawn.py:275` `"trusted": trust.trusted` (`None` for "no entry", `trust.py:160`) |
| 28 | INC-3 | P1 | U2 / preflight | `tests/qa6/paths.py:53-55`. Guards: `tests/qa6/test_harness_guards.py:1592,1670,1695`. Text: `tests/qa6/manifest/qa6-live-harness.json:350` |

## Codebase reality check — plan-vs-code gaps found while planning

| Obvious reading of a ruling | What the code or a guard says | What this plan does |
|---|---|---|
| #1: add an RPC socket to `controld` | `controld.py` is at 140/140, and three `test_controld.py` pins forbid a fourth thread and a second socket | The wiring goes in a new ≤ 150-line `daemons/control_rpc.py` (ADR-M4-6 precedent). `controld.py` stays ≤ 140 through net-zero edits. The pins are retired with successors (P10) |
| #1: name it `controld-rpc` | C8's crafted 103-byte `controld.sock` path. `rpc.sock` is 5 bytes shorter; `controld-rpc.sock` is 4 bytes longer and would refuse | `RPC_SOCKET_NAME = "rpc"`, pinned `len(...) <= len(CONTROL_SOCKET_NAME)` (PP15) |
| #1: `cli/` calls the daemon | `cli/` may import only `toolsurface` (and `host`). Gate B (`test_consumer_surface_additive.py:211-229`) makes consumer imports additive-only against T24's **empty** table | The client lives in `toolsurface/rpc.py`. P9 adds a declared post-M4 import table beside T24's, and P13 fills it |
| #1: C3 flips | C3 has no daemon | RD-1: C3 moves to the daemon-backed wave-2 sub module |
| #1: `replay --since 2026-13-45` → 64 | C5's oracle requires `2026-13-45` **and** `invalid` (case-folded) in stderr, the `shepherd: ` prefix and an empty stdout (`tests/qa6/cli/test_wave2_cli.py:104-121`). `invalid_since_date` is not in `PARSE_ERRORS` (`:94-95`), so the usage text is not required | The problem text is `--since 2026-13-45 is an invalid date (expected YYYY-MM-DD)` (P10) |
| #5 × M14: level 3 plus a kill | M14 sets level 3 and kills a master-spawned X. After P6 that stop opens a wake turn, and the wake turn's factory call pops whatever script is in the process-global `BOOK` (`tests/qa6/inproc/master.py:104-137,171-176`). If M14's retry script is pushed first, the wake turn steals it | P5's M14 rewrite scripts the wake turn explicitly and waits for it to finish before it sends the retry turn (P5) |
| #6: add `retry_of` and link it | `tools_m3.py` is at 449/450. `admission.py` is at 300/300. `retry_chain_depth` walks **up** from `retry.of` (`store/reads.py:493-516`), so two retries both declared "of X" are both depth 1 and never refused | The admission code is unchanged (`admit(retry=Retry(...))` already exists). `tools_m3.py` stays ≤ 450 by re-wrapping. RD-2 refuses a second retry of the same attempt |
| #6: M14 passes as written | M14 expects the **third** retry refused with the first two spawned. The shipped cap refuses the **third attempt** (X + 1 retry; `t10.md` §T10-2, "depth 1 admits, depth 2 refuses"). M14's own note says it could only fake retries | M14's oracle is corrected to the declared chain: X, r1 spawned, r2 refused, anomaly +1 (P5, with the reason recorded) |
| #9: keep the row "with a verdict" | There is no `refused` StopReason, and the CHECK is fixed | Migration 005 (P4). See "What the rulings cost" §1 |
| #9: rebuild `session` the way 002 did | Since 003, `mailbox_message.session_id REFERENCES session(id)` (`003:37`). `migrate()` has FKs on (`migrate.py:89`) inside one `BEGIN` (`:167`), so `foreign_keys=OFF` is unavailable, and `DROP TABLE session`'s implicit `DELETE` orphans every mailbox row. Rehearsed: `FOREIGN KEY constraint failed` at COMMIT. 004 avoided rebuilding `session` for this family of reasons (`004_projects.sql:7-15`) | Stash the mailbox rows in a TEMP table, delete them, rebuild, re-insert (ADR-QR-6, rehearsed green). P4 tests it on a DB with mailbox rows, plus a negative control on the 002 pattern alone |
| #9 × #5: an ended `refused` row | It is `origin = orchestrator` (for a master spawn), `ended_at` set, `outcome = error`, which is exactly `_WAKE_SQL`'s population (`store/reads.py:453,460-464`). At level 3 it would open a turn, and a fresh respawn (no `retry_of`) is depth 1 again, so RD-3 does not bound it | `wake_candidates` excludes `stop_reason = 'refused'` (D73). The master already holds the refusal as its tool result (P4 store seam; P13 integration over P4 + P6) |
| #9: the version pins | `migrate(...) == 4`, `read_schema_version(...) == 4`, `schema_migration` count `== 4`, a sentinel `VALUES (5, …)` and `"schema version 4"` across `tests/store/test_migration_00{2,3,4}.py`, `tests/store/test_migrations.py` and `tests/cli/test_commands.py`. The sentinel `5` becomes a primary-key collision once 5 is real (the `…_at_four` precedent, `test_migration_003.py:424-430`) | Each is listed in P4 with its treatment: symbolic `EXPECTED_SCHEMA_VERSION` where the test means "current", and exactly one literal pin kept at the head |
| #9: spawn.py has room | `spawn.py` is at 280/300, and P5 also edits it | The refused Verdict is built in a new `orchestration/declared_verdicts.py`. P4 leaves `spawn.py` ≤ 288 |
| #11: "merge the branch" | It is based on `6c70cd3`. Its `routes.py`, `sse.py` and tests are already on the mainline (P10 → `588a75c`) | Merge it `--no-ff`. Resolve the `P10.md` add/add by keeping the mainline ledger and appending the branch's BC-32 section. Assert the net diff is exactly `web/server.py`, `tests/web/test_server_short_body.py` and `P10.md` |
| #12: "visible in the audit log" | The audit log has one record constructor, `registry.py:420` (C-M4-2, "the one record, from the one writer") | The failure record is built by a new function **in `registry.py`**, so there is still one construction site (ADR-QR-3) |
| #12: add an AnomalyKind | `tests/test_core_types.py:425-445` asserts M4's members are the last | Append a post-M4 section and change that assertion (declared). The node id is kept |
| #13: flock the socket | `bind_listener` calls `claim_socket` again inside the same process (`ingest_socket.py:151`). `flock` conflicts between two descriptors of the **same** process | A process-wide claim registry makes a second claim of a held path re-entrant (ADR-QR-2) |
| #13: `<path>.lock` beside the socket | `controld.start` claims at `controld.py:71`, before anything creates the runtime dir. Only `bind_listener` makes it (`ingest_socket.py:149-150`, `mkdir` + `chmod`, then the claim at `:151`) | `claim_socket` does the `mkdir(parents=True, exist_ok=True)` + `chmod(dir_mode)` itself, before it opens the lock file (ADR-QR-2; P8 test with the dir absent) |
| #13: lock files beside the sockets | `test_no_new_socket_is_bound` lists **every** file in the runtime dir (`test_controld.py:769-775`) | P8 filters that assertion to sockets (declared change, name still true). P10 retires it |
| #8: bind before the DB | `ThreadingHTTPServer.__init__` binds **and listens**. Requests queue in the backlog and are served only by `serve_forever` | Bind in `start()` before `open_store`. `serve_forever` still starts after `compose_tool_surface` freezes the registry. ADR-7 §4 is re-worded to "before the server serves" (P1). The frozen `test_the_registry_is_frozen_before_the_server_binds` is retired with a successor |
| #18: read the WebSocket | `test_ws_read_path.py` fails by design on the first reader. Keystrokes through `invoke("terminal_write")` would be audited per keystroke, against D40 | `TerminalStream.write()`: the `terminal_stream` open is the audited call, and keystrokes use the handle it returned (ADR-QR-4) |
| #19: make choices clickable | `session.js` "renders the answer it was given, and never parses a screen". `answer_permission` re-verifies the dialog server-side (`dialog_keys.is_the_captured_permission_dialog`) | The page maps the engine's numbers 1/2/3 to `approve` / `approve_always` / `deny` from one table. A test cross-checks that table against `PERMISSION_KEYS`. The trust dialog stays inert |
| #20: refuse at send time | The frozen pin `test_send_to_a_row_with_no_pane_is_queued_not_lost` states the opposite | Retired with a successor (P7) |
| #21: change `from_fork_of` | **L8 passes today** by asserting `from_fork_of == engine id` | L8's oracle is updated with the ruling (P7). Without it, L8 would be a PASS→FAIL |
| #22: build the channel | The Track C cut's prerequisite (2) and G-M4-16 (wrong SESSION audiences) are unmet | **Deferred by the owner.** The README "not yet" line only (P1). Everything else is in the backlog doc |
| #27: `trusted: false` | L6 answers the trust dialog when `trusted is False` (`test_wave8_1_live.py:1333`) | Watch item for P15. L6 is BLOCKED(topology) in every run so far |
| All qa6 phases | qa6 children import the main checkout | Only P15 runs qa6, in the main checkout, on the integrated branch |

## Hidden-assumption pass

| Assumption | Class | Consequence if wrong |
|---|---|---|
| `flock` holds across descriptors of different processes and is released when the process exits, even after a crash | proven_by_code (POSIX `flock(2)`, available on Linux and macOS. Not a platform branch, D55) | — |
| `HTTPServer.__init__` binds and listens, and nothing is served before `serve_forever` | proven_by_code (stdlib `socketserver.TCPServer.__init__`) | — |
| 002's rebuild pattern alone survives `mailbox_message`'s reference | **disproved** by rehearsal: `FOREIGN KEY constraint failed` at COMMIT (revision 1 had this as "inferred") | Replaced by the stash pattern below |
| Migration 005's stash-and-rebuild keeps every `session` row and column, every `mailbox_message` row, both tables' indexes, and FK enforcement | **proven_by_code (rehearsal)**: the real 001–004 plus a candidate 005, run by the real `migrate()` on the `.venv`'s SQLite 3.53.3, with 2 sessions (parent and retry links) and 2 mailbox rows. `foreign_key_check` empty, integrity `ok`, orphan insert still refused. **Critical, so P4 re-proves it in the suite** | P4's `test_migration_005.py` is written and run first. The negative control keeps the reason for the stash visible |
| Nothing depends on `mailbox_message` or `session` rowids surviving (the delete and re-insert, and the rebuild, renumber them) | proven_by_code: no `rowid` in `src/shepherd`. Mailbox reads order by `queued_at, id` and `session_id` (`store/mailbox.py:58,64`) | — |
| Browser WebSocket text and binary frames arrive masked, one `onData` string per frame | proven_by_code (RFC 6455; `ws.parse_frame` handles the mask; the T3 harness sends both opcodes) | — |
| The SDK's `rate_limit_info.status == "rejected"` is the "rate limit stops the turn" case | inferred (`data-schemas.md:3455` lists the literal. Only `allowed` is captured). RD-4 | A limit that stops a turn would render only in the status line. That is visible, not lost |
| A `refused` row wakes nothing, and nothing needs it to: the master already has the refusal as the `spawn_session` result of the turn that asked | proven_by_code: `spawn_owned_session` returns `SpawnRefused` synchronously (`orchestration/spawn.py:255-256`), and `tools_m3` projects it into that turn's tool result | — |
| The qa6 comparison treats a renamed clause as an oracle change, not a PASS→FAIL | inferred. P15's comparator lists every renamed clause | A false regression in the report. It is checked by hand against the ledger list |

## Recommended defaults — accepted by the router (JUST_GO), each low blast radius

Revision 1 listed these as unapproved. The router has since accepted all five as written. Revision 2 changes none of them. The one related addition, D73's wake exclusion, is a separate decision (Differences 10), not a change to RD-3.

- **RD-1 (ruling 1, C3).** C3 moves from `tests/qa6/cli/test_wave2_cli.py` (no daemon) to
  `tests/qa6/sub/test_wave2_1_cli_status.py`, against the running fleet daemon. Wave 2 runs both lanes,
  so the harness guard's wave rule holds. With no daemon, `install-hooks` keeps today's "start the
  shepherd control daemon" answer.
- **RD-2 (ruling 6).** A retry of a session that already has a retry is **refused**, with a reason
  naming the existing retry ("retry that one instead"), and no cap anomaly. Without this, siblings
  declared "of X" bypass D31's cap forever (`retry_chain_depth` walks up only). The cost is one store
  read verb, `Store.retried_by(session_id) -> str | None`.
- **RD-3 (ruling 5, "counts toward the cap").** An unprompted level-3 turn opens for a stopped
  session only while its lineage is below `MAX_MASTER_ATTEMPTS`
  (`retry_chain_depth(session) < 2`). A stop in a lineage already at the cap opens no turn, bumps
  `WAKE_RETRY_CAP_REACHED` **once per session** (not once per 2 s pass), and waits for the next user
  turn, the level-2 behaviour. The reason for this reading: the master could not act on such a wake,
  because admission would refuse its retry.
  - **What RD-3 does not bound, and what does.** RD-3 reads the `retry_of` chain, so a respawn with
    no `retry_of` starts a new lineage at depth 1. A start the runner refuses would therefore wake
    the master again and again. That loop is closed by D73's exclusion of `refused` rows from the
    wake set, not by RD-3.
- **RD-4 (ruling 3).** "A rate limit that stops the turn" means `detail.rate_limit.status ===
  "rejected"`. Every other `rate_limit` goes to `#shepherd-status`.
- **RD-5 (ruling 20).** "Attached (pane-less)" is read as `row.runner_handle is None`, the branch that
  exists today (`tools_messaging.py:149-160`). That covers attached rows **and** T12's handle-less
  orphans. An orphan re-adopted later is sent to again by the caller, never by a stale queued row.

## SD-09 and OD-1 — deferred by the owner

Revision 1 carried an open decision here, OD-1: how a `claude` session is handed ruling 22's
channel. On 2026-09-27 the owner deferred SD-09 as a whole ("Let's defer this for now"). OD-1, its
three options, the K22 per-caller scope property and G-M4-16 now live in
`docs/backlog/2026-09-27-sd09-session-tool-channel.md`, which is the one place to pick them up.
**Nothing in this build depends on OD-1**, and this plan holds no open decision. The only ruling-22
work here is P1's README line.

## ADRs (inline)

### ADR-QR-1: the CLI↔daemon RPC wire and where it lives

- **Context.** Ruling 1 sets the shape: one JSON request, then `registry.invoke()` with the HUMAN
  audience, then one JSON reply. `cli/` may import only L4. `daemons/` holds no logic (ADR-1).
- **Decision.** The wire and its logic live in **`toolsurface/rpc.py`** (L4): `answer_request` (bytes
  in, bytes out, pure apart from `invoke`) and `call_remote` (the client). The server loop is
  **`daemons/control_rpc.py`** (L6 wiring only: `bind_listener`, `accept_next`, `read_to_eof`,
  `answer_request`), started by `controld.start()` as thread `"rpc"`.
- **Framing** (the ingest hop's own framing): the client writes one JSON object, then
  `shutdown(SHUT_WR)`. The server reads to EOF (≤ `MAX_REQUEST_BYTES = 1 MiB`, 1 s idle timeout),
  writes one JSON reply, and closes.
- **Request** `{"v": int (== 1), "tool": str (1..128 chars, required), "args": object (required, may
  be {}), "correlation_id": str (32 lowercase hex, required)}`. **No audience field.** The server sets
  `CallerContext(audience=HUMAN, caller_id="cli", correlation_id=…)`.
- **Reply** `{"v": 1, "ok": bool, "data": JSON value or null, "error": str or null, "failure":
  "refused" | "failed" | "unavailable" | null}`.
- **Bad requests.** A malformed request (bad JSON, too big, wrong `v`, a missing field) gets
  `{"ok": false, "failure": "refused", "error": "bad request (correlation_id=<id or minted>)"}`, and
  **`invoke` is not called** (no audit row).
- **Unsendable data.** Data that cannot be JSON-encoded (for example a `TerminalStream`) →
  `failure: "failed"`, `error: "not transportable"`.
- **No logging.** A refusal is the reply's returned `failure` and `error`, and nothing is logged:
  `src/` has no logger, and D25 forbids `toolsurface/` importing `shepherd.logs` (revision 3, F4).
  An invoked call is audited by `invoke`, exactly as the web UI's are.
- **Client.** `call_remote(path, name, args, ctx, timeout_s=120.0) -> ToolResult | None`.
  `FileNotFoundError` or `ConnectionRefusedError` on connect → `None`, and the caller falls back to
  local `invoke`. Any failure after the connect → `ToolResult(ok=False, failure=Failure.FAILED,
  error="the daemon did not answer: <class name>")`.
- **Rejected.**
  - Loopback HTTP: any local process can reach the port, the tools are not routed, and `server.py` is
    pinned.
  - Multiplexing the control-ingest socket: one-way, with a versioned hello.
  - A client-declared audience: it puts a security field in the caller's hands (`registry.py:444-451`
    rejected the same shape).
- **Consequences.** Same uid = same trust as the loopback page, recorded in D68. The socket is 0600 in
  the 0700 dir (`plan.sock_mode`, `plan.dir_mode`).
- **Reversibility.** Reversible.

### ADR-QR-2: the lifetime lock

- **Decision.** `claim_socket(plan)` first makes sure the socket's directory exists at the plan's
  mode: `plan.path.parent.mkdir(parents=True, exist_ok=True)` then `os.chmod(plan.path.parent,
  plan.dir_mode)`. These are the two statements `bind_listener` runs today
  (`ingest_socket.py:149-150`). They run here because `controld.start` claims at `controld.py:71`,
  before anything else has created the runtime dir. `bind_listener` keeps its own copy, which is
  harmless and idempotent. Then `claim_socket` takes `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on
  `<plan.path>.lock` (created 0600 in that dir). The lock is held in a process-wide registry
  `{path: fd}` until `release_claim(path)`, which each `serve_*` listener calls in its `finally`
  after the owned unlink.
- **The order inside `claim_socket`, exactly** (revision 3, F2):
  1. make the dir (above)
  2. **lock step.** If `plan.path` is already in `_HELD` (this process holds it), skip **only**
     the `flock`, and remember `newly_locked = False`. Otherwise open `<path>.lock` and take the
     `flock`. `BlockingIOError` → `SocketInUse`, with nothing registered and the fd closed. Then
     register `{path: fd}` and remember `newly_locked = True`.
  3. **probe step, on every claim, re-entrant or not:** `if plan.path.exists() and
     _is_live(plan.path)` → refuse with `SocketInUse`. Before raising, **if `newly_locked`**,
     release what step 2 took (unregister, `LOCK_UN`, close). If it was re-entrant, leave the
     holder's lock alone: the in-process owner still owns it.
  4. return `plan`
- **Why the probe survives re-entrancy.** Two callers make a re-entrant claim meet a live socket.
  One is `bind_listener`'s inner claim. The other is a second in-process listener on a path an
  in-process owner serves. `tests/engines/test_socket_live_owner.py:120-121`, `:148-149` and
  `:161-176` are exactly that shape: an in-process owner, then `claim_refusal(plan)` or a second
  `bind_listener(plan)` that must be `SocketInUse` without harming the owner. They must stay green
  **unchanged**. A re-entrant claim that skipped the probe would turn them red, and it would let
  an in-process second bind unlink a live socket.
- **Probe kept for other processes too.** With the lock held, the connect-probe still runs, to
  refuse an older binary that holds no lock. **For a `newly_locked` claim only**, a path that
  exists and refuses the probe is stale by construction. No live Shepherd holds the lock, so the
  macOS full-backlog case can no longer be mistaken for a free path. For a **re-entrant** claim the
  lock proves nothing new (this process's own owner holds it), so a refused probe there is just
  "not live now" and carries no staleness claim (revision 4, A2).
- **Lock files are never unlinked.** Unlinking lets two processes lock two different inodes.
- **Rejected.** Returning a `Claim` object: that changes the signatures of `serve_ingest`,
  `serve_control_ingest`, `sessiond.main` and every test caller for the same guarantee.
- **Consequence.** A refused start in a test process leaks its claim to that process only. The next
  start in the same process is re-entrant, and another process is refused until this one exits.
- **Reversibility.** Reversible.

### ADR-QR-3: how a master failure reaches the audit log

- **Decision.** `registry.audit_master_failure(turn_id: str, error_class: str) -> None` builds the one
  `AuditRecord` type **in `registry.py`**:
  - `tool="master_send"`, `blast_class=` that tool's own
  - `actor_kind=MASTER`, `actor_id="master"`
  - `decision="allow"`, `result="failed"`, `failure=Failure.FAILED`
  - `args={"turn_id": …, "error_class": <class name only>}`
  - `autonomy_level=UNREPORTED_AUTONOMY_LEVEL`, `approved_by=None`, `approval_id=None`
  - `correlation_id=turn_id`, `duration_ms=0`

  It hands the record to the installed sink. It is a no-op with no chokepoint.
- **Wiring.** `compose.py` injects `record_failure=lambda turn_id, error_class: (store.bump_anomaly(
  "master_failed"), registry.audit_master_failure(turn_id, error_class))`, written as a named
  function, into `TurnDriver`.
- **Rejected.** Constructing `AuditRecord` in `orchestration/` (a second writer), and an anomaly with
  no record (not "visible in the audit log").
- **Reversibility.** Reversible.

### ADR-QR-4: the keystroke path

- **Decision.** `TerminalStream` gains `write(data: bytes) -> None`, bound at `terminal_stream()` to
  `runner.write(handle, data)`. `web/server.py::_terminal` starts one reader thread per connection,
  running `ws.pump_input(read=self.rfile.read1, deliver=stream.write)`.
- **`ws.pump_input`.** It parses masked client frames with `parse_frame`:
  - text and binary payloads are delivered verbatim (text is UTF-8 encoded)
  - a close frame, or a read that returns nothing, ends the pump and calls `stream.close()`, which
    ends `chunks()`
  - ping is ignored
  - an oversize frame ends the pump (the close frame goes out on the writer side)
- **Why the audit stays D40's.** The **open** is the audited `invoke("terminal_stream")`. Keystrokes
  go through the handle it returned, so they are not tool calls, which is what D40 says. The origin
  check and handshake validation stay first (`server.py:285-305`).
- **Rejected.** `invoke("terminal_write")` per frame (it audits each keystroke), and a POST route
  (`test_session_page.py::test_the_keystroke_path_is_absent_and_says_so` notes the route closure).
- **Reversibility.** Reversible.

### ADR-QR-5: level-3 wake queueing

- **Decision.** `orchestration/wake.py::LevelThreeWaker(store, level, open_wake, bump)` has
  `tick() -> bool`. It is called from the existing 2 s sweep (`compose.py:514`), so no thread is
  added. At level 3 with an eligible item (RD-3) it calls `TurnDriver.wake_turn()`.
  - **Busy.** If a turn holds the slot, `wake_turn` returns `None`, and the next tick offers the wake
    again. The set is not drained until a turn opens, so the stop is queued, never dropped.
  - **Drained elsewhere.** A user turn that opens first drains the set into its own summary (the
    level-2 path), and the waker then finds nothing.
  - **Refused starts.** The set the waker reads (`store.wake_candidates`) excludes `stop_reason =
    'refused'` rows (D73, P4). A start the runner refused is reported to the master synchronously,
    as its `spawn_session` result, so it never wakes it.
- **Rejected.** A pending flag checked in `_release` (a turn opened from the releasing worker thread's
  `finally`), and a subscriber on the stream ring (a second consumer with its own cursor to lose).
- **Reversibility.** Reversible.

### ADR-QR-6: how migration 005 widens `stop_reason`

- **Context.**
  - The approved value `refused` needs `stop_reason`'s CHECK widened (`002:93-100`).
  - SQLite cannot ALTER a CHECK. `migrate()` runs with `foreign_keys=ON` inside one `BEGIN`
    (`migrate.py:89,167`).
  - `mailbox_message` references `session` (`003:37`).
- **Options, measured** (scratchpad rehearsal over the real 001–004, SQLite 3.53.3, seeded with
  sessions that have parent and retry links, plus mailbox rows):
  1. **002's rebuild alone** (`defer_foreign_keys=ON`, `session_new`, copy, drop, rename,
     re-index). **Fails:** `FOREIGN KEY constraint failed` at COMMIT. The implicit `DELETE` of
     `DROP TABLE` leaves the deferred counter positive.
  2. **Stash, then rebuild.** Chosen.
     1. `PRAGMA defer_foreign_keys=ON` (kept for the self-references `parent_session_id` and
        `retry_of`).
     2. `CREATE TEMP TABLE mailbox_stash AS SELECT <10 named columns> FROM mailbox_message`, then
        `DELETE FROM mailbox_message`.
     3. 002's rebuild with `'refused'` appended to the list: all 52 columns named on both sides,
        the other CHECKs byte-identical, then `ix_session_fleet` and `ux_session_engine_id`
        recreated.
     4. `INSERT INTO mailbox_message (<10 named columns>) SELECT <same> FROM mailbox_stash`, then
        `DROP TABLE mailbox_stash`.

     **Passes**, with every property in "What it costs" §1. The mailbox indexes are untouched
     because that table is never dropped.
  3. **Rebuild `mailbox_message` too** (drop it, rebuild `session`, recreate the mailbox table and
     its two indexes). Rejected: it re-declares 003's table (a second definition site of its
     columns, CHECK and indexes), for the same outcome as option 2.
  4. **`PRAGMA writable_schema=ON` plus `UPDATE sqlite_master SET sql = replace(…)`.** It also passed
     the rehearsal, and it is the lightest option. Rejected for three reasons:
     - SQLite documents it as able to corrupt the database file.
     - It is refused under `SQLITE_DBCONFIG_DEFENSIVE`.
     - It edits the schema text by string replacement, so it would go silently wrong if a future
       build's stored text differed. A forward-only migration on the owner's real database is the
       wrong place for the only unsafe mechanism.
  5. **No CHECK change** (a `why` on an existing reason, or a NULL `stop_reason`). Rejected: the
     owner approved `refused` as a real stop reason, and ruling 9's "a `refused` verdict" is not
     spelled any other way (What it costs §1).
- **Consequences.**
  - 005 is plain DDL and DML with no string literal and no trigger, like 004
    (`test_004_holds_no_trigger_and_no_semicolon_inside_a_string_literal` is mirrored for 005).
  - The whole 001 → 005 chain still runs in one transaction.
  - `session` and `mailbox_message` rowids are renumbered. Nothing reads them (hidden-assumption
    pass).
  - It is irreversible once the owner's database has applied it (migrate rule 2).
- **Reversibility.** Irreversible on any database that applied it. The mechanism itself is
  replaceable before P4 merges.

## Expected qa6 outcome (P15)

- **FAIL→PASS (24):** C1 C2 C3 C4 C5 C7 M9 M12 M14 H4 H5 O4 O8 O9 O10 A4 D12 U7 U8 U10 U14 U27 U28
  T3.
  - C3's flip rests on RD-1, which the router accepted.
- **FAIL→BLOCKED (3):**
  - **U26** keeps the pre-existing harness block `ui.two_prose_lines_each_as_it_arrives`
    (SCOPE_INCREASE; the harness cannot script two text events in one turn).
  - **L4** keeps `files.stop_classification` and `files.keyset_parity` BLOCKED(topology).
  - **L5** keeps `db.idle_needs_you` BLOCKED on the 09-27 rerun. It is PASS if that clause is
    reached.
- **Stays FAIL by owner deferral:** O12 (SD-09). README says "not yet" and links the backlog doc. It is
  not a regression, because it is FAIL in the comparison set too.
- **No PASS→FAIL, no PASS→BLOCKED, no vanished PASS clause** (F8).
- **PASS scenarios whose oracles move with a ruling**, each of which must still PASS:
  - W1 (schema version) and C10 (fixture version), from P4
  - L8 (`from_fork_of`), from P7
  - **W4, D10 and M19** (the shutdown line `3 threads exited` → `4 threads exited`), from P10
  - **L1** (the node-count clause `ui.assistant_grows_in_two_updates`, ≥ 3 per-frame → ≥ 2 from a
    pre-send mark), from P3
- **PASS scenarios that read `#shepherd-status`, untouched by construction** (P3 never writes
  that slot; events go to `#shepherd-event`): U25 (`ui.1_status_turn_id`), U27/U28
  (`ui.status_says`), U46 (`ui.late_click_says_already_decided`), L2 (`ui.status_says_approved`),
  and every live-lane send through `ui_send`. Oracles unchanged.
- **Watch list, not expected to move:**
  - C8: socket budget, PP15
  - L6: the trust branch
  - U25 and U29–U32: `chat.js`
  - M11, M13, M18: the master turn driver (M11 and M13 kill at level 2, so no wake turn; M18's
    turn failure now also bumps `master_failed`)
  - D1–D11, D13, E-lane: the flock
  - O1–O3, O5–O7: spawn and messaging
  - H1–H3: backup

---

# Part 2 — Execution contract

## Context references (read before building)

- `CLAUDE.md`: tmux `-L`, inert fixtures, `__pycache__`.
- The design file `docs/plans/2026-09-27-qa6-owner-rulings.md`: the 28 rulings, verbatim authority.
- `docs/specs/orchestrator-platform.md`:
  - §0 and §3: D8, D12, D13, D19, D31, D38, D38.1, D40, D45, D53, D55, D66 (format)
  - §8 (lines 969-1005)
  - §9 write policy and §9.5 (1199-1300)
  - §11 bindings (1756-1804)
  - §12 Page 1
  - install text (2365-2374)
- `docs/specs/logical-architecture.md`: layers, the consumer boundary, L6.
- `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` ADR-7 (lines 1195-1210).
- `docs/plans/2026-09-17-m4-orchestrator-plan.md`: "The Track C cut" (84-135), ADR-M4-7 (814), and
  G-M4-15/16/18.
- `docs/plans/m4-blockers/t10.md`: T10-1…T10-4, the retry writer and the cap.
- `docs/plans/qa6-bugfix-blockers/README.md` (context, E16, siblings) and `P0-baseline.md`
  (reference reds).
- Boundary machinery:
  - `tests/boundaries/_imports.py` (`moved_paths`, `post_milestone_paths`, the layer map)
  - `test_consumer_surface_frozen.py`, `test_consumer_surface_additive.py`
  - `test_collected_node_ids.py` (`RETIRED_NODE_IDS`, the subset check)
  - `test_ws_read_path.py`, `test_session_audience.py`
- Caps: `tests/daemons/test_controld_composition.py`, `tests/toolsurface/test_tools_m3.py:380-430`,
  `tests/orchestration/test_lifecycle.py:86,776`, `tests/orchestration/test_spawn.py`
  (`test_the_modules_stay_small`).
- The real-browser seam: `tests/web/fixtures/shell_harness.html`, `tests/web/test_settings_live.py`,
  `tests/web/test_decision_live.py`.
- `tests/qa6/BUILDING.md` (verdict rules, lane dirs, guards) and `tests/qa6/run.py` (`--wave N`
  repeatable; wave 8 needs wave 1 in the same run).

## Working method (every phase)

1. **Branching.** P0 created **`fix/qa6-rulings`** from `qa/round6-full` @ `4209fc7`, in the main
   checkout. It is now at `87c3f4d`, carrying the P0 ledger. **P0 is done.** Each later phase `<n>` is built in its own worktree:
   `git -C /Users/noamsalit/Git/Shepherd worktree add .claude/worktrees/qa6r-P<n> -b fix/qa6r-P<n> <base>`.
   `<base>` is `fix/qa6-rulings` after P1 is merged into it, except:
   - P5 uses `fix/qa6r-P4`
   - P10 uses `fix/qa6r-P8`
   - P12 uses `fix/qa6r-P11`, then `git merge --no-ff fix/qa6r-P9` inside the P12 worktree before any
     edit

   Worktrees are removed only with `git worktree remove`. Commits stay local.
2. **TDD.** Write the phase's new tests first and run them. Record the **RED** output (a failing
   assertion, not an import error unless the ledger says why) in the ledger. Then fix, then GREEN.
   Oracle-only edits (qa6 files) have no RED. Their reason is recorded instead.
3. **Ledger.** Each phase writes exactly one ledger, `docs/plans/qa6-rulings-blockers/P<n>.md`. It
   holds:
   - RED/GREEN
   - every changed existing assertion, with its reason
   - every changed qa6 clause, old name → new name, with its reason
   - every new consumer import and module
   - every moved `web/` or `cli/` path, with a one-paragraph `why` for P13
   - every retired node id, with its successor and reason
   - deviations, and siblings left open
4. **Commands** (from the worktree root; `$W` is its absolute path; each is one Bash call):
   - tests: `cd $W && PYTHONPATH=$W/src /Users/noamsalit/Git/Shepherd/.venv/bin/pytest -p no:randomly <paths>`
   - boundaries: `cd $W && PYTHONPATH=$W/src /Users/noamsalit/Git/Shepherd/.venv/bin/pytest -p no:randomly tests/boundaries`
   - types: `cd $W && PYTHONPATH=$W/src /Users/noamsalit/Git/Shepherd/.venv/bin/mypy --strict src`
     (exactly the 2 baseline errors)
   - JS: `cd $W && PYTHONPATH=$W/src /Users/noamsalit/Git/Shepherd/.venv/bin/python tools/js_syntax_check.py <files>`
     (`0 failure(s)`)
   - qa6 module import check (collects only, starts nothing):
     `cd $W && PYTHONPATH=$W/src /Users/noamsalit/Git/Shepherd/.venv/bin/pytest -p no:randomly --collect-only -m "qa6 or qa6live" <qa6 files>`
   - harness guards: `… pytest -p no:randomly tests/qa6/test_harness_guards.py`
5. **Known-red until P13** (only these, only in the phases named):
   - `tests/boundaries/test_consumer_surface_frozen.py::test_completing_l4_changed_no_consumer_byte`
     and `::test_a_rebase_declares_every_path_whose_digest_moved`: P3, P9, P10, P11, P12
   - `tests/boundaries/test_consumer_surface_additive.py::test_web_server_is_byte_unchanged`: P9, P12
   - `::test_the_consumer_import_sets_are_additive_only`: P10, P12 (only if a consumer import was
     added; list it)
   - the 3 baseline `test_collected_node_ids.py` ERRORs: always

   No other red is acceptable.
5a. **Per-phase declaration table.** Every phase touches only the manifest paths, whole-set pins and
    D-rows listed here. "none" is a checked statement, not an omission.

    | Phase | Manifest paths needed (written by P13) | Whole-set assignment pins | D-rows / ADRs cited | Retired ids |
    |---|---|---|---|---|
    | P1 | none | none | writes D68–D79; amends ADR-7 §4 and ADR-M4-7 | none |
    | P2 | none | none | spec install text (P1) | none |
    | P3 | `web/static/chat.js`, `web/static/index.html` (both re-based: `files` digest only) | `REQUIRED_SHEPHERD_ASSIGNMENTS` (the `#shepherd-event` writer's assignment included, if it adds one) | U-entry (P1) | none. L1's clause is re-valued, not renamed |
    | P4 | none | none | D73 (incl. the wake exclusion), D78; ADR-QR-6 | `tests/orchestration/test_spawn.py::test_an_unknown_trust_verdict_stays_unknown` (frozen, `collected_node_ids.txt:692`); `tests/test_core_stops.py::test_stop_reason_has_twenty_members` (frozen, `:1231`). Renamed but **not** frozen: `tests/store/test_migration_003.py::test_future_schema_refuses_to_start_at_five` → `…_at_six` (ledger only) |
    | P5 | none | none | D70 | none |
    | P6 | none | none | D69, D79; D71 docstrings | none |
    | P7 | none | none | D74, D75 | `test_tools_m3.py::test_send_to_a_row_with_no_pane_is_queued_not_lost` |
    | P8 | none | none | D71, D72; ADR-7 §4 | `test_controld.py::test_the_registry_is_frozen_before_the_server_binds` |
    | P9 | `web/server.py` | none | ADR-M4-7 amendment | none |
    | P10 | `cli/main.py`, `cli/commands.py` | none | D68, ADR-QR-1 | `test_controld.py::test_no_new_socket_is_bound`, `::test_the_root_still_wires_exactly_three_threads`. **Kept ids with a changed value** (F1): `test_controld.py::test_stop_returns_the_shutdown_outcome_rather_than_nothing` (frozen, `:194`; `:959`) and `::test_the_process_prints_what_shutdown_found` (frozen, `:195`; `:1001`). Both names stay true |
    | P11 | `web/static/session.js` | `REQUIRED_ASSIGNMENTS` | D77 | none |
    | P12 | `web/server.py`, `web/ws.py`, `web/static/terminal.js`, `web/static/session.js` | `REQUIRED_ASSIGNMENTS` | D76, ADR-QR-4 | `tests/boundaries/test_ws_read_path.py::test_the_ws_parser_has_no_caller_anywhere_in_src` (frozen, `:58`); `tests/web/test_session_page.py::test_the_keystroke_path_is_absent_and_says_so` (frozen, `:1434`); `…::test_the_parser_tests_outnumber_the_parsers_callers` (frozen, `:60`) only if its name becomes false |
    | P13 | none of its own (it writes everyone's) | none | none | writes the entries |
    | P14 | DEFERRED, not built | — | D80 stays reserved | — |

    `REQUIRED_SETTINGS_ASSIGNMENTS` is touched by no phase. Every "frozen" and "not frozen" in this
    table was checked by `grep -n` against `tests/boundaries/collected_node_ids.txt` at `4209fc7`.
    A builder who renames or deletes **any other** test id greps that file first. A hit means a
    `RETIRED_NODE_IDS` entry through P13. `subset_violations` also flags as "stale" any retired id
    that is not actually missing: one that still collects, or one that was never frozen
    (`test_collected_node_ids.py:263-268`). Each entry's decision string must
    contain `§` or `RD-`, and its reason must be longer than 80 characters (`:331-337`).
6. **Files no phase before P13 edits:** `tests/boundaries/consumer_manifest.json`,
   `tests/boundaries/test_collected_node_ids.py`, and the entries (not the mechanism) of the post-M4
   import table in `test_consumer_surface_additive.py`. **No phase after P1 edits the spec §3 table.**

## Parallelism and ordering

| Phase | Rulings | Base | Can run in parallel with | Main files (disjoint, except the one shared file declared below) |
|---|---|---|---|---|
| P0 | baseline | `4209fc7` | — (first) | none (ledger only) |
| P1 | 14 15 16 17(docs) 22(README) 23(spec) 24 25 26 28 + D68–D79 | P0 | — (merged before any code phase branches) | docs; qa6 D12/U7/U8/M9/O8/L4 hunks; `tests/qa6/paths.py`, guards |
| P2 | 7, 23(oracle) | P1 | P3 P4 P6 P7 P8 P9 P11 | `engines/claude_code/hooks_config.py`; `tests/qa6/unit/test_wave2_hooks_config.py` |
| P3 | 2 3 4, 17(oracle) | P1 | P2 P4 P6 P7 P8 P9 P11 | `web/static/chat.js`; `tests/web/test_chat_page.py`; `tests/qa6/inproc/test_wave7_1_master_ui.py`; `tests/qa6/live/test_wave8_1_live.py` L1 hunk (shared with P7) |
| P4 | 9, 27 | P1 | P2 P3 P6 P7 P8 P9 P11 (and P10, see the shared file) | `orchestration/spawn.py`, `declared_verdicts.py` (new), `core/stops.py`, `signals/stop_rules.py`, `store/migrate.py`, `store/migrations/005_*.sql`, `store/reads.py` (`_WAKE_SQL`); `tests/store/test_migration_00{2,3,4}.py`, `tests/store/test_migrations.py`, `tests/store/test_wake_reads.py`, `tests/cli/test_commands.py` (the schema lines only); qa6 W1/C2/C10/O4 hunks, including **`tests/qa6/sub/test_wave2_1_cli_status.py:103`** |
| P5 | 6 | **P4** | P6 P7 P8 P9 P11 (after P4) | `orchestration/spawn.py`, `toolsurface/tools_m3.py`, `master/prompt.py`, `store/reads.py`, `store/db.py`; `tests/orchestration/test_degradation.py` (`:445`); qa6 M14 |
| P6 | 5, 12 | P1 | P2 P3 P4 P5 P7 P8 P9 P11 | `orchestration/master_turn.py`, `orchestration/wake.py`, `core/anomalies.py`, `toolsurface/registry.py`, `toolsurface/compose.py`; the `TurnDriver(` test callers (`tests/orchestration/test_master_turn.py`, `test_master_turn_failures.py`, `tests/qa/test_s6_restart_continuity.py`, `tests/qa/test_s2_spawn_stop_wake.py`) |
| P7 | 10, 20, 21 | P1 | all of P2–P6, P8, P9, P11 | `orchestration/lifecycle.py`, `orchestration/ask.py`, `toolsurface/tools_messaging.py`; qa6 L8 (`tests/qa6/live/test_wave8_1_live.py:1237`, shared with P3) |
| P8 | 8, 13 | P1 | P2–P7, P9, P11 | `daemons/controld.py`, `daemons/sessiond.py`, `daemons/control_ingest.py`, `engines/claude_code/ingest_socket.py`, `toolsurface/export.py` (docstring) |
| P9 | 11 | P1 | P2–P8, P11 | `web/server.py` (merge), `tests/boundaries/test_consumer_surface_additive.py`, `docs/plans/qa6-bugfix-blockers/P10.md` |
| P10 | 1 | **P8** | P11 and P4–P7 (after P8) | `toolsurface/rpc.py` (new), `daemons/control_rpc.py` (new), `daemons/controld.py`, `cli/main.py`, `cli/commands.py`; qa6 C3 move, which appends to **`tests/qa6/sub/test_wave2_1_cli_status.py`**; the shutdown-line pins in `tests/daemons/test_controld.py`, **`tests/qa6/sub/test_wave1_boot.py:46`** (shared with P4), `tests/qa6/sub/test_wave3_1_discovery.py:522`, `tests/qa6/inproc/test_wave5_9_shutdown.py:28-29`, `tests/qa6/manifest/qa6-live-harness.json:60` |
| P11 | 19 | P1 | P2–P10 | `web/static/session.js` (decision card) |
| P12 | 18 | **P11 + P9** | P10 | `web/server.py`, `web/ws.py`, `web/static/terminal.js`, `web/static/session.js` (note), `toolsurface/tools_terminal.py` |
| P13 | integration | all of P2–P12 | — | manifest, `RETIRED_NODE_IDS`, the post-M4 import table, the ledger README, one new integration test |
| P14 | 22 (build half) | **DEFERRED by the owner, not built** | — | — |
| P15 | verification | P13 | — | none (ledger only) |

**The one shared file.** P4 and P10 both edit `tests/qa6/sub/test_wave2_1_cli_status.py`. P4 renames
the C2 clause at `:103` (`logs.database_schema_4` → `logs.database_schema_current`, plus the
`EXPECTED_SCHEMA_VERSION` import). P10 appends the moved C3 scenario function and its imports. The
hunks are disjoint. P13 merges P5 (which contains P4) **before** P10. If git reports a conflict in
that file, P13 resolves it by keeping both hunks, and only in that file. A conflict anywhere else
still stops P13.

**Three more shared test files** (revision 3; disjoint hunks, and P13 merges in the order listed):
- `tests/qa6/sub/test_wave1_boot.py`: P4 edits W1 at `:127` (plus the `EXPECTED_SCHEMA_VERSION`
  import), and P10 edits W4's `W4_STOP_LINE` at `:46`. P5 (containing P4) merges before P10.
- `tests/qa6/live/test_wave8_1_live.py`: P3 edits L1 at `:918-930`, and P7 edits L8 at `:1237`.
  P1's L4 hunk (`:1544-1545`) is on the base of both. P3 merges before P7.
- `tests/daemons/test_controld.py`: P8, then P10 on P8's branch (sequential, not parallel), so this
  one cannot conflict.

**Sequential pairs that share a `src/` file by design** (never parallel): P4 → P5 (`spawn.py`,
`store/reads.py`), P8 → P10 (`controld.py`, `test_controld.py`), P9 + P11 → P12 (`server.py`,
`session.js`).

**Scheduling priority** when builders are scarce: P4 (migration risk first), P8, P10, P9, P12, then
P6, P5, P7, P2, P3, P11.

---

## Phases

### P0 — Baseline and the integration branch

- **Objective:** re-measure the reference reds on the exact base, so every later "no new red" claim
  has something to compare against.
- **Rulings / scenarios:** none. **Inputs:** `4209fc7`.
- **Files:** new `docs/plans/qa6-rulings-blockers/P0-baseline.md`.
- **Dependencies:** none. **Allowed scope:** create `fix/qa6-rulings` in the main checkout, run
  commands, write the ledger. **Out-of-scope drift:** fixing anything.
- **Checks** (main checkout, `cd /Users/noamsalit/Git/Shepherd && …`):
  1. `.venv/bin/pytest -p no:randomly --ignore=tests/qa5`: record the counts and every failing id.
  2. `.venv/bin/pytest -p no:randomly tests/boundaries`
  3. `.venv/bin/mypy --strict src`
  4. Record the qa6 comparison set (three run dirs, above). No qa6 run.
  5. The host-safety reads (Agreement snapshot, constraints), recorded as `QR_HOST_BEFORE`. None
     contacts a tmux server.
- **Exit criteria:** the red sets equal `docs/plans/qa6-bugfix-blockers/P0-baseline.md`'s (plus the
  known s7 flaky test, if it fires). Any other difference stops the build and goes to the router.
- **test_seams:** none (measurement). **Checkpoint:** none (AFK). **Validation:** deterministic.
  **Durability:** session-only.
- **Consumes:** none. **Produces:** `QR_BASELINE_DEFAULT_FAILS`, `QR_BASELINE_BOUNDARY_FAILS`,
  `QR_HOST_BEFORE` (named sets in the ledger).

### P1 — Spec rows, docs, and the oracle-only rulings

- **Objective:**
  - write every owner decision into the spec before any code depends on it
  - land every ruling whose whole deliverable is a document or a qa6 oracle
  - mark README capability 3 "not yet", linking the SD-09 backlog doc
- **Rulings:** 14, 15, 16, 17 (HANDOFF), 22 (README only; the channel is deferred), 23 (spec text), 24, 25, 26, 28, and D-rows for
  1, 5, 6, 8, 9, 12, 13, 18, 19, 20, 21, 27.
- **qa6:** D12, U7, U8, M9, O8, L4, U2/preflight.
- **Files:**
  - `docs/specs/orchestrator-platform.md`:
    - §3 **new rows D68–D79**, appended after D67 in the table's existing style
      (`| D68 | **decision** | reasoning |`, one blank line between rows, as at `:182-186`)
    - the decision count at `:34`: "**67 decisions** (D1–D67, plus D38.1, an amendment)" →
      "**79 decisions** (D1–D79, plus D38.1, an amendment)"
    - §8 table and the paragraph after it (975-1005)
    - §9 write-policy table and §9.5 (the attached line, the RPC path)
    - §11 "Two bindings" status note (unchanged meaning). Add: "SD-09, the session → tool-surface
      channel, is deferred by the owner (2026-09-27); see
      `docs/backlog/2026-09-27-sd09-session-tool-channel.md`. D80 is reserved for it."
    - §12 Page 1 (chat rendering)
    - install text 2370-2374
  - `docs/plans/2026-09-16-m1-foundation-visibility-plan.md`: ADR-7 §4 (lines 1206-1208). Re-word it
    to "frozen before the server **serves**", with a dated amendment line citing D71. Old text struck
    through or quoted, never deleted.
  - `docs/plans/2026-09-17-m4-orchestrator-plan.md`: an ADR-M4-7 amendment line (after line 814),
    citing ruling 11: "a declared `post_milestone` edit of `server.py` is accepted. The digest pin
    stays".
  - `docs/design/ui-decisions.md`:
    - U16 (line 117) → `color: var(--b-text)` for the label, with the AA reason
    - U8 (line 82) → `1 week ago` for 11 days, and why (week and month units)
    - a new U-entry for BC-06 rendering (one step per tool; `turn_ended` and non-stopping
      `rate_limit` **shown in the status area's event line** (`#shepherd-event`, beside
      `#shepherd-status`, which it never overwrites); a final text equal to the last text is not
      repeated)
  - `HANDOFF.md` item 2 (line 177): the decided card stays inline with its outcome label and leaves
    the sidebar.
  - `README.md:52`: capability 3 gets "*(not yet — sessions have no channel to Shepherd's tool
    surface in this build; see [the backlog note](docs/backlog/2026-09-27-sd09-session-tool-channel.md))*".
    The link is relative from the repo root, where `README.md` lives.
  - `docs/plans/qa6-bugfix-blockers/README.md` §"Owner decisions": one line per item, "ruled
    2026-09-27 → `docs/plans/2026-09-27-qa6-rulings-plan.md`". The body is unchanged.
  - qa6 (oracle-only, each with its reason in the ledger):
    - `tests/qa6/sub/test_wave3_3_hooks.py`, D12 (lines 80-205). `verification_required` and
      `cloud_credential_error` → `auth_failed`/`error`; `other` → recorded, `decided_by ==
      "heuristic"`; `unknown` → `(0.0, "mechanical")`; `stop_completed` → heuristic, confidence < 1.0
      (report §4b); `stream.session_state_stopped_per_session` →
      `stream.session_stopped_per_session`, kinds `session_stopped`/`session.classified` (§4b).
    - `tests/qa6/sub/test_wave6_2_flock.py`:
      - U7 line 260: the expected legend text colour is the computed colour of a probe element whose
        `color` is `color-mix(in srgb, <PALETTE hex> 78%, var(--text))`, inside the same
        `.legend-key`. The glyph clause is unchanged (raw hex).
      - U8 line 295: `"11 days": "1 week ago"`.
    - `tests/qa6/inproc/test_wave5_2_turns.py` M9 lines 529-532: HUMAN `fleet_summary` and
      `rename_project` expect `approved_by == "policy"`. HUMAN `create_project` stays
      `claimed_human`.
    - `tests/qa6/sub/test_wave4_1_owned.py` O8 lines 641-645: assert that the `delivered` count
      rose by exactly 2 across the scenario (read before k1 and after both deliveries), and that
      `messages` holds neither id. Named `api.mailbox_delivered_count_rose_by_2`.
    - `tests/qa6/live/test_wave8_1_live.py` L4 lines 1544-1545: also accept `row.ephemeral == 0 and
      row.state == "stopped"`.
    - `tests/qa6/paths.py:53-55` → `f99112b6db8b5adb5014792c84e75cac806ec12ecb73a2dee3a1ef95a7f1c52b`,
      with the comment updated (INC-3 accepted by the owner 2026-09-27).
    - `tests/qa6/test_harness_guards.py:1592,1670,1695`: `U2_OWNER_SHA` and the two expected lines
      (`expected f99112b6…`).
    - `tests/qa6/manifest/qa6-live-harness.json:350`: the "given" text.
- **The D-rows** (bold decision + reasoning, the §0 format; each cites its ruling and the
  `docs/plans/2026-09-27-qa6-owner-rulings.md` line):
  - **D68** (BC-05): CLI↔controld is a dedicated owner-only RPC Unix socket (`rpc`, 0600) that runs
    `invoke()` as HUMAN. Refines §5's topology, §13's socket list and D38's "no byte of `cli/`"
    (which governed M4 only; post-milestone edits are declared). Rejected alternatives: HTTP, and
    multiplexing ingest.
  - **D69** (BC-14): level 3 opens an unprompted turn carrying the wake summary alone. It is queued
    behind a running turn by the 2 s sweep. It counts toward the per-lineage cap under RD-3's reading.
    Refines D31's "wakes the master immediately". The wake set it reads excludes `refused` rows
    (D73).
  - **D70** (BC-15): a master retry is **declared** with `retry_of`, taught in the prompt. The
    lineage `link_retry` records is what the cap reads. The cap is **enforced by admission**
    (`admit(retry=…)`, before any row), not inside `link_retry`, which runs after the row exists.
    This is the ruling's "`link_retry` enforces the cap" read as "the link is what the cap
    counts" (Differences 7). A second retry of one attempt is refused (RD-2). Inferred retry is
    rejected. Closes T10-4.
  - **D71** (BC-21 C7): controld binds its port before it opens the store. The registry is frozen
    before the server **serves**. Amends ADR-7 §4.
  - **D72** (H1-lock): each daemon holds an exclusive `flock` on `<socket>.lock` for its lifetime.
    This closes E16's claim→bind race and the macOS full-backlog ambiguity (REMFIX-1 OWNER item).
  - **D73** (BC-28): a start the runner refuses ends its pre-written row with `stop_reason =
    refused` (bucket `error`, decided `declared`). It is §8's 21st reason and needs migration 005
    (owner-approved 2026-09-27; stash-and-rebuild, ADR-QR-6). C-M3-7's intent is kept: the attempt
    stays visible. **A `refused` row wakes nothing.** It is excluded from D31's wake set, at
    level 2 and level 3. This refines D31's "`unfinished` and `error` outcomes wake the master":
    the master that asked for the spawn already received the refusal as that call's result. Waking
    it again would tell it nothing, and at level 3 a fresh respawn would loop past RD-3's lineage
    reading.
  - **D74** (SD-07): a message to a pane-less session (`runner_handle IS NULL`) is refused at send
    time and **no row is written**. This reverses D45's "attached sessions keep `Stop` as their only
    trigger" for delivery (RD-5).
  - **D75** (SD-08): `ask()` names the asked session by Shepherd's id (`from_fork_of`). The engine id
    travels as `from_fork_of_engine_session_id`.
  - **D76** (SD-05): browser keystrokes reach the pane over the terminal WebSocket. This reverses
    BLOCKER-T19-c. D40 is unchanged: the open is audited, keystrokes are not.
  - **D77** (SD-06): decision-card choices answer through `answer_permission` (C-18). The trust dialog
    stays inert, labelled, with RD6's reason.
  - **D78** (L5): `session.spawned.trusted` is `false` until the folder is known to be trusted, and
    `trust_source` names the unknown. `trust.py`'s `None` is unchanged.
  - **D79** (H3): a master turn that fails is counted `master_failed` and written to the audit log with
    its class name only. `AnomalyKind` gains a post-M4 member.
  - **D80** stays reserved for SD-09 (deferred; the backlog doc says the same). It is **not**
    written.
- **Spec prose, per ruling:**
  - §8 (SD-01): add rows for `verification_required`/`cloud_credential_error` → `auth_failed`;
    SessionEnd `other` defers to the heuristic lane; the engine's `unknown` at confidence 0.0. Add the
    `refused` row (D73). Rewrite the "which no row above maps" sentences to say where each value goes.
    Add "amended 2026-09-27 (qa6 SD-01, D73)".
  - Install text (BC-20, SD-10): "The first pre-install image is kept at `<file>.shepherd-backup` and
    never overwritten. `uninstall-hooks` removes exactly our entries and does not restore bytes. An
    event value that is not an array of matchers is left untouched and reported as a warning. The
    other events are installed."
- **Dependencies:** P0. **Allowed scope:** documents, the listed qa6 hunks, paths/guards/manifest-json.
  **Out-of-scope drift:** any `src/` byte; any other qa6 clause; editing an existing D-row's text.
- **Checks:** harness guards; the qa6 import check on the six edited qa6 modules; a
  `grep -n '^| D6[89]\|^| D7[0-9]' docs/specs/orchestrator-platform.md` shows D68–D79 exactly once,
  in order; `grep -n '^| D80' docs/specs/orchestrator-platform.md` is empty; `grep -n '79 decisions'
  docs/specs/orchestrator-platform.md` shows line 34; `git diff --stat -- src` is empty.
- **Exit criteria:** the three checks green. The ledger holds one reason per oracle change, and the
  table of D-rows with each one's ruling.
- **test_seams:** the harness-guard seam (`test_harness_guards.py`). The qa6 seams are proved in P15.
- **Checkpoint:** none (AFK). **Validation:** deterministic (guards, collection) plus manual review
  of the prose. **Durability:** stable.
- **Consumes:** P0's baseline. **Produces:** the D-row numbers `D68`…`D79`, verbatim as above (later
  phases cite them). `D80` stays reserved and unwritten.

### P2 — BC-20: the first pre-install image survives

- **Objective:** `.shepherd-backup` is written once, from the first pre-image, and never overwritten.
  Uninstall keeps removing only our entries.
- **Rulings:** 7, 23 (oracle). **qa6:** H4, H5.
- **Files:**
  - `src/shepherd/engines/claude_code/hooks_config.py`:
    - `_commit` (299-301) and uninstall (369-371) write the backup with `open(path, "xb")`;
      `FileExistsError` → keep the existing one
    - the `InstallResult.backup_path` docstring
  - new `tests/engines/test_hooks_backup_first_image.py`
  - `tests/qa6/unit/test_wave2_hooks_config.py`:
    - H4 clause 2 → `files.clause2_uninstall_removes_only_ours`: `load(target) == json(H4_ORIGINAL)`
      and the backup still equals `H4_ORIGINAL`
    - H5 `stop_string` case → installed with a warning naming `Stop`, `Stop` still `"x"`, a backup
      holding the original bytes. The other H5 cases are unchanged.
- **Dependencies:** P1. **Out-of-scope drift:** byte-for-byte restore (rejected by the ruling); the
  `_serialise` format; `_restore`.
- **Tests (RED first):**
  - `test_a_second_install_keeps_the_first_pre_install_image`
  - `test_uninstall_never_overwrites_the_backup`
  - `test_a_backup_that_exists_before_the_first_install_is_kept` (the user's own file is never
    clobbered)
  - `test_uninstall_removes_only_our_entries_and_restores_no_bytes`
  - RED today: the second install's output replaces the backup.
- **Verify, not change:** `tests/engines/test_hooks_config_unreadable.py` (P9's mode-000 refusal) is
  green unchanged.
- **Checks:** the new file, `tests/engines/test_hooks_install.py`,
  `tests/engines/test_hooks_config_unreadable.py`, `tests/toolsurface` (the `tools_hooks` tests),
  boundaries, mypy, the qa6 import check on the H module.
- **Exit criteria:** GREEN, with the RED recorded; H4/H5 oracle reasons recorded.
- **test_seams:** unit at `install_hooks`/`uninstall_hooks` over `tmp_path` (the existing engine seam).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** none. **Produces:** `BACKUP_SUFFIX` (unchanged) and the backup-once rule.

### P3 — BC-06: master chat renders one step per tool, events to the status line

- **Objective:** a tool call and its result are one expandable step (the call is the title, the result
  is inside). `turn_ended` and non-stopping `rate_limit` go to `#shepherd-status`. The final result
  text is not repeated when it equals the last text.
- **Rulings:** 2, 3, 4, 17 (oracle). **qa6:** U26, U27, U28, plus L1's re-valued clause. U25, U46
  and L2 are untouched by construction (revision 4: `#shepherd-status` keeps its writers).
- **Files:**
  - `src/shepherd/web/static/chat.js` (`onShepherdEvent` 393-410, `shepherdStep` 215-228,
    `stepBody` 246-251)
  - `src/shepherd/web/static/index.html` (revision 4, B1): one static element directly after
    `#shepherd-status` (`:167`), inside the same status area:
    `<p class="status event-line" id="shepherd-event" aria-live="polite"></p>`. This is a **re-based**
    path (`rebase.regenerated_paths` holds `web/static/index.html`), so P13 gives it a `files`
    digest only. The id does not start with `page-` (`tests/web/test_settings_live.py`'s
    page-root rule)
  - `tests/web/fixtures/shell_harness.html` (`:173`): the same element after its `#shepherd-status`.
    `chat.js`'s `slot()` throws on a missing id (`chat.js:84-90`), and these two files are the only
    pages hosting the chat markup (grepped)
  - `tests/web/test_chat_page.py` (`REQUIRED_SHEPHERD_ASSIGNMENTS` 505-543; add each new assignment
    with its requirement)
  - new `tests/web/test_chat_steps_live.py` (real browser, `shell_harness.html`)
  - `tests/qa6/inproc/test_wave7_1_master_ui.py`:
    - U26 (292-340): expect `[prose…, step:fleet_summary]` with one step. The wait at `:305` becomes
      the event line (revision 4, B1): `ui.turn_ended_reaches_the_status_area` settles on
      `text_of(page.locator("#shepherd-event"))` naming the turn's outcome, and
      `ui.no_turn_ended_line_in_the_thread` checks that no `.prose` reads `turn_ended`.
      `#shepherd-status` is not read by U26.
    - U27/U28 (`:374-376`): exactly one `[data-approval-id]` remains, inside `#shepherd-thread`,
      carrying the outcome word. Clause renamed `ui.one_inline_card_with_the_outcome`.
  - `tests/qa6/live/test_wave8_1_live.py` L1 (`:918-930`; revision 3, F3):
    - take `before = len(shepherd_adds())` **immediately before each** `ui_turn` call: before the
      first one (`:896`), and **again** before the retry at `:901` (revision 4, A1), so the count
      covers only the final turn
    - `this_turn = shepherd_adds()[before:]`, replacing the last-`len(turn.frames)` slice, which
      rested on the one-node-per-frame premise
    - wait with `observe(lambda: len(shepherd_adds()) - before >= 2, 10.0)`
    - `ui.assistant_grows_in_two_updates` (name kept) becomes `len(this_turn) >= 2` ("≥ 2
      Shepherd-side DOM additions: the merged tool step and at least one prose line"), with the old
      comment at `:924` rewritten to say why
    - the ledger records old → new
    - **shared file with P7** (L8 `:1237`)
  - **Re-checked for other per-frame node counts:** `grep` over `tests/qa6` and `tests/web` for
    `len(turn.frames)`, `shepherd_adds`, `details.step` counts and `#shepherd-thread` child counts
    finds only U26 (`test_wave7_1_master_ui.py:305-322`, already P3's) and L1. Nothing else counts
    nodes per frame.
- **Design:**
  - A step is keyed by `detail.tool_use_id`. A `tool_result` whose id has a step fills that step's
    body. One with no step renders its own step, titled with its tool name, so nothing is dropped.
  - **The event line** (revision 4, B1, router-decided; it **replaces** revision 3's `setStatus`
    precedence mechanism, which is dropped). Ruling 3's events go to a **new sibling element**,
    `#shepherd-event`, in the same status area. They go neither in the thread nor over
    `#shepherd-status`:
    - `turn_ended` → `fill("shepherd-event", <outcome text>)` from `detail.outcome` (for example
      `turn ended · finished`). A turn that ended `error` still says so in the thread through
      `master.error` (unchanged).
    - a non-stopping `rate_limit` → `fill("shepherd-event", …)`. A `rate_limit` with
      `detail.rate_limit.status === "rejected"` (RD-4) gets a thread line **and** the event line.
    - `aria-live="polite"`, so the line is announced without stealing focus. The text goes through
      `fill` (`textContent`, §13; no new sink).
  - **`#shepherd-status` keeps exactly its current writers, untouched**: `chat.js:141`, `:146`,
    `:160`, `:165`, `:343` and `:385`. No event ever writes it. So U25
    (`test_wave7_1_master_ui.py:194-195`), U27/U28 (`:372-373`), U46 (`:670-671`), L2
    (`test_wave8_1_live.py:1667`), the live `ui_send` loop (`:843-858`) and
    `tests/web/test_settings_live.py:312` (`== "turn-01JCHAT"`) stay green **by construction**,
    oracles unchanged.
  - `lastText` per turn id. A `turn_ended` text equal to it is not rendered. A different one is
    rendered once, as prose.
  - No new sink. Everything goes through `el`/`fill` (`textContent`, §13).
- **Dependencies:** P1. **Out-of-scope drift:** `master/projection.py`; the approval card
  (BC-26 dedupe stays); the composer; `app.css` beyond `.step` states (if any CSS is needed, declare
  `app.css` as a re-based path in the ledger).
- **Tests (RED first, browser):**
  - `test_a_tool_call_and_its_result_are_one_step`
  - `test_a_result_with_no_call_still_renders_as_its_own_step`
  - `test_turn_ended_goes_to_the_status_line_not_the_thread`
  - `test_a_rate_limit_that_does_not_stop_the_turn_goes_to_the_status_line`
  - `test_a_rejected_rate_limit_is_also_shown_in_the_thread`
  - `test_a_final_result_text_equal_to_the_last_text_is_not_rendered_twice`
  - `test_a_final_result_text_that_differs_is_rendered_once`
  - `test_turn_ended_is_shown_in_the_event_line_and_the_status_keeps_the_turn_id` (send → the
    `#shepherd-status` turn id; then `turn_ended` → `#shepherd-event` names the outcome, and
    `#shepherd-status` is still the id)
  - `test_an_event_never_touches_the_status_after_an_approval_or_a_refusal` (the `approved`,
    `already decided` and send-refusal cases, each followed by a `turn_ended` and a `rate_limit`;
    `#shepherd-status` unchanged, `#shepherd-event` updated)
  - `test_the_event_line_is_polite_live_region_beside_the_status` (static: in both `index.html` and
    `shell_harness.html`, `#shepherd-event` exists, has `aria-live="polite"`, and immediately
    follows `#shepherd-status`)
  - RED today: two steps, a `turn_ended` prose line, the text twice, and no `#shepherd-event`.
- **Changed pin (declared):** `REQUIRED_SHEPHERD_ASSIGNMENTS` gains the exact new assignment strings
  (including any the `#shepherd-event` writer adds). The ledger lists them.
- **Manifest need (P13):** `web/static/chat.js` **and `web/static/index.html`** are **re-based** paths
  (`rebase.regenerated_paths`), so each gets a `files` digest only, recorded in the P13 README
  ledger. `tests/web/fixtures/shell_harness.html` is not a consumer path. **Known-red:** Gate A's
  two tests.
- **Checks:** `tests/web/test_chat_page.py`, the new file, `tests/web/test_chat_qa6_live.py`,
  `tests/web/test_settings_live.py` (`:312` unchanged), every `tests/web` test that loads
  `index.html` or `shell_harness.html`,
  `tests/web/test_frontend_escaping.py`, `tests/web/test_frontend_unreachable_daemon.py`,
  `js_syntax_check` on `chat.js`, boundaries (known-red listed), mypy, the qa6 import check on waves
  7 and 8.
- **Exit criteria:** GREEN; the pin updated; the U26/U27/U28 and L1 reasons recorded; `git diff`
  on `chat.js` shows none of the six `fill("shepherd-status", …)` lines changed; `#shepherd-event`
  is present in both pages.
- **test_seams:** the real-browser seam over the harness page (the existing seam). The static
  assignment pin.
- **Checkpoint:** none. **Validation:** deterministic (browser, event-driven, no sleeps).
  **Durability:** stable.
- **Consumes:** the master event payload keys `tool_use_id`, `outcome`, `rate_limit`
  (`master/projection.py:199-250`, existing). **Produces:** none used later.

### P4 — BC-28 and L5: a refused start ends its row `refused`; the spawn frame says `trusted: false`

- **Objective:**
  - a `RunnerRefusal` from `ensure_server()` or `runner.start()` leaves exactly one row: state
    `stopped`, `stop_reason = refused`, `decided_by = declared`, outcome `error`, `ended_at` set,
    `runner_handle` NULL
  - that row is **not** a wake candidate (D73)
  - `session.spawned.trusted` is `trust.trusted is True`
- **Rulings:** 9, 27. **qa6:** O4, L5, plus the W1, C2 and C10 oracles that spell the schema version.
- **Files:**
  - new `src/shepherd/store/migrations/005_refused_stop_reason.sql`, **ADR-QR-6 option 2,
    verbatim**, in this order:
    1. a header comment:
       - why the migration exists (D73)
       - why the stash (the rehearsal's `FOREIGN KEY constraint failed` for 002's pattern alone)
       - why not `writable_schema`
       - that `mailbox_message` is the only outside reference (`003:37`)
    2. `PRAGMA defer_foreign_keys=ON`
    3. `CREATE TEMP TABLE mailbox_stash AS SELECT id, owner_id, session_id, idempotency_key, body,
       origin, queued_at, delivered_at, delivery_attempts, last_refusal FROM mailbox_message`
    4. `DELETE FROM mailbox_message`
    5. `CREATE TABLE session_new (…)`: 002's 52-column declaration with `'refused'` appended to the
       `stop_reason` list and nothing else changed
    6. `INSERT INTO session_new (<52 named columns>) SELECT <same> FROM session`
    7. `DROP TABLE session`, then `ALTER TABLE session_new RENAME TO session`
    8. recreate `ix_session_fleet` and `ux_session_engine_id` exactly as `002` declares them
    9. `INSERT INTO mailbox_message (<10 named columns>) SELECT <same> FROM mailbox_stash`, then
       `DROP TABLE mailbox_stash`

    No string literal holds a `;` or `--`, and there is no trigger (the `_statements` splitter,
    `migrate.py:76-83`).
  - `src/shepherd/store/migrate.py:27` → `EXPECTED_SCHEMA_VERSION = 5`
  - `src/shepherd/core/stops.py`: `StopReason.REFUSED = "refused"`, appended with a docstring (the
    enum order is the migration's order); the class docstring "twenty" → "twenty-one". **The file
    is at its cap:** 300 lines, and `tests/test_core_stops.py:230` asserts `<= 300`. So the change
    is **net-zero** by re-wrapping code, never by removing prose (revision 3, F5)
  - `src/shepherd/signals/stop_rules.py`: `BUCKET_OF[REFUSED] = Bucket.ERROR`; a `DEFAULT_ACTIONS`
    row (a `respawn` "Start it again", then `inspect` "Read why the start was refused"), each ≤ 80
    chars
  - `src/shepherd/store/reads.py` (D73's wake exclusion; **≤ +8 lines**, so the file is ≤ 585 of
    600 and P5 keeps its share):
    - `WAKE_EXCLUDED_REASONS = (StopReason.REFUSED.value,)` beside `WAKE_OUTCOMES` (`:453`), with a
      comment citing D73
    - `_WAKE_SQL` (`:460-464`) gains `" AND (stop_reason IS NULL OR stop_reason NOT IN (?))"`
      (placeholders built from the tuple, as `WAKE_OUTCOMES` does)
    - `wake_candidates`' parameters gain the tuple
    - the docstring names D73
  - new `src/shepherd/orchestration/declared_verdicts.py`: `refused_verdict(reason: str) -> Verdict`
    and `REFUSED_CONFIDENCE = 1.0`
  - `src/shepherd/orchestration/spawn.py`:
    - 255-256: `store.apply_fold_delta(session_id, FoldDelta(state=SessionState.STOPPED,
      last_event_at=stamp))`, then `store.apply_stop_verdict(session_id,
      refused_verdict(refusal.reason), stamp, None)` (the real signatures, `store/db.py:354,472-474`;
      `FoldDelta` from `core/fold_types.py:37`). One `stamp = now()` serves both, using the
      **injected** `now: Callable[[], str]` parameter (`spawn.py:190`), never `utc_now()`, so a test
      clock controls it (revision 3, F9). Then
      `return SpawnRefused(refusal.reason, None)`
    - 275: `"trusted": trust.trusted is True`
    - the docstring's C-M3-7 paragraph
  - **Schema pins** (re-measured at `4209fc7`; every one below; the ledger records each with its
    reason). The rule: where a test means "the current version", it reads `EXPECTED_SCHEMA_VERSION`.
    Exactly one literal head pin is kept, in `test_migration_003.py::test_migrate_expected_version_matches_the_highest_file`.
    - `tests/store/test_migration_002.py`:
      - `:136-137`, `:260`, `:299`: `== 4` → `== EXPECTED_SCHEMA_VERSION`
      - `test_future_schema_refuses_to_start` (`:271-292`): the sentinel `VALUES (5, …)` at `:285`
        → `EXPECTED_SCHEMA_VERSION + 1`, which is a primary-key collision otherwise (the
        `…_at_four` precedent). `:291` `"5" … "4"` → the two versions as `str()`. `:292` → `+ 1`.
        Its docstring "moved from 4 to 5" gains "and from 5 to `EXPECTED + 1` with 005". The name
        carries no version, so the id is kept (frozen, `:1100`)
    - `tests/store/test_migration_003.py`:
      - `:185` `versions == [1, 2, 3, 4]` → `[1, 2, 3, 4, 5]`, and `:186` → `EXPECTED_SCHEMA_VERSION
        == 5`. This is **the one literal head pin**. Its docstring gains "and on 005"
      - `:203-204`, `:409`, `:458`: `== 4` → `== EXPECTED_SCHEMA_VERSION`. `:228`'s
        `schema_migration` count `== 4` → `== EXPECTED_SCHEMA_VERSION`, with the comment "four
        applied migrations" → "every applied migration"
      - `test_003_applies_over_002_and_changes_nothing_that_was_there` (`:189-228`) now also runs
        005. Its column-spec and index-spec assertions (`PRAGMA table_info` / `index_list`, no
        CHECK text) must still hold, and 005 is required to preserve exactly those. That is kept
        as a bonus guard, and its docstring gains a sentence saying so
      - `test_future_schema_refuses_to_start_at_five` (`:420-444`) → **renamed**
        `test_future_schema_refuses_to_start_at_six`. The sentinel `:437` `VALUES (5, …)` →
        `(6, '006_from_the_future', …)`. `:443` `"5" … "4"` → `"6" … "5"`. `:444` → `== 6`. The
        docstring gains the 005 sentence in the `…_at_four` paragraph's shape. **Not frozen**
        (absent from `collected_node_ids.txt`; `…_at_four` at `:1113` is, and is already retired at
        `test_collected_node_ids.py:84`), so there is no `RETIRED_NODE_IDS` entry, only the ledger.
        That existing `…_at_four` entry's **reason names its successor** as
        `test_future_schema_refuses_to_start_at_five, which inserts version 5` (`:91`). After the
        rename, P13 updates it to `…_at_six, which inserts version 6`. P4's ledger lists this for P13,
        because `test_collected_node_ids.py` stays P13-only
    - `tests/store/test_migration_004.py`: `:109-110`, `:150`, `:165`, `:188`, `:212-213`, `:240`:
      `== 4` → `== EXPECTED_SCHEMA_VERSION`. `:111` `EXPECTED_SCHEMA_VERSION == 4` → `>= 4`
      (002's `:123` shape: what 004 owns is its file, not the head). `:215`'s count `== 4` →
      `== EXPECTED_SCHEMA_VERSION`
    - `tests/store/test_migrations.py`: `:70` `== EXPECTED_SCHEMA_VERSION == 4` → `==
      EXPECTED_SCHEMA_VERSION`. `:77`, `:100-101` → `EXPECTED_SCHEMA_VERSION`. `:103`'s count →
      `EXPECTED_SCHEMA_VERSION`. `:142-143` already use 99 and the constant, so they are unchanged
    - `tests/cli/test_commands.py`: `:443` `"schema version 4"` → `f"schema version
      {EXPECTED_SCHEMA_VERSION}"`, `:444` `"expects 4"` → `f"expects {EXPECTED_SCHEMA_VERSION}"`,
      `:702` → `f"expects schema version {EXPECTED_SCHEMA_VERSION}"` (import from
      `shepherd.store.migrate`)
    - frozen ids among these: all kept by name except the rename above
  - other tests:
    - `tests/test_core_stops.py:23-26`: `test_stop_reason_has_twenty_members` is **frozen**
      (`collected_node_ids.txt:1231`), so it is **retired** → successor
      `test_stop_reason_has_twenty_one_members` (the same set plus `"refused"`; the docstring "16
      mechanical + 4 completeness + 1 declared (D73), spelled as migrations 002 and 005's CHECK
      lists them")
    - `tests/signals/test_stop_rules.py:33` (`== 21`; id kept, no count in its name)
    - `tests/golden/test_next_actions_coverage.py`: a `refused` row with gap id **`G-QR-1`** ("a
      spawn-side verdict; no stop capture can produce it"), recorded in this plan. The docstring
      "Twenty reasons, twenty rows" (`:91`) → "Every reason, one row each"
    - `tests/golden/expected/verdicts.json` only if the coverage harness requires it
    - `tests/orchestration/test_spawn.py`:
      - `test_an_ensure_server_that_refuses_is_a_refusal_not_a_traceback` gains the refused-verdict
        assertions (id kept)
      - `test_an_unknown_trust_verdict_stays_unknown` (frozen, `:692`) is **retired** → successor
        `test_an_unknown_trust_verdict_is_published_as_not_trusted`
    - `tests/store/test_wake_reads.py`: one new test (no fixture change; the existing FLEET and
      its coverage assertion are untouched)
    - new `tests/store/test_migration_005.py`
    - new `tests/orchestration/test_spawn_refused_row.py`
  - qa6:
    - `tests/qa6/sub/test_wave4_1_owned.py` O4 (~446): `db.refused_row_is_ended` (one new row, state
      stopped, stop_reason refused, handle NULL) and `api.session_count_rises_by_1_with_no_live_row`.
      The old clause names are retired in the ledger.
    - `tests/qa6/sub/test_wave1_boot.py:127` → `EXPECTED_SCHEMA_VERSION` (imported from
      `shepherd.store.migrate`)
    - `tests/qa6/sub/test_wave2_1_cli_status.py:103` → `logs.database_schema_current`
      (`f"schema version {EXPECTED_SCHEMA_VERSION}"`). **Shared file with P10** (parallelism table)
    - `tests/qa6/sub/test_wave2_2_refused_starts.py:180` C10 fixture: `VALUES (5, …)` →
      `EXPECTED_SCHEMA_VERSION + 1`
- **Dependencies:** P1 (D73, D78). **Allowed scope:** the above. **Out-of-scope drift:**
  - the admission refusals (no row, unchanged)
  - publishing a new stream event for the refusal (record it as a sibling)
  - the `outcome` CHECK
  - `trust.py`
  - rebuilding `mailbox_message` (ADR-QR-6 option 3)
  - `writable_schema`
  - any other `_WAKE_SQL` clause
  - the waker (P6)
- **Line budgets:** `spawn.py` ≤ **288** after P4 (P5 needs the rest); `store/reads.py` ≤ **585**;
  `core/stops.py` ≤ **300** (net-zero).
- **Tests (RED first; `test_migration_005.py` is written and run before any other P4 code):**
  - `test_migration_005.py`. Seed: build a **v4** database from a migrations dir holding 001–004
    only (the `through_002` shape), then insert a workspace, a parent session, a child session
    whose `parent_session_id` and `retry_of` name it, **at least two `mailbox_message` rows** (one
    per session, one of them delivered), and a `project_repo` row. Then run `migrate()` with the
    real dir.
    - `test_every_session_row_and_column_survives_005` (cell by cell, `FULL_SESSION` shape)
    - `test_every_mailbox_row_survives_005_and_still_references_its_session` (every column of every
      row equal before and after; `foreign_key_check` empty)
    - `test_both_tables_keep_every_index_after_005` (`index_spec` of `session` and
      `mailbox_message` equal before and after)
    - `test_refused_is_accepted_and_a_bogus_reason_is_still_rejected`
    - `test_005_leaves_foreign_keys_enforced` (an orphan mailbox insert raises `IntegrityError`)
    - `test_005_leaves_no_stash_table_behind` (`sqlite_temp_master` and `sqlite_master` hold no
      `mailbox_stash`)
    - `test_a_v5_database_refuses_a_v4_binary_by_rule_2` (via the migrate reader)
    - **negative control** `test_the_002_rebuild_alone_fails_on_a_database_with_mailbox_rows`:
      a tmp migrations dir holding 001–004 plus a test-written 005 that is ADR-QR-6 option 1
      (built from 005's own text with the stash statements removed). Against the same seeded
      DB, `migrate()` raises `MigrationRefused` naming `FOREIGN KEY`. This keeps the reason for
      the stash visible. It is inert SQL in `tmp_path`, not a planted mutation of executable code
    - `test_005_holds_no_trigger_and_no_semicolon_inside_a_string_literal` (the 004 test's shape)
  - `test_spawn_refused_row.py`:
    - `test_a_refused_start_ends_the_row_refused_and_not_live`
    - `test_an_ensure_server_refusal_ends_the_row_refused`
    - `test_a_refused_row_buckets_error_with_a_respawn_action`
    - `test_a_refused_start_publishes_no_spawn_event`
  - `test_wake_reads.py`: `test_a_refused_start_is_not_a_wake_candidate`. A master-origin row ended
    `refused`/`error`, beside a positive control, a master-origin row ended `killed`/`unfinished`
    with the same `ended_at`. The set holds the control and not the refused row, with `since` given
    and with `None`.
  - `test_spawn.py` successors:
    - `test_an_unknown_trust_verdict_is_published_as_not_trusted` (`trusted is False`,
      `trust_source` names the unknown)
    - `test_a_known_trusted_directory_is_published_as_trusted` (positive control)
  - `test_core_stops.py`: `test_stop_reason_has_twenty_one_members`
  - RED today:
    - the CHECK rejects `refused`
    - the row stays live with `stop_reason` NULL
    - with the stash statements absent, the migration fails (the negative control is GREEN from
      the start, and that is its point)
    - a refused-shaped row is a wake candidate
- **Checks:** `tests/store` (all), `tests/orchestration/test_spawn.py`, the new files,
  `tests/signals`, `tests/golden`, `tests/test_core_stops.py`, `tests/orchestration/test_wake.py`,
  `tests/qa/test_s2_spawn_stop_wake.py` (the wake-set population), `tests/toolsurface/test_tools_master.py`
  (`peek`), `tests/daemons/test_controld_refusals_qa6.py` (the newer schema is computed as
  `EXPECTED + 1` there already), `tests/cli` (the doctor database line), boundaries, mypy, the qa6
  import check on waves 1, 2 and 4.
- **Exit criteria:**
  - migration tests green on a DB populated with mailbox rows, with the RED recorded
  - the negative control green
  - `spawn.py` ≤ 288, `reads.py` ≤ 585 and `core/stops.py` ≤ 300
  - the pins moved 20 → 21 and 4 → symbolic or 5, each with its reason
  - both retired ids and their successors in the ledger; the not-frozen rename in the ledger
- **test_seams:** the store seam (`migrate()` on a real sqlite file in `tmp_path`;
  `Store.wake_candidates` over a real `Store`); the orchestration seam (`spawn_owned_session` with
  the scripted runner, the existing `test_spawn` helpers).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable (irreversible schema).
- **Consumes:** none. **Produces:**
  - `StopReason.REFUSED` (value `"refused"`)
  - `EXPECTED_SCHEMA_VERSION = 5`
  - `refused_verdict(reason: str) -> Verdict` (`shepherd.orchestration.declared_verdicts`)
  - migration file `005_refused_stop_reason.sql`
  - `WAKE_EXCLUDED_REASONS` (`shepherd.store.reads`), and the rule "a `refused` row is not in
    `Store.wake_candidates(since: str | None) -> tuple[Session, ...]`"
  - `session.spawned` payload `trusted: bool`

### P5 — BC-15: a master retry is declared with `retry_of`

- **Objective:** `spawn_session` takes `retry_of`, admission caps the declared lineage, the new row is
  linked by `Store.link_retry`, and the master prompt teaches it.
- **Ruling:** 6. **qa6:** M14.
- **Files:**
  - `src/shepherd/orchestration/spawn.py`: keyword-only **required** `retry_of: str | None`, with no
    default, following the `engine_config_home` precedent (`test_spawn.py`'s
    `test_the_engine_config_home_is_required_at_the_call_site` shape). The flow:
    1. `retry_of` given and `store.get_session(retry_of) is None` → `SpawnRefused("no session …", None)`
       before any row
    2. RD-2: `store.retried_by(retry_of)` is not None → `SpawnRefused(f"{retry_of!r} was already
       retried as {existing!r}; retry that one instead", None)`
    3. `admit(..., retry=Retry(of=retry_of, initiated_by=origin))`
    4. after `create_owned_session`: `store.link_retry(session_id, retry_of)`
  - `src/shepherd/toolsurface/tools_m3.py`: schema property `"retry_of": {"type": "string",
    "description": "the id of the stopped session this spawn retries (D31 caps the lineage)"}` and
    the `spawn()` pass-through. **Stays ≤ 450** by re-wrapping code (never prose). If that cannot free
    2 lines, move `spawn()` into `toolsurface/spawn_origin.py` and check
    `tests/orchestration/test_degradation.py`'s population first.
  - `src/shepherd/master/prompt.py`: one sentence in an **existing** section body: "to try a stopped
    session again, start it again with `retry_of` set to the session you are retrying; a lineage gets
    two attempts". No new heading. It must not contain the string `spawn_session`
    (`tests/master/test_prompt.py:206-237`).
  - `src/shepherd/store/reads.py` and `src/shepherd/store/db.py`: `retried_by(connection, session_id)
    -> str | None` (`SELECT id FROM session WHERE retry_of = ? ORDER BY started_at, id LIMIT 1`)
    and `Store.retried_by(session_id: str) -> str | None`. **Budget:** `reads.py` stays ≤ 600
    (it is ≤ 585 after P4, so ≤ 15 lines here). If it cannot, the read goes into `db.py` (521)
    through a new small `store/lineage.py` holding only `retried_by`, never by trimming prose.
  - **Every `spawn_owned_session(` caller** passes `retry_of` explicitly (the kwarg is required),
    re-measured:
    - `src/shepherd/toolsurface/tools_m3.py:189` (the tool's pass-through)
    - `tests/orchestration/test_spawn.py:229` (the `spawn()` helper, `retry_of=None`)
    - `tests/orchestration/test_degradation.py:445` (the `("spawn", "spawn_owned_session")` lambda,
      `retry_of=None`)
    - `tests/e2e/test_live_owned_session.py:210` (live lane, `retry_of=None`; not run here,
      collected by the import check below)
  - tests: new `tests/orchestration/test_spawn_retry_of.py`, new
    `tests/toolsurface/test_spawn_session_retry_of.py`, `tests/master/test_prompt.py` (a new test),
    `tests/store/test_retry_link.py` (a new `retried_by` test)
  - qa6: `tests/qa6/inproc/test_wave5_3_wake.py` M14 (`:243-275`), rewritten to the declared chain
    **and made robust to the level-3 waker** (finding B5b). M14 keeps level 3, because the
    test-plan's M14 "When" says so.
    1. `drain(w, "before-M14")` at level 2, so the wake set holds nothing older. Then
       `set_level(w, 3)` and `cap_before = anomaly(w, "wake_retry_cap_reached")`.
    2. Turn A (`master_spawn`) spawns X.
    3. **The wake is scripted, not raced.** With `BOOK.pending() == 0` asserted, push
       `Turn(says="QA6 M14 wake")`, stamp `before = last_turn_at(w)`, then `kill_and_wait(w, x)`.
       Then `await_env(lambda: BOOK.pending() == 0 and slot_free() and (last_turn_at(w) or "") >
       (before or "") or None, M12_BOUND_S, "X's level-3 wake turn opened and ended")`.
       - A blown bound is BLOCKED, never a FAIL. M12 owns that clause, and the `finally` runs
         `BOOK.clear()` so no scripted turn leaks.
       - The observed wake is recorded, not checked: `rec.record("stream.x_stop_woke_the_master",
         …)`.
       - Once it has passed, X is drained (`ended_at < master_last_turn_at`), so no second wake for
         X can take a later script.
    4. Turn B (`run_turn`) holds three calls:
       - `spawn_session(…, retry_of=X)` → r1 spawned
       - `spawn_session(…, retry_of=r1)` → `{spawned: false, cap: "retry_cap_reached"}`
       - `spawn_session(…, retry_of=X)` → refused, reason names r1 ("already retried"), no cap
    5. Clauses:
       - `api.retry_of_the_retry_refused_at_the_cap`
       - `api.anomaly_retry_cap_plus_one` (**read before cleanup**)
       - `api.second_retry_of_x_refused_naming_r1`
       - `db.r1_retry_of_is_x`
       - `logs.spawns_audited`: four master `spawn_session` rows (X plus three)
    6. `finally`: `set_level(w, 2)` **before** the cleanup kills, so killing r1 (depth 2) opens no
       wake and bumps nothing (RD-3 acts at level 3 only), then `BOOK.clear()`.

    Old → new clause names in the ledger:
    - `api.third_retry_refused` → `api.retry_of_the_retry_refused_at_the_cap`
    - `db.retries_link_to_x` → `db.r1_retry_of_is_x`
    - `api.second_retry_of_x_refused_naming_r1` is new

    The ledger records the reason: the declared chain, and the cap counts attempts including the
    original (`t10.md` §T10-2). The `rec.note` about C-3 is replaced by one citing D70.
- **Dependencies:** **P4** (branch `fix/qa6r-P4`; `spawn.py` ≤ 288, `reads.py` ≤ 585). The M14
  rewrite also **consumes P6's behaviour** (a level-3 wake turn), but only at P15, which runs the
  integrated tree. It needs no P6 code to collect or to be correct: without P6 the wait in step 3
  ends BLOCKED, with P6 it passes.
- **Out-of-scope drift:** `admission.py` (300/300, unchanged); a master-only count (T10-3, deferred);
  inferring retries.
- **Tests (RED first):**
  - `test_a_declared_retry_is_linked_to_its_predecessor`
  - `test_the_attempt_that_exceeds_two_is_refused_and_counted_once`
  - `test_a_retry_of_an_unknown_session_is_refused_before_any_row`
  - `test_a_second_retry_of_the_same_attempt_is_refused_naming_the_first`
  - `test_a_human_retry_is_linked_and_not_capped`
  - `test_spawn_session_carries_retry_of_through_invoke` (MASTER audience)
  - `test_the_prompt_teaches_retry_of_without_naming_a_tool`
  - RED today: the schema refuses `retry_of` (an unknown property), and `retry_of` stays NULL.
- **Checks:** the new files, `tests/orchestration/test_spawn.py`,
  `tests/orchestration/test_admission.py`, `tests/orchestration/test_degradation.py`,
  `tests/store/test_retry_link.py`, `tests/store/test_wake_reads.py`, `tests/master`,
  `tests/toolsurface/test_tools_m3.py` (the cap), `tests/boundaries/test_session_audience.py`
  (unchanged: `spawn_session`'s audiences do not move), boundaries, mypy, the qa6 import check on
  wave 5, and a collect-only of the live file:
  `… pytest -p no:randomly --collect-only -m live tests/e2e/test_live_owned_session.py` (it
  imports, and nothing starts).
- **Exit criteria:** GREEN; `spawn.py` ≤ 300; `tools_m3.py` ≤ 450; `reads.py` ≤ 600; prompt pins
  green; every `spawn_owned_session(` caller listed above updated (`grep -rn "spawn_owned_session("
  src tests` shows no call without `retry_of=`).
- **test_seams:** the orchestration seam (`spawn_owned_session`); the L4 seam (`invoke("spawn_session",
  …, MASTER ctx)` over a real `Store`).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** `StopReason.REFUSED` (unused here) and `spawn.py` as P4 left it.
- **Produces:**
  - `spawn_owned_session(*, …, retry_of: str | None)` (keyword-only, required)
  - `spawn_session` input property `retry_of`
  - `Store.retried_by(session_id: str) -> str | None`

### P6 — BC-14 and H3: level 3 wakes the master; a failed turn is counted and audited

- **Objective:**
  - at level 3, a master-spawned session stopping `unfinished`/`error` opens an unprompted turn with
    the wake summary, queued behind a running turn and gated by RD-3
  - every failed master turn bumps `master_failed` once and writes one audit record
- **Rulings:** 5, 12. **qa6:** M12 (no oracle change).
- **Files:**
  - `src/shepherd/orchestration/master_turn.py`:
    - `TurnDriver.__init__(…, record_failure: Callable[[str, str], None])` (keyword-only, required)
    - `wake_turn() -> TurnStarted | None`, a sibling of `send_turn`. It claims the slot or returns
      `None` when busy. It opens with `render_wake_text(drain(...))` alone. If the drain turns out
      empty, it closes the runtime, releases the slot and returns `None`.
    - both failure paths (221-229, 297-311) call `self._record_failure(turn.turn_id,
      type(error).__name__)`
  - `src/shepherd/orchestration/wake.py`: `LevelThreeWaker(store: Store, level: Callable[[], int],
    open_wake: Callable[[], object], bump: Callable[[str], None])` with `tick() -> bool`, the RD-3
    gate using `store.retry_chain_depth` and `MAX_MASTER_ATTEMPTS`, and a `declined: set[str]` so the
    anomaly is bumped once per session
  - `src/shepherd/core/anomalies.py`: `MASTER_FAILED = "master_failed"`, appended **after** M4's
    section under a new comment "post-M4 (qa6 rulings, D79)"
  - `src/shepherd/toolsurface/registry.py`: `audit_master_failure(turn_id: str, error_class: str) ->
    None` (ADR-QR-3), plus D71's "binds" → "serves" in all three places that say it (re-measured):
    the module docstring at `:22` ("The registry is frozen before the server binds"), the error text
    at `:203` ("the registry was frozen before the server bound" → "…before the server served"),
    and `freeze()`'s docstring at `:211` ("before it binds anything" → "before it serves
    anything"). A test that matches the `:203` text is updated with it (grep `"server bound"` under
    `tests/` first).
  - `src/shepherd/toolsurface/compose.py`:
    - builds `TurnDriver(..., record_failure=_master_failure_recorder(store))`
    - builds `LevelThreeWaker(store, level=lambda: int(autonomy_level(store)), open_wake=driver.wake_turn,
      bump=store.bump_anomaly)`
    - `sweep=sweep_and_wake(mailbox_sweep(store, runner), waker.tick)`, which returns the mailbox
      counts unchanged
    - the docstring prose at :386 → "serves"
  - `tests/test_core_types.py::test_every_anomaly_member_is_unique_and_appended` (`:405`,
    assertions `:420-435`): the M4 assertion becomes "M4's members, then the post-M4 members
    `["MASTER_FAILED"]`, last". Declared. Not frozen, and the id is kept anyway.
    `test_m3_anomaly_members_are_appended_at_the_end` (frozen, `:1249`) asserts a prefix and is
    unaffected.
  - **Every `TurnDriver(` caller** passes `record_failure` (the kwarg is required: a default no-op
    would let a new composition drop H3 silently), re-measured:
    - `src/shepherd/toolsurface/compose.py:477`
    - `tests/orchestration/test_master_turn.py:274,630,719`
    - `tests/orchestration/test_master_turn_failures.py:61,137,181`
    - `tests/qa/test_s6_restart_continuity.py:123,175`
    - `tests/qa/test_s2_spawn_stop_wake.py:562`

    The `tests/qa/*` pair is in the **default lane** (no `live` mark). The test callers pass a
    recording double or `lambda _t, _e: None`, whichever the test's intent needs, and the ledger
    says which.
  - new `tests/orchestration/test_master_turn_wake.py`, new `tests/orchestration/test_master_failed.py`,
    new `tests/toolsurface/test_compose_wake_sweep.py`
- **Dependencies:** P1 (D69, D79).
- **Out-of-scope drift:**
  - interrupting or replacing a running turn for a wake
  - waking on `needs_you` (D31 forbids it)
  - a new thread
  - `tools_master.py` (pinned at 505; `autonomy_level` is imported, not edited)
  - BC-07's `is_error` turns (they end as `error` events, not driver failures)
- **Tests (RED first):**
  - `test_master_turn_wake.py`:
    - `test_level_3_opens_an_unprompted_turn_with_the_summary_alone` (factory called, prompt
      starts with `while you were away —`, no user text)
    - `test_a_wake_while_a_turn_runs_opens_after_that_turn_ends`
    - `test_a_wake_for_a_lineage_at_the_cap_opens_no_turn_and_counts_once_across_many_ticks`
    - `test_level_2_never_opens_an_unprompted_turn`
    - `test_a_wake_turn_that_finds_the_set_already_drained_opens_nothing`
    - `test_needs_you_never_wakes_the_master_at_level_3`
  - `test_master_failed.py`:
    - `test_a_turn_that_fails_to_open_counts_master_failed_once`
    - `test_a_turn_that_raises_counts_master_failed_once`
    - `test_the_failure_audit_record_carries_the_class_name_and_no_message`
    - `test_no_chokepoint_means_no_record_and_no_raise`
  - `test_compose_wake_sweep.py`: `test_the_sweep_still_returns_the_mailbox_counts_and_ticks_the_waker`
  - RED today: no factory call, no `master_failed`.
- **Checks:** the new files, `tests/orchestration/test_master_turn.py` (all existing),
  `tests/orchestration/test_master_turn_failures.py`, `tests/qa/test_s6_restart_continuity.py`,
  `tests/qa/test_s2_spawn_stop_wake.py`,
  `tests/orchestration/test_wake.py`, `tests/toolsurface/test_compose.py`, `tests/toolsurface/test_audit.py`,
  `tests/daemons/test_shutdown_master.py`, `tests/daemons/test_controld.py` (the sweep pins at 702 and
  861), `tests/test_core_types.py`, `tests/cli` (the doctor anomaly lines), boundaries, mypy.
- **Exit criteria:** GREEN; `compose.py` ≤ 600; the `test_core_types` change declared; `grep -rn
  "TurnDriver(" src tests` shows no call without `record_failure=`.
- **test_seams:** the orchestration seam (`TurnDriver` with the scripted master and a real `Store`);
  the L4 seam (`compose_tool_surface` wiring, `invoke` audit via a tmp audit root).
- **Checkpoint:** none. **Validation:** deterministic: event-gated scripted runtimes, and ticks driven
  by the test, not by time. **Durability:** stable.
- **Consumes:** `MAX_MASTER_ATTEMPTS` (`orchestration/admission.py`), `Store.retry_chain_depth`,
  `wake.drain`, `wake.render_wake_text`, `tools_master.autonomy_level(store)`.
- **Produces:**
  - `AnomalyKind.MASTER_FAILED` (value `"master_failed"`)
  - `TurnDriver.wake_turn() -> TurnStarted | None`
  - `TurnDriver(..., record_failure: Callable[[str, str], None])`
  - `LevelThreeWaker` with `tick() -> bool`
  - `registry.audit_master_failure(turn_id: str, error_class: str) -> None`
  - `compose.sweep_and_wake(sweep: Callable[[], MailboxCounts], tick: Callable[[], bool]) ->
    Callable[[], MailboxCounts]`

### P7 — BC-37 residual, SD-07, SD-08: kill verdict, pane-less sends, ask ids

- **Objective:**
  - a kill of an owned session after a finished turn records `killed`, unless `ended_at` changed
    across the kill
  - a send to a pane-less row is refused with no row
  - `ask()` returns our id as `from_fork_of` and the engine id separately
- **Rulings:** 10, 20, 21. **qa6:** O9, O10, L8 (oracle).
- **Files:**
  - `src/shepherd/orchestration/lifecycle.py`: read `before = store.get_owned_session(session_id)`
    before `runner.terminate`. After it, write the killed verdict (and bump
    `KILL_WITHOUT_SESSION_END`) when `after.ended_at == before.ended_at`. Keep the order in the module
    docstring's sentence, and amend it. **≤ 250 lines** by re-wrapping code, never prose.
  - `src/shepherd/toolsurface/tools_messaging.py`: the `handle is None` branch moves **before**
    `queue_message` and returns `{"message_id": None, "queued": False, "decision": "refuse_no_pty",
    "decision_text": …, "reason": f"{session_id}: no pane of ours — …", "delivered": 0,
    "deferred": 0}`. `project_ask` gains `"from_fork_of_engine_session_id"`.
  - `src/shepherd/orchestration/ask.py`: `AskResult.from_fork_of_engine_session_id: str` added.
    `from_fork_of = row.id` for the reply; `_residue` and the fork row keep using the engine id (a
    local name, `target_engine_id`). The early-return paths set both fields.
  - tests:
    - `tests/orchestration/test_lifecycle.py:372-416` (declared). The second direction (the ending
      arrived before the kill) now records `killed` and is counted (2). A new third direction: the
      runner double's `terminate` stamps `ended_at` → not counted, verdict kept. Node id kept.
    - new tests in `tests/orchestration/test_lifecycle_post_turn_kill.py`
    - `tests/toolsurface/test_tools_m3.py:526-552`:
      `test_send_to_a_row_with_no_pane_is_queued_not_lost` is **retired** → successor
      `test_send_to_a_row_with_no_pane_is_refused_with_no_row` (the unknown-id half is kept)
    - `tests/orchestration/test_ask.py:810,838`: assertions move to `from_fork_of == our row id` and
      `from_fork_of_engine_session_id == TARGET_ENGINE_ID` (declared; ids kept, names still true)
    - `tests/e2e/test_live_ask_fork.py:174` (live lane, same change)
    - `tests/qa6/live/test_wave8_1_live.py:1237` L8: `api.from_fork_of_is_the_session` (== our id)
      plus `api.engine_id_carried_separately`, with the reason recorded
- **Dependencies:** P1 (D74, D75).
- **Out-of-scope drift:** the mailbox write policy table; `store/mailbox.py`; the fork mechanics;
  BC-29's pane-gone path; `rename.py`.
- **Tests (RED first):**
  - `test_a_kill_after_a_finished_turn_records_killed`
  - `test_a_session_end_during_the_kill_keeps_its_own_verdict`
  - `test_send_to_a_row_with_no_pane_is_refused_with_no_row` (attached **and** a handle-less owned
    row; `mailbox_message` stays empty)
  - `test_ask_names_the_asked_session_by_our_id_and_carries_the_engine_id`
  - RED today: the verdict is kept, a row is queued, and the engine id is returned.
- **Checks:** `tests/orchestration/test_lifecycle.py`, the new file, `tests/orchestration/test_ask.py`,
  `tests/orchestration/test_mailbox.py`, `tests/toolsurface/test_tools_m3.py`,
  `tests/toolsurface/test_tools_messaging*.py` (if present), boundaries, mypy, the qa6 import check
  on wave 8.
- **Exit criteria:** GREEN; `lifecycle.py` ≤ 250 with no prose removed; the retired id and its
  successor in the ledger.
- **test_seams:** the orchestration seam (`record_and_terminate` with a runner double; `ask_session`
  with the scripted fork runner); the L4 seam (`invoke("send_to_session")` over a real `Store`).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** none.
- **Produces:**
  - `AskResult.from_fork_of_engine_session_id: str`
  - `project_ask(...)["from_fork_of_engine_session_id"]`
  - send-refusal payload `queued: False, decision: "refuse_no_pty"`

### P8 — BC-21 (C7) and H1-lock: bind before the store; hold the claim for life

- **Objective:**
  - `controld` binds its port before opening the store, so a busy port writes nothing
  - `controld` and `sessiond` each hold an exclusive `flock` on their socket's lock file for their
    lifetime
- **Rulings:** 8, 13. **qa6:** C7 (no oracle change), plus E16 (no scenario).
- **Files:**
  - `src/shepherd/engines/claude_code/ingest_socket.py`: `LOCK_SUFFIX = ".lock"`, a process-wide
    `_HELD: dict[Path, int]` under a lock, `claim_socket(plan)`, `release_claim(path: Path) -> None`,
    and the docstrings. `claim_socket`'s order (ADR-QR-2):
    1. `plan.path.parent.mkdir(parents=True, exist_ok=True)` and `os.chmod(plan.path.parent,
       plan.dir_mode)`, the two statements `bind_listener` runs at `:149-150`, because
       `controld.start` claims at `controld.py:71` before anything has created the runtime dir
    2. the lock step. If the path is already in `_HELD` (re-entrant), skip **only** the `flock`.
       Otherwise open `<path>.lock` 0600 (`os.open(…, O_RDWR | O_CREAT, 0o600)`), take
       `flock(LOCK_EX | LOCK_NB)` (a `BlockingIOError` → close the fd, `SocketInUse`), and register
       it as newly locked
    3. the connect-probe, on **every** claim, re-entrant or not. On a live listener → release the
       lock **only if step 2 newly took it**, then `SocketInUse`
    4. return the plan
  - `src/shepherd/daemons/control_ingest.py`: `release_claim(plan.path)` in `finally`, after
    `unlink_owned_socket` (and `serve_ingest` in `ingest_socket.py` likewise).
  - `src/shepherd/daemons/controld.py`: the new order:
    1. claim
    2. `create_server` (binds, serves nothing)
    3. `open_store`; on failure, `server.server_close()`
    4. `compose_tool_surface`; on failure, close both
    5. threads

    Docstring lines 11-18 rewritten to D71's order. **≤ 140 lines, net zero, no prose removed.**
    `main()` keeps its three except arms.
  - `src/shepherd/daemons/sessiond.py`: the docstring sentence on the lock. It needs no code change
    (it already claims at `:71`).
  - `src/shepherd/toolsurface/export.py:49`: docstring "binds" → "serves" (D71).
  - tests:
    - new `tests/engines/test_socket_lifetime_lock.py`
    - new `tests/daemons/test_controld_start_order.py`
    - `tests/daemons/test_controld.py`: the module docstring's ADR-7 line (`:15`, "frozen before
      the server binds") → "serves"; `test_the_registry_is_frozen_before_the_server_binds` (frozen,
      `collected_node_ids.txt:174`) is
      **retired** → successor `test_the_registry_is_frozen_before_the_server_serves` in the new file;
      `test_no_new_socket_is_bound` (769-775) filters to socket files, declared (the name is still
      true)
    - `tests/daemons/test_sessiond_socket.py`: one new test
    - new `tests/daemons/conftest.py`. The `world` fixture and its `World` type are **moved** there
      from `tests/daemons/test_controld.py:128-` (module-local today, so the new
      `test_controld_start_order.py` cannot see it). It is a pure move: no node id changes, and
      `test_controld.py` keeps using it through the conftest
- **Dependencies:** P1 (D71, D72).
- **Out-of-scope drift:**
  - the RPC socket (P10)
  - `host/` (no platform branch: `fcntl.flock` is POSIX on both hosts, D55)
  - `RESERVED_FOR_M2`
  - unlinking lock files
  - `plane.py`
- **Tests (RED first):**
  - `test_socket_lifetime_lock.py`:
    - `test_a_second_descriptor_cannot_take_a_held_claim` (two raw fds in-process, the low-level
      acquire)
    - `test_a_held_claim_refuses_even_when_the_socket_file_is_absent` (E16's window)
    - `test_a_held_claim_refuses_a_path_that_answers_econnrefused` (the macOS full-backlog case, by
      fixture)
    - `test_a_second_claim_in_the_owning_process_is_reentrant`
    - `test_a_reentrant_claim_still_probes_and_refuses_a_live_listener` (an in-process owner via
      `bind_listener`; a second `claim_socket` → `SocketInUse`; the owner's lock is still held and
      its socket still serves)
    - `test_a_claim_refused_by_the_probe_does_not_keep_the_lock_it_took` (a fixture listener with no
      lock of ours, e.g. a raw `socket.bind` + `listen` standing in for an older binary. The claim →
      `SocketInUse`. A subprocess then takes `flock` on `<path>.lock` successfully, which proves the
      refused claim released it; no signal, no kill)
    - `test_release_frees_the_claim_for_the_next_owner`
    - `test_the_lock_file_is_0600_in_the_socket_dir`
    - `test_a_claim_with_the_runtime_dir_absent_creates_it_at_the_plans_mode` (the plan's parent
      does not exist; after the claim it exists at `dir_mode` and holds `<name>.sock.lock`; then
      `bind_listener` on the same plan still succeeds, re-entrant). RED today only after the lock
      lands: the first version of the lock code raises `FileNotFoundError` here, which is the
      finding this test pins
    - `test_a_child_process_that_exits_frees_its_lock`: a `subprocess` python that locks and returns
      normally. **No signal, no kill** (CLAUDE.md rule 3).
  - `test_controld_start_order.py`:
    - `test_an_occupied_port_writes_no_database` (C7)
    - `test_a_first_start_with_no_runtime_dir_claims_and_binds` (`world` fixture with the runtime
      dir removed before `start()`)
    - `test_a_newer_schema_closes_the_port_it_bound`
    - `test_the_registry_is_frozen_before_the_server_serves`: a request queued on the bound port before
      `serve_forever` is answered by the frozen registry
  - `test_sessiond_socket.py`: `test_sessiond_holds_its_claim_until_shutdown`
  - RED today: the DB exists after a busy port, and a second descriptor takes the path.
- **Checks:** the new files, `tests/daemons` (all), `tests/engines/test_socket_live_owner.py`
  (**must stay green unchanged**, and in particular `:120-121`, `:148-149` and `:161-176`, which
  claim in-process against an in-process owner and so pin "re-entrant still probes"),
  `tests/qa/test_s7_shutdown_in_flight.py` (the known flaky test, recorded separately), boundaries,
  mypy.
- **Exit criteria:** GREEN; `controld.py` ≤ 140; every `daemons/*` ≤ 150; the retired id and its
  successor in the ledger.
- **test_seams:** unit at `claim_socket`/`release_claim` over `tmp_path` (the ingest-socket seam);
  integration at `controld.start()` with a scripted host (the existing `tests/daemons` `world`
  fixture).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** none.
- **Produces:**
  - `claim_socket(plan: SocketPlan) -> SocketPlan` (now lock-holding, re-entrant, and it creates the
    socket dir at `plan.dir_mode`)
  - `release_claim(path: Path) -> None`
  - `LOCK_SUFFIX = ".lock"`
  - `controld.start` order: claim → bind → store → compose → threads

### P9 — BC-32: merge the parked fix under a declared `server.py` edit

- **Objective:** the body-read timeout ships. `test_web_server_is_byte_unchanged` accepts a
  **declared** `post_milestone.edits` entry and keeps the digest pin. Gate B gets a declared post-M4
  import table, whose entries P13 fills.
- **Ruling:** 11. **qa6:** A4 (no oracle change).
- **Files:**
  - `git merge --no-ff 9aa9f11` (the sha, not the branch name `fix/qa6-P10-bc32-owner`, so a moved
    branch cannot change what is merged; verify first that `git rev-parse fix/qa6-P10-bc32-owner`
    is still `9aa9f11…` and record it) (brings `src/shepherd/web/server.py` and
    `tests/web/test_server_short_body.py`). Resolve the `docs/plans/qa6-bugfix-blockers/P10.md`
    add/add: keep the mainline file and append the branch's "Router decision / BC-32" section, under
    a note "merged 2026-09-27, ruling 11".
  - `tests/boundaries/test_consumer_surface_additive.py`:
    1. `test_web_server_is_byte_unchanged` (280-294). Pass when the live digest ==
       `pre_m4_routes.json` `server_sha256` (unchanged). **Or** when the manifest's
       `post_milestone.edits` declares `web/server.py` **and** the live digest == manifest
       `files["web/server.py"]`. The `baseline["web/server.py"] == recorded` assertion stays. The
       docstring cites ruling 11 and ADR-M4-7's amendment.
    2. New negative controls on literals: `test_an_undeclared_server_edit_is_caught` and
       `test_a_declared_server_edit_with_a_stale_files_digest_is_caught`.
    3. `POST_M4_ADDED_IMPORTS: Mapping[str, frozenset[str]] = {}` and
       `POST_M4_ADDED_MODULES: frozenset[str] = frozenset()` beside T24's tables.
       `test_the_consumer_import_sets_are_additive_only` accepts `added == declared_additions() +
       post_m4_additions()`, and each post-M4 module path must have a manifest `post_milestone`
       entry.
    4. New negative control `test_a_post_m4_import_without_a_manifest_entry_is_caught`.
- **Dependencies:** P1.
- **Out-of-scope drift:** re-pinning `server_sha256`; editing `baseline`; any other `server.py`
  change; filling the tables (P13).
- **Verify:** `git diff --stat fix/qa6-rulings...HEAD` lists exactly `web/server.py`,
  `tests/web/test_server_short_body.py`, `docs/plans/qa6-bugfix-blockers/P10.md`, the boundary test
  and this phase's ledger.
- **Tests:** `tests/web/test_server_short_body.py` (branch, RED recorded on the branch in `P10.md`),
  and the new negative controls (RED: the old test rejects any declared edit).
- **Known-red until P13:** `test_web_server_is_byte_unchanged` (no manifest entry yet) and Gate A's
  two tests.
- **Checks:** `tests/web` (all), `tests/boundaries` (known-red listed), mypy.
- **Exit criteria:** the merge is clean as above; the new controls GREEN; `test_server_short_body.py`
  GREEN.
- **test_seams:** the boundary seam (manifest and digest over literals, then over the tree at P13); the
  HTTP seam (`tests/web/test_server_short_body.py`).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** `9aa9f11`.
- **Produces:**
  - `POST_M4_ADDED_IMPORTS: Mapping[str, frozenset[str]]`
  - `POST_M4_ADDED_MODULES: frozenset[str]`
  - `BODY_READ_TIMEOUT_S = 2.0` (`web/server.py`)
  - the rule: a declared `post_milestone` edit of `web/server.py` is accepted when `files` holds its
    live digest

### P10 — BC-05: the CLI reaches `controld` over an owner-only RPC socket

- **Objective:** `status`, `doctor` (the discovery and hooks lines), `install-hooks`,
  `uninstall-hooks`, `replay` and `recompute` run against a running `controld` through
  `invoke()` as HUMAN. `replay --since 2026-13-45` is exit 64.
- **Ruling:** 1. **qa6:** C1 C2 C3 C4 C5.
- **Files:**
  - new `src/shepherd/toolsurface/rpc.py` (ADR-QR-1): `RPC_SOCKET_NAME = "rpc"`,
    `RPC_WIRE_VERSION = 1`, `MAX_REQUEST_BYTES = 1 << 20`, `RPC_CALLER_ID = "cli"`,
    `answer_request(raw: bytes) -> bytes`, `call_remote(path: Path, name: str, args: Mapping[str,
    object], ctx: CallerContext, timeout_s: float = 120.0) -> ToolResult | None`, and small
    decode/encode helpers. **It logs nothing** (revision 3, F4): a refusal is the returned reply,
    and `src/` has no logger. D25 forbids `toolsurface/` importing `shepherd.logs`
    (`tests/boundaries/_imports.py:420-446`). Never `print`.
  - new `src/shepherd/daemons/control_rpc.py` (≤ 150 lines, wiring only):
    `serve_control_rpc(plan: SocketPlan, shutdown: threading.Event, bound: threading.Event | None =
    None) -> None`. It runs bind → `owned_inode` → `bound.set()` → accept loop (`accept_next`,
    `read_to_eof`, `answer_request`, `sendall`, close; a peer that closed early loses its connection,
    never the daemon) → `finally`: close, `unlink_owned_socket`, `release_claim`.
  - `src/shepherd/daemons/controld.py`: claim the `rpc` plan beside the control plan, a fourth thread
    `"rpc"`, `Controld.rpc_socket_path: Path`, and wait for both bounds. **≤ 140, net zero; prose
    kept.** If net zero is impossible, the permitted escape is a daemons helper module, not a cap
    edit.
  - `src/shepherd/cli/commands.py`: `Cli` gains `remote: Path | None`. `Cli.call` → `call_remote(...)`
    when `remote` is set and answers, else the local `invoke`. `explain()` is unchanged.
  - `src/shepherd/cli/main.py`:
    - builds `remote=host.control_socket(RPC_SOCKET_NAME).path` (a `SocketPathTooLong` → `None`)
    - `parse()` validates `--since` as a real `YYYY-MM-DD` (regex `^\d{4}-\d{2}-\d{2}$`, then
      `date.fromisoformat`) → the problem `f"{SINCE_FLAG} {value} is an invalid date (expected
      YYYY-MM-DD)"`, i.e. `--since 2026-13-45 is an invalid date (expected YYYY-MM-DD)` →
      `EXIT_USAGE` before any call. The word **`invalid`** is load-bearing: C5's clause
      `logs.names_the_date_invalid` requires `"2026-13-45" in stderr and "invalid" in
      stderr.lower()` (`tests/qa6/cli/test_wave2_cli.py:119-121`). `main()` prints the problem with
      the existing `shepherd: ` prefix and writes nothing to stdout (C5's `_prefix` and
      `_stdout_empty` clauses)
    - the module docstring cites D68
  - tests:
    - new `tests/toolsurface/test_rpc_wire.py`
    - new `tests/daemons/test_control_rpc.py`
    - new `tests/cli/test_cli_rpc.py`
    - `tests/cli/test_commands.py` only if a helper signature moved. P4 also edits this file (the
      schema lines `:443-444,702`), so any P10 hunk stays away from those lines, and the ledger
      lists it for P13's merge
    - `tests/daemons/test_controld.py`: `test_the_root_still_wires_exactly_three_threads` →
      **retired**, successor `test_the_root_wires_exactly_four_threads` (`("ingest", "rpc", "scan",
      "http")`); `test_no_new_socket_is_bound` → **retired**, successor
      `test_controld_binds_exactly_its_control_and_rpc_sockets`
    - `tests/qa/test_s8_status_against_a_daemon.py` (live lane, not frozen): the inability tests
      become their positive successors, as its own docstring predicts
    - **the shutdown line** (revision 3, F1). A fourth joined thread makes `ShutdownOutcome.__str__`
      (`src/shepherd/daemons/shutdown.py:69`, which counts `len(self.joined)`) print `4 threads
      exited · store closed`. `shutdown.py` itself is unchanged. Declared value changes, ids kept:
      - `tests/daemons/test_controld.py:959`: `sorted(outcome.joined) == ["http", "ingest",
        "scan"]` → `["http", "ingest", "rpc", "scan"]`, in
        `test_stop_returns_the_shutdown_outcome_rather_than_nothing` (frozen,
        `collected_node_ids.txt:194`; the name stays true)
      - `tests/daemons/test_controld.py:1001`: `"3 threads exited · store closed"` → `"4 threads
        exited · store closed"`, in `test_the_process_prints_what_shutdown_found` (frozen, `:195`;
        the name stays true)
      - `:940-948` (`test_when_every_thread_exits_…`) builds its own three synthetic threads and is
        **not** changed
  - qa6 shutdown-line oracles (revision 3, F1; each reason in the ledger, and each on P15's
    changed-clause list; clause names kept, expected text re-valued):
    - W4: `tests/qa6/sub/test_wave1_boot.py:46` `W4_STOP_LINE` → `"controld stopped: 4 threads
      exited · store closed"` (checked at `:251`, `logs.stop_line`). **Shared file with P4** (`:127`)
    - D10: `tests/qa6/sub/test_wave3_1_discovery.py:522` `logs.first_stop_line` → `"controld
      stopped: 4 threads exited · store closed"`
    - M19: `tests/qa6/inproc/test_wave5_9_shutdown.py:29` `EXPECTED_LINE` → `"4 threads exited ·
      store closed · 1 approvals withdrawn"` (checked at `:65`). Its comment at `:28` reads
      "test-plan M19, verbatim". The ledger records that the test-plan's M19 text
      (`.cc10x/qa/wf-20260923T182839Z-9adb11fc/test-plan.md`) is superseded by D68's fourth
      thread, and the comment becomes "test-plan M19, re-valued by D68 (a fourth thread,
      `rpc`)". The test-plan file is QA evidence and is not edited
    - `tests/qa6/manifest/qa6-live-harness.json:60`: W4's text `'controld stopped: 3 threads
      exited · store closed'` → `4 threads` (P1 already edited `:350` of this file, merged before)
  - qa6 (RD-1): move C3's scenario function from `tests/qa6/cli/test_wave2_cli.py` into
    `tests/qa6/sub/test_wave2_1_cli_status.py`, run against `fleet.controld`, clauses unchanged. Update
    the cli module docstring (C5 only). **Shared file with P4** (P4 edits `:103`). P10 only appends
    the function and its imports, and touches no existing line.
- **Dependencies:** **P8** (branch `fix/qa6r-P8`: `controld.py`, `test_controld.py`, `release_claim`);
  P1 (D68).
- **Out-of-scope drift:**
  - any SESSION audience on the socket (SD-09, deferred)
  - a client-declared audience
  - HTTP
  - multiplexing the ingest socket
  - registering hook tools in the CLI process
  - `cli/replay.py` (unless `--since` needs it; validation lives in `parse()`)
- **Tests (RED first):**
  - `test_rpc_wire.py` (pure):
    - `test_a_request_is_invoked_as_human_whatever_it_says`
    - `test_a_malformed_request_invokes_nothing` (bad JSON, too big, wrong `v`, a missing field, a bad
      correlation id)
    - `test_a_reply_round_trips_ok_refused_failed_and_unavailable`
    - `test_untransportable_data_is_a_failed_reply`
  - `test_control_rpc.py` (a real UDS in `tmp_path`):
    - `test_a_call_round_trips_through_the_socket`
    - `test_the_socket_is_0600_in_a_0700_dir`
    - `test_no_daemon_is_none_not_an_error`
    - `test_a_peer_that_hangs_up_early_harms_nothing`
    - `test_a_human_rpc_call_is_audited_like_the_web_ui` (chokepoint installed; one audit row,
      `actor_kind` human)
    - `test_the_rpc_socket_name_fits_the_control_sockets_budget` (PP15)
  - `test_cli_rpc.py`:
    - `test_status_reads_the_daemons_fleet_through_the_socket`
    - `test_install_hooks_dry_run_and_yes_run_in_the_daemon`
    - `test_the_cli_falls_back_to_local_reads_with_no_daemon`
    - `test_an_impossible_since_date_is_a_usage_error` (`2026-13-45`, `2026-02-30`, `30d` → 64;
      for each, stderr starts `shepherd: `, contains the value **and** `invalid`, and stdout is
      empty; no RPC request is sent, asserted with a listener double that records connects)
    - `test_a_valid_since_date_is_forwarded`
    - `test_doctor_discovery_and_hooks_lines_come_from_the_daemon` (a running `controld`, see
      test_seams; `doctor`'s discovery and hooks lines carry the daemon's state, and the audit
      holds the HUMAN `cli` rows for the tools `doctor` calls)
    - `test_uninstall_hooks_runs_in_the_daemon` (`--dry-run` then `--yes` against a `tmp_path`
      settings file; the file changes only on `--yes`; one audit row each, `actor_kind` human)
    - `test_replay_and_recompute_run_in_the_daemon` (`replay --since <valid date>` and
      `recompute`, its alias (`cli/main.py:64`), each answered by the daemon's registered tool rather than the local "not
      available" explanation; the exit codes are the tool's)
  - RED today: no socket, and exit 1 instead of 64.
- **Needs from P13:**
  - manifest `post_milestone` entries for `cli/main.py` and `cli/commands.py`
  - post-M4 imports: `cli/main.py: shepherd.toolsurface.rpc` (and whatever the ledger lists)

  **Known-red:** Gate A's two tests and `test_the_consumer_import_sets_are_additive_only`.
- **Checks:** the new files, `tests/cli`, `tests/daemons` (including `:959` and `:1001`),
  `tests/toolsurface/test_audit.py`,
  `tests/boundaries` (known-red listed), mypy. Live: `cd $W && PYTHONPATH=$W/src
  /Users/noamsalit/Git/Shepherd/.venv/bin/pytest -p no:randomly -m live
  tests/qa/test_s8_status_against_a_daemon.py`. Run it **only after** reading its fixture and
  confirming these, recorded in the ledger (revision 3, F9; re-measured):
  - a throwaway HOME (`isolated_env(home)` under `tmp_path`, `:212-216`)
  - a port from `a_free_port()` (`:71`, used at `:217`: a kernel-assigned loopback port, bound
    then released), which is **not** port 0 and must not be 8787
  - teardown `_stop` (`:234-248`): `terminate()` on **its own child** `process`, a bounded wait,
    then a `process.kill()` fallback on that same child only
  - no signal or kill reaches any other pid (CLAUDE.md mutation rule 3; the conftest net refuses
    pids 0, 1 and -1)
  The qa6 import check on waves 1, 2, 3 and 5 (the modules W4, C3, D10 and M19 live in).
- **Exit criteria:** GREEN; `controld.py` ≤ 140; `daemons/control_rpc.py` ≤ 150; the retired ids and
  successors in the ledger; the manifest and import needs listed.
- **test_seams:** the L4 seam (`answer_request` / `call_remote` over a real UDS); the CLI seam
  (`cli.main.main(argv, out, err, host)`, the existing one); `controld.start()` for the thread and
  socket pins.
  - `tests/cli/test_cli_rpc.py`'s "running daemon" is `controld.start(host, 0)` over the
    `tests/cli/conftest.py:60` `scripted_host(runtime_dir=…, data_dir=…)` helper (the one
    `test_commands.py:694` uses), stopped with `controld.stop` in a `finally`.
  - If that helper cannot drive `start()`, the builder adds a `world`-shaped fixture to
    `tests/cli/conftest.py`, modelled on P8's `tests/daemons/conftest.py::world`, and records it.
  - Wherever the P10 test list says "`world` fixture", it means this.
- **Checkpoint:** none. **Validation:** deterministic, plus the one live-lane file (a probabilistic
  host; a re-run once on failure, recorded).
- **Durability:** stable.
- **Consumes:** `claim_socket(plan: SocketPlan) -> SocketPlan` and `release_claim(path: Path) -> None`
  (P8); `bind_listener`, `accept_next`, `read_to_eof`, `owned_inode`, `unlink_owned_socket`
  (existing); `registry.invoke(name, args, ctx) -> ToolResult` (existing).
- **Produces:**
  - `RPC_SOCKET_NAME = "rpc"`
  - `answer_request(raw: bytes) -> bytes`
  - `call_remote(path: Path, name: str, args: Mapping[str, object], ctx: CallerContext, timeout_s:
    float = 120.0) -> ToolResult | None`
  - `serve_control_rpc(plan: SocketPlan, shutdown: threading.Event, bound: threading.Event | None =
    None) -> None`
  - `Controld.rpc_socket_path: Path`
  - thread name `"rpc"`

### P11 — SD-06: decision-card choices are clickable

- **Objective:** clicking a numbered choice on a permission dialog posts `{"choice": …}` to
  `/api/sessions/{id}/permission` once. The trust dialog stays inert and says why.
- **Ruling:** 19. **qa6:** U14 (no oracle change).
- **Files:**
  - `src/shepherd/web/static/session.js` (522-590):
    - `PERMISSION_ANSWERS = {1: "approve", 2: "approve_always", 3: "deny"}`, with a comment citing
      `dialog_keys.PERMISSION_KEYS`
    - `UNIVERSAL_ANSWERS = {approve: "approve", reject: "deny"}`
    - choices become `<button type="button">` rows, only when `pane_kind === "permission_dialog"`
    - the click posts once (an in-flight guard) and writes the reply's reason or outcome into the card
      note
    - `DECISION_INERT` stays for `trust_dialog` and for a choice with no mapping
  - `tests/web/test_session_wiring.py::REQUIRED_ASSIGNMENTS`: add the exact new assignments, declared
  - `tests/web/test_decision_live.py`: new browser tests
  - new `tests/web/test_decision_answer_table.py`: it parses the JS table and asserts it equals
    `{n: k for n, k in zip((1, 2, 3), PERMISSION_KEYS)}` in `dialog_keys` order
- **Dependencies:** P1 (D77).
- **Out-of-scope drift:** answering trust dialogs; `tools_terminal.get_decision`; the server route;
  the terminal (P12).
- **Tests (RED first):**
  - `test_clicking_a_permission_choice_posts_its_answer_once`
  - `test_a_double_click_posts_once`
  - `test_the_trust_dialog_choices_stay_inert_and_say_why`
  - `test_an_unreadable_permission_screen_answers_approve_and_reject_through_the_same_route`
  - `test_a_refused_answer_is_shown_on_the_card`
  - RED today: no POST.
- **Needs from P13:** a `post_milestone` rewrite for `web/static/session.js` (it already has an
  entry, so its whole divergence is rewritten). **Known-red:** Gate A's two tests.
- **Checks:** `tests/web/test_decision_live.py`, `tests/web/test_session_wiring.py`,
  `tests/web/test_session_page.py`, `tests/web/test_routes_decision.py`, the new file,
  `js_syntax_check` on `session.js`, boundaries (known-red listed), mypy.
- **Exit criteria:** GREEN; the pin updated.
- **test_seams:** the real-browser seam over the harness page (the existing one). The static
  JS-table cross-check.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Consumes:** route `POST /api/sessions/{session_id}/permission` with body arg `choice`
  (`web/routes.py:103,151`, existing).
- **Produces:** `PERMISSION_ANSWERS` (`session.js`).

### P12 — SD-05: typing in the terminal reaches the pane

- **Objective:** WebSocket text and binary frames from an origin-checked terminal connection are
  written to the pane. The emulator accepts input. The page stops saying input is unwired.
- **Ruling:** 18. **qa6:** T3, U10.
- **Files:**
  - `src/shepherd/toolsurface/tools_terminal.py`: `TerminalStream.write(data: bytes) -> None` (a
    field `writer: Callable[[bytes], None]` bound in `terminal_stream()` to `runner.write(handle,
    …)`). **≤ 450.**
  - `src/shepherd/web/ws.py`: `pump_input(read: Callable[[int], bytes], deliver: Callable[[bytes],
    None]) -> int`. It returns the close code it ended on and uses `parse_frame` (ADR-QR-4).
  - `src/shepherd/web/server.py` `_terminal` (273-322): after the snapshot, start
    `threading.Thread(target=_pump, daemon=True)`. `_pump` runs `ws.pump_input(self.rfile.read1,
    stream.write)`, then `stream.close()`. The writer loop is unchanged.
  - `src/shepherd/web/static/terminal.js`:
    - `disableStdin: false`
    - `term.onData((text) => socket.send(text))` once the socket is open
    - `INPUT_UNAVAILABLE` is replaced by nothing false. The note carries only `FIT_LIMITATION`; the
      export is removed or renamed, whichever the pins show.
  - `src/shepherd/web/static/session.js`: the `note.textContent` assignment.
  - tests:
    - `tests/web/test_session_wiring.py::REQUIRED_ASSIGNMENTS` (the note entry)
    - `tests/web/test_session_page.py`: `test_the_keystroke_path_is_absent_and_says_so` is
      **frozen** (`collected_node_ids.txt:1434`; revision 1 wrongly said "not frozen"), so it is
      **retired** → successor `test_the_keystroke_path_is_wired_and_the_page_says_nothing_false`
      (a `RETIRED_NODE_IDS` entry through P13, decision `§3 D76`); the pty-token scan covers the new
      input line
    - `tests/boundaries/test_ws_read_path.py`: `test_the_ws_parser_has_no_caller_anywhere_in_src`
      (frozen) → **retired**, successor `test_the_ws_parser_has_exactly_one_caller_the_input_pump`.
      The rule now asserts `parse_frame`'s only caller is `ws.pump_input` and `pump_input`'s only
      caller is `server.FleetHandler._terminal`. Keep `test_the_rule_fires_on_a_module_that_does_read_the_socket`.
      Re-read `test_the_parser_tests_outnumber_the_parsers_callers`; if its name becomes false, retire
      it too with a successor.
    - new `tests/web/test_ws_input_pump.py`
    - new `tests/web/test_terminal_input_server.py`
    - new `tests/web/test_terminal_input_live.py`
- **Dependencies:** **P9** (the declared `server.py` edit mechanism; `server.py` merged) and **P11**
  (`session.js`, `test_session_wiring.py`). Branch `fix/qa6r-P11` + merge `fix/qa6r-P9`.
- **Out-of-scope drift:** resize from the browser; a POST route; auditing keystrokes; the D6 fit;
  attached sessions (no pane).
- **Tests (RED first):**
  - `test_ws_input_pump.py` (pure, byte buffers):
    - `test_text_and_binary_frames_are_delivered_verbatim`
    - `test_a_masked_frame_is_unmasked`
    - `test_a_frame_split_across_reads_is_reassembled`
    - `test_a_close_frame_ends_the_pump`
    - `test_an_empty_read_ends_the_pump`
    - `test_an_oversize_frame_ends_the_pump_with_1009`
    - `test_a_ping_is_not_delivered`
  - `test_terminal_input_server.py` (a real server on port 0, scripted runner):
    - `test_a_typed_frame_reaches_runner_write`
    - `test_typing_writes_no_audit_row_but_the_open_does` (a chokepoint and sink installed)
    - `test_a_closed_pane_ends_the_reader_thread`
    - `test_a_bad_origin_gets_no_reader`
  - `test_terminal_input_live.py` (browser): `test_keystrokes_in_the_emulator_are_sent_on_the_socket`
  - RED today: no reader, `disableStdin`.
- **Needs from P13:**
  - manifest `post_milestone`: `web/server.py` (combined BC-32 + SD-05 divergence), `web/ws.py`
    (new entry), `web/static/terminal.js` and `web/static/session.js` (rewritten entries)
  - post-M4 imports: `web/server.py: threading` (and whatever the ledger lists)
  - `RETIRED_NODE_IDS`: the ws read-path id(s) and `test_session_page.py::test_the_keystroke_path_is_absent_and_says_so`

  **Known-red:** Gate A's two tests, `test_web_server_is_byte_unchanged`, and
  `test_the_consumer_import_sets_are_additive_only`.
- **Checks:** the new files, `tests/web` (all), `tests/boundaries` (known-red listed), mypy,
  `js_syntax_check` on `terminal.js` and `session.js`.
- **Exit criteria:** GREEN; `tools_terminal.py` ≤ 450; retirements listed.
- **test_seams:** unit at `ws.pump_input` (a pure loop over callables); the HTTP/WS seam (a real
  `FleetServer` on loopback port 0 with the scripted runner); the real-browser seam.
- **Checkpoint:** none. **Validation:** deterministic. Thread joins are bounded (5 s) and asserted.
  **Durability:** stable.
- **Consumes:** the P9 rule for a declared `server.py` edit; `PERMISSION_ANSWERS` (unused; `session.js`
  as P11 left it); `ws.parse_frame(buffer: bytes) -> tuple[Frame | None, int]` (existing).
- **Produces:**
  - `TerminalStream.write(data: bytes) -> None`
  - `ws.pump_input(read: Callable[[int], bytes], deliver: Callable[[bytes], None]) -> int`

### P13 — Integration: merges, the manifest, the import and node-id declarations

- **Objective:** one tree with every phase in it, every consumer move declared, every retired id
  explained, and the default lane at the baseline reds.
- **Files:**
  - `tests/boundaries/consumer_manifest.json`:
    - `files`: live digests for every `web/` and `cli/` path
    - `post_milestone.edits`: one entry per moved path not in `rebase.regenerated_paths`
      (`cli/commands.py`, `cli/main.py`, `web/server.py`, `web/ws.py`, `web/static/session.js`,
      `web/static/terminal.js`, and any other the ledgers list), each `why` covering the path's
      **whole** divergence from `baseline`
    - `baseline` and `rebase` **untouched**
  - `tests/boundaries/test_collected_node_ids.py::RETIRED_NODE_IDS`, one entry each. Each reason is
    longer than 80 characters and names the successor. Each decision string contains `§3 D<nn>`
    (the `§` satisfies `test_collected_node_ids.py:335`). Every id below was checked as present in
    `collected_node_ids.txt` (line shown):
    - `tests/daemons/test_controld.py::test_the_registry_is_frozen_before_the_server_binds` (`:174`;
      P8, §3 D71)
    - `tests/daemons/test_controld.py::test_no_new_socket_is_bound` (`:188`; P10, §3 D68)
    - `tests/daemons/test_controld.py::test_the_root_still_wires_exactly_three_threads` (`:187`; P10,
      §3 D68)
    - `tests/orchestration/test_spawn.py::test_an_unknown_trust_verdict_stays_unknown` (`:692`; P4,
      §3 D78)
    - `tests/test_core_stops.py::test_stop_reason_has_twenty_members` (`:1231`; P4, §3 D73:
      "twenty" became false when `refused` became §8's 21st reason; successor
      `test_stop_reason_has_twenty_one_members`, the same set plus `refused`)
    - `tests/toolsurface/test_tools_m3.py::test_send_to_a_row_with_no_pane_is_queued_not_lost`
      (`:1335`; P7, §3 D74)
    - `tests/boundaries/test_ws_read_path.py::test_the_ws_parser_has_no_caller_anywhere_in_src`
      (`:58`; P12, §3 D76)
    - `tests/web/test_session_page.py::test_the_keystroke_path_is_absent_and_says_so` (`:1434`; P12,
      §3 D76: the keystroke path now exists by ruling 18; successor
      `test_the_keystroke_path_is_wired_and_the_page_says_nothing_false`)
    - `tests/boundaries/test_ws_read_path.py::test_the_parser_tests_outnumber_the_parsers_callers`
      (`:60`), **only if** P12's ledger retired it
    - any other id a ledger lists

    **Updated entry** (revision 3, F9): the existing
    `tests/store/test_migration_003.py::test_future_schema_refuses_to_start_at_four` reason
    (`test_collected_node_ids.py:84-93`) names its successor as `test_future_schema_refuses_to_start_at_five,
    which inserts version 5` (`:91`). P4 renamed that successor, so the reason now ends:
    "…re-proved one version up by the named successor in the same module,
    test_future_schema_refuses_to_start_at_six, which inserts version 6 (renamed from …_at_five when
    §3 D73's migration 005 made 5 real)." The decision string gains "; §3 D73".

    Not an entry: `tests/store/test_migration_003.py::test_future_schema_refuses_to_start_at_five` →
    `…_at_six` (P4). It is not frozen, so it is not in `missing`, and an entry for it would itself
    be flagged as a stale exemption (`test_collected_node_ids.py:263-268`).
  - `tests/boundaries/test_consumer_surface_additive.py`: the `POST_M4_ADDED_IMPORTS` and
    `POST_M4_ADDED_MODULES` entries, from the P10 and P12 ledgers
  - new `docs/plans/qa6-rulings-blockers/README.md`:
    - ruling → phase → commit → ledger
    - every changed assertion
    - every changed qa6 clause (old → new, reason)
    - the re-based paths whose `files` digest alone moved (`web/static/chat.js`,
      `web/static/index.html` (P3, `#shepherd-event`), `web/routes.py` if
      touched, `app.css` if touched)
    - siblings left open
- **New integration test** (P13's one authored test file; no product edits):
  `tests/toolsurface/test_refused_start_wakes_nothing.py`, over the merged P4 + P6 composition
  (`compose_tool_surface` with a scripted runner and a counting master factory, a real `Store` in
  `tmp_path`, level 3). It drives `wiring.sweep()` directly, never waiting on the 2 s timer.
  - `test_a_refused_master_spawn_at_level_3_opens_no_wake_turn`. The runner refuses `start`, and
    `invoke("spawn_session", …, MASTER ctx)` → `spawned: false`. The row is ended `refused`. Then
    three `wiring.sweep()` calls. The factory count is unchanged, `wake_retry_cap_reached` is
    unchanged, and `master_last_turn_at` is unchanged.
  - Positive control `test_a_killed_master_spawn_at_level_3_opens_one_wake_turn`: same wiring, the
    start succeeds, then a kill (`record_and_terminate`). One `wiring.sweep()` → the factory count
    +1, and the next sweeps add nothing (PP9).

  This is the P4 × P6 seam that neither phase can test alone (finding B5a). Validation:
  deterministic.
- **Step 0, before any merge into `fix/qa6-rulings`: back up the owner's real database** (revision
  3, F7). Merging P4 puts migration 005 in the main checkout's editable install, and the owner's
  running `controld` imports that tree the next time it starts.
  1. Resolve the path from the host seam, read-only: `detect_host().dirs().data_dir / DB_NAME`,
     via a quoted-heredoc python in the main checkout. On this Mac that is
     `~/Library/Application Support/Shepherd/shepherd.db` (`host/mac.py:70,238`,
     `daemons/controld.py:46,73`).
  2. **Absent:** record "no real shepherd.db at <path>" in the P13 ledger and continue.
  3. **Present** (it is present at planning time: `shepherd.db` 102400 bytes, `shepherd.db-wal`
     4120032 bytes, `-shm`, and an older `shepherd.db.v3-backup-20260923`. The P0 ledger shows a
     live listener on 8787, so the database may be open):
     - if `shepherd.db.pre-005.bak` already exists, stop and report. Never overwrite it
     - take a **consistent** copy with SQLite's online backup, from a **read-only** connection:
       `src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)`,
       `dst = sqlite3.connect(bak)`, `src.backup(dst)`, then close both.
       - Why not `cp`: a plain copy of the main file alone misses every committed page still in
         the 4 MB WAL, and copying the three files while a writer runs can tear.
       - A `mode=ro` reader writes no page of the original (it only takes the reader's
         shared-memory slot, as any reader does), never checkpoints it, and never migrates it.
         `migrate()` is not called.
     - verify **the copy only**: `PRAGMA integrity_check` = `ok`, and
       `read_schema_version(bak)`. This is expected to be 4. Record it; a 3 is also possible,
       given the v3 backup's existence.
     - record in the P13 ledger: the original's path, size, mtime and sha256 **before and after**,
       for the main file, its `-wal` and its `-shm`. **Any change is recorded, not judged**
       (revision 4, A3): the owner's live daemon may write or checkpoint meanwhile. The safety proof
       is that our only connection was `mode=ro`, not the sha. Also record the backup's path, size,
       sha256, integrity result and schema version
  4. Never modify, move, checkpoint or open-for-write the original, its `-wal` or its `-shm`.
     Never stop the owner's daemon.
- **Merges** (`--no-ff`, into `fix/qa6-rulings` in the main checkout, in this order): P2, P3, P5
  (contains P4), P6, P7, P10 (contains P8), P12 (contains P9, P11). **Conflicts expected: none in
  `src/`.**
  - The declared test-file overlaps, each with disjoint hunks, **hand-resolvable** by keeping both
    hunks and recording it (revision 4, A5):
    - `tests/qa6/sub/test_wave2_1_cli_status.py`: P4 `:103` vs P10's appended C3
    - `tests/qa6/sub/test_wave1_boot.py`: P4 `:127` (W1, plus the `EXPECTED_SCHEMA_VERSION` import)
      vs P10 `:46` (`W4_STOP_LINE`)
    - `tests/qa6/live/test_wave8_1_live.py`: P3 `:895-930` (L1's `before` marks and clause) vs P7
      `:1237` (L8)
    - `tests/cli/test_commands.py`, only if P10's ledger says it touched that file
  - Any other conflict stops the phase and goes to the router with the file list.
- **Checks** (main checkout, `cd /Users/noamsalit/Git/Shepherd && …`):
  1. `find src tests -name __pycache__ -type d -prune -exec rm -rf {} +` (a clean import state before
     the full lane; it removes only bytecode caches inside the repo)
  2. `.venv/bin/pytest -p no:randomly --ignore=tests/qa5` → exactly `QR_BASELINE_DEFAULT_FAILS` (plus
     the s7 flaky test, if it fires, confirmed alone)
  3. `.venv/bin/pytest -p no:randomly tests/boundaries` → exactly `QR_BASELINE_BOUNDARY_FAILS`
  4. `.venv/bin/mypy --strict src` → the 2 baseline errors
  5. `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js` → 0 failures
  6. The frozen-id check the baseline cannot run (its test ERRORs on qa5 collection): a quoted-heredoc
     python that runs `pytest --collect-only -q -p no:randomly --ignore=tests/qa5`, parses the node
     ids, and asserts `test_collected_node_ids.subset_violations(baseline_node_ids(), live,
     RETIRED_NODE_IDS) == []`, the P16 precedent
  7. `git diff --stat 4209fc7 -- src/shepherd/cli` lists only `main.py` and `commands.py`
  8. The new integration test, alone and inside the full lane of check 2
  9. The host-safety reads, before step 0 and after check 8, compared **semantically** with
     `QR_HOST_BEFORE` (P0), as the Agreement constraint defines
  10. Step 0's ledger entry is present (the backup recorded, or its absence)
- **Dependencies:** P2–P12.
- **Out-of-scope drift:** product edits (a failing check goes back to its phase as a remediation);
  rewriting `baseline`/`rebase`.
- **Exit criteria:** step 0 done and recorded; all ten checks as stated; the README ledger complete.
- **test_seams:** the boundary seam and the whole default lane; the L4 composition seam
  (`compose_tool_surface` + `wiring.sweep()`) for the P4 × P6 integration test.
- **Checkpoint:** none (AFK). **Validation:** deterministic. **Durability:** stable.
- **Consumes:** every phase ledger's lists; `StopReason.REFUSED`, `WAKE_EXCLUDED_REASONS` (P4);
  `LevelThreeWaker` with `tick() -> bool`, `compose.sweep_and_wake(sweep: Callable[[],
  MailboxCounts], tick: Callable[[], bool]) -> Callable[[], MailboxCounts]` (P6).
  **Produces:** the integrated `fix/qa6-rulings` tree.

### P14 — SD-09: DEFERRED by the owner (2026-09-27), not in this build

- The owner deferred SD-09 ("Let's defer this for now"). The phase id is kept so the numbering in
  ledgers and branches does not shift. **No builder is dispatched for P14.**
- The whole of what it would have held lives in
  `docs/backlog/2026-09-27-sd09-session-tool-channel.md`:
  - OD-1 and its options A, B and C
  - the K22 per-caller scope property with its negative control
  - G-M4-16's audience fixes
  - D80, reserved
  - the re-verification of waves 1, 4, 5 and 8
- This build's ruling-22 deliverable is P1's README line only. O12 stays FAIL.
- **Consumes:** none. **Produces:** none. **Checkpoint:** none (not built).

### P15 — qa6 verification against the comparison set

- **Objective:** prove every ruling end to end, with 0 PASS→FAIL.
- **Dependencies:** P13. (P14 is deferred, so there is no second run. O12 is expected FAIL and the
  README says "not yet".)
- **Where:** the **main checkout**, on `fix/qa6-rulings` (the editable install, so that qa6 children
  run this tree).
- **Steps:**
  1. Host safety before the run, each read-only, recorded. None contacts a tmux server
     (revision 1's `tmux -L shepherd ls` is gone because it connects to that server):
     - `shasum -a 256 ~/.claude/settings.json` (expect `f99112b6…`)
     - `readlink ~/.local/bin/claude`
     - `ls -la /private/tmp/tmux-$(id -u)/` (the socket files, listed and never connected to)
     - `lsof -nP -iTCP:8787 -sTCP:LISTEN` (recorded, never touched)
     - `git -C /Users/noamsalit/Git/Shepherd branch --show-current` is `fix/qa6-rulings`
  2. `cd /Users/noamsalit/Git/Shepherd && .venv/bin/python tests/qa6/run.py`: the full run. Wave 8
     needs wave 1 in the same run, and the full run has both.
  3. Compare with a quoted-heredoc script in the scratchpad (not the repo). For each scenario, the
     baseline verdict is the 09-27 rerun's when the scenario ran there (`qa6-20260927T061932Z.json`
     for wave 6, `qa6-20260927T062958Z.json` for waves 1 and 8), else `qa6-20260924T124009Z.json`'s.
     All three are `.json` run records under `.cc10x/qa/wf-20260923T182839Z-9adb11fc/runs/`. A rerun
     record that is BLOCKED with **no clauses** means "not run".
     - Report: FAIL→PASS, PASS→FAIL, **PASS→BLOCKED** (revision 3, F8), clause-level PASS→FAIL, and
       **every clause that was PASS in the baseline and is absent from the new run** without being on
       the declared rename list (F8). The P1–P12 ledgers' renamed and changed clauses are excluded.
     - The declared changed-clause list, at least:
       - P1: D12, U7, U8, M9, O8, L4, U2
       - P2: H4, H5
       - P3: U26 (`ui.turn_ended_reaches_the_status_area`, `ui.no_turn_ended_line_in_the_thread`),
         U27/U28 (`ui.one_inline_card_with_the_outcome`), **L1 `ui.assistant_grows_in_two_updates`
         (re-valued ≥ 3 → ≥ 2)**
       - P4: O4, C2 (`logs.database_schema_4` → `logs.database_schema_current`), W1, C10
       - P5: M14
       - P7: L8
       - P10: C3 (moved), **W4 `logs.stop_line`, D10 `logs.first_stop_line`, M19
         `logs.stop_line` (re-valued `3 threads exited` → `4 threads exited`)**
     - Check the expected outcome table above scenario by scenario.
  4. Host safety after the run: the same reads, compared **semantically** with step 1 and P0's
     `QR_HOST_BEFORE` (revision 3, F6):
     - the settings sha is equal
     - the `~/.local/bin/claude` target is equal
     - the tmux socket-name **set** has nothing missing (a missing name stops P15). A new
       `default` or `shepherd` socket is owner activity, because we never create those names:
       record it and continue, never connect to it (revision 4, A4). A throwaway name this run
       created is named in the ledger
     - the 8787 listener is the same pre-existing pid, and nothing we started listens there

     No `/private/tmp/shq6-*` is left.
- **Files:** new `docs/plans/qa6-rulings-blockers/P15-verification.md` (runs, the tables, host
  safety, every remaining non-PASS with its cause).
- **Exit criteria:**
  - 0 PASS→FAIL and 0 PASS→BLOCKED (scenario and clause level), and no undeclared vanished PASS
    clause (the declared oracle changes excepted)
  - every ruling's scenario PASS, or BLOCKED only on the pre-existing blocks named above
  - host safety unchanged
- **Stop-if:** any PASS→FAIL, any PASS→BLOCKED, or any undeclared vanished PASS clause (F8) stops
  verification and goes to the router, which names the phase that owns the file. A PASS→BLOCKED is
  first re-run once under the probabilistic policy below. If it is still BLOCKED, it stops.
- **test_seams:** the qa6 e2e seam (the whole harness).
- **Checkpoint:** none (AFK), with the stop-if above. **Validation:** probabilistic (live lane,
  host timing). Policy: a scenario that is BLOCKED(model/timing) is re-run once, alone, with
  `--wave <n>` (plus wave 1 for wave 8), and the re-run is recorded. It never counts as PASS unless
  its clauses pass. **Durability:** session-only.
- **Consumes:** the integrated tree. **Produces:** `P15-verification.md`.

---

## Critical-path material

### Behaviour contract

- **C-QR-1 (RPC):** every request that reaches `invoke` has audience HUMAN and `caller_id "cli"`. A
  request that fails to decode reaches nothing and writes no audit row. The socket is 0600 in a 0700
  dir, and its path is no longer than the control socket's.
- **C-QR-2 (claim):** while a daemon runs, no other process can claim its socket path. A process that
  exits, cleanly or not, frees its claim. A claim in the owning process is re-entrant **for the
  lock only**: the connect-probe runs on every claim, so an in-process second claim of a path with
  a live listener is refused, and the owner is unharmed. A claim that took the lock and was then
  refused by the probe holds nothing afterwards. A claim succeeds on a first start whose runtime dir
  does not exist yet, and leaves that dir at the plan's mode. `tests/engines/test_socket_live_owner.py`
  `:120-121`, `:148-149` and `:161-176` stay green unchanged.
- **C-QR-3 (start order):** a start refused for the port writes no database. The registry is frozen
  before the first request is served.
- **C-QR-4 (refused start):** `runner.start` refused → exactly one row, ended `refused`, with no live
  state and no handle.
- **C-QR-5 (wake):** at level 3, one eligible drained stop set → at most one unprompted turn. It is
  never opened while the slot is held, never at level 2, never for a lineage at the cap, and **never
  for a `refused` row** (at any level, D73). The cap anomaly is counted once per session.
- **C-QR-6 (keystrokes):** bytes reach `runner.write` only on a connection that passed the origin
  check, the handshake and `invoke("terminal_stream")`. The keystrokes add no audit row.
- **C-QR-7 (backup):** the backup's bytes are the first pre-install image for the file's whole
  lifetime.
- **C-QR-8 (sends):** a pane-less target gets no `mailbox_message` row.
- **C-QR-9 (retry):** a declared lineage admits two master attempts. The third is refused with
  `retry_cap_reached` and one anomaly bump. A second retry of one attempt is refused, with no bump.
  Both refusals happen in `admit()` or before it, so neither writes a row.
- **C-QR-11 (the event line):** `turn_ended` and non-stopping `rate_limit` text is shown in
  `#shepherd-event` (a polite live region beside `#shepherd-status`) and nowhere else. No event
  writes `#shepherd-status`, whose writers are exactly the six it has today (revision 4, B1).
- **C-QR-10 (migration 005):** on a v4 database, 005 keeps every `session` row and cell and every
  `mailbox_message` row and cell, keeps both tables' indexes, leaves FKs enforced and
  `foreign_key_check` empty, leaves no stash table, and admits `refused` while still refusing a bogus
  reason. The whole 001 → 005 chain still applies in one transaction.

### Edge-case catalogue

| Edge case | Where it is proved |
|---|---|
| E-QR-1: an RPC request larger than 1 MiB, or a client that never shuts its write side (1 s idle) | `test_rpc_wire`, `test_control_rpc` |
| E-QR-2: a peer that connects and closes (a probe) harms nothing | `test_control_rpc` |
| E-QR-3: the RPC socket path is over budget → `controld` refuses before any write; the CLI treats it as "no daemon" | `test_cli_rpc`, `test_controld_start_order` |
| E-QR-4: a stale `rpc.sock` or `controld.sock` with no lock holder → unlinked. With a holder → refused | `test_socket_lifetime_lock` |
| E-QR-5: a newer schema after the bind → the port is released | `test_controld_start_order` |
| E-QR-6: a refused `ensure_server` and a refused `start` both end the row | `test_spawn_refused_row` |
| E-QR-7: a wake whose set was drained by a user turn in between → no turn | `test_master_turn_wake` |
| E-QR-8: a turn that fails to open during a wake → `master_failed` +1, the slot freed | `test_master_failed` |
| E-QR-9: a WS frame split across reads, or a close mid-frame | `test_ws_input_pump` |
| E-QR-10: a pane that dies while typing → the reader ends | `test_terminal_input_server` |
| E-QR-11: a double click on a choice → one POST. A trust dialog → no button | `test_decision_live` |
| E-QR-12: an existing user `.shepherd-backup` before any install → kept | `test_hooks_backup_first_image` |
| E-QR-13: the ending arrives during the kill vs before it | `test_lifecycle` |
| E-QR-14: a `retry_of` naming an attached session, or a human retry → linked, not capped | `test_spawn_retry_of` |
| E-QR-15: 005 over a DB with mailbox rows (delivered and pending) and parent/retry self-references | `test_migration_005` (plus the 002-pattern negative control) |
| E-QR-16: the first `controld` start on a host with no runtime dir → the claim creates it | `test_socket_lifetime_lock`, `test_controld_start_order` |
| E-QR-17: a refused master spawn at level 3 → no wake, however many sweeps | `test_wake_reads` (P4), `test_refused_start_wakes_nothing` (P13) |
| E-QR-18: M14's wake turn competes with its own retry script | P5's scripted-wake step (qa6, P15) |
| E-QR-19: `--since` with a real-looking impossible date (`2026-02-30`) | `test_cli_rpc` |
| E-QR-20: a previous turn's `turn_ended` arriving after the next send wrote its turn id | `test_turn_ended_is_shown_in_the_event_line_and_the_status_keeps_the_turn_id`; live `ui_send` (P15) |
| E-QR-21: an in-process second claim of a live path (re-entrant lock, live probe) | `test_a_reentrant_claim_still_probes_and_refuses_a_live_listener`; `test_socket_live_owner.py` |
| E-QR-22: an older binary's lockless live listener | `test_a_claim_refused_by_the_probe_does_not_keep_the_lock_it_took` |
| E-QR-23: the owner's real database is open (WAL) when P13 backs it up | P13 step 0 (online backup, read-only source; manual checklist in the ledger) |

### Provable properties

- **PP1:** claim exclusivity across descriptors (`test_a_second_descriptor_cannot_take_a_held_claim`).
- **PP2:** a busy port leaves no `shepherd.db` (`test_an_occupied_port_writes_no_database`).
- **PP3:** the registry is frozen before it is served (`test_the_registry_is_frozen_before_the_server_serves`).
- **PP4:** RPC audience is always HUMAN, and a malformed request invokes nothing (`test_rpc_wire`).
- **PP5:** RPC socket mode 0600 (`test_the_socket_is_0600_in_a_0700_dir`).
- **PP6:** the backup equals the first image over N installs and uninstalls
  (`test_hooks_backup_first_image`).
- **PP7:** a refused start = one ended `refused` row (`test_a_refused_start_ends_the_row_refused_and_not_live`).
- **PP8:** migration 005 preserves every row and column of `session` **and `mailbox_message`**, and
  every foreign key resolves and stays enforced (`test_migration_005`).
- **PP9:** at most one unprompted turn per drained set, and never while the slot is held
  (`test_master_turn_wake`).
- **PP10:** `master_failed` is bumped exactly once per failed turn (`test_master_failed`).
- **PP11:** keystrokes produce no audit row, and the open does (`test_typing_writes_no_audit_row_but_the_open_does`).
- **PP12:** one POST per choice click (`test_a_double_click_posts_once`).
- **PP13:** a pane-less send leaves no row (`test_send_to_a_row_with_no_pane_is_refused_with_no_row`).
- **PP14:** the declared lineage cap (`test_the_attempt_that_exceeds_two_is_refused_and_counted_once`).
- **PP15:** `len(RPC_SOCKET_NAME) <= len(CONTROL_SOCKET_NAME)` (`test_the_rpc_socket_name_fits_the_control_sockets_budget`).
- **PP16:** the stash is load-bearing. 002's rebuild alone is refused on a DB with mailbox rows
  (`test_the_002_rebuild_alone_fails_on_a_database_with_mailbox_rows`).
- **PP17:** a `refused` row is never a wake candidate, and at level 3 it opens no turn
  (`test_a_refused_start_is_not_a_wake_candidate`,
  `test_a_refused_master_spawn_at_level_3_opens_no_wake_turn`).
- **PP18:** a claim creates a missing socket dir at `dir_mode`
  (`test_a_claim_with_the_runtime_dir_absent_creates_it_at_the_plans_mode`).
- **PP19:** events never touch `#shepherd-status`, and they are visible in `#shepherd-event`
  (`test_turn_ended_is_shown_in_the_event_line_and_the_status_keeps_the_turn_id`,
  `test_an_event_never_touches_the_status_after_an_approval_or_a_refusal`).
- **PP20:** re-entrancy skips only the lock and never the probe; a probe-refused claim keeps no
  lock (`test_a_reentrant_claim_still_probes_and_refuses_a_live_listener`,
  `test_a_claim_refused_by_the_probe_does_not_keep_the_lock_it_took`).

### Purity-boundary map

- **Pure** (tested with no process, no socket, no clock):
  - `rpc.answer_request`'s decode, validate and encode; `invoke` is injected via the registry fixture
  - `ws.pump_input` over callables
  - `LevelThreeWaker`'s gate (`store` fake-free: a real in-memory `Store` in `tmp_path`)
  - `refused_verdict`
  - `chat.js` pairing helpers (via the browser seam)
  - the `session.js` answer table
- **Effectful shell:**
  - `daemons/control_rpc.py` (accept loop)
  - `ingest_socket.claim_socket` / `release_claim` (the `flock` fd)
  - `controld.start` (bind, store, threads)
  - `server._terminal`'s reader thread
  - `runner.write`
  - migration 005 (sqlite; its TEMP stash table)

### Verification strategy

1. Per phase: RED → GREEN at the phase's seam; the full module suites named; boundaries; mypy.
2. P13: the whole default lane at the baseline reds, boundaries at the baseline reds, the frozen-id
   subset check, and the manifest equality.
3. P15: the full qa6 run against the comparison set, 0 PASS→FAIL, and the expected-outcome table.
4. Host safety at P0, P13 and P15, with the reads recorded. None of them contacts a tmux server.

## Functionality flows → tests

```
Flow: shepherd status against a running controld (ruling 1)
1. parse argv → test_a_valid_since_date_is_forwarded / test_an_impossible_since_date_is_a_usage_error
2. resolve rpc path → test_status_reads_the_daemons_fleet_through_the_socket
3. send request / invoke as HUMAN → test_a_request_is_invoked_as_human_whatever_it_says
4. audit → test_a_human_rpc_call_is_audited_like_the_web_ui
Error paths:
- no daemon → test_the_cli_falls_back_to_local_reads_with_no_daemon
- malformed request → test_a_malformed_request_invokes_nothing
- peer hangs up → test_a_peer_that_hangs_up_early_harms_nothing

Flow: level-3 wake (ruling 5)
1. master-spawned session stops unfinished → test_level_3_opens_an_unprompted_turn_with_the_summary_alone
2. slot busy → test_a_wake_while_a_turn_runs_opens_after_that_turn_ends
Error paths:
- lineage at the cap → test_a_wake_for_a_lineage_at_the_cap_opens_no_turn_and_counts_once_across_many_ticks
- runtime fails to open → test_a_turn_that_fails_to_open_counts_master_failed_once

Flow: typing in the terminal (ruling 18)
1. open socket (audited) → test_typing_writes_no_audit_row_but_the_open_does
2. keystroke → frame → pane → test_a_typed_frame_reaches_runner_write
Error paths:
- bad origin → test_a_bad_origin_gets_no_reader
- pane dies → test_a_closed_pane_ends_the_reader_thread
- oversize frame → test_an_oversize_frame_ends_the_pump_with_1009

Flow: spawn refused by the runner (ruling 9)
1. row created → 2. start refused → test_a_refused_start_ends_the_row_refused_and_not_live
3. the ended row is not woken → test_a_refused_start_is_not_a_wake_candidate /
   test_a_refused_master_spawn_at_level_3_opens_no_wake_turn
Error path:
- server refused → test_an_ensure_server_refusal_ends_the_row_refused

Flow: the owner's database meets the new binary (ruling 9, migration 005)
1. v4 DB with sessions and mailbox rows → migrate() → test_every_session_row_and_column_survives_005
2. mailbox rows kept and referenced → test_every_mailbox_row_survives_005_and_still_references_its_session
3. refused writable → test_refused_is_accepted_and_a_bogus_reason_is_still_rejected
Error paths:
- the 002 pattern alone → test_the_002_rebuild_alone_fails_on_a_database_with_mailbox_rows
- an older binary on the v5 DB → test_a_v5_database_refuses_a_v4_binary_by_rule_2
```

## Risk-based testing matrix

| Risk | P | I | Test required |
|---|---|---|---|
| Migration 005 breaks foreign keys or loses a column or a mailbox row on a real DB | med (was high before the rehearsal) | high | `test_migration_005` on a DB seeded with sessions and mailbox rows, plus the PP16 negative control (deterministic) |
| A refused master spawn loops through level-3 wakes | high (without D73's exclusion) | high | `test_a_refused_start_is_not_a_wake_candidate`; `test_a_refused_master_spawn_at_level_3_opens_no_wake_turn` (deterministic) |
| M14's wake turn steals its retry script (qa6 flake or false FAIL) | high (after P6) | med | P5's scripted-wake step; P15 records the clause |
| A required kwarg breaks a default-lane caller outside the phase's own tests | high | med | Every caller listed in P5 and P6; the `grep` exit criterion; the default lane at P13 |
| First start on a fresh host fails because the lock dir is absent | med | high | `test_a_claim_with_the_runtime_dir_absent_creates_it_at_the_plans_mode`; `test_a_first_start_with_no_runtime_dir_claims_and_binds` |
| A schema-version pin missed, going red at P13 | med | low | P4's full `tests/store` and `tests/cli` checks; the P4 pin list |
| A frozen id renamed without a retirement entry | med | med | The 5a grep rule; P13 check 6 (the subset check) |
| The fourth thread silently breaks the shutdown-line oracles (W4, D10, M19) and two frozen default-lane tests | high (certain without the declaration) | med | P10's declared value changes; P15's changed-clause list |
| A late status event erases the turn id or approval word (U25, U27/U28, U46, L2, live `ui_send`) | low (events have their own element) | high | PP19's tests (deterministic, browser); `test_settings_live.py:312`; P15 |
| Ruling 3's events end up invisible | low (revision 4 gives them a visible line) | med | `test_turn_ended_is_shown_in_the_event_line_…`; U26 |
| A page hosting `chat.js` lacks `#shepherd-event` and `slot()` throws | med | high | `test_the_event_line_is_polite_live_region_beside_the_status` (both pages); every `tests/web` page test |
| L1's per-frame count goes false after rulings 2–4 | high | med | L1 re-valued in P3 from a pre-send mark; P15 list |
| A re-entrant claim skips the probe and an in-process second bind steals a live socket | med | high | PP20's tests; `test_socket_live_owner.py:161-176` unchanged |
| The owner's live DB is copied torn, or modified, by the P13 backup | low | high | Online backup from a `mode=ro` source; the original's before/after sha; integrity check of the copy |
| A PASS scenario turns BLOCKED or loses a clause unnoticed | med | high | P15 comparator (F8) with stop-if |
| RPC socket lets a request choose its audience | low | high | `test_a_request_is_invoked_as_human_whatever_it_says` |
| RPC name pushes C8 over its budget | med | high | PP15 test; P15 C8 PASS |
| `flock` in-process double claim deadlocks `bind_listener` | med | high | `test_a_second_claim_in_the_owning_process_is_reentrant` |
| Bind-first leaks the port when the store refuses | med | med | `test_a_newer_schema_closes_the_port_it_bound` |
| Unprompted wake loops (every 2 s) | med | high | `…counts_once_across_many_ticks`; `…drained_opens_nothing` |
| Keystrokes audited per byte (D40 broken), or typed into the wrong pane | low | high | `test_typing_writes_no_audit_row_but_the_open_does`; `test_a_typed_frame_reaches_runner_write` (session id asserted) |
| WS reader thread outlives the pane | med | med | `test_a_closed_pane_ends_the_reader_thread` (bounded join) |
| L8 / W1 / C10 / C2 regress from ruling-driven oracle drift | high | med | Oracles updated in P4/P7; P15 comparison |
| Cap lines (`controld` 140, `tools_m3` 450, `lifecycle` 250, `spawn` 300) blocked by a fix | high | low | Cap tests in each phase's checks (deterministic) |
| Parallel phases conflict at P13 | med | med | Disjoint file table; manifest/ids/import table held for P13 |
| Chat pairing drops a result with no call | low | med | `test_a_result_with_no_call_still_renders_as_its_own_step` |
| Decision click answers a trust dialog | low | high | `test_the_trust_dialog_choices_stay_inert_and_say_why` |
| qa6 run on a worktree tests the wrong tree | med | high | P15 runs only in the main checkout on `fix/qa6-rulings` (manual checklist: `git -C /Users/noamsalit/Git/Shepherd branch --show-current`) |
| A host-safety slip (settings, 8787, `shepherd` socket, `~/.local`) | low | high | The read-only reads at P0, P13 and P15, none contacting a tmux server; the qa6 runner's own guards |

## Durability horizon

- Stable: D68–D79, the RPC wire, the lock, the migration, retry and wake semantics, and the
  keystroke path.
- Near-term-refactor: the chat rendering (UI iteration expected) and the post-M4 import table (it
  grows with each post-milestone edit).
- Session-only: the P0/P15 ledgers and the comparison script.

## Plan completeness gate

1. Every phase names its tests (P0/P15 are measurement phases; their "test" is the command set).
2. Exact paths: yes (new files marked new).
3. Exit criteria: explicit per phase.
4. Dependencies by id: yes (the table plus each phase).
5. Scope drift is named in every phase.
6. Consumes/Produces are verbatim-checked below.
7. Validation level: stated per phase.
8. Risk matrix: complete; every high/high and high/med row maps to a deterministic test.
9. No TBD. P14 is a DEFERRED stub with no files.
10. Open decisions: none. OD-1 moved to the backlog doc with SD-09.

## Self-review — cross-phase contract drift

- P5 consumes `spawn.py` "as P4 left it" and `StopReason.REFUSED` (P4 produces both). ✓
- P10 consumes `claim_socket(plan: SocketPlan) -> SocketPlan` and `release_claim(path: Path) -> None`,
  which match P8's Produces verbatim. ✓
- P12 consumes "the P9 rule for a declared `server.py` edit", produced by P9. ✓ It consumes
  `session.js` as P11 left it (branch base). ✓
- P14 is deferred and consumes nothing. P10's Produces (`RPC_SOCKET_NAME`, `answer_request`,
  `call_remote`) have no later consumer in this build, and the backlog doc names them for SD-09. ✓
- P13 consumes `StopReason.REFUSED` and `WAKE_EXCLUDED_REASONS` (P4 Produces, verbatim) and
  `LevelThreeWaker` with `tick() -> bool` and `compose.sweep_and_wake(sweep: Callable[[],
  MailboxCounts], tick: Callable[[], bool]) -> Callable[[], MailboxCounts]` (P6 Produces,
  verbatim). ✓
- P5's M14 rewrite relies on P6's level-3 wake **behaviour** only at P15 (on the integrated tree).
  It names no P6 symbol. ✓
- P10 consumes `claim_socket(plan: SocketPlan) -> SocketPlan`, which P8 now also defines to create
  the socket dir. The signature is unchanged. ✓
- P6's `open_wake=driver.wake_turn` matches `TurnDriver.wake_turn() -> TurnStarted | None`. The
  waker's `open_wake: Callable[[], object]` accepts it. ✓
- P13 consumes ledger lists, which each phase is required to produce (working method 3). ✓
- Revision 3: P10's shutdown-line change consumes `ShutdownOutcome.__str__` as it is
  (`shutdown.py:69`, unchanged) and P10's own thread name `"rpc"` (P10 Produces). ✓ P3's
  `#shepherd-event` writer is P3-internal (revision 4 dropped `setStatus`/`showEvent`); no later
  phase consumes it. P12 edits `session.js`, not `chat.js` or `index.html`. ✓ P8's claim order is
  internal to `claim_socket(plan: SocketPlan) -> SocketPlan`, whose signature is unchanged, so P10's
  Consumes still match verbatim. ✓ P13's `…_at_four` reason update consumes P4's rename
  `test_future_schema_refuses_to_start_at_six`, spelled identically in P4 and P13. ✓ P4's
  `now: Callable[[], str]` is the existing parameter (`spawn.py:190`). ✓
- Self-review: no cross-phase reference drift.
