# Test Plan: Projects backend + dark-only web UI redesign (Shepherd / Flock / Projects / Settings) — QA round 5

**Workflow:** wf:wf-20260921T212808Z-9172ed6b · **Feature map:** `.cc10x/qa/wf-20260921T212808Z-9172ed6b/feature-map.md`
**Environment:** `.cc10x/qa/wf-20260921T212808Z-9172ed6b/env-plan.md`
**Status:** draft · **Revision:** `r4` — the `r4` amendment is **environment-only** (preflight-driven); no scenario, contract or coverage claim in this file changed, and `r3` remains what pass 2 reviewed
<!-- A bare `reviewed` is the unqualified claim the wording law forbids; name the revision it
     applies to. `{n}` here is the QA amendment-sweep marker (`r2`/`r3`) written by `qa-re-plan`
     into the three QA plan artifacts — NOT the PLAN route's `plan_revision`. -->

**verification_rigor:** critical_path
**Differences from agreement:** four, each stated rather than absorbed.

1. **AC-28's final clause is not executed.** Its command runs `pytest -m live`, which starts real `claude` processes against the user's real `~/.claude.json` and is forbidden by a standing user constraint (C-4). **S30 substitutes** a served-`controld` render sweep over `render_check.VIEWPORTS` carrying no `live` marker. A PASS on S30 does **not** discharge AC-28, and the run report must say so in those words.
2. **Three acceptance criteria are false of the tree and are not re-written by this run.** AC-16 asserts `len(BODY_ARGS) == 15` (measured: **16**), AC-21 asserts exactly six `post_milestone` entries (measured: **7**), AC-23 asserts `terminal.js` byte-clean against a baseline it has since left (`ace78240` → `781bed86`). Round 5 **measures the tree and declares the clauses stale** (S31). Amending the plan mid-QA would mean the run rewrites its own exam and then passes it — the same shape as a check that reports success without checking.
3. **AC-21's and AC-23's byte-cleanliness method is not reused.** Both use `git diff --name-only <path>`, which reads the **working tree**, so they now assert "no uncommitted edits", not "byte-identical to the milestone baseline". Every byte-cleanliness assertion here compares sha256 against `tests/boundaries/consumer_manifest.json`'s `baseline` digests (C-3).
4. **Owned sessions are seeded through `Store` verbs, not through the product's front door.** The only front door that creates a session is `spawn_session`, which starts a real engine process. See §7 — this is a named gap with a stated false-confidence cost, not an unremarked shortcut.

> The last two fields exist because cc10x's `plan_trust_gate` reads them. `Differences from
> agreement` must be present even when empty — a silent departure from what the user agreed to
> is the failure it is there to catch.

### Revision 4 — UNREVIEWED BY A FRESH PASS

**Revision 4 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap reached). This revision
was amended after the last fresh pass and has been checked only by amendment verification (not
run); no adversarial pass has read it whole. Sections changed since the last fresh review: §0 rule
4 · §1 preconditions · §2 (duplicate-name cell, viewport-width row) · §2c PP-2 · §3 wave 4
`Stop-if` · §3a (control frame count, window definition, control footprint) · §3d · §4 S5, S9,
S16, S17, S19, S22, S26, S27, S32, S33, S34 · §6 · §7 · §9a · env-plan §4 steps 5 and 10 · env-plan §5 (P2, R3) ·
env-plan §7's SSE-window row · env-plan §9 step 4 · env-plan §11 (degradation, C-8) · env-plan §12
· feature-map §4's `routes.py` row and §6's two `#p-name`/`#p-new-path` rows.
**`r4` adds, and only these**: §1's playwright, flags-OFF and **new run-root** preconditions rows ·
§3's flag-state `live` row · §9a · env-plan §1, §2, §3, §4 steps 1–3 and 9, §5, §7, §9 steps 8–9 and
the leak check, §10, §11 (B9, **new B20**, C-8, the owner census), §12 · feature map §5's B9 row.

**What `r4` is, and what it is not.** `qa-preflight` measured the machine for the first time and
returned five corrections — **all five against `env-plan.md`, all five classed `wrong-guess`, and
none of them a product defect**. This file was **not** a subject of that pass: it changes here only
where it *restates* an environment fact the measurement corrected. **No scenario, no partition, no
acceptance claim, no observation point and no denominator in this file moved** — the 35 scenarios,
the four partitions reconciling at 35, §2c's seventeen PP ids, §3a's control footprint, §3b's pane
ledger and §3d's `ROUND5_WIDTHS` are exactly as pass 2 read them.

**Reaching the cap is a stopping point, not closure.** A plan that has spent both fresh-review
passes and is then amended is **unreviewed at its current revision**, however many passes it
accumulated at earlier ones. The route's deferral register records exactly this hole — *no verifier
for a QA plan amendment made after `qa-plan-review-2`* — so the sweep in **§9a** and the
reconciliation script are the only things standing between `r3` and the harness builder. A reader
must take that as a **stated gap**, not as a review.

### What changed in `r3`, and why

Pass 2 returned **5 blocking and 11 advisory findings**. Every one was re-verified against its
cited source before acceptance. **All five blocking findings were this plan's error.** One — F5 —
was a real defect whose *proposed one-word fix* is necessary but not sufficient, and that
correction is recorded below rather than absorbed. All eleven advisories were valid.

**What pass 2 confirmed held is untouched**: all four partitions still reconcile at 35, §2c's
seventeen PP ids are unchanged, no 32-era denominator was reintroduced, the pane ledger (§3b) is
unmodified and no scenario depends on a pane another destroyed, and B2–B6 and RD-QA5-1 stand.

| # | What was wrong in `r2` | Where it is fixed now |
| --- | ------------------------ | ----------------------- |
| F1 | The liveness control **contradicted itself on frame count**: §3a said *"Two frames"*, twelve scenarios said *"exactly one frame"*, and env-plan step 10 asserted only the create. §3a's window definition said *"the control frame"*, singular, which named neither. On a healthy socket either all twelve assertions fail or the builder picks an interpretation silently | **§3a** (two frames, named and ordered; the window's opening and closing frame stated; the control's full footprint) · the twelve Queue rows · env-plan §4 step 10 |
| F2 | **S5 drove a call that cannot refuse.** `create_project` returns `{"created": True, …, "refused": None}` **unconditionally** (`toolsurface/tools_projects.py:158-169`) over a bare INSERT with no name check (`store/projects.py:52-70`); duplicate-name handling is a **client-side warning** held in page memory (`projects.js:615-627`, `:620`). S5 would have manufactured a product FAIL on the one scenario whose job is proving a negative | **S5**, rewritten onto the **reserved-project refusal** (`store/projects.py:73-80`, `:92`; `tools_projects.py:176-181`) · §2's duplicate-name cell · §2c PP-2 |
| F3 | **The S16 correction was half-propagated.** env-plan §11 said S16 is not tmux-blocked; wave 4's `Stop-if` blocked *the whole wave*, and S16's `Preconditions: as §1` inherited §1's four live panes. §11's denominators were computed on one reading and §3 on the other | **§3 wave 4** · **S16** · §1's pane row · env-plan §11 (denominator **re-derived**, not patched) |
| F4 | **`#p-new-path` was driven in a dialog mode where the control is hidden.** `projects.js:549` sets `#p-paths-section.hidden = !editing`, and `addDraftPath` returns at `:586` when `draft.project === null`. S33 (d)/(e) and S19's keyboard leg therefore issued **no request at all** — nothing refused, nothing added — and stranded R3, their only consumer | **S33** (split into a create-mode half and an edit-mode half, the latter on P1 as S32 does) · **S19** |
| F5 | **S34(d)'s path-precedence assertion could not fail for the reason it stated.** The path parameter for that template is `project_id` (`routes.py:111`) and `BODY_ARGS` for it is `("name",)` (`routes.py:160`), so `workspace_id` was dropped by the same undeclared-field rule as `colour` and *"P4 untouched"* proved nothing | **S34(d)** — the body carries **`project_id`**, the target is a **decoy the scenario owns** rather than P4, and what the assertion proves is stated as the **conjunction of two guards** it actually is, with the single-guard blindness carried as a new §7 gap |

---

### What changed in `r2`, and why

A fresh, read-only, anti-anchored review returned **6 blocking and 10 advisory findings**. Every
one was re-verified against the cited source before it was accepted; all six blocking findings
were **this plan's error**, and the sweep below is the whole list. The amendment log with the
per-finding source citation is **§9**.

