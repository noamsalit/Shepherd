# Projects backend + the dark UI redesign — execution plan

## Metadata

- Created: 2026-09-21
- Status: draft
- Plan Mode: `execution_plan`
- Verification Rigor: `critical_path` (irreversible migration · security-adjacent
  allowlist · a delete state machine · two concurrent discovery lanes)
- Branch / base: `integration` @ `4761c1d`
- Python: `/root/Shepherd/.venv/bin/python` (3.12)
- Supersedes: `docs/backlog/2026-09-21-projects-work-sources-and-ui.md` §W1, with
  real tasks. §W2 and §W3 stay in the backlog.

---

## Agreement Snapshot

- **Goal:** make a project a *declared* object with a lifecycle (migration 004,
  a repo↔project join table, seven verbs, a reserved `Unassigned`, a verb-side
  delete cascade), then replace the web UI with the dark redesign across
  Shepherd, Flock, Projects and Settings — with the Projects page as the
  acceptance test for the five lifecycle verbs.
- **Constraints (load-bearing, all measured):**
  1. `tests/boundaries/consumer_manifest.json` byte-freeze. Every path whose
     bytes differ from the step-0b `baseline` appears in **exactly one** of
     `rebase.regenerated_paths` or `post_milestone.edits`, never both. New files
     and deleted files both count as moved.
     **`web/static/chat.js` may be edited but never deleted or renamed.**
  2. `src/shepherd/web/server.py` is byte-pinned
     (`test_web_server_is_byte_unchanged`), which pins `_CONTENT_TYPES` to
     `.html` / `.js` / `.css`. No fonts, images, SVG files or JSON data files in
     the static tree. Inline SVG in markup is fine.
  3. `tests/boundaries/collected_node_ids.txt` freezes 1480 node ids. **Deleting
     or renaming a frozen test is a `RETIRED_NODE_IDS` entry** in
     `tests/boundaries/test_collected_node_ids.py`, carrying a reason and the
     decision that authorised it.
  4. Migration 001–003 are sha256-pinned and immutable; 004 is append-only, runs
     in the runner's one transaction, and may contain no trigger and no
     semicolon inside a string literal (`migrate.py:76-83`).
  5. `session.workspace_id` is `NOT NULL` (`002:43`) — `Unassigned` is seeded
     **by the migration**, never lazily.
  6. `mypy --strict` with `disallow_any_explicit` over `src/`, and 105 AST
     boundary rules, green at every phase boundary.
  7. Plain ES modules, no build step (D51). No `innerHTML` / `outerHTML` /
     `insertAdjacentHTML` with anything but a single string literal. No
     `setInterval`, no `requestAnimationFrame`. No remote `<script src>` or
     `<link href>`.
- **In scope:** everything in `docs/plans/2026-09-21-projects-and-ui-design.md`
  plus the two live defects that design's recon found (`last_activity_at` never
  written; `discover_repos` with no caller and a docstring about to become
  false).
- **Out of scope:** M5 queues and work-item providers beyond a disabled
  placeholder (W3); bring-your-own-harness; credentials and multi-user auth;
  real sandboxing; Queues and Kanban beyond nav placeholders; model/engine
  per spawned session (U15, deferred); §12's matrix view; D34's LLM verdict
  lane; W2's discovery switches (1) and (2) — only switch (3) is touched here,
  because it *is* D59's policy.
- **Open Decisions:** none. Eight were answered in the design's
  Questions-Resolved table; three more are recorded as
  `Recommended Defaults` below, each unapproved and each with the rejected
  alternative named.

### Recommended Defaults (proposed, NOT approved)

| # | Decision | Recommended | Rejected | Why |
|---|---|---|---|---|
| RD-1 | What happens to `upsert_workspace` | **Delete the verb.** D57 removes match-on-name, and binding stops creating projects, so it has no caller in `src/`. Test fixtures call `create_project(name=…)` instead. | Keep it as a thin alias over `create_project` | A second creation path around the verb the lifecycle is built from is exactly the drift D57 exists to close. Cost: one retired frozen node id (`test_upsert_workspace_updates_a_moved_root_path`) and the ~60-call-site sweep, which is its own task either way. |
| RD-2 | `discover_repos()`'s fate | **Delete `src/shepherd/signals/discovery.py` and `tests/signals/test_discovery.py`.** | Wire it to `add_repo` as a directory-scan helper | Its module docstring names `workspace.root_path` as its whole reason to exist and 004 removes that column. U14 has repo paths typed in the Edit dialog, not scanned, so wiring it would be building a caller to justify a module rather than the other way round. Cost: three retired frozen node ids. Recoverable from git if W3 ever wants a scanner. |
| RD-3 | `workspace.last_activity_at` | **Stop reading the column; derive the value** as `MAX(session.last_event_at)` over the project's sessions, in one read (`reads.project_last_activity`). The column stays in the schema (004 does not drop it) and stays unwritten, and the Projects page sorts on the derived value. | Write the column inside `apply_fold_delta` | A write per folded event on the hot path, to maintain a value one `GROUP BY` already answers, is a second source of truth for a number nothing else needs. **This is a deviation from the design's wording** (*"This design fills it"*) and is listed under Differences From Agreement rather than absorbed. |

---

## Context References — read before starting any task

| Path | Why |
|---|---|
| `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` | The measurement. §I is the byte-freeze worked out exactly, including the `chat.js` pin and the five simulated gate runs. Outranks every other document. |
| `docs/plans/2026-09-21-projects-and-ui-design.md` | The approved design. Its Questions-Resolved and Decisions tables are settled. |
| `docs/design/ui-decisions.md` | U1–U18 with their reasoning. |
| `docs/specs/orchestrator-platform.md` §3 (D22, D38, D47, D48, D51, D57–D65), §12, §13, §17 | §3 is law. A task may not silently reverse a row. |
| `CLAUDE.md` | tmux `-L` rule, inert-fixture rule, frozen-probe rule. Safety, not style. |
| `docs/plans/m4-blockers/README.md` | Why the ledger is one file per task. |
| `src/shepherd/toolsurface/tools_rename.py` | The smallest complete worked example of registering a verb. |
| `src/shepherd/store/migrations/002_m2_stop_verdicts.sql` | The `PRAGMA defer_foreign_keys=ON` idiom 004 copies rather than re-derives. |
| `src/shepherd/runner/pane.py` | Already parses the permission and trust dialogs from the frozen probe captures. U17 extends it; it does not start over. |
| `/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/ui/shepherd-dark.html` | The clickable prototype the UI must match. 3855 lines: ~1841 CSS, ~280 markup, ~1670 script. |
| `docs/probes/2026-09-14-schemas/tmux-tui/` | **Frozen evidence, read-only.** U17's parser is built and tested against these captures; not one byte of them is edited. |

**Durability horizon.** The store verbs, the migration and the tool surface are
**stable** (architectural, survive milestones). The route table and the
projections are **stable**. The page modules are **near-term-refactor** — W3's
work sources will reopen `projects.js` and `settings.js`. The prototype-porting
notes are **session-only**.

---

## Codebase Reality Check — what the source says, against the documents

Nine findings. Six confirm the design; **three contradict a document and are
stated here rather than planned around.**

1. **CONFIRMS.** `POST_ROUTES` holds 10 entries today
   (`web/routes.py:71-85`); `tests/web/test_routes_m3.py:112` asserts
   `checked == len(routes.POST_ROUTES) - 1 == 9`. Five new POST routes make it
   `== 14`.
2. **CONFIRMS.** `tests/web/test_routes.py:89-114` is a closed-set literal of
   all 11 GET paths, widened by hand.
3. **CONFIRMS.** `moved_paths` (`tests/boundaries/_imports.py:229-240`) uses
   `was.get(path) != now.get(path)`, so absent-on-both reads as *not moved* —
   the `chat.js` trap, reproduced independently here before the coordinator's
   correction arrived. `web/static/chat.js` is in `rebase.regenerated_paths`
   and **not** in `baseline`; deleting it makes the equality unsatisfiable and
   unrepairable. **It keeps its filename.**
4. **CONFIRMS.** `tests/web/test_frontend_no_build_step.py::test_no_remote_script_sources`
   already forbids a remote `<link href>`, so the drop-the-webfont decision is
   mechanically enforced and needs no new test.
5. **CONFIRMS.** The prototype contains no `setInterval` and no
   `requestAnimationFrame`, so `test_no_polling_in_the_ui` survives the port
   unchanged.
6. **CONFIRMS.** `core.stops.PALETTE`'s labels have exactly three consumers
   outside `stops.py` itself — `orchestration/wake.py:139` uses `.glyph` only,
   and two test files. The renames are low blast radius, exactly as designed.
7. **CONTRADICTS `docs/design/ui-decisions.md`.** That file says *"Everything in
   the prototype is `textContent`. §13's no-HTML-sink rule holds in the design
   as written."* **It does not.** The prototype contains **eight** `innerHTML`
   assignments (measured: `grep -c innerHTML` on the prototype == 8). Seven
   build inline SVG icons by string concatenation — lines 2520, 2688, 2796,
   2837, 2858, 3101, 3617 — and one, `prose.innerHTML = line[1]` at line 2814,
   assigns a bare variable.
   `tests/web/test_frontend_escaping.py::unsafe_sinks` allows a sink
   only when its right-hand side is a **single** quoted literal with no
   concatenation, so **all eight are findings**. Every one must become DOM
   construction (`document.createElementNS` for SVG) or static markup in
   `index.html` before it ships. Budgeted as its own task (T6.1).
8. **CONTRADICTS `docs/design/ui-decisions.md`.** That file says *"Spend one
   `post_milestone` declaration on the whole redesign."* `post_milestone_paths`
   (`_imports.py:242-266`) asserts `len(seen) == len(set(seen))` — entries are
   **per path, not per edit**. The redesign needs **one entry per moved path**:
   seven here (`rail.js` rewritten, `escape.js`, `fleet.js`, `flock.js`,
   `projects.js`, `settings.js`, and any further new module). The recon is right
   and the UI-decisions sentence is loose; the plan follows the recon.
9. **CONTRADICTS nothing, but is not in any document.**
   `tests/boundaries/collected_node_ids.txt` freezes **1480 node ids**, and
   `test_collected_node_ids.py` asserts the frozen set is a subset of the live
   one unless a `RETIRED_NODE_IDS` entry names the absence with a reason and an
   authorising decision. This work retires **fifteen**: seven in
   `tests/web/test_rail.py`, four in `tests/orchestration/test_admission.py`,
   three in `tests/signals/test_discovery.py`, one in
   `tests/store/test_store_delegation.py`, and one in
   `tests/web/test_frontend_escaping.py`. No document mentions this gate. It is
   the single most likely way this project goes red in a way nobody predicted,
   so every retirement is named in the task that causes it.

**Corollary the plan obeys everywhere:** *prefer rewriting a test's body to
renaming it.* `tests/web/test_fleet_page.py` (17 frozen ids) keeps its filename
and every function name even though `fleet.js` becomes `flock.js`; only the
string literals inside change. Same for `tests/web/test_palette.py` (7) and
`tests/web/test_session_wiring.py` (10).

---

## Hidden-Assumption Pass

