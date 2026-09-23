# QA research — lane `spec_docs` — Projects backend + dark-only UI redesign

Workflow `wf-20260921T212808Z-9172ed6b`. Lane: **spec_docs** (one of four parallel single-source scans).

**Read-only, with one authorised exception.** No file was created, edited, moved or deleted, no package installed, no service started, no tmux invoked. `Bash` was used only for `ls` / `wc` / `grep` / `sed`. The single write is **this file**, made at the coordinator's instruction into the workflow's `mutation_allowlist` (`.cc10x/`) after the inline hand-back spilled to a path on this workflow's read denylist.

**Scope discipline.** I read only the eight documents named in my dispatch, plus `docs/plans/projects-ui-blockers/README.md` (a sibling rule file inside the named glob). I did **not** open `src/**`, `tests/**`, `.cc10x/**`, `docs/probes/**`, or `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` — the plan calls the recon *"the measurement… outranks every other document"* (`plan:186`) and it is not in my authority list, so every recon-derived fact below is reported as **the plan's claim about a measurement**, never as measured truth. No denied material reached me over any channel.

**Sections 1 and 2 are condensed to decision ids plus one line each, per the coordinator's trim priority. Sections 3, 4 and 5 are full.**

---

## 1. User-side contract — condensed

Shell: dark only, collapsible left pane, **six** pages (`ui-decisions.md:25-34`). Palette `#08090D`→`#1C212D`, violet `#7A5CF0`, blue `#4C7DF0` (`:36-37`); the eight bucket hexes untouched (`:38-39`). Six roots `#page-shepherd|flock|queues|projects|kanban|settings`, three dialogs `#dlg-legend|project|delete` (`plan:1456-1462`, `:1500-1503`). `[hidden] { display: none !important }` is mandatory or every page renders atop every other (**U18**, `ui-decisions.md:199-212`).

**Shepherd** — master conversation left, live SSE sidebar right; approval cards inline at the blocked turn *and* in the sidebar (`orchestrator-platform.md:1897-1899`). **U6** (`:64-67`): audit tail is **not** here, it moves to Settings → Data. **D65** (`:182`, `:1901-1904`): no autonomy toggle on this page at all. D31 wake summary opens the first turn after an absence (`:1906-1918`).

**Flock** — **U9** (`:75-77`): three panes projects → cards → session; phone = drill-down with a back chevron. **U10** (`:78-81`): legend of all eight buckets, tooltip per key carrying an `acts:` line verbatim from `PALETTE.who_acts`. **U1** (`:150-159`): tap any legend key or the ⓘ opens one sheet explaining all eight; hover/focus keeps a single-key popover on a pointer device. **U7** (`:68-71`): a card carries exactly four things — glyph+colour, title, the ask verbatim (only when stopped/waiting), relative time; progress is a 2px hairline; model/ownership/session id/confidence/workspace path are deliberately out. **U8** (`:72-74`): relative time spelled out, scaling to years, `never seen` when there is no timestamp. **U16** (`:98-117`): ~16% wash of the bucket colour over the card ground, legend is glyph plus coloured text — and this **overrides the prototype's pixels**. **B3** (`plan:108`, `:592`): the stop-summary strip `#stop-summary` / `#unknown-rate` / `#low-confidence` sits in the Flock header. **U11** (`:82-87`): a `needs you` session shows the engine's own numbered prompt verbatim, never flattened to approve/reject; an **idle** session gets no card. **D67** (`:186`, `:2043-2108`): the third pane is the relocated session view — xterm terminal, D21's `next_actions[]` in the header with ordinal and source, D29 click-to-edit rename with a `local only` marker, `⌘K` queues via mailbox, `[tmux attach]`. **D66** (`:184`, `:1849-1874`): the Needs-You rail is off the shell; its *content* rules survive (the actual ask per row, empty = 4px green line ≠ not-read-yet, three row kinds). The page **never sorts** (`design:243-249`).

**Projects** — **U14** (`:118-121`): two panes, `Unassigned` pinned last and visually distinct, repo paths in full, edited in the Edit dialog, sessions are links into the Flock. `Unassigned`'s lifecycle controls are **absent, not disabled** (`plan:1880-1881`). `#dlg-delete` renders the three-way choice **from the server's refusal, not a guess** (`plan:1874-1877`). Verbatim allowlist warning: *"A path here widens where Shepherd may start sessions"* (`plan:1877-1878`). **D63** (`:179`): work sources belong here — shipped as `not built` (`plan:1862-1864`).

