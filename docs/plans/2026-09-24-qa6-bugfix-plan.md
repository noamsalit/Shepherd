# QA round 6 — bug-fix plan (BC-01 … BC-37)

## Metadata

- Created: 2026-09-24
- Status: approved for build — revision 3

**Revision 3.** Fresh-review passes: 2/2 (cap reached). Pass 2 read revision 2 whole: 0 blocking, 4 advisory; revision 3 applies exactly those four (router amendment, see the Revision 3 change log). No other section changed.
- Plan mode: `execution_plan`
- Verification rigor: `critical_path` (liveness judgement, concurrent delivery into a live pane,
  stream resume, daemon start refusals; each is a state machine or a race)
- Workflow: `wf-20260924T044326Z-3a830e78` (BUILD, QA-seeded from `wf-20260923T182839Z-9adb11fc`)
- Source of truth for the defects: `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md` (§1, §3, §4, §8, §13)
- Base: branch `qa/round6-full` @ `be9db6f` (`git diff --stat main..HEAD -- src` is empty)
- Owner authorisation: "Report + fix: after the report, fix confirmed bugs on a local branch, with
  tests, no push."
- plan_revision: 3 · last_reviewed_revision: 2 · planning_review_status: reviewed_advisory_applied · fresh-review passes: 2/2 (`.cc10x/plan-reviews/qa6-bugfix-pass1.md`, `.cc10x/plan-reviews/qa6-bugfix-pass2.md`)

---

# Part 1 — Human layer (what and why)

## Agreement snapshot

- **Goal:** fix every QA-round-6 bug candidate that is a clear defect inside the spec's decisions, each
  with a test that fails first, on a local branch, and prove it end to end with a full `tests/qa6`
  run that shows the expected FAIL→PASS flips and no new FAIL.
- **Constraints:**
  - Spec §3 decisions (D1–D67, D38.1) are law; nothing is reversed quietly. Where a fix needs one
    re-decided, it is not planned here — it is listed under *Owner decisions*.
  - `cli/` is byte-frozen with its one re-base spent (HANDOFF "Two rough edges", consumer manifest):
    **no byte of `src/shepherd/cli/` changes.**
  - `daemons/controld.py` is at 140 of 140 (ADR-1 cap 150 minus the pinned `RESERVED_FOR_M2 = 10`,
    `tests/daemons/test_controld_composition.py`); every edit to it is **net zero lines** and the two
    constants stay unedited.
  - Pinned module caps (read from the tests, not guessed): `orchestration/mailbox.py` ≤ 250 (at 250),
    `orchestration/lifecycle.py` ≤ 250 (at 250), `toolsurface/tools_*.py` ≤ 450
    (`tools_m3.py` 445, `tools_terminal.py` 444, `tools_projects.py` 448), `tools_m1.py` pinned at 574,
    `tools_master.py` pinned at 505, every other module ≤ 600, every `daemons/*` ≤ 150.
  - `mypy --strict src` with `disallow_any_explicit` stays clean. No `Any`, no `shell=True`.
  - Import rules in `docs/specs/logical-architecture.md` / `tests/boundaries/` hold; `core/clock.py`
    is the only wall-clock reader (P22, `tests/boundaries/test_one_clock.py`).
  - `tests/boundaries/collected_node_ids.txt` is a subset floor: new tests may add node ids;
    **no existing test is renamed or deleted** (a rename needs a `RETIRED_NODE_IDS` entry — none is
    planned).
  - Every edit under `src/shepherd/web/` is declared in `tests/boundaries/consumer_manifest.json`
    (Phase 16), never by editing `baseline` or `rebase`.
  - Host safety: never touch `~/.claude/settings.json`, `~/.local`, the default tmux server, the tmux
    socket `shepherd`, or port 8787. Every tmux call in a test uses its own `-L` socket. No planted
    signal, kill or teardown verb in executable code (CLAUDE.md). Clear `__pycache__` before any
    mutation run.
  - Local branch only, no push.
- **In scope:** the 33 BCs with a FIX in the triage below (BC-06, BC-20 and BC-21 only in part, and
  BC-37 with its post-turn residual left to the owner), their regression tests, the manifest
  declarations, a ledger, and full verification.
- **Out of scope:** the 8 owner questions (below: 4 whole BCs — 05, 14, 15, 28 — and the owner halves of BC-06, 20, 21, 37), SD-01…SD-10, the plan-oracle errors, the
  harness issues HI-1…HI-7, `tests/qa5` collecting on macOS (noted, not fixed), INC-1 (`claude` not
  on `PATH` — the fix lives in `~/.local`, which this plan may not touch), T15-1 (tail-subscriber
  window), and any HANDOFF/README rewrite.
- **Open decisions of this plan:** none. The owner-decision items are *excluded work*, each with its
  exact question; they are not decisions this plan leaves open.

## Triage — every bug candidate

Legend: **FIX** = planned here · **OWNER** = excluded, needs the owner's ruling (question below) ·
**NOT-A-BUG** = with evidence. Root causes are from reading the code at `be9db6f`, not from the
report's suspicion; where the report's line differed, the line here is the one read.