| # | Assumption | Class | Evidence / what would falsify it |
|---|---|---|---|
| A1 | Migration 004's SQL applies clean with `foreign_key_check` empty against real 001–003 with real rows | `proven_by_code` | Rehearsed before the design was written (design §"Migration 004, rehearsed"). T1.1 re-proves it as a test rather than trusting the rehearsal. |
| A2 | `ALTER TABLE repo DROP COLUMN workspace_id` succeeds on the FK-referencing side | `proven_by_code` | Probed against SQLite 3.45.1 (design Questions-Resolved). T1.1 asserts the host's `sqlite3.sqlite_version` is ≥ 3.35 so the probe's answer applies here. |
| A3 | A `HUMAN`-audience call to a `local_destructive` tool needs no approval card | `proven_by_code` | `toolsurface/policy.py` module docstring, DP2/K23: the `HUMAN` column allows without a card. So the Projects page's buttons work through `invoke()` without a dialog. |
| A4 | New routes are permitted by the additive gate | `proven_by_code` | `test_the_pre_m4_route_mappings_are_unchanged` (`test_consumer_surface_additive.py:170`) is a **subset** check; adding is allowed, re-pointing an existing route is not. |
| A5 | `playwright` + chromium work headless in this venv | `proven_by_code` | `import playwright` succeeds; `tools/render_check.py` already ran against the prototype and wrote `scratchpad/ui/shots/`. |
| A6 | `esprima` is importable but is **not** a declared dependency | `proven_by_code` | `import esprima` succeeds; `pyproject.toml:15` lists only `claude-agent-sdk` and `anyio`. **Therefore no suite test may import it.** It is used from `tools/`, in an acceptance command, never from `tests/`. |
| A7 | Deleting `fleet.js` and adding `flock.js` passes the freeze with two `post_milestone` entries | `proven_by_code` | Simulated through the real helpers; recon §I "Proven, not asserted". |
| A8 | `runner/pane.py`'s `PaneState.dialog_text` carries the permission dialog's full text, so U17's choices can be parsed from it without a new capture path | `inferred` | `pane.py:215` `_is_permission_dialog` already detects the dialog from `PERMISSION_MARKER` plus a numbered option line; `dialog_text` is populated for that kind. **Falsified if** `dialog_text` turns out to be truncated to the marker line — T8.1's first act is to assert the frozen capture's numbered lines survive into `dialog_text`, and to stop and report if they do not. |
| A9 | Deriving `last_activity_at` at read time is fast enough for the Projects page | `inferred` | One `GROUP BY` over `session`, a table this deployment holds in the hundreds. No index is added for it; if it ever matters, `ix_session_workspace` is a later migration, not this one. |
| A10 | The `unassigned` project's `owner_id` of `'local'` matches what every other row uses | `needs_user_confirmation` → resolved by code | `001_m1_foundation.sql:30-37` gives `workspace.owner_id` a default; T1.1 reads the default out of the schema and seeds with it rather than hard-coding `'local'` twice. Single definition site. |

---

## Behavior Contract (critical_path)

### `delete_project` — the state machine

`delete_project(workspace_id, on_running)` where
`on_running ∈ {"refuse", "kill", "orphan"}`, default `"refuse"`.

| Given | `on_running` | Then |
|---|---|---|
| `workspace_id == "unassigned"` | any | **Refused.** `deleted=False`, `refused="the Unassigned project cannot be deleted"`. Nothing is written. |
| no such project | any | **Refused**, `refused="there is no project …"`. Nothing is written. |
| project exists, **no** running sessions | any | Deleted. Cascade order inside one writer transaction: `mailbox_message` → `session` → `project_repo` → `workspace`. `repo` rows are **kept**. |
| project exists, ≥1 running session | `"refuse"` | **Refused**, `refused` names the count, `running=(session_id, …)`. Nothing is written. The page renders the three choices from this. |
| project exists, ≥1 running session | `"kill"` | Each running session is killed through the existing kill path, then the cascade runs. `killed=(…)`. |
| project exists, ≥1 running session | `"orphan"` | Each session's `workspace_id` is set to `"unassigned"`; the project's remaining rows cascade; the orphaned sessions survive and stay visible on Flock. `orphaned=(…)`. |
| `on_running` is any other string | — | **Refused** at the schema (`enum` in `input_schema`), before the handler. |

**Invariant, and it is the reason `orphan` is a correctness requirement not a
courtesy:** `Store.fleet()` is an **INNER** `JOIN workspace`
(`reads.py:~205-215`). A session whose workspace row vanished disappears from
the Flock page with no trace. So no code path may leave a `session` row pointing
at a deleted `workspace`.

### Binding, after the join table

`bind_cwd_to_repo(store, cwd)` **never raises** (`binding.py:213`). That contract
is kept verbatim.

| Branch | Today | After |
|---|---|---|
| not a repo (`:223`) | `upsert_workspace(basename(cwd), cwd)` | `workspace_id = "unassigned"`, anomaly counted as today |
| bare repo (`:232`) | `upsert_workspace(basename(cwd), cwd)` | `workspace_id = "unassigned"`, anomaly counted as today |
| new repo (`:251`) | creates a workspace **and** a repo | creates the **repo only**, unattached to any project; `workspace_id = "unassigned"` |
| known common dir (`:240-247`) | reads `known.workspace_id` off the repo row | resolves through `project_repo`: exactly one project → that one; more than one → `"unassigned"` (D60); none → `"unassigned"` (D59) |

### `_registered_roots` — §13's allowlist, after D57

Population becomes **the project's registered repo paths alone**. Three
properties survive verbatim and are asserted by name:

- matching is over **path components**, never strings (`admission.py:184`);
- **innermost wins** (D22, `:188`);
- an empty allowlist is a **refusal**, not permission (`:170-175`);
- and the mirror half at `:141-143`: a stored path that will not canonicalize
  is **named and refused**, never silently dropped — because a silent drop
  narrows the allowlist and then lies about it.

---

## Edge-Case Catalogue (critical_path)

| # | Edge case | Where it is decided | Test |
|---|---|---|---|
| E1 | `/work/api` and `/personal/api` — two projects, same basename | `create_project` (no name match) | `test_two_projects_may_share_a_name` — **must fail against today's code before the fix lands** |
| E2 | migration 004 run twice | `migrate.py`'s `schema_migration` ledger | `test_migration_004_is_idempotent_across_two_runs` |
| E3 | 001–003 edited after being applied | `migrate.py:141-153` sha256 | `test_the_recorded_checksums_of_001_to_003_are_unchanged` |
| E4 | a repo in two projects, session discovered | `bind_cwd_to_repo` steady-state branch | `test_a_repo_in_two_projects_binds_a_discovered_session_to_unassigned` |
| E5 | a repo in **no** project (last project deleted) | same branch | `test_an_orphaned_repo_binds_to_unassigned_and_the_repo_row_survives` |
| E6 | re-adding a path whose repo row was orphaned | `add_repo` + `ux_repo_path` | `test_re_adding_an_orphaned_path_rebinds_the_same_repo_row` |
| E7 | `add_repo` onto `"unassigned"` | `add_repo` guard | `test_unassigned_refuses_add_repo` |
| E8 | `rename_project("unassigned", …)` | guard | `test_unassigned_refuses_rename` |
| E9 | `delete_project("unassigned")` | guard | `test_unassigned_refuses_delete` |
| E10 | `add_repo` with a path that will not canonicalize | `add_repo` | `test_add_repo_refuses_a_path_that_does_not_canonicalize` |
| E11 | spawn into a project with zero repos | `_registered_roots` → empty | `test_a_project_with_no_repo_refuses_everything` |
| E12 | a stored repo path that stops canonicalizing after registration | `admission.py:141-143` | existing `test_a_registered_root_that_will_not_canonicalize_refuses_and_names_itself`, body rewritten, **node id kept** |
| E13 | `delete_project` while a session is mid-turn | `on_running="refuse"` default | `test_delete_refuses_by_default_and_names_the_running_sessions` |
| E14 | tool handler raises | `registry.py:69` → `"request failed (correlation_id=…)"` | `test_the_projects_page_renders_the_correlation_id` |
| E15 | every page hidden at once (U18) | `[hidden] { display: none !important }` in `app.css` | `test_app_css_carries_the_hidden_reset` + the live render check |
| E16 | a `needs_you` pane the parser cannot read | `read_decision` returns `None` | `test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses` |
| E17 | C15's workspace-trust dialog | `PaneKind.TRUST` recognised explicitly | `test_the_trust_dialog_is_named_and_never_answered_blind` |
| E18 | an **attached** session (no pty of ours) | card renders read-only | `test_an_attached_session_renders_the_decision_read_only` |
| E19 | a session with no timestamp at all (U8) | `never seen`, not `just now` | `test_a_session_with_no_timestamp_reads_never_seen` |
| E20 | an **idle** session | no decision card at all (U11) | `test_an_idle_session_gets_no_decision_card` |

---

## Provable Properties (critical_path)

Each is a property, not an example. Each names the test that proves it and the
mutation that would make that test red.

| # | Property | Proved by | Mutation that reddens it |
|---|---|---|---|
| P1 | **Total over the delete matrix.** Every `(exists, has_running, on_running)` triple has a defined outcome and none is silent. | `test_delete_is_total_over_its_matrix` builds `itertools.product` at test time and asserts every cell is reached. | Remove one branch from `delete_project`. |
| P2 | **No orphaned session row.** After any `delete_project` outcome, `SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)` is 0. | `test_no_session_ever_points_at_a_deleted_project`, run after every cell of P1's matrix. | Reorder the cascade to delete `workspace` first. |
| P3 | **The FK graph is intact after 004.** `PRAGMA foreign_key_check` returns no rows against a database carrying real 001–003 rows. | `test_migration_004_leaves_foreign_key_check_empty` | Drop the `project_repo` backfill. |
| P4 | **Binding never raises.** Over a matrix of cwd shapes (missing dir, NUL byte, bare repo, worktree, plain dir, unreadable dir), `bind_cwd_to_repo` returns a `RepoBinding` for every one. | `test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix` | Let one branch propagate `OSError`. |
| P5 | **The allowlist never silently narrows.** For every stored path, either it is in the returned roots or the call is a `SpawnRefused` that names it. | `test_every_registered_path_is_either_admitted_or_named_in_the_refusal` | Replace the refusal at `:141-143` with a `continue`. |
| P6 | **One label table.** The page's `BUCKET_LABEL` equals `PALETTE[b].label` for all eight buckets, and the page's CSS hexes equal `PALETTE[b].colour`. | existing `test_palette_matches_core_stops`, body's filename literals updated, **node id kept** | Change a label in the JS without changing `stops.py`. |
| P7 | **The page never re-derives the order.** No `.sort(`, `localeCompare`, `BUCKET_ORDER` or `FLEET_STATE_ORDER` in any shipped module. | existing `test_the_page_does_not_re_derive_the_order`, module list widened | Port the prototype's `fleetSortKey`. |
| P8 | **Zero HTML sinks.** `unsafe_sinks()` over every `static/*.js` returns `[]`. | existing `test_no_unescaped_interpolation_in_frontend` | Port any one of the prototype's nine `innerHTML` assignments verbatim. |
| P9 | **The freeze equality holds.** `moved_paths(baseline, files) == regenerated_paths ∪ post_milestone_paths`, and the two are disjoint. | existing `test_a_rebase_declares_every_path_whose_digest_moved` | Add `flock.js` without declaring it; or declare `app.css` twice. |
| P10 | **No frozen test vanished unaccounted.** The step-0b node-id set minus `RETIRED_NODE_IDS` is a subset of the live set. | existing `test_collected_node_ids` | Delete `tests/web/test_rail.py` without a retirement entry. |
| P11 | **Every served page renders.** Six pages × two viewports, zero console errors, no horizontal overflow, required content present — **against a real `controld` on loopback**. | `tools/render_check.py --url` driven by `tests/web/test_render_live.py` (`@pytest.mark.live`) | Omit the `[hidden]` reset; ship a module with a syntax error. |
| P12 | **Every POST route's declared body field is a real property of its tool's schema.** | existing `test_every_api_and_body_field_is_a_property_of_its_tool`, arrival count moved to 14 | Declare `on_running` in `BODY_ARGS` but omit it from `delete_project`'s schema. |

---

## Purity Boundary Map (critical_path)