| # | What was wrong in `r1` | Where it is fixed now |
| --- | ------------------------ | ----------------------- |
| B1 | Six frame-counting assertions (S0, S9, S10, S11, S12, S17) had **no in-scenario liveness control**, and S0 — which asserts *zero frames on the second SSE client* — ran as a bring-up gate **before** any SSE client was attached at all. The client lifecycle was specified only as far as wave 2 | §0 rule 4 · **§3a** (the rig's owner, for the whole run) · env-plan §4 steps 10–11 · every frame-counting scenario |
| B2 | Two `full-combinatorial` rows claimed `Uncovered: none` over sets with **undriven members**: `#proj-edit` was never opened on an ordinary project, and the **Wait** choice was driven by nothing | §2 rows · **S32** (the edit chain) · S9 (Wait and Cancel, as two distinct controls) |
| B3 | S29's "each of the four modules writes **its own** unreachable sentence" is **false of the tree**: three modules define a byte-identical string, one differs, and `flock.js` has no such constant at all | §5 provenance (four new rows, quoted from source) · **S29**, rewritten per module |
| B4 | S30 was credited with boundary widths it does not drive, its `--fail-on-empty` assertion was **unfalsifiable**, and the C-8 claim that "round 5's own scenarios read `VIEWPORTS` by reference" was true of S30 alone | §2 viewport row · **S30** (`--must-fill`) · §7's C-8 row · `ROUND5_WIDTHS` |
| B5 | PP-7's "non-zero box" tolerates a **1 px collapse**, and "≥1 clickable control" was undefined | §2c PP-7 · **§3d** (one definition of *hit-testable* and of the pane floor, read by reference by S19, S22, S23, S24, S25) |
| B6 | S10, S12 and S13 were **unprovisioned by the seed**: no attached-only project existed, and S13's owned session had no pane | env-plan §5 (P5, P6, P7) · **§3b** (the pane ledger) |
| RD-QA5-1 | — (router decision, binding) | env-plan §9: the `kill-server` teardown step is **dropped**; teardown ends by killing the QA panes by name and asserting no session remains on `shepherd-qa` |

---

## 0. Constraints that shape every assertion

**Mandatory.** These are measured facts from the feature map and the researcher reports — not wishes to be engineered away. Every scenario below is written *inside* them.

| Constraint | Consequence for assertions |
| ------------ | ---------------------------- |
| **No health or readiness endpoint exists** (B1). The only liveness proxy is `GET /api/fleet`, which needs a working store | Readiness is the `bound` event `controld.start` sets **plus** a functional probe. No scenario may assert "up" via HTTP alone, and a probe failure after a clean bind is `BLOCKED` |
| **`render_check.py` cannot see intra-page grid collapse** — `#page-flock`'s rectangle is byte-identical healthy and broken (56→900 in both); Chromium reports the *implicit* grid track so both read as three rows (B2) | No scenario may assert layout health from a **page-root** rectangle. Grid-collapse assertions measure the **panes** (`#proj-list`, `#proj-detail`, `#settings-nav`) |
| **A self-sizing box grows to fit** — a 307,418 px container passed every "content fits its box" assertion (B3) | Every containment assertion is against the **viewport**, never the parent. A parent-relative containment assertion is unfalsifiable here |
| **A module-graph walk certifies a fetch, not a call** (B4) — `flock.js` was "reached" while the page never drew | No scenario may assert that a module ran because it was imported. Every UI claim is a measured DOM or pixel fact |
| **A lexical `try`-scan cannot see an empty `catch`** (B5) | No scenario may assert error handling from the presence of a `try`. Every error path is driven and the assertion is the rendered sentence |
| **`tests/web/test_ws.py`'s 14 reader tests assert a contract with no implementer** — the WebSocket read half has no caller in `src/` (B14) | Vacuous by construction. Round 5 drives the **write** half over the wire and makes no claim about those 14 |
| **`js_syntax_check.py` and `render_check.py` sit behind `importorskip` for an undeclared playwright dependency** — a machine without it collects and **passes** (B13) | Preflight asserts playwright is present *and* that a real `chromium.launch()` succeeds. A skipped gate is never read as a green one |
| **`correlation_id` is `uuid4().hex` per request with no injection point** (B17) | Match a 32-hex **pattern**, never a value |
| **The page-level clock is not injectable** — `app.js:115` calls `Date.now()` directly in `drawFlock` (B12) | Seed timestamps ≥2× from every relative-time boundary; assert the `<60 s` class at the API seam only |
| **`web/server.py` is byte-pinned; `_CONTENT_TYPES` is `.html`/`.js`/`.css` only** (B8) | **No font, image, SVG or JSON fixture may enter the static tree.** Every fixture is a store row, an HTTP body, or a file outside `src/shepherd/web/static/` |
| **Registry, ring and `compose._PLANE` are module-global** (B10) | One `controld` per process; scenarios are serial. No `pytest-xdist` in this package |
| **`add_repo` shells out to git with no stub seam** (B11) | Every `add_repo` scenario needs a **real repository on disk** |
| **`app_state["kill.<id>"]`'s null-row distinction is unobservable through any `Store` verb** (B7) | No scenario asserts it. Reaching it would need a direct sqlite open, which the storage boundary forbids |
| **`pre_m4_routes.json` freezes only the pre-T24 surface**; the nine Projects/M4 routes are additive-checked only (B15) | No scenario may treat that gate as a contract freeze on the delete body |
| **No acceptance criterion, P-property or flow map covers any event/SSE obligation** (C-2) | The event obligation is asserted **directly** by this plan, because nothing in the acceptance set will. A **second live client** is a first-class requirement |
| **`pytest -m live` is forbidden** (C-4) | AC-28's final clause is not executed; S30 substitutes and the report declares it |
| **No latency SLO is stated anywhere in the authority documents** | Every time bound here is a harness liveness bound. Blowing one is `BLOCKED`/`TIMEOUT`, never a product `FAIL` |
| **`Audience.HUMAN` is allowed for `LOCAL_DESTRUCTIVE` at both autonomy levels**, attributed `claimed_human` (`policy.TABLE`) | No web call parks on an approval card. No scenario may assert that the level-2 toggle gates a browser delete — and the 600 s approval deadline is never reached |
| **A refusal announces nothing** — `announce()` publishes iff the record's own positive key is True | "Zero frames" is a real expected value, and it needs a liveness control to be meaningful — **in every scenario that asserts one**, which is rule 4 below and §3a, not S5 alone as `r1` had it |

Three rules follow from this section and bind the whole plan:

1. **A time bound is a harness liveness bound, never a product SLO.** Blowing an unsourced bound is `BLOCKED`/`TIMEOUT`, never a product `FAIL`.
2. **`BLOCKED` is a distinct outcome from `FAIL` and from `PASS`.** A scenario that could not run has not passed. It never rounds up.
3. **When a state is unreachable in code, assert its absence** — not its appearance. A fixture written past the application's own validators is testing fiction and is labelled as such.
4. **A zero frame count means nothing without an in-scenario liveness control.** A **strictly positive, unbounded-above** expected count is self-controlling — a dead socket delivers nothing and the scenario fails. **Every expectation that is zero, conditionally zero, or bounded above ("exactly `n` and no more") is not:** the scenario drives the §3a control **last in its own body** and asserts its **two** frames, `project.created` then `project.deleted`, the second of which closes the window. A zero that is not bracketed by a control is a reading off a socket that may be dead: it is recorded `BLOCKED`, never `PASS`. In `r1` this rule was stated once, in S5's prose, and six other scenarios asserted a zero without it — one of them, S0, before any client had been attached at all.

   **`r3`: the membership is a census over every `| Queue |` row in §4, not a list.** `r2` presented an exemption list *"S4, S6, S7, S8, S13, S18 and S28"* as exhaustive and it was not — S3's row and S19's are both frame counts and appeared in **neither** list. The argument was always sound; the enumeration is what loses a member each revision. So the rule is stated as a **partition with a decision procedure**, and every Queue row in §4 falls into exactly one cell:

   | Cell | Decision procedure | Members (re-derived from §4's Queue rows, `r3`) | Control? |
   | ------ | -------------------- | ------------------------------------------------- | ---------- |
   | **(i) not asserted** | the row reads `not asserted`, or asserts a socket state rather than a frame count | S1, S2, S14, S15, S16, S20, S21, S22, S23, S24, S25, **S29** (asserts the stream is *closed*), S30, S31 — **14** | no |
   | **(ii) strictly positive, unbounded above** | the row states a minimum and no maximum; a dead socket delivers nothing and the row fails on its own | S3, S4, S6, S7, S8, S13, S18, S28 — **8** | **no — self-controlling** |
   | **(iii) zero, conditionally zero, or bounded above** | the row states a zero, a zero on a branch, or an exact count with "and no others" | S0, S5, S9, S10, S11, S12, S17, **S19**, S26, S27, S32, S33, S34 — **13** | **yes** |

   14 + 8 + 13 = **35**, every scenario in exactly one cell. **Two changes from `r2`'s enumeration, both re-derived rather than patched:** S3 joins cell (ii) — it was in no list, and its *"both clients receive the `project.created` frame"* is a strictly-positive count that needs nothing added; and **S19 joins cell (iii)**, because under `r3`/F4 its Enter leg drives a **refusal**, which contributes zero, making its window all-zero. The rig's ownership across the whole run is **§3a**.
5. **The classification of a red is decided here, not at run time**, on the five chains that have never been executed in four rounds — S0, S11, S13, S14, S17. This is the ground where the plan has the least prior evidence, and it is exactly the ground where an executor should not be left to invent a verdict:

| What went red | Classification | Why |
| --------------- | ---------------- | ----- |
| The product's own call failed **and** every fixture-side control in **§3c** is green | product `FAIL` | the pane existed, the handle round-tripped, tmux answered — what is left is the product |
| Any fixture-side control in §3c is red (the pane could not be created, the seeded `RunnerHandle` does not round-trip through `handle_for`, a fixture `kill-session` did not remove a pane) | environment `BLOCKED` | a red here says the *seed* was wrong, not the shipped kill. Without §3c's controls the two are indistinguishable, and `r1` had no way to tell them apart |
| The chain could not be driven at all (no tmux, no pane, no 101) | environment `BLOCKED` | §11 of the env plan, degradation |
| What arrived differs from an expectation this plan **inferred** rather than quoted from source (§5's `I` rows; S0's binding; S11's and S17's `deleted` value) | **measurement**, reported as the finding | a plan's guess losing to the tree is a finding about the plan. Calling it a product `FAIL` manufactures a defect |

---

## 1. Scope

**Under test:** the shipped Projects surface end to end — the six project/repo mutations and three reads, the delete verb's plan→kill→commit path against **real running sessions on a real tmux socket**, the event obligation from `announce()` through the ring to a **second live client**, the terminal WebSocket against an **owned** session, and the four live pages (Shepherd, Flock, Projects, Settings) rendered in a real browser across widths from 320 to 2560 and under `prefers-reduced-motion`, forced colors, RTL and zoom.

**Not under test:** anything requiring a real `claude` process (`spawn_session`, the Agent SDK master turn loop, `pytest -m live`) · `sessiond` and the relay · the Queues and Kanban page roots, which are static "not built this milestone" stubs with no module · the WebSocket **read** half, which has no implementer by decision · `POST /api/sessions/{id}/permission`, which is routed, registered and called by no page · D1/D2/D3, closed at `b1c1eb9` and re-verified in round 4 — S24 and S25 are **cheap regression only**, not re-proof · round 1's eleven closures, which are recorded with no id, no description and no named check and **cannot be re-verified at all**.

**Services involved:** `controld` (HTTP + SSE + WebSocket + registry + chokepoint + audit sink + discovery loop), the SQLite `Store` at schema 004, the `LocalRunner` against tmux socket `shepherd-qa`, `git` (via `probe_repo`), and headless chromium.

### Preconditions carried from the environment

| Requirement | Value | Source |
| ------------- | ------- | -------- |
| Feature flags ON | none exist. `app_state["runner_socket"] = "shepherd-qa"` is the flag-shaped setting that must be ON before `controld.start` | env-plan §2 |
| Feature flags OFF | pytest's `live` marker (deselected by `addopts`, never overridden — and the gate is **marker-based**: live-marked **76 == 76** deselected, never a path scan; `r4`/P5); **`TMUX` unset by the fixture** (`r4`/P2 — measured inherited and non-empty on this host, and now an env-plan **§7** row, which is the table the manifest is generated from, rather than only a §2 rule); `XDG_RUNTIME_DIR` inside the scratchpad; the `shepherd` socket | env-plan §2 · **§7** · `setup.md` §2 |
| Entitlement / plan tier | `N/A` — single-user, single-tenant, loopback-only. No tier exists | env-plan §2 |
| Actor role / permissions | exactly one: `caller_id="web"`, `Audience.HUMAN`, an **unauthenticated self-stamp**. There is no role to select | env-plan §2 |
| Org / tenant settings | `N/A` — none exist | env-plan §2 |
| `app_state["autonomy_level"]` | `2` at bring-up (the default); driven 2→3→2 by S26 only | env-plan §2 |
| Store schema | `user_version == EXPECTED_SCHEMA_VERSION`, fresh DB, exactly one workspace (`unassigned`) before seeding | env-plan §5 |
| Seeded world | P0–P7, S-own-1..4, S-att-1..7, S-fin-1..6, R1, R2, **R3** — **`n > 1` everywhere**, four owned sessions each over its own pane, one **attached-only** project (P5), one duplicate name, one ellipsising path, **one regular file (`R3`, `$SCRATCH/work/afile`) as the non-directory fixture**. (**`r3`:** R3 was added to env-plan §5 and test-plan §6 in `r2` and omitted here — and this row is what *"Preconditions: as §1"* inherits, so S33's only non-directory fixture was not in the preconditions of the scenario that drives it) | env-plan §5 |
| tmux panes | `shepherd_r5a`, `shepherd_r5b`, `shepherd_r5c`, `shepherd_r5d` live on socket `shepherd-qa` — **four, one per owning scenario (§3b)**. **`r3` (F3): this row is the one §1 precondition S16 does NOT inherit** — S16 drives `no_pane` off a missing handle and contacts no tmux (`tools_terminal.py:228-237`). Any scenario that writes `Preconditions: as §1` inherits this row; S16 says so explicitly in its own block | env-plan §4 step 5 |
| second SSE client rig | clients **A** and **B** attached at bring-up **step 10** and proved live there; owned by the session fixture until teardown step 3 | env-plan §4 step 10 · §3a |
| fixture-side controls | the pane-kill control and the handle round-trip control both green before wave 1 | env-plan §4 step 10 · §3c |
| playwright | importable **and** `chromium.launch()` succeeded **under the harness's own redirected environment** — measured, not assumed. **`r4`/P1: that qualifier is the whole finding.** The chromium binary is **not** in `.venv`; it is at `/root/.cache/ms-playwright/chromium-1243/`, on a path playwright derives from `XDG_CACHE_HOME`/`HOME`, which the harness redirects — so the launch must be proved with `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` pinned (env-plan §7). Under the *inherited* environment this check passes while the harness still fails | `setup.md` §2 · env-plan §7 |
| `docs/probes/` | `git status --porcelain docs/probes/` empty | `setup.md` §2 |
| **`$SCRATCH` is a minted run root, not the session scratchpad** | **`r4`/P3.** Every `$SCRATCH/<sub>` path in this document — `$SCRATCH/work/notgit`, `$SCRATCH/work/afile`, `$SCRATCH/repo/plain`, `$SCRATCH/shots/` — denotes `$SESSION_SCRATCH/qa5-<pid>/<sub>`, minted per run and removed at teardown. The **session** scratchpad is long-lived and shared and holds `macwt`, a **registered git worktree of `/root/Shepherd`**; it is never removed, and teardown asserts `git worktree list` is unchanged across the run. Defined **once**, at env-plan §4 step 1 | env-plan §4 step 1 · §9 steps 8–9 · `setup.md` §2 |

**`Source` may be `env-plan §N` or `setup.md §N`, and the difference matters.** An `env-plan` source is a *prediction* written from source code; a `setup.md` source is a fact preflight *observed* on the machine. When the two disagree, the measurement wins and the disagreement is itself a finding — record it in `setup.md` §4 rather than quietly preferring one.

---

## 2. Coverage plan

The User Action Inventory in the feature map (§6, unreduced) is the full input space. This table is how much of it this plan actually executes, and by what rule.

**Reduction is deliberate, never silent.**

| Control group | Space size | Technique | Cases | Uncovered — and why that is acceptable |
| --------------- | ------------ | ----------- | ------- | ---------------------------------------- |
| six nav entries | 6 | every-option-once | 6 (S1, S23) | nav **orderings** beyond one forward pass and one back-pass. `data-level` unwind is covered once (S1); the permutation space is 720 and no defect shape in four rounds was order-dependent |
| eight legend keys + info button | 9 | risk-ranked | 2 (S20, S25) | seven keys. All nine bind **one** handler (`openLegendSheet`, U1) — measured in round 3, and round 3's own false probe #5 was reading them as filters. Driving nine identical bindings is nine tests of one line. Risk-ranked is a judgement call and is visible as one |
| project rows / session cards (data-driven) | unbounded | equivalence-classes: reserved · ordinary · duplicate-name · long-path · owned-session · empty | 6 — reserved S2 · ordinary S9 · duplicate-name S33 · long-path S24 · owned-session S11 · **empty S2** | rows outside the six classes. The classes are chosen from the defect record: five of them were the **absent** cases that made nine round-1 defects invisible at `n = 1`. **`r2` correction:** the `empty` class named S29, which is the daemon-down scenario and asserts nothing about an empty list. It is now S2, which reads P2 — zero repos, zero sessions — and asserts the **empty-state sentence**, not a blank pane |
| `next_actions[]` (7 kinds) | 7 | every-option-once over the 3 live kinds + 1 inert representative | 4 (S1) | three inert kinds. All four inert kinds render from **one** `not yet` branch; a second inert kind tests the same branch again |
| decision-card choices | inert by construction | `N/A` — nothing to reduce | 0 | everything. Asserted as an **absence**: S1's console sweep requires no error and no navigation from a card click |
| `#proj-new` / `#proj-edit` / `#proj-delete` × {`unassigned`, ordinary} | **5 real cells, not 6** — `#proj-new` is page-level and does not vary with the selected row, so its two nominal cells are one control | full-combinatorial | 5 — `#proj-new` S28 · `#proj-edit`×ordinary **S32** · `#proj-edit`×`unassigned` (absent) S2 · `#proj-delete`×ordinary S9 · `#proj-delete`×`unassigned` (absent) S2 | none. **`r2` correction:** `r1` claimed `Uncovered: none` while `#proj-edit` was **never opened on an ordinary project anywhere in the plan** — its only two occurrences were the *absence* assertion on `unassigned`, and the feature map's chain *"Edit a project's paths → add path → remove path → Save"* was driven by nothing. **S32** drives it. Edit and Delete are **absent, not disabled**, on `unassigned`, and "absent" is a different assertion from "disabled" — both are driven |
| `#p-name` / `#p-desc` / `#p-new-path` text values | 9 named values × 3 fields | boundary-values + equivalence-classes | 7 — empty **S33(a)** · whitespace-only **S33(b)** · duplicate name **S33(c)** · non-existent path **S33(d)** · non-directory **S33(e)** · non-git dir **S34(e)** · 935 px path S2, S24 | **bare repo, subdirectory-of-a-repo** — **two, not three**. **`r2` correction:** `r1` left the page's **entire validation surface** (empty, whitespace-only, non-existent path, non-directory) driven by nothing *and* absent from this column, and declared non-git-dir uncovered while **R2, a non-git directory, was seeded explicitly "for the `add_repo` refusal path"** — a fixture provisioned and never consumed, and a flat contradiction with env-plan §5. S33 drives the four page-side values; **S34 consumes R2** and drives the `add_repo` refusal. The two that remain each need a distinct real repository shape on disk (B11) and each exercises `probe_repo`, not the page. Carried as a `deferred` gap in §7. **`r3` correction (F2):** this cell credited **S5** with the duplicate-name value, and S5 drove `POST /api/projects {"name":"Shepherd"}` expecting a refusal that **cannot happen** — the store is a bare INSERT keyed by id (`store/projects.py:52-70`) and duplicate handling is a page-memory warning (`projects.js:615-627`). Duplicate-name is **S33(c)** alone, at the page seam where the behaviour actually lives; S5 now drives the reserved-project refusal on the wire. The count stays **7** because S33(c) already covered this value — the cell named two scenarios for one value, one of which could not deliver it |
| delete-dialog choices | 5 (Delete · Stop-then-delete · Move to Unassigned · Wait · Cancel) | full-combinatorial | 5 — Delete (no `on_running`) S0 · Stop-then-delete S11, S12 · Move-to-Unassigned S13 · **Wait S9** · **Cancel S9** | none — **but every row's meaning is bound by S0.** Until S0 returns, none of these five is interpretable. **`r2` corrections, two:** (a) `r1` claimed `Uncovered: none` while **Wait** was driven by no scenario — its only occurrence was this enumeration. `Wait — keep the project` and `#dlg-delete-cancel` are **two distinct controls** in `projects.js` and S9 now presses each. (b) **S10 was counted as a case and is not one**: it asserts the *disabled state* of the Stop-then-delete choice, which is a different claim from exercising it, and it is listed on its own row below |
| ten Settings sections | 10 | every-option-once | 10 (S23) | the controls *inside* each section. Section reachability is the D1 shape (`.herd-col` collapse); per-control coverage is a different plan. **`r2` correction:** S30 was listed here and sweeps **page roots**, not Settings sections — it contributes nothing to this row |
| the Stop-then-delete choice's **disabled state** | 2 (killable non-empty · killable empty) | full-combinatorial | 2 (S10) | none. Split out of the choices row above because a disabled-state assertion is not a choice exercise. Case (b) needs a project with **only attached** running sessions, which is **P5** — provisioned by env-plan §5 in `r2`, and provisioned by nothing in `r1` |
| autonomy options (2 = ask, 3 = auto) | 2 | full-combinatorial | 2 (S26) | none. And the measured finding is that **neither value changes what the web caller may do** — `Audience.HUMAN` is allowed at both |
| keyboard: composer (Enter / Shift+Enter / empty) · inline rename (Enter / Escape) · `#p-new-path` (Enter must not submit) | 6 | every-option-once | 6 (S19, S28) | modifier combinations beyond Shift (Ctrl/Alt/Meta+Enter). No handler reads them |
| drawer / rail toggles × viewport | 2 × 2 × 3 = 12 | pairwise | 4 — drawer-open×390 S19 · drawer-closed×390 S19 · **rail-open×1280 S24** · **rail-collapsed×2560 S23** | 3-way drawer × rail × zoom. Round 3's false probe #1 was a **closed drawer read as broken nav**; the pairwise set covers open-and-closed at each width class, which is the reading that went wrong. **`r2` correction:** `r1` claimed pairwise over drawer × rail × viewport while the **rail toggle was never driven** — `#collapse` and `#shell[data-rail]` appear in no `r1` scenario. S19 and S23 drive it now |
| dates / relative-time scale | 9 classes | equivalence-classes | 3 (S2) | six mid-scale buckets. **B12: the page clock is not injectable in a browser**, so asserting a mid-scale bucket in the browser is asserting the wall clock. The three covered (null, far-past, `<60 s`) are asserted at the API seam |
| viewport widths | unbounded | boundary-values | **9** — 320 S23 · 390 S21 · 760 S24 · 761 S24 · 820 S21, S24 · **900 S24** · 1280 S21, S22 · 1920 S23 · 2560 S23 | widths between the nine measured. **`r2` corrections, two:** (a) `r1` said *eight* and its own prose added 900, so the measured set was always nine — env-plan §12 called the same list *seven*, and both are corrected. (b) **S30 is not in this list.** It sweeps `render_check.VIEWPORTS` = `[("phone",390,844),("tablet",820,1180),("desktop",1280,900)]` (`tools/render_check.py:54`) — three widths S21 already drives, so it delivers **no boundary width** and is counted only under C-4's substitute. **761 and 900 were previously *reasoned from the media query*, never measured** — round 5 measures them. Anything above 1280 or below 390 has never been driven at all |

**Techniques:** `every-option-once` · `pairwise` · `equivalence-classes` · `boundary-values` · `full-combinatorial` · `risk-ranked` (used once, on the legend keys, and named as the judgement call it is)

**Every number in the `Cases` column is traceable to the scenario rows that deliver it** — written as `N (S3, S7)`, never as a bare `N`.

### Every rollup in this section must reconcile

**Total: 35 scenarios, S0–S34.** (`r1` had 32; `r2` adds **S32** — the `#proj-edit` chain B2 found undriven — and **S33** / **S34**, the page-side and wire-side halves of the validation-and-refusal surface B2's second half and three advisory findings found undriven. Every rollup below is re-derived, not patched.)

- **By id:** S0 … S34 → `34 − 0 + 1 = 35` ✓
- **By class:** happy-path 10 + error-handling 8 + edge-case 17 = **35** ✓
- **By tier:** integration 5 + e2e_backend 13 + ui 17 = **35** ✓
- **By wave:** W1 4 + W2 5 + W3 5 + W4 4 + W5 9 + W6 8 = **35** ✓

Every scenario appears in exactly one wave, one class and one tier. An off-by-one here is not cosmetic: the scenario most likely to fall out of a rollup is the one added last or the one that does not fit the usual shape — which here is **S0**, the binding probe, **S5**, the one deliberate expected-zero, and in `r2` the three added last: **S32**, **S33** and **S34**. All four partitions above were re-derived from the scenario headings in §4 rather than incremented, and each reconciles at 35 with no duplicate and no omission.

### Coverage by class

| Class | Scenarios | Notes |
| ------- | ----------- | ------- |
| happy-path | S1, S2, S3, S4, S9, S11, S14, S18, S26, S30 — **10** | Includes the two that have never been driven at all: S11 (a kill that lands on a real pane) and S14 (the terminal WebSocket) |
| error-handling | S5, S8, S12, S16, S17, S29, **S33**, **S34** — **8** | Per boundary: refused (S5), late/behind the ring (S8), kill refused (S12), no pane (S16), stale handle (S17), daemon down (S29), the page's own validation refusals (S33), the wire's refusals — `add_repo`, origin, undeclared field, `GENERIC_ERROR` (S34) |
| edge-case | S0, S6, S7, S10, S13, S15, S19, S20, S21, S22, S23, S24, S25, S27, S28, S31, **S32** — **17** | Boundaries, concurrency, ordering, identity, data shape, draft state across three round trips (S32), and every a11y/viewport mode never previously driven |

### Coverage by tier

| Tier | Scenarios | Why this tier |
| ------ | ----------- | --------------- |
| integration | S2, S6, S13, S26, S31 — **5** | The claim is about a store row, a projection field, a file on disk or a digest. Driving a browser to assert a digest would be an E2E test of a pure fact |
| e2e_backend | S0, S3, S4, S5, S7, S8, S11, S12, S14, S16, S17, S27, **S34** — **13** | The claim crosses HTTP/SSE/WS with every real dependency behind it, including real tmux — but the observation point is the wire and the store, not a pixel. This is the **highest seam that still covers the risk** for the event obligation and the delete family |
| ui | S1, S9, S10, S15, S18, S19, S20, S21, S22, S23, S24, S25, S28, S29, S30, **S32**, **S33** — **17** | The claim is only true if a browser laid it out, ran it, or handled the event. Every one of these is a claim no API assertion can make |

**Seam discipline:** prefer the existing seam. `tests/daemons/test_controld.py` already holds the composed-`controld` + SSE-`Subscriber` seam and `tests/web/conftest.py` already holds the HTTP-client seam; round 5 reuses both shapes rather than inventing a third. The one genuinely new seam is the **real tmux pane behind an owned session**, and it is new because the authorisation to open it is new.

### Coverage by flag state

| Flag | ON — feature behaves correctly | OFF — old path still works / feature absent cleanly | Toggled mid-session |
| ------ | -------------------------------- | ----------------------------------------------------- | --------------------- |
| `app_state["runner_socket"] = "shepherd-qa"` | S11, S14, S15, S16, S17 — the kill lands, the pane streams | **not driven ON=off.** With the default `shepherd-runner` there is no server and every kill answers a refusal. That is the state every prior round ran in, and it is what made `killable` empty everywhere — so the OFF column is not a gap, it is the previous four rounds | `N/A` — read once at composition time; changing it mid-run would not reach the composed runner, and asserting otherwise would be asserting fiction |
| `app_state["autonomy_level"]` | 3 (auto): S26 asserts the audit record's `decision`/`approved_by` | 2 (ask, the default): S26 asserts the same call is **still allowed** for `Audience.HUMAN`, attributed `claimed_human` | **S26 is the toggle**: 2 → 3 → 2, three POSTs, three audit records read off disk |
| pytest `live` marker | never ON | always OFF — asserted in preflight **on the marker, as an integer**: `--collect-only -q` (default) against `--collect-only -q -m live`, live-marked **==** deselected, measured **76 == 76** at 2226/2302 collected. (**`r4`/P5:** a *path*-based reading of the collected set is wrong on this tree — three `tests/e2e/` node ids are collected by default on purpose, and one of the two modules says so in its docstring) | never toggled |

**The OFF column is the one that gets skipped, and it is where the expensive incidents come from.** Here it produced the plan's sharpest finding: the autonomy toggle the Settings page presents **does not change what the browser may do**, at either value, because `policy.TABLE` allows `LOCAL_DESTRUCTIVE` for `Audience.HUMAN` at both levels. That is not a defect this plan asserts; it is a product question S26's measurement will put a number on.

**Entitlement × flag:** `N/A` — no entitlement system exists. Stated rather than omitted.

---

## 2c. Provable properties

**Required: `verification_rigor` is `critical_path`.** This work destroys rows, kills live processes and is irreversible: `delete_project` cascades inside the verb, `GAP 5` records that it destroys on its **first** call when nothing is running, and the kill leg runs outside any transaction on the calling thread.

| PP-id | Property — what a green run is claiming is true | Scenario ids that would break it | At risk of appearing proven |
| ------- | ------------------------------------------------- | ---------------------------------- | ----------------------------- |
| PP-1 | Every **succeeded** project mutation reaches a second live client as one `project.*` frame | S4, S18, S27 | **yes** — this is D7's hole exactly: six mutations, six 200s, zero frames, with every suite green. A suite with one client cannot see it |
| PP-2 | A **refused** mutation reaches no client at all | S5, S0, S9, S10, S12, S17 | **yes** — proving a negative. Without a liveness control the assertion passes on a dead socket. **`r2`:** in `r1` this row named S5 alone while six other scenarios asserted the same negative **with no control**; §0 rule 4 now binds all of them, and they are named here so the property's breaker set is the real one. **`r3` (F2), and it is the sharper failure:** the breaker set was right, but its **headline member drove a call that cannot refuse.** S5 posted a duplicate project name and expected `created == false`; `create_project` returns `created: True` unconditionally (`tools_projects.py:158-169`), so S5 would have failed against a **correct** product and reported a fabricated defect. A property whose headline breaker cannot produce the negative it is breaking is not proven by that breaker at all. S5 now drives the **reserved-project rename**, which refuses unconditionally at `store/projects.py:92` → `:73-80`. **The breaker id set is unchanged** — S5 is still the member; what changed is that it can now do the job |
| PP-3 | `killable` names exactly the running sessions **that have a `runner_handle`** — the set the shipped kill asks `handle_for` about — and the page's three-way choice is drawn from it | S0, S10, S11, S12, **S17** | **yes** — two authority documents describe this record differently (C-6), and every prior fixture read `killable` as empty. **`r2` restatement, and it is the honest form:** `r1` said *"the sessions the shipped kill **can stop**"*, which **S17 falsifies by construction** — a stale handle is in `killable` and cannot be stopped — while S17 was not in the breaker list. The store's own comment is the authority: *"The store reports the fact (`runner_handle IS NOT NULL`); naming it **killable** is the one inference"* (`src/shepherd/store/models.py:186`). The property is now that fact, which is provable; the stronger reading is false, and S17 is what proves it false |
| PP-4 | A `kill_sessions` delete against a real owned pane **removes the pane from the tmux socket** | S11, S17 | no — the pane is either listed or it is not |
| PP-5 | The first WebSocket frame is the pane snapshot **byte-for-byte** | S14 | no — byte equality against the same `capture-pane` bytes is not loosely satisfiable |
| PP-6 | Every gated invoke appends **exactly one** record to the on-disk audit log, with `at`, `tool`, `decision`, `approved_by` and redacted args | S26 | **yes** — the prior claim ("two autonomy POSTs append two audit rows") is **reasoned, not measured**; the chokepoint fixture collects into a list and never touches disk |
| PP-7 | At every measured width from 320 to 2560: no page root leaves the viewport, **the root reaches at least `FILL_FLOOR` of the viewport height**, and each of the Projects panes **contains the whole box of ≥1 hit-testable control** (§3d) | S21, S22, S23, S24 | **yes** — the root-rectangle check is structurally blind (B2) and a parent-relative containment assertion is vacuous (B3). This property is the one most able to look proven while proving nothing, **and in `r1` it was still proving nothing**: moving the measurement from the root to the panes defeated B2, but *"non-zero"* is a **one-pixel floor** — a pane collapsed to 1 px tall with a button inside satisfied it. The floor is now the product's own (`FILL_FLOOR = 0.75`, `tools/render_check.py:87`) plus a containment relation no 1 px box can satisfy |
| PP-8 | Frame `id:` values are strictly monotonic, and under two concurrent writers no frame is lost or duplicated at either client | S8, S27 | **yes** — ordering was never driven; every prior "concurrency" test was two synchronous `click()` calls on one thread |

**The fourth column is a self-flag, and the cost points toward honesty.** Six of eight rows are flagged `yes`. With eight properties the mutation floor applies per-row to the `yes` rows; declining to flag would fall back to the per-tier-**and**-per-wave floor, which across three tiers and six waves is strictly more mutation work than six honest rows.

### The three mapping cases, and the floor in each

| Case | Shape | Floor |
| ------ | ------- | ------- |
| One property → many scenarios | PP-1 → S4, S18, S27 · **PP-2 → S5, S0, S9, S10, S12, S17** · PP-3 → S0, S10, S11, S12, **S17** · PP-7 → S21, S22, S23, S24 · PP-8 → S8, S27 | **One** falsified assertion anywhere in the set satisfies the property. Which scenario shows it is the harness builder's choice |
| Many properties → one scenario | S27 carries **PP-1 and PP-8** | **Two separate mutations of S27**, one per property, each naming a different failing assertion. Collapsing them into one is the conflation this section exists to end |
| Property → no scenario | **none.** Every PP-id names at least one scenario that exists in §4 | — |

**Reconciliation (`r2`, re-derived):** PP-1…PP-8 name S0, S4, S5, S8, **S9**, S10, S11, S12, S14, S17, S18, S21, S22, S23, S24, S26, S27 — **seventeen** distinct ids, all present in §4. `r1` said sixteen; PP-2 gained S9 when the six uncontrolled zero-frame assertions were named as breakers of it. No row names `—`, so nothing is carried into `TESTABILITY_BLOCKERS` from this table.

**Mutation-run hygiene, binding on the harness builder:** clear `__pycache__` before **every** mutation run. CPython decides a `.pyc` is fresh from `(source mtime in whole seconds, source size)`, so a size-preserving mutation landing within the same second as the last compile re-imports the *unmutated* bytecode and records a **false survivor** — a hole in the tree written down as proof that there isn't one. Recorded REDs are unaffected; the exposure is entirely to survivors. And a planted violation, if any is planted, is an **inert fixture under `tests/boundaries/fixtures/` that nothing imports** — never a signal, a `kill`, a reboot-capable call or a teardown verb in executable code, not in the repo, not in a shadow tree, not in a scratch copy.

---

## 3. Build order

| Wave | Scenarios | Objective — what this wave proves | Depends on | Stop-if |
| ------ | ----------- | ----------------------------------- | ------------ | --------- |
| **1** | **S0**, S1, S2, S3 | The pipeline is wired end to end — the page is served, the store answers, the stream carries — **and C-6 is bound by measurement** | bring-up steps 1–11 (the rig of §3a is attached **and proved live** at step 10, and the §3c fixture-side controls are green, **before** S0 counts a frame at step 11) | S0 binds anything other than **B-OWNED** (see S0 — with this seed and `store/reads.py:283-284`, B-OWNED is the only reachable branch, so a departure is itself the finding and wave 1 stops on it); or step 10's rig control delivered no frame; or S1 records any `console.error`/`pageerror` at arrival; or S3's second client receives nothing |
| **2** | S4, S5, S6, S7, S8 | **The event obligation** — C-2's hole. Six mutations reach a second client; a refusal reaches none; the envelope and the frame have the shape the spec fixes | wave 1. **The rig is not S3's to provide:** it is attached and proved live at bring-up step 10 and owned by the session fixture (§3a); S3 asserts its contract | S4 shows **zero** frames for all six mutations — that is D7 returned, and waves 3–6 would spend their time re-finding it |
| **3** | S9, S10, S11, S12, S13 | **The delete family** against real running sessions: the refusal record rendered, the disabled choice, a kill that lands, a kill that cannot, and the orphan path | wave 1 (**S0's binding**), wave 2 (the event assertions reuse the rig). **Panes: S11 consumes `shepherd_r5a`, S13 consumes `shepherd_r5d`** — §3b | S0 bound **B-EMPTY**. With a green §3c handle control that means the projection lost a handle the store round-tripped, which is a product finding; with a red §3c control it is the seed, and the wave is `BLOCKED` (§0 rule 5). Either way S10 collapses to case (b) alone and S11 has nothing to drive. **Ordering inside the wave is fixed: S9, S10, S12, S11, S13** — S11 destroys P4's pane and S12 reads P5, so S12 must not wait behind it |
| **4** | S14, S15, S16, S17 | **The terminal WebSocket and a real tmux pane** — ground four rounds never touched | wave 3 (S11 must not have destroyed the pane these use — they use `shepherd_r5b`/P1, not P4) | tmux is unavailable, or the 101 handshake never completes: **S14, S15 and S17 are `BLOCKED`** and the run says so rather than substituting a frozen capture. **`r3` (F3): S16 is NOT stopped by this condition and must still run.** It drives the `no_pane` branch against an **attached** session that has no handle, and `terminal_stream` returns `no_pane(session_id)` from `handle_for` alone (`toolsurface/tools_terminal.py:228-237`) — contacting no tmux — which `server.py:296-308` turns into the 404 S16 asserts. `r2` said *"the whole wave is `BLOCKED`"* here while env-plan §11 said S16 is not in the tmux-blocked set, and §11's denominators were computed on the env plan's reading |
| **5** | S18, S19, S20, S21, S22, S23, S24, S25, **S32** | **The browser ground never driven**: two live tabs, real touch events, reduced motion, forced colors, RTL, zoom, every width above 1280 and below 390, and **the edit chain that keeps draft state across three round trips** | wave 1 (a served page), wave 2 (S18 asserts the event obligation at the real client) | chromium cannot launch — the entire `ui` tier is `BLOCKED` (**17 of 35**) and the run must be reported as not worth its name rather than as a partial pass |
| **6** | S26, S27, S28, S29, S30, S31, **S33**, **S34** | **The sinks, the races, the refusals, the degradation and the gates**: the audit log on disk, ordering under concurrency, the double-submit guard at a real browser, **the page's validation surface**, **the wire's refusal surface**, the daemon dying mid-flow, the AC-28 substitute, and the stale-clause measurement | waves 1–5 (**S29 stops the server and must run after everything that needs it**) | nothing — this wave is the last and its failures are findings, not blockers. **Ordering inside it is fixed: S26, S27, S28, S33, S34, S30, S31, then S29 last** |

Rules that make the waves real:

- **Wave 1 is the thinnest slice that proves the system is wired**, and it contains S0, the probe that binds the variable waves 3 and 5 consume.
- **Every wave carries a `Stop-if`.** A wave whose premise is broken must halt the build rather than hand the next wave a false baseline.
- **Order by what a failure teaches you.** S0 is first not because it is cheap but because ten scenarios are uninterpretable without it.
- **A scenario appears in exactly one wave** — reconciled above: 4 + 5 + 5 + 4 + 9 + 8 = **35**.

### 3a. The SSE client rig — one owner, for the whole run

**This section exists because `r1` did not have one.** `r1` attached the clients inside S3, left
them attached *"for wave 2"*, and said nothing after that — so S9, S10, S11, S12, S13, S17, S26
and S27 all counted frames against a rig with **no stated owner**, and S0 asserted *zero frames on
the second SSE client* at a point in bring-up where **no SSE client existed at all** (nothing in
env-plan steps 1–9 attaches one).

| Question | Answer, binding on the harness |
| ---------- | -------------------------------- |
| Who attaches the clients? | The **session fixture**, at env-plan §4 **step 10** — before S0, before wave 1, after the seed and the browser |
| How many? | Two: **A** and **B**. B is the one every "second live client" assertion reads; A exists so that no assertion can pass by being the only reader |
| When is the rig first proved live? | At step 10, by the same known-good control the scenarios use: create a throwaway project `RIG-PROBE`, assert **one** `project.created` frame at **both** A and B within 10 s, delete it. A step-10 failure is `BLOCKED` and **bring-up stops** — it is not a product verdict |
| Who owns them between waves? | The session fixture, continuously. They are **never** closed and re-opened by a scenario; the tail-subscription window (`sse.py:124-128`) is real, and re-attaching is the one operation that can walk into it |
| How does a wave re-prove liveness? | Every wave that counts frames re-runs the step-10 control **at its own start**, and every scenario that counts frames runs its own control **inside its body** (§0 rule 4). The wave-level control catches a rig that died between waves; the scenario-level control is what makes a *zero* mean something |
| What is the control mutation? | `POST /api/projects` creating `LIVENESS-<scenario-id>`, then `POST /api/projects/{id}/delete` on it. It has no sessions, so the delete lands on its **first** call (§8 decision 3, GAP 5) and `announce()` publishes on each record's own positive key — `create_project`→`project.created`/`created`, `delete_project`→`project.deleted`/`deleted` (`toolsurface/tools_projects_events.py:79-86`). **The control is therefore exactly TWO frames, in this order: `project.created`, then `project.deleted`** — both known-good, both disposable. The control is **never** one of the mutations under test |
| How is a counted window defined? | **Named by its two endpoints, both of them control frames.** A scenario's counted window **opens** on the **`project.deleted`** frame of the *previous* control — the previous control's second and last frame — and **closes** on the **`project.deleted`** frame of *this* scenario's own control. The window's interior is what the scenario's zero (or its `n`) is asserted over; the four control frames at the two ends are **outside** it and are asserted separately, by kind and by order. Comment lines (`: open`, `: keep-alive`) are **skipped**, so "no frame" stays distinguishable from "socket alive" (§5) |
| What does the control cost, everywhere it runs? | Two frames; **two gated invokes**, so **two audit records**; and one workspace row created and then destroyed, i.e. **net zero surviving rows**. This is stated once here because `r2` stated it nowhere and three kinds of count are read against it — see the footprint rule below |
| Who closes them? | env-plan §9 **step 3**, after the browser and before `controld.stop` |
| What if a control frame never arrives? | The scenario's frame assertions are `BLOCKED`, not `FAIL`, and the run report says which scenario's rig went quiet. A dead socket must never be able to *pass* a zero |

**`r3`, F1 — the control's frame count was stated two ways and the window closed on neither.** `r2`
said *"Two frames"* in the row above and **"exactly one frame for the in-scenario control"** in all
twelve scenarios that use it (S0, S5, S9, S10, S11, S12, S17, S26, S27, S32, S33, S34), while
env-plan step 10 asserted *"one `project.created` frame at both, then delete it"* — leaving the
delete's frame asserted nowhere and falling into S0's counted window. The window definition said
*"the control frame of this scenario"*, singular, and so disambiguated nothing. On a healthy socket
that is either twelve failing assertions or a builder choosing silently. **It is two frames, they
are named, they are ordered, and the second one is the window's boundary at both ends.**

**The control's footprint rule — one statement, binding on every count in §4.** The in-scenario
control runs **last in the scenario body**, after every other observation point has been read.
Therefore:

- **Frame counts** are over the window's interior and **exclude** the control's two frames, which
  are asserted separately by kind and order. A scenario whose window is a zero asserts
  *zero-then-`project.created`-then-`project.deleted`*.
- **Appended-record counts** (the audit JSONL, §5) are taken from the scenario's own mark to the
  moment **before** the control runs, and **exclude** the control's two gated invokes. Where a
  scenario states a number of audit records, that number is the calls under test; the control's two
  are asserted separately.
- **Surviving-row counts** (`workspace`, `workspace_repo`) are read **after** the control and are
  **net of** it, because the control deletes what it creates. A control that left a row behind is
  itself a failure of the control and is `BLOCKED`, not a product finding.

Without this rule, S26's *"exactly three new JSONL records"* and S33's *"exactly one new workspace
row"* would both be wrong by the control's own footprint — which is the shape F1 is an instance of.

**S3 is not the rig's constructor any more; it is the rig's contract test.** It asserts the
properties of the stream — the two headers, `id: <seq>`, the absence of an `event:` name, the
`: open` comment — and it re-proves liveness at the scenario seam. Its cleanup no longer says
*"leave both clients attached for wave 2"*, because the clients are not S3's to leave.

### 3b. The pane ledger — every owned session has a pane, and every pane has an owner

`r1` seeded **two** panes and spent them **four** times: `shepherd_r5a` is destroyed by S11 in
wave 3, `shepherd_r5b` is reserved for wave 4 (S14 and S15 depend on it surviving), `shepherd_r5c`
is consumed by S17 — and **S13's owned session had no pane at all**, which under §0 rule 3 is
exactly the thing that must be labelled rather than assumed.

| Pane | Created at | Owning session | Owning scenario | Destroyed by | Wave |
| ------ | ------------ | ---------------- | ----------------- | -------------- | ------ |
| `shepherd_r5a` | env-plan §4 step 5 | S-own-1 (P4) | **S11** — the kill that lands | **the product**, inside S11 | 3 |
| `shepherd_r5b` | env-plan §4 step 5 | S-own-2 (P1) | **S14**, **S15** — the terminal WebSocket | teardown step 5 | 4 |
| `shepherd_r5c` | env-plan §4 step 5 | S-own-4 (P7) | **S17** — the stale handle | **the fixture**, inside S17, *before* the delete | 4 |
| `shepherd_r5d` | env-plan §4 step 5 | S-own-3 (P6) | **S13** — `orphan` | teardown step 5 (S13 orphans the session; it does not kill the pane) | 3 |
| `shepherd_r5z` | env-plan §4 step 10 | none | **§3c**, the fixture-side kill control | the fixture, immediately, as the control's own assertion | bring-up |

**No pane is shared by two scenarios, and no owned session is seeded without one.** A scenario
that needs a pane it does not own is `BLOCKED`, not improvised. Every invocation carries
`-L shepherd-qa` as `argv[1]`; no name contains `:`; the `shepherd` socket is never named.

### 3c. Fixture-side controls — the product is not the only thing that can be wrong

S11 is the first kill this project has ever driven against a real pane. If it goes red, `r1` gave
the executor no way to tell **"the shipped kill is broken"** from **"the handle we seeded was
wrong"** — and the second is far likelier on ground this new. These three controls run at bring-up
step 10, **before** S0, and they use no product code on the path under test:

| Control | What it does | What a red one means |
| --------- | -------------- | ---------------------- |
| **Pane-kill mechanics** | The fixture creates `shepherd_r5z`, asserts it is listed, runs `tmux -L shepherd-qa kill-session -t '=shepherd_r5z:'`, and asserts it is **no longer listed** | tmux, the socket, or the fixture's own argv is wrong. **Every kill scenario is `BLOCKED`** — S11's red would have been unreadable |
| **Handle round-trip** | For each seeded owned session: `Store.set_runner_handle(...)` then read it back through the same store handle and assert the parsed form is `local\|shepherd-qa\|shepherd_r5<x>` — the three-field form `core/runner.py:23,64-79` defines and `runner/local.py:97` consumes | The seed did not land. `killable` would be empty for a reason that has nothing to do with the projection, and S0 would bind **B-EMPTY** off a fixture bug |
| **Socket knob** | `Store.get_app_state("runner_socket") == "shepherd-qa"`, read back **after** `controld.start` | The composed runner is pointed somewhere else. Every kill would answer a `RunnerRefusal` naming another socket |

The seeded handle form was re-verified against the tree during this amendment and is correct as
written; these controls exist so that a *future* red is attributable, not because the form is in
doubt.

### 3d. "Hit-testable", and the pane floor — one definition, read by reference

`r1` said *"hit-testable"* in S19 and S25 and plain *"clickable"* in S22, S23 and S24, where it
degraded to **"present in the DOM"**. It also accepted any **non-zero** box as a healthy pane,
which a 1 px collapse satisfies. Both are defined once here and referenced by id everywhere else.

**`HIT_TESTABLE(el)`** — all four, measured in one layout pass:

1. `el.getBoundingClientRect()` has `width > 0` **and** `height > 0`;
2. `document.elementFromPoint(cx, cy)` at the box's centre resolves to `el` or to a descendant of `el` — nothing is painted over it;
3. `getComputedStyle(el).pointerEvents !== "none"` and `el.disabled !== true`;
4. the box is **wholly inside the viewport** — `top >= -SLACK_PX`, `bottom <= viewportHeight + SLACK_PX`, and the same for `left`/`right`.

**`PANE_HEALTHY(pane)`** — both:

1. `pane` **wholly contains the box of at least one `HIT_TESTABLE` descendant** — not merely "has one inside the subtree". A pane collapsed to 1 px cannot contain a 32 px control's box, which is precisely the failure *"non-zero"* let through;
2. the page **root** that owns the pane satisfies `render_check.py`'s own fill rule: `bottom >= viewportHeight * FILL_FLOOR`, with `FILL_FLOOR = 0.75` read from `tools/render_check.py:87` — **never re-spelled as `0.75` in harness code**.

**`ROUND5_WIDTHS`** — the nine boundary widths of §2, defined **once** in the round-5 harness
package and read by reference by S21, S22, S23 and S24. `render_check.VIEWPORTS` holds three of
them and is read by reference by S30. Neither list is re-spelled in a scenario file: that
re-spelling is exactly the drift C-8 names as the thing that hid D1, and in `r1` this plan's own
scenarios reproduced it while §7 claimed they did not.

**`r3` — what "read by reference" binds, and what it does not.** The rule is about **harness
code**: no `.py` file under the round-5 package may contain a width literal; every width arrives
from `ROUND5_WIDTHS` (or, for S30 alone, from `render_check.VIEWPORTS`). It is **not** about this
document — §2, §3d, §12 and each scenario's `Preconditions` line print the numbers because a reader
cannot follow the plan otherwise, and a plan is read, not executed. **`r2`'s by-reference claim was
one member too wide:** it named S21–S24 while **S22's `Preconditions` hard-coded `1280x900`** with
no reference to the constant at all, reproducing in the fix the exact defect the fix is for. S22 is
corrected below. Coverage was never wrong — the width was driven — but a restated constant is this
tree's signature defect and the C-8 repair turns on there being **one definition site**.

---

## 4. Scenarios

### S0 — environment-truth probe

Two authority documents describe the same record differently. `t9-1.md` gap 2 says the delete plan *"does not say which sessions are killable, so the page cannot warn in advance"*; `qa-remfix.md:42` says *"the server sends `killable: []` / `unkillable: [ids]` — it already knows"*. The entire delete-dialog family — five choices, one of them disabled up front — rests on the answer, so it is settled empirically and **first**, not by picking the likelier document.

**Tier:** e2e_backend · **Class:** edge-case · **Covers:** C-6; the delete-dialog choice group, all five rows
**Preconditions:** as §1, plus: the §3a rig attached **and proved live at bring-up step 10**; the three §3c fixture-side controls green; tmux pane `shepherd_r5a` live; P4 seeded with S-own-1 (owned, handle over `shepherd_r5a`), S-att-1 (attached, no handle), S-fin-1..3 (finished)
**Given:** P4 has exactly two sessions with `ended_at IS NULL` — one with a `runner_handle`, one without — and three finished ones
**When:** `POST /api/projects/{P4}/delete` with body `{}` (no `on_running`, so the handler's default-refuse applies)

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | 200; `data.deleted == false`; `data.refused` is a non-empty string; the response **contains the keys** `running`, `killable`, `unkillable`, `doomed`, `kill_failures` |
| **Binding** | `KILLABLE := data.killable`, `UNKILLABLE := data.unkillable`, `DOOMED := data.doomed`, `RUNNING := data.running`. Recorded verbatim in the run report, with the four lists printed |
| DB | P4 **still exists**; both live sessions still have `ended_at IS NULL`; no `anomaly.stop_failed` increment |
| Queue | **zero frames** on client B between the last rig control and this scenario's own control — a refusal announces nothing — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S0`, created and deleted after the refusal). §0 rule 4: without the control this row asserts nothing, and in `r1` it was asserted at a point in bring-up where **no SSE client had been attached at all** |
| UI | not driven here (S9 renders it) |
| Logs | one audit JSONL record for `delete_project` with `decision == "allow"`, `approved_by == "claimed_human"` |

**The expected binding is B-OWNED, and `r1`'s four-branch gate was wrong about its own tree.** C-6
was resolvable by reading two lines, and the `code` lane never opened `store/reads.py`:

- `store/reads.py:283-284` — `killable = tuple(s.id for s in alive if s.runner_handle is not None)`, `unkillable` the complement. With S-own-1 holding a handle and S-att-1 holding none, `KILLABLE == [S-own-1]` and `UNKILLABLE == [S-att-1]` **follow from the seed**.
- `toolsurface/tools_projects_delete.py:128-136` — `"doomed"`, `"killable"` and `"unkillable"` are emitted **unconditionally** (`list(plan.doomed) if plan is not None else []`); the keys are always written, and `running`/`kill_failures` likewise.

So `qa-remfix.md:42` is right and `t9-1.md` gap 2 is wrong, and **S0 is a measurement that confirms
a reading, not a gate that chooses between four live possibilities.** It stays first, and it stays
a measurement — the projection is what five scenarios consume, and reading it once beats inferring
it four times — but the branch table is restated at its real weights:

| Binding | Reachable? | If it arrives |
| --------- | ------------ | --------------- |
| **B-OWNED** — `KILLABLE == [S-own-1]`, `UNKILLABLE == [S-att-1]` | **yes — the expected one** | S9–S13 run as written. Record the four lists verbatim |
| **B-EMPTY** — `KILLABLE == []`, `RUNNING` non-empty | only two ways | With §3c's handle control **green**, the store round-tripped a handle the projection then lost: a **product finding, HIGH**. With it **red**, the seed never landed: `BLOCKED` (§0 rule 5). S10 collapses to case (b); S11 has nothing to drive |
| **B-ALL** — `KILLABLE == RUNNING` | **no** — it would require `reads.py:283-284` to ignore `runner_handle`, with S-att-1 seeded without one | If it somehow arrives, the plan's reading of the store is wrong: stop, re-read, and report the departure as the finding. **`r1` carried a whole S10 re-scoping rule for this branch that contradicted S10's own text** — both are gone |
| **B-ABSENT** — a key missing | **no** — the three keys are unconditional at `tools_projects_delete.py:128-136` | Same as B-ALL: the plan's reading is wrong, not the product's behaviour "discovered". Stop and re-read |

**The gate moved to where the evidence actually is.** Wave 1's real premise is not *"does the
projection carry four keys"* — that is provable by reading. It is *"can a kill land on a real
pane at all"*, which nothing in four rounds has executed. That premise is now proved **before**
S0 by §3c's fixture-side pane-kill control, and the product half of it is S11.

**Cleanup:** delete `LIVENESS-S0`. The refusal itself changed nothing; P4 is left intact for S9–S13.

---

### S1 — the shell is served, all six roots mount, nothing errors

**Tier:** ui · **Class:** happy-path · **Covers:** six nav entries; `next_actions` live + inert representative; decision-card inertness as an absence
**Preconditions:** as §1 · **Given:** the seeded world, chromium at 1280x900
**When:** navigate to `/`, then click each of the six nav entries in turn, then return to Flock and drill Flock → project → card → session pane → back → back

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | exactly one `[id^="page-"]` is visible at arrival **and after every nav click**; `aria-current` follows the active nav entry; `data-level` unwinds to its arrival value after the two backs; Queues and Kanban render their "not built this milestone" stub with no module error; one `next_actions` entry of each live kind (`inspect`, `external`-with-target, `none`) renders, and one inert kind carries the `not yet` badge; a decision-card choice click changes nothing and navigates nowhere |
| API | every request 200; every response carries `X-Content-Type-Options: nosniff` |
| DB | unchanged — this scenario writes nothing |
| Queue | not asserted |
| Logs | **`console.error` and `pageerror`: zero, over the whole scenario.** Listeners registered before the first navigation |

**Cleanup:** close the page.

---

### S2 — the reads reflect an `n > 1` world, and `unassigned` is reserved

**Tier:** integration · **Class:** happy-path · **Covers:** project-row classes **including the empty class** (`r2`: §2's empty class named S29, which asserts nothing about an empty list); date classes (null, far-past, `<60 s`) at the API seam; `#proj-edit`/`#proj-delete` absence on `unassigned`
**Preconditions:** as §1 · **Given:** P0–P7 seeded, two of them sharing the name "Shepherd"
**When:** `GET /api/projects`, then `GET /api/projects/{id}` and `GET /api/projects/{id}/repos` for each

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | **eight** workspaces (P0–P7); `unassigned` present with its reserved marker; **two distinct ids share the name "Shepherd"**; P1 reports `repo_count == 2` and P3 `repo_count == 1` **on the read path**; `last_activity_at` is **derived at read time** and is non-null for projects with sessions (C-7 — never assert the column) |
| DB | `workspace`, `repo` and `workspace_repo` rows match the seed exactly; the `workspace_repo` edge for P3 names R2's long path |
| UI | `#proj-list` shows **eight** rows; the `unassigned` row has **no** `#proj-edit` and **no** `#proj-delete` child — asserted as **absence**, not as `disabled`; **the empty class:** selecting P2 (zero repos, zero sessions) renders the module's own empty sentence in `#proj-detail` — a rendered sentence, not a blank pane and not a spinner |
| Queue | not asserted |
| Logs | one audit record per gated read, `approved_by == "policy"` |

**Known contrast, asserted deliberately:** the **write** verbs answer `repo_count=0, last_activity_at=None` unconditionally (X3). S6 asserts that divergence at the write seam; S2 asserts the read seam is right. Neither is re-proved by the other.

**Cleanup:** none.

---

### S3 — the stream opens, and a second client is real

**Tier:** e2e_backend · **Class:** happy-path · **Covers:** the rig's **contract**, at the scenario seam
**Preconditions:** as §1; clients A and B attached and proved live at bring-up step 10 (§3a) · **Given:** `controld` up, the rig attached
**When:** drive one known-good mutation (`POST /api/projects` creating a throwaway project `S3-probe`) and read both sockets raw; **and**, as a negative control on the same surface, issue one `GET /api/events` carrying a **wrong `Origin`**

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | both streams answer 200 with `Content-Type: text/event-stream`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`. **The wrong-`Origin` stream is refused 403** with the `GENERIC_ERROR` envelope and **no stream body** — `server.py` runs the origin check on the stream *"rather than only on mutations"*, and `r1` drove that check on the WebSocket alone (S14) |
| Queue | both clients receive the `project.created` frame within 10 s; each frame carries `id: <seq>` and **no `event:` name**; the `: open` comment arrived before it and is skipped as a comment, so "no frame" stays distinguishable from "socket alive" |
| DB | one new workspace row |
| UI | `#stream-status` is `live` on a browser tab opened after the stream (asserted in S18; here the clients are raw readers) |
| Logs | one audit record for `create_project` |

**`r2`: this scenario no longer *is* the rig.** In `r1` it attached the clients, and everything
that counted frames before it — S0, at bring-up step 10 — was counting against nothing. The rig is
attached and first proved live at env-plan step 10 and owned by the session fixture until teardown
(§3a). S3 asserts its **contract**: the headers, the `id: <seq>`, the absent `event:` name, the
`: open` comment, and the origin refusal. If B never receives this frame, no later "zero frames"
assertion means anything — which is why every such scenario now carries its own control too.

**Cleanup:** delete `S3-probe` via `POST /api/projects/{id}/delete` (it has no sessions). **The clients stay attached because the fixture owns them, not because S3 left them.**

---

### S4 — all six project mutations reach a second live client

**Tier:** e2e_backend · **Class:** happy-path · **Covers:** C-2; PP-1
**Preconditions:** as §1; clients A and B attached and proved live at bring-up step 10 (§3a), re-proved at the start of wave 2
**Given:** a fresh project `S4-target` created through the front door, plus R1 on disk
**When:** drive the six mutations in order — `create_project`, `rename_project`, `set_project_description`, `add_repo`, `remove_repo`, `delete_project` — each as one POST

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | six 200s; each record's own positive key is `true` (`created`/`renamed`/`described`/`added`/`removed`/`deleted`) |
| Queue | **six frames at the second client**, kinds exactly `project.created`, `project.renamed`, `project.described`, `project.repo_added`, `project.repo_removed`, `project.deleted`, in that order; each envelope carries `project_id` **promoted to the top level**, not buried in the payload; `id:` strictly increasing across all six |
| DB | the six mutations landed: rows created, renamed, described, edge added, edge removed, workspace gone |
| UI | not driven here (S18 drives it at a real tab) |
| Logs | six audit records, one per gated invoke, `approved_by == "claimed_human"` for the destructive one |

**Note for the executor:** `remove_repo` returns `{"removed": bool}` with **no `refused` key** (X2), breaking the family's stated one-refusal-shape rule. Assert the actual shape; do not normalise it. The divergence is a recorded defect already routed to a DEBUG offer — reporting it as a *new* finding would double-count it.

**Cleanup:** none — the scenario ends with its own project deleted.

---

### S5 — a refusal reaches no client

**Rewritten in `r3` (F1 of pass 2's blocking set is F2 here).** `r2` drove
`POST /api/projects {"name": "Shepherd"}` and expected a refusal. **That call cannot refuse.**
`create_project` returns `{"created": True, "project": …, "refused": None}` **unconditionally**
(`toolsurface/tools_projects.py:158-169`) over `store.create_project`, which is a bare
`INSERT INTO workspace` with no name check at all (`store/projects.py:52-70`) — identity is
`workspace.id`, never the name (E1/D57). **Duplicate-name handling is a client-side warning, not a
refusal**, and `projects.js:615-627` says so in terms: *"a real intent the store supports on
purpose (E1: keyed by id, never by name), so this is a **warning and not a refusal**"*, with the
arming flag held in page memory at `:620` and `:665-669`. The call would have succeeded, announced
a `project.created` frame, and failed **both** of S5's assertions — a **fabricated defect** on the
one scenario whose whole job is proving a negative, and one that §0 rule 5's measurement list did
not cover. The page-side warn/re-arm chain is **S33 (c)**, where it belongs; S5 now drives a
refusal the wire really produces.

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** C-2's negative half; PP-2; the **reserved-project refusal on the wire** — a path no scenario drove
**Preconditions:** as §1; the §3a rig attached · **Given:** P0, the reserved `unassigned` workspace seeded by migration 004 (`store/models.py:59` — `UNASSIGNED_PROJECT_ID = "unassigned"`)
**When:** `POST /api/projects/unassigned/rename` with `{"name": "Renamed"}`; **then**, last in the body, the §3a in-scenario control (`LIVENESS-S5`)

**Why this refusal and not another.** It is unconditional in the tree, it needs no fixture beyond
the migration's own seed, it is reached through a **declared** body field so nothing about it
depends on `routes.py`'s dropping rule (which is S34's subject), and it destroys nothing — S5 can
therefore run in any wave order. `store.rename_project` calls `_refuse_reserved(workspace_id,
"renamed")` (`store/projects.py:92`), which raises `StoreError` for `UNASSIGNED_PROJECT_ID`
(`:73-80`); `tools_projects.rename_project` catches it and returns `_refused("renamed", …)`
(`:176-181`), i.e. `{"renamed": False, "project": None, "refused": "<sentence>"}`. `announce()`
publishes **iff** the record's own positive key is True (`tools_projects_events.py:79-86`), so
`renamed == False` publishes nothing. **That is the negative, and it is provable rather than
hoped for.**

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | **200**, not an HTTP error; `renamed == false`; `project` is `null`; `refused` is a non-empty string naming the reserved project and its reason (`store/projects.py:74-80`, quoted from source, never re-spelled in the harness) |
| Queue | **zero frames** in the counted window — a refusal announces nothing — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S5`). §0 rule 4: the control is what makes the zero meaningful; without it a dead socket passes |
| DB | `unassigned` still has its original name; **no** workspace row was added, renamed or removed by the refused call; the control's row is net zero (§3a footprint rule) |
| UI | not driven here — S2 asserts Edit/Delete are **absent** on `unassigned`, and S9 renders `#p-refusal` |
| Logs | **one** audit record for the refused invoke, counted before the control runs (§3a footprint rule) — a refusal is still a gated call |

**Cleanup:** none beyond the control — S5 changes nothing. Delete `LIVENESS-S5`.

---

### S6 — `set_project_description`, including "absent clears"

**Tier:** integration · **Class:** edge-case · **Covers:** C-5 / the eighth verb; the X3 divergence at the write seam
**Preconditions:** as §1 · **Given:** P1 with two repos and a non-null description
**When:** (a) `POST /api/projects/{P1}/description` with `{"description": "a new one"}`; (b) the same route with `{}` — the field absent

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | (a) `described == true`, the record echoes the new text; (b) `described == true` and the description is **cleared** — an absent field forwards nothing and the handler reads the absence as `None`. In **both**, the record answers `repo_count == 0` and `last_activity_at == null` **unconditionally**, while P1 has two repos (X3) |
| DB | `workspace.description` is the new text, then NULL; the two `workspace_repo` edges are untouched by either call |
| Queue | one `project.described` frame per successful call — two in total |
| UI | `#p-desc-note` reflects the cleared state after a reload |
| Logs | two audit records |

**Cleanup:** restore P1's description through the same route.

---

### S7 — the envelope and the frame have the shape the spec fixes

**Tier:** e2e_backend · **Class:** edge-case · **Covers:** legs 6 and 7 of the pipeline — described by one lane only, so assertions here carry less prior confidence and are worth measuring
**Preconditions:** as §1; the §3a rig attached · **Given:** a session in P1 and a fresh project
**When:** drive one `project.*` mutation and one `session.*`-bearing event, and read both envelopes raw off the socket

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| Queue | `session_id` and `project_id` are **promoted out of the payload** to the envelope's top level; the remaining payload is JSON-whitelisted (no non-JSON type survives); the frame is `id: <seq>` with **no `event:` line**, so a client with a single `message` listener still receives an unknown type |
| API | not asserted beyond the 200 |
| DB | not asserted |
| UI | not asserted |
| Logs | not asserted |

**Cleanup:** delete the fresh project.

---

### S8 — a client behind the ring is told, not silently short-changed

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** `stream.gap`; PP-8's loss half
**Preconditions:** as §1 · **Given:** a client that has recorded a `seq`, then detached
**When:** drive enough mutations to push the ring past that `seq`, then reattach with `Last-Event-ID: <stale seq>`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| Queue | a `stream.gap` notice reaches the reattached client **before** any replayed frame; subsequent `id:` values are strictly increasing from the resume point; no frame is delivered twice |
| API | 200 on the reattach |
| DB | unchanged by the reattach |
| UI | `#stream-status` would read `reconnecting` then `live` (asserted at the browser in S18, not here) |
| Logs | not asserted |

**Known window, declared:** `sse.py:124-128` records an **unclosed** tail-subscription window — a subscriber can miss an event published in the instant between subscriptions (BLOCKER T15-1). A single missed frame in this scenario is therefore `BLOCKED`/`retry once`, not an automatic product `FAIL`; a *systematic* miss is a finding.

**Cleanup:** close the client.

---

### S9 — the refusal record is rendered, and the page does not re-derive it

**Tier:** ui · **Class:** happy-path · **Covers:** the delete dialog's identity/doomed/live panels; GAP 1; **the `Wait` and `Cancel` choices, which are two distinct controls and which `r1` drove with nothing**
**Preconditions:** S0 bound — **and therefore tmux-dependent, transitively** (`r3`). S9's UI row compares `#dlg-delete-doomed` against `len(DOOMED)` **from S0's binding**, and §2 says *"until S0 returns, none of these five is interpretable"*. S0 needs pane `shepherd_r5a` to have an owned session at all, so a tmux-less run leaves S9 with nothing to compare against: **S9 is `BLOCKED`, not merely degraded.** env-plan §11's tmux row is re-derived from this dependency rather than patched.
**Given:** P4 as S0 left it, chromium at 1280x900
**When:** Projects → the P4 row → `#proj-delete` → read the dialog without pressing any choice; then press **`Wait — keep the project`** (the `choice("cancel", …)` button inside `#dlg-delete-choices`) and re-open; then press **`#dlg-delete-cancel`**

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | `#dlg-delete-identity` names P4 by name **and** id; `#dlg-delete-doomed` shows a count equal to `len(DOOMED)` from S0's binding — **the server's own number**; `#dlg-delete-live` lists `len(RUNNING)` sessions; `#dlg-delete-choices` holds all five choices; `#p-refusal` is present and, at this point, empty and hidden. **`Wait` closes the dialog and writes nothing** — `#dlg-delete.open` is false, the project still exists, zero POSTs fired by the press; **`#dlg-delete-cancel` does the same from the other control.** They are two nodes with two handlers and §2's enumeration counts them as two |
| API | exactly one POST fired by opening the dialog, or none — assert which, and assert it is not two |
| DB | unchanged |
| Queue | zero frames in the counted window — opening a dialog is not a mutation, and neither is `Wait` or `Cancel` — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S9`). §0 rule 4 |
| Logs | zero `console.error`/`pageerror` |

**The point of the doomed assertion:** `DeletePlan.doomed` is projected on refusals precisely so the dialog can say what the delete will take *before* the button. If the rendered count is right but the page computed it from a second read, that is GAP 1 — a copy of a store derivation. Assert the number **and** that no second list-sessions request was issued to produce it.

**Cleanup:** the two presses above *are* the cleanup; assert the dialog closed both times and nothing was written. Delete `LIVENESS-S9`.

---

### S10 — "Stop them, then delete" is disabled exactly when it cannot work

**Tier:** ui · **Class:** edge-case · **Covers:** the disabled-up-front choice; PP-3
**Preconditions:** S0 bound **B-OWNED**. **If S0 bound B-EMPTY, this scenario collapses to case (b) alone and the run report says so.**
**Given:** two projects — **P4** (`KILLABLE == [S-own-1]`, non-empty) and **P5**, seeded with **only attached** running sessions (S-att-5, S-att-6) and **no owned session**
**When:** open the delete dialog on each

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | (a) on P4: the `kill_sessions` choice is **enabled**; (b) on **P5**: it is **disabled**, and the disabled state is visible before any click — not discovered by clicking. In both, the disabled/enabled state matches `answer.killable.length === 0` exactly (`projects.js`: the fifth argument to `choice(...)`) |
| API | the dialog's own POST(s) only; no delete is issued |
| DB | unchanged in both |
| Queue | zero frames in the counted window — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S10`). §0 rule 4 |
| Logs | zero `console.error`/`pageerror` |

**`r2`, two fixes.** (a) **P5 did not exist in `r1`.** The seed table provisioned running sessions only in P4 and spread S-att-2..4 *"over P1 and P3"*, so *"a second project seeded with only attached running sessions"* named nothing — case (b) was unprovisioned, and so was the whole of S12. P5 is provisioned by env-plan §5. (b) `r1`'s S0 carried a **B-ALL** re-scoping rule that contradicted this scenario's own text; B-ALL is unreachable (S0) and the rule is gone.

**Cleanup:** Cancel both dialogs; delete `LIVENESS-S10`.

---

### S11 — a kill that lands on a real pane

**Tier:** e2e_backend · **Class:** happy-path · **Covers:** PP-3, PP-4; the never-driven `kill_for_delete → kill_session_now → record_and_terminate` chain
**Preconditions:** S0 bound **B-OWNED** (B-ALL is unreachable — S0); tmux available; the §3c pane-kill and handle round-trip controls **green**; `app_state["runner_socket"] == "shepherd-qa"` verified
**Given:** P4 with S-own-1 owned over the **live** pane `shepherd_r5a`, S-att-1 attached, S-fin-1..3 finished. **Pre-assertion: `tmux -L shepherd-qa list-sessions -F '#{session_name}'` contains `shepherd_r5a`.**
**When:** `POST /api/projects/{P4}/delete` with `{"on_running": "kill_sessions"}`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | 200. `killed` contains S-own-1; `kill_failures` contains S-att-1 with a reason naming `no_pane`; `deleted` is **false** and `refused` names the surviving session — because `commit_project_delete` re-derives and refuses while a live session remains. **`deleted` is one of §5's `I` rows**: if it arrives `true`, that is a **measurement** and the finding is the plan's reading of `commit_project_delete`, not a product `FAIL` (§0 rule 5) |
| **tmux** | `tmux -L shepherd-qa list-sessions -F '#{session_name}'` **no longer lists `shepherd_r5a`** — `-L` explicit, the `shepherd` socket never named |
| DB | S-own-1 has `ended_at` set; S-att-1 does not; P4's fate matches the API's `deleted` value exactly; `anomaly.stop_failed` incremented by exactly the number of `kill_failures` |
| Queue | a `project.deleted` frame **iff** `deleted == true`, and none otherwise — the announce gate, tested against a partial outcome. **A conditional zero is still a zero:** the window closes with the in-scenario control (`LIVENESS-S11`) and exactly two control frames — `project.created` then `project.deleted`, in that order, the second closing the window (§3a), or the row is `BLOCKED` (§0 rule 4) |
| UI | not driven here (S9/S10 cover the dialog) |
| Logs | one audit record for `delete_project`, `approved_by == "claimed_human"` |

**How a red S11 is classified — decided here, not at run time (§0 rule 5).** This is the chain no
round has executed. With §3c's pane-kill control and handle round-trip **green**, a red S11 is a
product `FAIL`. With either **red**, it is `BLOCKED`: the seed, not the shipped kill, is what the
run learned about. Without those controls — `r1`'s position — the two are indistinguishable, and
the executor was left to decide at run time on the single riskiest chain in the plan.

**Cleanup:** delete `LIVENESS-S11`. The pane is gone by design; the fixture must not attempt to kill it again (a second `kill-session` on a missing pane is tolerated — rc≠0 is normal after `kill-session`, which removes the row and its exit status with it), and teardown step 5 tolerates "session not found" for exactly this reason.

---

### S12 — a kill that cannot land says why

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** GAP 2; run-2 d1's `kill_failures` reader; PP-3
**Preconditions:** S0 bound; tmux available
**Given:** **P5** — seeded with **only attached** running sessions S-att-5 and S-att-6, no `runner_handle` on either, **no owned session**. (`r1` said *"a project seeded with only attached running sessions"* and the seed table provisioned none: S12's entire subject was unprovisioned.) P5 needs **no pane**, so this scenario survives a tmux-less run except for its dependence on S0
**When:** `POST /api/projects/{id}/delete` with `{"on_running": "kill_sessions"}`, then open the dialog in the browser and read the refusal

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | `deleted == false`; `killed == []`; `kill_failures` names every attached session with a reason; `refused` is a non-empty string |
| UI | `#dlg-delete-live` renders *what was not stopped, and why*, naming the session id and the reason — the reader added for run-2 d1 |
| DB | the project is **kept**; no session's `ended_at` changed; `anomaly.stop_failed` incremented by the number of failures |
| Queue | **zero frames** in the counted window — a refusal announces nothing — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S12`). §0 rule 4 |
| Logs | one audit record |

**Cleanup:** Cancel; delete `LIVENESS-S12`. **P5 survives** — S10 case (b) reads it and must not find it deleted, which is why this scenario runs after S10 in the fixed wave-3 order.

---

### S13 — `orphan` moves the living and destroys the dead

**Tier:** integration · **Class:** edge-case · **Covers:** the third dialog choice; `severed`/`destroyed`
**Preconditions:** S0 bound; tmux available · **Given:** **P6**, seeded for this scenario alone: S-own-3 (owned, handle over **`shepherd_r5d`** — its own pane, §3b), S-att-7 (attached), S-fin-4..6 (finished). (`r1` said *"a fresh project with 1 owned + 1 attached"* while **every pane was spoken for** — `r5a` destroyed by S11 in the same wave, `r5b` reserved for wave 4, `r5c` consumed by S17 — so S13's owned session had no pane, which §0 rule 3 says must be labelled rather than assumed.)
**When:** `POST /api/projects/{id}/delete` with `{"on_running": "orphan"}`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | `deleted == true`; `orphaned` names both running sessions; `destroyed` names the three finished ones; `severed` names each nulled lineage link as `{session_id, column}` |
| DB | both running sessions now belong to `unassigned`; the three finished session rows are gone; the workspace row is gone; the `workspace_repo` edges are gone |
| **tmux** | **`shepherd_r5d` is still listed.** `orphan` moves the row; it does not touch the pane — and a pane that vanished here would mean the orphan path is killing what it promised to keep |
| UI | after a reload, the Flock still shows the two orphaned sessions, now under Unassigned |
| Queue | exactly one `project.deleted` frame |
| Logs | one audit record |

**Cleanup:** none — the scenario consumed its own project. `shepherd_r5d` survives to teardown step 5. The two orphans stay under `unassigned` and later scenarios must not assume Unassigned is empty.

---

### S14 — the terminal WebSocket, against a real owned pane

**Tier:** e2e_backend · **Class:** happy-path · **Covers:** PP-5; `/api/sessions/{id}/terminal`; ground never opened in four rounds
**Preconditions:** tmux available; S-own-2 owned over the live pane `shepherd_r5b` in P1 (**not** P4 — S11 destroyed that pane)
**Given:** the pane has written some known bytes (the fixture sends a deterministic string through `send-keys` before the run, or leaves the pane at its start banner — either way the harness reads the pane's own `capture-pane` bytes for comparison)
**When:** open `ws://127.0.0.1:{port}/api/sessions/{S-own-2}/terminal` with a valid `Origin` and a valid handshake

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | HTTP **101** accepted; the first **binary** frame equals the pane snapshot **byte-for-byte** — no decode, no escape, no re-encode; the connection closes with `CLOSE_NORMAL` |
| **tmux** | the pane is still listed after the stream closes — reading a pane does not end it |
| DB | unchanged |
| Queue | not asserted |
| UI | not asserted here (S15 drives the browser side) |
| Logs | one audit record for `terminal_stream` |

**Negative control in the same scenario:** a connection with a **wrong `Origin`** is refused **403 before a byte of the connection is handed over** — the order is the security property, and a 101 written before `invoke()` answered would leave a browser holding an upgraded socket to a session it may not have.

**Cleanup:** close the socket; leave the pane.

---

### S15 — the emulator is fitted to the real pane

**Tier:** ui · **Class:** edge-case · **Covers:** D6's ground, measured against a live pane rather than a frozen capture
**Preconditions:** S14 passed (the socket works) · **Given:** the browser on the session pane for S-own-2, at 1280x900 and again at 390x844
**When:** open the session pane and let the terminal fit

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | `#session-terminal` carries `data-terminal-cols` and `data-terminal-rows`; both are >0 at both viewports; the values **change** between the two viewports (a geometry that does not respond to a 3× width change was never fitted); the rendered terminal box is inside the **viewport** at both, within `SLACK_PX` |
| API | the WS connection reaches 101 from the browser as well as from the raw client |
| **tmux** | the pane's own `#{pane_width}`/`#{pane_height}`, read with `-L shepherd-qa`, are **still the fixture's `-x 160 -y 45` at both viewports**, and the page's reported `data-terminal-cols`/`data-terminal-rows` **differ from them at at least one of the two** — `terminal_resize` is a registered tool with **no route**, so the page *cannot* push geometry back and the two must diverge. **`r2`:** `r1` wrote this row as *"consistent … or the difference is recorded as the finding"*, which is a probe wearing an assertion's clothes — it cannot fail. Stated as an expected **inequality** it can: if the pane's geometry tracked the page, the "no route" reading would be wrong |
| DB | unchanged |
| Logs | zero `console.error`/`pageerror` |

**Cleanup:** navigate away; assert the socket closed.

---

### S16 — an attached session has no pane, and the page says so

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** the `no_pane` branch
**Preconditions (`r3`, F3): §1 EXCEPT its tmux-pane row — S16 is the one scenario in this plan that needs no pane and no tmux server.** `terminal_stream` returns `no_pane(session_id)` from `handle_for` alone (`toolsurface/tools_terminal.py:228-237`); a session with no `runner_handle` never reaches `runner.snapshot` or `runner.attach`, so nothing in this path speaks to tmux, and `server.py:296-308` turns the non-`TerminalStream` result into the 404. Everything else in §1 is inherited as written. `r2` wrote `Preconditions: as §1`, which inherited *"tmux panes `shepherd_r5a`…`shepherd_r5d` live"* and contradicted env-plan §11's own correction — **the half-propagated correction pass 2 was convened to catch.**
**Given:** S-att-2, attached, no `runner_handle`
**When:** open the terminal WebSocket for it, and separately open its session pane in the browser

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | **404** after a valid handshake — the capability refused, and no 101 was written |
| UI | the session pane renders a sentence explaining there is no pane, **not** a blank terminal and not a spinner |
| DB | unchanged |
| Queue | not asserted |
| Logs | one audit record; zero `console.error`/`pageerror` |

**Cleanup:** none.

---

### S17 — a stale handle: the pane vanished between plan and kill

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** PP-4's negative half; the orphan case Shepherd exists to notice
**Tier note:** S17 is also **PP-3's breaker** — a stale handle is in `killable` and cannot be stopped, which falsifies the stronger reading of that property. §2c states the provable form.
**Preconditions:** tmux available · **Given:** **P7** with S-own-4, one **owned** session whose handle points at **`shepherd_r5c`** — a pane created at bring-up step 5 (§3b) and **killed by name by the fixture** (`tmux -L shepherd-qa kill-session -t '=shepherd_r5c:'`) inside this scenario, while the store row still has `ended_at IS NULL`
**When:** `POST /api/projects/{id}/delete` with `{"on_running": "kill_sessions"}`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | `killed == []`; `kill_failures` has one row naming the session id and a reason beginning `RunnerRefusal:`; `deleted` is whatever `commit_project_delete` re-derives — assert the actual value and reconcile it with the DB |
| DB | `anomaly.stop_failed` incremented by exactly 1; the project's fate matches `deleted` |
| Queue | a `project.deleted` frame **iff** `deleted == true`, and none otherwise — **and the window closes with the in-scenario control** (`LIVENESS-S17`) and exactly two control frames — `project.created` then `project.deleted`, in that order, the second closing the window (§3a), or the row is `BLOCKED`. §0 rule 4: a conditional zero needs a control exactly as much as an unconditional one |
| **tmux** | the pane is absent after the fixture's `kill-session` and after the delete — the fixture removed it, the product did not. The fixture's own removal is asserted, not assumed: `shepherd_r5c` **is listed before** and **is not listed after** |
| UI | not driven |
| Logs | one audit record; **no** `GENERIC_ERROR` — an escaping exception here would flatten to a correlation id and tell the page "request failed" for a call that just stopped a live agent. S34 is what proves the envelope exists at all, so this absence is read against a positive |

**Explicitly not tested: a kill that *hangs*.** No timeout was added, so a hanging kill blocks the verb — and driving it means planting a blocking call in executable code, which this workflow forbids outright. Carried as a `deferred` gap in §7.

**Cleanup (`r3` — conditional, because §0 rule 3 forbids asserting a state this scenario measures).**
`r2` wrote *"the scenario consumed its own project (P7)"* as a flat fact while its own API row says
`deleted` is *"whatever `commit_project_delete` re-derives"* and its DB row says *"the project's
fate matches `deleted`"*. Those cannot both be true. Cleanup therefore branches on the **measured**
value and the run report records which branch ran:

- `deleted == true` → P7 is gone; nothing to clean.
- `deleted == false` → **P7 survives**, with S-own-4 still `ended_at IS NULL` and a `kill_failures`
  row against it. The fixture deletes nothing and leaves it: no later scenario reads P7, and a
  fixture that "tidied" it would be writing past the product's own refusal.

Either way: delete `LIVENESS-S17`. The pane `shepherd_r5c` is gone — the **fixture** removed it
inside the scenario, and teardown step 5 tolerates "session not found" for exactly that reason.

---

### S18 — two live browser tabs

**Tier:** ui · **Class:** happy-path · **Covers:** C-2 at the real client; PP-1; the two-tab driver that has never been committed
**Preconditions:** chromium available; wave 2 passed · **Given:** two tabs on the same chromium, both on the Projects page, both showing the same list
**When:** in tab A, create a project, then rename it; do nothing in tab B

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI (tab B) | the new project appears **with no reload and no user action**; the rename is reflected; `#stream-status` reads `live` throughout; **`refreshAll` runs at most twice per envelope burst — observed at a named seam**: a `page.on("request")` listener registered **before** the first navigation counts tab B's own `GET /api/projects` + `GET /api/projects/{id}` fetches in the burst window, and "at most twice" is *at most two of each per burst*. **`r2`:** `r1` asserted "at most twice" with **no observation point named**, and this plan's own B4 forbids inferring that a module ran from the fact that it was loaded — the same error one level down |
| UI (tab A) | the same, plus the dialog closed on success |
| API | two POSTs total — tab B issues no mutation |
| Queue | two frames, both received by both tabs |
| DB | one workspace row, renamed once |
| Logs | zero `console.error`/`pageerror` **in both tabs** |

**Cleanup:** delete the project; close tab B.

---

### S19 — real touch events on a phone viewport

**Tier:** ui · **Class:** edge-case · **Covers:** touch (every prior phone assertion was a synthesized pointer event); drawer/rail pairwise; `#p-new-path` Enter
**Preconditions:** chromium with `has_touch=True`, `is_mobile=True`, 390x844; **P1 present with ≥1 repo** (the keyboard leg below opens the dialog on it)
**When:** dispatch **real** `touchstart`/`touchend` sequences (playwright `page.touchscreen.tap`, not `element.click()`) on: `#drawer-open`, a nav entry inside the drawer, a Projects row, `#proj-new`, a delete-dialog choice, **and `#collapse` — the rail toggle**; **then, as a separate leg, close the create dialog, tap `#proj-edit` on P1 to re-open `#dlg-project` in EDIT mode**, focus `#p-new-path` and press Enter on a path that does not exist

**`r3` (F4) — the keyboard leg was driven in create mode, where the field is hidden.** `r2` tapped
`#proj-new` and then asserted that Enter on `#p-new-path` *"adds the path and does NOT submit the
form"*. `projects.js:549` hides `#p-paths-section` outside edit mode, and `addDraftPath` returns at
`:586` when `draft.project === null` — so **no POST is issued and nothing is added**; the
"does not submit" half would have passed against a field the user cannot reach, and the "adds the
path" half was unfalsifiable. The leg now opens the dialog the way S32 and S33's edit half do. A
**non-existent** path is used deliberately: the assertion under test is the keydown handler at
`projects.js:480-482` (Enter reaches `addDraftPath` and does **not** submit the form), and a
refused add proves the request was issued without mutating P1's repo set.

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | every tap reaches its handler — the drawer opens, the nav entry navigates, the row selects, the dialog opens, the choice registers; **the rail toggle flips `#shell[data-rail]` between `open` and `collapsed` and the nav stays reachable in both** (`r2`: §2 claimed pairwise over drawer × rail × viewport and no `r1` scenario touched the rail); **in the EDIT-mode dialog, `#p-paths-section` is visible (`hidden === false`), Enter on `#p-new-path` issues exactly one `POST …/{P1}/repos/add` and does NOT submit the form** — `#dlg-project.open` is still true afterwards and the refusal sentence is in `#p-refusal`; the dialog satisfies **`HIT_TESTABLE` (§3d)** — not "non-zero", which a 1 px box satisfies |
| API | one request per action that issues one; **no double-fire** from a tap producing both touch and compatibility-mouse events; **exactly one `…/repos/add` from the Enter press**, answering `added == false` |
| DB | matches the actions taken; **P1's repo set is unchanged** — the Enter leg's path is refused, so it proves the handler fired without mutating anything |
| Queue | **one frame per successful mutation, and the successful mutations are enumerated, not left open**: the taps that mutate nothing (drawer, nav, row select, `#collapse`, the `Wait`/`Cancel` dialog choice) contribute **zero**, and the Enter leg's `…/repos/add` is **refused** and so contributes zero too — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S19`). **`r3`:** `r2` wrote this row as an unenumerated *"one per successful mutation"* and rule 4 listed it nowhere. Under F4 the Enter leg is a **refusal**, so this window is all-zero and needs a control exactly as S9's does — see rule 4's re-derived census |
| Logs | zero `console.error`/`pageerror` |

**Round 3's false probe #1 is guarded against here:** the closed off-canvas drawer sits at `x: -244..0` **by design**; its seven controls are excluded **by name and counted**, never silently, and the drawer is opened before any nav assertion is made.

**Cleanup:** close `#dlg-project` without Save, so P1's repo set is as S19 found it; delete `LIVENESS-S19`; close the context.

---

### S20 — `prefers-reduced-motion: reduce`

**Tier:** ui · **Class:** edge-case · **Covers:** entirely undriven ground
**Preconditions:** chromium context with `reduced_motion="reduce"`, 1280x900 and 390x844
**When:** **first** walk the same route in a **default context** (no preference) and record the box of every element in `CONTROL_SET`; **then** repeat in the reduced-motion context and compare. `CONTROL_SET` is a **named, enumerated list of ids** defined once in the round-5 harness — the six nav entries, `#drawer-open`, `#collapse`, `#legend-info`, `#proj-new`, `#dlg-legend`'s close control, and `#dlg-project`'s primary control — not "every element on the page". Walk all six nav entries; open and close the legend sheet; open and close a Projects dialog, in both passes

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | for **every id in `CONTROL_SET`**: `HIT_TESTABLE` (§3d) holds in the reduced-motion pass wherever it held in the baseline pass; the legend sheet **opens and closes**; dialogs open and close. **`r2`:** `r1` asserted a differential — *"no element is left with a zero-area box that has a non-zero box without the preference"* — with **no baseline pass and no named element set**, so it degraded into either an unbounded assertion over every node in the document or a trivially-true one over an empty set. The baseline pass and the enumerated set are what make it an assertion |
| API | unchanged behaviour |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror` |

**No animation-duration assertion is made.** No source states a motion SLO, and an assertion about duration would be an invented bound (§0 rule 1).

**Cleanup:** close the context.

---

### S21 — forced colors, and RTL

**Tier:** ui · **Class:** edge-case · **Covers:** entirely undriven ground; PP-7
**Preconditions:** chromium context with `forced_colors="active"`; and a second pass with `document.documentElement.dir = "rtl"`; at the three widths `ROUND5_WIDTHS` names for this scenario — **390, 820, 1280, read by reference (§3d), never re-spelled**
**When:** **first** render each of the four live page roots in a **default context** and record `CONTROL_SET`'s boxes (the baseline S20 defines); **then** render them under each mode

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | exactly one `[id^="page-"]` visible per navigation in both modes; **no horizontal overflow beyond `SLACK_PX` measured against the viewport**, never against a parent; for **every id in `CONTROL_SET`**, `HIT_TESTABLE` (§3d) holds in each mode wherever it held in the baseline pass — the same `r2` fix as S20, for the same reason; under RTL, the rail/drawer and the two Projects panes both remain on screen and each pane satisfies **`PANE_HEALTHY` (§3d)** |
| API | unchanged |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror` |

**Cleanup:** reset `dir`; close the context.

---

### S22 — zoom

**Tier:** ui · **Class:** edge-case · **Covers:** undriven ground; PP-7
**Preconditions:** the width `ROUND5_WIDTHS` names for this scenario — **1280x900, read by reference (§3d)** — with `device_scale_factor` and CSS zoom driven to 200%, and a 50% pass. (**`r3`:** `r2` hard-coded `1280x900` here while §3d and §7 both claimed S21–S24 read the constant by reference. S22 was the one member that did not.)
**When:** render the four live pages at each zoom level

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | containment **against the viewport** at both levels; each Projects pane satisfies **`PANE_HEALTHY` (§3d)** — it wholly contains the box of ≥1 `HIT_TESTABLE` control **and** its page root reaches `FILL_FLOOR` of the viewport height; the nav remains reachable. **`r2`:** `r1` said *"non-zero box with ≥1 clickable control"*, which a **1 px-tall pane with a button inside satisfies**, and left "clickable" undefined here while defining it as "hit-testable" in S19 and S25 — so it degraded to "present in the DOM" |
| API | unchanged |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror` |

**B3 is the whole reason this scenario is written against the viewport:** a 307,418 px container passes every "content fits its box" assertion because the box grew to fit the content. At 200% zoom that failure mode is at its most available.

**Cleanup:** reset zoom.

---

### S23 — width extremes: 320 and 1920 and 2560

**Tier:** ui · **Class:** edge-case · **Covers:** PP-7; "nothing above 1280 or below 390 has ever been driven"; ten Settings sections; six nav entries
**Preconditions:** chromium · **When:** render all six page roots and all ten Settings sections at the three widths `ROUND5_WIDTHS` names for this scenario — **320x568, 1920x1080, 2560x1440, read by reference (§3d)**; and at 2560 **toggle `#collapse`** and re-render with `#shell[data-rail]="collapsed"`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | at every width: exactly one `[id^="page-"]` visible; the nav is reachable (directly, or via a drawer that opens); each of the ten Settings sections is selectable and its panel renders ≥1 **`HIT_TESTABLE`** control (§3d); no horizontal overflow beyond `SLACK_PX` against the viewport; **with the rail collapsed at 2560 the nav is still reachable and every page root still satisfies `PANE_HEALTHY`'s fill half** — the rail pair §2 claims and `r1` never drove |
| API | unchanged |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror`; one screenshot per width per page, written under `$SCRATCH/shots/` — **never** into `src/shepherd/web/static/` (B8) |

**Cleanup:** none.

---

### S24 — intra-page collapse, measured at the panes, across the 760/761 boundary

**Tier:** ui · **Class:** edge-case · **Covers:** PP-7; B2; the D1 shape at the seam `render_check.py` is blind to; the long-path ellipsis class
**Preconditions:** chromium · **When:** render Projects and Settings at the four widths `ROUND5_WIDTHS` names for this scenario — **760, 761, 820 and 900, read by reference (§3d)** — the band where D1 lived, including the **inclusive** boundary that round 3's own helper got wrong (it used `width < 760`; the media query is `max-width: 760px`); and at 1280 with `#shell[data-rail]="open"`, the rail-open half of §2's pairwise set

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | at every one of the four widths: `#proj-list` **and** `#proj-detail` each satisfy **`PANE_HEALTHY` (§3d)** — each wholly contains the box of ≥1 `HIT_TESTABLE` control, and the Projects root reaches `FILL_FLOOR` of the viewport height; the same for the Settings nav column and its detail panel; P3's very long repo path is **ellipsised and carries a `title` attribute** holding the full value. **`r2`:** *"non-zero box"* was a one-pixel floor on the property §2c itself names as the one most able to look proven while proving nothing |
| API | unchanged |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror`; four screenshots under `$SCRATCH/shots/` |

**This is a cheap regression on closed ground, deliberately narrow.** D1 is closed at `b1c1eb9` and was re-verified in round 4; the value here is that 761 and 900 were **reasoned from the media query, never measured**, and that the measurement is taken at the **panes**, which is where the blindness was.

**Cleanup:** none.

---

### S25 — phone dialogs are visible and tappable

**Tier:** ui · **Class:** edge-case · **Covers:** D2 regression, cheap; the legend sheet
**Preconditions:** chromium at 390x844 · **When:** open `#dlg-project` and `#dlg-delete` and `#dlg-legend`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | each dialog reports `open: true`, a computed `display` that is not `none`, and **`HIT_TESTABLE` (§3d) on its primary control** — which subsumes "non-zero box", "not painted over" and "not `pointer-events: none`", and is the same definition S19, S22, S23 and S24 now read; Escape closes it and focus returns without re-firing the opener (D3's shape) |
| API | unchanged |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero `console.error`/`pageerror` |

**Cleanup:** close all dialogs.

---

### S26 — the production audit sink, on disk

**Tier:** integration · **Class:** happy-path · **Covers:** PP-6; the autonomy flag ON/OFF/toggled row; ground where prior claims are **reasoned, not measured**
**Preconditions:** as §1; `autonomy_level == 2` · **Given:** the audit directory `$XDG_DATA_HOME/shepherd/logs/<AUDIT_PREFIX>/` (prefix resolved from `shepherd.daemons.plane`, never spelled)
**When:** record the current record count; then `POST /api/autonomy {"level": 3}`, `POST /api/autonomy {"level": 2}`, and one `delete_project` against a project with no sessions

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| **Disk** | **exactly three** new JSONL records **for the three calls under test** — one per gated invoke, no more and no fewer — counted from the mark taken in the `When` to the moment **before** the in-scenario control runs (§3a footprint rule). Each has `at`, `tool`, `decision`, `approved_by`, and arguments in their redacted form. `tool` names the three tools in order. **The control's own two gated invokes append two further records and are asserted separately**; `r2` said "exactly three" over a scenario whose control adds two, which PP-6 — the property this row *is* — would have failed on |
| API | three 200s; `GET /api/autonomy` reads back 2 at the end |
| DB | `app_state["autonomy_level"]` is 2 at the end; the project is gone |
| Queue | one `project.deleted` frame; **zero** for the two autonomy POSTs (they are not project mutations) — **and the window closes with the in-scenario control** (`LIVENESS-S26`) and exactly two control frames — `project.created` then `project.deleted`, in that order, the second closing the window (§3a). §0 rule 4 applies to a mixed window exactly as it does to an all-zero one |
| Logs | the audit file itself is the log; `RotatingJsonlLog.lost` is **0** — a log that silently stopped writing is the failure D25 exists to prevent |

**The measured claim to report either way:** `approved_by` for the destructive call is `claimed_human` at level 2 **and** at level 3, because `policy.TABLE` allows `LOCAL_DESTRUCTIVE` for `Audience.HUMAN` at both. Whatever arrives, print the three records in the run report — this is the first time this sink has been read off disk.

**Cleanup:** delete `LIVENESS-S26` (**`r3`:** `r2` said *"none"* here while the scenario's Queue row already required the control — the one cell-(iii) scenario whose cleanup did not name its own throwaway). The **audit records stay for the report**, including the control's two, which is why the Disk row counts to the mark before the control rather than to the end of the scenario.

---

### S27 — ordering and coalescing under real concurrency

**Tier:** e2e_backend · **Class:** edge-case · **Covers:** PP-1 **and** PP-8 (two independent mutations required — see §2c); "no two-tab, two-writer or SSE-during-mutation race was ever driven"
**Preconditions:** clients A and B attached at bring-up and **re-proved live at the start of wave 6** (§3a) · **Given:** ten throwaway projects to mutate
**When:** two threads issue ten mutations concurrently (five each: renames and description sets), while both clients read

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| Queue | each client receives **exactly ten** frames; `id:` is **strictly increasing** at each client; the two clients' frame **sets** are equal (order across independent sockets is not asserted); no id appears twice at one client; **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S27`) at both clients, which is what makes "exactly ten and no more" a statement about the product rather than about a socket that stopped delivering after ten |
| API | ten 200s |
| DB | ten mutations landed; no lost update — each project's final state matches the last mutation issued against it |
| UI | a third observer tab runs `refreshAll` **at most twice** per burst — counted at the same named seam as S18 (`page.on("request")`, registered before navigation), never inferred |
| Logs | ten audit records |

**Cleanup:** delete the ten throwaways; delete `LIVENESS-S27` (**`r3`:** its Queue row required the control and its cleanup did not name it).

---

### S28 — double submit, at a real browser

**Tier:** ui · **Class:** edge-case · **Covers:** the in-flight-flag guard; run-2 d2 regression; composer and inline-rename keyboard
**Preconditions:** chromium · **When:** open the New Project dialog, fill a name, and issue **two `click()` in one tick** on Create; separately, drive the composer (Enter sends, Shift+Enter newlines, empty is a no-op) and an inline rename (Enter commits, Escape reverts)

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | **one** POST, not two — the guard is an in-flight **flag**, deliberately not `disabled`, because the nodes are rebuilt on every answer |
| DB | **one** workspace row |
| Queue | **one** frame |
| UI | **one** row in `#proj-list`; the composer's three keyboard cases behave; Escape reverts the rename to its prior text |
| Logs | zero `console.error`/`pageerror` |

**Declared uncovered:** four other POST handlers are **deliberately unguarded** on an idempotency bet. They are named in §7 rather than driven — driving them would assert the bet, not the guard.

**Cleanup:** delete the created project.

---

### S29 — the daemon dies mid-flow

**Tier:** ui · **Class:** error-handling · **Covers:** the degradation path, **per module and per element**; **runs last in wave 6**
**Preconditions:** every other scenario has completed · **Given:** all four live pages mounted in one tab
**When:** `controld.stop(running)`; then perform one action on each of the four pages

**`r1`'s assertion was false of the tree, and the measurement is the fix.** `r1` said *"each of the
four modules writes **its own** unreachable sentence"*. Measured on this tree: `chat.js:131-132`,
`app.js:65-66` and `projects.js:49-50` define the **byte-identical** string; only `settings.js:209-211`
differs; and **`flock.js` has no `UNREACHABLE` constant at all** — the Flock page's failure path runs
through `app.js`'s own `read()`, which calls `showError(UNREACHABLE)` into the **shell's shared
banner**. So `r1` was either a FAIL that is not a defect (four *distinct* sentences do not exist) or,
once weakened to "a sentence appears", a **pass the shared banner satisfies even when a module
rendered nothing**. §5 now carries the four provenance rows; this scenario asserts **the expected
string in the expected element, one row per page**:

| Page | Element asserted | Expected text | Defined at |
| ------ | ------------------ | --------------- | ------------ |
| Shepherd | `#shepherd-status` | `The request did not reach the server — Shepherd may not be running.` | `chat.js:131-132`, written by `fill("shepherd-status", UNREACHABLE)` (`chat.js:146,165`) |
| Projects | `#p-refusal` (and the detail error line) | the **same** string | `projects.js:49-50`, via `view.status` (`projects.js:151,166`) |
| Settings | `#settings-note` | `The request did not reach the server — Shepherd may not be running, so these numbers are whatever was last read.` — **the one that differs** | `settings.js:209-211`, written by `fill("settings-note", UNREACHABLE)` |
| Flock | the shell's shared banner `#stream-message-text`, **unhidden** | the `app.js` string, identical to Shepherd's and Projects' | `app.js:65-66`, written by `showError` (`app.js:83-86`) from `read()`'s `catch` (`app.js:109`) |

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | each row of the table above holds — **the named element carries the named string**, compared against the constant read out of the module, never re-spelled in the harness. For **Flock specifically**, the shared banner is not sufficient on its own: assert additionally that the Flock page did not silently keep stale content — the action taken produced either the banner **or** a rendered failure state, and **not** a spinner that never resolves. `#stream-status` reads `reconnecting` or `unreadable`, never `live` |
| API | connection refused at the socket level |
| DB | unchanged (the process is down) |
| Queue | the stream is closed; the page does not busy-loop |
| Logs | zero `console.error`/`pageerror` — a network failure must be **handled**, not thrown |

**The product finding this scenario can now produce, and could not before:** Flock has no
unreachable sentence of its own. Whether that is correct (one shell banner for the one page whose
read path is the shell's) or a gap (three modules say it themselves) is a **product question** the
run reports with the measurement attached — it is not a FAIL this plan invents.

**Cleanup:** the fixture proceeds straight to teardown; `controld` is already stopped and `controld.stop` must not be called twice.

---

### S30 — the AC-28 substitute: a served render sweep, with no `live` marker

**Tier:** ui · **Class:** happy-path · **Covers:** C-4; the viewport list by **reference**, never by restating widths
**Preconditions:** `controld` up; chromium available
**When:** run `render_check.py` **against the served URL** (`--url http://127.0.0.1:{port}/`), sweeping every entry of `render_check.VIEWPORTS` read from the module — never a re-spelled width list — across all six page roots, with **`--fail-on-empty` *and* `--must-fill`**

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | zero viewport faults: no root above the viewport top beyond `SLACK_PX`, none below its bottom beyond `SLACK_PX`; `[id^="page-"]` exclusivity at arrival **and after every nav click**; **`--must-fill`: every page root reaches `viewport_height * FILL_FLOOR` (`render_check.py:87,257`)** — the only check in this tool able to catch a root that does not reach the viewport bottom, and the only one that engages `FILL_FLOOR` at all |
| API | every asset and API request 200 |
| DB | unchanged |
| Queue | not asserted |
| Logs | zero console errors; screenshots under `$SCRATCH/shots/` |

**`r2`, three corrections.** (1) **`--fail-on-empty` is kept and is declared unfalsifiable here.** It
is `if fail_on_empty and not page.locator("body").inner_text().strip()` (`render_check.py:323`) — a
whole-body check — and `index.html` ships the nav, the wordmark and the section labels as **static
markup**, so the body can never be empty while the shell is served. It costs nothing and it catches a
server that answers 200 with nothing; it is not evidence about layout, and `r1` presented it as
S30's layout assertion. (2) **`--must-fill` is now passed.** `r1` declined the one flag that engages
`FILL_FLOOR`, leaving S30 with no falsifiable assertion of its own. (3) **S30 delivers no boundary
width.** `render_check.VIEWPORTS` is `[("phone",390,844),("tablet",820,1180),("desktop",1280,900)]`
(`render_check.py:54`) — three widths S21 already drives — so §2's viewport row no longer counts it.

**The declaration this scenario exists to carry, and it must appear verbatim in the run report:** *AC-28's final clause was **not run**. Its command invokes `pytest -m live`, which starts real `claude` processes against the user's real `~/.claude.json` and is forbidden by a standing user constraint. S30 is a substitute sweep carrying no `live` marker, and a PASS here does not discharge AC-28.*

**Cleanup:** none.

---

### S31 — measure the tree; declare the stale clauses

**Tier:** integration · **Class:** edge-case · **Covers:** C-1 and C-3; byte-cleanliness against the manifest baseline, never `git diff`
**Preconditions:** repo at `c243773` · **When:** measure, on the tree as it is: `len(routes.BODY_ARGS)`, `len(routes.API_ROUTES)`, `len(routes.POST_ROUTES)`, `len(consumer_manifest["post_milestone"]["edits"])`, and the sha256 of `src/shepherd/web/server.py` and `src/shepherd/web/static/terminal.js`

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| **Measured** | `BODY_ARGS == 16` (AC-16 says 15 — **stale**); `post_milestone.edits == 7` (AC-21 says 6 — **stale**); `terminal.js` digest ≠ its `baseline` digest (AC-23 assumes byte-clean — **stale**); `API_ROUTES == 14`; `POST_ROUTES == 16` |
| **Byte-pin** | `sha256(web/server.py)` **equals** `consumer_manifest["baseline"]["web/server.py"]` — server.py is byte-pinned and must not have moved. **Compared against the manifest digest, never via `git diff`**, which reads the working tree and now asserts only "no uncommitted edits" |
| DB | unchanged |
| API | unchanged |
| Queue | not asserted |
| Logs | none |

**This scenario does not amend anything.** It records three measurements and declares three clauses stale, routed out for a revision 7 the user or a BUILD owns. A run that rewrites its own exam and then passes it is the exact failure this route exists to prevent.

**Cleanup:** none.

---

### S32 — the edit chain: draft state across three round trips

**Added in `r2`.** §2 claimed `full-combinatorial` with `Uncovered: none` over
`{#proj-new, #proj-edit, #proj-delete} × {unassigned, ordinary}` while **`#proj-edit` was never
opened on an ordinary project anywhere in the plan** — its only two occurrences were the *absence*
assertion on `unassigned`. The feature map's chain *"Edit a project's paths → add path → remove
path → Save"*, whose whole point is that draft state survives three round trips inside the module,
was driven by nothing and appeared in no §7 row.

**Tier:** ui · **Class:** edge-case · **Covers:** `#proj-edit` on an ordinary project; the feature map's edit chain; `#p-new-path`'s add/remove round trips; R1
**Preconditions:** chromium at 1280x900; P1 seeded with two repos; R1 on disk · **Given:** the Projects page, P1 selected
**When:** `#proj-edit` on **P1** → the dialog opens in **edit** mode → add R1's path via `#p-new-path` → remove one of P1's two existing repos → **edit `#p-desc` to a new value, leaving `#p-name` unchanged** → Save

**`r3` — `r2`'s Save issued no request at all, so its API row could not fail.** `submitProject`'s
edit branch is two **conditionals**: `…/rename` fires only `if (name !== editing.name)`
(`projects.js:684`) and `…/description` only `if (description !== (editing.description || ""))`
(`:691`). `r2`'s `When` changed **neither**, so Save closed the dialog and called `reload()` and
nothing else — while the API row asserted *"Save issues the rename/description call"*. Changing the
description alone makes the row a **two-sided** assertion: one conditional must fire and the other
must not, which is strictly stronger than either "issues a call" or "issues none" on its own.

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | `#dlg-project-title` reads the **edit** title, not the create title (`projects.js:536` branches on `editing`); `#p-name` and `#p-desc` arrive **pre-filled with P1's current values**; after the add, the draft list shows three paths **before any Save**; after the remove, two; the dialog closes on success and `#proj-detail` reflects the new set without a reload |
| API | the add and the remove each issue **one** POST (`…/repos/add`, `…/repos/remove`) at the moment they are pressed — this is the round-trip shape the chain exists to test; **Save issues exactly one `POST …/{P1}/description` and exactly ZERO `…/rename`** — the name was not changed, so `projects.js:684`'s conditional must not fire — and **no** second repo call |
| DB | P1 ends with exactly two `workspace_repo` edges: R1 present, the removed one gone, the survivor untouched; **P1's `name` is byte-identical to its pre-scenario value and its `description` is the new text** |
| Queue | one `project.repo_added`, one `project.repo_removed` and one `project.described` frame, in that order — **and no `project.renamed`**, which is the frame-seam reading of the conditional that must not fire — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S32`) |
| Logs | zero `console.error`/`pageerror` |

**What a PASS here does not prove:** that draft state survives a **navigation away and back** mid-edit. That is a fourth round trip and a different scenario; it is recorded in §7 rather than smuggled in here.

**Cleanup:** restore P1's repo set through the same dialog, **and restore P1's description through `POST …/{P1}/description`** — S33's edit half and S19's keyboard leg both open this dialog on P1 afterwards and neither may inherit S32's edit; delete `LIVENESS-S32`.

---

### S33 — the page's validation surface

**Added in `r2`.** Of the nine named values the feature map enumerates for `#p-name` / `#p-desc` /
`#p-new-path`, **empty, whitespace-only, non-existent path and non-directory were driven by
nothing** and were absent from §2's `Uncovered` column and from §7 — the page's entire validation
surface, undeclared. The **duplicate-name re-arm chain** was exercised by the fixture (P2 exists)
and asserted by no scenario.

**`r3` (F4) — (d) and (e) were driven in a dialog mode where the control does not exist.** `r2`
opened `#dlg-project` in **create** mode for all five cases. `projects.js:549` sets
`document.getElementById("p-paths-section").hidden = !editing`, so `#p-new-path` is **hidden**
outside edit mode; and `addDraftPath` returns at `:586` (`if (typed === "" || draft.project ===
null) return;`) **before any request is built**. (d) and (e) would have issued **no POST**, refused
nothing, added nothing — and stranded **R3**, the regular file seeded in `r2` as their only
consumer. The scenario is now explicitly two halves in two dialog modes, and the edit half opens on
**P1** exactly as S32 does.

**`r3` (F4, advisory) — the API row for (a) and (b) described a response that will never exist.**
`submitProject` refuses an empty-or-whitespace name **locally**: `if (name === "") { showRefusal("p-refusal", NEEDS_NAME); return; }`
(`projects.js:658-661`, with the constant at `:52-54`) — **no request is issued at all**. `r2`
asked for *"at most one POST each, answered with the record's positive key `false`"*, which zero
POSTs satisfies vacuously on the count and cannot satisfy at all on the answer. **The UI half is
right and is the valuable half** — it is the whole point of Principle 5 over `required` — so the
API row for (a) and (b) is now the falsifiable statement it should always have been: **exactly
zero** requests.

**Tier:** ui · **Class:** error-handling · **Covers:** four of the nine named text values; the duplicate-name warn/re-arm chain; `#p-refusal`; **R3**
**Preconditions:** chromium at 1280x900; P1 and P2 both named "Shepherd"; **P1 selected, with the two repos S32 restored**; `$SCRATCH/work/notgit` (R2) and `$SCRATCH/work/afile` (**R3**, a regular file) on disk
**When:** in **two** dialog modes, because the controls live in different ones (`projects.js:549`):
**Create mode** — `#proj-new` opens `#dlg-project` with `#p-paths-section` hidden — drive, in order: (a) Create with `#p-name` **empty**; (b) Create with `#p-name` **a single space**; (c) Create with the name `"Shepherd"` → read the warning → **change the name** → set it back to `"Shepherd"` → Create → read the warning again → Create again.
**Edit mode** — `#proj-edit` on **P1**, which sets `draft.project` and unhides `#p-paths-section` — drive: (d) `#p-new-path` with a path that **does not exist**; (e) `#p-new-path` with `$SCRATCH/work/afile` (**R3**) — a **non-directory**. Close the dialog without Save.

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| UI | **Create mode.** (a) and (b) render `NEEDS_NAME` in `#p-refusal` — **a message, not a silent no-op**; the browser accepts a single space and the handler must not trim it to `""` and return with nothing said (`projects.js:52-54` defines the constant; `:658-661` is the branch, and it is Principle 5's case). Compare against the constant read out of the module, never re-spelled in the harness. (c) the first Create **warns and does not create**; **changing the name re-arms** (`duplicate.armed` is per-name, `:666-667`), so the second Create warns again rather than creating silently; the third creates. **Edit mode.** (d) and (e) render a refusal in `#p-refusal` naming the path — the sentence the **tool** wrote, not one the page invented — and the draft path list still shows P1's two existing repos, unchanged |
| API | **Create mode.** (a),(b): **exactly zero** requests — `submitProject` returns at `:660` before `write()` is reached, so a POST here is itself the defect; (c): **three POSTs to `/api/projects`, one workspace created**. **Edit mode.** (d),(e): **exactly one** `POST …/{P1}/repos/add` each — this is the assertion F4 restores, and in `r2` it was zero — both answering `added == false` with a non-empty `refused` |
| DB | exactly **one** new workspace row across the whole scenario, read after the control and net of it (§3a footprint rule); **no** new `workspace_repo` edge, and P1's two existing edges untouched |
| Queue | **one** frame (`project.created`, from (c)'s third press) and no others in the counted window — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S33`) |
| Logs | zero `console.error`/`pageerror` |

**The arming flag is per-name, and that is the defect shape:** a stale arm would let the second
`"Shepherd"` create **silently**. Case (c) is written as six presses precisely so a stale arm fails
it. Note that `duplicate.armed` is **reset on every dialog open** (`projects.js:547`), so (c) must
run without closing and re-opening the dialog between presses — that reset is page behaviour, not
a re-arm, and conflating the two would make (c) pass for the wrong reason.

**Cleanup:** delete the project (c) created; close `#dlg-project` **without Save** so the edit half changes nothing; delete `LIVENESS-S33`.

---

### S34 — the wire's refusal surface

**Added in `r2`.** Three product error paths had observation points in §5 and **no driver**: the
`GENERIC_ERROR` envelope (no scenario produced a failing request — S17 asserts its *absence*, with
no positive anywhere to read that absence against), the **Origin-and-Host check on POSTs** (S14
drove it on the WebSocket only), and `routes.py`'s **dropped-undeclared-field / no-redirect**
behaviour. And **R2 — a non-git directory seeded explicitly "for the `add_repo` refusal path" — was
consumed by nothing**, while §2 and §7 both declared non-git-dir uncovered.

**`r3` (F5) — (d) could not fail for the reason it stated, and the one-word fix is necessary but not sufficient.** `r2` sent `workspace_id` and called it *"one field that duplicates the path parameter"*. The path parameter for `/api/projects/{project_id}/rename` is **`project_id`** (`routes.py:111`), and `BODY_ARGS` for that template is `("name",)` (`routes.py:160`) — so `workspace_id` was dropped by **exactly the same undeclared-field rule** as `colour` (`routes.py:247-249`). No body key in that request could ever have reached the tool, and *"P4 untouched"* therefore proved nothing at all: it was true before the request was sent. This is the *probe wearing an assertion's clothes* shape fixed in S15 and reintroduced here.

**The body now carries `project_id`. What that proves, stated honestly, is a conjunction.** There are **two independent guards** and this seam cannot separate them: `project_id` is not in `BODY_ARGS` for the template, so the comprehension at `routes.py:247-249` drops it; and `args.update(captured)` at `:250` applies the path parameter **last**, so it would overwrite a declared one anyway. A regression that removed **either** guard alone leaves this assertion green. What S34(d) does prove is the property the page actually depends on — **no body key can redirect the target over the wire** — and it proves it against the key that names the path parameter, which `workspace_id` never did. The unit seam that separates the two guards already exists: `tests/web/test_routes_m3.py::test_no_declared_field_shadows_a_path_parameter`. The single-guard blindness is carried as a `deferred` gap in §7 rather than papered over.

**And the target is a decoy this scenario owns, not P4.** `r2` read **P4** in wave 6 and asserted *"P4 untouched"* — which holds only if S11's `deleted` arrived `false`, a value S11 itself flags as an inferred (`I`) row under §0 rule 5. A wave-6 assertion resting on a wave-3 inference is asserting a state rather than labelling it (§0 rule 3). S34 now creates and destroys its own decoy, so the assertion is self-contained and cannot be made vacuous by a measurement elsewhere.

**Tier:** e2e_backend · **Class:** error-handling · **Covers:** `GENERIC_ERROR` + `correlation_id`; the origin check on POST; `BODY_ARGS` field-dropping and the no-redirect property; `add_repo`'s refusal over R2
**Preconditions:** as §1; R2 at `$SCRATCH/work/notgit` (a directory, not a repository); P1 seeded. **P4 is not read by this scenario.**
**When:** first create the decoy — `POST /api/projects {"name": "S34-DECOY"}`, recording its id and its name; **its `project.created` frame opens S34's counted window** (§3a), so nothing before it is counted here. Then issue five raw requests against the running server:
(a) `POST /api/projects` with `Origin: http://evil.example` and a valid `Host`;
(b) `POST /api/projects` with a body that is **not JSON**;
(c) `POST /api/projects/{unknown-route-segment}` — a path no template matches;
(d) `POST /api/projects/{P1}/rename` with body `{"name": "Renamed", "project_id": "{S34-DECOY}", "colour": "blue"}` — one declared field, one field **named exactly as the path parameter**, one **undeclared** field;
(e) `POST /api/projects/{P1}/repos/add` with R2's path

**Then observe:**

| Point | Expected |
| ------- | ---------- |
| API | (a) **403**, and the body is exactly `{"ok":false,"data":null,"error":"GENERIC_ERROR","correlation_id":"<32 hex>"}` — id matched as a **pattern**, never a value (B17). **The refusal happens before the body is read** (`server.py:192-193`, ahead of `_json_body`): assert the 403 arrives for a request whose body the server never consumed. (b) **400**, same envelope. (c) **404**, same envelope. (d) **200** — the rename lands on **P1**, the body's `project_id` having redirected nothing, and the undeclared `colour` is **dropped, never forwarded** (`routes.py:247-250`; a forwarded `colour` would fail `invoke()`'s schema check, so the 200 is what makes the drop observable at this seam). (e) the `add_repo` record answers its positive key `false` with a non-empty `refused` naming the directory as not a repository — `probe_repo` shelling out to real `git` (B11) |
| DB | P1 renamed exactly once; **`S34-DECOY`'s name is byte-identical to the value recorded when it was created** — read immediately before (d) and again immediately after, so the assertion is about this request and not about what an earlier wave left behind; no new `workspace_repo` edge from (e) |
| Queue | one `project.renamed` frame from (d) and **none** from (a), (b), (c) or (e) — **then exactly two frames for the in-scenario control — `project.created` then `project.deleted`, in that order, the second closing the window (§3a)** (`LIVENESS-S34`). A refusal announces nothing, and here that zero is read against four distinct refusal shapes. The decoy's own `project.created` frame **opens** the window and is not counted inside it; its `project.deleted` frame lands in cleanup, after the control, and is asserted there |
| Logs | one audit record for (d) and one for (e) — a refusal is still a gated call; **(a), (b) and (c) never reach the chokepoint**, so they append nothing, and that difference is asserted. Counted before the control runs and **excluding** the decoy's own create and delete (§3a footprint rule) |

**Why the three `GENERIC_ERROR` statuses are driven together:** the envelope is one literal plus an
id whatever went wrong (`server.py:145-150`), so the risk is not in any one status — it is that the
shape is identical across 403, 400 and 404 and **no scenario had ever produced one**. Three
requests, one assertion, and S17's "no `GENERIC_ERROR`" finally reads against a positive.

**Cleanup:** rename P1 back through the same route; delete `LIVENESS-S34`; delete `S34-DECOY` (it has no sessions, so the delete lands and announces one `project.deleted` frame — asserted, after the control).

---

## 5. Observability assertions

| Service | Stage | Level | Message | Required fields | Provenance |
| --------- | ------- | ------- | --------- | ----------------- | ------------ |
| `FleetHandler` | any failed request — **driven by S34** at 403, 400 and 404 (`server.py:145-150`, called from `:193`, `:197`, `:201`) | error envelope (HTTP body) | `{"ok":false,"data":null,"error":"GENERIC_ERROR","correlation_id":"<32 hex>"}` | `ok`, `data`, `error`, `correlation_id` | **V** — quoted whole in feature map §4. The id is matched as a **pattern**, never a value (B17). **`r2`:** in `r1` this row had **no driver** — no scenario produced a failing request, and S17 asserted the envelope's *absence* with no positive anywhere to read it against |
| `FleetHandler` | every response | header | `X-Content-Type-Options: nosniff` | — | **V** |
| chokepoint / audit sink | every gated invoke | JSONL record on disk | one line per invoke | `at`, `tool`, `decision`, `approved_by`, redacted args | **Vp** — the **field names** are quoted; the record's serialised format is not. Assert the named keys and their values; do not assert key order, whitespace or a formatted substring |
| `announce()` → ring | every **succeeded** project mutation | StreamEvent kind | `project.created` · `project.renamed` · `project.described` · `project.deleted` · `project.repo_added` · `project.repo_removed` | envelope: promoted `project_id` | **V** — measured at `tools_projects_events.py:81-86` |
| `sse.py` | stream open / idle | SSE comment | `: open` · `: keep-alive` | — | **V**. Comment lines are **skipped** when counting frames, so "no frame" stays distinguishable from "socket alive" |
| `sse.py` | client behind the ring | StreamEvent kind | `stream.gap` | `seq` | **V** |
| `sse.py` | every frame | SSE field | `id: <seq>` and **no `event:` line** | `id` | **V** (one lane only — corroborated by nothing else, so a disagreement here is a measurement, not a product failure, until re-read) |
| store | a stop that did not land | anomaly counter | `stop_failed` | count delta | **V** — `AnomalyKind.STOP_FAILED.value` |
| browser | any page, any scenario | `console.error` / `pageerror` | any | — | **V** — the six existing browser test files already fail on any, and every round-5 UI scenario inherits that |
| `controld` | process start | stdout banner `controld: http://…` | — | — | **I** — real in `main()`, but the in-process fixture never calls `main()`, so **nothing may assert it** in this topology (env-plan §8) |
| `chat.js` | the Shepherd page, daemon unreachable | text in `#shepherd-status` | `The request did not reach the server — Shepherd may not be running.` | — | **V** — `chat.js:131-132`, written at `:146` and `:165`. Read out of the module, never re-spelled in the harness |
| `projects.js` | the Projects page, daemon unreachable | text in `#p-refusal` / the detail error line / `#dlg-delete-body` | **byte-identical to `chat.js`'s** | — | **V** — `projects.js:49-50`, via `view.status` at `:151` and `:166` |
| `settings.js` | the Settings page, daemon unreachable | text in `#settings-note` | `The request did not reach the server — Shepherd may not be running, so these numbers are whatever was last read.` — **the only one that differs** | — | **V** — `settings.js:209-211`, written by `fill("settings-note", …)` |
| `app.js` (the shell) | **the Flock page**, daemon unreachable | text in the shared banner `#stream-message-text`, unhidden | byte-identical to `chat.js`'s | — | **V** — `app.js:65-66`, written by `showError` (`:83-86`) from `read()`'s `catch` (`:109`). **`flock.js` defines no `UNREACHABLE` at all** — this is the whole of the Flock page's degradation path, and `r1`'s S29 asserted four distinct per-module sentences that do not exist |

**Provenance has three values, not two.**

| Value | Meaning | What may be asserted |
| ------- | --------- | ---------------------- |
| `V` | Quoted from source in full | The whole string |
| `Vp` | Verbatim-but-partial | **Only the quoted fragment.** Name which fragment |
| `I` | Inferred | Nothing, until confirmed against the code |

The `Vp` row above is the audit record, and the risk is concrete: the field **names** are quoted from the design, the **serialisation** is not. An assertion built on a formatted substring of that line would fail for a reason that has nothing to do with the product.

---

## 6. Test data

| Fixture | Built via | Deterministic? | Notes |
| --------- | ----------- | ---------------- | ------- |
| P0 `unassigned` | **migration 004** | yes | reserved; Edit and Delete are **absent** on it. Never created by the harness |
| P1 "Shepherd", 2 repos, long description | **front door** — `POST /api/projects` + `…/repos/add` ×2 | yes | the ordinary project |
| P2 "Shepherd" (duplicate name) | **front door** — **exactly one** `POST /api/projects {"name": "Shepherd"}` | yes | no prior fixture ever had two projects sharing a name. **`r3`: "arm, then create" was a wire step that does not exist.** `duplicate.armed` is **page memory** (`projects.js:620`), reset on every dialog open (`:547`), and the store has no name check at all (`store/projects.py:52-70`). A fixture taking *"arm, then create"* literally issues **two** POSTs and creates **two** extra "Shepherd" workspaces — breaking S2's *"eight workspaces / eight rows"*, the rollup this plan propagated correctly everywhere else. The arm/re-arm chain is a **browser** behaviour and is driven by **S33(c)**, not by the seed |
| P3 "Flock", 1 repo at a ~935 px path | **front door** + `git init` on disk | yes | the ellipsis/`title` class. The path is a **real directory** nested ~12 levels under the scratchpad |
| P4 "Doomed" | **front door** | yes | S0's and S11's subject |
| **P5 "Attached-only"** | **front door** | yes | **Added in `r2`.** Two attached running sessions, **no owned session, no pane**. S10 case (b) and the whole of S12 name *"a project seeded with only attached running sessions"* and `r1`'s seed provisioned none |
| **P6 "Orphan-subject"** | **front door** | yes | **Added in `r2`.** S13's own project: 1 owned (over `shepherd_r5d`), 1 attached, 3 finished. In `r1` S13's owned session had **no pane** — every pane was spoken for |
| **P7 "Stale-handle"** | **front door** | yes | **Added in `r2`.** S17's own project: 1 owned over `shepherd_r5c`, which the fixture kills inside the scenario |
| S-own-1..4 (owned) | **`Store.register_session` + `Store.set_runner_handle`** | yes | **Not the front door.** The only front door is `spawn_session`, which starts a real engine process. See §7. **Four, one per pane (§3b)** — `r1` seeded two and spent them four times. The handle form `local\|shepherd-qa\|shepherd_r5<x>` is the three-field shape `core/runner.py:23,64-79` defines and `runner/local.py:97` consumes, and §3c round-trips it before wave 1 |
| S-att-1..7 (attached) | `Store.register_session` | yes | same seam, same caveat. S-att-5/6 are **P5's**, which is what makes an attached-only project exist |
| S-fin-1..6 (finished) | `Store.register_session` + end | yes | `doomed` must be a count a dialog can show before the button — three in P4, three in P6 |
| R1 real git repo | `git init` + one commit, under `$SCRATCH/repo/plain` | yes | `add_repo` shells to git with **no stub seam** (B11) |
| R2 non-git directory | `mkdir`, under `$SCRATCH/work/notgit` | yes | the `add_repo` refusal path — **consumed by S34**. In `r1` it was seeded for this purpose and consumed by nothing, while §2 and §7 both declared non-git-dir uncovered |
| **R3** — a regular **file** at `$SCRATCH/work/afile` | `touch` | yes | **Added in `r2`.** The **non-directory** value, one of the nine the feature map names; driven by **S33(e)**, in the dialog's **edit** mode — `r2` drove it in create mode, where `#p-new-path` is hidden (`projects.js:549`) and `addDraftPath` returns before any request (`:586`), so R3 had **no consumer at all**. Named `R3` here to match env-plan §5 and §7 |
| tmux panes `shepherd_r5a/b/c/d` **and** `shepherd_r5z` | `tmux -L shepherd-qa new-session -d -s shepherd_<id>` | yes | **Four owned panes, one per owning scenario, plus the control pane §3c kills at bring-up.** `-L` explicit on **every** invocation; no `:` in any name. The ledger is §3b |
| timestamps | seeded absolute, ≥2× from every relative-time boundary | yes | B12 — the page clock is not injectable |
| static-tree fixtures | **none, and none permitted** | — | `web/server.py` is byte-pinned and serves `.html`/`.js`/`.css` only (B8): no font, image, SVG or JSON fixture may enter the static tree |
| planted violations | **none planned.** If one is added it is an **inert fixture under `tests/boundaries/fixtures/` that nothing imports** | — | never a signal, a `kill`, a reboot-capable call or a teardown verb in executable code — not in the repo, not in a shadow tree. Clear `__pycache__` before any mutation run |

Prefer building data through the system's own front door. Every project above is. The sessions are not, and that difference is declared in §7 rather than blurred.

---

## 7. Known gaps

| Gap | Reason | What a PASS does NOT prove | Severity |
| ----- | -------- | ---------------------------- | ---------- |
| **AC-28's final clause is not executed** | Its command runs `pytest -m live`, which starts real `claude` processes against the user's real `~/.claude.json` (C-4) | A green S30 is consistent with the live lane being entirely broken. The substitute sweeps viewports against a served page; it never starts an engine, never reads a real transcript, and never exercises the live-marked path AC-28 names | **blocking** (declared, resolved by substitution + declaration) |
| **AC-16 / AC-21 / AC-23 are false of the tree** | `BODY_ARGS`=16 not 15, `post_milestone`=7 not 6, `terminal.js` has moved from its baseline (C-1) | A green run here does not mean the acceptance set is satisfied; three of its clauses cannot be satisfied by any tree that is also correct. Routed out for a revision 7 | **blocking** (declared; the run measures and does not amend) |
| **Owned sessions are seeded through `Store` verbs, not `spawn_session`** | The only front door that creates a session starts a real engine process, which is forbidden | A green S11/S14/S15 proves the **kill and terminal paths** work over a row shaped like an owned session. It does **not** prove that `spawn_session` produces that shape — a spawn that wrote a malformed handle would be invisible to every scenario here | `deferred` |
| **Round 1's eleven closures cannot be re-verified** | Recorded with no id, no description and no named check; no `runs/qa1/` exists (E1) | Nothing in this run touches them. A fully green round 5 is consistent with all eleven being open | `deferred` |
| **A kill that *hangs*** | No timeout was added, so a hanging kill blocks the verb — and driving it means planting a blocking call in executable code, which this workflow forbids outright | A green S11/S12/S17 proves a kill that returns and a kill that raises. It says nothing about a kill that never returns, which is the failure mode that would take the verb down with it | `deferred` |
| **`app_state["kill.<id>"]`'s null-row distinction** | Not observable through any `Store` verb; only a direct sqlite open could see it, and the storage boundary forbids one (B7) | No scenario asserts it, and no scenario's PASS bears on it | `deferred` |
| **`pre_m4_routes.json` freezes only the pre-T24 surface** | The nine Projects/M4 routes are additive-checked only, never frozen (B15) | A green boundary suite is consistent with a **changed delete body contract** — exactly the contract five scenarios here depend on | `deferred` |
| **`tests/web/test_ws.py`'s 14 reader tests** | The WebSocket read half has no implementer in `src/`, by decision (B14) | Those 14 are vacuous by construction and are not part of this plan's evidence. Round 5's WS claims (S14, S16) rest on the **write** half over a real socket | `deferred` |
| **`js_syntax_check.py` / `render_check.py` skip silently without playwright** | Neither declares the dependency in `pyproject.toml`; both sit behind `importorskip` (B13) | On a machine without playwright these gates **collect and pass** while checking nothing. This run asserts playwright present in preflight, so it is closed **for this run only** — the undeclared dependency itself remains | `deferred` (ticketed) |
| **Two `#p-new-path` classes not driven**: bare repo, subdirectory-of-a-repo | Each needs a distinct real repository shape on disk (B11), and each exercises `probe_repo` rather than the page | A green S33/S34 does not prove `add_repo` refuses a **bare** repo or a repo **subdirectory** with a readable reason. **`r2`:** this row said *three* and included non-git dir, which R2 was seeded for and S34 now drives — `r1` declared uncovered a case its own fixture was provisioned to cover | `deferred` (**`r3`:** this cell was **empty** — the row was rewritten from three classes to two and lost its Severity. §7's own bar is *"mandatory, even when empty"*, and severity is what carries a gap into the run report; a gap with no severity is a gap that gets dropped from the summary) |
| **Draft state across a navigation mid-edit** | S32 drives three round trips inside the dialog; leaving the page mid-edit and returning is a fourth, and a different scenario | A green S32 proves the module keeps draft state across add/remove/Save. It says nothing about draft state surviving a nav away and back | `deferred` |
| **`refreshAll` is counted at the request seam, not inside the module** | The page exposes no counter and there is no injection point; `page.on("request")` counts the fetches a pass issues | S18/S27 prove *at most two passes' worth of requests* arrived. A pass that issued no request would be invisible — the seam bounds the observable, and `r1` named no seam at all | `deferred` |
| **S30's `--fail-on-empty` cannot fail while the shell is served** | `index.html` ships the nav and labels as static markup; the check is `body.inner_text()` (`render_check.py:323`) | It catches a 200-with-nothing and nothing else. S30's falsifiable layout assertion is `--must-fill` at `FILL_FLOOR`, and `r1` passed neither flag's reasoning on | `deferred` |
| **The Flock page has no `UNREACHABLE` of its own** | `flock.js` defines no such constant; the page's failure path is the shell's shared banner (`app.js:65-66`) | S29 asserts the banner, per §5's provenance row. Whether one shared banner is the right design for that page is a **product question** the run reports with the measurement — not a defect this plan asserts | `deferred` |
| **Four POST handlers deliberately unguarded against double-submit** | They rest on an idempotency bet; driving them would assert the bet, not the guard | S28's PASS covers the **one** guarded handler. It says nothing about the four | `deferred` |
| **Six mid-scale relative-time buckets** | The page clock is not injectable in a browser (B12), so asserting a mid-scale bucket in the browser would assert the wall clock | A green S2 covers null, far-past and `<60 s` at the API seam. Six date classes are unrendered anywhere in this run | `deferred` |
| **X1 / X2 / X3 / X4 are observed, not re-proved** | Already recorded defects routed to DEBUG offers or tickets | S2/S4/S6 assert the **actual** shapes so the run does not manufacture duplicates. A PASS there does not mean the divergences are fixed — it means they are still there and were asserted as they are | `deferred` |
| **`POST /api/sessions/{id}/permission`** | Routed, registered, called by no page — a product question, not a test-design input | No scenario drives it; its absence from the UI is not asserted as correct | `deferred` |
| **`viewport-drift` (C-8)** | `test_projects_page.py` and `test_settings_live.py` hard-code 1280x900 and reference `render_check.VIEWPORTS` zero times — the exact drift that hid D1 | A green existing `tests/web` suite is consistent with a defect that lives at any width those two files do not name. **Handed to `qa-build`** with its node-id retirement entries. **`r2` correction — `r1`'s claim here was false:** it said *"round 5's own scenarios read `VIEWPORTS` by reference"*, and **only S30 does**; S21, S22, S23 and S24 all hard-coded their widths, reproducing the exact drift this row names. The fix is not to read `VIEWPORTS` — it holds three widths and this round's subject is the six it does **not** hold — but to give round 5 **one definition site of its own**: `ROUND5_WIDTHS` (§3d), read by reference by S21–S24, with `VIEWPORTS` read by reference by S30 | **blocking** (for the harness, not for this plan) |
| **The SSE tail-subscription window** | `sse.py:124-128` records an unclosed window; a tail subscriber can miss an event published between subscriptions | A single missed frame in S8/S27 is `BLOCKED`/retry, not a product FAIL. So a PASS there does not prove the window is closed — it is not | `deferred` |
| **S34(d) cannot separate the two no-redirect guards** | `routes.py` guards a body key named after the path parameter **twice**: the undeclared-field comprehension drops it (`:247-249`) and `args.update(captured)` overwrites it anyway (`:250`). Over the wire only the conjunction is observable | A green S34(d) proves **no body key can redirect the target**, which is the property the page depends on. It does **not** prove either guard individually: removing one alone leaves S34(d) green. The unit seam that does separate them is `tests/web/test_routes_m3.py::test_no_declared_field_shadows_a_path_parameter`, which this plan does not run. **Added in `r3`** — `r2` asserted the stronger claim with a body key (`workspace_id`) that reached neither guard | `deferred` |
| **No cross-service stub exists in this run** | Nothing is stubbed: the engine is **absent**, not stubbed | Stated so the reader does not look for the usual `unproven by stub` row. Where the engine would be needed, the scenario is `BLOCKED`, never quietly passed | `deferred` |

**Mandatory, even when empty.** A plan that lists only what it covers reads as complete coverage.

| Severity | Meaning | Obligation |
| ---------- | --------- | ------------ |
| `blocking` | The suite cannot be believed about something it appears to cover | Resolve, or state it in §8, before the harness is built |
| `deferred` | Real, non-blocking, and **must not silently evaporate** | Carried into the run report and surfaced to the user at the end |

All three `blocking` rows are **resolved in place**: by substitution-and-declaration (AC-28), by measure-and-declare (AC-16/21/23), and by handing the work to `qa-build` with retirement entries (C-8). None of them is an unresolved contradiction the harness would be built on top of.

---

## 8. Open decisions

| # | Decision | Blocking? |
| --- | ---------- | ----------- |
| 1 | Should AC-16 / AC-21 / AC-23 become plan revision 7? Owner: **the user, or a BUILD** | **no** — nothing in round 5 waits on it. The run measures the tree and declares the clauses stale (S31) |
| 2 | Is `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md` still authoritative over the plan? `plan:186` says it *"outranks every other document"*, and no research lane read it (G-12). Owner: **the user** | **no** — no scenario here depends on a recon-derived fact; every such fact was reported as *the plan's claim about a measurement*, not as measured truth |
| 3 | Should `delete_project` gain a **dry-run**? It destroys on its first call when nothing is running, so probing for the refusal destroys any idle project (GAP 5). Owner: **the user** | **no** — worked around: every destructive scenario uses a project it created or a project seeded for destruction, never an idle one it needs afterwards |
| 4 | `main` and `integration` have **no common ancestor**; a PR would need `--allow-unrelated-histories`. This is the same `commits_behind = 2` that capped every round-3 severity at `unconfirmed`. Owner: **the user** | **no** — round 5 runs on `integration` at `c243773` and makes no claim about `main` |
| 5 | Where the round-5 harness lives: **`tests/qa5/` with its own `conftest.py`**. Resolved from the repo, not asked: `tests/qa/conftest.py` composes the tool surface under a `ScriptedHost` with autouse fixtures that would conflict with a real `controld`, and `tests/boundaries/test_collected_node_ids.py` is a **subset** check, so adding files is safe while renaming existing ones needs a `RETIRED_NODE_IDS` entry. Owner: **harness decision** | **no** — decided, and the builder states what it implemented |

**No decision in this table blocks the harness build.** The two contradictions that *would* have blocked it — C-6's killability record and C-2's event obligation — are not deferred to a decision at all.

**C-6 is settled by reading, and S0 confirms it.** `r1` presented S0 as a four-branch gate and
called C-6 *"settled empirically rather than by picking the likelier document"*. That was the right
instinct applied one step too late: the question was answerable from two lines of the tree
(`store/reads.py:283-284` and `toolsurface/tools_projects_delete.py:128-136`), and the `code` lane
never opened `reads.py`. **`qa-remfix.md:42` is right, `t9-1.md` gap 2 is wrong**, B-ABSENT and
B-ALL are unreachable, and B-OWNED is the only binding this seed can produce. S0 remains — a
projection five scenarios consume is worth reading once rather than inferring four times — as a
**measurement**, not a gate over four live possibilities. The gate moved to the thing that really
is unproven: **can a kill land on a real pane**, proved fixture-side at bring-up (§3c) and
product-side by S11.

**C-2 is answered by putting a second live client in the matrix as a first-class requirement** —
and, since `r2`, by giving that client a stated owner for the whole run (§3a) rather than a
lifecycle that ended at wave 2.

Do not build against an unresolved contradiction; there is none left here to build against.

---

## 9b. Amendment log — `r4`: the five preflight corrections

**`r4` is the first amendment on this route driven by a MEASUREMENT rather than by a reading.**
`qa-preflight` ran against this host, wrote `.cc10x/qa/env/Shepherd-local/setup.md`, and returned
`STATUS: FAIL` with five `ENV_PLAN_CORRECTIONS` — **three blocking, two advisory, all five
`wrong-guess` against `env-plan.md`, and none of them a product defect.** The machine is fine.

**This file is a restatement site, not a subject.** The corrections all land in `env-plan.md`; they
appear here only where this document restates the same fact, and **nothing about the product, the
scenarios or the coverage changed**.

| # | Correction | Class | Where it lands **in this file** | Where it lands in `env-plan.md` |
| --- | ------------ | ------- | --------------------------------- | --------------------------------- |
| **P1** | `PLAYWRIGHT_BROWSERS_PATH` is **unset** and chromium is **not in `.venv`** — it is at `/root/.cache/ms-playwright/chromium-1243/`, on a path derived from `XDG_CACHE_HOME`/`HOME`, **both of which the harness redirects**. Under the harness's own environment `executable_path` resolves *without raising* to a file that does not exist | blocking | §1's `playwright` precondition row, which now requires the launch to be proved **under the redirected environment** | §7 (row rewritten) · §4 steps 3 and 9 · §3's T2 row · §1 · §11 |
| **P2** | `$TMUX` **is** inherited and non-empty here, and `r3` named it only in §2 — a section the manifest is not generated from | blocking | §1's `Feature flags OFF` row, which now cites **§7** | §7 (**new `TMUX` (unset) row**) · §4 step 3 · §2 |
| **P3** | The session scratchpad is **long-lived and shared** and contains **`macwt`, a registered git worktree of `/root/Shepherd`**. `rm -rf $SCRATCH` destroys it — **and `git status --porcelain src/ tools/ docs/probes/` still reports empty**, so the teardown certifies itself clean | blocking | §1's **new** run-root precondition row; every `$SCRATCH/<sub>` path in this file (S32/S33/S34's fixtures, the `shots/` directory) now denotes the minted run root, with **one** definition site | §4 step 1 · §5 · §9 steps 8–9 and the leak check · §10 · §11 **B20** |
| **P4** | B9's premise described a different path than its prose: scratchpad **root 76**, subdir form **88**, suffix **23**, budget **107** (107 BOUND / 108 REFUSED), so the `XDG_RUNTIME_DIR` ceiling is **84**. The conclusion survives | advisory | nothing — this file never restates the arithmetic | §2 · §3 · §4 step 2 · §7 · §11 B9 · feature map §5's B9 row |
| **P5** | The `live` gate must be **marker-based**. Three `tests/e2e/` node ids are collected by default **deliberately**; a path-based gate goes red on them. The marker reading is exact: **76 == 76** | advisory | §1's `Feature flags OFF` row and §3's flag-state `live` row | §2 Verification · §3's collect-only row |

### What preflight CONFIRMED rather than corrected

- **Zero `human`-owned blockers** — env-plan §3's claim, **confirmed by probe**, not repeated on trust. `setup.md` §3 records *"None"*, with every prerequisite probed present: git 2.43.0, tmux 3.4, `.venv` Python 3.12.3, playwright 1.63.0, a chromium-1243 that really launches, `/tmp` writable with 24 GiB free, loopback bindable, four migrations, a clean `docs/probes/` / `src/` / `tools/`.
- **C-8's premise** — the node-id freeze really is a **subset** check (`test_collected_node_ids.py:309`), so **adding `tests/qa5/` is safe** and only a rename needs a `RETIRED_NODE_IDS` entry. The one thing `qa-build` most needed to be true of that gate is true.
- **The screenshot budget** — one nine-width sweep is **220 KiB** measured, S23+S24 ≈ **1.2 MiB**, 400 shots ≈ **9.5 MiB** against 24 GiB free. §12's estimates stand with ~2600× headroom.

### Reconciliation — and it is a re-derivation, not an assertion

Nothing partitioned moved, and the reason is structural rather than lucky: **no fact P1–P5
corrected is an input to any count in this file.** The 35 scenarios, the four partitions (id /
class / tier / wave) reconciling at 35, §2c's **seventeen** PP ids, §0 rule 4's **14 + 8 + 13**
census, §3b's pane ledger, §3d's `ROUND5_WIDTHS`, the **9**-scenario tmux-blocked set, the **17**
`ui` scenarios and the **5** `PARTIAL` non-`ui` browser rows are each a function of scenario
content, and `r4` changed no scenario. env-plan §12 carries the same derivation for the timings and
for step numbering: **§4 is still 11 steps and §9 is still 9 steps**, so every `§4 step N` /
`§9 step N` cross-reference in this file still resolves to the step it named in `r3` — checked by
search across all three artifacts rather than assumed.

**The one number `r4` moves lives in `env-plan.md` §11**: the owner census, 2 → **3**
`harness decision` (B20 is new) and 7 → **8** `external` (an `r3` slip — it had read the
*un-closable* list as the external one; B8 is the difference). Re-derived there by counting the
table, not patched.

**And the standing caveat, unchanged: this is self-verification.** There is no pass 3. `r4` was
checked against `setup.md` and against the two other artifacts by search; **no adversarial reader
has read it whole.**

---

## 9a. Amendment log — `r3`, and the sweep

**`r4` supersedes this paragraph's first sentence, and the correction is left visible rather than
rewritten.** `r3` said *"this is the final amendment on this route"* — and it was the final
**review-driven** one; `r4` is a later, **measurement-driven** amendment (§9b), which is a thing the
route allows and this sentence did not anticipate. What has not changed is the part that matters:
**there is no pass 3.** The deferral register records
the hole in terms — *no verifier for a QA plan amendment made after `qa-plan-review-2`* — so what
follows **is** the verification, and a reader must weigh it as self-verification rather than as a
fresh adversarial pass.

### The five blocking findings, each verified at source before acceptance

| # | Verified at | Verdict | Fixed in |
| --- | ------------- | --------- | ---------- |
| F1 | `test-plan.md` §3a *"Two frames"* vs the twelve `exactly one frame` Queue rows vs `env-plan.md` §4 step 10 *"one `project.created` frame … then delete it"*; `tools_projects_events.py:79-86` confirms create **and** delete each publish on their own positive key | **the plan's error.** Two statements of the same constant, and a window definition that disambiguated neither | §3a (three rows rewritten + the footprint rule) · twelve Queue rows · env-plan §4 step 10 |
| F2 | `tools_projects.py:158-169` (`"created": True` unconditional); `store/projects.py:52-70` (bare INSERT, no name check); `projects.js:615-627` and `:620` (*"a warning and not a refusal"*, flag in page memory) | **the plan's error, and the worst kind** — S5 would have failed against a **correct** product and reported a fabricated defect on the one scenario proving a negative | S5 rewritten onto the reserved-project refusal · §2's text-values cell · §2c PP-2 |
| F3 | `test-plan.md` §3 wave 4 `Stop-if` (*"the whole wave is `BLOCKED`"*) vs `env-plan.md` §11 (*"S16 is not in this list"*); S16's `Preconditions: as §1` vs §1's four-pane row; `tools_terminal.py:228-237` → `server.py:296-308` confirms no tmux contact | **the plan's error** — a correction landed in one artifact and in one section of it | §3 wave 4 · S16 · §1's pane row · env-plan §11 |
| F4 | `projects.js:549` (`hidden = !editing`), `:586` (`draft.project === null` → return), `:477-482` (the keydown handler), `:658-661` + `:52-54` (`NEEDS_NAME`, no request) | **the plan's error** — S33 (d)/(e) and S19's keyboard leg issued no request, stranding R3 | S33 (split by dialog mode) · S19 · §6's R3 row · env-plan §5's R3 row |
| F5 | `routes.py:111` (`{project_id}`), `:160` (`BODY_ARGS = ("name",)`), `:247-250` (the two guards) | **the plan's error — and the proposed one-word fix is necessary but not sufficient.** Sending `project_id` makes the request name the right key, but the two guards are **not separable at this seam**: either alone keeps the assertion green. Accepted with that correction stated, and the residue carried as a §7 gap rather than absorbed | S34 (d), the decoy target, the conjunction statement · §7's new row · feature map §4's `routes.py` row |

### The eleven advisories — all verified, all valid, all acted on

| Advisory | Verified at | Fixed in |
| ---------- | ------------- | ---------- |
| S33's API row for (a)/(b) describes a response that will never exist; `NEEDS_NAME` is at `:52-54`, not `:51-52` | `projects.js:658-661`, `:52-54` | S33's API row → **exactly zero** requests; the citation corrected |
| The tmux-BLOCKED denominator is **9**, not 8 — S9 reads `len(DOOMED)` from S0's binding | S9 `:547`/`:554`; §2's *"until S0 returns, none of these five is interpretable"* | env-plan §11, **re-derived from the dependency graph** in three steps, not patched; S9's `Preconditions` |
| The playwright loss is drawn on the tier partition only; five non-`ui` scenarios carry a named browser assertion | S2, S6, S12, S13, S16 `UI` rows | env-plan §11's playwright row names all five and records them `PARTIAL` |
| `ROUND5_WIDTHS` claimed read by reference by S21–S24; **S22 hard-codes `1280x900`** | S22's `Preconditions` | S22 reads the constant; §3d states what the by-reference rule binds (harness code) and what it does not (this document) |
| S32's Save issues no request at all | `projects.js:684`, `:691` (both conditionals) | S32's `When` edits `#p-desc`; the API/DB/Queue rows become a **two-sided** assertion |
| Teardown is specified to do the thing S29 forbids | S29's cleanup vs env-plan §9 step 4 | env-plan §9 step 4 is **conditional**, with a two-branch verification |
| §0 rule 4's exemption list is presented as exhaustive and is not | S3's and S19's Queue rows, in neither list | rule 4 restated as a **three-cell partition with a decision procedure**, censused over all 35 Queue rows (14 + 8 + 13) |
| P2's *"arm, then create"* is page memory, not a wire step | `projects.js:620`, `:547` | env-plan §5 and test-plan §6 → **exactly one** POST |
| S17's cleanup and S34's preconditions assert a state rather than labelling it | S17's API row vs its cleanup; S34 vs S11's `I`-row `deleted` | S17's cleanup **branches on the measured value**; S34 uses a decoy it owns and never reads P4 |
| §7's two-`#p-new-path`-classes row lost its Severity cell | §7's own *"mandatory, even when empty"* bar | Severity `deferred` restored, with why it matters |
| §1's `Seeded world` omits R3 | §1 vs env-plan §5 and §6 | R3 added to §1 — which is what *"as §1"* inherits |

### What `r3` did NOT touch, because pass 2 verified it independently

The four coverage partitions (id / class / tier / wave), all reconciling at **35** and re-derived
below by script; §2c's **seventeen** PP ids; the pane ledger §3b, where **no scenario depends on a
pane another destroyed**; every `-L shepherd-qa` invocation and the absence of `:` in every session
name; the absence of any `kill-server` at any blast radius (RD-QA5-1); and B2–B6. No 32-era
denominator exists anywhere in the three artifacts.

---

## 9. Amendment log — `r2`

Every finding below was **re-verified against the cited source before it was accepted**. All six
blocking findings were **this plan's error**; none was the reviewer's. The reviewer's independent
re-verifications — the four coverage partitions, no dropped scenario, the tmux handling, and the
AC-28 declaration in five places — were confirmed and are unchanged.

| Finding | Verified at | Verdict | Fixed in |
| --------- | ------------- | --------- | ---------- |
| **B1** — zero-frame assertions with no rig and no control | env-plan §4 steps 1–10 attach no SSE client; `r1` S0/S9/S10/S11/S12/S17 count frames; S3's cleanup ends the lifecycle at wave 2 | **plan's error, confirmed** | §0 rule 4 · §3a · S0, S9, S10, S11, S12, S17, S26, S27 · env-plan §4 steps 10–11, §9 step 3 |
| **B2** — `Uncovered: none` over undriven members | `#proj-edit` occurs in `r1` only in absence assertions; `choice("cancel", "Wait — keep the project", …)` at `projects.js:1000-1004` is driven by nothing; `#dlg-delete-cancel` (`:771`) is a second control | **plan's error, confirmed** | §2 rows · **S32** · S9 |
| **B3** — S29's per-module sentence is false of the tree | `chat.js:131-132`, `app.js:65-66`, `projects.js:49-50` are byte-identical; `settings.js:209-211` differs; `flock.js` has **no** `UNREACHABLE`; the Flock path is `app.js::showError` → `#stream-message-text` | **plan's error, confirmed** | §5 (four new provenance rows) · **S29 rewritten** · §7 |
| **B4** — three mismatches in the AC-28 substitute and the C-8 claim | `render_check.py:54` (`VIEWPORTS` = 390/820/1280), `:323` (`--fail-on-empty` is a whole-body check), `:87`/`:257` (`--must-fill`, `FILL_FLOOR`); `index.html` ships a static nav; S21–S24 hard-code widths | **plan's error, confirmed on all three** | §2 viewport and Settings rows · **S30** · §7's C-8 row · `ROUND5_WIDTHS` (§3d) |
| **B5** — "non-zero box" tolerates a 1 px collapse; "clickable" undefined | `FILL_FLOOR = 0.75` at `render_check.py:87`, used by no `r1` scenario; `r1` says "hit-testable" in S19/S25 and "clickable" in S22/S23/S24 | **plan's error, confirmed** | **§3d** (`HIT_TESTABLE`, `PANE_HEALTHY`) · PP-7 · S19, S22, S23, S24, S25 |
| **B6** — three scenarios unprovisioned by the seed | env-plan §5 provisions running sessions only in P4 and spreads S-att-2..4 "over P1 and P3"; `r5a` destroyed by S11, `r5b` reserved for wave 4, `r5c` consumed by S17 | **plan's error, confirmed** | env-plan §5 (**P5, P6, P7**, S-own-3/4, S-att-5..7, S-fin-4..6) · **§3b** (the pane ledger) · S10, S12, S13 |
| **RD-QA5-1** — drop the `kill-server` teardown step | Router decision, binding | applied | env-plan §9 (step 6 removed, steps renumbered), §11 |

**Advisories acted on, each verified first:**

| Advisory | Verified at | Fixed in |
| ---------- | ------------- | ---------- |
| S0's STOP branch unreachable; its outcome statically determined | `store/reads.py:283-284`; `tools_projects_delete.py:128-136` (keys unconditional) | S0 rewritten; §8's C-6 paragraph; wave-1 `Stop-if` |
| The failure-classification rule existed only in the hand-back YAML | `grep` of both artifacts for `inferred` / `never been executed` / `environment BLOCKED` → **0 hits** | **§0 rule 5**; §3c's fixture-side controls; S11's classification paragraph |
| The input-validation surface undriven and undeclared; R2 seeded and unconsumed; no `add_repo` refusal driven | feature map §6's nine named values; env-plan §5's R2 row vs §2/§7's "uncovered" | **S33**, **S34**; §2's text-values row; §7 |
| Duplicate-name re-arm chain asserted by nothing; rail toggle never driven; §2's empty class named S29 | feature map §7; `#collapse`/`#shell[data-rail]`; S29's text | S33 (re-arm); S19 and S23 (rail); S2 (empty) |
| `GENERIC_ERROR`, the origin check on POST and on the stream, `routes.py` field-dropping — observation points with no driver | `server.py:145-150`, `:192-193`, `:257`; `routes.py:239-248` | **S34**; S3's negative control |
| `refreshAll` "at most twice" with no named seam | S18, S27; this plan's own B4 | S18, S27 — `page.on("request")` |
| S20/S21 assert a differential with no baseline and no named element set | S20, S21 | `CONTROL_SET` + a baseline pass in both |
| PP-3 falsified by construction by S17, which was not a breaker | `store/models.py:186` | PP-3 restated; S17 named |
| Viewport rollup miscounts — eight vs nine, and env-plan's "seven" | §2 row vs S24's prose; env-plan §12 | §2 row; env-plan §12 |
| S10 vs S0's B-ALL branch contradict each other | S0's B-ALL rule vs S10's case (b) | B-ALL restated as unreachable; the re-scoping rule deleted |
| S11-under-B-ALL and S15's geometry row cannot fail | S11's API row; S15's tmux row | B-ALL branch removed from S11; S15 restated as an expected **inequality** |

**What was checked and left alone**, because the reviewer re-verified it independently and this
amendment agrees: the four coverage partitions (id / class / tier / wave) reconcile, no scenario
was dropped, every tmux invocation carries `-L shepherd-qa` and no name contains `:`, and AC-28's
non-execution is declared in five places. The `r2` arithmetic is re-derived from scratch in §2, not
patched.