| BC | Sev | Verdict | Root cause (file:line) | Phase |
|---|---|---|---|---|
| BC-01 | critical | FIX | `host/mac.py:286-302` runs `ps -o lstart=` with the process's own `TZ`, so the token is local time; the engine's sidecar `procStart` is the same format in **UTC** (report §13: `TZ=UTC ps -o lstart=` equals the sidecar). Compared verbatim at `mac.py:300`, `signals/discovery_loop.py:164-166` and `:318-321` | P1 |
| BC-02 | high | FIX | `orchestration/mailbox.py:158-206` reads pending (:169), writes (:203-204) and only then marks (:205) with no exclusion; the route (`toolsurface/tools_messaging.py:161`) and the 2 s sweep (`mailbox.py:233`, via `toolsurface/compose.py:356`) both reach it. The misreport: the re-decide after the clear (:187-188) overwrites `decision` with `SEND_NOW`, which is what :206 returns | P2 |
| BC-03 | high | FIX | `toolsurface/stream.py:54` `_SEQ = 0` and `reset_stream()` (:70-76, called at `compose.py:400`) restart `seq` at 0 in every process; `subscribe()` (:119) takes the client's cursor verbatim and `_drain_locked()` (:97-104) detects only a cursor *behind* the ring, never one *ahead* | P3 |
| BC-04 | high | FIX | `signals/discovery_loop.py:224-229` returns an empty delta whenever the stored `observed_at` ≥ the sidecar stamp; the idle split (`_state_for`, :295-298) depends on `now`, so an unchanged stamp never crosses 60 s | P4 |
| BC-05 | high | OWNER | The CLI reaches only its own process's tool surface; reaching a daemon needs a transport and an edit of byte-frozen `cli/` (C5's `--since` date validation is also in `cli/`) | — |
| BC-06 | medium | FIX (half) + OWNER (half) | `web/static/chat.js:357-360` passes `data.detail` (an object) to `shepherdStep`, whose body is `textOf(detail)` (:223) → `[object Object]`. **FIX:** the body. **OWNER:** one step vs two, how `turn_ended`/`rate_limit` are announced, the final answer twice — U26's own oracle asserts both `one_step_for_the_tool == 1` and `frames_render_in_order == [… step, step, prose:turn_ended]`, so no rendering passes it | P14 |
| BC-07 | medium | FIX | `master/projection.py:132-146` `result_ending()` never reads `ResultMessage.is_error`; `api_error` is not in `KNOWN_TERMINAL_REASONS` (:80-83) so it becomes `turn_ended/unknown` | P5 |
| BC-08 | medium | FIX | `orchestration/master_turn.py:196-209` drains the wake set (`_opening_text`, :262-264) **before** `build_master` can fail, and puts `{error!r}` in the reason (:207); `_run_turn` publishes `text=repr(error)` (:285-297) — the same S8 leak | P5 |
| BC-09 | medium | FIX | `runner/local.py:225-234` `_PipeStream.chunks()` ends only when `closed`, which only `close()` sets, which `web/server.py:322` calls only after `chunks()` ends; nothing observes pane death | P6 |
| BC-10 | medium | FIX (hypothesis, RED-first) | `capture-pane -e -p` ends lines with bare LF and `terminal.js:163-175` builds the emulator with `convertEol: false`, so the snapshot (frame 1, written verbatim at `terminal.js:199-203`) staircases and its trailing blank pane rows scroll the text out of a shorter emulator; the first live line lands mid-row. Server stays byte-for-byte (T19's `test_the_first_frame_is_the_snapshot_byte_for_byte`) | P15 |
| BC-11 | medium | FIX | `web/static/app.js:123-140` `loadFleet()` keeps the initial empty `view.fleet` when `read()` returns `null`; `flock.js` then renders the empty-fleet state and `registry: 0 sessions` (`flock.js:495`) | P11 |
| BC-12 | medium | FIX | No intent check on async replies: `settings.js:341-348` `choose()` (R2), `session.js` rename reply (R3), `projects.js` `loadDraftPaths()` (R4); `projects.js` list rebuild by `replaceChildren` (:296/:354) between pointer-down and click (R5) | P12 (R3), P13 (R2, R4, R5) |
| BC-13 | medium | FIX | `session.js:318-331` fills the header once from the opening read; `app.js:317-330` `onEnvelope → refreshAll → loadFleet` redraws cards only | P12 |
| BC-14 | medium | OWNER | D31 says level 3 "wakes the master immediately"; nothing opens an unprompted turn, and how it should is unsettled | — |
| BC-15 | medium | OWNER | `spawn_session` has no retry field and `Store.link_retry` (`store/db.py:493`) has no caller; *what makes a spawn a retry* is unsettled | — |
| BC-16 | medium | FIX | `engines/claude_code/ingest_socket.py:83-99` `bind_listener()` unlinks (:89) with no live-owner check; controld's bind happens in the ingest thread after `open_store` (`daemons/controld.py:74`, `daemons/control_ingest.py:47`). **And a live-owner probe is itself dangerous:** the owner's `serve_control_ingest` sends its hello (`control_ingest.py:56`) outside the `except (WireError, OSError)` guard (:57-63), so a peer that connects and closes raises out of the loop and the `finally` (:64-66) unlinks the owner's own socket | P9 |
| BC-17 | medium | FIX | `engines/claude_code/registry.py:190-191` calls `agents_json_fallback()` whenever `sessions/` is missing, and `discovery_pass` (`discovery_loop.py`, its `scan_registry` call after the `is_attached_interactive` branch at :403-413) calls it every 2 s — against its own docstring "once, never on a timer" | P4 |
| BC-18 | medium | FIX | `flock.js:273/292/373/471` and `projects.js:296/354` rebuild with `replaceChildren()`, destroying the focused node | P11 (Flock), P13 (Projects) |
| BC-37 | medium | FIX (never-turned rows) + OWNER (post-turn residual) | The kill path (`orchestration/lifecycle.py:131-135`) writes the verdict through `apply_stop_verdict`, which by stated contract does not touch `state` (`orchestration/ask.py:149-152`: "the fold carries the state column"), and nothing else sets it — so a killed owned row keeps `starting`. **Residual:** the verdict is written only when `row.ended_at is None`, but every turn end stamps `ended_at` (`signals/fold.py:63-64` via `rules.py:275-279` `_turn_stopped`; `stop_lane.py:113`), so a session that ever finished a turn keeps its last turn's verdict after a kill; `test_lifecycle.py:372-416` pins that guard | P7 |
| BC-19 | low | FIX | `index.html:30` `#mark` is a `<span>` with no tab stop (tabIndex −1); `app.css:2063` moves the closed drawer off-screen with `translate` only, so its buttons stay in the Tab order | P11 |
| BC-20 | low | FIX (unreadable file) + OWNER (backup, byte-reversible uninstall) | `engines/claude_code/hooks_config.py:98-103` `_load()` catches `FileNotFoundError`/`NotADirectoryError` only, so mode 000 raises `PermissionError` (also out of `inspect_hooks`, which discovery calls every pass). Backup semantics (:296-298) and uninstall re-serialisation are unsettled by the spec | P9 |
| BC-21 | low | FIX (C10) + OWNER (C7) | C10: `daemons/controld.py:120-127` `main()` does not catch `store.migrate.MigrationRefused`. C7: `open_store` (:74) runs before `create_server` (:77); moving it contradicts ADR-7 §4's written order | P9 |
| BC-22 | low | FIX | `toolsurface/registry.py:115,:432` writes `UNREPORTED_AUTONOMY_LEVEL`; `AuthzOutcome` (`toolsurface/types.py:242-249`) has no level although `approvals.py:351` reads `level()` — the one-field fix `docs/plans/m4-blockers/t6.md` §T6-3 already names | P8 |
| BC-23 | low | FIX | `web/routes.py:72-76` `QUERY_ARGS` has no `/api/audit` entry; and `resolve()` (:226-229) forwards query values as **strings**, which `invoke()`'s integer schema refuses — so declaring `limit` alone would 400 (sibling: `scrollback` on `/output`, same path) | P10 |
| BC-24 | low | FIX | `settings.js:342-345` returns silently on `null`; `projects.js` repo remove drops its refusal; the project save retries steps that already succeeded | P13 |
| BC-25 | low | FIX | `session.js:277-285` Escape repaints the `row.title` captured at render time; Enter has no in-flight guard. `chat.js:320-331` posts whitespace-only text and ignores `isComposing` | P12 (rename), P14 (composer) |
| BC-26 | low | FIX | `chat.js:365-371` (`approval.created`) and `:389-392` (`loadShepherd`) both append a card with no de-dup by `approval_id` | P14 |
| BC-27 | low | FIX | `registry.py:196-203` emits one `MALFORMED_PAYLOAD` per pass per bad file and `discovery_pass` bumps each (the `MALFORMED_PAYLOAD` counter bump right after its `scan_registry` call); the repo's own rule for a steady state is "stops counting" (`reconcile_sdk_cli`, :345-360) | P4 |
| BC-28 | low | OWNER | `orchestration/spawn.py:236-256` writes the row before `runner.start` by decision C-M3-7; whether a *refused* start deletes it (O4's oracle) or ends it with a verdict is unsettled | — |
| BC-29 | low | FIX | `toolsurface/tools_m3.py:229-252` `kill()` goes to `record_and_terminate` for a pane tmux no longer has: it writes `kill.<id>`, then `terminate` raises `RunnerRefusal` → generic 400. `ended_at` cannot be the discriminator — it is set on every live session that finished a turn (see BC-37) | P7 |
| BC-30 | low | FIX | `toolsurface/compose.py:209-219` `close_master()` calls `interrupt_master()` (which withdraws the master's own cards and discards the count) before the counted sweep | P3 |
| BC-31 | low | FIX | `toolsurface/tools_projects.py:163-190` and `store/projects.py` accept a whitespace-only name | P8 |
| BC-32 | low | FIX | `web/server.py:205-226` `_json_body()` does a blocking `rfile.read(length)` with no socket timeout | P10 |
| BC-33 | low | FIX | `web/sse.py:115-123` writes the keep-alive only after a subscription that delivered nothing, so after an event it waits a second full idle period (≈30 s) | P10 |
| BC-34 | low | FIX | `discovery_loop.py:200-206` `_state_event` payload has no `project_id`; `discovery_pass` (:437-443) rewrites only `session_id` | P4 |
| BC-35 | low | FIX | `web/static/sse.js:35` reports `reconnecting` on every `error`, including the terminal one where `EventSource` has closed (`readyState === CLOSED`) after a 403 | P15 |
| BC-36 | low | FIX (killed rows) | `session.js:347-367` opens a terminal socket for any owned row; the 404 comes from `terminal_stream` snapshotting a tmux session a kill removed. `ended_at` cannot be the discriminator (set after every turn on a live pane); the projection's `stop_reason === "killed"` (`tools_m1.py:110`) is the one field that means Shepherd removed the pane. Post-turn kills inherit BC-37's residual | P12 |

**NOT-A-BUG:** none. Every candidate was checked against its code and the documented decisions; the
two that looked like design (BC-17's "once", BC-27's per-pass count) are contradicted by the code's own
docstring and precedent respectively, and the design-shaped halves of BC-06/20/21/37 are split out as
owner items rather than dismissed.

## Codebase reality check — plan-vs-code gaps found while planning

Each row is a place where the report's suspicion, or the obvious fix, is contradicted by the code or
by a guard. The plan follows the right-hand column.

| Report / obvious fix | What the code actually says | Consequence in this plan |
|---|---|---|
| BC-02: "add a lock to `deliver_now`" | A lock only inside `deliver_now` still lets the sweep deliver the route's message between `queue_message` and the route's attempt (`tools_messaging.py:136-172`), and the route would then answer `delivered 0` | The lock is re-entrant and `send` holds it across queue **and** deliver (P2) |
| BC-02: assertion | `tests/orchestration/test_mailbox.py:575` pins `SEND_NOW` after a clear — the misreport itself | Changed and recorded (P2), node id kept |
| BC-02: room for the fix | `mailbox.py` is 250/250 (`test_mailbox.py:877`); moving `coalesce` out would drop it from `test_degradation.py`'s pinned `POPULATION` (`public_callables` keeps only names whose `__module__` is the module, :190-199) and break `core/mailbox.py`'s "types and constants only" charter | Stay in `mailbox.py`; reclaim lines by re-wrapping three multi-line `_defer(...)` calls, no prose removed (P2) |
| BC-23: "add `limit` to `QUERY_ARGS`" | `routes.resolve()` forwards query values as strings; the tool schema is `integer`, so `invoke()` would refuse it | Integer query args are converted in `resolve()` (P10); `scrollback` had the same latent defect |
| BC-16/BC-21: edits to `controld.py` | 140/140 with both guard constants pinned (`test_controld_composition.py`: "editing it is not a fix") | Net-zero-line edits only (P9); C7's reorder contradicts ADR-7 §4 and goes to the owner |
| BC-16: "probe the socket before binding" | The probe's connect-and-close crashes the owner's control-ingest loop (unguarded hello send, `control_ingest.py:56`) and its `finally` unlinks the socket; `host/base.py`'s charter is "the seven questions a platform answers, and nothing else" (:1) | Guard the hello send (P9 adds `daemons/control_ingest.py`); the probe lives beside `bind_listener` in `ingest_socket.py`, not in `host/base.py` |
| BC-29/BC-36: "refuse/hide when `ended_at` is set" | `ended_at` is stamped on every turn end of a live session (`fold.py:63-64`) and never cleared (`store/writes.py:86-103`) | BC-29 keys on the runner's pane listing; BC-36 on `stop_reason == killed`; both get live-post-turn regression tests (P7, P12) |
| Tests that compose then read the ring | `tests/toolsurface/test_compose.py:255` reads `subscribe(0)` after `compose_world`, which will now seed the ring at `seq_base` | Changed assertion declared in P3 (a leading `stream.gap`) |
| `QUERY_ARGS` size | `tests/web/test_routes_m3.py:290` pins `len(routes.QUERY_ARGS) == 3` | Changed assertion declared in P10 (3 → 4) |
| BC-10: "fix the server snapshot" | `web/server.py:282-285` and T19's `test_the_first_frame_is_the_snapshot_byte_for_byte` hold the server byte-exact | Fix is client-side, frame 1 only (P15) |
| BC-06: "one step per tool" | U26's `frames_render_in_order` expects two steps + `prose:turn_ended` in the same run | Only the `[object Object]` body is fixed; the rest is an owner item |
| BC-06: show the tool input | `chat.js` states raw arguments are not rendered (approval card, D25 reasoning) | Step body names argument keys only (P14) |
| BC-37: "set state in the verdict writer" | `ask.py:149-152` states the stop verb does not touch `state` and sets it through `apply_fold_delta` first; `lifecycle.py` is 250/250 | Follow that precedent in `lifecycle.py` (one `apply_fold_delta` after `terminate`), reclaiming the two lines by re-wrapping code, not prose (P7); the stop writer is unchanged |
| BC-31: "strip in the handler" | `tools_projects.py` is 448/450; `rename_project`'s handler already converts `StoreError` to a refusal | Store-level refusal + a two-line create check, landing exactly on 450 (P8) |
| BC-22: "pass the level into `invoke()`" | `docs/plans/m4-blockers/t6.md` §T6-3 already names the one-field fix on `AuthzOutcome` | That fix, nothing else (P8) |
| BC-28: "don't write the row" | C-M3-7 fixes row-before-process in `spawn.py`'s docstring | Owner item |
| Default lane | `pytest -p no:randomly` is interrupted by 3 qa5 collection errors on this Mac (measured while planning) | Baseline and verification also run `--ignore=tests/qa5` (P0, P17) |
| Web edits | Every `web/` file is digested in `consumer_manifest.json`; re-based paths may not appear in `post_milestone` | Declared once, in P16; lanes treat the two manifest tests as known-red |

## Owner decisions — excluded from this plan, with the exact question

| Item | Why it is not planned | The question |
|---|---|---|
| **BC-05** (C1–C5) | Needs a CLI↔daemon transport the spec does not settle, and a second, declared edit of byte-frozen `cli/` (its one re-base is spent) | "Which transport should `shepherd status/doctor/install-hooks/uninstall-hooks/replay/recompute` use to reach a running `controld`'s tool surface — HTTP on the loopback port, the control Unix socket, or another — and do you authorise a declared edit of `cli/` to wire it, including making `replay --since 2026-13-45` a usage error (exit 64)?" |
| **BC-06 (rendering half)** | U26's oracle contradicts itself (one step *and* two steps + `prose:turn_ended`); how non-text kinds are announced is a UI decision | "Should a tool call and its result render as **one** expandable step or two; should `turn_ended` and `rate_limit` appear in the thread as a line, in the status slot, or not at all; and should the SDK's final `result` text (identical to the last assistant text) be rendered?" |
| **BC-14** (M12) | D31 says level 3 wakes the master "immediately" but not how | "At level 3, when a master-spawned session stops `unfinished`/`error`, what does the unprompted turn send (the wake summary alone?), what happens when a turn is already running (queue, drop to next-turn drain, or retry), and does it count against D31's 2-per-lineage cap?" |
| **BC-15** (M14) | *What a retry is* is unsettled; M14 itself notes the schema has no retry field | "Is a master retry declared explicitly (a `retry_of` argument on `spawn_session`, taught in the master prompt) or inferred (same brief + cwd as a stopped master-spawned session)? The cap `link_retry` enforces depends on the answer." |
| **BC-20 (backup, byte-reversible uninstall)** (H4) | Spec (C6) says only "back up first"; both behaviours are defensible | "Should the `.shepherd-backup` keep the **first** pre-install image (never overwritten) or the latest, and should `uninstall-hooks` restore that pre-image byte-for-byte (losing edits made since install) or keep re-serialising with only our entries removed?" |
| **BC-21 (C7)** | ADR-7 §4 says the registry is frozen "before the server binds"; binding the port before `open_store` contradicts it, and `controld.py` has zero lines of headroom | "May ADR-7 §4 be re-worded to 'frozen before the server **serves**' so `controld` binds the port before opening the database (a busy port then writes nothing), or should a busy port be detected some other way?" |
| **BC-28** (O4) | C-M3-7 fixes row-before-process; O4 expects no row after a refused start | "When `runner.start` refuses, should the pre-written row be deleted (O4's oracle), or kept and ended with a verdict so the attempt stays visible (C-M3-7's intent)?" |
| **BC-37 residual** (no qa6 scenario asserts it — HI-2) | G-M3-9's guard reads `ended_at` as "a session ending arrived", but every turn end stamps it; `tests/orchestration/test_lifecycle.py:372-416` pins the guard as written | "When Shepherd kills an owned session that has already finished a turn, should the verdict be `killed` (so it buckets `stranded` and the page knows the pane is gone), and if so what marks 'a session end arrived during the kill' — the `ended_at` value changing across the kill, or the probe before it?" |

## Spec-vs-design questions and harness notes (listed only)

- **SD-01…SD-10** — owner rulings, unchanged by this plan: SD-01 DP8 stop-map departures (D12);
  SD-02 AA legend tint (U7); SD-03 week/month relative time (U8); SD-04 decided card kept inline
  (U27/U28); SD-05 terminal input unbuilt, T19-c (T3, U10); SD-06 inert decision choices, RD6 (U14);
  SD-07 attached-session message queued as `refuse_no_pty` (O9); SD-08 `from_fork_of` is the engine
  id (O10); SD-09 no session↔tool-surface channel, README capability 3 (O12); SD-10 `{"Stop": "x"}`
  warns rather than refuses (H5). For each: *"which document is right — the spec's oracle or the
  documented design decision the code cites?"*
- **Plan-oracle errors (harness notes, no product change):** M9 (HUMAN reads are `policy`, K23), O8
  (`list_mailbox` lists pending only), L4 (sweep sandboxed under `needs_real_home`), D12 ×2 clauses,
  L5 `stream.session_spawned_untrusted` (`trusted: None` is unknown, never `False`), R1 (no running
  count rendered).
- **New harness note from this planning pass:** U26's `ui.frames_render_in_order` and
  `ui.one_step_for_the_tool` cannot both pass; HI-4 makes U41's card clause racy — the new browser
  test in P11 is the proof for BC-18, not that clause; L7's `api.m3_queue` is BLOCKED on the macOS
  pane rule, so once BC-02 is fixed L7's verdict becomes **BLOCKED** (`tests/qa6/verdict.py:281-289`:
  BLOCKED when no clause failed and one is blocked), not PASS.
- **qa5** fails to collect on macOS (`tests/qa5/dom.py:27` imports `render_check`, which is not on
  the path) and interrupts the plain default lane; noted, not fixed.

## Expected qa6 outcome after all phases

- **34 scenarios FAIL→PASS:** A4, C9, C10, D2, D9, D13, E1, E5, T4, O6, M7, M16, M18, M19, P2, U2, U4,
  U11, U13, U17, U18, U24, U25, U30, U38, U39, U40, U41, U45, R2, R3, R4, R5, L11.
- **Clause-only flips (scenario stays FAIL/BLOCKED on a clause this plan does not own):**
  L5 `files.sidecar_procstart_is_product_token` · L7 `api.m2_clear_then_send_delivered` ·
  U8 `api.malformed_payload_rises_by_1` · U10 `ui.xterm_rows_show_the_marker` ·
  H5 `api.mode_000_refused` · U26 `ui.step_detail_not_object_object`.
- **Stay FAIL (owner / SD / oracle):** C1–C5, C7, H4, D12, T3, O4, O8, O9, O10, O12, M9, M12, M14,
  U7, U14, U27, U28, L4 (plus L5, U8, U10, H5, U26 above) = 27. **FAIL→BLOCKED:** L7 (its only
  non-PASS clause left is `api.m3_queue`, BLOCKED). **Stay BLOCKED:** R1, L6.
  Arithmetic: 62 FAIL = 34 → PASS + 27 stay FAIL + 1 → BLOCKED; BLOCKED 2 → 3 (R1, L6, L7).
  No flipping scenario carries a BLOCKED clause (checked against §3's clause tables), so none of the
  34 lands on BLOCKED instead of PASS.
- **No new FAIL:** every scenario PASS in baseline run 2 (`qa6-20260924T040750Z`) is PASS again, and
  no clause PASS in run 2 is FAIL in the post-fix run.
- Live lane (wave 8) caveat: if the real `claude` cannot be resolved on this host (INC-1), L5/L7/L11
  come back BLOCKED; their unit tests are then the proof and the run records it — it is not repaired
  here.

---

# Part 2 — Execution contract

## Context references (read before building)

- `CLAUDE.md` — tmux `-L` rule, inert-fixture rule, `__pycache__` rule.
- `HANDOFF.md` §State, §"Taking it to the Mac" — the `cli/` freeze and the 140-line root.
- `docs/specs/orchestrator-platform.md` §3 (decisions), §8, §9 (write policy, mailbox D12/D45),
  §12 (stream envelope, "seq is monotonic").
- `docs/specs/logical-architecture.md` — layer rules; L6 cap.
- `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` ADR-7 (threading, registry freeze).
- `docs/plans/m4-blockers/t6.md` §T6-3 — the autonomy-level one-field fix.
- `tests/boundaries/_imports.py`, `test_consumer_surface_frozen.py`, `test_collected_node_ids.py`,
  `tests/daemons/test_controld_composition.py`, `tests/toolsurface/test_tools_m3.py:365-430` — the
  caps and freezes this plan works under.
- `tests/contracts/test_hostplatform_contract.py:610-720` — `mac.py`'s annotation rule
  (`VERIFIED (docs/probes/<file>.md)` must name a capture that exists).
- `tests/web/test_settings_live.py` + `tests/web/fixtures/shell_harness.html` — the real-browser seam
  every UI regression test uses.
- `tests/qa6/BUILDING.md`, `tests/qa6/run.py` — how the end-to-end proof is run and recorded.
- The report's §3 clause tables and §13 repros for the scenario each phase flips.

## Working method (every phase)

1. Branch: Phase 0 creates `fix/qa6-bugfix` from `qa/round6-full` @ `be9db6f`. Parallel builders use
   one worktree per phase, `git worktree add .claude/worktrees/qa6-P<n> -b fix/qa6-P<n> fix/qa6-bugfix`;
   **except P12, which branches from `fix/qa6-P11` after P11's exit criteria are met**
   (`… -b fix/qa6-P12 fix/qa6-P11`), so the two `app.js` edits are sequential in history and never
   meet at the P16 merge. Worktrees are removed only with `git worktree remove` (never `rm -rf`).
   Commits stay local.
2. TDD: write the phase's new test file(s) first; run them; **record the RED output** (the failing
   assertion, not an import error, unless noted) in the phase ledger; then fix; then GREEN.
3. Ledger: each phase writes exactly one file, `docs/plans/qa6-bugfix-blockers/P<n>.md` — RED/GREEN
   evidence, every changed existing assertion with its reason, deviations, siblings left open.
4. Each phase's required checks: its new tests; the existing test modules named in the phase;
   `.venv/bin/pytest -p no:randomly tests/boundaries`; `.venv/bin/mypy --strict src`.
   **Known-red until Phase 16** (web phases P10–P15 only):
   `tests/boundaries/test_consumer_surface_frozen.py::test_completing_l4_changed_no_consumer_byte`
   and `::test_a_rebase_declares_every_path_whose_digest_moved`. No other red is acceptable.
5. Do not edit `tests/boundaries/consumer_manifest.json` or `tests/boundaries/test_collected_node_ids.py`
   in P1–P15 (both are Phase 16's).

## Parallelism and ordering

All of P1–P15 have **pairwise-disjoint file sets** (including test files) and may run in parallel,
with one exception: **P12 serialises after P11** (both edit `web/static/app.js`), and its branch is
cut from `fix/qa6-P11` once P11 exits, so P16 merges P12 (which contains P11) with no `app.js` meeting. Scheduling priority
when builders are scarce: P1 → P2 → P3 → P4 (critical, then the three highs), then P5–P10, then
P11–P15. P16 depends on P1–P15. P17 depends on P16.

| Phase | BCs | Files (src) | Parallel-safe with |
|---|---|---|---|
| P0 | baseline | none | — (first) |
| P1 | 01 | `host/mac.py`, new `docs/probes/2026-09-24-macos-procstart-utc.md` | all P2–P15 |
| P2 | 02 | `orchestration/mailbox.py`, `toolsurface/tools_messaging.py` | all |
| P3 | 03, 30 | `toolsurface/stream.py`, `core/clock.py`, `toolsurface/compose.py` | all |
| P4 | 04, 17, 27, 34 | `signals/discovery_loop.py`, `engines/claude_code/registry.py` | all |
| P5 | 07, 08 | `master/projection.py`, `orchestration/master_turn.py` | all |
| P6 | 09 | `runner/local.py` | all |
| P7 | 37, 29 | `orchestration/lifecycle.py`, `toolsurface/tools_m3.py` | all |
| P8 | 22, 31 | `toolsurface/types.py`, `toolsurface/approvals.py`, `toolsurface/registry.py`, `store/projects.py`, `toolsurface/tools_projects.py` | all |
| P9 | 16, 21-C10, 20-unreadable | `engines/claude_code/ingest_socket.py`, `daemons/control_ingest.py`, `daemons/controld.py`, `daemons/sessiond.py`, `engines/claude_code/hooks_config.py` | all |
| P10 | 23, 32, 33 | `web/routes.py`, `web/server.py`, `web/sse.py` | all |
| P11 | 11, 19, 18-Flock | `web/static/app.js`, `flock.js`, `index.html`, `app.css` | all except P12 |
| P12 | 13, 36, 25-rename, 12-R3 | `web/static/session.js`, `web/static/app.js` | all except P11 (branches from `fix/qa6-P11`, after it) |
| P13 | 12-R2/R4/R5, 18-Projects, 24 | `web/static/projects.js`, `web/static/settings.js` | all |
| P14 | 06-body, 25-composer, 26 | `web/static/chat.js` | all |
| P15 | 10, 35 | `web/static/terminal.js`, `web/static/sse.js` | all |
| P16 | integration | `tests/boundaries/consumer_manifest.json`, ledger README | — |
| P17 | verification | none | — |

## Phases

### P0 — Baseline, measured before any change

- **Objective:** a recorded baseline every later "no new failure" claim is compared against.
- **Inputs:** tree at `be9db6f`. **Files/surfaces:** new `docs/plans/qa6-bugfix-blockers/P0-baseline.md` only.
- **Dependencies:** none. **Allowed scope:** create branch `fix/qa6-bugfix`; run commands; write the ledger.
- **Out-of-scope drift:** fixing anything, including qa5's collection.
- **Steps / required checks:**
  1. `.venv/bin/pytest -p no:randomly` → record verbatim (expected: interrupted, 3 qa5 collection errors).
  2. `.venv/bin/pytest -p no:randomly --ignore=tests/qa5` → record passed/failed/error/skipped counts
     and the **full list of failing node ids** (the comparison set for P17).
  3. `.venv/bin/pytest -p no:randomly tests/boundaries` → counts and failing ids.
  4. `.venv/bin/mypy --strict src` → record.
  5. qa6 baseline is **not re-run**: record the path of run 2's records,
     `.cc10x/qa/wf-20260923T182839Z-9adb11fc/runs/qa6-20260924T040750Z/records/`, as the comparison set.
- **Expected artifacts:** `P0-baseline.md`. **Checkpoint:** none (AFK). **Validation:** deterministic (commands).
- **Exit criteria:** the four results and the failing-id lists are in the ledger.
- **test_seams:** none (measurement only).
- **Consumes:** none. **Produces:** `P0-baseline.md` failing-id sets (named `BASELINE_DEFAULT_FAILS`, `BASELINE_BOUNDARY_FAILS`).

### P1 — BC-01: macOS liveness token in UTC (critical)

- **Objective:** `MacHost.process_liveness` produces the same token the engine writes as `procStart`.
- **Files:** `src/shepherd/host/mac.py`; new `docs/probes/2026-09-24-macos-procstart-utc.md`;
  new `tests/contracts/test_machost_liveness_utc.py`.
- **Dependencies:** P0. **Allowed scope:** the env passed to the one `ps` call; one new constant and
  one pure helper; `process_liveness`'s docstring; the new capture file.
- **Out-of-scope drift:** `LinuxHost`, `discovery_loop.py`, a locale fix (`LC_ALL`), editing any
  existing file under `docs/probes/`.
- **Fix:**
  - `MAC_LIVENESS_TZ = "UTC"` with a `# VERIFIED (docs/probes/2026-09-24-macos-procstart-utc.md) — D55`
    annotation (the annotation rule requires an existing capture).
  - `def mac_liveness_env(environ: Mapping[str, str]) -> dict[str, str]` → `{**environ, "TZ": MAC_LIVENESS_TZ}`, pure, does not mutate its input.
    **Every** str/int literal in `mac.py` needs a marker on its own line
    (`test_hostplatform_contract.py:662-671,703-725`), so the line carrying the `"TZ"` key literal gets
    the same full `# VERIFIED (docs/probes/2026-09-24-macos-procstart-utc.md) — D55` citation.
  - `subprocess.run(..., env=mac_liveness_env(self.environ))` at the `ps` call.
  - The capture file: read-only commands run on this Mac and pasted verbatim — `ps -o lstart= -p <this shell's pid>`,
    `TZ=UTC ps -o lstart= -p <same pid>`, and the `procStart` field of one `~/.claude/sessions/<pid>.json`
    read through a copy in the scratchpad (never written in place), plus `date +%Z`. No other host file is read.
- **Regression tests (RED first):**
  - `test_mac_liveness_env_pins_utc` — pure: `TZ` is `UTC`, every other key survives, input unchanged.
  - `test_liveness_token_is_utc_whatever_the_process_tz` — `skipif(sys.platform != "darwin")`;
    `monkeypatch.setenv("TZ", "Asia/Jerusalem")` **without** `time.tzset()` — only the child `ps`'s
    environment matters, and `monkeypatch` restores the variable, so no tz state leaks into later
    tests; oracle = `ps -o lstart= -p <os.getpid()>`
    run with `TZ=UTC`; assert `MacHost().process_liveness(os.getpid(), oracle).alive is True` and
    `start_token == oracle`. RED today: token is local time → `alive False`.
- **Required checks:** new file; `tests/contracts/test_hostplatform_contract.py` (annotation rule);
  boundaries; mypy.
- **qa6 proof:** L5 `files.sidecar_procstart_is_product_token` FAIL→PASS and
  `files.procstart_offset_hours` 3.0→0.0 (L5 stays FAIL on its plan-oracle clause). D1–D11, D13 must
  stay PASS (the harness takes its tokens from `MacHost`, `tests/qa6/sandbox.py:185-194`).
- **Checkpoint:** none (AFK). **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** both tests GREEN on this Mac, the RED recorded, contract suite and mypy clean.
- **test_seams:** unit (`mac_liveness_env`); integration at the `HostPlatform` seam (real `ps`, this process's own pid).
- **Consumes:** none. **Produces:** `MAC_LIVENESS_TZ: str`, `mac_liveness_env(environ: Mapping[str, str]) -> dict[str, str]`.

### P2 — BC-02: one delivery at a time, and the decision that was taken

- **Objective:** a message is typed into a pane at most once, whichever trigger fires, and a cleared
  draft is reported as `clear_then_send`.
- **Files:** `src/shepherd/orchestration/mailbox.py`,
  `src/shepherd/toolsurface/tools_messaging.py`; new `tests/orchestration/test_mailbox_serialised.py`;
  edit one assertion in `tests/orchestration/test_mailbox.py` (line 575).
- **Dependencies:** P0. **Allowed scope:** as below. **Out-of-scope drift:** `rename.py`'s own typing
  path (a sibling race, recorded), the write-policy table, the store.
- **Fix:**
  1. `DELIVERY_LOCK = threading.RLock()` in `orchestration/mailbox.py`; the body of `deliver_now`
     runs under `with DELIVERY_LOCK:` (so the sweep's call is serialised too).
  2. `tools_messaging.send` wraps `queue_message(...)` **and** `deliver_now(...)` in one
     `with DELIVERY_LOCK:` — the sweep cannot deliver a message between the route queueing it and the
     route's own attempt (reentrant for the inner `deliver_now`).
  3. In `deliver_now`, remember `cleared = True` when the first decision is `CLEAR_THEN_SEND`; on the
     successful send return `Delivery(decision=WriteDecision.CLEAR_THEN_SEND if cleared else decision, …)`.
  4. Line budget (cap 250, `test_mailbox.py:877`; the fix adds ≈ 5 lines: `import threading`, the lock
     and its one-line comment, the `with`, the `cleared` flag). `coalesce` **stays** in this module —
     moving it would drop `("mailbox", "coalesce")` from `test_degradation.py`'s pinned `POPULATION`
     (`public_callables` filters on `__module__`, :190-199) and break `core/mailbox.py`'s
     types-and-constants charter (:5-6). Instead reclaim the lines by re-wrapping code only: the three
     multi-line `_defer(...)` calls (:175-180, :193-198, :228-230) onto one or two lines each
     (≈ 7 lines). No docstring or comment is shortened. `DELIVERY_LOCK` joins `__all__` on its
     existing line, so the degradation population gains no callable.
  5. Changed assertion: `test_mailbox.py:575` `SEND_NOW` → `CLEAR_THEN_SEND`, with one docstring
     sentence naming BC-02; node id unchanged; recorded in the ledger as a deliberate change.
- **Regression tests (RED first), in the new file:**
  - `test_concurrent_deliveries_type_the_message_once` — a gated runner double (wraps `ScriptedRunner`;
    its `pane()` blocks the first caller on a `threading.Event`); two threads call `deliver_now` for
    one session; assert exactly one body write plus one `b"\r"`, and the second `Delivery` is
    `delivered == 0`. RED: two body writes.
  - `test_send_holds_the_queue_until_its_own_attempt` — the gate sits in `attached_clients()` and **blocks only the first caller** (the sweep's own `deliver_now` also calls `attached_clients()`, `mailbox.py:174`, and must pass through ungated or the RED would be a timeout instead of `delivered == 1`); while
    `send` is inside it, a thread runs `sweep_pending`. **The one timing element in this phase, stated:**
    the test joins the sweep thread with a 2 s timeout while `send` is still gated. Before the fix the
    sweep finishes inside that window having delivered the message (RED: sweep `delivered == 1`);
    after the fix the join times out because the sweep is blocked on `DELIVERY_LOCK` (the thread is
    asserted still alive), the gate is released, both threads are joined with a 5 s timeout, and the
    sweep delivered 0 while `send`'s projection has `delivered == 1`. The blocked direction cannot be
    satisfied early, so a slow host cannot turn it green by accident.
  - `test_a_cleared_draft_is_reported_as_clear_then_send` — panes `[DRAFT, READY]`; `decision` is
    `CLEAR_THEN_SEND`, `delivered == 1`, and `project_delivery(...)["decision"] == "clear_then_send"`.
- **Required checks:** new file; `tests/orchestration/test_mailbox.py`, `test_degradation.py`,
  `tests/toolsurface/` modules that import `tools_messaging`; boundaries; mypy.
- **qa6 proof:** L7 `api.m2_clear_then_send_delivered` FAIL→PASS; `tmux.draft_not_in_input` shows no
  doubled line (it was intermittent — 3/6 — so the unit test is the deterministic proof). O-lane
  mailbox scenarios (O7, O8's passing clauses) stay PASS.
- **Checkpoint:** none (AFK). **Validation:** deterministic (Event-gated interleaving) plus one bounded
  timed join, described above. **Durability:** stable.
- **Exit criteria:** three tests GREEN, RED recorded, `mailbox.py` ≤ 250 lines with no prose removed,
  `test_degradation.py` unchanged and green, mypy clean.
- **test_seams:** unit at `deliver_now`/`sweep_pending` (orchestration seam, runner double); integration at `send` (L4 handler over a real `Store`).
- **Consumes:** none. **Produces:** `DELIVERY_LOCK` (`orchestration.mailbox`, a `threading.RLock`).

### P3 — BC-03 stream resume across a restart; BC-30 withdrawn-card count

- **Objective:** a client resuming with an id from an earlier process gets a `stream.gap` and the new
  events; controld's stop line counts every approval it withdrew.
- **Files:** `src/shepherd/toolsurface/stream.py`, `src/shepherd/core/clock.py`,
  `src/shepherd/toolsurface/compose.py`; new `tests/toolsurface/test_stream_restart.py`,
  new `tests/toolsurface/test_close_master_withdrawn_count.py`.
- **Dependencies:** P0. **Out-of-scope drift:** `web/sse.py`, `web/static/sse.js`, T15-1, an id format change.
- **ADR (inline) — how a restart is made visible to a resuming client.**
  *Context:* §12 "seq is monotonic … Last-Event-ID … gets the gap replayed"; restarts reset `seq` to 0.
  *Decision:* seed each process's sequence above every earlier process's (`seq_base = epoch_millis() * 1000`)
  so the existing *behind-the-ring* path sends `stream.gap` then the ring; and treat a cursor *ahead*
  of the head (clock regression) as `0`, which replays the ring with the gap the existing code emits.
  *Rejected:* an epoch prefix in `id:` (`<epoch>-<seq>`) — changes the wire format, `parse_last_event_id`
  and `sse.js`; a gap-only answer to an ahead cursor with no replay — loses the new events E5 asks for.
  *Consequences:* seq values are ~1.8e15 (below 2^53, safe in JSON and JS); tests that call
  `reset_stream()` keep base 0. *Reversibility:* reversible (one constant, one argument).
- **Fix:**
  - `core/clock.py`: `def epoch_millis() -> int` (the only wall-clock read, P22).
  - `toolsurface/stream.py`: `SEQ_BASE_PER_MS: int = 1000`; `def stream_seq_base() -> int` →
    `epoch_millis() * SEQ_BASE_PER_MS`; `reset_stream(seq_base: int = 0)` sets `_SEQ = seq_base`;
    in `subscribe`, `since_seq > _SEQ` → cursor `0`.
  - `compose.py:400`: `reset_stream(seq_base=stream_seq_base())`.
  - BC-30, `compose.py` `close_master`: withdraw first — `withdrawn = sum(withdraw_all(t) for every
    pending turn id)`; then `interrupt_master()`; `wait_for_turn(timeout_s)`; then add a second sweep
    for anything raised meanwhile; return the total. ADR-M4-3's withdraw-then-interrupt order holds.
- **Regression tests (RED first):**
  - `test_a_cursor_ahead_of_the_ring_gets_the_new_events` — `reset_stream()`, publish 3,
    `subscribe(since_seq=50)` (no timeout) yields those 3. RED today: `[]`.
  - `test_a_cursor_from_an_earlier_process_gets_a_gap_then_the_new_events` — publish 5, keep the last
    seq, `reset_stream(seq_base=last + 1000)`, publish 3, subscribe from the old last → `stream.gap`
    first, then 3.
  - `test_the_seq_base_moves_with_the_clock` — monkeypatched `epoch_millis`; base(t+1 ms) − base(t) == 1000.
  - `test_close_master_counts_the_masters_own_card` — compose over `tests/daemons/test_shutdown_master.py`'s
    fixtures with one pending master-turn approval; `close_master(...) == 1`. RED today: 0.
- **Changed existing assertion (declared, node id unchanged):** `tests/toolsurface/test_compose.py:255`
  reads `subscribe(0)` after `compose_world`; the composed ring now starts at `seq_base + 1`, so cursor
  0 is behind the ring and the existing gap path yields `stream.gap` first. The expected list becomes
  `["stream.gap", "session.registered", "session.updated"]`, with one docstring sentence naming BC-03.
  `test_compose.py:265/269` are unaffected (a ring emptied by compose yields nothing, not a gap).
  The web and SSE tests use the conftest's `reset_stream()` (base 0) and are unaffected.
- **Required checks:** new files; `tests/web/test_sse.py`, `tests/web/test_projects_stream.py`,
  `tests/toolsurface/test_stream.py`, `tests/toolsurface/test_compose.py`,
  `tests/daemons/test_shutdown_master.py`, `tests/daemons/test_controld.py`, `tests/test_core_clock.py`;
  boundaries (incl. `test_one_clock.py`); mypy.
- **qa6 proof:** E5 `stream.resumed_gets_three_or_gap`, U39 `ui.a_lists_it_within_10s`, M19
  `logs.stop_line` FAIL→PASS; E2–E4, E6 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** four tests GREEN, RED recorded, `compose.py` ≤ 600, mypy clean.
- **test_seams:** unit at the ring (`subscribe`/`reset_stream`); integration at `close_master` (composed plane).
- **Consumes:** none. **Produces:** `epoch_millis() -> int`, `SEQ_BASE_PER_MS: int`, `stream_seq_base() -> int`, `reset_stream(seq_base: int = 0) -> None`.

### P4 — BC-04 idle crossing, BC-17 one fallback fork, BC-27 steady-state count, BC-34 project_id

- **Objective:** discovery re-evaluates the idle threshold on an unchanged stamp, forks the agents
  fallback at most once per loop, counts one bad sidecar once, and stamps `project_id` on its frames.
- **Files:** `src/shepherd/signals/discovery_loop.py`, `src/shepherd/engines/claude_code/registry.py`;
  new `tests/signals/test_discovery_qa6.py`.
- **Dependencies:** P0. **Out-of-scope drift:** the hook lane; `liveness_sweep`'s frames' `project_id`
  (sibling, recorded); per-pass `unknown_registry_status` (sibling, recorded); `bind_cwd_to_repo`.
- **Fix:**
  - BC-04: `def _idle_crossed(entry: RegistryEntry, liveness: Liveness, prior: SessionSnapshot, observed_at: str, now: str) -> bool`
    — true only when the stamps are **equal**, `entry.status == IDLE_STATUS`, `liveness_verdict(...)`
    holds, `prior.state is SessionState.RUNNING`, and `now − observed_at ≥ IDLE_TO_NEEDS_YOU_S`.
    Checked before RD8's early return; when true, return the `NEEDS_YOU` delta
    (`needs_you_reason=IDLE_REASON`, `observed_at` unchanged) with its `session.state` event.
    A strictly newer prior still wins (RD8 unchanged); `test_equal_timestamps_tie_break_to_the_hook_path`
    (busy entry, `needs_you` prior) is untouched.
  - BC-17: `scan_registry(config_dir: Path, *, consult_agents_fallback: bool = True)` returns `([], ())`
    for a missing `sessions/` when the flag is false; `discovery_pass(..., consult_agents_fallback: bool = True, reported_problems: set[str] | None = None)`;
    `run_discovery_loop` passes `True` on its first pass and `False` after.
  - BC-27: with `reported_problems` given, bump `MALFORMED_PAYLOAD` only for a detail not already in
    the set, then replace the set's contents with this pass's details (a healed-then-broken file
    counts again). `run_discovery_loop` owns the set.
  - BC-34: `discovery_pass`'s `replace(event, …)` also sets `payload={**event.payload, "project_id": session.workspace_id}`.
- **Regression tests (RED first):**
  - `test_an_idle_session_crosses_to_needs_you_on_an_unchanged_stamp` — prior `RUNNING` with
    `observed_at == stamp`, `now = stamp + 61 s` → `NEEDS_YOU`, reason `IDLE_REASON`, one event. RED: empty delta.
  - `test_a_newer_hook_observation_still_wins_over_the_idle_crossing` — prior stamp +5 s → no delta.
  - `test_the_agents_fallback_is_consulted_once_per_loop` — `run_discovery_loop` over a config dir
    with no `sessions/`, `agents_json_fallback` monkeypatched to a counter, interval monkeypatched to
    0.01 s. Passes are counted through the loop's **`sweep`** callable, which runs once per pass
    (`discovery_loop.py:486-487`) — `on_result` never fires with no entries — and the counting sweep
    sets `shutdown` on its third call, so the loop stops itself with no sleep in the test → 1 fallback
    call. RED: 3.
  - `test_one_bad_sidecar_is_counted_once_while_it_persists` — three passes over one malformed file
    with one set → `malformed_payload == 1`; fix the file, break it again → 2. RED: 3.
  - `test_session_state_frames_carry_the_project_id` — a discovered session bound to a project → its
    event payload's `project_id` is the row's `workspace_id`; the envelope (`web/sse.envelope`) promotes it.
- **Required checks:** new file; `tests/signals/test_discovery_loop.py`, `tests/engines/` registry tests; boundaries; mypy.
- **qa6 proof:** D2 (4 clauses), D9 `files.forks_at_most_1`, D13 `stream.frames_carry_project_id`
  FAIL→PASS; U8 `api.malformed_payload_rises_by_1` clause FAIL→PASS (U8 stays FAIL on SD-03); D1, D3–D8,
  D10, D11 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** five tests GREEN, RED recorded, `discovery_loop.py` ≤ 600, mypy clean.
- **test_seams:** unit at `registry_delta` (pure); integration at `discovery_pass`/`run_discovery_loop` over a real `Store` and a throwaway config dir.
- **Consumes:** none. **Produces:** `scan_registry(config_dir: Path, *, consult_agents_fallback: bool = True)`, `discovery_pass(..., consult_agents_fallback: bool = True, reported_problems: set[str] | None = None)`.

### P5 — BC-07 a failed master turn is an error; BC-08 no lost summary, no internals

- **Files:** `src/shepherd/master/projection.py`, `src/shepherd/orchestration/master_turn.py`;
  new `tests/master/test_projection_is_error.py`, new `tests/orchestration/test_master_turn_failures.py`.
- **Dependencies:** P0. **Out-of-scope drift:** chat rendering (P14 / owner), new `AnomalyKind` members, `sdk_master.py`.
- **Fix:**
  - BC-07: `result_ending(subtype: str, terminal_reason: str | None, is_error: bool = False)`; when
    `is_error` is true the kind is `"error"` and the outcome `"error"`; an unrecognised
    `terminal_reason` is still counted (`unmapped` true). `project_events` passes `obj.is_error`.
  - BC-08: in `send_turn`, build the runtime **before** the drain (`turn.runtime = self._build_master(...)`,
    then `prompt = self._opening_text(text)`); the refusal reason becomes
    `OPEN_FAILED_REASON.format(turn_id=turn.turn_id)` with
    `OPEN_FAILED_REASON = "the turn {turn_id} could not be opened — the master runtime failed to start"`;
    `_run_turn`'s error event text becomes `TURN_FAILED_TEXT = "the turn failed inside Shepherd before it could finish"`.
    No `repr`, no exception class name reaches a caller (S8).
- **Regression tests (RED first):**
  - `test_an_is_error_result_is_an_error_ending` — `result_ending("success", "api_error", True) == ("error", "error", True)`. RED: `turn_ended`.
  - `test_a_clean_result_is_unchanged` — `("success", "completed", False)` → `("turn_ended", "success", False)`.
  - `test_a_turn_that_fails_to_open_keeps_the_wake_summary` — a waking stop planted (as
    `test_a_turn_opens_with_the_wake_summary` does), `build_master` raises; `peek()` still holds the
    item; the next turn's input starts with the wake line. RED: summary gone.
  - `test_no_failure_reason_carries_internals` — the refusal reason and the published error text
    contain neither `"RuntimeError"` nor `"("` + the exception's message.
- **Required checks:** new files; `tests/master/`, `tests/orchestration/test_master_turn.py`,
  `test_degradation.py`; boundaries (master isolation); mypy.
- **qa6 proof:** L11 `stream.master_error`, M18 `api.b_not_started_no_internals` and
  `files.c_summary_not_lost` FAIL→PASS; M1–M6, M10, M11, M13, M17 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, mypy clean.
- **test_seams:** unit at `result_ending`; integration at `TurnDriver` (real `Store`, recording master double).
- **Consumes:** none. **Produces:** `result_ending(subtype: str, terminal_reason: str | None, is_error: bool = False) -> tuple[MasterEventKind, str, bool]`, `OPEN_FAILED_REASON: str`, `TURN_FAILED_TEXT: str`.

### P6 — BC-09 a terminal stream ends when its pane dies

- **Files:** `src/shepherd/runner/local.py`; new `tests/runner/test_pipe_stream_pane_death.py`.
- **Dependencies:** P0. **Out-of-scope drift:** `web/server.py`, a WS read loop (T19-c), the Runner Protocol.
- **Fix:** `_PipeStream` gains `alive: Callable[[], bool]`; `STREAM_LIVENESS_S = 0.5`; when a read
  returns nothing, at most every `STREAM_LIVENESS_S` it asks `alive()`; if false, it reads once more
  (drains the tail) and returns. `attach()` passes `alive=lambda: self.probe(handle).alive`. `stop()`
  uses `_run` instead of `_checked`, so unpiping a pane tmux has already removed is not a raise in
  the WS handler's `finally`.
- **Regression tests (RED first):**
  - `test_chunks_end_after_the_pane_is_gone` — `LocalRunner` over a scripted `run_argv` whose
    `list-sessions` stops listing the session after the first poll; `chunks()` consumed in a thread;
    joined within 3 s; tail bytes written before death are yielded. RED: thread still alive.
  - `test_stopping_a_stream_whose_pane_is_gone_does_not_raise`.
- **Required checks:** new file; `tests/runner/`, `tests/contracts/test_runner_contract.py`,
  `tests/boundaries/test_tmux_blast_radius.py`; mypy.
- **qa6 proof:** T4 `stream.close_1000` FAIL→PASS; T1, T2 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic (scripted tmux, no real server). **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, `local.py` ≤ 600.
- **test_seams:** integration at `Runner.attach` over the injected command seam.
- **Consumes:** none. **Produces:** `STREAM_LIVENESS_S: float`, `_PipeStream(path, stop, alive)`.

### P7 — BC-37 a killed row is stopped; BC-29 killing a pane that is gone is refused

- **Files:** `src/shepherd/orchestration/lifecycle.py`, `src/shepherd/toolsurface/tools_m3.py`;
  new `tests/orchestration/test_kill_stops_the_row.py`, new `tests/toolsurface/test_kill_pane_gone.py`.
- **Dependencies:** P0. **Out-of-scope drift:** BC-28's row; the stop writer (`apply_stop_verdict`
  keeps its stated contract — it does not touch `state`, `ask.py:149-152`); G-M3-9's `ended_at` guard
  and its pinned test (`test_lifecycle.py:372-416` — the BC-37 residual is an owner item);
  `ordering.py` bucketing.
- **The discriminator, stated once:** `ended_at` does **not** mean the process is gone — every turn end
  stamps it on a live session (`signals/fold.py:63-64`, `rules.py:275-279`, `stop_lane.py:113`) and
  nothing clears it (`store/writes.py:86-103`). "The pane is gone" is read from the runner: the
  handle's session name is absent from `runner.list_owned_panes()` (the panes on the socket, never
  rows in a store — `runner/local.py:485-496`; `ScriptedRunner` answers from `owned_panes`).
- **Fix:**
  - BC-37, following `ask.py:_finish`'s precedent: in `record_and_terminate`, immediately after a
    `runner.terminate(handle)` that returned, `store.apply_fold_delta(session_id, FoldDelta(state=SessionState.STOPPED, last_event_at=recorded_at))`
    — unconditional, because the kill itself is the hard signal. `FoldDelta` is already imported;
    `SessionState` joins an import. The file is at its 250 cap, so the two lines are reclaimed by
    re-wrapping the `record` dict literal (:119-125) onto fewer lines — code only, no docstring or
    comment shortened. The verdict branch (`row.ended_at is None`) is left exactly as it is.
  - BC-29, `tools_m3.kill`: after `handle_for(...)`, if `handle.session_name` is not among
    `runner.list_owned_panes()`' session names, return
    `{"session_id": session_id, "ok": False, "killed": False, "reason": f"{session_id}: its pane is gone — nothing to kill"}`;
    no `kill.<id>` record, no `terminate`. `kill_landed(...)` reads it as `False`. Budget: `tools_m3.py`
    ≤ 450 (445 → 447).
- **Coverage limit, recorded (BC-37 residual → owner):** a session that finished a turn before it was
  killed now ends `stopped` (it already was, from the turn) but keeps its last turn's verdict, because
  the verdict guard reads `ended_at`. Never-turned rows — O6's and U11's — get `state stopped` and the
  `killed` verdict (bucket `stranded`).
- **Regression tests (RED first):**
  - `test_a_kill_leaves_a_never_turned_row_stopped_and_stranded` — owned row `starting`, ScriptedRunner
    with the pane listed; after `record_and_terminate`, `state == stopped`, `stop_reason == killed`,
    bucket `stranded`. RED: `starting`.
  - `test_a_kill_after_a_turn_leaves_the_row_stopped` — the row first folded through a turn stop
    (`ended_at` set, pane still listed and alive); after the kill `state == stopped` (records the
    residual: the verdict is the turn's, asserted as today's behaviour and named in the ledger).
  - `test_killing_a_pane_that_is_gone_is_a_refusal_value` — no pane listed; `kill` answers `ok False`,
    `kill_landed(...) is False`, `app_state` has no `kill.<id>`, the runner saw no `terminate`.
    RED: `RunnerRefusal` and a record left behind.
  - `test_a_live_session_that_finished_a_turn_can_still_be_killed` — **live post-turn regression:** row
    with `ended_at` set by a turn stop, pane listed and alive → `killed True`, `terminate` called once.
    (Passes today; it is the guard against the `ended_at` discriminator the review rejected.)
- **Required checks:** new files; `tests/orchestration/test_lifecycle.py` (250 cap, and its G-M3-9
  test unchanged and green), `tests/store/test_stop_verbs.py` (single stop writer untouched),
  `tests/toolsurface/test_tools_m3.py` (450 cap, count 14), `tests/orchestration/test_degradation.py`; the project-delete-with-kill tests (`tests/toolsurface/` project delete tests, `tests/web/test_routes_projects.py`) — BC-29 changes the `kill_landed` answer `compose.py:462-466` feeds into `delete_project(on_running=KILL)` (`store/projects.py:201-240`); mypy.
- **qa6 proof:** O6 `api.already_killed_refused` and `db.no_state_change` FAIL→PASS; O5 stays PASS;
  U11's killed header chip is no longer `UNCLASSIFIED/starting` (screenshot, not asserted — HI-2).
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, `lifecycle.py` ≤ 250 with no prose removed, caps held, mypy clean.
- **test_seams:** integration at the lifecycle function (real `Store`, scripted runner); L4 handler for BC-29.
- **Consumes:** none. **Produces:** none (no signature changes).

### P8 — BC-22 the audit states the level in force; BC-31 blank project names refused

- **Files:** `src/shepherd/toolsurface/types.py`, `src/shepherd/toolsurface/approvals.py`,
  `src/shepherd/toolsurface/registry.py`, `src/shepherd/store/projects.py`,
  `src/shepherd/toolsurface/tools_projects.py`; new `tests/toolsurface/test_audit_level_in_force.py`,
  new `tests/toolsurface/test_project_name_blank.py`.
- **Dependencies:** P0. **Out-of-scope drift:** name normalisation (stripping stored names), UI validation, `tools_master.py`.
- **Fix:**
  - BC-22 (T6-3's recorded fix): `AuthzOutcome.autonomy_level: int | None = None`; both
    `AuthzOutcome(...)` sites in `approvals.py` pass `autonomy_level=int(current)` where
    `current = level()` is read once per call; `registry._audit` writes
    `outcome.autonomy_level if outcome.autonomy_level is not None else UNREPORTED_AUTONOMY_LEVEL`.
    `UNREPORTED_AUTONOMY_LEVEL` and `test_the_unreported_autonomy_level_is_not_a_real_level` stay.
  - BC-31: `store.projects` `create_project`/`rename_project` raise `StoreError("a project name cannot be blank")`
    when `not name.strip()`; `rename_project`'s handler already answers `_refused(...)`; `create_project`'s
    handler gains a two-line blank check returning `_refused("created", "a project name cannot be blank", "project")`
    (`tools_projects.py` reaches exactly 450, the cap).
- **Regression tests (RED first):**
  - `test_the_audit_record_carries_the_level_the_gate_read` — chokepoint installed with level 3; one
    gated and one read call; both records `autonomy_level == 3`. RED: 0.
  - `test_a_whitespace_rename_is_refused` / `test_a_whitespace_create_is_refused` — HTTP-free, via `invoke()`;
    `renamed/created False`, `refused` non-empty, the stored name unchanged.
- **Required checks:** new files; `tests/toolsurface/test_registry_gate.py`, `test_tools_m3.py`
  (cap/count), `tests/store/` project tests, `tests/web/test_routes_projects.py`; boundaries; mypy.
- **qa6 proof:** M7 `logs.kill_autonomy_level_3`, M16 `files.autonomy_level_is_the_level_in_force`
  (M16 flips with P10's `limit`), P2 both clauses FAIL→PASS; P1, P3–P10 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, caps held, mypy clean.
- **test_seams:** integration at `invoke()` with the real chokepoint and audit sink.
- **Consumes:** none. **Produces:** `AuthzOutcome.autonomy_level: int | None`.

### P9 — BC-16 a live socket is never stolen, and probing it harms nothing; BC-21 (C10) a newer DB is a refusal; BC-20 an unreadable settings file is a refusal

- **Files:** `src/shepherd/engines/claude_code/ingest_socket.py`, `src/shepherd/daemons/control_ingest.py`,
  `src/shepherd/daemons/controld.py`, `src/shepherd/daemons/sessiond.py`,
  `src/shepherd/engines/claude_code/hooks_config.py`; new `tests/daemons/test_controld_refusals_qa6.py`,
  new `tests/engines/test_socket_live_owner.py`, new `tests/engines/test_hooks_config_unreadable.py`.
- **Dependencies:** P0. **Out-of-scope drift:** C7's order (owner), the backup/uninstall halves of
  BC-20 (owner), the two guard constants, `host/base.py` (its charter is "the seven questions a
  platform answers, and nothing else", :1 — a socket-connecting helper is not one of them), a new
  `HostPlatform` member.
- **Why the probe needs a second fix:** `claim_socket` connects and closes. The live owner's
  `serve_control_ingest` accepts that connection and sends its hello at `control_ingest.py:56`,
  **outside** the `except (WireError, OSError)` at :57-63; the send to a closed peer raises EPIPE/ENOTCONN
  out of the loop and the `finally` (:64-66) closes the listener and unlinks the owner's own socket —
  the exact theft BC-16 is about, now caused by the refusal path. `serve_ingest`
  (`ingest_socket.py:163-191`, sessiond's lane) ignores an empty payload and is already safe; it is
  covered by the same test.
- **Fix:**
  - `engines/claude_code/ingest_socket.py` (beside `bind_listener`, which both listeners share):
    `class SocketInUse(RuntimeError)`; `def claim_socket(plan: SocketPlan) -> SocketPlan` — if
    `plan.path` exists and an `AF_UNIX` connect to it succeeds within 0.25 s, close it and raise
    `SocketInUse(f"{plan.path} is held by a running process")`; a refused/absent socket returns
    `plan`. `bind_listener` calls `claim_socket(plan)` before `unlink_socket` (so sessiond's ingest
    socket is covered too).
  - `daemons/control_ingest.py`: the hello `sendall` moves inside a `try … except OSError: continue`
    (a peer that closed before the greeting loses its connection, never the daemon — the rule the
    existing `except` already states). `SocketInUse` and `claim_socket` join its existing
    `ingest_socket` import and its `__all__` (explicit re-export under `mypy --strict`).
  - `daemons/sessiond.py`: `main` catches `SocketInUse` and prints `sessiond refuses to start: …`,
    exit 2 (≤ 150 lines).
  - `daemons/controld.py`, **net zero lines**: line 30 becomes
    `from shepherd.daemons.control_ingest import SocketInUse, claim_socket, serve_control_ingest`;
    line 71 `plan = claim_socket(host.control_socket(CONTROL_SOCKET_NAME))` (before `open_store`);
    line 122 `except (SocketPathTooLong, SocketInUse, MigrationRefused) as refused:`; line 40 gains
    `MigrationRefused`. Line count stays 140; `RESERVED_FOR_M2` untouched.
  - `hooks_config._load`: `except PermissionError as error: return None, f"settings file cannot be read ({error.strerror}), so it is left untouched"`.
- **Regression tests (RED first):**
  - `test_probing_a_live_control_ingest_leaves_the_owner_serving` — run `serve_control_ingest` on a
    tmp plan in a thread (`bound` event awaited, no sleep); connect and close without reading (the
    probe's shape), then `claim_socket(plan)` raises `SocketInUse`; afterwards a real client still
    receives the hello, the owner thread is alive, and the socket inode is unchanged; shutdown joins
    the thread with a timeout. RED today: the owner thread has exited and the path is gone after the
    first connect-and-close.
  - `test_probing_a_live_ingest_listener_leaves_it_serving` — the same against `serve_ingest`
    (sessiond's lane): a frame sent after the probe is still delivered to `on_frame`.
  - `test_a_second_bind_does_not_steal_a_live_socket` — `bind_listener` on a path a live listener
    owns raises `SocketInUse`; inode unchanged. RED: the second bind unlinks and rebinds.
  - `test_a_stale_socket_file_is_reclaimed` — a socket file with no listener → `claim_socket` returns the plan.
  - `test_controld_refuses_a_held_control_socket_and_writes_nothing` — `controld.main([...])` inside
    `tests/daemons/test_controld.py`'s `world` pattern (env-redirected `detect_host()`, as
    `test_a_refused_start_leaves_no_database_behind` does — `main` takes no host argument) with
    `serve_control_ingest` already serving on `detect_host().control_socket(CONTROL_SOCKET_NAME).path`
    → returns 2, prints `controld refuses to start:`, `shepherd.db` not created, the first owner still
    serving. The fixture is imported from that module or copied into the new file;
    `test_controld.py` itself is not edited.
  - `test_controld_refuses_a_newer_schema` — a DB at `EXPECTED_SCHEMA_VERSION + 1` → returns 2 with
    the refusal line, no traceback. RED: `MigrationRefused` raised.
  - `test_an_unreadable_settings_file_is_a_refusal` — mode 000 file (skipped when running as root):
    `install_hooks` answers `refused_reason` non-empty; `inspect_hooks` does not raise. RED: `PermissionError`.
- **Required checks:** new files; `tests/daemons/` (incl. `test_controld_composition.py` — 140 ≤ 140,
  and `test_the_composition_root_registers_no_capability_itself`), `tests/engines/` ingest and relay
  tests, `tests/engines/test_hooks_install.py`, `tests/boundaries/test_platform_branching.py`,
  `tests/boundaries/test_hookd_isolation.py`; mypy.
- **qa6 proof:** C9 (4 clauses, incl. `files.socket_inode_unchanged` — now true for the probed owner
  too), C10 (2 clauses) FAIL→PASS; H5 `api.mode_000_refused` clause FAIL→PASS (H5 stays FAIL on SD-10);
  C6, C8 stay PASS; C7 stays FAIL (owner).
- **Checkpoint:** none. **Validation:** deterministic (tmp sockets, `bound` events, timed joins only as
  a failure bound; no port 8787). **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, `controld.py` still 140 lines, mypy clean.
- **test_seams:** unit at `claim_socket`/`bind_listener`; integration at `serve_control_ingest`,
  `serve_ingest`, `controld.main`, `sessiond.main` (in-process, tmp dirs).
- **Consumes:** none. **Produces:** `SocketInUse`, `claim_socket(plan: SocketPlan) -> SocketPlan`
  (`shepherd.engines.claude_code.ingest_socket`, re-exported by `shepherd.daemons.control_ingest`).

### P10 — BC-23 integer query args; BC-32 body read timeout; BC-33 keep-alive after an event

- **Files:** `src/shepherd/web/routes.py`, `src/shepherd/web/server.py`, `src/shepherd/web/sse.py`;
  new `tests/web/test_routes_query_ints.py`, `tests/web/test_server_short_body.py`,
  `tests/web/test_sse_keepalive_after_event.py`.
- **Dependencies:** P0. **Out-of-scope drift:** new routes, a global handler `timeout` (would touch SSE/WS), the ring.
- **Fix:**
  - BC-23: `QUERY_ARGS["/api/audit"] = ("limit",)`; `INTEGER_QUERY_ARGS: frozenset[str] = frozenset({"limit", "scrollback"})`;
    `resolve()` converts those with `int(value)`; a value that is not an integer is dropped (the
    tool's default applies) — never forwarded as a string.
  - BC-32: `BODY_READ_TIMEOUT_S = 2.0`; `_json_body` sets `self.connection.settimeout(BODY_READ_TIMEOUT_S)`
    around the read, treats `TimeoutError`/`OSError` or a short read as `None` (→ 400), sets
    `close_connection = True` on that path, and restores `settimeout(None)`.
  - BC-33: `stream()` yields `KEEPALIVE` after **every** subscription that ends (a subscription only
    ends after `idle_timeout_s` of silence), not only an empty one; the `cursor` handling is unchanged.
- **Regression tests (RED first):**
  - `test_limit_is_forwarded_as_an_integer` (`resolve("/api/audit", {"limit": ["0"]})` → `{"limit": 0}`),
    `test_scrollback_is_forwarded_as_an_integer`, `test_a_non_integer_value_is_dropped`,
    and one HTTP test: `GET /api/audit?limit=0` → `records == []`. RED: key absent / string.
  - `test_a_short_body_is_a_400_within_the_timeout` — real server on an ephemeral loopback port; send
    `Content-Length: 100` and 10 bytes; 400 within 3 s. RED: no answer.
  - `test_a_keepalive_follows_an_event_after_one_idle_period` — `sse.subscribe` monkeypatched to a
    scripted generator (one delivery, then end); `next()` ×3 on `stream(None)` gives
    `OPENED, frame, KEEPALIVE`. RED: the third item comes from a second subscription instead.
- **Changed existing assertion (declared, node id unchanged):** `tests/web/test_routes_m3.py:290`
  `assert len(routes.QUERY_ARGS) == 3` → `4`, and its comment gains "and BC-23's `/api/audit`".
  `test_no_declared_field_shadows_a_path_parameter` (:280-289) still passes — `limit` shadows no path
  parameter.
- **Required checks:** new files; `tests/web/test_routes*.py`, `test_sse.py`, `test_security.py`,
  `test_restart.py`; boundaries (**known-red: the two consumer-manifest tests**); mypy.
- **qa6 proof:** A4, E1 FAIL→PASS; M16 `api.limit_zero_empty` FAIL→PASS; A1–A3, A5–A8, E2–E4 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** stable.
- **Exit criteria:** tests GREEN, RED recorded, mypy clean.
- **test_seams:** unit at `routes.resolve` and `sse.stream`; integration at the real HTTP server.
- **Consumes:** none. **Produces:** `INTEGER_QUERY_ARGS`, `BODY_READ_TIMEOUT_S` (web-internal).

### P11 — BC-11 dead daemon ≠ empty fleet; BC-19 shell keyboard; BC-18 Flock focus

- **Files:** `src/shepherd/web/static/app.js`, `flock.js`, `index.html`, `app.css`;
  new `tests/web/test_shell_flock_qa6_live.py`.
- **Dependencies:** P0. **Out-of-scope drift:** the session pane (P12), projects (P13), new nav entries.
- **Fix:**
  - BC-11: `view.fleetReadable` (initially `false`) set by `loadFleet` from whether the fleet read
    answered; `flock.js` renders, when it is false, `FLEET_UNKNOWN = "the fleet is unknown — Shepherd did not answer"`
    instead of the empty-fleet state, and no `registry: 0 sessions` source line.
  - BC-19: `#mark` gets `tabindex`/`role="button"`/`aria-label`; `app.js` makes it a tab stop only
    while the rail is collapsed and expands on Enter/Space; `app.css` phone media block hides the
    closed drawer from the Tab order (`visibility: hidden` with the transition delayed so the slide-out still animates).
  - BC-18 (Flock half): card rendering reuses existing nodes keyed by `data-session-id` when their
    rendered content is unchanged, and restores focus to the node with the previously focused key.
- **Regression tests (RED first, chromium via playwright, served by the real server, `importorskip` as the existing live tests do):**
  - `test_a_dead_daemon_is_not_an_empty_fleet` (fetch refused) — empty-state absent, `FLEET_UNKNOWN` visible.
  - `test_the_collapsed_rail_expands_by_keyboard` — Tab reaches `#mark`, Enter expands.
  - `test_the_closed_drawer_takes_no_focus` — 390 px viewport, Tab never lands in the closed drawer.
  - `test_card_focus_survives_an_event` — focus a card, publish a `session.state` event, wait for the
    DOM rebuild signal (a mutation observer promise, not a request count — HI-4), focus still on it.
- **Required checks:** new file; `tests/web/test_shell.py`, `test_flock_page.py`, `test_shell_live.py`,
  `test_frontend_escaping.py`, `test_frontend_unreachable_daemon.py`, `tools/js_syntax_check.py`;
  boundaries (known-red manifest pair); mypy.
- **qa6 proof:** U38, U2, U4 FAIL→PASS; U41 `ui.card_focus_survives` PASS (U41 flips with P13); U1,
  U3, U5, U6, U9, U12, U15, U16 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic (DOM signals, no sleeps). **Durability:** near-term-refactor (UI).
- **Exit criteria:** tests GREEN, RED recorded.
- **test_seams:** e2e-in-browser at the page (real server, real modules).
- **Consumes:** none. **Produces:** `view.fleetReadable` (app.js view state), `FLEET_UNKNOWN` (flock.js).

### P12 — BC-13 header follows state; BC-36 no terminal for a killed session; BC-25 rename intent; BC-12 R3

- **Files:** `src/shepherd/web/static/session.js`, `src/shepherd/web/static/app.js`;
  new `tests/web/test_session_pane_qa6_live.py`.
- **Dependencies:** **P11** (shared `app.js`) — P12's branch is cut from `fix/qa6-P11`, not from the base. **Out-of-scope drift:** decision card (SD-06), terminal input (SD-05).
- **Fix:**
  - BC-13: `export function refreshSessionHeader(row)` in `session.js` fills title, chip, state,
    why and actions only when `showing === row.session_id`, never touching the terminal; `app.js`'s
    refresh loop re-reads the open session (intent-guarded by `view.openSessionId`) and calls it.
  - BC-36: `renderSession` skips `openTerminal` for an owned row whose `stop_reason === "killed"`,
    showing `KILLED_BANNER = "this session was killed — its terminal is gone"`. **Not `ended_at`:**
    every turn end stamps it on a live pane (`fold.py:63-64`), so keying on it would hide the terminal
    of every session that has answered once. `stop_reason === "killed"` is the projection's one field
    (`tools_m1.py:110`) that means Shepherd removed the tmux session; a session whose process exited on
    its own keeps its pane (`remain-on-exit on`, `runner/local.py:351`) and its socket still opens.
    Limit (BC-37 residual, owner): a session killed after a turn keeps its turn's `stop_reason` and
    still opens a socket that 404s.
  - BC-25 (rename): the Escape path repaints from a module-held current title updated on every
    successful rename; Enter sets an in-flight flag and a second Enter while in flight posts nothing.
  - BC-12 R3: the rename reply paints only if `showing` still names the renamed session.
- **Regression tests (RED first, browser):** `test_the_header_follows_a_state_change`,
  `test_a_killed_owned_session_opens_no_socket` (`stop_reason: "killed"`: no WS request, no console
  error, `KILLED_BANNER` shown), `test_a_live_session_that_finished_a_turn_still_opens_its_terminal`
  (**live post-turn regression:** owned row with `ended_at` set, `state: "stopped"`, `stop_reason:
  "completed"` → exactly one WS request to `/api/sessions/<id>/terminal`),
  `test_escape_after_a_rename_shows_the_new_title`, `test_a_double_enter_posts_one_rename`,
  `test_a_slow_rename_reply_does_not_paint_another_session` (fetch parked with a page-level shim, as
  round 5's DUP-1 proof did).
- **Required checks:** new file; `tests/web/test_session_page.py`, `test_session_wiring.py`,
  `test_decision_live.py`, `test_terminal_fit_live.py`; boundaries (known-red manifest pair); mypy.
- **qa6 proof:** U45, U11, U13, R3 FAIL→PASS; U9, U10's passing clauses, U12 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** near-term-refactor.
- **Exit criteria:** tests GREEN, RED recorded.
- **test_seams:** e2e-in-browser at the page.
- **Consumes:** `view.fleetReadable` (P11, unchanged). **Produces:** `refreshSessionHeader(row)` (session.js export), `KILLED_BANNER`.

### P13 — BC-12 R2/R4/R5; BC-18 Projects focus; BC-24 refusals and retries

- **Files:** `src/shepherd/web/static/projects.js`, `src/shepherd/web/static/settings.js`;
  new `tests/web/test_projects_settings_qa6_live.py`.
- **Dependencies:** P0. **Out-of-scope drift:** new project verbs, D63/D64.
- **Fix:**
  - R2: `choose(level)` records the intent synchronously; a reply for a superseded click paints nothing
    and the last click is re-sent if the server holds an older value.
  - R4: `loadDraftPaths()` checks the dialog's project id before painting.
  - R5 + BC-18 (Projects): the list reuses row nodes keyed by project id when unchanged, so a rebuild
    between pointer-down and click leaves the clicked node in place, and focus is restored by key.
  - BC-24: a refused repo remove shows its refusal (as refused adds already do); a refused or
    unreachable autonomy change shows the error with its correlation id; a retried save sends only the
    steps that have not yet succeeded (the dialog's baseline is updated after each successful step).
- **Regression tests (RED first, browser):** `test_the_last_autonomy_click_wins`,
  `test_a_slow_path_read_does_not_paint_another_project`, `test_a_rebuild_does_not_swallow_an_edit_click`,
  `test_row_focus_survives_an_event`, `test_a_refused_remove_is_shown`, `test_a_refused_level_change_is_shown`,
  `test_a_retried_save_does_not_resend_the_rename`.
- **Required checks:** new file; `tests/web/test_projects_page.py`, `test_projects_stream.py`,
  `test_settings_page.py`, `test_settings_live.py`; boundaries (known-red manifest pair); mypy.
- **qa6 proof:** R2, R4, R5, U17, U18, U24 FAIL→PASS; U41 `ui.row_focus_survives` → U41 PASS; R6, R7,
  U15, U16, U19–U23 stay PASS.
- **Checkpoint:** none. **Validation:** deterministic (parked fetches). **Durability:** near-term-refactor.
- **Exit criteria:** tests GREEN, RED recorded.
- **test_seams:** e2e-in-browser at the page.
- **Consumes:** none. **Produces:** none.

### P14 — BC-06 (step body), BC-25 composer, BC-26 one card per approval

- **Files:** `src/shepherd/web/static/chat.js`; new `tests/web/test_chat_qa6_live.py`.
- **Dependencies:** P0. **Out-of-scope drift:** the owner half of BC-06 (step count, `turn_ended`/`rate_limit`
  announcement, the duplicate final answer) — the current split into two steps and the `eventText`
  fallback are left as they are.
- **Fix:**
  - BC-06 body: a `tool_call` step's body names the argument **keys** only (never values — the rule
    `chat.js`'s approval card states for raw arguments); a `tool_result` step's body is `data.text`,
    or `(no result text)` when empty. No object reaches `textContent`.
  - BC-25 composer: `submit()` posts nothing when `text.trim() === ""` (the sent text is not
    trimmed — `"a\nb"` still posts as is); `onComposerKey` returns early when `event.isComposing`.
  - BC-26: a card is appended only if no `[data-approval-id="<id>"]` exists and the id is not already in `state.approvals`.
- **Regression tests (RED first, browser):** `test_no_step_renders_object_object`,
  `test_whitespace_only_text_posts_nothing`, `test_enter_during_composition_posts_nothing`,
  `test_an_approval_in_both_the_load_read_and_the_stream_is_one_card`.
- **Required checks:** new file; `tests/web/test_chat_page.py`, `test_frontend_escaping.py`; boundaries
  (known-red manifest pair); mypy.
- **qa6 proof:** U25, U30 FAIL→PASS; U26 `ui.step_detail_not_object_object` clause FAIL→PASS (U26
  stays FAIL, owner half); U27–U29, U31–U37 stay PASS; L1 still PASS.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** near-term-refactor.
- **Exit criteria:** tests GREEN, RED recorded.
- **test_seams:** e2e-in-browser at the page.
- **Consumes:** none. **Produces:** none.

### P15 — BC-10 the snapshot opens readable; BC-35 a refused stream says so

- **Files:** `src/shepherd/web/static/terminal.js`, `src/shepherd/web/static/sse.js`;
  new `tests/web/test_terminal_sse_qa6_live.py`.
- **Dependencies:** P0. **Out-of-scope drift:** the server's snapshot bytes (T19 byte-for-byte test stays),
  `convertEol` for live chunks, terminal input.
- **Fix:**
  - BC-10 (**RED first confirms the hypothesis before any fix**): frame 1 only is passed through
    `export function snapshotForEmulator(bytes)` — every LF not preceded by CR becomes CRLF, and
    trailing runs of LF/CR/space are trimmed; later frames are written unchanged. If the RED test does
    not reproduce a blank viewport with a real capture fixture, stop and record the disproof in the
    ledger instead of fixing.
  - BC-35: the `error` listener reports `"unreadable"` when `source.readyState === EventSource.CLOSED`,
    `"reconnecting"` otherwise (the existing vocabulary, `app.js:78-79`; no new status word).
- **Regression tests (RED first, browser):** `test_the_snapshot_text_is_visible_on_open` — terminal
  mounted with a fake WebSocket fed a real `capture-pane -e -p` capture from `docs/probes/` (read, not
  edited) on a pane taller than the emulator; the marker line is in the visible rows and the next live
  chunk starts at column 0. `test_a_forbidden_stream_reads_unreadable` — `/api/events` answered 403 by
  a route interception; status `unreadable` within 5 s.
- **Required checks:** new file; `tests/web/test_terminal_fit_live.py`, `test_session_page.py`,
  `test_shell_live.py`, `test_ws.py`; boundaries (known-red manifest pair); mypy.
- **qa6 proof:** U40 FAIL→PASS; U10 `ui.xterm_rows_show_the_marker` clause FAIL→PASS (U10 stays FAIL on
  SD-05); U38(a), U39 stay as P3 leaves them.
- **Checkpoint:** none. **Validation:** deterministic. **Durability:** near-term-refactor.
- **Exit criteria:** tests GREEN (or BC-10 disproved and recorded), RED recorded.
- **test_seams:** e2e-in-browser at the module (real xterm vendor file).
- **Consumes:** none. **Produces:** `snapshotForEmulator(bytes)` (terminal.js export).

### P16 — Integration: merge, declare, re-check

- **Objective:** one branch with every phase, the consumer manifest declaring each `web/` edit, and the
  boundary suite green.
- **Files:** `tests/boundaries/consumer_manifest.json`; new `docs/plans/qa6-bugfix-blockers/README.md`.
- **Dependencies:** P1–P15.
- **Steps:**
  1. Merge `fix/qa6-P1` … `fix/qa6-P10`, `fix/qa6-P12` (which already contains P11), `fix/qa6-P13`,
     `fix/qa6-P14`, `fix/qa6-P15` into `fix/qa6-bugfix` (disjoint files → no conflicts expected; any
     conflict is a scope violation to record, not to resolve silently).
  2. Manifest: never touch `baseline` or `rebase`. Update `files` digests for every changed `web/` file.
     `post_milestone.edits` (one entry per path, rewritten rather than appended, each with `at`, `by`,
     `why` naming the BCs): **new** entries for `web/server.py`, `web/sse.py`, `web/static/sse.js`;
     **rewritten** entries for `web/static/flock.js`, `projects.js`, `session.js`, `settings.js`,
     `terminal.js`. Re-based paths (`web/routes.py`, `web/static/app.js`, `chat.js`, `index.html`,
     `app.css`) get only their `files` digest (the test forbids them in `post_milestone`); their
     edits are recorded in the README instead.
  3. Assert `git diff --stat be9db6f -- src/shepherd/cli` is empty (the `cli/` freeze held).
  4. README: one line per BC → phase → commit → ledger file; the changed-assertion list —
     `tests/orchestration/test_mailbox.py:575` (P2, `SEND_NOW` → `CLEAR_THEN_SEND`),
     `tests/toolsurface/test_compose.py:255` (P3, leading `stream.gap`),
     `tests/web/test_routes_m3.py:290` (P10, 3 → 4) — each with its reason; the siblings left open
     (rename's typing race, `liveness_sweep` frames without `project_id`, per-pass
     `unknown_registry_status`, the BC-37 residual and its BC-36 consequence, a pane-gone owned row with `ended_at` NULL being undeletable under `on_running=KILL` after BC-29, and P9's claim-to-bind window).
- **Required checks:** `.venv/bin/pytest -p no:randomly tests/boundaries` fully green (the manifest
  pair included) except any failure already in `BASELINE_BOUNDARY_FAILS`; mypy.
- **Checkpoint:** none. **Validation:** deterministic.
- **Exit criteria:** boundary suite at or better than baseline; `cli/` diff empty.
- **test_seams:** boundary (AST/digest) suite.
- **Consumes:** every phase's commits. **Produces:** branch `fix/qa6-bugfix` at an integration commit.

### P17 — Full verification

- **Objective:** evidence that the fixes hold and nothing regressed.
- **Dependencies:** P16. **Files:** new `docs/plans/qa6-bugfix-blockers/P17-verification.md`.
- **Steps:**
  1. `.venv/bin/pytest -p no:randomly` → expected: still interrupted by the 3 qa5 collection errors (noted, as baseline).
  2. `.venv/bin/pytest -p no:randomly --ignore=tests/qa5` → failing ids ⊆ `BASELINE_DEFAULT_FAILS`;
     passed count = baseline passed + the new tests (±0 elsewhere); every new test PASS.
  3. `.venv/bin/mypy --strict src` → clean.
  4. `.venv/bin/python tests/qa6/run.py --report-dir .cc10x/qa/wf-20260924T044326Z-3a830e78/qa6-postfix`
     (full run, all waves; never with `--skip-t4`).
  5. Compare its records with run 2's (`…/qa6-20260924T040750Z/records/`) per scenario **and** per
     clause, with a throwaway script in the scratchpad (not committed): the 34 scenario flips and 6
     clause flips listed in Part 1 appear; no scenario or clause that was PASS is now FAIL; the
     remaining 27 FAILs are exactly the owner/SD/oracle set; BLOCKED is exactly R1, L6 and **L7**
     (L7's only non-PASS clause is `api.m3_queue`, BLOCKED — `verdict.py:281-289`), plus wave-8
     scenarios if INC-1 is still open — recorded as such.
  6. Host safety from the runner's own checks: settings sha unchanged, no `~/.local/bin/claude`
     change, no Z2-class tmux argv, clean teardown.
- **Checkpoint:** none (AFK); any unexpected FAIL returns the owning phase to its builder with the
  clause evidence — never an oracle edit.
- **Validation:** deterministic for 1–3; qa6 is a live multi-process run — a scenario that differs
  from expectation is re-run once alone (the report's one-re-run rule) and reported FLAKY if it then passes.
- **Exit criteria:** all five comparisons hold and are written in the ledger.
- **test_seams:** the qa6 e2e harness; the default lane.
- **Consumes:** `BASELINE_DEFAULT_FAILS`, `BASELINE_BOUNDARY_FAILS` (P0). **Produces:** `P17-verification.md`.

---

## Behaviour contract (critical path)

| # | Given | When | Then |
|---|---|---|---|
| B1 | a live `claude` on a Mac off UTC | discovery reads its sidecar | the product token equals `procStart`; the row is not stopped |
| B2 | one pending message, route and sweep both firing | both try to deliver | the pane receives the text once; one `Delivery` has `delivered == 1` |
| B3 | a draft in the input box that the clear removes | the message is sent | `decision == clear_then_send`, delivered 1 |
| B4 | a page connected to process A, A restarts as B | the page reconnects with A's last id | it receives `stream.gap` then B's events |
| B5 | an idle session first seen at age < 60 s, stamp unchanged | a pass runs at age ≥ 60 s | state `needs_you`, reason `idle — waiting…`, one frame |
| B6 | a terminal WebSocket open on an owned pane | the pane is killed | the socket closes with 1000 within ~1 s |
| B7 | a second controld on the same runtime dir | it starts | exit 2, `controld refuses to start: …`, socket inode and DB untouched, and the first controld's ingest loop still serving after the probe |
| B9 | an owned session alive after finishing a turn (`ended_at` set) | the user kills it, or opens it | the kill proceeds; the terminal socket opens |
| B10 | an owned session Shepherd already killed (pane gone) | the user kills it again, or opens it | a refusal value with no `kill.<id>` record; no terminal socket, the killed banner |
| B8 | a master turn whose runtime fails to build | the user sends | refusal without internals; the wake summary opens the next turn |

## Edge-case catalogue

E1 pid reused within one second (lstart resolution — unchanged, recorded in `mac.py`) · E2 a `TZ`
variable already `UTC` (helper is idempotent) · E3 sweep and route racing while a human client is
attached (deferral path runs under the lock, still counted) · E4 the clear does not empty the box
(still `REFUSE_INPUT_NOT_EMPTY`, not `CLEAR_THEN_SEND`) · E5 wall clock stepped back between restarts
(ahead-cursor → replay from 0) · E6 ring overflow behind a live client (existing gap path, E4 scenario
stays PASS) · E7 hook observation newer than the sidecar (RD8 wins) · E8 sidecar dir created after
startup (fallback not re-consulted; the scan simply finds sidecars) · E9 a malformed file healed and
broken again (counted again) · E10 pane exits by itself vs killed (both end the stream) · E11 a stale
socket file with no listener (reclaimed) · E12 settings file mode 000 while running as root
(test skipped; behaviour unchanged) · E13 a kill racing a SessionEnd hook (verdict guard unchanged; `apply_fold_delta(state=stopped)` is idempotent with the hook's,
state already stopped) · E14 `limit=abc` (dropped, default applies) · E15 a body sent slowly but
completely within 2 s (accepted) · E16 a second owner binding the control socket between `claim_socket` (`controld.py:71`) and the ingest thread's `bind_listener`: the thread raises `SocketInUse`, `start()` raises `TimeoutError`, and `main`'s `except OSError` prints "port N is not available" — a misleading line on a narrow race; accepted as a known residual (no theft happens, the daemon still refuses), recorded in P16's README.

## Provable properties

- **PP-A (BC-01):** for every environment `e`, `mac_liveness_env(e)["TZ"] == "UTC"` and all other keys equal `e`'s — unit.
- **PP-B (BC-02):** while `DELIVERY_LOCK` is held by one caller, no other caller's `deliver_now` writes
  to any pane; hence a pending set is written at most once — interleaving test.
- **PP-C (BC-02):** `decision == CLEAR_THEN_SEND` on the returned `Delivery` iff a clear was sent and the re-read found the box empty.
- **PP-D (BC-03):** for processes started at wall times t1 < t2 (ms), every seq issued by the t1
  process is < `stream_seq_base()` at t2 provided it issued fewer than 1000·(t2−t1) events; and a
  cursor > head is served as cursor 0.
- **PP-E (BC-04):** `registry_delta` never writes over a strictly newer prior; with an equal stamp it
  writes only the idle→needs_you crossing.
- **PP-F (BC-09):** `chunks()` terminates within `STREAM_LIVENESS_S` + one poll after `alive()` turns false.
- **PP-G (BC-16):** `bind_listener` never unlinks a path a live listener accepts on, and a probe
  connection that closes without reading never ends a live `serve_control_ingest` or `serve_ingest` loop.
- **PP-K (BC-29/36):** no kill refusal and no terminal suppression is keyed on `ended_at`; the kill
  refusal holds iff the pane is absent from `runner.list_owned_panes()`, and the terminal is suppressed
  iff `stop_reason == "killed"`.
- **PP-H (BC-17/27):** per `run_discovery_loop` lifetime, `agents_json_fallback` is called ≤ 1 time;
  a persistent malformed file raises `malformed_payload` by exactly 1.
- **PP-I (S8, BC-07/08):** no master reason or error text contains an exception `repr` or class name.
- **PP-J (freeze):** `git diff be9db6f -- src/shepherd/cli` is empty; `controld.py` is 140 lines.

## Purity boundary map

| Pure (unit-tested, no I/O) | Effectful (integration-tested) |
|---|---|
| `mac_liveness_env`, `result_ending`, `registry_delta`, `_idle_crossed`, `coalesce` (unchanged, still in `orchestration/mailbox.py`), `stream_seq_base` (clock injected via monkeypatch), `routes.resolve`, `snapshotForEmulator` | `MacHost.process_liveness` (`ps`), `deliver_now`/`send`/`sweep_pending` (pane + store), `subscribe`/`publish` (lock, ring), `discovery_pass`/`run_discovery_loop`, `_PipeStream.chunks`, `claim_socket`/`bind_listener`/`serve_control_ingest`, `controld.main`, `hooks_config._load`, `record_and_terminate` (`apply_fold_delta` + unchanged `apply_stop_verdict`), `tools_m3.kill` (`list_owned_panes`), HTTP server, browser pages |

## Verification strategy

Three layers, each owning a different claim: (1) the new per-phase tests prove each root cause and
each fix, RED before GREEN, at the lowest seam that exercises the real code path; (2) the default lane
(minus qa5), the boundary suite and mypy prove nothing else moved and every freeze held; (3) the full
qa6 run proves the fixes are visible end to end and that no previously passing clause regressed. A
clause flip without its unit test is not accepted as proof (HI-3/HI-4 show clauses can be green or
racy for reasons unrelated to the fix).

## Risk-based testing matrix

| Risk | P | I | Test |
|---|---|---|---|
| UTC env breaks the token on a host where sidecars are local time | low | high | P1 darwin test with oracle `TZ=UTC ps`; D1–D11 in P17 |
| Lock deadlock between route and sweep | low | high | P2 interleaving tests (RLock, no store-side lock) |
| Seeded seq breaks a test or client assuming small seqs | med | med | P3 required checks run `tests/web`, `tests/daemons`, `tests/qa`; qa6 E-lane |
| Idle crossing overrides a hook-lane state | low | med | P4 newer-prior test + existing tie test |
| Pane-death probe adds tmux load per stream | med | low | `STREAM_LIVENESS_S` throttle; P6 argv count assertion |
| `claim_socket` refuses a legitimate restart (stale file) | low | high | P9 stale-socket test |
| The live-owner probe itself breaks the owner (unguarded hello send) | high (proven by code) | high | P9 probe-a-live-`serve_control_ingest` test |
| A kill/terminal discriminator hides a live post-turn session | med | high | P7 and P12 live-post-turn regression tests |
| A composing test reads the seeded ring from cursor 0 | high (proven: `test_compose.py:255`) | low | declared changed assertion in P3 |
| controld grows a line | med | high | `test_controld_composition.py` in P9 checks |
| A UI fix breaks a static JS scan (`test_frontend_escaping`, D25 whitelist) | med | med | each UI phase runs those modules |
| BC-10 hypothesis wrong | med | med | P15 RED-first gate; stop-and-record path |
| Manifest declaration wrong or missed | med | med | P16 boundary suite green |
| qa6 live lanes BLOCKED by INC-1 | high | low | recorded; unit tests carry L5/L7/L11 |
| Parallel lanes touch a shared file | low | med | disjoint table; P16 merge treats a conflict as a scope violation |

## Functionality flow mapping

- Discovery → liveness → state: P1 (token), P4 (idle crossing, fallback, count, project_id) → D-lane, L5.
- Message → queue → deliver → report: P2 → L7, O-lane.
- Event → ring → SSE → page: P3 (resume), P10 (keep-alive), P15 (refused stream), P11/P12 (rebuild, header) → E-lane, U38–U45.
- Master turn → error/refusal → page: P5, P14 → L11, M18, U25, U26, U30.
- Kill → verdict → state → page: P7, P12 → O6, U11.
- Start → refusals: P9 → C9, C10.
- Error paths: every phase's RED test is the error path it names.

## Assumptions (classified)

| Assumption | Class |
|---|---|
| The engine writes `procStart` as `ps -o lstart` in UTC on macOS | proven_by_evidence (report §13 repro, this host) |
| Both mailbox triggers can run concurrently in one process | proven_by_code (`compose.py:356`, `tools_messaging.py:161`) |
| `EventSource` resends the last `id:` after a restart | proven_by_evidence (U39 0.51 s back to `live`, E5) |
| No boundary rule forbids a module-level lock in `orchestration/` | proven_by_code (boundary suite read) |
| `ended_at` means only "a turn or session ended", never "the process is gone" | proven_by_code (`fold.py:63-64`, `rules.py:275-279`, `stop_lane.py:113`, `store/writes.py:86-103`) |
| A kill removes the tmux session, so a killed pane is absent from `list_owned_panes()` | proven_by_code (`lifecycle.py` → `LocalRunner.terminate` `kill-session`, `local.py:438-440`) |
| U11's and O6's killed sessions never finished a turn, so they carry `stop_reason: killed` and flip under P7/P12's discriminators | proven_by_evidence (O6 db row `{'state': 'starting', 'stop_reason': 'killed'}`; U11 header `starting`, report §4c BC-37) |
| A probe connect-and-close crashes a live `serve_control_ingest` today | proven_by_code (`control_ingest.py:56-66`) |
| BC-10's cause is bare-LF + trailing blank rows | **inferred** — gated by P15's RED-first stop-and-record rule |
| qa6 live lanes can resolve `claude` on this host | needs_user_confirmation (INC-1); non-blocking, outcome recorded either way |

## Decisions taken by this plan (with rationale)

- BC-03 uses a seeded seq plus ahead-cursor replay (ADR in P3), not an id format change.
- BC-35 reuses the existing `unreadable` status word — the report's oracle names it; no new vocabulary.
- BC-06's body shows argument keys, never values, because `chat.js` already states raw arguments are not
  rendered; the step count and non-text announcements are left for the owner.
- BC-29 answers a refusal **value** (O6 accepts `ok:false`), not a raise, keyed on the runner's pane
  listing; BC-36 is keyed on `stop_reason == "killed"`; neither on `ended_at`.
- BC-37 sets `state` through `apply_fold_delta` in the kill path, following `ask.py:_finish`; the stop
  writer's contract ("does not touch state") is kept. The post-turn verdict residual is an owner item.
- BC-16's probe lives in `engines/claude_code/ingest_socket.py` beside `bind_listener`, not in
  `host/base.py`, and the owner's hello send is guarded so a probe cannot harm it.
- Line budgets are met by re-wrapping code (P2's `_defer` calls, P7's `record` dict), never by
  shortening prose, and `coalesce` does not move.
- Three changed existing assertions are declared, not hidden: `test_mailbox.py:575` (P2 — it pinned
  the misreport), `test_compose.py:255` (P3 — the seeded ring), `test_routes_m3.py:290` (P10 — one more
  declared query route).
- Test files are new per phase so parallel lanes never share one; no existing test is renamed.

## Differences from the agreement

- **Four BCs are split** rather than classified whole: BC-06, BC-20, BC-21 (and BC-37, below) each have a FIX half
  planned here and an OWNER half listed above. The request asked for one verdict per BC; a split is
  the honest verdict where one half is a clear defect and the other needs a ruling.
- **Final verification uses two default-lane commands**, not one: the plain `pytest -p no:randomly`
  cannot run to completion on this Mac (qa5 collection), so `--ignore=tests/qa5` is the comparable
  lane. qa5 itself is noted, not fixed, as asked.
- **qa6's baseline is not re-run** in P0; run 2 of the round-6 report on the same tree is the
  comparison set.
- **BC-37 is split too** (revision 2): the never-turned half is fixed; the post-turn verdict residual
  is an owner item because the guard it would change is pinned by `test_lifecycle.py:372-416`.
- **BC-36 is fixed for killed rows only**, the rows U11 exercises; post-turn kills inherit the BC-37 residual.
- Otherwise none: the FIX set, owner list, SD/oracle listing, disjoint phases with BC-01 and the highs
  first, TDD per fix, and the verification phase are as requested.

Self-review: every `Consumes` names a `Produces` of an earlier phase verbatim (`view.fleetReadable`
P11→P12; `BASELINE_DEFAULT_FAILS`/`BASELINE_BOUNDARY_FAILS` P0→P16/P17); every other phase consumes
none. No cross-phase reference drift.


## Revision 2 change log (fresh review pass 1, `.cc10x/plan-reviews/qa6-bugfix-pass1.md`)

Every finding was re-checked against the code before it was accepted; all ten were accepted.

| # | Finding | Verified at | Change |
|---|---|---|---|
| 1 | `ended_at` is set on live sessions | `fold.py:63-64`, `rules.py:275-279`, `stop_lane.py:113`, `writes.py:86-103` | BC-29 keys on `list_owned_panes()`, BC-36 on `stop_reason == "killed"`; live-post-turn tests in P7 and P12; BC-37 residual → owner row |
| 2 | Probe crashes the live control ingest | `control_ingest.py:56-66` | P9 adds `daemons/control_ingest.py` (hello send guarded), a probe-a-live-owner test for both listeners; `claim_socket` moved to `ingest_socket.py` (`host/base.py`'s charter, :1) |
| 3 | Moving `coalesce` breaks `POPULATION` | `test_degradation.py:190-199`, `core/mailbox.py:5-6` | `coalesce` stays; lines reclaimed by re-wrapping `_defer(...)` calls; `core/mailbox.py` leaves P2 |
| 4 | Undeclared red assertions | `test_compose.py:255`, `test_routes_m3.py:290` | Declared in P3 and P10; listed in P16's README step |
| 5 | P12's branch base | Working method step 1 | P12 branches from `fix/qa6-P11`; P16 merges P12 in P11's place |
| 6 | L7 ends BLOCKED | `tests/qa6/verdict.py:281-289` | Expected outcome: 34 PASS · 27 FAIL · L7 → BLOCKED (3 BLOCKED); P17 step 5 |
| 7 | BC-37 reversed a stated split | `ask.py:149-152` | State set via `apply_fold_delta` in `lifecycle.py`; the stop writer is unchanged; store files leave P7 |
| 8 | P1 annotation and `tzset` leak | `test_hostplatform_contract.py:662-671,703-725` | The `"TZ"` line carries its own citation; `setenv` without `tzset` |
| 9 | P2's gated test cannot be sleep-free | — | One bounded timed join, stated, with its direction argued |
| 10 | P4's pass counter never fires | `discovery_loop.py:403-444, 486-487` | Passes counted through the `sweep` callable, which stops the loop itself |

## Revision 3 change log (fresh review pass 2, `.cc10x/plan-reviews/qa6-bugfix-pass2.md`)

| # | Finding (advisory) | Change |
|---|---|---|
| 1 | BC-29 changes project delete under `on_running=KILL` | P7 required checks add project-delete-with-kill tests; sibling recorded in P16 README |
| 2 | P2 test 2 gate must block only the first `attached_clients()` caller | Stated in P2's second regression test |
| 3 | P9 claim-to-bind window prints a misleading refusal | Edge case E16, accepted residual, recorded in P16 README |
| 4 | Line drift in P4 / Triage (BC-04, BC-17, BC-27, BC-34) | Line numbers corrected; BC-17/BC-27 cite the call by function |

## Revision 4 change log (router amendment during build)

| # | Trigger | Change |
|---|---|---|
| 1 | P8 builder: `AuthzOutcome.autonomy_level` (plan-required) breaks 4 undeclared pins | Declared, additive-only: `tests/toolsurface/test_policy.py::test_the_caller_context_field_is_defaulted` field set gains `autonomy_level`; `tests/toolsurface/test_approvals.py` ×3 (`test_an_unanswered_approval_times_out_and_counts`, `test_a_withdrawal_denies_the_blocked_call_and_counts`, `test_a_click_is_the_only_thing_that_produces_user_and_the_declared_denial`) expected outcomes gain `autonomy_level=int(AutonomyLevel.LEVEL_2)`. Strengthens, never weakens. P16 README lists them with the other changed assertions. |
| 2 | P13 builder: new state writes in `settings.js` must be declared | `tests/web/test_settings_page.py` REQUIRED_SETTINGS_ASSIGNMENTS gains `autonomy.intent = level`, `autonomy.sending = true`, `autonomy.sending = false` (additive). |
| 3 | P10: BC-32 needs `web/server.py`, digest-pinned under ADR-M4-7 | BC-32 moved to owner decisions; ready on `fix/qa6-P10-bc32-owner`; not merged. |
| 4 | P12 builder: session.js assignments pinned whole-set | `tests/web/test_session_wiring.py` REQUIRED_ASSIGNMENTS: +`shownTitle = title`, +`banner.textContent = KILLED_BANNER`, `input.value` entry now reads `shownTitle` (the old one encodes BC-25's stale pre-fill). |