| Layer | Pure? | What may cross |
|---|---|---|
| `core/stops.py` `PALETTE` | pure data | label/colour/glyph/who_acts. The **only** label table. |
| `runner/pane.py` (incl. new `read_decision`) | **pure** — bytes + format fields in, dataclasses out. No clock, no I/O, no process. | `PaneState` → `DecisionPrompt \| None` |
| `store/reads.py`, `store/writes.py` | take a `sqlite3.Connection`, no clock beyond `_now()` | rows → dataclasses |
| `store/db.py` `Store` | the one writer thread | delegation only, no logic |
| `signals/binding.py` | I/O (git subprocess), never raises | `RepoBinding` |
| `orchestration/admission.py` | filesystem `resolve()` only | `Path` list or `SpawnRefused` |
| `toolsurface/tools_projects.py` | composition + projection | `dict[str, object]` |
| `web/routes.py` | a path→name table. **No logic, ever.** | `Resolved` |
| `web/static/*.js` | DOM only, `textContent` only | — |

The two new pure seams (`read_decision`, and `delete_project`'s outcome
dataclass) are where the critical-path tests attach. Nothing in `web/` decides
anything.

---

## Safety Rules — absolute, for every task in this plan

These are not style. Each one is here because it has already cost this repo
something.

1. **`tmux`: pass `-L` on every invocation. Never `kill-server` without it.**
   The user's live sessions are on the `shepherd` socket (`m3`, `master`) —
   never named in a write, never touched. A command run *inside* tmux inherits
   `$TMUX` and resolves to that session's own socket, so `-L` on the session is
   not enough. Never put `:` in a session name. **No task in this plan creates,
   attaches to, or tears down a tmux session**; if a revision needs one it uses
   a throwaway socket (`tmux -L shepherd-render …`) for every command, teardown
   included.
2. **Never write anywhere under `~/.claude/`.** The engine's config directory is
   injected as a value and is never defaulted to the user's real one — that is
   why `rename_session` made it required.
3. **A planted violation is an inert fixture that nothing imports.** It lives in
   `tests/boundaries/fixtures/`, is read as text or parsed as an AST, and is
   never on an import path the suite executes. A shadow tree isolates *files*;
   it does not isolate signals, subprocesses, sockets, ports or the host. Never
   plant a signal, a `kill`, a reboot-capable call or a teardown verb into
   executable code at all.
4. **`docs/probes/` is frozen evidence.** Phase 8 builds a parser *against* it
   and edits not one byte of it. `git status --porcelain docs/probes/` is in
   T8.1's and T10.2's required checks for exactly this reason.
5. **Never `rm -rf` under the repo except `__pycache__`.** Deletions in this
   plan are of named files, one at a time, each with its manifest declaration
   and its node-id retirement.
6. **Clear `__pycache__` before any mutation run** — a size-preserving mutation
   landing in the same second as the last compile re-imports the *unmutated*
   bytecode and records a false survivor.

## Durable Decisions — the facts every phase references

These are written once here and never re-decided inside a phase. A task that
finds itself choosing one of these has drifted.

| Surface | The decision | Phase that establishes it |
|---|---|---|
| **Schema version** | `EXPECTED_SCHEMA_VERSION = 4`; one migration, `004_projects.sql`, append-only, `00N_` numbering | 1 |
| **Project identity** | `workspace.id`. Names are labels and two projects may share one. | 1 |
| **Repo↔project** | the `project_repo` join table; `repo` has no `workspace_id` | 1 |
| **Reserved project** | the literal id `"unassigned"`, defined once at `store.models.UNASSIGNED_PROJECT_ID`, seeded by 004 | 1 |
| **Delete semantics** | cascade in the verb, ordered `mailbox_message → session → project_repo → workspace`, inside the one writer transaction; `on_running` defaults to refuse | 1 |
| **Orphaned repo rows** | kept, to preserve D48 binding identity under `ux_repo_path` | 1 |
| **Discovery policy** | `bind_cwd_to_repo` is the one chokepoint; it creates no project and binds to `"unassigned"` in every branch that cannot resolve one | 2 |
| **Allowlist model** | §13's population is the project's registered repo paths alone; component matching, innermost wins, empty means refuse, an uncanonicalizable path is named and refused | 2 |
| **Blast classes** | `create_project` / `add_repo` / `delete_project` = `LOCAL_DESTRUCTIVE`; `rename_project` / `remove_repo` = `LOCAL_WRITE`; `list_repos` / `get_project` = `LOCAL_READ`; audiences `{MASTER, HUMAN}` | 3 |
| **Auth posture** | a `HUMAN`-audience call needs no approval card (`policy.py`, DP2/K23), so the Projects page's buttons work through `invoke()` unchanged. Nothing in this project adds an auth surface. | 3 |
| **API shape** | 14 GET routes, 15 POST routes; `web/routes.py` stays a path→tool table with no logic; additions only, never a re-point | 4, 8 |
| **Third-party boundary** | none added. No npm, no build step, no CDN, no webfont, no new file type — `web/server.py` is byte-pinned and `_CONTENT_TYPES` is `.html`/`.js`/`.css`. | 5 |
| **Label source of truth** | `core.stops.PALETTE`. There is no UI-side label table, ever. | 6 |
| **Module filenames** | `fleet.js` → `flock.js`; **`chat.js` keeps its name** (ADR-P3); new modules `projects.js`, `settings.js` | 5–9 |
| **Ordering** | server-side only (`fleet_bucket_sort_key`). The page renders the order it is handed. | 6 |

## Phase Dependency Map