**Settings** — **U13** (`:93-97`): ten sections under *Yours* (Account, Notifications, API keys) and *This instance* (Autonomy, Shepherd, Discovery, Limits, Users & access, Data, System); every unbuilt section carries a `not built` chip **and says why in the panel**; `shepherd uninstall` dropped from the UI entirely. **U12** (`:88-92`): autonomy levels unnumbered — *"Ask me before anything leaves this machine"* / *"Approve automatically"*, the second stating auto-approved is never unlogged. Real today: Autonomy, Discovery's hook status, Data's audit tail (four fields: `at`, `tool`, `decision`, `approved_by`), System's facts (`ui-decisions.md:257-259`).

---

## 2. System-side contract — condensed

**Migration 004** (`design:91-106`) — `workspace` gains `description TEXT`, loses `root_path`; `project_repo(workspace_id, repo_id, added_at)` PK on the pair, backfilled from `repo.workspace_id`; `repo` drops `workspace_id`; `ix_repo_common_dir` added because D48 makes `git_common_dir` the binding key; the `unassigned` row seeded. Append-only, one transaction, `00N_` lexical order, **no trigger and no semicolon inside a string literal** (`plan:144-146`). 001–003 sha256-pinned; `EXPECTED_SCHEMA_VERSION` 3→4 (`plan:574`). **`session` is never rebuilt and no `ON DELETE CASCADE` is added** (`design:108-128`, ADR-P1 `plan:2217-2229`). Orphaned `repo` rows are **kept** to preserve the path identity under `ux_repo_path` (`design:160-164`).

**`Unassigned`** — reserved literal id `"unassigned"`, defined once at `store.models.UNASSIGNED_PROJECT_ID`, **seeded by the migration** because `session.workspace_id` is `NOT NULL`; the `INSERT` omits `owner_id` so the schema default applies (A10 `plan:400`); refuses rename, delete and `add_repo` (`design:134-141`). Stated consequences: a fresh install holds one project not zero, and BINARY collation puts `"Unassigned"` first under `ORDER BY name`, so every `list_workspaces()[0]` returns the reserved project (`plan:289-322`).

**Delete** (`plan:407-431`) — `on_running ∈ {"refuse","kill_sessions","orphan"}`, default `"refuse"`. **`kill_sessions`, not `kill`**, because a bare `kill` is a tmux command-name prefix the boundary suite refuses (`plan:411-413`). Cascade ordered `mailbox_message → session → project_repo → workspace` in one writer transaction. Unknown `on_running` is **refused by the handler as a renderable `DeleteOutcome`** — corrected in place 2026-09-22 from an earlier claim that it was refused at the schema (`plan:424`). Invariant: `Store.fleet()` is an **INNER JOIN workspace**, so a session pointing at a deleted workspace vanishes without trace — which is why `orphan` is a correctness requirement (`plan:426-430`).

**Binding** (`plan:432-441`) — `bind_cwd_to_repo` **never raises**; four branches: not-a-repo → `unassigned` + anomaly; bare repo → `unassigned` + anomaly; new repo → creates the **repo only**, unattached; known common dir → resolve through `project_repo`: exactly one project → that one, more than one → `unassigned` (D60), none → `unassigned` (D59).

**The verbs** (`design:168-179`) — `create_project` / `add_repo` / `delete_project` = `local_destructive`; `rename_project` / `remove_repo` = `local_write`; `list_repos` / `get_project` = `local_read`; audiences `{MASTER, HUMAN}`; a `HUMAN`-audience call needs no approval card. Consumer key is **`project_id`** everywhere (`plan:583`). Routes (`plan:1308-1318`): GET `…/{project_id}`, `…/{project_id}/repos`; POST `/api/projects`, `…/rename`, `…/delete`, `…/repos/add`, `…/repos/remove`; `BODY_ARGS` never declares `project_id`. `add_repo` canonicalizes **and probes git** at the tool layer because `store/` does no filesystem I/O; a path that will not probe is refused, never stored with a placeholder (`plan:1223-1238`).

**Event obligations** — §12 fixes one SSE endpoint and one envelope `{seq, at, type, session_id, project_id, data}`, monotonic `seq`, `Last-Event-ID` gap replay, **no polling anywhere in the UI** (`orchestrator-platform.md:2122-2140`). **No `project.*` kind is listed in §12**, and the design says *"The Projects page adds no counters"* (`design:310-313`). Project events exist only post-hoc, from remediation: six mutations publish `project.created|renamed|described|deleted|repo_added|repo_removed`, each gated on the record's own positive key, `project_id` promoted into the envelope by `web/sse.py::envelope`; **a refusal announces nothing** (`qa-remfix-4-lane-b.md:128-196`). `set_autonomy_level` remains a seventh silent mutation, explicitly not fixed and not hidden (`:198-203`).

