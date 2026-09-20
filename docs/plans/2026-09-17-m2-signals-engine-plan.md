# Shepherd M2 — Signals Engine — Execution Plan

## Metadata

- **Created:** 2026-09-17
- **Status:** draft
- **Plan Mode:** execution_plan
- **Verification Rigor:** critical_path
- **Scope:** **M2 only** (spec §16). M3–M6 are out of scope and get their own plan → implementation cycles (§0).
- **Builds on:** `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` (revision 6) and everything it shipped. M1's ADRs 1–7, its blocker protocol, its constraint keys and its vocabulary are **inherited, not restated except where M2 changes them**.
- **Inherits open blockers from:** `docs/plans/2026-09-16-m1-BLOCKERS.md` — see "Inherited blockers" below.
- **Plan revision:** 3 · **Last reviewed revision:** 2 · **Fresh-review passes:** 1/2
- **Revision 3 (2026-09-17) — the fresh review's four blocking findings and seven advisories, applied
  in place.** The reviewer verified the evidence base independently and it held (the 13-value `o_`
  enum, `overloaded` at 0 assignments, 529 → `server_error`, plain 400 → `unknown`, `Stop` with no
  `stop_reason` in 26 captures *and* in the zod schema, `SessionEnd.reason` 47/2/1, and the second
  corpus). The 19-task structure stands; `REPLAN_NEEDED: false`. What changed: **B1** — C12's bound
  could not fire (both `Stop` and `SessionEnd` are one `SignalKind`, so two required tests
  contradicted each other) → a kind split plus an `end_reason` guard; **B2** — `handle_stop` was fully
  tested and **never constructed in the daemon** → Task 18 takes the stop path's wiring; **B3** — the
  hermetic lane could not reach `completed` (1 of 50 sessions has a checked-in transcript) → the 26
  fixtures are **composed** and P-M2-14 names its population; **B4** — ADR-M2-5 deviates from D34's
  literal sentence → promoted to **DP10**, and the residue D34 wants counted is now a real counter on
  the fleet page. A1–A7 applied. **Router decision recorded: T18-2 (`PostToolBatch`) is deferred past
  M2**, and `doctor` must report the two refusal counters as *idle*, not zero.
- **This was M2's only planned fresh-review pass.** Anything found after this is a blocker entry under
  the plan's own protocol, not another revision.
- **Revision 2 (2026-09-17) — re-grounded against a tree that changed while the plan was being
  written.** The plan-review gate found that **M1's Task 18 landed mid-write**: `daemons/controld.py`
  (150 lines), `signals/hook_lane.py`, `toolsurface/tools_engine.py`, `fleet_tree`,
  `[project.scripts]`, `tests/e2e/`. Revision 1 asserted the composition root **absent** and had T13
  *create* a `fleet_tree` that already exists. Sections changed: Metadata · Agreement Snapshot (in and
  out of scope) · **DP6 rewritten, DP9 added** · Inherited blockers (rewritten from M1's T18 ledger
  sweep) · Codebase Reality Check (six rows) · Risk matrix (+5) · Differences from agreement (D-2,
  D-5, D-6) · ADR-M2-7 · **T11** (consumes `HookLane`) · **T13** (extends, does not create) ·
  **Tasks 18 and 19 added** · Live Verification Strategy (new) · Verification strategy · Dependency
  graph · Completeness gate · Self-review · Milestone acceptance (clause 12, +2) · step 0b.

---

# LAYER 1 — HUMAN LAYER

## Agreement Snapshot

**Goal.** Make every stopped session answer *why it stopped* and *what to do about it* — mechanically,
for free, and correctably. A hook payload plus the transcript Claude Code already wrote becomes one
immutable **stop-evidence record**; a pure classifier turns that record into a `stop_reason`, an
`outcome` bucket, a one-line `why`, a confidence, and one to three `next_actions[]`; the record goes
to a rotating JSONL log so a missed case is fixed by **editing a rule and replaying history**, not by
waiting for it to recur (D3, D25). The fleet page renders the seven-bucket palette, expandable
stopped rows with action buttons, a Needs-You rail, and the **`unknown` rate** — which *is* the
tuning backlog (principle 5).

**The LLM verdict lane is not built (D34).** Mechanical reasons and the five heuristics only, with
exactly one named call site — `signals/verdict.py::classify_end_turn()` — that today returns the
heuristic result unchanged. **No `Classifier` seam**: an interface with zero implementations behind
it is D9's mistake in its purest form.

