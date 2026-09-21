# Projects backend + the dark UI redesign — execution plan

## Metadata

- Created: 2026-09-21
- **Revision: 4** — **router-directed amendment** applying fresh-review pass 2
  (5 blocking + 10 advisories). The two-pass fresh-review cap is spent; this is
  the diff-scoped amendment lane, not a third pass.
- Prior revisions: 3 (two router corrections), 2 (fresh-review pass 1: 7
  blocking + 6 major + the minors), 1 (initial)
- Status: draft
- Plan Mode: `execution_plan`
- Verification Rigor: `critical_path` (irreversible migration · security-adjacent
  allowlist · a delete state machine · two concurrent discovery lanes)
- Branch / base: `integration` @ `4761c1d`
- Python: `/root/Shepherd/.venv/bin/python` (3.12)
- Supersedes: `docs/backlog/2026-09-21-projects-work-sources-and-ui.md` §W1, with
  real tasks. §W2 and §W3 stay in the backlog.

### What changed in revision 4

Fifteen findings from fresh-review pass 2, all applied. Every one was
re-verified against the source before it was written in; **one I can show is
partly wrong, and it is flagged in F6 below rather than absorbed.**

| # | Finding | Fix |
|---|---|---|
| **F1** | the `EXPECTED_SCHEMA_VERSION 3 → 4` bump was unswept, so **T1.1 could not pass its own Required Checks** | the three migration test modules join T1.1's Files; **19** hard-coded `3` literals enumerated by grep (the review listed seven); and a **17th retirement** — `test_future_schema_refuses_to_start_at_four` builds its impossible sentinel by inserting version 4, which 004 makes real and `schema_migration.version INTEGER PRIMARY KEY` turns into a PK collision. Successor proves the rule at version **5**. |
| **F2** | Phase 1 still did not end green: `tools_m1.py:156` reads `workspace.root_path`, served by `/api/projects`, called by `test_fleet_page.py:102` — a **suite failure**, not a `mypy` finding | new **Task 1.10** moves the `project_workspace` projection into Phase 1; T3.2 shrinks to compose wiring alone |
| **F3** | Phase 5 did not end green either: `test_palette.py:97` reads `rail.js`, deleted by T5.3 one phase before the literal is fixed; and `:42` reads `fleet.js`, deleted by T6.1, making **T6.1's own exit criterion unsatisfiable** | `tests/web/test_palette.py` joins T5.3's and T6.1's Files and Allowed Scope |
| **F4** | T6.4's exit said "exactly 5 entries" against its own `Produces` of "4 of 6" — the **third** total-versus-rows disagreement | 5 → 4, with the arithmetic spelled out; every table in the plan re-added afterwards |
| **F5** | `add_repo` could not be built from its declared inputs: `git_common_dir`, `name` and `vcs_remote` have no source | T3.1 names `probe_repo` / `repo_root` / `resolve_remote` and the `toolsurface → signals` edge (which already exists at `tools_m1.py:33`); the Purity Map now says this module is **not pure**; new **E23** because `git_common_dir` is D48's binding key and a placeholder would silently route every UI-registered repo's sessions to `Unassigned` |
| **F6** | the sink line-to-module mapping was wrong and named a non-existent `T4.3` | an authoritative **line → enclosing function → module → task** table, recovered by walking each line back to its top-level function. **Partly disagrees with the review — see the report.** |
| **F7** | T5.3 and T6.3 ran the freeze gate before their own manifest task | `tests/boundaries` removed from those Required Checks and the **red internal boundary declared**, the way Phase 1 declares its own |
| **F8** | AC-21 `print`ed the count instead of asserting it — it exited 0 for any value, and it is the clause that would have caught F4 | now `sys.exit(0 if n==6 else …)`, plus an `escape.js` byte check |
| **F9** | AC-15 selected `-k bounded` against a test the plan never named | names `test_the_project_list_issues_a_bounded_number_of_statements`, now owned by T1.10 |
| **F10** | T1.7's Consumes named `Store.add_repo`; the unattached-repo verb is `Store.upsert_repo`. Following it would have attached every discovered repo to the reserved project and **widened `_registered_roots("unassigned")` to every repo the machine has ever seen** | corrected, with the consequence written down; `Store.upsert_repo` added to T1.6's Produces |
| **F11** | the typography reversal was in Durable Decisions but not in Differences From Agreement — the same quiet-reversal shape `escape.js` was corrected for | **Differences From Agreement #6** |
| **F12** | `test_controld.py:313` asserts a static markup literal the seed cannot affect, and was wrongly on N1's red list | removed, with a note saying why listing it would invite a builder to "repair" a green assertion |
| **F13** | `tools/render_check.py:29` imports `playwright.sync_api` at module level, so T0.1's by-path load would make **playwright an undeclared suite dependency** — A6's hazard by a second door, and `-m 'not live'` does not help because deselection happens after import | `pytest.importorskip("playwright")` as the test's first statement, asserted by T0.1's exit; recorded in **A5** and as **E24** |
| **F14** | citation slips in RD-2 and E14 | RD-2 now cites `discovery.py:1` and `:28-66`; E14 cites `registry.py:69` **and** `:318-319`, where the correlation id is actually recorded |
| **F15** | §3's headline *"65 decisions (D1–D65…)"* (`orchestrator-platform.md:34`) becomes false when D66 and D67 land | in T5.1's Allowed Scope (→ 66) and T6.3's (→ 67) |

### What changed in revision 3

Two corrections, both from the router, both re-verified against the source
before applying. **Nothing else changed.**

| Correction | What it did |
|---|---|
| **N2's premise was wrong** | Revision 2 claimed `reads.list_workspaces` has no `ORDER BY`. **It does** — `SELECT * FROM workspace ORDER BY name` (`reads.py:102`). The real hazard is a *specified* order whose first element moves: BINARY collation sorts uppercase first, so the seeded `"Unassigned"` leads (`['Unassigned', 'api', 'payments-api', 'shepherd']`, measured on SQLite 3.45.1) and every `list_workspaces()[0]` returns the reserved project. **The failure is deterministic**, not a flake — it cannot hide. Revision 2's proposed `ORDER BY name, id` is **dropped**: it repaired nothing and would have left a reader believing the hazard was closed. The repair is rewriting the sites to select by name or captured id. Count corrected **10 → 8** (measured). |
| **RD-4 decided: keep `escape.js`** | Owner reversal of the design's file-layout row, recorded as **ADR-P6** and as Differences From Agreement #5. Retirements **17 → 16**; `post_milestone` entries **7 → 6**; T5.3 loses its `UNREACHABLE_BY_DESIGN` edit and now retires nothing. |

### What changed in revision 2