**Layer law** (`logical-architecture.md`) — L5 (`master/`, `web/`, `cli/`) reaches the system only through L4 `toolsurface/`; nothing outside `store/` imports a DB driver; both enforced as **AST properties, not spellings** (`:10-13`, `:68-77`). `daemons/` is L6: may import anything, nothing may import it, capped at 150 lines (`:165-191`). `controld` is the only process that writes the DB; `sessiond` never migrates the schema (`:132`, `:150-157`).

---

## 3. Acceptance-criteria inventory — all 28, verbatim id + claim + falsifiability

Source: `docs/plans/2026-09-21-projects-and-ui-plan.md:2340-2369`. The "Falsifiable as written?" column is my read of whether the clause, **as written**, can fail for the reason it names.

| AC | Claim (as the plan states it) | Falsifiable as written? |
|---|---|---|
| **AC-1** | Migration 004 applies clean over real 001–003 rows with `foreign_key_check` empty | **Yes** — names a module and a concrete PRAGMA outcome |
| **AC-2** | 001–003's sha256 unchanged; a second `migrate()` is a no-op | **Yes** — two named node ids |
| **AC-3** | `/work/api` and `/personal/api` are two projects | **Yes, and strongest in the set** — the plan requires this test be *shown red against today's code* before the fix lands (`plan:2095-2098`, E1 `plan:473`) |
| **AC-4** | `delete_project` is total over its matrix and never orphans a session row | **Yes** — P2's `SELECT COUNT(*) FROM session WHERE workspace_id NOT IN (SELECT id FROM workspace)` is a real zero-check (`plan:506`) |
| **AC-5** | `Unassigned` refuses rename, delete and `add_repo` | **Weak.** The command is `-k unassigned`, a substring selection. If the three tests were renamed or never written the selector matches whatever remains — including nothing. E7–E9 exist (`plan:479-481`) but the *clause* does not name them |
| **AC-6** | A fresh install holds exactly the seeded `unassigned` project (N1) | **Yes** — one named node id |
| **AC-7** | No test selects a project by position, and the ordered list's first element is pinned (N2) | **Yes** — `! grep -rn "list_workspaces()\[0\]" tests/` is a genuine absence check |
| **AC-8** | `bind_cwd_to_repo` never raises, over the cwd matrix | **Yes, conditionally** — the clause does not pin the matrix's cardinality, so a one-cell matrix would satisfy it |
| **AC-9** | A repo in two projects, and a repo in none, both bind to `Unassigned` | **Weak** — same `-k unassigned` substring-selection problem as AC-5 |
| **AC-10** | `discover_repos` is gone and nothing references it | **Yes** — a pure absence grep over `src/` and `tests/` |
| **AC-11** | The allowlist never silently narrows | **Yes** — named node id, and P5 states the mutation that reddens it (replace the refusal at `admission.py:141-143` with a `continue`) |
| **AC-12** | The five escape shapes still refuse, node ids intact | **Partly.** The clause says *"the five parametrised escape cases"* but the command names the un-parametrised node id with no id-selector, so it asserts the test runs, not that five cases remain five |
| **AC-13** | Seven project tools register and freeze, and all seven schemas spell `project_id` | **Yes** for registration; the "seven" is asserted inside the module's own tests, which the clause does not enumerate |
| **AC-14** | Every new tool module is held to the 450-line cap | **Yes** |
| **AC-15** | `list_projects` over N projects issues a bounded number of statements | **Yes** — F9 corrected this from a `-k bounded` selector to a named node id (`plan:84`). "Bounded" is not defined in the clause, so what counts as a regression lives in the test, not here |
| **AC-16** | Every POST body field is a property of its tool's schema; arrival count 14; `len(BODY_ARGS) == 15` | **Yes** — hard literals |
| **AC-17** | No body field shadows a path parameter, for `project_id` as well as `session_id` | **Yes**, plus a positive test that a body claiming a different id cannot move the target |
| **AC-18** | The GET closed-set literal names all **14** paths by hand | **Yes** — but see C6: T4.2 widens it to **13**, with the fourteenth arriving in Phase 8 |
| **AC-19** | The pre-M4 route mappings are unchanged (additive only) | **Weakened by design.** A4 records the underlying gate is a **subset** check (`plan:394`), so it cannot catch an addition that was never meant to exist |
| **AC-20** | `web/server.py` is byte-identical | **Yes** |
| **AC-21** | Byte-freeze equality and disjointness hold, with exactly **six** `post_milestone` entries, and `escape.js` byte-unchanged | **Yes — and it is the one AC whose falsifiability was itself repaired.** F8 found it `print`ed the count and exited 0 for any value: the clause that would have caught F4's off-by-one (`plan:83`). Now `sys.exit(0 if n==6 else …)` |
| **AC-22** | `chat.js` still exists at its own path | **Yes** (trivially) |
| **AC-23** | D67's retained modules still ship and are byte-clean where promised (`terminal.js`, `sse.js`) | **Yes as a check — but now false of the tree.** `terminal.js` was edited by D6's fit and given a new `post_milestone` entry (`qa-remfix-4-lane-b.md:230-236`, `:247`) |
| **AC-24** | No frozen test vanished without a retirement entry the gate accepts | **Yes** |
| **AC-25** | Zero HTML sinks; the shipped module list matches the directory | **Yes** |
| **AC-26** | The page never re-derives the order; its labels are `PALETTE`'s; the stop-summary strip renders | **Yes** |
| **AC-27** | No build step, no remote asset, no polling | **Yes** |
| **AC-28** | Whole tree: suite green, `mypy --strict` clean, 105 boundary rules green, probes byte-unchanged, and six pages × **three** viewports — every width in `render_check.VIEWPORTS` — from a **served** `controld` | **Falsifiable but demonstrably insufficient, by the plan's own account.** Revision 6 exists *because* AC-28 "reported green over" an unusable 140px band (`plan:35`). The repair names `render_check.VIEWPORTS` as the single definition site — **and then restates both the count ("three") and all three widths in the same sentence**, reproducing the second-definition-site defect it was written to remove |

