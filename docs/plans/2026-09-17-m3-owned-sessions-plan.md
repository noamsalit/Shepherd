# Shepherd M3 — Owned Sessions — Execution Plan

## Metadata

- **Created:** 2026-09-17
- **Status:** draft
- **Plan Mode:** execution_plan
- **Verification Rigor:** critical_path
- **Scope:** **M3 only** (spec §16). M4–M6 are out of scope and get their own plan → implementation cycles (§0).
- **Builds on:** `docs/plans/2026-09-17-m2-signals-engine-plan.md` (revision 3) and `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` (revision 6). **M1's ADRs 1–7, M2's ADRs M2-1…M2-7, the blocker protocol, the constraint keys K1–K15 and the vocabulary are inherited, not restated except where M3 changes them.**
- **Inherits open blockers from:** `docs/plans/2026-09-16-m1-BLOCKERS.md` and `docs/plans/2026-09-17-m2-BLOCKERS.md` — see "Inherited blockers".
- **Plan revision:** 2 · **Last reviewed revision:** 1 · **Fresh-review passes:** 2/2 (cap reached)
- **Revision 2 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap reached). This revision
  was amended after the last fresh pass and has been checked only by amendment verification (not
  run); no adversarial pass has read it whole. **Sections changed since the last fresh review:**
  Agreement Snapshot (pressure count); constraint keys **K3, K6, new K6-a, K16**; Vocabulary
  (write-policy key); **DP1, DP5, DP7, DP10**; Functionality flows B and C; risk matrix (+7 rows,
  3 rewritten); **G-M3-1, G-M3-2**; gap row **N4, N11**; assumption ledger (**A21, A22, new A22-a,
  new A25**) and the confidence note; **Codebase Reality Check (+7 rows)**; behaviour contract
  **C-M3-1, C-M3-3, C-M3-9**; purity boundary map (2 rows); **provable properties P-M3-1…16 rewritten
  and new P-M3-17**, plus the property↔task rule below the table; edge case **E-M3-6**;
  **ADR-M3-2, ADR-M3-4, ADR-M3-5, new ADR-M3-8**; **Tasks 1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14,
  15, 16, 18, 19, 20, 21, 22, 23, 24**; Live Verification Strategy; verification strategy's mutation
  table; dependency graph, the four changed edges and the new shared-file table; Plan Completeness
  Gate (items 1, 4, 10 and new 11–12); Self-review; acceptance clauses **1, 2, 3, 4, 5, 10, 14**;
  Progress-notes mutation table; amendment log.
  **Unchanged since the last fresh review:** DP2, DP3, DP4, DP6, DP8, DP9; K1, K2, K4, K5, K7–K15;
  G-M3-3…9; N1–N3, N5–N10, N12–N14; ADR-M3-1, ADR-M3-3, ADR-M3-6, ADR-M3-7; Tasks 3, 7, 17;
  RD1–RD9; step 0 and step 0b; the durability horizons and the context-reference table.
  **Reaching the cap is a stopping point, not closure:** a plan that has spent both fresh-review
  passes and then been amended is *unreviewed at its current revision*, however many passes it
  accumulated at earlier ones. `plan_revision` (2) ≠ `last_reviewed_revision` (1) is the checkable
  form of that sentence, and the next reader should treat revision 2 as unread rather than as twice-
  reviewed.

---

# LAYER 1 — HUMAN LAYER

## Agreement Snapshot

**Goal.** Make Shepherd able to **start a session and own it**. A tmux runner spawns `claude` into a
pane Shepherd names and keeps; the browser shows the pane's real bytes through `xterm.js`; a
programmatic write obeys one policy that knows the difference between *asking you a question* and
*holding a permission dialog open*; a message to a running session queues in a mailbox and is
delivered coalesced at the next `Stop` or prompt-ready pane; `ask()` forks the target and never
touches it; and a rename is pushed at the engine by typing `/rename` into the pty rather than by
writing into a file the engine owns.

**The one thing that must not be wrong** is the write policy (§9's own words). Everything in M3 that
sends bytes into a live agent goes through one pure decision function with one table, and the two
rows that were factually wrong in the spec (D44's permission dialog; D45's interrupted turn) are the
two rows with the most fixtures behind them.

**Constraints (all binding; K1–K15 are M1's and M2's, unchanged and still law):**

| # | Constraint | Source |
|---|---|---|
| K1 | No data shape asserted without a real captured example in `data-schemas.md`. A shape not there is a **gap**, and the task's first step is a probe. | D41, user brief |
| K2 | Nothing we install may harm Claude Code. | Principle 4 |
| K3 | **No Shepherd process writes, or deletes, under `~/.claude/`.** The real `~/.claude/settings.json` is never touched (sha256 guard per test; the file's digest is `375e5322…`, verified on this host 2026-09-17). Live tests isolate by **throwaway working directory + explicit `--settings`**, never `CLAUDE_CONFIG_DIR` (M1 probe Finding 3: isolation and authentication are mutually exclusive on this host). **What is accepted and named, not forbidden: the engine's own bookkeeping.** Every `claude` Shepherd starts writes its transcript under `~/.claude/projects/…`, a trust entry into `~/.claude.json`, and a sidecar under `~/.claude/sessions/<pid>.json` that it deletes at exit. The shipped live lane already documents this ("What a run leaves behind"); M3 multiplies it, because M3 *spawns* sessions and `ask()` forks one per call. K3 is a rule about **our** writes. The engine's writes are the engine's, are never deleted by us (DP7, N6), and are listed in the Live Verification Strategy so a reader is not surprised by them. | User brief, C6, M1 F10 |
| K4 | `mypy --strict`, Python 3.12, no `Any`, no file past ~600 lines, `daemons/*` under 150. | Principle 6, ADR-1 |
| K5 | No `shell=True` anywhere; argv lists only. | §13 |
| **K6** | **Every tmux invocation — including teardown — passes `-L` explicitly**, because a command run *inside* tmux inherits `$TMUX` and resolves to that session's own socket. Never a `:` or a `.` in a tmux session name. The user's live sessions (`aivisor`, `main`, `spike`, alive since Sep 13) are on the `shepherd` socket; Shepherd's default is `shepherd-runner` (D49) and spikes/tests use `shepherd-m3-*`. **`kill-server` is permitted in exactly one place: an argv produced by `tmux_argv` whose socket matches `^shepherd-m3-`, enforced at runtime by `check_tmux_argv` (K16).** It is forbidden in `src/` outright — production tears down one session at a time. | CLAUDE.md, §18 incident 2026-09-12, D49 |
| **K6-a** | **Why K6 relaxes `kill-server` rather than banning it, stated so the relaxation is bounded rather than discovered at 3am.** Revision 1 banned it outright, which was **stricter than CLAUDE.md** — CLAUDE.md rule 1 bans it *without* `-L`, and rule 2 gives `tmux -L shepherd-spike …` "teardown included" as the correct pattern. The extra strictness pointed at the incident: `ensure_server` creates a bootstrap session nothing removes, T24's teardown is `kill-session` per session then "assert no server", and a builder whose teardown assertion fails — forbidden the one idiom every shipped probe used (`probe_tui.py:393`, and every `gap-fill/probe_*.py`) — is pushed toward the **bare** form that caused 2026-09-12. A rule that makes the safe idiom unavailable manufactures pressure toward the unsafe one. The socket predicate is what keeps the blast radius at a throwaway socket: `^shepherd-m3-` can never be `shepherd`, and can never be `shepherd-runner`. | CLAUDE.md rules 1–2, §18, this revision |
| K7 | The 55 decisions + D38.1 are law. Pressure against one is a **named Decision pressure** — four parts, recommended, never silently reversed. | §3, §0 |
| K8 | stdlib-first; no build step for the frontend. **`xterm.js` is the one runtime dependency and it arrives here** (D51) — vendored as a plain ES module, never fetched at runtime. | §5 Stack, D51 |
| K9 | Unknown is a first-class value — counted and displayed, never hidden. | Principle 5 |
| K10 | The host has no pip/ensurepip in the system Python, no node/npm/tsc, **no browser**. `/root/Shepherd/.venv` is the toolchain: `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/mypy`. There is no `python` on `PATH`. | data-schemas §Runtime toolchain; user brief |
| K11 | **The 23 AST boundary tests are properties, not spellings. An exemption is not an acceptable way to make one pass** (ADR-1: "an exemption is how boundaries die"). A rule that fires on this plan's prescribed code is a **plan defect**, fixed by re-shaping the code or by a named plan change. | M1 ADR-1, T2 r6 |
| K12 | `Signal.fields` reads fail closed on computed keys inside `signals/`. | M1 BLOCKER T11 |
| K13 | **No engine event name and no engine field name may appear in `signals/`.** M3 adds `orchestration/` and `runner/`, which are L3/L2 and **not** `signals/` — but the same discipline applies by design: engine words live in `engines/claude_code/`, tmux words live in `runner/`. | D35 §5.0 |
| K14 | Nothing the UI renders may read a log (D25). | D25 |
| K15 | No rule may reference `Stop.stop_reason`. | D46 |
| **K16** | **K6 is enforced at runtime on the real argv, at the one process-exec site, and by AST rules only as a cheap second net.** `check_tmux_argv(argv, permitted)` runs inside the callable `make_run_argv(permitted)` returns — the single place a tmux process is started — and **refuses, never repairs**: it raises unless `argv[0:2] == ["tmux", "-L"]`, unless `argv[2]` is a permitted socket, unless every element following a `-t` matches `^=[A-Za-z0-9_-]+:$`, and unless a `kill-server` argv's socket matches `^shepherd-m3-`. The socket `shepherd` is never permitted, whatever configuration says. **Rationale (revision 2): the three AST rules revision 1 relied on were spellings, not properties**, and each fell to one line — `["tm" + "ux", …]`, `f"kill-{verb}"`, or `from .tmux_cmd import TMUX_BIN` (which yields an argv with **no `-L`**: the exact blast radius). `tests/boundaries/_taint.py:5-9` exists because two earlier rules were defeated this way and says it in words: *"a rule about a value has to follow the value."* The argv is the value. `src/` additionally keeps its one-builder rule (the literal `"tmux"` in exactly one module) as the second net, with one **indirection fixture per rule** — the shape `test_platform_branching.py` already ships as `cli_platform_alias_import.py`, `cli_platform_module_alias.py`, `cli_platform_from_import.py`. | K6, this plan (ADR-M3-2, ADR-M3-8) |
| **K17** | **The dominant defect class in this repo is a check that reports success without checking.** Every task's `Required Checks` states **what would make the check go red**, and every negative or tree-wide claim is proved by planting a real violation in `src/` and watching it fail. | M1 r6, M2 acceptance clauses 2 and 6, two mutation reviews 2026-09-17 |

**In scope (§16's M3 row, decomposed):**

1. **tmux runner** — the `Runner` seam (D36, §6), `LocalRunner` over a dedicated socket, `ScriptedRunner`, and the one contract suite both pass (§14.2).
2. **spawn** — `spawn_argv` with argv words and `--` (C4), `--session-id` so the row is bound before the process starts, `--name`, the **trust-dialog** path (C15) and the recursion caps (§11).
3. **xterm.js terminal** — snapshot + live byte stream + byte-exact keystrokes, over a hand-rolled RFC 6455 WebSocket (D51).
4. **write policy** — one pure table, including D44's refusal and D45's two triggers.
5. **mailbox** — one delivery path, coalesced, idempotent, triggered on `Stop` *or* a prompt-ready pane (D45).
6. **`ask()` via fork** — `can_fork = True` is **answered** (data-schemas §Fork l.2920); the `can_fork=False` mailbox fallback is still built, as the fallback.
7. **rename + the `can_set_title` probe (D29)** — the local ratchet, the `local only` marker, the drive-the-engine path, and **DP1**, which re-decides D29's mechanism out loud.
8. **Owned-session lifecycle** — exit codes from `pane_dead_status` (which **closes M2's G-M2-2** for owned sessions), `/resume` rebinding (C14), interrupt (`Escape`, never SIGINT — D43), terminate.
9. **The two inherited ledger entries M3 is the named owner of** — **T18-2** (`PostToolBatch`, re-pointed to "a milestone that can install hooks: M3 spawns sessions") and **T19-1** (ownership vs `entrypoint`, "to be decided at M3, where `ownership` stops being a single value").

**Out of scope (named so they cannot leak in):**

- **`PtyRunner`** (§9's fallback). M3 ships one real `Runner` adapter. If tmux is absent, `EngineCapabilities.can_spawn` is **False**, `spawn_session` refuses with a readable reason, and the fleet page says so — an honest absence, not a degraded path nobody tested. The raw pty stream also has **no trust-dialog detector** (data-schemas §Fallback `PtyRunner`: "screen-state detection needs a terminal emulator"), so the fallback would be strictly less safe than refusing. Reopened when a host without tmux exists.
- **`sessions/<id>/pty.log` as a ring file** (§7's layout line). Nothing in M3 reads it, an unbounded byte log of every owned session is a disk risk, and a `pipe-pane` stream **cannot be replayed from an arbitrary offset** — the bytes are cursor-addressed diffs (`Print^[[9Gthe^[[13Gintegers`), not lines. `pipe-pane` runs **only while a terminal client is attached** and its sink is deleted on detach. Gap **N7**.
- **`authorize()`, the audit log, MCP exporters, `master/`, the wake set** — M4 (D38). M3's tools carry a `blast_class` and `audiences` and are gated by nothing, exactly as M1's and M2's are.
- **Channels** (`channel_message`, `post_to_channel`) — M6. The mailbox is the transport; the channel is the addressing layer and has no delivery code of its own (D12), so building the transport alone is complete.
- **Worktrees, queue workers, `work_item`** — M5. M3 spawns into a registered project directory only.
- **The LLM verdict lane** — D34, deferred past M2 and not reopened.
- **`shepherd install`, systemd units, `enable-linger`** — M6. M3's runner must nevertheless start the tmux server so it survives the daemon; **DP5** says how, and the unit file that makes it permanent is M6's.
- **A macOS run.** `MacHost` gains M3's seventh member written-and-unverified, like every other member (D55, G1).

**Open decisions:** none. **Nine** Decision pressures — DP1–DP4 and DP6–DP10 — of which **DP1 is
recommended and explicitly NOT APPLIED**. **DP5 is no longer a pressure**: D55 was amended on
2026-09-17 to own seven things and names detached launch itself, so the DP5 entry is kept as a
**record** of that amendment and of the fact that T7 implements the member the decision now names
(see DP5, and N4 "absorbed into D55"). **Nine** Recommended Defaults (RD1–RD9), each low-blast-radius
and explicitly unapproved.

---

## Decision pressures — named, four-part, recommended out loud

Per §0 and K7. Each says what the decision is, what pushes against it, the options, and the
recommendation.

**There are nine entries — DP1–DP4 and DP6–DP10 — plus DP5, which is no longer a pressure at all.**
**One of the nine is recommended and NOT applied — DP1 — and it is first because the user's standing
instruction is to recommend without applying when implementation pressure pushes against a
decision.** The other eight are applied: **seven** are *readings* of a decision that dictates the
reading (DP2, DP4, DP6, DP7, DP8, DP9, DP10) and **one** is a flagged widening of a data shape §7
never wrote (DP3, the seventh table).

**DP5 is kept in place as a record, not as a pressure** (revision 2): `orchestrator-platform.md:166`
was amended on 2026-09-17 to say the `HostPlatform` seam owns **seven** things, it names detached
launch, it cites the two captures, and it credits this plan's DP5 by name. There is nothing left to
recommend, and T7 simply implements the member the decision now declares.

### DP1 — D29's stated mechanism is wrong, and `can_set_title` can be `True` for an owned session

- **Decision.** D29: "pushing a user rename back into the harness is an **engine capability**
  (`can_set_title`), not an assumption. Until verified it is local-only, and the UI says `local only`."
  §7.1 (`orchestrator-platform.md:724–731`) gives the candidate mechanism as *"appending an `ai-title`
  entry to the session transcript"* and sets `can_set_title = False` *"until the probe in §18 says
  otherwise"*.
- **Pressure.** The probe says otherwise **and says the mechanism is wrong.**
  `ai-title` (`aiTitle`) is the **engine-generated** channel. A user-supplied title is
  **`custom-title`** (`customTitle`) plus **`agent-name`** (`agentName`), and **Claude Code writes
  those itself** when `/rename <title>` is typed over the pty or when the process is spawned with
  `--name` — after which the registry sidecar reports `nameSource:"user"` and `#{pane_title}` reads
  `✳ <title>` (data-schemas §Session title, l.2586–2631; captures
  `tmux-tui/run-20260914T154946Z/10-rename-transcript-new-lines.jsonl`, `10-rename-after-fmt.txt`,
  `10-sidecar-after-rename.json`). **Shepherd therefore never writes the file**, which is the whole
  objection §7.1 raised against the `ai-title` mechanism (principle 4). Appending `ai-title` would at
  best record a *user* title in the *engine's* channel, and precedence between the two entry types
  **was not determined** (data-schemas Spec corrections, row 724–731), so an existing `custom-title`
  may hide it entirely. Meanwhile `title_synced_at` — which D29 says records the write-back — has
  **three** capture-proven readers: the transcript's `custom-title` entry, the sidecar's
  `name`/`nameSource`, and `#{pane_title}`.
  Two facts bound the pressure. **First, it holds only for owned sessions**: driving `/rename` needs a
  pty Shepherd owns, and the attached case — `claude --resume <id> -p '/rename …'` against a session
  **live in another process** — is in `data-schemas.md` §Not verified twice over, once because it was
  not attempted and once because it *"risks two writers on one transcript"*. **Second, `can_set_title`
  is declared on `EngineCapabilities`, which is per *engine*, and the honest answer is per *session*.**
- **Options.**
  1. **Leave `can_set_title = False` for every engine.** D29 literally. Every owned rename shows
     `local only` although the engine would accept it, and §16's "rename + the `can_set_title` probe"
     ends with the probe answered and the answer unused.
  2. **Flip `can_set_title` to `True` for Claude Code and drive the engine** — `send-keys -l -- "/rename <title>"` then `Enter`, at an idle prompt only, then confirm from the
     sidecar's `nameSource:"user"` before stamping `title_synced_at`. Correct for owned sessions;
     **wrong for attached ones**, where the same flag would promise a sync that is unverified and
     that risks a second writer on the transcript.
  3. **Make the capability per-session** — keep `EngineCapabilities.can_set_title` as the engine's
     *ceiling* and let the call site answer `ceiling and ownership is OWNED and runner is present`.
     The UI's `local only` marker then keys on the per-session answer, which is what §12 actually
     renders. Costs one flagged widening of §6's capability record's *meaning* (not its shape).
  4. **Append an `ai-title` entry ourselves.** The spec's candidate. Rejected on evidence: wrong
     channel, undetermined precedence, and it writes into a file the engine owns (K3, principle 4).
- **Recommendation — option 3, `ceiling = True` for Claude Code. STATED AND NOT APPLIED.**
  **No builder applies this.** M3 ships `can_set_title = False` (D29's literal value), the UI shows
  `local only` for every rename, and the drive-the-engine function **is built, is exercised in the
  live lane, and is unreachable in production** — the same shape M2 used for `crashed`/`killed`/
  `derailed` (G-M2-2/4/6).
  **What the reversal costs, under option 3 and not option 2** (revision 2 — revision 1 described
  option 2's mechanism while recommending option 3, and the two did not agree). Option 2 flips one
  engine-wide flag and is wrong for attached sessions. Option 3 keeps
  `EngineCapabilities.can_set_title` as the engine's *ceiling* and makes the **call site** answer
  `ceiling and ownership is OWNED and runner is present`. **That per-session predicate is built and
  ships in M3** (T20's `rename_session` evaluates it), gated to `False` today only because the
  ceiling is `False`. So the reversal really is one constant —
  `CLAUDE_CODE_CAPABILITIES.can_set_title = True` in `engines/claude_code/spawn.py` — **and it is
  one constant precisely because the predicate that makes it safe for attached sessions is already
  there.** Under option 2 the same one-line flip would silently promise a sync for attached sessions
  that is unverified (G-M3-5) and risks two writers on one transcript; under option 3 it cannot,
  because the call site refuses a non-owned session on its own. That difference is the whole reason
  option 3 is the recommendation.
  **The live-lane test *is* §18's probe**, and its recorded evidence is what a reviewer reads
  before approving the flip. `tests/…::test_can_set_title_ships_false` asserts the flag, names this
  DP, and fails the build if someone flips it without a recorded approval.
  `test_the_per_session_predicate_refuses_an_attached_session_even_with_the_ceiling_true` asserts
  the option-3 half is real rather than aspirational — **goes red** if the predicate is a comment.

### DP2 — T19-1: `ownership` stops being a single value here, and the hook lane cannot see `entrypoint`

- **Decision.** **D47** — registration accepts the first event of *any* kind from an unknown
  `session_id`. **E35/RD9/C8** — `entrypoint` is the discriminator for what is a fleet session
  (`cli` = attached interactive, `sdk-cli` = a `-p` run), never `kind`.
- **Pressure.** M2's T19 proved live that a hooked `claude -p` run registers as
  `origin=external, ownership=attached` and appears on the fleet tree. The hook lane cannot apply the
  discriminator, because **`entrypoint` is absent from all 429 captured hook payloads** — it exists
  only on transcript entries (`data-schemas.md` l.1445) and in the registry sidecar (l.1989). The two
  decisions are orthogonal and neither is being reversed; the hook lane simply has no way to
  implement E35. **M3 makes it urgent for a reason M2 did not have: `ask()` spawns a `claude -p` fork
  per call**, so every `ask()` would put a finished attached row on the fleet page.
- **Options.**
  1. Read `entrypoint` from the transcript at registration. Costs a file open on the hot ingest lane
     (3.4 ms budget), which D24 deliberately keeps evidence off.
  2. **Let discovery reconcile.** The registry already carries `entrypoint`, and
     `signals/discovery_loop.py::discovery_pass` already parses it and already `continue`s on
     `sdk-cli`. Change the `continue` into a *reconcile*: when an `sdk-cli` entry matches a row the
     hook lane created, mark that row `ephemeral = TRUE` so it is hidden from the fleet by default —
     the mechanism §7 already defines for `ask()` forks. D47 stays intact; the cost is up to one
     2.0 s sweep of visibility, and a `-p` run shorter than one sweep is never reconciled at all
     (the sidecar is deleted at exit).
  3. Accept the noise.
  4. Suppress registration for non-interactive entrypoints — reopens D47's failure mode. Rejected.
- **Recommendation (APPLIED, in two halves, flagged as gap N1).**
  **Half one, which makes the general case rare instead of common: Shepherd pre-registers its own
  sessions.** Every session M3 starts — owned spawns *and* `ask()` forks — is created in the store
  **before the process starts**, with an `engine_session_id` Shepherd chose and passed as
  `--session-id <uuid>` (capture-proven: `SessionStart` echoes the requested uuid,
  `tmux-tui/supp-20260914T155346Z/02-sessionstart-and-sidecar.txt`). `register_session` is idempotent
  on `ux_session_engine_id`, and the hook lane's own `get_session_by_engine_id` then finds our row
  and creates nothing. An `ask()` fork is therefore `origin=ask_fork, ephemeral=TRUE` **from birth**,
  never for one sweep. This is not a decision change at all — it is using a flag that already exists.
  **Half two: option 2** for everyone else's `-p` runs, because M3 has to teach discovery about
  ownership anyway. Its limits are stated in the product: `doctor` reports
  `sdk_cli_reconciled` and `sdk_cli_missed` (a row the sweep never saw because the process had
  already exited), so the reconcile never claims to be complete.

### DP3 — the mailbox needs a table, and §7 has six tables and no room for it

- **Decision.** §7: "**Six tables**" — `workspace`, `repo`, `session`, `work_item`, `queue`,
  `app_state`. §7's *not stored* list names four things and their homes. D12 makes the mailbox the
  one delivery path, with coalescing and an `idempotency_key`.
- **Pressure.** A mailbox message must survive a `controld` restart (D37: "restart, upgrade and crash
  freely"), must be idempotent for a retrying caller, must be coalesced at delivery, and must be
  queryable per session. §7 gives it nowhere to live. `app_state` is a key/value row for singletons
  and has no index, no ordering and no partial write; memory loses the queue on every restart, which
  makes D12's "one place to get it right" untrue at the first upgrade.
- **Options.** (a) A seventh table `mailbox_message` in migration 003. (b) A JSON blob in
  `app_state`. (c) In-memory only. (d) A JSON column on `session` — one row's queue rewritten whole
  on every enqueue, and a lost update the first time two callers send at once.
- **Recommendation (APPLIED, flagged as gap N2).** (a). §7's "six tables" is an enumeration written
  before the mailbox was built, and every property D12 asks for is a property a table has and the
  alternatives do not. The table is small and bounded: rows are deleted on delivery, and a
  `delivered_at`-stamped row is kept for the retention window so `idempotency_key` can refuse a
  duplicate. `store/mailbox.py` holds its SQL, per D26/D33.

### DP4 — §9 puts the browser WebSocket on `sessiond`, which has no HTTP server and no store

- **Decision.** §5's process table: `sessiond` hosts "the pty supervisor (`runner/`) and the
  hook-ingest endpoint". §9's diagram: `browser ──WS──► sessiond`. **D51**: a hand-rolled stdlib
  RFC 6455 WebSocket. **§13**: `127.0.0.1` only, origin-checked, no knob.
- **Pressure.** Three shipped facts. `sessiond` **has no HTTP server** and
  `tests/daemons/test_sessiond_isolation.py` proves its whole import closure cannot reach a database
  driver — it is deliberately the process that must not restart, and adding a listener to it makes it
  the process that is restarted whenever the terminal changes. There is **no channel from `controld`
  to `sessiond`**: the two sockets run hooks → `sessiond` → `controld`, one way, and inventing a
  reverse control protocol is an unplanned surface larger than the terminal itself. And a second
  loopback listener doubles the surface §13 exists to keep at one.
- **Options.** (a) Terminal WS on `controld`'s existing loopback server, same port, same origin
  check. (b) A second listener in `sessiond` plus a new controld→sessiond protocol. (c) Proxy the WS
  through `controld` to `sessiond` over the UDS — b's protocol plus a proxy.
- **Recommendation (APPLIED as a reading, flagged as gap N3).** (a), and it is only available because
  of **ADR-M3-1**: the tmux **server** is the pty supervisor, `runner/` is a stateless argv adapter
  over it, and any process can drive it. §5's sentence assigned `runner/` to `sessiond` on the premise
  that owning a pty means holding a file descriptor; under D14 it does not. What `sessiond` actually
  owns — the hook ingest — is unchanged, and what §9's diagram wanted — a terminal that survives a
  `controld` restart — is delivered by the tmux server, not by the daemon. **The pane survives; the
  browser reconnects.** `web/` still imports nothing below L4 (D35); the WS handler resolves its
  capability through `toolsurface`.

### DP5 — **RECORD, not a pressure: D55 was amended on 2026-09-17 and now names the seventh member itself**

**Revision 2 restates this entry.** Revision 1 argued against a D55 that no longer says what it
quoted. The spec was amended the same morning: `orchestrator-platform.md:166` now reads *"The seam
owns exactly **seven** things"*, its seventh is **"detached launch (wrapping an argv so the process
it starts escapes the caller's supervision cgroup)"**, it cites `q1-cgstop.txt` and `q1-scopestop.txt`
by name, and it credits **"Seven, raised from six on 2026-09-17 (M3 plan DP5)"**. Verified by reading
the line on this host, and both captures were re-read: under the default `KillMode=control-group`
(`q1-cgstop.txt`) the capture reads `tmux-server 4054473: dead`, `pane-claude 4054474: dead`,
`no server running`; started through `systemd-run --user --scope` (`q1-scopestop.txt`) the same stop
leaves `tmux-server 4054726: alive(tmux: server)`, `pane-claude 4054727: alive(claude)` and both
sessions listed.

**So there is no pressure against D55 left, and no recommendation to state.** **T7 implements the
seventh member the decision now names**, and T7's engineering content is unchanged from revision 1 —
the same four files, the same `DetachedLaunch` record, the same contract rows, the same
write-and-annotate regime for `MacHost`. What changed is only the plan's *standing*: this is a
record that the spec moved, not a request to move it. **Gap row N4 is re-labelled "absorbed into
D55"** rather than dropped, so the audit trail from "the plan pushed" to "the decision absorbed it"
survives. **The count is now nine Decision pressures (DP1–DP4, DP6–DP10) plus this record**, and the
Agreement Snapshot says so.

The reasoning is preserved below verbatim, because it is what the amended D55 is *made of* and a
reader of T7 needs it:

- **Decision (as amended 2026-09-17).** **D55**: host-dependent behaviour lives behind
  `HostPlatform`, and the seam owns exactly **seven** things: directories, the control socket and its
  budget, the hook dispatch command, supervision, process liveness, login persistence, **and detached
  launch**.
- **Pressure (now absorbed).** D49 and the gap-fill probe together: a tmux server **first started inside a systemd
  user unit stays in that unit's cgroup**, and the default `KillMode=control-group` kills the server
  **and every owned pane** on `systemctl --user stop` *and* on `restart`
  (`gap-fill/systemd-tmux-20260914T170532Z/q1-cgstop.txt`, `q1-cgrestart.txt`). Survival needs one of
  two measures, **both verified**: start the server in its own scope
  (`systemd-run --user --scope`, `q1-scopestop.txt`) or set `KillMode=process` (`q1-procstop.txt`).
  The first is a launch-time decision the runner must make; the second is a unit-file decision M6
  owns. Which one applies is a **host** question — systemd user manager, launchd, or a container with
  no systemd at all, which is exactly the three-way `SupervisionKind` D55 already declares. And
  `tests/boundaries/test_platform_branching.py` fails the build on any platform branch outside
  `host/`, which is the rule working as intended: `runner/` must not answer this question itself.
- **Options.** (a) A **seventh member**, `detached_launch(argv) -> list[str]`, which wraps a command
  so it escapes the caller's cgroup, returning the argv unchanged where that is right. (b) Defer to
  M6's unit file and accept that every owned session dies when `controld` restarts — which contradicts
  D14's stated reason for choosing tmux and cannot be tested before M6. (c) Branch on
  `Supervision.kind` inside `runner/` — platform branching by proxy; the boundary rule does not
  currently name `systemd-run`, so it would *pass*, which makes it worse rather than better (K11).
- **Disposition — (a), and D55 now says so itself (N4 "absorbed into D55").** D55's own reasoning for
  admitting it as a **member** rather than a widening of `supervision()` is recorded in the spec:
  *"the count clause is an anti-growth clause, and absorbing a new concern into an existing member
  would keep its letter, defeat its purpose, and hide the change from every diff."* `LinuxHost` returns the
  `systemd-run --user --scope --` prefix when `supervision().kind == "systemd_user"` and the bare argv
  otherwise; `MacHost` ships it written, annotated `# UNVERIFIED (no capture) — D55`, returning the
  bare argv and reporting `verified() is False`; `ScriptedHost` answers from a fixture; and
  `tests/contracts/test_hostplatform_contract.py` gains rows for all three.

### DP6 — §6 declares an `EngineAdapter` Protocol; M1 and M2 shipped a module boundary

- **Decision.** **D9**: "`EngineAdapter` interface with one implementation (Claude Code), plus a
  written capability matrix for Codex and Antigravity." **D36**: runtime swaps get a `Protocol` + a
  `Scripted*` + a contract suite; edit-time swaps get a module boundary, and `EngineAdapter` is
  listed in the runtime row.
- **Pressure.** M3 is the first milestone that needs three of §6's `EngineAdapter` members
  (`capabilities`, `spawn_argv`, `set_title`) — the other four (`locate_transcript`,
  `parse_transcript_delta`, `install_hooks`, `uninstall_hooks`) **already ship as module-level
  functions in `engines/claude_code/`**, with no Protocol, and no Decision pressure was ever written
  about it. Writing the Protocol now means writing an interface against exactly one implementation,
  which is the mistake D9 itself describes; not writing it means M3 silently continues a deviation
  two milestones old.
- **Options.** (a) Add the three functions in `engines/claude_code/` in the shapes §6 names, and keep
  the module boundary, with a **named promotion trigger**. (b) Write the `EngineAdapter` Protocol now
  and make `engines/claude_code/` satisfy it, plus a `ScriptedEngine` and a contract suite (§14.2) —
  three new files for a seam with one adapter. (c) Write the Protocol and skip the `Scripted*` —
  forbidden by §14.2.
- **Recommendation (APPLIED as a continuation, flagged as gap N5).** (a). The **named promotion
  trigger**, in D33's shape: the day a second engine ships, **or** the day the
  `EngineCapabilities.has_hooks = False` degrade path (§6's last paragraph) is built — whichever comes
  first. Until then the deviation is recorded here rather than inherited silently, and `Runner`
  **does** get its Protocol, its `ScriptedRunner` and its contract suite, because D36 lists it in the
  same row and M3 is the milestone that builds it.

### DP7 — D13 says "discard the fork"; K3 says nothing is written under `~/.claude/`

- **Decision.** **D13**: `ask()` forks the target's session, asks the fork, **discards** it. **K3**
  (M1, from the probe rules): nothing Shepherd runs writes under `~/.claude/`.
- **Pressure.** A TUI fork **persists its transcript** (`tmux-tui/run-…/12-fork-summary.json`), and
  `--no-session-persistence` *"only works with `--print`"* per `claude --help`
  (`claude-help-excerpt.txt`). So under §9's stated implementation — a fork in a second tmux session —
  "discard" means **deleting a file the engine owns**, which is a write under `~/.claude/` and runs at
  principle 4. `data-schemas.md` records this as a gap, not a contradiction: "the spec does not say
  how discard is done".
- **Options.** (a) Fork **headless**: `claude --resume <id> --fork-session -p "<question>"
  --no-session-persistence --output-format json`. The probe confirms a headless fork produces the same
  `SessionStart{source:fork}` shape (`headless-20260914T160308Z/event-sequence.txt`), the target is
  provably untouched (original sha256 unchanged, no hooks for the original), and `--print` is exactly
  the mode `--no-session-persistence` supports. (b) Fork into a tmux pane as §9 says, then delete the
  transcript — K3 violation. (c) Fork into a tmux pane and leave the file — residue per `ask()`, and
  the fork inherits the user title, so `/resume` lists two sessions under one name
  (`13-dead-pane.txt`).
- **Recommendation (APPLIED, flagged as gap N6).** (a), **with the combination probed first**
  (**P2**): `--fork-session` **combined with `--session-id`** is in `data-schemas.md` §Not verified —
  "not attempted" — and so is `--no-session-persistence` in that combination.
  **The fallback, corrected in revision 2.** Revision 1's fallback was "learn the fork's id from the
  sidecar keyed on the child pid". That **races a file the engine deletes**:
  `engines/claude_code/registry.py:3-5` documents Claude Code writing one sidecar per running session
  and **deleting it on exit**, and this plan relies on that deletion at DP2 ("a `-p` run shorter than
  one sweep is never reconciled at all — the sidecar is deleted at exit"). T15 never polls during the
  run, so by the time `ask_session` has a result the sidecar is gone. The fallback would have been a
  read of a file that is reliably absent.
  **The real fallback is the `-p` run's own result JSON, which carries the fork's id.** Capture-proven
  on this exact argv: `tmux-tui/headless-20260914T160308Z/h5_fork.cmd.txt` is
  `claude --model … --output-format json --resume 55b21a24-… --fork-session -p …`, and
  `h5_fork.stdout.json` carries `"session_id": "f0c208a0-76e1-4c07-bf1f-0c799409542d"` — **different
  from the resumed id**, so it is the fork's own, alongside `"type":"result"`,
  `"subtype":"success"`, `"is_error": false`, `"result":"FORKED"` and `"uuid"`. `ask()` already parses
  this object for its answer; the id is the same read.
  **What that costs, stated rather than hidden.** The id is known only **after** the run, so if P2
  shows `--session-id` is refused, the `ask_fork` row is created **without** an
  `engine_session_id` and **bound afterwards**. `store/db.py::register_session` requires a non-null
  `engine_session_id`; **`create_owned_session` (T4) therefore types it
  `engine_session_id: str | None`**, and T4's signature says so. Pre-registration's guarantee is
  weaker on this branch — the row exists first and is `ephemeral` from birth (which is what keeps the
  fork off the fleet), but it is not engine-bound until the fork returns. **The K1-compliant step:**
  P2 appends the result-JSON field table to `data-schemas.md` §Fork, so the shape M3 asserts is in
  the document and not only in a capture folder.
  If P2 shows a transcript is left anyway, **the residue is named and never deleted** — D13's
  "discard" is satisfied by discarding the *session*, and the file is Claude Code's, not ours (K3).

### DP8 — D44's refusal needs a dialog detector, and no hook marks a dialog resolved

- **Decision.** **D44**: a `needs_you` caused by an open permission dialog **refuses** programmatic
  writes and is answered only by an explicit `approve`/`deny` action.
- **Pressure.** Nothing in the hook stream says a dialog is open *now*. `PermissionRequest` has **no
  `tool_use_id`** and nothing marks its resolution; `Notification{permission_prompt}` arrives **6.0 s
  later and only if still unanswered** (0 of 4 fast answers produced one); a TUI Esc rejection emits
  nothing. The **only observed clearing signal anywhere** is the registry sidecar's
  `status: waiting` + `waitingFor: "permission prompt"` → `busy` transition, captured 9.194 s apart
  for one pid (data-schemas §Session sidecar, added 2026-09-16). Getting this wrong is not cosmetic:
  the probe shows text sent into an open dialog is **discarded**, and the `Enter` that follows selects
  the default `1. Yes` — *"the tool ran and the file was created"*.
- **Options.** (a) Key the refusal on `session.needs_you_reason` alone — it is folded from hooks and
  is 6 s late and never cleared. (b) Key it on the **sidecar** (`status`/`waitingFor`). (c) Key it on
  the **pane text** (`capture-pane -e -p`: `Do you want to proceed?`, `❯ 1. Yes`,
  `Esc to cancel · Tab to amend`). (d) **Refuse if *either* (b) or (c) says a dialog is open, and
  require *both* to be clear before a write.**
- **Recommendation (APPLIED as a reading of D44, flagged as gap N8).** (d). The two sources fail in
  opposite directions — the sidecar is authoritative but polls a file that is absent during the trust
  dialog, and the pane is immediate but is a text match against a screen — so requiring both to be
  clear makes the failure mode *refusing a write that would have been fine*, which is recoverable, and
  never *approving a tool the human never saw*, which is not. **Answering** the dialog is
  `answer_permission(session_id, choice)`, a registered `local_destructive` tool, and its key
  delivery is blocked on **probe P4**: `1`/`2`/`3` at a permission dialog is in §Not verified, and
  `Enter`-on-the-default is the one mechanism that *is* captured — so until P4 lands, `approve` is
  `Enter` (default `1. Yes`, capture-proven) and `deny` **refuses with a reason** rather than
  guessing a keystroke.

### DP9 — §12's `[tmux attach]` promises an *exact* hand-off; `resize-window` makes the window `manual`

- **Decision.** **D14**: tmux makes "jump to terminal" **exact** instead of AppleScript keystroke
  injection. §12: `[tmux attach]` in the header "hands the session to your own terminal".
- **Pressure.** `Runner.resize` is `resize-window`, and `resize-window` **silently switches the window
  to `window-size=manual`** (`gap-fill/tmux-attach-keys-…/attach.txt`). A human attaching from a
  smaller terminal then sees a clipped, panning viewport; from a larger one, dead space. With
  `window-size latest` instead, the attached client's size **overrides the browser's** and the two
  fight. `attach -f ignore-size` did not stop the window following the only client. `attach -r`
  delivers **no keys at all** (verified: `hex: 0`). And "a second tmux client typing at the same time
  as browser writes" is in §Not verified.
- **Options.** (a) `manual` + browser-driven size; the header offers `attach -r` (view-only, exact
  and safe) and the full-control command with the size caveat named. (b) `latest`; the human wins and
  the browser's terminal reflows under it. (c) No `[tmux attach]` at M3.
- **Recommendation (APPLIED as a clarification, flagged as gap N9).** (a). §12's "exact" is achievable
  for *bytes* and not for *size*, and `data-schemas.md` says so in those words ("the 'exact' claim
  needs a chosen policy"). The header renders **two** commands, both copyable, with one sentence of
  truth beside them. **P3** probes the concurrent-typing case, because a human at a keyboard and a
  browser writing at once is not an edge case in this product.

### DP10 — D45 says the input line is cleared before every delivery, and no capture shows how to clear it

- **Decision.** **D45**: "Mailbox delivery triggers on `Stop` *or* on a prompt-ready pane, **and the
  input line is cleared before every delivery**." The reason is captured: after `Esc` during
  streaming, the previous prompt is **put back in the input box**, and the next programmatic write is
  **concatenated onto it** — the observed prompt was
  `INT-ESC-STREAMReply with only the word AFTER`.
- **Pressure — and it is smaller than revision 1 said, because the repo already captured `C-u`.**
  Revision 1 wrote "the one clearing keystroke anyone tried is `Esc`" and planned a probe for `C-u`.
  **That is false, and the capture beside the one it read says so.** `data-schemas.md` §Key semantics
  omits the `C-u` row; the capture folder does not. In
  `gap-fill/keys-claude-20260914T180105Z/steps.log`, lines 6–7 are `send-keys -H 1b 5b 41` (raw `Up`,
  which `results.json` records as `raw_up_recalls_history: true`) at 18:01:14 and `send-keys C-u` at
  18:01:15 — **history recalled into a non-empty box, then `C-u`, on this exact surface, at
  `claude 2.1.270` under `tmux 3.4`, the same tmux this host runs.** The before/after captures are
  unambiguous: `01-after-raw-up.txt` renders the input line `❯` + NBSP + `FIRST-PROMPT-FOR-HISTORY`;
  `01b-after-ctrl-u.txt` renders `❯` + NBSP + **nothing**, with the hint `Ctrl+Y to paste deleted
  text` where the `tmux detected · scroll with PgUp/PgDn` banner had been. **`C-u` clears the input
  line.** It is sent as a tmux **key name** (`send-keys -t <target> C-u`), not as `-l` literal text.
  What remains genuinely untried: `C-a C-k`, `C-w`, and **the post-`Esc` restored prompt** — step 04
  of the same probe typed text and sent `Esc` twice, and never sent `C-u` afterwards, so whether the
  restored prompt is the same widget as a history recall is not captured either way.
- **Options.** (a) Send `C-u` and hope. (b) **Refuse to deliver onto a non-empty input line** —
  detectable today, because `capture-pane -e -p` renders the input box as `❯` + NBSP + text between
  two `────` rules, and ghost text is distinguishable by SGR 2 (dim) — and retry at the next trigger.
  (c) Deliver anyway and accept concatenation. (d) Probe the remaining cases first.
- **Recommendation (APPLIED — the clearing form ships, backed by the capture; the refusal stays as
  the fallback, not as the policy).** `C-u` is **captured**, so K1 is satisfied and there is nothing
  left to defer for the history-recall case. The write table gains a row: at `PROMPT_READY` with a
  non-empty input line, delivery sends `C-u`, **re-reads the pane**, and proceeds **only if the box
  is now empty**. If it is not, that is `REFUSE_INPUT_NOT_EMPTY`, counted as
  `AnomalyKind.MAILBOX_INPUT_NOT_EMPTY`, retried at the next trigger. **The re-read is the whole
  safety property**: it means the clearing form can never be worse than the refusing form, because a
  clear that did not work is indistinguishable from never having tried. A message that arrives late
  is a delay; a message concatenated onto a stale prompt is a corrupted instruction, and the re-read
  is what makes the second impossible without a second probe.
  **P1 is narrowed** to what is untried: `C-a C-k`, `C-w`, and `C-u` **after** an `Esc`-restored
  prompt. If P1 shows the post-`Esc` box is a different widget that `C-u` does not clear, the
  re-read catches it and that pane state falls back to refusal — no code changes, one row's evidence
  string changes. **A claim that the post-`Esc` box is a different widget must cite the capture that
  shows it; revision 1 made that claim with no capture at all.**

**If a builder finds pressure this list does not cover, the instruction is unchanged: write the
four-part entry in `docs/plans/2026-09-17-m3-BLOCKERS.md` and do not apply the recommendation.**

---

## Vocabulary (used exactly, throughout)

| Term | Meaning here |
|---|---|
| **owned** | Shepherd started the process and holds its pane: `ownership = owned`, a `runner_handle`, a `pane_dead_status` exit code, steering, rename. |
| **attached** | Someone else started it; Shepherd observes it (M1/M2). No pane, no exit code (C13), no rename (DP1). |
| **runner handle** | `(runner, socket, session_name)` — everything needed to address a pane. Stored on `session.runner_handle` as one string, parsed in `runner/` and nowhere else. |
| **pane state** | The *meaning* of the current screen: `TRUST_DIALOG`, `PERMISSION_DIALOG`, `PROMPT_READY`, `BUSY`, `DEAD`, `UNREADABLE`. Derived from `capture-pane -e -p` plus four tmux format fields. |
| **write decision** | The write policy's **output**: `SEND_NOW`, `QUEUE`, `REFUSE_DIALOG`, `REFUSE_NO_PTY`, `REFUSE_INPUT_NOT_EMPTY`. Five values. |
| **write-policy key** | The write policy's **input**, a 4-tuple: `(SessionState, PaneKind, Ownership, input_empty: bool)` — 4 × 6 × 2 × 2 = **96** keys. `input_empty` is a key field, not a note: `REFUSE_INPUT_NOT_EMPTY` is reachable *only* through it. Totality is a property of the **key** space; the value space (`WriteDecision`) cannot break it. |
| **prompt-ready** | `alternate_on = 1`, pane alive, pane kind `PROMPT_READY`, input box empty (ghost text is not input). D45's second delivery trigger. |
| **ghost text** | Claude Code's prompt suggestion, drawn in the input box in SGR 2 (dim). A plain `capture-pane -p` reader mistakes it for a draft; `-e` does not. |
| **coalesce** | Five queued messages become **one** delivery with five bullets, not five turns (D12). |
| **ask fork** | A headless `claude --resume <id> --fork-session -p` run. `origin = ask_fork`, `ephemeral = TRUE`, hidden from the fleet. |
| **the throwaway socket** | `shepherd-m3-probe` for probes, `shepherd-m3-live` for the live lane. Never `shepherd`. Never `shepherd-runner` in a test. |

---

## Functionality flows (every step and every error path maps to a test)

```
Flow A — spawn an owned session
A1 spawn_session validates the project, the caps and the cwd allowlist
      → test: tests/orchestration/test_spawn.py::test_spawn_refuses_an_unregistered_directory
A2 a row is created FIRST: our ulid, our chosen engine_session_id, ownership=owned
      → test: ::test_the_row_exists_before_the_process_does
A3 the tmux server is started detached, on the configured socket, via HostPlatform
      → test: tests/runner/test_local.py::test_the_server_is_started_through_detached_launch
A4 new-session runs claude with argv WORDS, `--` before the brief, --session-id, --name
      → test: tests/engines/test_spawn_argv.py::test_the_brief_is_one_argv_word_after_a_separator
A5 the pane is polled until PROMPT_READY, TRUST_DIALOG or DEAD
      → test: tests/orchestration/test_spawn.py::test_spawn_resolves_to_one_of_three_pane_states
A6 SessionStart{startup} arrives on the hook lane and finds the existing row
      → test: tests/e2e/test_live_owned_session.py::test_a_spawn_registers_exactly_one_row
Error paths:
- untrusted directory        → state=needs_you, reason names the trust dialog; NO blind Enter
      → test: ::test_an_untrusted_directory_becomes_needs_you_and_no_key_is_sent
- brief over the tmux limit  → refused before spawn, with the measured limit in the message
      → test: tests/engines/test_spawn_argv.py::test_an_oversized_brief_is_refused_not_truncated
- brief starting with `-`    → accepted, because `--` precedes it
      → test: ::test_a_brief_starting_with_a_dash_survives
- tmux absent                → can_spawn=False, refusal, and the page says so
      → test: tests/orchestration/test_spawn.py::test_no_tmux_is_a_refusal_not_a_traceback
- recursion cap hit          → a tool error the caller can read
      → test: ::test_depth_children_and_total_caps_each_refuse_with_their_own_message

Flow B — a programmatic write reaches (or does not reach) a session
B1 the policy reads the 4-tuple key (state, pane kind, ownership, input_empty) and returns one decision
      → test: tests/orchestration/test_write_policy.py::test_the_key_set_equals_the_product
B2 stopped or needs_you-by-question → SEND_NOW: send-keys -l -- text, then Enter
      → test: tests/runner/test_local.py::test_text_is_delivered_as_one_literal_argv_word
B3 running → QUEUE: one mailbox row, idempotent on its key
      → test: tests/orchestration/test_mailbox.py::test_a_repeated_idempotency_key_enqueues_once
B4 delivery fires on Stop or on a prompt-ready pane, coalesced into one message
      → test: ::test_five_queued_messages_deliver_as_one_message_with_five_bullets
B5 the delivered rows are stamped, never re-sent
      → test: ::test_delivery_is_not_repeated_after_a_restart
Error paths:
- permission dialog open     → REFUSE_DIALOG; no bytes are sent at all
      → test: tests/orchestration/test_write_policy.py::test_a_dialog_refuses_and_sends_no_bytes
- input line not empty       → CLEAR_THEN_SEND: `C-u`, re-read the pane, then send (DP10, A22)
      → test: tests/orchestration/test_mailbox.py::test_clear_then_send_re_reads_the_pane_before_the_text
- the clear did not work     → REFUSE_INPUT_NOT_EMPTY, counted, retried next trigger
      → test: ::test_a_failed_clear_defers_and_counts_the_named_member
- ghost text in the box      → NOT treated as input; delivery proceeds
      → test: tests/runner/test_pane.py::test_ghost_text_is_not_a_draft
- attached session           → REFUSE_NO_PTY with the §9 banner's wording
      → test: tests/orchestration/test_write_policy.py::test_an_attached_session_has_no_write_path

Flow C — the browser drives a terminal
C1 the WS handshake completes against the origin check
      → test: tests/web/test_ws.py::test_the_handshake_matches_rfc6455_and_checks_origin
C2 on connect, one snapshot frame: capture-pane -e -p -S -2000, bytes unaltered
      → test: ::test_the_first_frame_is_the_snapshot_byte_for_byte
C3 then live bytes from pipe-pane, in order, until the client leaves
      → test: ::test_live_chunks_arrive_in_order_and_stop_on_close
C4 a keystroke arrives as an xterm.js onData string and reaches the pane byte-exact
      → test: tests/runner/test_local.py::test_keys_go_through_send_keys_H_never_the_pane_tty
C5 a resize sets the window and the pane gets SIGWINCH
      → test: ::test_resize_uses_resize_window_and_records_that_it_becomes_manual
Error paths:
- the last client leaves     → pipe-pane is turned off and the sink is removed
      → test: tests/web/test_ws.py::test_the_stream_is_torn_down_with_the_last_client
- the pane is dead           → one frame saying so, then close; never an empty stream
      → test: ::test_a_dead_pane_closes_the_socket_with_a_reason
- the session is attached    → refused with §9's read-only banner, never a blank terminal
      → test: ::test_an_attached_session_is_refused_with_the_banner

Flow D — ask() a running session without touching it
D1 can_fork is True, so the fork path is chosen and reported as method="fork"
      → test: tests/orchestration/test_ask.py::test_the_method_is_reported_never_silently_downgraded
D2 a row is created first: origin=ask_fork, ephemeral=TRUE
      → test: ::test_the_fork_row_is_ephemeral_from_birth
D3 claude --resume <id> --fork-session -p <question> runs with a timeout, argv only
      → test: ::test_the_fork_argv_has_no_shell_and_carries_no_settings_of_ours
D4 the answer is the result JSON's `result` field
      → test: ::test_the_answer_comes_from_the_result_field
Error paths:
- can_fork False             → mailbox-and-wait, method="mailbox"
      → test: ::test_the_fallback_is_the_mailbox_and_it_says_so
- timeout                    → a refusal the caller can read; the fork is killed
      → test: ::test_a_timeout_kills_the_fork_and_returns_a_readable_refusal
- the target is untouched    → asserted on the target's transcript sha256 in the live lane
      → test: tests/e2e/test_live_ask_fork.py::test_the_target_transcript_is_unchanged

Flow E — rename
E1 a rename sets title + title_source=user locally, always, and ratchets
      → test: tests/orchestration/test_rename.py::test_user_beats_engine_and_never_reverts
E2 can_set_title is False, so nothing is typed into the pane and title_synced_at stays null
      → test: ::test_no_keys_are_sent_while_can_set_title_is_false
E3 the UI shows `local only` beside the renamed title
      → test: tests/web/test_session_page.py::test_a_renamed_session_says_local_only
Error paths:
- the drive-the-engine path, exercised only in the live lane, under the flag (DP1)
      → test: tests/e2e/test_live_rename.py::test_typing_rename_makes_the_engine_write_custom_title
```

---

## Risk-based testing matrix

| Risk | Prob | Impact | Test required |
|---|---|---|---|
| **A tmux invocation omits `-L` and resolves to the user's live socket** (K6; three live sessions since Sep 13) | **high** *(certain without the rule)* | **high** | deterministic, **at runtime on the real argv**: `tests/runner/test_tmux_guard.py::test_an_argv_without_L_is_refused_at_the_exec_site` over `check_tmux_argv`, plus `tests/boundaries/test_tmux_blast_radius.py::test_every_tmux_argv_carries_an_explicit_socket` as the AST second net — **two planted proofs**: a `["tmux", "list-sessions"]` literal in `runner/local.py`, **and** the indirection `from .tmux_cmd import TMUX_BIN; [TMUX_BIN, "ls"]`, which defeats the AST rule and **must still be refused at runtime** |
| **A tmux rule is defeated by one line of indirection** (`_taint.py:5-9`: two shipped rules died this way) | **high** *(certain for an AST-only rule)* | **high** | deterministic: one **indirection fixture per rule** — `runner_tmux_via_constant_import.py`, `runner_tmux_via_fstring.py`, `runner_kill_server_via_fstring.py` — the shape `test_platform_branching.py` already ships; **goes red** if a rule matches only the literal spelling |
| **`kill-server` reaches `src/`, or reaches a non-throwaway socket anywhere** (§18's incident, exit 137) | med | **catastrophic** | deterministic: `check_tmux_argv` refuses `kill-server` unless the socket matches `^shepherd-m3-` (**runtime**, on the argv) + `::test_kill_server_appears_nowhere_in_src` (AST, second net) — planted proof for each, including the f-string form |
| **A session name contains `:` or `.`** and `-t` resolves to a different session | med | **high** | deterministic: `::test_a_session_name_never_contains_a_target_separator` over 10 000 generated ulids — **goes red** on any generated id that survives `session_name` with a separator — + `test_every_target_uses_the_exact_form` (`=name:`), which **goes red** on a bare `name` or a `name:0` target, and `check_tmux_argv` refuses a loose `-t` at the exec site |
| **An owned pane orphans: `controld` dies between `runner.start` and `set_runner_handle`** — a real `claude` in a real pane with `runner_handle IS NULL`, made durable by DP5's `detached_launch`, terminable by nothing (`observe_exit` needs the handle it lacks) and invisible to a cap that counts **rows** | **high** *(certain across restarts; one leaked process each)* | **high** | deterministic: `test_a_handle_less_owned_row_is_rebound_by_the_startup_reconcile` and `test_a_pane_with_no_row_is_counted_as_ORPHANED_PANE`; `test_the_total_cap_counts_panes_not_rows` — **goes red** if the cap reads `owned_session_counts` alone |
| **A blind `Enter` answers the trust dialog with "No, exit"** (C15; exit status 1) | **high** *(certain without the detector)* | **high** | deterministic: `test_an_untrusted_directory_becomes_needs_you_and_no_key_is_sent`, run through **`LocalRunner` with a counting `run_argv`**, asserting the spawn **reached its step and set `state == needs_you`** *before* asserting zero calls — a zero count that passes because nothing ran is this repo's dominant defect, and a bare `Enter` here selects **"No, exit"** |
| **A "no bytes were sent" proof is taken at a seam that cannot see the bytes** | **high** *(certain with `ScriptedRunner.writes`)* | **high** | deterministic: the refusal proofs run through `LocalRunner` + a counting `run_argv`. `ScriptedRunner` has **no `run_argv`**, and `write` is one of **ten** `Runner` members — `interrupt` sends `send-keys Escape` through a different one, so a stray `Enter` through any other member leaves `writes == []` and the test green. The `ScriptedRunner` versions are kept as the **fast path**, never as the proof |
| **Text sent into an open permission dialog approves the tool** (D44; the probe created the file) | **high** *(certain without the refusal)* | **catastrophic** | deterministic: `test_a_refusal_sends_no_bytes` (all three refusal outcomes) and `test_a_dialog_refuses_and_sends_no_bytes` over the real capture `06-permission-dialog.txt` + `B2-after-typing-into-dialog.txt`, both counting calls on the injected `run_argv` |
| **A queued message is concatenated onto a stale prompt** after an interrupted turn (D45; observed) | **high** | **high** | deterministic: `test_a_non_empty_input_line_defers_delivery` over the captured post-Esc screen |
| **Ghost text is read as a user draft**, so delivery defers forever | **high** *(certain with a plain `-p` reader)* | med | deterministic: `test_ghost_text_is_not_a_draft` over `A1-suggestion.ansi.cat-v.txt` (SGR 2), plus a negative over the same screen captured with `-p` |
| **`Runner.write` writes to `#{pane_tty}`** and delivers **zero bytes** while printing to the screen | med | **high** | deterministic: `test_keys_go_through_send_keys_H_never_the_pane_tty` + a boundary rule that `pane_tty` is never read outside `runner/` |
| **An interrupt is sent as SIGINT**, which *terminates* Claude Code (D43; `SessionEnd{other}`, exit 0) | **high** *(certain if §6's old `signal()` is copied)* | **high** | deterministic: `test_interrupt_is_escape_and_never_a_signal` — asserts the argv and asserts no `os.kill`/`signal` symbol resolves inside `runner/` |
| **The tmux server dies with `controld`**, taking every owned pane (D49, DP5) | **high** *(certain under a default unit)* | **high** | deterministic: `test_the_server_is_started_through_detached_launch` + the `HostPlatform` contract rows; **live**: `test_the_pane_survives_a_controld_restart` |
| **Discovery registers a second, attached row for an owned session** | **high** *(certain without pre-registration)* | **high** | deterministic: `test_discovery_does_not_duplicate_an_owned_session`; **live**: `test_a_spawn_registers_exactly_one_row` |
| **Every `ask()` litters the fleet with a finished row** (T19-1, now per call) | **high** | med | deterministic: `test_the_fork_row_is_ephemeral_from_birth` + `test_an_sdk_cli_row_is_reconciled_to_ephemeral` |
| **`can_set_title` is flipped to `True` without the recorded approval** (DP1) | med | med | deterministic: `test_can_set_title_ships_false`, which names DP1 in its failure message |
| **`/rename` is delivered mid-turn** and reaches the model as *text* rather than as a command (the enqueue/`absorbed_mid_turn` path) | **high** *(certain without a gate)* | med | deterministic: `test_a_slash_command_is_only_delivered_at_a_prompt_ready_pane` |
| **A snapshot is re-encoded** (decoded, escaped, or `innerHTML`-ed) and the terminal renders mojibake | med | **high** | deterministic: `test_the_first_frame_is_the_snapshot_byte_for_byte` + `test_no_unescaped_interpolation_in_frontend` (inherited) over the new files |
| **The WebSocket accepts a cross-origin handshake** (§13) | med | **high** | deterministic: `test_the_handshake_matches_rfc6455_and_checks_origin`, with a negative case per origin form |
| **`xterm.js` cannot be obtained on this host** (no node, no npm, no browser) | **high** | med | manual checklist **T19-a**, plus `test_the_terminal_degrades_to_a_screen_view_when_the_vendor_file_is_absent` — the page renders `capture-pane -p` text and says why |
| **The terminal is *unverifiable* on this host** — no browser exists | **high** *(certain)* | med | named host gap **G-M3-6**; server-side proofs only, and acceptance clause 11 says in words what is not claimed |
| **`db.py` is at 599 of 600 lines**, so one new verb fails the build | **high** *(certain if touched)* | low | deterministic: inherited `test_no_source_file_exceeds_600_lines`; M3 puts every new verb in `store/sessions.py` / `store/mailbox.py` (ADR-M3-6) |
| **`controld.py` has zero spendable lines and M3 wires five capabilities into it** — it is **140**, and `tests/daemons/test_controld_composition.py` asserts `lines <= MAX_DAEMON_LINES(150) − RESERVED_FOR_M2(10)` = **140**. Revision 1's T23 claimed both "≤ 5 lines in the root" **and** "the reserve intact", which are mutually exclusive | **high** *(certain if the root grows at all)* | **high** | deterministic: inherited `test_the_composition_root_keeps_headroom_under_adr1s_cap`, **unmodified** — T23's budget is **zero new root lines** (see T23), and weakening `MAX_DAEMON_LINES` or `RESERVED_FOR_M2` to fit is forbidden by K11/K17 and by `test_the_line_budget_constants_are_unchanged` |
| **A boundary rule fires on this plan's own code and a builder adds an exemption** (K11) | **high** | **high** | deterministic: all 23 inherited rules green **with no new exemption**, asserted by the inherited exemption-list test |
| **Subscribing `PostToolBatch` slows every hook or corrupts the user's settings** (T18-2) | med | **high** | deterministic: installer dry-run diff against a throwaway settings file **that is populated with Shepherd's own installed block**, not the shipped `{}` — a merge reviewed against an empty file cannot exhibit the bad-merge-with-a-populated-file risk it exists to check + `test_hookd_latency_under_10ms` re-run + the per-test sha256 guard |
| **The live lane's registration test passes vacuously**: `tests/e2e/conftest.py:103-109` writes `settings.write_text("{}\n")` ("an explicit, empty settings file"), so a spawned session emits **no hooks to Shepherd at all**, and `test_a_spawn_registers_exactly_one_row` asserts `count == 1` in a world where the second writer could never run. Acceptance clause 2's "after the hook lane has run" is then false | **high** *(certain with `{}`)* | **high** | deterministic: T24's fixture installs Shepherd's **real** block via the shipped `install_hooks(settings_path, entry)`, and the test asserts a `SessionStart` was **actually received** before asserting any count — **goes red** if the ingest count is zero, which is exactly the state that made the old assertion vacuous |
| **The live lane's `test_no_tmux_is_invoked_at_all` is deleted** to make room for M3's tmux tests | **high** *(certain if unplanned)* | **high** | deterministic: it is **replaced by a stronger rule**, not removed — and the replacement lives in `tests/boundaries/`, **deterministic and unmarked**, so it runs on the default `-m "not live"` sweep. The shipped one is in `tests/e2e/test_live_attached_session.py`, whose module-level `pytestmark = pytest.mark.live` (line 47) **deselects it on every ordinary run** — the strongest blast-radius rule in the tree, never executed by CI's equivalent. Planted `-L shepherd` turns it red |
| **A blast-radius rule's stated scope exceeds the tree it walks** (M2 acceptance clause 2's exact defect, and revision 1 repeated it: P-M3-15 claimed "every tmux invocation in `tests/`" from a single-directory `glob("*.py")`) | **high** | **high** | deterministic: the rule walks `tests/**/*.py` **and** `docs/probes/**/*.py` by recursive iteration, and `test_the_scan_scope_is_what_it_claims` asserts the walked set is non-empty, contains a file from each of three directories, and equals the recursive glob — **goes red** if the walk is narrowed |
| **A live test leaves a tmux session behind** on a shared machine | **high** | med | deterministic: a session-scoped fixture asserting `tmux -L shepherd-m3-live ls` reports **no server** at teardown, exactly as the 2026-09-14 probe did (`*/teardown.txt`) |
| **A probe or live test touches `~/.claude/settings.json`** (K3) | low | **catastrophic** | deterministic: the inherited per-test sha256 guard, which M3's new live module inherits by living in `tests/e2e/` |
| **This plan's repo facts go stale under a concurrent builder** — it happened twice during M2 | **high** | med | manual: **step 0b**, six rows, three ASSERT and three RECORD, before T1 |

---

## Blocker protocol

Unchanged from M1 and M2, and it is the reason an overnight run survives. A builder that hits a
blocker **marks it and moves to the next workable task. It does not stop the milestone.**

1. Append to **`docs/plans/2026-09-17-m3-BLOCKERS.md`**:
   `T<id> · <symptom> · <what was tried> · <what it blocks> · <owner: evidence gap | decision gap | host gap | upstream bug>`.
2. An **evidence gap** names the probe that would close it. Do not guess the shape.
3. A **decision gap** is written in the four-part form — decision · pressure · options · recommendation
   — and **the recommendation is not applied**.
4. Mark the task `BLOCKED`, leave the partial work behind `pytest.mark.xfail(strict=True, reason=…)`
   naming the blocker id, and take the next task whose `Dependencies` are satisfied.
5. **A boundary rule firing is never a blocker and never earns an exemption** (K11).
6. **A tmux rule firing is a stop-work item, not a blocker.** K6/K16 exist because of an incident.
   Fix the argv; never widen the rule.

---

## Inherited blockers — what M3 owns, and what it does not

| Entry | Owner per the ledgers | M3's disposition |
|---|---|---|
| **T18-2** — `PostToolBatch` is not in `SUBSCRIBED_EVENTS` (24 names), so M1's `TOOL_BLOCKED_BY_HOOK` / `TOOL_PERMISSION_REFUSED` counters can never fire | re-pointed 2026-09-17 to **"a milestone that can install hooks (M3 spawns sessions; M6 owns packaging)"** | **M3 owns it — Task 22.** M3 is the first milestone that can satisfy the preserved checklist honestly: it spawns a real session with an explicit `--settings <throwaway>`, so the dry-run diff is reviewed against a file that is not the user's and K3 is upheld **by construction, not by a guard**. The checklist is executed verbatim: add the name; re-review the installer's dry-run diff against a throwaway settings file; re-run `test_hookd_latency_under_10ms` against E34's 3.2 ms budget; assert the real settings file's sha256 unchanged. If any step fails, the entry is re-pointed to M6 with the failure recorded — **not** quietly left. |
| **T19-1** — a hooked `claude -p` run registers and appears on the fleet tree; `entrypoint` is absent from all 429 hook payloads | **"decided at M3, where `ownership` stops being a single value"** | **M3 owns it — DP2, Task 21.** Option 2 applied, plus pre-registration, which makes the general case rare rather than common. D47 untouched. |
| **T18-2a** — `doctor` may not name the unsubscribed event, because §5.0's engine-vocabulary rule fails the build on a hook event name outside `engines/` | decision gap; names `hook_subscription_status` as the tool to add | **Closed as a consequence of Task 22, or re-pointed.** Once `PostToolBatch` is subscribed the two counters can move, and the `idle` line is replaced by real numbers. If Task 22 re-points, T18-2a stays open unchanged. |
| **T3-1** (`stop_sequence` capture), **T3-2/T4-1** (`AnomalyKind` ordering), **T8-1** (heuristic 5's vocabulary), **T8-2**, **T13-3**, **T15-1**, **T17-2/G-M2-7** | M2, various | **Not M3's.** Named so a builder touching `signals/` for the owned-session lifecycle does not half-fix one. |
| **T14/T15/T16-1** — the *rendered* page is unproven on this host (no browser) | **host gap** | **Inherited and widened, not closed.** M3 adds a terminal, which is the least verifiable thing in the product on a host with no browser. See **G-M3-6** and acceptance clause 11. |
| **T3/T4** — `MacHost` unverified | open by design (D55) | **Not a blocker.** M3's seventh member joins the same regime: written, annotated, `verified() is False`. |
| **G-M2-2** — `crashed` is unreachable at M2 because an attached session yields an exit time and never an exit code (C13) | M2 named M3 as the milestone that makes it reachable | **M3 closes it for owned sessions only** (Task 12): `remain-on-exit on` + `#{pane_dead_status}` gives a real exit code. For attached sessions it stays open, unchanged and correct. |

---

## Evidence gaps — named here so BUILD does not discover them

K1 applies: the task's first step is a probe, or the behaviour ships **explicitly unverified and says
so**, counted.

| # | Gap | Effect on M3 | Disposition |
|---|---|---|---|
| **G-M3-1** | **Mostly closed, and it was closed before this plan was written.** `C-u` **does** clear the TUI input line: `gap-fill/keys-claude-20260914T180105Z/steps.log` lines 6–7 recall history into a non-empty box (`raw_up_recalls_history: true`) and then send `C-u`; `01-after-raw-up.txt` shows `❯` + NBSP + `FIRST-PROMPT-FOR-HISTORY` and `01b-after-ctrl-u.txt` shows `❯` + NBSP + **empty**, with `Ctrl+Y to paste deleted text`. Revision 1 missed this because it read `data-schemas.md` §Key semantics — which has no `C-u` row — and not the capture folder beside it. `Esc` is separately captured as *not* clearing (`esc_clears_input: false`). **What is still open:** `C-a C-k`, `C-w`, and whether `C-u` clears the **post-`Esc` restored** prompt, which the same probe never tried. | D45's clearing step **ships** on the `C-u` evidence; only the post-`Esc` variant is unproven. | **Narrowed probe P1** (T1). The clearing form ships now (**DP10**), guarded by a **re-read of the pane after `C-u`**: if the box is not empty afterwards, it is `REFUSE_INPUT_NOT_EMPTY`, counted, retried. The re-read is why the unproven variant costs nothing. |
| **G-M3-2** | **`--fork-session` combined with `--session-id` was "not attempted"**, and `--no-session-persistence` in that combination is help text, not a capture. | `ask()`'s pre-registration (DP2 half one) and its no-residue claim (DP7). | **Probe P2** (T1). Fallback named in DP7 and **capture-backed**: the fork's id comes from the `-p` run's own `--output-format json` result (`headless-20260914T160308Z/h5_fork.stdout.json`, `"session_id"`), never from the sidecar — which `registry.py:3-5` says the engine **deletes on exit**, and which T15 never polls in time to read. Transcript residue is accepted and named, never deleted. |
| **G-M3-3** | **"A second tmux client typing at the same time as browser writes" is unverified.** Only size interaction, read-only attach and byte delivery were tested. | §12's `[tmux attach]` beside a live browser terminal (**DP9**). | **Probe P3** (T1). If interleaving corrupts input, the header offers `attach -r` only, and the full-control command carries the warning. |
| **G-M3-4** | **Text starting with a digit at a permission dialog, `Esc`, and `Tab to amend` are unverified.** Only `Enter`, `Down` and letters were sent. | `answer_permission`'s `deny` and `approve_always` (**DP8**, D44). | **Probe P4** (T1). Until it lands, `approve` is the captured `Enter`-on-default and `deny` **refuses with a reason** rather than guessing a keystroke. |
| **G-M3-5** | **`/rename` against a session live in another process is unverified**, and the probe notes it *"risks two writers on one transcript"*. | The attached half of **DP1**. | **No probe is planned at M3.** `can_set_title` stays `False` for attached sessions on this evidence, and the probe that would close it is named here so a later milestone can weigh the risk deliberately. |
| **G-M3-6** | **xterm.js rendering is not probeable on this host** — `data-schemas.md` §Not probeable on this host: "no node, npm, tsc or browser here". Browser notification/sound likewise. | The terminal's *rendering* cannot be verified anywhere in M3. | Every **server-side** claim is proven: the snapshot bytes are byte-identical to `capture-pane -e -p` output, the WS frames round-trip (`gap-fill/websocket-…/handshake.json`), and a keystroke reaches the pane byte-exact (provable with `gap-fill/keydump.py`, which is checked in). **Acceptance clause 11 states what is not claimed.** Closing it needs a machine with a browser. |
| **G-M3-7** | **Engine version drift**: `data-schemas.md` pins every shape to **2.1.270**; this host runs **2.1.273**. | Every argv flag M3 spawns with (`--session-id`, `--name`, `--fork-session`, `--no-session-persistence`, `--effort`, `--settings`). | **Step 0 re-runs `docs/probes/drift_check.py --record`**, which M1's T17-2 made a shipped gate `doctor` reads. **T10 additionally asserts each flag against `claude --help` on this host** and records the output — a flag list is not an enum the drift check covers. |
| **G-M3-8** | **`Notification{permission_prompt}` arrives 6 s late and only if unanswered; nothing marks a `PermissionRequest` resolved.** The sidecar's `waiting → busy` is the only observed clearing signal. | The write policy's dialog gate (**DP8**). | Both sources are read and both must be clear (DP8 option d). The 9.194 s sidecar-transition capture is the fixture. |
| **G-M3-9** | **A slow `SessionEnd` hook's survival past `kill-session` is unverified** — only fork-free bash hooks were used. | `kill_session` may lose the final `SessionEnd`. | **Record the kill before issuing it** (the same rule `data-schemas.md` gives for `pane_dead_status`, which `kill-session` erases). The verdict is written from the recorded action, not from a hook that may not arrive. Counted as `KILL_WITHOUT_SESSION_END` when the hook does not follow. |

---

## Codebase Reality Check (verified on this host, 2026-09-17)

Every row was checked by running the command, not recalled.

| Fact | How it was verified | Consequence for the plan |
|---|---|---|
| **M2 is complete and green: 869 passed, 1 skipped, 13 deselected** on `.venv/bin/pytest -m "not live"`; **`mypy --strict` clean over 79 source files**; **23 boundary tests** over **57 fixtures**, all green. The live lane collects **12** (`test_live_attached_session.py` 7, `test_live_stop_classification.py` 5). | ran all four | M3 edits a working system. Every `Consumes` below names a symbol that exists today. |
| **`src/shepherd/store/db.py` is 599 lines. The cap is 600.** | `wc -l` | **One line of headroom.** Every M3 store verb goes in **`store/sessions.py`** and **`store/mailbox.py`**, following `store/stops.py`'s precedent (ADR-M3-6). A task that edits `db.py` beyond one line has already failed. |
| **`src/shepherd/daemons/controld.py` is 140 lines and has ZERO spendable lines.** The guard is `lines <= MAX_DAEMON_LINES(150) − RESERVED_FOR_M2(10)` = **140**, so it is exactly on its budget. `toolsurface/compose.py` is 119 (cap 600) and holds both module-globals plus `log_root`, `transcript_root`, `publish_result`. **The reserve's docstring itemises M2 wiring that has since shipped** ("the stop path's construction is 4 lines … M2's two tools add their directories"), so the *justification* is stale even though the *number* still binds. | `wc -l`, read `test_controld_composition.py` in full | **Revision 2 correction.** Revision 1 said "≤ 5 lines in the root" **and** "the reserve intact" — mutually exclusive at 140/140. **T23's budget is zero new root lines**, achieved by having `compose_tool_surface` construct the runner from the `store` and `host` the root **already passes** (`controld.py:74`) and return them in one record. The stale reserve is **not** re-targeted by a builder: if a builder judges zero impossible, that is a named plan change (rename the reserve, state the new number, itemise what each line buys), never an improvisation, and never a weakening of the guard. |
| **`src/shepherd/core/anomalies.py` is a closed `StrEnum`, documented "append-only"**, with 22 members ending at `TOOL_RESULT_UNPAIRED`. `toolsurface/tools_m1.py:239-240` renders `{str(kind.value): 0 for kind in AnomalyKind} \| store.list_anomaly_counts()` — the **enum is what supplies the zero rows**. `Store.bump_anomaly(kind: str)` accepts any string. | read all three | **A bare `str` anomaly kind is counted only once it has fired and is never displayed as `0`**, which is precisely the state principle 5 (K9) forbids. Revision 1 declared `KILL_WITHOUT_SESSION_END`, `MAILBOX_INPUT_NOT_EMPTY` and `ASK_FORK_RESIDUE` as bare `str` inside `orchestration/` and no task listed `core/anomalies.py`. **T2 now owns the file and appends M3's members at the end** (M2's deferred ordering blocker T3-2/T4-1 is **not** reopened). |
| **`tests/e2e/conftest.py:103-109`'s `throwaway` fixture writes `settings.write_text("{}\n")`** — docstring: *"a throwaway working directory plus an explicit, empty settings file"*. `engines/claude_code/hooks_config.py` ships `install_hooks(settings_path, entry, dry_run)` and `HookEntry`, built from `HostPlatform.hook_dispatch()`, with `_shepherd_managed` markers and post-write validation. | read both | **A session spawned with `--settings {}` emits no hooks to Shepherd at all.** So revision 1's `test_a_spawn_registers_exactly_one_row` was a **vacuous pass** and T22's merge dry-run was reviewed against a file that cannot exhibit a bad merge. **T24 populates the fixture with the M1 installer's own output** — the installed block, not a hand-written imitation — and the registration test asserts a `SessionStart` **arrived** before asserting any count. The real `~/.claude/settings.json` (sha256 `375e5322…`) is still never touched. |
| **`signals/hook_lane.py:149` already defines `HookLane._rebind`**, reached from line 92. | `grep -n` | Revision 1's T12 added a callback also called `rebind` **in the same file**. Renamed to **`on_engine_session_rebound`** (T12), so no reader meets two `rebind`s in one module. |
| **`tests/e2e/test_live_attached_session.py:47` carries a module-level `pytestmark = pytest.mark.live`**, and `test_no_tmux_is_invoked_at_all` (l.107) sits under it, globbing `Path(__file__).parent.glob("*.py")` — **one directory, non-recursive**. | read it, `grep -n pytestmark` | The strongest blast-radius rule in the tree is **deselected on every `-m "not live"` run** and never walked `tests/` at all. **T5 moves the replacement to `tests/boundaries/`** — deterministic, unmarked, walking `tests/**/*.py` and `docs/probes/**/*.py` recursively. T24 keeps a narrower live version as a second check. |
| **tmux is `3.4` on this host and was `3.4` in the 2026-09-14 capture run** (`run-20260914T154946Z/versions.txt`). `claude` was `2.1.270` then and is `2.1.273` now. **`run-20260914T154946Z/` holds exactly six `.ansi` files**: `01-trust-dialog`, `02-after-trust`, `03-after-stop`, `06-permission-dialog`, `08-prompt-with-suggestion`, `09-resize-after-70x30`. Neither `07-running-after-send` nor `13-dead-pane` is among them. | `cat versions.txt`, `tmux -V`, `ls *.ansi` | **The `capture-pane -e -p` **format** is stable across the two runs (same tmux); the **screen content** is not (different engine). And **`BUSY` and `DEAD` have no `-e` capture**, so revision 1 cited them to plain-`.txt` evidence while `read_pane` consumes `-e` bytes. **T6 reclassifies both on format fields** (see T6). |
| **`list-sessions -F` prints `#{pane_dead}`, `#{pane_dead_status}` and `#{alternate_on}` as first-class fields**: `14-list-sessions-after-sigterm.txt` shows `probe_b\|4041912\|1\|1\|\|0\|…` and `probe_sig\|…\|1\|143\|\|0\|…`. | read the capture | **`pane_dead == 1` is sufficient for `DEAD` and needs no pane capture at all.** This is what lets T6 drop a citation it could not honour. |
| **`shepherd.runner` and `shepherd.orchestration` are already in the layer map** (`tests/boundaries/_imports.py::LAYER_OF`, L2 and L3) and in `FORBIDDEN_BELOW_L4`. Neither package exists. | read `_imports.py`, `ls src/shepherd/` | **The boundary rules already govern code M3 has not written.** `web/` and `cli/` may not import either; the terminal reaches them through `toolsurface` (**DP4**, ADR-M3-3). |
| **`host/base.py` declares exactly six `HostPlatform` members** plus `verified()`, and `testkit/scripted_host.py` + `tests/contracts/test_hostplatform_contract.py` cover all three drivers. | read all three | **DP5**: a seventh member touches four files, and the contract suite is where it is proved. |
| **`signals/discovery_loop.py::discovery_pass` already parses `entrypoint`, `tmux` and `nameSource`**, already applies D29's title ratchet from the registry (`title_from_registry`, `TITLE_SOURCE_RANK`), already `continue`s on `sdk-cli`, and already finds an existing row with `store.get_session_by_engine_id` before registering. | read it | **This is why DP2's fix is small and why DP1's confirmation reader already exists.** Task 21 changes a `continue` into a reconcile; Task 20 reads `nameSource` through the parser that ships. |
| **`store/db.py::register_session` requires a non-null `engine_session_id`** and is idempotent on `ux_session_engine_id`; it sets neither title, parent, depth, nor `runner_handle`. | read it | M3 needs **`create_owned_session`**, a new verb in `store/sessions.py`. Pre-registration (DP2) depends on `--session-id` giving us the id in advance. |
| **Migration 001 already has every session column M3 needs**: `runner_handle`, `worktree_path`, `title_synced_at`, `parent_session_id`, `ephemeral`, `depth`, `attempt`, `origin`, `ownership`, `engine/provider/model/effort/credential_ref`. Migration 002 added the stop group. | read `001_m1_foundation.sql` | **Migration 003 adds one table and no session column** — the mailbox (**DP3**). |
| **`tests/e2e/conftest.py` ships the live lane's isolation**: `throwaway` (a workdir + an explicit `--settings`), `shepherd_home` (XDG relocation), and an **autouse per-test sha256 guard** on the real `~/.claude/settings.json`. `LIVE_MODEL = "claude-haiku-4-5"`, `CLAUDE_TIMEOUT_S = 180.0`. | read it | M3's live tests inherit K3's guard by living in `tests/e2e/`. `Throwaway.argv()` is `-p`-shaped and M3 needs a TUI shape: **extend, do not replace** (Task 24). |
| **`tests/e2e/test_live_attached_session.py::test_no_tmux_is_invoked_at_all` globs `Path(__file__).parent.glob("*.py")`** and fails on any tmux token in a non-docstring literal **anywhere in `tests/e2e/`**. | read it | **M3's live lane cannot exist beside it unchanged.** Task 24 replaces it with a **stronger** rule (every tmux call names a throwaway socket, never `shepherd`), and the replacement is mutation-proved. Deleting it is a plan violation. |
| **`tmux 3.4` and `claude 2.1.273` are on this host**; `data-schemas.md` pins every shape to **2.1.270**. | `tmux -V`, `claude --version` | **G-M3-7.** Step 0's drift check, plus T10's `--help` assertion for the five flags M3 spawns with. |
| **`tmux -L shepherd ls` reports `aivisor`, `main`, `spike`, created Sun Sep 13.** The socket directory also holds `shepherd-probe`, `shepherd-spike` and 25 `shp-gap-*` sockets from the probe suite. | ran it (read-only) | **K6 is not hypothetical on this machine.** Shepherd's default socket is `shepherd-runner` (D49); probes use `shepherd-m3-probe`; the live lane uses `shepherd-m3-live`. |
| **`web/static/` holds 7 files and no vendored library**; `pyproject.toml` ships `"shepherd.web" = ["static/*"]` — a **single-level** glob. | `ls`, read `pyproject.toml` | A vendored `xterm.js` in a subdirectory would be **absent from an installed wheel**, which is M1's T16-2 defect returning. Task 19 vendors at the top level or adds the glob, and `tests/test_packaging.py` is extended to prove it. |
| **`web/routes.py` maps GET paths to tool names and has no POST support**; `web/server.py` already validates `Origin`/`Host` against the bound address and refuses any bind but `127.0.0.1`. | read both | M3 adds POST routes and one WS path. The origin check exists and is **inherited, not written under deadline** — exactly what its docstring promised M4 and M3 gets first. |
| **`toolsurface/types.py::ToolResult.data` is typed `object`**, and `ToolDef.handler` is `Callable[[ToolArgs], object]`. | read it | A terminal **stream handle** can cross L4 as a returned object without widening the seam (ADR-M3-3). No `Any` is introduced. |
| **No ADR directories exist** — `docs/adr/`, `docs/decisions/`, `docs/rfcs/`, `*ADR*.md` all absent. | `find` | The architecture of record is **§3's 55 decisions + D38.1**, treated as settled. M1's, M2's and this plan's ADRs live inside their plans. |

**Technical-approach match.** The approach is the one M1 and M2 proved: pure functions at the unit
seam, a data table rather than a branch tree (ADR-6), `store/` verbs returning dataclasses (D33),
consumers through `invoke()` only (D35), stdlib everything. **Unstated infrastructure: one** —
`xterm.js`, which D51 already names as the single runtime dependency and which K8 requires be
vendored rather than fetched. No new Python dependency, no service, no network call.

---

## Plan-vs-spec and plan-vs-code gaps

| # | Spec/code says | Plan does | Why | Evidence |
|---|---|---|---|---|
| **N1** | D47 registers on any event; E35 keys fleet membership on `entrypoint` | pre-registration + a discovery-side reconcile of `sdk-cli` rows | `entrypoint` is absent from all 429 hook payloads | **DP2**, T19-1 |
| **N2** | §7: "six tables" | **seven** — `mailbox_message` in migration 003 | D12's coalescing, idempotency and restart survival are table properties | **DP3** |
| **N3** | §9: `browser ──WS──► sessiond`; §5: `sessiond` hosts `runner/` | the WS is served by `controld`; `runner/` is a stateless adapter callable from either | `sessiond` has no HTTP server, no store, and no inbound control channel; §13 keeps listeners at one | **DP4**, ADR-M3-1 |
| **N4** | ~~D55: the seam owns **exactly six** things~~ — **absorbed into D55 on 2026-09-17.** `orchestrator-platform.md:166` now reads "exactly **seven** things", names detached launch, cites `q1-cgstop.txt`/`q1-scopestop.txt`, and credits this plan's DP5 | seven — `detached_launch`, which is now what the decision says | **no gap remains.** The row is kept rather than deleted so the trail from "the plan pushed" to "the decision absorbed it" survives | **DP5** (now a record, not a pressure) |
| **N5** | §6/D36: `EngineAdapter` is a `Protocol` seam | three module-level functions in `engines/claude_code/`, with a named promotion trigger | M1/M2 already shipped four of its members that way; a Protocol with one adapter is D9's own mistake | **DP6** |
| **N6** | D13: "discard the fork" | a **headless** fork with `--no-session-persistence`; any residue is named, never deleted | K3 forbids writing (and deleting) under `~/.claude/`; `--no-session-persistence` works only with `--print` | **DP7** |
| **N7** | §7 layout: `sessions/<id>/pty.log` — terminal scrollback, ring file | **not built.** `pipe-pane` runs only while a client is attached and its sink is removed on detach | the byte stream is cursor-addressed diffs and cannot be replayed from an offset; nothing in M3 reads it | §tmux pipe-pane live byte stream |
| **N8** | §9: `needs_you` → "write immediately (it is *asking* you)" | **two kinds of `needs_you`**: a question writes, a dialog refuses | D44, and the probe in which the message was discarded and the tool approved | **DP8** |
| **N9** | D14/§12: `tmux attach` makes jump-to-terminal **exact** | exact for bytes; **not** for size, and the UI says so; `attach -r` offered for a safe hand-off | `resize-window` forces `window-size=manual` | **DP9** |
| **N10** | §9 line 1135: owned sessions on `tmux -L shepherd` | `shepherd-runner`, configurable | **D49**, and a live `shepherd` server with three of the user's sessions on it | audit + `tmux -L shepherd ls` |
| **N11** | §6 `Runner` has eight members | **ten** — `pane(handle) -> PaneState` and `list_owned_panes() -> tuple[PaneRef, ...]` | `pane()`: the write policy and the trust detector need the screen's *meaning*, and `snapshot()` returns bytes. `list_owned_panes()`: an owned pane can outlive its row (`controld` dying between `runner.start` and `set_runner_handle`, made durable by `detached_launch`), so **the panes are the ground truth and the rows are the index** — the total cap counts panes, and the startup reconcile needs the same enumeration. Both must be answerable by `ScriptedRunner` or no test above the unit seam can run | this plan, ADR-M3-4; the tenth added in revision 2 |
| **N12** | §11: `get_session_output(id, lines)` → "pty tail (owned)" | for owned sessions it returns the **`capture-pane -p` screen**, not a tail of the byte log | a tail of ANSI diff-render bytes is not readable text; the screen is what a human means | §tmux capture-pane output |
| **N13** | §8 line 940: `starting` holds until the first signal or 60 s | a **trust-blocked** spawn is `needs_you`, with the dialog named | no hook and no sidecar appear until a human answers; the literal rule mislabels it `running` or `crashed` | C15, `01-hooks-before-trust.txt` |
| **N14** | §6: `Runner.signal()` / §8 `killed` | there is no `signal()`; interrupt is `send-keys Escape` | **D43**, and SIGINT *terminates* Claude Code | §Interrupting a running TUI turn |

---

## Assumption ledger

`proven_by_code` means proven by a real capture or by a command run on this host.

| # | Assumption | Class | Basis / what would falsify it |
|---|---|---|---|
| A1 | tmux `send-keys -H` delivers arbitrary bytes to a pane, byte-exact | `proven_by_code` | `keys-keydump.jsonl`: `1b`, `03`, `e29c93`, a hand-built bracketed-paste sequence |
| A2 | Writing to `#{pane_tty}` delivers **zero** bytes of input | `proven_by_code` | same capture: "nothing read; `XYZ` appears on screen" |
| A3 | `capture-pane -e -p` returns the screen with SGR and OSC 8 intact; the alternate screen has **no** scrollback (`history_size` 0) | `proven_by_code` | `04-scrollback-stats.txt` |
| A4 | `pipe-pane` yields a cursor-addressed diff stream, not lines | `proven_by_code` | `03-pipe-pane-head.cat-v.txt` |
| A5 | A `:` or `.` in a session name is silently rewritten, and `-t a:b` resolves to session `a`, window `b` | `proven_by_code` | `tmux-naming-…/naming.txt` |
| A6 | A bare `tmux` inside a pane resolves to that pane's socket; `-L` overrides | `proven_by_code` | `inpane-output.txt` |
| A7 | A tmux server started inside a systemd user unit dies with `systemctl --user stop`/`restart`; a `--scope` server survives | `proven_by_code` | `q1-cgstop.txt`, `q1-cgrestart.txt`, `q1-scopestop.txt` |
| A8 | `--session-id <uuid>` makes the engine session id known **before** the process starts, and `SessionStart` echoes it | `proven_by_code` | `supp-…/02-sessionstart-and-sidecar.txt` |
| A9 | A positional brief auto-submits and stays byte-exact **only** as separate argv words; a single command string goes through `sh -c` | `proven_by_code` | `argv-…/results.json` (`prompt_equals_brief` true/false) |
| A10 | tmux refuses a command over ~16 KB (largest accepted word 16 324 B) | `proven_by_code` | `tmux-argv-limit.txt` |
| A11 | An untrusted directory stops the spawn on a dialog with **no hook and no sidecar**, and a bare `Enter` exits 1 | `proven_by_code` | `01-hooks-before-trust.txt`, `01b-list-sessions-after-refuse.txt` |
| A12 | Text typed into a permission dialog is discarded and the following `Enter` approves the tool | `proven_by_code` | `B2-after-typing-into-dialog.txt`, `B-file-created.txt` |
| A13 | An interrupted turn emits **no** `Stop`; after `Esc` during streaming the prompt returns to the input box | `proven_by_code` | `interrupt-…/results.json`, `hooks.jsonl` |
| A14 | SIGINT terminates Claude Code (`SessionEnd{other}`, exit 0); `Escape` interrupts | `proven_by_code` | same |
| A15 | `/rename` makes the engine write `custom-title` + `agent-name`; the sidecar reports `nameSource:"user"`; **no hook fires** | `proven_by_code` | `10-rename-transcript-new-lines.jsonl`, `10-sidecar-after-rename.json`, `10-rename-hooks.txt` |
| A16 | A fork leaves the target's transcript byte-identical and fires no hook for it; `can_fork = True` | `proven_by_code` | `12-fork-summary.json`, data-schemas §Fork l.2920 |
| A17 | `remain-on-exit on` preserves `#{pane_dead_status}`; `kill-session` removes the row entirely | `proven_by_code` | `14-list-sessions-after-sigterm.txt`, `15-list-sessions-after-kill.txt` |
| A18 | A stdlib RFC 6455 handshake and masked-frame round-trip works on this Python | `proven_by_code` | `websocket-…/handshake.json` |
| A19 | The sidecar's `waiting`+`waitingFor` → `busy` transition is the only observed permission-clearing signal | `proven_by_code` | the three-file capture pair, 9.194 s apart |
| A20 | `new-session -e KEY=VAL` sets a pane variable; a **later** client's env is ignored, and `PATH` comes from the client | `proven_by_code` | `tmux-env-…/env.txt` |
| A21 | **`--fork-session` accepts `--session-id`** | `inferred` **(non-critical — DP7's fallback is capture-backed and P2 decides before any code is written)** | §Not verified: "not attempted". Falsified by: the CLI refusing the combination, in which case the fork's id comes from A25's result JSON and `create_owned_session` takes `engine_session_id: str \| None` |
| A22 | **`C-u` clears the TUI input line** | **`proven_by_code`** *(reclassified in revision 2 — the capture was in the repo when revision 1 called this `inferred`)* | `gap-fill/keys-claude-20260914T180105Z/steps.log` l.6–7 (`Up` → `C-u`, `raw_up_recalls_history: true`), `01-after-raw-up.txt` (box holds `FIRST-PROMPT-FOR-HISTORY`) → `01b-after-ctrl-u.txt` (box empty, `Ctrl+Y to paste deleted text`), at `claude 2.1.270` / `tmux 3.4`. Falsified by: the box being non-empty after `C-u` — **which the delivery path re-reads and handles** (DP10), so falsification degrades to a counted refusal rather than to a corrupted instruction |
| A22-a | **`C-u` also clears the post-`Esc` restored prompt** | `inferred` **(non-critical — the post-`C-u` re-read makes a wrong answer a refusal, not a concatenation)** | the same probe sent `Esc` twice (steps 04, 04b) and never sent `C-u` afterwards. Falsified by: P1's narrowed run |
| A25 | **A `--resume … --fork-session -p --output-format json` run's result object carries the fork's own `session_id`** | `proven_by_code` | `headless-20260914T160308Z/h5_fork.cmd.txt` (the exact argv) + `h5_fork.stdout.json`: `"type":"result"`, `"subtype":"success"`, `"is_error":false`, `"result":"FORKED"`, `"session_id":"f0c208a0-…"` — **different from the resumed `55b21a24-…`**, so it is the fork's. Falsified by: the key moving or disappearing at 2.1.273, which **T1/P2 re-checks and records into `data-schemas.md` §Fork** |
| A23 | **`1`/`2`/`3` selects a permission-dialog option** | `inferred` **(non-critical — `approve` uses the captured `Enter`-on-default; `deny` refuses rather than guesses)** | §Not verified. Falsified by: P4 |
| A24 | **xterm.js renders the snapshot and the stream identically** | `inferred` **(non-critical in the sense that nothing else depends on it, and critical in the sense that it cannot be tested here — G-M3-6 states it and clause 11 refuses to claim it)** | not probeable on this host |

**Critical assumptions classified `inferred`: none.** A21, A22-a and A23 are each gated by a probe
that runs **before** the code they would affect, and each has a named fallback that needs no
unverified shape — A21's is A25's captured result JSON, A22-a's is the post-`C-u` pane re-read, A23's
is refusing rather than guessing a keystroke. A24 is a stated non-claim, not a load-bearing
assumption.

**Confidence arithmetic:** 90 base − 0 (no critical inferred assumption) − 25 (Recommended Defaults
non-empty: RD1–RD9) = **65**. Unchanged at revision 2: A22 moved from `inferred` to `proven_by_code`,
which removes a probe dependency but does not change the arithmetic, because no `inferred` assumption
was critical at revision 1 either.

---

## Differences from agreement

| # | Agreement | This plan | Status |
|---|---|---|---|
| D-1 | §16's M3 row lists seven items | all seven, **plus** owned-session lifecycle (exit codes, `/resume` rebinding, interrupt/terminate) | **Decomposition, not addition.** "tmux runner" without `probe()` and `terminate()` is not a `Runner`; §6 declares both, and M2's G-M2-2 named M3 as the milestone where `crashed` becomes reachable. |
| D-2 | §16 lists M3's contents | **plus** migration 003 (`mailbox_message`) | **Addition**, forced by D12 — see **DP3**. A reviewer who rejects the table must say where a queued message survives a restart. |
| D-3 | §16 lists M3's contents | **plus** the two inherited ledger entries M3 is the **named** owner of (T18-2, T19-1) | **Addition**, and both were assigned to M3 by name. T19-1 is forced: without it every `ask()` litters the fleet. |
| D-4 | §16: "rename + the `can_set_title` probe (D29)" | the local rename ships; the write-back ships **behind a flag that is `False`**; the probe is the live-lane test | **Clarification, and it is DP1's whole point.** The user's instruction is that DP1's recommendation is stated and **not applied**. §16 asked for the probe, not for the flip. |
| D-5 | §9: fallback `PtyRunner` behind the same interface | not built; `can_spawn=False` and a readable refusal instead | **Reduction, named.** A fallback with no trust-dialog detector is less safe than an honest refusal. |
| D-6 | §7's layout names `sessions/<id>/pty.log` | not built | **Reduction, named** — **N7**. |
| D-7 | The brief: "M3 only" | four probes (P1–P4) run **before** the code that depends on them, and two probes named-but-not-run (P5, P6) | **Clarification.** §18's spike is done; these four are exactly what `data-schemas.md` §Not verified still leaves open for M3's surfaces, and the brief asks the plan to say which. |

---

# LAYER 2 — EXECUTION CONTRACT LAYER

## Context references — read before starting (paths, not summaries)

| File | Why the builder must open it |
|---|---|
| `/root/Shepherd/CLAUDE.md` | **All four tmux rules. Not advisory — there is an incident behind them.** Read before writing a single tmux argv. |
| `docs/specs/orchestrator-platform.md` **§9** | **The heart of M3.** LocalRunner, terminal fidelity, the write-policy table, the mailbox, `ask()`, and §9.5's complete list of who talks to whom. Also **§3** (the 55 decisions + D38.1), **§5.0** (the five layers, downward-only imports), **§6** (the `Runner` protocol and `EngineCapabilities`), **§7/§7.1** (the session columns and the title ratchet), **§11** (the tool surface and the recursion caps), **§12** (page 3, the rename affordance), **§13** (loopback, origin, subprocess), **§14.2** (`Scripted*`), **§18** (the risks and the incident). |
| `docs/specs/data-schemas.md` **§Surface: interactive Claude Code (TUI) under tmux** (l.2053–2931) | **Every shape M3 asserts lives here.** Read the whole surface once: trust dialog, hook parity, `Notification`, `PermissionRequest`, `SessionEnd`, `SessionStart`, send-keys hazards, titles, the sidecar, `list-sessions` formats, `capture-pane`, `pipe-pane`, `resize-window`, fork. |
| `docs/specs/data-schemas.md` **§Not verified** (l.5909) and **§Not verified on this surface** (l.5831) | **What is *not* known.** G-M3-1…9 are drawn from here; a builder who adds a shape that is not in the document has written a gap, not a feature. |
| `docs/specs/data-schemas.md` gap-fill blocks l.4781–5250 and l.5745–5828 | tmux under systemd (DP5), pane environment, naming, `$TMUX` inheritance, second-client attach, raw key bytes, key semantics, interrupts, argv limits, the WebSocket handshake, `PtyRunner`. |
| `docs/specs/implementation-constraints.md` | All 24. **C4, C5, C14, C15, C16, C17 are M3's**; C7, C8, C13, C21, C23 shape what M3 may read. |
| `docs/plans/2026-09-17-m2-signals-engine-plan.md` | **ADRs M2-1…M2-7 and the constraint keys are inherited.** Its Task 1 (`core/stops.py`) is the shape every M3 vocabulary module copies; its Task 18 is how a composition root is extended. |
| `docs/plans/2026-09-17-m2-BLOCKERS.md`, `docs/plans/2026-09-16-m1-BLOCKERS.md` | The open entries M3 inherits; T19-1 at l.1100 and the T18-2 re-pointing at l.304 are M3's by name. |
| `src/shepherd/host/base.py` + `src/shepherd/host/linux.py` + `src/shepherd/testkit/scripted_host.py` + `tests/contracts/test_hostplatform_contract.py` | **The four files a seventh seam member touches** (DP5), and the pattern for an unverified `MacHost` value. |
| `src/shepherd/signals/discovery_loop.py` | `discovery_pass`, `title_from_registry`, the `sdk-cli` `continue`. **Tasks 20 and 21 both read this before touching anything.** |
| `src/shepherd/engines/claude_code/registry.py` | The sidecar parser: `RegistryEntry`, `parse_sidecar`, `scan_registry`, `is_attached_interactive`, `entrypoint`, `tmux`, `name_source`, `status`, `waiting_for`. **The write policy's dialog gate and the rename's confirmation both read it.** |
| `src/shepherd/store/db.py` (**599 lines, cap 600**) + `src/shepherd/store/stops.py` | `register_session`, `get_session_by_engine_id`, `apply_fold_delta`, and the precedent for putting new SQL in a sibling module. |
| `src/shepherd/toolsurface/compose.py` + `src/shepherd/daemons/controld.py` | Where capabilities are registered and in what order. **The root has a 10-line reserve and M3 adds five capabilities.** |
| `src/shepherd/web/server.py` + `src/shepherd/web/routes.py` | The origin check, the loopback refusal, and the path→tool table M3 extends with POSTs and one WS path. |
| `tests/boundaries/_imports.py` + `tests/boundaries/_taint.py` | **K11.** `LAYER_OF` already contains `shepherd.runner` and `shepherd.orchestration`. Read `_taint.py` before writing a rule: it follows the *value*, not the syntax. |
| `tests/e2e/conftest.py` + `tests/e2e/test_live_attached_session.py` | The live lane's isolation, and `test_no_tmux_is_invoked_at_all`, which Task 24 **replaces with a stronger rule** rather than deletes. |
| `docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/` | **The fixtures.** `01-trust-dialog.ansi.cat-v.txt`, `06-permission-dialog.txt`, `03-after-stop.txt`, `09-resize-after-70x30.txt`, `13-dead-pane.txt`, `14-list-sessions-after-sigterm.txt`. **No mocking of Claude Code — the fixtures ARE Claude Code.** |
| `docs/probes/2026-09-14-schemas/gap-fill/keydump.py` | A checked-in raw-mode pane program. **The keystroke path's end-to-end proof runs against it, not against a mock.** |
| `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` | The probe harness P1–P4 copy: throwaway socket, `env -i` server, verified teardown, `versions.txt`. |

**Distillation rule:** reference by path. The next agent reads the file, not a summary of it.

---

## Durability horizons

| Piece | Horizon | Consequence for effort |
|---|---|---|
| `core/runner.py` — `RunnerHandle`, `ProcState`, `PaneState`, `SessionSpec`, `EngineCapabilities` | **stable** — M4's wake set, M5's worker loop and any future `SSHRunner` all read these | worth precision; designed twice (ADR-M3-1) |
| `runner/base.py::Runner` | **stable** — §6 declares it and D36 makes it a Protocol | the interface is the artifact; the tmux driver is replaceable |
| `runner/tmux_cmd.py` | **stable** — it is where K6 is enforced, and its shape is what makes the rule checkable | one function, one property, mutation-proved |
| `runner/pane.py` | **near-term-refactor** — a TUI redraw changes a screen, and the fixtures are dated `2.1.270` | one predicate per pane kind, each citing its capture |
| `orchestration/write_policy.py` | **stable** — §9 calls it "the part that must not be wrong" | a total table over three enums, no branches |
| `orchestration/mailbox.py` + `store/mailbox.py` + migration 003 | **stable** — D12 says channels get no second delivery path, so M6 builds on this exactly | version nothing, but keep coalescing pure |
| `orchestration/ask.py` | **near-term-refactor** — the fork flags are the newest evidence in the plan | one argv builder, probed at T1 |
| `web/ws.py` | **stable** — D51 makes it ~200 lines Shepherd owns forever | RFC 6455 is a fixed target; test the framing, not the transport |
| `web/static/terminal.js` + the vendored `xterm.js` | **near-term-refactor** — M4 adds the chat page beside it | one render function, no framework |
| `engines/claude_code/spawn.py` | **near-term-refactor** — flags drift with the engine (G-M3-7) | each flag asserted against `--help` and recorded |

---

## Test-seam selection

**Four seams, and M3 introduces exactly one new one — the tmux command boundary.** The ideal is one;
the others are M1's and M2's and are reused unchanged.

- **Unit seam (existing) — pure functions over real captures.** `pane_state(bytes, fields)`,
  `decide_write(...)`, `coalesce(messages)`, `spawn_argv(spec)`, `tmux_argv(...)`, the WS framer.
  **The 2026-09-14 capture files are the fixtures.** Fastest, most stable, and it is where the
  write policy — the thing that must not be wrong — is proved.
- **Command seam (new, and the only new one) — `run_argv: Callable[[list[str]], CommandResult]`,
  injected into `LocalRunner`.** Every tmux interaction is an argv list in and captured bytes out, so
  the whole runner is testable with **no tmux server at all**, and a test asserts *the exact argv
  list* — which is what makes K6 checkable rather than hopeful. Proposed at the highest point that
  still covers the risk: one function, one injection point, no per-command abstraction.
- **Integration seam (existing) — `toolsurface.invoke()`.** Every M3 capability is a `ToolDef`;
  route tests and CLI tests attach here, never to an HTTP handler, so M4's gate lands under existing
  tests (D38).
- **Contract seam (existing pattern, new suite) — `tests/contracts/test_runner_contract.py`.**
  §14.2: one suite, every implementation passes it — `LocalRunner` (real tmux, `live`-marked rows
  skipped off-host) and `ScriptedRunner`. The same shape `test_hostplatform_contract.py` already has.
- **E2E lane (existing) — `tests/e2e` under the `live` marker.** The claims no fixture can prove: a
  real trust dialog, a real `/rename` reaching `custom-title`, a real fork leaving the target
  untouched, a real pane surviving a `controld` restart.

**No new `Scripted*` beyond the one §14.2 mandates.** `ScriptedRunner` is a concrete peer of
`LocalRunner`, never a base class, and it ships in `testkit/` with the package.

---

## Behavior contract (critical_path requirement)

**C-M3-1 — No tmux process starts without a permitted socket, and the check is on the argv.**
The callable `make_run_argv(permitted)` returns — the single process-exec site in `src/` — calls
`check_tmux_argv(argv, permitted=permitted)` **before** `subprocess.run`, and **refuses, never
repairs**: `argv[0:2] == ["tmux", "-L"]`,
`argv[2] ∈ permitted` (never `shepherd`, whatever configuration says), every element after a `-t`
matching `^=[A-Za-z0-9_-]+:$`, and `kill-server` only when `argv[2]` matches `^shepherd-m3-`. The one
argv permitted without `-L` is the exact list `["tmux", "-V"]`, which contacts no server — matched by
list equality, never by prefix. Every argv `src/` produces is still built by
`runner/tmux_cmd.py::tmux_argv`, and `kill-server` still appears nowhere in `src/`; those are AST
rules and are the **second** net, not the guarantee. *(K6, K16, ADR-M3-2, ADR-M3-8; P-M3-1, P-M3-2; T5, T8)*

**C-M3-2 — A pane target is always exact.** Every `-t` value is `=<session_name>:`, and
`<session_name>` is `shepherd_<ulid>`, which contains neither `:` nor `.`. Existence is checked with
`has-session -t =name`, never with `display-message`, which returns rc 0 for a missing target.
*(A5; P-M3-3; T5)*

**C-M3-3 — The write policy is a total, pure function of a 4-tuple key.** The key is
`(SessionState, PaneKind, Ownership, input_empty: bool)` — **96** tuples — and `WRITE_RULES` holds
exactly one rule per tuple. `decide_write(state, pane, ownership)` projects a `PaneState` onto that
key (`input_empty` comes from `PaneState.input_text` with ghost text excluded) and returns exactly
one `WriteDecision`; it never raises, reads no clock, opens no file and sends no bytes. **`input_empty`
is a key field, not a note: `REFUSE_INPUT_NOT_EMPTY` is reachable only through it.** **Sending is the
caller's separate step, and a refusal sends nothing.** *(§9, D44, ADR-M3-5; P-M3-4, P-M3-5; T13)*

**C-M3-4 — No programmatic write reaches a pane with a dialog open.** Both the sidecar and the pane
text must say the pane is clear. A refusal is counted and named; it is never converted into a send.
*(D44, DP8; P-M3-5; T13)*

**C-M3-5 — A spawn never answers a dialog for you.** In the trust-dialog state the spawn sends
**zero** keys, sets `needs_you`, and names the dialog. *(C15, A11; P-M3-6; T11)*

**C-M3-6 — Interrupting is `Escape`; terminating is `kill-session`; neither is a signal.** No module
in `runner/` or `orchestration/` resolves `os.kill`, `signal.`, `SIGINT` or `SIGTERM`.
*(D43, A14; P-M3-7; T8)*

**C-M3-7 — A session Shepherd starts exists in the store before its process does**, with the
`engine_session_id` Shepherd chose, so no lane ever creates a second row for it.
*(DP2; P-M3-8; T11, T15)*

**C-M3-8 — The observer still never harms the observed.** M3 writes only under
`$XDG_DATA_HOME/shepherd` and into panes it owns. It never writes, and never deletes, under
`~/.claude/`. A missing sidecar, an unreadable pane, a dead server or an absent tmux degrades the
answer and is counted; it never raises and never blocks a fold. *(principle 4, K3; P-M3-9; T6, T8)*

**C-M3-9 — Terminal bytes are never transformed, and the claim is proved on this host.** The snapshot
frame is the exact bytes `capture-pane -e -p -S -2000` returned; live chunks are the exact bytes
`pipe-pane` wrote, in order; a keystroke is delivered with `send-keys -H` as the exact bytes the
browser sent. Nothing is decoded, escaped, normalised or routed through `innerHTML`.
**Two proofs, because one of them proves less than it sounds.** (i) Deterministic, over the six
checked-in `.ansi` captures: the framer does not mutate bytes. That is *all* it proves — the test
reads a checked-in file, frames it, and compares to the same file; it says nothing about what
`capture-pane` returns here. (ii) **Live (T24), which is the clause's real basis**: run the real
`capture-pane -e -p -S -2000` through the live lane's `make_run_argv` callable against an owned pane on
`shepherd-m3-live`, frame the result, and assert the WS frame payload **equals those bytes**. Added
in revision 2 because revision 1 asserted (i) and claimed (ii). *(§13, A1, A3; P-M3-10, P-M3-17; T17, T19, T24)*

**C-M3-10 — `ask()` never touches its target.** The target's transcript sha256 is unchanged and no
hook fires for it. The method (`fork` or `mailbox`) is always reported. *(D13, A16; P-M3-11; T15)*

**C-M3-11 — A rename is honest.** `title_synced_at` is set **only** after the engine's own
`nameSource:"user"` is read back. While `can_set_title` is `False`, no keys are sent and the UI says
`local only`. *(D29, DP1; P-M3-12; T20)*

**C-M3-12 — The mailbox delivers once.** A repeated `idempotency_key` enqueues once; a delivered
message is never re-sent, across a restart; five queued messages arrive as one. *(D12; P-M3-13; T14)*

---

## Purity boundary map (critical_path requirement)

| Module | Pure? | What it may touch | Enforced by |
|---|---|---|---|
| `core/runner.py`, `core/mailbox.py` | **pure** — types, enums, constants | nothing | inherited `test_core_purity` |
| `runner/tmux_cmd.py` | **pure** — argv in, argv out; **and `check_tmux_argv`, argv in, refusal or nothing out** (ADR-M3-8) | nothing. No `subprocess`, no `os`, no clock. The **predicate** lives here; the **exec site** that calls it is `runner/local.py` | `test_tmux_cmd_imports_no_process_module` (AST over its import closure) |
| `runner/pane.py` | **pure** — bytes + format fields in, `PaneState` out | nothing | `test_pane_reader_opens_nothing` |
| `runner/local.py` | **impure** — it runs processes | `LocalRunner` **only** through the injected `run_argv`; `make_run_argv`'s callable is the **one** `subprocess` site in `src/`, and `check_tmux_argv` is its first statement. Never `shell=True`, never a path it resolved itself | `test_local_runner_constructs_no_subprocess_call` (AST: no `subprocess.` symbol resolves in `LocalRunner`), `test_the_exec_callable_checks_before_it_execs` (`subprocess.run` patched to fail the test if reached) |
| `orchestration/write_policy.py` | **pure** | nothing. No clock, no store, no runner | `test_write_policy_reads_no_clock` |
| `orchestration/mailbox.py` | **impure orchestration** | an injected `Store`, an injected `Runner`, an injected clock, an injected publisher | `test_mailbox_constructs_nothing` |
| `orchestration/spawn.py`, `lifecycle.py`, `ask.py`, `dialogs.py`, `rename.py` | **impure orchestration** | the same four injections and nothing else | same rule, one test per module |
| `engines/claude_code/spawn.py` | **pure** — `SessionSpec` in, argv out | nothing | `test_spawn_argv_is_pure` (200 cases, same input → same output) |
| `store/sessions.py`, `store/mailbox.py` | **impure, SQL** | the connection `db.py` hands them (ADR-7) | inherited `test_storage_boundary` |
| `web/ws.py` | **impure, socket** | the connection `server.py` hands it | `test_ws_resolves_no_capability_itself` |
| `toolsurface/tools_m3.py` | **impure, projection** | injected `Store`, `Runner`, clock | inherited `test_consumer_boundary` |

**`now` is always a parameter.** Same rule M1 and M2 already enforce through `test_one_clock`.

---

## Provable properties (critical_path requirement)

| # | Property | How it is proven |
|---|---|---|
| **P-M3-1** | **Runtime:** no argv reaches `subprocess` whose `argv[0] == "tmux"` and whose `argv[1:3]` is not `["-L", <permitted socket>]`; the socket `shepherd` is refused unconditionally. **AST (second net):** every list returned by `tmux_argv` has `argv[0] == "tmux"`, `argv[1] == "-L"`, `argv[2] == socket`, over 1 000 generated calls; and the literal `"tmux"` appears in **no other** module under `src/` | `tests/runner/test_tmux_guard.py::test_an_argv_without_L_is_refused_at_the_exec_site`, `::test_the_socket_shepherd_is_never_permitted`; `tests/boundaries/test_tmux_blast_radius.py::test_every_tmux_argv_carries_an_explicit_socket`, `::test_tmux_is_spelled_in_exactly_one_module` — **three planted proofs (T5, T8):** `["tmux", "list-sessions"]` in `runner/local.py`; the indirection fixture `runner_tmux_via_constant_import.py` (`from .tmux_cmd import TMUX_BIN`), which the AST rule **misses by design** and the runtime check **must still refuse**; and `["tm" + "ux", "ls"]` |
| **P-M3-2** | **Runtime:** a `kill-server` argv is refused unless `argv[2]` matches `^shepherd-m3-`. **AST (second net):** the token `kill-server` appears in no AST string literal under `src/` | `tests/runner/test_tmux_guard.py::test_kill_server_is_refused_off_a_throwaway_socket` — **goes red** if the socket predicate is dropped or widened to `shepherd-runner`; `test_kill_server_appears_nowhere_in_src` — **planted proof, plus the f-string fixture `runner_kill_server_via_fstring.py` (`f"kill-{verb}"`), which the literal scan misses and the runtime check refuses.** The scan is over every module `iter_modules()` finds, not a named list (M2 acceptance clause 2's lesson) |
| **P-M3-3** | For 10 000 generated session ids, `session_name(id)` contains neither `:` nor `.`; every `-t` argument matches `^=[A-Za-z0-9_-]+:$`, enforced at the exec site as well as by the builder | `test_a_session_name_never_contains_a_target_separator` — **goes red** on any generated id that survives with a separator; `test_every_target_uses_the_exact_form` — **goes red** on a bare `name` or `name:0`; `tests/runner/test_tmux_guard.py::test_a_loose_target_is_refused_at_the_exec_site` |
| **P-M3-4** | `WRITE_RULES`' **set of key tuples** equals `set(itertools.product(SessionState, PaneKind, Ownership, (False, True)))` — 4 × 6 × 2 × 2 = **96** — and each rule's `decision` is a `WriteDecision` member. **The assertion is on the set, never on a length.** `decide_write` never raises over 500 mutated inputs | `test_the_key_set_equals_the_product` — **goes red** when `SessionState`, `PaneKind` or `Ownership` grows and the table does not, **and** when a row is dropped or duplicated, which `len(...) == 96` would not catch. **`len(WRITE_RULES) == 96` is forbidden**: it is the hand-maintained-list defect this repo has shipped three times, and here a dropped `REFUSE_INPUT_NOT_EMPTY` row would pass silently while bytes went into a pane the policy meant to refuse. `test_decide_write_never_raises` over 500 mutated inputs including non-members, fed as `cast(SessionState, "no-such-state")` — **`cast` is not `Any`, so `disallow_any_explicit` holds** |
| **P-M3-5** | For **every** key whose decision is a refusal — all three of `REFUSE_DIALOG`, `REFUSE_NO_PTY`, `REFUSE_INPUT_NOT_EMPTY` — the delivery path issues **zero calls on the injected `run_argv`**, and the caller **reached the refusal** (the returned `WriteDecision` equals the expected refusal and `last_refusal` is stamped on the row) before the zero is asserted | `tests/orchestration/test_write_policy.py::test_a_refusal_sends_no_bytes` (T13) — driven through **`LocalRunner` with a counting `run_argv`**, not through `ScriptedRunner.writes`. **Why**: `ScriptedRunner` has no `run_argv`, and `write` is one of ten `Runner` members — `interrupt` sends `send-keys Escape` through a different one, so a stray key through any other member leaves `writes == []` and the test green. The `ScriptedRunner` version is kept as the fast path. **Planted proof:** a `send-keys` call before the decision check in `orchestration/mailbox.py` |
| **P-M3-6** | A spawn that resolves to `TRUST_DIALOG` sets `state == needs_you` **and** issues zero calls on the injected `run_argv` — the state assertion first, so a spawn that never ran cannot pass | `tests/orchestration/test_spawn.py::test_an_untrusted_directory_becomes_needs_you_and_no_key_is_sent` (T11), through `LocalRunner` + a counting `run_argv`. **Goes red** on any convenience `Enter`, which at this dialog selects **"No, exit"** (A11, exit status 1), **and** on a spawn that returns before reaching the poll |
| **P-M3-7** | No module under `src/shepherd/runner/` or `src/shepherd/orchestration/` resolves `os.kill`, `signal.SIGINT`, `signal.SIGTERM` or `subprocess.Popen.kill` | `test_no_signal_reaches_a_session` (AST with origin resolution, the r6 form) — **planted proof** |
| **P-M3-8** | After a spawn, `SELECT count(*) FROM session WHERE engine_session_id = ?` is exactly 1, after the hook lane and a discovery sweep have both run | `tests/signals/test_discovery_loop.py::test_discovery_does_not_duplicate_an_owned_session` (**T21** — added in revision 2; revision 1 named it in no task's Required Checks), and live `tests/e2e/test_live_owned_session.py::test_a_spawn_registers_exactly_one_row` (**T24**), which asserts a `SessionStart` was **received** before asserting the count |
| **P-M3-9** | **Population, named rather than implied.** *Runner:* the ten `Runner` members plus `ensure_server`, enumerated from the `Runner` Protocol at test time — **11** entry points. *Orchestration:* every public callable in every module under `src/shepherd/orchestration/`, enumerated by `iter_modules()` — the plan's own count is **17** (`spawn`×2, `lifecycle`×4, `mailbox`×4, `ask`×1, `dialogs`×2, `rename`×3, `write_policy`×2 — the two pure ones included because purity is not immunity to a bad input). *Degradations:* **the whole capture truncated at every byte boundary**, plus empty, non-UTF-8, a directory's bytes, and an absent sidecar. **Each test asserts its own case count equals the value it computed**, so the loop cannot shrink silently. Every degradation returns a value and counts a named `AnomalyKind` member; **none raises** | `tests/runner/test_local.py::test_the_runner_never_raises` (**T8**) and `tests/orchestration/test_degradation.py::test_orchestration_degrades_and_counts` (**T20** — added in revision 2). **Revision 1's generator could not reach its own number**: "truncation at every byte boundary of the **last line**" of `13-dead-pane.txt` yields **49** cases (the last line is 49 bytes; the whole file is 154), and no check asserted `cases == 200` — M2 fixed this exact shape and wrote down why. **Goes red** if the enumerated population shrinks, if the asserted count disagrees with the generated one, or if any input escapes as an exception |
| **P-M3-10** | The framer does not mutate bytes: the snapshot frame equals the captured bytes byte-for-byte for **the six checked-in `.ansi` captures** — `01-trust-dialog`, `02-after-trust`, `03-after-stop`, `06-permission-dialog`, `08-prompt-with-suggestion`, `09-resize-after-70x30` (`ls run-20260914T154946Z/*.ansi`, verified 2026-09-17) — including the OSC 8 hyperlink and the NBSP after `❯`. **This set is not T6's six captures**; the two overlap in four, and each is now named in full where it is used | `tests/web/test_ws.py::test_the_first_frame_is_the_snapshot_byte_for_byte` — **one owner: T19** (revision 1 let both T17's and T19's checks claim it). **Goes red** if the snapshot is decoded, escaped, or re-encoded anywhere between `capture-pane` and `term.write` |
| **P-M3-17** | **Live:** the WS frame payload equals the bytes the **real** `capture-pane -e -p -S -2000` returned on this host, for an owned pane on `shepherd-m3-live` | `tests/e2e/test_live_owned_session.py::test_the_live_snapshot_frame_is_the_bytes_capture_pane_returned` (**T24**, added in revision 2). P-M3-10 proves the framer; this proves the **path**. **Goes red** if any layer between the exec callable and the frame normalises, and it is the only test that can — tmux is `3.4` both in the captures and here, so the format is stable, but the live path is not proved by a file comparing to itself |
| **P-M3-11** | Over the fork capture, the target's transcript digest and hook count are unchanged; `AskResult.method` is always one of `fork`/`mailbox` and is never absent | `test_the_target_transcript_is_unchanged`, `test_the_method_is_reported_never_silently_downgraded` |
| **P-M3-12** | `title_synced_at` is non-null **only** on a row whose confirmation read returned `nameSource == "user"`; and while `can_set_title` is `False`, no path sets it | `test_title_synced_at_requires_a_confirmation`, `test_can_set_title_ships_false` |
| **P-M3-13** | `enqueue` is idempotent on `(session_id, idempotency_key)`; `deliver` moves every pending row to delivered in one transaction; `coalesce` is a pure function whose output contains every input's text exactly once | `test_a_repeated_idempotency_key_enqueues_once`, `test_delivery_is_not_repeated_after_a_restart`, `test_coalesce_loses_nothing` |
| **P-M3-14** | No `src/` module and no test opens a path under `/root/.claude/` or `$HOME/.claude/` **for writing**, by AST over `src/**/*.py` and `tests/**/*.py` with origin resolution on the path expression; the live lane's per-test sha256 guard (`375e5322…`) holds for every new test | `tests/boundaries/test_engine_config_is_read_only.py::test_nothing_writes_under_the_engine_config_dir` (**new, T5** — revision 2). Revision 1 said "inherited `test_no_fixture_reads_the_real_claude_dir` (extended to a write scan)"; **that name exists twice** (`tests/golden/test_classifier_golden.py:250`, `tests/engines/test_transcript_tail.py:536`), each scoped to its own module's fixtures, and neither is a tree-wide write scan — so the property named a test nobody was going to write. **Planted proof:** `Path.home()/".claude"/"x"` opened `"w"` in a `src/` module. Plus the autouse sha256 guard |
| **P-M3-15** | Every tmux invocation in **`tests/**/*.py` and `docs/probes/**/*.py`** names a socket, never `shepherd`; `kill-server` under `src/**`, `tests/**` and `docs/probes/2026-09-17-m3-*/**` carries a socket matching `^shepherd-m3-` | `tests/boundaries/test_tmux_blast_radius.py::test_no_tmux_call_in_the_tree_can_reach_the_users_socket` — **deterministic, unmarked, in the default run.** Revision 1 claimed "every tmux invocation in `tests/`" and carried the rule in `tests/e2e/`'s `glob("*.py")`, **behind `pytestmark = pytest.mark.live` (line 47)** — one directory, and deselected on every `-m "not live"` run. `test_the_scan_scope_is_what_it_claims` asserts the walked set equals the recursive glob and spans three directories — **goes red** if the walk narrows. **Planted proof: `-L shepherd` in a test.** T24 keeps a narrower live version as a second check |
| **P-M3-16** | Every row of the pane table (T6), the write table (T13), the **spawn-argv** table (T10) and the dialog key map (T16) carries a non-empty `evidence` string naming a section that **exists** in `docs/specs/data-schemas.md` | Four tests, each named in exactly one task's Required Checks: `test_every_pane_rule_cites_an_existing_section` (T6), `test_every_write_rule_cites_an_existing_section` (T13), **`test_every_spawn_rule_cites_an_existing_section` (T10 — added in revision 2; the spawn-argv variant was named by the property and created by no task)**, `test_every_dialog_rule_cites_an_existing_section` (T16). Each **goes red** if a row's `evidence` names a section that is not in the document — the mechanical K1 enforcement M1 and M2 already have |

**The rule this table now obeys (revision 2):** *every test named in a property row appears **verbatim
in exactly one task's Required Checks**, and every task that owns one is named in the row.* Revision 1
broke it five times — P-M3-5's `test_a_refusal_sends_no_bytes`, P-M3-8's deterministic half, P-M3-9's
`test_orchestration_degrades_and_counts`, P-M3-14's write scan, and P-M3-16's spawn-argv variant each
named a test **no task created**. **P-M3-5 is one of the five mandatory mutation proofs**, and its
nearest neighbour (`test_a_dialog_refuses_and_sends_no_bytes`) covers only the dialog cells — so a
verifier matching on name alone would have scored it PASS while two of its three refusal outcomes went
unproved. **This is verbatim the defect M2 recorded and fixed**, and it is why the rule is stated here
rather than left to the self-review.

---

## Edge-case catalogue (critical_path requirement)

| # | Case | Source | Handling |
|---|---|---|---|
| E-M3-1 | The pane is on the trust dialog: `alternate_on=0`, no sidecar, no hook, for ≥15 s | `01-*` | `TRUST_DIALOG` → `needs_you`, reason names the directory. Zero keys sent (**N13**) |
| E-M3-2 | Trust is refused: pane dead, status 1, and **no `SessionEnd` at all** | `01b-*`, `debug-b.log` | `stopped` with `why` naming the refusal; **not** `crashed` |
| E-M3-3 | A permission dialog is open and a programmatic write arrives | `B2-*`, `B-file-created.txt` | `REFUSE_DIALOG`, counted. The message stays queued |
| E-M3-4 | The dialog is answered within ~6 s, so no `Notification` ever fires | `event-counts.txt` | The sidecar's `waiting → busy` clears it; no rule waits for a `Notification` |
| E-M3-5 | Ghost text sits in the input box | `A1-suggestion.ansi.cat-v.txt` | SGR 2 → not input. A bare `Enter` on a ghost submits **nothing** (captured), so delivery still needs its own text |
| E-M3-6 | A prompt is back in the input box after `Esc` during streaming | `interrupt-*` | **`CLEAR_THEN_SEND`**: `C-u`, then **re-read the pane**, then send. `C-u` is capture-proven on a history-recalled prompt (`01-after-raw-up.txt` → `01b-after-ctrl-u.txt`); whether the post-`Esc` box is the same widget is **P1's one remaining question**, and the re-read is why the answer changes no code. If the box is still non-empty: `REFUSE_INPUT_NOT_EMPTY`, counted as `AnomalyKind.MAILBOX_INPUT_NOT_EMPTY`, retried (**DP10**) |
| E-M3-7 | A turn is interrupted, so **no `Stop` arrives** | `interrupt-*` | Delivery's second trigger — a prompt-ready pane — is why the mailbox does not stall (D45) |
| E-M3-8 | A message is written mid-turn anyway (a human typed it) | `07-*` | Claude Code enqueues it and removes it `absorbed_mid_turn`. Shepherd does not fight it; the transcript entries are the evidence it landed |
| E-M3-9 | `/rename` would be delivered mid-turn | inferred from E-M3-8 | **Refused.** A slash command delivered mid-turn reaches the model as *text*. Only `PROMPT_READY` delivers one |
| E-M3-10 | The brief is 20 KB | `tmux-argv-limit.txt` | Refused before spawn with the measured limit (16 324 B) in the message. **Never truncated** |
| E-M3-11 | The brief starts with `-` | `claude-dash-brief.stderr` | `--` precedes it in `spawn_argv`; without it the pane dies with `unknown option` |
| E-M3-12 | The brief contains `$(…)`, backticks, quotes, `*`, LF, TAB, UTF-8 | `argv-…/results.json` | Byte-exact as **one argv word**. A single command string would be `sh -c`-expanded (K5) |
| E-M3-13 | A second `new-session` client's environment is ignored because the server already exists | `tmux-env-…/env.txt` | Per-session variables go through `new-session -e KEY=VAL`; `PATH` is set on the client |
| E-M3-14 | `claude` is not on the daemon's `PATH` (systemd user manager lacks `~/.local/bin`) | C1, `q2-*` | Resolved to an absolute path **before** spawn; an unresolvable binary is a refusal, not a dead pane |
| E-M3-15 | `/resume` is typed in an owned pane: the old `session_id` **ends** and the same pane continues as another | **C14**, `lifecycle-end-*` | The row **rebinds** `engine_session_id`; it is not marked stopped. `SessionEnd{reason:resume}` + `SessionStart{source:resume}` in the same pane is the signature |
| E-M3-16 | The pane exits: `remain-on-exit on` keeps the row with `pane_dead_status` | `14-*` | Owned sessions get a real `exit_code` — **this closes G-M2-2** for owned |
| E-M3-17 | `kill-session` removes the row entirely, so no exit status survives | `15-*` | **Record the kill before issuing it** (G-M3-9) |
| E-M3-18 | SIGTERM to the pane process: `SessionEnd{other}`, `pane_dead_status` 143, empty `pane_dead_signal` | `14-*` | `killed` when Shepherd sent it; `crashed` otherwise — and the *record-first* rule is what tells them apart |
| E-M3-19 | A `/compact` prints every hook's command line into the pane | `11-compact-after.txt` | Pane noise. The pane reader classifies on structure, never on hook text |
| E-M3-20 | The TUI prints `tmux detected · scroll with PgUp/PgDn` | `03-after-stop.txt` l.41 | Expected. Not a dialog, not an error |
| E-M3-21 | `capture-pane -S -2000` returns only the visible rows (`history_size` 0 on the alternate screen) | `04-scrollback-stats.txt` | The snapshot is the screen. Earlier output comes from the transcript, never from a promised scrollback (**N7**) |
| E-M3-22 | `resize-window` silently switches the window to `window-size=manual` | `attach.txt` | Recorded on the handle, surfaced in the UI, and the `[tmux attach]` affordance says what a human will see (**DP9**) |
| E-M3-23 | A read-only client (`attach -r`) delivers zero bytes | `attach.txt` (`hex: 0`) | The safe hand-off, offered first |
| E-M3-24 | A fork inherits the user title, so two sessions share one name and `/resume` is ambiguous | `13-dead-pane.txt` | An `ask` fork is `ephemeral` and hidden; the ambiguity is named, not fixed |
| E-M3-25 | The fork's transcript does not exist until its first prompt | `12-fork-summary.json` | The answer is read from the `-p` result JSON, not from the file |
| E-M3-26 | A fork carries only post-compact history | `12-fork-answer.txt` | Stated in `AskResult`; it is also all the target's own live context holds |
| E-M3-27 | The session id resolves to two transcript files (the slug is lossy) | §slug rule | M1's shipped `locate_transcript` behaviour, unchanged, counted |
| E-M3-28 | `tmux` is absent, or the server refuses to start | host | `can_spawn=False`; every owned capability refuses with one readable reason; the fleet page says so (D-5) |
| E-M3-29 | Two browser clients open the same terminal | design | One `pipe-pane`, N subscribers; the last one to leave tears it down |
| E-M3-30 | A human attaches and types while the browser writes | **G-M3-3** | Unverified — **probe P3**. Until it lands the header offers `attach -r` first and names the risk |
| E-M3-31 | The vendored `xterm.js` is absent from the wheel because `package-data` is a single-level glob | M1 T16-2 | `tests/test_packaging.py` is extended to assert the file is present **in a built wheel**, not merely in the tree |
| E-M3-32 | A spawn races a discovery sweep | design | `register_session` is idempotent on `ux_session_engine_id`; the pre-registered row wins by existing first (C-M3-7) |
| E-M3-33 | The fork's transcript carries **copied** entries: `uuid` preserved, `sessionId` rewritten, the other spelling `session_id` still the original's, `entrypoint` rewritten `cli` → `sdk-cli`, and **no `forkedFrom` field** | `12-fork-structure.txt`, `12-fork-transcript-head3.jsonl` | The parent link is **Shepherd's own** `parent_session_id`, never an engine field (ADR-M3-7). Nothing reads a fork transcript at M3; if a later milestone does, the duplicate `uuid`s are the hazard to design against |

---

## Architecture Decision Records (inline, durable)

### ADR-M3-1: tmux is the pty supervisor; `runner/` is a stateless argv adapter over it

**Context.** §5 assigns `runner/` to `sessiond`, "the pty supervisor". §9 puts the browser WebSocket
there too. But `sessiond` has no HTTP server, is provably unable to reach the database, and has no
inbound control channel from `controld`, where the tool registry lives. Meanwhile D14 chose tmux
precisely so that session state lives **outside** the daemon.

**First design (rejected — shallow, and expensive).** `sessiond` holds a `LocalRunner` object with a
handle table; `controld` reaches it over a new request/response protocol on a third socket. The
`Runner` interface then exists twice — once as a Python Protocol and once as a wire format — and
every method needs a frame type, a timeout, a failure mode and a test. By the deletion test the
`runner/` module vanishes into a serializer: the complexity does not move anywhere useful, it
multiplies. It also makes the process that must not restart the process that changes most.

**Second design (chosen — deep).** **The tmux server is the supervisor.** Pane lifetime, the pty,
the scrollback, the exit status and the window size all live in a process neither daemon owns, and
every operation §6's `Runner` names is one or two `tmux` argv invocations against a socket. So
`runner/` holds **no state between calls**: a `RunnerHandle` is `(runner, socket, session_name)`, a
string on `session.runner_handle`, and any process that can exec `tmux` can act on it. `LocalRunner`
takes one injected `run_argv` callable, which is the whole seam.

**Consequences.** No new IPC, no third socket, no duplicated interface. The terminal WebSocket can
live in `controld`'s existing loopback server (**DP4**). A `controld` restart loses the browser's
socket and **not** the session. `sessiond` keeps exactly what it owns today. The cost is that the
runner must make the tmux **server** outlive the daemon that first started it, which is **DP5**. It
is also what makes the whole runner testable with no tmux server: a test asserts the argv list.

**Rejected alternative recorded.** Holding pty file descriptors directly (`PtyRunner`) — D14 rejected
it, and the probe adds a second reason: raw pty bytes cannot be searched for dialog text without a
server-side terminal emulator, so the trust detector has no equivalent there (D-5).

### ADR-M3-2: one tmux argv builder, and K6 becomes a property the build checks

**Context.** On 2026-09-12 a bare `tmux kill-server` in an M3 spike destroyed three live sessions,
including the one that issued it. CLAUDE.md's four rules exist because of it. This repo's dominant
defect is a check that reports success without checking, and "we always pass `-L`" is a habit, not a
check.

**Decision.** Every tmux argv list in `src/` is produced by **one** function,
`runner/tmux_cmd.py::tmux_argv(socket: str, *args: str) -> list[str]`, which returns
`["tmux", "-L", socket, *args]` and nothing else. Three boundary rules, all AST-based, all
mutation-proved **and each carrying an indirection fixture**: the literal `"tmux"` may appear in
exactly one module, the token `kill-server` may appear in no `src/` module, and every `-t` argument
is `=<name>:`.

**Revision 2 — the AST rules are the second net, not the guarantee. See ADR-M3-8.** Revision 1 put
the load-bearing invariant here, and it did not hold: each of the three rules falls to one line
(`["tm" + "ux", …]`, `f"kill-{verb}"`, or `from .tmux_cmd import TMUX_BIN`, the last of which yields
an argv with **no `-L`** — the exact blast radius of 2026-09-12). Worse, revision 1's planted proofs
planted *the spelling the rule already looks for*, so they demonstrated only the case never in doubt.
And this very ADR rejected "a lint on the string `kill-server` in one named file" as M2's clause-2
defect, then specified that lint with a wider glob. `tests/boundaries/_taint.py:5-9` exists because
two shipped rules were defeated exactly this way, and says so: *"a rule about a value has to follow
the value."*

**Rejected alternatives.** A code-review convention (unenforceable); a lint on the string
`kill-server` in one named file (M2's acceptance clause 2 showed a four-file scan claiming tree-wide
scope — the exact defect); a wrapper that *appends* `-L` if missing (it would hide the bug rather
than fail on it — and ADR-M3-8's runtime check **refuses, never repairs**, for the same reason);
**AST rules alone** (rejected in revision 2, above).

**Consequences.** Teardown, tests and probes are covered by construction, because they call the same
builder. Adding a tmux call anywhere else fails the build **and cannot start a process** (ADR-M3-8).
The failure message names CLAUDE.md and §18's incident, so the next reader learns why rather than how
to silence it. **Each of the three rules ships one indirection fixture** — `runner_tmux_via_constant_
import.py`, `runner_tmux_via_fstring.py`, `runner_kill_server_via_fstring.py` — the shape the shipped
`test_platform_branching.py` already carries as `cli_platform_alias_import.py`,
`cli_platform_module_alias.py` and `cli_platform_from_import.py`. Two of the three fixtures are
expected to **defeat** the AST rule and are asserted to be **refused at runtime**; that asymmetry is
the point, and a test states it.

### ADR-M3-3: a terminal stream crosses L4 as a returned handle, not as a private import

**Context.** D35 forbids `web/` importing below L4. A terminal needs three request/response
operations (snapshot, write, resize) and one **long-lived** byte stream, and `ToolDef` handlers
return a value.

**First design (rejected).** `web/ws.py` imports `runner/` directly. It is the obvious shape and it
fails the consumer-boundary test on the first run — a plan defect by K11, not a code defect.

**Second design (chosen).** Four registered tools. `terminal_snapshot` (`local_read`),
`terminal_write` (`local_write`), `terminal_resize` (`local_write`) and `terminal_stream`
(`local_read`), whose handler returns a `TerminalStream` — a frozen handle with `chunks()` and
`close()`. `ToolResult.data` is already typed `object`, so nothing widens and no `Any` appears.

**Consequences.** `web/` learns four tool names and no module below L4. D40 is satisfied without a
special case: keystrokes are `local_write`, which §11's blast table **allows** at both autonomy
levels, so M4's gate never prompts per keystroke; what M4 adds is an audit entry for the *connection*
(`terminal_opened` / `terminal_closed`), which is what D40 says should be logged. The drawback is
real and recorded: a long-lived object crossing a call gate is unusual, and the open/close pair is
the only reason it is defensible.

### ADR-M3-4: `Runner` gains a ninth member, `pane()`, because "what is on the screen" is not `snapshot()`

**Context.** §6's `Runner` has eight members. The write policy, the trust detector and the
prompt-ready trigger all need the screen's **meaning** — is a dialog open, is the input box empty —
and `snapshot()` returns bytes. The tmux format fields (`alternate_on`, `pane_dead`,
`pane_dead_status`, `pane_title`, size) are a second call, not a parse of the first.

**Decision.** Add `pane(handle) -> PaneState` to the Protocol, and split it in two: `runner/pane.py`
holds a **pure** `read_pane(capture: bytes, fields: PaneFields) -> PaneState`, and `LocalRunner.pane`
is the two tmux calls that feed it. The classification is unit-testable against the six checked-in
capture files; the plumbing is argv.

**Rejected alternatives.** Parsing bytes at every call site (the same classifier three times, and the
ghost-text trap repeated); folding it into `probe()` (two questions, one record, and `ProcState` is
about the process while `PaneState` is about the screen); leaving it out of the Protocol
(`ScriptedRunner` could then not answer it, so no test above the unit seam could run).

**Consequences.** §6's record grows by two members (**N11**): `pane()`, and — added in revision 2 —
`list_owned_panes()`, on the same argument. An owned pane can outlive its row, so **the panes are the
ground truth and the rows are the index**; the total cap counts panes and T12's startup reconcile
walks them. Putting it on the Protocol rather than in `orchestration/lifecycle.py` also breaks a
dependency cycle: T11 needs the count and T12 depends on T11. `ScriptedRunner` answers both from
fixtures, which is what lets the whole write policy and the reconcile be tested with no tmux at all.

### ADR-M3-5: the write policy is a table, and refusal is a first-class outcome

**Context.** §9 calls this "the part that must not be wrong", and two of its four rows were factually
wrong (D44, D45). A branch tree over `if state == …` is how the wrong rows stayed invisible.

**Decision.** `WRITE_RULES` is a total lookup over the **4-tuple key**
`(SessionState, PaneKind, Ownership, input_empty: bool)` — 4 × 6 × 2 × 2 = **96** keys — each rule
carrying an `evidence` string naming its capture (ADR-6's shape, P-M3-16's rule). `decide_write`
projects a `PaneState` onto that key and returns one of five outcomes, three of which are refusals
with distinct names, because "it did not send" and "it refused because a dialog is open" are
different facts a UI must render differently.

**Revision 2 — the key space was wrong, and the error hid the refusal D45 exists to produce.**
Revision 1 said 48 (`4 × 6 × 2`), but `WriteRule` carries a fourth key field, `input_empty: bool`,
and **`REFUSE_INPUT_NOT_EMPTY` is reachable only through it**. `SessionState` = 4 and `Ownership` = 2
are confirmed in `src/shepherd/core/states.py:22-33`; `PaneKind` is pinned at 6 by T2's own
`test_pane_kind_has_six_members`, so it cannot absorb `input_empty`. The summary table below is
itself 56 rows once its `PROMPT_READY` split and its `DEAD`/`UNREADABLE` merge are expanded — which
already disagreed with 48 on the plan's own page. **96 is the number, carried through P-M3-4,
ADR-M3-5, T13 and acceptance clause 4.** The summary table is a human projection of those 96 keys,
not the key set.

**Consequences.** Totality is a test over the **set of key tuples**, built with
`itertools.product(SessionState, PaneKind, Ownership, (False, True))` and compared as a set — **never
a literal length.** `len(WRITE_RULES) == 96` is forbidden: it is the hand-maintained-list defect this
repo has shipped three times, and here it would let a dropped `REFUSE_INPUT_NOT_EMPTY` row pass
silently (a duplicate elsewhere restoring the count) while bytes went into a pane the policy meant to
refuse. A new pane kind or session state fails the build until every key has an answer; growing
`WriteDecision` — the **value** space — cannot and should not break totality, which is why the
red-condition names the three key enums and not `WriteDecision`. And the refusals are counted as
`AnomalyKind` members, so principle 5 applies to the write path too: how often Shepherd declines to
type is a number on the page.

### ADR-M3-6: new store verbs go in `store/sessions.py` and `store/mailbox.py`, never in `db.py`

**Context.** `store/db.py` is **599** lines against a 600-line enforced cap. M2 hit this and created
`store/stops.py`; `store/rows.py` exists for the same reason.

**Decision.** `store/sessions.py` owns the owned-session verbs
(`create_owned_session`, `set_runner_handle`, `rebind_engine_session_id`, `apply_title`,
`set_ephemeral`, `count_owned`, `children_of`); `store/mailbox.py` owns the mailbox verbs. `db.py`
gains only the thin delegating methods it must, and a task that needs more than one line there has
found a design error, not a line-count problem.

**Consequences.** The cap keeps doing its job — it is a proxy for single responsibility, and here it
produced two modules with obvious names. D33's three rules hold in both: verbs, dataclasses,
transactions inside.

### ADR-M3-7: `ask()` is a headless fork, and the fork is a first-class session row

**Context.** D13 wants a fork asked and discarded; K3 forbids deleting the engine's files; §9's
implementation is a second tmux pane; the probe shows `--no-session-persistence` works only with
`--print`.

**Decision.** `claude --resume <id> --fork-session -p "<question>" --no-session-persistence
--output-format json`, argv only, with a timeout, into a row pre-created as
`origin=ask_fork, ephemeral=TRUE`. The answer is the result JSON's `result` field. No pane, no
`Runner` call, no tmux.

**Consequences.** `ask()` works even when tmux is absent, which is worth stating: the one capability
that reads another session's mind does not depend on the runner at all. The mailbox fallback stays
built for `can_fork=False`, reported as `method="mailbox"`, never a silent downgrade. What is
unverified — `--session-id` with `--fork-session`, and whether a transcript is left — is **P2**, and
both fallbacks are named in DP7.

**What the fork's transcript actually looks like, and the one consequence that changes code.** The
capture (`12-fork-structure.txt`, `12-fork-transcript-head3.jsonl`) shows the fork **copies the
target's history from the last `compact_boundary` onward** with:

| On a copied entry | What happens | Why it matters here |
|---|---|---|
| `uuid` | **preserved** — 16 of 29 fork entries share a `uuid` with the original | Two files on disk carry the same entry `uuid`. Any reader that keys on `uuid` alone (M2's tail reader does not) would see a duplicate rather than a copy |
| `sessionId` | **rewritten** to the fork's id | The fork's own entries are internally consistent, so `locate_transcript` + the tail reader work on it unchanged |
| `session_id` (the other spelling, on 11 copied lines) | **still the original's** | **This is the only parent link the engine records** |
| `entrypoint` | rewritten `cli` → `sdk-cli` on a `-p` fork | **Confirms DP2's discriminator**: a `-p` fork is exactly the `sdk-cli` shape the reconcile keys on, so the fork is discriminable from an attached interactive session by the field E35 already uses |
| `forkedFrom` | **does not exist** | So `AskResult.from_fork_of` is **Shepherd's own `parent_session_id`**, written at row creation, and **never** read back from the transcript. A field invented to hold it would be a shape asserted from memory (K1) |

The last two rows are the ones that change code: the parent link is ours to record, and the
`entrypoint` rewrite is why T21's reconcile and T15's pre-registration do not fight each other.

### ADR-M3-8: the tmux blast-radius invariant is enforced at runtime, on the argv, at one exec site

**Context.** M3 is the milestone with §18's incident behind it: on 2026-09-12 a bare
`tmux kill-server` destroyed three live sessions including the one that issued it. ADR-M3-2 made K6
three AST rules. **Two independent reviews found all three are spellings, not properties.** Each
falls to one line — `["tm" + "ux", …]`, `f"kill-{verb}"`, or `from .tmux_cmd import TMUX_BIN`, which
produces an argv with **no `-L`** and therefore resolves to `$TMUX`, which is exactly CLAUDE.md
rule 3's scenario and exactly the incident's blast radius. `tests/boundaries/_taint.py:5-9` is in this
repo because two shipped rules died this way, and its docstring is the finding: *"a rule about a
value has to follow the value."*

**Decision.** The invariant moves to **runtime**, into the callable
`runner/local.py::make_run_argv(permitted)` returns — the one place in `src/` a tmux process is
started, and the one place the **actual argv** is visible.

```python
# runner/tmux_cmd.py — pure, no process module, no os
VERSION_ARGV: tuple[str, ...] = ("tmux", "-V")          # contacts no server
FORBIDDEN_SOCKET = "shepherd"                            # the user's; never permitted
THROWAWAY_SOCKET_RE = r"^shepherd-m3-[A-Za-z0-9_-]+$"
TARGET_RE = r"^=[A-Za-z0-9_-]+:$"

def check_tmux_argv(argv: list[str], *, permitted: frozenset[str]) -> None:
    """Refuse — never repair. Raises RunnerRefusal naming CLAUDE.md and §18."""
```

Five refusals, in order: (1) not a tmux argv → return, not our business; (2) `tuple(argv) ==
VERSION_ARGV` → allow, by **list equality, never prefix**; (3) `argv[0:2] != ["tmux", "-L"]` → refuse;
(4) `argv[2] not in permitted` (and `permitted` never contains `shepherd`, asserted when it is built)
→ refuse; (5) any element following a `-t` not matching `TARGET_RE` → refuse; (6) `"kill-server" in
argv` and `argv[2]` not matching `THROWAWAY_SOCKET_RE` → refuse.

The exec callable is built by `make_run_argv(permitted: frozenset[str]) -> RunArgv`, so the permitted
set is an explicit construction-time argument rather than a module global; `compose.py` (T23) builds
it from the configured socket, and the probe/live harnesses build it from their own. **There is no
module-level default instance**, because a default would fix the permitted set at import and make the
configured socket (D49, RD1) a lie.

**Why refuse and never repair.** ADR-M3-2 already rejected "a wrapper that *appends* `-L` if missing"
for the right reason: it hides the bug instead of failing on it. A repair also cannot know *which*
socket was intended, so it would have to guess — and a wrong guess here is the incident.

**Rejected alternatives.** *Keep AST rules only* — defeated by three one-liners, demonstrated by three
fixtures. *A `subprocess` wrapper module every caller must import* — unenforceable without an AST rule,
so it inherits the same defect one level up. *Refuse in `tmux_argv`* — correct but insufficient: the
whole failure mode is an argv that **did not come from `tmux_argv`**.

**Consequences.** The AST rules stay, cheap and fast, as a second net that catches the honest mistake
at edit time; the runtime check catches the dishonest one at exec time. **Two of the three indirection
fixtures are expected to pass the AST rules and be refused at runtime**, and a test asserts exactly
that asymmetry — which is the only way to prove the two nets are catching different things. The cost
is one function call per tmux invocation and one more refusal path to render; `RunnerRefusal` already
exists for it (T2).

---

## Task list

**Notation.** Each task names its `data-schemas.md` sections. Validation levels per
`cc10x:verification`. **Every task inherits K1–K17**; the `Out-of-Scope Drift` line names only what is
specifically tempting *here*. Every `Required Checks` line states **what would make the check go red**
(K17). The toolchain is `/root/Shepherd/.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/mypy` —
**there is no `python` on `PATH`**.

**Step 0, before Task 1 and before any code:** run
`.venv/bin/python docs/probes/drift_check.py --record <data_dir>/drift.json` (M1's T17-2 made this a
gate `doctor` reads) and record the result in **Progress notes** (G-M3-7). A moved enum value is a
blocker entry, not an assumption.

**Step 0b, immediately after.** Six rows. **Three ASSERT (a mismatch is a blocker entry before T1)
and three RECORD (write down what you see).** The split exists because M2's plan was invalidated
twice mid-write by a concurrent lane: only facts a task's *design* depends on are asserted.

| # | Command | Kind | Expected / note |
|---|---|---|---|
| 1 | `tmux -L shepherd ls` | **ASSERT** | The user's live sessions are there (`aivisor`, `main`, `spike` at the time of writing). **Read-only. Do not touch this socket again for the rest of the milestone.** If it is empty, K6 still stands — the rule is not conditional on the sessions being up today |
| 2 | `wc -l src/shepherd/store/db.py` | **ASSERT** | **599**, cap 600. If it has grown, someone else is in `db.py` and ADR-M3-6's split is urgent rather than merely right |
| 3 | `grep -n 'shepherd.runner\|shepherd.orchestration' tests/boundaries/_imports.py` | **ASSERT** | Both present in `LAYER_OF` (L2, L3) and `FORBIDDEN_BELOW_L4`. Zero hits means the boundary rules will not govern M3's new packages and T5/T13's design is wrong |
| 4 | `wc -l src/shepherd/daemons/controld.py src/shepherd/toolsurface/compose.py` | **RECORD** | Measured 140 and 119. **Any number is fine to find; write it down.** What T23 owes is *headroom*, not a count |
| 5 | `.venv/bin/pytest -m "not live" -q \| tail -3` and `.venv/bin/mypy --strict src/shepherd \| tail -1` | **RECORD** | Measured **869 passed, 1 skipped, 13 deselected**; mypy clean over **79** files. **If it is red for a reason M3 does not own, that is a blocker entry before T1** |
| 6 | `claude --version` and `tmux -V` | **RECORD** | Measured `2.1.273` and `3.4`; `data-schemas.md` pins shapes to `2.1.270`. Feeds G-M3-7 and T10's `--help` assertions |

---

### Task 1: the four probes M3 still needs (P1–P4)

**Objective:** close the four `§Not verified` items M3's own design depends on — **before** any code
reads them — and leave the captures in the repo the way the 2026-09-14 suite did. **§18's tmux spike
is already done** (five capture folders, probe hygiene recorded, teardown verified); this task adds
nothing it covered.

**Files/Surfaces:**
- `docs/probes/2026-09-17-m3-tmux/probe_m3.py` — new (copies `tmux-tui/probe_tui.py`'s harness)
- `docs/probes/2026-09-17-m3-tmux/FINDINGS.md` — new, in `data-schemas.md`'s entry shape
  (Produced by · Consumed by · Probe · Status · Real example · field table · Variants · Spec alignment)
- `docs/probes/2026-09-17-m3-tmux/<name>-<UTC>/` — capture folders, one per probe

**Dependencies:** step 0, step 0b.

**Allowed Scope:** the four probes below and their captures.

**Every socket P1–P4 need, named here rather than improvised** (revision 2 — revision 1 named one and
P3 needs two; the 2026-09-14 attach probe used three):

| Socket | Used by | Why |
|---|---|---|
| `shepherd-m3-probe` | P1, P2, P4 | the TUI under test |
| `shepherd-m3-outer` | P3 | the **outer** throwaway pane from which the second client attaches — the shape `gap-fill/tmux-attach-keys-…` used, because an `attach` must run from inside a pane and that pane must not be on the socket being attached to |
| `shepherd-m3-inner` | P3 | the **inner** server holding the TUI the second client attaches to |

All three match `^shepherd-m3-`, so `check_tmux_argv` (ADR-M3-8) permits their teardown
`kill-server` and refuses every other socket's. **`-L` on every invocation, teardown included.** Never
`shepherd`. Never `shepherd-runner`.

**The harness this task copies is not fit to reuse unchanged, and the two defects are named.**
`docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py` is the reference, and: (i) **line 136 runs a
bare `tmux -V` with no `-L`** — verified by reading it — which is CLAUDE.md rule 3's forbidden form
even though `-V` contacts no server; (ii) **lines 392-395 tear down with `kill-server` on socket
`shepherd-probe`**, which does not match `^shepherd-m3-` and which K6 now permits only on a throwaway.
**Both must be fixed in the copy before the copy runs** — `tmux -V` becomes the exact
`VERSION_ARGV` form `check_tmux_argv` allows, and `SOCK` becomes one of the three above. **The
original is frozen evidence and is not edited**: its captures are what M3 reads, and re-running it
would invalidate them. `docs/probes/**/*.py` comes into T5's scan scope this milestone, and the scope
clause that keeps the frozen folders out of the `kill-server` rule is stated and checked in T5.

Also: the server started under `env -i` so panes inherit no `$TMUX` or `CLAUDECODE`; a throwaway
`mktemp` working directory and an explicit `--settings` per run; `claude-haiku-4-5`; a timeout on
every run; `versions.txt` per folder; and a `teardown.txt` per folder proving `no server running` on
the socket it used.

| Probe | Question | Why M3 cannot proceed without it | §Not verified line |
|---|---|---|---|
| **P1** *(narrowed in revision 2)* | **`C-u` is already captured and it works** — `gap-fill/keys-claude-20260914T180105Z/steps.log` l.6–7 (`Up` recalls history into a non-empty box, then `C-u`), `01-after-raw-up.txt` (box holds `FIRST-PROMPT-FOR-HISTORY`) → **`01b-after-ctrl-u.txt` (box empty, `Ctrl+Y to paste deleted text`)**, `results.json: raw_up_recalls_history: true`. So P1 probes only what is **untried**: `C-a C-k`, `C-w`×N, and **`C-u` against the post-`Esc` restored prompt**, which may be a different widget from a history recall. Capture `-e` before and after each | **DP10 / D45.** The clearing form **ships now** on the `C-u` evidence, guarded by a post-`C-u` pane re-read; P1 only tells us whether the post-`Esc` case needs the guard's fallback. **This probe no longer gates T13 or T14** | §Key semantics has no `C-u` row — but the capture folder beside it does, which is why revision 1 re-probed a question the repo had answered |
| **P2** | Does `--resume <id> --fork-session` accept `--session-id <uuid>`? Does `--no-session-persistence` apply with `-p` in that combination, and is a transcript left? **And:** re-confirm at `2.1.273` that the result object still carries `session_id` (captured at `2.1.270` in `headless-20260914T160308Z/h5_fork.stdout.json`), then **append the result-JSON field table to `data-schemas.md` §Fork** so K1 is satisfied in the document and not only in a capture folder | **DP7 / DP2.** `ask()`'s pre-registration and its no-residue claim. The **fallback** depends on the result JSON, not on the sidecar — `registry.py:3-5` says the engine deletes the sidecar on exit, and T15 never polls in time | "`--resume` (without fork) of a session live in another process; `--fork-session` combined with `--session-id`: not attempted" |
| **P3** | With a browser-equivalent writer sending `send-keys -H` and a second client attached and typing, do the two interleave cleanly? Run the second client as `env -u TMUX tmux -L <inner> attach` from an outer throwaway pane, exactly as the 2026-09-14 attach probe did | **DP9 / D40.** A human at `[tmux attach]` beside a live browser terminal is the normal case, not an edge one | "Second tmux client typing at the same time as browser writes: only size interaction, read-only attach and byte delivery were tested" |
| **P4** | At a permission dialog: what does `1` / `2` / `3` do, what does `Esc` do, what does `Tab` do? | **DP8 / D44.** `answer_permission`'s `deny` has no captured mechanism, and guessing one that lands on `1. Yes` approves a tool the human never saw | "text starting with a digit typed into a permission dialog: only Enter, Down and letters were sent" |

**Named and deliberately NOT run:** **P5** — `/rename` against a session live in another process
(**G-M3-5**): the 2026-09-14 prober declined it because it *"risks two writers on one transcript"*,
and DP1's recommendation keeps `can_set_title = False` for attached sessions on exactly that
evidence. **P6** — xterm.js rendering (**G-M3-6**): not probeable on this host, and no amount of
effort changes that.

**Out-of-Scope Drift:** re-probing anything the 2026-09-14 folders already cover (trust dialog,
hooks, idle/permission, send-keys, resize, `/rename`, `/compact`, fork, `/exit`, SIGTERM,
`kill-session`, `--name`/`--session-id` at spawn, `capture-pane -S -2000`, `pipe-pane`, ghost text,
headless parity, **and `C-u` clearing the input line after a history recall — `01b-after-ctrl-u.txt`,
which revision 1 re-probed**). **Before adding a probe question, grep the capture folders, not just
`data-schemas.md` §Key semantics** — the omission that cost revision 1 a probe was a missing *row* in
the summary, not a missing *capture*. Probing `claude` behaviour M3 does not call. Touching the
`shepherd` socket. **Editing any pre-2026-09-17 probe script** (frozen evidence; fix the copy).

**Expected Artifacts:** four capture folders, one `FINDINGS.md` whose every fenced example is a byte
substring of a capture file, and four rows appended to this plan's **Progress notes**.

**Required Checks:**
`test_m3_probe_captures_exist` (each of the four folders is present with a `versions.txt` and a
`teardown.txt`) — **goes red** if a folder is missing or a teardown does not say `no server running`;
`test_findings_cite_real_capture_paths` — **goes red** if a path named in `FINDINGS.md` does not
exist, which is the check that stops a finding from being written from memory.
**Checkpoint Type:** human_verify — a human reads `FINDINGS.md` and the teardown files before T15 and
T16 consume them. **(T13 no longer waits on P1: `C-u` is captured, and the clearing form ships with a
re-read guard.)**
**Validation Level:** **Live.** `.venv/bin/python docs/probes/2026-09-17-m3-tmux/probe_m3.py`.
**Exit Criteria:** four folders captured; `FINDINGS.md` written in the entry shape; **each of
`shepherd-m3-probe`, `shepherd-m3-outer`, `shepherd-m3-inner` reports no server** (`tmux -L <s> ls`);
`tmux -L shepherd ls` still reports the user's sessions, unchanged; the real
`~/.claude/settings.json` sha256 still `375e5322…`; **the copied harness's bare `tmux -V` and its
socket name were fixed before the first run, and the diff against `probe_tui.py` is in
Progress notes**; P2's result-JSON field table appended to `data-schemas.md` §Fork.
**Test Seams:** live (probe harness).

**Consumes:** none.
**Produces:**
```
docs/probes/2026-09-17-m3-tmux/FINDINGS.md
  P1 → C-a C-k / C-w, and whether C-u clears the post-Esc restored prompt
       (C-u after a history recall is NOT re-probed: 01b-after-ctrl-u.txt)
  P2 → does --fork-session accept --session-id; is a transcript left;
       does the result object still carry session_id at 2.1.273
  P3 → concurrent-client interleaving (sockets: -outer drives, -inner is attached)
  P4 → permission-dialog key semantics for 1/2/3/Esc/Tab
docs/specs/data-schemas.md §Fork  ← the result-JSON field table (K1)
```

---

### Task 2: `core/runner.py` — the runner and engine vocabulary

**Objective:** one L1 module holding every type `runner/`, `orchestration/`, `engines/`, `store/`,
`toolsurface/` and `web/` speak in, so none of them defines a second copy (M1's F9/BLOCKER-T7b-1
lesson: two structurally identical types is a split `mypy` only catches where they meet).

**Files/Surfaces:**
- `src/shepherd/core/runner.py` — new
- `src/shepherd/core/anomalies.py` — **M3's seven members, appended at the end** (see below)
- `tests/test_core_runner.py` — new
- `tests/test_core_types.py` — extended for the new members

**Dependencies:** none (after step 0b). Runnable from day 1, beside T1.

**Allowed Scope:** types, enums, frozen dataclasses, constant tables. No logic, no I/O, no import
above L1, no import of `shepherd.runner` or `shepherd.engines`.

**M3's anomaly members — real `AnomalyKind` values, in `core/anomalies.py`, appended at the end.**
Revision 1 declared three of these as bare `str` constants inside `orchestration/` modules
(`KILL_WITHOUT_SESSION_END` in T12, `MAILBOX_INPUT_NOT_EMPTY` in T14, `ASK_FORK_RESIDUE` in T15), and
**no task listed `core/anomalies.py` at all**. That does not work: `AnomalyKind` is a closed `StrEnum`
documented **append-only**, and `toolsurface/tools_m1.py:239-240` renders
`{str(kind.value): 0 for kind in AnomalyKind} | store.list_anomaly_counts()` — **the enum is what
supplies the zero rows**. A bare `str` is counted only after it first fires and is never displayed as
`0`, which is exactly the state principle 5 (K9) forbids, while **P-M3-9 claimed the principle was
met**. `Store.bump_anomaly(kind: str)` accepts anything, so nothing would have failed; it would simply
have been untrue.

| Member | Counted when | Owner |
|---|---|---|
| `KILL_WITHOUT_SESSION_END` | `kill-session` was recorded and no `SessionEnd` followed (G-M3-9) | T12 |
| `MAILBOX_INPUT_NOT_EMPTY` | delivery deferred because the input line was non-empty **after** the `C-u` re-read (DP10) | T14 |
| `ASK_FORK_RESIDUE` | P2 says a fork transcript is left; it is named, never deleted (DP7, K3) | T15 |
| `ORPHANED_PANE` | a `shepherd_<ulid>` pane exists on the socket with no row, or with a handle-less row the reconcile could not rebind (see T12's reconcile) | T12 |
| `PANE_UNREADABLE` | the capture could not be classified: **empty capture** *or* **non-UTF-8 bytes**. One member, three detail strings — the shape `TRANSCRIPT_TAIL_ABSENT` already uses ("Three absences, one count, each with its own detail string") | T6 |
| `SIDECAR_ABSENT` | the dialog gate wanted the sidecar and it was not there — which is the **normal** state during the trust dialog (DP8) | T13/T16 |
| `TMUX_UNAVAILABLE` | Shepherd cannot reach its panes: **no server on the socket** *or* **`tmux` not on `PATH`**. One member, two detail strings — they mean the same thing to a reader | T8 |

**The six degraded conditions P-M3-9 names, mapped explicitly, including the one that is not an
anomaly:** absent sidecar → `SIDECAR_ABSENT`; empty capture → `PANE_UNREADABLE`; non-UTF-8 →
`PANE_UNREADABLE`; missing server → `TMUX_UNAVAILABLE`; `tmux` absent → `TMUX_UNAVAILABLE`; **a dead
pane → no anomaly at all** — `DEAD` is a real classification carrying a real `pane_dead_status`
(E-M3-16), and counting a knowable outcome as an unknown is the opposite of principle 5.

**Every "counts an anomaly" claim elsewhere in this plan names its member**, and
`test_every_anomaly_claim_names_a_member` (T2) asserts that the members M3's modules reference all
exist in the enum.

**M2's `AnomalyKind` ordering blocker (T3-2/T4-1) stays deferred and is not reopened.** M3 appends;
it does not reorder. `tests/boundaries/fixtures/events_module_reordered.py` already guards the
adjacent case and is untouched.

**Out-of-Scope Drift:** writing the write-policy **table** here (T13 — this module holds the enums it
is total over). Putting a tmux word in a member value (tmux vocabulary lives in `runner/`). Adding
`Runner` itself (T5 — a `Protocol` in `core/` would make L1 depend on L2's shape).

**Contents, exactly:**

| Symbol | Members / fields | Notes |
|---|---|---|
| `PaneKind(StrEnum)` | `TRUST_DIALOG`, `PERMISSION_DIALOG`, `PROMPT_READY`, `BUSY`, `DEAD`, `UNREADABLE` | Six, because the six are the six the captures show. `UNREADABLE` is principle 5 on the screen |
| `WriteDecision(StrEnum)` | `SEND_NOW`, `CLEAR_THEN_SEND`, `QUEUE`, `REFUSE_DIALOG`, `REFUSE_NO_PTY`, `REFUSE_INPUT_NOT_EMPTY` | ADR-M3-5. **Six** — three named refusals, because a UI renders them differently, plus `CLEAR_THEN_SEND` (revision 2: `C-u` is capture-proven, `01b-after-ctrl-u.txt`, so D45's clearing step ships rather than being deferred). `WriteDecision` is the **value** space and is not part of the totality key |
| `RunnerHandle` | `runner: str`, `socket: str`, `session_name: str` | frozen. `to_text()`/`from_text()` round-trip for `session.runner_handle`; the separator is `|`, which no field may contain — asserted |
| `ProcState` | `alive: bool`, `pid: int \| None`, `exit_code: int \| None`, `exit_signal: int \| None`, `observed_at: str` | frozen. `exit_signal` stays `None` on this evidence: `#{pane_dead_signal}` was **empty even after SIGTERM** |
| `PaneFields` | `alternate_on: bool`, `pane_dead: bool`, `pane_dead_status: int \| None`, `pane_title: str \| None`, `width: int`, `height: int`, `pane_pid: int \| None` | frozen. Exactly the `list-sessions -F` fields the capture prints, in that order |
| `PaneState` | `kind: PaneKind`, `fields: PaneFields`, `input_text: str`, `ghost_text: str \| None`, `dialog_text: str \| None` | frozen. `input_text` is **draft text only**; ghost text is separate by construction (E-M3-5) |
| `SessionSpec` | `session_id: str`, `engine_session_id: str`, `cwd: str`, `brief: str \| None`, `title: str \| None`, `model: str \| None`, `effort: str \| None`, `engine: str`, `runner: str`, `env: Mapping[str, str]` | frozen. §6's "a session is (engine, provider, credential, runner, project, task)", narrowed to what M3 resolves |
| `EngineCapabilities` | `can_spawn: bool`, `can_steer: bool`, `can_fork: bool`, `can_set_title: bool`, `has_hooks: bool`, `effort_ladder: tuple[str, ...]`, `transcript_format: Literal["jsonl","sqlite","none"]` | §6 verbatim, with `list` → `tuple` for frozenness. **`can_spawn` is the tmux-absent degrade** (D-5) |
| `TerminalFrame` | `kind: Literal["snapshot","live","closed"]`, `data: bytes`, `reason: str \| None` | frozen. A `closed` frame always carries a reason (E-M3-29) |
| `RunnerRefusal(Exception)` | `reason: str` | The one refusal type the runner raises upward; every entry point converts a failure into it or into a counted degrade |
| `SPAWN_POLL_INTERVAL_S` / `SPAWN_TIMEOUT_S` | `0.25` / `60.0` | §8 line 940's own number for the second |
| `MAX_SESSION_DEPTH` / `MAX_CHILDREN_PER_SESSION` / `MAX_TOTAL_OWNED_SESSIONS` | `3` / `5` / `20` | §11 verbatim |
| `TMUX_COMMAND_LIMIT_B` | `16324` | The **measured** largest accepted argv word, not a round number |

**Expected Artifacts:** one module, ≤ 250 lines, no logic.
**Required Checks:**
`test_pane_kind_has_six_members` — **goes red** if a kind is added without T13's key set growing by
16 (2 × 2 × 4); `test_write_decision_has_six_members` — **goes red** if a decision is added with no
key mapping to it, which is a value nothing can return;
`test_runner_handle_round_trips` over 1 000 generated handles, including one whose session name
contains the separator, which must **raise** — **goes red** if `to_text` ever produces an ambiguous
string;
`test_no_tmux_word_appears_in_core` (AST literals: none of `tmux`, `send-keys`, `capture-pane`,
`-L`) — **goes red** the moment runner vocabulary leaks down a layer;
`test_caps_match_the_spec_numbers` (3/5/20, 16324, 60.0) — **goes red** if a constant drifts from §11;
`test_m3_anomaly_members_are_appended_at_the_end` — asserts the seven are the **last** seven of
`AnomalyKind` and that every pre-existing member keeps its position; **goes red** on a reorder, which
is M2's deferred T3-2/T4-1 and must not be reopened here;
`test_every_anomaly_claim_names_a_member` — every anomaly constant referenced from `runner/` or
`orchestration/` resolves to an `AnomalyKind` member; **goes red** on a bare `str` kind, which
`bump_anomaly(kind: str)` would accept silently and `doctor` would never show as `0`;
inherited `test_core_purity` — **goes red** if this module imports above L1.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/test_core_runner.py tests/boundaries -q && .venv/bin/mypy --strict src/shepherd`.
**Exit Criteria:** all checks pass; `mypy --strict` clean; 23 boundary tests green with **no new
exemption**; file under 600 lines.
**Test Seams:** unit.

**Consumes:** none.
**Produces:**
```python
class PaneKind(StrEnum): TRUST_DIALOG PERMISSION_DIALOG PROMPT_READY BUSY DEAD UNREADABLE
class WriteDecision(StrEnum): SEND_NOW CLEAR_THEN_SEND QUEUE REFUSE_DIALOG REFUSE_NO_PTY REFUSE_INPUT_NOT_EMPTY
@dataclass(frozen=True) class RunnerHandle: runner: str; socket: str; session_name: str
    def to_text(self) -> str: ...
    @classmethod
    def from_text(cls, text: str) -> RunnerHandle: ...
@dataclass(frozen=True) class ProcState: alive: bool; pid: int | None; exit_code: int | None; exit_signal: int | None; observed_at: str
@dataclass(frozen=True) class PaneFields: alternate_on: bool; pane_dead: bool; pane_dead_status: int | None; pane_title: str | None; width: int; height: int; pane_pid: int | None
@dataclass(frozen=True) class PaneState: kind: PaneKind; fields: PaneFields; input_text: str; ghost_text: str | None; dialog_text: str | None
@dataclass(frozen=True) class SessionSpec: session_id: str; engine_session_id: str; cwd: str; brief: str | None; title: str | None; model: str | None; effort: str | None; engine: str; runner: str; env: Mapping[str, str]
@dataclass(frozen=True) class EngineCapabilities: can_spawn: bool; can_steer: bool; can_fork: bool; can_set_title: bool; has_hooks: bool; effort_ladder: tuple[str, ...]; transcript_format: Literal["jsonl", "sqlite", "none"]
@dataclass(frozen=True) class TerminalFrame: kind: Literal["snapshot", "live", "closed"]; data: bytes; reason: str | None
class RunnerRefusal(Exception): ...
SPAWN_POLL_INTERVAL_S: float; SPAWN_TIMEOUT_S: float
MAX_SESSION_DEPTH: int; MAX_CHILDREN_PER_SESSION: int; MAX_TOTAL_OWNED_SESSIONS: int
    # MAX_TOTAL_OWNED_SESSIONS counts PANES, not rows — see T11 and T12's reconcile
TMUX_COMMAND_LIMIT_B: int

# core/anomalies.py — appended at the end of AnomalyKind, in this order
class AnomalyKind(StrEnum):   # ... the 22 shipped members, unmoved ...
    KILL_WITHOUT_SESSION_END = "kill_without_session_end"
    MAILBOX_INPUT_NOT_EMPTY  = "mailbox_input_not_empty"
    ASK_FORK_RESIDUE         = "ask_fork_residue"
    ORPHANED_PANE            = "orphaned_pane"
    PANE_UNREADABLE          = "pane_unreadable"
    SIDECAR_ABSENT           = "sidecar_absent"
    TMUX_UNAVAILABLE         = "tmux_unavailable"
```

---

### Task 3: `core/mailbox.py` and migration 003

**Objective:** give a queued message a place to live that survives a `controld` restart (**DP3**), and
give the mailbox its vocabulary.

**Files/Surfaces:**
- `src/shepherd/core/mailbox.py` — new
- `src/shepherd/store/migrations/003_m3_mailbox.sql` — new
- `src/shepherd/store/migrate.py` — `EXPECTED_SCHEMA_VERSION` 2 → 3 (one line)
- `tests/test_core_mailbox.py`, `tests/store/test_migration_003.py` — new

**Dependencies:** none. Track A, runnable from day 1.

**Allowed Scope:** one table, one enum, two frozen dataclasses, and the version bump. §7's three
migration rules apply and are already implemented.

**Out-of-Scope Drift:** a `channel_message` table (M6 — D12 says channels have no delivery code of
their own, so the transport alone is complete). Any `session` column (001 already has every one M3
needs). Editing 001 or 002 (forward-only; ADR-M2-4).

**Schema, exactly:**
```sql
CREATE TABLE mailbox_message (
  id               TEXT PRIMARY KEY,                         -- ulid
  owner_id         TEXT NOT NULL DEFAULT 'local',
  session_id       TEXT NOT NULL REFERENCES session(id),
  idempotency_key  TEXT NOT NULL,
  body             TEXT NOT NULL,
  origin           TEXT NOT NULL CHECK (origin IN
                     ('orchestrator','queue_worker','user_ui','session','external')),
  queued_at        TEXT NOT NULL,
  delivered_at     TEXT,
  delivery_attempts INTEGER NOT NULL DEFAULT 0,
  last_refusal     TEXT                                      -- the WriteDecision that deferred it
);
CREATE UNIQUE INDEX ux_mailbox_idem ON mailbox_message(session_id, idempotency_key);
CREATE        INDEX ix_mailbox_pending ON mailbox_message(session_id, delivered_at);
```
`last_refusal` is what makes principle 5 true of the write path: a message that keeps deferring says
**why**, on the row, and `doctor` counts them.

**Expected Artifacts:** one SQL file, one ≤ 80-line module, one version bump.
**Required Checks:**
`test_003_applies_over_002` against a database built by 001+002 with rows in it — **goes red** if any
existing row, index or default changes;
`test_checksum_mismatch_refuses_to_start` and `test_future_schema_refuses_to_start` re-run at version
3 — **go red** if the rules regressed;
`test_a_duplicate_idempotency_key_is_rejected_by_the_index` (an `INSERT` that must raise) — **goes
red** if the unique index is dropped or its columns reordered;
`test_migrate_expected_version_matches_the_highest_file` — **goes red** if a file is added without the
bump, which is the failure mode that leaves `sessiond` waiting forever (§7 rule 3).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/test_core_mailbox.py tests/store -q`.
**Exit Criteria:** all checks pass; `mypy --strict` clean; the full suite green.
**Test Seams:** unit, plus the store's real-SQLite verb seam.

**Consumes:** none.
**Produces:**
```python
class MailboxOrigin(StrEnum): ORCHESTRATOR QUEUE_WORKER USER_UI SESSION EXTERNAL
@dataclass(frozen=True) class MailboxMessage:
    id: str; session_id: str; idempotency_key: str; body: str
    origin: MailboxOrigin; queued_at: str; delivered_at: str | None
    delivery_attempts: int; last_refusal: str | None
@dataclass(frozen=True) class MailboxCounts: pending: int; delivered: int; deferred: int
MAILBOX_TABLE: str                      # "mailbox_message"
COALESCE_BULLET: str                    # "- "
EXPECTED_SCHEMA_VERSION = 3             # store/migrate.py
```

---

### Task 4: `store/sessions.py` and `store/mailbox.py` — the verbs

**Objective:** every SQL statement M3 needs, behind D33 verbs returning dataclasses, in **new
modules** — because `db.py` is at 599 of 600 lines (ADR-M3-6).

**Files/Surfaces:**
- `src/shepherd/store/sessions.py` — new
- `src/shepherd/store/mailbox.py` — new
- `src/shepherd/store/db.py` — **delegating methods only**; if this file needs more than ~15 lines,
  the split is wrong
- `src/shepherd/store/models.py` — `Session` and `FleetRow` gain `runner_handle`, `title_synced_at`,
  `parent_session_id`, `depth` (columns that already exist and are not yet projected)
- `tests/store/test_session_verbs.py`, `tests/store/test_mailbox_verbs.py` — new

**Dependencies:** T2, T3.

**Allowed Scope:** the verbs listed under *Produces*. Transactions stay inside (D33 rule 3); no caller
passes SQL or receives a driver row.

**Out-of-Scope Drift:** a `Store` Protocol (D33's trigger has not fired). A second writer for the stop
columns (`apply_stop_verdict` holds the only one — M2 asserts it). Reaching into `db.py`'s internals
rather than taking the connection it hands over (ADR-7).

**Expected Artifacts:** two modules, each ≤ 250 lines.
**Required Checks:**
`test_create_owned_session_sets_ownership_origin_and_handle` — **goes red** if a default silently
makes an owned row attached;
`test_create_owned_session_is_idempotent_on_engine_session_id` — **goes red** if the pre-registration
race (C-M3-7) can produce two rows;
`test_an_owned_spawn_never_creates_an_unbound_row` — `engine_session_id=None` is accepted **only**
with `origin=ask_fork`; **goes red** if a spawn can create an unbound row, which would reopen the
duplicate-row hole `--session-id` exists to close;
`test_an_unbound_ask_fork_row_is_bindable_exactly_once` — **goes red** if `rebind_engine_session_id`
can overwrite an already-bound id, which would silently repoint a live row;
`test_rebind_moves_the_engine_session_id_and_keeps_the_row` (C14) — **goes red** if a rebind is
implemented as delete-and-insert, which would lose the stop history;
`test_apply_title_ratchets_and_never_reverts` over all nine `(prior, incoming)` source pairs — **goes
red** if `engine` ever overwrites `user`;
`test_title_synced_at_is_only_set_with_a_confirmation` — **goes red** if any path can stamp it from a
send rather than from a read-back;
`test_enqueue_is_idempotent`, `test_deliver_marks_every_row_in_one_transaction`,
`test_pending_for_excludes_delivered` — the last **goes red** if a delivered row can be re-sent after
a restart;
inherited `test_storage_boundary` and `test_no_source_file_exceeds_600_lines` — the latter **goes
red** if the work lands in `db.py` after all.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/store -q`.
**Exit Criteria:** all checks pass; `db.py` still ≤ 600; `mypy --strict` clean; full suite green.
**Test Seams:** the store's existing real-SQLite verb seam (`tmp_path`), not a new one.

**Consumes:**
```python
from shepherd.core.runner import RunnerHandle, SessionSpec          # T2
from shepherd.core.mailbox import MailboxMessage, MailboxOrigin, MailboxCounts   # T3
from shepherd.core.states import Origin, Ownership, TitleSource, TITLE_SOURCE_RANK  # shipped
from shepherd.store.db import Store                                  # shipped
```
**Produces:**
```python
# store/sessions.py
def create_owned_session(connection, *, session_id: str, engine_session_id: str | None,
                         # `None` is the ask-fork branch only: if P2 says --fork-session refuses
                         # --session-id, the fork's id is not knowable until the -p run returns
                         # (A25), so the row is created unbound and bound by rebind_engine_session_id.
                         # A spawn ALWAYS passes a uuid (C-M3-7). A test asserts that.
                         workspace_id: str, repo_id: str | None, cwd: str, started_at: str,
                         origin: Origin, parent_session_id: str | None, depth: int,
                         ephemeral: bool, title: str | None, title_source: TitleSource,
                         handle: RunnerHandle | None, model: str | None, effort: str | None) -> Session: ...
def set_runner_handle(connection, session_id: str, handle: RunnerHandle) -> None: ...
def rebind_engine_session_id(connection, session_id: str, engine_session_id: str) -> None: ...
def apply_title(connection, session_id: str, title: str, source: TitleSource) -> Session: ...
def set_title_synced_at(connection, session_id: str, synced_at: str) -> None: ...
def set_ephemeral(connection, session_id: str, ephemeral: bool) -> None: ...
def owned_session_counts(connection) -> tuple[int, int]: ...        # (total_owned_alive, ...)
def children_of(connection, session_id: str) -> int: ...
# store/mailbox.py
def enqueue(connection, message: MailboxMessage) -> MailboxMessage: ...
def pending_for(connection, session_id: str) -> list[MailboxMessage]: ...
def sessions_with_pending(connection) -> list[str]: ...
def mark_delivered(connection, ids: tuple[str, ...], delivered_at: str) -> int: ...
def record_refusal(connection, ids: tuple[str, ...], refusal: str) -> None: ...
def mailbox_counts(connection) -> MailboxCounts: ...
# Store (db.py) gains thin delegations with the same names.
```

---

### Task 5: `runner/base.py` and `runner/tmux_cmd.py` — the seam and K6 made mechanical

**Objective:** declare the `Runner` Protocol (§6, D36) and put **every** tmux argv list in the
codebase behind one pure builder, so K6 is a property the build checks rather than a habit
(ADR-M3-2, K16).

**Files/Surfaces:**
- `src/shepherd/runner/__init__.py`, `src/shepherd/runner/base.py`, `src/shepherd/runner/tmux_cmd.py` — new
- `tests/runner/__init__.py`, `tests/runner/test_tmux_cmd.py`, `tests/runner/test_tmux_guard.py` — new
- `tests/boundaries/test_tmux_blast_radius.py` — new
- `tests/boundaries/test_engine_config_is_read_only.py` — new (P-M3-14's tree-wide write scan)
- `tests/boundaries/fixtures/runner_bare_tmux_call.py`, `.../runner_kill_server.py`,
  `.../runner_loose_target.py` — new fixtures, each a **real** violation
- `tests/boundaries/fixtures/runner_tmux_via_constant_import.py`,
  `.../runner_tmux_via_fstring.py`, `.../runner_kill_server_via_fstring.py` — new **indirection**
  fixtures, one per rule, the shape `cli_platform_alias_import.py` /
  `cli_platform_module_alias.py` / `cli_platform_from_import.py` already ships
- `tests/boundaries/fixtures/src_writes_under_claude_home.py` — new
- `tests/e2e/test_live_attached_session.py` — `test_no_tmux_is_invoked_at_all` **removed here**,
  because its replacement lands in `tests/boundaries/` (T24 adds the narrower live second check)

**Dependencies:** T2.

**Allowed Scope:** the Protocol, the argv builder, the session-name function, the target function,
**`check_tmux_argv` (pure — ADR-M3-8's predicate, which T8's exec callable calls)**, and the
boundary rules below. **Pure** — `tmux_cmd.py` imports no process module and no `os`.

**Out-of-Scope Drift:** running a command here (T8 — this task supplies the *predicate*, T8 supplies
the *exec site*). A convenience that *appends* `-L` when missing — it would hide the defect the rule
exists to surface, and ADR-M3-8 refuses rather than repairs for the same reason. Adding a rule that
names one file, or one directory (M2's acceptance clause 2: a scan whose stated scope exceeded its
real scope by 75 files; revision 1 of **this** plan repeated it with `glob("*.py")` in one directory).

**The scan scope, stated exactly, because a scope that is implied is a scope that is wrong.**

| Rule | Walks | Why that scope |
|---|---|---|
| socket present, never `shepherd` | `src/**/*.py`, `tests/**/*.py`, `docs/probes/**/*.py` — recursive | the blast radius is the same wherever the argv is written. **The shipped tree is green under this clause**, checked: `probe_tui.py` uses `shepherd-probe`, every `gap-fill/probe_*.py` uses `shp-gap-*`, and the one bare tmux call in the tree (`probe_tui.py:136`, `tmux -V`) is the `VERSION_ARGV` form the predicate allows by list equality |
| one builder (`"tmux"` in exactly one module) | `src/**/*.py` | tests and probes legitimately spell tmux; production may not |
| `kill-server` on a throwaway socket only | `src/**/*.py`, `tests/**/*.py`, and `docs/probes/` folders dated **2026-09-17 or later**, computed **from the path**, never from a name list | the pre-2026-09-17 probe folders are **frozen evidence**: they are never re-run, their captures are what M3 reads, and re-running them would invalidate those captures. Their teardowns are `tmux -L shepherd-probe kill-server` / `tmux -L shp-gap-* kill-server` — correct under CLAUDE.md, outside `^shepherd-m3-`. **The exclusion is itself checked**: `test_the_frozen_probe_folders_are_exactly_the_dated_ones` asserts the excluded set is non-empty and that **every** excluded file sits under a folder whose date prefix is before 2026-09-17, so the exclusion cannot silently grow. **This is a stated scope, not an exemption** — nothing was added to make a failing thing pass |
| target form `^=[A-Za-z0-9_-]+:$` | same as the socket rule | a loose `-t` resolves to a different session (A5) |
| nothing writes under `~/.claude/` | `src/**/*.py`, `tests/**/*.py` | P-M3-14, K3 |

**Contents, exactly:**
- `DEFAULT_SOCKET = "shepherd-runner"` — **D49**, never `shepherd`. A test asserts the value is not
  `shepherd` **and** that the constant is the only default anywhere.
- `tmux_argv(socket, *args) -> list[str]` returning `["tmux", "-L", socket, *args]`.
- `session_name(session_id) -> str` returning `f"shepherd_{session_id}"`, raising if the id contains
  `:` or `.` (A5).
- `target(session_name) -> str` returning `f"={session_name}:"` (the exact form; prefix matching
  would let `shepherd_x` hit `shepherd_x2`).
- The `Runner` Protocol: §6's eight members plus `pane()` and `list_owned_panes()`
  (**N11**, ADR-M3-4) — ten in total.

**Expected Artifacts:** three modules, ≤ 150 lines each; seven boundary fixtures (three direct
violations, three indirections, one `~/.claude` write).
**Required Checks:**

*The runtime predicate (`tests/runner/test_tmux_guard.py`) — this is the load-bearing net:*
`test_an_argv_without_L_is_refused_at_the_exec_site` — **goes red** if the check returns instead of
raising, or if it **repairs** by inserting `-L`;
`test_the_socket_shepherd_is_never_permitted` — **goes red** if a `permitted` set containing
`shepherd` is accepted at construction;
`test_kill_server_is_refused_off_a_throwaway_socket` — **goes red** if the predicate is dropped or
widened to `shepherd-runner`;
`test_a_loose_target_is_refused_at_the_exec_site` — **goes red** on `-t name` or `-t name:0`;
`test_tmux_V_is_the_only_argv_allowed_without_a_socket_and_it_matches_by_equality` — **goes red** if
the exception becomes a prefix match, which would readmit `["tmux", "-V", "; anything"]`;
`test_a_non_tmux_argv_passes_through_untouched` — **goes red** if the guard starts policing `git`.

*The AST second net (`tests/boundaries/test_tmux_blast_radius.py`):*
`test_every_tmux_argv_carries_an_explicit_socket` over 1 000 generated calls — **goes red** when
`runner_bare_tmux_call.py` (a literal `["tmux", "list-sessions"]`) is scanned, and the test asserts
that it does, so the rule cannot be emptied;
`test_tmux_is_spelled_in_exactly_one_module` (AST literals over all of `src/`) — **goes red** if any
second module names it; **mutation proof required**: plant the literal in `runner/local.py`, run,
confirm red, revert;
`test_kill_server_appears_nowhere_in_src` — same mutation proof;
`test_no_tmux_call_in_the_tree_can_reach_the_users_socket` (P-M3-15) over `tests/**/*.py` **and**
`docs/probes/**/*.py`, recursive — **goes red** on a planted `-L shepherd` in a test;
`test_the_scan_scope_is_what_it_claims` — the walked set equals the recursive glob and spans three
directories; **goes red** if the walk narrows to one directory, which is what revision 1 shipped;
`test_the_frozen_probe_folders_are_exactly_the_dated_ones` — **goes red** if a file outside a
pre-2026-09-17 dated folder ends up excluded, i.e. if the stated scope starts drifting from the real
one;
**`test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime`** — the asymmetry
proof: `runner_tmux_via_constant_import.py` and `runner_kill_server_via_fstring.py` are asserted to
**pass** the AST scan (they carry no matching literal) and to be **refused** by `check_tmux_argv`;
`runner_tmux_via_fstring.py` likewise. **Goes red** if either net stops doing its half — and it is the
only test that can show the two nets catch different things.

*The rest:*
`test_a_session_name_never_contains_a_target_separator` over 10 000 ulids — **goes red** if any
generated id survives `session_name` carrying a `:` or a `.`;
`test_every_target_uses_the_exact_form` — **goes red** on a bare `name`, on `name:0`, or on a prefix
form that would let `shepherd_x` hit `shepherd_x2`;
`test_the_default_socket_is_not_the_users` — **goes red** if `DEFAULT_SOCKET` becomes `shepherd`;
`test_tmux_cmd_imports_no_process_module` — **goes red** if `subprocess` or `os` enters the pure layer;
`test_nothing_writes_under_the_engine_config_dir` (P-M3-14) over `src/**` and `tests/**`, AST with
origin resolution on the path expression — **goes red** on the planted
`src_writes_under_claude_home.py`;
inherited `test_layer_direction` — **goes red** if `runner/` imports above L2.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/runner tests/boundaries -q`.
**Exit Criteria:** all checks pass; **25** boundary tests green (23 shipped + `test_tmux_blast_radius`
+ `test_engine_config_is_read_only`) with **no new exemption**; `test_no_tmux_is_invoked_at_all`
**replaced, not deleted** — its docstring's rule now lives in `tests/boundaries/` and runs on the
default sweep; the four mutation proofs recorded in Progress notes with their red output.
**Test Seams:** unit; boundary (AST); **the new command seam's predicate, tested without a process**.

**Consumes:**
```python
from shepherd.core.runner import (PaneState, ProcState, RunnerHandle, SessionSpec,
                                  TerminalFrame, RunnerRefusal)      # T2
```
**Produces:**
```python
# runner/tmux_cmd.py
DEFAULT_SOCKET: str                                   # "shepherd-runner" (D49)
FORBIDDEN_SOCKET: str                                 # "shepherd" — never permitted
VERSION_ARGV: tuple[str, ...]                         # ("tmux", "-V"); matched by equality
THROWAWAY_SOCKET_RE: str                              # r"^shepherd-m3-[A-Za-z0-9_-]+$"
TARGET_RE: str                                        # r"^=[A-Za-z0-9_-]+:$"
def tmux_argv(socket: str, *args: str) -> list[str]: ...
def session_name(session_id: str) -> str: ...         # "shepherd_<id>"; raises on ':' or '.'
def target(name: str) -> str: ...                     # "=<name>:"
def permitted_sockets(*names: str) -> frozenset[str]: ...   # raises if any is FORBIDDEN_SOCKET
def check_tmux_argv(argv: list[str], *, permitted: frozenset[str]) -> None: ...
    # ADR-M3-8. Refuses — never repairs. Raises RunnerRefusal naming CLAUDE.md and §18.
# runner/base.py
class ByteStream(Protocol):
    def chunks(self) -> Iterator[bytes]: ...
    def close(self) -> None: ...
class Runner(Protocol):
    def start(self, spec: SessionSpec) -> RunnerHandle: ...
    def attach(self, handle: RunnerHandle) -> ByteStream: ...
    def snapshot(self, handle: RunnerHandle, lines: int) -> bytes: ...
    def write(self, handle: RunnerHandle, data: bytes) -> None: ...
    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None: ...
    def interrupt(self, handle: RunnerHandle) -> None: ...
    def terminate(self, handle: RunnerHandle) -> None: ...
    def probe(self, handle: RunnerHandle) -> ProcState: ...
    def pane(self, handle: RunnerHandle) -> PaneState: ...            # N11 (ninth)
    def list_owned_panes(self) -> tuple[PaneRef, ...]: ...            # N11 (tenth)
@dataclass(frozen=True)
class PaneRef:                          # one `shepherd_<ulid>` session on the socket
    session_name: str; session_id: str; pane_pid: int | None; dead: bool
```

---

### Task 6: `runner/pane.py` — what is on the screen, as a pure function over real captures

**Objective:** turn `capture-pane -e -p` bytes plus six tmux format fields into a `PaneState`, so the
write policy, the trust detector and the delivery trigger all read one classification.

**Files/Surfaces:**
- `src/shepherd/runner/pane.py` — new
- `tests/runner/test_pane.py` — new
- `tests/runner/fixtures/` — **symlink-free copies are forbidden**; the tests read the checked-in
  probe captures **by path**, so a fixture can never drift from the capture it claims to be

**Dependencies:** T2, T5.

**Allowed Scope:** one pure function and its predicates. No I/O, no tmux call.

**Out-of-Scope Drift:** classifying on hook text that happens to be printed into the pane
(E-M3-19). Treating ghost text as input (E-M3-5). Returning `PROMPT_READY` for a screen it could not
parse — that is `UNREADABLE`, and principle 5 says count it.

**The table, one row per kind. Revision 2 fixes an evidence error: two of the six kinds had no `-e`
capture and were cited to plain-`.txt` files, while `read_pane` consumes `capture-pane -e -p` bytes —
and T6's own negative asserts plain bytes must classify `UNREADABLE`, which contradicted the table.**
`ls run-20260914T154946Z/*.ansi` returns **exactly six** files and neither `07-running-after-send`
nor `13-dead-pane` is among them (verified 2026-09-17). **The fix is to classify `DEAD` and `BUSY`
on format fields and structure rather than on text markers**, which needs no new capture.

| Kind | Detected by | Evidence, and of what kind |
|---|---|---|
| `TRUST_DIALOG` | `alternate_on == 0` **and** the stable substring `Quick safety check: Is this a project you created or one you trust?` | **`-e` capture**: `01-trust-dialog.ansi` |
| `PERMISSION_DIALOG` | `Do you want to proceed?` **and** a line matching `^\s*❯?\s*1\. Yes` | **`-e` capture**: `06-permission-dialog.ansi` |
| `DEAD` | **`pane_dead == 1`. That alone is sufficient and no pane capture is consulted.** The text marker `Pane is dead (status ` is **withdrawn** as a detector | **format field**: `14-list-sessions-after-sigterm.txt` prints `probe_b\|…\|1\|1\|…` and `probe_sig\|…\|1\|143\|…` under `#{pane_dead}\|#{pane_dead_status}` — the field exists and is unambiguous |
| `PROMPT_READY` | `alternate_on == 1`, `pane_dead == 0`, an input line `❯` + NBSP between two `────` rules, and **no** dialog | **`-e` captures**: `03-after-stop.ansi`, `09-resize-after-70x30.ansi` |
| `BUSY` | **the residual**: `alternate_on == 1`, `pane_dead == 0`, no dialog, and no input-line structure. **No capture is cited, because `BUSY` asserts no byte shape** — it is what is left once the four positive kinds have been excluded, and its evidence is the four `-e` captures that define what it is *not* | **derived**, and the table says so rather than pointing at a `.txt` the reader would assume is `-e` bytes |
| `UNREADABLE` | anything else: non-UTF-8 bytes, an empty capture, or a capture with no recognisable structure. Counted `AnomalyKind.PANE_UNREADABLE` with a detail string | — |

**No row cites a capture for a byte shape production never produces.** The rule that produced the
error: `read_pane` is fed `capture-pane -e -p` bytes, so a `.txt` (plain `-p`) capture may be cited
only for a **format field** or as a **negative**, never as the positive example of a screen.

**Two different sets of six, disambiguated.** T6's classification set is the **five `-e` captures
above plus `14-list-sessions-after-sigterm.txt`'s format line** — it is not "the six captures", and
that phrase is withdrawn. P-M3-10's set is **the six `.ansi` files**, named in full there. They
overlap in four (`01`, `03`, `06`, `09`).

`input_text` is the input line's content with SGR-2 (dim) runs removed; `ghost_text` is the SGR-2 run
itself. A plain `-p` capture cannot separate them, which is why `read_pane` takes the `-e` bytes and a
test asserts the `-p` form of the same screen classifies the ghost as **ghost, not input** only when
`-e` is used — and fails loudly when it is not.

**Expected Artifacts:** one module ≤ 250 lines.
**Required Checks:**
`test_every_ansi_capture_classifies_to_its_documented_kind` over the **five** `-e` captures named in
the table — **goes red** if any predicate is loosened enough to swallow a neighbour;
`test_dead_is_decided_by_pane_dead_alone` — feeds `pane_dead=1` with an **empty** capture and asserts
`DEAD`; **goes red** if the withdrawn text marker creeps back, which would make `DEAD` depend on a
byte shape no `-e` capture in this repo demonstrates;
`test_busy_is_the_residual_and_cites_no_capture` — asserts `PANE_RULES`' `BUSY` row carries an
`evidence` string that names the **derivation**, not a capture path; **goes red** if someone points it
at `07-running-after-send.txt`, which is plain `-p` bytes production never feeds `read_pane`;
`test_ghost_text_is_not_a_draft` — **goes red** if the SGR-2 split is removed, which is the exact trap
`data-schemas.md` warns about;
`test_a_plain_capture_cannot_separate_ghost_from_input` — the **negative**: asserts the `-p` bytes
produce `UNREADABLE` or a ghost-free read, so a future "optimisation" to `-p` fails here rather than
in production. **This no longer contradicts the table**, because no kind is now positively classified
from plain bytes;
`test_read_pane_never_raises` — **the generator, corrected (P-M3-9).** Truncate **the whole capture**
at every byte boundary, for each of the five `-e` captures, plus empty, non-UTF-8, and a directory's
bytes. The test **computes** its case count from the enumerated inputs and **asserts the computed
count equals the constant it states**, so the loop cannot shrink silently. Revision 1 said
"truncation at every byte boundary of the **last line**" and claimed 200: `13-dead-pane.txt`'s last
line is **49 bytes** and the whole file is **154** (measured), so the stated generator could not reach
the stated number, and nothing asserted it — **M2 fixed this exact shape and wrote down why**.
**Goes red** if any input escapes as an exception, or if the asserted and generated counts disagree;
`test_every_pane_rule_cites_an_existing_section` (P-M3-16) — **goes red** if a row's `evidence` names
a `data-schemas.md` section that does not exist, **or** names a capture path that does not exist.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/runner -q`.
**Exit Criteria:** all checks pass; `mypy --strict` clean; no test reads anything under `~/.claude/`.
**Test Seams:** unit, over the checked-in captures.

**Consumes:** `PaneFields`, `PaneKind`, `PaneState` (T2).
**Produces:**
```python
def read_pane(capture: bytes, fields: PaneFields) -> PaneState: ...
PANE_RULES: tuple[PaneRule, ...]          # kind, predicate, evidence
TRUST_MARKER: str; PERMISSION_MARKER: str; DEAD_MARKER: str
def parse_pane_fields(line: str) -> PaneFields: ...   # the -F format's output, one pane per line
PANE_FORMAT: str        # "#{alternate_on}|#{pane_dead}|#{pane_dead_status}|#{pane_title}|#{pane_width}|#{pane_height}|#{pane_pid}"
```

---

### Task 7: `HostPlatform` gains `detached_launch` — the seventh member (DP5)

**Objective:** let the runner start a tmux server that **outlives the daemon that started it**,
without any module outside `host/` knowing what a cgroup is.

**Files/Surfaces:**
- `src/shepherd/host/base.py` — one `Protocol` member, one frozen record
- `src/shepherd/host/linux.py` — the verified driver
- `src/shepherd/host/mac.py` — written, annotated `# UNVERIFIED (no capture) — D55`
- `src/shepherd/testkit/scripted_host.py` — one fixture-answered method
- `tests/contracts/test_hostplatform_contract.py` — rows for all three

**Dependencies:** none. Track B, runnable from day 1.

**Allowed Scope:** one member. `LinuxHost` returns the `systemd-run --user --scope --` prefix when
`supervision().kind == "systemd_user"` **and** `systemd-run` resolves, and the bare argv otherwise
(a container has no systemd, which is why `SupervisionKind` already has three values).

**Which honesty regime `MacHost` uses, stated rather than left to the builder.** `host/mac.py` has
two: *refuse* (`UnverifiedHostCapability`) where a wrong value would look measured, and
*write-and-annotate* where the shape is knowable and only the value is not. `detached_launch` takes
**write-and-annotate**, because the record carries a `verified: bool` that makes the guess visible at
the call site, and because refusing would make `MacHost` unable to answer a question every spawn
asks — which would turn an unverified value into a broken product rather than an honest one. The
value is `DetachedLaunch(prefix=(), mechanism="none", verified=False)` with
`# UNVERIFIED (no capture) — D55` beside it, and `MacHost.verified()` stays `False`. **A caller that
wants to refuse can read `verified`; a caller that merely wants to spawn on Linux is unaffected.**

**Out-of-Scope Drift:** writing a unit file (M6). Making the wrapper conditional on anything outside
`host/`. Adding a member for anything M3 does not need — D55's six became seven for one measured
reason and a reviewer must be able to see it.

**Expected Artifacts:** one member across four files; five contract rows.
**Required Checks:**
`test_detached_launch_wraps_under_systemd_and_not_otherwise` — **goes red** if the wrapper is applied
unconditionally, which would break every container install;
`test_detached_launch_returns_argv_never_a_string` — **goes red** on any `shell=True`-shaped value (K5);
`test_machost_constants_are_annotated` (inherited) — **goes red** if the macOS value ships without its
`# UNVERIFIED` marker;
`test_scripted_host_answers_every_protocol_member` — **goes red** the moment the Protocol grows and
the double does not, which is §14.2's whole point;
inherited `test_platform_branching` — **goes red** if any module outside `host/` names `systemctl`,
`sys.platform`, `os.name` or their aliases. **Plant `Supervision.kind` branching in
`runner/local.py`** and confirm the *layer* rule catches the import; record it.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/contracts tests/boundaries -q`.
**Exit Criteria:** three drivers pass the one suite; `MacHost.verified()` still `False`;
`mypy --strict` clean.
**Test Seams:** contract (existing suite), unit.

**Consumes:** `HostPlatform`, `Supervision`, `SupervisionKind` (shipped).
**Produces:**
```python
@dataclass(frozen=True)
class DetachedLaunch:
    prefix: tuple[str, ...]      # () when no wrapper is needed
    mechanism: str               # "systemd-run --user --scope" | "none"
    detail: str
    verified: bool
class HostPlatform(Protocol):
    def detached_launch(self) -> DetachedLaunch: ...    # the seventh member (DP5)
```

---

### Task 8: `runner/local.py` — `LocalRunner`

**Objective:** the ten `Runner` members, each one or two tmux argv invocations through one injected
`run_argv`, so the whole driver is testable with **no tmux server**.

**Files/Surfaces:**
- `src/shepherd/runner/local.py` — new
- `tests/runner/test_local.py` — new

**Dependencies:** T2, T5, T6, T7.

**Allowed Scope:** the ten members plus `ensure_server`, **plus the one real `RunArgv`
implementation and the runtime guard inside it** (ADR-M3-8). One injected
`run_argv: Callable[[list[str]], CommandResult]`; one injected `now`. Nothing else.

**The exec site, exactly.** `make_run_argv(permitted: frozenset[str]) -> RunArgv` returns the one
function in `src/` that starts a process, and its **first statement** is
`check_tmux_argv(argv, permitted=permitted)` (T5, pure) — before `subprocess.run`, argv only, never
`shell=True`, never a path it resolved itself. It **refuses, never repairs**. `permitted` is built by
`permitted_sockets(...)`, which raises if handed `shepherd`. This is where K6 actually holds: the
three AST rules are a second net and each of them falls to one line of indirection (ADR-M3-8).

**Out-of-Scope Drift:** spawn **policy** (T11 — this module starts a pane, it does not decide whether
one may exist). Reading the store. Calling `subprocess` directly (the injection is the seam and a
test asserts no `subprocess.` symbol resolves here). Adding `signal()` — D43 removed it (**N14**).

**The ten members, exactly:**

| Member | tmux |
|---|---|
| `ensure_server` | `has-session` probe; on failure, `host.detached_launch().prefix + tmux_argv(socket, "new-session", "-d", "-s", <bootstrap>, ...)`; `set-option -g status off` so the attached view carries no host name |
| `start` | `new-session -d -s <name> -x <cols> -y <rows> -e KEY=VAL… <argv words>`, then `set-option -w -t <target> remain-on-exit on` (**E-M3-16** — without it the exit code is gone) |
| `attach` | `pipe-pane -o -t <target> 'cat >> <sink>'` and a tailing `ByteStream`; `pipe-pane -t <target>` (no command) to stop |
| `snapshot` | `capture-pane -e -p -S -<lines> -t <target>` |
| `write` | `send-keys -H -t <target> <hex>` for raw bytes; `send-keys -l -t <target> -- <text>` for text (C4: a payload starting with `-` needs `--`) |
| `resize` | `resize-window -t <target> -x <cols> -y <rows>`; the returned handle records that the window is now `manual` (**E-M3-22**) |
| `interrupt` | `send-keys -t <target> Escape` — **never a signal** (D43) |
| `terminate` | `kill-session -t <target>` — **never `kill-server` in `src/`** (K6, K16). A teardown that needs `kill-server` is a *test* teardown, on a `^shepherd-m3-` socket, and the guard is what bounds it |
| `probe` | `list-sessions -F <PANE_FORMAT>` filtered to the target |
| `pane` | `capture-pane -e -p` + `list-sessions -F <PANE_FORMAT>` → `read_pane` (T6) |
| `list_owned_panes` | `list-sessions -F <PANE_FORMAT>`, filtered to session names matching `^shepherd_[0-9A-HJKMNP-TV-Z]{26}$`, one `PaneRef` each. **The ground truth for the total cap and for T12's orphan reconcile** — rows are an index over these, never the other way round |

**Expected Artifacts:** one module ≤ 350 lines.
**Required Checks:**
`test_every_member_produces_the_documented_argv` — a table test asserting the **exact list**, which is
what makes K6 checkable; **goes red** on any argv drift, including a lost `-L`;
`test_keys_go_through_send_keys_H_never_the_pane_tty` — **goes red** if `#{pane_tty}` is read here
(A2: writing to it delivers zero bytes and prints to the screen);
`test_interrupt_is_escape_and_never_a_signal` plus `test_no_signal_reaches_a_session` (P-M3-7, AST with
origin resolution) — **planted proof**: add `os.kill(pid, signal.SIGINT)`; confirm red;
`test_terminate_uses_kill_session_with_an_exact_target` — **goes red** on `kill-server`, on a bare
`-t <name>`, or on a target that is not the `=<name>:` form (A5: `-t a:b` resolves to session `a`);
`test_remain_on_exit_is_set_at_start` — **goes red** if it moves to a later call, where a fast exit
would beat it;
`test_the_server_is_started_through_detached_launch` — **goes red** if `ensure_server` builds its own
prefix;
`test_local_runner_constructs_no_subprocess_call` — **goes red** if the injection is bypassed;
**`test_the_exec_callable_checks_before_it_execs`** — patches `subprocess.run` to fail the test if
it is reached, hands `make_run_argv` a bad argv, and asserts the refusal arrived **without** a process
being started; **goes red** if the guard moves after the exec, is `try`-wrapped, or is skipped for
`rc`-checking convenience. This is the single assertion ADR-M3-8 rests on;
**`test_the_guard_refuses_the_indirection_fixtures_the_ast_rules_miss`** — feeds the argvs
`runner_tmux_via_constant_import.py` and `runner_kill_server_via_fstring.py` build; **goes red** if
the runtime check is reduced to a literal match, i.e. to the AST rule it exists to back up;
`test_the_runner_never_raises` — **the generator, corrected (P-M3-9).** The population is the **ten
`Runner` members plus `ensure_server`**, enumerated at test time from the `Runner` Protocol rather
than hand-listed — **11** entry points, and the test asserts it found 11, so a member that stops being
covered fails here rather than silently. Degradations per entry point: `rc ≠ 0`, empty stdout,
**non-UTF-8 stdout truncated at every byte boundary of a whole capture**, and
`FileNotFoundError` for `tmux`. The test **computes** its case count and **asserts it equals the
constant it states**. **Goes red** if any case leaks an exception instead of a `ProcState`, a
`PaneState(UNREADABLE)` or a `RunnerRefusal`; if a degradation is not counted as an `AnomalyKind`
member (`TMUX_UNAVAILABLE` for the absent binary and the absent server, `PANE_UNREADABLE` for the
unparseable bytes); or if the enumerated population shrinks below 11.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/runner tests/boundaries -q`. **No tmux
server is started by this task's tests**, including the guard's — `subprocess.run` is patched.
**Exit Criteria:** all checks pass; the planted-signal proof recorded; the guard's
check-before-exec proof recorded; `mypy --strict` clean.
**Test Seams:** unit; the new command seam (`run_argv`).

**Consumes:** `tmux_argv`, `session_name`, `target`, `DEFAULT_SOCKET`, `check_tmux_argv`,
`permitted_sockets`, `Runner`, `ByteStream` (T5); `read_pane`, `parse_pane_fields`, `PANE_FORMAT`
(T6); `DetachedLaunch` (T7); the `core/runner.py` records and `AnomalyKind.TMUX_UNAVAILABLE`,
`AnomalyKind.PANE_UNREADABLE` (T2).
**Produces:**
```python
@dataclass(frozen=True) class CommandResult: rc: int; stdout: bytes; stderr: bytes
RunArgv = Callable[[list[str]], CommandResult]
@dataclass(frozen=True)
class LocalRunner:                      # satisfies Runner structurally; not a base class
    socket: str; run_argv: RunArgv; launch: DetachedLaunch; now: Callable[[], str]
    def ensure_server(self) -> None: ...
    # ... the ten Runner members
def make_run_argv(permitted: frozenset[str]) -> RunArgv: ...
    # the one real implementation. Its first statement is check_tmux_argv(argv, permitted=permitted)
    # (ADR-M3-8); argv only, never shell=True, never a path it resolved itself.
```

---

### Task 9: `testkit/scripted_runner.py` and the `Runner` contract suite

**Objective:** §14.2's rule, applied to the seam M3 creates: one `Scripted*` that ships with the
package, and **one** suite every implementation passes.

**Files/Surfaces:**
- `src/shepherd/testkit/scripted_runner.py` — new
- `tests/contracts/test_runner_contract.py` — new

**Dependencies:** T5, T6, T8.

**Allowed Scope:** a concrete peer answering from frozen fixtures — a scripted `PaneState` sequence, a
`ProcState`, a snapshot `bytes`, and a recorded list of every `write` it received. **Never a base
class**; nothing inherits from it.

**Out-of-Scope Drift:** a mock with call expectations (§14.2 says what a `Scripted*` is not). Growing
it toward a real runner. Letting the contract suite start a tmux server outside the `live` marker.

**Expected Artifacts:** one `testkit/` module ≤ 150 lines; one suite.
**Required Checks:**
The suite runs against **both** implementations. Platform-independent rows (argv shape, handle
round-trip, refusal on an unknown target, `pane()` totality, `write` byte-exactness) run everywhere;
rows that need a server are `live`-marked and **skipped, never faked**, exactly as
`test_hostplatform_contract.py` skips `MacHost`'s real-host rows.
`test_scripted_runner_answers_every_protocol_member` — over all **ten** members; **goes red** when
`Runner` grows a member and the double does not, which is §14.2's whole point and is how the tenth
member (`list_owned_panes`) stays testable above the unit seam;
`test_scripted_runner_is_not_a_base_class` (no `src/` class has it as a base) — **goes red** on the
inheritance that §14.2 names as the failure;
`test_every_write_is_recorded_byte_exact` — **goes red** if the double normalises what it was handed,
which would let a real byte-mangling bug pass the suite.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic for the shared rows; **Live** for the server rows
(`.venv/bin/pytest tests/contracts -m live`), on socket `shepherd-m3-live`.
**Exit Criteria:** both implementations pass; the live rows skip cleanly with no tmux server present;
`mypy --strict` clean.
**Test Seams:** contract.

**Consumes:** `Runner`, `ByteStream` (T5); `PaneState`, `ProcState`, `RunnerHandle`, `SessionSpec`,
`TerminalFrame` (T2); `LocalRunner`, `CommandResult` (T8).
**Produces:**
```python
@dataclass(frozen=True)
class ScriptedRunner:                    # a concrete peer of LocalRunner
    panes: tuple[PaneState, ...]; proc: ProcState; screen: bytes
    owned_panes: tuple[PaneRef, ...] = ()
    writes: list[bytes] = field(default_factory=list)
    # ... the ten Runner members, answered from the fixtures
```

---

### Task 10: `engines/claude_code/spawn.py` — `spawn_argv`, the capability record, and the trust pre-flight

**Objective:** the three `EngineAdapter` members M3 needs (**DP6**), as module functions in the one
package engine vocabulary is allowed to live in.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/spawn.py` — new
- `tests/engines/test_spawn_argv.py` — new

**Dependencies:** T2. (T1/P2 only for the **fork** argv, which is T15's.)

**Allowed Scope:** `spawn_argv`, `CLAUDE_CODE_CAPABILITIES`, `resolve_binary`, `trust_state`. Pure
except `resolve_binary` (a `PATH` lookup) and `trust_state` (a read-only read of
`~/.claude.json`).

**Out-of-Scope Drift:** running anything. Writing anything under `~/.claude/` — `trust_state` **reads**
`projects[<cwd>].hasTrustDialogAccepted` and writes nothing (9 True / 2 False in the captured file).
Setting `can_set_title = True` (**DP1** — not applied). Building the fork argv (T15).

**`spawn_argv`, exactly** — every element a separate argv word (A9), `--` before the brief (A11):
```
<claude> --session-id <uuid> [--name <title>] [--model <m>] [--effort <e>] [-- <brief>]
```
A brief whose UTF-8 length plus the rest of the command exceeds `TMUX_COMMAND_LIMIT_B` is **refused**,
never truncated (A10, E-M3-10). §16's M3 does not spawn queue workers, so no `--settings` is passed in
production; the **live lane** adds one, which is how K3 stays true there.

**Expected Artifacts:** one module ≤ 250 lines.
**Required Checks:**
`test_the_brief_is_one_argv_word_after_a_separator` — **goes red** if the brief is joined into a
command string, which `argv-…/results.json` shows makes `sh -c` expand `$()` and strip quotes;
`test_a_brief_starting_with_a_dash_survives` — **goes red** if `--` is dropped (`claude-dash-brief.stderr`);
`test_an_oversized_brief_is_refused_not_truncated` at 16 324 / 16 325 bytes — **goes red** on a silent
truncation, which would send the model half an instruction;
`test_spawn_argv_is_pure` (200 cases) — **goes red** if a clock or a path read creeps in;
`test_every_flag_is_present_in_claude_help` (**live**, G-M3-7) — runs `claude --help`, asserts
`--session-id`, `--name`, `--model`, `--effort`, `--fork-session`, `--no-session-persistence` each
appear, and **records the version** — **goes red** when the engine renames a flag, which is the drift
the enum-only `drift_check.py` cannot see;
`test_can_set_title_ships_false` — **goes red** if anyone flips it; its message names **DP1** and says
a recorded approval is required;
`test_trust_state_writes_nothing` (the file's mtime and sha256 unchanged) — **goes red** on any write
under `~/.claude/` (K3);
`test_every_spawn_rule_cites_an_existing_section` (**P-M3-16**, added in revision 2) — every row of
the spawn-argv table carries a non-empty `evidence` string; **goes red** if a row names a
`data-schemas.md` section that does not exist. Revision 1's P-M3-16 claimed the spawn-argv table was
covered and **no task created the test**, so a verifier matching on name would have scored it PASS
against T6's or T13's variant.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, plus one **Live** row for `--help`.
**Exit Criteria:** all checks pass; the `--help` output recorded in Progress notes with the version.
**Test Seams:** unit; one live row.

**Consumes:** `SessionSpec`, `EngineCapabilities`, `TMUX_COMMAND_LIMIT_B`, `RunnerRefusal` (T2).
**Produces:**
```python
CLAUDE_CODE_CAPABILITIES: EngineCapabilities
    # can_spawn=<tmux present>, can_steer=True, can_fork=True (data-schemas §Fork l.2920),
    # can_set_title=False (D29 literal — DP1 recommends True for owned and is NOT APPLIED),
    # has_hooks=True, effort_ladder=("low","medium","high","xhigh","max"),
    # transcript_format="jsonl"
def spawn_argv(spec: SessionSpec, binary: str) -> list[str]: ...
def resolve_binary() -> str: ...          # absolute path; raises RunnerRefusal (C1, E-M3-14)
@dataclass(frozen=True) class TrustState: trusted: bool | None; source: str
def trust_state(cwd: str, engine_config_home: Path | None = None) -> TrustState: ...
```

---

### Task 11: `orchestration/spawn.py` — the spawn sequence

**Objective:** turn "start a session" into a sequence that cannot answer a dialog for you, cannot
create two rows, and cannot exceed §11's caps.

**Files/Surfaces:**
- `src/shepherd/orchestration/__init__.py`, `src/shepherd/orchestration/spawn.py` — new
- `tests/orchestration/__init__.py`, `tests/orchestration/test_spawn.py` — new

**Dependencies:** T4, T8, T10.

**Allowed Scope:** the sequence below, with `Store`, `Runner`, `now` and a publisher all injected.

**Out-of-Scope Drift:** worktrees (M5). A `--settings` in production. Sending **any** key during a
spawn. Deciding a stop verdict (M2 owns that lane).

**The sequence, in order:**
1. Validate the project and canonicalize `cwd` against the **registered repo/workspace roots** (§13:
   "no path traversal into an unregistered directory"). Refuse otherwise.
2. Check the caps: `depth < 3`, `children_of(parent) < 5`, and **`len(runner.list_owned_panes()) < 20`** — the
   total cap counts **panes on the socket**, not rows (revision 2). Revision 1 counted rows, which
   makes the cap uncountable in exactly the case it matters: a handle-less orphaned row can never be
   terminated, so orphans accumulate across every restart while each holds a live `claude`. The pane
   count comes from the same `list-sessions -F` sweep T12's reconcile runs, filtered to
   `shepherd_<ulid>` names. Each refusal names **which** cap, because §11 says the error must be one
   the caller can reason about.
3. Read `trust_state(cwd)`. If it is `False`, **say so in the refusal-or-warning before spawning** —
   the session will stop on a dialog and that is a fact worth knowing in advance.
4. `engine_session_id = uuid4()`. **`create_owned_session(...)` — the row exists first** (C-M3-7).
5. `runner.ensure_server()`; `runner.start(spec)`; `set_runner_handle(...)`.
6. Poll `runner.pane()` every `SPAWN_POLL_INTERVAL_S` up to `SPAWN_TIMEOUT_S` until `PROMPT_READY`,
   `TRUST_DIALOG` or `DEAD`.
7. `PROMPT_READY` → leave `starting`; the hook lane's `SessionStart` moves it (D47 path unchanged).
   `TRUST_DIALOG` → `needs_you`, reason `workspace trust: <cwd>` (**N13**). `DEAD` → `stopped`, `why`
   naming the refusal, `exit_code` from `pane_dead_status`. Timeout → `needs_you` with
   `pane state unreadable after 60s`, counted.
8. Publish `session.spawned`.

**Expected Artifacts:** one module ≤ 300 lines.
**Required Checks:**
`test_the_row_exists_before_the_process_does` — asserts ordering by making `runner.start` raise and
finding the row; **goes red** if steps 4 and 5 are swapped, which is the whole of C-M3-7;
`test_an_untrusted_directory_becomes_needs_you_and_no_key_is_sent` (**P-M3-6**) — run through
**`LocalRunner` with a counting `run_argv`**, asserting the spawn **reached step 6 and set
`state == needs_you`** *before* asserting zero calls. **Goes red** if any convenience `Enter` is added
(a bare `Enter` selects **"No, exit"**, A11, exit status 1) **and** if the spawn returns early, which
is the zero-count-that-passes-because-nothing-ran hazard. Revision 1 asserted
`ScriptedRunner.writes == []`, and `ScriptedRunner` has **no `run_argv`** while `write` is one of nine
`Runner` members — a stray `Enter` through `interrupt` (`send-keys Escape`) or any other member would
have left `writes` empty and the test green. The `ScriptedRunner` assertion is kept beside it as the
fast path, not as the proof;
`test_depth_children_and_total_caps_each_refuse_with_their_own_message` — **goes red** if one message
serves all three, which would make the agent-facing error unactionable;
`test_the_total_cap_counts_panes_not_rows` — a handle-less owned row plus a live pane; **goes red** if
the cap reads `owned_session_counts` alone, which is the state in which orphans accumulate unbounded;
`test_spawn_refuses_an_unregistered_directory` including `../` traversal — **goes red** on any path
accepted outside the registered roots;
`test_no_tmux_is_a_refusal_not_a_traceback` (`resolve_binary`/`ensure_server` failing) — **goes red**
if an exception reaches the tool surface;
`test_spawn_resolves_to_one_of_three_pane_states` over a scripted pane sequence — **goes red** if a
fourth outcome can escape unlabelled.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, with `ScriptedRunner`. No tmux server.
**Exit Criteria:** all checks pass; `mypy --strict` clean; boundary suite green.
**Test Seams:** unit; `invoke()` later at T18.

**Consumes:** `create_owned_session`, `set_runner_handle`, `owned_session_counts`, `children_of` (T4);
`Runner`, `Runner.list_owned_panes`, `PaneRef` (T5); `spawn_argv`, `resolve_binary`, `trust_state`,
`CLAUDE_CODE_CAPABILITIES` (T10); `SessionSpec`, `PaneKind`, `RunnerRefusal`, the three caps,
`SPAWN_*` (T2).

*(`list_owned_panes` is a `Runner` member rather than a `lifecycle` helper precisely so T11 can call
it without depending on T12, which depends on T11 — the cycle a pane-counting cap would otherwise
create. It is the tenth member; see N11 and ADR-M3-4, whose argument applies unchanged: `ScriptedRunner`
must be able to answer it or no test above the unit seam can run.)*
**Produces:**
```python
@dataclass(frozen=True) class SpawnOutcome: session_id: str; state: SessionState; detail: str
@dataclass(frozen=True) class SpawnRefused: reason: str; cap: str | None
def spawn_owned_session(*, store: Store, runner: Runner, now: Callable[[], str],
                        publish: Callable[[StreamEvent], None], workspace_id: str, cwd: str,
                        brief: str | None, title: str | None, model: str | None, effort: str | None,
                        parent_session_id: str | None, origin: Origin,
                        ephemeral: bool = False) -> SpawnOutcome | SpawnRefused: ...
```

---

### Task 12: `orchestration/lifecycle.py` — exit codes, rebinding, interrupt, terminate

**Objective:** make an owned session's *end* knowable, which is what closes **G-M2-2** for owned
sessions, and make `/resume` a rebinding rather than a death (**C14**).

**Files/Surfaces:**
- `src/shepherd/orchestration/lifecycle.py` — new
- `src/shepherd/signals/hook_lane.py` — **`HookLane.__init__` gains BOTH of M3's defaulted
  parameters, here and nowhere else**: `on_engine_session_rebound` and `on_stop_deliver`. M1/M2's
  two-argument and four-argument calls still work
- `tests/orchestration/test_lifecycle.py` — new

**Dependencies:** T4, T8, T11.

**Allowed Scope:** five operations: `record_and_terminate`, `interrupt`, `observe_exit`, `rebind`,
`reconcile_owned_panes`.

**`signals/hook_lane.py` is this task's file alone (revision 2).** Revision 1 had **T12 add a
`rebind` callback and T14 add an `on_stop_deliver` hook to the same module**, and T12 is Track C
while T14 is Track D — which violates this plan's own hard rule that no two tracks share a file, a
rule it calls hard because **half of M1's blocker file is two builders in one file**. Both parameters
now land here, in one additive change; **T14 consumes `on_stop_deliver` and does not open the file.**
T14 gains a dependency on T12 for it.

**And the callback is renamed: `on_engine_session_rebound`, not `rebind`.**
`HookLane._rebind` **already exists** at `signals/hook_lane.py:149` (called from line 92, and it does
something else — it re-binds a moved session to a *repo*). Two `rebind`s in one module is the hazard
M2 recorded for `replay`. The `orchestration/lifecycle.py` function keeps the name `rebind`; only the
`HookLane` parameter is renamed, because the collision is inside `hook_lane.py`.

**Out-of-Scope Drift:** classifying a stop (M2's `stop_lane` owns it; this task **supplies the exit
code** and nothing else). Reaching into `signals/` beyond the two defaulted parameters. Adding a
second stop writer — `apply_stop_verdict` remains the only one. Touching `HookLane._rebind`.

**The four, exactly:**
- **`record_and_terminate`** — write the action **before** issuing `kill-session`, because
  `kill-session` removes the `list-sessions` row and the exit status with it (E-M3-17), and a slow
  `SessionEnd` hook may not survive (**G-M3-9**). A kill with no following `SessionEnd` is counted
  `KILL_WITHOUT_SESSION_END`, and the verdict is written from the recorded action.
- **`interrupt`** — `send-keys Escape`. An interrupted turn emits **no `Stop`** (A13), so this is also
  the moment the mailbox's second trigger matters (D45); the session is left `running` and the pane
  poll decides.
- **`observe_exit`** — `probe()` → `pane_dead_status`. For **owned** sessions this is a real
  `exit_code`: `0` (`/exit`), `1` (trust refused), `143` (SIGTERM). `pane_dead_signal` is **always
  empty** on this evidence and is recorded as `None`, never guessed.
- **`rebind`** — `SessionEnd{reason:resume}` followed by `SessionStart{source:resume}` **in the same
  pane** means the row keeps its identity and changes its `engine_session_id` (C14). It is **not** a
  stop. Reached from `HookLane`'s `on_engine_session_rebound` parameter.
- **`reconcile_owned_panes`** *(new in revision 2 — the orphan reaper)*. **Why it must exist:** if
  `controld` dies between `runner.start(spec)` and `set_runner_handle(...)`, a real `claude` is
  running in a real pane and its row has `runner_handle IS NULL`. **DP5's `detached_launch` makes that
  orphan durable by design** — the pane deliberately survives the daemon. Nothing in revision 1
  reconciled it: T23 only constructs and registers, discovery reads the **registry** and not tmux,
  `observe_exit` needs the handle it does not have, and the total cap counted **rows**, so a
  handle-less row could never be terminated and orphans accumulated across every restart, each
  holding a live process.
  **What it does, at startup, once:** `runner.list_owned_panes()` → for each `PaneRef` whose
  `session_name` is `shepherd_<ulid>`, look up the row by that ulid (**the name is deterministic**,
  `session_name(session_id)`, which is exactly why rebinding is possible at all):
  * row exists, handle set → nothing;
  * row exists, `runner_handle IS NULL` → **rebind the handle** from the `PaneRef`, because the name
    determines `(runner, socket, session_name)` completely;
  * **no row at all** → count `AnomalyKind.ORPHANED_PANE` with the pane name in the detail, and
    surface it in `doctor`. Not killed: a pane Shepherd cannot account for is a fact to show a human,
    not a process to destroy silently (principle 5, and K6's own reasoning about blast radius).
  Rows whose pane is gone are left to the normal stop path; this function adds no second stop writer.

**Expected Artifacts:** one module ≤ 250 lines; one defaulted parameter elsewhere.
**Required Checks:**
`test_the_kill_is_recorded_before_it_is_issued` — asserts order by making `terminate` raise and
finding the record; **goes red** on the natural implementation, which is why it is written first;
`test_an_owned_exit_code_reaches_the_row` over the three captured statuses (0, 1, 143) — **goes red**
if `pane_dead_status` is read after `kill-session`, where the row no longer exists;
`test_crashed_is_now_reachable_for_owned_and_still_unreachable_for_attached` — **goes red** in either
direction; M2 asserts the attached half today and this must not weaken it;
`test_resume_rebinds_and_does_not_stop` — **goes red** if the pair is folded as a stop, which would
mark a live session dead (C14);
`test_interrupt_leaves_the_session_running_and_emits_no_stop` — **goes red** if an interrupt is
treated as a stop, which no capture supports;
`test_hook_lane_signature_is_backward_compatible` — **goes red** if M1's or M2's two- and
four-argument `HookLane(...)` call sites break;
`test_hook_lane_gains_exactly_two_parameters_and_no_other_task_opens_the_file` — asserts
`HookLane.__init__` has M1/M2's parameters plus exactly `on_engine_session_rebound` and
`on_stop_deliver`; **goes red** if a second task adds a third, which is the two-builders-one-file
failure this plan calls a hard rule;
`test_the_callback_name_does_not_collide_with_the_existing_private_rebind` — asserts
`hook_lane.py` binds no second `rebind`; **goes red** on the collision with `HookLane._rebind`
(l.149), which a reader of one file would have to disambiguate by hand;
`test_a_handle_less_owned_row_is_rebound_by_the_startup_reconcile` — **goes red** if the reconcile
skips rows whose handle is null, which is the exact orphan `detached_launch` makes durable;
`test_a_pane_with_no_row_is_counted_as_ORPHANED_PANE_and_is_not_killed` — **goes red** in either
direction: a silent kill, or a pane that is neither adopted nor counted;
`test_the_reconcile_runs_before_the_first_spawn_can_take_a_cap_slot` — **goes red** if the cap is
read before the panes are enumerated, in which case the orphan is invisible to the very count that
exists to bound it.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic.
**Exit Criteria:** all checks pass; M2's `test_unreachable_reasons_are_unreachable` still passes for
attached sessions; full suite green.
**Test Seams:** unit; the golden lane re-run unchanged.

**Consumes:** `rebind_engine_session_id`, `set_runner_handle` (T4); `Runner.probe`,
`Runner.terminate`, `Runner.interrupt`, `Runner.list_owned_panes`, `PaneRef`, `session_name`
(T5/T8); `ProcState`, `AnomalyKind.KILL_WITHOUT_SESSION_END`, `AnomalyKind.ORPHANED_PANE` (T2);
`apply_stop_verdict`, `StopReason`, `Verdict`, `HookLane` (M2).
**Produces:**
```python
def record_and_terminate(*, store, runner, handle, session_id, now, publish) -> ProcState: ...
def interrupt_session(*, store, runner, handle, session_id, now, publish) -> None: ...
def observe_exit(*, runner, handle) -> ProcState: ...
def rebind(*, store, session_id: str, new_engine_session_id: str) -> None: ...
def reconcile_owned_panes(*, store, runner, now) -> ReconcileCounts: ...
@dataclass(frozen=True) class ReconcileCounts: rebound: int; orphaned: int; intact: int
# signals/hook_lane.py — HookLane.__init__ gains BOTH, here and nowhere else:
#   on_engine_session_rebound: Callable[[str, str], None] | None = None   # NOT `rebind` (l.149 collides)
#   on_stop_deliver:           Callable[[str], None] | None = None        # consumed by T14
```

---

### Task 13: `orchestration/write_policy.py` — the table that must not be wrong

**Objective:** one pure, total decision over the **4-tuple key**
`SessionState × PaneKind × Ownership × input_empty` (ADR-M3-5), with D44's and D45's corrections built
in rather than bolted on.

**Files/Surfaces:**
- `src/shepherd/orchestration/write_policy.py` — new
- `tests/orchestration/test_write_policy.py` — new

**Dependencies:** T2, T6, T8 (for `LocalRunner` + a counting `run_argv`, which is where the refusal
proof is taken). **No longer blocked on P1**: `C-u` is captured (`01b-after-ctrl-u.txt`), so the
clearing row ships now and P1 only reports on the post-`Esc` variant, which the post-`C-u` re-read
handles either way.

**Allowed Scope:** the table, the lookup, and an `evidence` string per row. **Pure**: no clock, no
store, no runner, and — the point — **no sending**.

**Out-of-Scope Drift:** doing the write here (T14/T18 call the runner). Reading the sidecar here
(the caller supplies the dialog fact; this function takes values, not sources). Collapsing the three
refusals into one.

**The 96 keys, summarised by rule. The table below is a human projection, not the key set** — it
collapses `input_empty` for the kinds where it does not change the answer and merges `DEAD` with
`UNREADABLE`. Expanded, it is 56 rows; as a 4-tuple key space it is **96**. The test asserts the
**set of 96 key tuples**, never the table's appearance and never a length (ADR-M3-5).

| state \ pane | `PERMISSION_DIALOG` | `TRUST_DIALOG` | `PROMPT_READY` (input empty) | `PROMPT_READY` (input non-empty) | `BUSY` | `DEAD`/`UNREADABLE` |
|---|---|---|---|---|---|---|
| `stopped` | `REFUSE_DIALOG` | `REFUSE_DIALOG` | `SEND_NOW` | **`CLEAR_THEN_SEND`** | `QUEUE` | `REFUSE_NO_PTY` |
| `needs_you` | **`REFUSE_DIALOG`** (D44) | `REFUSE_DIALOG` | **`SEND_NOW`** (a question in the transcript) | **`CLEAR_THEN_SEND`** | `QUEUE` | `REFUSE_NO_PTY` |
| `running` | `REFUSE_DIALOG` | `REFUSE_DIALOG` | `QUEUE` | `QUEUE` | `QUEUE` | `REFUSE_NO_PTY` |
| `starting` | `REFUSE_DIALOG` | `REFUSE_DIALOG` | `QUEUE` | `QUEUE` | `QUEUE` | `REFUSE_NO_PTY` |

**`CLEAR_THEN_SEND` is revision 2's sixth `WriteDecision`**, and it exists because `C-u` is captured
(DP10, A22, `01b-after-ctrl-u.txt`): the caller sends `C-u`, **re-reads the pane**, and proceeds only
if the box is now empty. If it is not, that is `REFUSE_INPUT_NOT_EMPTY`, counted as
`AnomalyKind.MAILBOX_INPUT_NOT_EMPTY`, retried at the next trigger. `REFUSE_INPUT_NOT_EMPTY` is
therefore still a reachable decision — it is the **re-read's** outcome, not the table's, which is
what makes the clearing form unable to be worse than the refusing form.
**T2's `WriteDecision` gains `CLEAR_THEN_SEND`**, so `test_write_decision_has_five_members` becomes
`test_write_decision_has_six_members`.

**Every `ownership == ATTACHED` key is `REFUSE_NO_PTY`**, with §9's banner wording — attached
sessions have no pane Shepherd may drive, and the user's socket is K6 territory. That is 48 of the 96
keys, and their uniformity is asserted separately rather than assumed from the table.
`input_empty` is a *pane* fact and a **key field**, not a fifth state: `PaneState.input_text`
non-empty with `ghost_text` excluded (E-M3-5). Every pane kind gets both values of it, even where the
answer is the same for both — that is what makes a dropped `CLEAR_THEN_SEND` or
`REFUSE_INPUT_NOT_EMPTY` row detectable.

**Expected Artifacts:** one module ≤ 200 lines.
**Required Checks:**
`test_the_key_set_equals_the_product` (**P-M3-4**) — builds
`set(itertools.product(SessionState, PaneKind, Ownership, (False, True)))` and asserts
`{(r.state, r.pane, r.ownership, r.input_empty) for r in WRITE_RULES}` **equals** it, and that
`len(WRITE_RULES)` equals the size of that set (no duplicate keys). **Goes red** when `SessionState`,
`PaneKind` or `Ownership` grows and the table does not, **and** when a row is dropped or duplicated.
**`len(WRITE_RULES) == 96` on its own is forbidden** — it is the hand-maintained-list defect this repo
has shipped three times, and here a dropped `REFUSE_INPUT_NOT_EMPTY`/`CLEAR_THEN_SEND` row with a
duplicate elsewhere would pass while bytes went into a pane the policy meant to refuse. Note the
red-condition names the three **key** enums: `WriteDecision` is the **value** space and growing it
cannot break totality, which is what revision 1's red-condition got backwards;
`test_every_attached_key_refuses_with_no_pty` over all 48 attached keys — **goes red** if one
ownership cell drifts;
`test_decide_write_never_raises` over 500 mutated inputs including **non-members**, fed as
`cast(SessionState, "no-such-state")` and `cast(PaneKind, "")` — **`cast` is not `Any`, so
`disallow_any_explicit` holds** (K4), and a `# type: ignore` here would be a plan defect, not a
technique. **Goes red** if a lookup falls off the end instead of degrading;
`test_a_refusal_sends_no_bytes` (**P-M3-5**, added in revision 2) — **all three** refusal outcomes,
driven through **`LocalRunner` with a counting `run_argv`**, asserting the caller **reached the
refusal** (the returned `WriteDecision` equals the expected one and `last_refusal` is stamped)
*before* asserting zero calls. **Goes red** if a refusal is implemented as "send, then check", if the
count is zero because nothing ran, or if only the dialog cells are covered. Revision 1 named this
test in P-M3-5 and **created it in no task**, while its nearest neighbour covered only the dialog
cells — so a verifier matching on name would have scored one of the five mandatory mutation proofs
PASS. **Planted proof:** a `send-keys` call before the decision check in `orchestration/mailbox.py`;
`test_a_dialog_refuses_and_sends_no_bytes` — the `ScriptedRunner` **fast path**, kept beside the
proof above and never in place of it: `ScriptedRunner` has no `run_argv`, and `write` is one of ten
`Runner` members, so a stray `Enter` through `interrupt` leaves `writes == []` and the test green;
`test_an_attached_session_has_no_write_path` — **goes red** if any attached key returns anything but
`REFUSE_NO_PTY`, which would give Shepherd a write path into a pane on the user's own socket;
`test_a_non_empty_input_line_clears_then_re_reads_before_sending` — **goes red** if the re-read is
skipped, i.e. if `C-u` is sent and the text follows unconditionally, which is the concatenation D45
exists to prevent;
`test_every_write_rule_cites_an_existing_section` (P-M3-16) — **goes red** if a row's `evidence`
names a `data-schemas.md` section that does not exist;
`test_write_policy_reads_no_clock` (AST: no `datetime.now`, no `time.`, no `open(`) — **goes red** if
the policy starts timing out a dialog, which would make it impure and untestable as a table.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic for the table; the refusal proof runs `LocalRunner` with a
counting `run_argv` and **no tmux server** (`subprocess.run` is never reached).
**Exit Criteria:** the key set equals the 96-element product; all checks pass; boundary suite green;
the planted `send-keys` mutation proof recorded with its red output.
**Test Seams:** unit; the command seam (`run_argv`) for the refusal proof.

**Consumes:** `WriteDecision` (incl. `CLEAR_THEN_SEND`), `PaneKind`, `PaneState` (T2);
`SessionState`, `Ownership` (shipped, `core/states.py:22-33`); `LocalRunner`, `make_run_argv` (T8).
**Produces:**
```python
@dataclass(frozen=True) class WriteRule: state: SessionState; pane: PaneKind; ownership: Ownership; input_empty: bool; decision: WriteDecision; evidence: str
WRITE_KEY = tuple[SessionState, PaneKind, Ownership, bool]
WRITE_RULES: tuple[WriteRule, ...]        # one per key; the KEY SET is 4*6*2*2 = 96
def decide_write(state: SessionState, pane: PaneState, ownership: Ownership) -> WriteDecision: ...
def refusal_text(decision: WriteDecision) -> str: ...   # what the UI renders; never "failed"
```

---

### Task 14: `orchestration/mailbox.py` — one delivery path, coalesced and idempotent

**Objective:** D12's mailbox: enqueue, coalesce, deliver on `Stop` **or** on a prompt-ready pane
(D45), never twice.

**Files/Surfaces:**
- `src/shepherd/orchestration/mailbox.py` — new
- `tests/orchestration/test_mailbox.py` — new

**`signals/hook_lane.py` is NOT in this task's surfaces (revision 2).** Revision 1 had T14 add an
`on_stop_deliver` parameter to that file while **T12 added a `rebind` callback to the same file** —
T14 is Track D, T12 is Track C, and this plan's own hard rule is that no two tracks share a file,
because half of M1's blocker file is two builders in one file. **T12 now adds both parameters**;
T14 **consumes** `on_stop_deliver` and never opens the module.

**Dependencies:** T3, T4, T8, T12 (for `on_stop_deliver`), T13.
**No longer blocked on P1** — the clearing sequence is captured (`01b-after-ctrl-u.txt`, DP10).

**Allowed Scope:** `enqueue`, `coalesce` (pure), `deliver_now`, `sweep_pending`. All collaborators
injected.

**Out-of-Scope Drift:** channels (M6). A retry timer of its own — the two triggers are the schedule.
A sweep that polls **every** owned session: `sessions_with_pending()` returns the only ones worth a
`capture-pane`, so an empty mailbox costs one indexed query and **zero** tmux calls.

**Delivery, exactly:** trigger → `runner.pane(handle)` → `decide_write(...)`.

* `SEND_NOW` → `coalesce(pending)` → `runner.write(text)` then `runner.write(b"\r")` →
  `mark_delivered`.
* **`CLEAR_THEN_SEND`** → `send-keys -t <target> C-u` (a tmux **key name**, not `-l` literal text —
  that is the form the capture used, `steps.log` l.7) → **`runner.pane(handle)` again** → proceed to
  the `SEND_NOW` path **only if `input_text` is now empty**. If it is not, treat it as
  `REFUSE_INPUT_NOT_EMPTY`.
* Anything else → `record_refusal(ids, decision)`, count `AnomalyKind.MAILBOX_INPUT_NOT_EMPTY` where
  that is the decision, and leave the rows pending.

**Nothing is ever delivered onto a non-empty input line** (DP10). **The re-read is the whole safety
property**: it makes the clearing form unable to be worse than the refusing form, because a `C-u`
that did not work is indistinguishable from never having tried. This is why T13/T14 no longer wait on
P1 — `C-u` clearing a history-recalled prompt is captured (`01-after-raw-up.txt` → `01b-after-ctrl-u.
txt`), and the only unproven variant (the post-`Esc` restored prompt) degrades to the refusal the
re-read already implements.

**Expected Artifacts:** one module ≤ 250 lines.
**Required Checks:**
`test_a_repeated_idempotency_key_enqueues_once` — **goes red** if the unique index is relied on
without being caught, which would surface as a 500 rather than as an idempotent no-op;
`test_five_queued_messages_deliver_as_one_message_with_five_bullets` — **goes red** on five writes,
which is the interruption D12 exists to prevent;
`test_coalesce_loses_nothing` (every input text appears exactly once in the output) — **goes red** on
a truncation or a dedupe that silently drops;
`test_delivery_is_not_repeated_after_a_restart` — rebuild the `Store` from the same file between
delivery and the next sweep; **goes red** if pending is held in memory;
`test_an_interrupted_turn_still_delivers_at_the_next_prompt_ready_pane` — **goes red** if delivery is
keyed on `Stop` alone, which is D45's stall (A13: an interrupted turn emits no `Stop`);
`test_the_sweep_makes_no_tmux_call_when_the_mailbox_is_empty` — asserts `run_argv` was never called;
**goes red** on a sweep that polls the fleet;
`test_a_refusal_is_recorded_on_the_row` — **goes red** if `last_refusal` stays null, which is where
principle 5 lives for the write path;
`test_clear_then_send_re_reads_the_pane_before_the_text` — asserts the argv order
`send-keys … C-u` → `capture-pane` → `send-keys -l …`, through **`LocalRunner` with a counting
`run_argv`**; **goes red** if the re-read is dropped, which turns the clearing form into DP10's
option (a), "send `C-u` and hope";
`test_a_failed_clear_defers_and_counts_the_named_member` — a scripted pane that is still non-empty
after `C-u`; **goes red** if delivery proceeds, or if the count is a bare string rather than
`AnomalyKind.MAILBOX_INPUT_NOT_EMPTY` (T2).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, with `ScriptedRunner` and a `tmp_path` store; the argv-order
proofs use `LocalRunner` + a counting `run_argv` and start no tmux server.
**Exit Criteria:** all checks pass; **`signals/hook_lane.py` is untouched by this task** and its
M1/M2 call sites still work (T12 owns that file); full suite green.
**Test Seams:** unit; the store's verb seam; the command seam for argv order.

**Consumes:** `enqueue`, `pending_for`, `sessions_with_pending`, `mark_delivered`, `record_refusal`,
`mailbox_counts` (T4); `decide_write`, `refusal_text` (T13); `Runner.pane`, `Runner.write` (T5/T8);
`HookLane`'s `on_stop_deliver` parameter (**T12** — this task passes a callable to it and does not
edit `hook_lane.py`); `MailboxMessage`, `MailboxOrigin`, `COALESCE_BULLET` (T3);
`AnomalyKind.MAILBOX_INPUT_NOT_EMPTY` (T2).
**Produces:**
```python
def coalesce(messages: Sequence[MailboxMessage]) -> str: ...         # pure
def queue_message(*, store, session_id: str, body: str, origin: MailboxOrigin,
                  idempotency_key: str, now) -> MailboxMessage: ...
def deliver_now(*, store, runner, handle, session_id, state, ownership, now) -> WriteDecision: ...
def sweep_pending(*, store, runner, now, handles: Mapping[str, RunnerHandle]) -> MailboxCounts: ...
```

---

### Task 15: `orchestration/ask.py` — `ask()` via a headless fork

**Objective:** D13's synchronous question that never touches the target, on the evidence that
`can_fork = True` (ADR-M3-7, DP7).

**Files/Surfaces:**
- `src/shepherd/orchestration/ask.py` — new
- `src/shepherd/engines/claude_code/spawn.py` — `fork_argv` added (same module, same owner as T10;
  **no other track touches this file**)
- `tests/orchestration/test_ask.py` — new

**Dependencies:** T1 (**P2 decides the argv**), T4, T10, T14.

**Allowed Scope:** the fork path, the mailbox fallback, and the result record. One injected runner of
processes (the same `RunArgv` shape T8 defines), one injected clock, one timeout.

**Out-of-Scope Drift:** forking into a tmux pane (§9's letter; DP7 explains why not). **Deleting the
fork's transcript** — K3 forbids it and D13's "discard" means the session, not the file (**N6**).
Using the fork for anything but one question.

**The sequence:** create the row first (`origin=ask_fork`, `ephemeral=TRUE`, `depth = parent+1`) →
`claude --resume <engine_session_id> --fork-session -p <question> --no-session-persistence
--output-format json` → parse the result object → mark the row stopped → return.

**The two branches on P2's finding, and the corrected fallback (revision 2):**

* **P2 says `--session-id` is accepted** → pass `--session-id <uuid>`; the row is engine-bound
  **before** the process starts, exactly as a spawn is (C-M3-7).
* **P2 says it is refused** → the row is created with **`engine_session_id = None`** and bound
  afterwards from **the result object's own `session_id`**. Revision 1's fallback was "learn the
  fork's id from the sidecar keyed on the child pid", which **races a file the engine deletes**:
  `engines/claude_code/registry.py:3-5` documents the sidecar being written per running session and
  **deleted on exit**, and this plan relies on that deletion at DP2. T15 never polls during the run,
  so by the time `ask_session` has a result the sidecar is gone — the fallback would have read a file
  reliably absent. The result object is already parsed for the answer; the id is the same read.
  **Capture-proven on this exact argv:** `headless-20260914T160308Z/h5_fork.cmd.txt` is
  `claude --model … --output-format json --resume 55b21a24-… --fork-session -p …` and
  `h5_fork.stdout.json` carries `"type":"result"`, `"subtype":"success"`, `"is_error":false`,
  `"result":"FORKED"`, **`"session_id":"f0c208a0-76e1-4c07-bf1f-0c799409542d"`** — different from the
  resumed id, so it is the fork's own (A25).

**What that costs, stated rather than hidden.** `store/db.py::register_session` requires a non-null
`engine_session_id`, so **T4's `create_owned_session` must type it `engine_session_id: str | None`**
and T4's signature says so. On this branch the row is not engine-bound until the fork returns; it is
`ephemeral` **from birth** either way, which is what keeps the fork off the fleet page (DP2). If the
fork never returns, the row is an unbound `ask_fork` row that the startup reconcile leaves alone (it
has no pane) and that `doctor` shows — an honest dangling row, not a phantom session.

**Expected Artifacts:** one module ≤ 250 lines; one function added to T10's module.
**Required Checks:**
`test_the_fork_row_is_ephemeral_from_birth` — **goes red** if `ephemeral` is set after the process
starts, which is the window that puts an `ask` on the fleet page (DP2);
`test_the_method_is_reported_never_silently_downgraded` — **goes red** if `method` can be absent;
`test_the_fallback_is_the_mailbox_and_it_says_so` with `can_fork=False`;
`test_a_timeout_kills_the_fork_and_returns_a_readable_refusal` — **goes red** if a timeout leaves a
process behind, which on a fleet machine is a leak per call;
`test_the_fork_argv_has_no_shell_and_carries_no_settings_of_ours` (K5, and production passes no
`--settings`) — **goes red** on a single command string, which `argv-…/results.json` shows makes
`sh -c` expand `$()` and strip quotes, and on any `--settings` reaching a production argv;
`test_the_fork_id_comes_from_the_result_object_not_the_sidecar` — **goes red** if any code path opens
`<config_dir>/sessions/<pid>.json` for a fork; the engine **deletes it on exit**
(`registry.py:3-5`), so that read is a race this plan elsewhere depends on losing;
`test_an_unbound_ask_row_is_created_and_bound_afterwards` — exercises the P2-refused branch;
**goes red** if `create_owned_session` cannot take `engine_session_id=None`, which is the signature
change this branch forces;
`test_ask_needs_no_tmux` — asserts zero `tmux` argv lists; **goes red** if `ask()` grows a runner
dependency, which would make the one mind-reading capability fail when tmux is absent;
`test_from_fork_of_comes_from_our_own_row_not_from_the_transcript` (E-M3-33) — **goes red** if anyone
reads a `forkedFrom` field, which **does not exist**; the engine's only parent link is the original
`session_id` left on copied entries, and Shepherd's `parent_session_id` is written before the fork
even starts;
`test_every_ask_rule_cites_an_existing_section` — **goes red** if the result-object field names
(`result`, `session_id`, `is_error`) are asserted without `data-schemas.md` §Fork's field table,
which **P2 appends** (K1: no data shape asserted without a real captured example in the document);
**live** `test_the_target_transcript_is_unchanged` (T24) — sha256 before and after; **goes red** if
the target's transcript digest or hook count moves, which is C-M3-10's whole claim.
**Checkpoint Type:** none (AFK) — the human_verify was spent at T1, where P2 was read.
**Validation Level:** Deterministic here; one **Live** row at T24.
**Exit Criteria:** all checks pass; the argv matches P2's finding **verbatim**, and if P2 refused the
combination the fallback path is the one that ships and the plan's note says so.
**Test Seams:** unit.

**Consumes:** `create_owned_session` (**with `engine_session_id: str | None`**),
`rebind_engine_session_id`, `set_ephemeral` (T4); `queue_message` (T14);
`CLAUDE_CODE_CAPABILITIES`, `resolve_binary` (T10); `RunArgv`, `CommandResult` (T8);
`AnomalyKind.ASK_FORK_RESIDUE` (T2).
**Produces:**
```python
@dataclass(frozen=True) class AskResult:
    text: str | None; method: Literal["fork", "mailbox"]; from_fork_of: str
    duration_ms: int; refusal: str | None
@dataclass(frozen=True) class ForkResult:      # the parsed -p result object (A25, h5_fork.stdout.json)
    result: str | None; session_id: str; is_error: bool; subtype: str
def parse_fork_result(stdout: bytes) -> ForkResult | None: ...    # None degrades; never raises
def fork_argv(*, binary: str, engine_session_id: str, question: str,
              fork_session_id: str | None) -> list[str]: ...      # engines/claude_code/spawn.py
def ask_session(*, store, run_argv, now, session_id: str, question: str,
                timeout_ms: int = 120_000) -> AskResult: ...
```

---

### Task 16: `orchestration/dialogs.py` — answering a permission dialog (D44)

**Objective:** give D44's "answered only by an explicit `approve`/`deny` action" a real mechanism, and
refuse to invent the half that has no capture.

**Files/Surfaces:**
- `src/shepherd/orchestration/dialogs.py` — new
- `tests/orchestration/test_dialogs.py` — new

**Dependencies:** T1 (**P4 decides `deny`**), T6, T8, T13.

**Allowed Scope:** `answer_permission(session_id, choice)` for
`choice ∈ {approve, approve_always, deny}`, plus the `PERMISSION_DIALOG` precondition.

**Out-of-Scope Drift:** answering a **trust** dialog through this path — it is a different dialog with
different options and it gets its own function (`answer_trust`), because "Yes, I trust this folder"
is `Down` then `Enter` and mixing the two key maps is how the wrong one gets sent.

**What ships, and why it is asymmetric:** `approve` is `Enter`, which selects the highlighted default
`1. Yes` — **capture-proven** (`B-hooks.json`, `B-file-created.txt`). `approve_always` and `deny`
need `2` and `3`, and *"text starting with a digit typed into a permission dialog"* is in §Not
verified. So until **P4** lands, `approve_always` and `deny` **refuse with a reason naming P4**.
Guessing a keystroke here is not a style question: the failure mode is a key that lands on
`1. Yes` and approves a tool the human never saw.

**Expected Artifacts:** one module ≤ 150 lines.
**Required Checks:**
`test_approve_sends_exactly_one_enter` — **goes red** on any extra key, including a "clear the line
first" convenience, which at a dialog is discarded text followed by an approval;
`test_deny_refuses_until_p4` (or, after P4, `test_deny_sends_the_captured_key`) — **goes red** if a
guessed keystroke ships;
`test_answering_requires_a_permission_dialog_pane` — **goes red** if the precondition is dropped and
an `Enter` lands at an ordinary prompt, submitting whatever is in the box;
`test_trust_and_permission_use_different_key_maps` — **goes red** if one function serves both;
`test_every_dialog_rule_cites_an_existing_section` (P-M3-16) — **goes red** if a `PERMISSION_KEYS`
entry's `evidence` names a `data-schemas.md` section that does not exist, which is how a guessed
keystroke would get in;
`test_an_absent_sidecar_is_counted_not_assumed_clear` — **goes red** if a missing sidecar is read as
"no dialog open"; the sidecar is **absent by design** during the trust dialog (DP8), so the gate must
count `AnomalyKind.SIDECAR_ABSENT` and refuse rather than infer.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, with `ScriptedRunner`.
**Exit Criteria:** all checks pass; if P4 did not land, `deny`'s refusal text names the probe and a
`doctor` line counts the refusals.
**Test Seams:** unit.

**Consumes:** `PaneKind`, `PaneState` (T2); `Runner.pane`, `Runner.write` (T5/T8); `decide_write` (T13).
**Produces:**
```python
PermissionChoice = Literal["approve", "approve_always", "deny"]
def answer_permission(*, store, runner, handle, session_id: str, choice: PermissionChoice,
                      now) -> WriteDecision: ...
def answer_trust(*, store, runner, handle, session_id: str, trust: bool, now) -> WriteDecision: ...
PERMISSION_KEYS: Mapping[PermissionChoice, tuple[str, ...]]   # only captured keys are present
```

---

### Task 17: `web/ws.py` — the hand-rolled RFC 6455 WebSocket (D51)

**Objective:** own ~200 lines of framing rather than pretend a dependency is free. The host has
**no** WebSocket library and **no pip** (`websockets`, `wsproto`, `aiohttp`, `tornado`,
`simple_websocket` all absent), and a stdlib handshake plus a masked-frame round-trip is
**capture-proven** to work.

**Files/Surfaces:**
- `src/shepherd/web/ws.py` — new
- `tests/web/test_ws.py` — new

**Dependencies:** none. Track E, runnable from day 1.

**Allowed Scope:** the handshake (`Sec-WebSocket-Key` → `Accept`), frame parse/build for binary,
text, ping/pong and close, masking, continuation frames, a payload cap, and the origin check.
**No capability resolution here** — the handler is handed a stream object.

**Out-of-Scope Drift:** extensions (`permessage-deflate`). Server-initiated masking (RFC 6455 forbids
it). Resolving a session or importing anything below L4 — that is T18's tool, and the boundary test
fails otherwise.

**Expected Artifacts:** one module ≤ 300 lines.
**Required Checks:**
`test_the_handshake_matches_rfc6455_and_checks_origin` against the captured exchange
(`websocket-…/handshake.json`: `Sec-WebSocket-Accept: e1dFrKT8fv/yzhkYZ+5wPsDLWK4=`) — **goes red** if
the digest algorithm or the magic GUID is wrong;
`test_a_cross_origin_handshake_is_refused`, with one case per origin form (absent, `null`, a LAN
address, a different port) — **goes red** if any is accepted (§13);
`test_an_unmasked_client_frame_is_rejected` — **goes red** on the common shortcut of trusting the mask
bit;
`test_frames_round_trip_for_every_length_class` (0, 1, 125, 126, 127, 65 535, 65 536) — **goes red** on
the 16/64-bit length boundary, which is where hand-rolled framers break;
`test_a_payload_over_the_cap_closes_with_1009` — **goes red** if a client can allocate without bound;
`test_ws_resolves_no_capability_itself` (AST: no import below L4) — **goes red** if the handler starts
reaching for `runner/`.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — a loopback socket pair in-process; no browser needed and none
available.
**Exit Criteria:** all checks pass; `mypy --strict` clean; boundary suite green.
**Test Seams:** unit.

**Consumes:** none.
**Produces:**
```python
WS_MAGIC: str
MAX_FRAME_BYTES: int
def accept_key(client_key: str) -> str: ...
def handshake_response(headers: Mapping[str, str], allowed_origins: frozenset[str]) -> bytes | None: ...
def parse_frame(buffer: bytes) -> tuple[Frame | None, int]: ...
def build_frame(payload: bytes, *, opcode: int) -> bytes: ...
@dataclass(frozen=True) class Frame: opcode: int; payload: bytes; fin: bool
class WebSocketClosed(Exception): ...
```

---

### Task 18: `toolsurface/tools_m3.py` and the routes — M3's capabilities

**Objective:** register every M3 capability once, as a `ToolDef`, so `web/` and `cli/` reach them
through `invoke()` and M4's gate lands under existing tests (D32, D35, D38).

**Files/Surfaces:**
- `src/shepherd/toolsurface/tools_m3.py` — new
- `src/shepherd/web/routes.py` — new GET routes, the first POST routes, and one WS path
- `src/shepherd/web/server.py` — POST dispatch and the WS upgrade (the origin check already exists)
- `tests/toolsurface/test_tools_m3.py`, `tests/web/test_routes_m3.py` — new

**Dependencies:** T11, T12, T13, T14, T15, T16, T17.

**Allowed Scope:** the tools below and their routes. Every `input_schema` is validated at registration
(D53), and every handler returns a projection — **never a raw row** (§13).

**Out-of-Scope Drift:** `authorize()` or an audit entry (M4 — but the `blast_class` values are set
correctly **now**, which is what makes M4 a no-caller-changes addition). A second read path into the
store from `web/`. Widening `ToolResult`. **Registering `rename_session`** — see below.

**`rename_session` is registered by T20, not here (revision 2).** Revision 1 had T18 register a tool
whose handler T20 **produces**, while **T20 depends on T18** — so T18's `Consumes` block named no
rename verb at all, which falsified this plan's own self-review claim that every `Consumes` symbol
appears verbatim in exactly one earlier `Produces`. The fix registers the tool where the function is
written: **T20 registers its own tool**, the way T21 adds its own counters and T22 its own event name.
This leaves `T20 ◄── T18` intact and inverts no edge. T18 still owns `POST_ROUTES`, and the
`/api/sessions/{session_id}/rename` entry **stays here** — a route is a path→name table, and the name
it points at is resolved through `invoke()` at call time, so the route may be declared before the tool
is registered. `test_every_post_route_resolves_to_a_registered_tool` (T23, after both have run)
catches the case where it never is.

| Tool | Blast | Audiences | Notes |
|---|---|---|---|
| `spawn_session` | `local_write` | MASTER, SESSION, HUMAN | caps enforced inside (§11) |
| `send_to_session` | `local_write` | MASTER, SESSION, HUMAN | the write policy decides; the result **names the decision** |
| `ask_session` | `local_write` | MASTER, SESSION, HUMAN | returns `AskResult` |
| `interrupt_session` | `local_destructive` | MASTER, HUMAN | |
| `kill_session` | `local_destructive` | MASTER, HUMAN | records before killing |
| `answer_permission` | `local_destructive` | HUMAN | D44; `deny` may refuse until P4 |
| `get_session_output` | `local_read` | all | owned → the `capture-pane -p` screen (**N12**); attached → the transcript tail (M2's reader) |
| `terminal_snapshot` | `local_read` | HUMAN | bytes, base64 in JSON; raw over the WS |
| `terminal_write` | `local_write` | HUMAN | D40: a human's keystrokes, allowed at both levels |
| `terminal_resize` | `local_write` | HUMAN | |
| `terminal_stream` | `local_read` | HUMAN | returns a `TerminalStream` handle (ADR-M3-3) |
| `list_mailbox` | `local_read` | MASTER, HUMAN | pending, delivered, deferred, and `last_refusal` |

**Expected Artifacts:** one module ≤ 450 lines; the route table extended.
**Required Checks:**
`test_every_m3_tool_declares_a_blast_class_and_audiences` — **goes red** on a missing field, which
`ToolDef` already makes a type error, and on an audience set that hands a tier-2 session a
`local_destructive` tool (§11: "a tier-2 session cannot kill anything");
`test_every_input_schema_validates_at_registration` (D53) — **goes red** on a schema
`create_sdk_mcp_server` would silently mangle;
`test_no_handler_returns_a_raw_row` (AST over the handlers) — **goes red** on a spread of a dataclass
into a response (§13);
`test_send_to_session_reports_the_decision` — **goes red** if a refusal is rendered as a generic
failure, which is what makes `REFUSE_DIALOG` invisible;
`test_the_route_table_declares_every_query_and_body_field` — **goes red** if an undeclared parameter
can be smuggled past `invoke()`;
`test_a_post_without_a_matching_origin_is_refused` — **goes red** if the inherited check is not
applied to the new verb;
inherited `test_consumer_boundary` — **goes red** if `web/` imports `runner/` or `orchestration/`;
inherited `test_no_read_tool_touches_a_log_path` (K14) — **goes red** if a terminal tool reaches into
`logs/`.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, through `invoke()` with a `tmp_path` store and `ScriptedRunner`.
**Exit Criteria:** all checks pass; M1's and M2's route tests pass **unchanged**; boundary suite green.
**Test Seams:** integration (`invoke()`).

**Consumes:** `spawn_owned_session` (T11); `record_and_terminate`, `interrupt_session` (T12);
`decide_write`, `refusal_text` (T13); `queue_message`, `deliver_now`, `mailbox_counts` (T14);
`ask_session` (T15); `answer_permission`, `answer_trust` (T16); `Frame`, `build_frame` (T17);
`ToolDef`, `BlastClass`, `Audience`, `invoke`, `arg_str` (shipped).
**Produces:**
```python
def register_m3_tools(store: Store, runner: Runner, now: Callable[[], str]) -> None: ...
    # the twelve tools in the table above. `rename_session` is NOT among them: T20 registers it
    # (register_rename_tool), because T20 produces the handler and T20 depends on T18.
@dataclass(frozen=True) class TerminalStream:
    session_id: str
    def chunks(self) -> Iterator[bytes]: ...
    def close(self) -> None: ...
# web/routes.py
API_ROUTES  gains: "/api/sessions/{session_id}/output" -> "get_session_output"
                   "/api/mailbox"                      -> "list_mailbox"
POST_ROUTES: Mapping[str, str] = {
    "/api/sessions":                          "spawn_session",
    "/api/sessions/{session_id}/send":        "send_to_session",
    "/api/sessions/{session_id}/ask":         "ask_session",
    "/api/sessions/{session_id}/interrupt":   "interrupt_session",
    "/api/sessions/{session_id}/kill":        "kill_session",
    "/api/sessions/{session_id}/rename":      "rename_session",
    "/api/sessions/{session_id}/permission":  "answer_permission",
}
BODY_ARGS: Mapping[str, tuple[str, ...]]
TERMINAL_WS_PATH = "/api/sessions/{session_id}/terminal"
```

---

### Task 19: the terminal in the browser — vendoring `xterm.js` and the session page

**Objective:** §12's page 3: the real terminal bytes, the header band, the action buttons when the
session is stopped, and the rename affordance.

**Files/Surfaces:**
- `src/shepherd/web/static/vendor/xterm.js`, `.../vendor/xterm.css` — **vendored**, with
  `vendor/VERSION.txt` recording the version, the source URL and a sha256
- `src/shepherd/web/static/terminal.js`, `.../session.js` — new
- `src/shepherd/web/static/index.html`, `.../app.css` — extended
- `pyproject.toml` — `"shepherd.web" = ["static/*", "static/vendor/*"]` (the current glob is
  **single-level**, so a vendored subdirectory would be absent from a wheel — M1's T16-2 returning)
- `tests/web/test_session_page.py`, `tests/test_packaging.py` — new / extended
- `tests/web/test_ws.py` — **extended (T17 created it).** This task is the **one owner** of
  `test_the_first_frame_is_the_snapshot_byte_for_byte`; revision 1 let both T17's and T19's check
  lists claim it while Flow C named this file, so the test had two homes and no owner

**Dependencies:** T17, T18.

**Allowed Scope:** plain ES modules, no build step (D51). `xterm.js` is the **only** runtime
dependency (K8) and is vendored, never fetched at runtime.

**Out-of-Scope Drift:** an addon (`fit`, `webgl`) — each is another vendored file and none is needed
for a fixed-size pane. A framework. Routing pty bytes through `innerHTML` (§13 forbids it by name).
Re-rendering a transcript instead of the bytes (§9: "not a re-render of a transcript").

**T19-a — the manual checklist (the vendoring is a host risk, not a coding one):**
1. Is a prebuilt ESM `xterm.js` obtainable on this machine at all? There is no npm and no network
   guarantee.
2. If yes: record version, URL, sha256 in `vendor/VERSION.txt`; confirm it is a **module** (`export`),
   not a UMD bundle expecting a loader.
3. If no: **the degrade ships instead** — the pane renders `capture-pane -p` text in a `<pre>` via
   `textContent`, refreshed on SSE, with one line saying *"live terminal unavailable: xterm.js is not
   vendored"*. This is a real product state, not a stub, and its test is listed below.
4. Either way, write the outcome into Progress notes.

**Expected Artifacts:** two new static modules, one vendored pair or a recorded refusal, one page.
**Required Checks:**
`tests/web/test_ws.py::test_the_first_frame_is_the_snapshot_byte_for_byte` (P-M3-10) — **one owner:
this task**; over **the six `.ansi` captures**, named in full at P-M3-10 (this is *not* T6's set of
six, which overlaps in four). **Goes red** if the snapshot is decoded, escaped or re-encoded anywhere
between `capture-pane` and `term.write`. **It does not prove what `capture-pane` returns on this
host** — that is T24's live `test_the_live_snapshot_frame_is_the_bytes_capture_pane_returned`
(P-M3-17), and clause 10 now says which proof carries which half;
`test_no_unescaped_interpolation_in_frontend` (inherited) over the new files — **goes red** on any
`innerHTML` interpolation that is not `escapeHtml`-wrapped;
`test_pty_bytes_never_reach_innerHTML` (AST over the new JS) — **goes red** if the terminal's data
path touches the DOM-as-HTML;
`test_the_terminal_degrades_to_a_screen_view_when_the_vendor_file_is_absent` — **goes red** if a
missing vendor file yields a blank pane instead of the honest message;
`test_the_vendor_file_ships_in_a_built_wheel` — builds the wheel and lists it; **goes red** on the
single-level glob, which is the exact defect M1 shipped once;
`test_a_renamed_session_says_local_only` — **goes red** if the marker is dropped while
`can_set_title` is `False` (D29, DP1);
`test_an_attached_session_shows_the_read_only_banner` with §9's wording — **goes red** if an attached
session renders a live terminal instead of the banner, which would offer a write path into a pane on
the user's own socket (K6);
`test_the_page_does_not_re_derive_the_order` (inherited) — **goes red** if the session page starts
sorting in JavaScript.
**Checkpoint Type:** **human_verify** — a human reads the vendoring outcome and, if a browser is ever
available, the rendering. **The rendering is not verifiable on this host (G-M3-6).**
**Validation Level:** Deterministic for every server-side and DOM-free claim; **Manual** for
rendering, with the checklist above.
**Exit Criteria:** all deterministic checks pass; `vendor/VERSION.txt` present **or** the degrade
shipped and recorded; the wheel test green.
**Test Seams:** unit (the static files are parsed, not executed — the host has no JS runtime).

**Consumes:** `TERMINAL_WS_PATH`, `POST_ROUTES` (T18); `escapeHtml` from `escape.js` (shipped).
**Produces:** `web/static/terminal.js` (`openTerminal(sessionId, el)`),
`web/static/session.js` (`renderSession(row)`), `vendor/VERSION.txt`.

---

### Task 20: rename — the ratchet, the marker, and the write-back that ships disabled (DP1)

**Objective:** §16's "rename + the `can_set_title` probe (D29)", decided out loud and **not applied**.

**Files/Surfaces:**
- `src/shepherd/orchestration/rename.py` — new
- `src/shepherd/toolsurface/tools_m3.py` — **`register_rename_tool` appended** (see below)
- `tests/orchestration/test_rename.py` — new
- `tests/orchestration/test_degradation.py` — new (**P-M3-9's orchestration half**)
- `tests/e2e/test_live_rename.py` — new (**the probe §18 asked for**)

**Dependencies:** T4, T8, T13, T18.

**Allowed Scope:** the local ratchet (always), the confirmation reader (always),
`drive_engine_rename` (built, tested live, **unreachable in production** while
`CLAUDE_CODE_CAPABILITIES.can_set_title` is `False`), **the registration of the `rename_session`
tool**, and **P-M3-9's orchestration degradation suite**.

**This task registers its own tool (revision 2).** Revision 1 had T18 register `rename_session` while
T20 produced the handler — and **T20 depends on T18**, so the symbol was consumed before it was
produced and T18's `Consumes` block named no rename verb at all. Registering it here is the same
shape T21 uses for its counters and T22 for its event name, it leaves `T20 ◄── T18` intact, and it
inverts no dependency edge. The `blast_class` is `local_write` and the audiences are
`MASTER, HUMAN` — declared here, unchanged from T18's table row.

**This task also owns P-M3-9's orchestration half**, because it is the **last** task to create an
`orchestration/` module (`rename.py`) and therefore the first point at which the whole population
exists. `test_orchestration_degrades_and_counts` enumerates every public callable under
`src/shepherd/orchestration/` with `iter_modules()` — **the plan's own count is 17** — and **asserts
the enumerated count equals 17**, so a module that stops being covered fails here rather than
silently. Revision 1 named this test in P-M3-9 and created it in no task at all.

**Out-of-Scope Drift:** **flipping the flag** — DP1's recommendation is stated and not applied, and
`test_can_set_title_ships_false` fails the build if anyone does. Writing an `ai-title` entry
(DP1 option 4: wrong channel, undetermined precedence, and a write into a file the engine owns).
Renaming an **attached** session through the engine (G-M3-5; the probe was declined because it risks
two writers on one transcript).

**How the write-back works, for the reviewer who will approve or reject it:**
`send-keys -l -- "/rename <title>"` then `Enter`, **only** at a `PROMPT_READY` pane — delivered
mid-turn it would be enqueued and reach the model as *text* (E-M3-9). The engine then writes
`custom-title` + `agent-name` itself; **no hook fires**. Confirmation is a read of the registry
sidecar's `name`/`nameSource` through the parser that already ships (`registry.parse_sidecar`), with
`#{pane_title}` (`✳ <title>`) as corroboration. `title_synced_at` is stamped **only** on
`nameSource == "user"` with a matching name — never on a successful send.

**Expected Artifacts:** one module ≤ 200 lines; one live test.
**Required Checks:**
`test_user_beats_engine_and_never_reverts` over all nine source pairs — **goes red** if the ratchet
is implemented as last-writer-wins, which the discovery loop would then undo on its next sweep;
`test_no_keys_are_sent_while_can_set_title_is_false` (`ScriptedRunner.writes == []`) — **goes red** the
moment the flag is honoured in one place and not another;
`test_title_synced_at_requires_a_confirmation` — **goes red** if a send stamps it, which is precisely
the "silent half-success" D29 forbids;
`test_a_rename_is_refused_at_a_busy_pane` — **goes red** if a slash command can be queued;
`test_can_set_title_ships_false`, whose failure message names DP1 — **goes red** if anyone flips the
flag without a recorded approval, which is the one thing this task forbids by name;
`test_the_per_session_predicate_refuses_an_attached_session_even_with_the_ceiling_true` (**DP1
option 3**) — constructs capabilities with `can_set_title=True` and an **attached** session and
asserts the rename stays local; **goes red** if the predicate is a comment rather than code, which is
what would make DP1's "one-line reversal" claim false;
`test_rename_session_is_registered_by_this_task_and_not_by_tools_m3s_bulk_register` — **goes red** if
the tool reappears in `register_m3_tools`, which is the double-registration `invoke()` would refuse
at freeze time (ADR-7);
`test_orchestration_degrades_and_counts` (**P-M3-9**) — enumerates every public callable under
`src/shepherd/orchestration/`, **asserts the enumerated count is 17**, and drives each with the
degradation set (absent sidecar, empty capture, non-UTF-8 bytes truncated at every byte boundary of a
whole capture, a dead pane, a missing server, `tmux` absent). **Asserts its own computed case count
equals the constant it states.** **Goes red** if any entry point raises, if a degradation is counted
as a bare string rather than a named `AnomalyKind` member, if the population shrinks below 17, or if
the asserted and generated counts disagree;
**live** `test_typing_rename_makes_the_engine_write_custom_title` — spawns a throwaway owned session,
types `/rename`, and asserts the transcript gains `custom-title` **and** `agent-name`, the sidecar
reports `nameSource:"user"`, and `#{pane_title}` becomes `✳ <title>`. **This test is §18's probe**;
its recorded output is what a reviewer reads before considering the flip.
**Checkpoint Type:** **decision** — the live test's evidence is recorded and DP1 is left for a human.
No builder flips the flag.
**Validation Level:** Deterministic, plus one **Live** test.
**Exit Criteria:** deterministic checks pass; the live test's evidence recorded in Progress notes;
`can_set_title` still `False`.
**Test Seams:** unit; live.

**Consumes:** `apply_title`, `set_title_synced_at` (T4); `Runner.pane`, `Runner.write` (T5/T8);
`decide_write` (T13); `ToolDef`, `BlastClass`, `Audience`, `register` (shipped, via T18's pattern);
`parse_sidecar`, `RegistryEntry` (shipped); `TITLE_SOURCE_RANK` (shipped);
`AnomalyKind` (T2, for the degradation suite).
**Produces:**
```python
def rename_session(*, store, runner, handle, session_id: str, title: str, now,
                   capabilities: EngineCapabilities, ownership: Ownership) -> RenameOutcome: ...
    # the DP1 option-3 predicate lives here: capabilities.can_set_title
    #   and ownership is Ownership.OWNED and handle is not None
def drive_engine_rename(*, runner, handle, title: str) -> WriteDecision: ...   # unreachable while can_set_title is False
def confirm_engine_title(*, config_dir: Path, pid: int, title: str) -> bool: ...
@dataclass(frozen=True) class RenameOutcome: title: str; source: TitleSource; synced_at: str | None; local_only: bool
def register_rename_tool(store: Store, runner: Runner, now: Callable[[], str]) -> None: ...
    # registers the `rename_session` tool: local_write, audiences (MASTER, HUMAN).
    # NOT registered by register_m3_tools (T18) — this task produces the handler.
```

---

### Task 21: ownership reconcile — closing T19-1 (DP2)

**Objective:** stop a hooked `claude -p` run from putting a finished row on the fleet page, without
touching D47.

**Files/Surfaces:**
- `src/shepherd/signals/discovery_loop.py` — the `sdk-cli` `continue` becomes a reconcile
- `src/shepherd/toolsurface/tools_m1.py` — two `doctor`/status counters (l.181 reads
  `sdk_cli_skipped` today)
- `src/shepherd/cli/commands.py` — **l.375 renders `sdk_cli_skipped`; revision 1 omitted this file**,
  and a counter added in two of its three sites is a counter that disagrees with itself
- `tests/signals/test_discovery_loop.py`, `tests/toolsurface/test_tools_m1.py`,
  `tests/cli/` — extended
- `docs/plans/2026-09-17-m2-BLOCKERS.md` — T19-1's disposition appended (append-only)

**Dependencies:** T4, T11, T15.

**What happens to the shipped `sdk_cli_skipped` counter (revision 2 — revision 1 did not say).**
**It stays, and keeps its meaning**: *every `sdk-cli` registry entry the sweep saw and did not
register.* It is the **denominator**, and the two new counters partition what happened to each one:
`sdk_cli_reconciled` (a row existed and was marked `ephemeral`) and — implicitly — entries with no
row at all. `sdk_cli_missed` counts the **other** population: `-p` runs that exited before any sweep
saw them, so the sidecar was already deleted. The three are reported **together**, because
`reconciled` alone would read as coverage and it is not. `test_the_three_sdk_cli_counters_are_reported_together`
asserts that; **goes red** if `sdk_cli_skipped` is silently dropped or if only the flattering one is
rendered — which is this repo's dominant defect wearing a new hat.

**Allowed Scope:** for a registry entry whose `entrypoint` is `sdk-cli`, look up
`get_session_by_engine_id`; if a row exists and is not already `ephemeral`, set `ephemeral = TRUE` and
count `sdk_cli_reconciled`. Rows the sweep never saw are counted `sdk_cli_missed`. **Registration is
unchanged** — D47 still accepts the first event of any kind.

**Out-of-Scope Drift:** reading `entrypoint` from the transcript on the ingest path (option 1: a file
open on the 3.4 ms lane, which D24 keeps evidence off). Suppressing registration (option 4: reopens
D47's failure mode). Deleting the row — a `-p` run genuinely happened, and `ephemeral` is §7's own
word for "real, and not on the board by default".

**Expected Artifacts:** ~20 changed lines and two counters.
**Required Checks:**
`test_an_sdk_cli_row_is_reconciled_to_ephemeral` — **goes red** if the `continue` returns;
`test_registration_still_accepts_the_first_event_of_any_kind` (D47, inherited) — **goes red** if the
reconcile leaks into the hook lane;
`test_an_owned_session_is_never_reconciled_to_ephemeral` — **goes red** if the match is done on `kind`
rather than `entrypoint`, which is `interactive` for a `-p` run too (E35's whole point);
`test_a_short_p_run_is_counted_as_missed_not_as_reconciled` — **goes red** if the counter lies about
coverage, which is this repo's dominant defect wearing a new hat;
`test_doctor_reports_all_three_counters` — `sdk_cli_skipped`, `sdk_cli_reconciled`, `sdk_cli_missed`;
**goes red** if any is hidden, **or** if `cli/commands.py:375`'s line disagrees with
`tools_m1.py:181`'s mapping, which is what happens when a counter is added in two of its three sites;
`test_discovery_does_not_duplicate_an_owned_session` (**P-M3-8**, added in revision 2) — a
pre-registered owned row plus a registry entry for the same engine session; asserts
`SELECT count(*) … WHERE engine_session_id = ?` is exactly **1** after a sweep. **Goes red** if
`get_session_by_engine_id` is bypassed or if the reconcile registers rather than updates. Revision 1
named this test in P-M3-8 and in the risk matrix and **created it in no task**.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic, with a throwaway `engine_config_dir` of sidecar fixtures.
**Exit Criteria:** all checks pass; M1's and M2's discovery tests pass **unchanged**; T19-1's
disposition appended to the M2 ledger.
**Test Seams:** unit.

**Consumes:** `set_ephemeral` (T4); `RegistryEntry`, `is_attached_interactive`,
`SDK_CLI_ENTRYPOINT`, `discovery_pass`, `DiscoveryStatus`, `DiscoveryStatus.sdk_cli_skipped`
(shipped).
**Produces:** `DiscoveryStatus` gains `sdk_cli_reconciled: int` and `sdk_cli_missed: int`.
**`sdk_cli_skipped` is retained, unchanged in meaning**, and all three are rendered together by
`tools_m1.py` and `cli/commands.py`.

---

### Task 22: `PostToolBatch` — closing T18-2, the entry M1 re-pointed to M3

**Objective:** execute M1's preserved four-item checklist, which M3 is the first milestone able to
satisfy honestly: it spawns a real session with an explicit `--settings <throwaway>`, so the dry-run
diff is reviewed against a file that is **not** the user's and K3 holds by construction.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/events.py` — `SUBSCRIBED_EVENTS` 24 → 25
- `src/shepherd/toolsurface/tools_m1.py` — the `idle` counter line becomes real numbers
- `tests/cli/test_doctor_idle_counters.py`, `tests/engines/test_hooks_install.py` — updated
- `docs/plans/2026-09-16-m1-BLOCKERS.md` — the disposition appended (append-only)

**Dependencies:** T11 (a real spawn), T24's fixtures.

**Allowed Scope:** **M1's checklist, verbatim:** add the name to `SUBSCRIBED_EVENTS`; re-review the
installer's dry-run diff against a **throwaway** settings file; re-run `test_hookd_latency_under_10ms`
against E34's 3.2 ms budget; assert the real settings file's sha256 is unchanged.

**The diff is taken against a POPULATED copy, not the shipped `{}` (revision 2).**
`tests/e2e/conftest.py:103-109` writes `settings.write_text("{}\n")` — its docstring says so: *"an
explicit, empty settings file"*. A merge dry-run reviewed against `{}` **cannot exhibit the
bad-merge-with-a-populated-file risk this task exists to check**: there is nothing to merge into, no
pre-existing `hooks` key, no user entry to preserve, and none of `hooks_config.py`'s three stated
properties (marking, backup-write-validate-restore, refusing what it did not understand) is
exercised. T24 provides the populated fixture: a throwaway copy carrying **Shepherd's own installed
block** — produced by the shipped `install_hooks(settings_path, entry)`, never hand-written — plus one
**foreign** entry on `PreToolUse` that the diff must leave untouched. **The real
`~/.claude/settings.json` (sha256 `375e5322…`) is still never read and never written**; the populated
copy lives in the throwaway directory.

**Out-of-Scope Drift:** touching the user's `~/.claude/settings.json` (K3 — the reason this entry
exists). Subscribing anything else while in the file. Deleting the `idle` reporting before the
counters can actually move.

**If any step fails, the entry is re-pointed to M6 with the failure recorded** — it is not quietly
left, and `doctor` keeps saying `idle` rather than `0`.

**Expected Artifacts:** one name, one `doctor` line, two ledger appends.
**Required Checks:**
`test_post_tool_batch_is_subscribed` replaces `test_post_tool_batch_is_still_not_subscribed`, and the
**replacement names this task** — **goes red** if the name is removed again;
`test_the_two_refusal_counters_can_now_move` — drives a `PostToolBatch` frame and asserts a counter
increments; **goes red** if the counters are still structurally dead, which is the only thing that
makes this task worth doing;
`test_hookd_latency_under_10ms` (inherited, re-run against E34's 3.2 ms budget) — **goes red** if the
25th event costs measurable time on the hot path;
`test_the_installer_diff_is_reviewed_against_a_populated_throwaway_file` — **goes red** if any test
path resolves to the real settings file, **and** if the file the diff is taken against has no
pre-existing `hooks` key, because a diff against `{}` proves only that a merge into nothing works;
`test_a_foreign_hook_entry_survives_the_subscription_change` — **goes red** if the added 25th event
disturbs an entry Shepherd does not own, which is `hooks_config.py`'s first stated property and the
one `{}` could never test;
the inherited per-test sha256 guard (`375e5322…`) — **goes red** on any byte change to the real file.
**Checkpoint Type:** **human_verify** — a human reads the dry-run diff before it is applied anywhere.
**Validation Level:** Deterministic for the subscription and the counters; **Manual** for the diff
review; **Live** for the latency re-run.
**Exit Criteria:** 25 subscribed, counters moving, latency inside budget, the real settings file
byte-identical, both ledgers appended — **or** a recorded re-point to M6.
**Test Seams:** unit; live.

**Consumes:** `SUBSCRIBED_EVENTS` (shipped); `install_hooks`, `HookEntry`, `InstallResult` (shipped,
`engines/claude_code/hooks_config.py`); **`installed_settings` — T24's POPULATED throwaway-settings
fixture**, not the shipped `{}` one.
**Produces:** `SUBSCRIBED_EVENTS` at 25 names; `doctor` reporting real counts.

---

### Task 23: composition — six new capabilities into a root with ZERO spendable lines

**Objective:** wire M3 into the process **without adding a single line to `controld.py`**.

**The budget, measured rather than assumed (revision 2).** `controld.py` is **140** lines.
`tests/daemons/test_controld_composition.py` asserts
`lines <= MAX_DAEMON_LINES(150) − RESERVED_FOR_M2(10)` = **140**. It is exactly on its budget:
**there are zero spendable lines.** Revision 1's T23 claimed "≤ 5 lines in the root" **and** "the
reserve intact" — mutually exclusive, and the guard would have gone red on the first line. Its
`Files/Surfaces` also listed the guard test as "extended", which quietly permits weakening a check to
make a plan item fit (forbidden by K11 and K17).

**Decision: the root grows by zero lines**, and here is the mechanism, so it is not left to a builder
at 2am:

1. **`compose_tool_surface` constructs the runner itself.** It already receives `store` and `host`
   (`controld.py:74`: `compose_tool_surface(store, host, db_path, ingest)`), which is everything a
   `LocalRunner` needs — the socket from `store`'s `app_state` under `RUNNER_SOCKET_KEY` (RD1), the
   `detached_launch()` prefix from `host`. **No new argument, no new line.**
2. **It returns a frozen `M3Wiring(runner, sweep)`.** Line 74 becomes
   `wiring = compose_tool_surface(store, host, db_path, ingest)` — an assignment on the **same
   physical line**, not a new one.
3. **The sweep rides `run_discovery_loop` through the dict that already exists.** `scan_args`
   (`controld.py:86-87`) gains `"sweep": wiring.sweep` on its existing second physical line, which is
   ~75 characters today against a file that already carries a 104-character import at line 30.
4. **The startup reconcile (T12) runs inside `compose_tool_surface`**, before the registry is frozen,
   for the same reason: the root never learns it exists.

**If a builder judges zero genuinely impossible, that is a named plan change, never an
improvisation**: re-target the reserve explicitly — rename it (it is `RESERVED_FOR_M2` and M2 has
shipped; its docstring itemises wiring that is now in the tree, so the *justification* is stale even
though the *number* still binds), state the new number, and itemise what each line buys. **Weakening
`MAX_DAEMON_LINES` or `RESERVED_FOR_M2` is not that change** and is forbidden.

**Files/Surfaces:**
- `src/shepherd/toolsurface/compose.py` — the runner, the tools, the reconcile and the mailbox sweep
- `src/shepherd/daemons/controld.py` — **two existing lines edited; zero lines added**
- `src/shepherd/signals/discovery_loop.py` — the sweep piggy-backs the 2.0 s cadence it already owns
- `tests/daemons/test_controld_composition.py` — **READ, not weakened.** `MAX_DAEMON_LINES` and
  `RESERVED_FOR_M2` keep their values; the only permitted change is *adding* the constants test below
- `tests/daemons/test_controld.py` — extended

**Dependencies:** T8, T12, T14, T18, T20, T21.

**Allowed Scope:** construct one `LocalRunner` **inside `compose.py`** (socket from `app_state`,
default `shepherd-runner`, host from the `host` already passed, `run_argv` from
`make_run_argv(permitted_sockets(socket))`), register the M3 tools, call `register_rename_tool`
(T20), run `reconcile_owned_panes` (T12) before the registry freezes, and hand `sweep_pending` to the
loop that already runs. **The root keeps the order; `compose.py` keeps the composition** (ADR-1,
M2 T18-3).

**Out-of-Scope Drift:** a fourth thread. A second socket. Logic in the root — ADR-1's 150-line cap is
a **proxy** for "no logic in a composition root", and the reserve is a proxy for "the next change can
be additive". **Spending the reserve to fit is the failure T18-3 closed, and editing the guard's
constants is worse than spending it.**

**Expected Artifacts:** ~35 lines in `compose.py`; **`wc -l controld.py` still 140**.
**Required Checks:**
`test_the_composition_root_keeps_headroom_under_adr1s_cap` (inherited, **unmodified**) — **goes red**
if the root grows by even one line, because it is at 140 of 140;
**`test_the_line_budget_constants_are_unchanged`** (new) — asserts `MAX_DAEMON_LINES == 150` and
`RESERVED_FOR_M2 == 10`; **goes red** if a builder edits the guard to make the wiring fit, which is
the K11/K17 failure this task is most exposed to and the one revision 1's "extended" quietly
permitted;
`test_the_composition_builds_the_runner_and_the_root_never_names_it` — asserts `controld.py` imports
no `LocalRunner`, no `make_run_argv` and no `register_` name (the shipped
`test_the_composition_root_registers_no_capability_itself` already covers the last); **goes red** if
a tool builds its own runner, which would give the process two sockets' worth of state;
`test_the_registry_is_frozen_before_the_server_binds` (ADR-7, inherited) — **goes red** on any
registration after bind, including T20's `register_rename_tool`;
`test_every_post_route_resolves_to_a_registered_tool` — **goes red** if
`/api/sessions/{id}/rename` points at a name nothing registered, which is the failure mode of
splitting T18's route from T20's registration;
`test_the_reconcile_runs_before_the_registry_freezes` — **goes red** if an orphaned pane can take a
cap slot before it is counted;
`test_the_mailbox_sweep_runs_on_the_existing_loop` — **goes red** if a fourth thread appears;
`test_no_new_socket_is_bound` — **goes red** if the terminal opens a second listener (**DP4**, §13);
inherited `test_composition_root` boundary rule — **goes red** if the root grows a branch.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic.
**Exit Criteria:** all checks pass; **`wc -l src/shepherd/daemons/controld.py` is still 140**;
`MAX_DAEMON_LINES` and `RESERVED_FOR_M2` unchanged at 150/10; full suite green; `mypy --strict` clean.
**Test Seams:** integration.

**Consumes:** `LocalRunner`, `make_run_argv` (T8); `reconcile_owned_panes` (T12);
`register_m3_tools` (T18); `register_rename_tool` (T20); `sweep_pending` (T14);
`compose_tool_surface`, `log_root`, `transcript_root`, `publish_result` (shipped);
`permitted_sockets` (T5).
**Produces:**
```python
@dataclass(frozen=True) class M3Wiring: runner: Runner; sweep: Callable[[], MailboxCounts]
def compose_tool_surface(store, host, db_path, ingest) -> M3Wiring: ...
    # SAME signature as shipped; it now RETURNS instead of returning None, so controld.py:74
    # becomes an assignment on the same physical line. Zero root lines added.
RUNNER_SOCKET_KEY: str    # an app_state key, default "shepherd-runner" (RD1, D49)
```

---

### Task 24: the live lane — one real owned session, end to end

**Objective:** prove the claims no fixture can: a real trust dialog, a real pane, a real stop with a
real exit code, a real fork that leaves its target untouched, and a pane that survives a `controld`
restart.

**Files/Surfaces:**
- `tests/e2e/conftest.py` — a `tmux_live` fixture, a TUI-shaped `Throwaway.tui_argv`, and an
  **`installed_settings`** fixture that writes Shepherd's **real** hook block (see below)
- `tests/e2e/test_live_owned_session.py`, `.../test_live_ask_fork.py` — new
  (`.../test_live_rename.py` is T20's)
- `tests/e2e/test_live_attached_session.py` — `test_no_tmux_is_invoked_at_all` was **removed by T5**,
  which put its rule in `tests/boundaries/`; this task adds the **narrower live second check**

**Dependencies:** T11, T12, T15, T18, T20, T23.

**Allowed Scope:** the live lane's existing isolation (throwaway workdir + explicit `--settings` +
the autouse per-test sha256 guard + XDG relocation) **plus** tmux on socket `shepherd-m3-live`, with
`-L` on every invocation and a session-scoped teardown that **asserts the socket has no server**.

**The `installed_settings` fixture, and why the shipped one is not enough (revision 2).** The shipped
`throwaway` fixture writes `settings.write_text("{}\n")` — `tests/e2e/conftest.py:103-109`, docstring
*"an explicit, empty settings file"*. **A session spawned with `--settings {}` emits no hooks to
Shepherd at all.** So revision 1's `test_a_spawn_registers_exactly_one_row` asserted `count == 1` in a
world where the second writer could never run: a **vacuous pass**, and acceptance clause 2's "after
the hook lane has run" was simply false.

`installed_settings` therefore writes the **M1 installer's own output** into the throwaway directory:
`install_hooks(throwaway.settings, entry)` where `entry` is a `HookEntry` built from
`host.hook_dispatch(ingest_socket)` — the shipped path, marked `_shepherd_managed`, validated after
the write by `hooks_config.py`'s own post-write check. **Never a hand-written imitation**: the shape
`docs/probes/2026-09-14-schemas/tmux-tui/make_settings.py` demonstrates is the *probe's* block, and
what this lane must exercise is **Shepherd's**. The fixture additionally plants one **foreign**
`PreToolUse` entry, which T22's diff must leave untouched.

**`throwaway` (empty) is kept** for the tests that genuinely want no hooks; `installed_settings`
composes on top of it. **The real `~/.claude/settings.json` is still never touched** — the autouse
per-test guard asserts sha256 `375e5322…` before and after every test in the lane, and the populated
file lives only in `tmp_path`.

**Out-of-Scope Drift:** `CLAUDE_CONFIG_DIR` (M1 Finding 3: it breaks authentication). Asserting a
session **count** (the real config dir means the user's own sessions are visible — M1's F10).
A timing assertion (a live test that fails is investigated, never retried into green). **Deleting**
`test_no_tmux_is_invoked_at_all`.

**The replacement rule, where it lives, and why revision 1's placement made it ineffective.** The
shipped test asserts *no tmux anywhere in `tests/e2e/`*, which M3 makes impossible. Revision 1
replaced it in place — but **`tests/e2e/test_live_attached_session.py:47` carries a module-level
`pytestmark = pytest.mark.live`**, so the strongest blast-radius rule in the tree was **deselected on
every `-m "not live"` run**, and its `Path(__file__).parent.glob("*.py")` walked **one directory**
while P-M3-15 claimed "every tmux invocation in `tests/`".

**T5 owns the replacement**, in `tests/boundaries/test_tmux_blast_radius.py` — deterministic,
unmarked, **in the default run** — walking `tests/**/*.py` **and** `docs/probes/**/*.py` recursively.
**T24 keeps a narrower live second check**,
`test_every_tmux_call_in_the_live_lane_names_a_throwaway_socket`: every tmux argv the live lane
actually **issues** (observed through the lane's `make_run_argv`, not scanned from source) names a
`^shepherd-m3-` socket. Source-scanning and call-observing catch different things, which is why both
exist. **Mutation proof required on the boundaries rule**: plant `-L shepherd` in a live test and
confirm red. The old rule forbade a tool; the new pair forbids the blast radius, which is what K6 is
actually about.

**The six live tests:**

| Test | Proves |
|---|---|
| `test_an_untrusted_directory_stops_on_the_trust_dialog_and_no_key_is_sent` | C15, E-M3-1, C-M3-5 — the fixture's workdir is fresh, so the dialog is **real**. Asserts `state == needs_you` **before** asserting zero `run_argv` calls |
| `test_a_spawn_registers_exactly_one_row` | C-M3-7, P-M3-8 — uses **`installed_settings`**, and **asserts a `SessionStart` was actually received** (the ingest count moved) before asserting `count == 1`. With the shipped `{}` fixture this test could not fail |
| `test_a_real_stop_carries_an_exit_code` | E-M3-16 — **G-M2-2 closed for owned sessions** |
| `test_the_pane_survives_a_controld_restart` | D14, DP5 — stop and restart `controld`; `has-session` still true |
| **`test_the_live_snapshot_frame_is_the_bytes_capture_pane_returned`** *(new, P-M3-17)* | C-M3-9's real basis. Runs the real `capture-pane -e -p -S -2000` through the lane's `make_run_argv` against an owned pane, frames it, and asserts the WS frame payload **equals those bytes**. P-M3-10's deterministic test reads a checked-in file, frames it, and compares to the same file — which proves the framer does not mutate and **nothing about what `capture-pane` returns here**. tmux is `3.4` in both the captures and on this host, so the format is stable; the **path** is what was unproven |
| `test_the_target_transcript_is_unchanged` (ask) | C-M3-10, P-M3-11 — sha256 before and after |

**Expected Artifacts:** two new live modules, two new fixtures, one live second check.
**Required Checks:** the six above, plus
`test_the_live_socket_has_no_server_at_teardown` — **goes red** if a run leaks a session onto a shared
machine, which is the hygiene the 2026-09-14 probes proved with `teardown.txt`. Teardown is
`kill-session` per session, then **one `kill-server` on `shepherd-m3-live`**, which `check_tmux_argv`
permits because the socket matches `^shepherd-m3-` (K6, K6-a) — the idiom every shipped probe used,
now bounded by a predicate rather than forbidden outright;
`test_every_tmux_call_in_the_live_lane_names_a_throwaway_socket` — observed through the lane's
`make_run_argv`, not scanned from source; **goes red** if any issued argv names another socket;
`test_the_installed_block_is_the_installers_own_output` — asserts the fixture's file was produced by
`install_hooks` and carries `_shepherd_managed`; **goes red** on a hand-written imitation, which would
let the lane pass against a block Shepherd does not actually install;
the inherited per-test sha256 guard on every new test — **goes red** on any byte change to
`~/.claude/settings.json` (`375e5322…`).
**Checkpoint Type:** **human_verify** before the first run — a human confirms the socket names and the
teardown, once, because the blast radius of getting this wrong is §18's incident.
**Validation Level:** **Live** — `.venv/bin/pytest tests/e2e -m live -q`. Default run is unchanged:
`.venv/bin/pytest -m "not live" -q` — **and it now includes the blast-radius rule**, which T5 put in
`tests/boundaries/` precisely so it is not deselected.
**Exit Criteria:** M1's 7 and M2's 5 live tests still pass; M3's **7** (six here plus T20's) pass;
`tmux -L shepherd-m3-live ls` reports no server; `tmux -L shepherd ls` unchanged; the real
`~/.claude/settings.json` byte-identical at `375e5322…`.
**Test Seams:** live/e2e.

**Consumes:** everything M3 produced; `Throwaway`, `settings_guard`, `shepherd_home`, `LIVE_MODEL`,
`CLAUDE_TIMEOUT_S` (shipped); `install_hooks`, `HookEntry` (shipped,
`engines/claude_code/hooks_config.py`); `make_run_argv`, `permitted_sockets` (T8/T5).
**Produces:**
```python
LIVE_TMUX_SOCKET = "shepherd-m3-live"
@pytest.fixture(scope="session") def tmux_live() -> Iterator[str]: ...   # asserts no server at teardown
@pytest.fixture() def installed_settings(throwaway: Throwaway) -> Path: ...
    # Shepherd's REAL block via install_hooks(...), plus one foreign PreToolUse entry.
    # Consumed by T22's diff review and by test_a_spawn_registers_exactly_one_row.
def tui_argv(self, brief: str | None) -> list[str]: ...                 # Throwaway, TUI-shaped
```

---

## Live Verification Strategy

**Why a live lane at all.** Six of M3's claims cannot be proved in `tmp_path`: a **real** trust
dialog (it only appears in a directory Claude Code has never trusted), a **real** exit code (it comes
from a pane that really died), a **real** `/rename` reaching `custom-title` (the engine writes it,
not us), a **real** fork leaving its target byte-identical, a pane that survives a **real** `controld`
restart, and — added at revision 2 — **the bytes a real `capture-pane` returns on this host**, which
a checked-in file compared to itself cannot show. M1 built the lane and it passes 7 tests; M2 added 5;
M3 adds **7** (six in T24, one in T20).

**What the live lane is *not* asked to carry (revision 2).** The blast-radius rule that protects the
user's socket lives in `tests/boundaries/`, **not here** — `tests/e2e/`'s module-level
`pytestmark = pytest.mark.live` would deselect it on every ordinary run, which is what revision 1
shipped: the strongest rule in the tree, never executed by the CI-equivalent command. T24 keeps only
a narrower live second check, which observes the argvs the lane actually issues.

| Field | Value |
|---|---|
| **Command** | `.venv/bin/pytest tests/e2e -m live -q` |
| **Default run** | `.venv/bin/pytest -m "not live" -q` — the live lane is excluded, as M1 set it up |
| **Isolation** | throwaway working directory + explicit `--settings`. **Not** `CLAUDE_CONFIG_DIR`: M1's probe Finding 3 proved `CLAUDE_CONFIG_DIR=<throwaway>` gives `Not logged in`, rc=1 — isolation and authentication are mutually exclusive on this host |
| **Guard** | the real `~/.claude/settings.json` sha256 asserted **per test**, not per suite (M1's F10 lesson) |
| **tmux** | **used, on `shepherd-m3-live`, with `-L` on every invocation including teardown.** Never `shepherd`. Never `shepherd-runner` (that is the product's socket, and a test must not share it). **Teardown is `kill-session` per session, then one `kill-server` on `shepherd-m3-live`, then an assertion that the socket reports no server.** The `kill-server` is permitted because `check_tmux_argv` requires a `^shepherd-m3-` socket for it (K6, K6-a) — revision 1 banned the verb outright, which was *stricter than CLAUDE.md* and would have pushed a builder whose "assert no server" failed toward the bare form that caused 2026-09-12. The user's `aivisor`, `main` and `spike` are on `shepherd` and are never named, never listed after step 0b, never touched |
| **hooks** | **Shepherd's real installed block**, written into the throwaway settings file by the shipped `install_hooks(...)` (`installed_settings`, T24), plus one foreign `PreToolUse` entry the installer must leave alone. The shipped `{}` fixture is kept for tests that want no hooks — but a test that asserts registration **must** use the populated one, because with `{}` a spawned session emits no hooks and the assertion cannot fail |
| **Blast radius** | one `claude` process per test in a throwaway directory; one tmux session on a throwaway socket; no write outside `$XDG_DATA_HOME/shepherd` and the throwaway directory |
| **What a run leaves behind** | Claude Code's own bookkeeping: a `~/.claude.json` trust entry for the throwaway directory and a transcript under `~/.claude/projects/-tmp-…`. The same durable side effects the 2026-09-14 probe suite accepted, named so a reader knows. **Nothing is deleted** (K3) |
| **Flake policy** | a live test that fails is **investigated, never retried into green**. No timing assertions are permitted in this lane: if the failure is the engine being slow, the assertion was wrong |
| **What it does not prove** | **the terminal renders.** There is no browser on this host (**G-M3-6**). Every server-side byte is asserted; the picture is not. Acceptance clause 11 says so in words |
| **Checkpoint** | human_verify before the first run (T24), then AFK |

---

## Verification strategy (critical_path requirement)

**The gate function.** A task is done when its Required Checks pass **and** the whole suite passes.
M2 shipped 869 tests and M3 touches `core/`, `store/`, `signals/`, `toolsurface/` and `web/`; a task
that leaves the suite red has not finished, whatever its own file says.

| Level | Where | Command |
|---|---|---|
| **Deterministic** | every task | `.venv/bin/pytest <paths> -q` |
| **Type** | every task | `.venv/bin/mypy --strict src/shepherd` — no `Any`, `disallow_any_explicit` |
| **Boundary** | every task touching `core/`, `runner/`, `orchestration/`, `engines/`, `signals/`, `web/`, `cli/`, `daemons/` | `.venv/bin/pytest tests/boundaries -q`, **with no new exemption** (K11) |
| **Contract** | T7, T9 | `.venv/bin/pytest tests/contracts -q` — one suite, every implementation |
| **Golden regression** | T12, T21 | M2's 429-event table byte-identical for every existing kind |
| **Live** | T1, T9 (server rows), T10 (`--help`), T20, T22, T24 | `.venv/bin/pytest tests/e2e -m live -q` |
| **Manual** | T19-a (vendoring), T22 (the dry-run diff) | the checklists in those tasks |

**Probabilistic: none.** M3 adds no timing-sensitive assertion. The spawn poll has a timeout, not a
deadline, and no test asserts how long anything took.

**The mutation discipline is mandatory here, not advisory (K17).** Two independent reviews on
2026-09-17 ran mutation testing and found **4 of 8 mutations surviving 72 green tests**. For each of
**P-M3-1, P-M3-2, P-M3-5, P-M3-7, P-M3-15**, plant a real violation **in `src/`** (not only in a
fixture), run, confirm red, revert, and record the red output in Progress notes. **Revision 2 adds
three indirection plants**, because a plant that uses the spelling the rule already looks for
demonstrates only the case never in doubt. The seven planted violations are named in their tasks:

| Property | Plant | Where | Which net must catch it |
|---|---|---|---|
| P-M3-1 | `["tmux", "list-sessions"]` | `runner/local.py` (T5) | AST **and** runtime |
| P-M3-1 | **`from .tmux_cmd import TMUX_BIN; [TMUX_BIN, "ls"]`** (fixture `runner_tmux_via_constant_import.py`) | `runner/local.py` (T5) | **runtime only** — the AST rule misses it **by design**, and that asymmetry is the proof the two nets are not the same net. This argv carries **no `-L`**, which is the exact blast radius of 2026-09-12 |
| P-M3-2 | the literal `"kill-server"` | any `src/` module (T5) | AST **and** runtime |
| P-M3-2 | **`f"kill-{verb}"`** (fixture `runner_kill_server_via_fstring.py`) | any `src/` module (T5) | **runtime only** |
| P-M3-5 | a `send-keys` call before the decision check | `orchestration/mailbox.py` (**T13** owns `test_a_refusal_sends_no_bytes`; T14 re-runs it) | the counting `run_argv`, **not** `ScriptedRunner.writes` |
| P-M3-7 | `os.kill(pid, signal.SIGINT)` | `runner/local.py` (T8) | AST with origin resolution |
| P-M3-15 | `-L shepherd` | a live test (rule owned by **T5**, in `tests/boundaries/`) | AST, **in the default run** |

**Revision 1's planted proofs planted the spelling the rule already looks for**, so four of the seven
rows above did not exist and the three that did demonstrated only the case never in doubt. The three
indirection rows are the ones that matter, and each is a checked-in fixture rather than a scratch
edit, so the proof survives the session that ran it.

**A check that cannot fail has not checked.** Three of this repo's recorded defects were *checks*:
a negative self-check that early-returned before opening the file; a rule pinned to one spelling
defeated by a one-line alias; and a scan whose stated scope (`src/shepherd/`) exceeded its real scope
(4 of 79 files). Every rule M3 adds is scanned over **every** module found by `iter_modules()`, never
over a hand-named list.

**Evidence array, per task:** command run, exit code, counts (`N passed, M skipped`), and for a
planted proof the **red output**. "Tests pass" without the counts is not evidence.

---

## Dependency graph and the six tracks

```
        step 0: drift_check.py --record        step 0b: six reality re-checks
                              │
     ┌─────────────┬──────────┴─────────┬──────────────┬──────────────┐
     │             │                    │              │              │
  T1 PROBES     T2 core/runner       T3 core/mailbox  T7 host        T17 web/ws
  (P1–P4)          │                  + migration 003   (7th member)  (RFC 6455)
  live, gated      │                    │              │              │
     │             ├────────────────────┴──────┐       │              │
     │             │                           │       │              │
     │          T5 runner/base + tmux_cmd    T4 store verbs           │
     │             │   (K6 made mechanical)    │                      │
     │          T6 runner/pane                 │                      │
     │             │                           │                      │
     │          T8 runner/local ◄── T6, T7     │                      │
     │             │                           │                      │
     │          T9 ScriptedRunner + contract   │                      │
     │             │                           │                      │
     │          T10 engines/spawn ◄── T2       │                      │
     │             │                           │                      │
     │          T11 orchestration/spawn ◄── T4, T8, T10                │
     │             │                                                  │
     │          T12 lifecycle ◄── T4, T8, T11                          │
     │             │                                                  │
     └──► T13 write_policy ◄── T2, T6, T8   (NOT P1 — C-u is captured)   │
              │                                                        │
     ┌────────┼─────────────┬──────────────┐                          │
     │        │             │              │                          │
   T14 mailbox  T15 ask   T16 dialogs      │                          │
   ◄─T3,T4,T8,  ◄─P2,T4,   ◄─P4,T6,T8,     │                          │
     T12,T13     T10,T14      T13          │                          │
     └──────────┴─────────────┴────────────┼──────────────────────────┘
                                           │
                                  T18 tools_m3 + routes ◄── T11…T17
                                           │
              ┌────────────────┬───────────┴──────┬────────────────────┐
              │                │                  │                    │
        T19 terminal UI   T20 rename         T21 reconcile       T23 composition
        ◄── T17, T18      ◄── T4, T8,        ◄── T4, T11, T15    ◄── T8, T12, T14,
                              T13, T18                               T18, T20, T21
                                │                  │                    │
                                └──────────────────┴────────┬───────────┘
                                                            │
                                    T24 live lane ◄── T11, T12, T15, T18, T20, T23
                                                            │
                                    T22 PostToolBatch ◄── T11, T24
```

**Three edges changed in revision 2, and one ambiguity in the old diagram is removed.**

| Edge | Was | Now | Why |
|---|---|---|---|
| `T13 ◄── P1` | present | **removed** | `C-u` is capture-proven (`01b-after-ctrl-u.txt`); the clearing row ships and the post-`C-u` re-read handles the unproven variant. T13 gains `◄── T8` for `LocalRunner` + a counting `run_argv`, which is where P-M3-5's refusal proof is taken |
| `T14 ◄── T12` | absent | **added** | T12 now owns **both** `hook_lane.py` parameters; T14 consumes `on_stop_deliver` and never opens the file |
| `T20`'s position | drawn hanging off T13's row, with `T20 ◄── T18` implied by an arrow that also seemed to run the other way | **drawn under T18 with the other three T18-dependants** | T20 depends on T18 and **registers its own `rename_session` tool**, so nothing flows back up. The old drawing was the visual form of the same confusion that let T18 register a handler T20 produced |
| `T23 ◄── T12, T20` | absent | **added** | `compose.py` calls `reconcile_owned_panes` (T12) and `register_rename_tool` (T20) |

**Six tracks, five of which are workable in parallel from day 1** — the property that made M1's and
M2's overnight runs survivable:

- **Track P — probes.** T1 alone. Gates **T15 (P2) and T16 (P4)**, informs DP9 (P3), and **no longer
  gates T13** — `C-u` was already captured, so P1 narrowed to `C-a C-k`, `C-w` and the post-`Esc`
  prompt, none of which the shipped code waits on. It is
  first because a probe that runs after the code it decides is a rewrite, not a probe.
- **Track A — vocabulary and schema.** T2 → T3 → T4. `core/`, `store/`, migration files.
- **Track B — the runner.** T5 → T6 → T8 → T9, with T7 beside them. `runner/`, `host/`, `testkit/`.
- **Track C — the engine and the spawn sequence.** T10 → T11 → T12. `engines/claude_code/spawn.py`,
  `orchestration/spawn.py`, `orchestration/lifecycle.py`.
- **Track D — the write path.** T13 → T14, T15, T16, T20. `orchestration/` (different files from
  Track C).
- **Track E — the browser.** T17 → T19, plus T18 as the convergence. `web/`, `toolsurface/`.
- **Track F — closure.** T21, T23, T24, T22. `signals/discovery_loop.py`, `compose.py`,
  `controld.py`, `tests/e2e/`, `events.py`.

**No two tracks share a file.** A hard rule, not a preference: half of M1's blocker file is two
builders in one file.

**Every file more than one task touches, named — revision 2 (revision 1 named one, and it was not
even the dangerous one):**

| File | Tasks | Tracks | Disposition |
|---|---|---|---|
| `src/shepherd/signals/hook_lane.py` | **T12 only** | C | **Was T12 (Track C) *and* T14 (Track D) — a real violation of the hard rule, with no dependency edge between them.** T12 now adds **both** defaulted parameters; T14 consumes and gains `◄── T12`. The callback is renamed `on_engine_session_rebound` because `HookLane._rebind` already exists at l.149 |
| `src/shepherd/engines/claude_code/spawn.py` | T10, T15 | C, D | Written by T10, extended by T15 (`fork_argv`). **T15 ◄── T10**, so never concurrent |
| `src/shepherd/toolsurface/tools_m1.py` | T21, T22 | F, F | **Same track**, and T22 ◄── T24 ◄── … ◄── T21, so ordered. Named because revision 1's "the one file two tasks touch" was false |
| `src/shepherd/signals/discovery_loop.py` | T21, T23 | F, F | **Same track**; T23 ◄── T21 |
| `src/shepherd/toolsurface/tools_m3.py` | T18, T20 | E, D | T20 appends `register_rename_tool`; **T20 ◄── T18** |
| `tests/web/test_ws.py` | T17, T19 | E, E | **Same track**; T19 ◄── T17. `test_the_first_frame_is_the_snapshot_byte_for_byte` has **one owner: T19** (revision 1 let two tasks' checks claim it) |
| `tests/e2e/test_live_attached_session.py` | T5, T24 | B, F | T5 **removes** `test_no_tmux_is_invoked_at_all` (its rule moves to `tests/boundaries/`); T24 adds the narrower live check. **T24 ◄── T23 ◄── T8 ◄── T5**, so ordered |
| `src/shepherd/core/anomalies.py` | **T2 only** | A | All seven M3 members land in one append, by one owner |

`orchestration/` is shared by Tracks C and D at the *package* level and by no single file.

**The convergence points are T13, T18, T23 and T24**, and each has a single owner. **T22 is last** and
depends on T24's fixtures; the graph is acyclic (T24 does not depend on T22, and `list_owned_panes`
sits on the `Runner` seam rather than in `lifecycle.py` **specifically** so T11's pane-counting cap
does not need T12, which depends on T11).

**A blocker in any one track leaves four workable.** T2 is the only broad dependency, and it is a
types-only module with no logic. **T1 now blocks two tasks, not three** — T13 was released when `C-u`
turned out to be captured — and if a probe cannot run, T15/T16 ship their fallback forms (DP7's
result-JSON binding, DP8's refuse-rather-than-guess) and the milestone continues.

---

## Plan Completeness Gate — self-check before save

1. **Every task has a test that verifies completion.** ✓ — 24 tasks, each with a named
   `Required Checks` list. **Red-conditions: the tick is now a count, not a claim.** Revision 1 ticked
   "every check states what would make it go red" while **sixteen** checks carried none (T5×2, T8×1,
   T13×5, T15×2, T16×1, T19×1, T22×1, T23×1, T24×2). Revision 2 **wrote red-conditions for all
   sixteen** and added them to every check it introduced. The honest statement is therefore:
   *every check in every task now names a red-condition, and the count was 16 short at revision 1* —
   which is a checkable sentence, where "✓ every check" was not.
2. **Every task lists exact file paths.** ✓ — every `Files/Surfaces` entry is a path.
3. **Every task has checkable exit criteria.** ✓ — "N pass; `mypy --strict` clean; boundary suite
   green with no new exemption", never "done".
4. **Dependencies are explicit task ids.** ✓ — the graph is acyclic, verified by walking it; **two**
   near-cycles are resolved and stated: T22 ↔ T24 (T24 does not depend on T22), and T11 ↔ T12 (the
   pane-counting cap, resolved by putting `list_owned_panes` on the `Runner` seam rather than in
   `lifecycle.py`). Four edges changed at revision 2 and each is tabled beside the diagram.
5. **Scope drift is named per task.** ✓ — and the two drifts the milestone is defined by are named at
   the level of individual forbidden actions: flipping `can_set_title` (T20) and sending a key during
   a spawn (T11).
6. **Consumes/Produces are verbatim-matched.** ✓ — see the self-review below.
7. **Validation level stated for every task.** ✓ — 18 Deterministic, 4 with a Live row, 2 with a
   Manual checklist, and the **Live Verification Strategy** section exists.
8. **Risk-based testing matrix complete.** ✓ — 26 rows; every high/high and high/med row carries a
   deterministic test; the three rows whose mitigation is a checklist are the vendoring (host risk),
   the dry-run diff (a human must read a diff), and step 0b.
9. **No placeholders or TBD.** ✓ — where a value is unknown it is a named gap (G-M3-1…9) with a
   disposition and, where one exists, a probe.
10. **Open decisions listed, not hidden in prose.** ✓ — **none**. **Nine** Decision pressures
    (DP1–DP4, DP6–DP10), of which **DP1 is recommended and explicitly NOT APPLIED**, plus DP5 kept as
    a **record** that D55 was amended to own seven things and names detached launch itself. Nine
    Recommended Defaults, each explicitly unapproved.
11. **Every provable property names a test that exactly one task creates.** ✓ *(revision 2 — this
    check did not exist at revision 1 and five properties failed it: P-M3-5, P-M3-8's deterministic
    half, P-M3-9's second half, P-M3-14, and P-M3-16's spawn-argv variant. All five now have a task.)*
12. **No number is carried inconsistently.** ✓ *(revision 2 — the write policy's key space was 48 in
    four places and 96 in fact; `Runner` was "nine members" in five places and is now ten. Both are
    now single-valued throughout.)*

**Prefactor question applied.** Four abstractions were proposed and rejected: an `EngineAdapter`
Protocol (**DP6** — one adapter, and D9 names the mistake); a `TerminalSession` manager class (one
caller — the WS handler — and no state beyond the stream it already holds); a `DialogAnswerer`
seam (two dialogs, two key maps, one function each, and a shared interface would invite the mixed
key map T16 forbids); and a `MailboxPolicy` Protocol beside `decide_write` (zero second
implementations). Two abstractions were **kept** because each has two or more callers in this plan:
**`Runner`** (D36 names it, `LocalRunner` and `ScriptedRunner` both implement it, and §14.2 requires
the suite) and **`tmux_argv`** (every runner member plus the tests and the probe harness call it, and
the single spelling is what makes K6 checkable).

---

## Self-review — cross-phase contract drift

Every `Consumes` entry checked verbatim against the `Produces` that supplies it, and against the
shipped code for M1/M2 symbols. Findings, all fixed inline before save:

- **`interrupt_session` collided with itself.** T12 produces
  `orchestration/lifecycle.py::interrupt_session` and T18 registers a **tool** named
  `interrupt_session`. Two namespaces, one word — the same hazard M2 recorded for `replay`.
  **Fixed:** the tool's handler is a thin adapter and the module function keeps the name; T18's
  `Consumes` names `record_and_terminate, interrupt_session (T12)` explicitly, and the tool table
  lists tool names only. No module imports both unqualified.
- **`ByteStream` vs `TerminalStream`.** T5 produces a `ByteStream` Protocol (a runner-level stream of
  pane bytes); T18 produces a `TerminalStream` dataclass (an L4 handle). **Fixed:** different names,
  different layers, and T18's `Consumes` does not name `ByteStream` — the tool holds a `Runner` and
  calls `attach()`, so only one of the two crosses any given boundary.
- **`session_name` vs `RunnerHandle.session_name`.** A function and a field. **Fixed:** the function
  lives in `runner/tmux_cmd.py` and is always called qualified; the field is only ever reached through
  a handle. Stated here because a future reader will meet both in one file (T8).
- **`SessionSpec` was nearly defined twice.** T2 puts it in `core/runner.py`; T10 needs it for
  `spawn_argv`. **Fixed:** T10 `Consumes` it and defines nothing — M1's BLOCKER T7b-1 was exactly two
  structurally identical types written by two builders.
- **`EngineCapabilities` shape vs §6's.** §6 types `effort_ladder: list[str]`; T2 produces
  `tuple[str, ...]`. **Fixed and flagged**: frozen dataclasses need hashable fields, the values are
  constants, and the change is recorded here rather than discovered at `mypy` time.
- **`CommandResult` / `RunArgv` are produced by T8 and consumed by T15.** `ask()` runs a process and
  is not a runner. **Fixed:** T15 `Consumes` them by name from T8 rather than declaring its own
  subprocess helper — one spelling of "run an argv list and get bytes back" in the whole codebase.
- **`WriteDecision` crosses four tasks** (T13 produces, T14/T16/T20 consume, T18 renders).
  Checked verbatim in all five places, including `refusal_text`, which T18 needs so a refusal reaches
  the UI as a sentence rather than as a generic failure.
- **`EXPECTED_SCHEMA_VERSION` is produced by T3 and read by `sessiond`.** §7 rule 3 says `sessiond`
  waits for `controld` to report it. **Checked:** `daemons/sessiond.py` takes it as a required
  argument, so the bump is a one-line change with no second site.
- **`discovery_pass`'s counters.** T21 adds two fields to `DiscoveryStatus`, which `_as_mapping`
  serialises into `app_state` and `doctor` renders. **Checked:** both consumers read the mapping, so
  adding a key is additive and no existing key moves.

**Revision 2 additions — what the first self-review missed, and why.**

- **`rename_session` was consumed before it was produced.** T18 registered the tool; T20 produced the
  handler; **T20 depends on T18**. T18's `Consumes` block named **no rename verb at all**, so the
  first self-review's own criterion ("every `Consumes` symbol appears verbatim in exactly one earlier
  `Produces`") was satisfied *vacuously* — the symbol was never consumed, it was just used.
  **Fixed:** T20 registers its own tool (`register_rename_tool`); T18 keeps the route; T23 asserts
  `test_every_post_route_resolves_to_a_registered_tool`. No edge inverted.
  **Lesson recorded:** a self-review that only checks named `Consumes` entries cannot see a symbol
  used without being named. The gate item added at Completeness Gate 11 checks the property directly.
- **`hook_lane.py` was edited by two tracks.** T12 (Track C) and T14 (Track D), no edge between them,
  against this plan's own hard rule. The first self-review checked *symbols*, not *files*.
  **Fixed:** T12 owns both parameters; T14 consumes; a shared-file table now exists beside the tracks.
- **`HookLane._rebind` already exists** (`hook_lane.py:149`, called from l.92) and T12's callback was
  also `rebind`. **Fixed:** `on_engine_session_rebound`. This is the same hazard M2 recorded for
  `replay`, found this time only by reading the shipped file.
- **`run_argv_subprocess` became `make_run_argv(permitted)`** (ADR-M3-8), because the permitted-socket
  set must be a construction argument and not a module global. T8 produces it; T13, T23 and T24
  consume it; C-M3-1 and C-M3-9 name it. Checked in all five places.
- **`create_owned_session`'s `engine_session_id` is now `str | None`**, forced by DP7's corrected
  fallback. T4 produces the signature; T11 always passes a uuid; T15 is the only caller that may pass
  `None`, and T4 asserts that (`test_an_owned_spawn_never_creates_an_unbound_row`).
- **`Runner` gained a tenth member, `list_owned_panes`, with `PaneRef`.** T5 produces both; T8
  implements; T9's `ScriptedRunner` answers from `owned_panes`; T11 and T12 consume. Checked in all
  five, and the member count is now "ten" in T5, T8, T9, N11 and ADR-M3-4 — it read "nine" in all
  five at revision 1.
- **`WriteDecision` gained `CLEAR_THEN_SEND`.** T2 produces; T13's table and T14's delivery consume;
  T2's member-count test renamed `test_write_decision_has_six_members`. Checked in four places.
- **Seven `AnomalyKind` members moved from bare `str` constants in `orchestration/` into
  `core/anomalies.py`.** T2 produces; T6, T8, T12, T13/T16, T14, T15 consume by member name. The
  three bare-`str` `Produces` entries (`KILL_WITHOUT_SESSION_END` in T12, `MAILBOX_INPUT_NOT_EMPTY` in
  T14, `ASK_FORK_RESIDUE` in T15) are **removed** from those blocks so no reader meets two spellings.

**Self-review result: no cross-phase reference drift remains.** Every `Consumes` symbol appears
verbatim in exactly one earlier `Produces` block or in shipped code named by path in the
Codebase Reality Check — **and, added at revision 2, every symbol a task *registers, renders or
wires* is likewise named in a `Consumes` block, which is the check that would have caught
`rename_session`.**

---

## Recommended Defaults (proposed, **explicitly unapproved** — a reviewer may overturn any of these)

Each is low blast radius and additive. None touches one of the 55 decisions; anything that did is a
Decision pressure above.

| # | Default | Why it is safe |
|---|---|---|
| **RD1** | The runner socket is `shepherd-runner`, stored in `app_state` so it is configuration (D49) rather than a constant. | D49 says "configuration, default `shepherd-runner`, never `shepherd`". One key, one default, one test that the default is not the user's. |
| **RD2** | A new pane is `160x45` until the first browser resize. | The probe's own size, so every captured screen and every fixture line length matches what a fresh pane produces. |
| **RD3** | `snapshot(lines=2000)`, matching §9's `-S -2000`. | The alternate screen has no scrollback anyway (`history_size` 0), so the number costs nothing and keeps the spelling identical to the spec's. |
| **RD4** | The mailbox sweep rides the discovery loop's existing **2.0 s** cadence. | No new thread, no new cadence to tune, and `sessions_with_pending()` makes an empty mailbox cost one indexed query and zero tmux calls. |
| **RD5** | Coalescing joins bodies with `"- "` bullets in queue order, newest last, with no separator line. | §9 says "five queued notes become one message with five bullets" and specifies nothing further. |
| **RD6** | `ask_session` default timeout **120 000 ms**, from §11's signature. | Verbatim from the spec; the fork is killed at the timeout, so the cost of a wrong value is bounded. |
| **RD7** | `pipe-pane` sinks live under `$XDG_RUNTIME_DIR/shepherd/panes/<session_id>` and are removed when the last client leaves. | Runtime data, not state (ADR-2); a tmpfs directory that is empty after a reboot is the correct home for a stream nobody replays (**N7**). |
| **RD8** | The session header renders **two** commands: `attach -r` (view-only, exact) first, then full-control with the size caveat. | **DP9**. `attach -r` is capture-proven to deliver zero keys; the second is what a human actually wants, with the one true sentence beside it. |
| **RD9** | The `local only` marker's text is exactly §12's: `local only`. | Verbatim from the spec, and it is the string a reviewer will grep for when DP1 is decided. |

---

## Milestone acceptance — M3 is done when

1. **No tmux invocation in the product or its tests can reach the user's sessions — and the guarantee
   is on the argv, not on a spelling.** At runtime, `check_tmux_argv` refuses any tmux argv that is
   not `["tmux", "-L", <permitted socket>, …]` (the socket `shepherd` never permitted, whatever
   configuration says), any `-t` that is not the exact `=name:` form, and any `kill-server` whose
   socket does not match `^shepherd-m3-`; the one argv allowed without `-L` is the exact list
   `["tmux", "-V"]`, matched by equality. `kill-server` appears nowhere in `src/`. As a second net,
   the AST rules scan the scopes **they actually walk and say so**: `src/**/*.py` for the one-builder
   rule; `src/**`, `tests/**` and `docs/probes/**` — recursive — for the socket and target rules;
   `src/**`, `tests/**` and `docs/probes/2026-09-17-m3-*/**` for `kill-server`, with the pre-M3 probe
   folders named as frozen evidence and the exclusion itself asserted. **The seven planted violations are frozen as inert fixtures
   in `tests/boundaries/fixtures/`, and the assertions that catch them run in every default sweep** —
   `test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime` is the one that
   shows the two nets catch *different* things, and it is the strongest artefact here because it runs
   every time rather than once. Six of the seven rows also carry a dated red in the Mutation proofs
   table below; the seventh (P-M3-5) is a behavioural property with no AST shape and says so there. **The blast-radius rule runs in the default
   `-m "not live"` sweep**, in `tests/boundaries/`. `tmux -L shepherd ls` reports the same sessions at
   the end of the milestone as at step 0b. *(T5, T8, T24, K6, K6-a, K16, ADR-M3-2, ADR-M3-8)*
2. **A session Shepherd starts is owned, and there is exactly one row for it** — after the hook lane
   has run, live, **with Shepherd's real hook block installed in the throwaway settings file and a
   hook frame asserted to have arrived before any count is taken**. *(Corrected at this milestone's
   remediation: the conjunction "and a discovery sweep" was false of the tree — no sweep runs in the
   test that takes the count — and is deleted rather than satisfied, because the sweep is not what
   this clause is about. What is asserted is not a `SessionStart` by name but `last_event_at` moving
   off the spawn's own stamp — **some** hook frame, which BLOCKER-T24-3 reasons out as the right
   mechanism: `spawn.py::_record` stamps `last_event_at` itself on the `needs_you` path, so its mere
   presence is not evidence a hook arrived.)*
   With the shipped `{}` fixture the second writer could never run, so the old assertion could not
   fail; that is fixed, not merely restated. `--session-id` binds the row before the process exists
   (the one exception is an `ask` fork if P2 refuses the flag combination — then the row is created
   unbound, `ephemeral` from birth, and bound from the result object's own `session_id`).
   **And an owned pane can never outlive accounting**: a startup reconcile rebinds handle-less rows
   from the deterministic `shepherd_<ulid>` name and counts `ORPHANED_PANE` for panes with no row.
   *(T11, T12, T21, T24, C-M3-7, DP7)*
3. **A spawn into an untrusted directory never answers the dialog.** Zero keys sent, state
   `needs_you`, the directory named. Asserted by **counting calls on the injected `run_argv` through
   `LocalRunner`**, and the state assertion comes **first**, so a spawn that never ran cannot pass.
   *(T11, T24, C-M3-5, P-M3-6)*
4. **The write policy is total over a 96-key space, pure, and refuses rather than sends.** The key is
   the 4-tuple `(SessionState, PaneKind, Ownership, input_empty)` — 4 × 6 × 2 × 2 — and totality is
   asserted as a **set equality against `itertools.product`, never as a length**, because a literal
   length lets a dropped `REFUSE_INPUT_NOT_EMPTY` row pass while bytes go into a pane the policy meant
   to refuse. All **three** refusal outcomes are proved by counting the runner's calls, with the
   caller shown to have reached the refusal first. A programmatic write **never** reaches a pane with
   a permission dialog open, and both the sidecar and the pane text must be clear before one does; an
   absent sidecar is counted, never read as clear. *(T13, DP8, C-M3-3, C-M3-4, ADR-M3-5)*
5. **The mailbox delivers once, coalesced, on either trigger, and D45's clearing step ships.** Five
   messages arrive as one; a repeated idempotency key enqueues once; a delivered message is not
   re-sent across a restart; an interrupted turn — which emits **no `Stop`** — still delivers at the
   next prompt-ready pane; a non-empty input line is cleared with `C-u` (capture-proven,
   `01b-after-ctrl-u.txt`) and **the pane is re-read before any text follows**, so a clear that did
   not work becomes a counted `MAILBOX_INPUT_NOT_EMPTY` rather than a concatenated instruction; and a
   deferred message records **why** on its row. *(T14, D45, DP10, C-M3-12)*
6. **`ask()` forks headlessly, never touches its target, and never deletes a file the engine owns.**
   The target's transcript sha256 is unchanged live; `method` is always reported; the `can_fork=False`
   mailbox fallback exists and says so. Any transcript residue is **named and counted**, never
   removed. *(T15, DP7, C-M3-10)*
7. **An owned session's end is knowable.** `remain-on-exit` is set at start, `pane_dead_status`
   reaches the row, a kill is recorded **before** it is issued, and `/resume` **rebinds** rather than
   stops. **M2's G-M2-2 is closed for owned sessions and still open for attached ones**, asserted in
   both directions. *(T12, T24, C14, E-M3-16)*
8. **Interrupting is `Escape` and terminating is `kill-session`; no signal reaches a session.** Proved
   by an AST rule with origin resolution and by a planted `os.kill`. *(T8, D43, C-M3-6, N14)*
9. **The `Runner` seam has one contract suite that `LocalRunner` and `ScriptedRunner` both pass**,
   with real-server rows skipped rather than faked when no server is present — §14.2's shape, the same
   one `HostPlatform` already has. *(T9)*
10. **The browser terminal moves real bytes, and the byte-identity claim is proved on this host.**
    Deterministically, the framer does not mutate bytes, over the six checked-in `.ansi` captures
    (`01-trust-dialog`, `02-after-trust`, `03-after-stop`, `06-permission-dialog`,
    `08-prompt-with-suggestion`, `09-resize-after-70x30`). **Live (T24), the WS frame payload equals
    the bytes the real `capture-pane -e -p -S -2000` returned** against an owned pane — added because
    the deterministic test reads a checked-in file, frames it, and compares it to the same file, which
    says nothing about what `capture-pane` returns here. A cross-origin handshake is refused, and the
    stream is torn down with the last client.

    **Deterministically, not live: chunks arrive in order and stop on close.**
    `test_live_chunks_arrive_in_order_and_stop_on_close` drives a **scripted** `_StreamingRunner`
    with `b"one"/b"two"/b"three"`, and **no test in the live lane calls `attach()`**. *(Corrected at
    this milestone's remediation: the sentence "Live chunks are `pipe-pane`'s bytes in order" sat
    under the Live (T24) paragraph and claimed a live proof this tree does not carry. It is moved
    rather than deleted — the ordering property is real and is asserted — and deliberately not
    upgraded to a live test: the honest version of that work is a live `attach()` row against a real
    `pipe-pane` sink, which is a task, not an acceptance correction.)*

    **And M3 claims no browser→pane keystroke path at all.** `POST_ROUTES` has no `terminal_write`,
    the upgraded socket is never read, and `terminal.js` disables input and renders the reason
    (BLOCKER-T19-c; `src/shepherd/web/vendor/VERSION.txt` states this in full, and this clause now
    agrees with it). What **is** asserted about `send-keys -H` is server-side: a write through the
    `Runner` seam is byte-exact and **never** reaches a pane through the pane tty. *(Corrected at
    this milestone's remediation: "a keystroke reaches the pane through `send-keys -H`" read as if
    the browser could type.)*
    *(T17, T18, T19, T24, C-M3-9, P-M3-10, P-M3-17)*
11. **What M3 does not claim: that the terminal *renders*.** There is no browser, no node and no npm
    on this host (`data-schemas.md` §Not probeable on this host), so xterm.js drawing the snapshot and
    the stream identically is **unverified** and is recorded as **G-M3-6**. Every server-side byte on
    the path is asserted; the picture is not. If `xterm.js` could not be vendored at all, the honest
    degrade shipped instead and **T19-a's outcome is written in Progress notes**. *(T19, G-M3-6)*
12. **A rename is honest, and D29 is re-decided out loud without being applied.**
    `can_set_title` ships **`False`**; no keys are sent; the UI says `local only`; `title_synced_at`
    can only be stamped from a read-back of the engine's own `nameSource:"user"`. **DP1 is written in
    the four-part form with its recommendation stated and NOT applied**, the live test that *is*
    §18's probe has run, and its evidence is recorded for the human who will decide. A build that
    flips the flag fails `test_can_set_title_ships_false`. *(T20, DP1)*
13. **The two inherited entries M3 owns are dispositioned, neither silently inherited.**
    **T19-1** — decided at M3 per its own recommendation: pre-registration plus a discovery reconcile,
    **D47 untouched**, with `sdk_cli_reconciled` and `sdk_cli_missed` both reported so the reconcile
    never claims completeness. **T18-2** — M1's checklist executed verbatim against a **throwaway**
    settings file, the counters proved able to move, the latency re-run inside E34's budget, the real
    settings file byte-identical — **or** a recorded re-point to M6 with the failure named. Both
    ledgers appended. *(T21, T22)*
14. **The whole suite is green and the boundary suite has no new exemption.** **No test M1 or M2
    shipped has been deleted or weakened, and the whole default sweep is green** — which is the
    defensible form of this clause and replaces "M1's and M2's 869 tests still pass": those 869
    cannot be isolated out of the default run (measured **1479 passed, 1 skipped, 37 deselected** at
    this milestone's remediation), and at least three of them were *edited* during M3 — two M2 live
    tests re-pointed for BLOCKER-T24-2 and `test_discovery_does_not_duplicate_an_owned_session`
    rewritten after T21's provably-dead check. "Still pass" is true; "unchanged" would not be, so the
    clause does not say it. `mypy --strict` clean under `disallow_any_explicit` (the totality test's
    non-member inputs use `cast`, which is not `Any`); the 429-event golden table byte-identical for
    every pre-existing `SignalKind`; the boundary suite green at **60 rules across 15 modules**,
    derived rather than quoted (`ls tests/boundaries/*.py | grep -v /_`, then
    `pytest tests/boundaries`) — the plan's earlier "**25** boundary test modules (23 shipped + 2)"
    was M2's **rule** count read as a **module** count, the same conflation `T-ACC-14` recorded;
    `db.py` still ≤ 600 lines; **`controld.py` still exactly 140 lines**, with `MAX_DAEMON_LINES` and
    `RESERVED_FOR_M2` unchanged at 150 and 10 — the root grew by **zero** lines, and neither guard
    constant was edited to make M3 fit. **`core/anomalies.py` grew by nine members, appended at the
    end, with no member reordered** (M2's T3-2/T4-1 stays deferred). The nine is derived from the
    file's own `M3's owned sessions` section marker, which is what makes "appended, never reordered"
    checkable; the clause's original **seven** was a count taken before T1's probes ran, and T14 and
    T16 each added one from a captured behaviour (`MAILBOX_CLIENT_ATTACHED` from P3,
    `DIALOG_TEXT_UNRECOGNISED` from P4) — see `T-ACC-14` and the T16-1 entry in BLOCKERS. **The
    properties are what this clause protects and both hold; the numbers are measurements, and they
    are now the measured ones.** *(every task, K4, K9, K11)*
15. **Every gap is named, not discovered.** `docs/plans/2026-09-17-m3-BLOCKERS.md` exists; G-M3-1…9
    each carry a disposition; the four probes that ran are in
    `docs/probes/2026-09-17-m3-tmux/FINDINGS.md` with their captures; and the two probes that were
    **deliberately not run** (P5, P6) say why in the plan rather than in someone's memory.
16. **Step 0b's six rows are recorded in Progress notes ahead of Task 1's entries**, and any ASSERT
    row that disagreed became a blocker entry rather than a discovery at T11. *(Restated at this
    milestone's remediation. The clause used to say "recorded **before T1 started**", which is a
    claim about **history**, and this tree cannot carry it: everything under `docs/plans/` is
    untracked on a single baseline commit, so `git log -- docs/plans/` is empty and no ordering of
    edits is recoverable. Document order is checkable and is what the clause now asserts; the
    stronger temporal claim is recorded as permanently **UNVERIFIED**, with that as its reason,
    rather than left standing as if something proved it.)*
17. **The live lane leaves nothing behind.** `tmux -L shepherd-m3-live ls` reports **no server** at
    teardown; the real `~/.claude/settings.json` sha256 is unchanged by every test individually; and
    the replacement for `test_no_tmux_is_invoked_at_all` is **stronger** than what it replaced and has
    been proved to go red on a planted `-L shepherd`. *(T24, P-M3-15)*

---

## Amendment log

| Revision | Date | What changed | Why |
|---|---|---|---|
| 1 | 2026-09-17 | Initial plan. | — |
| 2 | 2026-09-17 | **Two independent fresh reviews applied in place: 6 and 14 blocking findings, both `REPLAN_NEEDED: true`. Amended, not rewritten — the Codebase Reality Check was re-checked row by row and held, and the 24-task structure, the six tracks and every ADR but two stand.** **Three findings both reviewers reached independently.** **(1) The write policy's key space was wrong and the error hid the refusal D45 exists to produce**: `WriteRule` carries a fourth key field, `input_empty: bool`, and `REFUSE_INPUT_NOT_EMPTY` is reachable only through it, so the space is 4 × 6 × 2 × 2 = **96**, not 48 — and the summary table already expanded to 56, disagreeing with 48 on the plan's own page. The key is now a 4-tuple, totality is asserted as a **set equality against `itertools.product`**, a literal length is **forbidden** by name, and the red-condition names the three **key** enums rather than `WriteDecision`, which is the value space and cannot break totality. One number carried through P-M3-4, ADR-M3-5, T13 and clause 4. **(2) `signals/hook_lane.py` was edited by T12 (Track C) and T14 (Track D) with no edge between them**, against this plan's own hard rule — a rule it calls hard because half of M1's blocker file is two builders in one file — while the plan claimed `engines/claude_code/spawn.py` was "the one file two tasks touch", which was false (`tools_m1.py` is T21+T22 and `discovery_loop.py` is T21+T23). T12 now owns both parameters, T14 consumes and gains `◄── T12`, the callback is renamed `on_engine_session_rebound` because `HookLane._rebind` already exists at l.149, and a **shared-file table** replaces the false sentence. **(3) The three tmux safety rules were spellings, not properties** — each falls to one line (`["tm" + "ux", …]`, `f"kill-{verb}"`, `from .tmux_cmd import TMUX_BIN`, the last yielding an argv with **no `-L`**), and the planted proofs planted the spelling the rule already looks for. **ADR-M3-8** moves the invariant to **runtime at the one process-exec site**, on the actual argv, refusing and never repairing; the AST rules stay as a cheap second net, each with an **indirection fixture**, the shape the shipped platform rule already carries. **Decisions applied.** K6 permits `kill-server` **only** on a `^shepherd-m3-` socket, with the reasoning stated (revision 1 was stricter than CLAUDE.md, and the extra strictness pushed a builder toward the bare form that caused 2026-09-12). T23's root budget is **zero new lines** — `controld.py` is 140 of 140 — with the mechanism spelled out and the guard constants forbidden from being edited. T24 installs Shepherd's **real** hook block (the shipped `install_hooks`) because the `{}` fixture made `test_a_spawn_registers_exactly_one_row` a vacuous pass. **Seven `AnomalyKind` members** move into `core/anomalies.py`, appended, owned by T2; the six degraded conditions are mapped and the one that is **not** an anomaly is named. A **startup reconcile** (T12) rebinds handle-less owned rows and counts `ORPHANED_PANE`; the total cap counts **panes**, via a tenth `Runner` member. **P1 narrowed and DP10 ships the clearing form**: `C-u` was already captured (`01b-after-ctrl-u.txt`), A22 reclassified `proven_by_code`, guarded by a post-`C-u` re-read. **DP5 restated as a record** that D55 was amended to own seven things; N4 re-labelled "absorbed into D55"; the pressure count is nine. **DP7's fallback corrected** to the `-p` result object's own `session_id` (A25, `h5_fork.stdout.json`), because the sidecar is deleted on exit; `create_owned_session` takes `str \| None`. **`rename_session` registration moves to T20**. **Five properties that named a test no task created** now name one — P-M3-5 (a mandatory mutation proof) covers all three refusal outcomes. **P-M3-5/6 re-seated at the argv seam** through `LocalRunner` with a counting `run_argv`, asserting the caller reached its step before asserting zero. **The `never_raises` loops** enumerate their populations, assert their counts and truncate whole captures. **`BUSY`/`DEAD` reclassified on format fields**; the two "six"s disambiguated. **C-M3-9 gains a live T24 row** rather than being downgraded. **P-M3-15 moved to `tests/boundaries/`**, walking `tests/**` and `docs/probes/**`. **T1 names all three sockets P1–P4 need** and requires the copied harness's teardown and bare `tmux -V` fixed first. Advisories folded in: 16 missing red-conditions written, K3 restated to accept and name the engine's own bookkeeping, DP1's reversal made to describe option 3, `sdk_cli_skipped`'s disposition stated, the doubly-claimed snapshot test given one owner, and P-M3-4's non-member technique named (`cast`, not `Any`). | The reviewers verified the evidence base independently and it held, so this is an amendment. Every finding was a **consequence the plan had not traced**, and the sharpest ones were provable by reading shipped code the plan itself cited: `core/states.py:22-33`, `hook_lane.py:149`, `_taint.py:5-9`, `test_controld_composition.py`, `conftest.py:103-109`, `registry.py:3-5`, `core/anomalies.py`, `test_live_attached_session.py:47`. Three were provable by reading a **capture folder beside the one the plan read** — `01b-after-ctrl-u.txt`, `h5_fork.stdout.json`, and `ls *.ansi`. The pattern worth recording: **revision 1 read the summary documents and not the evidence they summarise**, and every one of those three cost it either a needless probe, a racing fallback, or a citation it could not honour. |

---

## Progress notes

*(Appended by builders. The first entries are step 0's drift check and step 0b's six rows, before any
code — G-M3-7, DP6's staleness lesson from M2.)*

### Step 0 — engine drift check (filled by T1's builder, 2026-09-17, BEFORE any code)

| Command | Observed | Clean? |
|---|---|---|
| `.venv/bin/python docs/probes/drift_check.py --record <data_dir>/drift.json` | engine discovered **2.1.273**; 33/33 event names present; `SessionEnd.reason`, `SessionStart.source`, `StopFailure.error`, `Notification.notification_type` all UNCHANGED | **yes**, exit 0 |
| same, **re-run after the engine self-updated mid-task** | engine discovered **2.1.274**; 33/33 names; all four enums UNCHANGED | **yes**, exit 0 |

**The engine moved 2.1.273 → 2.1.274 while Task 1 was running** (11:03 → 11:04 UTC). Not a moved
enum value, so not a blocker by the Step-0 rule — but recorded as **BLOCKER-T1-1** because "verified
at version X" is not stable across an hour-long task. `drift_check.py` does not cover per-event
field shapes; `data-schemas.md`'s header still pins shapes to 2.1.270.

### Step 0b — reality re-check (to be filled by the first builder, BEFORE Task 1)

| # | Command | Kind | Observed | Matches plan? |
|---|---|---|---|---|
| 1 | `tmux -L shepherd ls` | ASSERT | `aivisor`, `main`, `spike` — all three up (created Sun Sep 13). **Read-only; not touched again** | **yes** |
| 2 | `wc -l src/shepherd/store/db.py` | ASSERT | **406**, not 599 | **no — and it is fine.** The plan's 599/cap-600 row exists to catch *growth*; 406 is the post-T4-3 split the router already ratified in BLOCKERS ("`db.py` at 406 … is accepted"). Nobody else is in `db.py` |
| 3 | `grep -n 'shepherd.runner\|shepherd.orchestration' tests/boundaries/_imports.py` | ASSERT | `"shepherd.runner": 2` and `"shepherd.orchestration": 3` in `LAYER_OF`, both also in `FORBIDDEN_BELOW_L4` | **yes** |
| 4 | `wc -l src/shepherd/daemons/controld.py src/shepherd/toolsurface/compose.py` | RECORD | **140** and **119** | matches the plan's measurement |
| 5 | `.venv/bin/pytest -m "not live"`; `.venv/bin/mypy --strict src/shepherd` | RECORD | **1176 passed, 1 skipped, 24 deselected** (81.97 s), exit 0; mypy **clean over 98 files**. (Before T1's test file: same, minus T1's 2 tests) | green; nothing red that M3 does not own |
| 6 | `claude --version`; `tmux -V` | RECORD | **`2.1.273 (Claude Code)`** at 10:59 UTC, **`2.1.274 (Claude Code)`** from 11:04 UTC onward; `tmux 3.4` | drifted **during** the task — see Step 0 and BLOCKER-T1-1 |

### Probe findings (to be filled by Task 1)

| Probe | Question | Finding | Capture folder |
|---|---|---|---|
| P1 | a clearing keystroke for the input line | **`C-a C-k` clears the line; `C-w` deletes one word backward per press (3 presses cleared 3 words); and `C-u` DOES clear the post-`Esc` restored prompt** — same widget as a history recall, same `Ctrl+Y to paste deleted text` affordance. The `Esc` was read back as mid-flight (`c_stop_before_esc: false`) before the result was trusted. **DP10/D45 hold; `CLEAR_THEN_SEND` ships as designed** | `docs/probes/2026-09-17-m3-tmux/p1-keys-20260917T111048Z/` |
| P2 | `--fork-session` + `--session-id`; `--no-session-persistence` residue | **`--session-id <uuid>` is accepted** with `--resume … --fork-session` (`rc=0`, and `result.session_id` is the requested uuid). **`--no-session-persistence` applies with `-p` and leaves NO transcript** — with or without `--session-id`; the control without the flag does leave one. `result.session_id` still present at 2.1.274. **Contradicts §Fork's "a fork leaves a permanent transcript" and T2's `ASK_FORK_RESIDUE` trigger → BLOCKER-T1-2.** Field table appended to `data-schemas.md` §Fork | `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/` |
| P3 | a second tmux client typing beside browser writes | **Nothing is lost and no single `send-keys` is torn — but the streams interleave per call, and the writer's `Enter` submitted `Reply with only the word CONCURRENTZZZZZZZ`: the human's keystrokes inside Shepherd's prompt.** A pre-write input-line check narrows the race and cannot close it. **→ BLOCKER-T1-3 (decision gap for the router, recommendation not applied)** | `docs/probes/2026-09-17-m3-tmux/p3-concurrent-20260917T111005Z/` |
| P4 | `1`/`2`/`3`/`Esc`/`Tab` at a permission dialog | **`1` = Yes (tool runs); `2` = Yes + allow-list the dir (tool runs); `3` = No (tool does not run); `Esc` = same end state as `3`; `Tab` = amend — dialog STAYS UP and option 1 becomes `1. Yes, and tell Claude what to do next`.** `answer_permission(deny)` now has a captured mechanism and nothing was guessed. Residue: digits are **positional**, and **no `PermissionDenied` and no `Stop` fired on either refusal** → **BLOCKER-T1-4** | `docs/probes/2026-09-17-m3-tmux/p4-permission-20260917T110527Z/` |

### Task 1 — the copied harness's two named defects, fixed before the copy ran (exit-criteria item)

`docs/probes/2026-09-17-m3-tmux/probe_m3.py` vs `docs/probes/2026-09-14-schemas/tmux-tui/probe_tui.py`
(**the original was not edited**):

| Defect in the original | Fix in the copy |
|---|---|
| `probe_tui.py:136` — `subprocess.run(["tmux", "-V"], …)`, a bare invocation with no `-L` (CLAUDE.md rule 3's forbidden form, even though `-V` contacts no server) | `tmux_version()` builds `list(VERSION_ARGV)` — the exact tuple imported from `shepherd.runner.tmux_cmd` — and passes it through `check_tmux_argv` before running it, so the one allowed exception is the product's own, matched by equality and not by prefix |
| `probe_tui.py:18, 392-395` — `SOCK = "shepherd-probe"`, torn down with `kill-server` on a socket that does **not** match `^shepherd-m3-` | `SOCK_PROBE/SOCK_OUTER/SOCK_INNER` = `shepherd-m3-probe` / `-outer` / `-inner`, and `PERMITTED = permitted_sockets(...)` of exactly those three. `shepherd` and `shepherd-runner` are absent and the guard refuses them by name |
| (beyond the two) `probe_tui.py:36` — `assert "kill-server" not in args or args == ("kill-server",)`, a hand-rolled assertion | every argv goes through `check_tmux_argv` **twice**: whole, and from the binary onward (`_tail_from_binary`, T8-2's `_tmux_tail` scan) so the `env -i` prefix cannot hide it |
| (beyond the two) `probe_tui.py:115-119` — `sidecar()` reads `/root/.claude/sessions/<pid>.json` | dropped. No probe here needs it, and nothing under `~/.claude/` is read or written by this harness |
| (beyond the two) `probe_tui.py` calls `subprocess.run` with no timeout | every subprocess call carries a timeout (`TMUX_TIMEOUT=30 s`, `CLAUDE_P_TIMEOUT=240 s`) |

One harness bug of the copy's own, found and fixed by running it: `trust()` sent `Down`+`Enter`
blind, the TUI had not yet bound the key, `Enter` took the **default** — which is **`No, exit`** —
and the pane exited (status 1). It now reads the selection back off the chevron line before pressing
`Enter`. The first, failed folder was deleted rather than kept.

### Mutation proofs (to be filled as each is run — K17, and they are required, not optional)

**Filled at the milestone remediation, 2026-09-17, and the *shape* of the evidence changed with it.**
Each row's planted violation is now an **inert fixture** in `tests/boundaries/fixtures/` — read as
text, parsed as an AST, never on an import path the suite executes — and the red is produced by
**neutering the fixture** and watching the shipped assertion that catches it go red. That is a
mutation of the *planted violation*, not of live source, and it is re-runnable by anyone at any time
without executing anything.

Why it is shaped that way: on 2026-09-17 the previous form of this round — planting into a shadow
copy of `runner/local.py` — put `os.kill(1, signal.SIGINT)` into a module the suite **imports and
runs**, and rebooted the host. See CLAUDE.md "Mutations: plant inert fixtures, never live source the
suite executes", and the full entry in `2026-09-17-m3-BLOCKERS.md`.

| Property | Planted violation (frozen fixture) | Mutation | Red output recorded? |
|---|---|---|---|
| P-M3-1 | `["tmux", "list-sessions"]` — `runner_bare_tmux_call.py` | the fixture names `git` instead of the binary | **yes** — `test_tmux_is_spelled_in_exactly_one_module`: `AssertionError: assert [] != [] where [] = command_word_sites(fixture('runner_bare_tmux_call.py'), 'tmux')`, and `test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime`: `AssertionError: runner_bare_tmux_call.py` |
| P-M3-1 | the binary as an imported constant — `runner_tmux_via_constant_import.py` — **runtime net only** | the fixture builds a legal `-L shepherd-m3-live` argv | **yes** — `test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime`: `Failed: DID NOT RAISE RunnerRefusal` |
| P-M3-2 | the literal `"kill-server"` — `runner_kill_server.py` | the verb becomes `list-sessions` | **yes** — `test_kill_server_is_never_a_command_word_in_src`: `AssertionError: assert [] != [] where [] = kill_server_violations(fixture('runner_kill_server.py'))`; also `test_a_server_wide_teardown_is_bounded_to_a_throwaway_socket` and the asymmetry test |
| P-M3-2 | `f"kill-{verb}"` — `runner_kill_server_via_fstring.py` — **runtime net only** | `SCOPE = "server"` → `"session"` | **yes** — `test_the_indirection_fixtures_defeat_the_ast_rules_and_are_refused_at_runtime`: `Failed: DID NOT RAISE RunnerRefusal` |
| P-M3-5 | a `send-keys` call before the decision check, `orchestration/mailbox.py` | **not reducible to a fixture** — see below | **partly** — 12 red in `tests/orchestration/test_mailbox.py`, this session, listed below with its caveat |
| P-M3-7 | `os.kill(1, signal.SIGINT)` — `runner_signals_init.py` | the fixture returns instead of signalling | **yes** — `tests/runner/test_local.py::test_no_signal_reaches_a_session`: `AssertionError: assert [] != [] where [] = signal_violations(fixture('runner_signals_init.py'))` |
| P-M3-15 | `-L shepherd` — `runner_forbidden_socket.py` (**new at this remediation**) | the socket becomes `shepherd-m3-live` | **yes** — `test_no_tmux_call_in_the_tree_can_reach_the_users_socket`: `AssertionError: the scan cannot see an argv that names the user's own socket` |

**P-M3-5 is the one row that is not a fixture proof, and it is named rather than forced.** It is a
*behavioural* property — "no write reaches the pane before `decide_write` has answered" — with no AST
shape, so there is nothing to freeze: the violation is an ordering inside a function, and only
running the function can show it. It was planted into `orchestration/mailbox.py` in a shadow tree
earlier in this session (a `runner.write(...)` hoisted above the `decide_write` call) and produced
**12 failures in `tests/orchestration/test_mailbox.py`**, among them
`test_a_failed_clear_defers_and_counts_the_named_member`,
`test_a_refusal_is_recorded_on_the_row[permission_dialog|dead_pane|unreadable_pane|mid_turn]`,
`test_an_attached_session_has_no_write_path` and
`test_the_mailbox_takes_verbs_and_never_a_connection`.

That plant was in the **safe class** and the escape analysis is the reason it is recorded rather than
withdrawn: in the default lane `runner` is a `ScriptedRunner`, or a `LocalRunner` over a scripted
`run_argv`, so the hoisted `write` becomes a recorded argv and never a process, a signal or a socket
— nothing leaves the interpreter. It is reported here with that analysis attached, and it was **not**
re-run under the new rule, because re-running it is exactly the "force it" the rule now forbids.
Anyone re-verifying this row should read the escape analysis first and decide again.

### T19-a — the vendoring outcome (step 4: "either way, write the outcome into Progress notes")

**Branch taken: vendored.** Not the degrade — though the degrade ships beside it, because a vendored
file can still be missing from an installed wheel.

| | |
|---|---|
| package | `@xterm/xterm` **6.0.0**, MIT (`LICENSE` vendored verbatim beside the code) |
| source | `https://cdn.jsdelivr.net/npm/@xterm/xterm@6.0.0/`, fetched with `curl` on this host 2026-09-17 |
| files | `xterm.js` ← `lib/xterm.mjs` (344 970 B, byte-identical), `xterm.css` ← `css/xterm.css` (7 112 B), `LICENSE` (1 261 B) |
| sha256 | `b336ec65…` / `854a7c0f…` / `b569f629…`, recomputed from the shipped bytes on every run by `test_the_vendor_manifest_pins_every_byte_it_ships` |
| module? | **yes** — step 2's check: the ESM build, last statement `export{Dl as Terminal}`. `lib/xterm.js` in the same package is the UMD bundle, which needs the loader D51 forbids |
| the one rename | `.mjs` → `.js`, because `web/server.py`'s `_CONTENT_TYPES` 404s every suffix but `.html`/`.js`/`.css`. Bytes unaltered; both the upstream name and the digest are recorded so the claim is checkable |
| not vendored | `lib/xterm.mjs.map` (1 690 930 B) — `test_frontend_no_build_step` forbids `.map` under `web/` by suffix. The trailing `sourceMappingURL` comment therefore 404s in devtools; stripping it would have broken the byte-identity, and a dangling sourcemap is the cheaper honesty |
| integrity | digests cross-checked against jsdelivr's **metadata** API, a different endpoint from the CDN that served the bytes. **Two endpoints of one CDN agreeing** — that detects a corrupted transfer, not a compromised registry, and `VERSION.txt` says so rather than calling it a signature |

**What this does not establish — G-M3-6, and it is acceptance clause 11's point.** There is no
browser, no node and no npm on this host. That `xterm.js` *renders* the snapshot and the stream
identically is **unverified** and goes on the handoff's by-hand list. Every server-side byte on the
path is asserted; the picture is not.

**BLOCKER-T19-c:** there is no browser→pane keystroke path in this tree. `POST_ROUTES` has no
`terminal_write` and the upgraded socket is never read; `terminal.js` disables input and renders the
reason instead of swallowing keys. The plan's Task 19 never asked for one — **the router's dispatch
brief did, and it was over-scope**; adding it would have meant a POST route outside T18's set, which
clause 11 asserts closed. Full entry in `2026-09-17-m3-BLOCKERS.md` under "T19 — verified by the
router".

**T19's builder filed no report** (session rate limit, mid-task). The six mutation proofs recorded in
BLOCKERS were planted by the router, not by the builder, in a shadow tree of the router's own.

### Task 23 — composition, and T20's two leftovers (2026-09-17)

**Shipped.** `compose_tool_surface` now returns a frozen `M3Wiring(runner, sweep)`; the root edited
**two existing lines and added none**, and `wc -l src/shepherd/daemons/controld.py` is still **140**
with `MAX_DAEMON_LINES == 150` and `RESERVED_FOR_M2 == 10` unchanged (the new
`test_the_line_budget_constants_are_unchanged` pins both spellings — this file's and
`tests/boundaries/_imports.py`'s — so they cannot drift apart).

Inside `toolsurface/compose.py`: one `LocalRunner` (socket from `app_state` under
`RUNNER_SOCKET_KEY`, default `shepherd-runner`, `make_run_argv(permitted_sockets(...),
permitted_commands("cat", BINARY_NAME))` after T8-3 landed mid-task), the twelve M3 tools,
`register_rename_tool`, T12's `reconcile_owned_panes` **before** the freeze, `run_fork` and the
sidecar reader the tool surface may not spell for itself, and T14's `sweep_pending` handed back as
`M3Wiring.sweep`. `run_discovery_loop` gained a `sweep` parameter and calls it on the 2.0 s cadence
it already owns — **no fourth thread, no second socket**, both asserted.

**T20's leftovers, both landed.** `register_rename_tool` ships with `blast_class=local_write` and
audiences `(MASTER, HUMAN)` — in a **new module `toolsurface/tools_rename.py`**, because
`tools_m3.py` is at 447 of its own 450-line guard and appending would have meant editing the guard;
the size assertion now holds four files to the unchanged 450. P-M3-9's orchestration suite is
`tests/orchestration/test_degradation.py`.

**The plan's numbers, measured rather than taken.** P-M3-9's population is **22**, not 17, and the
suite asserts a **set** of `(module, callable)` pairs with the enumeration rule written down in the
test. 160 degradation cases (154-byte capture truncated at every byte boundary, plus empty,
non-UTF-8, whole, a sidecar that is a directory, and an absent sidecar) x 22 callables = 3520 drives,
with both counts computed in the same run.

**One real defect found and handed off:** `admission.admit` raises `ValueError: embedded null byte`
on a `cwd` containing a NUL — reachable from `POST /api/sessions` — pinned in the suite's
`KNOWN_DEFECTS` set. `admission.py` belongs to another builder; see the T23 entry in
`docs/plans/2026-09-17-m3-BLOCKERS.md`.

**Evidence.** 13 mutations planted in `scratchpad/t23/shadow/` (never the real tree), each restored
under `sha256sum -c`: 11 red, 1 bad mutation replaced, **1 survivor** that exposed a genuine hole in
the degradation suite (the orphan-pane branch was never driven) — all tabulated with their red output
in the BLOCKERS entry. Full suite **1453 passed, 1 skipped, 28 deselected**; `mypy --strict src`
clean over 109 files.

### Task 24 — the live lane, and the static net it turned out to need (2026-09-17)

**Done.** `tests/e2e/conftest.py` gains `LIVE_TMUX_SOCKET`, the `TMUX_CALLS`
ledger, `lane_run_argv`, `tmux_live`, `installed_settings` and
`Throwaway.tui_argv`; `tests/e2e/test_live_owned_session.py` and
`tests/e2e/test_live_ask_fork.py` are new;
`tests/e2e/test_live_attached_session.py` gains the narrower live second check.
**21 live tests pass** (M1's 7, M2's 5, M3's 9). Default run **1458 passed, 1
skipped, 37 deselected**; `mypy --strict src` clean over 109 files.
`tmux -L shepherd-m3-live ls` → no server; `tmux -L shepherd ls` → `aivisor`,
`main`, `spike`, untouched; `~/.claude/settings.json` still `375e5322…`.

**Three things in this task's text were false of this tree**, each recorded in
`docs/plans/2026-09-17-m3-BLOCKERS.md` under "T24 — the live lane":

1. **T24-1** — a refused trust dialog does not carry a readable
   `#{pane_dead_status}` *at the instant the pane goes dead*; tmux fills the
   status when it reaps the child, and a read 0.3 s after the keypress sees
   `pane_dead=1` with the process still running. E-M3-16 itself holds and is
   measured three other ways (`exit 7`, `claude -p` → 0, a bad flag → 1).
2. **T24-2** — the plan's Required Check list inherits M2's clause *"the fleet
   page's tree carries the row's bucket"*, and **T21/DP2 option 2 deliberately
   reverses it**: `reconcile_sdk_cli` marks a hooked `-p` run `ephemeral` and
   `Store.fleet()` excludes those. M2's live test was re-pointed at the store row
   and now asserts DP2's hiding positively.
3. **T24-3** — `last_event_at is not None` is **not** evidence a hook arrived:
   `spawn.py::_record` stamps it itself on the `needs_you` path. The arrival
   signal is the stamp moving off the spawn's own value.

**Two deviations, both reported rather than quiet.**

1. **`tests/e2e/test_live_rename.py:157` was calling `make_run_argv` with one
   argument** and would have raised `TypeError` the moment T20's live test ran.
   T8-3 landed after T20 wrote it. Fixed in place (the call only —
   `permitted_commands(SINK_PROGRAM, BINARY_NAME)`, both imported), never
   rewritten. This is the defect that produced the next item.
2. **A file outside this task's list: `tests/e2e/test_live_stop_classification.py`**
   — re-pointed for T24-2 above, and four JSON decoders annotated `-> Any` so the
   new static gate is green. No assertion was moved.

**The static gate (raised by the coordinator mid-task).**
`tests/e2e/test_live_lane_typechecks.py` carries **no `live` marker** and so runs
in the default lane, type-checking exactly the files the default run does not
execute — derived from pytest's own `-m live` collection, never a list. Profile:
`tests/e2e/live_lane_mypy.ini`, relaxed on purpose (`mypy --strict tests` is 233
errors in 108 files). Its mutation proof is the best evidence in the task: with
T8-3's arity break planted back into a live test, the gate named **two** sites —
the plant and `tests/contracts/test_runner_contract.py:795`, the real defect, at
its real line.

**Six mutations planted, six red, no survivors**, all in
`scratchpad/t24/shadow/`, never in the real tree; restoration proved by
`sha256sum -c` and finally by `diff -r src shadow/src` → exit 0 and
`diff -r tests shadow/tests` → exit 0.

**The human_verify checkpoint** ran before the first live run:
`scratchpad/t24/argv_checkpoint.py` prints all nineteen argvs the lane can issue
plus the four-step teardown, checks each against `check_tmux_argv` twice
(directly and through `_tmux_tail`), and reports `refusals: 0` with
`sockets named: ['shepherd-m3-live']`.