| From the review | Change |
|---|---|
| **B1** Phase 1's boundary left `binding.py` and `admission.py` broken | **Phase 2 is folded into Phase 1.** Its three tasks become T1.7–T1.9. The number 2 is **retired, not re-flowed** — phases 3–10 keep their numbers, because this repo's rule is that ids are never reused (`docs/plans/m4-blockers/README.md`) and re-flowing would silently invalidate every reference the review and the ledger already carry. |
| **B2** the D21 action-list retirements were over-counted | **D21's `next_actions` relocates from the session card to the session pane** (§12 already says *"The same list renders in the Session view header"*). Walked `tests/web/test_fleet_page.py` test by test: **1 retirement, 16 body rewrites** — was 17 retirements. |
| **B3** the stop-summary strip was dropped | **Kept.** `#stop-summary`, `#unknown-rate`, `#low-confidence` live in the Flock header beside the legend. Saves 3 frozen palette ids and honours principle 5. The prototype omitted it; the prototype is a mock, not the contract. |
| **B4** deleting the session view was a silent capability regression | **D67** — the session view *relocates* into the Flock's third pane. `session.js`, `terminal.js` and `vendor/xterm.js` are **retained**. `test_session_page.py`'s 16 frozen ids all survive as body rewrites. |
| **B5** retirement strings would not satisfy the gate | `test_collected_node_ids.py:172` asserts `"RD-" in decision or "§" in decision`, **and** `len(reason) > 80`. Both are now in Durable Decisions. Every retirement below is spelled `§3 D57` / `§3 D66` / `§3 D67` / `§12 …` / `RD-4`. |
| **B6** a second hard-coded count was missed | `tests/web/test_routes_m3.py:237` asserts `len(routes.BODY_ARGS) == 10` → `== 15`, now in T4.2's Allowed Scope beside `:112`. |
| **B7** `test_app_css_carries_the_hidden_reset` was named and built by nothing | Fixed, and structurally: there is now a **Test Ownership Index** mapping every test named anywhere in this plan to its owning module and the task that builds it. The "named but unbuilt" failure is now a table lookup, not a memory. |
| **M1–M6, minors** | all applied; see the index and the task bodies |
| **My own r1 arithmetic** | r1's prose said "fifteen retirements" over a list of 7+4+3+1+1 = **16**. Corrected. |
| **The dispatch brief's `1482`** | The brief used `wc -l`; `grep -c "::"` is **1480**. The plan carried 1480 from r1 and keeps it. |
| **Two hazards nobody named** | N1 and N2 below — the seeded `unassigned` row breaks two "empty" assertions, and eight `list_workspaces()[0]` sites start returning the reserved project. Both are sweep items in T1.5. |

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
  3. `tests/boundaries/collected_node_ids.txt` freezes **1480** node ids
     (`grep -c "::"`, not `wc -l`). Deleting or renaming a frozen test needs a
     `RETIRED_NODE_IDS` entry, and
     `test_every_retirement_names_its_reason_and_the_decision_that_authorised_it`
     (`:166-174`) imposes **two mechanical requirements** on it: the reason must
     be **longer than 80 characters**, and the decision string must contain
     `"§"` or `"RD-"`.
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
  Questions-Resolved table, three by the router at revision 2 (D67, the
  stop-summary strip, D21's relocation); four more are recorded as
  `Recommended Defaults` below, each unapproved and each with the rejected
  alternative named.

### Recommended Defaults (proposed, NOT approved)

| # | Decision | Recommended | Rejected | Why |
|---|---|---|---|---|
| RD-1 | What happens to `upsert_workspace` | **Delete the verb.** D57 removes match-on-name, and binding stops creating projects, so it has no caller in `src/`. Test fixtures call `create_project(name=…)` instead. | Keep it as a thin alias over `create_project` | A second creation path around the verb the lifecycle is built from is exactly the drift D57 exists to close. Cost: one retired frozen node id and the ~35-module sweep, which is its own task either way. |
| RD-2 | `discover_repos()`'s fate | **Delete `src/shepherd/signals/discovery.py` and `tests/signals/test_discovery.py`.** | Wire it to `add_repo` as a directory-scan helper | Its module docstring (`discovery.py:1`) names `workspace.root_path` as its whole reason to exist, and 004 removes that column; the function itself is `discovery.py:28-66` and has no caller in `src/`. U14 has repo paths typed in the Edit dialog, not scanned, so wiring it would be building a caller to justify a module rather than the other way round. Cost: three retired frozen node ids. Recoverable from git if W3 ever wants a scanner. |
| RD-3 | `workspace.last_activity_at` | **Stop reading the column; derive the value** as `MAX(session.last_event_at)` over the project's sessions, in one read (`reads.project_last_activity`). The column stays in the schema (004 does not drop it) and stays unwritten. | Write the column inside `apply_fold_delta` | A write per folded event on the hot path, to maintain a value one `GROUP BY` already answers, is a second source of truth for a number nothing else needs. **This is a deviation from the design's wording** and is listed under Differences From Agreement rather than absorbed. |
| ~~RD-4~~ | ~~`escape.js`~~ | **Decided by the owner at revision 3: KEEP it, byte-unchanged.** No longer a default; it is applied. See ADR-P6 and Differences From Agreement #5. | Deleting it, as the design's file-layout table said | Deleting a documented, deliberately-kept helper is a small capability decision wearing a tidy-up's clothes — B4's lesson applied to a different file. It would also cost one retirement, one `post_milestone` entry and one `UNREACHABLE_BY_DESIGN` edit, in a change already retiring seventeen ids. |

---

## Context References — read before starting any task

| Path | Why |
|---|---|
| `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` | The measurement. §I is the byte-freeze worked out exactly, including the `chat.js` pin and the five simulated gate runs. Outranks every other document. |
| `docs/plans/2026-09-21-projects-and-ui-design.md` | The approved design. Its Questions-Resolved and Decisions tables are settled. |
| `docs/design/ui-decisions.md` | U1–U18 with their reasoning. |
| `docs/specs/orchestrator-platform.md` §3 (D22, D38, D47, D48, D51, D57–D65), §12, §13, §17 | §3 is law. A task may not silently reverse a row. This plan **adds** D66 and D67. |
| `CLAUDE.md` | tmux `-L` rule, inert-fixture rule, frozen-probe rule. Safety, not style. |
| `docs/plans/m4-blockers/README.md` | Why the ledger is one file per task, and why ids are never reused. |
| `src/shepherd/toolsurface/tools_rename.py` | The smallest complete worked example of registering a verb. |
| `src/shepherd/store/migrations/002_m2_stop_verdicts.sql` | The `PRAGMA defer_foreign_keys=ON` idiom 004 copies rather than re-derives. |
| `src/shepherd/runner/pane.py` | Already parses the permission and trust dialogs from the frozen probe captures. U17 extends it; it does not start over. |
| `/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/ui/shepherd-dark.html` | The clickable prototype. 3855 lines: ~1841 CSS, ~280 markup, ~1670 script. **A mock, not the contract** — where it omits something the shipped page has (the stop-summary strip) the shipped page wins. |
| `docs/probes/2026-09-14-schemas/tmux-tui/` | **Frozen evidence, read-only.** U17's parser is built and tested against these captures; not one byte of them is edited. |

**Durability horizon.** The store verbs, the migration and the tool surface are
**stable**. The route table and the projections are **stable**. The page modules
are **near-term-refactor** — W3's work sources will reopen `projects.js` and
`settings.js`. The prototype-porting notes are **session-only**.

---

## Codebase Reality Check — what the source says, against the documents

Eleven findings. **Four contradict a document** and are stated here rather than
planned around. N1 and N2 were new at revision 2 and were named by neither the
design, the recon, nor the first review; **N2 is restated at revision 3 because
revision 2 diagnosed it wrongly.**

1. **CONFIRMS.** `POST_ROUTES` holds 10 entries today (`web/routes.py:71-85`);
   `tests/web/test_routes_m3.py:112` asserts
   `checked == len(routes.POST_ROUTES) - 1 == 9`. Five new POST routes make it
   `== 14`.
2. **CONFIRMS.** `tests/web/test_routes.py:89-114` is a closed-set literal of
   all 11 GET paths, widened by hand.
3. **CONFIRMS.** `moved_paths` (`tests/boundaries/_imports.py:229-240`) uses
   `was.get(path) != now.get(path)`, so absent-on-both reads as *not moved* —
   the `chat.js` trap, reproduced independently here before the coordinator's
   correction arrived. **`chat.js` keeps its filename** (ADR-P3).
4. **CONFIRMS.** `test_no_remote_script_sources` already forbids a remote
   `<link href>`, so the drop-the-webfont decision is mechanically enforced and
   needs no new test.
5. **CONFIRMS.** The prototype contains no `setInterval` and no
   `requestAnimationFrame`, so `test_no_polling_in_the_ui` survives the port.
6. **CONFIRMS.** `core.stops.PALETTE`'s labels have exactly three consumers
   outside `stops.py` — `orchestration/wake.py:139` uses `.glyph` only, and two
   test files. The renames are low blast radius.
7. **CONTRADICTS `docs/design/ui-decisions.md`.** That file says *"Everything in
   the prototype is `textContent`."* **It does not.** The prototype contains
   **eight** `innerHTML` assignments (measured: `grep -c innerHTML` == 8). Seven
   build inline SVG by string concatenation — lines 2520, 2688, 2796, 2837,
   2858, 3101, 3617 — and one, `prose.innerHTML = line[1]` at line 2814, assigns
   a bare variable. `unsafe_sinks` allows a sink only when its right-hand side is
   a **single** quoted literal with no concatenation, so **all eight are
   findings**.

   **Assigned by enclosing function, not by line proximity** — revision 3's
   split named a task (`T4.3`) that does not exist and put three of them in the
   wrong module. The mapping below was recovered by walking each line back to
   its top-level function in the prototype, and it is the authoritative one:

   | line | enclosing function | ships in | task |
   |---|---|---|---|
   | 2520 | `renderLegend()` | `flock.js` | T6.1 |
   | 2858 | `BACK_BUTTON(level)` | `flock.js` | T6.1 |
   | 2688 | `bylineMark()` | `session.js` (the Flock's third pane, D67) | T6.3 |
   | 2796 | `renderDetail()` — the `<details>` step | `session.js` | T6.3 |
   | 2814 | `renderDetail()` — `prose.innerHTML = line[1]`, **the one bare variable** | `session.js` | T6.3 |
   | 2837 | `renderDetail()` — the send-button icon | `session.js` | T6.3 |
   | 3101 | `BACK_BUTTON_P()` | `projects.js` | T9.1 |
   | 3617 | `panelHead(title)` | `settings.js` | T7.2 |

   **T5.3 rewrites none of them** — the shell has no sink, and revision 3's
   "the shell's back chevron" was wrong: both back chevrons belong to pages.
   **T7.1 rewrites none either** — `chat.js` already has no sink
   (`test_the_chat_page_has_no_html_sink`), and the prototype's Shepherd thread
   is static markup; `renderDetail` is the *session pane's* renderer, which D67
   puts in `session.js`. Totals: T6.1 = 2, T6.3 = 4, T7.2 = 1, T9.1 = 1.
8. **CONTRADICTS `docs/design/ui-decisions.md`.** That file says *"Spend one
   `post_milestone` declaration on the whole redesign."* `post_milestone_paths`
   (`_imports.py:242-266`) asserts `len(seen) == len(set(seen))` — entries are
   **per path, not per edit**. **Seven** entries are needed (M6): `rail.js`
   (rewritten), `fleet.js`, `flock.js`, `projects.js`, `settings.js`, and
   **`session.js`**. **Six, not seven** — `escape.js` stays byte-unchanged
   (ADR-P6), so it never enters `moved_paths` at all.
9. **CONTRADICTS nothing, but no input document mentions it.**
   `tests/boundaries/collected_node_ids.txt` freezes **1480** node ids, and
   retirement entries must carry a reason over 80 characters and a decision
   string containing `"§"` or `"RD-"`. This work retires **seventeen**; the
   per-file walk is in the next section.
10. **N1 — CONTRADICTS nothing written down, and it breaks three tests.**
    Migration 004 seeds the `unassigned` row, so a fresh database is **no longer
    empty of projects**. Three assertions go red:
    **two** assertions go red: `tests/web/test_fleet_page.py:104`
    (`projects["projects"] == []`) and `tests/signals/test_binding.py:54`
    (`len(store.list_workspaces()) == 1`). Both are **body rewrites** — the
    seeded project is real and the tests should say so — and both are named in
    T1.5's sweep.
    **`tests/daemons/test_controld.py:313` is NOT one of them** (corrected at
    revision 4, F12): it asserts `"no sessions discovered yet" in body`, a
    **static markup literal** that the seeded row cannot affect. Listing it
    would invite a builder to "repair" a green assertion, which is how a real
    check gets weakened while nobody is looking.
    Good news, verified: `fleet_tree` groups over rows that exist, so an empty
    `unassigned` project does **not** appear in `data["workspaces"]`, and
    `test_controld.py:318`'s `data["workspaces"] == []` stays green.
11. **N2 — eight tests select a project by position, and the seed moves it.**
    *(Restated at revision 3: revision 2 got the premise wrong.)*
    `reads.list_workspaces` **does** have an `ORDER BY` — `SELECT * FROM
    workspace ORDER BY name` (`reads.py:102`). So the hazard is not an
    unspecified order; it is a **specified order whose first element changes.**
    Under SQLite's default BINARY collation uppercase sorts before lowercase,
    measured on this host (3.45.1):

    ```
    ORDER BY name -> ['Unassigned', 'api', 'payments-api', 'shepherd']
    ```

    So once 004 seeds `"Unassigned"`, every `store.list_workspaces()[0]`
    returns **the reserved project** instead of the one the fixture created.
    **Eight** sites, measured
    (`grep -rn "list_workspaces()\[0\]" tests/ | wc -l` == 8):
    `test_retry_link.py:55`, `test_store_delegation.py:57`,
    `test_store_delegation.py:365`, `test_admission.py:384`,
    `test_lifecycle.py:726`, `test_wake_reads.py:113`,
    `test_master_turn.py:217`, `test_wake.py:195`.
    `test_store_delegation.py:365` is the clearest: it asserts
    `list_workspaces()[0].name == "shepherd"` and will read `"Unassigned"`.

    **This is good news and the plan says so: the failure is deterministic**,
    not a flake. It fails identically on every machine and every SQLite build,
    so it cannot hide, cannot pass locally and fail in CI, and cannot be
    mistaken for something intermittent.

    **Adding `ORDER BY name, id` would repair nothing** — revision 2 proposed
    it, and it would have left a reader believing the hazard was closed. The
    repair is that **no test selects a project by position**: T1.5 rewrites all
    eight to select by name or by the id the fixture captured, and the exit
    check `grep -rn "list_workspaces()\[0\]" tests/` (which was always the
    right check, just attached to the wrong diagnosis) holds it there.
    `test_lifecycle.py:726` has to be rewritten regardless — it reads
    `.root_path`, which D57 removes.

**Corollary the plan obeys everywhere:** *prefer rewriting a test's body to
renaming it.* A test keeps its node id when the property survives and the name
does not name a location the redesign removed.

---

## The frozen node-id walk — seventeen retirements, named per file

Walked test by test. **Everything not listed as a retirement is a body rewrite
that keeps its node id.**

| File | Frozen ids | Retired | Kept | The decision string each retirement carries |
|---|---|---|---|---|
| `tests/store/test_migration_003.py` | 12 | **1** | 11 | `"§7 rule 2, re-anchored by §3 D57's migration 004"` |
| `tests/web/test_rail.py` | 7 | **7** (all) | 0 | `"§3 D66"` |
| `tests/orchestration/test_admission.py` | 15 | **4** | 11 | `"§3 D57"` |
| `tests/signals/test_discovery.py` | 3 | **3** (all) | 0 | `"§3 D57 / RD-2"` |
| `tests/store/test_store_delegation.py` | 15 | **1** | 14 | `"§3 D57"` |
| `tests/web/test_frontend_escaping.py` | 5 | **0** | 5 | — (`escape.js` is kept, ADR-P6) |
| `tests/web/test_fleet_page.py` | 17 | **1** | 16 | `"§12 (the Session view header already carries the list) with §3 D67"` |
| `tests/web/test_session_page.py` | 16 | **0** | 16 | — (D67 retains the view) |
| `tests/web/test_palette.py` | 7 | **0** | 7 | — (the stop-summary strip is kept) |
| `tests/web/test_session_wiring.py` | 10 | **0** | 10 | — (D67 retains reachability) |
| `tests/web/test_routes.py`, `test_routes_m3.py`, `test_frontend_no_build_step.py` | 27 | **0** | 27 | — (literals widened, names untouched) |
| **Total** | | **17** | | |

**The four in `test_admission.py`**, each `"§3 D57"`:
`test_a_repo_registered_outside_its_workspace_root_is_admitted`,
`test_a_workspace_with_no_root_path_still_admits_its_registered_repos`,
`test_the_workspace_root_stays_a_permitted_root_beside_the_repos`,
`test_a_workspace_with_neither_a_root_nor_a_repo_refuses_everything`.
Each names a column that no longer exists or asserts behaviour D57 reverses.
Each gets a named successor in the same file.

**The one in `test_migration_003.py`:**
`test_future_schema_refuses_to_start_at_four` — see T1.1. Its eleven siblings
in that module, and all 21 frozen ids in `test_migrations.py` and
`test_migration_002.py`, survive as body rewrites of the version-3 literals.

**The one in `test_store_delegation.py`:**
`test_upsert_workspace_updates_a_moved_root_path` (RD-1 deletes the verb; the
property it protected is now `add_repo`'s and is asserted by E6).

**None in `test_frontend_escaping.py`.** Revision 2 retired
`test_escape_html_exists_and_is_used_where_required` in order to delete
`escape.js`. The owner reversed that at revision 3: the file stays
byte-unchanged, the test stays live, and `UNREACHABLE_BY_DESIGN` in
`tests/web/test_session_wiring.py:55-63` — whose reason string quotes that very
test — is **left alone**. That reason string is the argument: a helper whose
exemption cites a live test is documented, not forgotten.

**The one in `test_fleet_page.py`:** `test_stopped_row_renders_why_and_first_action`.
It asserts `function_body(source, "stoppedRow")` contains `session-why` and
`actions[0]`. U7's card carries four things and no more, so after the redesign a
*row* renders neither — the name would be false. The other sixteen survive,
including `test_expanded_row_lists_every_action_with_its_source`, because in the
three-pane Flock the third pane **is** the expansion, so "expanding a row lists
every action with its source" stays literally true.

---

## Hidden-Assumption Pass

| # | Assumption | Class | Evidence / what would falsify it |
|---|---|---|---|
| A1 | Migration 004's SQL applies clean with `foreign_key_check` empty against real 001–003 with real rows | `proven_by_code` | Rehearsed before the design was written. T1.1 re-proves it as a test rather than trusting the rehearsal. |
| A2 | `ALTER TABLE repo DROP COLUMN workspace_id` succeeds on the FK-referencing side | `proven_by_code` | Probed against SQLite 3.45.1. T1.1 asserts the host's `sqlite3.sqlite_version >= "3.35"` so the probe's answer applies here. |
| A3 | A `HUMAN`-audience call to a `local_destructive` tool needs no approval card | `proven_by_code` | `toolsurface/policy.py` docstring, DP2/K23. |
| A4 | New routes are permitted by the additive gate | `proven_by_code` | `test_the_pre_m4_route_mappings_are_unchanged` (`:170`) is a **subset** check. |
| A5 | `playwright` + chromium work headless in this venv | `proven_by_code` | `import playwright` succeeds; the tool already ran against the prototype. **But it is not a declared dependency either** (`pyproject.toml:15`), and `tools/render_check.py:29` imports `playwright.sync_api` at **module level** — so a test that loads that module by path makes playwright a suite import (F13). Marker deselection does not help: `-m 'not live'` deselects *after* collection imports the module. `tests/tools/test_render_check_args.py` therefore opens with `pytest.importorskip("playwright")`. |
| A6 | `esprima` is importable but **not** a declared dependency | `proven_by_code` | `pyproject.toml:15` lists only `claude-agent-sdk` and `anyio`. **No suite test may import it.** |
| A7 | Deleting `fleet.js` and adding `flock.js` passes the freeze with two `post_milestone` entries | `proven_by_code` | Simulated through the real helpers; recon §I. |
| A8 | `PaneState.dialog_text` carries the permission dialog's numbered option lines | `inferred` | `pane.py:215` detects the dialog from `PERMISSION_MARKER` **plus a numbered option line**, so the lines are on the screen; that they survive into `dialog_text` is the inference. **Falsified by** T8.1's first assertion, which stops and writes `t8-1.md` rather than widening the capture path. |
| A9 | Deriving `last_activity_at` at read time is fast enough here | `inferred` | One `GROUP BY` over `session`, a table this deployment holds in the hundreds. No index added; if it ever matters, that is a later migration. |
| A10 | The `unassigned` row's `owner_id` matches every other row's | `proven_by_code` | 004's `INSERT` **omits `owner_id` entirely** so the column default in `001_m1_foundation.sql:30-37` applies. A hard-coded `'local'` would be a second definition site of a value the schema already owns. |
| A11 | `session.js` and `terminal.js` can be restyled without changing `terminal.js`'s bytes | `inferred` | All styling lives in `app.css`. **If `terminal.js` must change**, it becomes an **eighth** `post_milestone` entry and the task says so rather than absorbing it. |

---

## Behavior Contract (critical_path)

### `delete_project` — the state machine

`delete_project(workspace_id, on_running)` where
`on_running ∈ {"refuse", "kill", "orphan"}`, default `"refuse"`.

| Given | `on_running` | Then |
|---|---|---|
| `workspace_id == "unassigned"` | any | **Refused.** `deleted=False`, `refused="the Unassigned project cannot be deleted"`. Nothing written. |
| no such project | any | **Refused**, `refused="there is no project …"`. Nothing written. |
| exists, **no** running sessions | any | Deleted. Cascade order inside one writer transaction: `mailbox_message` → `session` → `project_repo` → `workspace`. `repo` rows are **kept**. |
| exists, ≥1 running session | `"refuse"` | **Refused**, naming the count, `running=(session_id, …)`. Nothing written. The page renders the three choices from this. |
| exists, ≥1 running session | `"kill"` | Each running session is killed through the existing kill path, then the cascade runs. `killed=(…)`. |
| exists, ≥1 running session | `"orphan"` | Each session's `workspace_id` becomes `"unassigned"`; the rest cascades; the orphaned sessions survive and stay visible on Flock. `orphaned=(…)`. |
| any other string | — | **Refused at the schema** (`enum` in `input_schema`), before the handler. |

**Invariant, and the reason `orphan` is a correctness requirement not a
courtesy:** `Store.fleet()` is an **INNER** `JOIN workspace`
(`reads.py:~205-215`). A session whose workspace row vanished disappears from
the Flock page with no trace. So no code path may leave a `session` row pointing
at a deleted `workspace`.

### Binding, after the join table

`bind_cwd_to_repo(store, cwd)` **never raises** (`binding.py:213`). Kept verbatim.

| Branch | Today | After |
|---|---|---|
| not a repo (`:223`) | `upsert_workspace(basename(cwd), cwd)` | `workspace_id = "unassigned"`, anomaly counted as today |
| bare repo (`:232`) | `upsert_workspace(basename(cwd), cwd)` | `workspace_id = "unassigned"`, anomaly counted as today |
| new repo (`:251`) | creates a workspace **and** a repo | creates the **repo only**, unattached; `workspace_id = "unassigned"` |
| known common dir (`:240-247`) | reads `known.workspace_id` off the repo row | resolves through `project_repo`: exactly one project → that one; more than one → `"unassigned"` (D60); none → `"unassigned"` (D59) |

### `_registered_roots` — §13's allowlist, after D57

Population becomes **the project's registered repo paths alone**. Four
properties survive verbatim:

- matching is over **path components**, never strings (`admission.py:184`);
- **innermost wins** (D22, `:188`);
- an empty allowlist is a **refusal**, not permission (`:170-175`);
- a stored path that will not canonicalize is **named and refused**, never
  silently dropped (`:141-143`) — a silent drop narrows the allowlist and then
  lies about it.

### The session view, after D67

The view is **relocated, not deleted**. It becomes the Flock's third pane
(U9: *"projects → session cards → the session, and the session is shaped like
the Shepherd conversation"*). `session.js`, `terminal.js` and
`web/static/vendor/xterm.js` are **retained and reachable**. On a phone the
three panes are a drill-down with a back chevron. D21's `next_actions` list
renders in this pane's header, which is where §12 already put it.

---

## Edge-Case Catalogue (critical_path)

Every test named here has an owning module and a building task in the
**Test Ownership Index**.

| # | Edge case | Where it is decided | Test |
|---|---|---|---|
| E1 | `/work/api` and `/personal/api` — two projects, same basename | `create_project` (no name match) | `test_two_projects_may_share_a_name` — **must fail against today's code first** |
| E2 | migration 004 run twice | the `schema_migration` ledger | `test_migration_004_is_idempotent_across_two_runs` |
| E3 | 001–003 edited after being applied | `migrate.py:141-153` | `test_the_recorded_checksums_of_001_to_003_are_unchanged` |
| E4 | a repo in two projects, session discovered | `bind_cwd_to_repo` steady state | `test_a_repo_in_two_projects_binds_a_discovered_session_to_unassigned` |
| E5 | a repo in **no** project | same branch | `test_an_orphaned_repo_binds_to_unassigned_and_the_repo_row_survives` |
| E6 | re-adding a path whose repo row was orphaned | `add_repo` + `ux_repo_path` | `test_re_adding_an_orphaned_path_rebinds_the_same_repo_row` |
| E7 | `add_repo` onto `"unassigned"` | guard | `test_unassigned_refuses_add_repo` |
| E8 | `rename_project("unassigned", …)` | guard | `test_unassigned_refuses_rename` |
| E9 | `delete_project("unassigned")` | guard | `test_unassigned_refuses_delete` |
| E10 | `add_repo` with a path that will not canonicalize | **the tool, not the store** — `store/` takes a connection and does no filesystem I/O | `test_add_repo_refuses_a_path_that_does_not_canonicalize` |
| E11 | spawn into a project with zero repos | `_registered_roots` → empty | `test_a_project_with_no_repo_refuses_everything` |
| E12 | a stored repo path that stops canonicalizing | `admission.py:141-143` | existing `test_a_registered_root_that_will_not_canonicalize_refuses_and_names_itself`, body rewritten, **node id kept** |
| E13 | `delete_project` while a session is mid-turn | default refuse | `test_delete_refuses_by_default_and_names_the_running_sessions` |
| E14 | tool handler raises | `registry.py:69` (`GENERIC_ERROR = "request failed"`) and `registry.py:318-319` (where the correlation id is recorded against the failure) | `test_the_projects_page_renders_the_correlation_id` |
| E15 | every page hidden at once (U18) | `[hidden] { display: none !important }` | `test_app_css_carries_the_hidden_reset` |
| E16 | a `needs_you` pane the parser cannot read | `read_decision` returns `None` | `test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses` |
| E17 | C15's workspace-trust dialog | `PaneKind.TRUST` named explicitly | `test_the_trust_dialog_is_named_and_never_answered_blind` |
| E18 | an **attached** session (no pty of ours) | card renders read-only | `test_an_attached_session_renders_the_decision_read_only` |
| E19 | a session with no timestamp at all (U8) | `never seen`, not `just now` | `test_a_session_with_no_timestamp_reads_never_seen` |
| E20 | an **idle** session | no decision card at all (U11) | `test_an_idle_session_gets_no_decision_card` |
| E21 | a fresh install now has one project, not zero (**N1**) | 004 seeds `unassigned` | `test_a_fresh_install_holds_exactly_the_unassigned_project` |
| E22 | the seeded project leads the ordered list, so `[0]` is the wrong project (**N2**) | `reads.py:102`'s existing `ORDER BY name` + BINARY collation | `test_unassigned_leads_the_ordered_project_list` |
| E23 | a repo registered through the UI must bind a later discovered session (**F5**) | `add_repo` probes git for `git_common_dir`, D48's binding key; a path that does not probe is refused, never stored with a placeholder | `test_a_ui_registered_repo_binds_a_discovered_session_to_that_project` |
| E24 | the suite must not import `playwright` (**F13**) | `pytest.importorskip("playwright")` as the first statement of the tool test | `test_the_tool_test_skips_rather_than_importing_playwright` |

---

## Provable Properties (critical_path)

| # | Property | Proved by | Mutation that reddens it |
|---|---|---|---|
| P1 | **Total over the delete matrix.** Every `(exists, has_running, on_running)` triple has a defined outcome and none is silent. | `test_delete_is_total_over_its_matrix`, building `itertools.product` at test time | Remove one branch from `delete_project`. |
| P2 | **No orphaned session row.** After any outcome, `SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)` is 0. | `test_no_session_ever_points_at_a_deleted_project`, after every cell of P1 | Reorder the cascade to delete `workspace` first. |
| P3 | **The FK graph is intact after 004.** | `test_migration_004_leaves_foreign_key_check_empty` | Drop the `project_repo` backfill. |
| P4 | **Binding never raises**, over a matrix of cwd shapes. | `test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix` | Let one branch propagate `OSError`. |
| P5 | **The allowlist never silently narrows.** | `test_every_registered_path_is_either_admitted_or_named_in_the_refusal` | Replace the refusal at `:141-143` with a `continue`. |
| P6 | **One label table.** | existing `tests/web/test_palette.py::test_palette_matches_core_stops` | Change a label in the JS without changing `stops.py`. |
| P7 | **The page never re-derives the order.** | existing `tests/web/test_palette.py::test_the_page_does_not_re_derive_the_order` | Port the prototype's `fleetSortKey`. |
| P8 | **Zero HTML sinks.** | existing `tests/web/test_frontend_escaping.py::test_no_unescaped_interpolation_in_frontend` | Port any one of the prototype's eight `innerHTML` assignments verbatim. |
| P9 | **The freeze equality holds**, over exactly **six** `post_milestone` entries. | existing `tests/boundaries/test_consumer_surface_frozen.py::test_a_rebase_declares_every_path_whose_digest_moved` | Add `flock.js` without declaring it; declare `app.css` twice; or declare the byte-unchanged `escape.js`. |
| P10 | **No frozen test vanished unaccounted.** | existing `tests/boundaries/test_collected_node_ids.py::test_every_node_id_frozen_at_step_0b_still_collects` | Delete `tests/web/test_rail.py` without a retirement entry. |
| P11 | **Every served page renders**, six pages × two viewports, from a real `controld`. | `tests/web/test_render_live.py::test_every_page_renders_at_both_widths` (`@pytest.mark.live`) | Omit the `[hidden]` reset; ship a module with a syntax error. |
| P12 | **Every declared body field is a real property of its tool's schema.** | existing `tests/web/test_routes_m3.py::test_the_route_table_declares_every_query_and_body_field` | Declare `on_running` in `BODY_ARGS` but omit it from `delete_project`'s schema. |
| P13 | **No path parameter is shadowed by a body field** — for `project_id` as well as `session_id` (**M1**). | existing `tests/web/test_routes_m3.py::test_no_body_field_shadows_a_path_parameter`, widened | Declare `project_id` in a `BODY_ARGS` tuple. |

---

## Purity Boundary Map (critical_path)

| Layer | Pure? | What may cross |
|---|---|---|
| `core/stops.py` `PALETTE` | pure data | label/colour/glyph/who_acts. The **only** label table. |
| `runner/pane.py` (incl. new `read_decision`) | **pure** — bytes + format fields in, dataclasses out | `PaneState` → `DecisionPrompt \| None` |
| `store/reads.py`, `store/writes.py` | take a `sqlite3.Connection`; **no filesystem I/O at all** — which is why E10's canonicalization is the tool's job | rows → dataclasses |
| `store/db.py` `Store` | the one writer thread | delegation only, no logic |
| `signals/binding.py` | I/O (git subprocess), never raises | `RepoBinding` |
| `orchestration/admission.py` | filesystem `resolve()` only | `Path` list or `SpawnRefused` |
| `toolsurface/tools_projects.py` | composition, projection, path validation, **and the git probe** — it runs `probe_repo` / `repo_root` / `resolve_remote` in a subprocess, so it is the one new module in this plan that is **not** pure. Named rather than implied (F5): `writes.add_repo` needs `git_common_dir`, and `git_common_dir` is D48's binding key. | `dict[str, object]` |
| `web/routes.py` | a path→name table. **No logic, ever.** | `Resolved` |
| `web/static/*.js` | DOM only, `textContent` only | — |

---

## Safety Rules — absolute, for every task in this plan

1. **`tmux`: pass `-L` on every invocation. Never `kill-server` without it.**
   The user's live sessions are on the `shepherd` socket (`m3`, `master`) —
   never named in a write, never touched. A command run *inside* tmux inherits
   `$TMUX` and resolves to that session's own socket, so `-L` on the session is
   not enough. Never put `:` in a session name. **No task in this plan creates,
   attaches to, or tears down a tmux session**; a revision that needs one uses
   a throwaway socket (`tmux -L shepherd-render …`) on every command, teardown
   included.
2. **Never write anywhere under `~/.claude/`.** The engine's config directory is
   injected as a value and never defaulted to the user's real one.
3. **A planted violation is an inert fixture that nothing imports.** It lives in
   `tests/boundaries/fixtures/`, is read as text or parsed as an AST, and is
   never on an import path the suite executes. A shadow tree isolates *files*;
   it does not isolate signals, subprocesses, sockets, ports or the host. Never
   plant a signal, a `kill`, a reboot-capable call or a teardown verb into
   executable code at all.
4. **`docs/probes/` is frozen evidence.** Phase 8 builds a parser *against* it
   and edits not one byte. `git status --porcelain docs/probes/` is in T8.1's
   and T10.2's required checks for exactly this reason.
5. **Never `rm -rf` under the repo except `__pycache__`.** Deletions here are of
   named files, one at a time, each with its manifest declaration and its
   node-id retirement.
6. **Clear `__pycache__` before any mutation run** — a size-preserving mutation
   landing in the same second as the last compile re-imports the *unmutated*
   bytecode and records a false survivor.

---

## Durable Decisions — the facts every phase references

Written once, never re-decided inside a phase. A task that finds itself choosing
one of these has drifted.

| Surface | The decision | Phase |
|---|---|---|
| **Schema version** | `EXPECTED_SCHEMA_VERSION = 4`; one migration, `004_projects.sql`, append-only, `00N_` numbering | 1 |
| **Project identity** | `workspace.id`. Names are labels; two projects may share one. | 1 |
| **Repo↔project** | the `project_repo` join table; `repo` has no `workspace_id` | 1 |
| **Reserved project** | the literal id `"unassigned"`, defined once at `store.models.UNASSIGNED_PROJECT_ID`, seeded by 004, and **`owner_id` is omitted from the INSERT** so the schema default applies | 1 |
| **Delete semantics** | cascade in the verb, ordered `mailbox_message → session → project_repo → workspace`; `on_running` defaults to refuse | 1 |
| **Orphaned repo rows** | kept, to preserve D48 binding identity under `ux_repo_path` | 1 |
| **Read ordering** | `list_workspaces` keeps its existing `ORDER BY name` (`reads.py:102`) and `list_repos` its `ORDER BY root_path` — **neither is changed**. What changes is that **no caller selects a project by position**: BINARY collation puts the seeded `"Unassigned"` first, so `[0]` is the reserved project (**N2**). | 1 |
| **Discovery policy** | `bind_cwd_to_repo` is the one chokepoint; it creates no project and binds to `"unassigned"` wherever it cannot resolve one | 1 |
| **Allowlist model** | §13's population is the project's registered repo paths alone; component matching, innermost wins, empty means refuse, an uncanonicalizable path is named and refused | 1 |
| **Consumer key spelling** | the project key is **`project_id`** — in all seven tool schemas, in every route template, and in every projection. `project_workspace` already spells it that way (`tools_m1.py:151-158`); a second spelling is the drift D57 exists to close (**M1**). | 2 |
| **Blast classes** | `create_project` / `add_repo` / `delete_project` = `LOCAL_DESTRUCTIVE`; `rename_project` / `remove_repo` = `LOCAL_WRITE`; `list_repos` / `get_project` = `LOCAL_READ`; audiences `{MASTER, HUMAN}` | 2 |
| **Auth posture** | a `HUMAN`-audience call needs no approval card (`policy.py`, DP2/K23). Nothing in this project adds an auth surface. | 2 |
| **API shape** | 14 GET routes, 15 POST routes, `len(BODY_ARGS) == 15`; `web/routes.py` stays a path→tool table with no logic; additions only, never a re-point | 3, 7 |
| **Retirement-entry format** | every `RETIRED_NODE_IDS` value is `(reason, decision)` where the **reason exceeds 80 characters** and the **decision contains `"§"` or `"RD-"`** — `test_collected_node_ids.py:166-174` asserts both. `"the design's file-layout row"` would fail (**B5**). | all |
| **Third-party boundary** | none added. No npm, no build step, no CDN, no webfont, no new file type. | 4 |
| **Label source of truth** | `core.stops.PALETTE`. There is no UI-side label table, ever. | 5 |
| **Module filenames** | `fleet.js` → `flock.js`; **`chat.js` keeps its name** (ADR-P3); `session.js`, `terminal.js`, `sse.js` and `vendor/` are **retained** (D67); new modules `projects.js`, `settings.js` | 4–8 |
| **Ordering on the page** | server-side only (`fleet_bucket_sort_key`). The page renders the order it is handed. | 5 |
| **What stays on the Flock header** | the legend **and** the stop-summary strip — `#stop-summary`, `#unknown-rate`, `#low-confidence`. Principle 5: the unknown rate is displayed, never hidden. | 4, 5 |
| **Where D21's actions render** | the session **pane**, not the card. U7's four-item card is unchanged; §12 already places the list in the Session view header. | 5 |

---

## Phase Dependency Map

**There is no Phase 2.** It was folded into Phase 1 at revision 2 (B1) and its
number is **retired rather than re-flowed**, so every reference already written
down still resolves. Ten phases run.

| Phase | Depends on | Enables |
|---|---|---|
| 0 — tooling and ledger | — | 10 (the live harness), every task (the ledger) |
| 1 — migration, store, binding, admission, the project projection | 0 | 3 |
| ~~2~~ | *retired — folded into 1* | |
| 3 — tool surface | 1 | 4 |
| 4 — routes | 3 | 5, 7, 8 |
| 5 — UI shell + D66 | 0, 4 | 6, 7, 8, 9 |
| 6 — Flock page + D67's third pane | 5 | 7, 8, 9 |
| 7 — Shepherd + Settings | 6 | 10 |
| 8 — U17 decision card | 4, 6 | 10 |
| 9 — Projects page | 4, 6 | 10 |
| 10 — live verification | 7, 8, 9 | the release gate |

**Serialization rule (M2).** Phases **7, 8 and 9 run one at a time, never
concurrently.** All three edit the same four files —
`src/shepherd/web/static/index.html`, `src/shepherd/web/static/app.css`,
**`src/shepherd/web/static/app.js`**, and
`tests/boundaries/consumer_manifest.json`. Two builders editing one manifest is
the M3 shared-ledger hazard wearing a different hat: the file that records what
changed is the file least able to survive a concurrent rewrite. Their internal
order is free (7→8→9, 9→8→7, any permutation); their overlap is not.

---

## Phase Plan

Ten phases. **The suite is green at every phase boundary.** Where a phase's
internal task boundaries are *not* green, the phase says so and why.

Legend: **AFK** = `checkpoint_type: none`. **HITL** = human checkpoint with a
reason category.

---

### Phase 0 — Verification tooling and the ledger

**Objective:** make the acceptance commands real before anything they decide
exists. Every later clause names a file this phase builds.
**Autonomy:** AFK.
**Test Seams:** unit (argument parsing); integration (the tool against a
throwaway static server).
**What this phase does NOT prove:** that any page is correct. Only that the
checker can reach a served page and fails on a page it should fail on.

#### Task 0.1 — `render_check.py` learns to point at a server

- **Files:** `tools/render_check.py`, `tools/js_syntax_check.py` *(new)*,
  `tests/tools/test_render_check_args.py` *(new)*
- **Dependencies:** none
- **Allowed Scope:** argument handling (`--url` for a served origin, `--file`
  for the prototype); **`PAGES` grows from four entries to six (M5)** —
  `("shepherd", …)`, `("flock", …)`, `("queues", …)`, `("projects", …)`,
  `("kanban", …)`, `("settings", …)`, each with a `must_see` string that is
  present on the **served** page, not merely on the prototype; a `--fail-on-empty`
  arrival check. The two selectors the tool drives — `.nav-item[data-page="…"]`
  and `#drawer-open` — become named module constants so the shell and the
  checker cannot drift apart silently.
- **Out-of-Scope Drift:** changing any assertion the tool already makes;
  touching `src/`; adding `tools/` to `pythonpath` in `pyproject.toml`.
- **Expected Artifacts:** `render_check.check(origin: str, shots: Path) -> int`
  accepting both `http(s)://…` and a filesystem path.
- **Required Checks:** `.venv/bin/python -m pytest tests/tools -q`;
  `.venv/bin/mypy --strict tools/render_check.py` *(advisory — `pyproject.toml`
  sets `mypy_path = "src"` (line 49) and `pythonpath = ["src"]` (**line 53**),
  so `tools/` is outside both; recorded so the next reader knows it was run, not
  that it gates)*.
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `tests/tools` passes; `PAGES` has six entries and
  `NAV_SELECTOR` / `DRAWER_SELECTOR` are named constants; the tool still runs
  against the prototype file; `grep -rn "esprima" tests/` is empty (A6); and
  **the suite collects and passes with playwright uninstalled** — proved by
  running the collection with the package hidden
  (`.venv/bin/python -m pytest tests/tools -q -p no:cacheprovider` under a
  `sys.path` that cannot see it, or simply by asserting the
  `pytest.importorskip("playwright")` call is the module's first statement via
  an AST read). (F13)
- **Consumes:** none
- **Produces:** `tools/render_check.py::check(origin, shots)`,
  `tools/render_check.py::PAGES` (six entries),
  `tools/render_check.py::NAV_SELECTOR`,
  `tools/render_check.py::DRAWER_SELECTOR`,
  `tools/js_syntax_check.py::main(paths) -> int`

> **Import mechanics, stated because guessing them is how this task stalls.**
> `pyproject.toml:53` sets `pythonpath = ["src"]`, so `import render_check` does
> **not** work from a test. `tests/tools/test_render_check_args.py` loads the
> tool by path with
> `importlib.util.spec_from_file_location("render_check", REPO_ROOT / "tools" / "render_check.py")`.
> No `tests/tools/__init__.py` — `tests/store/` has none either, and nothing
> cross-imports this package.
>
> `tools/js_syntax_check.py` imports `esprima`. **No file under `tests/` may
> import it** (A6): a suite import would make a green run depend on an
> undeclared package. It is an acceptance command, not a gate.
>
> **The same hazard reaches playwright by a different door (F13).**
> `tools/render_check.py:29` does `from playwright.sync_api import sync_playwright`
> at module level, and this task's test loads that module by path — so a plain
> `pytest tests/tools` would import playwright. `-m 'not live'` does **not**
> save it: deselection happens after collection has already imported the module.
> The test's **first statement** is therefore
> `pytest.importorskip("playwright")`, and T0.1's exit asserts the suite still
> collects and passes on a machine where playwright is absent.

#### Task 0.2 — the blockers ledger, one file per task

- **Files:** `docs/plans/projects-ui-blockers/README.md` *(new)*
- **Dependencies:** none
- **Allowed Scope:** the directory and its README.
- **Out-of-Scope Drift:** writing any entry.
- **Expected Artifacts:** the directory, with its rule written down.
- **Required Checks:** `test -d docs/plans/projects-ui-blockers`
- **Validation Level:** Manual (file exists).
- **Checkpoint Type:** none
- **Exit Criteria:** README states — one file per task, named
  `docs/plans/projects-ui-blockers/<task-id>.md` (e.g. `t1-1.md`); nobody opens
  another task's file; entries are
  `T<id> · symptom · what was tried · what it blocks · owner`; **ids are never
  reused** (which is also why there is no Phase 2); an entry is never deleted,
  only retired in place. **Never a shared ledger.**
- **Consumes:** none
- **Produces:** `docs/plans/projects-ui-blockers/`

---

### Phase 1 — Migration 004, the store, and the `src/` half of the schema change

**Objective:** the schema, the store verbs, **and every `src/` module the schema
change breaks**, in one phase — because a phase that ends with two known-broken
`src/` modules is not a phase boundary (B1).
**Autonomy:** AFK, except T1.1's exit which is **HITL (`manual-verification`)**:
an irreversible migration gets one human look at the applied schema.
**Test Seams:** unit (`store/writes.py`, `store/reads.py` against an in-memory
connection); unit (`_registered_roots`, `bind_cwd_to_repo` against a temp git
tree); unit (`project_workspace` as a pure projection, T1.10); integration
(`Store` across its one writer thread); integration (the migration runner
against a real file database with real rows); integration (both discovery lanes
through `discovery_loop` and `hook_lane`); integration (`/api/projects` through
`tests/web/conftest.py::Client`, which is the seam F2 showed was unguarded).
**Green at the boundary:** yes.
**Green at the internal task boundaries T1.1→T1.10:** **no, by construction.**
`repo.workspace_id` cannot both exist and not exist, so expand–contract is
unavailable for a single rehearsed migration. The design settled on one
migration; this plan does not reopen it. These nine tasks share the phase's green
promise, and **nothing outside Phase 1 starts until it is kept.** **T1.10 is
the task that makes it true** (F2): it is the last `src/` module the schema
change breaks, and `/api/projects` is a suite path, not a `mypy` path.
**What this phase does NOT prove:** that any of it is reachable from a tool, a
route or a page. Seven verbs with no caller are seven unproven verbs — Phase 9
is where they are proved. It also does not prove the hook lane's other three
call sites (`hook_lane.py:165,179,203`) under load, only that each gets a
`RepoBinding` with a non-null `workspace_id`.

> **Task-id note.** T1.7–T1.9 were T2.1–T2.3 at revision 1. **T1.10 is new at
> revision 4** (F2) and was T3.2's first half at revisions 1–3. Both mappings
> are recorded so a ledger entry written against any spelling resolves.

#### Task 1.1 — migration 004

- **Files:** `src/shepherd/store/migrations/004_projects.sql` *(new)*,
  `src/shepherd/store/migrate.py` (one constant),
  `tests/store/test_migration_004.py` *(new)*,
  **`tests/store/test_migrations.py`**, **`tests/store/test_migration_002.py`**,
  **`tests/store/test_migration_003.py`** (the version-3 literals — **F1**),
  `tests/boundaries/test_collected_node_ids.py` (one retirement)
- **Dependencies:** none
- **Allowed Scope:** the SQL exactly as the design rehearsed it, plus
  `PRAGMA defer_foreign_keys=ON` copied from `002:37`; `EXPECTED_SCHEMA_VERSION`
  `3 → 4`.
  **The version-3 sweep, which is not optional and is the reason those three
  modules are in Files (F1).** `EXPECTED_SCHEMA_VERSION` is compared against a
  hard-coded `3` in **19 places** across them —
  `grep -rn "== 3\b" tests/store/test_migrations.py tests/store/test_migration_002.py tests/store/test_migration_003.py`
  is the enumeration — including `test_migrations.py:70,77,100-103,142`,
  `test_migration_002.py:123,136-137,260,296` and
  `test_migration_003.py:186,203-204,228,409,448`. T1.1's own Required Checks
  run exactly these modules, so **without this sweep T1.1 cannot pass its own
  checks.** Every one is a body rewrite; **one is not.**
  **The one retirement: `tests/store/test_migration_003.py::test_future_schema_refuses_to_start_at_four`.**
  It migrates to 3 and then inserts a `schema_migration` row at version **4** to
  build "a database from the future" (`:420-434`). Migration 004 makes version 4
  real, and `schema_migration.version` is `INTEGER PRIMARY KEY`
  (`001_m1_foundation.sql:22`), so that insert becomes a **PK collision** — it
  stops being the future-schema refusal it asserts. Decision string
  **`"§7 rule 2, re-anchored by §3 D57's migration 004"`**, reason over 80
  characters: *the test builds its impossible sentinel by inserting version 4,
  and 004 makes 4 the real current version, so the row collides on the primary
  key instead of tripping §7 rule 2; the rule itself is unchanged and is
  re-proved one version up by the named successor
  `test_future_schema_refuses_to_start_at_five`.*
- **Out-of-Scope Drift:** touching 001–003; adding a trigger; a semicolon inside
  a string literal; numbering outside `00N_`; rebuilding `session`.
- **Expected Artifacts:** `004_projects.sql` containing, in order —
  `ALTER TABLE workspace ADD COLUMN description TEXT;`
  `CREATE TABLE project_repo (workspace_id … REFERENCES workspace(id), repo_id … REFERENCES repo(id), added_at …, PRIMARY KEY (workspace_id, repo_id));`
  `INSERT INTO project_repo … SELECT workspace_id, id, added_at FROM repo;`
  `ALTER TABLE repo DROP COLUMN workspace_id;`
  `ALTER TABLE workspace DROP COLUMN root_path;`
  `CREATE INDEX ix_repo_common_dir ON repo(git_common_dir);`
  `INSERT INTO workspace (id, name, description, created_at) VALUES ('unassigned', …);`
  — **`owner_id` is deliberately omitted from that INSERT** so the column default
  in `001_m1_foundation.sql:30-37` applies (A10). Hard-coding `'local'` would be
  a second definition site of a value the schema already owns.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/store/test_migration_004.py tests/store/test_migrations.py tests/store/test_migration_002.py tests/store/test_migration_003.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** **human_verify** — print `PRAGMA table_info` for
  `workspace`, `repo` and `project_repo` from a migrated copy of a real database
  and have a person read it once.
- **Exit Criteria:** (a) applies clean over a database built by 001→003 **with
  rows in `workspace`, `repo`, `session` and `mailbox_message`**; (b)
  `PRAGMA foreign_key_check` returns no rows; (c) every pre-existing `repo` row
  has exactly one `project_repo` row with the same `added_at`; (d) the
  `unassigned` row exists and its `owner_id` equals the schema default, read
  from `PRAGMA table_info` rather than typed twice; (e) re-running `migrate()`
  is a no-op; (f) 001–003's recorded sha256 are unchanged; (g)
  `sqlite3.sqlite_version >= "3.35"` is asserted, so A2's probe applies here and
  a host that regresses says so; the 19 version-3 literals are updated and
  `tests/store` is green; exactly one retirement, whose successor
  `test_future_schema_refuses_to_start_at_five` inserts version **5** and proves
  §7 rule 2 unchanged.
- **Consumes:** none
- **Produces:** `004_projects.sql`, `project_repo` (table), `ix_repo_common_dir`,
  `workspace.description`, `EXPECTED_SCHEMA_VERSION = 4`, the seeded project id
  `"unassigned"`

#### Task 1.2 — models and rows

- **Files:** `src/shepherd/store/models.py`, `src/shepherd/store/rows.py`
- **Dependencies:** T1.1
- **Allowed Scope:** `Workspace` loses `root_path`, gains
  `description: str | None`; `Repo` loses `workspace_id`; new
  `UNASSIGNED_PROJECT_ID: Final[str] = "unassigned"` — **the one definition
  site** (`tests/boundaries/test_one_definition_site.py` is the rule); new
  `OnRunning(StrEnum)` with `REFUSE`/`KILL`/`ORPHAN`; new frozen
  `DeleteOutcome(deleted, refused, running, killed, orphaned)`.
- **Out-of-Scope Drift:** touching `Session`, `FleetRow` or any stop field.
- **Required Checks:** `.venv/bin/mypy --strict src/shepherd/store` ·
  `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `mypy --strict` clean over `src/shepherd/store`; the 105
  boundary rules green.
- **Consumes:** `project_repo`, `workspace.description`
- **Produces:** `shepherd.store.models.UNASSIGNED_PROJECT_ID`,
  `shepherd.store.models.OnRunning`, `shepherd.store.models.DeleteOutcome`,
  `Workspace(id, owner_id, name, description, created_at, last_activity_at)`,
  `Repo(id, owner_id, name, root_path, git_common_dir, vcs_remote, active, added_at)`

#### Task 1.3 — reads

- **Files:** `src/shepherd/store/reads.py`, `tests/store/test_verbs.py`
- **Dependencies:** T1.2
- **Allowed Scope:** `list_repos` keeps its signature and its
  `ORDER BY root_path`; its body becomes a join through `project_repo`.
  `list_workspaces` is **left exactly as it is** — it already carries
  `ORDER BY name` (`reads.py:102`) and adding a tiebreak would repair nothing
  and imply the N2 hazard was closed here (it is closed in T1.5). New
  `get_workspace`,
  `projects_for_repo`, `project_last_activity`, `running_sessions_for`, and
  **`repo_counts`** — one `GROUP BY` returning `{workspace_id: count}` for the
  whole list, so the Projects page's `repo_count` is one query and not an
  N+1 loop over `list_repos` (**M4**). `fleet()` stays an INNER JOIN, unchanged.
- **Out-of-Scope Drift:** changing `fleet()`'s ordering or its join kind;
  touching `snapshot`, `wake_candidates` or the stop group; calling
  `list_repos` per project anywhere.
- **Required Checks:** `.venv/bin/python -m pytest tests/store -q` ·
  `.venv/bin/mypy --strict src/shepherd/store`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `tests/store` green; E22's
  `test_unassigned_leads_the_ordered_project_list` passes — it pins the measured
  fact (`['Unassigned', 'api', 'payments-api', 'shepherd']`) so the next reader
  meets it as a documented consequence rather than as a surprise; `repo_counts`
  answers N projects in one statement, asserted by counting statements through a
  tracing connection.
- **Consumes:** `shepherd.store.models.UNASSIGNED_PROJECT_ID`, `project_repo`
- **Produces:**
  `reads.get_workspace(connection, workspace_id: str) -> Workspace | None`
  `reads.list_repos(connection, workspace_id: str) -> list[Repo]`
  `reads.list_workspaces(connection) -> list[Workspace]` *(unchanged)*
  `reads.projects_for_repo(connection, repo_id: str) -> list[str]`
  `reads.project_last_activity(connection) -> dict[str, str]`
  `reads.repo_counts(connection) -> dict[str, int]`
  `reads.running_sessions_for(connection, workspace_id: str) -> list[Session]`

#### Task 1.4 — the lifecycle writes

- **Files:** `src/shepherd/store/writes.py`, `tests/store/test_verbs.py`
- **Dependencies:** T1.3
- **Allowed Scope:** `create_project`, `rename_project`, `delete_project`,
  `add_repo`, `remove_repo`. `upsert_workspace` **deleted** (RD-1). `upsert_repo`
  keeps its name, loses `workspace_id`, and becomes the path-identity upsert
  `add_repo` builds on.
- **Out-of-Scope Drift:** killing a session here —
  `delete_project(on_running="kill")` **delegates** to the existing kill path;
  the store does not learn about runners. Adding `ON DELETE CASCADE` anywhere.
  **Any filesystem call** — `Path.resolve()` belongs to the tool (E10, and the
  purity map says so).
- **Required Checks:** `.venv/bin/python -m pytest tests/store -q` ·
  `.venv/bin/mypy --strict src/shepherd/store`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P1 and P2 pass; E1, E6, E7, E8, E9, E13 pass, plus
  `test_delete_with_kill_stops_them_then_cascades` and
  `test_delete_with_orphan_moves_them_to_unassigned`. E1 is **shown red against
  today's code before the fix lands** — a test that has never failed has not
  been proved to bite.
- **Consumes:** `shepherd.store.models.OnRunning`,
  `shepherd.store.models.DeleteOutcome`,
  `shepherd.store.models.UNASSIGNED_PROJECT_ID`,
  `reads.running_sessions_for(connection, workspace_id: str) -> list[Session]`
- **Produces:**
  `writes.create_project(connection, *, name: str, description: str | None) -> Workspace`
  `writes.rename_project(connection, *, workspace_id: str, name: str) -> Workspace | None`
  `writes.delete_project(connection, *, workspace_id: str, on_running: OnRunning, kill: Callable[[str], None]) -> DeleteOutcome`
  `writes.add_repo(connection, *, workspace_id: str, root_path: str, name: str, git_common_dir: str, vcs_remote: str | None) -> Repo`
  `writes.remove_repo(connection, *, workspace_id: str, repo_id: str) -> bool`

#### Task 1.5 — the sweep: `root_path`, `upsert_workspace`, and the seeded row

- **Files:** the **35** test modules that call `upsert_workspace` (measured:
  `grep -rl "upsert_workspace" tests/ --include=*.py | wc -l` == 35), plus those
  reading `Workspace.root_path` / `Repo.workspace_id`, plus `tests/golden/corpus.py`,
  plus the **two** N1 sites (`tests/web/test_fleet_page.py:104`,
  `tests/signals/test_binding.py:54` — **not** `test_controld.py:313`, F12),
  plus the **eight** N2 sites listed in Codebase Reality Check #11, plus
  `tests/boundaries/test_collected_node_ids.py` for the one retirement.
- **Dependencies:** T1.4
- **Allowed Scope:** mechanical only —
  `store.upsert_workspace(name, root)` → `store.create_project(name=name, description=None)`
  plus, where the fixture needed the path admissible, `store.add_repo(...)`;
  `tests/golden/corpus.py::Binding.root_path` → `repo_root`;
  **N1:** the two "empty" assertions become assertions about the one seeded
  project (E21's `test_a_fresh_install_holds_exactly_the_unassigned_project` is
  the new positive statement of it);
  **N2:** all eight `store.list_workspaces()[0]` sites select the project they
  mean **by name or by the id the fixture captured**, never by position —
  because BINARY collation makes `[0]` the seeded `"Unassigned"`.
  **One** `RETIRED_NODE_IDS` entry for
  `tests/store/test_store_delegation.py::test_upsert_workspace_updates_a_moved_root_path`,
  decision string **`"§3 D57"`**, reason over 80 characters: *the column and the
  verb it pinned are both removed by D57; the property it protected — that a
  moved path updates the existing row rather than minting a second under
  `ux_repo_path` — is now `add_repo`'s and is asserted by E6's
  `test_re_adding_an_orphaned_path_rebinds_the_same_repo_row`.*
- **Out-of-Scope Drift:** changing what any test asserts beyond N1's three. If a
  test cannot be made green mechanically, **stop and write
  `docs/plans/projects-ui-blockers/t1-5.md`** rather than weakening it.
- **Required Checks:** `.venv/bin/python -m pytest -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** whole suite green; exactly one new retirement;
  `grep -rn "upsert_workspace" src/ tests/` returns nothing;
  `grep -rn "list_workspaces()\[0\]" tests/` returns nothing.
- **Consumes:** `writes.create_project(connection, *, name: str, description: str | None) -> Workspace`,
  `writes.add_repo(connection, *, workspace_id: str, root_path: str, name: str, git_common_dir: str, vcs_remote: str | None) -> Repo`,
  `reads.list_workspaces(connection) -> list[Workspace]` *(unchanged)*
- **Produces:** a green suite on the new store shape;
  `tests/golden/corpus.py::Binding(workspace_id, repo_id, repo_root)`

#### Task 1.6 — `Store` delegation

- **Files:** `src/shepherd/store/db.py`, `tests/store/test_store_delegation.py`
- **Dependencies:** T1.5
- **Allowed Scope:** one delegating method per new verb, same names, through the
  one writer thread. Remove `Store.upsert_workspace`.
- **Out-of-Scope Drift:** logic in `db.py`. It delegates; it does not decide.
- **Required Checks:** `.venv/bin/python -m pytest tests/store -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_every_delegated_write_crosses_the_one_writer_thread`
  and `test_every_delegated_verb_is_refused_once_the_store_is_closed` cover every
  new verb.
- **Consumes:** every `writes.*` and `reads.*` name from T1.3/T1.4
- **Produces:** `Store.create_project`, `Store.rename_project`,
  `Store.delete_project`, `Store.add_repo`, `Store.remove_repo`,
  `Store.get_workspace`, `Store.projects_for_repo`, `Store.project_last_activity`,
  `Store.repo_counts`, `Store.running_sessions_for`, **`Store.upsert_repo`**

#### Task 1.7 — `bind_cwd_to_repo` binds to `Unassigned` *(was T2.1)*

- **Files:** `src/shepherd/signals/binding.py`, `tests/signals/test_binding.py`
- **Dependencies:** T1.6
- **Allowed Scope:** the four-branch table in the Behavior Contract; delete
  `_workspace_name`; D62's switch (3) written as a switch and **shipped on**.
- **Out-of-Scope Drift:** making `bind_cwd_to_repo` raise; touching switches (1)
  and (2) — they are W2.
- **Required Checks:** `.venv/bin/python -m pytest tests/signals -q` ·
  `.venv/bin/mypy --strict src/shepherd/signals`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P4, E4, E5 pass, plus
  `test_a_non_repo_cwd_binds_to_unassigned_and_counts_the_anomaly` and
  `test_the_new_session_lands_in_that_project`; `RepoBinding.workspace_id` is
  still non-optional; the *"never raises"* docstring is unchanged **and true**.

> **F10, and it is a live hazard, not a typo.** Revision 3's Consumes named
> `Store.add_repo`. That verb attaches a repo **to a project**; the new-repo
> branch must register the repo row **unattached**. Following revision 3 would
> have put every discovered repo into `project_repo` under the reserved id, and
> `_registered_roots("unassigned")` would then widen to every repo the machine
> has ever seen — a §13 allowlist that grows by discovery. The verb is
> `Store.upsert_repo`.

- **Consumes:** `shepherd.store.models.UNASSIGNED_PROJECT_ID`,
  `Store.projects_for_repo`, `Store.upsert_repo`
- **Produces:** `bind_cwd_to_repo(store, cwd) -> RepoBinding` with
  `workspace_id` never null and never auto-created

#### Task 1.8 — `discover_repos` is deleted (RD-2) *(was T2.2)*

- **Files:** delete `src/shepherd/signals/discovery.py`, delete
  `tests/signals/test_discovery.py`; `tests/boundaries/test_collected_node_ids.py`
  (three retirements)
- **Dependencies:** T1.7
- **Allowed Scope:** the deletion and three `RETIRED_NODE_IDS` entries, decision
  string **`"§3 D57 / RD-2"`**, reason over 80 characters: *the module's sole
  documented justification is `workspace.root_path` (`discovery.py:1`), which
  migration 004 removes; it had no caller anywhere in `src/`; and U14 has repo
  paths typed into the Edit dialog rather than scanned for, so wiring it would
  mean building a caller to justify a module.*
- **Out-of-Scope Drift:** deleting `probe_repo` or `resolve_remote`, which
  `binding.py` imports.
- **Required Checks:** `.venv/bin/python -m pytest -q` ·
  `! grep -rn "discover_repos" src/ tests/` ·
  `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** no reference to `discover_repos` anywhere; three retirement
  entries present, each passing the >80-character and `"§"`-or-`"RD-"` checks;
  suite green.
- **Consumes:** none
- **Produces:** none *(a deletion; the artifact is the absence and its record)*

#### Task 1.9 — the allowlist becomes the repo paths alone *(was T2.3)*

- **Files:** `src/shepherd/orchestration/admission.py`,
  `tests/orchestration/test_admission.py`,
  `tests/boundaries/test_collected_node_ids.py` (four retirements)
- **Dependencies:** T1.7
- **Allowed Scope:** delete the `list_workspaces()` comprehension at `:129-133`;
  use `Store.get_workspace` for existence and `Store.list_repos` for the
  population; rewrite the T11-1 comment block to say what it now means. Four
  retirements, decision string **`"§3 D57"`**, each with a >80-character reason
  and a named successor in the same file.
- **Out-of-Scope Drift:** changing component matching to string matching;
  changing innermost-wins; turning an empty allowlist into permission; replacing
  the canonicalize-refusal with a silent drop. **Rewrite the bodies of the other
  eleven frozen tests in this file; do not rename them.**
- **Required Checks:** `.venv/bin/python -m pytest tests/orchestration -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` ·
  `.venv/bin/mypy --strict src/shepherd/orchestration`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P5, E11, E12 pass, plus
  `test_add_repo_widens_the_allowlist` and
  `test_a_registered_repo_admits_a_spawn`; the five parametrised escape cases
  (`sibling_of_the_repo`, `repo_name_is_a_string_prefix`,
  `traversal_out_of_the_repo`, `symlink_out_of_the_repo`, `the_repos_parent`)
  still refuse with their node ids intact.
- **Consumes:** `Store.get_workspace`, `Store.list_repos`
- **Produces:** `_registered_roots(store, workspace_id) -> list[Path] | SpawnRefused`
  over repo paths alone

#### Task 1.10 — the `project_workspace` projection, because Phase 1 must end green

- **Files:** `src/shepherd/toolsurface/tools_m1.py`,
  `tests/toolsurface/test_tools_m1.py`, `tests/web/test_fleet_page.py`
- **Dependencies:** T1.6
- **Allowed Scope:** **F2, and it is B1's shape on a third module B1 did not
  enumerate.** `project_workspace` reads `workspace.root_path`
  (`tools_m1.py:156`) and is reached from `list_projects` (`:363-364`), which
  `/api/projects` serves and `tests/web/test_fleet_page.py:102` calls. T1.2
  removes that field, so leaving the repair in Phase 3 would end Phase 1 with a
  **suite failure, not merely a `mypy` finding**.
  `project_workspace()` drops `root_path`, gains `description` and
  `repo_count`, and takes `last_activity_at` and `repo_count` as arguments fed
  from `Store.project_last_activity` and `Store.repo_counts` — **one query each
  for the whole list**, never an N+1 (M4, RD-3). The consumer key stays
  `project_id`. `list_projects` is rewired to pass them.
- **Out-of-Scope Drift:** registering anything (that is T3.1); touching
  `compose.py` (T3.2); touching `fleet_tree`'s ordering; calling `list_repos`
  once per project.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/toolsurface tests/web/test_fleet_page.py -q` ·
  `.venv/bin/mypy --strict src/shepherd`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** **the whole suite is green and `mypy --strict src/` is
  clean** — this is the task that makes Phase 1's green boundary true;
  `test_the_project_list_issues_a_bounded_number_of_statements` passes.
- **Consumes:** `Store.project_last_activity`, `Store.repo_counts`,
  `Workspace(id, owner_id, name, description, created_at, last_activity_at)`
- **Produces:** `project_workspace(workspace, *, repo_count: int, last_activity_at: str | None) -> dict[str, object]`
  with keys `project_id`, `name`, `description`, `repo_count`, `last_activity_at`

---

### Phase 2 — *retired*

Folded into Phase 1 at revision 2 (B1). The number is not re-used and not
re-flowed: ids in this repo are permanent, and re-flowing would silently
invalidate every reference already written into the review, the contract and the
ledger.

---

### Phase 3 — The tool surface: seven verbs

**Objective:** one implementation the master and the HTTP API both reach (D58).
**Autonomy:** AFK.
**Test Seams:** unit (`build_project_tools()` schemas); integration (`invoke()`
through the registry with a composed chokepoint).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that any route reaches these tools (Phase 4)
or that a person can drive them (Phase 9).

#### Task 3.1 — `toolsurface/tools_projects.py`

- **Files:** `src/shepherd/toolsurface/tools_projects.py` *(new)*,
  `tests/toolsurface/test_tools_projects.py` *(new)*,
  `tests/toolsurface/test_tools_m3.py` (the module-cap enumeration)
- **Dependencies:** Phase 1
- **Allowed Scope:** seven `ToolDef`s.
  **Every schema spells the project key `project_id` (M1)** — the same spelling
  `project_workspace` already emits (`tools_m1.py:151-158`) and the same
  spelling the route templates use, so a body field can never quietly mean
  something a path parameter does not.
  `create_project`, `add_repo`, `delete_project` → `LOCAL_DESTRUCTIVE` (D58);
  `rename_project`, `remove_repo` → `LOCAL_WRITE`; `list_repos`, `get_project`
  → `LOCAL_READ`. Audiences `{MASTER, HUMAN}` for all seven.
  `delete_project`'s schema carries `on_running` as
  `{"type": "string", "enum": ["refuse", "kill", "orphan"]}` with **no schema
  default**, and `OnRunning.REFUSE` as the handler's fallback — default-refuse
  must be unskippable by omission.
  **`add_repo` canonicalizes its path here** (E10), because `store/` does no
  filesystem I/O — **and it probes git here too (F5).**
  `writes.add_repo` requires `git_common_dir`, `name` and `vcs_remote`, and the
  route declares only `("root_path",)`. The three are answered by
  `signals/binding.py`'s `probe_repo` (`:158`), `repo_root` (`:163`) and
  `resolve_remote` (`:181`) — a **subprocess**, and a `toolsurface → signals`
  import edge. That edge already exists (`tools_m1.py:33` imports
  `shepherd.signals.ordering`), so it is permitted rather than new; it is named
  here because this module was not previously authorised to use it and a builder
  would otherwise have to invent the values.
  **Why this is more than plumbing:** `git_common_dir` is **D48's binding key**.
  A repo registered through the UI with a guessed or empty `git_common_dir`
  never matches `find_repo_by_common_dir`, so a session started in it binds to
  `Unassigned` — silently, and in exactly the flow the Functionality Flow
  Mapping's step 5 asserts works. A path that does not probe as a repo is
  **refused and says so**; it is never registered with a placeholder.
  **Add the new module to `test_the_three_modules_are_each_under_the_cap`'s
  enumeration** (`len(sizes) == 5` becomes 6); if the module would exceed 450
  lines, split into `tools_projects.py` + `tools_projects_reads.py` and name
  **both** there, so a split cannot hide growth.
- **Out-of-Scope Drift:** registering anything in `tools_m1.py` or `tools_m3.py`;
  a schema that is not `{"type": "object", "properties": {...}}`; an eighth verb;
  spelling the key `workspace_id` on any consumer-facing surface.
- **Required Checks:** `.venv/bin/python -m pytest tests/toolsurface -q` ·
  `.venv/bin/mypy --strict src/shepherd/toolsurface`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** seven tools register and freeze; the cap test names every
  new module; E10 and **E23** pass; `delete_project` with no `on_running`
  refuses a project with a running session; a test asserts all seven schemas
  spell `project_id`; `test_a_ui_registered_repo_binds_a_discovered_session_to_that_project`
  passes, which is the end-to-end statement that the probed `git_common_dir` is
  the same key D48 binds on.
- **Consumes:** every `Store.*` name from T1.6,
  `shepherd.store.models.OnRunning`, `shepherd.store.models.DeleteOutcome`,
  `shepherd.store.models.UNASSIGNED_PROJECT_ID`,
  `probe_repo`, `repo_root`, `resolve_remote`,
  `bind_cwd_to_repo(store, cwd) -> RepoBinding`
  *(the three probe helpers are `shepherd.signals.binding`'s — see Allowed
  Scope for the layer edge that permits the import)*
- **Produces:**
  `PROJECT_TOOL_NAMES: tuple[str, ...] = ("create_project", "rename_project", "delete_project", "add_repo", "remove_repo", "list_repos", "get_project")`
  `build_project_tools(...) -> tuple[ToolDef, ...]`
  `register_project_tools(*, store: Store, kill: Callable[[str], None], now: Clock) -> None`
  `project_repo_row(repo: Repo) -> dict[str, object]`
  `project_detail(workspace, repos, sessions, last_activity_at) -> dict[str, object]`

#### Task 3.2 — compose wiring

- **Files:** `src/shepherd/toolsurface/compose.py`,
  `tests/boundaries/test_composition_root.py`
- **Dependencies:** T3.1
- **Allowed Scope:** call `register_project_tools(...)` **before**
  `install_chokepoint` (`compose.py:457`) and `freeze_registry()` (`:473`).
  Nothing else. **The `project_workspace` projection moved to T1.10** at
  revision 4 (F2), because leaving it here ended Phase 1 with a red suite.
- **Out-of-Scope Drift:** reordering anything else in `compose_tool_surface`;
  touching `tools_m1.py` (T1.10 owns it); changing `fleet_tree`'s ordering.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/toolsurface tests/boundaries -q` ·
  `.venv/bin/mypy --strict src/shepherd`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** a composed process answers all seven; the registry freezes
  without a double-registration refusal; the 105 boundary rules green.
- **Consumes:** `register_project_tools(*, store: Store, kill: Callable[[str], None], now: Clock) -> None`
- **Produces:** a composed process in which all seven project tools are
  reachable through `invoke()`

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
  `"/api/projects/{project_id}/repos" → "list_repos"` (11 → 13; the fourteenth
  arrives in Phase 8).
  `POST_ROUTES` gains `"/api/projects" → "create_project"`,
  `"/api/projects/{project_id}/rename" → "rename_project"`,
  `"/api/projects/{project_id}/delete" → "delete_project"`,
  `"/api/projects/{project_id}/repos/add" → "add_repo"`,
  `"/api/projects/{project_id}/repos/remove" → "remove_repo"` (10 → 15).
  `BODY_ARGS` declares `("name", "description")`, `("name",)`,
  `("on_running",)`, `("root_path",)`, `("repo_id",)` respectively — and
  **never `project_id`**, which is the path parameter (M1, P13).
- **Out-of-Scope Drift:** re-pointing any existing route; any logic in
  `routes.py`; declaring a body field that is not a property of the tool's
  schema.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web/test_routes.py tests/web/test_routes_m3.py -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `/api/projects` (2 segments) is never read as
  `/api/projects/{project_id}` (3); `test_the_pre_m4_route_mappings_are_unchanged`
  green.
- **Consumes:** `PROJECT_TOOL_NAMES: tuple[str, ...] = ("create_project", "rename_project", "delete_project", "add_repo", "remove_repo", "list_repos", "get_project")`
- **Produces:** the seven route templates above

#### Task 4.2 — the three hand-widened literals, and the path-parameter guard

- **Files:** `tests/web/test_routes.py`, `tests/web/test_routes_m3.py`,
  `tests/web/test_routes_projects.py` *(new)*
- **Dependencies:** T4.1
- **Allowed Scope:** three hard-coded numbers, all measured, all in Allowed Scope
  so none is discovered at run time —
  1. `tests/web/test_routes.py:89-114` — the GET closed-set literal, widened by
     hand to 13 entries with a comment in M3's and M4's voice, so the next route
     still has to be declared there;
  2. `tests/web/test_routes_m3.py:112` — `checked == len(routes.POST_ROUTES) - 1 == 9`
     becomes `== 14`;
  3. **`tests/web/test_routes_m3.py:237` — `assert len(routes.BODY_ARGS) == 10`
     becomes `== 15` (B6).**
  Plus **P13 (M1):** widen
  `test_no_body_field_shadows_a_path_parameter` so it asserts **no POST route
  declares `project_id` as a body field either**, and add a positive test in
  `tests/web/test_routes_projects.py` that a body claiming a different
  `project_id` than the URL cannot move the target. Caught in Phase 4, where the
  table is, rather than in Phase 9 where the page is.
- **Out-of-Scope Drift:** loosening any literal into a computed set. A
  closed-set literal is the point; a bare `len()` comparison would pass over a
  route nobody declared.
- **Required Checks:** `.venv/bin/python -m pytest tests/web -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P12 and P13 pass; all three literals name their contents by
  hand; `test_create_project_through_http` passes end to end.
- **Consumes:** the seven route templates
- **Produces:** a green `tests/web` on 13 GET routes, 15 POST routes and
  `len(BODY_ARGS) == 15`

---

### Phase 5 — The UI shell, and the rail's removal

**Objective:** the dark shell — tokens, the `[hidden]` reset, the side pane, six
page roots, the stop-summary strip — and the paperwork for the one decision this
reverses.
**Autonomy:** **HITL (`design-decision`)** at the exit: D66 reverses §12, and §0
forbids taking a reversal quietly.
**Test Seams:** unit (static scans of `index.html` / `app.css` / `app.js`); E2E
(the live render check, Phase 10).
**Green at the boundary:** yes — **after T5.4**. T5.3 → T5.4 is red by
construction (F7): a deleted path and its manifest declaration cannot land in
the same commit without the declaration being written first against a file that
still exists. Declared here rather than discovered, the way Phase 1 declares its
own internal reds.
**What this phase does NOT prove:** that any page has content. The Flock,
Projects and Settings roots are empty shells until Phases 6, 7 and 9. It proves
the shell, the reset, the routing, and that removing the rail was recorded.

#### Task 5.1 — D66, in the same task that deletes the assertion

- **Files:** `docs/specs/orchestrator-platform.md` (§3 row **D66**, §12's rail
  section rewritten to point at it), delete `tests/web/test_rail.py`,
  `tests/boundaries/test_collected_node_ids.py` (seven retirements),
  `tests/qa/test_s4_needs_you_rail.py`
- **Dependencies:** Phase 0
- **Allowed Scope:** **D66** — *"The Needs-You rail leaves the shell. §12's 'on
  every page' is reversed; if the rail returns it lives on the Flock page alone
  (U2)."* — with owner attribution and date, in §3's voice. Seven
  `RETIRED_NODE_IDS` entries, decision string **`"§3 D66"`**, each reason over
  80 characters.
  **§3's headline sentence must move with the row (F15):**
  `docs/specs/orchestrator-platform.md:34` reads *"**65 decisions** (D1–D65,
  plus D38.1, an amendment)"*. D66 makes that false. Update it in this task —
  a section whose own count is wrong is a section that has stopped being
  checkable. `tests/qa/test_s4_needs_you_rail.py` is not frozen: retarget its
  projection assertions at `project_needs_you`, which survives.
- **Out-of-Scope Drift:** deleting `tools_m1.py::project_needs_you` or
  `fleet_summary`'s `needs_you` list — the projection stays, only its renderer
  goes. Writing D66 in a later task than the deletion.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` ·
  `grep -n "D66" docs/specs/orchestrator-platform.md`
- **Validation Level:** Deterministic + Manual (a person reads D66).
- **Checkpoint Type:** **decision** — a numbered reversal of a spec row.
- **Exit Criteria:** D66 exists in §3; §12's rail section points at it; seven
  retirements present, each passing both mechanical checks; suite green.
- **Consumes:** none
- **Produces:** spec row **D66**

#### Task 5.2 — `app.css`: tokens, the reset, the wash

- **Files:** `src/shepherd/web/static/app.css`, `tests/web/test_shell.py` *(new)*
- **Dependencies:** T5.1
- **Allowed Scope:** the prototype's stylesheet, token layer first.
  **`[hidden] { display: none !important; }` is mandatory and explicit** (U18) —
  the recon found this is already a live bug in the shipped page, because
  `.chat-view` is `display: grid` (`app.css:483-488`) and only stays hidden
  because JS also sets `.hidden`.
  **The eight `.bucket-<name> { --bucket-colour: #RRGGBB }` rules keep exactly
  that shape** — `tests/web/test_palette.py::_CSS_BUCKET` parses them back out,
  and the prototype's `:root`-level `--needs-you` spelling would not match. Port
  the hexes into the existing `.bucket-*` blocks and let the prototype's `:root`
  names alias them.
  U16's ~16% wash of the bucket colour over the card ground.
  **System font stack, no `@font-face`, no remote `<link>`.**
  `tests/web/test_shell.py` is **the owning module for E15's
  `test_app_css_carries_the_hidden_reset`** (B7) — it reads `app.css` and
  asserts the rule is present, with `!important`, and is not commented out.
- **Out-of-Scope Drift:** editing `web/static/vendor/`; adding any file that is
  not `.html` / `.js` / `.css`.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web/test_shell.py tests/web/test_palette.py tests/web/test_frontend_no_build_step.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E15 passes **in `tests/web/test_shell.py`**; all eight
  `.bucket-*` rules parse; `test_no_remote_script_sources` green.
- **Consumes:** none
- **Produces:** `app.css` with `[hidden] { display: none !important }` and the
  eight `.bucket-<name>` rules intact; `tests/web/test_shell.py`

#### Task 5.3 — `index.html` and `app.js`: the shell, the routing, the strip

- **Files:** `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`,
  delete `src/shepherd/web/static/rail.js`,
  `tests/web/test_frontend_escaping.py`,
  **`tests/web/test_palette.py`** (F3),
  `tests/web/test_shell.py`
- **Dependencies:** T5.2
- **Allowed Scope:** six page roots (`#page-shepherd`, `#page-flock`,
  `#page-queues`, `#page-projects`, `#page-kanban`, `#page-settings`), the side
  pane, the drawer, the header, the three `<dialog>`s, the static empty-state
  panel (`id="empty-state"` and the literal *"no sessions discovered yet"*, both
  still asserted by frozen tests), and **the stop-summary strip
  `#stop-summary` / `#unknown-rate` / `#low-confidence` (B3)**. `app.js` owns
  page routing and the one `EventSource`. **The prototype's `herd` page id
  becomes `flock` everywhere**, including `render_check.PAGES`.
  **None of the eight `innerHTML` rewrites land here (F6).** The shell has no
  sink; both back chevrons belong to pages (`BACK_BUTTON` → `flock.js`,
  `BACK_BUTTON_P` → `projects.js`). See the table in Codebase Reality Check #7.
  `EXPECTED_MODULES` in `test_frontend_escaping.py` is widened by name (`rail.js`
  drops out, `flock.js` / `projects.js` / `settings.js` come in), never loosened
  into a glob. **`escape.js` stays in that list** and the file stays
  byte-unchanged (ADR-P6).
  **`tests/web/test_palette.py` is edited here, not one phase later (F3).**
  `test_palette.py:97` iterates `("fleet.js", "app.js", "rail.js")` and reads
  each file, so deleting `rail.js` raises `FileNotFoundError` at a boundary this
  plan declares green. Drop `"rail.js"` from that tuple **in this task**; the
  `"fleet.js"` → `"flock.js"` half of the same literal is T6.1's, for the same
  reason one task later.
  **This task retires nothing** and makes **no** edit to
  `UNREACHABLE_BY_DESIGN`.
- **Out-of-Scope Drift:** deleting or renaming `chat.js` (**pinned**); deleting
  `session.js`, `terminal.js`, `sse.js` or `vendor/` (**D67 retains them**);
  **deleting `escape.js` or touching `UNREACHABLE_BY_DESIGN`** (ADR-P6);
  introducing `setInterval` or `requestAnimationFrame`; a second `EventSource`.
- **Required Checks:** `.venv/bin/python -m pytest tests/web -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
  — **`tests/boundaries` is deliberately NOT run here (F7).** Deleting
  `rail.js` moves a path, and the declaration for it is T5.4's; running the
  freeze gate before its own manifest task would be running a check this task
  cannot pass. **T5.3 → T5.4 is a red internal boundary, declared, exactly the
  way Phase 1 declares T1.1 → T1.9.** The phase boundary (after T5.4) is green.
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_every_shipped_module_is_reachable_from_the_page`
  reaches every shipped module; `EXPECTED_MODULES` matches the directory
  exactly; `escape.js` is byte-unchanged
  (`git diff --name-only src/shepherd/web/static/escape.js` is empty) and
  `UNREACHABLE_BY_DESIGN` is untouched; `#stop-summary`, `#unknown-rate`,
  `#low-confidence` and `#empty-state` are all present in the markup; suite
  green, with **zero** new retirements from this task.
- **Consumes:** `app.css`, `tools/render_check.py::PAGES`
- **Produces:** page roots `#page-shepherd`, `#page-flock`, `#page-queues`,
  `#page-projects`, `#page-kanban`, `#page-settings`; `app.js::showPage(name)`;
  dialog ids `#dlg-legend`, `#dlg-project`, `#dlg-delete`; the strip ids
  `#stop-summary`, `#unknown-rate`, `#low-confidence`

#### Task 5.4 — the manifest, declared once and correctly

- **Files:** `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T5.3
- **Allowed Scope:** update every changed path's sha256 in `files`. Add
  `post_milestone.edits` entries for exactly the paths that moved and are not
  already in `rebase.regenerated_paths`: **one path, `web/static/rail.js`** —
  whose 2026-09-20 entry must be **rewritten**, not appended to, because entries
  are per path and the old sentence (*"Comment text only: no statement, no
  selector and no behaviour changed"*) stops being true the moment the file is
  deleted. Leaving it would be a false record in the one gate whose purpose is an
  honest one.
  **`web/static/escape.js` gets no entry** — it is byte-unchanged (ADR-P6), so it
  is not in `moved_paths` and declaring it would be a false record of the other
  kind.
  `app.css`, `app.js`, `index.html` are already in `regenerated_paths` and
  **must NOT be added to `post_milestone`** — that is the trap.
- **Out-of-Scope Drift:** touching `baseline`; touching
  `rebase.regenerated_paths`; adding a path twice; adding `chat.js` anywhere.
- **Required Checks:**
  `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_frozen.py tests/boundaries/test_consumer_surface_additive.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P9 passes.
- **Consumes:** the moved-path set from T5.3
- **Produces:** one `post_milestone` entry (running total: 1 of 6)

---

### Phase 6 — The Flock page, and D67's third pane

**Objective:** U7–U11, U16, U1 — the sessions page, three panes, the legend
sheet, the wash, the stop-summary strip. The three label renames, at their
source. And D67: the session view relocates into the third pane rather than
being deleted.
**Autonomy:** **HITL (`design-decision`)** at T6.3's exit — D67 is a numbered
spec row and §0 forbids taking one quietly.
**Test Seams:** unit (static scans: label/glyph tables, no-sort, no-sink);
integration (`tests/web/conftest.py::Client` over `/api/fleet/tree`).
**Green at the boundary:** yes — **after T6.4**. T6.1 → T6.4 is red by
construction (F7), for the same reason Phase 5's is.
**What this phase does NOT prove:** a pixel. `test_palette.py`'s own docstring
says so: the scan proves the palette the page *ships* is `PALETTE`; the rendering
is Phase 10's live check and the human look there.

#### Task 6.1 — port the render logic with **no HTML sink**

- **Files:** `src/shepherd/web/static/flock.js` *(new)*, delete
  `src/shepherd/web/static/fleet.js`, `src/shepherd/web/static/index.html`,
  `src/shepherd/web/static/app.js`, `tests/web/test_flock_page.py` *(new)*,
  `tests/web/test_fleet_page.py`, **`tests/web/test_palette.py`** (F3)
- **Dependencies:** Phase 5
- **Allowed Scope:** the prototype's three-pane render, `textContent`
  throughout. **Two of the eight `innerHTML` assignments are rewritten here
  (F6)** — `renderLegend()` at prototype line 2520 and `BACK_BUTTON(level)` at
  2858 — as `document.createElementNS` construction or static markup in
  `index.html`.
  U8's relative time spelled out, scaling to years, with `never seen` for no
  timestamp (E19). U16's wash. U10's legend with an **`acts:`** line taken
  verbatim from `PALETTE.who_acts`. U1's `ⓘ` sheet (`#dlg-legend`) —
  hover/focus popover on a pointer device, tap anywhere in the legend opens the
  sheet, rising from the bottom edge on a narrow screen. **The stop-summary
  strip is rendered from `fleet_summary`'s existing payload**, beside the
  legend (B3). `tests/web/test_flock_page.py` owns the new tests (E19, E21's
  page half, `test_unassigned_sessions_render_on_the_flock_page`);
  `tests/web/test_fleet_page.py` **keeps its filename and all 17 test names**
  and its body literals move from `fleet.js` to `flock.js`.
  **`tests/web/test_palette.py` is edited here too (F3)**, in the same breath as
  the deletion that breaks it: its module-level helper `fleet_js()` reads
  `fleet.js` (`:42`) and `test_the_page_does_not_re_derive_the_order` names it
  again (`:97`). Deleting `fleet.js` without them makes **this task's own exit
  criterion ("P7 passes") unsatisfiable**, which is the defect F3 caught.
- **Out-of-Scope Drift:** porting `BUCKET_ORDER`, `fleetSortKey`, `.sort(` or
  `localeCompare` — all four banned by name; porting the Google Fonts link; a
  second label table; putting D21's action list on the card (U7 is four items and
  no more).
- **Required Checks:** `.venv/bin/python -m pytest tests/web -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P7 and P8 pass; E19 and E21's page half pass;
  `test_the_shipped_modules_are_all_there` matches the directory;
  `#unknown-rate` and `#low-confidence` are filled by the page.
- **Consumes:** `app.js::showPage(name)`, `#page-flock`, `#dlg-legend`,
  `#stop-summary`, `#unknown-rate`, `#low-confidence`
- **Produces:** `flock.js::mountFlock()`, `flock.js::renderFlock(tree)`,
  `flock.js::BUCKET_LABEL`, `flock.js::BUCKET_MARK`

#### Task 6.2 — the renames land in `core.stops.PALETTE`

- **Files:** `src/shepherd/core/stops.py`, `tests/test_core_stops.py`,
  `tests/web/test_palette.py`, `tests/web/test_fleet_page.py`,
  `tests/web/test_session_wiring.py`
- **Dependencies:** T6.1
- **Allowed Scope:** three label strings only — `Bucket.UNFINISHED` →
  `"stranded"`, `Bucket.PAUSED` → `"limit exceeded"`, `Bucket.UNCLASSIFIED` →
  `"unknown"`. Update filename literals in the test modules (`"fleet.js"` →
  `"flock.js"`, drop `"rail.js"`), **keeping every test function name** so no
  node id moves.
- **Out-of-Scope Drift:** touching any `Bucket` **value**; touching
  `signals/stop_rules.py`, the store or the 90-day stop log; touching any hex or
  glyph; adding a UI-side label table.
- **Required Checks:** `.venv/bin/python -m pytest -q` ·
  `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P6 passes with **zero** new retirements —
  `git diff --stat tests/boundaries/test_collected_node_ids.py` is empty for this
  task, which is what B3's decision bought.
- **Consumes:** `flock.js::BUCKET_LABEL`
- **Produces:** `PALETTE[Bucket.UNFINISHED].label == "stranded"`,
  `PALETTE[Bucket.PAUSED].label == "limit exceeded"`,
  `PALETTE[Bucket.UNCLASSIFIED].label == "unknown"`

#### Task 6.3 — D67: the session view becomes the third pane

- **Files:** `docs/specs/orchestrator-platform.md` (§3 row **D67**, §12's
  Page 3 rewritten as a pane), `src/shepherd/web/static/session.js`,
  `src/shepherd/web/static/index.html`, `src/shepherd/web/static/app.js`,
  `src/shepherd/web/static/flock.js`, `tests/web/test_session_page.py`,
  `tests/web/test_session_wiring.py`, `tests/web/test_fleet_page.py`,
  `tests/boundaries/test_collected_node_ids.py` (one retirement)
- **Dependencies:** T6.2
- **Allowed Scope:** **D67** — *"The session view relocates into the Flock's
  third pane. It is not deleted: `session.js`, `terminal.js` and
  `web/static/vendor/xterm.js` are retained and reachable from that pane. §12's
  Page 3 is rewritten as a pane rather than a page. D21's `next_actions` list
  renders in that pane's header, which is where §12 already placed it — the
  session **card** carries U7's four items and no more."* — with date and
  attribution, in §3's voice.
  On a phone the three panes are a drill-down with a back chevron.
  **§3's headline count moves again in this task (F15):** it reads `66` after
  T5.1 and must read **`67` (D1–D67, plus D38.1)** after D67 lands.
  **Four of the eight `innerHTML` assignments are rewritten here (F6)** —
  `bylineMark()` (2688) and `renderDetail()`'s three (2796, 2814, 2837). The one
  at 2814, `prose.innerHTML = line[1]`, assigns a **bare variable** and becomes
  `textContent`; the other three build SVG by concatenation and become
  `document.createElementNS`. They land here rather than in `chat.js` because
  `renderDetail` is the *session pane's* renderer, which D67 puts in
  `session.js`.
  `session.js` is restyled and its mount point moves; its **contracts are
  unchanged**. `tests/web/test_session_page.py` keeps all **16** node ids as body
  rewrites. One `RETIRED_NODE_IDS` entry for
  `tests/web/test_fleet_page.py::test_stopped_row_renders_why_and_first_action`,
  decision string
  **`"§12 (the Session view header already carries the list) with §3 D67"`**,
  reason over 80 characters: *the test asserts `stoppedRow` renders `session-why`
  and `actions[0]`, and U7 fixes the card at four items — glyph, title, the ask,
  relative time — so after the redesign no row renders either; the property
  survives at the pane and is asserted by its named successor
  `test_the_session_pane_renders_why_and_every_action`.*
- **Out-of-Scope Drift:** deleting `terminal.js`, `sse.js` or `vendor/`;
  changing `session.js`'s API contracts; changing the terminal's WebSocket path.
  **If `terminal.js`'s bytes must change** (A11), stop and say so — it becomes an
  eighth `post_milestone` entry and the plan's count is wrong, which is worth
  one line in `t6-3.md`.
- **Required Checks:** `.venv/bin/python -m pytest tests/web -q` ·
  *(`tests/boundaries` is T6.4's, for F7's reason: T6.1 and T6.3 move paths
  whose declarations T6.4 writes. **T6.1 → T6.4 is a red internal boundary,
  declared.** The phase boundary, after T6.4, is green.)* ·
  `grep -n "D67" docs/specs/orchestrator-platform.md` ·
  `git diff --stat src/shepherd/web/static/terminal.js src/shepherd/web/static/sse.js`
  (expected: empty)
- **Validation Level:** Deterministic + Manual (a person reads D67).
- **Checkpoint Type:** **decision** — a new numbered spec row.
- **Exit Criteria:** D67 exists in §3; §12's Page 3 reads as a pane; all 16
  `test_session_page.py` ids and all 10 `test_session_wiring.py` ids still
  collect; `terminal.js` and `sse.js` are byte-unchanged; exactly one retirement.
- **Consumes:** `#page-flock`, `flock.js::renderFlock(tree)`, `app.js::showPage(name)`
- **Produces:** spec row **D67**; `session.js` mounted in the Flock's third pane;
  `test_the_session_pane_renders_why_and_every_action`

#### Task 6.4 — manifest

- **Files:** `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T6.3
- **Allowed Scope:** `files` hashes; `post_milestone.edits` entries for
  `web/static/fleet.js` (removed), `web/static/flock.js` (added) — the exact pair
  the recon simulated and confirmed — and **`web/static/session.js` (edited,
  M6)**. State explicitly in this task's ledger note that `web/static/sse.js`,
  `web/static/terminal.js` and `web/static/vendor/*` are **byte-unchanged and
  therefore get no entry**; if that stops being true, the count moves from seven
  to eight and the task says so.
- **Out-of-Scope Drift:** as T5.4.
- **Required Checks:** `.venv/bin/python -m pytest tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** P9 passes; `post_milestone.edits` holds exactly **4** entries — 1 from T5.4 (`rail.js`) plus this task's 3 (`fleet.js`, `flock.js`, `session.js`). Revision 3 said 5, which contradicted this task's own `Produces` (**F4**); a builder satisfying the wrong number would have declared a path that did not move and failed P9's equality.
- **Consumes:** the moved-path set from T6.1 and T6.3
- **Produces:** three `post_milestone` entries (running total: 4 of 6)

---

### Phase 7 — Shepherd and Settings

**Objective:** the conversation page (U6, U11, U12) and Settings' ten sections
(U13), including the audit tail's move.
**Autonomy:** AFK.
**Serialization:** runs alone — see the Phase Dependency Map's serialization
rule (M2).
**Test Seams:** unit (static scans of `chat.js` / `settings.js`); integration
(`Client` over `/api/master/send`, `/api/approvals`, `/api/audit`,
`/api/autonomy`).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that the unbuilt Settings sections do
anything. Nine of ten are labelled placeholders; this phase proves only that each
says **why** in its panel (U13), not that any of them works.

#### Task 7.1 — `chat.js` keeps its name and loses the audit tail

- **Files:** `src/shepherd/web/static/chat.js`,
  `src/shepherd/web/static/index.html`, `src/shepherd/web/static/app.js`,
  `tests/web/test_chat_page.py`
- **Dependencies:** Phase 6
- **Allowed Scope:** the prototype's conversation, composer and inline approval
  card. **None of the eight `innerHTML` assignments are rewritten here (F6).**
  `chat.js` has no sink today (`test_the_chat_page_has_no_html_sink`) and gains
  none: the prototype's Shepherd thread is static markup, and `renderDetail` —
  which revision 3 mis-assigned to this task — is the session pane's renderer
  and belongs to T6.3. The audit tail (`chat.js:242-260` into `#chat-audit`) **moves to
  Settings → Data with its four-field whitelist intact** (`at`, `tool`,
  `decision`, `approved_by`; `args` deliberately excluded per D25). D65: the
  autonomy toggle **leaves this page entirely**.
- **Out-of-Scope Drift:** **renaming or deleting the file** — the freeze pins it.
  Widening the audit whitelist. Leaving an autonomy control on this page.
- **Required Checks:** `.venv/bin/python -m pytest tests/web -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** `test_the_chat_page_has_no_html_sink` green; no autonomy
  control in `chat.js` or `#page-shepherd`'s markup;
  `test -f src/shepherd/web/static/chat.js` succeeds.
- **Consumes:** `#page-shepherd`, `app.js::showPage(name)`
- **Produces:** `chat.js` exporting `mountShepherd()`

#### Task 7.2 — `settings.js`

- **Files:** `src/shepherd/web/static/settings.js` *(new)*,
  `src/shepherd/web/static/index.html`, `src/shepherd/web/static/app.js`,
  `tests/web/test_settings_page.py` *(new)*,
  `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T7.1
- **Allowed Scope:** **one of the eight `innerHTML` rewrites lands here (F6)** —
  `panelHead(title)` at prototype line 3617. Then: ten sections under *Yours*
  (Account, Notifications, API keys) and *This instance* (Autonomy, Shepherd, Discovery, Limits, Users &
  access, Data, System). Real today: Autonomy, Discovery's hook status, Data's
  audit tail, System's facts. Everything else carries a `not built` chip **and
  says why in its panel**. U12: the two autonomy options read *"Ask me before
  anything leaves this machine"* and *"Approve automatically"*, the second
  stating that auto-approved is never unlogged. `shepherd uninstall` is absent
  from the UI entirely.
- **Out-of-Scope Drift:** building any placeholder section; W3's work-source
  configuration (that belongs on the Projects page, D63).
- **Required Checks:** `.venv/bin/python -m pytest tests/web tests/boundaries -q`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** a test asserts every `not built` chip is accompanied by
  non-empty explanatory text in the same panel; the audit whitelist is exactly
  four fields; one `post_milestone` entry for `web/static/settings.js`.
- **Consumes:** `#page-settings`, `app.js::showPage(name)`, the audit whitelist
  from T7.1
- **Produces:** `settings.js` exporting `mountSettings()`; one `post_milestone`
  entry (running total: 5 of 6)

---

### Phase 8 — U17: the decision card's projection

**Objective:** `{text, choices[]}` off a pane snapshot, with three mandatory
degradations.
**Autonomy:** AFK, with a **stop-and-report** gate at T8.1's first step (A8).
**Serialization:** runs alone (M2).
**Test Seams:** unit (`read_decision` as a pure function over the frozen probe
captures — the highest seam that covers the risk); integration (the tool through
`invoke()`); integration (`Client` over the new route).
**Green at the boundary:** yes.
**What this phase does NOT prove:** that the parser survives an engine update. It
cannot — the choices are the engine's and move with its version. What it proves
is that an unrecognised screen **degrades and never guesses**, which is the
property that has to hold across updates.

#### Task 8.1 — `read_decision`, pure, against frozen evidence

- **Files:** `src/shepherd/runner/pane.py`,
  `tests/runner/test_pane_decision.py` *(new)*
- **Dependencies:** Phase 4
- **Allowed Scope:** `Choice(number: int, label: str)` and
  `DecisionPrompt(text: str, choices: tuple[Choice, ...])`; a pure
  `read_decision(state: PaneState) -> DecisionPrompt | None`.
  **First step, before writing the parser:** assert that `PaneState.dialog_text`
  for the frozen permission capture actually carries the numbered option lines.
  If it does not, **stop, write `docs/plans/projects-ui-blockers/t8-1.md`, and
  report** — do not widen the capture path on the way past (A8).
- **Out-of-Scope Drift:** **editing any file under `docs/probes/`** — frozen
  evidence, no exceptions short of `CLAUDE.md`'s three standing conditions.
  Adding I/O, a clock or a process to `pane.py`. Answering a dialog from here.
- **Required Checks:** `.venv/bin/python -m pytest tests/runner tests/boundaries -q` ·
  `test -z "$(git status --porcelain docs/probes/)"` ·
  `.venv/bin/mypy --strict src/shepherd/runner`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E16 passes (unparseable → `None`, never a guess); E17 passes
  (`PaneKind.TRUST` is named and never answered blind — a blind Enter there
  answers *"No, exit"*); `test_the_choices_are_the_engines_own_numbering` passes;
  `docs/probes/` byte-unchanged.
- **Consumes:** `PaneState`, `PaneKind`
- **Produces:** `shepherd.runner.pane.Choice`,
  `shepherd.runner.pane.DecisionPrompt`,
  `shepherd.runner.pane.read_decision(state: PaneState) -> DecisionPrompt | None`

#### Task 8.2 — the tool, the route, and the card

- **Files:** `src/shepherd/toolsurface/tools_terminal.py`,
  `src/shepherd/web/routes.py`, `tests/web/test_routes.py`,
  `src/shepherd/web/static/session.js`, `src/shepherd/web/static/flock.js`,
  `tests/web/test_session_page.py`, `tests/boundaries/consumer_manifest.json`
- **Dependencies:** T8.1
- **Allowed Scope:** a `get_decision` `ToolDef` (`LOCAL_READ`), the route
  `"/api/sessions/{session_id}/decision" → "get_decision"` (API_ROUTES 13 → 14,
  and the closed-set literal widened by hand), and the card's render in the
  Flock's third pane. U11: the engine's own prompt with its numbered choices,
  verbatim — **not** flattened to approve/reject, because that throws away the
  option carrying the scope. E18: an **attached** session renders read-only and
  says so, rather than showing three buttons that go nowhere.
- **Out-of-Scope Drift:** a client-side parser; `innerHTML`; sending a keystroke
  from the read path; a second `post_milestone` entry for `session.js` (T6.4
  already declared it — **entries are per path**).
- **Required Checks:**
  `.venv/bin/python -m pytest tests/web tests/toolsurface tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** E16, E18, E20 pass end to end, plus
  `test_a_needs_you_session_shows_the_engines_own_prompt`; the GET literal names
  14 paths; `test_pty_bytes_never_reach_innerHTML` green.
- **Consumes:** `shepherd.runner.pane.read_decision(state: PaneState) -> DecisionPrompt | None`,
  `shepherd.runner.pane.DecisionPrompt`, `#page-flock`
- **Produces:** the tool name `"get_decision"`; the route
  `"/api/sessions/{session_id}/decision"`

---

### Phase 9 — The Projects page — the acceptance test for the seven verbs

**Objective:** U14 — two panes, `Unassigned` pinned last and visually distinct,
repo paths in full, edited in the Edit dialog. This is the phase that proves
Phases 1–4 shipped something a person can use.
**Autonomy:** **HITL (`manual-verification`)** at the exit.
**Serialization:** runs alone (M2).
**Test Seams:** integration (`Client` over all seven routes); E2E (Phase 10).
**Green at the boundary:** yes.
**What this phase does NOT prove:** W3's work-source configuration — the Work
source block is a `not built` placeholder (D63's fields exist; nothing behind
them does).

#### Task 9.1 — `projects.js`

- **Files:** `src/shepherd/web/static/projects.js` *(new)*,
  `src/shepherd/web/static/index.html`, `src/shepherd/web/static/app.js`,
  `src/shepherd/web/static/app.css`, `tests/web/test_projects_page.py` *(new)*,
  `tests/boundaries/consumer_manifest.json`
- **Dependencies:** Phase 4, Phase 6
- **Allowed Scope:** **one of the eight `innerHTML` rewrites lands here (F6)** —
  `BACK_BUTTON_P()` at prototype line 3101. Then: the list/detail panes;
  `#dlg-project` (create and edit) and
  `#dlg-delete` (the three-way choice rendered **from the refusal**, not from a
  guess); the allowlist warning the prototype carries verbatim — *"A path here
  **widens where Shepherd may start sessions**"* (D22/D58, and it is true).
  Sessions listed on a project are links into the Flock. `Unassigned` is pinned
  last, visually distinct, and its rename/delete/add-repo controls are **absent,
  not merely disabled**.
- **Out-of-Scope Drift:** client-side sorting; a second set of project verbs;
  building the Work source block; spelling the key anything but `project_id`.
- **Required Checks:** `.venv/bin/python -m pytest tests/web tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js`
- **Validation Level:** Deterministic, then Manual.
- **Checkpoint Type:** **human_verify** — drive all five lifecycle verbs in a
  browser, including a delete refused into the three choices.
- **Exit Criteria:** E1, E7, E8, E9, E13, E14 pass through HTTP, plus
  `test_the_delete_dialog_renders_the_three_choices_from_the_refusal` and
  `test_cancel_writes_nothing`; one `post_milestone` entry for
  `web/static/projects.js`; `Unassigned` offers no lifecycle control at all.
- **Consumes:** every route template from T4.1; `#page-projects`,
  `#dlg-project`, `#dlg-delete`, `app.js::showPage(name)`
- **Produces:** `projects.js` exporting `mountProjects()`; one `post_milestone`
  entry (running total: **6 of 6**)

---

### Phase 10 — Live verification against the served page

**Objective:** prove the product, not the design.
**Autonomy:** **HITL (`manual-verification`)** — a person looks at the twelve
screenshots once.
**Test Seams:** E2E (headless chromium against a real `controld` on loopback).
**Green at the boundary:** yes.
**What this phase does NOT prove:** anything about a phone's real browser, a
tunnel, or a slow network. Six pages × two viewports in headless chromium on this
host.

#### Task 10.1 — the live render check

- **Files:** `tests/web/test_render_live.py` *(new)*, `tools/render_check.py`
- **Dependencies:** Phase 9
- **Allowed Scope:** `test_every_page_renders_at_both_widths`, marked
  `@pytest.mark.live`, which starts a real `controld` bound to loopback on an
  ephemeral port against a temporary data directory, waits for it, and calls
  `render_check.check(f"http://127.0.0.1:{port}/", shots)`. **The served page,
  never the prototype file** — that is the difference between testing the design
  and testing the product.
- **Out-of-Scope Drift:** pointing the check at the prototype; binding to
  anything but loopback; any `tmux` invocation without `-L`; touching the
  `shepherd` socket.
- **Required Checks:**
  `.venv/bin/python -m pytest -m live tests/web/test_render_live.py -q`
- **Validation Level:** **Live.**
- **Checkpoint Type:** **human_verify** — the twelve screenshots.
- **Exit Criteria:** P11 passes; zero console errors at 390×844 and 1280×900;
  horizontal overflow ≤ 1px on every page; the `must_see` string found on each of
  the six pages.
- **Consumes:** `tools/render_check.py::check(origin, shots)`,
  `tools/render_check.py::PAGES`, `tools/render_check.py::NAV_SELECTOR`,
  `tools/render_check.py::DRAWER_SELECTOR`, every page root id
- **Produces:** `tests/web/test_render_live.py::test_every_page_renders_at_both_widths`,
  twelve screenshots under the scratchpad

#### Task 10.2 — the whole-tree gate

- **Files:** none (verification only)
- **Dependencies:** T10.1
- **Allowed Scope:** running the gates.
- **Out-of-Scope Drift:** fixing anything. A gate task that repairs what it
  finds has stopped being a gate — a failure here opens a ledger entry and goes
  back to the owning task, it is not patched in place.
- **Required Checks:** `.venv/bin/python -m pytest -q` ·
  `.venv/bin/mypy --strict src/` ·
  `.venv/bin/python -m pytest tests/boundaries -q` ·
  `.venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js` ·
  `test -z "$(git status --porcelain docs/probes/)"`
- **Validation Level:** Deterministic.
- **Checkpoint Type:** none
- **Exit Criteria:** suite green; `mypy --strict` clean; 105 boundary rules
  green; `docs/probes/` byte-unchanged; `post_milestone.edits` holds exactly
  **six** entries.
- **Consumes:** everything
- **Produces:** the release gate result

---

## Test Ownership Index (B7)

**Every test named anywhere in this plan, with the module that holds it and the
task that builds it.** A name that appears in a clause, an edge case or a
property and *not* in this table is the M4 failure shape. This table is the
check; re-running it is `grep`, not memory.

| Test | Module | Task | New or existing |
|---|---|---|---|
| `test_migration_004_leaves_foreign_key_check_empty` | `tests/store/test_migration_004.py` | T1.1 | new |
| `test_migration_004_is_idempotent_across_two_runs` | `tests/store/test_migration_004.py` | T1.1 | new |
| `test_the_recorded_checksums_of_001_to_003_are_unchanged` | `tests/store/test_migration_004.py` | T1.1 | new |
| `test_unassigned_leads_the_ordered_project_list` (E22) | `tests/store/test_verbs.py` | T1.3 | new |
| `test_future_schema_refuses_to_start_at_five` (F1's successor) | `tests/store/test_migration_003.py` | T1.1 | new (replaces the one retirement there) |
| `test_the_project_list_issues_a_bounded_number_of_statements` (M4, AC-15) | `tests/toolsurface/test_tools_m1.py` | **T1.10** | new |
| `test_a_ui_registered_repo_binds_a_discovered_session_to_that_project` (E23) | `tests/toolsurface/test_tools_projects.py` | T3.1 | new |
| `test_the_tool_test_skips_rather_than_importing_playwright` (E24) | `tests/tools/test_render_check_args.py` | T0.1 | new |
| `test_two_projects_may_share_a_name` (E1) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_re_adding_an_orphaned_path_rebinds_the_same_repo_row` (E6) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_unassigned_refuses_add_repo` (E7) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_unassigned_refuses_rename` (E8) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_unassigned_refuses_delete` (E9) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_delete_refuses_by_default_and_names_the_running_sessions` (E13) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_delete_with_kill_stops_them_then_cascades` | `tests/store/test_verbs.py` | T1.4 | new |
| `test_delete_with_orphan_moves_them_to_unassigned` | `tests/store/test_verbs.py` | T1.4 | new |
| `test_delete_is_total_over_its_matrix` (P1) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_no_session_ever_points_at_a_deleted_project` (P2) | `tests/store/test_verbs.py` | T1.4 | new |
| `test_a_fresh_install_holds_exactly_the_unassigned_project` (E21) | `tests/store/test_verbs.py` | T1.5 | new |
| `test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix` (P4) | `tests/signals/test_binding.py` | T1.7 | new |
| `test_a_repo_in_two_projects_binds_a_discovered_session_to_unassigned` (E4) | `tests/signals/test_binding.py` | T1.7 | new |
| `test_an_orphaned_repo_binds_to_unassigned_and_the_repo_row_survives` (E5) | `tests/signals/test_binding.py` | T1.7 | new |
| `test_a_non_repo_cwd_binds_to_unassigned_and_counts_the_anomaly` | `tests/signals/test_binding.py` | T1.7 | new |
| `test_the_new_session_lands_in_that_project` | `tests/signals/test_binding.py` | T1.7 | new |
| `test_every_registered_path_is_either_admitted_or_named_in_the_refusal` (P5) | `tests/orchestration/test_admission.py` | T1.9 | new |
| `test_a_project_with_no_repo_refuses_everything` (E11) | `tests/orchestration/test_admission.py` | T1.9 | new |
| `test_add_repo_widens_the_allowlist` | `tests/orchestration/test_admission.py` | T1.9 | new |
| `test_a_registered_repo_admits_a_spawn` | `tests/orchestration/test_admission.py` | T1.9 | new |
| `test_a_registered_root_that_will_not_canonicalize_refuses_and_names_itself` (E12) | `tests/orchestration/test_admission.py` | T1.9 | **existing, body rewritten** |
| `test_a_directory_outside_every_registered_repo_is_refused[*]` | `tests/orchestration/test_admission.py` | T1.9 | **existing, body rewritten** |
| `test_add_repo_refuses_a_path_that_does_not_canonicalize` (E10) | `tests/toolsurface/test_tools_projects.py` | T3.1 | new |
| `test_every_project_schema_spells_project_id` (M1) | `tests/toolsurface/test_tools_projects.py` | T3.1 | new |
| `test_the_route_table_declares_every_query_and_body_field` (P12) | `tests/web/test_routes_m3.py` | T4.2 | **existing, literals widened** |
| `test_no_body_field_shadows_a_path_parameter` (P13) | `tests/web/test_routes_m3.py` | T4.2 | **existing, widened to `project_id`** |
| `test_create_project_through_http` | `tests/web/test_routes_projects.py` | T4.2 | new |
| `test_a_body_cannot_move_the_project_the_url_names` (M1) | `tests/web/test_routes_projects.py` | T4.2 | new |
| `test_app_css_carries_the_hidden_reset` (E15) | **`tests/web/test_shell.py`** | **T5.2** | **new — this is B7's fix** |
| `test_the_shell_carries_the_stop_summary_strip` (B3) | `tests/web/test_shell.py` | T5.3 | new |
| `test_every_shipped_module_is_reachable_from_the_page` | `tests/web/test_session_wiring.py` | T5.3 | **existing, body rewritten** |
| `test_a_session_with_no_timestamp_reads_never_seen` (E19) | `tests/web/test_flock_page.py` | T6.1 | new |
| `test_unassigned_sessions_render_on_the_flock_page` | `tests/web/test_flock_page.py` | T6.1 | new |
| `test_palette_matches_core_stops` (P6) | `tests/web/test_palette.py` | T6.2 | **existing, body rewritten** |
| `test_the_page_does_not_re_derive_the_order` (P7) | `tests/web/test_palette.py` | T6.2 | **existing, body rewritten** |
| `test_the_session_pane_renders_why_and_every_action` | `tests/web/test_session_page.py` | T6.3 | new (successor to the one retirement) |
| `test_the_chat_page_has_no_html_sink` | `tests/web/test_chat_page.py` | T7.1 | **existing, body rewritten** |
| `test_no_unescaped_interpolation_in_frontend` (P8) | `tests/web/test_frontend_escaping.py` | T7.1 | **existing, module list widened** |
| `test_an_unparseable_dialog_degrades_to_the_ask_and_never_guesses` (E16) | `tests/runner/test_pane_decision.py` | T8.1 | new |
| `test_the_trust_dialog_is_named_and_never_answered_blind` (E17) | `tests/runner/test_pane_decision.py` | T8.1 | new |
| `test_the_choices_are_the_engines_own_numbering` | `tests/runner/test_pane_decision.py` | T8.1 | new |
| `test_an_attached_session_renders_the_decision_read_only` (E18) | `tests/web/test_session_page.py` | T8.2 | new |
| `test_an_idle_session_gets_no_decision_card` (E20) | `tests/web/test_session_page.py` | T8.2 | new |
| `test_a_needs_you_session_shows_the_engines_own_prompt` | `tests/web/test_session_page.py` | T8.2 | new |
| `test_the_projects_page_renders_the_correlation_id` (E14) | `tests/web/test_projects_page.py` | T9.1 | new |
| `test_the_delete_dialog_renders_the_three_choices_from_the_refusal` | `tests/web/test_projects_page.py` | T9.1 | new |
| `test_cancel_writes_nothing` | `tests/web/test_projects_page.py` | T9.1 | new |
| `test_a_rebase_declares_every_path_whose_digest_moved` (P9) | `tests/boundaries/test_consumer_surface_frozen.py` | T5.4, T6.4, T7.2, T9.1 | existing, untouched |
| `test_every_node_id_frozen_at_step_0b_still_collects` (P10) | `tests/boundaries/test_collected_node_ids.py` | T1.5, T1.8, T1.9, T5.1, T5.3, T6.3 | existing, untouched |
| `test_every_page_renders_at_both_widths` (P11) | `tests/web/test_render_live.py` | T10.1 | new |

### Existing gates this plan leans on — edited, or untouched and relied upon

Named in an acceptance clause or an exit criterion, so listed here too. None
needs building; each row says whether a task touches it.

| Test | Module | Touched by | How |
|---|---|---|---|
| `test_every_api_route_names_a_registered_tool` | `tests/web/test_routes.py` | T4.2, T8.2 | GET closed-set literal widened by hand |
| `test_the_pre_m4_route_mappings_are_unchanged` | `tests/boundaries/test_consumer_surface_additive.py` | — | untouched; the additive gate |
| `test_web_server_is_byte_unchanged` | `tests/boundaries/test_consumer_surface_additive.py` | — | untouched; the byte pin |
| `test_the_three_modules_are_each_under_the_cap` | `tests/toolsurface/test_tools_m3.py` | T3.1 | enumeration widened 5 → 6 |
| `test_the_shipped_modules_are_all_there` | `tests/web/test_frontend_escaping.py` | T5.3, T6.1 | `EXPECTED_MODULES` widened by name |
| `test_no_remote_script_sources` | `tests/web/test_frontend_no_build_step.py` | — | untouched; enforces the webfont drop |
| `test_no_polling_in_the_ui` | `tests/web/test_frontend_no_build_step.py` | — | untouched |
| `test_pty_bytes_never_reach_innerHTML` | `tests/web/test_session_page.py` | T8.2 | body rewritten (D67 pane) |
| `test_every_delegated_write_crosses_the_one_writer_thread` | `tests/store/test_store_delegation.py` | T1.6 | widened to the new verbs |
| `test_every_delegated_verb_is_refused_once_the_store_is_closed` | `tests/store/test_store_delegation.py` | T1.6 | widened to the new verbs |
| `test_expanded_row_lists_every_action_with_its_source` | `tests/web/test_fleet_page.py` | T6.1, T6.3 | body rewritten; **node id kept** |
| `test_the_terminal_degrades_to_a_screen_view_when_the_vendor_file_is_absent` | `tests/web/test_session_page.py` | T6.3 | body rewritten; **node id kept** (D67) |
| `test_the_vendor_file_ships_in_a_built_wheel` | `tests/test_packaging.py` | — | untouched; why D67 must keep `vendor/` |
| `test_escape_html_exists_and_is_used_where_required` | `tests/web/test_frontend_escaping.py` | — | **untouched and live** — `escape.js` is kept (ADR-P6) |
| `test_a_stale_exemption_is_caught` | `tests/boundaries/test_collected_node_ids.py` | — | untouched; why revision 2's `escape.js` deletion would have cost a third edit |
| `test_every_retirement_names_its_reason_and_the_decision_that_authorised_it` | `tests/boundaries/test_collected_node_ids.py` | — | untouched; the source of B5's two mechanical rules |

### Retired — no builder, by design

These seventeen are **deleted**, so "nobody builds it" is the correct state, not
a gap. Each carries a `RETIRED_NODE_IDS` entry with a >80-character reason and a
decision string containing `"§"` or `"RD-"`.

| Test | Retired by | Decision string |
|---|---|---|
| `test_future_schema_refuses_to_start_at_four` | T1.1 | `"§7 rule 2, re-anchored by §3 D57's migration 004"` |
| the 7 in `tests/web/test_rail.py` | T5.1 | `"§3 D66"` |
| `test_a_repo_registered_outside_its_workspace_root_is_admitted` | T1.9 | `"§3 D57"` |
| `test_a_workspace_with_no_root_path_still_admits_its_registered_repos` | T1.9 | `"§3 D57"` |
| `test_the_workspace_root_stays_a_permitted_root_beside_the_repos` | T1.9 | `"§3 D57"` |
| `test_a_workspace_with_neither_a_root_nor_a_repo_refuses_everything` | T1.9 | `"§3 D57"` |
| the 3 in `tests/signals/test_discovery.py` | T1.8 | `"§3 D57 / RD-2"` |
| `test_upsert_workspace_updates_a_moved_root_path` | T1.5 | `"§3 D57"` |
| `test_stopped_row_renders_why_and_first_action` | T6.3 | `"§12 (the Session view header already carries the list) with §3 D67"` |

> **How to re-run this check.** Extract every `` `test_…` `` and `::test_…`
> token from this file, subtract the three tables above, and subtract every
> token that is a module-name fragment (anything matching `([A-Za-z0-9_]+)\.py`
> anywhere in the file — `test_wake_reads.py:113` is a *file*, not a test). The
> remainder must be empty. **Verified empty at revision 2.**

---

## Verification Strategy (critical_path)

Four layers, each with a named owner and a stated limit.

| Layer | What it proves | Where it attaches | Limit |
|---|---|---|---|
| **Pure-unit** | `read_decision`, `delete_project`'s outcome table, `_registered_roots`, `bind_cwd_to_repo`'s branch table | the function's own seam, no store, no browser | proves the decision, not the wiring |
| **Store integration** | the migration, the seven verbs, the cascade ordering, the FK graph, read ordering | a real SQLite file through `Store`'s one writer thread | proves the data, not the surface |
| **Route integration** | every path resolves to a registered tool with a real schema property per declared field; no body field shadows a path parameter | `tests/web/conftest.py::Client` against the real handler | proves the wire, not the render |
| **Live E2E** | six pages × two viewports from a served `controld`: no console error, content present, no sideways scroll | headless chromium via `tools/render_check.py` | proves this host's headless chromium, not a phone |

Plus three **static gates that are not tests of behaviour at all**, listed
separately because confusing them with behaviour tests is how a green suite hides
a broken page: the byte-freeze equality (P9), the node-id freeze (P10), and the
HTML-sink / no-sort / no-build scans (P7, P8).

**TDD.** Each store and parser task is written RED first. E1's
`test_two_projects_may_share_a_name` **must be shown red against today's code**
before T1.4's fix lands — a test that has never failed has not been proved to
bite.

**Mutation discipline** (`CLAUDE.md`): any planted violation is an inert fixture
under `tests/boundaries/fixtures/` that nothing imports, read as text or parsed
as an AST. Never live source the suite executes. `__pycache__` is cleared before
any mutation run, because CPython decides freshness from
`(source mtime in whole seconds, source size)` and a size-preserving mutation
inside the same second re-imports unmutated bytecode and records a **false
survivor**.

---

## Live Verification Strategy

- **Harness command:**
  `.venv/bin/python -m pytest -m live tests/web/test_render_live.py -q`
- **Topology:** one `controld` process, loopback only, ephemeral port,
  `--data-dir` under the session scratchpad. Headless chromium via the
  already-installed Playwright. **No tmux session is created, attached, or torn
  down by this lane**; a future revision that needs one uses
  `tmux -L shepherd-render …` with `-L` on every invocation and never
  `kill-server` without it.
- **Isolation:** a fresh database per run, migrated from empty through 004 — so
  it holds exactly the seeded `unassigned` project and nothing else (E21). The
  user's `shepherd` socket and its `m3` / `master` sessions are never named and
  never touched.
- **Flake policy:** the check waits 700ms after navigation and 350ms after each
  nav click, as the tool already does. A failure is a failure — **no retries**. A
  flaky render check is a render check that has stopped being evidence.
- **Teardown:** the `controld` process is terminated by pid from the fixture that
  started it. Never `pkill`, never a signal to `0`, `1` or `-1` —
  `tests/conftest.py`'s net refuses those, and a guard against a reboot must not
  be able to cause one.

---

## Functionality Flow Mapping

```
Flow: declare a project and start work in it
1. open Projects            → test: test_every_page_renders_at_both_widths
2. + New project            → test: test_create_project_through_http
3. add a repo path          → test: test_add_repo_widens_the_allowlist
4. spawn into that repo     → test: test_a_registered_repo_admits_a_spawn
5. the session appears      → test: test_the_new_session_lands_in_that_project
Error paths:
- two projects named "api"  → test: test_two_projects_may_share_a_name
- a path that will not canonicalize → test: test_add_repo_refuses_a_path_that_does_not_canonicalize
- a spawn outside every repo → test: test_a_directory_outside_every_registered_repo_is_refused[*]
- a project with no repo     → test: test_a_project_with_no_repo_refuses_everything
- a body claiming another id → test: test_a_body_cannot_move_the_project_the_url_names
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
3. the pty is still there    → test: test_the_terminal_degrades_to_a_screen_view_when_the_vendor_file_is_absent (existing, D67)
4. send the keystroke        → existing answer_permission tests, unchanged
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
| Migration 004 corrupts a real database | low | **high** | Deterministic — `test_migration_004_leaves_foreign_key_check_empty` over a database with real rows, plus T1.1's human look at `PRAGMA table_info` |
| `delete_project` orphans session rows out of the INNER JOIN | med | **high** | Deterministic — P2, after every cell of P1's matrix |
| The allowlist silently narrows | med | **high** | Deterministic — P5 |
| The allowlist silently **widens** (a §13 admission bypass) | low | **high** | Deterministic — the five parametrised escape cases, node ids kept |
| A byte-freeze assertion goes red and is "repaired" by editing `rebase` | med | **high** | Deterministic — P9, plus every manifest task naming `rebase` as untouchable |
| A frozen test is deleted without a retirement entry, or with one the gate rejects | **high** | med | Deterministic — P10, seventeen retirements pre-identified per file, and both mechanical checks written into Durable Decisions |
| An `innerHTML` is ported from the prototype | **high** | med | Deterministic — P8, and the eight rewrites assigned by **enclosing function** across T6.1 (2), T6.3 (4), T7.2 (1), T9.1 (1) — the table in Codebase Reality Check #7 |
| The client-side sort is ported | med | med | Deterministic — P7 |
| Every page renders on top of every other (U18) | med | **high** | Deterministic (`test_app_css_carries_the_hidden_reset`, **owned by `tests/web/test_shell.py`**) and Live (P11) |
| A module ships with a syntax error and the page still "looks fine" | med | **high** | Live — P11; a parse error is a console error. Plus `tools/js_syntax_check.py` |
| A hard-coded count literal is left stale (`9`, `10`, the GET set) | **high** | low | Deterministic — P12; all three are in T4.2's Allowed Scope so none is discovered at run time |
| A body field shadows the `project_id` path parameter | med | **high** | Deterministic — P13, in Phase 4 rather than Phase 9 |
| `list_projects` becomes an N+1 over `list_repos` | med | med | Deterministic — T3.2's bounded-statement assertion over `repo_counts` |
| The seeded `unassigned` row silently breaks "empty" assertions | **high** | low | Deterministic — E21, and the two sites named in T1.5 |
| `list_workspaces()[0]` returns the seeded `Unassigned` instead of the fixture's project | **high** | med | Deterministic (and **the failure itself is deterministic**, so it cannot hide) — E22, and `grep -rn "list_workspaces()\[0\]" tests/` empty at T1.5's exit |
| U17's parser breaks on an engine update | **high** | med | Deterministic — E16: the property tested is *degrades, never guesses*, which is what survives the update |
| `esprima` becomes an undeclared suite dependency | med | med | Deterministic — `grep -rn "esprima" tests/` empty, in T0.1's exit |
| A `tmux kill-server` or a signal to pid 1 escapes a test | low | **high** | Deterministic — `tests/conftest.py`'s net and `tests/test_signal_guard.py`; and no task here creates a tmux session |
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
**Consequences:** enables D61's three-way choice, which the schema cannot express
at all. Prevents a future accidental `DELETE FROM workspace` from destroying
session rows silently. Costs: the ordering is a property of code, so P1 and P2
exist to hold it.
**Reversibility:** reversible (a later migration could add the clause).

### ADR-P2: `Unassigned` is the literal id `"unassigned"`, seeded by 004

**Context:** `session.workspace_id` is `NOT NULL`, so the sentinel must exist
before any row can be orphaned.
**Decision:** a reserved id, seeded in the migration with `owner_id` omitted so
the schema default applies, defined once at
`store.models.UNASSIGNED_PROJECT_ID`.
**Rejected:** a ULID; lazy creation at first use; hard-coding `'local'`.
**Consequences:** reads as itself in a log; `workspace.id` has no format
constraint. **A fresh install now holds one project rather than zero** — three
"empty" assertions become assertions about it (N1/E21).
**Reversibility:** irreversible in practice once rows point at it.

### ADR-P3: `chat.js` keeps its filename

**Context:** the design named it `shepherd.js`. Simulating the freeze gate found
the rename unrepairable (Codebase Reality Check #3).
**Decision:** the module keeps the filename `chat.js`; the page is called
Shepherd.
**Rejected:** rewriting `rebase.regenerated_paths`, spent exactly once by T24 and
whose `regenerated_by` is asserted.
**Consequences:** a module filename stops matching its page's name — the cheaper
of two bad options.
**Reversibility:** only by a future, deliberate, second re-base.

### ADR-P4: `last_activity_at` is derived, not written

See **RD-3**. Recorded here because the next reader will find a column in the
schema that nothing writes and needs to know that is deliberate.

### ADR-P5: the session view is relocated, not deleted (D67)

**Context:** U9 makes the Flock three panes whose third is *"shaped like the
Shepherd conversation"*. Revision 1 read that as replacing the session page.
**Decision:** the view **relocates** into the third pane. `session.js`,
`terminal.js` and `vendor/xterm.js` are retained and reachable. Recorded as spec
row **D67**, written in the task that performs the relocation.
**Rejected:** deleting the session page and the vendored emulator.
**Consequences:** keeps the live pty view, which nobody asked to lose; keeps 16
frozen node ids as body rewrites instead of retirements; keeps `vendor/xterm.js`
in the package, which `test_the_vendor_file_ships_in_a_built_wheel` already
depends on. Costs: `session.js` is edited, so it is the seventh
`post_milestone` entry.
**Reversibility:** reversible — a later decision could still delete the pane.

### ADR-P6: `escape.js` is kept, byte-unchanged

**Context:** the design's file-layout table says *"`escape.js` — dead, nothing
imports it — deleted"*. Revision 1 and 2 followed it. Revision 2 also discovered
that the file is named, with a reason, in `UNREACHABLE_BY_DESIGN`
(`tests/web/test_session_wiring.py:55-63`), and that the reason quotes
`test_escape_html_exists_and_is_used_where_required` — the very test the
deletion would retire.
**Decision:** keep `escape.js`, byte-unchanged. It stays in
`EXPECTED_MODULES`, its exemption stays in `UNREACHABLE_BY_DESIGN`, and the
test stays live. Owner instruction, 2026-09-21, revision 3.
**Rejected:** deleting it per the design table.
**Consequences:** retirements drop by one; `post_milestone` entries drop
7 → 6; T5.3 loses its `UNREACHABLE_BY_DESIGN` edit and now retires nothing at
all. The cost is a 21-line module that nothing imports — which is what
`UNREACHABLE_BY_DESIGN` exists to make legible, and which
`test_escape_html_exists_and_is_used_where_required` keeps correct for the first
HTML sink that ever needs it.
**Reversibility:** trivially reversible, and cheaper later: once the redesign
has settled, deleting it costs the same three edits it costs today, and by then
nobody is also changing eight other files in the same tree.

---

## Blockers Ledger

**One file per task. Never one shared ledger.**

`docs/plans/projects-ui-blockers/<task-id>.md` — e.g. `t1-1.md`, `t6-3.md`.

- A builder writes **only** its own file. Nobody opens another task's file.
- Format, as M1–M4:
  `T<id> · symptom · what was tried · what it blocks · owner: …`
- **Ids are never reused** — which is also why Phase 2's number is retired rather
  than re-flowed, and why T1.7–T1.9 record that they were T2.1–T2.3.
- An entry is never deleted; a retired one says so in place.
- `docs/plans/2026-09-21-projects-and-ui-BLOCKERS.md` is the assembled, readable
  ledger. **Only the router writes it, and only when no builder is live.**

**Why the rule exists, stated so it survives a compression:** M3 gave four
concurrent builders one file and told them to append. One rewrote it whole
instead, and **Task 2's and Task 8's entries were destroyed**. They were
reconstructed from hand-back reports, but a reconstruction is not the original.
*"Append to this file" is an instruction, not a concurrency protocol.*

**Entries this plan already predicts will be needed:**

- `t8-1.md` if `PaneState.dialog_text` does not carry the numbered option lines
  (A8). Stop and report; do not widen the capture path on the way past.
- `t1-5.md` for any fixture that cannot be swept mechanically.
- `t1-9.md` for any admission test whose property genuinely changes rather than
  whose wording does.
- `t6-3.md` if `terminal.js`'s bytes must change after all (A11) — the
  `post_milestone` count moves from seven to eight and the plan is wrong by one.

---

## Acceptance Clauses

Twenty-eight clauses. **Every deciding command names a file this plan builds or
a file that exists today**, and every test it names appears in the
**Test Ownership Index** — the failure M4's verification returned was a clause
whose command named a file nobody built.

| # | Clause | Deciding command |
|---|---|---|
| AC-1 | Migration 004 applies clean over real 001–003 rows with `foreign_key_check` empty | `.venv/bin/python -m pytest tests/store/test_migration_004.py -q` |
| AC-2 | 001–003's sha256 unchanged; a second `migrate()` is a no-op | `.venv/bin/python -m pytest tests/store/test_migration_004.py::test_the_recorded_checksums_of_001_to_003_are_unchanged tests/store/test_migration_004.py::test_migration_004_is_idempotent_across_two_runs -q` |
| AC-3 | `/work/api` and `/personal/api` are two projects | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_two_projects_may_share_a_name -q` |
| AC-4 | `delete_project` is total over its matrix and never orphans a session row | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_delete_is_total_over_its_matrix tests/store/test_verbs.py::test_no_session_ever_points_at_a_deleted_project -q` |
| AC-5 | `Unassigned` refuses rename, delete and `add_repo` | `.venv/bin/python -m pytest tests/store/test_verbs.py -k unassigned -q` |
| AC-6 | A fresh install holds exactly the seeded `unassigned` project (**N1**) | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_a_fresh_install_holds_exactly_the_unassigned_project -q` |
| AC-7 | No test selects a project by position, and the ordered list's first element is pinned (**N2**) | `.venv/bin/python -m pytest tests/store/test_verbs.py::test_unassigned_leads_the_ordered_project_list -q && ! grep -rn "list_workspaces()\[0\]" tests/` |
| AC-8 | `bind_cwd_to_repo` never raises, over the cwd matrix | `.venv/bin/python -m pytest tests/signals/test_binding.py::test_bind_cwd_to_repo_never_raises_over_the_cwd_matrix -q` |
| AC-9 | A repo in two projects, and a repo in none, both bind to `Unassigned` | `.venv/bin/python -m pytest tests/signals/test_binding.py -k unassigned -q` |
| AC-10 | `discover_repos` is gone and nothing references it | `! grep -rn "discover_repos" src/ tests/` |
| AC-11 | The allowlist never silently narrows | `.venv/bin/python -m pytest tests/orchestration/test_admission.py::test_every_registered_path_is_either_admitted_or_named_in_the_refusal -q` |
| AC-12 | The five escape shapes still refuse, node ids intact | `.venv/bin/python -m pytest "tests/orchestration/test_admission.py::test_a_directory_outside_every_registered_repo_is_refused" -q` |
| AC-13 | Seven project tools register and freeze, and all seven schemas spell `project_id` | `.venv/bin/python -m pytest tests/toolsurface/test_tools_projects.py -q` |
| AC-14 | Every new tool module is held to the 450-line cap | `.venv/bin/python -m pytest tests/toolsurface/test_tools_m3.py::test_the_three_modules_are_each_under_the_cap -q` |
| AC-15 | `list_projects` over N projects issues a bounded number of statements (**M4**) | `.venv/bin/python -m pytest tests/toolsurface/test_tools_m1.py::test_the_project_list_issues_a_bounded_number_of_statements -q` |
| AC-16 | Every POST body field is a property of its tool's schema, arrival count 14, `len(BODY_ARGS) == 15` | `.venv/bin/python -m pytest tests/web/test_routes_m3.py -q` |
| AC-17 | No body field shadows a path parameter, for `project_id` as well as `session_id` (**M1**) | `.venv/bin/python -m pytest tests/web/test_routes_m3.py::test_no_body_field_shadows_a_path_parameter tests/web/test_routes_projects.py -q` |
| AC-18 | The GET closed-set literal names all 14 paths by hand | `.venv/bin/python -m pytest tests/web/test_routes.py::test_every_api_route_names_a_registered_tool -q` |
| AC-19 | The pre-M4 route mappings are unchanged (additive only) | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py -q` |
| AC-20 | `web/server.py` is byte-identical | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_additive.py::test_web_server_is_byte_unchanged -q` |
| AC-21 | The byte-freeze equality and disjointness hold, with exactly **six** `post_milestone` entries, and `escape.js` byte-unchanged | `.venv/bin/python -m pytest tests/boundaries/test_consumer_surface_frozen.py -q && .venv/bin/python -c "import json,sys; n=len(json.load(open('tests/boundaries/consumer_manifest.json'))['post_milestone']['edits']); sys.exit(0 if n==6 else f'post_milestone has {n} entries, expected 6')" && test -z "$(git diff --name-only src/shepherd/web/static/escape.js)"` |
| AC-22 | `chat.js` still exists at its own path | `test -f src/shepherd/web/static/chat.js` |
| AC-23 | D67's retained modules still ship and are still byte-clean where promised | `test -f src/shepherd/web/static/session.js && test -f src/shepherd/web/static/terminal.js && test -f src/shepherd/web/static/vendor/xterm.js && test -z "$(git diff --name-only src/shepherd/web/static/terminal.js src/shepherd/web/static/sse.js)"` |
| AC-24 | No frozen test vanished without a retirement entry the gate accepts | `.venv/bin/python -m pytest tests/boundaries/test_collected_node_ids.py -q` |
| AC-25 | Zero HTML sinks; the shipped module list matches the directory | `.venv/bin/python -m pytest tests/web/test_frontend_escaping.py -q` |
| AC-26 | The page never re-derives the order; its labels are `PALETTE`'s; the stop-summary strip renders | `.venv/bin/python -m pytest tests/web/test_palette.py tests/web/test_shell.py -q` |
| AC-27 | No build step, no remote asset, no polling | `.venv/bin/python -m pytest tests/web/test_frontend_no_build_step.py -q` |
| AC-28 | Whole tree: suite green, `mypy --strict` clean, 105 boundary rules green, probes byte-unchanged, and six pages × two viewports render from a **served** `controld` | `.venv/bin/python -m pytest -q && .venv/bin/mypy --strict src/ && .venv/bin/python -m pytest tests/boundaries -q && test -z "$(git status --porcelain docs/probes/)" && .venv/bin/python -m pytest -m live tests/web/test_render_live.py -q` |

---

## What each phase does NOT prove — collected

| Phase | Not proved |
|---|---|
| 0 | That any page is correct. Only that the checker can reach a served page and fails on a page it should fail on. |
| 1 | That any of it is reachable from a **tool** or from the **project routes**; the hook lane's other three call sites under load. (`/api/projects` *is* exercised here, by T1.10 — that is F2's repair.) |
| ~~2~~ | *retired* |
| 3 | That any route reaches these tools; that a person can drive them. |
| 4 | That any page calls these routes. |
| 5 | That any page has content. It proves the shell, the reset, the routing, the strip, and that the rail's removal was recorded. |
| 6 | A pixel. `test_palette.py`'s own docstring says so. |
| 7 | That the unbuilt Settings sections do anything — only that each says why. |
| 8 | That the parser survives an engine update. It cannot; it proves degradation instead. |
| 9 | W3's work-source configuration. |
| 10 | Anything about a real phone, a tunnel, or a slow network. Six pages × two viewports, headless, on this host. |

---

## Differences From Agreement

Six, all stated rather than absorbed:

1. **`last_activity_at` is derived, not written** (RD-3). The design says *"This
   design fills it"*; this plan projects `MAX(session.last_event_at)` at read
   time and leaves the column unwritten. The design's requirement — that the
   Projects page can sort on it — is met. Its wording is not.
2. **The `post_milestone` declaration is per path, not "one for the whole
   redesign"** (`docs/design/ui-decisions.md` §"And the freeze"). The reader's own
   `assert len(seen) == len(set(seen))` settles it. **Six** entries:
   `rail.js` (rewritten), `fleet.js`, `flock.js`, `session.js`, `settings.js`,
   `projects.js`.
3. **The prototype contains eight `innerHTML` assignments**, contradicting
   `docs/design/ui-decisions.md`'s *"Everything in the prototype is
   `textContent`"*. Rewriting all eight is scoped by **enclosing function**
   across T6.1 (2), T6.3 (4), T7.2 (1) and T9.1 (1) — see the table in Codebase
   Reality Check #7.
4. **The prototype omits the stop-summary strip; the plan keeps it.** The
   prototype is a mock, and principle 5 plus §12 put the unknown rate on the
   fleet page. Where the mock and the shipped page disagree, the shipped page
   wins.
5. **`escape.js` is kept; the design's file-layout table said delete it.** This
   reverses a row of the approved design, **on the owner's explicit instruction
   at revision 3** — recorded here rather than absorbed, because a design row
   reversed quietly is the thing §0 forbids. The reasoning: `escape.js` is not
   forgotten dead code, it is *documented* dead code —
   `UNREACHABLE_BY_DESIGN` in `tests/web/test_session_wiring.py:55-63` names it
   with a reason, and that reason quotes
   `test_escape_html_exists_and_is_used_where_required`. Deleting the file
   therefore either leaves a stale exemption citing a test that no longer
   collects — the exact shape `test_a_stale_exemption_is_caught` exists to
   catch — or forces a third edit to keep the record honest. One retirement,
   one `post_milestone` entry and one constant edit, all bought for tidiness, in
   a change already retiring seventeen ids. Deleting a deliberately-kept helper is
   a small capability decision wearing a tidy-up's clothes. See **ADR-P6**.

6. **The typefaces are reversed: a system font stack, not Instrument Sans and
   JetBrains Mono.** `docs/design/ui-decisions.md:36-37` specifies both by name.
   T5.2 mandates a system stack instead, and the design's own Questions-Resolved
   table agrees (*"Webfont? Dropped."*) — but this plan had it recorded only in
   Durable Decisions, which is the **same quiet-reversal shape `escape.js` was
   corrected for** (F11). Stated here: the reasons are that the server binds
   loopback only and must work offline, that a remote font is a third-party
   request from a local tool, and that `web/server.py` is byte-pinned so
   `_CONTENT_TYPES` cannot host a font file locally. The design's type choices
   survive as the fallback list. `test_no_remote_script_sources` enforces it
   mechanically, so the reversal is also checkable.

Plus two corrections carried from outside the plan: **`chat.js` keeps its
filename** (ADR-P3), and **the session view relocates rather than being deleted**
(ADR-P5 / D67).

---

## Self-review

Cross-phase contract drift: checked at revision 2. Every `Consumes` name
verbatim-matches a `Produces` in an earlier phase or task —
`UNASSIGNED_PROJECT_ID`, `OnRunning`, `DeleteOutcome`, the five `writes.*`
signatures, the seven `reads.*` signatures (including `repo_counts` and the now-
ordered `list_workspaces`), the ten `Store.*` delegations, `PROJECT_TOOL_NAMES`,
`register_project_tools`, `project_workspace`, the seven route templates,
`app.js::showPage`, the six `#page-*` roots, the three `#dlg-*` ids, the three
strip ids, `flock.js::BUCKET_LABEL`, `flock.js::renderFlock`,
`shepherd.runner.pane.read_decision(state: PaneState) -> DecisionPrompt | None`,
`shepherd.runner.pane.DecisionPrompt`,
`tools/render_check.py::check(origin, shots)`, `tools/render_check.py::PAGES`,
`tools/render_check.py::NAV_SELECTOR`, `tools/render_check.py::DRAWER_SELECTOR`.
No dangling reference found.

Named-test ownership: checked. Every test named in E1–E22, P1–P13, the four flow
maps and AC-1–AC-28 appears in the Test Ownership Index with a module and a
building task. That was B7's failure and it is now a table lookup.

**Self-review: no cross-phase reference drift; no test named without an owner.**