**Two structural notes on the AC set.**

1. Every clause is a **command**, and four of them (AC-5, AC-9, AC-12, and AC-15 before F9) select tests by **substring** rather than by node id — the same failure the section's own preamble says M4's verification returned: *"a clause whose command named a file nobody built"* (`plan:2335-2338`).
2. **Nothing in AC-1…AC-28 asserts any event or SSE obligation.** That is consistent with *"The Projects page adds no counters"* (`design:310-313`) and it is precisely the hole D7 later occupied — six mutations, six 200s, zero frames to a second client (`qa-remfix-4-lane-b.md:128-137`).

---

## 4. Stated non-goals and "does not prove" claims

**This section decides what round 5 must not spend effort on. A QA run that tests these wastes effort; a QA run that assumes they are proven is wrong.**

### Declared out of scope (`plan:159-164`, `design:74-79`)

- M5 queues and work-item providers **beyond a disabled placeholder** (W3)
- Bring-your-own-harness (`harness-contract.md`, six open questions)
- Credentials and multi-user auth (`credentials-and-auth.md`, four questions, **none answered**)
- Real sandboxing (spec §17 — none exists today)
- **Queues and Kanban beyond nav placeholders** — never discussed at all (`ui-decisions.md:30,33`; `backlog:107`)
- Model/engine per spawned session (**U15, deferred**, no precedence rule adopted; `spawn_session`'s `model` argument is the only lever and `engine="claude_code"` stays a literal)
- §12's **matrix view** (Page 2b, D27) — ships with M5, not here
- D34's **LLM verdict lane**
- **W2's discovery switches (1) and (2)** — only switch (3) is touched, because it *is* D59's policy

### Per-phase "does not prove" (`plan:2373-2387`)

| Phase | Not proved — verbatim |
|---|---|
| 0 | That any page is correct. Only that the checker can reach a served page and fails on a page it should fail on |
| 1 | That any of it is reachable from a **tool** or from the **project routes**; the hook lane's other three call sites under load |
| 2 | *retired* |
| 3 | That any route reaches these tools; that a person can drive them |
| 4 | That any page calls these routes |
| 5 | That any page has content. It proves the shell, the reset, the routing, the strip, and that the rail's removal was recorded |
| 6 | **A pixel.** `test_palette.py`'s own docstring says so |
| 7 | That the unbuilt Settings sections do anything — only that each says **why** |
| 8 | That the parser survives an engine update. **It cannot**; it proves degradation instead |
| 9 | W3's work-source configuration |
| 10 | Anything about a real phone, a tunnel, or a slow network. Six pages × three viewports, headless, on this host |

### Verification-layer limits (`plan:2083-2093`)

Pure-unit proves the decision, **not the wiring**. Store integration proves the data, **not the surface**. Route integration proves the wire, **not the render**. Live E2E proves **this host's headless chromium, not a phone**. Three named gates are explicitly **not tests of behaviour at all** — the byte-freeze equality (P9), the node-id freeze (P10), and the sink/no-sort/no-build scans (P7, P8): *"confusing them with behaviour tests is how a green suite hides a broken page."*

### Remediation-lane "does not prove" — these describe the **shipped tree**

**D6, the terminal fit** (`qa-remfix-4-lane-b.md:104-124`):
- G-M3-6 is **narrowed, not closed** — that xterm draws the *glyphs* identically to a real terminal is still unverified
- Three viewports driven, not the full declared sweep
- **The `ResizeObserver` re-fit is wired but driven by no test**
- `top` is sampled once per open; content arriving *above* the terminal later will not re-budget rows — **untested**
- `app.css` untouched, including `#session-terminal { overflow: hidden }` and `min-height: 12rem`
- **`terminal_resize` remains a registered `ToolDef` with no route and no caller** — a known unwired capability

**D7, project events** (`qa-remfix-4-lane-b.md:205-218`):
- Proved at the **HTTP/SSE wire, not at two live browser tabs**; the two-tab driver is **not committed**
- That `app.js::refreshAll()` really re-renders tab A on receipt is **not re-proved**
- **Ordering and coalescing under concurrency are untested**
- `remove_repo` is the one verb in the family whose record shape is not the family's

**Lane A, four frontend defects** (`qa-remfix-4-lane-a.md:269-289`):
- `closedby` verified in **chromium 153 only**
- **`#dlg-project` and `#dlg-delete` still have no light-dismiss** — recorded, not fixed
- **42 controls sit between 24 and 44px**, untouched and still AA-conformant
- **No `-m live` lane was run**, per the standing constraint
- D5 proved at the handler-count seam, **not at the `Runner` seam**

**Run 3** (`qa-remfix-3.md:194-210`):
- **Nothing above 1280 or below 390.** Three points, **not a continuum**; 761 and 900 — the band's own edges — are **reasoned from the media query, not driven**
- **No touch events**; every phone assertion is synthesized pointer events
- **`prefers-reduced-motion`, forced colors, zoom and RTL — untouched**
- `test_projects_page.py` and `test_settings_live.py` **still spell `{390,844}` and `{1280,900}` as their own literals** — *"the drift they represent is real and is the same shape that hid D1"*
- The `kill.<id>` row's survival is a measurement, **not a committed test**

**Run 2** (`qa-remfix-2.md:76-84`, `:48-74`):
- **Every `unreachableControls: 0` reading in both QA runs is unproven** — the driver over-reports (it decided reachability from `document.documentElement.scroll*` only)
- **Four POST handlers are deliberately left unguarded** against double-click — `addDraftPath`, `removeDraftPath`, `settings choose`, `chat submit` — on the stated bet that their verbs are idempotent. The stated cost: if any later stops being idempotent, it is defect 7's shape for a third time

**Integration pass** (`integration.md:193-203`):
- Not a phone's real browser, not a tunnel, not a slow network
- **Not the terminal**: no test drives an *owned* session's WebSocket from the shipped page
- **Not the Shepherd conversation against a real master**
- **`app.css` defines no `.session-*` rule, so that pane renders unstyled until somebody owns it**

**And the structural one** (`t10-1.md`): `render_check.py` **cannot** see the `.herd` grid collapse. Measured — `#page-flock`'s rectangle is **byte-identical** healthy and broken (56→900 in both), and Chromium reports the **implicit** track so both states read as three rows. *"No per-root rectangle can distinguish those, and there is no generic property of a page root that does."*

---

## 5. Contradictions and gaps — recorded, NOT reconciled

Reconciliation is the router's job. Each entry names both sides with a locatable citation.

### 5a. Cross-document contradictions

**C1 — how many viewports.**
- `plan:2088`, `:2369`, `:2387`, `:1908`, `:1929`, `:515` all say **three** (390 / 820 / 1280), and `qa-remfix-3.md:98-119` records `VIEWPORTS` going from two to three, with both tool gates reporting *"18 pages checked · 18 screenshots"*.
- `qa-remfix-4-lane-b.md:108`: *"`tools/render_check.py::VIEWPORTS` declares **six**, including the 820x1180 tablet QA run 3 added."*
- Both cannot be true of the same constant. **This one is load-bearing for round 5's coverage claim.**

**C2 — how many verbs.**
- `design:168-179`, `plan:1194`, `plan:1264` fix the surface at **seven**, and T3.1 lists *"an eighth verb"* as Out-of-Scope Drift (`plan:1243-1245`).
- `qa-remfix.md:41`: `set_project_description` *"is built, routed, registered and works"*. `qa-remfix-4-lane-b.md:149-155` lists it as one of **six** project mutations.
- So the shipped surface is **eight** tools.

**C3 — POST route count.** `plan:1315`, `:586`, AC-16 say **15 POST routes** / `len(BODY_ARGS) == 15`. `qa-remfix-4-lane-b.md:135` says run 4 *"enumerated all **sixteen** `POST_ROUTES`"*.

**C4 — were U1–U4 and U15 blockers.**
- `backlog:96-98` (W4): *"U1–U4 and U15, **which must be answered before implementing**."*
- `ui-decisions.md:127`: *"**None of them was a blocker**, and this section says so rather than leaving them looking like gates."*

**C5 — the register's ranges are stale.** `backlog:16` says the decisions are **D57–D64**; the spec ships **D57–D67**. `backlog:18` says the UI decisions are **U1–U15**; `ui-decisions.md` ships **U1–U18**.

**C6 — §12's own headline was never updated.** `orchestrator-platform.md:1841`: *"Three surfaces, one settings page, and **one rail that is always present**."* D66 at `:184` and the rewritten subsection at `:1849-1863` say the rail is **off the shell**.

**C7 — the GET literal's size.** AC-18 (`plan:2359`): *"names all **14** paths by hand"*. T4.2 (`plan:1341`): widened *"by hand to **13** entries"*, with T4.1 (`plan:1310`) saying the fourteenth arrives in Phase 8. Both are reachable readings of the end state; they disagree at the point a builder reads them.

**C8 — `terminal.js`'s bytes.** AC-23 (`plan:2364`) and T6.3's exit (`plan:1678`) require it byte-unchanged; A11 (`plan:401`) and T6.3's drift note (`plan:1664-1666`) say that if it changes the count moves six → seven **and the plan is wrong by one**. `qa-remfix-4-lane-b.md:230-236`, `:247` records that it **was** edited and given one new entry.

**C9 — `last_activity_at`.** `design:193-196`: *"This design **fills it**, from the project's most recent session event."* `plan:177` (RD-3) and `:2256` (ADR-P4): **derived** at read time, column left unwritten. Flagged by the plan itself as Difference #1 (`plan:2395-2398`).

**C10 — `escape.js`.** `design:221` says delete it; ADR-P6 (`plan:2276-2296`) keeps it byte-unchanged on the owner's instruction. Flagged as Difference #5.

**C11 — typefaces.** `ui-decisions.md:36-37` names Instrument Sans and JetBrains Mono; `plan:2428-2438` and `design:250-252` mandate a system stack. Flagged as Difference #6, and F11 records it was previously a **quiet** reversal.

**C12 — the plan quotes `ui-decisions.md` claims that file has already retracted in place.** `plan:230-237` and `:2404-2408` cite it as saying *"Everything in the prototype is `textContent`"*; the file corrected that at `:227-236` (*"**Correction, 2026-09-21: … was false.** Counted: eight `innerHTML` assignments"*). Identical shape at `plan:261-267` vs `ui-decisions.md:286-297` (the one-declaration-for-the-whole-redesign claim). **The plan's two CONTRADICTS labels point at sentences no longer in force.**

**C13 — screenshot count across lanes.** `integration.md:180` and `t10-1.md`: **12 screenshots at two viewports**. `plan:1927`, `:1936`: **eighteen**. Chronology explains the lanes; it does not explain C14.

**C14 — `DeletePlan.running` and killability.** `t9-1.md` gap 2: *"`DeletePlan.running` does not say which sessions are killable, so the page cannot warn in advance."* `qa-remfix.md:42`: *"the server sends `killable: []` / `unkillable: [ids]` — **it already knows** the stop cannot reach anything."* Two documents in this lane describe the same record differently.

### 5b. Contradictions **inside a single document** (nobody else will see these)

**C15 — Phase 10 disagrees with itself.** `plan:1903`: *"a person looks at the **twelve** screenshots once"*. `plan:1927`: *"the **eighteen** screenshots"*. `plan:1936`: *"**eighteen** screenshots under the scratchpad"*. Revision 6 moved two of the three.

**C16 — AC-28 reproduces the defect revision 6 exists to fix.** `plan:37-41` states the rule: *"a restated constant is a second definition site, and the gap between two restated bounds is where a defect hides from every check that quotes them. A criterion should name the enumeration, not copy its length."* AC-28 (`plan:2369`) then reads *"six pages × **three** viewports — every width in `render_check.VIEWPORTS`"*, and P11 (`:515`) and the Phase-10 header (`:1908`) each restate both the count and all three widths. The plan also records that the node id `test_every_page_renders_at_both_widths` is *"now one width short"* and is being kept anyway (`plan:42-45`).

**C17 — finding N1's heading contradicts its own body.** `plan:273-275`: *"N1 — … and it breaks **three** tests."* `plan:276`: *"**Three** assertions go red: **two** assertions go red."* The correction was applied to the body and to neither enclosing sentence.

**C18 — finding #8's arithmetic.** `plan:264`: *"**Seven** entries are needed (M6)"*, followed by a list of **six** names, followed by `plan:266-267`: *"**Six, not seven**."*

**C19 — the Durable Decisions phase column points at a retired phase.** `plan:599`: *"**There is no Phase 2.**"* `plan:583-585`: three rows (consumer key spelling, blast classes, auth posture) are assigned to **Phase 2**. Several further rows name phases the Phase Plan assigns elsewhere (label source of truth → 5 vs Phase 6's T6.2; Flock header → 4,5 vs Phase 6; D21's actions → 5 vs Phase 6). The column was never re-flowed when Phase 2 was folded in — the repo's id rule applied to a *pointer* rather than an id.

**C20 — `ui-decisions.md`'s status line is stale against its own body.** `:3`: *"**Status: design only. No file under `src/shepherd/web/` has been changed.**"* `:100`: *"Clarified 2026-09-22, **during the port** …"*. The same file records the port it declares has not happened.

**C21 — an "Open / Nothing is gating" header above a live item.** `ui-decisions.md:146-148`: *"## Open — **Nothing is gating the implementation.**"* Four of the five items below are struck through; **U4 at `:164-168` is not** — *"stops that were never classified are not logged … The gap is the cohort whose record never arrived, currently only a count on a page."* The header reads as though all five were closed.

### 5c. Gaps — a decision stated with no observable consequence, or a consequence with no observer

- **G1 — no AC, no P-property and no flow map covers any event/SSE obligation.** §12 fixes the envelope and forbids polling; the design says the Projects page adds no counters. There is no criterion from which *"a mutation tells a second client"* could ever have failed. D7 is what that hole looked like when a browser finally ran.
- **G2 — D62's open sub-question is deliberately unanswered.** With switch (2) off, a hook event from an unregistered session must either be **dropped** (losing the stop reason for a session the scan is showing) or **accepted without registering** (holding state for a session we decided not to track). *"Neither is free and neither is needed until a switch is"* (`orchestrator-platform.md:178`, `backlog:71-75`).
- **G3 — D64 is fully specified and entirely unbuilt.** The filter declaration, the `Advanced` raw-query escape hatch, and *"saving validates and reports the match count"* (`orchestrator-platform.md:180`, `backlog:82-89`). The Projects page ships a `not built` placeholder, and **nothing distinguishes "correctly absent" from "silently missing"**.
- **G4 — U4 has no owning task.** `ui-decisions.md:164-168` asks for the absence to be logged at the point the fleet notices a stopped session with no record. It is W-level backlog work and appears in no phase.
- **G5 — U17's degradation is proved; its coverage is not.** The plan states outright it cannot prove survival across an engine update (`plan:1787-1790`), and **A8 is an `inferred` assumption** — that `PaneState.dialog_text` carries the numbered option lines — carrying a stop-and-report gate rather than a proof (`plan:398`).
- **G6 — C15's trust dialog has no stated UI obligation.** Named as a thing any prompt parser meets, where *a blind Enter answers "No, exit"* (`ui-decisions.md:196-197`, E17 `plan:489`). One test; nothing about what the **page** shows when it is recognised.
- **G7 — `DeletePlan.doomed` never reaches a consumer** (`t9-1.md` gap 1). The store computes it *"so the dialog can say what it is about to take **before** the button"*, and the tool discards it. The page derives a copy from the detail it holds: *"Two rules now say the same thing in two languages, and the page's is the one that will drift."* Asked for; not granted in that task.
- **G8 — no spec document enumerates the runtime option set of any data-driven control.** Project lists, repo lists, session cards and engine decision choices are all data-driven. Requires a running system.
- **G9 — role/tenant/flag-gated options are unenumerable here.** The docs assert the product is single-user loopback with no auth (`orchestrator-platform.md:2146`), so they assert there are none. That assertion is itself unverified from this source.
- **G10 — no stated behaviour on a store write failure mid-cascade** beyond *"inside one writer transaction"*, and **no stated timeout or retry policy for `add_repo`'s git probe**.
- **G11 — `web/server.py` is byte-pinned**, so `_CONTENT_TYPES` is `.html`/`.js`/`.css` only: **no font, image, SVG file or JSON data fixture may enter the static tree** (`design:64-66`, `plan:133-136`). A hard constraint on any fixture round 5 wants to stage.
- **G12 — the recon is unread by this lane.** `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` is named by the plan as *"the measurement … outranks every other document"* (`plan:186`) and is outside this lane's authority list.

---

## 6. Testability findings

1. **`render_check.py` is structurally blind to intra-page layout collapse** — `#page-flock`'s rectangle is byte-identical healthy and broken; Chromium reports the implicit grid track so both read as three rows (`t10-1.md`).
2. **A restated constant is this project's recurring detector failure.** A width count in four places left a 140px unreachable band every gate quoting it reported green over (`plan:35`); a third literal was found only by the full suite going red (`qa-remfix-3.md:112-120`). Residual restatements at C16.
3. **Green suites over unpopulated fixtures.** Every `tests/web` fixture seeded one project and at most two sessions, all *attached*, so `DeletePlan.killable` was empty in every test that read it; no two projects shared a name; no path ellipsised; no envelope was published at a rate. **Nine of eleven defects were invisible at n=1** (`qa-remfix.md:17-34`). Seeding helpers are now committed.
4. **Module-graph reachability certifies a fetch, not a call.** `flock.js` was *reached* while the page never drew: *"Loaded is not driven, and a walk structurally cannot see the difference"* (`integration.md:64-75`).
5. **A lexical `try`-scan cannot see whether the `catch` does anything** — a silent `catch {}` satisfies it (`qa-remfix.md:88-91`).
6. **Vacuous assertions over self-sizing boxes.** A 307,418px container passed every *"the content fits inside its box"* assertion, because the box grew to fit the content (`qa-remfix-4-lane-b.md:86-93`).
7. **The byte-freeze gate reddens on any changed byte and says nothing about the page** — mutation M5 survived with only the digest red (`integration.md:151-157`).
8. **No spec-side criterion covers project-mutation events** (G1).
9. **`terminal_resize` is a registered tool with no route and no caller** — a known unwired capability (`qa-remfix-4-lane-b.md:123-124`).
10. **The `ResizeObserver` re-fit is wired but driven by no test**; `top` is sampled once per open and is untested.
11. **`#dlg-project` and `#dlg-delete` still have no light-dismiss** — recorded, not fixed.
12. **No touch-event path has ever been driven**; every phone assertion is synthesized pointer events.
13. **`prefers-reduced-motion`, forced colors, zoom and RTL are entirely undriven.**
14. **Nothing above 1280 or below 390 is driven**; 761 and 900 are reasoned, not measured.
15. **`app.css` defines no `.session-*` rule** — the session pane renders unstyled until somebody owns it.
16. **Every `unreachableControls: 0` reading in QA runs 1 and 2 is unproven** — the driver over-reports (`qa-remfix-2.md:76-84`).
17. **Four POST handlers are deliberately unguarded against double-click** on an idempotency bet (`qa-remfix-2.md:48-74`).
18. **The `app_state["kill.<id>"]` null-row distinction is not observable through any `Store` verb** — only a direct sqlite open could see it, which the storage-boundary test forbids (`qa-remfix-3.md:151-157`).
19. **`web/server.py`'s byte-pin blocks every non-`.html`/`.js`/`.css` fixture** (G11).
20. **`controld` refuses to start with `XDG_RUNTIME_DIR` inside the scratchpad** — the abstract socket budget is 107 bytes and the scratchpad path alone is 88 (`SocketPathTooLong`). Only the runtime dir may be pointed at a short throwaway; data and config stay in the scratchpad (`integration.md:205-211`).
21. **Stated flake policy is no retries**, with fixed 700ms-after-navigation and 350ms-after-nav-click waits: *"A flaky render check is a render check that has stopped being evidence"* (`plan:2124-2126`).
22. **Phases 7, 8 and 9 may never run concurrently** — all three edit `index.html`, `app.css`, `app.js` and `consumer_manifest.json` (`plan:617-624`).
23. **Isolation model is specified and strong** (`plan:2114-2130`): one `controld`, loopback, ephemeral port, `--data-dir` under the session scratchpad, a **fresh database per run migrated from empty through 004** so it holds exactly the seeded `unassigned` project; teardown by pid from the fixture that started it — never `pkill`, never a signal to `0`, `1` or `-1`.
24. **Safety constraints binding any harness** (`plan:537-563`, `CLAUDE.md`): `tmux -L` on every invocation and **no task in this plan creates a tmux session**; never write under `~/.claude/`; a planted violation is an **inert fixture** under `tests/boundaries/fixtures/` that nothing imports; `docs/probes/` byte-unchanged, asserted by `git status --porcelain docs/probes/`; clear `__pycache__` before any mutation run.