| Phase | Depends on | Enables |
|---|---|---|
| 0 — tooling and ledger | — | 10 (the live check's harness), every task (the ledger) |
| 1 — migration + store | 0 | 2, 3 |
| 2 — binding, discovery, admission | 1 | 3 |
| 3 — tool surface | 1, 2 | 4 |
| 4 — routes | 3 | 8, 9 |
| 5 — UI shell + D66 | 0, 4 | 6, 7, 8, 9 |
| 6 — Flock page | 5 | 7, 8, 9 |
| 7 — Shepherd + Settings | 6 | 10 |
| 8 — U17 decision card | 4, 6 | 10 |
| 9 — Projects page | 4, 6 | 10 |
| 10 — live verification | 7, 8, 9 | the release gate |

No forward references: every phase's dependencies are strictly earlier. The two
UI leaves (8 and 9) are independent of each other and may run in either order,
but **not concurrently** — both edit `index.html`, `app.css` and
`tests/boundaries/consumer_manifest.json`, and two builders editing one manifest
is the M3 shared-ledger hazard wearing a different hat.

## Phase Plan

Eleven phases. **The suite is green at every phase boundary.** Where a phase's
internal task boundaries are *not* green, the phase says so and why.

Legend: **AFK** = `checkpoint_type: none`. **HITL** = human checkpoint, with a
reason category.

---

### Phase 0 — Verification tooling and the ledger

**Objective:** make the acceptance commands real before anything they decide
exists. Every later clause names a file this phase builds.
**Autonomy:** AFK.
**Test Seams:** unit (argument parsing); integration (the tool against a
throwaway static server).
**What this phase does NOT prove:** that any page is correct. It proves only
that the checker can reach a served page and that it fails on a page it should
fail on.

#### Task 0.1 — `render_check.py` learns to point at a server

- **Files:** `tools/render_check.py`, `tools/js_syntax_check.py` *(new)*,
  `tests/tools/test_render_check_args.py` *(new)*
- **Dependencies:** none
- **Allowed Scope:** argument handling (`--url` for a served origin, `--file`
  for the prototype), the page list becoming a module-level constant
  `PAGES` with the six real page ids, `--fail-on-empty` arrival check.
- **Out-of-Scope Drift:** changing any assertion the tool already makes;
  touching `src/`; adding `tools/` to `pythonpath` in `pyproject.toml`.
- **Expected Artifacts:** `render_check.check(origin: str, shots: Path) -> int`
  accepting both `http(s)://…` and a filesystem path.
- **Required Checks:** `.venv/bin/python -m pytest tests/tools -q`;
  `.venv/bin/mypy --strict tools/render_check.py` *(advisory — `pyproject.toml`
  sets `mypy_path = "src"` and `pythonpath = ["src"]`, so `tools/` is outside
  both; the command is recorded so the next reader knows it was run, not that
  it gates)*.
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `tests/tools` passes; the tool still runs against the
  prototype file and reports the same failure count as before the change;
  `grep -rn "esprima" tests/` is empty (A6).

> **Import mechanics, stated because guessing them is how this task stalls.**
> `pyproject.toml:51` sets `pythonpath = ["src"]`, so `import render_check`
> does **not** work from a test. `tests/tools/test_render_check_args.py` loads
> the tool by path with
> `importlib.util.spec_from_file_location("render_check", REPO_ROOT / "tools" / "render_check.py")`.
> No `tests/tools/__init__.py` — `tests/store/` has none either, and nothing
> cross-imports this package (`tests/web/__init__.py` exists only because
> `from web.conftest import Client` needs it).
- **Consumes:** none
- **Produces:** `tools/render_check.py::check(origin, shots)`,
  `tools/render_check.py::PAGES`,
  `tools/js_syntax_check.py::main(paths) -> int`

> `tools/js_syntax_check.py` imports `esprima`. **No file under `tests/` may
> import it** — `esprima` is not in `pyproject.toml`'s dependencies (A6), and a
> suite import would make a green run depend on an undeclared package. It is an
> acceptance command, not a gate.

#### Task 0.2 — the blockers ledger, one file per task

- **Files:** `docs/plans/projects-ui-blockers/README.md` *(new)*
- **Dependencies:** none
- **Allowed Scope:** the directory and its README, stating the rule.
- **Out-of-Scope Drift:** writing any entry.
- **Expected Artifacts:** the directory exists with its rule written down.
- **Required Checks:** `test -d docs/plans/projects-ui-blockers`
- **Validation Level:** Manual (file exists).
- **Checkpoint Type:** none
- **Exit Criteria:** README states: one file per task, named
  `docs/plans/projects-ui-blockers/<task-id>.md` (e.g. `t1-1.md`); nobody opens
  another task's file; entries are `T<id> · symptom · what was tried · what it
  blocks · owner`; ids are never reused; an entry is never deleted, only
  retired in place. **Never a shared ledger** — M3 lost two tasks' entries that
  way.
- **Consumes:** none
- **Produces:** `docs/plans/projects-ui-blockers/` (the per-task ledger root)

---

### Phase 1 — Migration 004 and the store's project model

**Objective:** the schema and the store verbs the whole project rests on.
**Autonomy:** AFK, except T1.1's exit which is **HITL (`manual-verification`)** —
an irreversible migration gets one human look at the applied schema before the
rest of the tree is built on it.
**Test Seams:** unit (`store/writes.py`, `store/reads.py` against an in-memory
connection); integration (`Store` across its one writer thread); integration
(the migration runner against a real file database with real rows).
**Green at the boundary:** yes.
**Green at T1.1→T1.5 boundaries:** **no, by construction.** `repo.workspace_id`
cannot both exist and not exist, so the expand–contract sequence is unavailable
for a single rehearsed migration. The design settled on one migration; this plan
does not reopen it. The tasks below share Phase 1's green promise and nothing
outside Phase 1 may start until it is kept.
**What this phase does NOT prove:** that any caller uses the new verbs; that
binding, admission, the tool surface or any page behave. Five verbs with no
caller are five unproven verbs — Phase 9 is where they are proved.

#### Task 1.1 — migration 004

- **Files:** `src/shepherd/store/migrations/004_projects.sql` *(new)*,
  `src/shepherd/store/migrate.py` (one constant),
  `tests/store/test_migration_004.py` *(new)*
- **Dependencies:** none
- **Allowed Scope:** the SQL exactly as the design rehearsed it, plus
  `PRAGMA defer_foreign_keys=ON` copied from `002:37`; `EXPECTED_SCHEMA_VERSION`
  `3 → 4`.
- **Out-of-Scope Drift:** touching 001–003 (sha-pinned); adding a trigger (the
  splitter cannot parse one); a semicolon inside a string literal; numbering
  outside `00N_` (discovery is lexical, `migrate.py:55`); rebuilding `session`.
- **Expected Artifacts:** `004_projects.sql` containing, in order:
  `ALTER TABLE workspace ADD COLUMN description TEXT;`
  `CREATE TABLE project_repo (workspace_id … REFERENCES workspace(id), repo_id … REFERENCES repo(id), added_at …, PRIMARY KEY (workspace_id, repo_id));`
  `INSERT INTO project_repo … SELECT workspace_id, id, added_at FROM repo;`
  `ALTER TABLE repo DROP COLUMN workspace_id;`
  `ALTER TABLE workspace DROP COLUMN root_path;`
  `CREATE INDEX ix_repo_common_dir ON repo(git_common_dir);`
  `INSERT INTO workspace (id, owner_id, name, description, created_at) VALUES ('unassigned', …);`
- **Required Checks:**
  `.venv/bin/python -m pytest tests/store/test_migration_004.py tests/store/test_migrations.py tests/store/test_migration_002.py tests/store/test_migration_003.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** **human_verify** — print `PRAGMA table_info` for
  `workspace`, `repo` and `project_repo` from a migrated copy of a real
  database and have a person read it once.
- **Exit Criteria:** all of —
  (a) applies clean over a database built by 001→003 **with rows in `workspace`,
  `repo`, `session` and `mailbox_message`**;
  (b) `PRAGMA foreign_key_check` returns no rows;
  (c) every pre-existing `repo` row has exactly one `project_repo` row with the
  same `added_at`;
  (d) the `unassigned` row exists with `owner_id` read from the schema's own
  default, not hard-coded twice;
  (e) re-running `migrate()` is a no-op;
  (f) the recorded sha256 of 001–003 is unchanged;
  (g) `sqlite3.sqlite_version` is asserted `>= "3.35"`, so A2's probe applies on
  this host and a future host that regresses says so.
- **Consumes:** none
- **Produces:** `004_projects.sql`, `project_repo` (table),
  `ix_repo_common_dir`, `workspace.description`,
  `EXPECTED_SCHEMA_VERSION = 4`, the seeded project id `"unassigned"`

#### Task 1.2 — models and rows

- **Files:** `src/shepherd/store/models.py`, `src/shepherd/store/rows.py`
- **Dependencies:** T1.1
- **Allowed Scope:** `Workspace` loses `root_path`, gains `description: str | None`;
  `Repo` loses `workspace_id`; new
  `UNASSIGNED_PROJECT_ID: Final[str] = "unassigned"` — **the one definition
  site** (`tests/boundaries/test_one_definition_site.py` is the rule); new
  `OnRunning(StrEnum)` with `REFUSE`/`KILL`/`ORPHAN`; new frozen
  `DeleteOutcome(deleted, refused, running, killed, orphaned)`.
- **Out-of-Scope Drift:** touching `Session`, `FleetRow` or any stop field.
- **Required Checks:**
  `.venv/bin/mypy --strict src/shepherd/store` ·
  `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `mypy --strict` clean over `src/shepherd/store`; the 105
  boundary rules green.
- **Consumes:** `project_repo`, `workspace.description`
- **Produces:** `shepherd.store.models.UNASSIGNED_PROJECT_ID`,
  `shepherd.store.models.OnRunning`,
  `shepherd.store.models.DeleteOutcome`,
  `Workspace(id, owner_id, name, description, created_at, last_activity_at)`,
  `Repo(id, owner_id, name, root_path, git_common_dir, vcs_remote, active, added_at)`

#### Task 1.3 — reads

- **Files:** `src/shepherd/store/reads.py`, `tests/store/test_verbs.py`
- **Dependencies:** T1.2
- **Allowed Scope:** `list_repos` keeps its signature and its
  `ORDER BY root_path`, body becomes a join through `project_repo`; new
  `get_workspace`, `projects_for_repo`, `project_last_activity`,
  `running_sessions_for`. `fleet()` stays an INNER JOIN — unchanged.
- **Out-of-Scope Drift:** changing `fleet()`'s ordering or its join kind;
  touching `snapshot`, `wake_candidates` or anything in the stop group.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/store -q` ·
  `.venv/bin/mypy --strict src/shepherd/store`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `tests/store` green; `list_repos`'s order assertion
  survives unchanged.
- **Consumes:** `UNASSIGNED_PROJECT_ID`, `project_repo`
- **Produces:**
  `reads.get_workspace(connection, workspace_id: str) -> Workspace | None`
  `reads.list_repos(connection, workspace_id: str) -> list[Repo]`
  `reads.projects_for_repo(connection, repo_id: str) -> list[str]`
  `reads.project_last_activity(connection) -> dict[str, str]`
  `reads.running_sessions_for(connection, workspace_id: str) -> list[Session]`

#### Task 1.4 — the lifecycle writes

- **Files:** `src/shepherd/store/writes.py`, `tests/store/test_verbs.py`
- **Dependencies:** T1.3
- **Allowed Scope:** `create_project`, `rename_project`, `delete_project`,
  `add_repo`, `remove_repo`. `upsert_workspace` **deleted** (RD-1).
  `upsert_repo` keeps its name but loses `workspace_id` and becomes the
  path-identity upsert `add_repo` builds on.
- **Out-of-Scope Drift:** killing a session here — `delete_project(on_running="kill")`
  **delegates** to the existing kill path; the store does not learn about
  runners. Adding `ON DELETE CASCADE` anywhere (settled: the cascade lives in
  the verb).
- **Required Checks:**
  `.venv/bin/python -m pytest tests/store -q` ·
  `.venv/bin/mypy --strict src/shepherd/store`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P1 (`test_delete_is_total_over_its_matrix`) and P2
  (`test_no_session_ever_points_at_a_deleted_project`) pass; E1's
  `test_two_projects_may_share_a_name` passes; E7/E8/E9's `Unassigned` refusals
  pass.
- **Consumes:** `OnRunning`, `DeleteOutcome`, `UNASSIGNED_PROJECT_ID`,
  `reads.running_sessions_for`
- **Produces:**
  `writes.create_project(connection, *, name: str, description: str | None) -> Workspace`
  `writes.rename_project(connection, *, workspace_id: str, name: str) -> Workspace | None`
  `writes.delete_project(connection, *, workspace_id: str, on_running: OnRunning, kill: Callable[[str], None]) -> DeleteOutcome`
  `writes.add_repo(connection, *, workspace_id: str, root_path: str, name: str, git_common_dir: str, vcs_remote: str | None) -> Repo`
  `writes.remove_repo(connection, *, workspace_id: str, repo_id: str) -> bool`

#### Task 1.5 — the `root_path` sweep across the fixtures

- **Files:** the 35 test modules that call `upsert_workspace` (measured:
  `grep -rl "upsert_workspace" tests/ --include=*.py | wc -l` == 35) plus those
  that read `Workspace.root_path` / `Repo.workspace_id` — enumerated by
  `grep -rln "upsert_workspace\|root_path" tests/ --include=*.py` — plus
  `tests/golden/corpus.py` (whose `Binding` dataclass carries `root_path`), and
  `tests/boundaries/test_collected_node_ids.py` for the one retirement.
- **Dependencies:** T1.4
- **Allowed Scope:** mechanical only: `store.upsert_workspace(name, root)` →
  `store.create_project(name=name, description=None)` plus, where the fixture
  needed the path to be admissible, `store.add_repo(...)`.
  `tests/golden/corpus.py::Binding.root_path` → `repo_root`.
  **One** `RETIRED_NODE_IDS` entry for
  `tests/store/test_store_delegation.py::test_upsert_workspace_updates_a_moved_root_path`,
  authorised by **D57**, reason: *the column and the verb it pinned are both
  gone; the property it protected (a moved path updates rather than duplicating)
  is now `add_repo`'s and is asserted by E6.*
- **Out-of-Scope Drift:** changing what any test asserts. If a test cannot be
  made green mechanically, **stop and write a ledger entry** rather than
  weakening it.
- **Required Checks:**
  `.venv/bin/python -m pytest -q` (whole suite) ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** whole suite green; exactly one new `RETIRED_NODE_IDS`
  entry; `grep -rn "upsert_workspace" src/ tests/` returns nothing.
- **Consumes:** `writes.create_project`, `writes.add_repo`
- **Produces:** a green suite on the new store shape;
  `tests/golden/corpus.py::Binding(workspace_id, repo_id, repo_root)`

#### Task 1.6 — `Store` delegation

- **Files:** `src/shepherd/store/db.py`,
  `tests/store/test_store_delegation.py`
- **Dependencies:** T1.5
- **Allowed Scope:** one delegating method per new verb, same names, through the
  one writer thread. Remove `Store.upsert_workspace`.
- **Out-of-Scope Drift:** logic in `db.py`. It delegates; it does not decide.
- **Required Checks:** `.venv/bin/python -m pytest tests/store -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_every_delegated_write_crosses_the_one_writer_thread`
  and `test_every_delegated_verb_is_refused_once_the_store_is_closed` cover
  every new verb.
- **Consumes:** every `writes.*` and `reads.*` name from T1.3/T1.4
- **Produces:** `Store.create_project`, `Store.rename_project`,
  `Store.delete_project`, `Store.add_repo`, `Store.remove_repo`,
  `Store.get_workspace`, `Store.projects_for_repo`,
  `Store.project_last_activity`, `Store.running_sessions_for`

---

### Phase 2 — Binding, discovery policy, admission

**Objective:** D59's single chokepoint and D57's allowlist.
**Autonomy:** AFK.
**Test Seams:** unit (`bind_cwd_to_repo` against a temp git tree);
unit (`_registered_roots` against an in-memory store); integration (both
discovery lanes through `discovery_loop` and `hook_lane`).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that the policy is reachable from a UI, or
that a human can create the project a session would otherwise land outside of.
It also does **not** prove the hook lane's *other* three call sites
(`hook_lane.py:165,179,203`) behave under load — only that they get a
`RepoBinding` with a non-null `workspace_id`.

#### Task 2.1 — `bind_cwd_to_repo` binds to `Unassigned`

- **Files:** `src/shepherd/signals/binding.py`, `tests/signals/test_binding.py`
- **Dependencies:** Phase 1
- **Allowed Scope:** the four-branch table in the Behavior Contract; delete
  `_workspace_name`; D62's switch (3) written as a switch and **shipped on**.
- **Out-of-Scope Drift:** making `bind_cwd_to_repo` raise; touching switches
  (1) and (2) — they are W2.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/signals -q` ·
  `.venv/bin/mypy --strict src/shepherd/signals`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P4 passes; E4 and E5 pass; `RepoBinding.workspace_id` is
  still non-optional; the *"never raises"* docstring is unchanged and true.
- **Consumes:** `UNASSIGNED_PROJECT_ID`, `Store.projects_for_repo`,
  `Store.add_repo`
- **Produces:** `bind_cwd_to_repo(store, cwd) -> RepoBinding` with
  `workspace_id` never null and never auto-created

#### Task 2.2 — `discover_repos` is deleted (RD-2)

- **Files:** delete `src/shepherd/signals/discovery.py`, delete
  `tests/signals/test_discovery.py`;
  `tests/boundaries/test_collected_node_ids.py` (three retirements)
- **Dependencies:** T2.1
- **Allowed Scope:** the deletion and the three `RETIRED_NODE_IDS` entries,
  each authorised by **D57** with the reason: *its sole documented justification
  was `workspace.root_path`, which 004 removed; it had no caller in `src/`; U14
  types repo paths rather than scanning for them.*
- **Out-of-Scope Drift:** deleting `probe_repo` or `resolve_remote`, which
  `binding.py` imports.
- **Required Checks:**
  `.venv/bin/python -m pytest -q` ·
  `grep -rn "discover_repos" src/ tests/` (must be empty) ·
  `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** no reference to `discover_repos` anywhere; three retirement
  entries present; suite green.
- **Consumes:** none
- **Produces:** none *(a deletion; the artifact is the absence and its record)*

#### Task 2.3 — the allowlist becomes the repo paths alone

- **Files:** `src/shepherd/orchestration/admission.py`,
  `tests/orchestration/test_admission.py`,
  `tests/boundaries/test_collected_node_ids.py` (four retirements)
- **Dependencies:** T2.1
- **Allowed Scope:** delete the `list_workspaces()` comprehension at
  `:129-133`; use `Store.get_workspace` for existence and `Store.list_repos` for
  the population; rewrite the T11-1 comment block to say what it now means.
  Four retirements — `test_a_repo_registered_outside_its_workspace_root_is_admitted`,
  `test_a_workspace_with_no_root_path_still_admits_its_registered_repos`,
  `test_the_workspace_root_stays_a_permitted_root_beside_the_repos`,
  `test_a_workspace_with_neither_a_root_nor_a_repo_refuses_everything` — each
  authorised by **D57** and each replaced by a named successor in the same file.
- **Out-of-Scope Drift:** changing component matching to string matching;
  changing innermost-wins; turning an empty allowlist into permission; replacing
  the canonicalize-refusal with a silent drop. **Rewrite the bodies of the other
  eleven frozen tests in this file; do not rename them.**
- **Required Checks:**
  `.venv/bin/python -m pytest tests/orchestration -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` ·
  `.venv/bin/mypy --strict src/shepherd/orchestration`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P5 passes; E11 and E12 pass; the five parametrised escape
  cases (`sibling_of_the_repo`, `repo_name_is_a_string_prefix`,
  `traversal_out_of_the_repo`, `symlink_out_of_the_repo`, `the_repos_parent`)
  still refuse, with their node ids intact.
- **Consumes:** `Store.get_workspace`, `Store.list_repos`
- **Produces:** `_registered_roots(store, workspace_id) -> list[Path] | SpawnRefused`
  over repo paths alone

---

### Phase 3 — The tool surface: seven verbs

**Objective:** one implementation the master and the HTTP API both reach (D58).
**Autonomy:** AFK.
**Test Seams:** unit (`build_project_tools()` schemas); integration
(`invoke()` through the registry with a composed chokepoint).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that any route reaches these tools (Phase 4)
or that a person can drive them (Phase 9).

#### Task 3.1 — `toolsurface/tools_projects.py`

- **Files:** `src/shepherd/toolsurface/tools_projects.py` *(new)*,
  `tests/toolsurface/test_tools_projects.py` *(new)*,
  `tests/toolsurface/test_tools_m3.py` (the module-cap enumeration)
- **Dependencies:** Phase 1, Phase 2
- **Allowed Scope:** seven `ToolDef`s.
  `create_project`, `add_repo`, `delete_project` → `BlastClass.LOCAL_DESTRUCTIVE`
  (D58). `rename_project`, `remove_repo` → `LOCAL_WRITE` (design's ADR row).
  `list_repos`, `get_project` → `LOCAL_READ`.
  Audiences `{MASTER, HUMAN}` for all seven.
  `delete_project`'s schema carries `on_running` as
  `{"type": "string", "enum": ["refuse", "kill", "orphan"]}` with no default in
  the schema and `OnRunning.REFUSE` as the handler's fallback — default-refuse
  must be unskippable by omission.
  **Add the new module to `test_the_three_modules_are_each_under_the_cap`'s
  enumeration** (it asserts `len(sizes) == 5`; it becomes 6) so the 450-line cap
  cannot be escaped by a split. If the module would exceed 450, split it into
  `tools_projects.py` + `tools_projects_reads.py` and name **both** in that
  enumeration.
- **Out-of-Scope Drift:** registering anything in `tools_m1.py` or `tools_m3.py`;
  a schema that is not `{"type": "object", "properties": {...}}` (`register()`
  raises `SchemaInvalid`); inventing an eighth verb.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/toolsurface -q` ·
  `.venv/bin/mypy --strict src/shepherd/toolsurface`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** seven tools register; the cap test names every new module;
  `delete_project` with no `on_running` refuses a project with a running
  session.
- **Consumes:** every `Store.*` name from T1.6, `OnRunning`, `DeleteOutcome`,
  `UNASSIGNED_PROJECT_ID`
- **Produces:**
  `PROJECT_TOOL_NAMES: tuple[str, ...] = ("create_project", "rename_project", "delete_project", "add_repo", "remove_repo", "list_repos", "get_project")`
  `build_project_tools(...) -> tuple[ToolDef, ...]`
  `register_project_tools(*, store: Store, kill: Callable[[str], None], now: Clock) -> None`
  `project_repo_row(repo: Repo) -> dict[str, object]`
  `project_detail(workspace, repos, sessions, last_activity_at) -> dict[str, object]`

#### Task 3.2 — compose wiring and the `project_workspace` projection

- **Files:** `src/shepherd/toolsurface/compose.py`,
  `src/shepherd/toolsurface/tools_m1.py`,
  `tests/toolsurface/test_tools_m1.py`,
  `tests/boundaries/test_composition_root.py`
- **Dependencies:** T3.1
- **Allowed Scope:** call `register_project_tools(...)` **before**
  `install_chokepoint` (`compose.py:457`) and `freeze_registry()` (`:473`).
  `project_workspace()` drops `root_path`, gains `description` and
  `repo_count`, and takes `last_activity_at` as an argument from
  `Store.project_last_activity` (RD-3).
- **Out-of-Scope Drift:** reordering anything else in `compose_tool_surface`;
  changing `fleet_tree`'s ordering.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/toolsurface tests/boundaries -q` ·
  `.venv/bin/mypy --strict src/shepherd`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** a composed process answers all seven; the registry freezes
  without a double-registration refusal; the 105 boundary rules green.
- **Consumes:** `register_project_tools`, `Store.project_last_activity`
- **Produces:** `project_workspace(workspace, *, repo_count: int, last_activity_at: str | None) -> dict[str, object]`
  with keys `project_id`, `name`, `description`, `repo_count`, `last_activity_at`

---

### Phase 4 — Routes

**Objective:** a path→tool table and nothing else.
**Autonomy:** AFK.
**Test Seams:** unit (`resolve` / `resolve_post` over literal paths);
integration (`tests/web/conftest.py::Client` against the real handler).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that any page calls these routes.

#### Task 4.1 — the table

- **Files:** `src/shepherd/web/routes.py`
- **Dependencies:** Phase 3
- **Allowed Scope:** additions only.
  `API_ROUTES` gains `"/api/projects/{project_id}" → "get_project"` and
  `"/api/projects/{project_id}/repos" → "list_repos"` (11 → 13; a third arrives
  in Phase 8).
  `POST_ROUTES` gains `"/api/projects" → "create_project"`,
  `"/api/projects/{project_id}/rename" → "rename_project"`,
  `"/api/projects/{project_id}/delete" → "delete_project"`,
  `"/api/projects/{project_id}/repos/add" → "add_repo"`,
  `"/api/projects/{project_id}/repos/remove" → "remove_repo"` (10 → 15).
  `BODY_ARGS` declares `("name", "description")`, `("name",)`,
  `("on_running",)`, `("root_path",)`, `("repo_id",)` respectively.
- **Out-of-Scope Drift:** re-pointing any existing route (the additive gate
  forbids it); any logic in `routes.py`; declaring a body field that is not a
  property of the tool's schema.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web/test_routes.py tests/web/test_routes_m3.py -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `/api/projects` (2 segments) is never read as
  `/api/projects/{project_id}` (3); `test_the_pre_m4_route_mappings_are_unchanged`
  green.
- **Consumes:** `PROJECT_TOOL_NAMES`
- **Produces:** the seven route templates above

#### Task 4.2 — the two hand-widened literals

- **Files:** `tests/web/test_routes.py`, `tests/web/test_routes_m3.py`
- **Dependencies:** T4.1
- **Allowed Scope:** widen the GET closed-set literal at `test_routes.py:89-114`
  to 13 entries, with a comment saying why — in the same voice as M3's and M4's
  widenings, so the next route still has to be declared here. Change
  `test_routes_m3.py:112`'s `checked == len(routes.POST_ROUTES) - 1 == 9` to
  `== 14`.
- **Out-of-Scope Drift:** loosening either literal into a computed set. A
  closed-set literal is the point; a `len()` comparison alone would pass over a
  route nobody declared.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P12 passes; both literals name every route by hand.
- **Consumes:** the seven route templates
- **Produces:** a green `tests/web` on 13 GET and 15 POST routes

---

### Phase 5 — The UI shell, and the rail's removal

**Objective:** the dark shell — tokens, the `[hidden]` reset, the side pane, six
page roots — and the paperwork for the one decision this reverses.
**Autonomy:** **HITL (`design-decision`)** at the exit: D66 is a numbered spec
row reversing §12, and §0 forbids taking one quietly.
**Test Seams:** unit (static scans of `index.html` / `app.css` / `app.js`);
E2E (the live render check, Phase 10).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that any page has content. The Flock,
Projects and Settings roots are empty shells until Phases 6, 7 and 9. It proves
the shell, the reset, the routing, and that removing the rail was recorded.

#### Task 5.1 — D66 and §12, in the same task that deletes the assertion

- **Files:** `docs/specs/orchestrator-platform.md` (§3 row **D66**, §12's rail
  section rewritten to point at it), delete `tests/web/test_rail.py`,
  `tests/boundaries/test_collected_node_ids.py` (seven retirements),
  `tests/qa/test_s4_needs_you_rail.py`
- **Dependencies:** Phase 0
- **Allowed Scope:** **D66** — *"The Needs-You rail leaves the shell. §12's
  'on every page' is reversed; if the rail returns it lives on the Flock page
  alone (U2)."* — with the owner attribution and the date, in §3's voice. Seven
  `RETIRED_NODE_IDS` entries, all authorised by **D66**.
  `tests/qa/test_s4_needs_you_rail.py` is not frozen; retarget its projection
  assertions at `project_needs_you`, which survives, or delete it with a reason.
- **Out-of-Scope Drift:** deleting `tools_m1.py::project_needs_you` or
  `fleet_summary`'s `needs_you` list — the projection stays; only its renderer
  goes. Writing D66 in a later task than the deletion.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` ·
  `grep -n "D66" docs/specs/orchestrator-platform.md`
- **Validation Level:** Deterministic + Manual (a person reads D66).
- **Checkpoint Type:** **decision** — a numbered reversal of a spec row.
- **Exit Criteria:** D66 exists in §3; §12's rail section points at it; seven
  retirements present and each names D66; suite green.
- **Consumes:** none
- **Produces:** spec row **D66**

#### Task 5.2 — `app.css`: tokens, the reset, the wash

- **Files:** `src/shepherd/web/static/app.css`
- **Dependencies:** T5.1
- **Allowed Scope:** the prototype's stylesheet, token layer first.
  **`[hidden] { display: none !important; }` is mandatory and explicit** (U18) —
  the recon found this is already a live bug in the shipped page, because
  `.chat-view` is `display: grid` (`app.css:483-488`) and only stays hidden
  because JS also sets `.hidden`.
  **The eight `.bucket-<name> { --bucket-colour: #RRGGBB }` rules keep exactly
  that shape** — `tests/web/test_palette.py::_CSS_BUCKET` parses them back out,
  and a `:root`-level `--needs-you` (which is how the prototype spells them)
  would not match. Port the hexes into the existing `.bucket-*` blocks and let
  the prototype's `:root` names alias them.
  U16's ~16% wash of the bucket colour over the card ground.
  **System font stack, no `@font-face`, no remote `<link>`.**
- **Out-of-Scope Drift:** editing `web/static/vendor/`; adding any file that is
  not `.html`/`.js`/`.css`.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web/test_palette.py tests/web/test_frontend_no_build_step.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E15's `test_app_css_carries_the_hidden_reset` passes; all
  eight `.bucket-*` rules parse; `test_no_remote_script_sources` green.
- **Consumes:** none
- **Produces:** `app.css` with `[hidden] { display: none !important }` and the
  eight `.bucket-<name>` rules intact

#### Task 5.3 — `index.html` and `app.js`: the shell and the routing

- **Files:** `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`, delete
  `src/shepherd/web/static/rail.js`, delete
  `src/shepherd/web/static/escape.js`,
  `tests/web/test_frontend_escaping.py`,
  `tests/web/test_session_wiring.py`,
  `tests/boundaries/test_collected_node_ids.py` (one retirement)
- **Dependencies:** T5.2
- **Allowed Scope:** six page roots (`#page-shepherd`, `#page-flock`,
  `#page-queues`, `#page-projects`, `#page-kanban`, `#page-settings`), the side
  pane, the drawer, the header, the three `<dialog>`s. `app.js` owns page
  routing and the one `EventSource`. **The prototype's `herd` page id becomes
  `flock` everywhere**, including `tools/render_check.py::PAGES`.
  `EXPECTED_MODULES` in `test_frontend_escaping.py` is widened by name (never
  into a glob). One `RETIRED_NODE_IDS` entry for
  `test_escape_html_exists_and_is_used_where_required`, authorised by the
  design's file-layout row, reason: *`escape.js` was dead — nothing imported it
  — and after the port there is no HTML sink anywhere for `escapeHtml` to wrap,
  so the property is vacuous. The live gate is
  `test_no_unescaped_interpolation_in_frontend`, which stays.*
- **Out-of-Scope Drift:** deleting or renaming `chat.js` (**pinned**);
  introducing `setInterval` or `requestAnimationFrame`; a second `EventSource`.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_every_shipped_module_is_reachable_from_the_page`
  walks from `index.html` and reaches every shipped module; `EXPECTED_MODULES`
  matches the directory exactly; suite green.
- **Consumes:** `app.css`
- **Produces:** page roots `#page-shepherd`, `#page-flock`, `#page-queues`,
  `#page-projects`, `#page-kanban`, `#page-settings`;
  `app.js::showPage(name)`; the dialog ids `#dlg-legend`, `#dlg-project`,
  `#dlg-delete`

#### Task 5.4 — the manifest, declared once and correctly

- **Files:** `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T5.3
- **Allowed Scope:** update every changed path's sha256 in `files`. **Add
  `post_milestone.edits` entries for exactly the paths that moved and are not
  already in `rebase.regenerated_paths`.** For this phase:
  `web/static/escape.js` (removed, new entry) and `web/static/rail.js` —
  whose 2026-09-20 entry must be **rewritten** to describe the path's whole
  divergence from baseline, because entries are per path and the old sentence
  (*"Comment text only: no statement, no selector and no behaviour changed"*)
  stops being true the moment the file is deleted. Leaving it would be a false
  record in the one gate whose purpose is an honest one.
  `app.css`, `app.js`, `index.html` are already in `regenerated_paths` and
  **must NOT be added to `post_milestone`** — that is the trap.
- **Out-of-Scope Drift:** touching `baseline`; touching
  `rebase.regenerated_paths`; adding a path twice; adding `chat.js` anywhere.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_frozen.py tests/boundaries/test_consumer_surface_additive.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P9 passes.
- **Consumes:** the deleted/added path set from T5.3
- **Produces:** a manifest satisfying
  `moved_paths(baseline, files) == regenerated_paths ∪ post_milestone_paths`

---

### Phase 6 — The Flock page

**Objective:** U7–U11, U16, U1 — the sessions page, three panes, the legend
sheet, the wash. And the three label renames, at their source.
**Autonomy:** AFK.
**Test Seams:** unit (static scans: label/glyph tables, no-sort, no-sink);
integration (`tests/web/conftest.py::Client` over `/api/fleet/tree`).
**Green at the boundary:** yes.
**What this phase does NOT prove:** a pixel. `test_palette.py`'s own docstring
says so: the scan proves the palette the page *ships* is `PALETTE`; the
rendering is Phase 10's live check and the human look there.

#### Task 6.1 — port the render logic with **no HTML sink**

- **Files:** `src/shepherd/web/static/flock.js` *(new)*, delete
  `src/shepherd/web/static/fleet.js`,
  `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`
- **Dependencies:** Phase 5
- **Allowed Scope:** the prototype's three-pane render, `textContent`
  throughout. **Every one of the prototype's eight `innerHTML` assignments is
  rewritten** — the seven SVG icons become `document.createElementNS`
  construction or static markup in `index.html`; `prose.innerHTML = line[1]`
  becomes `textContent`. U8's relative time spelled out, scaling to years, with
  `never seen` for no timestamp. U16's wash. U10's legend with an **`acts:`**
  line taken verbatim from `PALETTE.who_acts`. U1's `ⓘ` sheet
  (`#dlg-legend`), hover/focus popover on a pointer device, tap anywhere in the
  legend opens the sheet, rising from the bottom edge on a narrow screen.
- **Out-of-Scope Drift:** porting `BUCKET_ORDER`, `fleetSortKey`, `.sort(` or
  `localeCompare` — all four are banned by name; porting the Google Fonts link;
  a second label table.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P7 and P8 pass; E19 and E20 pass;
  `test_the_shipped_modules_are_all_there` matches the directory.
- **Consumes:** `app.js::showPage`, `#page-flock`, `#dlg-legend`
- **Produces:** `flock.js` exporting `mountFlock()` and `renderFlock(tree)`;
  `flock.js::BUCKET_LABEL`; `flock.js::BUCKET_MARK`

#### Task 6.2 — the renames land in `core.stops.PALETTE`

- **Files:** `src/shepherd/core/stops.py`, `tests/test_core_stops.py`,
  `tests/web/test_palette.py`, `tests/web/test_fleet_page.py`,
  `tests/web/test_session_wiring.py`
- **Dependencies:** T6.1
- **Allowed Scope:** three label strings only —
  `Bucket.UNFINISHED` → `"stranded"`, `Bucket.PAUSED` → `"limit exceeded"`,
  `Bucket.UNCLASSIFIED` → `"unknown"`. Update the filename literals in the three
  test modules (`"fleet.js"` → `"flock.js"`, drop `"rail.js"`), **keeping every
  test function name** so no node id moves.
- **Out-of-Scope Drift:** touching any `Bucket` **value**; touching
  `signals/stop_rules.py`, the store or the 90-day stop log; touching any hex or
  glyph; adding a UI-side label table.
- **Required Checks:**
  `.venv/bin/python -m pytest -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P6 passes with **zero** new retirements —
  `git diff --stat tests/boundaries/test_collected_node_ids.py` is empty for
  this task.
- **Consumes:** `flock.js::BUCKET_LABEL`
- **Produces:** `PALETTE[Bucket.UNFINISHED].label == "stranded"`,
  `PALETTE[Bucket.PAUSED].label == "limit exceeded"`,
  `PALETTE[Bucket.UNCLASSIFIED].label == "unknown"`

#### Task 6.3 — manifest

- **Files:** `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T6.2
- **Allowed Scope:** `files` hashes; `post_milestone.edits` entries for
  `web/static/fleet.js` (removed) and `web/static/flock.js` (added) — the exact
  pair the recon simulated and confirmed passes.
- **Out-of-Scope Drift:** as T5.4.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P9 passes.
- **Consumes:** the moved-path set from T6.1
- **Produces:** two `post_milestone` entries

---

### Phase 7 — Shepherd and Settings

**Objective:** the conversation page (U6, U11, U12) and Settings' ten sections
(U13), including the audit tail's move.
**Autonomy:** AFK.
**Test Seams:** unit (static scans of `chat.js` / `settings.js`);
integration (`Client` over `/api/master/send`, `/api/approvals`, `/api/audit`,
`/api/autonomy`).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that the unbuilt Settings sections do
anything. Nine of ten are labelled placeholders and this phase proves only that
each says **why** in its panel (U13), not that any of them works.

#### Task 7.1 — `chat.js` keeps its name and loses the audit tail

- **Files:** `src/shepherd/web/static/chat.js`,
  `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`,
  `tests/web/test_chat_page.py`
- **Dependencies:** Phase 6
- **Allowed Scope:** the prototype's conversation, composer and inline approval
  card. The audit tail (`chat.js:242-260` into `#chat-audit`) **moves to
  Settings → Data with its four-field whitelist intact** (`at`, `tool`,
  `decision`, `approved_by`; `args` deliberately excluded per D25). D65: the
  autonomy toggle **leaves this page entirely**.
- **Out-of-Scope Drift:** **renaming or deleting the file** — the freeze pins
  it (recon §I). Widening the audit whitelist. Leaving an autonomy control on
  this page.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_the_chat_page_has_no_html_sink` green; no autonomy
  control in `chat.js` or in `#page-shepherd`'s markup;
  `ls src/shepherd/web/static/chat.js` succeeds.
- **Consumes:** `#page-shepherd`, `app.js::showPage`
- **Produces:** `chat.js` exporting `mountShepherd()`

#### Task 7.2 — `settings.js`

- **Files:** `src/shepherd/web/static/settings.js` *(new)*,
  `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`,
  `tests/web/test_settings_page.py` *(new)*,
  `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T7.1
- **Allowed Scope:** ten sections under *Yours* (Account, Notifications, API
  keys) and *This instance* (Autonomy, Shepherd, Discovery, Limits, Users &
  access, Data, System). Real today: Autonomy, Discovery's hook status, Data's
  audit tail, System's facts. Everything else carries a `not built` chip **and
  says why in its panel**. U12: the two autonomy options read *"Ask me before
  anything leaves this machine"* and *"Approve automatically"*, the second
  stating that auto-approved is never unlogged. `shepherd uninstall` is absent
  from the UI entirely.
- **Out-of-Scope Drift:** building any placeholder section; W3's work-source
  configuration (that belongs on the Projects page, D63).
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** a test asserts every `not built` chip is accompanied by
  non-empty explanatory text in the same panel; the audit whitelist is exactly
  four fields; one `post_milestone` entry for `web/static/settings.js`.
- **Consumes:** `#page-settings`, `app.js::showPage`, the audit whitelist from
  T7.1
- **Produces:** `settings.js` exporting `mountSettings()`

---

### Phase 8 — U17: the decision card's projection

**Objective:** `{text, choices[]}` off a pane snapshot, with three mandatory
degradations.
**Autonomy:** AFK, with a **stop-and-report** gate at T8.1's first step (A8).
**Test Seams:** unit (`read_decision` as a pure function over the frozen probe
captures — the highest seam that covers the risk); integration (the tool through
`invoke()`); integration (`Client` over the new route).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that the parser survives an engine update.
It cannot — the choices are the engine's and move with its version. What it
proves is that an unrecognised screen **degrades and never guesses**, which is
the property that has to hold across updates.

#### Task 8.1 — `read_decision`, pure, against frozen evidence

- **Files:** `src/shepherd/runner/pane.py`,
  `tests/runner/test_pane_decision.py` *(new)*
- **Dependencies:** Phase 4
- **Allowed Scope:** `Choice(number: int, label: str)` and
  `DecisionPrompt(text: str, choices: tuple[Choice, ...])`; a pure
  `read_decision(state: PaneState) -> DecisionPrompt | None`.
  **First step, before writing the parser:** assert that
  `PaneState.dialog_text` for the frozen permission capture actually carries the
  numbered option lines. If it does not, **stop, write
  `docs/plans/projects-ui-blockers/t8-1.md`, and report** — do not widen the
  capture path on the way past.
- **Out-of-Scope Drift:** **editing any file under `docs/probes/`** — frozen
  evidence, read-only, no exceptions short of the three standing conditions in
  `CLAUDE.md`. Adding I/O, a clock or a process to `pane.py` (it is pure and a
  boundary rule says so). Answering a dialog from here.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/runner tests/boundaries -q` ·
  `git status --porcelain docs/probes/` (must be empty) ·
  `.venv/bin/mypy --strict src/shepherd/runner`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E16 passes (unparseable → `None`, never a guess); E17
  passes (`PaneKind.TRUST` is named and never answered blind — a blind Enter
  there answers *"No, exit"*); `docs/probes/` byte-unchanged.
- **Consumes:** `PaneState`, `PaneKind`
- **Produces:** `shepherd.runner.pane.Choice`,
  `shepherd.runner.pane.DecisionPrompt`,
  `shepherd.runner.pane.read_decision(state: PaneState) -> DecisionPrompt | None`

#### Task 8.2 — the tool, the route, and the card

- **Files:** `src/shepherd/toolsurface/tools_terminal.py`,
  `src/shepherd/web/routes.py`, `tests/web/test_routes.py`,
  `src/shepherd/web/static/session.js`,
  `src/shepherd/web/static/flock.js`,
  `tests/web/test_session_page.py`,
  `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T8.1
- **Allowed Scope:** a `get_decision` `ToolDef` (`LOCAL_READ`), the route
  `"/api/sessions/{session_id}/decision" → "get_decision"` (API_ROUTES 13 → 14,
  and the closed-set literal widened by hand), and the card's render. U11: the
  engine's own prompt with its numbered choices, verbatim — **not** flattened to
  approve/reject, because that throws away the option carrying the scope.
  E18: an **attached** session renders read-only and says so, rather than
  showing three buttons that go nowhere.
- **Out-of-Scope Drift:** a client-side parser; `innerHTML`; sending a keystroke
  from the read path.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web tests/toolsurface tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E16, E17, E18, E20 pass end to end; the GET literal names
  14 paths; `test_pty_bytes_never_reach_innerHTML` green.
- **Consumes:** `shepherd.runner.pane.read_decision(state: PaneState) -> DecisionPrompt | None`,
  `shepherd.runner.pane.DecisionPrompt`, `#page-flock`
- **Produces:** the tool name `"get_decision"`; the route
  `"/api/sessions/{session_id}/decision"`

---

### Phase 9 — The Projects page — the acceptance test for the five verbs

**Objective:** U14 — two panes, `Unassigned` pinned last and visually distinct,
repo paths in full, edited in the Edit dialog. This is the phase that proves
Phase 1–4 shipped something a person can use.
**Autonomy:** **HITL (`manual-verification`)** at the exit — a person creates,
renames, adds a repo to, removes a repo from, and deletes a project through the
browser.
**Test Seams:** integration (`Client` over all seven routes); E2E (Phase 10's
live check).
**Green at the boundary:** yes.
**What this phase does NOT prove:** W3's work-source configuration — the Work
source block is a `not built` placeholder (D63's fields exist; nothing behind
them does).

#### Task 9.1 — `projects.js`

- **Files:** `src/shepherd/web/static/projects.js` *(new)*,
  `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`,
  `src/shepherd/web/static/app.css`,
  `tests/web/test_projects_page.py` *(new)*,
  `tests/boundaries/consumer_manifest.json`
- **Dependencies:** Phase 4, Phase 6
- **Allowed Scope:** the list/detail panes; `#dlg-project` (create and edit) and
  `#dlg-delete` (the three-way choice rendered **from the refusal**, not from a
  guess); the allowlist warning the prototype carries verbatim — *"A path here
  **widens where Shepherd may start sessions**"* (D22/D58, and it is true).
  Sessions listed on a project are links into the Flock. `Unassigned` is pinned
  last, visually distinct, and its rename/delete/add-repo controls are absent —
  not merely disabled.
- **Out-of-Scope Drift:** client-side sorting; a second set of project verbs;
  building the Work source block.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic, then Manual.
- **Checkpoint Type:** **human_verify** — drive all five verbs in a browser,
  including a delete refused into the three choices.
- **Exit Criteria:** E1, E7, E8, E9, E13, E14 pass through HTTP; one
  `post_milestone` entry for `web/static/projects.js`; `Unassigned` offers no
  lifecycle control at all.
- **Consumes:** every route template from T4.1; `#page-projects`,
  `#dlg-project`, `#dlg-delete`
- **Produces:** `projects.js` exporting `mountProjects()`

---

### Phase 10 — Live verification against the served page

**Objective:** prove the product, not the design.
**Autonomy:** **HITL (`manual-verification`)** — a person looks at the twelve
screenshots once.
**Test Seams:** E2E (headless chromium against a real `controld` on loopback).
**Green at the boundary:** yes.
**What this phase does NOT prove:** anything about a phone's real browser, a
tunnel, or a slow network. It proves six pages × two viewports in headless
chromium on this host: zero console errors, required content present, no
horizontal overflow.

#### Task 10.1 — the live render check

- **Files:** `tests/web/test_render_live.py` *(new)*,
  `tools/render_check.py`
- **Dependencies:** Phase 9
- **Allowed Scope:** a `@pytest.mark.live` test that starts a real `controld`
  bound to loopback on an ephemeral port against a temporary data directory,
  waits for it, and calls `render_check.check(f"http://127.0.0.1:{port}/", shots)`.
  **The served page, never the prototype file** — that is the difference between
  testing the design and testing the product.
- **Out-of-Scope Drift:** pointing the check at the prototype; binding to
  anything but loopback (`server.py:41` raises `BindAddressRefused` anyway);
  any `tmux` invocation without `-L`; touching the `shepherd` socket, whose
  sessions are the user's.
- **Required Checks:**
  `.venv/bin/python -m pytest -m live tests/web/test_render_live.py -q`
- **Validation Level:** **Live.**
- **Checkpoint Type:** **human_verify** — the twelve screenshots.
- **Exit Criteria:** P11 passes; zero console errors at 390×844 and 1280×900;
  horizontal overflow ≤ 1px on every page; the required content string found on
  each of the six pages.
- **Consumes:** `tools/render_check.py::check(origin, shots)`,
  `tools/render_check.py::PAGES`, every page root id
- **Produces:** `tests/web/test_render_live.py`, twelve screenshots under the
  scratchpad

#### Task 10.2 — the whole-tree gate

- **Files:** none (verification only)
- **Dependencies:** T10.1
- **Allowed Scope:** running the gates.
- **Required Checks:**
  `.venv/bin/python -m pytest -q` ·
  `.venv/bin/mypy --strict src/` ·
  `.venv/bin/python -m pytest tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js` ·
  `git status --porcelain docs/probes/`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** suite green; `mypy --strict` clean; 105 boundary rules
  green; `docs/probes/` byte-unchanged.
- **Consumes:** everything
- **Produces:** the release gate result

---

## Verification Strategy (critical_path)

Four layers, each with a named owner and a stated limit.

| Layer | What it proves | Where it attaches | Limit |
|---|---|---|---|
| **Pure-unit** | `read_decision`, `delete_project`'s outcome table, `_registered_roots`, `bind_cwd_to_repo`'s branch table | the function's own seam, no store, no browser | proves the decision, not the wiring |
| **Store integration** | the migration, the seven verbs, the cascade ordering, the FK graph | a real SQLite file through `Store`'s one writer thread | proves the data, not the surface |
| **Route integration** | every path resolves to a registered tool with a real schema property per declared field | `tests/web/conftest.py::Client` against the real handler | proves the wire, not the render |
| **Live E2E** | six pages × two viewports from a served `controld`: no console error, content present, no sideways scroll | headless chromium via `tools/render_check.py` | proves this host's headless chromium, not a phone |

Plus three **static gates that are not tests of behaviour at all** and are
listed separately because confusing them with behaviour tests is how a green
suite hides a broken page: the byte-freeze equality (P9), the node-id freeze
(P10), and the HTML-sink / no-sort / no-build scans (P7, P8).

**TDD.** Each store and parser task is written RED first through
`component-builder`. E1's `test_two_projects_may_share_a_name` **must be shown
red against today's code** before T1.4's fix lands — a test that has never
failed has not been proved to bite.

**Mutation discipline** (`CLAUDE.md`): any planted violation is an inert
fixture under `tests/boundaries/fixtures/` that nothing imports, read as text or
parsed as an AST. Never live source the suite executes. `__pycache__` is cleared
before any mutation run, because CPython decides freshness from
`(source mtime in whole seconds, source size)` and a size-preserving mutation
inside the same second re-imports unmutated bytecode and records a **false
survivor**.

## Live Verification Strategy

- **Harness command:** `.venv/bin/python -m pytest -m live tests/web/test_render_live.py -q`
- **Topology:** one `controld` process, loopback only, ephemeral port,
  `--data-dir` under the session scratchpad. Headless chromium via the
  already-installed Playwright. No tmux session is created, attached, or killed
  by this lane; if a future revision needs one, it uses
  `tmux -L shepherd-render …` with `-L` on **every** invocation and never
  `kill-server` without it.
- **Isolation:** a fresh database per run, migrated from empty through 004. The
  user's `shepherd` socket and its `m3` / `master` sessions are never named and
  never touched.
- **Flake policy:** the check waits 700ms after navigation and 350ms after each
  nav click, as the tool already does. A failure is a failure — **no retries**.
  A flaky render check is a render check that has stopped being evidence.
- **Teardown:** the `controld` process is terminated by pid from the fixture
  that started it. Never `pkill`, never a signal to `0`, `1` or `-1` —
  `tests/conftest.py`'s net refuses those, and a guard against a reboot must not
  be able to cause one.

---

## Functionality Flow Mapping

```
Flow: declare a project and start work in it
1. open Projects            → test: test_render_live (page opens, 2 viewports)
2. + New project            → test: test_create_project_through_http
3. add a repo path          → test: test_add_repo_widens_the_allowlist
4. spawn into that repo     → test: test_a_registered_repo_admits_a_spawn
5. the session appears      → test: test_the_new_session_lands_in_that_project
Error paths:
- two projects named "api"  → test: test_two_projects_may_share_a_name
- a path that will not canonicalize → test: test_add_repo_refuses_a_path_that_does_not_canonicalize
- a spawn outside every repo → test: test_a_directory_outside_every_registered_repo_is_refused[*]
- a project with no repo     → test: test_a_project_with_no_repo_refuses_everything
- the handler raises         → test: test_the_projects_page_renders_the_correlation_id
```

```
Flow: a session nobody declared a project for
1. discovery sees a cwd     → test: test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix
2. no declared project      → test: test_an_orphaned_repo_binds_to_unassigned_and_the_repo_row_survives
3. it shows on Flock        → test: test_unassigned_sessions_render_on_the_flock_page
Error paths:
- repo in two projects       → test: test_a_repo_in_two_projects_binds_a_discovered_session_to_unassigned
- not a git repo / bare repo → test: test_a_non_repo_cwd_binds_to_unassigned_and_counts_the_anomaly
```

```
Flow: delete a project that is busy
1. Delete                    → test: test_delete_refuses_by_default_and_names_the_running_sessions
2. three choices rendered    → test: test_the_delete_dialog_renders_the_three_choices_from_the_refusal
3a. kill                     → test: test_delete_with_kill_stops_them_then_cascades
3b. orphan                   → test: test_delete_with_orphan_moves_them_to_unassigned
3c. cancel                   → test: test_cancel_writes_nothing
Error paths:
- Unassigned                 → test: test_unassigned_refuses_delete
- after any outcome          → test: test_no_session_ever_points_at_a_deleted_project
```

```
Flow: answer an engine prompt from the phone
1. a needs_you card          → test: test_a_needs_you_session_shows_the_engines_own_prompt
2. numbered choices verbatim → test: test_the_choices_are_the_engines_own_numbering
3. send the keystroke        → existing answer_permission tests, unchanged
Error paths:
- unparseable                → test: test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses
- trust dialog               → test: test_the_trust_dialog_is_named_and_never_answered_blind
- attached session           → test: test_an_attached_session_renders_the_decision_read_only
- idle session               → test: test_an_idle_session_gets_no_decision_card
```

---

## Risk-Based Testing Matrix

| Risk | Prob | Impact | Test required |
|---|---|---|---|
| Migration 004 corrupts a real database | low | **high** | Deterministic — `test_migration_004_leaves_foreign_key_check_empty` over a database with real rows, plus the human look at `PRAGMA table_info` (T1.1) |
| `delete_project` orphans session rows out of the INNER JOIN | med | **high** | Deterministic — P2, run after every cell of P1's matrix |
| The allowlist silently narrows and refuses legitimate spawns | med | **high** | Deterministic — P5 |
| The allowlist silently **widens** (a §13 admission bypass) | low | **high** | Deterministic — the five parametrised escape cases, node ids kept |
| A byte-freeze assertion goes red and is "repaired" by editing `rebase` | med | **high** | Deterministic — P9, plus this plan naming `rebase` as untouchable in every manifest task |
| A frozen test is deleted without a retirement entry | **high** | med | Deterministic — P10, and fifteen retirements pre-identified by task |
| An `innerHTML` is ported from the prototype | **high** | med | Deterministic — P8, and T6.1 budgets the rewrite as scope |
| The client-side sort is ported | med | med | Deterministic — P7 |
| Every page renders on top of every other (U18) | med | **high** | Deterministic (`test_app_css_carries_the_hidden_reset`) **and** Live (P11) |
| A module ships with a syntax error and the page still "looks fine" | med | **high** | Live — P11; a parse error is a console error. Plus `tools/js_syntax_check.py` as an explicit command |
| The POST arrival count literal `9` is left stale | **high** | low | Deterministic — P12 (it fails loudly; the risk is only wasted time) |
| U17's parser breaks on an engine update | **high** | med | Deterministic — E16: the property tested is *degrades, never guesses*, which is what survives the update |
| `esprima` becomes an undeclared suite dependency | med | med | Deterministic — `grep -rn "esprima" tests/` must be empty (A6); checked in T0.1's exit |
| A `tmux kill-server` or a signal to pid 1 escapes a test | low | **high** | Deterministic — `tests/conftest.py`'s net plus `tests/test_signal_guard.py`; and no task in this plan creates a tmux session |
| `docs/probes/` is edited to make a parser test pass | low | **high** | Deterministic — `git status --porcelain docs/probes/` in T8.1's and T10.2's required checks |

---

## ADRs recorded by this plan

### ADR-P1: the delete cascade lives in the verb

**Context:** D61 says delete forgets and cascades to sessions. SQLite cannot
`ALTER` a foreign key.
**Decision:** the cascade is ordered code inside the store's single writer
transaction — `mailbox_message → session → project_repo → workspace`.
**Rejected:** `ON DELETE CASCADE` on `session.workspace_id`, which needs a
40-column table rebuild the way 002 did.
**Consequences:** enables D61's three-way choice, which the schema cannot
express at all. Prevents a future accidental `DELETE FROM workspace` from
destroying session rows silently. Costs: the ordering is a property of code, so
P1 and P2 exist to hold it.
**Reversibility:** reversible (a later migration could add the clause).

### ADR-P2: `Unassigned` is the literal id `"unassigned"`, seeded by 004

**Context:** `session.workspace_id` is `NOT NULL`, so the sentinel must exist
before any row can be orphaned.
**Decision:** a reserved id, seeded in the migration, defined once at
`store.models.UNASSIGNED_PROJECT_ID`.
**Rejected:** a ULID; lazy creation at first use.
**Consequences:** reads as itself in a log; `workspace.id` has no format
constraint so nothing else has to change. Prevents a class of "the sentinel did
not exist yet" bugs.
**Reversibility:** irreversible in practice once rows point at it.

### ADR-P3: `chat.js` keeps its filename

**Context:** the design named it `shepherd.js`. Simulating the freeze gate found
the rename unrepairable (see Codebase Reality Check #3).
**Decision:** the module keeps the filename `chat.js`; the page is called
Shepherd.
**Rejected:** rewriting `rebase.regenerated_paths`, which is spent exactly once
by T24 and whose `regenerated_by` is asserted.
**Consequences:** a module filename stops matching its page's name. That is the
cheaper of two bad options: the alternative is a broken gate or a relaundered
re-base.
**Reversibility:** reversible only by a future, deliberate, second re-base.

### ADR-P4: `last_activity_at` is derived, not written

See **RD-3**. Recorded here because the next reader will find a column in the
schema that nothing writes and needs to know that is deliberate.

---

## Blockers Ledger

**One file per task. Never one shared ledger.**

`docs/plans/projects-ui-blockers/<task-id>.md` — e.g. `t1-1.md`, `t6-2.md`.

- A builder writes **only** its own file. Nobody opens another task's file.
- Format, as M1–M4: `T<id> · symptom · what was tried · what it blocks · owner: …`
- Ids are never reused. An entry is never deleted — a retired one says so in
  place.
- `docs/plans/2026-09-21-projects-and-ui-BLOCKERS.md` is the assembled, readable
  ledger. **Only the router writes it, and only when no builder is live.**

**Why the rule exists, stated so it survives a compression:** M3 gave four
concurrent builders one file and told them to append. One rewrote it whole
instead, and **Task 2's and Task 8's entries were destroyed**. They were
reconstructed from hand-back reports, but a reconstruction is not the original.
*"Append to this file" is an instruction, not a concurrency protocol.* This plan
runs two discovery lanes and several UI tasks that can overlap; the hazard is
live here.

**Entries this plan already predicts will be needed:**

- `t8-1.md` if `PaneState.dialog_text` does not carry the numbered option lines
  (A8). Stop and report; do not widen the capture path on the way past.
- `t1-5.md` for any fixture that cannot be swept mechanically.
- `t2-3.md` for any admission test whose property genuinely changes rather than
  whose wording does.

---

## Acceptance Clauses

Twenty-four clauses. **Every deciding command names a file this plan builds or
a file that exists today** — the failure M4's verification returned was a clause
whose command named a file nobody built, and each command below was checked
against the tree on `integration` @ `4761c1d` or against a task above that
creates it.

| # | Clause | Deciding command |
|---|---|---|
| AC-1 | Migration 004 applies clean over real 001–003 rows with `foreign_key_check` empty | `.venv/bin/python -m pytest tests/store/test_migration_004.py -q` |
| AC-2 | 001–003's recorded sha256 are unchanged and a second `migrate()` is a no-op | `.venv/bin/python -m pytest tests/store/test_migration_004.py::test_the_recorded_checksums_of_001_to_003_are_unchanged tests/store/test_migration_004.py::test_migration_004_is_idempotent_across_two_runs -q` |
| AC-3 | `/work/api` and `/personal/api` are two projects | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_two_projects_may_share_a_name -q` |
| AC-4 | `delete_project` is total over its matrix and never orphans a session row | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_delete_is_total_over_its_matrix tests/store/test_verbs.py::test_no_session_ever_points_at_a_deleted_project -q` |
| AC-5 | `Unassigned` refuses rename, delete and `add_repo` | `.venv/bin/python -m pytest tests/store/test_verbs.py -k unassigned -q` |
| AC-6 | `bind_cwd_to_repo` never raises, over the cwd matrix | `.venv/bin/python -m pytest tests/signals/test_binding.py::test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix -q` |
| AC-7 | A repo in two projects, and a repo in none, both bind to `Unassigned` | `.venv/bin/python -m pytest tests/signals/test_binding.py -k unassigned -q` |
| AC-8 | `discover_repos` is gone and nothing references it | `! grep -rn "discover_repos" src/ tests/` |
| AC-9 | The allowlist never silently narrows | `.venv/bin/python -m pytest tests/orchestration/test_admission.py::test_every_registered_path_is_either_admitted_or_named_in_the_refusal -q` |
| AC-10 | The five escape shapes still refuse, with their frozen node ids intact | `.venv/bin/python -m pytest "tests/orchestration/test_admission.py::test_a_directory_outside_every_registered_repo_is_refused" -q` |
| AC-11 | Seven project tools register and freeze | `.venv/bin/python -m pytest tests/toolsurface/test_tools_projects.py -q` |
| AC-12 | Every new module is held to the 450-line cap | `.venv/bin/python -m pytest tests/toolsurface/test_tools_m3.py::test_the_three_modules_are_each_under_the_cap -q` |
| AC-13 | Every POST body field is a property of its tool's schema, arrival count 14 | `.venv/bin/python -m pytest tests/web/test_routes_m3.py -q` |
| AC-14 | The GET closed-set literal names all 14 paths by hand | `.venv/bin/python -m pytest tests/web/test_routes.py::test_every_api_route_names_a_registered_tool -q` |
| AC-15 | The pre-M4 route mappings are unchanged (additive only) | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py -q` |
| AC-16 | `web/server.py` is byte-identical | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py::test_web_server_is_byte_unchanged -q` |
| AC-17 | The byte-freeze equality and disjointness hold | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_frozen.py -q` |
| AC-18 | `chat.js` still exists at its own path | `test -f src/shepherd/web/static/chat.js` |
| AC-19 | No frozen test vanished without a retirement entry | `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` |
| AC-20 | Zero HTML sinks; the shipped module list matches the directory | `.venv/bin/python -m pytest tests/web/test_frontend_escaping.py -q` |
| AC-21 | The page never re-derives the order, and its labels are `PALETTE`'s | `.venv/bin/python -m pytest tests/web/test_palette.py -q` |
| AC-22 | No build step, no remote asset, no polling | `.venv/bin/python -m pytest tests/web/test_frontend_no_build_step.py -q` |
| AC-23 | Six pages × two viewports render from a **served** `controld`: zero console errors, required content present, no horizontal overflow | `.venv/bin/python -m pytest -m live tests/web/test_render_live.py -q` |
| AC-24 | Whole tree: suite green, `mypy --strict` clean, 105 boundary rules green, probes byte-unchanged | `.venv/bin/python -m pytest -q && .venv/bin/mypy --strict src/ && .venv/bin/python -m pytest tests/boundaries -q && test -z "$(git status --porcelain docs/probes/)"` |

---

## What each phase does NOT prove — collected

| Phase | Not proved |
|---|---|
| 0 | That any page is correct. Only that the checker can reach a served page and fails on a page it should fail on. |
| 1 | That any caller uses the new verbs. Five verbs with no caller are five unproven verbs. |
| 2 | That the policy is reachable from a UI; the hook lane's other three call sites under load. |
| 3 | That any route reaches these tools; that a person can drive them. |
| 4 | That any page calls these routes. |
| 5 | That any page has content. It proves the shell, the reset, the routing, and that the rail's removal was recorded. |
| 6 | A pixel. `test_palette.py`'s own docstring says so. |
| 7 | That the unbuilt Settings sections do anything — only that each says why. |
| 8 | That the parser survives an engine update. It cannot; it proves degradation instead. |
| 9 | W3's work-source configuration. |
| 10 | Anything about a real phone, a tunnel, or a slow network. Six pages × two viewports, headless, on this host. |

---

## Differences From Agreement

Three, all stated rather than absorbed:

1. **`last_activity_at` is derived, not written** (RD-3). The design says *"This
   design fills it"*; this plan projects `MAX(session.last_event_at)` at read
   time and leaves the column unwritten and unrendered. The design's
   requirement — that the Projects page can sort on it — is met. Its wording is
   not.
2. **The `post_milestone` declaration is per path, not "one for the whole
   redesign"** (`docs/design/ui-decisions.md` §"And the freeze"). The recon and
   the reader's own `assert len(seen) == len(set(seen))` are right; the
   UI-decisions sentence is loose. Seven entries, not one.
3. **The prototype contains eight `innerHTML` assignments**, contradicting
   `docs/design/ui-decisions.md`'s *"Everything in the prototype is
   `textContent`"*. Rewriting all eight is scoped into T6.1 rather than
   discovered during it.

Plus the correction that arrived mid-plan and is now in both source documents:
**`chat.js` keeps its filename** (ADR-P3). This plan is written against the
corrected design.

---

## Self-review

Cross-phase contract drift: checked. Every `Consumes` name in Phases 1–10
verbatim-matches a `Produces` in an earlier phase or task —
`UNASSIGNED_PROJECT_ID`, `OnRunning`, `DeleteOutcome`, the five `writes.*`
signatures, the five `reads.*` signatures, the nine `Store.*` delegations,
`PROJECT_TOOL_NAMES`, `register_project_tools`, `project_workspace`, the seven
route templates, `app.js::showPage`, the six `#page-*` roots, the three
`#dlg-*` ids, `flock.js::BUCKET_LABEL`, `shepherd.runner.pane.read_decision`,
`tools/render_check.py::check(origin, shots)`,
`tools/render_check.py::PAGES`. No dangling reference found.

**Self-review: no cross-phase reference drift.**