**Constraints (all binding; K1–K10 are M1's, unchanged and still law):**

| # | Constraint | Source |
|---|---|---|
| K1 | No data shape asserted without a real captured example in `data-schemas.md`. A shape not there is a **gap**, and the task's first step is a probe. | D41, user brief |
| K2 | Nothing we install may harm Claude Code. | Principle 4 |
| K3 | The real `~/.claude/settings.json` is never touched; every installer/live test runs against a throwaway dir. M2 installs nothing, so K3 is upheld by construction. | User brief, C6 |
| K4 | `mypy --strict`, Python 3.12, no `Any`, no file past ~600 lines. | Principle 6 |
| K5 | No `shell=True` anywhere; argv lists only. | §13 |
| K6 | Never `tmux kill-server`; never touch the `shepherd` socket; always pass `-L`. | CLAUDE.md, §18 incident |
| K7 | The 55 decisions + D38.1 are law. Pressure against one is a **named Decision pressure** — four parts, recommended, never silently reversed. | §3, §0 |
| K8 | stdlib-first; no build step for the frontend; no runtime dependency at M2. | §5 Stack, D51 |
| K9 | Unknown is a first-class value — counted and displayed, never hidden. | Principle 5 |
| K10 | The host has no pip/ensurepip in the system Python, no node/npm/tsc, no `sqlite3` CLI. `/root/Shepherd/.venv` is the toolchain. | data-schemas §Runtime toolchain |
| **K11** | **The thirteen AST boundary rules are stated as properties and discover targets by what a module *declares*. An exemption is not an acceptable way to make one pass** — ADR-1 calls that "how boundaries die". A rule that fires on this plan's prescribed code is a **plan defect**, fixed by re-shaping the code or by a named plan change. | M1 ADR-1, T2, r6 |
| **K12** | **`Signal.fields` reads fail closed on computed keys.** Named neutral keys, one at a time; `dict(signal.fields)`, `{**fields}`, `.keys()`, iteration and passing the mapping to a callee are build failures inside `signals/`. | M1 BLOCKER T11 (from T2 r6) |
| **K13** | **No engine event name and no engine field name may appear in `signals/`**, and `raw_kind` may not be compared, aliased-then-compared, method-called or membership-tested there. | D35 §5.0, M1 `test_no_engine_vocabulary_in_signals` |
| **K14** | **Nothing the UI renders may read a log** (D25). The stop log is read by `replay` and by nothing a page can call. | D25 |
| **K15** | **No rule may reference `Stop.stop_reason`.** It does not exist — absent from all 26 captures and from the CLI's own schema. | **D46** |

**In scope (verbatim from §16, decomposed):**

1. The **mechanical stop-reason table as code**, keyed on `StopFailure.error`, `SessionEnd.reason`
   and the **transcript tail** — never on `Stop.stop_reason` (D46). Unmapped values land in
   `unknown` and are **counted**.
2. The **completeness split** on `end_turn` — the five heuristics and `blocked_external` sources 1–2,
   with the LLM lane **stubbed behind `classify_end_turn()`** and no seam (D34).
3. **`next_actions[]` and its default table** (D21) — one row per stop reason, computed free in the
   same pass that sets `outcome_class`.
4. The **`session` stop columns** — `stop_reason`, `outcome`, `why`, `confidence`, `decided_by`,
   `next_actions`, `ended_at`, `exit_code` — written for the first time (M1 created them and never
   wrote them).
5. The **stop-evidence log** (D25): rotating daily JSONL, gzip on close, size cap as a second
   trigger, 90-day retention, a reader that **skips malformed trailing lines**.
6. **`shepherd replay`** — re-runs the current classifier over the stop log, overwrites the `stop_*`
   columns, writes a before/after diff to `logs/replay/`.
7. The **seven-bucket palette and its ordering** (§4, §12) — every bucket with a **colour and a
   glyph**; `blocked` sorts **below** `running`, deliberately.
8. **Expandable stopped rows with action buttons**, the **Needs-You rail** on every page, and the
   **`unknown` rate** as a first-class fleet metric.
9. **Test lane 1**: the classifier over golden fixtures — real stop records plus transcript tails.
   **No mocking of Claude Code; the fixtures ARE Claude Code.**
10. **T18-3** — `controld.py` is over ADR-1's 150-line cap (154 at r3, and the boundary suite is red)
    and M2 adds wiring. Task 18. *(Not in §16's sentence; in scope because M1 named M2 as the owner.)*
11. **The stop path's construction in the daemon** — nothing else owns it, and without it `handle_stop`
    is a tested seam that never runs (**r3 BLOCKING 2**). Task 18.

**Out of scope (named so they cannot leak in):**

- **The LLM verdict lane** — deferred past M2 (D34). One call site, no seam, no credential, no prompt,
  no `Anthropic` client, no `Credentials.available()` check.
- `owned` sessions, tmux runner, pty, xterm.js, write policy, mailbox, `ask()`, `/rename` — **M3**.
  Therefore `exit_code` stays null at M2 (owned-only, §7) and `killed` is unreachable (it needs the
  `action_log`, M4).
- `authorize()`, audit log, MCP exporters, `master/`, approvals, chat page, the wake set (D31) — **M4**.
  `report_blocked()` is a tier-2 registered tool and is **M4**, so `blocked_external` source 1 is not
  built; source 2 needs `work_item.status_class` and is **M5**.
- `work_item`, `queue`, claims, workers, worktrees, the matrix view (D27), two-chip rows — **M5**.
- `shepherd install`, systemd units, packaging — **M6**.
- **Re-planning M1's Task 18** — it **landed while this plan was being written** (DP6). M2 wires into
  the composition root it built; it does not rebuild it, and it does not move `HookLane`'s three
  impure rules.
- **A second transport for `cli/`** — blocker T18-1 assigns it to M4 (D38's exporter). `shepherd
  replay` inherits that gap and says so (**DP9**).
- **Subscribing `PostToolBatch`** — blocker **T18-2, DEFERRED past M2** by router decision at r3.
  Verifying it needs a real hook install against a real session, and **K3 forbids touching the user's
  `~/.claude/settings.json`**. M1's two refusal counters stay correct and idle, and **M2 owes the
  honesty**: `doctor` reports them as *idle because `PostToolBatch` is not subscribed*, never as `0`.
  A zero that cannot move is a claim of coverage.

**Open decisions:** none. **Nine** items are recorded under **Recommended Defaults** (RD1–RD9); each
is low-blast-radius, each names the evidence that makes it safe, and each is explicitly
**unapproved**. Anything touching one of the 55 decisions is a **named Decision pressure**, never a
default: DP1–DP8.

---

## Decision pressures — named, four-part, recommended out loud

Per §0 and K7. Each says what the decision is, what pushes against it, the options, and the
recommendation.

**One of the ten is applied against a decision's literal words — DP10 — and it says so in its own
heading.** The other nine are not. The user's standing instruction is to *recommend without applying*
when implementation pressure pushes against a decision, so the exception is named first rather than
buried:

- **DP10 (r3) is the exception.** D34 says the heuristic residue is `unknown`; M2 makes it `completed`
  at confidence 0.5. It is applied because the literal reading yields a **~98% `unknown` rate** on the
  measured corpus against §8's own worked figure of 8.2%, painting the whole fleet red and destroying
  the very trigger D34 defines. **The half of D34 that matters — the counted tuning signal — is
  restored by a new `completed_low_confidence` counter**, and reversing the decision is a one-line
  change. A reviewer who wants the literal reading gets it for the price of that line.

The remaining nine do not touch a decision:

- **DP1, DP2, DP5** are applied as flagged **spec widenings**, in the same shape M1 used for its
  M13/M16 rows. Each corrects a **data shape** (§7's enums, migration 001's `CHECK`s, §7's
  `next_actions` field list) against a **decision or a later spec section that already says
  otherwise** — D34 says `decided_by='heuristic'`, §8 assigns four completeness `stop_reason` values,
  §8 requires the `source` field. Applying them *follows* the decision log; refusing them would leave
  M2 unable to persist its own output.
- **DP3, DP4, DP7, DP8** are applied as **readings** of decisions that dictate the reading: D24 ("stop
  analysis reads the transcript"), D46 ("unmapped values land in `unknown` and are counted" and the
  boundary that keeps engine words out of `signals/`). They resolve an ambiguity *inside* a decision;
  they do not trade one away.
- **DP6, DP9** are **facts plus a deferral to a milestone that already owns the work** (M1's T18 had
  landed; T18-1 assigns the `cli/` transport to M4). Neither changes a decision.

**If a builder finds pressure this list does not cover, the instruction is unchanged: write the
four-part entry in `docs/plans/2026-09-17-m2-BLOCKERS.md` and do not apply the recommendation.**

### DP1 — `decided_by` has no value for a heuristic verdict

- **Decision.** §7's `session.decided_by` is `mechanical | model | declared | manual`, and migration
  001 encodes exactly those four in a `CHECK` constraint
  (`src/shepherd/store/migrations/001_m1_foundation.sql:122`).
- **Pressure.** **D34 and §8's deferral note both say `decided_by` is `'heuristic'`** — twice, in the
  decision log and in the spec body (`orchestrator-platform.md:1075`, `:145`). Every completeness-split
  verdict M2 writes is a heuristic verdict, so as things stand the first row M2 writes violates its
  own `CHECK`.
- **Options.** (a) Widen the enum to five values, `heuristic` beside `mechanical` — the mechanical
  table keeps `mechanical` at confidence 1.0, the split gets `heuristic`. (b) Write `mechanical` for
  both — one enum, but the column then cannot answer "which of these did a rule *guess*?", which is
  the only question it exists to answer, and `replay`'s diff loses its most useful filter.
  (c) Write `model` — false.
- **Recommendation (APPLIED, flagged as gap N1).** (a). D34 is a decision and §7's enum is a data
  shape written before it; the decision log is the higher authority (§0). Migration 002 widens the
  `CHECK` to five values.

### DP2 — `stop_reason`'s `CHECK` omits the four completeness-split values

- **Decision.** §7 says `stop_reason` holds "values in §8". Migration 001 encoded the **16 mechanical
  values only** (`001_m1_foundation.sql:115–119`).
- **Pressure.** §8's completeness split assigns `stop_reason` ∈ `completed | incomplete | derailed |
  blocked_external` (`orchestrator-platform.md:1042–1047`), and §8's `next_actions[]` default table
  has a row for each. None is in the `CHECK`. M2's central deliverable cannot be persisted.
- **Options.** (a) Migration 002 widens the `CHECK` to all 20 values. (b) A second column
  `completeness` beside `stop_reason` — two columns for one concept, and §8's default table, the
  palette map and `replay`'s diff all key on one value.
- **Recommendation (APPLIED, flagged as gap N2).** (a). It is what §7 already says; 001 under-read it.

### DP3 — §8's heuristics 2–5 need per-event history that D24 forbids storing

- **Decision.** **D24: no event store.** Events are folded into `session` columns and discarded.
- **Pressure.** Read literally, three of the five heuristics need history no column holds:
  heuristic 2 wants "no matching `PostToolUse` **after** the promise", heuristic 3 wants "the **last 3
  signals** are `PostToolUseFailure` on the same tool", heuristic 4 wants "**zero** `Edit`/`Write`
  calls". M1 stores none of that, and adding it is an event store by instalments.
- **Options.** (a) Bounded history columns on `session` (a rolling failure window, an edit counter) —
  a widening per heuristic, and each one is a small event store. (b) **Read them from the transcript
  tail at stop**, which is exactly what D24 says the stop path does: *"Stop analysis reads the
  transcript Claude Code already writes to disk plus the stop event's own metadata"*. (c) Drop the
  three heuristics.
- **Recommendation (APPLIED as a reading, flagged as gap N3).** (b), and it is not a compromise — it
  is D24's own sentence. **Heuristic 1 reads columns** (`tasks_total`/`tasks_done`, already folded and
  already persisted with their identity sets since BLOCKER-T6-1). **Heuristics 2–5 read the tail**:
  the promise-then-no-tool-use pair is two adjacent `assistant` entries; a failure tail is
  `tool_result` blocks with `is_error: true` paired back to their `tool_use` by `tool_use_id`
  (**observed: 4 such blocks in the checked-in transcript copies**); a no-op session is zero `tool_use`
  blocks named `Edit`/`Write` (**observed: `Bash` 8, `Agent` 3, `Workflow` 1, `Write` 2**). No new
  history column is created and D24 is not bent.

### DP4 — the mechanical table keys on engine fields, and `signals/` may not name them

- **Decision.** **D46**: the stop-reason engine keys on `StopFailure.error`, `SessionEnd.reason` and
  the transcript tail. **§5.0 / K13**: no engine event name may appear in `signals/`, enforced by
  `tests/boundaries/test_engine_vocabulary.py`.
- **Pressure.** A table keyed on `StopFailure.error` written inside `signals/` contains the literal
  `StopFailure` and fails the build on this plan's own prescribed code — the F4 failure mode ADR-1
  calls "how boundaries die".
- **Options.** (a) An exemption. **Rejected by K11 outright.** (b) A neutral intermediate enum, one
  member per engine value — ADR-6's r5 note names this as the thing that makes a closed set "a rename
  rather than a boundary". (c) **The map from one engine's vocabulary to ours lives in the adapter**,
  because that is literally what it is; its output is a `core.stops.StopReason` member, and `signals/`
  owns everything downstream of it — the `stop_reason → outcome_class` table, the heuristics over a
  neutral evidence record, and `next_actions[]`.
- **Recommendation (APPLIED; see ADR-M2-2).** (c). D46 is satisfied — the rule keys on exactly those
  three fields, in the one package allowed to read them — and `signals/` never sees an engine string.
  The §8 table stays legible as **one table**, in `engines/claude_code/stop_map.py`, with an `evidence`
  citation per row exactly as Table B has.

### DP5 — `next_actions[]` has two incompatible shapes and two incompatible `kind` lists in §8

- **Decision.** §7: `next_actions` is "up to 3 `{text, kind, target}`". §8's D21 block shows
  `{text, kind, target, source}` and calls the ordering guarantee — *declared* outranks *llm*
  outranks *heuristic* — a requirement (`orchestrator-platform.md:1130–1136`, `:1169`). §8's classifier
  JSON lists **seven** `kind` values; §8's D21 block lists **nine** (`reauth`, `none` extra) and the
  default table **uses both of the extra two**.
- **Pressure.** Built to §7 the ordering guarantee is unimplementable (nothing records which line a
  model wrote); built to the seven-value list the default table's `auth_failed` and `rate_limited`
  rows do not typecheck.
- **Options.** (a) `{text, kind, target, source}` with the nine-value `kind`. (b) §7's three fields
  and a seven-value kind, dropping two default-table rows.
- **Recommendation (APPLIED, flagged as gap N4).** (a). §8 is the later and more specific text, it is
  the one that defines the behaviour, and `source` is what §12's `2 heuristic · 1 llm ⓘ` footer
  renders. The seven-value list is the *LLM output* schema, which M2 does not build.

### DP6 — M1's Task 18 landed **while this plan was being written**, and it built three things M2 planned to build

- **Decision.** §16 puts "both daemons" in M1; ADR-1 puts the composition root in `daemons/`; M1's
  blockers assigned `[project.scripts]`, package data and tool registration to "T18 wiring".
- **Pressure.** This plan's first Codebase Reality Check pass, at 22:1x, recorded
  `daemons/controld.py` as **absent** and concluded M2 had no process to run in. **By 00:5x the same
  check was false**: `controld.py` exists (150 lines then; **154 and failing the line-cap test by
  r3** — the remediation lane is still moving), `signals/hook_lane.py` exists,
  `toolsurface/tools_engine.py` exists, `[project.scripts]` and `[tool.setuptools.package-data]` are
  in `pyproject.toml`, `tests/e2e/` and `tests/test_packaging.py` exist, and M1's own T18 ledger sweep
  records the new baseline: **443 passed, 1 skipped, 8 deselected** on `pytest -m "not live"`, **7
  passed** on `pytest tests/e2e -m live`, `mypy --strict` clean over **61 files**. Three things this
  plan proposed to build are **already built**: `fleet_tree` (T16-1, closed), the hook-lane
  composition (`HookLane`), and cross-repo attribution (T11-3, closed).
- **Options.** (a) Ship the plan as first drafted. **A plan that asserts an absent file which exists
  is a plan a builder will not trust twice**, and it would have had T13 create a function that is
  already there. (b) Re-ground every affected section against the repo as it is now, and make the
  plan **robust to a moving tree** rather than to one snapshot. (c) Freeze the tree and re-plan.
- **Recommendation (APPLIED, and it is what revision 2 of this plan does).** (b), in four parts:
  1. **Every affected section is corrected** — the Reality Check, the inherited-blocker table, T11
     (which now consumes `HookLane` rather than inventing a sibling), T13 (which **extends**
     `fleet_tree` rather than creating it), the risk matrix, and acceptance clause 12.
  2. **M2 gains a live lane**, because one now exists: `tests/e2e/` with a `live` marker,
     `pytest tests/e2e -m live`. See **Live Verification Strategy** below.
  3. **M2 accepts the two blockers M1's sweep assigned to it by name** — T18-2 (`PostToolBatch` is
     not subscribed, so T11-2's refusal counters can never fire) and T18-3 (`controld.py` is *at*
     ADR-1's 150-line cap, and M2 adds wiring). Task 18 below owns both. **An entry that quietly
     disappears is worse than one that stays open** — M1's sweep says so in those words.
  4. **Step 0b is added:** before T1, the first builder re-runs the Reality Check's four mechanical
     rows and records the result in Progress notes. This plan was invalidated once by a concurrent
     builder; the cheap defence is to check rather than to assume.

### DP7 — `message.stop_reason` has a fourth observed value with no §8 row

- **Decision.** §8: `end_turn` runs the completeness split; `tool_use` at a `Stop` is
  `stalled_pending_tool`; `max_tokens` is `truncated`.
- **Pressure.** Measured on this host against the corpus: **all 26 `Stop` captures resolve to
  `end_turn`; all 23 `StopFailure` captures resolve to `stop_sequence`** on the last `assistant`
  entry. Across the 19 checked-in transcript copies the distribution is `end_turn` 57, `tool_use` 26,
  `stop_sequence` 2 — and `data-schemas.md` §"Transcript entry: `assistant`" records **`null` 702** of
  4345 in user data, "null on non-final blocks of interactive streams". Neither `stop_sequence` nor
  `null` has a row.
- **Options.** (a) Guess (`stop_sequence` ≈ `end_turn`). **Rejected** — a guess in the one table the
  milestone exists for. (b) Make the tail the **last** authority, consulted only when neither
  `StopFailure.error` nor `SessionEnd.reason` decided, and map `stop_sequence` and `null` to
  `unknown`, counted.
- **Recommendation (APPLIED).** (b), which is D46's own sentence ("unmapped values land in `unknown`
  and are counted") and is why the precedence order is **error → reason → tail** rather than the
  reverse: on 23/23 error paths the tail says `stop_sequence`, and reading it first would classify
  every API failure as unknown.

### DP8 — `SessionEnd.reason = "other"` is the most common value and §8 has no row

- **Decision.** §8 maps four `SessionEnd.reason` values and omits `other`. D46 names this explicitly:
  *"`SessionEnd.reason` is `other` for every `-p` exit, `tmux kill-session` and `SIGTERM` — the most
  common value, and the one §8 had no row for."*
- **Pressure.** Measured: **47 of 50** corpus `SessionEnd` captures carry `other`, and 11 of 16 in the
  gap-fill corpus. Mapping it to any reason would mislabel the majority of stops; leaving it unmapped
  would push the majority into `unknown` (red, `outcome_class = error`) — a wall of false alarms.
- **Options.** (a) `other` → `unknown`. Honest but useless: 47/50 sessions red. (b) `other` → a new
  reason. Invents a shape. (c) **`other` *defers*** — it says the process ended and says nothing about
  why, so classification falls through to the transcript tail, which is the authority §8 already
  names for a clean end. A value that **decides nothing** is a third outcome, distinct from a value we
  **could not map**, and the two are counted separately.
- **Recommendation (APPLIED).** (c), and `DEFERS` becomes a first-class result of the adapter's map
  beside `UNMAPPED`. The same treatment closes §8's other omissions by naming them rather than leaving
  them: `verification_required` and `cloud_credential_error` → `auth_failed` (both are credential
  states the human must fix; neither has ever been observed, so both ship marked unverified and
  counted); `oauth_org_not_allowed` → `auth_failed` and `account_on_hold` → `account_blocked` (§8
  already has both rows); `overloaded` → `rate_limited` (§8's row is kept, with the measured note that
  the binary contains **zero** assignments of it and a 529 arrives as `server_error`).

### DP9 — `shepherd replay` needs a store, and a standalone `shepherd` process may not open one

- **Decision.** §7 migration rule 3: only `controld` migrates. ADR-7: one writer thread. D37: one
  writer process. M1's **T18-1** records the consequence — `shepherd status` against a running daemon
  exits 1 and says so, because the registry is process-global and a second process opening the store
  would be a second writer against the database `controld` owns.
- **Pressure.** `replay` **writes** — it overwrites the `stop_*` columns on up to hundreds of rows.
  It is exactly the command T18-1's option (c) ("a read-only `Store` mode") is a trap for.
- **Options.** (a) `cli/` opens its own `Store`. Rejected: a second writer, and §7 rule 3 exists to
  stop it. (b) `replay` is a `controld`-registered `ToolDef`; the CLI subcommand reaches it through
  `invoke()` and, in a standalone process, **inherits T18-1's transport gap and prints the same honest
  message** `status` does. (c) Build the transport. Rejected: D38 puts the exporter at M4, and
  T18-1's own recommendation is (b) for exactly this reason — building a transport now is one `cli/`
  would have to unlearn.
- **Recommendation (APPLIED).** (b). The replay **engine** is proven at the `invoke()` seam with a
  store in a fixture (as all 27 `tests/cli/` tests already are), and **end to end inside `controld`'s
  own process** in the live lane. What M2 does not build is a second transport, and acceptance clause
  12 says so rather than implying a command that works everywhere.

### DP10 — a null heuristic result is `completed`, and D34's sentence says it is `unknown`

*(Promoted from gap N6 / ADR-M2-5 at revision 3. The fresh review was right that this belongs in the
four-part form and nowhere else: it is the one place M2 does not do what a numbered decision literally
says, and burying that in a gap row was exactly the "quiet reversal" §0 forbids.)*

- **Decision. D34, verbatim** (`orchestrator-platform.md:145`): *"`end_turn` resolves on heuristics
  alone, `decided_by='heuristic'`, and **the residue is `unknown`** … `unknown` being visible and
  counted is principle 5 working as intended — **it is the tuning backlog that tells you when the lane
  is worth building**."*
- **Pressure.** Taken literally, a clean `end_turn` on which none of the five heuristics fires is
  `unknown`. **Measured on the corpus: 3 `TaskCreated` across 50 sessions**, so no heuristic fires on
  ~49 of 50 — a **~98% `unknown` rate**, against §8's own worked figure of *"unknown rate: 8.2% →
  0.7%"*. And `unknown`'s `outcome_class` is **`error`**, so the literal reading paints the entire
  fleet red on day one. §8's Replay block refutes it from the other side: its three change lines are
  `unknown → stalled_pending_tool` (a *mechanical* reclassification) and `completed → incomplete` /
  `completed → blocked_external` — which is only consistent with a clean stop **starting life as
  `completed`** and `unknown` counting *unmapped mechanical* stops. **Two parts of the spec disagree**,
  and one of them is a decision.
- **Options.**
  (a) **Literal D34.** ~98% unknown, the fleet is red, and the metric D34 wants is drowned by the
  cohort it was meant to isolate. It also makes §8's replay example unreproducible.
  (b) **A sixth completeness value** (`unsettled`) with its own bucket. §4 has seven buckets and §16
  says seven; this adds an eighth *outcome* and changes the palette, which is a bigger deviation than
  the one it avoids.
  (c) **`completed` at `HEURISTIC_COMPLETED_CONFIDENCE` (0.5)**, which is below
  `CONFIDENT_ENOUGH` (0.8), so §8's default table gives the row `Review the diff` (`inspect`) rather
  than an empty action list — **and a separate counter for exactly that cohort**, so D34's tuning
  signal survives in the product rather than only in the argument.
- **Recommendation (APPLIED — and this is the one place in the plan where a decision's literal words
  are not followed, so it is flagged rather than absorbed).** (c). **The reason (a) is refused is not
  convenience, it is that D34's own stated purpose is destroyed by it:** a metric that reads 98% is not
  a tuning backlog, it is noise, and the trigger D34 defines for building the LLM lane ("the `unknown`
  rate on the fleet page is what tells you when it is worth doing") stops being a trigger.

  **What (c) owes D34, and pays (r3 BLOCKING 4).** Revision 2 applied the classification and **dropped
  the counting**, which is the half that mattered: `BUCKET_OF[COMPLETED] = FINISHED` regardless of
  confidence, so ~96% of clean stops rendered a **green `finished` chip** and *nothing counted them* —
  principle 5's "counted and displayed" unmet for the largest cohort, and D34's trigger absent from the
  product. Revision 3 adds **`completed_low_confidence`** to `StopCounts` (T2) and to `fleet_summary`
  (T13), rendered on the fleet page **beside the `unknown` rate** (T14). That cohort *is* the residue
  D34 is talking about; it is now visible, counted, and the number that says when the LLM lane is worth
  building. **D34's sentence is not followed; D34's purpose is.**

- **How to reverse it, if a reviewer prefers the literal reading:** one line —
  `split_completeness()` returns `StopReason.UNKNOWN` instead of `StopReason.COMPLETED` when
  `fired == ()`. Everything else (the counter, the bucket map, the action table, `replay`) is
  unchanged, and `shepherd replay` re-derives every historical row either way. That is why A16 is
  classified `inferred` and **non-critical** in the assumption ledger.

---

## Vocabulary (used exactly, throughout)

| Term | Meaning here |
|---|---|
| **stop evidence** | The one immutable record assembled at a stop: stop metadata + the session's folded counters + the neutral transcript tail. The classifier's whole input. Written to `logs/stops/`. |
| **mechanical reason** | A `stop_reason` decided with certainty from `StopFailure.error`, `SessionEnd.reason` or the tail's turn ending. `decided_by = mechanical`, confidence 1.0. |
| **completeness split** | The four-way `completed | incomplete | derailed | blocked_external` question, asked **only** when the turn ended cleanly. `decided_by = heuristic` (DP1). |
| **defers** | An engine value that says the process ended and nothing about why (`SessionEnd.reason = other`). Falls through to the next authority. Counted. Not an unknown. |
| **unmapped** | An engine value no row claims. Lands in `stop_reason = unknown`, counted. The tuning backlog (principle 5). |
| **unclassified** | A stopped session with **no verdict at all** — M1 wrote the row, M2 never saw its stop. A different thing from `unknown`, counted and displayed separately. |
| **bucket** | One of §4's seven palette values, each with a colour **and** a glyph. What a fleet row renders. |
| **turn ending** | The neutral projection of the tail's `message.stop_reason`: `ENDED_TURN | HELD_TOOL_CALL | HIT_TOKEN_CAP | OTHER | ABSENT`. The engine's four spellings do not cross into `signals/`. |
| **the two corpora** | `hooks/live/` (429 events, 50 sessions) and `gap-fill/*/hooks.jsonl` (37 sessions, the only captures of `resume`, `logout` and death mid-compaction). |

---

## Functionality flows (every step and every error path maps to a test)

```
Flow A — a session stops and is classified
A1 a stop signal arrives (SESSION_STOPPED | STOP_FAILED)
      → test: tests/signals/test_stop_lane.py::test_stop_signal_triggers_classification
A2 the adapter locates the transcript by session id (glob, never by reversing the slug)
      → test: tests/engines/test_transcript_tail.py::test_tail_is_found_by_session_id_glob
A3 the adapter reads the tail: last 20 user/assistant entries, filtered BY TYPE first
      → test: ::test_tail_filters_by_entry_type_before_counting
A4 the adapter assembles StopEvidence (stop metadata + counters + neutral tail)
      → test: tests/engines/test_evidence.py::test_evidence_carries_no_engine_spelling
A5 the adapter maps error → reason → tail into a StopReason, or DEFERS, or UNMAPPED
      → test: tests/engines/test_stop_map.py::test_precedence_is_error_then_reason_then_tail
A6 signals/ maps StopReason → outcome bucket and builds next_actions[]
      → test: tests/signals/test_stop_rules.py::test_every_stop_reason_has_a_bucket_and_actions
A7 on a clean turn ending, the five heuristics run and classify_end_turn() returns them unchanged
      → test: tests/signals/test_verdict.py::test_classify_end_turn_returns_the_heuristic_result
A8 the verdict is written to the eight stop columns, in one store verb
      → test: tests/store/test_stop_verbs.py::test_apply_stop_verdict_writes_all_eight_columns
A9 the evidence + verdict are appended to logs/stops/<date>.jsonl
      → test: tests/logs/test_stop_log.py::test_record_roundtrips
A10 a `session.classified` event is emitted so the page repaints without polling
    (the fold already emitted `session_stopped` at step A1 — two facts, two times; A3)
      → test: tests/signals/test_stop_lane.py::test_stop_emits_one_classified_event

Error paths:
- transcript absent (E26-class)        → tail is ABSENT, evidence still complete, counted
      → test: tests/engines/test_evidence.py::test_missing_transcript_is_an_absent_tail_not_a_crash
- transcript's last line half-written  → skipped and counted, never raised
      → test: tests/engines/test_transcript_tail.py::test_malformed_trailing_line_is_skipped
- StopFailure.error is a value no row claims → unknown, counted
      → test: tests/engines/test_stop_map.py::test_unmapped_error_is_unknown_and_counted
- SessionEnd.reason = other            → defers to the tail, counted as a defer not an unknown
      → test: ::test_other_defers_and_is_not_an_unknown
- no stop event at all, process exit observed → unknown + "exit code not observable" (C13)
      → test: ::test_observed_exit_without_a_stop_event_is_honest_about_the_exit_code
- the log directory is unwritable      → the verdict is still written to the columns; the loss is counted
      → test: tests/logs/test_stop_log.py::test_write_failure_never_loses_the_verdict

Flow B — a rule improves and history is corrected
B1 shepherd replay --since 30d reads logs/stops/*.jsonl (+ .gz), skipping malformed tails
      → test: tests/logs/test_stop_log.py::test_reader_skips_malformed_and_reads_gzip
B2 each record is re-classified by the CURRENT classifier
      → test: tests/signals/test_replay.py::test_replay_uses_the_current_rules
B3 changed verdicts overwrite the stop_* columns
      → test: ::test_replay_overwrites_the_stop_columns
B4 a before/after diff is written to logs/replay/<date>.log
      → test: ::test_replay_writes_a_diff_file
B5 the command prints counts and the unknown-rate delta
      → test: tests/cli/test_replay_command.py::test_replay_prints_counts_and_unknown_rate
Error paths:
- a record written by a newer/unknown record_version → skipped and counted, never guessed
      → test: tests/logs/test_stop_log.py::test_unknown_record_version_is_skipped_and_counted
- a session in the log no longer in the store        → counted as orphaned, not an error
      → test: tests/signals/test_replay.py::test_orphaned_record_is_counted_not_fatal
- replay is idempotent: running it twice changes nothing the second time
      → test: ::test_replay_is_idempotent

Flow C — a human reads the fleet
C1 fleet_tree returns rows already ordered by bucket, server-side
      → test: tests/toolsurface/test_tools_m2.py::test_fleet_tree_is_ordered_by_bucket
C2 each row renders its bucket colour AND glyph
      → test: tests/web/test_palette.py::test_every_bucket_has_a_colour_and_a_glyph
C3 blocked sorts below running
      → test: tests/signals/test_ordering.py::test_blocked_sorts_below_running
C4 a stopped row shows one line of why and the first action as a button
      → test: tests/web/test_fleet_page.py::test_stopped_row_renders_why_and_first_action
C5 expanding shows the whole action list with its source footer
      → test: ::test_expanded_row_lists_every_action_with_its_source
C6 the Needs-You rail shows the actual ask on every page
      → test: tests/web/test_rail.py::test_rail_shows_the_actual_ask
C7 the unknown rate renders as a first-class metric
      → test: tests/toolsurface/test_tools_m2.py::test_fleet_summary_reports_the_unknown_rate
Error paths:
- a stopped session with no verdict     → `unclassified` chip, sorted last, counted separately
      → test: tests/signals/test_ordering.py::test_unclassified_is_its_own_bucket
- [why?] with no LLM lane               → a one-time note, never a dead button (§8)
      → test: tests/web/test_fleet_page.py::test_why_is_a_note_not_a_button_without_the_lane
- an action whose kind needs M3/M4      → rendered, labelled, and inert (RD6)
      → test: ::test_unreachable_action_kinds_are_labelled_not_silently_dead
```

---

## Risk-based testing matrix

| Risk | Prob | Impact | Test required |
|---|---|---|---|
| **A rule references `Stop.stop_reason`, which does not exist** (D46) | med | **high** | deterministic: `test_no_rule_references_stop_reason` extended to `engines/claude_code/stop_map.py` and every M2 module |
| **The engine→reason map is keyed on the wrong field name** (`error_type`, `end_reason`, `start_reason` are all wrong) | med | **high** | deterministic: `test_stop_map_reads_the_captured_field_names` — the map is exercised against the 23 `StopFailure` and 50 `SessionEnd` **captures**, not against hand-written payloads |
| **A 529 is classified `rate_limited`** (§8's row is wrong; a 529 arrives as `server_error`) | **high** *(certain if §8 is copied)* | med | deterministic: `test_http529_capture_is_server_error` over `S08_mock_http529` |
| **A plain 400 is classified `bad_request`** (it arrives as `unknown`) | **high** | med | deterministic: `test_plain_400_capture_is_unknown_and_counted` over `S08_mock_http400` |
| **`other` classifies 47 of 50 sessions as an error** (DP8) | **high** *(certain without the defer)* | **high** | deterministic: `test_other_defers_and_is_not_an_unknown`, plus `test_corpus_unknown_rate_is_under_20_percent` over the two corpora |
| **The `unknown` rate is meaningless** because the end-turn residue is dumped into it (reading B of DP-note below) | med | **high** | deterministic: `test_null_heuristic_result_is_completed_at_low_confidence` + `test_unknown_counts_only_unmapped_mechanical_stops` |
| **A boundary test fires on this plan's own prescribed code, so the first thing a builder does is add an exemption** (K11, ADR-1) | **high** | **high** | deterministic: `test_no_engine_vocabulary_in_signals`, `test_signals_reads_only_neutral_field_keys`, `test_signals_never_compares_raw_kind` all green **with no new exemption**, asserted by `test_boundary_exemption_list_is_unchanged` |
| **`dict(evidence.fields)`-style whole-mapping reads creep into `signals/`** (K12 fails closed) | med | med | deterministic: `StopEvidence` is a frozen dataclass of **named typed fields**, never a mapping; `test_stop_evidence_has_no_mapping_field` |
| **`PreCompact{auto}` on a healthy turn is read as `context_exhausted`** (C12) | **high** *(certain without the bound)* | **high** | deterministic: `test_benign_auto_compact_is_not_context_exhausted` over `autocompact-real-*` (observed 2/3 turns), and `test_kill_during_compaction_is_context_exhausted` over `lifecycle-end-*` |
| **`crashed` is asserted for an attached session whose exit code cannot be read** (C13) | **high** | **high** | deterministic: `test_observed_exit_without_a_stop_event_is_honest_about_the_exit_code` — asserts `unknown` + the stated reason, and asserts `crashed` is **never** produced at M2 |
| **`idle_prompt` puts every finished interactive session in `needs_you` after 60 s** (C21, M1 DP3) | **high** | med | deterministic: `test_idle_prompt_is_needs_you_and_the_rail_says_idle` — inherited behaviour, surfaced in the rail's wording, not softened |
| **A stop log killed mid-write breaks `replay` entirely** (D25) | med | **high** | deterministic: `test_reader_skips_malformed_and_reads_gzip` + a property test over 200 truncations |
| **`replay` corrupts good verdicts** (a worse rule overwrites a better one) | med | **high** | deterministic: `test_replay_is_idempotent`, `test_replay_never_writes_a_verdict_it_did_not_derive`, and the **diff file is the review artifact** before the write is trusted |
| **The next-actions table is not total, so a stop reason renders a dead row** (§14) | med | **high** | deterministic: `test_every_stop_reason_has_a_bucket_and_actions` + `test_non_completed_verdict_never_has_an_empty_action_list` (§14's literal words) |
| **Migration 002 refuses to start on a dev database** (§7 rules 1–2, never exercised before) | med | med | deterministic: `test_checksum_mismatch_refuses_to_start`, `test_future_schema_refuses_to_start`, `test_002_applies_over_001` |
| **A file passes 600 lines** (`db.py` is already 535; `transcript.py` is ~340) | **high** | low | deterministic: `test_no_source_file_exceeds_600_lines` (inherited) — M2 puts the stop SQL in `store/stops.py` and the tail in a new module for exactly this reason |
| **The page re-derives the order in JavaScript** (M1's T16-1 trap) | med | **high** | deterministic: `test_the_page_does_not_re_derive_the_order` (inherited, extended to the bucket order) |
| **A refinement of `fleet_tree` re-opens the blocker M1 just closed** (T16-1) | med | **high** | deterministic: M1's three `fleet_tree` tests must pass **unchanged** — `test_fleet_tree_orders_by_state_not_by_creation`, `test_fleet_tree_applies_the_read_time_liveness_backstop`, `test_the_fleet_route_hands_the_page_an_ordered_tree` (T13) |
| **Wiring M2 into `controld.py` pushes it past ADR-1's 150-line cap** — it is **at** the cap today (T18-3) | **high** *(certain without Task 18)* | med | deterministic: `test_no_composition_root_file_exceeds_150_lines` (inherited) + `compose_tool_surface` extraction (T18) |
| **Subscribing `PostToolBatch` changes the user's `settings.json` and slows every hook** (principle 4; T18-2 is why M1 refused to do it in passing) | med | **high** | deterministic: installer dry-run diff against a throwaway settings file + `test_hookd_latency_under_10ms` (inherited, re-run) + the P13 sha256 guard on the real file (T18) |
| **This plan's repo facts go stale again under a concurrent builder** — it happened once mid-write, and again between r2 and r3 (`compose.py` appeared, `controld.py` 150 → 154) | **high** | med | manual: **step 0b**, five rows, **two asserted and three recorded**, in Progress notes before T1 (A6) |
| **C12's bound fires on every healthy turn** because `Stop` and `SessionEnd` are one `SignalKind` and the mark is read before the fold clears it — **two required tests contradicted each other at r2** | **high** *(certain without both guards)* | **high** | deterministic: `test_benign_auto_compact_is_not_context_exhausted` **and** `test_kill_during_compaction_is_context_exhausted` both green, plus `test_compaction_bound_requires_an_end_reason` and `test_auto_compact_mark_is_set_and_cleared` (**r3 BLOCKING 1**, T4 + T10) |
| **`handle_stop` is fully tested and never runs** — nothing constructs `StopLog` or resolves `log_dir` | **high** *(certain at r2)* | **high** | deterministic: `test_controld_constructs_the_stop_log_and_hands_it_to_the_hook_lane`, `test_a_real_stop_lands_a_record_under_logs_stops` (**r3 BLOCKING 2**, T18) + the live lane (T19) |
| **The tail read scans a 4 345-entry transcript on the single ingest thread**, delaying the next hook frame — the observer harming the observed | med | **high** | deterministic: `test_tail_read_is_bounded`, `test_truncated_window_is_flagged_and_counted` (**A4**, T3); the largest captured single entry is 410 665 B, so the 256 KiB window is sized against real data |
| **~96% of stops render a green `finished` chip that nothing counts**, so D34's trigger for building the LLM lane is absent from the product | **high** *(certain at r2)* | **high** | deterministic: `test_stop_verdict_counts_reports_low_confidence_completions`, `test_low_confidence_completions_are_counted_and_not_folded_into_unknown`, `test_low_confidence_completions_render_beside_the_unknown_rate` (**r3 BLOCKING 4 / DP10**) |
| **The golden lane's `unknown` rate is a majority** because 49 of 50 corpus sessions have no checked-in transcript, so acceptance clause 11 fails on day one for a fixture-set reason | **high** *(certain at r2)* | **high** | deterministic: composed fixtures + `test_composed_fixtures_name_their_captures`, and P-M2-14 states its population (**r3 BLOCKING 3**, T17) |
| **Untrusted `why` / action text reaches `innerHTML`** (§13) | med | **high** | deterministic: `test_no_unescaped_interpolation_in_frontend` (inherited) over the new files |
| **The fleet page reads a log** (D25's guardrail, K14) | low | **high** | deterministic: `test_no_read_tool_touches_a_log_path` — every `local_read` tool's handler is scanned for a `logs/` path |
| **`quota_paused` is built on a payload shape nobody ever captured** (K1) | **high** | med | manual checklist + `test_quota_rule_reads_only_the_notification_type` — the rule reads the **enum value only**, which `drift_check.py` verified byte-identical at 2.1.273; no payload field is read, and no resume time is displayed |
| **`stalled_pending_tool` has no fixture** (0 captures of `tool_use` at a `Stop`) | **high** | med | deterministic over a **synthetic tail built from real entries** (`test_held_tool_call_is_stalled_pending_tool`) + named evidence gap G-M2-3 and a `doctor` counter |

---

## Blocker protocol (explicit, per the user's standing instruction)

Unchanged from M1, and it is the reason an overnight run survives. A builder that hits a blocker
**marks it and moves to the next workable task. It does not stop the milestone.**

1. Write a line to **`docs/plans/2026-09-17-m2-BLOCKERS.md`** (append only, same shape as M1's):
   `T<id> · <one-line symptom> · <what was tried> · <what it blocks> · <suspected owner: evidence gap | decision gap | host gap | upstream bug>`.
2. If it is an **evidence gap** (a shape not in `data-schemas.md`), the entry **names the probe** that
   would close it. Do not guess the shape. Do not build on the guess.
3. If it is a **decision gap** (pressure against one of the 55 + D38.1), write the pressure in the
   four-part form this plan uses — decision · pressure · options · recommendation — and **do not apply
   the recommendation**.
4. Mark the task `BLOCKED` here, leave the partial work behind a failing test with
   `pytest.mark.xfail(strict=True, reason=…)` **naming the blocker id**, and pick up the next task
   whose `Dependencies` are all satisfied.
5. **A boundary rule firing is never a blocker and never earns an exemption** (K11). It is either a
   code-shape defect (fix the code) or a plan defect (a named plan change). Recording an exemption is
   a build failure by policy.

The dependency graph is deliberately shallow: after T1 there are **four independent tracks**
(schema · evidence · classification · surfaces), so a blocker in any one leaves three workable.

---

## Inherited blockers — what M2 owns, and what it does not

Read from `docs/plans/2026-09-16-m1-BLOCKERS.md` **after** M1's T18 ledger sweep (the file is now
70 KB and every earlier entry carries a disposition). Only entries still open are listed.

| Entry | Owner per M1's sweep | M2's disposition |
|---|---|---|
| **T18-2** — `PostToolBatch` is not in `SUBSCRIBED_EVENTS`, so T11-2's `TOOL_BLOCKED_BY_HOOK` / `TOOL_PERMISSION_REFUSED` counters are built, tested, correct and **can never fire** | **"T9/T18 → M2"**, by name | **DEFERRED past M2 (router decision, r3), and re-pointed rather than dropped.** M1's own reason for not doing it in passing is the reason M2 cannot either: subscribing changes what is written into the user's `settings.json`, and verifying that needs a real install against a real session, which **K3 forbids**. It goes to a milestone that can install hooks (M3 spawns sessions; M6 owns packaging), with M1's four-item checklist preserved verbatim. **M2 pays the debt in honesty:** `doctor` reports the counters as `idle — PostToolBatch is not subscribed (M1 blocker T18-2)`, asserted by a test so it cannot be quietly dropped. |
| **T18-3** — `controld.py` was *at* ADR-1's 150-line cap and is now **over it (154 lines; the boundary suite is RED)**; the next wiring change cannot be additive | **"M2"**, by name | **M2 owns it — Task 18.** `toolsurface/compose.py` **already exists** (51 lines — a remediation landed after r2), so the work is *verify and extend*, not *extract* (**A6, r3**). M2 adds the stop path's construction, a log directory and a `replay` tool to the composition root, and getting the boundary suite green is Task 18's first deliverable. |
| **T18-1** — `shepherd status` cannot see a running daemon's fleet; a second process has no fleet tools and must not open the store (§7 rule 3) | **M4 — decision gap** | **Not M2's**, and **DP9** explains why `shepherd replay` inherits the same gap and prints the same honest message rather than inventing the transport D38 assigns to M4. |
| **T15-1** — a tail SSE subscriber's one-instant window before its first event | open; M1's sweep says the fix is three coupled changes including `sse.js`'s reconnect path | **Not M2's.** M2 adds no subscriber and changes no reconnect path. Named so a builder touching `sse.js` for the rail (T16) does not half-fix it. |
| **T17-4** — `status` cannot say which source saw each row | **NOT APPLIED**; needs a `session` column + a projection field + a fold rule deciding what to write when both lanes touch one row | **Not M2's.** Recorded because M2 *does* add fold rules and a column, and the temptation to bundle it is real. The sweep's reason stands: a column saying "registry" for a row the hook path last wrote is worse than no column. |
| **T7b-2** — `claude agents --json` is a projection; the fallback is deliberately inert | evidence gap, probe named | **Not M2's.** |
| **T3/T4** — `MacHost` unverified (now including `peercred()`) | **open by design** (D55) | **Not a blocker**, expected state. |

**Three entries M2 must not re-open, because M1 closed them and M2 builds on the closure:**
**T11-3** (cross-repo `repos_touched`, applied at `HookLane._with_foreign_repos`) — heuristic 4 still
reads the tail, not `repos_touched`, for the reason DP3 gives, but the hole the old disposition warned
about is gone; **T16-1** (`fleet_tree` shipped); **BLOCKER-T6-1** (the fold identity columns, which are
why `HookLane` can hold no state between frames and why M2's stop lane may do the same).

## Evidence gaps — named here so BUILD does not discover them

K1 applies: the task's first step is a probe, or the behaviour ships **explicitly unverified and says
so**, counted.

| # | Gap | Effect on M2 | Disposition |
|---|---|---|---|
| **G-M2-1** | **`quota_*` notification payloads were never captured.** The four `quota_auto_resume_*` values exist in the binary enum `VAr` and were re-verified byte-identical at 2.1.273 by `drift_check.py`; **no payload of any of them exists.** | `quota_paused` and §8's action *"Resumes `<time>` — nothing to do"* have no captured time field. | The rule reads the **notification type only** — a capture-proven enum value — and reads **no payload field**. The action text degrades to `Quota pause — it resumes by itself` with **no time**, because no field for one has been seen. Counted on every occurrence. Probe that closes it: a real quota exhaustion, which cannot be provoked. |
| **G-M2-2** | **`crashed` needs an exit code that an attached session cannot give** (C13; pidfd probe: `waitid(P_PIDFD)` on a non-child is `ChildProcessError errno=10`). | §8's `crashed` row is **unreachable at M2**, which is attached-only. | An observed process exit with no preceding stop event → `stop_reason = unknown`, `why = "process exited; an attached session gives an exit time but no exit code (C13)"`, counted under `EXIT_CODE_UNOBSERVABLE`. **A test asserts `crashed` is never produced at M2.** It becomes reachable at M3 via tmux `pane_dead_status`. |
| **G-M2-3** | **No capture of `message.stop_reason = tool_use` at a `Stop`.** 26/26 corpus stops are `end_turn`; the 26 `tool_use` entries in the copies are all mid-turn. | `stalled_pending_tool` — the row §8 calls "likely a bug" — has no end-to-end fixture. | The rule ships, tested against a **tail assembled from real captured entries** (a real `tool_use` assistant entry as the final one), which is composition of captured data, not invented data. Counted in `doctor`. Probe that closes it: a TUI turn interrupted while a tool call is pending. |
| **G-M2-4** | **`killed` needs the `action_log`, which is M4.** | The row exists in the table and in the default-action table; nothing at M2 can produce it. | Written, total, unreachable, and a test asserts so. `replay` will fill it retroactively when M4 lands — which is the point of the log. |
| **G-M2-5** | **Five `StopFailure.error` values were never observed**: `oauth_org_not_allowed`, `account_on_hold`, `verification_required`, `overloaded`, `cloud_credential_error` (binary assignment counts 1, 1, 1, **0**, 1). | Five rows of the mechanical table rest on the binary enum, not on a capture. | Each row carries a `# UNVERIFIED (binary enum only)` comment citing the assignment count, exactly as `MacHost` does for its unverified values. `overloaded` additionally records **zero assignments** — the row is kept because the enum contains the value, and the measured note says a 529 arrives as `server_error`. |
| **G-M2-6** | **`derailed` has no mechanical detector.** §8's five heuristics contain none; detecting "believed it finished but did something else" needs intent. | `derailed` is **unreachable at M2** by construction. | Row exists, bucket and actions exist, a test asserts nothing at M2 produces it, and §8's `[why?]`-fires-the-LLM path is the one that will. This is the clearest single measure of what D34 deferred. |
| **G-M2-7** | **`blocked_external` sources 1 and 2 are both out of M2's reach** — source 1 is a tier-2 registered tool (M4), source 2 is `work_item.status_class` (M5). | Only heuristic 5 (blocked phrasing) can produce it, and it cannot know `waiting_on`. | The verdict carries `waiting_on = None`; §8's action `Chase <waiting_on>` degrades to `Chase — what it is waiting on is not recorded` with `kind = external`, `target = None`. Honest, and it is the row `replay` will most improve. |
| **G-M2-8** | **Engine version drift persists**: `data-schemas.md` pins shapes to `2.1.270`; this host runs `2.1.273`. | M2's enum surface is the part `drift_check.py` already covered. | **T1 step 0 re-runs `docs/probes/drift_check.py`** before any mapping code is written. All four enums M2 keys on — `SessionEnd.reason`, `SessionStart.source`, `StopFailure.error`, `Notification.type` — were **byte-identical as exact ordered literals** at the M1 run. A moved value is a blocker entry, not an assumption. |

---

## Codebase Reality Check (verified on this host, 2026-09-17)

Every row was checked by running the command, not recalled.

| Fact | How it was verified | Consequence for the plan |
|---|---|---|
| **M1 is complete and green.** M1's own T18 ledger sweep records the baseline: **443 passed, 1 skipped, 8 deselected** on `pytest -m "not live"`, **7 passed** on `pytest tests/e2e -m live`, `mypy --strict` clean over **61 files**. | read the sweep; re-counted 61 `.py` under `src/shepherd` | M2 edits a working, running system. Every `Consumes` below names a symbol that exists today. |
| **`src/shepherd/daemons/controld.py` moved three times during the writing of this plan: 150 lines (r2) → 154 and the boundary suite RED (early r3) → 148 and green (r3 reconciliation, ~20 minutes later).** `toolsurface/compose.py` appeared at 51 lines between r2 and r3. It wires the registered tools, two lanes, three threads and a shutdown. `[project.scripts]` registers `shepherd`, `shepherd-controld`, `shepherd-sessiond`; `[tool.setuptools.package-data]` ships `static/*` and `migrations/*.sql`. | `wc -l` ×3, `pytest tests/boundaries -q` ×2, `ls toolsurface/` | **A remediation lane is live in this repo and this row has a half-life measured in minutes** (DP6, **A6**). **Do not plan against the number — plan against the constraint:** whatever `controld.py` measures on the day, ADR-1's cap is 150 and M2 adds the stop path's construction plus two tools to it. **T18 verifies and extends `compose_tool_surface` (which exists); it does not extract it**, and it leaves the composition root with room, not merely under the line. This is why step 0b rows 1 and 4 are **RECORD**, not ASSERT. |
| **`src/shepherd/signals/hook_lane.py::HookLane` exists** — frame → signal → fold → store → stream, holding no state between frames and reading its prior back out of the database. | read it | **This is the stop lane's caller.** T11 consumes it rather than inventing a sibling orchestration (ADR-M2-7, revised at r2). |
| **`toolsurface/tools_m1.py::fleet_tree` already exists** (line ~176) and closed blocker T16-1: it projects `Store.fleet()` through `effective_state` and `fleet_sort_key`, grouped workspace → session, and `web/` reads `/api/fleet/tree`. | read it | **T13 extends it** with the bucket order and the stop fields; it does not create it. The claim "M2 closes T16-1" was **false** and is corrected. |
| **`toolsurface/tools_engine.py` exists** — `schema_status` and `engine_version`, closing T17-1 and T17-2. `drift_check.py --record <path>` now writes a real drift record and `doctor` exits non-zero on drift. | read it | Step 0's drift check is now a **shipped gate**, not a manual probe. M2 runs it through the tool that exists. |
| **`tests/e2e/` exists with a `live` pytest marker** (`pytest tests/e2e -m live` → 7 passed), and `tests/test_packaging.py` asserts every console entry point resolves to a real callable. | `ls tests/`, read `pyproject.toml` markers | **M2 has a live lane.** See Live Verification Strategy. |
| **`src/shepherd/logs/__init__.py` is 0 lines.** | `wc -l` | ADR-1 assigned `logs/` to M1 "daemon log only" and it was never written. **M2 owns `logs/` outright** — the stop log and the replay log are M2 deliverables anyway. |
| **Migration 001 already created all eight stop columns** — and its `stop_reason` `CHECK` lists **16** values, omitting `completed`/`incomplete`/`derailed`/`blocked_external`; its `decided_by` `CHECK` lists four, omitting `heuristic`. | read `001_m1_foundation.sql:115–123` | DP1 and DP2. Migration **002**, not an edit in place — see ADR-M2-4. |
| **The corpus is intact and measured**: 429 events, **50 sessions**, **26 `Stop`**, **23 `StopFailure`**, **50 `SessionEnd`**. | parsed every `events.jsonl` | T16's lane is buildable today against real data; the counts below are measured, not estimated. |
| **`StopFailure.error` distribution in the corpus**: `model_not_found` 14, `authentication_failed` 2, `server_error` 2, `rate_limit` 1, `invalid_request` 1, `billing_error` 1, `max_output_tokens` 1, `unknown` 1. **Eight of thirteen** enum values have a capture. | parsed | Eight mechanical rows are capture-proven. The other five are G-M2-5. |
| **`SessionEnd.reason` distribution**: `other` **47**, `clear` 2, `prompt_input_exit` 1. | parsed | DP8 is not theoretical: `other` is 94% of the corpus. |
| **A second real corpus exists**: `gap-fill/*/hooks.jsonl` — **37 sessions**, including `SessionEnd.reason` = **`resume` (1)** and **`logout` (1)**, 7 `PreCompact` / 3 `PostCompact`, and the kill-mid-compaction sequence. | parsed | These are **the only captures** of `resumed_elsewhere`, `logged_out` and `context_exhausted`. T16 extends the golden loader to both corpora. |
| **All 26 `Stop` captures resolve to `message.stop_reason = end_turn`; all 23 `StopFailure` captures resolve to `stop_sequence`** on the last `assistant` entry of the live transcript. | resolved each `transcript_path` and read the last `assistant` entry | DP7. It is why precedence is **error → reason → tail**. |
| **Only 1 of the 50 corpus sessions has a checked-in transcript copy**, though **424 of 429** payloads carry a `transcript_path` that still exists on this host. | parsed + `os.path.exists` | **A test must never read `/root/.claude/`.** T17's fixtures are the 19 checked-in copies plus tails composed from captured entries. A live-file read is a hermeticity failure, asserted by `test_no_fixture_reads_the_real_claude_dir`. **r3 BLOCKING 3: this is also why `COMPLETED`'s 26 fixtures are *composed*, and why P-M2-14's ceiling names its population** — a stop with no readable tail is `ABSENT` → `UNKNOWN`, so the naive lane would be a majority unknown by construction. |
| **All 26 `Stop` captures resolve to `end_turn` — but the measurement read `/root/.claude/`.** | ran it here, once, as a *planning* measurement | **The suite may not repeat it** (P-M2-15). The fact stands as evidence for DP7's precedence; it is **not** a fixture, and T17 says so. |
| **The 19 checked-in transcript copies** carry `message.stop_reason` ∈ `end_turn` 57, `tool_use` 26, `stop_sequence` 2; `tool_result.is_error` **true 4 / false 5 / absent 5**; `tool_use` names `Bash` 8, `Agent` 3, `Workflow` 1, **`Write` 2**. | parsed | DP3's heuristics 2–5 have real data at the tail. Heuristic 4's `Edit`/`Write` test has two positive `Write` cases and many negatives. |
| **`TaskCreated` 3 / `TaskCompleted` 2 across the whole corpus.** | parsed | Heuristic 1 has exactly **one** session with an open task. It is the strongest heuristic and the thinnest fixture — recorded, and T16 asserts it fires on that one session. |
| **`PostToolUseFailure` appears twice in 429 events.** | parsed | §8's heuristic 3 ("last 3 signals are `PostToolUseFailure` on the same tool") has **no** hook-path fixture — another reason DP3 puts it on the tail, where `is_error` blocks exist. |
| **No ADR directories exist** — `docs/adr/`, `docs/decisions/`, `docs/rfcs/` absent; no `*ADR*.md`. | `find` | The architecture of record is **§3's 55 decisions + D38.1**, treated as settled. M1's seven ADRs live inside its plan and are inherited. The ADRs below are new and additive. |
| **Thirteen boundary tests are live** and 54 mutation fixtures back them; emptying any one fails the suite. | `ls tests/boundaries/`, M1 progress notes | K11. Every M2 module is written to pass them **without a new exemption**. |
| **`store/db.py` is 535 lines**, cap 600; `engines/claude_code/transcript.py` is ~340. | `wc -l` | New SQL goes in `store/stops.py`; the tail reader goes in `engines/claude_code/transcript_tail.py`. Not style — the cap is an enforced test. |
| **`cli/` already has a `recompute` stub returning exit 2** ("a named M2 stub"); `tests/cli/conftest.py` builds the registry in a fixture; and `cli/main.register_local_reads` registers `schema_status`+`engine_version` **only when the registry is empty**, so a process composed by someone else keeps exactly that surface. | read all three | `replay` follows the identical shape, and **DP9** explains why it is a `controld`-registered tool rather than a second store opener. |
| **The tree changed under this plan.** `signals/fold.py` was modified at 00:58:50, five seconds before a verification command in this session; `tools_m1.py` at 00:41; `hook_lane.py` and `tools_engine.py` did not exist at 22:1x. | `ls -la --time-style` twice, forty minutes apart | **DP6.** A snapshot is not a guarantee. **Step 0b** below makes the first builder re-check the four mechanical rows rather than trust this table. |

**Technical-approach match.** The approach is the one M1 proved: pure functions at the unit seam, a
data table rather than a branch tree (ADR-6), `store/` verbs returning dataclasses (D33), consumers
through `invoke()` only (D35), stdlib everything. **Unstated infrastructure: none.** M2 adds no
dependency, no service, no environment variable and no network call — the LLM lane, which would have
added the first credential, is exactly what D34 defers.

---

## Plan-vs-spec and plan-vs-code gaps

Every place this plan does something the spec or the shipped code does not literally say.

| # | Spec/code says | Plan does | Why | Evidence |
|---|---|---|---|---|
| **N1** | §7 / migration 001: `decided_by ∈ {mechanical, model, declared, manual}` | five values, adding `heuristic` | D34 and §8 both say `decided_by='heuristic'`; the decision log outranks a data shape written before it | **DP1**; `orchestrator-platform.md:145`, `:1075` |
| **N2** | migration 001: `stop_reason` `CHECK` has 16 values | 20 values — the four completeness-split reasons added | §7 says "values in §8", and §8's split assigns them | **DP2**; `orchestrator-platform.md:1042–1047` |
| **N3** | §8 heuristics 2–5 read signal history | they read the **transcript tail** | D24 forbids an event store and names the transcript as the stop path's source | **DP3**; D24 |
| **N4** | §7: `next_actions` items are `{text, kind, target}` | `{text, kind, target, source}`, nine `kind` values | §8's ordering guarantee and its default table both require them | **DP5**; `orchestrator-platform.md:1130–1136`, `:1169` |
| **N5** | §8 has no row for `SessionEnd.reason = other` | it **defers**, a third outcome beside mapped and unmapped | 47/50 of the corpus; D46 names the omission | **DP8**; measured |
| **N6** | §8's completeness split has four rows and no "unsettled" row | **a null heuristic result is `completed` at confidence 0.5**, never `unknown` | §8's own replay example proves it: its changes are `unknown → stalled_pending_tool` (mechanical) and `completed → incomplete` / `completed → blocked_external` — so the pre-improvement state of a clean stop is `completed`, and `unknown` counts *unmapped mechanical* stops. A residue rule would make the corpus 98% unknown against §8's worked figure of 8.2% | `orchestrator-platform.md:1178–1191`; measured: 3 `TaskCreated` in 50 sessions |
| **N7** | §8: `overloaded → rate_limited` | row kept, annotated **zero assignments in the binary**; a 529 is `server_error` | D46's own correction | `data-schemas.md` §Enumerations |
| **N8** | §8: `crashed` = process exit ≠ 0 with no preceding stop | **unreachable at M2**; an observed exit with no stop event is `unknown` with the reason stated | C13: an attached session gives an exit time and never a code | **G-M2-2**; §Observed process exit (pidfd) |
| **N9** | §8: `context_exhausted` = `PreCompact{auto}` with no `PostCompact` before death | **bounded**: the most recent `PreCompact{auto}` must be followed by neither a `PostCompact` **nor a `Stop`** | C12, and `data-schemas.md` says so in those words: *"The rule needs a time bound"* | **C12**; §Auto compaction |
| **N10** | §12: `[why?]` fires the LLM verdict on demand | a **one-time note** that an API key enables it | §8's own no-credential paragraph specifies exactly this degrade | `orchestrator-platform.md:1094–1100` |
| **N11** | §16: M1 ships both daemons | **it does — `controld.py` landed mid-write.** M2 wires into it through `compose_tool_surface` (T18) because the file is *at* ADR-1's 150-line cap, and adds a live lane (T19) | **DP6**, **T18-3** | `wc -l src/shepherd/daemons/controld.py` → 150 |
| **N12** | ADR-1: `logs/` is L1, "M1: daemon log only" | `logs/` is built from scratch by M2 | the module is empty | `wc -l src/shepherd/logs/__init__.py` → 0 |
| **N13** | §7's `session` table has no column for a pending auto-compaction or a quota notice | **two nullable columns added**: `auto_compact_at TEXT`, `quota_notice_at TEXT` | D24 discards the event, and both facts must survive to the stop for §8's `context_exhausted` and `quota_paused` rows to be computable at all. Same shape as M1's M13/M16 widenings, and each is cleared by the next turn so neither accumulates | **DP-note in ADR-M2-4**; C12; §Auto compaction |
| **N14** | §8's `incomplete`/`derailed` row: "one item per `missing[]` entry **truncated to 3** · `Requeue with what's missing`" | truncated to **2**, then the `Requeue` item | 3 + 1 = 4, against D21's "**at most three**" and §7's "up to 3". Two parts of §8 disagree; the cap is the one D21 states as a decision, so the truncation yields (**A7, r3**) | §8's D21 block; §7 `next_actions` |
| **N15** | §8: `Re-authenticate <provider>` | `Re-authenticate`, no provider | **no captured field supplies one at M2.** `session.provider` is null on every attached session, and a blank or a guess in an action button is worse than a shorter true sentence (principle 5). M3 spawns with a known provider and the text takes it then (**A7, r3**) | §7 `session.provider`; §8's default table |

**Spot-check performed:** N6 was verified by re-reading §8's Replay block at `orchestrator-platform.md:1178–1191` — its three change lines are `unknown → stalled_pending_tool (31)`, `completed → incomplete (6)`, `completed → blocked_external (1)`, which is only consistent with a clean stop starting life as `completed`.

---

## Assumption ledger

`proven_by_code` means proven by a real capture or by a command run on this host.

| # | Assumption | Class | Basis / what would falsify it |
|---|---|---|---|
| A1 | The two corpora are byte-faithful hook stdin and replayable | `proven_by_code` | parsed both here: 429 + ~230 records, 0 malformed in `hooks/live/` |
| A2 | `Stop` has no `stop_reason` field | `proven_by_code` | 26/26 captures; absent from the CLI's own zod schema `xle` |
| A3 | The field names are `error`, `reason`, `source` | `proven_by_code` | captures; D41's four corrections |
| A4 | A 529 is `server_error`, a plain 400 is `unknown`, `overloaded` is never assigned | `proven_by_code` | mock-API captures + binary assignment counts (0 for `overloaded`) |
| A5 | `SessionEnd.reason = other` dominates | `proven_by_code` | 47/50 corpus, 11/16 gap-fill |
| A6 | `SessionEnd` is not guaranteed in `-p` | `proven_by_code` | missing in 4 runs; §SessionEnd variants |
| A7 | The last `assistant` entry carries the turn's ending | `proven_by_code` | 26/26 stops → `end_turn`; 23/23 failures → `stop_sequence` |
| A8 | `message.stop_reason` can be `null` on a non-final block | `proven_by_code` | §Transcript entry `assistant`: null 702/4345 |
| A9 | Transcript writes are whole-line appends | `proven_by_code` **(bounded)** | §Transcript JSONL: 34 observed changes, 0 violations, 0 partial tails — *evidence, not proof*. **Mitigation:** the reader skips malformed lines anyway (D25), so the bound does not matter |
| A10 | ~56% of entries are `user`/`assistant`; metadata clusters in the tail and is re-appended | `proven_by_code` | §Project directory layout, E25; M1's `ACTIVITY_ENTRY_TYPES` already encodes it |
| A11 | The slug is lossy and hash-suffixed past 200 UTF-16 units; glob for the session id | `proven_by_code` | §Project directory slug rule; M1's `locate_transcript` already does it |
| A12 | `PreCompact{auto}` with no `PostCompact` happens on healthy turns | `proven_by_code` | 2/3 turns real API, 1/2 mock (C12) |
| A13 | An attached session's exit code is unobtainable | `proven_by_code` | pidfd probe: `waitid(P_PIDFD)` → `ChildProcessError errno=10` |
| A14 | The registry sidecar carries a `needs_you` clearing signal | `proven_by_code` | the capture pair 9.194 s apart, same pid, `waiting`+`waitingFor` → `busy` |
| A15 | The four enums M2 keys on are unchanged at 2.1.273 | `proven_by_code` | `drift_check.py`, exact ordered literals; **re-run at T1 step 0** |
| A16 | **A null heuristic result means `completed`, not unknown** | `inferred` **(non-critical — it is a wiring choice a one-line change reverses, and `replay` re-derives every historical row either way)** | §8's replay example (N6). Falsified by: a spec amendment adding an "unsettled" row to the completeness split |
| A17 | **The quota notification type alone is enough to set `quota_paused`** | `inferred` **(non-critical — the row is unreachable in practice until a quota pause occurs, and it reads no payload field)** | binary enum `VAr`, drift-verified. Falsified by: a capture showing the type arriving on a session that is not paused |
| A18 | **A promise followed by a `tool_use` block in a later `assistant` entry is a kept promise** | `inferred` **(non-critical — heuristic 2 is one of five, it only ever moves a verdict from `completed` to `incomplete`, and `replay` corrects it)** | the tail's entry order. Falsified by: a capture where the promised tool ran *before* the promise text in entry order |

**Critical assumptions classified `inferred`: none.** The three `inferred` rows are each explicitly
non-critical with the reason stated.
**Confidence arithmetic:** 90 base − 0 (no critical inferred assumption) − 25 (Recommended Defaults
non-empty: RD1–RD9) = **65**.

---

## Differences from agreement

The agreement is the user's brief + §16's M2 scope. **Five differences, all additive or
decompositional, none reducing scope.**

| # | Agreement | This plan | Status |
|---|---|---|---|
| D-1 | §16 and the brief list M2's contents | all present, **plus migration 002 and two fold columns** (`auto_compact_at`, `quota_notice_at`) | **Addition**, forced by D24: the events that prove `context_exhausted` and `quota_paused` are discarded on arrival, so the fact must land on a column or the two rows are uncomputable. Flagged as gap N13. A reviewer who rejects the columns must also reject those two rows. |
| D-2 | The brief asks for "`replay`" | the replay **engine** + a `controld`-registered `ToolDef` + a CLI subcommand that inherits blocker T18-1's transport gap in a standalone process | **Clarification**, per **DP9**. Building the transport is M4's (D38's exporter); opening a second `Store` would be a second writer, which §7 rule 3 exists to stop. |
| D-3 | §16: "expandable stopped rows with action buttons" | buttons render for every `kind`; the six kinds whose capability is M3/M4 render **labelled and inert** | **Clarification** (RD6). §12 says "the row is never a dead end"; an unlabelled button that does nothing *is* a dead end. |
| D-4 | The brief: "7-bucket palette and its ordering" | **eight** rendered buckets — the seven plus `unclassified` for a stopped row with no verdict | **Addition** (principle 5). M1 wrote `stopped` rows that M2 never saw stop; colouring them green or red would be a lie. Sorted last, counted separately from `unknown`. |
| D-5 | The brief lists M2's deliverables | **plus** the two blockers M1's sweep assigned to M2 by name — **T18-2** (`PostToolBatch`) and **T18-3** (the 150-line cap) — as **Task 18** | **Addition.** T18-3 is forced: M2 adds wiring to a file with zero lines to spare. T18-2 is a choice, and the reason to take it is M1's own rule that a ledger entry must not quietly disappear; a reviewer may defer it, in which case M1's two refusal counters stay permanently idle and `doctor` should say so. |
| D-6 | The brief says "M2 builds directly on what M1 shipped" | revision 1 of this plan was written against a **stale snapshot** and asserted `controld.py` absent; revision 2 re-grounds every affected section and adds **step 0b** | **Correction**, recorded rather than silently fixed (**DP6**). The plan-review gate caught it; the four claims it invalidated are listed there by name. |

**Nothing in §16's M2 list is omitted or deferred.** The out-of-scope list contains only items §16
assigns to other milestones, plus D34's own deferral.

---

# LAYER 2 — EXECUTION CONTRACT LAYER

## Context references — read before starting (paths, not summaries)

| File | Why the builder must open it |
|---|---|
| `docs/specs/orchestrator-platform.md` **§8** | **The heart of M2.** The stop-reason table, the completeness split, the five heuristics, `next_actions[]` and its default table, Replay. Also §3 (55 decisions + D38.1), §4 (the palette), §7 (the stop columns, the logs layout), §12 (the rail, stopped rows, `[why?]`), §14 (lane 1). |
| `docs/specs/data-schemas.md` **Index (lines 11–144)** | Jump table. **Do not read front to back** — 6 063 lines. Each task names its sections. |
| `docs/specs/implementation-constraints.md` | All 38 lines. **C12, C13, C21 are M2's**; C7, C8, C9, C10, C11, C20 shape what M2 may read. |
| `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` | **ADRs 1–7 are inherited**, especially ADR-6 (the fold is a data table) and ADR-7 (threading). Its blocker protocol, its constraint keys and its Table A / Table B are what M2 extends. |
| `docs/plans/2026-09-16-m1-BLOCKERS.md` | The open entries M2 inherits; see the disposition table above. |
| `src/shepherd/signals/rules.py` | **Table B as shipped.** M2 appends rows; it does not restructure. Read the module docstring first — it states the three cross-cutting rules that are deliberately not in the table. |
| `src/shepherd/signals/hook_lane.py` | **The stop lane's caller** (T11). Its docstring states why the three impure rules live there and not in `fold()`. Do not move them. |
| `src/shepherd/daemons/controld.py` | The composition root — **154 lines at r3, over ADR-1's cap, and `tests/boundaries/test_composition_root.py` is failing on it**. Read it before wiring anything; T18 owns its growth and its first deliverable is getting that test green. |
| `src/shepherd/toolsurface/compose.py` | **Already exists (51 lines).** T18 *verifies and extends* it; it does not create it (A6). |
| `src/shepherd/toolsurface/tools_m1.py` | `fleet_tree` **already exists** here and already closed blocker T16-1. T13 extends it; read it before assuming otherwise. |
| `tests/e2e/` + the `live` marker in `pyproject.toml` | M1's live lane, 7 passing tests. T19 adds five. The default run is `pytest -m "not live"`. |
| `src/shepherd/engines/claude_code/normalise.py` | **Table A as shipped** — the only place engine vocabulary lives. M2 adds rows here and nowhere else. |
| `src/shepherd/core/{signals,states,fold_types,anomalies,stream}.py` | The closed vocabularies M2 extends: `SignalKind` (20), `SIGNAL_FIELD_KEYS` (11), `AnomalyKind` (append-only), `FoldDelta`, `SessionSnapshot`, `CLEARED`. |
| `src/shepherd/store/migrations/001_m1_foundation.sql` | The eight stop columns already exist, with two `CHECK`s that are too narrow (DP1, DP2). |
| `tests/boundaries/` (13 tests, 54 fixtures) + `tests/boundaries/_taint.py` | **K11/K12/K13.** Read `_taint.py` before writing anything in `signals/`: it follows the *value*, through aliases, not the syntax. |
| `tests/golden/corpus.py` | The loader M2 extends to the second corpus. Its `replay()` and `session_table()` are the shape T16 reuses. |
| `docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl` | Corpus 1 — 429 events, 50 sessions, 26 `Stop`, 23 `StopFailure`, 50 `SessionEnd`. |
| `docs/probes/2026-09-14-schemas/gap-fill/*/hooks.jsonl` | Corpus 2 — 37 sessions; **the only** captures of `SessionEnd.reason` = `resume` / `logout` and of death mid-compaction. |
| `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-*/pty-hooks.jsonl` + `results.json` | **A separate filename the `*/hooks.jsonl` glob does not match (A5, r3).** The observed-process-exit evidence C13 and G-M2-2 rest on lives here, and the loader must name it explicitly or `test_observed_exit_without_a_stop_event_is_honest_about_the_exit_code` has no fixture. |
| `docs/probes/2026-09-14-schemas/transcripts/copies/` | 19 real transcripts, read-only. The **only** legal transcript fixtures — never `/root/.claude/`. |
| `docs/probes/drift_check.py` | T1 step 0. ~30 lines, needs no live session. |
| `CLAUDE.md` | tmux safety. The user has live sessions on the `shepherd` socket. M2 spawns nothing, so this binds only if a builder reaches for a spike. |
| `/root/Shepherd/.venv/bin/{python,pytest,mypy}` | The only working toolchain. |

`docs/solutions/` does not exist in this repo; nothing to check there.

## Durability horizons

| Piece | Horizon | Consequence for effort |
|---|---|---|
| `core/stops.py` — `StopReason`, `Bucket`, `NextActionKind`, `StopEvidence`, `Verdict` | **stable** — the vocabulary every later milestone reads; M4's wake set and M5's verdict routing both key on it | worth precision; design the record twice (ADR-M2-1 does) |
| `engines/claude_code/stop_map.py` | **near-term-refactor** — it is the table `replay` exists to let you edit | keep it a data table with an `evidence` string per row, never branches |
| `signals/heuristics.py` | **near-term-refactor** — five rules that will be tuned from the `unknown` rate, and the LLM lane refines four of them | one row per heuristic, each a pure predicate over `StopEvidence` |
| `signals/stop_rules.py` — bucket map + `next_actions[]` defaults | **stable** shape, **near-term-refactor** contents | totality over `StopReason` is the invariant; the text is not |
| `logs/` — rotating JSONL + the stop record | **stable** — D25 makes it the truth `replay` reads, and the record format outlives every rule | version the record; a reader must tolerate an older one |
| `store/stops.py` + migration 002 | **stable** — forward-only, and 002 is the first migration to run over an existing schema | the three migration rules get their first real test here |
| `web/static/*.js` palette and rail | **near-term-refactor** — M3 adds terminal affordances, M5 adds the second chip | one render function per row type, no framework, no abstraction beyond that |
| `signals/verdict.py::classify_end_turn()` | **stable signature, session-only body** — D34's whole point | the signature is the artifact; the body is `return heuristic_result` |

## Test-seam selection

**The same three seams M1 chose, plus the e2e lane M1 already built** — M2 creates no *new* seam. The
ideal is one; three exist because three processes do, and the fourth is not a seam M2 introduces but a
lane M1 shipped (`tests/e2e/`, `live` marker, 7 passing tests) that M2 adds five tests to.

- **Unit seam — the classifier and the tail reader.** Pure functions:
  `(StopEvidence) → Verdict`, `(bytes) → TranscriptTail`, `(engine values) → StopReason | DEFERS | UNMAPPED`.
  **Both corpora and the 19 transcript copies attach here.** Fastest, most stable, and it is where the
  differentiator lives. This is §14 lane 1.
- **Integration seam — `toolsurface.invoke()`.** `fleet_tree`, the extended `fleet_summary` and
  `replay` are exercised through `invoke()` with a `tmp_path` store, exactly as `tests/cli/conftest.py`
  already builds one. Route tests and CLI tests attach here, never to an HTTP handler, so M4's gate
  lands under existing tests (D38).
- **Process seam — the UDS.** Untouched by M2 and therefore unextended, except that T18 re-runs the
  latency assertion across it after subscribing a 25th event. Recorded so nobody adds to it.
- **E2E lane (M1's, not a new seam) — `tests/e2e` under the `live` marker.** Five M2 tests attach: the
  three claims `tmp_path` cannot prove (the transcript append race at a real stop, the record across a
  real process boundary, `replay` inside the store-owning process) plus the settings-file guard. See
  **Live Verification Strategy**.

**The store gets a verb test, not a seam.** `apply_stop_verdict` is one `UPDATE` behind one verb
(D33); testing it means calling the verb against a real SQLite file in `tmp_path`, which is what
`tests/store/` already does.

**No new `Scripted*`.** M2 introduces no seam, so §14.2's rule does not fire. `ScriptedHost` is
reused unchanged where a host is needed at all.

## Behavior contract (critical_path requirement)

What M2 guarantees, in the form a test can hold it to. Each clause binds every task.

**C-M2-1 — The classifier is a pure function of one record.** For every `StopEvidence`,
`classify(evidence)` returns the same `Verdict` on every call, in every process, with no clock read,
no filesystem read, no network call and no store access. *(proven by P-M2-1, P-M2-2; T8)*

**C-M2-2 — Every stop reason is total and every verdict is actionable.** The bucket map and the
`next_actions[]` default table are total functions of `StopReason`. **A non-`completed` verdict never
carries an empty action list** — §14's literal words. *(P-M2-3; T6)*

**C-M2-3 — Unknown is counted, never hidden and never guessed.** An engine value no row claims
produces `stop_reason = unknown` **and** an anomaly. A value that decides nothing (`other`) produces a
**defer**, counted under its own kind. Neither is ever converted into a confident reason.
*(P-M2-4; T4)*

**C-M2-4 — No rule may reference `Stop.stop_reason`.** Not in `engines/`, not in `signals/`, not in
`store/`, not in a test fixture's expectation. *(D46; P-M2-5; T4)*

**C-M2-5 — `signals/` never learns an engine word.** No engine event name, no engine field name, no
`raw_kind` comparison, no whole-mapping read. The evidence record crossing the boundary is a frozen
dataclass of named typed fields — **never a mapping** — so K12's fail-closed rule has nothing to fire
on and nothing to hide behind. *(K12, K13; P-M2-6; T5, T6, T7, T8)*

**C-M2-6 — The observer still never harms the observed.** M2 reads the engine's transcript and writes
only under `$XDG_DATA_HOME/shepherd`. It never writes into `~/.claude`, never spawns a process, never
signals one. A transcript that is missing, truncated, half-written or unreadable degrades the verdict
and is counted; it never raises and never blocks a fold. *(principle 4; P-M2-7; T3)*

**C-M2-7 — A verdict is always reconstructible.** Every verdict written to a column was derived from a
record that was written to the stop log in the same operation, and re-running the current classifier
over that log reproduces the columns exactly. *(principle 2, D25; P-M2-8; T10, T11)*

**C-M2-8 — `replay` is idempotent and reviewable.** Running it twice over an unchanged rule set changes
nothing the second time, and every run writes a before/after diff **before** the run is trusted.
*(§8 Replay; P-M2-9; T11)*

**C-M2-9 — Nothing the UI renders reads a log.** Every `local_read` tool the page can call answers from
columns. `replay` reads the log and is not one of them. *(D25, K14; P-M2-10; T12)*

**C-M2-10 — The LLM lane is absent, not stubbed-and-wired.** `classify_end_turn()` is the one named
call site; there is no `Classifier` Protocol, no `Credentials` lookup, no prompt string, no model id
and no HTTP client anywhere in M2. *(D34; P-M2-11; T8)*

## Purity boundary map (critical_path requirement)

| Module | Pure? | What it may touch | Enforced by |
|---|---|---|---|
| `core/stops.py` | **pure** — types and constants only | nothing | `test_core_purity` (inherited: `core/` imports nothing above L1) |
| `engines/claude_code/transcript_tail.py` | **impure, read-only** — it opens files | one transcript path, read; never `~/.claude/settings.json` | `test_tail_reader_only_reads`; the K3 session guard in `tests/conftest.py` |
| `engines/claude_code/stop_map.py` | **pure** | nothing — engine values in, `StopReason` out | `test_stop_map_is_pure` (same input → same output, 200 cases) |
| `engines/claude_code/evidence.py` | **impure, read-only** — it calls the tail reader | the transcript, and the `SessionSnapshot` it is handed | `test_evidence_takes_its_clock_as_a_parameter` |
| `signals/stop_rules.py`, `signals/heuristics.py`, `signals/verdict.py` | **pure** | nothing. No clock, no path, no store | `test_classifier_reads_no_clock` (AST: no `datetime.now`, no `time.`, no `open(`) |
| `signals/stop_lane.py` | **impure orchestration** — the only M2 module that writes | an injected `Store`, an injected log writer, an injected publisher | it takes all three as parameters; `test_stop_lane_constructs_nothing` |
| `logs/jsonl.py`, `logs/stops.py`, `logs/replay.py` | **impure, file I/O** | a directory it is handed (ADR-2's rule: `logs/` receives its paths, never resolves them) | `test_logs_never_read_the_environment` |
| `store/stops.py` | **impure, SQL** | the connection `db.py` hands it | inherited `test_storage_boundary` |
| `toolsurface/tools_m2.py` | **impure, projection only** | an injected `Store` and clock | inherited `test_consumer_boundary` |

**`received_at` / `now` is always a parameter**, never a clock read — that is what makes the golden
lane byte-identical across processes, and M1's `new_ulid(now=…)` injected lane is already built for it.

## Provable properties (critical_path requirement)

| # | Property | How it is proven |
|---|---|---|
| **P-M2-1** | `classify(e) == classify(e)` for every evidence record in both corpora and for 500 mutated ones | `test_classify_is_deterministic` |
| **P-M2-2** | `classify` never raises — for any record, including every field null, absent, empty, oversized, or wrong-typed | `test_classify_never_raises` (500 mutations) |
| **P-M2-3** | `BUCKET_OF` and `DEFAULT_ACTIONS` are total over `StopReason`; `DEFAULT_ACTIONS[r]` is non-empty for every `r != COMPLETED`; `len(actions) <= 3` always | `test_every_stop_reason_has_a_bucket_and_actions`, `test_non_completed_verdict_never_has_an_empty_action_list`, `test_action_list_is_capped_at_three` |
| **P-M2-4** | For every value in the 13-member `error` enum and the 5-member `reason` enum, the map returns a `StopReason`, a `DEFERS` or an `UNMAPPED` — never `None`, never a raise; and every `UNMAPPED`/`DEFERS` emits exactly one anomaly | `test_stop_map_is_total_over_both_enums`, `test_unmapped_and_defer_are_counted` |
| **P-M2-5** | The literal `stop_reason` never appears as a **payload key read** anywhere in `src/shepherd/` | `test_no_rule_references_stop_reason` (AST, extended from M1's) |
| **P-M2-6** | `StopEvidence` and `Verdict` have no `Mapping` field and no field whose name is an engine spelling | `test_stop_evidence_has_no_mapping_field`, `test_no_engine_vocabulary_in_signals` (inherited, green with **no new exemption**) |
| **P-M2-7** | For 200 corrupted transcripts (truncated at every byte boundary of the last line, empty file, absent file, directory-instead-of-file, non-UTF-8 bytes) the tail reader returns a record and counts an anomaly | `test_tail_reader_never_raises` |
| **P-M2-8** | For every session in both corpora, the verdict written to the columns equals `classify(record_read_back_from_the_log)` | `test_columns_equal_the_replayed_log` |
| **P-M2-9** | `replay(replay(state)) == replay(state)` over both corpora | `test_replay_is_idempotent` |
| **P-M2-10** | No handler of a `local_read` `ToolDef` reaches a path under `logs/` | `test_no_read_tool_touches_a_log_path` (AST over every registered handler) |
| **P-M2-11** | `src/shepherd/` contains no model id, no `anthropic` import, no `Classifier` class and exactly **one** call site of `classify_end_turn` | `test_no_llm_lane_exists`, `test_classify_end_turn_has_one_call_site` |
| **P-M2-12** | `crashed`, `killed` and `derailed` are never produced by any M2 code path, over both corpora and 500 mutations | `test_unreachable_reasons_are_unreachable` — the honest form of G-M2-2/4/6 |
| **P-M2-13** | Every row of the stop map and every heuristic carries a non-empty `evidence` string naming a section that **exists** in `docs/specs/data-schemas.md` | `test_every_stop_rule_cites_an_existing_section` — the same mechanical enforcement of K1 that M1's `test_every_fold_rule_cites_an_existing_section` gives Table B |
| **P-M2-14** | The `unknown` rate is **< 20%** over the **stop-fixture population**: every stop record in both corpora, each paired with a tail (its own where one is checked in, a composed one otherwise). **The population is named because the ceiling is meaningless without it** — over raw corpus stops with no tails available the rate is a majority by construction, since 49 of 50 sessions have no checked-in transcript (**r3 BLOCKING 3**) | `test_corpus_unknown_rate_is_under_20_percent`, whose docstring states the population and whose fixture list is `load_stop_fixtures()` |
| **P-M2-15** | No test opens a path under `/root/.claude/` or `$HOME/.claude/` | `test_no_fixture_reads_the_real_claude_dir` |

## Edge-case catalogue (critical_path requirement)

| # | Case | Source | Handling |
|---|---|---|---|
| E-M2-1 | `Stop` arrives with **no** `StopFailure` and no `SessionEnd` (the normal turn end) | 26 captures | tail decides; `end_turn` → completeness split |
| E-M2-2 | `StopFailure` arrives with **no** `Stop` (`max_output_tokens`) | §Stop variants | `error` decides; the tail is not consulted |
| E-M2-3 | `SessionEnd` never arrives in `-p` | 4 runs | the `Stop`/`StopFailure` already classified; nothing is owed |
| E-M2-4 | `StopFailure` is **lost** at `-p` shutdown (a slow hook is killed) | C7, 2/2 | the session is left `stopped` with **no verdict** → `unclassified` bucket, counted. Never guessed |
| E-M2-5 | Two `Stop`s in one session (S18: `Stop`, injected prompt, `Stop`) | corpus | each is classified; the **later** verdict overwrites, and both records are in the log |
| E-M2-6 | A human rejects a permission prompt in the TUI → **no `Stop` at all** | I01 | nothing classifies; the session stays `needs_you` until another signal. Recorded, not invented |
| E-M2-7 | `PreCompact{auto}` on a healthy turn, followed by a normal `Stop` | C12, 2/3 turns | **not** `context_exhausted`: the bound requires no `PostCompact` **and** no `Stop` after it |
| E-M2-8 | Killed during compaction: `PreCompact{auto}` → `SessionEnd{other}`, no `PostCompact` | gap-fill capture | `context_exhausted`. The one positive fixture |
| E-M2-9 | `SessionEnd{resume}` — the same pane continues as a **different** `session_id` | gap-fill capture | `resumed_elsewhere`; §8's name is misleading (the spec says so) and the `why` text says "continued as a new session id" |
| E-M2-10 | `SessionEnd{logout}` | gap-fill capture | `logged_out` → `error` bucket → `Re-authenticate` (`reauth`) |
| E-M2-11 | The transcript's last line is half-written | D25, §Transcript JSONL | skipped and counted; the tail is one entry shorter |
| E-M2-12 | The transcript file does not exist | E26-class | tail is `ABSENT`; the mechanical reason still decides; `end_turn` cannot be established so the split does not run and the verdict is `unknown`, counted |
| E-M2-13 | The last `assistant` entry is a lone `thinking` block with `stop_reason: null` | §Transcript entry `assistant` | walk back to the most recent `assistant` entry with a non-null `stop_reason` within the tail window; if none, `ABSENT` |
| E-M2-14 | One API message split across several entries (same `message.id`, increasing `apiBlockIndex`) | §Transcript entry `assistant` | the final **text** is the concatenation of `text` blocks grouped by `message.id`; the tail groups before it reads |
| E-M2-15 | 44% of entries are neither `user` nor `assistant`, and metadata is **re-appended** so it clusters in the tail | E25, M1's `ACTIVITY_ENTRY_TYPES` | **filter by `type` first, then take 20.** A line-count tail returns metadata |
| E-M2-16 | A `user` entry that is a `<task-notification>` injected prompt, not a human one | C11, §Transcript entry `user` (`origin.kind`) | excluded from the tail's prompt view, exactly as M1 excludes it from `brief` |
| E-M2-17 | `tool_result` with `is_error: true`, whose tool name lives on the **assistant** entry that issued it | 4 observed | paired by `tool_use_id`; an unpairable error result is counted, not attributed |
| E-M2-18 | `message.model` is `<synthetic>` (client-generated, no API call) | §`<synthetic>` assistant | not a model, not a turn ending; excluded from the tail's ending resolution |
| E-M2-19 | The session id resolves to **two** transcript files (the slug is lossy) | §slug rule | `locate_transcript` sorts and takes the first — M1's shipped behaviour, unchanged, and the ambiguity is counted |
| E-M2-20 | `/clear` starts a **new** transcript file for a new session id | §Transcript JSONL | each session id globs to its own file; `cleared` classifies the old one |
| E-M2-21 | A stop log record written by a future `record_version` | D25 + forward compat | skipped and counted, never parsed optimistically |
| E-M2-22 | The stop log's daily file is already gzipped when `replay` runs | D25 | the reader handles `.jsonl` and `.jsonl.gz`; a gzip whose tail is truncated is skipped and counted |
| E-M2-23 | The data directory does not exist when the first stop arrives | M1's F16 | created with `0700` (ADR-2's mode), and a failure to create is counted — the **verdict still reaches the columns** |
| E-M2-24 | Two stops for two sessions in the same millisecond | ADR-7 | both go through the single writer thread; the log appends under one lock |
| E-M2-25 | A session in the log whose row no longer exists | replay | counted as orphaned; not an error, not a resurrection |
| E-M2-26 | `idle_prompt` flips an idle TUI to `needs_you` 60 s after `Stop` — **after** the session was classified | **C21** | `needs_you` outranks `stopped` (§8), so the row shows the rail; the **verdict is not erased**, and expanding the row still shows it. The two facts coexist because they answer different questions |
| E-M2-27 | `elicitation_url_dialog` cannot arrive over stdio; `agent_needs_input` was never observed | **C21** | both stay in the `needs_you` type set (§8 lists them) and are counted if they ever appear. No rule depends on either |
| E-M2-28 | A `why` string longer than 120 chars, or action text longer than 80 | §7, §8 | truncated at the boundary with `…`, and the **untruncated** text is in the log record. Asserted, because a column that silently exceeds its documented width is a lie a UI inherits |
| E-M2-29 | `next_actions` would exceed three | D21 | capped at 3 **after** the source ordering (`declared` > `llm` > `heuristic`) and the `kind`+`target` dedupe, so the cap never drops the best item |
| E-M2-30 | An observed process exit for a session that already has a verdict | pidfd | ignored; a stop that already classified is not re-classified by a later exit |
| **E-M2-31** | **`shepherd recompute` still prints "recompute lands in M2 … nothing in this build replays a session's history"** (`cli/main.py`) after M2 ships `replay` | **A2, r3** | T18 fixes the text. **`recompute` and `replay` are not the same command** — §7 says `shepherd recompute` rebuilds the stop columns *from the transcript plus the log*, while `replay` re-runs the classifier over *the log alone*. M2 ships `replay`; `recompute`'s transcript half needs a transcript that may be gone, so it stays a named stub — but one that says **"`replay` ships; `recompute`'s transcript half does not"**, never that M2 has not happened |

---

## Architecture Decision Records (inline, durable)

### ADR-M2-1: the classifier's input is **one immutable record**, designed twice

**Context.** §8's classifier needs facts from three places: the stop event's own metadata, the
session's folded counters, and the transcript. D24 forbids storing events; D25 says a stop record is
"a few KB: the stop metadata, the last assistant message, the task counts, and the verdict produced";
§8 says `replay` "re-runs the current classifier over each record". Those three sentences only fit
together one way, and getting the shape wrong makes `replay` impossible.

**First design (rejected — shallow).** `classify(stop_payload, session_row, transcript_path)`.
Three parameters, one of them a **path**. The classifier then reads the filesystem, so it is not pure,
cannot be replayed (the transcript may be gone, or may have grown), and the log would have to record
the path rather than the evidence — which is precisely the "an answer only we can remember" failure
principle 2 forbids. It is also shallow by the deletion test: inlining it moves no complexity, because
the complexity is all in the reading.

**Second design (chosen — deep).** **One frozen record, assembled once, at the stop, by the adapter.**

```python
classify(evidence: StopEvidence) -> Verdict
```

`StopEvidence` carries everything any rule may read: the neutral turn ending, the mechanical reason
the adapter derived, the last assistant text, the tail's tool ledger and failure pairs, the task
counts, the compaction and quota marks, and the identity of the session. It is **written to the log
verbatim** and read back by `replay`. The transcript is read **exactly once**, at the stop; `replay`
never touches it and therefore works months later, on a machine where `~/.claude` has been cleared.

**Rejected alternatives.** (a) A `Classifier` Protocol with a mechanical and a future LLM
implementation — **D34 forbids it by name**, and it would be D9's mistake with zero implementations.
(b) Passing the `Signal` itself — it is the fold's input, it carries `raw_kind`, and it would drag
engine vocabulary across the boundary. (c) A `Mapping[str, object]` evidence bag — K12 fails closed on
whole-mapping reads, so every rule would be a build failure; and a bag has no totality a test can check.

**Consequences.** Enables: purity (C-M2-1), replay (C-M2-7), a golden lane that is one function call
per fixture, and an LLM lane later that takes the *same* record with no plumbing change. Prevents: any
rule reading the filesystem, and any rule reading a field nobody declared. Requires: the record to be
**complete at assembly** — a field the classifier wants later must be added to the record *and* to its
version, which is a visible change rather than a silent new read.

### ADR-M2-2: the engine→reason map lives in the adapter; `signals/` owns everything downstream

**Context.** D46 keys the table on `StopFailure.error`, `SessionEnd.reason` and the transcript tail.
§5.0 and K13 forbid those names in `signals/`. See **DP4**.

**Decision.**

```
engines/claude_code/stop_map.py    engine values → StopReason | DEFERS | UNMAPPED   (+ evidence per row)
core/stops.py                      StopReason, Bucket, NextActionKind, TurnEnding, StopEvidence, Verdict
signals/stop_rules.py              StopReason → Bucket, and StopReason → default next_actions[]
signals/heuristics.py              StopEvidence → the completeness split
signals/verdict.py                 classify(evidence) -> Verdict, and classify_end_turn()
```

The adapter's map is **one table** — §8's table, legible in one screen, with one `evidence` citation
per row, and a precedence of **`error` → `reason` → tail** that is a property of the function, not of
the rows.

**Rejected.** (a) An exemption in `test_no_engine_vocabulary_in_signals` — K11. (b) A neutral
intermediate enum with one member per engine value — ADR-6's r5 note calls that a rename, not a
boundary. (c) The whole table in `signals/`, keyed on the neutral `failure_note` field M1 already
projects — tempting, because the field exists; rejected because the *values* are still the engine's
(`"rate_limit"`, `"max_output_tokens"`), and putting them in `signals/` is the same leak wearing a
neutral key. **The neutral key is not the point; the neutral vocabulary is.**

**Consequences.** Enables: swapping the engine edits exactly one file (§5.0's own test of the
boundary). Prevents: a `signals/` rule from ever branching on a Claude Code spelling. Requires: the
adapter to own `UNMAPPED` and `DEFERS` — so the counting of unknowns happens where the unknown is
first seen, which is also where its detail string can name the actual value (principle 5).

### ADR-M2-3: `TurnEnding` is a **narrowing**, not a rename

**Context.** `message.stop_reason` has four observed spellings plus `null`
(`end_turn` 57, `tool_use` 26, `stop_sequence` 2, `null` 702/4345 in user data). ADR-6's r5 note warns
that a neutral key which is the engine's spelling is a rename, not a boundary.

**Decision.** `core.stops.TurnEnding` has **five** members that are not one-to-one with the engine's:

| `TurnEnding` | from | meaning to a rule |
|---|---|---|
| `ENDED_TURN` | `end_turn` | the model chose to stop → run the completeness split |
| `HELD_TOOL_CALL` | `tool_use` | it stopped holding an unexecuted call → `stalled_pending_tool` |
| `HIT_TOKEN_CAP` | `max_tokens` | → `truncated` |
| `OTHER` | `stop_sequence`, **and anything unrecognised** | decides nothing; counted (DP7) |
| `ABSENT` | `null`, no transcript, no `assistant` entry in the window | decides nothing; counted (E-M2-12/13) |

The narrowing is real: two engine spellings collapse into `OTHER`, and three distinct *absences*
(null, missing file, empty window) collapse into `ABSENT` while each still emits its own anomaly kind.

**Rejected.** A `str` field carrying the raw value — it would put `"end_turn"` into `signals/`, and
more importantly it would let a future rule branch on a spelling nobody had verified.

**Consequences.** Enables: a total `match` in `signals/` over five members. Prevents: a fifth engine
spelling silently becoming a fifth behaviour — it becomes `OTHER`, counted, and the count is what tells
you to add a member.

### ADR-M2-4: migration **002**, not another edit of 001

**Context.** M1 twice amended `001_m1_foundation.sql` in place, justified explicitly by "migration 001
has never been applied anywhere but a dev database" *within that milestone*. M2 needs four schema
changes: two widened `CHECK`s (DP1, DP2) and two nullable columns (N13).

**Decision.** `002_m2_stop_verdicts.sql`, and `EXPECTED_SCHEMA_VERSION` becomes **2**.

**Rejected.** (a) Edit 001 again. It re-litigates a decision whose justification was milestone-local,
it breaks every dev database by checksum (§7 rule 1 — *refuse to start*), and it means the
forward-only rule still has never actually run. (b) Widen the `CHECK`s by dropping them. A `TEXT`
column with no constraint is how `stop_reason` becomes free-text.

**Consequences.** Enables: §7's three migration rules get their **first real exercise** — a second
migration applying over a first, a checksum mismatch refusing to start, and a future-schema database
refusing to start. That is worth more than the one-line convenience of editing 001. Prevents: a
silently diverging dev database. Requires: `store/migrate.py`'s `EXPECTED_SCHEMA_VERSION` to move, and
a test that 002 applies cleanly **over** a 001-shaped database rather than only onto an empty one.

**Note on SQLite and `CHECK`.** SQLite cannot alter a `CHECK` in place. 002 therefore uses the
documented twelve-step table rebuild for `session` (`PRAGMA foreign_keys=off`, create
`session_new`, copy, drop, rename, recreate the two indexes, `PRAGMA foreign_key_check`) inside the
one transaction the runner already opens. This is the single riskiest statement in M2 and it gets its
own test that every row, every index and every default survives.

### ADR-M2-5: the `unknown` rate counts **unmapped mechanical stops**, and a null heuristic is `completed`

> **Promoted to DP10 at revision 3.** This ADR records the *design*; **DP10** records that it is
> applied against D34's literal sentence, what that costs, and the one line that reverses it. Read
> DP10 first — an ADR is not the right home for a deviation from the decision log.

**Context.** §8 says the residue of the heuristics "lands as `unknown` and is counted", and also that
the `unknown` rate is "the tuning backlog". Read as *"a clean stop no heuristic could settle is
unknown"*, the corpus would be ~98% unknown (3 `TaskCreated` in 50 sessions), against §8's own worked
figure of 8.2% → 0.7%.

**Decision.** `unknown` is the **mechanical** table's residue — a `StopFailure.error` or turn ending no
row claims. A clean turn ending on which no heuristic fires is **`completed` at confidence 0.5**,
`decided_by = heuristic`, and §8's default table gives it `Review the diff` (`inspect`) because the
confidence is below 0.8. The fleet also reports **`unclassified`** — a stopped row with no verdict at
all — separately, so "we never saw this stop" is never disguised as "we classified it as fine".

**Evidence.** §8's own replay block: its changes are `unknown → stalled_pending_tool` (a *mechanical*
reclassification), `completed → incomplete` and `completed → blocked_external` (the split improving).
That is only consistent with a clean stop starting life as `completed`.

**Rejected.** (a) Residue → `unknown`. Makes the metric useless and paints the fleet red, since
`unknown`'s bucket is `error`. (b) Residue → a sixth bucket. §4 has seven and §16 says seven.

**Consequences.** Enables: the `unknown` rate to mean "rows I could improve by editing the mechanical
table", which is what `replay` acts on. Prevents: a green `finished` chip that claims verification it
does not have — confidence 0.5 carries an action, so the row is never a dead end. Requires: the
confidence threshold (0.8) to be **one named constant**, because it is the only number standing
between "quiet" and "noisy".

### ADR-M2-6: the stop log is **versioned**, and `logs/` receives its paths

**Context.** D25 makes the log the truth `replay` reads, for 90 days, across rule changes and code
changes. ADR-2 (inherited) says `store/` receives its paths and never resolves them; `logs/` is L1
beside it and the same reasoning applies verbatim.

**Decision.** Every record carries `record_version: int` as its **first** key. A reader that meets a
version it does not know **skips the record and counts it** — it never parses optimistically. The
writer is constructed with a directory; it never reads an environment variable, never asks a host and
never creates a path it was not given the parent of.

**Rejected.** (a) No version — the first evidence-field addition silently changes the meaning of every
older record. (b) A schema registry — six months of records and one field list do not need one.

**Consequences.** Enables: adding a field to `StopEvidence` without invalidating history; `replay` can
say "412 replayed, 37 changed, 9 skipped at version 1". Prevents: a half-parsed old record producing a
confident wrong verdict. Requires: the version to bump whenever a field is **removed or re-meant** —
adding an optional field does not, and the test says which is which.

### ADR-M2-7: the stop lane is one impure function with three injected collaborators

**Context (corrected at r2).** `fold()` is pure by contract. Something must nevertheless read a
transcript, write eight columns, append a log line and publish a stream event, in that order, exactly
once. M1's `signals/hook_lane.py::HookLane` **already performs the impure half of the hook path** —
registration, cwd re-binding, cross-repo attribution — and is called from `daemons/controld.py`, which
is **exactly at ADR-1's 150-line cap** (blocker T18-3). So the orchestration can neither live in the
composition root (no room, and ADR-1 forbids logic there) nor be invented beside `HookLane` (two
orchestrations of one path is the F9/T7b-1 mistake in a new costume).

**Decision.** `signals/stop_lane.py`:

```python
def handle_stop(evidence: StopEvidence, store: Store, stop_log: StopLog,
                publish: Callable[[StreamEvent], int]) -> Verdict: ...
```

All three collaborators are **parameters**. The function constructs nothing, opens nothing and
resolves no path. When T18 lands, the composition root passes the three it already owns and this
function does not change.

**Rejected.** (a) A `StopLane` class holding the three — one caller, no state between calls; the
prefactor question answers itself. (b) Putting it in `daemons/controld.py` — ADR-1 forbids logic in
the composition root, and the file is at its cap. (c) Making `fold()` do it — it would destroy the
purity the golden lane rests on. (d) **Putting the body inside `HookLane`** — tempting, since
`HookLane` is the caller; rejected because `HookLane` is 6.8 KB of hook-path composition with its own
tests, and a stop path folded into it could not be replayed or golden-tested on its own. **`HookLane`
calls `handle_stop`; it does not contain it.**

**Consequences.** Enables: the whole lane tested with a `tmp_path` store, a `tmp_path` log and a list
for `publish` — no process, no socket, no composition root. Prevents: a hidden clock or a hidden path.
Requires: the caller to already hold a `Store`, which `HookLane` does, having been handed one by
`controld`.

---

## Task list

**Notation.** Each task names its `data-schemas.md` sections. Validation levels per
`cc10x:verification`. **Every task inherits K1–K15**; the `Out-of-Scope Drift` line names only what is
specifically tempting *here*. `[UNVERIFIED]` marks a row that ships from the binary enum with no
capture (G-M2-5).

**Step 0, before Task 1 and before any mapping code exists:** run
`.venv/bin/python docs/probes/drift_check.py --record <data_dir>/drift.json` — M1's T17-2 made this a
real gate that `doctor` reads — and record the result in **Progress notes** below (G-M2-8). A moved
enum value is a blocker entry, not an assumption.

**Step 0b, immediately after, and it exists because this plan was invalidated once mid-write (DP6):**
re-check four mechanical rows of the Codebase Reality Check and record the answers beside the drift
result. Two minutes, and it is the difference between building against the repo and building against
a memory of it:

**Two rows are RECORDED (write down what you see), two are ASSERTED (a mismatch is a blocker entry).
The split is A6's point (r3):** the tree has a live remediation lane in it, and a plan that *asserts* a
line count is a plan that goes stale by the hour. Only the facts a task's design depends on are
asserted.

| # | Command | Kind | Expected / note |
|---|---|---|---|
| 1 | `wc -l src/shepherd/daemons/controld.py` | **RECORD** | Measured **150 → 154 (red) → 148 (green)** during the writing of this plan. **Any number is fine to find; write it down.** What T18 owes is *headroom*, not a particular count |
| 2 | `grep -n 'def fleet_tree' src/shepherd/toolsurface/tools_m1.py` | **ASSERT** | one hit. **T13 extends, never creates** — zero hits means the design is wrong, not the count |
| 3 | `ls src/shepherd/toolsurface/compose.py src/shepherd/signals/hook_lane.py src/shepherd/logs/` | **ASSERT** | `compose.py` present (**51 lines at r3 — it already exists; T18 verifies and extends, A6**); `hook_lane.py` present; `logs/` holds **only** an empty `__init__.py`, so T5 owns it outright. A non-empty `logs/` means someone else started it |
| 4 | `.venv/bin/pytest -m "not live" -q \| tail -3` | **RECORD** | M1's sweep baseline was 443 passed / 1 skipped; it was **red on the line caps** mid-r3 and **green again** at the r3 reconciliation. Write down what you get. **If it is red for a reason T18 does not own, that is a blocker entry before T1** |
| 5 | `grep -c 'PostToolBatch' src/shepherd/engines/claude_code/events.py` and the `SUBSCRIBED_EVENTS` length | **ASSERT** | **24 subscribed, `PostToolBatch` not among them.** T18-2 is deferred (r3) and `doctor` must say the refusal counters are *idle*; if it has been subscribed since, that decision has been overtaken and the `doctor` text is wrong |

**An asserted row that disagrees is a blocker entry before T1 starts**, not a surprise discovered at
T13. **A recorded row never blocks** — it is the evidence that the next reader is looking at the same
tree this plan was written against.

---

### Task 1: `core/stops.py` — the stop vocabulary

**Objective:** one L1 module holding every type the rest of M2 speaks in, so `engines/`, `signals/`,
`store/`, `logs/` and `toolsurface/` all import **downward** and none of them defines a second copy
(the F9/BLOCKER-T7b-1 lesson: two structurally identical types is a type split `mypy` only catches at
the call site that mixes them).

**Files/Surfaces:**
- `src/shepherd/core/stops.py` — new
- `tests/test_core_stops.py` — new

**Dependencies:** none (after step 0).

**Allowed Scope:** types, enums, frozen dataclasses and constant tables **only**. No logic, no I/O,
no imports above L1, and no import of `shepherd.signals` or `shepherd.engines` (inherited
`test_core_purity`). The bucket **map** and the action **table** are T7's — this module holds the
vocabulary they are total over.

**Out-of-Scope Drift:** writing `BUCKET_OF` or `DEFAULT_ACTIONS` here (T7). Adding a `Classifier`
Protocol (D34 forbids it). Adding a confidence *policy* — the threshold constant lives here, the
decision that uses it is T9's. Naming a model or a prompt (P-M2-11).

**Contents, exactly:**

| Symbol | Members / fields | Notes |
|---|---|---|
| `StopReason(StrEnum)` | **20**: the 16 mechanical (`RATE_LIMITED`, `QUOTA_PAUSED`, `AUTH_FAILED`, `ACCOUNT_BLOCKED`, `BAD_REQUEST`, `SERVER_ERROR`, `TRUNCATED`, `STALLED_PENDING_TOOL`, `CRASHED`, `KILLED`, `CONTEXT_EXHAUSTED`, `USER_EXITED`, `CLEARED`, `LOGGED_OUT`, `RESUMED_ELSEWHERE`, `UNKNOWN`) + the 4 completeness (`COMPLETED`, `INCOMPLETE`, `DERAILED`, `BLOCKED_EXTERNAL`) | Values are the §8 spellings verbatim, because migration 002's `CHECK` lists them. **`StopReason.CLEARED` is not `core.fold_types.CLEARED`** (the empty-string clear sentinel) — different namespaces, and a module that needs both imports the module, not the name. |
| `Bucket(StrEnum)` | **8**: §4's seven (`RUNNING`, `NEEDS_YOU`, `FINISHED`, `UNFINISHED`, `BLOCKED`, `PAUSED`, `ERROR`) + `UNCLASSIFIED` | D-4. `UNCLASSIFIED` is a stopped row with no verdict — never green, never red. |
| `PALETTE: Mapping[Bucket, BucketStyle]` | `BucketStyle(colour: str, glyph: str, label: str, who_acts: str)` | §4, verbatim, **colour *and* glyph for all eight** so amber/red survives colourblindness and greyscale. `UNCLASSIFIED` is grey `#9CA3AF`, glyph `?`, "not classified". |
| `BUCKET_ORDER: tuple[Bucket, ...]` | `needs_you → error → unfinished → running → paused → blocked → finished → unclassified` | **§12's order for its first seven entries, then ours.** §12's eighth entry is `idle`, which is **not** a `Bucket`: M1's D-2 already resolved `idle` as a *workspace-level* rendering (a workspace whose sessions are all stopped), not a session state. `unclassified` takes the last slot because a row we could not classify should never outrank one we could. **Stated rather than called "verbatim" (A1, r3)** — §12's list and this tuple are not the same list, and saying so is cheaper than a reader discovering it. **`blocked` below `running` is deliberate** and *is* verbatim — it is real, it is visible, it is not yours to act on. |
| `TurnEnding(StrEnum)` | `ENDED_TURN`, `HELD_TOOL_CALL`, `HIT_TOKEN_CAP`, `OTHER`, `ABSENT` | ADR-M2-3. A narrowing, not a rename. |
| `DecidedBy(StrEnum)` | `MECHANICAL`, `HEURISTIC`, `MODEL`, `DECLARED`, `MANUAL` | **DP1**. `MODEL`/`MANUAL` exist and nothing at M2 writes them. |
| `NextActionKind(StrEnum)` | **9**: `RETRY`, `RESUME`, `RESPAWN`, `INSPECT`, `EXTERNAL`, `REAUTH`, `ESCALATE`, `REQUEUE`, `NONE` | **DP5**. §8's D21 list, which is the one the default table uses. |
| `ActionSource(StrEnum)` | `DECLARED`, `LLM`, `HEURISTIC` | The ordering guarantee's rank; `DECLARED` > `LLM` > `HEURISTIC` (§8). |
| `NextAction` | `text: str`, `kind: NextActionKind`, `target: str \| None`, `source: ActionSource` | frozen. `text` ≤ 80 chars — **asserted**, not hoped (E-M2-28). |
| `ToolUseRef` | `tool_use_id: str`, `name: str`, `entry_index: int` | from the tail; `name` is the tool's own name (`Bash`, `Write`), which is API vocabulary, not hook vocabulary |
| `ToolFailure` | `tool_use_id: str \| None`, `name: str \| None`, `entry_index: int` | an `is_error` result, paired where possible (E-M2-17) |
| `TranscriptTail` | `ending: TurnEnding`, `last_assistant_text: str \| None`, `entry_count: int`, `tool_uses: tuple[ToolUseRef, ...]`, `failures: tuple[ToolFailure, ...]`, `promise_followed_by_tool_use: bool \| None`, `skipped_lines: int`, **`truncated: bool`** | frozen, **no mapping field** (P-M2-6). `promise_followed_by_tool_use` is `None` when there was no promise to judge. `truncated` is A4's bounded-window flag: the tail is honest about being short. |
| `StopEvidence` | `record_version: int`, `session_id`, `engine_session_id`, `received_at`, `mechanical: StopReason \| None`, `mechanical_detail: str \| None`, `tail: TranscriptTail`, `tasks_total: int`, `tasks_done: int`, `brief: str \| None`, `auto_compact_pending: bool`, `quota_notice: bool`, `process_exit_observed: bool`, `exit_code: int \| None` | frozen. **The classifier's whole input** (ADR-M2-1). `mechanical is None` means the adapter deferred to the tail. |
| `Verdict` | `stop_reason: StopReason`, `bucket: Bucket`, `why: str`, `confidence: float`, `decided_by: DecidedBy`, `next_actions: tuple[NextAction, ...]`, `waiting_on: str \| None`, `missing: tuple[str, ...]` | frozen. `why` ≤ 120 chars, asserted. `waiting_on` is `None` at M2 (G-M2-7). |
| `CONFIDENT_ENOUGH: float` | `0.8` | ADR-M2-5. §8's "*(empty when confidence ≥ 0.8)*". **One named constant** — it is the only number between a quiet fleet and a noisy one. |
| `HEURISTIC_COMPLETED_CONFIDENCE: float` | `0.5` | ADR-M2-5. Deliberately below the threshold, so a clean stop still carries `Review the diff`. |
| `WHY_MAX: int` / `ACTION_TEXT_MAX: int` / `MAX_ACTIONS: int` | `120` / `80` / `3` | §7, §8, D21 |
| `STOP_RECORD_VERSION: int` | `1` | ADR-M2-6 |

**Expected Artifacts:** one module, ≤ 300 lines, no logic.
**Required Checks:**
`test_stop_reason_has_twenty_members`,
`test_every_bucket_has_a_colour_and_a_glyph` (all 8, both non-empty, colours distinct),
`test_bucket_order_is_total_over_bucket` (every member appears exactly once),
`test_blocked_sorts_below_running` (§12, by index),
`test_turn_ending_has_five_members_and_no_engine_spelling` (AST: no member *value* equals `end_turn`/`tool_use`/`max_tokens`/`stop_sequence` — ADR-M2-3's narrowing is checkable),
`test_stop_evidence_has_no_mapping_field` (P-M2-6 — introspect `__annotations__`; a `Mapping`/`dict` field fails),
`test_next_action_text_is_capped`, `test_verdict_why_is_capped` (E-M2-28),
`test_core_purity` (inherited — this module imports nothing above L1).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/test_core_stops.py tests/boundaries -q && .venv/bin/mypy --strict src/shepherd`.
**Exit Criteria:** nine pass; `mypy --strict` clean; all 13 boundary tests still green with **no new exemption**; file under 600 lines.
**Test Seams:** unit.

**Consumes:** none.
**Produces:**
```python
class StopReason(StrEnum): ...        # 20 members, §8 spellings
class Bucket(StrEnum): ...            # 8 members
class TurnEnding(StrEnum): ...        # ENDED_TURN HELD_TOOL_CALL HIT_TOKEN_CAP OTHER ABSENT
class DecidedBy(StrEnum): ...         # MECHANICAL HEURISTIC MODEL DECLARED MANUAL
class NextActionKind(StrEnum): ...    # 9 members
class ActionSource(StrEnum): ...      # DECLARED LLM HEURISTIC
@dataclass(frozen=True) class BucketStyle: colour: str; glyph: str; label: str; who_acts: str
@dataclass(frozen=True) class NextAction: text: str; kind: NextActionKind; target: str | None; source: ActionSource
@dataclass(frozen=True) class ToolUseRef: tool_use_id: str; name: str; entry_index: int
@dataclass(frozen=True) class ToolFailure: tool_use_id: str | None; name: str | None; entry_index: int
@dataclass(frozen=True) class TranscriptTail:
    ending: TurnEnding; last_assistant_text: str | None; entry_count: int
    tool_uses: tuple[ToolUseRef, ...]; failures: tuple[ToolFailure, ...]
    promise_followed_by_tool_use: bool | None; skipped_lines: int
    truncated: bool                     # A4 — the bounded window was hit
@dataclass(frozen=True) class StopEvidence:
    record_version: int; session_id: str; engine_session_id: str | None; received_at: str
    mechanical: StopReason | None; mechanical_detail: str | None; tail: TranscriptTail
    tasks_total: int; tasks_done: int; brief: str | None
    auto_compact_pending: bool; quota_notice: bool
    process_exit_observed: bool; exit_code: int | None
@dataclass(frozen=True) class Verdict:
    stop_reason: StopReason; bucket: Bucket; why: str; confidence: float
    decided_by: DecidedBy; next_actions: tuple[NextAction, ...]
    waiting_on: str | None; missing: tuple[str, ...]
PALETTE: Mapping[Bucket, BucketStyle]
BUCKET_ORDER: tuple[Bucket, ...]
CONFIDENT_ENOUGH: float                  # 0.8
HEURISTIC_COMPLETED_CONFIDENCE: float    # 0.5
WHY_MAX: int; ACTION_TEXT_MAX: int; MAX_ACTIONS: int   # 120, 80, 3
STOP_RECORD_VERSION: int                 # 1
```

---

### Task 2: migration 002 and the stop verbs

**Objective:** make the eight stop columns writable and readable through D33 verbs, and give §7's
three migration rules their first real exercise (ADR-M2-4).

**Files/Surfaces:**
- `src/shepherd/store/migrations/002_m2_stop_verdicts.sql` — new
- `src/shepherd/store/migrate.py` — `EXPECTED_SCHEMA_VERSION` 1 → 2
- `src/shepherd/store/stops.py` — new: the stop SQL and its row→dataclass (keeps `db.py` under the cap; it is at 535/600)
- `src/shepherd/store/db.py` — three thin verbs delegating to `store/stops.py`
- `src/shepherd/store/models.py` — `Session` and `FleetRow` gain the stop fields
- `tests/store/test_stop_verbs.py`, `tests/store/test_migration_002.py` — new

**Dependencies:** T1.

**Allowed Scope:** the four schema changes below and three verbs. Nothing else touches `store/`.

**Out-of-Scope Drift:** editing `001_m1_foundation.sql` (ADR-M2-4). Adding an index — §7's index list
is closed and the stop counts run over tens-to-hundreds of rows; if a measurement later says
otherwise, that is a plan change with a number attached. Exposing SQL, a cursor or a `sqlite3.Row`
past the package (D33). Writing a `Store` Protocol (D26/D33 — the named trigger has not fired).

**Migration 002 does exactly four things:**

1. Widen `stop_reason`'s `CHECK` from 16 to **20** values (DP2 / gap N2).
2. Widen `decided_by`'s `CHECK` from 4 to **5**, adding `heuristic` (DP1 / gap N1).
3. Add `auto_compact_at TEXT` — the timestamp of the most recent `PreCompact{auto}`, cleared by a
   `PostCompact` or by a `Stop` (C12's bound; gap N13).
4. Add `quota_notice_at TEXT` — the timestamp of the most recent quota notification, cleared by the
   next turn (G-M2-1; gap N13).

Because SQLite cannot alter a `CHECK`, (1) and (2) use the documented twelve-step table rebuild for
`session` inside the runner's existing transaction: `PRAGMA foreign_keys=off`, create `session_new`
with the widened constraints **and** the two new columns, `INSERT INTO session_new SELECT …` naming
every column explicitly, `DROP TABLE session`, `ALTER TABLE session_new RENAME TO session`, recreate
`ix_session_fleet` and `ux_session_engine_id`, `PRAGMA foreign_key_check`. **This is the riskiest
statement in M2** and Required Checks below hold it to every row, every index and every default.

**Three verbs (D33 — verbs, dataclasses, transactions inside):**

```python
def apply_stop_verdict(self, session_id: str, verdict: Verdict, ended_at: str,
                       exit_code: int | None) -> Session: ...
def stop_verdict_counts(self) -> StopCounts: ...
def sessions_for_replay(self, since: str | None) -> list[ReplayTarget]: ...
```

`StopCounts` carries `by_reason: Mapping[str, int]`, `classified: int`, `unclassified: int`,
`unknown: int` and **`completed_low_confidence: int`** — enough for `unknown_rate`, the `unclassified`
count and **D34's tuning signal** (DP10, r3 BLOCKING 4) to be computed by the caller without a second
query, and **not** enough for a caller to reconstruct a query. `completed_low_confidence` counts rows
with `stop_reason = 'completed' AND confidence < 0.8`: **the cohort D34 calls the residue**, which
revision 2 rendered as a green chip and counted nowhere.

**Expected Artifacts:** a second migration that applies over a first; three verbs; two widened models.
**Required Checks:**
`test_002_applies_over_001` (build a 001 database, insert a session with every column populated,
migrate, assert **every value survives**, both indexes exist, `foreign_key_check` is empty),
`test_002_widens_both_checks` (insert `stop_reason='derailed'` and `decided_by='heuristic'` — both
rejected before, both accepted after),
`test_checksum_mismatch_refuses_to_start` (§7 rule 1 — edit an applied migration's bytes, assert
`MigrationRefused`),
`test_future_schema_refuses_to_start` (§7 rule 2 — record version 3, assert refusal),
`test_apply_stop_verdict_writes_all_eight_columns` (round-trip including `next_actions` JSON),
`test_next_actions_roundtrips_as_a_whole_value` (read back whole; never queried into — §7's rule),
`test_apply_stop_verdict_is_the_only_stop_writer` (AST: no other module contains an `UPDATE session
SET stop_`),
`test_stop_verdict_counts_separates_unknown_from_unclassified` (ADR-M2-5),
`test_stop_verdict_counts_reports_low_confidence_completions` (**DP10 / r3 BLOCKING 4** — the residue
D34 wants counted; a `completed` at 1.0 must **not** be in it),
`test_sessions_for_replay_returns_dataclasses` (D33 rule 2 — no `sqlite3.Row` escapes),
`test_no_source_file_exceeds_600_lines` (inherited — `db.py` must stay under; this is why
`store/stops.py` exists).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/store tests/boundaries -q`.
**Exit Criteria:** ten pass; every pre-existing `tests/store/` test still passes **unchanged** (the
rebuild is invisible above the verb); `mypy --strict` clean.
**Test Seams:** integration (a real SQLite file in `tmp_path`).

**Consumes:** `Verdict`, `StopReason`, `Bucket`, `DecidedBy`, `NextAction` (T1); `Store`,
`open_store(db_path: Path) -> Store`, `Session`, `FleetRow`, `EXPECTED_SCHEMA_VERSION`,
`migrate(db_path: Path, migrations_dir: Path | None = None) -> int`,
`read_schema_version(db_path: Path) -> int` (M1, shipped).
**Produces:**
```python
EXPECTED_SCHEMA_VERSION = 2
@dataclass(frozen=True) class StopCounts:
    by_reason: Mapping[str, int]; classified: int; unclassified: int; unknown: int
    completed_low_confidence: int        # DP10 — D34's tuning signal, made visible
@dataclass(frozen=True) class ReplayTarget:
    session_id: str; engine_session_id: str | None; stop_reason: str | None; outcome: str | None
class Store:
    def apply_stop_verdict(self, session_id: str, verdict: Verdict, ended_at: str,
                           exit_code: int | None) -> Session: ...
    def stop_verdict_counts(self) -> StopCounts: ...
    def sessions_for_replay(self, since: str | None) -> list[ReplayTarget]: ...
# Session and FleetRow gain:
#   stop_reason: str | None; outcome: str | None; why: str | None; confidence: float | None
#   decided_by: str | None; next_actions: tuple[NextAction, ...]; exit_code: int | None
#   auto_compact_at: str | None; quota_notice_at: str | None      (Session only)
```

---

### Task 3: the transcript tail reader

**Objective:** turn a real Claude Code transcript into a neutral `TranscriptTail` — the one place the
engine's on-disk format is read for classification, and the source of four of the five heuristics
(DP3).

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/transcript_tail.py` — new (a separate module from
  `transcript.py`, which is ~340 lines and owns the subagent rollup; principle 6 and the 600-line cap)
- `tests/engines/test_transcript_tail.py` — new

**Dependencies:** T1.

**data-schemas.md sections:** §Transcript entry: common envelope · §Transcript entry: `assistant` ·
§Transcript entry: `<synthetic>` assistant · §Transcript entry: `user` · §Transcript entry:
`attachment` · §Project directory layout · §Project directory slug rule · §Transcript JSONL:
append-only and whole-line writes · §Compaction entries.

**Allowed Scope:** reading one transcript path and projecting it. **Read-only** — this module opens
nothing for writing and touches no path it was not handed.

**Out-of-Scope Drift:** reading `~/.claude/settings.json` or anything outside the given path.
Reversing the project-directory slug (it is lossy and hash-suffixed past 200 UTF-16 units — **glob for
the session id**, and `locate_transcript` already does). Reading subagent transcripts (T13's job at M1,
already shipped). Returning an engine spelling in any field (ADR-M2-3). Caching.

**The eight rules this reader obeys, each from a capture:**

1. **Filter by entry `type` first, then take the last `TAIL_ENTRIES` (20).** Only ~56% of lines are
   `user`/`assistant`, metadata is **re-appended** so it clusters in the tail, and a line-count tail
   returns bookkeeping (E25, E-M2-15). M1's `ACTIVITY_ENTRY_TYPES` already names the two types.
2. **Skip malformed lines and count them** (`skipped_lines`); never raise (D25, E-M2-11).
3. **Group `assistant` entries by `message.id`** before reading text: one API message is split across
   entries, one per content block, with a repeated `usage` and an increasing `apiBlockIndex`
   (E-M2-14). `last_assistant_text` is the concatenation of the `text` blocks of the **last** group.
4. **Resolve `ending` from the last group with a non-null `message.stop_reason`**, walking back within
   the window; `null` throughout → `ABSENT` (E-M2-13). Map per ADR-M2-3; **anything unrecognised is
   `OTHER`, counted**, never guessed (DP7).
5. **Exclude `<synthetic>` entries** from the ending resolution — client-generated, no API call, not a
   turn ending (E-M2-18).
6. **Collect `tool_use` blocks** into `tool_uses` with their `tool_use_id`, `name` and entry index —
   this is heuristic 4's whole input (`Edit`/`Write` count).
7. **Collect `tool_result` blocks with `is_error: true`** into `failures`, pairing each back to its
   `tool_use` by `tool_use_id` for the name; an unpairable one keeps `name=None` and is counted
   (E-M2-17). This is heuristic 3's input.
8. **`promise_followed_by_tool_use`**: if the last assistant group's text matches the promise
   vocabulary, `True` when any later `assistant` entry in the window carries a `tool_use` block,
   `False` when none does, `None` when there was no promise. The *matching* is T8's; this reader
   provides the ordering fact. (A18 — non-critical, and `replay` corrects it.)

**A bounded read, because this runs on the ingest thread (A4, r3).** Revision 2 said "filter by type,
then take the last 20", which is a **full-file scan per stop** — against user transcripts of **4 345
assistant entries**, on the **single** ingest thread `controld` runs (`controld.py`: one `ingest`
thread calls `HookLane.apply` for every frame). A slow read there delays the next hook's frame, and
"the observer never harms the observed" (C-M2-6, principle 4) is the one clause M2 may not trade.

**The rule:** read the **last `TAIL_BYTES` (256 KiB)** of the file, discard the first partial line,
then filter by type and take the last 20. If the window was truncated — i.e. the file is larger and
the first byte read was not the file's first byte — set `truncated=True` and **count it**. The
correctness cost is bounded and visible: a transcript whose last 20 `user`/`assistant` entries do not
fit in 256 KiB yields a shorter tail, which degrades a heuristic rather than inventing one. The one
captured single-entry outlier is **410 665 bytes** (§Transcript JSONL: "one line of 410665 bytes
appeared whole"), so the window is sized to hold more than one such line and the truncation counter is
not decorative.

**Expected Artifacts:** `read_tail(path, limit=TAIL_ENTRIES) -> TranscriptTail`, plus a re-export of
M1's `locate_transcript` so callers have one import.
**Required Checks:**
`test_tail_filters_by_entry_type_before_counting` (against a copy whose tail is metadata),
`test_malformed_trailing_line_is_skipped` (append half a line; assert it is skipped and counted),
`test_tail_reader_never_raises` (**P-M2-7**: 200 corruptions — truncate the file at every byte of its
last line, empty file, absent file, a directory, non-UTF-8 bytes),
`test_blocks_of_one_message_are_grouped` (assert against a real `apiBlockIndex` > 0 capture),
`test_ending_walks_back_over_null_stop_reason`,
`test_synthetic_entry_is_not_a_turn_ending`,
`test_unknown_stop_reason_spelling_is_other_and_counted` (DP7 — `stop_sequence` is the live case; the
2 real occurrences in the copies are the fixture),
`test_tool_uses_and_failures_are_collected` (assert `Write` 2 and `is_error` true 4 over the copies),
`test_unpairable_error_result_is_counted_not_attributed`,
`test_tail_is_found_by_session_id_glob` (never by reversing the slug),
`test_tail_read_is_bounded` (**A4, r3** — a file larger than `TAIL_BYTES` is read from the end, not
scanned; assert the bytes read, not the wall clock),
`test_first_partial_line_of_the_window_is_discarded` (a mid-line seek is not a malformed line),
`test_truncated_window_is_flagged_and_counted` (principle 5 — a shorter tail is honest, a silent one
is not),
`test_no_fixture_reads_the_real_claude_dir` (**P-M2-15**),
`test_tail_reader_only_reads` (AST: no `open(..., "w")`, no `Path.write_*`, no `os.remove`).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/engines/test_transcript_tail.py -q`.
**Exit Criteria:** fifteen pass; the module contains **no** `stop_reason` *payload* key read from a
hook payload (P-M2-5 — it reads `message.stop_reason` from the **transcript**, which is a different
object and is exactly what D46 says to read); the read is bounded (A4); file under 600 lines.
**Test Seams:** unit (a pure projection over a file the test wrote into `tmp_path` by copying a real
capture).

**Consumes:** `TranscriptTail`, `TurnEnding`, `ToolUseRef`, `ToolFailure` (T1);
`locate_transcript(projects_root: Path, engine_session_id: str) -> Path | None`,
`ACTIVITY_ENTRY_TYPES` (M1 `engines/claude_code/transcript.py`, shipped);
`Anomaly`, `AnomalyKind` (M1 `core/anomalies.py`).
**Produces:**
```python
TAIL_ENTRIES: int   # 20 — §8's "last ~20 user/assistant entries"
TAIL_BYTES: int     # 256 * 1024 — the bounded window (A4); the largest captured single entry is 410 665 B
def read_tail(path: Path, limit: int = TAIL_ENTRIES,
              max_bytes: int = TAIL_BYTES) -> tuple[TranscriptTail, tuple[Anomaly, ...]]: ...
```

---

### Task 4: the mechanical stop-reason table (the adapter's map)

**Objective:** §8's table, as code, in the one package allowed to read the engine's vocabulary
(ADR-M2-2, DP4). **This is the differentiator's core.**

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/stop_map.py` — new
- `tests/engines/test_stop_map.py` — new

**Dependencies:** T1, T3.

**data-schemas.md sections:** §StopFailure · §SessionEnd · §Stop · §Enumerations · §`SessionEnd.reason`
= `resume` and `logout` · §Auto compaction · §Observed process exit (pidfd) · §Notification.

**Allowed Scope:** the table below, its precedence function, and one `evidence` string per row.
**Pure** — engine values in, `StopReason | DEFERS | UNMAPPED` out.

**Out-of-Scope Drift:** **any reference to `Stop.stop_reason`** (K15, D46 — it does not exist in 26
captures nor in the CLI's own schema). Reading `error_type`, `end_reason` or `start_reason` — the
fields are `error`, `reason`, `source` (D41's four corrections). Reaching for a transcript (T3 already
did; this map takes the `TurnEnding`). Deciding `outcome_class` or actions (T7).

**Precedence — and it is a property of the function, not of a row:**

```
1. StopFailure.error   → if a row claims it, that reason wins, decided_by = MECHANICAL, confidence 1.0
2. SessionEnd.reason   → if a MAPPED row claims it, that reason wins
                          `other` DEFERS (DP8): it says the process ended and nothing about why
3. TurnEnding          → HELD_TOOL_CALL → STALLED_PENDING_TOOL ; HIT_TOKEN_CAP → TRUNCATED
                          ENDED_TURN    → DEFERS to the completeness split (T8/T9)
                          OTHER/ABSENT  → UNMAPPED
4. compaction bound    → applied BEFORE 3, and ONLY when `end_reason is not None`
                          (r3 BLOCKING 1: §8 says "before **death**", and the death path is the
                           one carrying a SessionEnd. A clean `Stop` never reaches this step.)
5. quota notice        → applied BEFORE 1 when quota_notice and no StopFailure.error
```

**Why error-before-tail, measured:** on **23/23** `StopFailure` captures the last `assistant` entry
says `stop_sequence`. Reading the tail first would classify every API failure as unknown.

**Table — 13 `error` values (all of the binary enum `o_`):**

| `error` | → | `evidence` | Note |
|---|---|---|---|
| `rate_limit` | `RATE_LIMITED` | §Enumerations | 1 capture |
| `overloaded` | `RATE_LIMITED` | §Enumerations | **[UNVERIFIED]** — **0 assignments in the binary**; a 529 arrives as `server_error` (N7) |
| `authentication_failed` | `AUTH_FAILED` | §StopFailure | 2 captures |
| `oauth_org_not_allowed` | `AUTH_FAILED` | §Enumerations | **[UNVERIFIED]** — 1 assignment, needs a real org policy |
| `verification_required` | `AUTH_FAILED` | §Enumerations | **[UNVERIFIED]**, and §8 maps it nowhere (DP8) |
| `cloud_credential_error` | `AUTH_FAILED` | §Enumerations | **[UNVERIFIED]** — 3P cloud only; §8 maps it nowhere (DP8) |
| `account_on_hold` | `ACCOUNT_BLOCKED` | §Enumerations | **[UNVERIFIED]** |
| `billing_error` | `ACCOUNT_BLOCKED` | §StopFailure | 1 capture (mock 400, "credit balance too low") |
| `invalid_request` | `BAD_REQUEST` | §StopFailure | 1 capture — **only** a prompt-too-long 400 |
| `model_not_found` | `BAD_REQUEST` | §StopFailure | 14 captures, one from the **real** API |
| `server_error` | `SERVER_ERROR` | §StopFailure | 2 captures, incl. the **529** |
| `max_output_tokens` | `TRUNCATED` | §StopFailure | 1 capture; arrives with **no `Stop`** |
| `unknown` | `UNKNOWN` **(mapped, not unmapped)** | §StopFailure | 1 capture — a plain 400. The engine's own "I don't know"; counted under its own kind, distinct from ours |
| *anything else* | `UNMAPPED` → `UNKNOWN` + anomaly | §Enumerations | principle 5 |

**Table — 5 `reason` values (binary enum `rce`):**

| `reason` | → | `evidence` | Note |
|---|---|---|---|
| `prompt_input_exit` | `USER_EXITED` | §SessionEnd | 1 capture |
| `clear` | `CLEARED` | §SessionEnd | 2 captures |
| `logout` | `LOGGED_OUT` | §`SessionEnd.reason` = resume and logout | 1 capture (gap-fill) |
| `resume` | `RESUMED_ELSEWHERE` | same | 1 capture. **The name misleads**: the same pane continues as a *different* session id, and the `why` says so |
| `other` | **DEFERS** | §SessionEnd | **47/50** of the corpus. DP8 |
| *anything else* | `UNMAPPED` → `UNKNOWN` + anomaly | §Enumerations | |

**Two bounded rows that are not a simple lookup:**

- **`CONTEXT_EXHAUSTED` (C12, bounded per N9 — and the bound needs TWO guards, r3 BLOCKING 1).**
  §8 says "`PreCompact{auto}` with no `PostCompact` **before death**". Revision 2 tried to express
  "cleared by a `Stop`" inside `signals/` and **it is not expressible**: `normalise.py:85-86` maps
  **both `Stop` and `SessionEnd` to `SignalKind.SESSION_STOPPED`**, and `hook_lane.py` reads `prior`
  *before* `fold`, so at the benign capture (`PreCompact{auto}` → `MessageDisplay` → `Stop`,
  `data-schemas.md:5582-5586`) the mark is still set when the classifying stop arrives and the rule
  fires unconditionally. `test_benign_auto_compact_is_not_context_exhausted` and
  `test_kill_during_compaction_is_context_exhausted` **contradicted each other**. Two guards, both
  required, and they are independent:

  1. **The kinds split (T10).** ADR-6's rule is *one `SignalKind` per distinct column effect*, and
     these two now have different effects — a turn ending clears the compaction mark, a session ending
     does not. So `Stop` gets **`SignalKind.TURN_STOPPED`** and `SessionEnd` keeps `SESSION_STOPPED`,
     their Table B rows differing in exactly one column. "Cleared by a turn ending" then says itself
     in `signals/`, with **no engine name anywhere near it** (K13). This is the mechanism ADR-6 exists
     for, used rather than worked around.
  2. **The adapter's own guard (here).** Precedence step 4 fires **only when `end_reason is not
     None`** — that is, only when a `SessionEnd` drove the stop. §8's word is *death*, and the death
     path carries an `end_reason` while a clean `Stop` carries none. The adapter may read that field;
     `signals/` may not know it exists.

  Either guard alone would close the contradiction the reviewer found. **Both are specified** because
  guard 1 depends on a fold rule firing in the right order and guard 2 depends on one parameter being
  threaded, and this is the row §8 warns is "likely a bug" territory. Evidence: §Auto compaction — the
  benign pattern is **2/3 turns (real API), 1/2 (mock)**; the positive case is
  `PreCompact{auto}` → `SessionEnd{reason:"other"}` with no `PostCompact`.
- **`QUOTA_PAUSED` (G-M2-1).** Requires `quota_notice`, set from the **notification type alone** —
  `quota_auto_resume_fired | _stale | _disabled`, capture-proven as enum values by `drift_check.py`,
  with **no payload field read**. `[UNVERIFIED]` payload; no resume time is displayed.

**The three unreachable rows, and they say so:** `CRASHED` (G-M2-2 — C13: an attached session gives an
exit time and never a code), `KILLED` (G-M2-4 — needs M4's `action_log`), and, on the other side,
`DERAILED` (G-M2-6 — no mechanical detector exists). An observed process exit with no stop event
produces `UNKNOWN` with `why = "process exited; an attached session gives an exit time but no exit
code (C13)"` and an `EXIT_CODE_UNOBSERVABLE` anomaly.

**Expected Artifacts:** one table, one precedence function, three result kinds.
**Required Checks:**
`test_stop_map_is_total_over_both_enums` (**P-M2-4**: all 13 `error` + all 5 `reason` values return a
result; none raises; none returns `None`),
`test_precedence_is_error_then_reason_then_tail`,
`test_every_stopfailure_capture_classifies` (all **23**, from the capture files),
`test_every_sessionend_capture_classifies` (all **50** + the gap-fill 16),
`test_http529_capture_is_server_error` (§8's row is wrong; the capture is right),
`test_plain_400_capture_is_unknown_and_counted`,
`test_other_defers_and_is_not_an_unknown` (DP8 — asserts the defer counter, **not** the unknown one),
`test_unmapped_error_is_unknown_and_counted`,
`test_benign_auto_compact_is_not_context_exhausted` (C12, over `autocompact-real-*` — **the exact
sequence that made revision 2 self-contradictory**: `PreCompact{auto}` → `MessageDisplay` → `Stop`
with the mark still set),
`test_kill_during_compaction_is_context_exhausted` (over `lifecycle-end-*`),
`test_compaction_bound_requires_an_end_reason` (**r3 BLOCKING 1, guard 2** — the same evidence with
`end_reason=None` must NOT classify as `CONTEXT_EXHAUSTED`),
`test_quota_rule_reads_only_the_notification_type` (AST: no payload field read beyond the type),
`test_observed_exit_without_a_stop_event_is_honest_about_the_exit_code` (C13),
`test_crashed_and_killed_are_never_produced` (**P-M2-12**),
`test_no_rule_references_stop_reason` (**P-M2-5**, extended from M1's to this module),
`test_every_stop_rule_cites_an_existing_section` (**P-M2-13** — every row's `evidence` is non-empty
**and** names a heading that exists in `docs/specs/data-schemas.md`; the only mechanical enforcement
of K1, exactly as M1's Table B has),
`test_unverified_rows_are_marked` (the five G-M2-5 rows carry the `[UNVERIFIED]` marker and a test
reads the marker, so the honesty cannot be quietly deleted),
`test_stop_map_is_pure` (200 cases, same input → same output, no I/O).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/engines/test_stop_map.py tests/boundaries -q`.
**Exit Criteria:** seventeen pass, **including the two that contradicted each other at revision 2**;
`test_no_engine_vocabulary_in_signals` green (this module is in `engines/`, where the vocabulary
belongs); no new boundary exemption.
**Test Seams:** unit.

**Consumes:** `StopReason`, `TurnEnding` (T1); `Anomaly`, `AnomalyKind` (M1).
**Produces:**
```python
DEFERS: Final          # sentinel: the value decided nothing; fall through
UNMAPPED: Final        # sentinel: no row claims this value; → UNKNOWN + anomaly
@dataclass(frozen=True) class StopRule:
    value: str; reason: StopReason; evidence: str; verified: bool
ERROR_RULES: tuple[StopRule, ...]     # 13 rows
REASON_RULES: tuple[StopRule, ...]    # 5 rows (`other` carries DEFERS)
@dataclass(frozen=True) class MechanicalResult:
    reason: StopReason | None; detail: str | None; anomalies: tuple[Anomaly, ...]
def mechanical_reason(*, failure_error: str | None, end_reason: str | None,
                      ending: TurnEnding, auto_compact_pending: bool, quota_notice: bool,
                      process_exit_observed: bool, exit_code: int | None) -> MechanicalResult: ...
```

---

### Task 5: `logs/` — the rotating JSONL writer and the versioned stop record (D25)

**Objective:** the other half of the data layer. Rotating daily JSONL, gzip on close, a size cap as a
second trigger, 90-day retention, and a reader that **skips malformed trailing lines** — because a
daemon killed mid-write leaves one.

**Files/Surfaces:**
- `src/shepherd/logs/jsonl.py` — new: the generic rotating writer/reader
- `src/shepherd/logs/stops.py` — new: the `StopEvidence`+`Verdict` record and its codec
- `tests/logs/test_rotating_jsonl.py`, `tests/logs/test_stop_log.py` — new

**Dependencies:** T1.

**Allowed Scope:** file I/O under a directory the caller hands in (ADR-M2-6 / ADR-2's rule). Nothing
here reads an environment variable, asks a host, or resolves XDG.

**Out-of-Scope Drift:** the audit log (M4) and the pty ring file (M3) — `logs/jsonl.py` is written so
both are a second and third caller, but **neither is built here**. A background rotation thread — the
writer rotates on write, which is when it can. Compressing the *current* file. Reading a log from any
tool the UI can call (K14, C-M2-9).

**The writer's five rules, each from D25:**

1. **Daily files**, `stops/<YYYY-MM-DD>.jsonl`, named from a **timestamp the caller passes**, never
   from a clock read — that is what makes the tests deterministic and the golden lane byte-identical.
2. **Gzip on close.** When the day rolls over or the writer is closed, the finished file becomes
   `<name>.jsonl.gz` and the plain file is removed **after** the gzip is fsynced — in that order, so a
   crash mid-rotation leaves a readable copy rather than none.
3. **Size cap as a second trigger** (`MAX_BYTES`, 32 MiB): the file rolls to `<date>.<n>.jsonl` and the
   finished part is gzipped.
4. **90-day retention**, applied on rotation only, by filename date — never by mtime, which lies.
5. **The reader skips malformed lines and counts them**, reads `.jsonl` and `.jsonl.gz`, and tolerates
   a truncated gzip tail the same way (E-M2-22).

**The record (ADR-M2-6):** `record_version` first, then the evidence and the verdict, as one JSON
object. A reader meeting an unknown version **skips and counts** (E-M2-21).

**Expected Artifacts:** a writer, a reader, a record codec.
**Required Checks:**
`test_rotates_on_date_change` (dates injected, no clock),
`test_gzips_the_finished_file_and_removes_the_plain_one_after`,
`test_crash_between_gzip_and_unlink_leaves_a_readable_copy` (simulate by leaving both; assert the
reader yields each record **once**),
`test_size_cap_rolls_within_a_day`,
`test_retention_drops_by_filename_date_not_mtime` (set a stale mtime on a fresh name; assert it stays),
`test_reader_skips_malformed_and_reads_gzip` (**D25's own sentence**),
`test_reader_survives_a_truncated_gzip_tail`,
`test_unknown_record_version_is_skipped_and_counted` (**E-M2-21**),
`test_record_roundtrips` (every `StopEvidence` and `Verdict` field survives, including empty tuples
and `None`s — asserted field by field, not by `==` on a dict),
`test_write_failure_never_loses_the_verdict` (make the directory unwritable; assert the writer reports
the loss and **raises nothing** that could stop the column write — C-M2-6),
`test_logs_never_read_the_environment` (AST: no `os.environ`, no `Path.home()`, no XDG string),
`test_no_read_tool_touches_a_log_path` (**P-M2-10** — lives here because this is where the paths are).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/logs -q`.
**Exit Criteria:** twelve pass; both files under 600 lines; `mypy --strict` clean.
**Test Seams:** integration (real files in `tmp_path`).

**Consumes:** `StopEvidence`, `Verdict`, `STOP_RECORD_VERSION`, and every type they contain (T1).
**Produces:**
```python
MAX_BYTES: int            # 32 * 1024 * 1024
RETENTION_DAYS: int       # 90
class RotatingJsonlLog:
    def __init__(self, directory: Path, prefix: str, max_bytes: int = MAX_BYTES,
                 retention_days: int = RETENTION_DAYS) -> None: ...
    def append(self, record: Mapping[str, object], date: str) -> bool: ...   # False = lost, counted
    def close(self) -> None: ...
def read_records(directory: Path, prefix: str,
                 since: str | None = None) -> Iterator[tuple[Mapping[str, object], int]]: ...
@dataclass(frozen=True) class ReadStats:
    records: int; skipped_malformed: int; skipped_version: int
class StopLog:
    def __init__(self, log: RotatingJsonlLog) -> None: ...
    def append(self, evidence: StopEvidence, verdict: Verdict) -> bool: ...
def read_stop_records(directory: Path,
                      since: str | None = None) -> tuple[list[StopEvidence], ReadStats]: ...
```

---

### Task 6: `StopEvidence` assembly

**Objective:** the one place the three sources meet — stop metadata, the session's folded counters,
and the neutral tail — producing the immutable record everything downstream reads (ADR-M2-1).

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/evidence.py` — new
- `tests/engines/test_evidence.py` — new

**Dependencies:** T1, T3, T4.

**Allowed Scope:** assembling one record. It calls `read_tail` and `mechanical_reason`, and it is
handed everything else.

**Out-of-Scope Drift:** classifying (T9). Writing anything (T11). Reading the store (it takes a
`SessionSnapshot`). Reading a clock — `received_at` is a parameter, always (the purity map).
Projecting an engine field name into the record (P-M2-6): the record's fields are neutral by name and
by value.

**The one subtlety worth stating.** The neutral `failure_note` field M1's normaliser already projects
from `StopFailure.error` **is the input to `mechanical_reason`** — so the hook lane hands the adapter
back its own neutral projection, and the engine spelling never leaves `engines/`. Read it with a named
key, one at a time (**K12** — `signal.fields["failure_note"]`, never `dict(...)`, never a loop).

**Expected Artifacts:** one function.
**Required Checks:**
`test_evidence_carries_no_engine_spelling` (every string field asserted against the 33 event names and
the engine field names),
`test_missing_transcript_is_an_absent_tail_not_a_crash` (**E-M2-12**),
`test_evidence_takes_its_clock_as_a_parameter` (AST: no `datetime.now`, no `time.`),
`test_assembly_is_deterministic` (same inputs → byte-identical record, twice, in two processes),
`test_counters_come_from_the_snapshot_not_the_tail` (heuristic 1's source is the folded columns — DP3),
`test_record_version_is_stamped`,
`test_reads_named_signal_fields_one_at_a_time` (**K12** — the taint scan is the real gate; this is the
readable assertion beside it).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/engines/test_evidence.py tests/boundaries -q`.
**Exit Criteria:** seven pass; boundary suite green with no new exemption.
**Test Seams:** unit.

**Consumes:** `StopEvidence`, `TranscriptTail`, `STOP_RECORD_VERSION` (T1);
`read_tail(path: Path, limit: int = TAIL_ENTRIES) -> tuple[TranscriptTail, tuple[Anomaly, ...]]` (T3);
`mechanical_reason(...) -> MechanicalResult` (T4); `SessionSnapshot` (M1 `core/fold_types.py`);
`Signal` (M1 `core/signals.py`); `locate_transcript` (M1).
**Produces:**
```python
def build_stop_evidence(*, signal: Signal, prior: SessionSnapshot, projects_root: Path,
                        received_at: str, process_exit_observed: bool = False,
                        exit_code: int | None = None) -> tuple[StopEvidence, tuple[Anomaly, ...]]: ...
```

---

### Task 7: the bucket map, the `next_actions[]` default table, and the fleet's bucket ordering

**Objective:** D21, as a lookup computed **free in the same pass that sets `outcome_class`**, plus
§4's palette ordering applied to real rows. This is the task that makes "it stopped" into "it stopped
and here is the one thing to do".

**Files/Surfaces:**
- `src/shepherd/signals/stop_rules.py` — new: `BUCKET_OF` and `DEFAULT_ACTIONS`
- `src/shepherd/signals/ordering.py` — extended: `bucket_of(row, now)` and `fleet_bucket_sort_key`
- `tests/signals/test_stop_rules.py`, `tests/signals/test_ordering.py` — new / extended

**Dependencies:** T1, T2.

**Allowed Scope:** two total tables and two read-time derivations. **Pure.** No engine word, no
mapping read, no clock (`now` is a parameter, as M1's `fleet_sort_key` already takes it).

**Out-of-Scope Drift:** an LLM refinement path (§8 describes how LLM items replace or merge behind
defaults — **the merge function is not built at M2**; D34). Deciding *which* reason applies (T4/T8/T9).
Sorting in JavaScript (M1's `test_the_page_does_not_re_derive_the_order`). Changing M1's
`fleet_sort_key` or `effective_state` — both stay, and the new key is built **on top of** them so
M1's tests keep passing unchanged.

**`BUCKET_OF` — §8's `outcome_class` column, total over the 20 `StopReason` values:**

`RATE_LIMITED`·`QUOTA_PAUSED` → `PAUSED` · `AUTH_FAILED`·`ACCOUNT_BLOCKED`·`BAD_REQUEST`·`SERVER_ERROR`·`STALLED_PENDING_TOOL`·`CRASHED`·`LOGGED_OUT`·`UNKNOWN` → `ERROR` ·
`TRUNCATED`·`KILLED`·`CONTEXT_EXHAUSTED`·`USER_EXITED`·`CLEARED`·`RESUMED_ELSEWHERE`·`INCOMPLETE`·`DERAILED` → `UNFINISHED` ·
`COMPLETED` → `FINISHED` · `BLOCKED_EXTERNAL` → `BLOCKED`.

**`DEFAULT_ACTIONS` — §8's default table, total over 20, ≤ 3 per row, `source = HEURISTIC`.**
**Not "verbatim" — two rows are reconciliations, and they get gap rows rather than the word (A7, r3):**
see **N14** (`missing[]` truncated to 2, not §8's 3, so D21's max-of-3 survives the `Requeue` item)
and **N15** (`Re-authenticate` without §8's `<provider>`, which no captured field supplies at M2).

| `StopReason` | action items (`text` · `kind`) |
|---|---|
| `COMPLETED` | **empty when `confidence >= CONFIDENT_ENOUGH`**, else `Review the diff` · `inspect` |
| `INCOMPLETE` / `DERAILED` | one item per `missing[]` entry (`requeue`), **truncated to 2** (N14 — §8 says 3, but its own row then appends `Requeue with what's missing`, which would make 4 against D21's hard max of 3), then `Requeue with what's missing` · `requeue` |
| `BLOCKED_EXTERNAL` | `Chase <waiting_on>` · `external` (`target` = the url). **At M2 `waiting_on` is `None`** (G-M2-7), so the text degrades to `Chase — what it is waiting on is not recorded` |
| `RATE_LIMITED` / `QUOTA_PAUSED` | `Resumes by itself — nothing to do` · `none` , then `Retry now` · `retry`. **No time is shown** (G-M2-1: no capture carries one) |
| `TRUNCATED` | `Resume — output hit the token cap` · `resume` |
| `CONTEXT_EXHAUSTED` | `Re-spawn with a compacted brief` · `respawn` |
| `CRASHED` | `Read the last 50 lines` · `inspect` , `Re-spawn from the last good commit` · `respawn` |
| `STALLED_PENDING_TOOL` | `Open logs — a tool call never executed; likely a bug` · `inspect` , `Escalate` · `escalate` |
| `KILLED` | `Re-spawn with the remaining brief` · `respawn` |
| `USER_EXITED` / `CLEARED` / `RESUMED_ELSEWHERE` | `Resume the session` · `resume` |
| `AUTH_FAILED` / `LOGGED_OUT` | `Re-authenticate` · `reauth` (N15 — §8 writes `Re-authenticate <provider>`; **no captured field carries a provider** at M2. `session.provider` exists in §7 and is null on every attached session, so the word would be a blank or a guess. When M3 spawns sessions with a known provider, the text takes it) |
| `ACCOUNT_BLOCKED` | `Check billing` · `external` |
| `BAD_REQUEST` | `Inspect the request — model or args rejected` · `inspect` |
| `SERVER_ERROR` | `Retry` · `retry` |
| `UNKNOWN` | `Open logs` · `inspect` , `Run shepherd replay after fixing the rule` · `inspect` |

**Ordering (§4, §12).** `bucket_of(row, now)` — **total by construction, with a final `else`
(A1, r3)**:
`needs_you` state → `NEEDS_YOU`; a live `running`/`starting` → `RUNNING`; a stopped row **with** an
`outcome` → that bucket; **anything else → `UNCLASSIFIED`**.

**The `else` is not defensive padding; it is a real captured case.** M1's `effective_state`
(`ordering.py`) demotes a stale `running` row to **`STARTING`**, and C7 records a `-p` session whose
`StopFailure` was killed at shutdown **2/2 times** — so a session that went quiet with no stop event
matches neither "live" nor "stopped with an outcome". Revision 2's four cases left it falling off the
end. It is `UNCLASSIFIED`: we do not know, we say so, and we count it (principle 5).
`fleet_bucket_sort_key(row, now)` = `(BUCKET_ORDER.index(bucket), row.session_id)` — the same stable
ulid tiebreak M1 chose, so a live page re-sorted on every event never shuffles rows that did not
change. M1's `effective_state` still applies its 90-second liveness demotion **before** the bucket is
taken, so silence still demotes a `running` row and never demotes a `needs_you` one.

**Expected Artifacts:** two total tables, two functions.
**Required Checks:**
`test_every_stop_reason_has_a_bucket_and_actions` (**P-M2-3**, totality by iterating `StopReason`),
`test_non_completed_verdict_never_has_an_empty_action_list` (**§14's literal words**),
`test_completed_is_empty_only_above_the_threshold` (ADR-M2-5),
`test_action_list_is_capped_at_three`,
`test_every_action_text_is_within_eighty_chars`,
`test_incomplete_row_never_exceeds_three_actions_with_many_missing` (**N14 / A7** — five `missing[]`
entries still yield 3 items, and the `Requeue` item is one of them),
`test_reauth_text_has_no_empty_provider_slot` (**N15 / A7** — never `Re-authenticate ` with a
trailing blank),
`test_every_action_kind_is_reachable_from_some_row` (all 9 used — otherwise the enum is aspirational),
`test_blocked_sorts_below_running` (**§12's deliberate choice**),
`test_bucket_order_matches_section_12`,
`test_unclassified_is_its_own_bucket` (D-4),
`test_bucket_of_is_total` (**A1, r3** — every `SessionState` × (`outcome` present / absent) ×
(live / stale) combination returns a `Bucket`; the stale-`running`-with-no-stop case, which C7 makes
real, is `UNCLASSIFIED`),
`test_bucket_order_is_section_12_plus_unclassified` (**A1** — asserts the first seven against §12 and
documents that `idle` is a workspace-level rendering, not a bucket),
`test_needs_you_outranks_a_stopped_verdict` (§8: a session waiting on a permission prompt is not
finished — **E-M2-26**),
`test_liveness_demotion_still_applies_before_bucketing` (M1's `effective_state`, unchanged),
`test_m1_fleet_sort_key_is_unchanged` (M1's tests pass verbatim — the new key is additive).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals tests/boundaries -q`.
**Exit Criteria:** fourteen pass; every pre-existing `tests/signals/` test passes unchanged;
`test_no_engine_vocabulary_in_signals` green with no new exemption.
**Test Seams:** unit.

**Consumes:** `StopReason`, `Bucket`, `BUCKET_ORDER`, `NextAction`, `NextActionKind`, `ActionSource`,
`CONFIDENT_ENOUGH`, `MAX_ACTIONS`, `ACTION_TEXT_MAX` (T1);
`FleetRow` with its new `outcome` field (T2);
`effective_state(row: FleetRow, now: str) -> SessionState`,
`fleet_sort_key(row: FleetRow, now: str) -> tuple[int, str]`, `LIVENESS_WINDOW_S` (M1, shipped).
**Produces:**
```python
BUCKET_OF: Mapping[StopReason, Bucket]                    # total over StopReason
def default_actions(reason: StopReason, *, confidence: float,
                    missing: tuple[str, ...], waiting_on: str | None) -> tuple[NextAction, ...]: ...
def bucket_of(row: FleetRow, now: str) -> Bucket: ...
def fleet_bucket_sort_key(row: FleetRow, now: str) -> tuple[int, str]: ...
```

---

### Task 8: the five heuristics

**Objective:** §8's completeness split, mechanically, with no model and no credential — five pure
predicates over one `StopEvidence`, each carrying its `evidence` citation (DP3).

**Files/Surfaces:**
- `src/shepherd/signals/heuristics.py` — new
- `tests/signals/test_heuristics.py` — new

**Dependencies:** T1, T3 (for the tail's shape).

**Allowed Scope:** five rules, a promise vocabulary, a blocked-phrasing vocabulary, and the ordering
between them. **Pure.**

**Out-of-Scope Drift:** an LLM anything (D34 — no prompt, no model id, no client, P-M2-11). Reading a
column heuristic 1 does not need. Reading `repos_touched` as heuristic 4's source — it has a known
cross-repo hole (inherited blocker T11-3) and the tail does not. Semantic reading of prose: **the
matching is literal**, exactly as M1's refusal classifier is — an uncaptured wording matches nothing
and the heuristic **under-fires rather than inventing** a verdict.

**The five, with source and evidence:**

| # | Heuristic | Source (DP3) | Fires → | `evidence` |
|---|---|---|---|---|
| 1 | **Open task ledger** — `tasks_total - tasks_done > 0` | the **folded columns**, persisted with their identity sets since BLOCKER-T6-1 | `INCOMPLETE` | §TaskCreated / TaskCompleted |
| 2 | **Unkept promise** — the last assistant text matches the promise vocabulary and `tail.promise_followed_by_tool_use is False` | the **tail** | `INCOMPLETE` | §Transcript entry: `assistant` |
| 3 | **Failure tail** — the last `FAILURE_TAIL_N` (3) failures in the window are all on the **same** tool name | the **tail**'s `failures`, paired by `tool_use_id` | `INCOMPLETE` | §Transcript entry: `user` (`tool_result.is_error`) |
| 4 | **No-op session** — zero `tool_uses` named `Edit` or `Write`, **and** the brief matches the change vocabulary | the **tail** + `brief` | `INCOMPLETE` | §Transcript entry: `assistant` (`tool_use` blocks) |
| 5 | **Blocked phrasing** — the last assistant text matches the waiting vocabulary **and** `tasks_total - tasks_done == 0` | the **tail** + columns | `BLOCKED_EXTERNAL` (candidate) | §Transcript entry: `assistant` |

**Resolution order, stated because two can fire at once.** 5 before 1–4 (§8 makes blocked phrasing
conditional on zero open tasks, so it is already disjoint from 1 but not from 2–4, and "waiting on a
review" is a better answer than "incomplete" — D18's whole argument). Then 1 (§8: "strongest and
cheapest"), then 3, 2, 4. **No heuristic fires → `COMPLETED` at `HEURISTIC_COMPLETED_CONFIDENCE`**
(ADR-M2-5). Each firing heuristic contributes its one-line reason to `why` and its finding to
`missing[]`; `why` is truncated at `WHY_MAX` with the untruncated text kept in the log record
(E-M2-28).

**`derailed` is not here** and cannot be: no mechanical detector for "believed it finished but did
something else" exists (**G-M2-6**). That absence is the single clearest measure of what D34 deferred,
and a test asserts it rather than leaving it to be noticed.

**Expected Artifacts:** five rules as a table, one resolver.
**Required Checks:**
`test_every_heuristic_cites_an_existing_section` (**P-M2-13**),
`test_open_task_ledger_fires_on_the_one_corpus_session_with_an_open_task` (**the corpus has exactly 3
`TaskCreated` and 2 `TaskCompleted`** — this is the whole fixture, and the test says so),
`test_unkept_promise_needs_both_the_phrase_and_the_absence`,
`test_kept_promise_does_not_fire` (`promise_followed_by_tool_use is True`),
`test_no_promise_is_not_a_broken_promise` (`None`),
`test_failure_tail_needs_three_on_the_same_tool` (two, or three on different tools, do not fire),
`test_no_op_session_uses_the_tail_not_repos_touched` (AST: `repos_touched` is not read here),
`test_blocked_phrasing_requires_zero_open_tasks` (§8),
`test_blocked_phrasing_outranks_incomplete`,
`test_no_heuristic_fires_means_completed_at_low_confidence` (**ADR-M2-5**, and the reason the corpus
is not 98% unknown),
`test_unmatched_wording_under_fires_rather_than_inventing` (an uncaptured phrase matches nothing),
`test_derailed_is_never_produced` (**P-M2-12**, G-M2-6),
`test_heuristics_are_pure` (AST: no clock, no `open(`, no store).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals/test_heuristics.py -q`.
**Exit Criteria:** thirteen pass; no engine vocabulary; file under 600 lines.
**Test Seams:** unit.

**Consumes:** `StopEvidence`, `TranscriptTail`, `StopReason`, `HEURISTIC_COMPLETED_CONFIDENCE`,
`WHY_MAX` (T1).
**Produces:**
```python
FAILURE_TAIL_N: int      # 3
PROMISE_PHRASES: tuple[str, ...]       # literal, captured wordings only
WAITING_PHRASES: tuple[str, ...]
CHANGE_PHRASES: tuple[str, ...]
@dataclass(frozen=True) class Heuristic:
    name: str; fires: Callable[[StopEvidence], bool]
    reason: StopReason; why: str; evidence: str
HEURISTICS: tuple[Heuristic, ...]      # 5 rows, in resolution order
@dataclass(frozen=True) class SplitResult:
    reason: StopReason; why: str; confidence: float
    missing: tuple[str, ...]; fired: tuple[str, ...]
def split_completeness(evidence: StopEvidence) -> SplitResult: ...
```

---

### Task 9: `classify()` and D34's one named call site

**Objective:** the public classifier — one pure function of one record — and the single place a model
call would ever go, which today returns the heuristic result **unchanged**.

**Files/Surfaces:**
- `src/shepherd/signals/verdict.py` — new
- `tests/signals/test_verdict.py` — new

**Dependencies:** T1, T7, T8.

**Allowed Scope:** composing T4's mechanical result, T8's split and T7's tables into a `Verdict`.
**Pure.**

**Out-of-Scope Drift — and this is the task where it matters most (D34):**
**no `Classifier` Protocol or ABC** ("an interface with zero implementations behind it is D9's mistake
in its purest form"); no `Credentials` lookup; no `available("anthropic")`; no prompt string; no model
id; no HTTP client; no `anthropic` import; no `if llm_enabled:` branch; **no second call site** of
`classify_end_turn`. Building the lane later means **filling that function in, and nothing else in the
system moves** — a property `test_classify_end_turn_has_one_call_site` keeps true.

**The composition, in order:**

```
1. evidence.mechanical is not None → that reason, decided_by = MECHANICAL, confidence 1.0
2. otherwise (the adapter deferred) and tail.ending is ENDED_TURN
        → classify_end_turn(evidence)  ← THE ONE CALL SITE
        → decided_by = HEURISTIC, confidence from the split
3. otherwise → UNKNOWN, decided_by = MECHANICAL, counted (DP7: OTHER/ABSENT decide nothing)
4. bucket   = BUCKET_OF[reason]
5. actions  = default_actions(reason, confidence=…, missing=…, waiting_on=…)   ← free, same pass (D21)
```

```python
def classify_end_turn(evidence: StopEvidence) -> SplitResult:
    """D34's one named call site for the deferred LLM verdict lane.

    Today this returns the heuristic result unchanged. Building the lane means
    filling this function in; nothing else in the system moves. There is no
    `Classifier` seam, deliberately — an interface with zero implementations
    behind it is D9's mistake in its purest form.
    """
    return split_completeness(evidence)
```

**Expected Artifacts:** one classifier, one stub with a real signature.
**Required Checks:**
`test_classify_is_deterministic` (**P-M2-1**, both corpora + 500 mutations),
`test_classify_never_raises` (**P-M2-2**, 500 mutations: every field null, absent, empty, oversized,
wrong-typed),
`test_mechanical_short_circuits_the_split` (§8: "that short-circuit is what keeps the common case
free" — assert the split is **not called** when a mechanical reason exists),
`test_classify_end_turn_returns_the_heuristic_result` (D34, byte-identical),
`test_classify_end_turn_has_one_call_site` (**P-M2-11**, AST over `src/shepherd/`),
`test_no_llm_lane_exists` (**P-M2-11**: no `Classifier`, no model id, no `anthropic`, no prompt
constant, no credential check anywhere in `src/shepherd/`),
`test_every_verdict_has_actions_unless_confidently_completed` (C-M2-2),
`test_confidence_is_one_for_mechanical_reasons` (§8: "mechanical, confidence 1.0"),
`test_decided_by_is_heuristic_for_the_split` (**DP1** — and it is the value migration 002 added),
`test_other_and_absent_endings_are_unknown_and_counted` (DP7),
`test_why_is_never_longer_than_the_column` (E-M2-28).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals tests/boundaries -q`.
**Exit Criteria:** eleven pass; boundary suite green with no new exemption; `mypy --strict` clean.
**Test Seams:** unit.

**Consumes:** `StopEvidence`, `Verdict`, `StopReason`, `Bucket`, `DecidedBy`, `NextAction` (T1);
`BUCKET_OF`, `default_actions(...)` (T7); `SplitResult`, `split_completeness(evidence)` (T8).
**Produces:**
```python
def classify(evidence: StopEvidence) -> Verdict: ...
def classify_end_turn(evidence: StopEvidence) -> SplitResult: ...   # D34's one named call site
```

---

### Task 10: the fold's three new rows — compaction, quota, and the stop marks

**Objective:** make the two facts the classifier needs survive D24's discard, by **appending rows** to
Table A and Table B exactly as ADR-6 promised ("Adding M2's rules appends rows").

**Files/Surfaces:**
- `src/shepherd/core/signals.py` — `SignalKind` gains **3** members. **`SIGNAL_FIELD_KEYS` is
  unchanged**: the three new rows read no payload field at all, and the stop path reads
  `failure_note`, which is already a member. A closed set that does not need to grow is the
  evidence that ADR-6's boundary is the right shape (self-review)
- `src/shepherd/core/anomalies.py` — `AnomalyKind` gains 4 members (append-only by design)
- `src/shepherd/core/fold_types.py` — `FoldDelta` and `SessionSnapshot` gain 2 fields each
- `src/shepherd/engines/claude_code/normalise.py` — Table A rows
- `src/shepherd/signals/rules.py` — Table B rows
- `src/shepherd/store/db.py` — `DELTA_COLUMNS` gains the 2 columns (which T2 created)
- `tests/signals/test_fold_rules.py`, `tests/engines/test_normalise.py` — extended

**Dependencies:** T1, T2.

**Allowed Scope:** the rows below and the two delta fields. **Nothing restructures the fold.**

**Out-of-Scope Drift:** touching any existing rule's effect (M1's 429-event golden table is the
regression gate and must stay byte-identical for every existing kind). Putting an engine word in
`signals/` (K13). A computed `fields` key (K12). Making `fold()` impure.

**Table A — three new rows, and one existing row split in two (`engines/claude_code/normalise.py`):**

| Engine event | → `SignalKind` | `fields` | Evidence | Constraint |
|---|---|---|---|---|
| `PreCompact{trigger: auto}` | `COMPACT_STARTED` | — | §Auto compaction | **C12** |
| `PreCompact{trigger: manual}` · `PostCompact` | `COMPACT_FINISHED` | — | §PreCompact / PostCompact | a manual compact is not exhaustion |
| `Notification{quota_auto_resume_fired \| _stale \| _disabled}` | `QUOTA_NOTICE` | — | §Enumerations (`VAr`) | **G-M2-1** — the **type only**; no payload field is read |
| **`Stop`** *(was `SESSION_STOPPED`)* | **`TURN_STOPPED`** | — | §Stop (**no `stop_reason` field**) | **r3 BLOCKING 1** |
| **`SessionEnd`** *(unchanged)* | `SESSION_STOPPED` | — | §SessionEnd (**not guaranteed in `-p`**) | **r3 BLOCKING 1** |

**The `Stop`/`SessionEnd` split is the fix for the contradiction the fresh review found**, and it is
ADR-6's own rule applied rather than worked around: *one `SignalKind` per distinct column effect*.
`normalise.py:85-86` maps both to `SESSION_STOPPED` today, which was correct at M1 because their
column effects were identical. They are no longer identical — **a turn ending clears the compaction
mark and a session ending does not** — so the enum gains a member, exactly as it did for
`TOOL_FAILED`, `TOOL_BATCH_FINISHED`, `STOP_FAILED` and `NOTICE_UNMAPPED` when revision 4 of the M1
plan hit the same wall. Without it, "cleared by a turn ending" can only be written by naming an engine
event inside `signals/`, which K13 forbids and which is the F4 failure mode ADR-1 calls "how
boundaries die".

The other three were previously `TURN_PROGRESS` and `NOTICE_UNMAPPED`. **All four splits are the
ADR-6 rule working**: one `SignalKind` per distinct column effect, so no rule ever needs a `raw_kind`
predicate.

**Table B — four new rows (`signals/rules.py`), each with its `evidence` string:**

| `SignalKind` | Column effect | Clears `needs_you`? |
|---|---|---|
| `COMPACT_STARTED` | `auto_compact_at = received_at` | no |
| `COMPACT_FINISHED` | `auto_compact_at = CLEARED_STAMP` | no |
| `QUOTA_NOTICE` | `quota_notice_at = received_at` | no |
| **`TURN_STOPPED`** | `state = stopped`, `ended_at = received_at`, **`auto_compact_at = CLEARED_STAMP`** | **yes** |

**And one amendment to an existing row:** `SESSION_STOPPED` keeps its M1 effect **exactly** — `state =
stopped`, `ended_at` — and **does not** clear the compaction mark, because a session ending is the
"death" §8's rule is bounded by. `STOP_FAILED` likewise keeps its M1 effect unchanged.

**The two rows differ in exactly one column**, and that column is the whole of C12's bound. A reader
who wants to know why the enum grew a member can see the reason in one line of the table
(**r3 BLOCKING 1**).

**Golden-lane consequence, stated because it is the one place this split is visible:** every `Stop` in
the 429-event corpus changes `SignalKind` from `SESSION_STOPPED` to `TURN_STOPPED`. **No `session`
column changes** — both rules set `state` and `ended_at` identically — so
`tests/golden/expected/sessions.json` must be **byte-identical except for the two new columns**, which
is what `test_golden_table_is_unchanged_for_every_existing_kind` already asserts. If any other cell
moves, the split was done wrong.

**The clear sentinel.** `FoldDelta`'s contract is "`None` means *untouched*, never *cleared*", and
`core.fold_types.CLEARED` is the empty string, which is falsey for every reader. These are **timestamp**
columns, and `""` is not a timestamp; a reader doing `if row.auto_compact_at:` is correct either way,
but a reader parsing it is not. **`CLEARED_STAMP = CLEARED`** is therefore declared as a named alias in
`core/fold_types.py` beside `CLEARED`, with the one-line reason, so both lanes agree **by
construction** rather than by coincidence — which is exactly the lesson BLOCKER T11-6 recorded.

**`AnomalyKind` gains four members** (append-only): `STOP_UNMAPPED_VALUE`, `STOP_DEFERRED_VALUE`,
`EXIT_CODE_UNOBSERVABLE`, `TRANSCRIPT_TAIL_ABSENT`. Four rather than one because `doctor` reading
"37 unknowns" cannot tell an unmapped API error from a `-p` exit that deferred, and those are
different work items.

**Expected Artifacts:** three kinds, three rules, two delta fields, four anomaly kinds.
**Required Checks:**
`test_every_signal_kind_has_exactly_one_rule` (inherited — still total at 23 kinds),
`test_every_engine_event_maps_to_a_kind` (inherited — still total over the 33 names),
`test_every_fold_rule_cites_an_existing_section` (inherited — the three new rows too),
`test_auto_compact_mark_is_set_and_cleared` (set by `COMPACT_STARTED`, cleared by `COMPACT_FINISHED`
**and by `TURN_STOPPED`, but NOT by `SESSION_STOPPED`** — **C12/N9, r3 BLOCKING 1**),
`test_stop_and_session_end_are_different_kinds` (the split, asserted at the normaliser),
`test_session_stopped_keeps_its_m1_column_effect` (the row M1 shipped is untouched),
`test_manual_compact_does_not_set_the_mark` (§PreCompact: `trigger` distinguishes them),
`test_quota_notice_reads_only_the_type` (G-M2-1),
`test_quota_notice_is_no_longer_an_unmapped_notice` (it was `NOTICE_UNMAPPED`; assert the counter moves),
`test_golden_table_is_unchanged_for_every_existing_kind` (**the regression gate**: replay the 429
events and diff against `tests/golden/expected/sessions.json`; only the two new columns may differ),
`test_signals_reads_only_neutral_field_keys` (inherited, **K12**),
`test_no_engine_vocabulary_in_signals` (inherited, **K13**),
`test_fold_is_deterministic`, `test_fold_never_raises` (inherited).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests -q` (the whole suite: this task touches
`core/`, which everything imports).
**Exit Criteria:** twelve pass; **all 407 pre-existing tests still pass**; the golden expected table
changes **only** by the two new columns, and that diff is shown in the commit message rather than
regenerated silently.
**Test Seams:** unit + the golden replay.

**Consumes:** `SignalKind`, `SIGNAL_FIELD_KEYS`, `Signal` (M1 `core/signals.py`); `FoldDelta`,
`SessionSnapshot`, `CLEARED`, `IdentitySets` (M1 `core/fold_types.py`); `FoldRule`, `FOLD_RULES`,
`RULE_BY_KIND` (M1 `signals/rules.py`); `parse_hook_payload(raw: bytes, received_at: str) -> Signal |
MalformedPayload` (M1); `DELTA_COLUMNS` (M1 `store/db.py`); the two columns from T2.
**Produces:**
```python
# core/signals.py  — SignalKind gains:
COMPACT_STARTED = "compact_started"; COMPACT_FINISHED = "compact_finished"; QUOTA_NOTICE = "quota_notice"
# core/anomalies.py — AnomalyKind gains:
STOP_UNMAPPED_VALUE; STOP_DEFERRED_VALUE; EXIT_CODE_UNOBSERVABLE; TRANSCRIPT_TAIL_ABSENT
# core/fold_types.py
CLEARED_STAMP = CLEARED          # one alias, one reason, both lanes (BLOCKER T11-6's lesson)
# FoldDelta gains:      auto_compact_at: str | None = None ; quota_notice_at: str | None = None
# SessionSnapshot gains: auto_compact_at: str | None ; quota_notice_at: str | None
```

---

### Task 11: the stop lane — assemble, classify, write, log, publish

**Objective:** the one impure function that turns a stop signal into a persisted, logged, published
verdict — with all three collaborators injected, so it is testable with no process at all **and** is
what `signals/hook_lane.py::HookLane` calls in the running daemon (ADR-M2-7, revised at r2).

**Files/Surfaces:**
- `src/shepherd/signals/stop_lane.py` — new
- `tests/signals/test_stop_lane.py` — new

**Dependencies:** T2, T5, T6, T9, T10.

**Allowed Scope:** one function, ≤ 80 lines, five ordered steps, **plus the one call site inside
`signals/hook_lane.py::HookLane`** that routes a stop signal into it. It **constructs nothing**, opens
nothing, and resolves no path.

**Out-of-Scope Drift:** becoming a composition root — `daemons/controld.py` is **at** ADR-1's cap
(T18-3) and Task 18 owns its growth, not this task. Moving any of `HookLane`'s existing three impure
rules (registration, re-binding, cross-repo attribution) — they are tested where they are, and
`tests/signals/test_hook_lane.py` must pass **unchanged**. Reading a clock. Retrying. Owning a thread —
ADR-7's single writer already serialises the store, and the log append happens on the caller's thread
under the log's own lock.

**The five steps, and the order is the contract:**

1. `build_stop_evidence(...)` — the transcript is read **exactly once**, here (ADR-M2-1).
2. `classify(evidence)` — pure.
3. `store.apply_stop_verdict(...)` — the eight columns, in one verb, in one transaction (D33).
4. `stop_log.append(evidence, verdict)` — **after** the columns, so a log failure never costs a
   verdict (C-M2-6, E-M2-23). A failed append is counted, not raised.
5. `publish(StreamEvent(kind="session.classified", …))` — so the page repaints with no polling (§12).

**Two events per stop, deliberately (A3, r3).** `signals/rules.py` **already** emits
`"session_stopped"` from both the `SESSION_STOPPED` and `STOP_FAILED` rules, and after T10's split
from `TURN_STOPPED` as well. That one fires inside `fold()`, **before the verdict exists** — it is
what makes the row go grey immediately. This one fires **after** the verdict is written and carries
the bucket and the first action. They are two different facts arriving at two different times, and a
page that waited for the second would show a live row for the length of a transcript read. **The name
is `session.classified`, not a second `session_stopped`**, so a subscriber can tell them apart;
revision 2 called it `session.stopped` and asserted "exactly one", which was wrong on both counts.

**Idempotence.** A second stop for a session that already has a verdict **re-classifies and
overwrites** (E-M2-5: S18 has two `Stop`s in one session) — and both records are in the log, so
`replay` sees the history. An observed process **exit** for a session that already has a verdict is
**ignored** (E-M2-30).

**Expected Artifacts:** one function.
**Required Checks:**
`test_stop_signal_triggers_classification`,
`test_stop_emits_one_classified_event` (**A3, r3** — exactly one `session.classified`, carrying the
bucket and the first action, **in addition to** the `session_stopped` the fold already emits; the test
asserts both are present and that they are distinguishable by `kind`),
`test_columns_are_written_before_the_log`,
`test_log_failure_never_loses_the_verdict` (**C-M2-6** — unwritable directory; columns still correct),
`test_second_stop_overwrites_and_both_are_logged` (**E-M2-5**),
`test_observed_exit_after_a_verdict_is_ignored` (**E-M2-30**),
`test_stop_lane_constructs_nothing` (AST: no `open_store`, no `RotatingJsonlLog(`, no `Path(` literal,
no clock),
`test_transcript_is_read_exactly_once` (instrument the reader; assert one call),
`test_lane_runs_without_a_composition_root` (the whole test builds a `tmp_path` store, a `tmp_path`
log and a list for `publish` — the seam ADR-M2-7 exists to give),
`test_hook_lane_routes_a_stop_into_the_stop_lane` (the one new call site),
`test_existing_hook_lane_tests_pass_unchanged` (run `tests/signals/test_hook_lane.py` verbatim — the
three impure rules M1 built there are untouched).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals/test_stop_lane.py -q`.
**Exit Criteria:** eleven pass; every pre-existing `tests/signals/test_hook_lane.py` test passes
**unchanged**; no engine vocabulary in the module; under 600 lines; `daemons/controld.py` is not
edited by this task.
**Test Seams:** integration (`invoke()`-adjacent: a real store, a real log, a real classifier — only
the publisher is a list).

**Consumes:** `StopEvidence`, `Verdict` (T1); `Store`, `apply_stop_verdict(...)` (T2);
`StopLog`, `StopLog.append(evidence, verdict) -> bool` (T5);
`build_stop_evidence(...)` (T6); `classify(evidence) -> Verdict` (T9);
`StreamEvent` (M1 `core/stream.py`); `SessionSnapshot` (M1);
**`HookLane`, `Publisher = Callable[[StreamEvent], int]`, `changed_paths` (M1
`signals/hook_lane.py` / `signals/rules.py`, shipped by T18)**.
**Produces:**
```python
def handle_stop(*, signal: Signal, prior: SessionSnapshot, projects_root: Path, received_at: str,
                store: Store, stop_log: StopLog, publish: Callable[[StreamEvent], int],
                process_exit_observed: bool = False,
                exit_code: int | None = None) -> Verdict | None: ...   # None = already classified
```

---

### Task 12: `shepherd replay` — the engine, the tool, and the command

**Objective:** *"This is what makes a missed case a rule edit rather than a wait for recurrence"*
(D3). Re-run the current classifier over the stop log, overwrite the columns, and write the
before/after diff that is the review artifact.

**Files/Surfaces:**
- `src/shepherd/logs/replay.py` — new: the diff writer
- `src/shepherd/signals/replay.py` — new: the replay engine
- `src/shepherd/toolsurface/tools_replay.py` — new: the `replay` `ToolDef` **only** (T13 owns `tools_m2.py`; two builders must never share a file — half of M1's blocker file is that lesson)
- `src/shepherd/cli/main.py`, `src/shepherd/cli/commands.py` — the `replay` subcommand
- `tests/signals/test_replay.py`, `tests/cli/test_replay_command.py` — new

**Dependencies:** T2, T5, T9, **T18** (the composition root is at its line cap; a new tool is wired
through `compose_tool_surface`, never by editing `controld.py`).

**Allowed Scope:** reading the stop log, re-classifying, writing changed columns, writing one diff
file, and one registered tool + one CLI subcommand that reaches it through `invoke()`.

**Out-of-Scope Drift:** reading a **transcript** (ADR-M2-1: the record is the truth; the transcript
may be gone). A `--fix` that edits rules. A `--dry-run` flag that is the *default* — the diff is
written **every** run and `--apply` is what writes the columns (see below). **Editing `daemons/controld.py`** — it is at ADR-1's cap and T18 owns its growth; this task adds its
tool to `compose_tool_surface`. **Opening a second `Store` from `cli/`** (**DP9** — §7 rule 3, D37,
and T18-1's option (c) is a named trap). **Building a transport for a standalone `shepherd` process** —
blocker T18-1 assigns that to M4. Letting a page call this tool: `replay` is `LOCAL_DESTRUCTIVE` and
`audiences={HUMAN}`, so M4 gates it by one policy-table row, per D38.1's precedent for the installer
trio.

**The command, as §8 shows it:**

```
$ shepherd replay --since 30d
  read 412 records (9 skipped: 4 malformed, 5 unknown version)
  reclassified 412 sessions
  changed 37:  unknown → stalled_pending_tool (31)
               completed → incomplete (6)
  unknown rate: 8.2% → 0.7%
  diff: ~/.local/share/shepherd/logs/replay/2026-09-17.log
```

**`--apply` is required to write.** §8's example implies a write; a command that silently overwrites
412 verdicts because a rule was mid-edit is the one way `replay` can do damage, and the diff exists
precisely so a human reads it first. Without `--apply` the diff is written and the columns are not.
*(Recorded as **RD7**, explicitly unapproved.)*

**`--classifier h-8`** in §8's example names a rule-set version. M2 has no rule-set versioning, so the
flag is **not implemented**; the diff header records the code's own `STOP_RECORD_VERSION` and the git
description if one is available, and says `classifier version: not recorded` otherwise (principle 5).
*(RD8.)*

**Expected Artifacts:** a replay engine, a diff file, a tool, a command.
**Required Checks:**
`test_replay_uses_the_current_rules` (change a table row; assert the verdict changes),
`test_replay_overwrites_the_stop_columns` (with `--apply`),
`test_replay_without_apply_writes_the_diff_and_no_column` (**RD7**),
`test_replay_is_idempotent` (**P-M2-9**, over both corpora),
`test_replay_never_writes_a_verdict_it_did_not_derive`,
`test_replay_writes_a_diff_file` (the before/after pairs, the counts, the unknown-rate delta),
`test_replay_reports_skipped_records_separately` (malformed vs unknown version — E-M2-21/22),
`test_orphaned_record_is_counted_not_fatal` (**E-M2-25**),
`test_columns_equal_the_replayed_log` (**P-M2-8**, over both corpora),
`test_replay_never_reads_a_transcript` (AST + an instrumented reader that fails the test if called),
`test_replay_prints_counts_and_unknown_rate` (CLI, through `invoke()`),
`test_replay_in_a_standalone_process_says_so_and_exits_one` (**DP9** — the same honest message
`status` gives, never a silent no-op and never a second store),
`test_replay_never_opens_a_store_from_cli` (AST over `cli/`: no `open_store`, no `sqlite3`),
`test_replay_tool_is_local_destructive_and_human_only` (D38.1's shape),
`test_replay_command_reaches_the_system_only_through_invoke` (inherited
`test_consumer_boundary` plus an explicit assertion).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals/test_replay.py tests/cli tests/boundaries -q`.
**Exit Criteria:** fifteen pass; `cli/` imports nothing below L4 and opens no store; `controld.py` is
unmodified by this task; the consumer-boundary test is green with no new entry in its exemption list.
**Test Seams:** integration (`toolsurface.invoke()`).

**Consumes:** `Verdict`, `StopEvidence`, `StopReason` (T1); `Store`, `sessions_for_replay(since)`,
`stop_verdict_counts()`, `apply_stop_verdict(...)`, `StopCounts`, `ReplayTarget` (T2);
`read_stop_records(directory, since)`, `ReadStats`, `RotatingJsonlLog` (T5);
`classify(evidence) -> Verdict` (T9);
`ToolDef`, `BlastClass`, `Audience`, `CallerContext`, `register(tool: ToolDef) -> None`,
`invoke(name, args, ctx) -> ToolResult` (M1 `toolsurface/`); `Cli`, `EXIT_OK`, `EXIT_FAILURE`,
`EXIT_USAGE` (M1 `cli/`).
**Produces:**
```python
@dataclass(frozen=True) class VerdictChange:
    session_id: str; before: str | None; after: str
@dataclass(frozen=True) class ReplayReport:
    read: int; skipped_malformed: int; skipped_version: int; orphaned: int
    reclassified: int; changes: tuple[VerdictChange, ...]
    unknown_rate_before: float; unknown_rate_after: float; applied: bool
def replay(*, store: Store, log_dir: Path, since: str | None, apply: bool,
           diff_dir: Path) -> ReplayReport: ...
def write_replay_diff(report: ReplayReport, diff_dir: Path, date: str) -> Path: ...
def register_replay_tool(store: Store, log_dir: Path, diff_dir: Path) -> None: ...
def run_replay(cli: Cli, since: str | None, apply: bool) -> int: ...
# compose_tool_surface() (T18) gains one call: register_replay_tool(store, log_dir, diff_dir)
```

---

### Task 13: the read tools — `fleet_tree`, the `unknown` rate, and the stop projection

**Objective:** give the page the three things it cannot compute for itself, through `invoke()` and
nothing else (D35).

**Corrected at r2 (DP6).** An earlier draft said this task *creates* `fleet_tree` and closes blocker
T16-1. **Both were false by the time the plan was saved**: `toolsurface/tools_m1.py::fleet_tree`
already exists, T16-1 is **closed**, `web/` already reads `/api/fleet/tree`, and `groupByWorkspace` is
already gone from `fleet.js`. This task **extends** what is there: the order becomes the *bucket*
order rather than the three-state order, and each row carries the stop fields.

**Files/Surfaces:**
- `src/shepherd/toolsurface/tools_m1.py` — `fleet_tree` sorts by `fleet_bucket_sort_key` instead of
  `fleet_sort_key`; `project_session` gains the stop fields; `fleet_summary` gains the rate
- `src/shepherd/toolsurface/tools_m2.py` — new, **only** if `tools_m1.py` would pass 600 lines (it is
  14.2 KB today); the bucket projection lands there if so. **Decide by measuring, not by preference.**
- `tests/toolsurface/test_tools_m1.py` — extended; `tests/toolsurface/test_tools_m2.py` — new if the
  split happens
- **`src/shepherd/web/routes.py` is NOT edited** — `/api/fleet/tree` already exists

**Dependencies:** T2, T7.

**Allowed Scope:** projections. **No new logic** — `fleet_tree` applies `effective_state`,
`bucket_of` and `fleet_bucket_sort_key`, all of which already exist, to rows `Store.fleet()` already
returns. This is exactly what blocker T16-1 recommends: *"the tool is a projection, not new logic."*

**Out-of-Scope Drift:** **reading a log** (K14, C-M2-9, P-M2-10) — every field here comes from a
column. Sorting in the page (M1's `test_the_page_does_not_re_derive_the_order`). Adding a polling
endpoint (`routes.py`'s own rule: §12 has one liveness path and it is SSE). Widening
`project_session`'s whitelist beyond the stop fields — it is a whitelist on purpose (§13: never return
a raw row).

**Three additions:**

1. **`fleet_tree` gains the bucket order and the verdict fields** — it keeps its shape (workspace →
   session, workspaces ordered by their best-ranked session, `effective_state` applied), and swaps
   `fleet_sort_key` for `fleet_bucket_sort_key`. Each row gains `bucket`, `stop_reason`, `why`,
   `confidence`, `decided_by` and `next_actions[]`. `tests/toolsurface/test_tools_m1.py::
   test_fleet_tree_orders_by_state_not_by_creation` and `::test_fleet_tree_applies_the_read_time_
   liveness_backstop` must still pass — the bucket order is a **refinement** of the state order for
   live rows, so they do.
2. **`fleet_summary` gains** `unknown_rate: float`, `unclassified: int`,
   **`completed_low_confidence: int`** and `by_bucket: Mapping[str, int]` — computed from
   `stop_verdict_counts()`. `unknown_rate` is `unknown / classified`, `0.0` when `classified == 0`,
   and **`unclassified` and `completed_low_confidence` are reported beside it, never folded into it**
   (ADR-M2-5, **DP10**, D-4). Three numbers, three different meanings: *we could not map this stop*,
   *we never saw this stop*, and *the turn ended cleanly and no heuristic could tell us whether it
   finished* — the last being the one **D34 says is the trigger for building the LLM lane**.
3. **`get_session` / `project_session` gain** the eight stop fields, `next_actions[]` as a list of
   `{text, kind, target, source}` (DP5), and `bucket`. §12: the same list "is returned by
   `get_session()`, so the master reads the identical items rather than re-reasoning about a stop it
   can already see classified."

**Expected Artifacts:** one new tool, two extended projections, one route.
**Required Checks:**
`test_fleet_tree_is_ordered_by_bucket`,
`test_fleet_tree_orders_by_state_not_by_creation` (**M1's, must still pass unchanged**),
`test_fleet_tree_applies_the_read_time_liveness_backstop` (**M1's, must still pass unchanged**),
`test_the_fleet_route_hands_the_page_an_ordered_tree` (**M1's, over HTTP, must still pass unchanged**),
`test_fleet_summary_reports_the_unknown_rate` (**principle 5's headline metric**),
`test_unknown_rate_is_zero_not_nan_when_nothing_is_classified`,
`test_unclassified_is_reported_separately_from_unknown` (**ADR-M2-5**),
`test_low_confidence_completions_are_counted_and_not_folded_into_unknown` (**DP10 / r3 BLOCKING 4**),
`test_get_session_returns_the_same_actions_as_the_fleet` (§12's identical-items requirement),
`test_project_session_whitelists_the_new_fields` (§13 — a field not on the list is not projected),
`test_no_read_tool_touches_a_log_path` (**P-M2-10**, re-asserted here where the tools are),
`test_schema_is_validated_at_registration` (D53 — inherited behaviour, asserted for the new tool),
`test_every_new_tool_declares_its_audiences` (ADR-3's `HUMAN`),
`test_consumer_boundary` (inherited — `web/` still imports nothing below L4).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/toolsurface tests/web tests/boundaries -q`.
**Exit Criteria:** thirteen pass; **every pre-existing `fleet_tree` test passes unchanged** (T16-1
stays closed rather than being re-opened by a refinement); `web/routes.py` is unmodified; no file in
`web/` imports below L4; no source file passes 600 lines.
**Test Seams:** integration (`toolsurface.invoke()`).

**Consumes:** `Bucket`, `PALETTE`, `NextAction` (T1); `Store.fleet()`, `Store.stop_verdict_counts()
-> StopCounts`, `FleetRow` with its stop fields (T2); `bucket_of(row, now)`,
`fleet_bucket_sort_key(row, now)` (T7); `effective_state(row, now)`, `fleet_sort_key(row, now)` (M1);
`Clock = Callable[[], str]`, `utc_now() -> str`, `ToolDef`, `BlastClass`, `Audience`,
`register(tool)`, `project_session(session)`, `fleet_summary(store, clock)`,
`fleet_tree(store, clock)`, `build_read_tools(...)`, `register_read_tools(store, projects_root,
clock)` (M1 `toolsurface/tools_m1.py`, all shipped).
**Produces:**
```python
def project_fleet_row(row: FleetRow, now: str) -> dict[str, object]: ...
def fleet_tree(store: Store, clock: Clock) -> dict[str, object]: ...   # SIGNATURE UNCHANGED (M1's)
# API_ROUTES is UNCHANGED — "/api/fleet/tree": "fleet_tree" already exists
# fleet_tree rows gain: bucket
# fleet_summary gains keys:  unknown_rate: float ; unclassified: int ;
#                            completed_low_confidence: int ; by_bucket: dict[str, int]
# project_session gains keys: bucket, stop_reason, outcome, why, confidence, decided_by,
#                             next_actions (list of {text, kind, target, source}), exit_code, ended_at
```

---

### Task 14: the eight-bucket palette on the fleet page

**Objective:** §4's palette rendered with **both a colour and a glyph**, in §12's order, with the
`unknown` rate visible — replacing M1's three-state chip.

**Files/Surfaces:**
- `src/shepherd/web/static/fleet.js` — the chip and the row
- `src/shepherd/web/static/app.css` — the eight bucket classes
- `src/shepherd/web/static/app.js` — the summary line gains the rate
- `tests/web/test_palette.py` — new; `tests/web/test_fleet_page.py` — extended

**Dependencies:** T13.

**Allowed Scope:** rendering. Plain ES modules, **no build step**, no framework, no runtime dependency
(D51, K8).

**Out-of-Scope Drift:** `innerHTML` / `outerHTML` / `insertAdjacentHTML` **anywhere** (§13; the static
scan fails the build). Sorting, comparing names, or reading a timestamp to decide position (M1's
`test_the_page_does_not_re_derive_the_order` — the page renders the order the API handed it). A colour
without a glyph, or a glyph without a colour. Deriving a bucket in JavaScript — the tool sends it.

**The eight, from §4 verbatim plus D-4's eighth:**
`running` blue `#3B82F6` ● · `needs_you` amber `#F59E0B` ⏸ · `finished` green `#10B981` ✓ ·
`unfinished` violet `#8B5CF6` ◑ · `blocked` slate `#64748B` ⏳ · `paused` cyan `#06B6D4` ⏱ ·
`error` red `#EF4444` ✕ · `unclassified` grey `#9CA3AF` ?

Slate stays deliberately desaturated: a blocked session reads as *parked*, not as demanding.

**Expected Artifacts:** an eight-bucket chip, a rate in the summary.
**Required Checks:**
`test_every_bucket_has_a_colour_and_a_glyph` (**the accessibility invariant** — parses `app.css` and
`fleet.js`, asserts all eight appear in both, colours distinct, glyphs distinct and non-empty),
`test_palette_matches_core_stops` (the CSS colours equal `PALETTE`'s — one source of truth, checked,
because a hand-copied hex is how a palette drifts),
`test_the_page_does_not_re_derive_the_order` (inherited, extended: no `.sort(`, no `localeCompare`, no
`BUCKET_ORDER` in JS),
`test_no_unescaped_interpolation_in_frontend` (inherited — `why` and action text are untrusted),
`test_unknown_rate_renders` (principle 5's metric, on the page §12 puts it on),
`test_low_confidence_completions_render_beside_the_unknown_rate` (**DP10 / r3 BLOCKING 4** — D34's
tuning signal is on the page, not only in the store; a green chip that nothing counts is what revision
2 shipped and what this test forbids),
`test_unclassified_chip_renders_and_is_not_green_or_red` (D-4),
`test_page_renders_with_every_field_null` (an M1-era row with no verdict must not crash the page).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/web -q`. *(No JS test runner exists on
this host — no node, no npm; the rule is enforced by a Python static scan, exactly as M1 does.)*
**Exit Criteria:** eight pass; the escaping scan green; no new runtime dependency.
**Test Seams:** integration (route + static scan).

**Consumes:** `PALETTE`, `Bucket`, `BUCKET_ORDER` (T1); `fleet_tree` and the `bucket` key (T13);
`element()`, `chip()`, `escape.js` (M1 `web/static/`).
**Produces:**
```js
// fleet.js
const BUCKET_LABEL = { … }   // 8 entries
const BUCKET_MARK  = { … }   // 8 entries, glyph per bucket
function bucketChip(row) { … }   // colour class + glyph + label, textContent only
```

---

### Task 15: expandable stopped rows, action buttons, and the honest `[why?]`

**Objective:** §12's whole point — *"a session that stopped for any reason answers 'so what do I do'
without you reading a transcript"* — with every affordance telling the truth about what it can do at
M2.

**Files/Surfaces:**
- `src/shepherd/web/static/fleet.js` — the stopped row and its expansion
- `src/shepherd/web/static/app.css` — the expansion and the button states
- `tests/web/test_fleet_page.py` — extended

**Dependencies:** T14.

**Allowed Scope:** rendering `next_actions[]`. The **capabilities** those actions name are M3
(`resume`, `respawn`, `retry`) and M4 (`escalate`, `requeue`, `reauth`) and are **not built**.

**Out-of-Scope Drift:** wiring a button to an action (M3/M4). A `⚡ do all` control — §12 says it is
**not** in v1. Reading a log for the expansion (K14) — everything shown comes from the row.
Re-deriving anything the tool sent.

**The collapsed row** carries the bucket chip, one line of `why`, and **the first action as a
button**, exactly as §12 draws it. **Expanding** lists every action with its ordinal, and a footer
counting sources (`2 heuristic · 1 llm ⓘ`) — at M2 that footer always reads `N heuristic`, which is
itself the honest signal that D34's lane is off.

**Three honesty rules, each because the alternative is a lie:**

1. **`[why?]` is a note, not a button** (N10). §8's own no-credential paragraph specifies this:
   *"the UI replaces `[why?]` with a one-time note that an API key enables it."* A button that fires
   nothing is worse than no button.
2. **An action whose `kind` needs M3 or M4 renders labelled and inert** — visibly `not yet`, with a
   title naming the milestone (RD6). §12 says "the row is never a dead end"; an unlabelled dead button
   *is* the dead end.
3. **`external` and `inspect` are live at M2** where they can be: `external` is a link when `target`
   is set (§12's `[↗]`), and `inspect` expands the row. Everything shown in the expansion is already
   in the row, so no log and no transcript is read.

**Expected Artifacts:** a stopped row, an expansion, a source footer.
**Required Checks:**
`test_stopped_row_renders_why_and_first_action`,
`test_expanded_row_lists_every_action_with_its_source`,
`test_source_footer_counts_by_source` (and at M2 reads `N heuristic`),
`test_why_is_a_note_not_a_button_without_the_lane` (**N10**),
`test_unreachable_action_kinds_are_labelled_not_silently_dead` (**RD6**),
`test_external_action_with_a_target_is_a_link`,
`test_external_action_without_a_target_is_not_a_link` (G-M2-7 — `Chase — what it is waiting on is not
recorded` has no url and must not pretend to),
`test_expansion_reads_no_log_and_no_transcript` (**K14** — the scan looks for a fetch of any path
outside `API_ROUTES`),
`test_no_unescaped_interpolation_in_frontend` (inherited),
`test_row_with_zero_actions_is_only_a_confident_completed` (§14's rule, rendered).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/web -q`.
**Exit Criteria:** ten pass; escaping scan green.
**Test Seams:** integration (route + static scan).

**Consumes:** `next_actions` and `bucket` from `project_session` / `project_fleet_row` (T13);
`bucketChip(row)` (T14).
**Produces:**
```js
function actionButton(action) { … }    // live | labelled-inert | link, never a silent dead button
function stoppedRow(row) { … }
function expansion(row) { … }          // ordinal list + "N heuristic" footer
```

---

### Task 16: the Needs-You rail

**Objective:** §12's one element that is on **every page** and is never a page you navigate to —
showing *the actual ask*, never "session needs attention".

**Files/Surfaces:**
- `src/shepherd/web/static/rail.js` — new
- `src/shepherd/web/static/index.html`, `app.css` — the rail's slot and styling
- `tests/web/test_rail.py` — new

**Dependencies:** T13.

**Allowed Scope:** rendering the `needs_you` list `fleet_summary` already returns, fed by the SSE
stream M1 already ships.

**Out-of-Scope Drift:** approvals or a pending-approval row — §12's rail shows one, and `authorize()`
is **M4**; at M2 the rail carries sessions only. A browser notification or sound (§12 mentions both;
they need a permission prompt and a user setting, which is Settings — **M4**; recorded as **RD9**, and
the rail is built so the transition hook has an obvious place). Polling (§12: none in the UI).

**Behaviour, from §12:** fixed to the top; **empty collapses to a 4 px green line**; non-empty shows an
amber bar, the count, and **the actual ask on each row** — §12's own example row is
`payments-api · permission: Bash(…)`. `needs_you_reason` is the ask M1's normaliser already composes,
so the rail renders it and composes nothing.

**The C21 consequence is surfaced, not softened** (M1's Decision pressure 3, gap M10): `idle_prompt`
flips an idle TUI to `needs_you` 60 s after a `Stop`, so on the user's machine idle sessions **will**
appear in the rail. The reason string says `idle — waiting for your next instruction`, which is the
difference between a rail that is wrong and a rail that is precise. A session that is *both* idle and
already classified keeps its verdict; the two facts answer different questions (**E-M2-26**).

**Expected Artifacts:** a rail module, its slot, its two states.
**Required Checks:**
`test_rail_shows_the_actual_ask` (never "needs attention"; the exact `needs_you_reason`),
`test_empty_rail_collapses_to_a_line`,
`test_rail_is_on_every_page` (the slot is in `index.html`, not in one view),
`test_idle_prompt_is_needs_you_and_the_rail_says_idle` (**C21** — the honest wording),
`test_rail_updates_from_sse_not_polling` (no `setInterval`, no `fetch` on a timer),
`test_no_unescaped_interpolation_in_frontend` (inherited — the ask is untrusted text),
`test_rail_renders_with_a_null_reason` (principle 5 — `unknown`, never a blank row).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/web -q`.
**Exit Criteria:** seven pass; escaping scan green; no timer in any static file.
**Test Seams:** integration (route + static scan).

**Consumes:** the `needs_you` list from `fleet_summary` (M1, extended at T13); `sse.js`,
`escape.js`, `element()` (M1).
**Produces:**
```js
// rail.js
export function renderRail(summary, slot) { … }   // collapsed | amber bar + count + per-row ask
```

---

### Task 17: the golden lane — the classifier over real fixtures (§14 lane 1)

**Objective:** the test lane that carries the value. **No mocking of Claude Code — the fixtures ARE
Claude Code.** Adding a missed case must be: capture signals, drop in a fixture, fix the rule, run
`replay`.

**Files/Surfaces:**
- `tests/golden/corpus.py` — extended to the **second** corpus
- `tests/golden/stops.py` — new: stop fixtures = (stop record, transcript tail)
- `tests/golden/expected/verdicts.json` — new: the checked-in expected verdict table
- `tests/golden/test_classifier_golden.py`, `tests/golden/test_next_actions_coverage.py` — new

**Dependencies:** T4, T9, T12.

**Allowed Scope:** fixtures assembled from **captured data only**, and assertions over them.

**Out-of-Scope Drift:** **inventing a payload.** Every fixture is either a real capture or a
composition of real captured entries, and each composed one says which captures it is made of.
**Reading `/root/.claude/`** — 424 of 429 payloads name a `transcript_path` that still exists on this
host, and reading one would make the suite non-hermetic and dependent on a directory the user may
clear at any moment (**P-M2-15**). Mocking `claude`.

**r3 BLOCKING 3 — what "composed" costs, stated so nobody mistakes it for a claim.** Only **1 of 50**
corpus sessions has a checked-in transcript copy. A stop record whose tail cannot be read resolves to
`TurnEnding.ABSENT` → `UNKNOWN`, so a lane built naively from corpus stops alone would classify
**25 of 26 `Stop`s and all 47 `SessionEnd{other}` defers as unknown** — a majority, and acceptance
clause 11's <20% ceiling would fail on day one for a reason that is an artefact of the fixture set,
not of the classifier. **The fix is composition, not a looser ceiling:** pair each real stop record
with a real tail from the 19 checked-in copies. Both halves are captured data; only their pairing is
ours, and `test_composed_fixtures_name_their_captures` makes the pairing auditable. **What the lane
therefore does not prove** is that the *specific* transcript belonging to a *specific* corpus session
said `end_turn` — that is what **T19's live lane** exists for, against a session it creates itself.

**The fixture inventory, measured, and it is the honest coverage report:**

| Source | What it gives | Count |
|---|---|---|
| `hooks/live/*/events.jsonl` | 429 events, 50 sessions, **26 `Stop`**, **23 `StopFailure`**, **50 `SessionEnd`** | corpus 1 |
| `gap-fill/*/hooks.jsonl` | 37 sessions; **the only** `SessionEnd.reason` = `resume` (1) and `logout` (1); 7 `PreCompact` / 3 `PostCompact`; the kill-mid-compaction sequence | corpus 2 |
| `gap-fill/pidfd-pty-*/pty-hooks.jsonl` + `results.json` | the observed-process-exit evidence (C13: `waitid(P_PIDFD)` → `ChildProcessError errno=10`). **`pty-hooks.jsonl`, not `hooks.jsonl`** — the corpus-2 glob misses it (**A5, r3**) | corpus 2b |
| `transcripts/copies/**/*.jsonl` | 19 real transcripts: `end_turn` 57, `tool_use` 26, `stop_sequence` 2; `is_error` true 4; `tool_use` names `Bash` 8 `Agent` 3 `Workflow` 1 `Write` 2 | the tails |

**Coverage, stated per stop reason rather than claimed in aggregate** — this table *is* the
deliverable, because a lane that says "23 fixtures pass" while five reasons have none is a lane that
lies:

| Reason | Fixture | Source |
|---|---|---|
| `RATE_LIMITED` | real | `S08_mock_http429` |
| `AUTH_FAILED` | real ×2 | mock 401 / 403 |
| `ACCOUNT_BLOCKED` | real | mock 400 credit balance |
| `BAD_REQUEST` | real ×15 | `S07_bad_model` (real API), mock prompt-too-long |
| `SERVER_ERROR` | real ×2 | mock 500, **mock 529** |
| `TRUNCATED` | real | `S08_mock_max_tokens` |
| `UNKNOWN` (engine's own) | real | `S08_mock_http400` |
| `USER_EXITED` | real | `I01_interactive` |
| `CLEARED` | real ×2 | `S06_clear`, `I01` |
| `LOGGED_OUT` | real | `lifecycle-end-*` |
| `RESUMED_ELSEWHERE` | real | `lifecycle-end-*` |
| `CONTEXT_EXHAUSTED` | real | `lifecycle-end-*` kill-mid-compaction |
| *(benign compaction, must NOT fire)* | real ×2 | `autocompact-real-*` |
| `COMPLETED` | **composed ×26** | **r3 BLOCKING 3.** A real `Stop` record from corpus 1 + a real `end_turn` tail from the 19 checked-in copies. The *measurement* that every corpus `Stop` resolves to `end_turn` was taken by reading `/root/.claude/`, which **P-M2-15 forbids the suite to do**; only **1 of 50** corpus sessions has a checked-in transcript. Each composed fixture names both captures |
| `INCOMPLETE` (heuristic 1) | real ×1 | the one session with an open task (3 `TaskCreated`, 2 `TaskCompleted`) |
| `INCOMPLETE` (heuristics 2–4) | **composed** from real entries | the copies' `is_error` and `Write` blocks |
| `BLOCKED_EXTERNAL` | **composed** | waiting phrasing over a real tail |
| `STALLED_PENDING_TOOL` | **composed** | a real `tool_use` assistant entry as the last one — **G-M2-3** |
| `QUOTA_PAUSED` | **enum-only** | **G-M2-1**: no payload was ever captured |
| `CRASHED` · `KILLED` · `DERAILED` | **none, by design** | G-M2-2 / G-M2-4 / G-M2-6 — asserted **unreachable** |
| 5 unobserved `error` values | **enum-only**, marked | G-M2-5 |

**Expected Artifacts:** an extended loader, a stop-fixture set, a checked-in expected table.
**Required Checks:**
`test_both_corpora_load` (429 + the gap-fill count, 0 malformed in corpus 1),
`test_the_pidfd_capture_is_loaded` (**A5, r3** — `pty-hooks.jsonl` is reached; a glob that silently
matches nothing is how an evidence gap becomes invisible),
`test_every_stop_capture_produces_a_verdict` (all 26 + 23 + the gap-fill stops),
`test_verdicts_match_the_expected_table` (a checked-in table, regenerated only by an explicit command,
never silently — the shape M1's `expected/sessions.json` already set),
`test_replay_of_the_golden_lane_is_byte_identical` (twice, same table — M1's own discipline),
`test_every_stop_reason_has_a_fixture_or_a_named_gap` (**the coverage table above, as a test**: a
reason with neither is a failure, and the gap ids are the only accepted excuse),
`test_every_stop_reason_in_the_table_has_a_non_empty_action_list_unless_completed` (**§14's literal
sentence**),
`test_corpus_unknown_rate_is_under_20_percent` (**P-M2-14** — DP8's defer working, measured **over the
stop-fixture population defined below**, not over raw corpus stops),
`test_no_fixture_reads_the_real_claude_dir` (**P-M2-15**),
`test_composed_fixtures_name_their_captures` (every composed fixture carries a `sources` tuple naming
real capture paths, and the test asserts each path exists — the mechanical form of "no shape without
a capture", K1),
`test_unreachable_reasons_are_unreachable` (**P-M2-12** over both corpora).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/golden -q`.
**Exit Criteria:** ten pass; the expected table is checked in; **every** row of the coverage table is
either a fixture or a named gap id; the whole suite green.
**Test Seams:** unit (the classifier is a pure function; the fixtures attach at the lowest seam that
covers the risk — §14 lane 1's whole design).

**Consumes:** `classify(evidence) -> Verdict`, `classify_end_turn` (T9);
`mechanical_reason(...)`, `ERROR_RULES`, `REASON_RULES` (T4);
`build_stop_evidence(...)` (T6); `read_tail(...)` (T3); `replay(...)`, `ReplayReport` (T12);
`CorpusEvent`, `load_corpus()`, `sequential_order(events)`, `session_table(...)`,
`load_expected()`, `write_expected(table)` (M1 `tests/golden/corpus.py`).
**Produces:**
```python
GAPFILL_ROOT: Path
GAPFILL_HOOK_GLOBS: tuple[str, ...]   # ("*/hooks.jsonl", "pidfd-pty-*/pty-hooks.jsonl")  — A5
def load_gapfill_corpus() -> list[CorpusEvent]: ...
@dataclass(frozen=True) class StopFixture:
    name: str; evidence: StopEvidence; expected: StopReason; sources: tuple[str, ...]
def load_stop_fixtures() -> list[StopFixture]: ...
def verdict_table(fixtures: Sequence[StopFixture]) -> dict[str, dict[str, object]]: ...
```

---

### Task 18: the two blockers M1 assigned to M2 — the composition root's headroom, and `PostToolBatch`

**Objective:** own everything in the daemon's wiring that M2 needs — **the composition root's
headroom (T18-3)** and, added at r3, **the stop path's construction**, which the fresh review proved
nobody else owns.

**T18-3 is about headroom, not about a number.** `controld.py` was 150 lines at r2, 154 and failing
the cap mid-r3, and 148 and green twenty minutes later. **The constraint is what matters:** ADR-1 caps
it at 150, M2 adds the stop path's construction and two tools, and the file must end with room to
spare rather than sitting on the line. Whatever step 0b row 1 records, that is this task's starting
point.

**r3 BLOCKING 2 — `handle_stop` was fully tested and never ran.** `HookLane.__init__(store, publish)`
(`hook_lane.py:62`) takes no `StopLog` and no `projects_root`, and `controld.py:91` constructs it that
way. T11 forbids touching the composition root, T18 (at r2) forbade behaviour change, and T12 only
registers a tool — so **nothing anywhere constructed `RotatingJsonlLog` or resolved `log_dir` /
`diff_dir`**, while T19 and acceptance clause 12 both require a real stop to land a record under
`logs/stops/`. This is exactly the hole DP6 caught in revision 1, one level up: a seam with no caller.
**Task 18 takes it**, because it already owns `controld.py` alone and no track may share a file.

**r3 router decision — T18-2 (`PostToolBatch`) is DEFERRED past M2.** Verifying it needs a real hook
install against a real session, and the user's standing rule forbids touching their
`~/.claude/settings.json` (K3). The two refusal counters stay correct and idle. **What M2 owes
instead:** `doctor` must **say they are idle** rather than implying coverage — a counter reading `0`
is indistinguishable from a counter that cannot fire, and principle 5 is the whole reason that
distinction matters.

**Files/Surfaces:**
- `src/shepherd/toolsurface/compose.py` — **already exists (51 lines, verified at r3)**; extended with
  the `replay` tool and the bucket projection
- `src/shepherd/daemons/controld.py` — measured at **150 → 154 (red) → 148 (green)** across r2/r3;
  this task keeps it **under ADR-1's cap with room to spare** **and** constructs the stop path: `StopLog(RotatingJsonlLog(dirs.data_dir / "logs" / "stops", prefix="stops"))`, the
  `projects_root`, and the `diff_dir`, handing them to `HookLane`
- `src/shepherd/signals/hook_lane.py` — **`__init__` gains two defaulted parameters**, additively:
  `stop_log: StopLog | None = None`, `projects_root: Path | None = None`. With neither, behaviour is
  byte-identical to M1's, so every existing `HookLane(store=…, publish=…)` call site and test keeps
  working — the same additive widening M1's own T9 blocker used for `inspect_hooks`
- `src/shepherd/cli/main.py` — the `recompute` stub's text (**A2**)
- `src/shepherd/toolsurface/tools_m1.py` — `doctor`'s anomaly view marks the two refusal counters
  **idle, not zero** (the T18-2 deferral's debt)
- `tests/toolsurface/test_compose.py`, `tests/daemons/test_controld.py`,
  `tests/signals/test_hook_lane.py`, `tests/cli/test_commands.py` — extended
- **`src/shepherd/engines/claude_code/events.py` is NOT touched** — T18-2 is deferred

**Dependencies:** the headroom half has **none** and runs on day 1, in parallel with T1. The
**stop-path construction half depends on T5 and T11** (it constructs what they define), so this task
lands in two commits and its second half is a convergence point. The dependency graph carries both edges.

**Allowed Scope:** registration wiring; the composition root's line budget; two **defaulted**
parameters on `HookLane.__init__`; the stop path's construction; two text changes (`recompute`,
the idle counters). **No behaviour change to anything that exists**: the same tools, the same order,
the same blast classes and audiences, and `HookLane` with no new argument behaves exactly as it does
today.

**Out-of-Scope Drift:** raising ADR-1's 150-line cap (the entry offers it as an option; moving the
list out is the better half, because the cap is a proxy for "no logic here"). Putting stop **logic**
in `controld.py` — it constructs the collaborators and hands them over; `handle_stop` stays in
`signals/` (ADR-M2-7). Making `HookLane`'s new parameters **required** — that would break every
existing call site and test, which is the opposite of the point. **Touching `SUBSCRIBED_EVENTS` or the
real `~/.claude/settings.json`** (K3, and T18-2 is deferred).

**T18-3 — `compose_tool_surface` exists; verify and extend it (A6).** Revision 2 said "extract it".
By r3 a remediation had already created `toolsurface/compose.py` (51 lines) and `controld.py` had
grown to **154 lines**, so `tests/boundaries/test_composition_root.py` is **failing right now**. The
work is therefore *verify what the helper registers, extend it with M2's tools, and bring the root
back under the cap* — not an extraction. `compose_tool_surface(...)` takes what the tools need and
returns nothing; `controld` calls it once and then `freeze_registry()`, in the order ADR-7 requires
(**before the server binds**).

**The stop path's construction (r3 BLOCKING 2).** `controld` resolves two directories under
`HostDirs.data_dir` — `logs/stops/` and `logs/replay/` (ADR-2: `logs/` **receives** its paths) —
builds one `StopLog`, and passes it plus `projects_root` into `HookLane`. That is four lines in the
composition root and zero logic, which is what ADR-1's cap is protecting. `HookLane` then has what
`handle_stop` needs, and **T11's seam finally has a caller in a running process**.

**T18-2 — `PostToolBatch`: DEFERRED past M2 (router decision, r3).** M1's T11-2 built
`TOOL_BLOCKED_BY_HOOK` and `TOOL_PERMISSION_REFUSED` from 40 real captures (1 hook-block marker, 7
permission sentences) and they **can never fire**, because nothing dispatches the event. Subscribing
it changes what is written into the user's `settings.json`, and verifying that needs a real install
against a real session — which **K3 forbids**. So the entry stays open, and **M2 pays the honesty
debt instead**: `doctor` reports the two counters as **`idle — PostToolBatch is not subscribed (M1
blocker T18-2)`**, never as `0`. A zero that cannot move is a claim of coverage; saying so is
principle 5. The blocker entry is re-pointed from "T9/T18 → M2" to a milestone that can install hooks
(M3 spawns sessions; M6 owns packaging), with the checklist M1 wrote preserved verbatim: add the name,
re-review the installer's dry-run diff, re-run `test_hookd_latency_under_10ms` against E34's 3.2 ms
budget, and assert the real settings file's sha256 is unchanged.

**Expected Artifacts:** a composition root back under its cap, a constructed stop path, an honest
`doctor` line.
**Required Checks:**
`test_compose_registers_every_tool_the_daemon_had` (the names read off the helper equal the names
`controld` registered before — a list, compared, not counted),
`test_compose_is_called_before_freeze_registry` (ADR-7),
`test_no_composition_root_file_exceeds_150_lines` (inherited — it has gone red and green twice during
this plan's writing; it must be **green with the stop path and both new tools wired**, which is the
only version of it this task controls),
`test_controld_still_wires_two_lanes_and_three_threads` (M1's `tests/daemons/test_controld.py` passes
**unchanged**),
`test_controld_constructs_the_stop_log_and_hands_it_to_the_hook_lane` (**r3 BLOCKING 2** — the seam
has a caller),
`test_hook_lane_without_a_stop_log_behaves_exactly_as_before` (the additive widening: every M1 call
site and test is untouched),
`test_a_real_stop_lands_a_record_under_logs_stops` (through `controld`'s own construction, not a
hand-built one — this is the test whose absence was the finding),
`test_log_directories_are_resolved_from_host_dirs_only` (ADR-2 — `logs/` never reads the environment),
`test_recompute_stub_no_longer_claims_m2_has_not_happened` (**A2**),
`test_doctor_reports_the_refusal_counters_as_idle_not_zero` (**the T18-2 deferral's debt** — the
string says `PostToolBatch is not subscribed`, and a test reads it so it cannot be quietly dropped),
`test_post_tool_batch_is_still_not_subscribed` (24 events — **the deferral, asserted**, so a later
build cannot subscribe it without noticing this decision).
**Checkpoint Type:** **none (AFK)** — changed at r3. The human_verify checkpoint existed for the
installer dry-run diff, and **T18-2 is deferred**, so nothing in this task writes to a file Claude
Code owns.
**Validation Level:** Deterministic — `.venv/bin/pytest tests/daemons tests/toolsurface tests/signals/test_hook_lane.py tests/cli tests/boundaries -q`.
**Exit Criteria:** eleven pass; `controld.py` **under** ADR-1's 150-line cap *with the stop path and
both M2 tools wired*, and the whole boundary suite green; `~/.claude/settings.json` untouched by construction (nothing here
writes one); **T18-3 closed** and **T18-2 re-pointed with its deferral reason** in
`docs/plans/2026-09-16-m1-BLOCKERS.md`.
**Test Seams:** integration (`invoke()` + the daemon's own construction).

**Consumes:** `compose_tool_surface(store, host, db_path, ingest)` **as it exists today** (verified
at r3: `toolsurface/compose.py`, 51 lines — read it before changing the signature);
`register(tool: ToolDef) -> None`, `freeze_registry() -> None`, `reset_registry()` (M1);
`HookLane`, `HookLane.apply(frame)` (M1 `signals/hook_lane.py:62`); `HostDirs`, `HostPlatform.dirs()`
(M1 `host/base.py`); `Store`, `open_store(db_path: Path) -> Store` (M1);
`StopLog`, `RotatingJsonlLog(directory, prefix, max_bytes, retention_days)` (T5);
`register_replay_tool(store, log_dir, diff_dir)` (T12); `handle_stop(...)` (T11).
**Produces:**
```python
# compose.py — signature EXTENDED additively, never re-shaped
def compose_tool_surface(store: Store, host: HostPlatform, db_path: Path, ingest: object,
                         *, log_dir: Path | None = None,
                         diff_dir: Path | None = None) -> None: ...
# hook_lane.py — two DEFAULTED parameters; M1's two-argument call still works
class HookLane:
    def __init__(self, store: Store, publish: Publisher, *,
                 stop_log: StopLog | None = None,
                 projects_root: Path | None = None) -> None: ...
STOPS_LOG_DIRNAME  = "logs/stops"     # resolved under HostDirs.data_dir by controld (ADR-2)
REPLAY_LOG_DIRNAME = "logs/replay"
# SUBSCRIBED_EVENTS is UNCHANGED at 24 names — T18-2 is deferred (r3)
```

---

### Task 19: the live lane — one real stopped session, classified end to end

**Objective:** prove the claim the unit seams cannot: that a **real** Claude Code session stopping on
this host produces a verdict, a log record and a repainted row. M1 built `tests/e2e/` for exactly this.

**Files/Surfaces:**
- `tests/e2e/test_live_stop_classification.py` — new
- `tests/e2e/conftest.py` — extended if a fixture is needed

**Dependencies:** T11, T12, **T18 (both halves — the stop path must be constructed in the daemon
before a live run can land a record; r3 BLOCKING 2)**.

**Allowed Scope:** one live test module, under the existing `live` marker, excluded from the default
run. It reads; it spawns at most one throwaway `claude -p` in a throwaway working directory.

**Out-of-Scope Drift — and the safety rules are absolute:**
- **K6.** Never `tmux kill-server`. If a spike needs tmux at all, `tmux -L shepherd-spike` on **every**
  invocation including teardown. **The user has live sessions on the `shepherd` socket.** M2 needs no
  tmux at all (that is M3), so the honest scope here is: **do not touch tmux.**
- **K3.** The real `~/.claude/settings.json` is not modified. M1's probe Finding 3 proved a live
  `claude` cannot be both isolated and authenticated on this host, so isolation is by **throwaway
  working directory + an explicit `--settings` file**, exactly as M1's T18 live lane does, with the
  P13 sha256 guard asserted **per test**.
- No assertion on wall-clock timing; no assertion that requires the network to be fast.

**What it proves, and nothing more:**
1. A real `-p` run that ends normally produces a `Stop`, a transcript whose last `assistant` entry is
   `end_turn`, and a verdict with `decided_by = heuristic`.
2. The stop record is on disk under `logs/stops/`, readable, and re-classifying it reproduces the
   columns (**C-M2-7** in the real world, not only in `tmp_path`).
3. `replay` inside `controld`'s own process is idempotent against that record (**DP9** — this is where
   the command is genuinely exercised).
4. The fleet page's tree carries the row's bucket.

**Expected Artifacts:** one live module.
**Required Checks:**
`test_a_real_session_stop_produces_a_verdict` (live),
`test_the_stop_record_is_on_disk_and_replays_to_the_same_columns` (live),
`test_replay_inside_controld_is_idempotent` (live),
`test_real_settings_file_is_untouched` (P13, per test),
`test_no_tmux_socket_is_touched` (assert no `tmux` invocation at all in this module).
**Checkpoint Type:** **human_verify** — reason category **manual-verification**: a live run that
spawns a real `claude` process on the user's machine is read once by a human before it is trusted,
and the §18 incident is why that is not paranoia.
**Validation Level:** **Live** — `.venv/bin/pytest tests/e2e -m live -q`. See Live Verification
Strategy.
**Exit Criteria:** five pass under `-m live`; the default run (`-m "not live"`) is unchanged; the real
settings file's sha256 is identical before and after; no tmux command was run.
**Test Seams:** e2e (the only seam that can prove principle 4 and C-M2-7 against reality).

**Consumes:** `handle_stop(...)` (T11); `replay(...)`, `ReplayReport` (T12);
`compose_tool_surface(...)` (T18); `read_stop_records(directory, since)` (T5);
M1's `tests/e2e/conftest.py` fixtures and its `live` marker.
**Produces:** `Produces: none` — a test module produces no importable surface.

---

## Live Verification Strategy

**Why a live lane at all.** Three of M2's claims are unprovable in `tmp_path`: that a real transcript's
last `assistant` entry is reachable at the moment a real `Stop` arrives (the append race A9 bounds but
cannot close), that the stop record survives a real process boundary, and that `replay` works in the
process that owns the store (**DP9**). M1 built the lane and it passes 7 tests; M2 adds 5.

| Field | Value |
|---|---|
| **Command** | `.venv/bin/pytest tests/e2e -m live -q` |
| **Default run** | `.venv/bin/pytest -m "not live" -q` — the live lane is **excluded**, as M1 set it up |
| **Isolation** | throwaway working directory + explicit `--settings` file. **Not** `CLAUDE_CONFIG_DIR`: M1's probe Finding 3 proved `CLAUDE_CONFIG_DIR=<throwaway>` gives `Not logged in`, rc=1 — isolation and authentication are mutually exclusive on this host |
| **Guard** | the real `~/.claude/settings.json` sha256 asserted unchanged **per test**, not per suite (M1's F10 lesson) |
| **tmux** | **not used.** M2 needs no pty. If that ever changes it is `tmux -L shepherd-spike` on every invocation, never a bare `kill-server`, and never the `shepherd` socket (K6, §18 incident) |
| **Blast radius** | one `claude -p` process in a throwaway dir; no write outside `$XDG_DATA_HOME/shepherd` and the throwaway dir |
| **Flake policy** | a live test that fails is **investigated, never retried into green**. If the failure is the engine being slow, the assertion was wrong — no timing assertions are allowed in this lane |
| **What it does not prove** | `shepherd replay` in a process `controld` did not start (blocker T18-1, M4) — acceptance clause 12 |
| **Checkpoint** | human_verify before the first run, then AFK |

---

## Verification strategy (critical_path requirement)

**The gate function.** A task is done when its Required Checks pass **and** the whole suite passes —
not when its own tests pass. M1 shipped 407 tests and M2 touches `core/`, which every one of them
imports; a task that leaves the suite red has not finished, whatever its own file says.

**Four levels, and every task states which it is:**

| Level | Where | Command |
|---|---|---|
| **Deterministic** | every task | `.venv/bin/pytest <paths> -q` |
| **Type** | every task | `.venv/bin/mypy --strict src/shepherd` — no `Any`, `disallow_any_explicit` |
| **Boundary** | every task touching `core/`, `signals/`, `engines/`, `web/`, `cli/` | `.venv/bin/pytest tests/boundaries -q`, **with no new exemption** (K11) |
| **Golden regression** | T10, T17 | the 429-event table must stay byte-identical for every existing kind |

**Probabilistic: none.** M2 adds no timing-sensitive path. M1's one probabilistic test
(`test_ingest_throughput`) is untouched.

**Live: one task, T19.** M1 shipped `tests/e2e/` with a `live` marker and 7 passing live tests, so the
lane exists and M2 uses it. `pytest -m "not live"` stays the default run; `pytest tests/e2e -m live` is
the separate gate. See **Live Verification Strategy** below. What M2 still does **not** claim is a
`shepherd replay` that works in a process `controld` did not start — that is blocker T18-1 and
**DP9**, and acceptance clause 12 says it in those words.

**The mutation discipline M1 established applies to every new boundary-adjacent check.** A check that
cannot fail has not checked: for each of P-M2-5, P-M2-6, P-M2-10, P-M2-11 and P-M2-15, plant a real
violation in `src/shepherd/` (not only in a fixture) and assert the check goes red. M1's r6
remediation is the precedent — its acceptance evidence was a mutation sweep, not a green run.

**Evidence array, per task:** command run, exit code, counts (`N passed, M skipped`), and for the
golden lane the **diff** against the checked-in expected table. "Tests pass" without the counts is not
evidence.

---

## Dependency graph and the four independent tracks

```
              step 0: drift_check.py --record   (G-M2-8)
              step 0b: four reality re-checks   (DP6)
                                 │
                    ┌────────────┴─────────────┐
                   T1  core/stops.py          T18  compose + PostToolBatch
                    │                          (TRACK E — no dependencies,
                    │                           runnable from day 1)
        ┌────────────────┬───────┴────────┬──────────────────┐
        │                │                │                  │
   TRACK A (schema)  TRACK B (evidence)  TRACK C (rules)   TRACK D (surfaces)
        │                │                │                  │
       T2  ─────────────►│                T7 ◄──── T2        │
   migration 002         T3  tail          │                  │
   store verbs           │                 T8  heuristics     │
        │                T4  stop map      │                 │
        │                │                 T9  verdict ◄──T7,T8
        │                T6  evidence ◄─T3,T4                │
        │                                                    │
       T10 fold rows ◄── T1,T2                               T13 read tools ◄── T2,T7
        │                                                     │   (EXTENDS M1's fleet_tree)
       T5  logs ◄── T1                                        T14 palette
        │                                                     T15 stopped rows
        └──────────► T11 stop lane ◄── T2,T5,T6,T9,T10        T16 rail
                          │
                     T12 replay ◄── T2,T5,T9
                          │
                     T17 golden lane ◄── T3,T4,T9,T12
```

**Five tracks, four of them workable in parallel after T1 and one from day 1** — the property that
made M1's overnight run survivable:

- **Track A — schema.** T2 → T10 → T5. Touches `store/`, `core/`, migration files.
- **Track B — evidence.** T3 → T4 → T6. Touches `engines/claude_code/` only.
- **Track C — rules.** T7 → T8 → T9. Touches `signals/` only.
- **Track D — surfaces.** T13 → T14 → T15, and T16 beside them. Touches `toolsurface/tools_m1.py`,
  `web/static/`.
- **Track E — the daemon's wiring.** T18 alone, in **two commits**. Its *headroom* half has **no
  dependencies**, starts before T1, and must finish before anything wires a new tool into `controld` —
  the boundary suite has gone red and green twice under this plan, so this half is about leaving the
  root with **headroom**, not about a line count. Its *stop-path
  construction* half **depends on T5 and T11** (it constructs what they define) and is the fourth
  convergence point (**r3 BLOCKING 2**). Touches `toolsurface/compose.py`, `daemons/controld.py`,
  `signals/hook_lane.py` (two defaulted parameters), `cli/main.py` (the `recompute` text),
  `toolsurface/tools_m1.py` (the idle-counter line). **`engines/claude_code/events.py` is NOT
  touched** — T18-2 is deferred.
- **T19 (live) is last**, after T11, T12 and T18, and is the only human_verify task besides T18's diff
  review.

**No two tracks share a file.** That is a hard rule, not a preference: half of M1's blocker file is
two builders in one file (`tools_replay.py` at T12 vs `tools_m1.py` at T13 is this rule being applied
before it bites; so is Track E owning `controld.py` alone). The four convergence points are **T11**,
**T12**, **T17** and **T19**, and each has a single owner.

**One ordering constraint that is not a data dependency:** T12 and T13 both add a capability to the
composition root, and **T18's headroom half must land first** or they will push `controld.py` further
past its cap — it is already over, at 154 lines. The graph shows that half with no inbound edge for
that reason: it is a precondition, not a consumer. **T18's second half is a consumer** (T5, T11) and
carries real edges.

**A blocker in any one track leaves three workable.** T1 is the only universal dependency, and it is a
types-only module with no logic.

---

## Plan Completeness Gate — self-check before save

1. **Every task has a test that verifies completion.** ✓ — 19 tasks, every one with a named
   `Required Checks` list and an `Exit Criteria` line stating counts.
2. **Every task lists exact file paths.** ✓ — every `Files/Surfaces` entry is a path, not a module
   description.
3. **Every task has exit criteria that are checkable.** ✓ — "N pass; `mypy --strict` clean; boundary
   suite green with no new exemption", never "done".
4. **Dependencies are explicit task ids.** ✓ — and the graph above is acyclic, verified by walking it.
5. **Scope drift is named per task.** ✓ — and the D34 case (T9) is named at the level of individual
   forbidden symbols, because that is the one drift the milestone is defined by.
6. **Consumes/Produces are verbatim-matched.** ✓ — see the self-review below.
7. **Validation level stated for every task.** ✓ — eighteen Deterministic and one **Live** (T19),
   which is why the **Live Verification Strategy** section exists. *(T18's Manual half and its
   human_verify checkpoint were removed at r3 when T18-2 was deferred: nothing in M2 now writes to a
   file Claude Code owns, so there is no diff for a human to read.)*
8. **Risk-based testing matrix complete.** ✓ — 31 rows, every high/high and high/med row carrying a
   deterministic test; the one row whose mitigation is a checklist ("this plan's repo facts go stale
   again") is med-impact and its checklist is **step 0b**, which is a numbered command table with an
   assert/record column, not a sentiment. **Five rows were added at r3, and four of them describe
   defects the plan had at revision 2** — they are kept rather than deleted so the next reader sees
   what the review caught.
9. **No placeholders or TBD.** ✓ — every table is filled; where a value is unknown it is a named gap
   with a disposition, not a blank.
10. **Open decisions listed, not hidden in prose.** ✓ — **none**; **ten** Decision pressures and nine
    Recommended Defaults, each explicitly unapproved. **DP10 is the one place M2 does not follow a
    decision's literal words, and it is a numbered Decision pressure with a one-line reversal rather
    than a gap-table row** (r3 BLOCKING 4).

**Prefactor question applied.** Three abstractions were proposed and rejected: a `Classifier` Protocol
(D34 forbids it by name, and it would have zero implementations), a `StopLane` class (ADR-M2-7 — one
caller, no state between calls), and a `repo_for_path` store verb for heuristic 4 (M1's blocker T11-3
already found it has no caller; the tail has no such hole, so the heuristic reads the tail). One
abstraction was **kept** because it has two callers in this plan: `RotatingJsonlLog`, used by the stop
log and the replay diff, and with the audit log (M4) as its third.

---

## Self-review — cross-phase contract drift

Every `Consumes` entry checked verbatim against the `Produces` that supplies it, and against the
shipped code for M1 symbols. Findings, all fixed inline before save:

- **`replay` collided with itself.** `tests/golden/corpus.py` already ships a function named `replay`,
  and T12 produces `signals/replay.py::replay`. T17's `Consumes` block named both. **Fixed:** T17
  consumes `replay(...)`/`ReplayReport` from T12 and, from M1's loader, only `load_corpus`,
  `sequential_order`, `session_table`, `load_expected`, `write_expected` — the loader's own `replay`
  is no longer named, so the two never appear unqualified in one list.
- **`StopReason.CLEARED` vs `core.fold_types.CLEARED`.** Two symbols, one word, two meanings (a stop
  reason and the empty-string clear sentinel). **Fixed:** T1's contents table states the hazard, and
  T10 introduces `CLEARED_STAMP` as the named alias for timestamp columns so no module ever needs both
  names unqualified.
- **`tools_m2.py` had two owners.** T12 and T13 both named it. **Fixed:** T12 owns
  `toolsurface/tools_replay.py`; T13 owns `toolsurface/tools_m2.py`.
- **`FoldResult`'s lesson applied pre-emptively.** M1's BLOCKER T7b-1 was two structurally identical
  types written by two concurrent builders. Every M2 type that crosses a track boundary —
  `StopEvidence`, `Verdict`, `TranscriptTail`, `NextAction` — is defined **once**, in T1, in `core/`,
  before any track starts. No task defines a type another track also needs.
- **`Store.fleet()` returns `FleetRow`**, and T7's `bucket_of` takes one — checked against
  `src/shepherd/store/models.py:99`. T2 adds `outcome` to `FleetRow`; without that addition `bucket_of`
  cannot work, so T7's `Consumes` names T2 and the graph carries the edge.
- **`fleet_sort_key(row, now) -> tuple[int, str]`** — verbatim from `signals/ordering.py`. T7's new key
  is a *second* function, not a replacement, so M1's tests stay green; T7's Required Checks say so.
- **`parse_hook_payload(raw: bytes, received_at: str) -> Signal | MalformedPayload`** — verbatim from
  `engines/claude_code/normalise.py:230`.
- **`locate_transcript(projects_root: Path, engine_session_id: str) -> Path | None`** — verbatim from
  `engines/claude_code/transcript.py:76`.
- **`open_store(db_path: Path) -> Store`**, `migrate(db_path, migrations_dir=None) -> int`,
  `read_schema_version(db_path) -> int`, `EXPECTED_SCHEMA_VERSION` — verbatim from `store/`.
- **`invoke(name, args, ctx) -> ToolResult`**, `register(tool: ToolDef) -> None`,
  `publish(event: StreamEvent) -> int` — verbatim from `toolsurface/`.
- **`ToolDef` fields** — `name, description, input_schema, blast_class, handler, audiences` — verbatim
  from `toolsurface/types.py:44`; T12's and T13's tools name all six.
- **`SIGNAL_FIELD_KEYS` is a closed set of 11**, and T6 reads `failure_note`, which is already a member
  — so no new key is needed for the stop path, and T10's one addition is for the quota/compact rows,
  which read no field at all. **Re-checked:** T10's Produces therefore adds **no** new
  `SIGNAL_FIELD_KEYS` member; the earlier draft said "gains 1" and that was wrong. **Fixed** in T10's
  Files/Surfaces line, which now says the closed set is unchanged.

**Added at revision 2, after the plan-review gate found the tree had moved under the plan:**

- **`fleet_tree` was a phantom Produces.** T13 declared `def fleet_tree(...)` and
  `register_fleet_tree_tool(...)` as new, against a function that already exists in
  `toolsurface/tools_m1.py` with the **same name and the same signature**. Consumes/Produces matching
  catches drift *between phases of this plan*; it cannot catch a collision with the repo. **Fixed:**
  T13 now consumes `fleet_tree(store, clock)` from M1 and produces no new name for it, and **step 0b
  row 2 makes the check mechanical** for the next plan.
- **`handle_stop` had no caller.** T11 produced it and nothing consumed it, because revision 1 assumed
  no composition root existed. **Fixed:** `HookLane` is the caller, named in T11's Allowed Scope, its
  Consumes block and its Required Checks.
- **`compose_tool_surface` is the new convergence point.** T12 and T13 both register a capability, and
  both now go through T18's helper rather than editing `controld.py` — so the file two tracks would
  otherwise have shared has exactly one owner.
- **`SUBSCRIBED_EVENTS` moves from 24 to 25**, and it is produced by T18 and consumed by nothing else
  in M2 — `normalise.py`'s Table A already maps `PostToolBatch` (M1 built the row; only the
  subscription was missing). Checked against `engines/claude_code/events.py`.

**Added at revision 3, from the fresh review — three of the four blocking findings were
*consequence* drift, not *name* drift, which is the class this self-review had no way to catch:**

- **A type shared by two rules is not the same as a rule.** T10 gave `Stop` and `SessionEnd` one
  `SignalKind` (as M1 does) while T4 required them to behave differently. Every name matched; the
  *behaviour* could not. **Fixed** by the split, and the lesson is recorded in T10's table: when two
  events stop having the same column effect, the enum grows a member — that is ADR-6's rule and it
  works only if someone checks the effects, not the names.
- **A produced symbol with no constructor is as dead as one with no definition.** `handle_stop` was
  produced by T11 and consumed by T19 and acceptance clause 12 — but **nothing constructed its
  collaborators**, because `HookLane.__init__` takes two arguments and T11 was forbidden to change it.
  **Fixed** by giving T18 the wiring. **The check this self-review now owes:** for every `Produces`
  entry that needs a collaborator, name the task that *constructs* it, not just the task that calls it.
- **A fixture population is part of a contract.** P-M2-14's "<20%" was measured against a population
  the suite is forbidden to read. **Fixed** by naming the population in the property itself.
- **`compose_tool_surface` was produced by T18 and already existed in the repo** — the same class of
  collision as `fleet_tree` at r2, caught this time by a reviewer rather than by the gate. **Step 0b
  row 3 now asserts it.**

**Self-review result: no remaining cross-phase reference drift; the two repo collisions the gate found
and the four consequence gaps the fresh review found are closed.**

---

## Recommended Defaults (proposed, **explicitly unapproved** — a reviewer may overturn any of these)

Each is low blast radius and additive. None touches one of the 55 decisions; anything that did is a
Decision pressure above.

| # | Default | Why it is safe |
|---|---|---|
| **RD1** | `TAIL_ENTRIES = 20` — §8 says "last ~20 `user`/`assistant` entries". | One constant; widening it costs a re-read at stop time only. Named so a reviewer can pick 30. |
| **RD2** | `FAILURE_TAIL_N = 3` — §8's heuristic 3 says "last 3". | Verbatim from §8. |
| **RD3** | `MAX_BYTES = 32 MiB` for a daily stop log — D25 gives no number. | A stop record is "a few KB" (D25), so 32 MiB is ~8 000 stops a day. Rolls rather than truncates. |
| **RD4** | The promise / waiting / change vocabularies are **literal captured wordings only**, and an unmatched phrase **under-fires**. | Identical to M1's refusal classifier (BLOCKER T11-2, applied "from the captures rather than from a guess"). Under-counting is honest; inventing is not. |
| **RD5** | Heuristic resolution order: 5 → 1 → 3 → 2 → 4. | §8 calls heuristic 1 "strongest and cheapest" and makes 5 disjoint from it by construction; the rest is a stated tie-break, not a hidden one. |
| **RD6** | Action buttons whose capability is M3/M4 render **labelled inert**, not hidden and not live. | §12 says "the row is never a dead end". Hiding them would hide §8's answer; wiring them would lie. |
| **RD7** | `shepherd replay` writes the **diff always** and the **columns only with `--apply`**. | §8's example implies a write; the diff exists to be read first, and this is the one command in M2 that can damage 412 rows. |
| **RD8** | `--classifier <id>` from §8's example is **not implemented**; the diff header records what it can and says what it cannot. | M2 has no rule-set versioning. Principle 5: say the version is not recorded rather than print one. |
| **RD9** | The rail's **browser notification and sound are not built**; the transition hook has a named place. | §12 mentions both; both need a permission prompt and a user setting, and Settings is M4. |

---

## Milestone acceptance — M2 is done when

1. **The mechanical table is total and capture-backed.** All 13 `StopFailure.error` values and all 5
   `SessionEnd.reason` values map, defer, or land in `unknown` **and are counted**; eight error values
   and **all five** reason values are proven against real captures; the five unobserved error values
   carry a marker that a test reads. *(T4)*
   > **Corrected at M2 verification.** This clause said "four reason values"; the corpus census says
   > **five** (`clear` 3, `prompt_input_exit` 4, `other` 59, `resume` 1, `logout` 1). It also said the
   > marker is the literal `[UNVERIFIED]`; it is the boolean field **`verified`**, and that token
   > appears in `src/` only inside one comment and in **no** test. The implementation is *stronger*
   > than the clause described — `test_unverified_rows_are_marked` asserts `verified == captured_errors`,
   > so a marked row that later gains a capture fails rather than staying stale.
2. **No rule anywhere references `Stop.stop_reason`** (D46), and a test proves it over
   `src/shepherd/`. *(T4, P-M2-5)*
   > **FAILED at M2 verification, now fixed.** The clause claimed tree-wide proof; enforcement was a
   > substring scan of **four hand-named files of 79**. The verifier proved the hole by appending
   > `PLANTED = "stop_reason"` to `signals/stop_lane.py` — a signals module of exactly the kind this
   > clause governs — and watching all 864 tests pass.
   >
   > The tree-wide version could not be a substring scan: `stop_reason` is a legitimate name in
   > thirteen places (our `session` column, our stop-record key, our rendered payload key) including
   > `engines/claude_code/transcript_tail.py`, which reads the **transcript's** `message.stop_reason`
   > — a real captured field that merely shares the name. D46 is about a *different* field:
   > `Stop.stop_reason`, on the hook payload, absent from all 78 captured `Stop` events.
   >
   > So the rule is now a **property over the object being read**, not the word:
   > `tests/boundaries/test_stop_reason_is_never_read_from_a_payload.py` flags a subscript or `.get()`
   > of `"stop_reason"` whose receiver names a `payload`, a `fields` mapping or a `signal`. It needs
   > no exemption, and a planted `payload.get("stop_reason")` in `signals/stop_lane.py` turns it red.
3. **The completeness split runs with no model and no credential**, `decided_by = heuristic`, through
   exactly **one** named call site, `signals/verdict.py::classify_end_turn()`, with **no
   `Classifier` seam anywhere in the tree**. *(T9, D34, P-M2-11)*
4. **`next_actions[]` is total over the 20 stop reasons**, capped at 3, and **a non-`completed`
   verdict never has an empty action list** — §14's literal sentence, as a test. *(T7, T17)*
5. **The eight `session` stop columns are written** by one verb, in one transaction, and read back
   whole; migration 002 applies **over** a 001-shaped database with every row, index and default
   intact. *(T2)*
6. **The stop-evidence log exists as D25 specifies**: daily JSONL, gzip on close, a size cap as a
   second trigger, 90-day retention, and a reader that **skips malformed trailing lines** — proven
   against 200 truncations, not asserted. *(T5)*
   > **FAILED at M2 verification, now fixed.** The property was true; the *evidence had been banked
   > from a neighbour*. This reader (`scan_records`) had **two** truncations — each a single half-file
   > cut — while the 200-case proof belonged to `read_tail`, the **transcript** reader, in
   > `tests/engines/test_transcript_tail.py`. Name-matching a test to this clause would have scored it
   > PASS, which is why the verifier was told to run things rather than locate them.
   >
   > `test_the_stop_log_reader_never_raises_over_200_truncations` now runs the 200 cuts against the
   > real stop-log reader. Two things it had to get right to be worth anything: the padding is
   > **high-entropy** (repeated padding gzips to 270 bytes, which would have put most of the 200
   > "cuts" past end-of-file and quietly made it a test of an absent archive), and it asserts
   > `cuts == 200` so the loop cannot shrink silently. Proven to bite by dropping `EOFError` from
   > `logs/jsonl.UNREADABLE`.
   >
   > Worth keeping: the two readers fail *differently*. A transcript is a file the engine owns and we
   > observe; this one is a file **we wrote**, so a truncation here means our own process died
   > mid-append — which is why the property deserved its own proof rather than an inherited one.
7. **`shepherd replay` re-runs the current classifier over the log**, writes a before/after diff to
   `logs/replay/`, is **idempotent**, and never reads a transcript. *(T12, P-M2-8, P-M2-9)*
8. **The seven-bucket palette renders with a colour *and* a glyph** for all eight rendered buckets, in
   §12's order, with **`blocked` below `running`**. *(T1, T7, T14)*
9. **Stopped rows expand to their full action list**, the first action is a button, unreachable kinds
   are labelled rather than silently dead, and `[why?]` is the honest note §8 specifies. *(T15)*
10. **The Needs-You rail is on every page and shows the actual ask**, including the honest
    `idle — waiting for your next instruction` wording C21 forces. *(T16)*
11. **The `unknown` rate is a first-class fleet metric**, reported beside a separate `unclassified`
    count **and beside the low-confidence `completed` count** (r3 BLOCKING 4), and it is **under 20%
    over the stop-fixture population P-M2-14 names** — every stop record in both corpora, each paired
    with a real tail. The population is stated because 49 of 50 corpus sessions have no checked-in
    transcript and the ceiling is meaningless without it (**r3 BLOCKING 3**). *(T13, T14, P-M2-14)*
12. **`handle_stop` runs in the daemon**, not only in a test: `controld` constructs the `StopLog` and
    the `projects_root`, hands them to `HookLane`, and a real stop lands a record under
    `logs/stops/` (**r3 BLOCKING 2**). **Every claim above is proven at the unit and `invoke()` seams,
    and four of them again in the live lane** (`pytest tests/e2e -m live`): a real session's stop classifies, its record is on disk,
    re-classifying it reproduces the columns, and `replay` inside `controld`'s process is idempotent.
    **What M2 does not claim:** `shepherd replay` working in a process `controld` did not start —
    that is blocker **T18-1**, assigned to M4, and **DP9** says why building the transport now is work
    `cli/` would have to unlearn. *(T19, DP9)*
13. **The whole suite is green and the boundary suite has no new exemption.** M1's 407 tests still
    pass; `mypy --strict` is clean; the 429-event golden table is byte-identical for every pre-existing
    `SignalKind`. *(T10, T17, K11)*
14. **Every gap is named, not discovered.** `docs/plans/2026-09-17-m2-BLOCKERS.md` exists, and every
    unreachable reason (`crashed`, `killed`, `derailed`), every unverified row, and every composed
    fixture points at a gap id from this plan or at a new entry written in the four-part form.
15. **The two entries M1 handed to M2 are dispositioned, neither silently inherited.** `controld.py`
    is **below** ADR-1's cap with registration behind `compose_tool_surface`, and the boundary suite is
    green (**T18-3, APPLIED**). `PostToolBatch` is **still not subscribed** — **T18-2 is DEFERRED past
    M2** because verifying it needs a real hook install and K3 forbids one — and the debt is paid in
    the product: **`doctor` reports the two refusal counters as `idle`, not `0`**, asserted by a test.
    Both entries carry their disposition in `docs/plans/2026-09-16-m1-BLOCKERS.md`, the deferred one
    re-pointed to a milestone that can install hooks. *(T18)*
16. **Step 0b's rows were recorded before T1 started**, and any row that disagreed with this
    plan became a blocker entry rather than a discovery at T13. *(DP6)*
    > **Corrected at M2 verification:** the clause said "four rows"; the recorded table has **five**,
    > all populated, with the engine drift check clean at 2.1.273. The count is dropped from the
    > clause rather than re-pinned — a number that has already drifted once will drift again, and the
    > claim that matters is *recorded before T1*, not *how many*.

---

## Amendment log

| Revision | Date | What changed | Why |
|---|---|---|---|
| 1 | 2026-09-17 | Initial plan. | — |
| 3 | 2026-09-17 | **Fresh review applied in place: 4 blocking, 7 advisory.** B1 (C12's bound could not fire → `TURN_STOPPED`/`SESSION_STOPPED` split + `end_reason` guard, T4/T10); B2 (`handle_stop` had no constructor → T18 owns the stop path's wiring, and `HookLane.__init__` gains two defaulted parameters); B3 (the hermetic lane could not reach `completed` → 26 composed fixtures, P-M2-14's population named); B4 (**DP10** promoted from N6/ADR-M2-5, plus `completed_low_confidence` on `StopCounts`, `fleet_summary` and the page). A1 (`bucket_of` totality, `BUCKET_ORDER` honesty), A2 (`recompute`'s stale text, E-M2-31), A3 (two stream events, named `session.classified`), A4 (bounded 256 KiB tail read — the observer must not harm the observed), A5 (`pty-hooks.jsonl` glob), A6 (step 0b records vs asserts; `compose.py` already exists; `controld.py` measured 150 → 154-and-red → 148-and-green in one session, so T18-3 is framed as **headroom**, not a number), A7 (N14, N15 — "verbatim" withdrawn). **T18-2 deferred past M2** by router decision. | The review verified the evidence base independently and it held; every finding was a **consequence** the plan had not traced, and three of the four were provable by reading shipped code (`normalise.py:85-86`, `hook_lane.py:62`, `controld.py:91`). B1's two required tests contradicted each other, which is the kind of defect only a reader who runs the plan against the code can find. |
| 2 | 2026-09-17 | **Re-grounded against a tree that moved mid-write.** DP6 rewritten; DP9 added; inherited-blocker table rewritten from M1's T18 ledger sweep; six Reality Check rows corrected; T11 consumes `HookLane`; T13 extends `fleet_tree` instead of creating it; Tasks 18 and 19 added; Live Verification Strategy added; step 0b added; risk matrix +5; acceptance clauses 12, 15, 16; self-review +4. | The plan-review gate verified `daemons/controld.py` and found it **present** (150 lines) where revision 1 asserted it absent — M1's Task 18 landed while this plan was being written. Four of revision 1's claims were false; a plan that asserts an absent file which exists is a plan a builder will not trust twice. |

---

## Progress notes

*(Appended by builders. The first entry is step 0's drift check, before any mapping code is written —
G-M2-8.)*

### Step 0b — reality re-check (to be filled by the first builder, BEFORE Task 1)

| # | Command | Kind | Observed | Matches plan? |
|---|---|---|---|---|
| 1 | `wc -l src/shepherd/daemons/controld.py` | RECORD | | (154 at r3, suite red) |
| 2 | `grep -c 'def fleet_tree' .../tools_m1.py` | **ASSERT** = 1 | | |
| 3 | `ls toolsurface/compose.py signals/hook_lane.py logs/` | **ASSERT** | | |
| 4 | `pytest -m "not live" -q \| tail -3` | RECORD | | (red at r3 on the line caps) |
| 5 | `SUBSCRIBED_EVENTS` length; `PostToolBatch` among them? | **ASSERT** 24 / no | | |

An **asserted** row that disagrees is a blocker entry before T1 starts. A **recorded** row never
blocks — it is the evidence that the next reader is looking at the same tree this plan was written
against (A6, DP6).

### Step 0 — engine drift check (to be filled by the first builder)

| field | value |
|---|---|
| date | |
| command | `.venv/bin/python docs/probes/drift_check.py` |
| host engine | |
| 33 hook-event names | |
| `SessionEnd.reason` | |
| `SessionStart.source` | |
| `StopFailure.error` | |
| `Notification.type` | |
| outcome | |

A moved name or a moved enum value is a **blocker entry**, not an assumption. M1's run on 2026-09-16
was green on all four enums as exact ordered literals against the 2.1.273 binary.

---

## Step 0 / 0b — recorded by builder-AB (wf-m2-build::builder-AB), 2026-09-17, before Task 1

### Step 0b — reality re-check (filled)

| # | Command | Kind | Observed | Matches plan? |
|---|---|---|---|---|
| 1 | `wc -l src/shepherd/daemons/controld.py` | RECORD | **148** | recorded; plan measured 150 → 154 → 148. No contradiction of the *reasoning* (T18 owes headroom, not a number). |
| 2 | `grep -n 'def fleet_tree' src/shepherd/toolsurface/tools_m1.py` | **ASSERT** = 1 | **1 hit** (`tools_m1.py:175`) | ✅ T13 extends, never creates |
| 3 | `ls toolsurface/compose.py signals/hook_lane.py logs/` | **ASSERT** | `compose.py` present (**51 lines**); `hook_lane.py` present; `logs/` holds **only** an empty `__init__.py` (0 bytes) | ✅ |
| 4 | `.venv/bin/pytest -m "not live"` | RECORD | **454 passed, 1 skipped, 8 deselected** in 50.9 s — **green** | recorded; green, so no pre-T1 blocker |
| 5 | `SUBSCRIBED_EVENTS` length; `PostToolBatch` among them? | **ASSERT** 24 / no | **24**, `PostToolBatch` **not** among them (it appears twice in `events.py` — once in `ALL_HOOK_EVENT_NAMES`, once in the comment explaining its absence) | ✅ T18-2's deferral stands; `doctor`'s "idle" text is still correct |

All three asserted rows hold. No blocker entry is owed before T1.

### Step 0 — engine drift check (filled)

| field | value |
|---|---|
| date | 2026-09-17 |
| command | `.venv/bin/python docs/probes/drift_check.py --record ~/.local/share/shepherd/engine-drift-check.json` |
| host engine | **2.1.273** (discovered; captures pinned at 2.1.270) |
| 33 hook-event names | **33/33 present** in the running binary |
| `SessionEnd.reason` | UNCHANGED — exact ordered list found |
| `SessionStart.source` | UNCHANGED — exact ordered list found |
| `StopFailure.error` | UNCHANGED — exact ordered list found (13 values) |
| `Notification.type` | UNCHANGED — exact ordered list found (14 values) |
| outcome | **clean, exit 0.** Recorded to `~/.local/share/shepherd/engine-drift-check.json`. No enum moved; the captures remain trustworthy for this surface. |

### Tasks 1, 2, 3, 4, 6 — built by builder-AB, 2026-09-17

| Task | Files | Evidence |
|---|---|---|
| **T1** `core/stops.py` | +`core/stops.py` (300 lines, types only), +`tests/test_core_stops.py` | 15 tests; `StopReason` 20 · `Bucket` 8 · `TurnEnding` 5 (no engine spelling, asserted over the module's AST) · `NextAction.text`/`Verdict.why` capped at 80/120 with an ellipsis |
| **T2** migration 002 + verbs | +`store/migrations/002_m2_stop_verdicts.sql`, +`store/stops.py`, `store/{migrate,db,models,rows}.py`, +2 test modules | 24 tests; `EXPECTED_SCHEMA_VERSION` 1→2; the rebuild is asserted cell-by-cell over a fully populated 001 row, both indexes by name **and** behaviour, every DEFAULT, and an empty `foreign_key_check`. `db.py` 595/600 |
| **T3** tail reader | +`engines/claude_code/transcript_tail.py` (406), +`tests/engines/test_transcript_tail.py` | 38 tests over the 15 real captured transcripts; bounded 256 KiB read asserted on **bytes pulled off disk**; 260 truncations, empty/absent/directory/non-UTF-8 — none raises |
| **T4** the stop map | +`engines/claude_code/stop_map.py` (290), +`tests/engines/test_stop_map.py` | 45 tests over all 23 `StopFailure` and all 68 `SessionEnd` captures; the two tests that contradicted each other at r2 are **both green**; every row cites a heading that exists in `data-schemas.md` |
| **T6** evidence assembly | +`engines/claude_code/evidence.py` (160), +`tests/engines/test_evidence.py` | 18 tests; byte-identical record in a second interpreter; no clock, no write, one named neutral key |

**Suite:** `454 passed, 1 skipped` → **`599 passed, 1 skipped`**, no regressions.
`mypy --strict src/shepherd` clean over **68** files. All 14 boundary tests green
with **no new exemption** (the new `test_one_clock.py` included).

**Touched outside the five tasks' own files, each for a stated reason:**
`core/anomalies.py` (+6 append-only kinds — see BLOCKERS T3-2/T4-1),
`tests/store/test_migrations.py` and `tests/cli/test_commands.py` (schema-version
literals 1→2, which ADR-M2-4 orders; no production `cli/` code was edited).

**Four blocker entries** in `docs/plans/2026-09-17-m2-BLOCKERS.md`: T6-1
(decision gap — `end_reason` and the two fold marks have no threading path),
T3-1 (evidence gap — no non-synthetic `stop_sequence` capture), T3-2/T4-1
(decision gap — anomaly kinds needed ahead of T10), T2-1 (`PRAGMA
foreign_keys=off` is a no-op inside the runner's transaction).

---

### Tasks 5, 7, 8, 9 — built by builder-rules (wf-m2-build::builder-rules), 2026-09-17

**Shipped.** `logs/jsonl.py` + `logs/stops.py` (T5), `signals/stop_rules.py` and
`bucket_of` / `fleet_bucket_sort_key` on `signals/ordering.py` (T7),
`signals/heuristics.py` (T8), `signals/verdict.py` (T9), with
`tests/logs/test_rotating_jsonl.py`, `tests/logs/test_stop_log.py`,
`tests/signals/test_stop_rules.py`, `tests/signals/test_heuristics.py`,
`tests/signals/test_verdict.py` and thirteen tests appended to
`tests/signals/test_ordering.py`.

**Measured on this host, after.** `pytest -m 'not live'` → **706 passed, 1
skipped** (from 599/1); `mypy --strict src/shepherd` → clean, **73 files** (from
68); all 14 boundary rules green with **no exemption added**; every new module
under 600 lines (366 / 348 / 189 / 325 / 160).

**Corpus facts measured this session, and asserted in the tests rather than
quoted:** 50 sessions, **3 `TaskCreated`, 2 `TaskCompleted`**, falling in two
sessions — one closed, **one** with a single open task. That one session is the
entire positive evidence for heuristic 1, and
`test_open_task_ledger_fires_on_the_one_corpus_session_with_an_open_task`
recounts it from the captures at run time. 100 non-`<synthetic>` assistant texts
were read to build `PROMISE_PHRASES`; none of them waits on a review, a merge,
CI or a deploy (blocker T8-1).

**Deviations, each with a blocker entry:** T5-1 (`read_records`' unnamed `int`
resolved as a line number, `scan_records` added beside it), T8-1 (heuristic 5's
vocabulary is spec-derived — evidence gap), T8-2 (heuristic 1's citation cannot
be §8's verbatim heading without breaking K13), T8-3/T6-2 (**nothing injects the
promise predicate, so heuristic 2 cannot fire in production until T11/T18
threads it** — the one live wiring gap this build leaves), T9-1 (two confidence
values the plan never names). `decode_verdict` was added to T5's Produces so the
required roundtrip check can assert the `Verdict` half survives, and `replay`
can say what *changed* rather than only how many rows it re-derived.

**DP10 applied as written, both halves.** A null heuristic result is `completed`
at 0.5, and because 0.5 is below `CONFIDENT_ENOUGH` the row carries
`Review the diff` rather than an empty action list. The counter half
(`completed_low_confidence`) is T2's and is already on `StopCounts`; T13/T14
still owe it the `fleet_summary` field and the chip beside the `unknown` rate.
Without those two, ~96% of clean stops render green and nothing counts them —
the r3 BLOCKING 4 defect returns at the page instead of at the classifier.
