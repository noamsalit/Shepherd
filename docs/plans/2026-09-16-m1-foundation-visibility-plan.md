# Shepherd M1 — Foundation + Visibility — Execution Plan

## Metadata

- **Created:** 2026-09-16
- **Status:** draft
- **Plan Mode:** execution_plan
- **Verification Rigor:** critical_path
- **Scope:** M1 only (spec §16). M2–M6 are out of scope and get their own plan → implementation cycles (§0).
- **Supersedes:** `docs/plans/2026-09-13-m1-foundation-visibility-plan.md` — **STALE** (predates D35–D55). Not read, not diffed, not extended.
- **Plan revision:** 6 · **Last reviewed revision:** 5 (code review of the built T1+T2, rule-scoped) ·
  **Fresh-review passes:** 2/2 (cap spent at r4)
- **Revision 6 (2026-09-16) — rule-text amendment, scoped to five of T2's rules.** A code review of
  the **built** T1+T2 proved three of T2's rules defeatable by one-line idioms, against the shipped
  scan functions. **The builder implemented them faithfully — this is a plan defect, not a build
  defect**, and the lesson is in the shape of the mistake: **all three were written as enumerations
  of AST syntax, and all three are now written as properties** ("any access to the mapping", not
  "every string-literal subscript"). A syntactic rule is only ever as wide as the forms its author
  happened to think of; a property is wide by construction and leaves the enumeration to the
  implementation, where a missed form is a bug rather than a specified hole. Two further rule fixes
  from the same review: the `hookd` isolation rule is restated as a property of the **generated
  command string** (the strict reading blocked T8's own prescribed code), and every string-literal
  scan now exempts docstrings and matches at word boundaries.
  **Nothing outside T2's rule text changed.** The import-based half of the machinery was confirmed
  sound and alias-proof by the same review and is untouched.

> **Revision 6 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (**cap spent at revision
> 4**). Checked since only by diff-scoped passes: amendment verification (saw r4), and this code
> review (saw the built T1+T2 against r5). **No adversarial pass has read any revision since r3
> whole.** Sections changed at r6: **Task 2's rule text and `Produces` only** — plus this header and
> the Amendment log.
>
> **Reaching the cap is a stopping point, not closure**, and r6 is evidence of what that costs: the
> defect it fixes was introduced at r4, survived r5's amendment verification, and was caught only
> when someone ran the code. Diff-scoped review finds diff-scoped problems. **Anything further is a
> blocker entry under the blocker protocol** — one is already open in Task 17 (`cli/` cannot import
> `engines/`, so the hook-install commands have no legal path; three candidate resolutions written
> down, none chosen).
>
> *(Revision 3's change list, retained:* Metadata · Agreement Snapshot (K3, Open decisions) · Decision pressures 1, 2, 5,
> 6 (new), 7 (new) · Flows A0 · Risk matrix (+7 rows) · Evidence gaps (G9, G10 closed; G12, G13
> new) · Codebase Reality Check (+4 rows) · Plan-vs-spec gaps (M2 rewritten, M13–M15 new) ·
> Assumption ledger (A8, A9, A13 revised; A16, A17 new) · Behavior contract (C-4, C-11) ·
> Purity map · Provable properties (P17–P21) · Edge-case catalogue (E34–E37) · ADR-4, ADR-5, ADR-7 (new) ·
> Tasks 1, 2, 3, 4, 5, 6, 7, 7b, 8, 9, 10, 10b (new), 11, 14, 16, 17, 18 · Dependency graph ·
> Completeness gate · Self-review · Recommended Defaults (RD1, RD8 overturned; RD9 new) ·
> Acceptance criteria 2, 9, 12 · Amendment log.*)

---

# LAYER 1 — HUMAN LAYER

## Agreement Snapshot

**Goal.** Make the fleet of hand-launched (`attached`) Claude Code sessions legible in a browser,
read-only, on Linux and macOS from one build — by discovering running sessions from Claude Code's
own live-session registry, optionally enriching them with hook events through one dispatcher,
folding both into four SQLite tables from a single writer, and rendering a workspace → session →
subagent tree that updates over SSE with no polling **in the browser**.

**The fleet page must not be empty on a machine where no hooks are installed.** That is the
constraint the user's "do not touch my `~/.claude/settings.json`" rule creates, and it is what
Decision pressure 5 below resolves.

**Constraints (all binding, all from in-repo artifacts):**

| # | Constraint | Source |
|---|---|---|
| K1 | No data shape may be asserted without a real captured example in `data-schemas.md`. A shape that is not there is a **gap**, and the task's first step is a probe. | D41, user brief |
| K2 | Nothing we install may harm Claude Code. Hooks bound their own runtime, swallow everything, always exit 0. | Principle 4 |
| K3 | The real `~/.claude/settings.json` is never touched. Every installer test runs against an isolated `CLAUDE_CONFIG_DIR` or a `--settings` file in a throwaway dir. **The one exception is the live lane (T18), which cannot use an isolated config dir because credentials live in the real one** (`docs/probes/2026-09-16-registry-and-version-drift.md` Finding 3: `Not logged in · Please run /login`, rc=1). There, isolation is by throwaway **working directory** + an explicit `--settings` file, and K3 is upheld by the P13 sha256 guard plus an instrumented-write assertion rather than by construction. See Task 18, isolation rule 1. | User brief, C6; probe Finding 3 |
| K4 | `mypy --strict`, Python 3.12, no `Any`, no file past ~600 lines. | Principle 6 |
| K5 | No `shell=True` anywhere; argv lists only. | §13 |
| K6 | Never `tmux kill-server`; never touch the `shepherd` socket; always pass `-L`. | CLAUDE.md, §18 incident |
| K7 | The 55 decisions are law. Pressure against one is named and re-decided out loud, never reversed silently. | §3, §0 |
| K8 | stdlib-first; no build step for the frontend; `xterm.js` is the only runtime dep (and it is M3, not M1). | §5 Stack, D51 |
| K9 | Unknown is a first-class value — counted and displayed, never hidden. | Principle 5 |
| K10 | The host has **no pip/ensurepip in the system Python, no node/npm/tsc, no `sqlite3` CLI, no Secret Service**. `/root/Shepherd/.venv` is the working toolchain. | data-schemas §Runtime toolchain |

**In scope (verbatim from §16, decomposed):**

1. `HostPlatform` seam (D55) — Protocol, `LinuxHost`, `MacHost` (unverified), `ScriptedHost`, contract suite.
1b. **Hookless discovery** from `~/.claude/sessions/<pid>.json` and `claude agents --json`
   (Decision pressure 5) — the primary discovery, liveness and state source when no hook is installed.
2. `hookd` dispatcher + hook install/uninstall with `_shepherd_managed`.
3. `sessiond` (UDS ingest + relay + bounded buffer) and `controld` (sole DB writer, fold, HTTP/SSE).
4. Ingest folding into `session` columns (D24, D37) — no event store.
5. Four tables (`workspace`, `repo`, `session`, `app_state`) + `schema_migration` + migrations with the three rules.
6. Workspace/repo discovery and cwd→repo binding via **D48**, `vcs_remote` normalisation via **D50**.
7. Minimal final-shaped `toolsurface/`: `ToolDef` + `invoke()`, read-only tools, registration-time schema validation (D53), **no gate, no audit log** (D38).
8. Workspace → session → subagent tree; fleet page; SSE with `seq` and `Last-Event-ID` replay.
9. The two enforced import boundaries as **tests that fail the build** (D35) — M1 deliverables, not M4's.
10. Test lanes: golden fixtures over the 429 captured events (§14 lane 1), contract suites for the seams M1 introduces (§14 lane 2), import-boundary tests (§14 lane 2b).

**Out of scope (named so they cannot leak in):**

- `owned` sessions, tmux runner, pty, xterm.js, write policy, mailbox, `ask()` — **M3**.
- Stop-reason engine, `stop_reason`/`outcome`/`why`/`confidence`/`next_actions[]`, the 7-bucket palette, the Needs-You rail as a page element, `replay`, `unknown` rate — **M2**. M1 sets `state` only.
- `authorize()`, audit log, MCP exporters, `master/`, approvals, chat page — **M4**.
- `work_item`, `queue`, claims, workers, worktree creation, the matrix view — **M5**.
- `shepherd install`, systemd unit files, launchd plists, Dockerfile, `loginctl enable-linger` **mutation** — **M6**. M1 *reads* supervision and linger state; it never writes a unit or flips linger.
- LLM verdict lane — deferred past M2 (D34). No seam, no call site in M1.

**Open decisions:** none. **Eight** items are recorded under **Recommended Defaults** below
(RD2–RD9); each is low-blast-radius and additive, each names the evidence that makes it safe, and
each is explicitly **unapproved** — a reviewer can overturn any of them without restructuring the
plan. Two of revision 2's defaults were overturned by the revision-2 review and are no longer
defaults: **RD1** became Decision pressure 2's re-decision (a sixth `HostPlatform` member), and
**RD8** was replaced by a recency rule. Anything that touches one of the 55 decisions is a **named
Decision pressure**, never a default: DP1, DP2, DP5, DP6, DP7.

---

## What changed in the world since the spec was written, and what this plan does about it

Two pieces of evidence landed after §8 was drafted. Neither reverses a numbered decision; both
change how a task is built, so both are written down here rather than absorbed quietly (K7).

### Decision pressure 1 — the `hookd` dispatcher must not be a Python process

**The decision under pressure.** §8 "Hook installation" shows `hookd.py`, a Python dispatcher.
It is a **code block, not a numbered decision** — D37 says "`hookd` still writes to `sessiond`",
and says nothing about the language. So this is a choice the spec left open, and the rule it must
obey is principle 4.

**The pressure.** Three independent facts:

| Fact | Evidence |
|---|---|
| A Python hook dispatched at `-p` shutdown was killed and its payload lost, **2 of 2 times**, while a fork-free bash hook on the same events survived. | data-schemas §StopFailure "Delivery race in `-p`"; §Hook runtime contract "**`-p` shutdown kills slow hooks**"; C7 |
| Python costs **31.7 ms/call** (27.2 ms with `-S -E`); `sh` + `nc -U` costs **3.4 ms** — 9.3× cheaper. Delivery is intact: three 77-byte frames and one 40 011-byte frame arrived byte-complete. | `docs/probes/2026-09-16-hookd-latency.md` Results 1 and 2 |
| `MessageDisplay` is dispatched with `forceSyncExecution`, so dispatcher cost lands directly on the user's screen latency, and hooks for one event block the next one (a 3 s `PostToolUse` hook delayed `PostToolBatch` by 3.0 s). | data-schemas §MessageDisplay; §Hook runtime contract, synchronicity row |
| **The command is exact, and one flag carries the whole result.** `timeout 0.25 nc -U -q0 "$1"` costs 3.2 ms/call; the *same command without `-q0`* costs **253.6 ms/call** — 79× worse and 8× worse than the Python dispatcher this decision exists to avoid. Without `-q0`, `nc` never shuts down its write side at stdin EOF, so a listener reading to EOF (T10) never sees the frame end and the call blocks until `timeout` kills it. **Both variants delivered every frame**, so the failure is silent: it reads as "Claude Code got sluggish since we installed Shepherd" and never points at a flag. | `docs/probes/2026-09-16-hookd-latency.md` **Result 1b** |

**Options.**

| Option | For | Against |
|---|---|---|
| **(a) Python `hookd.py`** (§8's sketch) | one language; no host dependency | 31.7 ms on every event of every session; the exact shape that lost `StopFailure` 2/2; §18's write-volume risk is 9× worse |
| **(b) `sh` + `nc -U`, bounded by `timeout 0.25`** | 3.4 ms; measured byte-complete delivery to 40 KB; 3.6 ms and exit 0 with no daemon (principle 4 **measured**, not asserted); fork-free bash already survived shutdown 2/2 | `nc` is a host dependency; **its flags are not portable — `-q0` is not on macOS's netcat**; the hook cannot report delivery failure |
| **(c) `sh` + append to a spool file, `sessiond` tails it** | 2.9 ms; **no daemon needs to be listening at hook time**, which removes the shutdown race entirely | a spool of raw events reads like the event store D24 refuses; needs a tail reader, a rotation policy and a truncation story |
| **(d) a compiled helper (C/Rust)** | fastest, no host dependency | needs a toolchain and a per-platform build the packaging story (M6) does not have; enormous cost for 0.5 ms |

**Recommendation — (b), with (c) designed but not built.** It is an order of magnitude cheaper
than Python on the path that runs on every event of every session, it is the shape that was
*observed to survive* the shutdown race, and its daemon-down behaviour is measured rather than
argued. (c) stays in the plan as a named degrade (Task 8's fallback) because it is the only option
that removes the race rather than shrinking it — but it is not built at M1, because building an
unused second path is speculative and D24 would have to be re-argued to keep the spool honest.

**Four consequences this plan carries:**

1. **The 250 ms timeout stays and is re-aimed.** It bounds a hung `sessiond`. It never bounded
   interpreter start-up, which is what actually bit. `timeout 0.25 nc -U -q0 …` enforces it from
   outside the client.
2. **The hook command line becomes a `HostPlatform` concern** (see Decision pressure 2) — and, per
   Result 1b, a **sixth seam member**.
3. **The command has exactly one definition site in this plan and in the code**:
   `SocketPlan.dispatch_command`, produced by `host/`. **No other section of this plan, and no
   other module, restates it as a literal.** Revision 2 carried a second copy in Task 8 that had
   lost `-q0`; a divergent copy is what produced that near-miss, and the structural fix — one
   definition site, cited rather than restated — is what stops it recurring. T2's boundary lane
   enforces it (`test_dispatch_command_has_one_definition_site`).
4. **The installer must check for the binary** and refuse-with-a-reason rather than writing a
   hook that silently does nothing. A hook that exits 0 having delivered nothing is exactly the
   failure principle 5 forbids hiding.

**Gap, stated plainly:** there is **no macOS capture for any of this**. `MacHost`'s hook command
is written from D55's prose and marked unverified, exactly as `can_set_title` is (D29).

### Decision pressure 2 — D55 says the `HostPlatform` seam owns *exactly five* things, and the hook command line is a sixth

**The decision under pressure.** D55: the seam owns (1) directory resolution, (2) the control
socket's directory and path-length budget, (3) service supervision, (4) process liveness and exit
observation, (5) login persistence — and **"nothing else may branch on platform."**

**The pressure.** After Decision pressure 1, the hook command line differs by platform (`nc` flags
differ; the binary may be absent in a container). It must live *somewhere*, and D55 forbids every
other module from branching on platform.

**Options.**

| Option | For | Against |
|---|---|---|
| **(a) a sixth member, `hook_dispatch()`** | explicit; visible in a diff; the count is the anti-growth clause and incrementing it deliberately is what that clause is *for* | contradicted D55's then-wording, so D55's row had to be amended — **which it since has been** (r4, A3) |
| **(b) widen member (2)** to "the control socket: its directory, its path-length budget, **and the hook-side client command that writes to it**" | the hook command *is* how a non-Python client reaches that socket; keeps the count at five | **keeps D55's letter while defeating its purpose** — an anti-growth clause about *count* is satisfied by making one member absorb anything, and the widening is invisible in a diff |
| **(c) leave it in `engines/claude_code/`** | no change to D55 | puts a platform branch in `engines/`, which D55 forbids outright — not a real option |

**Recommendation — (a), the sixth member. Re-decided at revision 3 (was (b)).** The revision-2
recommendation took (b) on the argument that the difference was presentational. It is not. D55's
"exactly five" is an **anti-growth clause about count**; widening a member's definition to avoid
incrementing the count keeps the clause's letter and removes its effect, and it hides the change
from every diff. A sixth member is honest and reviewable. The author of D55 has confirmed this
reading and authorised five → six.

Two facts settle it beyond presentation:

1. **`-q0` is the exact character the platforms differ on**, and it is worth 250 ms per hook
   invocation (Result 1b below, and F1/Decision pressure 1). A per-host value that expensive is a
   first-class seam member, not a rider on the path budget.
2. `SocketPlan` already bundles six facts. Hanging a seventh on it because the *member count* must
   stay at five is precisely the accounting trick (a) avoids.

**Consequence — the spec amendment has LANDED (applied 2026-09-16 by D55's author, confirmed at
revision 4).** `docs/specs/orchestrator-platform.md:165` now reads "The seam owns exactly **six**
things … and **the hook-side dispatch command** … **Six, raised from five on 2026-09-16**", with the
`-q0` portability and 250 ms measurement as its reasoning. **Nothing is outstanding; do not paste
the text below anywhere.** It is retained only as the record of what was proposed and why:

> …and **login persistence** (`loginctl enable-linger` vs a `RunAtLoad` agent), and **the hook-side
> dispatch command** (the shell one-liner a non-Python hook client uses to reach the control
> socket). **Six things, raised from five on 2026-09-16:** the dispatch command's `nc` flag set is
> not portable — `-q0` exists on OpenBSD netcat and not on macOS's — and omitting it costs 250 ms
> on *every* hook invocation while still delivering (`docs/probes/2026-09-16-hookd-latency.md`
> Result 1b). That is a platform branch, so by this decision's own rule it belongs here; it was
> raised as a member rather than folded into the socket member because "exactly five" is an
> anti-growth clause about count, and absorbing new concerns into an existing member would keep its
> letter while defeating it.

The plan builds against six members, and the spec now says six, so plan and decision log agree.
**RD1 is withdrawn** — this is no longer a recommended default but a re-decided pressure.

### Decision pressure 3 — `idle_prompt` puts every finished interactive session in `needs_you` after 60 s

**Not a reversal — a consequence the spec states but never names.** §8's `state` table lists
`idle_prompt` in the `needs_you` set, and "`needs_you` outranks `stopped`". Measured: `idle_prompt`
arrives **60.03 s after every `Stop`** in a TUI session (data-schemas §Hook event parity;
§Notification; C21). M1's ordering is `needs_you → running → stopped → idle`, so **every idle
attached session sorts to the top of the fleet page one minute after it finishes.**

**This plan implements §8 literally** — that is what "the decision log is law" means — and makes
the consequence visible rather than surprising: `needs_you_reason` is written as the actual ask,
`"idle — waiting for your next instruction"`, never "needs attention" (§7 `needs_you_reason`).
M2 owns the 7-bucket palette and is where a separate `idle` bucket, if one is wanted, belongs.
Recorded here so M2 inherits the observation instead of rediscovering it.

### Decision pressure 4 — §5.0 has no home for three real M1 modules

**The gap.** §5.0's five layers name `master/ web/ cli/ · toolsurface/ · orchestration/ ·
signals/ runner/ providers/ engines/ · store/ logs/ core/`. M1 must also ship: the two **daemon
entrypoints**, the **`hookd` dispatcher** (a separate process launched by Claude Code), the
**`host/` seam** (new at D55), and **`testkit/`** (§14.2 says `Scripted*` ships with the package).

**Resolution, recorded as ADR-1 below, not as an open question:**

- `host/` → **L2**, beside `runner/`, `engines/`, `providers/`. It reads and drives the outside
  world; that is L2's definition.
- `daemons/` → a **composition root above L5**. It wires layers together and contains no domain
  logic. The import test's rule is stated on the L5 *packages* (`web/`, `cli/`, `master/`), and
  `daemons/` is named as the wiring layer, capped at 150 lines per file. A second test asserts
  **nothing imports from `daemons/`** — a composition root with importers is not a composition root.
- `engines/claude_code/hookd.py` → physically inside the engine adapter, but with a hard rule of
  its own: **it imports nothing from `shepherd`** (an AST test enforces it), because its whole
  value is that it is not a Python process at all — it is a shell one-liner whose *text* the
  adapter owns.
- `testkit/` → **L1-adjacent**, importable by tests and by any layer, importing only `core/` and
  the seam Protocols.

### Decision pressure 5 — D47's "supplementary" discovery source is M1's *primary* one

**The decision under pressure.** D47: "Registration accepts the first event of *any* kind from an
unknown `session_id`, not `SessionStart` alone. **`claude agents --json` is a supplementary
discovery source.**"

**The pressure.** The user's rule — the real `~/.claude/settings.json` is never touched (K3) —
means **no hook is installed on this machine**. D47 read literally then produces a fleet page that
is empty on the user's own machine until they install hooks themselves. The one capability M1
exists to deliver would not be delivered.

**The evidence that there is a hookless path.** Two schemas already document it —
§"Live-session registry `~/.claude/sessions/<pid>.json`" and §"`claude agents --json`" — and I
re-verified both on this host on 2026-09-16 with **zero hooks installed**:

```text
$ claude agents --json
[{"pid":3971404,"cwd":"/root/Shepherd","kind":"interactive","startedAt":1789279600271,
  "sessionId":"2fb6befd-2e8e-47f2-986a-e24ed36aab8f","name":"shepherd-0b","status":"idle"},
 {"pid":3971492,…,"name":"shepherd-c8","status":"busy"},
 {"pid":3971545,"cwd":"/root/AIVisor",…,"name":"aivisor-29","status":"idle"}]
```

Three of the user's real sessions, visible with no hook. The per-pid sidecar carries more —
`sessionId · pid · procStart · cwd · kind · entrypoint · name · nameSource · nameSince · status ·
statusUpdatedAt · startedAt · updatedAt · version · tmux · pidDomain · messagingSocketPath ·
bridgeSessionId · peerProtocol · peerFeatures`.

What that yields for M1 with no hook installed:

| M1 need | Registry field | Note |
|---|---|---|
| Discovery | `sessionId`, `cwd` | `cwd` → repo via D48 (T7) |
| Interactive vs headless | **`entrypoint`** (`cli` vs `sdk-cli`) — **never `kind`**, which is `"interactive"` for both | proven 2026-09-16 (probe Finding 1); **the registry scan** filters on it (RD9). Not a scope rule: `attached` is about who launched the process (§19), and `entrypoint` is not on hook payloads at all (C8) |
| pid-reuse guard | `pid` + `procStart` | `procStart` **==** `/proc/<pid>/stat` field 22 — re-verified on this host: `531685515` in both |
| Liveness and `state` | `status` ∈ `idle` \| `busy` \| `waiting`, with `statusUpdatedAt` | covers most of §8's three live values with no hook event |
| A `needs_you` signal | `status:"waiting"` + `waitingFor` | the actual ask, per §7's `needs_you_reason` rule |
| Title | `name` + `nameSource` (`user` when `--name` was passed, `derived` otherwise) | maps straight onto D29's `title_source` ratchet |
| Terminal location (M3, noted only) | `tmux` = `"<session>:@<window>.%<pane>"` | the spec assumes attached sessions cannot be located in a terminal; this says otherwise |
| Container identity (D55) | `pidDomain` = `linux:<machine-id>:pid:[<ns inode>]` | D55's container shape showing up in real data |

**Options.**

| Option | For | Against |
|---|---|---|
| **(a) Hooks only, as §8 reads** | one ingest path; richest data | **the page is empty on the user's machine**, because K3 forbids installing the hook |
| **(b) Registry as primary, hooks as enrichment** | works today with zero installation; `sessionId` is a clean join key so both paths converge on one row; hook ingest simply makes the same rows richer when it is switched on | two sources to reconcile; the registry is a poll; its limits (below) are real |
| **(c) Registry only, drop hooks from M1** | simplest | throws away `tasks_*`, `active_subagents`, `repos_touched`, `brief` and every §8 signal — i.e. the differentiator |

**Recommendation — (b), and this is an elevation of D47, not a reversal.** D47 already names
`claude agents --json` as a discovery source; what changes is its rank, and the reason it changes
is a constraint that did not exist when D47 was written (the "do not touch my settings" rule).
D47's substance — *register on the first evidence of a session, whatever kind of evidence it is*
— is exactly what (b) does; the registry is simply another first evidence. **Both paths converge
on the same `session` row, joined on `sessionId`**, which is `session.engine_session_id` in §7.

**Consequences carried into the plan:**

1. A new task, **Task 7b**, owns the registry source. It is a *source*, not a second store: it
   produces the same `FoldDelta` shape the hook path produces (T11), so there is one writer and
   one set of fold rules (D37).
2. `shepherd doctor` reports which source is live — `hooks: not installed · registry: 3 sessions`
   — so a user is never left guessing why a column is null (principle 5).
3. When both sources speak about one field, **the newer observation wins** — recency, not source.
   See RD8 (overturned at revision 3) and Task 7b's precedence rule. Source is only the tie-break.

**The caveats, all from `data-schemas.md` or the 2026-09-16 probes, all carried into Task 7b:**

- **`-p` sessions DO register — proven, and the discriminator is `entrypoint`, not `kind`.**
  `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 1 launched `claude -p` with a
  ~20 s prompt and read the registry while `kill -0 <pid>` confirmed the process alive: pids
  4110260 and 4110361 both had a `<pid>.json` sidecar present during the run, deleted on exit.
  **`kind` is `"interactive"` even for `-p`** — it does not separate print mode from a TUI.
  **`entrypoint` does**: `sdk-cli` for `-p`, `cli` for interactive. *Any discovery code that
  branches on `kind` to decide "is this headless" is wrong.* This closes G9 and supersedes the
  "not verified" note in data-schemas, which was written against 2.1.270 and whose probe raced the
  exit. **Consequence for M1:** without an `entrypoint` filter, T7b would register every `-p` and
  SDK session as an attached interactive session. See RD9.
- **The file appears only after the trust dialog is accepted, and is deleted on exit.** So absence
  means *"not running, or not trusted"* — **never "finished successfully"**. **No stop is ever
  inferred from a missing file.** (A stop *is* inferred from an **observed process exit**, which is
  §8's own fourth clause — see Decision pressure 7.)
- **`waiting` / `waitingFor` are verified live, not a user-data shape.** `data-schemas.md`
  §"Session sidecar file `~/.claude/sessions/<pid>.json`" is marked *verified live 2026-09-14* and
  carries the real capture `{"status":"waiting",…,"waitingFor":"permission prompt"}` from
  `run-20260914T154946Z/06-sidecar-permission.json`. Revision 2 cited the weaker `partial` section
  and classified this `inferred`; that was a citation error. **G10 closes and A8 becomes
  `proven_by_code`.** The value is still counted on every occurrence, because counting a rare value
  is cheap and principle 5 wants it visible.
- **The `waiting → idle|busy` transition is a real, captured resolution signal — cited by capture
  pair, not by prose (r4, A5).** The *entry* is what `data-schemas.md` §PermissionRequest records
  ("the sidecar changes to `waiting` 14 ms after the hook"). The **exit** is in the captures and not
  yet in the prose: `run-20260914T154946Z/06-sidecar-permission.json` (`status:"waiting"`, `waitingFor:"permission prompt"`, `statusUpdatedAt:1789401085541`) → `07-sidecar-running.json` (`status:"busy"`, `waitingFor` cleared to null, `statusUpdatedAt:1789401094735`) — **same pid 4041880, same sessionId `71757dd1-…`, 9.2 s apart**. So on the registry path the exit from `needs_you` is
  **observed**, not inferred — which is the one thing G5 says the hook path lacks. T7b uses it;
  A9's residual shrinks to the hooks-only path. **`data-schemas.md` §Session sidecar file does not
  yet record this sequence**; that is a doc gap, not an evidence gap, and it is named here because
  "critical assumptions classified `inferred`: none" rests on this pair.
- **Never read the sibling `<pid>.<64hex>.key` file** — it holds a peer token (§Live-session
  registry). On this host those files are mode 0600 while the `.json` files are 0644; the reader
  globs `*.json` explicitly and a test asserts no `.key` path is ever opened.
- **The registry is a poll, and §12 says "no polling anywhere in the UI".** That constraint is
  about the **browser** — the UI is fed by SSE and never polls. A daemon polling its own data
  sources is not what §12 forbids, and saying so here stops a reviewer reading Task 7b as a
  violation.
- **New observation, this host, 2026-09-16:** a sidecar's **file mtime is not a liveness signal**.
  One of the three sidecars had an mtime of Sep 13 while its process was alive and `idle` —
  `updatedAt`/`statusUpdatedAt` advance only on a status change. Liveness therefore comes from
  `HostPlatform.process_liveness(pid, procStart)` (T3), never from the file's timestamp. This is
  also the real M1 call site that stops seam member (4) being speculative.

### Decision pressure 6 — §8's `state` rules have no row for "alive, and doing nothing"

**The decision under pressure.** §8 "`state` — three live values, hard signals only"
(`orchestrator-platform.md:982–990`) defines `stopped` as "`Stop`, `StopFailure`, `SessionEnd`, or
**observed process exit**" and `running` as "any tool/message signal within `LIVENESS_WINDOW_S`
(90)". §7's enum is `starting | running | needs_you | stopped`.

**The pressure.** The registry reports `status: "idle"` for a session whose process is **alive**.
Revision 2 mapped that to `stopped`. That is wrong and it is the K7 failure mode: an idle live
process is none of §8's four stop triggers, so the mapping was an **undeclared narrowing of §8's
stopped rule**. It is also contradicted by the captures: `data-schemas.md` §Session sidecar file
records that `status` **stayed `idle` across the 60 s `idle_prompt` notification**
(`04-sidecar-idle.json`) — the exact moment at which §8 puts that session in **`needs_you`**. On
the user's own machine (no hooks, registry-primary — the case Decision pressure 5 exists to serve)
the common case is an idle attached session, and revision 2 rendered every one of them `stopped`
while alive.

**Options.**

| Option | For | Against |
|---|---|---|
| **(a) `idle` → `stopped`** (revision 2) | simple | asserts a stop §8 does not license; contradicts `04-sidecar-idle.json`; the common case on the user's machine renders wrong |
| **(b) `idle` → `running` while the pid is alive** | never asserts a stop | dishonest in the other direction: a session idle for an hour is not running, and it would outrank nothing in the fleet sort |
| **(c) `idle` → `starting`** (§7's fourth value) | no new value | `starting` means "spawned, no signal yet" (§8) — a *different* claim, and M1 spawns nothing |
| **(d) split on the age of `statusUpdatedAt`, mirroring §8's own two rules** | uses only §8's existing rules and constants; makes the two sources **agree** instead of contradicting each other, which is what P14 needs | needs the pressure written down, because §8 never contemplated a non-hook idle signal |

**Recommendation — (d).** The mapping becomes, for a session whose pid is **alive**:

| Registry observation | `state` | Which §8 rule licenses it |
|---|---|---|
| `status: "busy"` | `running` | "any tool/message signal within `LIVENESS_WINDOW_S`" — `statusUpdatedAt` **is** the signal time |
| `status: "idle"`, `statusUpdatedAt` within 60 s | `running` | same rule; the session just finished a turn and the hook path would still be inside its own liveness window |
| `status: "idle"`, `statusUpdatedAt` older than 60 s | `needs_you`, reason `"idle — waiting for your next instruction"` | §8's `idle_prompt` row **verbatim**, at the measured 60 s (C21: `idle_prompt` arrives 60.03 s after `Stop`). This is Decision pressure 3's consequence, reached from the other source |
| `status: "waiting"` + `waitingFor` | `needs_you`, reason = `waitingFor` | §8's `needs_you` row (an unresolved permission prompt) |
| `status` outside `{idle, busy, waiting}` | **prior `state` kept**, anomaly counted | nothing in §8 licenses a state change from a value we cannot read; principle 5 makes it visible (r4, A9) |
| pid **not alive** (or `procStart` differs) | `stopped`, `ended_at = observed_at` | §8's fourth stop trigger, "**observed process exit**" — verbatim |
| sidecar absent, pid unknown | *(unchanged)* | E29/P16: absence is "not running or not trusted", never a stop |

**Why this is a pressure and not a silent change:** it adds no state and reverses no rule, but it
*applies* §8's `idle_prompt` row to a source §8 never named, and it makes the 60 s constant
load-bearing on a second path. Both are visible consequences a reviewer may reject — in which case
(b) is the fallback and idle sessions simply never leave `running` until their process exits.

**It also removes a contradiction between the two sources.** Under revision 2, a hooks-installed
machine put an idle session in `needs_you` (via `idle_prompt`) while the registry put the same
session in `stopped` — two sources, one row, opposite verdicts, resolved only by whichever wrote
last. Under (d) they agree by construction, which is what P14 is for.

### Decision pressure 7 — §7's `session` table cannot store what liveness needs, so the hookless path can never end a session

**The decision under pressure.** §7's `session` table. C13 states the limitation outright: *"there
is no `pid`/`procStart` column, so `crashed` versus `stopped` cannot always be separated."*

**The pressure.** After Decision pressure 6, the registry path's **only** legal stop signal is
`HostPlatform.process_liveness(pid, start_token)` — §8's "observed process exit". Its two inputs
are `pid` and `procStart`, which live **only in the sidecar**, and the sidecar is **deleted on
exit** (E29). Revision 2 read them and explicitly did not store them ("read, not stored at M1").
So at the exact moment a session ends, both inputs vanish, the row freezes in its last state, and
`ended_at` is never set. **Acceptance criterion 2 is unreachable on the path this plan calls
critical**, and no task owned the problem.

**Options.**

| Option | For | Against |
|---|---|---|
| **(a) two nullable columns on `session`: `pid INTEGER`, `proc_start TEXT`** | the state survives a `controld` restart; closes the limitation C13 names by name; two columns, one migration line | a §7 change — the schema is a numbered artefact and this widens it |
| **(b) an in-memory liveness map in `controld`** | no schema change | lost on every restart — and T18 restarts `controld` deliberately; after a restart no session whose sidecar has already vanished can ever be ended, which is the same bug with a smaller window |
| **(c) a JSON blob in `app_state` keyed by session id** | no `session` change | a schema hiding inside a value column; every reader needs bespoke code; strictly worse than (a) and less honest |

**Recommendation — (a).** `pid` and `proc_start` are nullable, written **only** by the registry
path, and read only by the liveness sweep. C13 records their absence as a *limitation* of the
current schema, not as a design choice to preserve — closing it is what C13 anticipates. **This is
a widening of §7 and is flagged, not applied silently**; it appears in the Plan-vs-spec gaps table
(M13), in Task 5's migration, and in acceptance criterion 2. A reviewer who rejects it gets (b) and
must accept that a `controld` restart permanently freezes any session that ended while it was down.

---

## Vocabulary (used exactly, throughout)

The domain words come from the spec; this plan adds none. Two pairs need stating because the spec
uses both halves:

| Persistence word | Consumer-facing word | Why both | Source |
|---|---|---|---|
| `workspace` (the table, `session.workspace_id`) | **project** (the tool names `list_projects()` / `list_sessions(project_id=…)`, the fleet page's "projects → sessions → subagents") | D22: "A project is a workspace of 1..N repos." They are the same entity; §7 names the row, §11 and §12 name the thing a human sees. | §7, §11, §12, D22 |
| `attached` session | the only kind M1 sees | §19 glossary | §19 |

**The tool names in §11 are used verbatim** (`fleet_summary`, `list_projects`, `list_sessions`,
`get_session`, `list_subagents`). M4's acceptance test is "no file in `web/` or `cli/` changes"
(D38) — renaming a tool now would break that test three milestones early.

**A signal is engine-neutral.** §5.0: "Engine-specific vocabulary stays inside its adapter…
`signals/` consumes what `EngineAdapter` produces, not what Claude Code emits. If swapping the
engine would edit `signals/`, the boundary has leaked." This plan makes that mechanical: the 33
Claude Code hook names appear **only** in `engines/claude_code/`, and a test greps `signals/` for
all 33 and fails on any hit.

---

## Functionality flows (every step and every error path maps to a test)

```
Flow A0 — a session becomes visible with NO hook installed (the user's actual machine)
1. human runs `claude` in a repo, accepts trust → Claude Code writes ~/.claude/sessions/<pid>.json
2. controld's registry scan reads *.json       → never the sibling .key file
                                                 test: test_registry_never_opens_key_file
3. pid + procStart checked for liveness         → HostPlatform.process_liveness, not file mtime
                                                 test: test_liveness_ignores_file_mtime
3b. entrypoint == "sdk-cli" (a -p run)           → skipped and counted (REGISTRY PATH ONLY —
                                                 the hook path registers it, D47/C8)
                                                 test: test_sdk_cli_entrypoint_is_skipped_and_counted
4. unknown sessionId                            → register a session row, cwd → repo (D48)
                                                 test: test_registry_registers_unknown_session
   …and pid + proc_start are stored on the row   → so liveness survives the sidecar's deletion
                                                 test: test_register_stores_pid_and_proc_start
5. status busy | idle<60s | idle>60s | waiting   → running | running | needs_you | needs_you
                                                 test: test_registry_status_maps_to_state (DP6)
5b. waiting → idle|busy observed                 → needs_you cleared from a captured signal
                                                 test: test_leaving_waiting_clears_needs_you
6. name + nameSource                            → title + title_source (D29 ratchet)
                                                 test: test_registry_name_sets_title_source
7. same sessionId later arrives on a hook event → SAME row; newer observation wins per field
                                                 test: test_sources_converge_on_session_id
8. the pid stops being alive                    → state stopped, ended_at set (§8 "observed exit")
                                                 test: test_dead_pid_sets_stopped_with_ended_at
Error paths:
- sidecar disappears        → session is NOT marked finished; liveness decides
                              test: test_absent_sidecar_is_not_a_stop
- sidecar is malformed      → counted, skipped, scan continues
                              test: test_malformed_sidecar_is_counted
- claude agents --json slow → bounded timeout, previous snapshot kept, counted
                              test: test_agents_json_timeout_is_bounded

Flow A — a hand-launched session becomes visible (hooks installed — the richer path)
1. human runs `claude` in a repo          → (nothing yet)
2. hook fires on that session's next event → hookd writes the payload to sessiond's UDS
                                              test: test_hookd_delivers_payload_bytes
3. sessiond frames it, stamps nothing      → relays to controld
                                              test: test_sessiond_relays_and_buffers
4. controld stamps received_at, normalises → engine-neutral Signal
                                              test: test_normalise_all_33_event_names
5. unknown session_id, ANY event kind      → register a session row (D47)
                                              test: test_registers_on_first_event_of_any_kind
6. cwd → repo via --git-common-dir (D48)   → repo_id, workspace_id
                                              test: test_bind_worktree_to_main_repo
7. fold sets last_event_at / state / brief → session row updated
                                              test: test_fold_golden_corpus (429 events)
8. controld emits an SSE envelope           → fleet page row appears without a reload
                                              test: test_sse_emits_on_state_change
Error paths:
- sessiond down            → hookd exits 0 in 3.6 ms, event lost, nothing blocks
                             test: test_hookd_exits_zero_with_no_listener
- controld down            → sessiond buffers, counts overflow, drains on reconnect
                             test: test_relay_buffer_overflow_is_counted
- malformed payload        → counted as an anomaly, never crashes the fold
                             test: test_fold_malformed_payload_is_counted
- cwd is not a git repo    → repo_id null, counted, session still visible
                             test: test_bind_non_repo_yields_null_repo_id
- git dubious ownership    → repo_id null, counted (rc=128)
                             test: test_bind_dubious_ownership_is_counted

Flow B — the human opens the fleet page
1. GET /                → static ES modules, no build step
                          test: test_static_assets_served_without_build
2. GET /api/fleet       → toolsurface.invoke("fleet_summary")   test: test_fleet_route_goes_through_invoke
3. render tree          → workspace → session → subagent        test: test_fleet_ordering
4. GET /api/events      → SSE stream, seq monotonic             test: test_sse_seq_monotonic
5. reconnect w/ Last-Event-ID → contiguous replay or explicit gap
                          test: test_sse_replay_from_last_event_id
Error paths:
- untrusted text in a title/brief → escaped or textContent only
                          test: test_no_unescaped_interpolation_in_frontend
- unknown tool name              → ToolResult error, never a stack trace to the browser
                          test: test_unknown_tool_returns_generic_error
- seq older than the ring        → explicit `gap` event, never silent loss
                          test: test_sse_replay_gap_is_explicit

Flow C — install and uninstall the hook
1. `shepherd install-hooks`  → back up settings.json first     test: test_install_backs_up_first
2. merge marked entries      → every entry carries _shepherd_managed
                               test: test_installed_entries_are_marked
3. validate after writing    → refuse and roll back on invalid JSON / broken entry
                               test: test_install_rolls_back_on_invalid_result
4. `shepherd uninstall-hooks`→ exactly our entries removed, user's hooks untouched
                               test: test_uninstall_leaves_foreign_hooks
Error paths:
- nc absent on this host     → install refuses with a reason; no hook is written
                               test: test_install_refuses_without_dispatch_binary
- socket path over budget    → install refuses before writing (Linux 107 / macOS 103)
                               test: test_install_refuses_over_socket_path_budget
- a pre-existing malformed PreToolUse entry → detected and reported (C6)
                               test: test_install_detects_pre_existing_breakage
```

---

## Risk-based testing matrix

| Risk | Prob | Impact | Test required |
|---|---|---|---|
| The dispatcher harms Claude Code (blocks, fails, or delays a turn) | med | **high** | deterministic: `test_hookd_exits_zero_*` (5 cases incl. daemon-down, oversized, malformed, binary-absent) + a measured latency assertion under 10 ms |
| Hook install corrupts the user's settings and disables **all** their hooks (C6) | med | **high** | deterministic: `test_install_*` suite against an isolated `CLAUDE_CONFIG_DIR`; a test asserts the real `~/.claude/settings.json` sha256 is unchanged across the whole suite |
| `active_subagents` goes negative (C10) | **high** | med | deterministic: `test_subagent_count_never_negative` over the corpus (2 starts vs 4 stops is in the fixtures) + a property test |
| `repos_touched` stays empty because `FileChanged` never fires for agent edits (C9) | **high** | med | deterministic: `test_repos_touched_from_posttooluse_paths` over S09/S13 fixtures |
| `brief` is a `<task-notification>` blob (C11) | **high** | med | deterministic: `test_brief_ignores_injected_prompts` over S18 fixtures |
| A worktree session gets `repo_id = null` because of prefix matching (D48) | **high** | med | deterministic: `test_bind_worktree_to_main_repo` against a throwaway worktree |
| A token in `vcs_remote` reaches the DB/UI (D50) | low | **high** | deterministic: `test_vcs_remote_strips_userinfo` (property test over the 7 captured URL forms) |
| Untrusted content reaches `innerHTML` (§13) | med | **high** | deterministic: `test_no_unescaped_interpolation_in_frontend` (static scan of `web/static/*.js`) |
| The consumer or storage boundary erodes under pressure (§5.0 "the one thing to watch") | **high** | **high** | deterministic: `test_consumer_boundary`, `test_storage_boundary`, `test_no_engine_vocabulary_in_signals`, `test_nothing_imports_daemons`, `test_hookd_imports_nothing_from_shepherd`, **`test_layer_direction_is_downward_only`** (the general §5.0 rule — F5) |
| **A boundary test fires on the plan's own prescribed code, so the first thing a builder does is add an exemption** ("how boundaries die" — ADR-1) | **high** *(certain in revision 2)* | **high** | deterministic: the scans are **AST-based, not text**, and each ships a paired *negative* fixture: `test_scan_does_not_fire_on_declared_evidence_strings`, `test_scan_does_not_fire_on_attribute_names` (T2, F4) |
| A platform branch (`/proc`, `systemctl`) leaks into `signals/`, `store/`, `web/` or `cli/`, making D55's seam decorative | **high** | **high** | deterministic: `test_no_platform_branching_outside_host` (P7b) |
| Two writers race one migration (§7 rule 3) | low | **high** | deterministic: `test_sessiond_never_migrates` + `test_version_mismatch_refuses_to_start` |
| Concurrent folds from N sessions corrupt a row | med | **high** | deterministic: `test_fold_concurrent_interleave` (synthetic interleave built from `_epoch` — see the fixture gap below). **Note (r3):** this covers the *pure fold* only; the shared mutable state lives in `controld` and is covered by P18/P19 (ADR-7) |
| Socket path exceeds `sun_path` on macOS (103 < 107) | med | med | deterministic: `test_socket_path_budget_enforced` in the `HostPlatform` contract suite |
| `XDG_RUNTIME_DIR` unset ⇒ hookd cannot find the socket (C3) | med | med | deterministic: `test_runtime_dir_falls_back_to_run_user_uid` |
| SSE loses events across a reconnect | med | med | deterministic: `test_sse_replay_from_last_event_id` + `test_sse_replay_gap_is_explicit` |
| `MacHost` is wrong | **high** | low *(at M1)* | manual checklist + `ScriptedHost` contract suite; `MacHost.verified() is False` is asserted, and the UI/CLI say so |
| Hook write volume at 20 concurrent sessions (§18) | med | med | probabilistic: `test_ingest_throughput` — 20×`PostToolUse` bursts, assert p95 fold < 5 ms, **flake policy: 3 retries, fail on 2 of 3** |
| **The fleet page is empty because no hook is installed** (K3) | **high** *(certain without Task 7b)* | **high** | deterministic: `test_registry_registers_unknown_session` + the live `test_hookless_discovery_sees_running_sessions` (T18) |
| **A vanished sidecar is misread as "session finished"** | **high** | **high** | deterministic: `test_absent_sidecar_is_not_a_stop` — absence is *not running or not trusted*, never a stop |
| **A peer token is read from a `.key` sidecar** | low | **high** | deterministic: `test_registry_never_opens_key_file` (the reader globs `*.json`; the test asserts no `.key` path is opened) |
| The two discovery sources disagree and create duplicate rows | med | **high** | deterministic: `test_sources_converge_on_session_id` (P14) + `ux_session_engine_id` partial unique index makes P14 true by construction (F14) |
| **A `-p`/SDK session flickers through the fleet page from the 2 s registry poll** (proven to register — probe Finding 1; `kind` is `"interactive"` for both) | **high** *(certain without the filter)* | med | deterministic: `test_sdk_cli_entrypoint_is_skipped_and_counted`, `test_kind_is_never_branched_on` (AST: no comparison against `RegistryEntry.kind`). **Registry path only** — the hook path must keep registering `-p` runs (C8, RD9) |
| **The dispatch command loses `-q0` in a copy** — 3.2 ms → 253.6 ms on every hook of every session, **while still delivering**, so no test fails and it reads as "Claude Code got slow" | med | **high** | deterministic: `test_dispatch_command_has_one_definition_site` (AST, T2), `test_dispatch_command_shuts_down_write_side` (T8, a listener that reads to EOF must see EOF in < 50 ms), `test_hookd_latency_under_10ms` (T8) |
| **The hookless path can never end a session** (liveness inputs vanish with the sidecar) | **high** *(certain without DP7)* | **high** | deterministic: `test_dead_pid_sets_stopped_with_ended_at`, `test_liveness_survives_controld_restart` (T7b/T18) |
| **An idle live session renders `stopped`** (the common case on the user's machine) | **high** *(certain without DP6)* | **high** | deterministic: `test_registry_status_maps_to_state`, `test_idle_live_session_is_never_stopped` (T7b) |
| **Three concurrent writers corrupt the store or the SSE ring** (HTTP threads + fold + 2 s registry scan against one `Store`) | med | **high** | deterministic: `test_store_writes_are_serialised_under_threads`, `test_reads_use_a_thread_local_connection`, `test_stream_ring_is_thread_safe` (ADR-7, T6/T14) |
| **The `sessiond → controld` hop loses frames or starts against a mismatched schema** (§7 rule 3) | med | **high** | deterministic: `test_relay_frame_roundtrip_40kb`, `test_relay_refuses_on_schema_version_mismatch`, `test_relay_drains_in_order_on_reconnect` (T10b) |
| **The live lane cannot authenticate** under an isolated `CLAUDE_CONFIG_DIR`, and the failure looks like a Shepherd bug | **high** *(certain — probe Finding 3)* | med | deterministic: `test_live_lane_uses_real_config_dir_with_working_dir_isolation` + the P13 hash guard asserted **per test**, not per suite (T18) |

---

## Blocker protocol (explicit, per the user's instruction)

A builder that hits a blocker **marks it and moves to the next workable area. It does not stop the
milestone.**

1. Write a line to `docs/plans/2026-09-16-m1-BLOCKERS.md`:
   `T<id> · <one-line symptom> · <what was tried> · <what it blocks> · <suspected owner: evidence gap | decision gap | host gap | upstream bug>`.
2. If the blocker is an **evidence gap** (a shape not in `data-schemas.md`), the entry names the
   probe that would close it. Do not guess the shape. Do not build on the guess.
3. If the blocker is a **decision gap** (implementation pressure against one of the 55), write the
   pressure into the blockers file in the same four-part form this plan uses
   (decision · pressure · options · recommendation) and **do not apply the recommendation**.
4. Mark the task `BLOCKED` in the plan's task list, leave the partial work behind a failing test
   with a `pytest.mark.xfail(reason=…)` that names the blocker id, and pick up the next task whose
   `Dependencies` are all satisfied.
5. A task blocked on **macOS verification specifically is not a blocker** — it is the expected
   state (`MacHost` ships unverified by design, D55). Mark it `unverified`, not `BLOCKED`.

The dependency graph is deliberately shallow: after Task 2 there are three independent tracks
(host · store · hook plumbing), so a blocker in any one of them leaves two workable.

---

## Evidence gaps — named here so BUILD does not discover them

Each row is a shape or a behaviour M1 touches for which **no capture exists**. K1 applies: the
task's first step is a probe, or the behaviour ships explicitly unverified and says so.

| # | Gap | Effect on M1 | Disposition |
|---|---|---|---|
| G1 | **Everything macOS.** No capture exists for any macOS path, socket budget, `launchctl`, `ps`/kqueue liveness, `RunAtLoad`, or `nc` flag set. | `MacHost` is written from D55's prose and the platform's documented behaviour. | Ships with `verified() → False`; every `MacHost` value carries a `# UNVERIFIED (no capture)` comment citing D55; the contract suite runs against it with real-host assertions skipped and `ScriptedHost` covering the logic. `shepherd doctor` prints `host: macOS (unverified driver)`. |
| G2 | **`nc` on macOS.** `-q0` is not portable; macOS's netcat is a different build — **and on Linux `-q0` is worth 250 ms per invocation** (Result 1b, E34). | The hook command line differs per host, on exactly that flag. | `HostPlatform.hook_dispatch()` — **the sixth seam member** — owns the command, and is the only definition site of it (P20, Decision pressure 2). `MacHost`'s command is unverified, marked, and returns `available=False` with a reason, so installer preflight refuses rather than writing a dead or slow hook. |
| G3 | **Multi-session concurrency in the fixtures.** The 429 captures are 50 **sequential** sessions; nothing exercises contention on the fold. | The concurrency risk above is untested by fixtures alone. | Task 12 builds a **synthetic interleave** by merge-sorting all 429 envelopes on `_epoch` across session ids — a real ordering from real events, not invented data — plus a live 3-session run in Task 18. |
| G4 | **`Notification{idle_prompt}` outside the single TUI run** (I01). One capture, one session. | The `needs_you` rule that will dominate the fleet page rests on 1 observation. | Fold rule is written and tested from the one capture; `shepherd doctor --anomalies` counts how often it is seen in real use (principle 5). Not blocking. |
| G5 | **No resolution event for `PermissionRequest`.** It carries no `tool_use_id`; a TUI Esc rejection emits nothing; `-p` auto-refusal shows only in `PostToolBatch`. | `needs_you` can be entered but has no explicit exit signal. | Clearing rule is inferred and written down as such (see the fold table); tested over the I01 and S09 fixtures. Recorded as a known imprecision, counted, and handed to M2. |
| G6 | *(superseded by Decision pressure 5 — the registry is now M1's primary discovery source; see G9, G10, G11.)* | — | — |
| ~~G9~~ | **CLOSED at revision 3.** Whether `-p` sessions appear in the registry. | — | **Proven: they do.** `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 1 (pids 4110260/4110361, sidecar present while `kill -0` confirmed the process alive, deleted on exit). The gap is replaced by a **design consequence**: `kind` is `"interactive"` for `-p` too, so `entrypoint` (`sdk-cli` vs `cli`) is the discriminator, and T7b must filter on it (RD9). |
| ~~G10~~ | **CLOSED at revision 3 — it was a citation error, not a gap.** `status: "waiting"` / `waitingFor`. | — | `data-schemas.md` §"Session sidecar file" is **verified live 2026-09-14** and carries the real capture `{"status":"waiting",…,"waitingFor":"permission prompt"}`. Revision 2 cited the weaker `partial` section. A8 becomes `proven_by_code`. Still counted on every occurrence (principle 5), but no longer an unknown. |
| G12 | **Engine version drift.** `data-schemas.md:3` pins all 127 shapes to `2.1.270`; this host runs **2.1.273** (`docs/probes/2026-09-16-registry-and-version-drift.md` Finding 2). | Every per-event *field* shape M1 folds is verified at 2.1.270 only. | **Half closed, cheaply, and the residual is named.** `docs/probes/drift_check.py` (in-repo, ~30 lines, needs no live session) re-verified against the 2.1.273 binary: all **33 event names present**, and `SessionEnd.reason` / `SessionStart.source` / `StopFailure.error` / `Notification.type` **byte-identical as exact ordered literals**. So the fold's and M2's enum surface is unchanged. **Residual:** per-event field shapes (the zod schemas), which the extractor would have given but no longer runs (below). Acceptable because C8 makes the fold field-tolerant — only four fields are on every event — but not zero. **M1 owns the check as a step:** Task 1 runs `drift_check.py` before any fold code is written, and a moved name or enum is a blocker entry. |
| G13 | **A stored artefact contradicts its own citation.** `docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json` is **empty on disk** (`{"offset":null,"count":0,"events":null}`) although `data-schemas.md:242` cites `"count": 33` from it; and `extract_binary.py` no longer runs against 2.1.273 (`ValueError: subsection not found` — minified anchors move every build). | T2's `CLAUDE_CODE_HOOK_EVENT_NAMES` and T9's `ALL_HOOK_EVENT_NAMES` were sourced from a file that holds nothing. | **The names' real source is the `claude doctor` capture**, `hooks/live/R03_config_unknown_event_name/doctor.txt`, which lists all 33 verbatim in its "Valid events:" line. **Two independent copies, one reconciling test** (r4, A7): T9's `ALL_HOOK_EVENT_NAMES` is a **literal tuple in `engines/claude_code/events.py`** — product code must not read the probe tree at runtime, or M6's installed package breaks — while T2's `CLAUDE_CODE_HOOK_EVENT_NAMES` **parses the capture**, and `test_hook_event_names_match_the_doctor_capture` asserts the two are equal, in order, 33 of them. Repairing the empty JSON and the extractor's anchors is **not M1 work** and is recorded here so a future reader does not trust the empty file. |
| G11 | **Registry poll interval.** No capture says how often `status` changes or what interval is cheap. | A too-fast poll wastes work; a too-slow one makes the page stale. | Default 2 s for sidecar files (a directory read of ~3 files) and **never** shell out to `claude agents --json` on a timer — the CLI forks a `claude` process per poll (§`claude agents --json`) and is used only as a one-shot fallback when the sidecar directory is absent. Listed as RD7. |
| G7 | **Running as a non-root user.** Every probe ran as root, which is the actual user here. | Socket modes, `/run/user/<uid>`, and linger are uid-sensitive. | `LinuxHost` derives `/run/user/<uid>` from `os.getuid()` rather than hard-coding `0`; the contract suite asserts the derivation, not the literal. |
| G8 | **`pr-link` entries** were never observed (0 in user data, 0 in probes). | `session.pr_url` may stay null forever. | Column exists; nothing in M1 writes it; the UI hides the chip when null. No claim is made that it is "free" (spec correction l.681). |

---

## Codebase Reality Check (verified on this host, 2026-09-16)

Every row below was checked by running the command, not recalled. This is what M1 is actually
being built against.

| Fact | How it was verified | Consequence for the plan |
|---|---|---|
| **The repo is docs-only. There is no product code.** `ls /root/Shepherd` → `CLAUDE.md`, `docs/`. `src/` does not exist. | `ls`, `git status` (branch `main`, one baseline commit `22d9ef2`) | This is **greenfield**. No existing pattern to follow, no call sites to preserve, no refactor. Every `src/shepherd/**` path in the task list is a **file to create**, not one to edit. Task 1 creates the tree. |
| `docs/plans/2026-09-13-m1-foundation-visibility-plan.md` exists and is **stale** | `ls docs/plans/` | Not read, not diffed, not extended (user instruction). This plan is a fresh artifact at a new path. |
| `docs/reviews/2026-09-14-m1-plan-review/` exists | `ls docs/reviews/` | A review of the **stale** plan. Not an input; not read. |
| **No ADR directories exist** — `docs/adr/`, `docs/decisions/`, `docs/rfcs/` are all absent; no `*ADR*.md` anywhere | `ls`, `find . -iname '*adr*'` | There are no pre-existing ADRs to contradict. The architecture of record is **§3's 55 decisions**, which this plan treats as settled and never silently reverses (K7). The six ADRs in this plan are new and additive. |
| **Toolchain is the venv, not the system Python.** `/root/Shepherd/.venv/bin/` has `pytest`, `mypy`, `pip`, `jsonschema`, `mcp` | `ls .venv/bin/` | Every command in this plan is `.venv/bin/…`. The system `python3` has **no pip and no ensurepip** (data-schemas §Runtime toolchain), so `python3 -m venv` cannot be recreated on this host — the existing venv is the environment. |
| **SQLite 3.45.1** via the Python module; **no `sqlite3` CLI** | data-schemas §Runtime toolchain | ≥ 3.39, so `FULL OUTER JOIN` is available — §18's open row. T5 asserts it on the running interpreter rather than trusting the number. Every schema check goes through Python. |
| **`nc` is present** (OpenBSD netcat 1.226-1ubuntu2); **`socat` is absent**; `timeout` present | `command -v nc socat timeout` | The T8 dispatcher is buildable here. `socat` is not an alternative on this host. The installer preflight (G2) is not theoretical. |
| **No node / npm / tsc** | data-schemas §Runtime toolchain | D51's "plain ES modules, no build step" is **aligned with the host**, not a compromise. The frontend escaping rule is enforced by a Python static scan (T16), because no JS test runner exists. |
| **No Secret Service, no keyring** | data-schemas §Credential store availability | Irrelevant to M1 (no credentials until M4), and recorded so M4 does not rediscover it. |
| **The 429-event corpus is real and intact**: 429 lines, **0 malformed**, **50 distinct `session_id`s**, **54 scenario dirs of which 53 carry `events.jsonl`**, 32 distinct `_event` values | parsed every `events.jsonl` under `hooks/live/` | T12's lane is buildable today against real data. The counts in T12 are measured, not estimated. |
| **Three of the user's real `claude` sessions are visible with zero hooks installed** — `claude agents --json` returned 3 entries; `~/.claude/sessions/` holds 3 `.json` sidecars (mode 0644) and 3 `.key` files (mode 0600) | ran `claude agents --json`; `ls -la ~/.claude/sessions/` | This is the evidence base for Decision pressure 5 and Task 7b. |
| **`procStart` == `/proc/<pid>/stat` field 22**, re-confirmed: `531685515` in both for pid 3971404 | read both | T7b's pid-reuse guard (E31) is proven on this host, not inferred. |
| **A sidecar's mtime is not liveness** — one sidecar's mtime was 3 days old while its pid was alive and `idle` | `ls -la ~/.claude/sessions/`, `ls /proc/<pid>` | E30. This is a fact this plan discovered; it is not in `data-schemas.md` and is labelled as newly observed wherever it is used. |
| **The engine on this host is `2.1.273`; every schema in `data-schemas.md` was captured against `2.1.270`** — versions `2.1.269 · 2.1.270 · 2.1.271 · 2.1.273` are installed | `claude --version`; `ls /root/.local/share/claude/versions/`; `data-schemas.md:3` | **Three patch versions of drift, recorded rather than assumed away** (G12). D41's re-probe trigger firing for the first time. `docs/probes/drift_check.py` closed the cheap half (33 names + 4 enums unchanged, byte-identical ordered literals); per-event field shapes remain at 2.1.270. Task 1 re-runs the check before the fold is written. |
| **`hooks/binary/hook-events.json` is empty on disk** (`{"offset":null,"count":0,"events":null}`) though `data-schemas.md:242` cites `"count": 33` from it; `extract_binary.py` dies on 2.1.273 with `ValueError: subsection not found` | `cat` the file; ran the extractor | **A stored artefact that contradicts its own citation** (G13). The 33 names are still good — they come from `hooks/live/R03_config_unknown_event_name/doctor.txt`, whose "Valid events:" line lists all 33. T2 and T9 source from that capture, and a test parses it rather than trusting a hand-copied tuple. |
| **`claude -p` sessions DO appear in the registry**, and `kind` is `"interactive"` for them — `entrypoint` (`sdk-cli` vs `cli`) is the discriminator | `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 1 (pids 4110260/4110361, sidecar present under `kill -0`) | Closes G9. `scan_registry` **must** filter on `entrypoint`, never on `kind`, or every `-p` run flickers through the fleet page (RD9, F3). The filter stops at the registry: `entrypoint` is not a hook-payload field (C8). |
| **There is no hermetic authenticated `claude` on this host.** `CLAUDE_CONFIG_DIR=<throwaway>` → `Not logged in · Please run /login`, rc=1 | `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 3 | **Isolation and authentication are mutually exclusive for live runs.** T18's isolation rule 1 is rewritten around it (F10): real config dir, isolation by working directory + `--settings`, K3 upheld by the P13 guard rather than by construction. |
| **The user has live tmux sessions on the `shepherd` socket** | `CLAUDE.md`; the hook-env capture shows `TMUX=/tmp/tmux-0/shepherd,…` | K6 is not a precaution, it is a live hazard. T18's isolation rules are written against it. |

**Technical-approach match.** There is no existing code to match, so the applicable check is
*does the approach match the project's declared stack and the host's actual capabilities?* —
Python 3.12 + `mypy --strict` (principle 6, venv has mypy 2.3.1), stdlib HTTP/SSE (§5), SQLite via
the stdlib module (§5, D26), plain ES modules with no build step (D51, and no node exists), argv
lists with no `shell=True` (§13). Every one of those is satisfied by the host as measured above.

**Unstated infrastructure: none.** M1 introduces no external service, no environment variable it
does not itself define, and no database beyond one SQLite file whose path is resolved by
`HostPlatform` (ADR-2). The only host binaries relied on are `git`, `nc`, `timeout` and `claude` —
all verified present, and the one that could be absent (`nc`) has an explicit preflight refusal.

---

## Plan-vs-spec gaps — where this plan and the written design disagree

The usual form of this table is plan-vs-code. **There is no code** (see above), so the artifact of
record is the spec, and this is the honest equivalent: every place the plan does something the
spec does not literally say, with the reason and a spot-checkable citation.

| # | Spec says | Plan does | Why | Evidence |
|---|---|---|---|---|
| M1 | §8 shows `hookd.py`, a Python dispatcher | a `sh` + `nc -U` one-liner | 31.7 ms → 3.4 ms measured; the Python shape lost `StopFailure` 2/2 at shutdown. §8's block is illustrative; D37 fixes only the *destination*, not the language | Decision pressure 1; `docs/probes/2026-09-16-hookd-latency.md`; C7 |
| ~~M2~~ | ~~D55: the seam owns **exactly five** things~~ | **NO LONGER A GAP (r4).** D55's row was amended to **six** on 2026-09-16 by its author and now names the hook-side dispatch command as the sixth member, so the plan's `hook_dispatch()` matches the decision log exactly. Retained as a row so the history is legible | — | `orchestrator-platform.md:165`; Decision pressure 2 |
| M3 | D47: `claude agents --json` is a **supplementary** source | the registry is M1's **primary** discovery, liveness and state source | K3 means no hook is installed, so the hook path sees nothing; D47's substance ("register on first evidence") is preserved | Decision pressure 5; verified live above |
| M4 | §5.0's five layers name ten packages | four more exist: `host/`, `daemons/`, `testkit/`, and `hookd` inside `engines/` | §5.0 predates D55 and never placed the process entrypoints | ADR-1; RD4 |
| M5 | §11.0 types `audiences` as `{MASTER, SESSION}` | a third value, `HUMAN` | §11.0's own table lists five consumers including `web/` and `cli/`; two values cannot serve them | ADR-3; RD2 |
| M6 | §12 specifies an SSE endpoint; D35 says L5 reaches the system only through L4 | L4's interface is two functions — `invoke()` **and** `subscribe()` | a stream is not a tool call and has no other legal home | ADR-4; RD3 |
| M7 | §8 subscribes 24 events and omits `PostToolBatch` | subscribes `PostToolBatch` too | it is the **only** event that records a permission refusal or hook block | data-schemas §PostToolBatch; RD5 |
| M8 | §7 lists `session.work_item_id` with `FK` | column created with **no** foreign key | the `work_item` table arrives at M5; a FK to a missing table is a runtime error | RD6 |
| M9 | §12: "**No polling anywhere in the UI**" | the *daemon* polls the registry every 2 s; the **UI still never polls** | the constraint is about the browser, which is SSE-fed | Decision pressure 5, final caveat; RD7 |
| M10 | §8's `state` table makes `idle_prompt` a `needs_you` | implemented **literally**, with the consequence written down (every idle session sorts to the top after 60 s) | the decision log is law; the consequence is surfaced, not silently softened | Decision pressure 3; C21 |
| M11 | §7: `brief` for attached sessions is the transcript's `lastPrompt` | prefer `UserPromptSubmit.prompt` of the **first** prompt; transcript is fallback | `lastPrompt` is the *latest* prompt, truncated and newline-flattened, and stale in a fork | spec correction l.664; C11 |
| M12 | §7/§8: `repos_touched` accumulates from `FileChanged` | accumulates from `PostToolUse{Edit,Write}.tool_input.file_path` | `FileChanged` never fires for agent edits | C9; spec correction l.680, 886 |
| M13 | §7's `session` table has no `pid` / `procStart` column, and C13 names that as a limitation | **two nullable columns added**, `pid INTEGER` and `proc_start TEXT`, written only by the registry path | without them the sidecar's deletion destroys both liveness inputs and the hookless path can never set `ended_at`; C13 records the absence as a limitation, not as a choice to preserve | **Decision pressure 7**; C13; E29 |
| M14 | §8 defines `stopped` as `Stop`/`StopFailure`/`SessionEnd`/**observed process exit** and says nothing about a registry `status` | registry `idle` maps to `running` (< 60 s) or `needs_you` (≥ 60 s) and **never** to `stopped`; `stopped` comes only from an observed process exit | an idle live process triggers none of §8's four stop conditions, and `04-sidecar-idle.json` shows `status` staying `idle` across the very notification §8 calls `needs_you` | **Decision pressure 6**; `orchestrator-platform.md:982–990`; data-schemas §Session sidecar file |
| M15 | §7: `engine_session_id` is "null until the engine emits it — **nothing may key off it**" | it is the convergence key **when present**, enforced by a *partial* unique index `WHERE engine_session_id IS NOT NULL`; it is never a primary key and never assumed present | §7's rule forbids *depending on its presence*; P14 needs uniqueness *when it is there*. The partial index says exactly that and nothing more | §7; E3 (reworded at r3); F14 |
| M16 | §7's `session` table has no column for `SessionSnapshot.observed_at` or for the fold's three identity sets, and T5's Allowed Scope forbids columns the spec does not list | **four nullable/defaulted columns added** — `observed_at TEXT`, and `live_subagent_ids` / `created_task_ids` / `completed_task_ids` as JSON arrays read back whole | the same shape as M13, and for the same kind of reason. `core/fold_types.py` (T1, shipped) declares all four on `SessionSnapshot`, and T6's `snapshot()` is specified to return one, so without the columns the fold's prior input is partly a fiction after every process restart. Two consequences were already visible in shipped code: RD8's per-field recency rule (T7b-5) was implemented and **inert at runtime** — through the store the registry observation always looked newer than the hook's and won every field — and subagent pairing did not survive `controld` restarting, which D37 expects it to do freely, so an in-flight subagent's stop was counted as an anomaly that was not one (T11-4). Option (b), one JSON `fold_state` column, was rejected for the reason Decision pressure 7 rejected its option (b): a schema hiding inside a value column that every reader needs bespoke code for | **BLOCKER-T6-1** (four-part entry, options and recommendation), confirmed independently by **T7b-5** and **T11-4**; D37; RD8 |

**Spot-check performed:** M12 was verified against the capture named in the correction —
`hooks/live/S09_perm_acceptEdits_write_inside/events.jsonl` exists and contains no `FileChanged`
event despite an `acceptEdits` Write, exactly as the correction states.

---

## Assumption ledger

Every load-bearing claim in this plan, classified. `proven_by_code` here means *proven by a real
capture or by a command run on this host* — the repo's equivalent of code, since there is none.

| # | Assumption | Class | Basis / what would falsify it |
|---|---|---|---|
| A1 | The 429 captures are byte-faithful hook stdin and replayable without synthesis | `proven_by_code` | parsed all 429 here: 0 malformed, `payload` is the exact stdin JSON |
| A2 | A shell dispatcher costs ~3.4 ms and delivers 40 KB frames intact | `proven_by_code` | `docs/probes/2026-09-16-hookd-latency.md`, Results 1–2 |
| A3 | A Python hook was killed at `-p` shutdown and a fork-free shell hook was not | `proven_by_code` | S07 and R04 debug-hooklines, 2/2 |
| A4 | **That interpreter start-up is *why* the Python hook was killed** | `inferred` | the probe proves cost, not mechanism. **Not critical:** the choice rests on cost *and* observed loss together; if the mechanism were something else, the shell dispatcher is still 9× cheaper |
| A5 | The registry exposes running sessions with no hooks installed | `proven_by_code` | ran `claude agents --json` here: 3 real sessions |
| A6 | `procStart` == `/proc/<pid>/stat` field 22 | `proven_by_code` | re-checked here: `531685515` both |
| A7 | A vanished sidecar does not mean "finished" | `proven_by_code` | data-schemas: the file is deleted on exit **and** absent before trust is accepted — so absence is two-valued |
| A8 | `status: "waiting"` + `waitingFor` means a human is being asked | `proven_by_code` **(upgraded at r3)** | data-schemas §"Session sidecar file", **verified live 2026-09-14**, real capture `{"status":"waiting",…,"waitingFor":"permission prompt"}` (`06-sidecar-permission.json`), written 14 ms after the `PermissionRequest` hook. Revision 2 cited the weaker `partial` section; that was a citation error, not a gap (G10 closed) |
| A9 | **`needs_you` can be cleared by the next `PreToolUse`/`PostToolUse`/`UserPromptSubmit`/`Stop`** | `inferred` | **No longer critical as of r3, and here is why.** On the **registry path** the clearing signal is *observed*, not inferred: `run-20260914T154946Z/06-sidecar-permission.json` (`status:"waiting"`, `waitingFor:"permission prompt"`, `statusUpdatedAt:1789401085541`) → `07-sidecar-running.json` (`status:"busy"`, `waitingFor` cleared to null, `statusUpdatedAt:1789401094735`) — **same pid 4041880, same sessionId `71757dd1-…`, 9.2 s apart** — the dialog resolving is visible in the sidecar. (r4, A5: revision 3 cited the prose, which records only the *entry* to `waiting`; the capture pair is the actual evidence and is stronger.) Every interactive session on any host writes a sidecar, so the inference governs only the residual where no sidecar is readable — a `-p`/SDK run (skipped at M1 by RD9) or a session whose sidecar is unreadable. On that residual the old wording still applies. Mitigation unchanged: one isolated `FoldRule` row, counted, and M2 owns the rail. Falsified by: a capture showing a cleared dialog with neither those four events nor a `waiting` exit |
| A10 | `--git-common-dir` binds a worktree session to its main repo | `proven_by_code` | data-schemas §git rev-parse §D |
| A11 | `_shepherd_managed` survives in user scope and identical commands deduplicate | `proven_by_code` | §User-scope hooks, verified in an isolated config dir |
| A12 | `MacHost`'s paths, 103-byte budget, `launchctl`, `ps` liveness and netcat flags | `inferred` | **Not critical at M1:** no M1 behaviour on this host depends on them, `verified()` is `False`, and `doctor` says so (G1). Falsified by the first run on a Mac, which is M6's checklist |
| A13 | `-p` sessions **do** appear in the registry, and `entrypoint` — not `kind` — separates them from interactive ones | `proven_by_code` **(upgraded at r3)** | `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 1: pids 4110260/4110361, sidecar present while `kill -0` confirmed the process alive, `kind:"interactive"` with `entrypoint:"sdk-cli"`. Falsified by: a `-p` run with `entrypoint:"cli"` |
| A14 | SQLite 3.45.1 supports everything §7 needs | `proven_by_code` | §Runtime toolchain; re-asserted at runtime by T5 |
| A15 | `nc` exists on the target host | `proven_by_code` **here**, `needs_user_confirmation` **for a container** | verified on this host; a minimal image may lack it, which is why the installer refuses rather than writing a dead hook (G2) |
| A16 | **A live `claude` run cannot be both isolated and authenticated on this host** | `proven_by_code` | probe Finding 3: `CLAUDE_CONFIG_DIR=<throwaway>` → `Not logged in · Please run /login`, rc=1. Consequence: T18 runs against the real config dir and isolates by working directory + `--settings`, exactly as the 2026-09-14 suite did. Falsified by: a credential path that survives a config-dir swap |
| A17 | **The 33 hook-event names and the four enums are unchanged from 2.1.270 to 2.1.273** | `proven_by_code` | `docs/probes/drift_check.py` searched the 2.1.273 binary for each enum as its **exact ordered comma-separated literal** — stronger than "the values exist". Per-event *field* shapes remain verified at 2.1.270 only (G12's residual), bounded by C8's four-always-present fields |

**Critical assumptions classified `inferred`: none as of revision 3** (A9 was the only one, and its
blast radius is now the no-sidecar residual — see its row). Everything else load-bearing is
capture-proven; the remaining `inferred` items are explicitly non-critical with the reason stated.
**Confidence arithmetic:** 90 base − 0 (no critical inferred assumption) − 25 (Recommended Defaults
non-empty: RD2–RD9) = **65**.

---

## Differences from agreement

The agreement is: the user's brief + spec §16's M1 scope. This section lists every place this plan
is not a literal transcription of it. **Four differences, all additive or decompositional, none reducing scope.**

| # | Agreement | This plan | Status |
|---|---|---|---|
| D-1 | §16 lists M1's contents; the brief adds the `HostPlatform` seam, the dispatcher decision, the fold rules, D48/D50 binding, the four tables, `toolsurface/`, fleet+SSE, the test plan and a blocker protocol | all present; **plus Task 7b**, which §16 does not name | **Addition.** Forced by the brief's own constraint (never touch the real settings ⇒ no hooks ⇒ nothing to fold). Recorded as Decision pressure 5. A reviewer who rejects it must accept an empty fleet page on the user's machine. |
| D-2 | The brief says "Ordering uses the three live `state` values (`needs_you` → `running` → `stopped` → idle)" | implemented exactly; `idle` is rendered as a **workspace-level** bucket (a workspace whose sessions are all stopped), since `idle` is not one of §7's four `state` enum values | **Clarification**, not a change. §7's enum is `starting \| running \| needs_you \| stopped`; `starting` sorts with `running`. |
| D-3 | The brief asks for "a minimal `toolsurface/`… every `web/` and `cli/` read is a registered read-only tool" | five tools, all `local_read`, **plus** `subscribe()` for the SSE stream | **Addition** (ADR-4/RD3). The stream is a read that §12 requires and the registry cannot express. |

| D-4 | §16 item 3 names "`sessiond` (UDS ingest + relay + bounded buffer) and `controld`" as one deliverable | split across **T10** (ingest + teardown) and **T10b** (the `sessiond → controld` hop: socket ownership, frame format, §7 rule 3's schema handshake, buffer, backoff, drain) | **Decomposition, not addition.** Revision 2 left the hop implicit inside a ≤150-line composition root that ADR-1 forbids from holding logic, so half of M1's process topology had no owner, no wire format and no test (F7). Nothing new is in scope; something already in scope now has a task. |

**Nothing in §16's M1 list is omitted or deferred.** The out-of-scope list contains only items
§16 assigns to other milestones.

---

# LAYER 2 — EXECUTION CONTRACT LAYER

## Context references — read before starting (paths, not summaries)

| File | Why the builder must open it |
|---|---|
| `docs/specs/orchestrator-platform.md` §3 | The 55 decisions. §5.0 is the layer map every import test is checked against; §7 is the schema; §8 is the fold; §13 is the security posture; §14 is the test lanes. |
| `docs/specs/data-schemas.md` **Index (lines 11–144)** | Jump table. **Do not read front to back** — 6 054 lines. Every task below names its sections. |
| `docs/specs/implementation-constraints.md` | All 38 lines. Every row changes how a task is built. |
| `docs/probes/2026-09-16-hookd-latency.md` | The measured basis for the shell dispatcher, including the re-run script. |
| `docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl` | The 429-event golden corpus. `_field-matrix.txt` and `_sequences.txt` beside it are the per-event presence tables. |
| `data-schemas.md` §"Live-session registry `~/.claude/sessions/<pid>.json`" and §"`claude agents --json`" | Task 7b's entire evidence base — the hookless discovery path, and the four caveats that bound it. |
| `docs/probes/2026-09-14-schemas/transcripts/copies/` | Real transcripts, read-only — Task 13's fixtures. |
| `CLAUDE.md` | tmux safety. The user has live sessions on the `shepherd` socket. |
| `/root/Shepherd/.venv/bin/{python,pytest,mypy}` | The only working toolchain (system Python has no pip — data-schemas §Runtime toolchain). |

`docs/solutions/` does not exist in this repo; nothing to check there.

## Durability horizons

| Piece | Horizon | Consequence for effort |
|---|---|---|
| `core/` types, the layer map, the two import tests | **stable** — architectural, survives every milestone | worth precision; they are the invariants |
| `HostPlatform` Protocol + contract suite | **stable** — D55 draws it at M1 precisely so it does not move at packaging | design the interface twice (Task 3 does) |
| `store/` domain verbs + migrations | **stable** — D33's three rules make the future engine swap a one-package rewrite | verbs and dataclasses, never rows or SQL strings, at every call site |
| `signals/fold.py` rule table | **near-term-refactor** — M2 adds the stop columns to the same rows | keep the rules a data table, not branches, so M2 extends rather than edits |
| `toolsurface/` | **stable shape, near-term-refactor body** — D38 says M4 fills it in behind `invoke()` | the *shape* is final at M1; the body is three lines |
| `web/static/*.js` fleet page | **near-term-refactor** — M2 replaces the 3-state chip with the 7-bucket palette | no abstraction beyond a render function per row type |
| `daemons/*` wiring | **session-only** for the supervision details; **stable** for the layer wiring | thin; 150-line cap |

## Test-seam selection

Three seams, no more (the ideal is one; three is the floor here because three processes exist):

- **Unit seam — `fold()` and the normaliser.** Pure functions: `(Signal, prior snapshot,
  received_at) → (delta, stream events, anomalies)`. The 429-event corpus attaches here. Fastest,
  most stable, and it is where the differentiator lives.
- **Integration seam — `toolsurface.invoke()`.** Everything `web/` and `cli/` do crosses it
  (D38). Route tests attach here, not to HTTP handlers, so M4's gate lands under existing tests.
- **Process seam — the UDS.** `hookd → sessiond → controld` is exercised end-to-end over a real
  socket in a throwaway runtime dir. This is the only seam where "principle 4" can actually be
  proven, so it earns its existence.

`HostPlatform` gets a **contract suite** rather than a fourth seam: one suite, three
implementations (`LinuxHost`, `MacHost`, `ScriptedHost`), per §14.2 and the fourth invariant.

## Behavior contract (critical_path requirement)

What M1 guarantees, in the form a test can hold it to. Each clause is binding on every task.

**C-1 — The observer never harms the observed.** For every possible input and every possible
daemon state, the hook dispatcher terminates with exit status 0 in under 250 ms, and delivers
either the whole payload or nothing. It never blocks a turn, never fails a tool call, never writes
to stderr in the pane. *(principle 4, K2; proven by P4, T8)*

**C-2 — One writer, one row per session.** `controld` is the only process that writes the
database. A `session_id` maps to exactly one `session` row regardless of which source saw it first
or how many events it produced. *(D37, D47; proven by P8, P14)*

**C-3 — Derived state is honest or absent.** Every column M1 writes is either derived from a real
signal with a cited capture, or left null. No column is filled by inference presented as fact. An
unmapped value is counted and visible, never guessed. *(principle 5, K1, K9; proven by the
`FoldRule.evidence` test and the anomaly counters)*

**C-4 — Absence is not a verdict.** A missing sidecar, a missing `SessionEnd`, a missing
`FileChanged`, or a missing hook event never causes M1 to assert that something *finished*,
*succeeded*, or *did not happen*. **An observed process exit is not an absence** — it is a positive
observation and §8's own fourth stop trigger; the distinction is the whole of Decision pressure 7.
*(E8, E29; proven by P16, P17)*

**C-5 — The fold is a pure function of (signal, prior state, received time).** No clock read, no
I/O, no ambient state. Replaying the same inputs yields the same outputs, forever. *(D24; proven
by P2, P3)*

**C-6 — Read-only, everywhere.** M1 writes to exactly two places: its own SQLite file under the
host's data dir, and — only on an explicit `install-hooks` command against an explicitly supplied
settings path — one settings file which is backed up first and validated after. It never writes
under `~/.claude` otherwise, never writes a systemd unit, never flips linger, never sends a
keystroke to any session. *(§16 "Read-only"; K3; proven by P13 and
`test_scan_makes_no_writes_under_claude_home`)*

**C-7 — Untrusted content stays data.** Every value originating outside Shepherd — a brief, a
title, a `waitingFor` string, a tool name, a repo path — reaches the browser as text, never as
markup, and reaches the API as an explicitly whitelisted field, never as a raw row.
*(§13; proven by `test_no_unescaped_interpolation_in_frontend`, `test_response_never_contains_a_raw_row`)*

**C-8 — No secret is ever stored or displayed.** A URL with userinfo is stripped before storage; a
`.key` sidecar is never opened. *(D50, §13; proven by P9, P15)*

**C-11 — Concurrency is declared, not hoped for.** `controld` runs three concurrent producers — a
`ThreadingHTTPServer`, the relayed-frame fold, and a 2.0 s registry scan. Every database **write**
crosses exactly one serialising writer thread; every read uses a thread-local connection under WAL;
the SSE ring is guarded by one lock; the tool registry is frozen before the server accepts its
first connection. No shared mutable structure in `controld` is touched by two threads without one
of those four mechanisms. *(ADR-7; proven by P18, P19 and
`test_store_writes_are_serialised_under_threads`)*

**C-9 — The boundaries are mechanical.** A commit that violates the consumer boundary, the storage
boundary, or the engine-vocabulary boundary does not build. *(D19, D26, D35, §5.0; proven by
P5, P6, P7)*

**C-10 — Degradation is announced.** When a capability is unavailable — no hook installed, no
`nc`, an unverified host driver, an unresolvable repo — `doctor` and the UI say which one and why.
No silent partial success. *(principle 5; proven by `test_doctor_reports_discovery_sources`,
`test_doctor_reports_unverified_host`, `test_install_refuses_without_dispatch_binary`)*

---

## Purity boundary map (critical_path requirement)

| Pure — no I/O, no clock, no env | Impure — I/O adapters, kept thin |
|---|---|
| `core/*` (types, enums, ids, ordering) | `core/ids.py::new_ulid` (reads the clock — isolated, injectable `now` param) |
| `engines/claude_code/normalise.py::parse_hook_payload` — **Table A: the only place an engine event or field name is read** | `engines/claude_code/install.py` (reads/writes settings files) |
| `signals/fold.py::fold` | `engines/claude_code/transcript.py` (reads transcript files) |
| `signals/binding.py::parse_git_output`, `normalise_remote_url` | `signals/binding.py::run_git` (subprocess, argv list, K5) |
| `engines/claude_code/registry.py::parse_sidecar`, `signals/discovery_loop.py::registry_delta` | `engines/claude_code/registry.py::scan_registry`, `agents_json_fallback` (directory read, subprocess) |
| `toolsurface/registry.py::validate_schema` | `store/sqlite.py` (the only `sqlite3` importer) |
| `signals/ordering.py::fleet_sort_key` | `host/linux.py`, `host/mac.py` (env, `/proc`, `systemctl`, `loginctl`) |
| `web/render` helpers (JSON projection, field whitelist) | `daemons/*`, `web/server.py`, `sessiond` socket code |

**The second rule (added at r3, F5):** a pure module **returns** its events; it never publishes
them. `fold()` returns `FoldResult.events`; `registry_delta()` returns the same shape;
`daemons/controld.py` — the composition root — is what calls `toolsurface.publish()`. `signals/`
(L2) therefore imports nothing at L4, and §5.0's "dependencies point down only" holds without an
exception. `StreamEvent` itself lives in `core/` (L1) so both sides can name it downward.

**The rule:** every impure module is a **thin adapter** whose job is to produce or consume a pure
type. `fold()` never touches a clock — `received_at` is a parameter. That is what makes the
429-event corpus a deterministic test rather than a timing-dependent one, and it is what lets the
`_epoch` field in the fixtures stand in for the receiver's stamp (C8).

## Provable properties (critical_path requirement)

| # | Property | How it is proven |
|---|---|---|
| P1 | `session.active_subagents >= 0` for every possible event sequence | property test over permutations of Subagent* fixtures + `test_subagent_count_never_negative` over the corpus (C10) |
| P2 | `fold` is pure and total: identical inputs → identical outputs; no input raises | `test_fold_is_deterministic` (corpus replayed twice, outputs compared) + `test_fold_never_raises` (corpus + 200 mutated/truncated payloads) |
| P3 | `fold` writes only fields in its declared rule table | `test_fold_writes_only_declared_fields` — the `FoldDelta` dataclass field set is compared to the rule table |
| P4 | `hookd` exits 0 for **every** input and **every** daemon state | `test_hookd_exits_zero_*` × 5 (principle 4, K2) |
| P5 | Nothing outside `store/` imports a DB driver | `test_storage_boundary` (AST over every module) — D26 |
| P6 | Nothing in `web/`, `cli/`, `master/` imports below L4 | `test_consumer_boundary` (AST) — D35 |
| P7 | No Claude Code hook name appears outside `engines/claude_code/` | `test_no_engine_vocabulary_in_signals` (all 33 names grepped) — §5.0 |
| P7b | **No module outside `host/` branches on platform** — no `/proc`, `systemctl`, `loginctl`, `launchctl`, `/run/user`, `sun_path`, `XDG_`, `nc -U`, `sys.platform`, `platform.system()`, `os.uname` — with `signals/`, `store/`, `web/` and `cli/` asserted by name | `test_no_platform_branching_outside_host` — **D55** |
| P8 | Registration is idempotent: N events from one unknown `session_id` → exactly one row | `test_registers_once_per_session` over the corpus (50 session ids, 429 events → 50 rows) — D47 |
| P9 | `repo.vcs_remote` never contains URL userinfo | property test over the 7 captured URL forms + generated variants — D50 |
| P10 | Every registered `ToolDef.input_schema` has a string `type` and a `properties` key, or registration fails at startup | `test_registration_rejects_mangled_schema` — D53 |
| P11 | `tasks_done <= tasks_total` | property test + corpus (S18: 2 created, 1 completed) |
| P12 | SSE `seq` is strictly increasing; a replay returns a contiguous suffix or an explicit `gap` | `test_sse_seq_monotonic`, `test_sse_replay_gap_is_explicit` |
| P13 | The real `~/.claude/settings.json` is byte-identical before and after the entire test suite | session-scoped `conftest.py` fixture hashing the file at start and end — K3, C6 |
| P14 | The two discovery sources converge: one `sessionId` ⇒ exactly one `session` row, whichever source saw it first | `test_sources_converge_on_session_id` — registry-first and hook-first orderings both produce one row (Decision pressure 5) |
| P15 | No `.key` file path is ever opened | `test_registry_never_opens_key_file` — the reader is instrumented and asserted against every path it opens (E32) |
| P16 | A session is never marked `stopped` because its sidecar vanished | `test_absent_sidecar_is_not_a_stop` (E29) |
| P17 | **A session with a stored `pid`/`proc_start` whose process is observed gone reaches `stopped` with `ended_at` set — across a `controld` restart** | `test_dead_pid_sets_stopped_with_ended_at`, `test_liveness_survives_controld_restart` (Decision pressure 7; §8's "observed process exit") |
| P18 | **No two threads write the database concurrently**: every write is executed on the single writer thread | `test_store_writes_are_serialised_under_threads` (20 threads × 50 `apply_fold_delta` calls, assert the writer thread id is constant and no `sqlite3.OperationalError` is raised) — ADR-7 |
| P19 | **The SSE ring never yields a torn or out-of-order read under concurrent publish/subscribe** | `test_stream_ring_is_thread_safe` (publisher thread + 4 subscriber threads; every subscriber sees a strictly increasing `seq` prefix) — ADR-7, C-11 |
| P20 | **The dispatch command has exactly one definition site** and every consumer reads it from `HostPlatform.hook_dispatch()` | `test_dispatch_command_has_one_definition_site` (AST over `src/shepherd/**`: the literals `nc` and `-q0` appear in exactly one **package**, `shepherd.host` — one per driver is expected; a second *authority* is not) — Decision pressure 1, consequence 3 |
| P21 | **No module imports a layer above its own** (the general §5.0 rule, not just the L5 case) | `test_layer_direction_is_downward_only` — the layer map of ADR-1 is a data table; every import is checked against it |

## Edge-case catalogue (critical_path requirement)

Every row is drawn from a capture. No row is hypothetical.

| # | Edge case | Evidence | Handled by |
|---|---|---|---|
| E1 | Only 4 fields are on every event; `permission_mode` absent from ~15 types; `effort` never with haiku; **no payload carries a timestamp** | C8; §Common input fields | T11 — receiver stamps `received_at`; every other field is `| None` |
| E2 | A session already running at install time never emits `SessionStart` again | §Hooks written into a running session; D47 | T11 — register on first event of any kind |
| E3 | `session_id` changes on `/clear` and on `--fork-session`; `--continue` reports a provisional id on `InstructionsLoaded` | §Common input fields; §SessionStart | T11 — new id ⇒ new row. **§7's "nothing may key off `engine_session_id`" means: it is never a primary key and never assumed *present*** (it is null until the engine emits it). When it **is** present it is the convergence key both sources agree on, and uniqueness is enforced by the *partial* index `ux_session_engine_id … WHERE engine_session_id IS NOT NULL` (T5). Our own `session.id` (ulid) remains the only key anything joins on. *(Reworded at r3 — revision 2 stated the prohibition and the convergence in two places without reconciling them, F14.)* |
| E4 | `SubagentStop` with `agent_type: ""` and no matching `SubagentStart` (compaction, post-turn helper); 10 stops / 0 starts across 4 TUI captures | C10; §SubagentStop; §Hook event parity | T11 — **the normaliser** reads `agent_id`/`agent_type`, drops `agent_type == ""` and emits `subagent_id`; the fold pairs on that neutral key, clamps at 0 and counts the anomaly (r4) |
| E5 | `FileChanged` never fires for agent edits — only declared watch paths | C9; §FileChanged | T11 — `repos_touched` from `PostToolUse{Edit,Write}.tool_input.file_path`, read **in the normaliser** and passed to the fold as `fields["changed_paths"]` (r4) |
| E6 | `UserPromptSubmit` fires for injected `<task-notification>` prompts, with **no `source` field to tell them apart** | C11; §UserPromptSubmit | T11 — `brief` only from the **first** prompt of a session, and only if it does not start with `<task-notification>` |
| E7 | `lastPrompt` is the *latest* prompt, 200 chars + `…`, newlines flattened; stale in a fork | §`last-prompt` entry | T11 — prefer the hook's `UserPromptSubmit.prompt`; transcript is fallback only, and marked |
| E8 | `SessionEnd` is **not guaranteed** in `-p` (missing in 4 runs) | §SessionEnd | T11 — `Stop`/`StopFailure` also set `stopped`; liveness window is the backstop |
| E9 | `Stop` has **no** `stop_reason` field | D46; §Stop | T11 — no M1 rule references it. Asserted by a test that greps the fold for the literal |
| E10 | `StopFailure.error`, not `error_type` | D46; §StopFailure | T11 — M1 stores `state=stopped` only; the error goes to M2 |
| E11 | A linked worktree is a **sibling** of the repo; `--show-toplevel` returns the worktree | D48; §git rev-parse | T7 — bind via `--path-format=absolute --git-common-dir` |
| E12 | `git remote get-url origin` exits **2** with no remote (`/root/Shepherd` is such a repo); ambiguous with several | C19; §git remote get-url | T7 — rc=2 ⇒ try `git remote`; exactly one ⇒ use it; several ⇒ null + anomaly |
| E13 | `get-url` returns embedded credentials verbatim (`https://oauth2:<token>@…`) | D50; §git remote get-url | T7 — strip userinfo **before** storage; P9 |
| E14 | A worktree's `.git` is a **regular file**, not a directory; so is a submodule's | §git worktree list | T7 — discovery must not test `isdir('.git')` |
| E15 | `git` rc=128 on dubious ownership, bare repos, and outside a repo | §git rev-parse | T7 — three distinct anomalies, counted, never an exception to the caller |
| E16 | One malformed `PreToolUse`/`PermissionRequest` entry disables **every** hook in that file; invalid JSON voids the whole file; `-p` reports neither — only `claude doctor` does | C6; §Hooks config schema | T9 — back up, write, re-read, validate, roll back on failure; report pre-existing breakage |
| E17 | Identical hook `command` strings in user + project scope **deduplicate**; a slightly different string runs twice | §User-scope hooks with `_shepherd_managed` | T9 — one canonical command string, byte-stable across installs |
| E18 | Default hook timeout is **600 s** | C7; §Hooks config schema | T9 — every installed entry sets `timeout` explicitly |
| E19 | `sun_path` ≤ 107 bytes on Linux (108 fails); macOS budget is 103 per D55 (**no capture**) | §Unix domain socket; D55 | T3/T10 — budget is a `HostPlatform` value, checked before bind and before install |
| E20 | Socket mode must be set by `umask` **before** `bind()` — there is no chmod window; a stale socket gives `ECONNREFUSED`/`EADDRINUSE` | §Unix domain socket | T10 — umask 0177, unlink before bind |
| E21 | `SO_PEERCRED` is captured at `connect()` and survives the peer's exit; `/proc` from it races the hook | §Unix domain socket | T10 — prefer `CLAUDE_PID` from the frame; `/proc` is best-effort |
| E22 | `XDG_DATA_HOME`/`XDG_CONFIG_HOME` are **never set** on this host; `XDG_RUNTIME_DIR` has no default | C3; §XDG base directories | T3 — `LinuxHost` applies XDG defaults and falls back to `/run/user/<uid>` |
| E23 | `systemctl --user` fails with "No medium found" when `XDG_RUNTIME_DIR` is unset | C3; §systemd user manager | T3 — supervision detection treats that as `foreground`, not as an error |
| E24 | `Restart=always` alone ends `failed` after 5 restarts in 10 s | C2; §systemd user manager | T3 — reported by `doctor`; the unit file itself is M6 |
| E25 | 44.4 % of transcript entries are neither `user` nor `assistant`; the last 20 lines may hold only 2 | spec correction l.1022 | T13 — subagent reads filter by `type`, never by line count |
| E26 | A `SubagentStop.agent_transcript_path` may name a file that **does not exist** (compaction agent) | §Project directory layout | T13 — missing file is a counted absence, not an error |
| E27 | Workflow subagents live under `subagents/workflows/wf_*/`, have no `toolUseId`, and their state is in `journal.jsonl` / `wf_<runId>.json` | §Workflow subagents | T13 — two readers, one merged view |
| E28 | A subagent has **no structured state field anywhere**; state comes from the `<status>` tag of a `<task-notification>` | C20; §queue-operation | T13 — parse `<status>`; unparsed ⇒ `unknown`, counted (principle 5) |
| E29 | The registry file appears **only after the trust dialog is accepted** and is **deleted on exit** | §Live-session registry | T7b — absence is "not running or not trusted", **never** a stop |
| E30 | **File mtime is not liveness.** One sidecar had an mtime 3 days old while its process was alive and `idle`; `updatedAt` advances only on a status change | verified this host, 2026-09-16 (Decision pressure 5) | T7b — liveness from `HostPlatform.process_liveness(pid, procStart)` |
| E31 | `procStart` **equals** `/proc/<pid>/stat` field 22 (24/24 in captures; re-verified `531685515` here) | §pid ↔ session_id linkage | T7b — the pid-reuse guard; a pid whose start token differs is a **different** process |
| E32 | The sibling `<pid>.<64hex>.key` holds a peer token | §Live-session registry ("Never read it") | T7b — glob `*.json` only; a test asserts no `.key` path is opened |
| E33 | `claude agents --json` forks a `claude` process per call and omits `tmux`, `procStart`, `nameSource` | §`claude agents --json` | T7b — one-shot fallback only, never a timer (G11) |
| E34 | **`nc -U` without `-q0` does not shut down its write side at stdin EOF.** A listener that reads to EOF never sees the frame end; the call blocks until `timeout 0.25` kills it — 253.6 ms vs 3.2 ms — **and still delivers**, so nothing fails loudly | `docs/probes/2026-09-16-hookd-latency.md` Result 1b | T3/T8 — the command has **one** definition site (`SocketPlan.dispatch_command`); T8 asserts the listener sees EOF in < 50 ms and mean latency < 10 ms; T2 asserts no second definition exists (P20) |
| E35 | **`-p` sessions register, and `kind` is `"interactive"` for them.** `entrypoint` is `sdk-cli` vs `cli` — **and `entrypoint` is absent from every hook payload** (C8; 0/429) | probe Finding 1; C8 | T7b — filter on `entrypoint` **in `scan_registry` only**; a test asserts `kind` is never compared against (RD9). The hook path registers `-p` runs unchanged (D47) |
| E36 | **A throwaway `CLAUDE_CONFIG_DIR` has no credentials** — `Not logged in · Please run /login`, rc=1 | ibid. Finding 3 | T18 — real config dir; isolation by working directory + `--settings`; K3 upheld by the P13 hash guard per test |
| E37 | **`tmux` in the sidecar is inherited from the launching environment, not discovered** — a `-p` process launched from a tmux pane faithfully recorded that pane although nothing about it is "in" tmux | ibid. Finding 1 | T7b — read, not stored at M1; M3 must treat it as a hint for sessions Shepherd did not spawn |

---

## Architecture Decision Records (inline, durable)

### ADR-1: Module layout, and where the three homeless modules go

**Context.** §5.0's five layers are the import law, but they do not name the daemon entrypoints,
`hookd`, `host/` (new at D55), or `testkit/` (which §14.2 says ships with the package).

**Decision.**

```
src/shepherd/
  core/            L1   types · enums · ids (ulid) · Signal/SignalKind · palette · ordering
  store/           L1   ALL SQL · migrations/ · domain verbs → dataclasses (D26, D33)
  logs/            L1   rotating JSONL (M1: daemon log only)
  host/            L2   HostPlatform Protocol · LinuxHost · MacHost                (D55)
  engines/
    claude_code/   L2   hook install/uninstall · hookd command text · normalise · transcript
  signals/         L2   ingest → fold · cwd→repo binding · fleet ordering
  runner/          L2   (absent at M1 — M3)
  providers/       L2   (absent at M1 — M5)
  orchestration/   L3   (absent at M1 — M5)
  toolsurface/     L4   ToolDef · registry · invoke() · subscribe()                (D32, D38)
  web/             L5   stdlib HTTP · SSE · static ES modules
  cli/             L5   status · doctor · install-hooks · uninstall-hooks · recompute (stub)
  master/          L5   (absent at M1 — M4)
  testkit/         --   ScriptedHost (+ the seams M3/M4/M5 add later)              (§14.2)
  daemons/         **composition root, above L5** — controld.py · sessiond.py · __main__.py
```

**Rejected alternatives.** (a) Put the daemons in `cli/` — they would have to import `store/` and
`signals/`, which is exactly the consumer-boundary violation the test exists to catch, and the test
would then have to carry an exemption, which is how boundaries die. (b) Put `host/` in `core/` —
`core/` is pure vocabulary and `host/` shells out to `systemctl` and reads `/proc`; L1 must stay
pure or `store/` and `logs/` inherit an env dependency.

**Consequences.** Enables: a genuinely fail-closed import test with **no exemptions inside L5**.
Prevents: `web/` or `cli/` ever opening a database (P5/P6). Requires: the composition root to be
thin — a 150-line-per-file cap, enforced by a test, so logic cannot hide in the wiring.

### ADR-2: `store/` receives its paths; it never asks the host for them

**Context.** `store/` is L1 and `host/` is L2. If `store/` resolved its own data directory it
would import upward, breaking the layer rule on its first line.

**Decision.** `daemons/controld.py` resolves `HostDirs` once and calls
`open_store(db_path=dirs.data_dir / "shepherd.db")`. `store/` takes a `Path` and knows nothing
about XDG, platforms, or environment variables. Same for `logs/`.

**Rejected.** A module-level singleton reading `os.environ` inside `store/` — untestable, and it
would make the storage boundary test pass while the layering had already leaked.

**Consequences.** Every `store/` test opens a `tmp_path` database with no environment setup, and
the D2 remote-path swap stays a one-package rewrite (D33's stated goal).

### ADR-3: `Audience` gains `HUMAN`

**Context.** §11.0's `ToolDef.audiences: frozenset[Audience]` is annotated `{MASTER, SESSION}`,
but the same section's own table lists **five** consumers including `web/` and `cli/`. With only
two audience values, `invoke()`'s `require_audience` would deny every UI read — the first call M1
makes.

**Decision.** `Audience = {MASTER, SESSION, HUMAN}`. `HUMAN` covers `web/` and `cli/`. Every M1
read tool carries `HUMAN`; `MASTER`/`SESSION` membership follows §11's lists verbatim so M4
inherits them unchanged.

**Rejected.** Letting `web/`/`cli/` bypass `require_audience` — that is a second path, and "there
is no second path" is the entire point of §11.

**Consequences.** Additive; D40's asymmetry (a human at a keyboard is not an agent acting on
someone's behalf) gets a name in the type system, which M4's `authorize()` will want anyway.
Listed under Recommended Defaults as **unapproved**.

### ADR-4: the event stream is the second member of L4's interface

**Context.** §12 specifies one SSE endpoint. D35 says L5 reaches the system only through L4. A
stream is not a tool call, and the registry has no shape for it.

**Decision (corrected at revision 3, F5).** `toolsurface/stream.py` exposes
`subscribe(since_seq: int | None) -> Iterator[StreamEvent]` and `publish(event) -> int` beside
`invoke()`. `web/` consumes only through `subscribe()`. **`signals/` does not publish.** It
*returns* its events — `fold()` already returns `FoldResult.events`, and `registry_delta()` returns
the same shape — and the **composition root (`daemons/controld.py`) calls `publish()`**.

Revision 2's wording ("`signals/` publishes into it") described an **upward import**: `signals/` is
L2 and `toolsurface/` is L4, and §5.0 says "dependencies point **down only**"
(`orchestrator-platform.md:225–227`). It was the one layering violation in the plan, and it was the
one no test covered — T2's consumer-boundary test only inspects `web/ cli/ master/`. Revision 3
therefore also adds the **general** rule as a test (P21,
`test_layer_direction_is_downward_only`), so the next such slip fails the build instead of a review.

`StreamEvent` lives in **`core/`** (L1, defined at T1) so that `signals/` returning it and
`toolsurface/` ringing it are both downward imports.

**Rejected.** (a) A bus in `core/` — `core/` is types, and `web/` subscribing to a bus that
`signals/` publishes to is a private read path wearing an L1 hat. (b) `web/` importing `signals/`
— a direct consumer-boundary violation. (c) `signals/` importing `toolsurface/` to publish — the
revision-2 wording; rejected above.

**Consequences.** M4 can gate or audit the stream in one place without touching `web/` (D38's
acceptance test). The ring buffer's size is one constant in `toolsurface/`, and its lock is one
lock (ADR-7). The cost is that the composition root grows one line per event source — which is
what a composition root is for, and it stays inside the 150-line cap.

### ADR-5: `HostPlatform`'s interface, designed twice

**First design (rejected — shallow).** One method per fact: `data_dir()`, `config_dir()`,
`runtime_dir()`, `socket_dir()`, `sun_path_max()`, `is_supervised()`, `supervisor_name()`,
`pid_alive()`, `pid_start_token()`, `linger_enabled()`, `hook_command()`, … Eleven methods that
mirror the implementation. Every caller learns eleven things; every new fact adds a method; the
interface is as complex as the body. Shallow by the deletion test — inlining it would move the
complexity nowhere, because there is barely any.

**Second design (chosen — deep).** **Six methods, each returning a frozen record that answers a
whole question**, so a caller learns one call and gets everything that question implies:

```python
class HostPlatform(Protocol):
    def dirs(self) -> HostDirs: ...                       # data · config · runtime, XDG defaults applied
    def control_socket(self, name: str) -> SocketPlan: ...# path · dir_mode · sock_mode · socket_path_budget
    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan: ...  # command · requires · available · reason
    def supervision(self) -> Supervision: ...             # kind · detail · manageable · start_limit_note
    def process_liveness(self, pid: int, start_token: str | None) -> Liveness: ...
    def login_persistence(self) -> LoginPersistence: ...  # enabled · mechanism · detail
```

**The sixth member is the revision-3 correction** (Decision pressure 2, re-decided). Revision 2 hung
the dispatch command on `SocketPlan` to keep the member count at five. Two reasons that was wrong:
D55's "exactly five" is an anti-growth clause about *count*, and satisfying it by widening a member
hides the growth from every diff; and `SocketPlan` was already carrying six facts, so the seventh
was accounting, not cohesion. The command also has a different **lifetime and consumer** from the
path — the path is used at bind time by one process, the command is written into a settings file
and executed by a foreign process thousands of times — which is the ordinary sign of two questions,
not one.

**Why the second design still wins.** `control_socket()` hides: XDG resolution, the
`/run/user/<uid>` fallback (C3), the directory mode, the umask-before-bind requirement (E20) and
the byte budget (E19). `hook_dispatch()` hides the platform's netcat flag set — including `-q0`,
worth 250 ms per invocation on Linux and **absent on macOS's netcat** (G2, E34). The deletion test:
inline either and those facts reappear at three call sites (sessiond bind, hook command generation,
installer preflight) — both are deep.

**Consequences.** The contract suite has six cases, one per method, plus `verified()`.
`ScriptedHost` is trivially constructible from six frozen records, which is what makes the rest of
the system testable without a Linux host (§14.2 reason 1). **D55's spec row was amended from five to
six on 2026-09-16** by the decision's author (`orchestrator-platform.md:165`), so the Protocol and
the decision log agree (r4, A3).

### ADR-6: the fold is a data table, not a branch tree

**Context.** M2 adds the stop columns, M5 adds `work_item_id`, and the fold rules are the
most-tuned code in the system (D37). A `match` statement over 33 event names will be edited by
every future milestone.

**Decision.** `signals/rules.py` holds a frozen tuple of `FoldRule(kind, delta_fn, emits, evidence)`
where `kind` is a **`SignalKind`** and `evidence` is the literal `data-schemas.md` section name.
`fold()` selects the rule by `signal.kind` — **a dict lookup, not a predicate walk**. Adding M2's
rules appends rows.

**The revision-4 correction that makes this possible (BLOCKING 2).** Revision 3's table could not
have been keyed on `SignalKind`, because four kinds were **overloaded by rows with different column
effects**: `TOOL_FINISHED` spanned `PostToolUse` (appends `repos_touched`), `PostToolUseFailure`
(liveness only) and `PostToolBatch` (refusal counter); `NEEDS_INPUT` spanned `PermissionRequest`,
`Notification{…}` and `Elicitation`; `TURN_PROGRESS` spanned `MessageDisplay` and
`Notification{other}` (which must also be counted); `SESSION_STOPPED` spanned `Stop`/`SessionEnd`
and `StopFailure` (which also feeds an anomaly counter). The only discriminator left was
`Signal.raw_kind` — which would have put the literals `"PostToolUseFailure"`, `"PostToolBatch"`,
`"StopFailure"` **inside `signals/`** and failed T2's `test_no_engine_vocabulary_in_signals` on this
plan's own prescribed code. That is precisely the F4 failure mode, answered as before with an
exemption, "which is how boundaries die".

**Two mechanical rules close it, and both are testable:**

1. **One `SignalKind` per distinct column effect.** The enum gains `TOOL_FAILED`,
   `TOOL_BATCH_FINISHED`, `STOP_FAILED` and `NOTICE_UNMAPPED` (T1). `FoldRule.kind: SignalKind`
   then types the table, the `applies` predicate disappears, and `signals/` never needs to know an
   engine event name existed. A rule is selected by a value `core/` defines.
2. **Engine field names are read in `engines/claude_code/normalise.py` and nowhere else.** The
   normaliser projects every payload field it needs into `Signal.fields` under a **closed set of
   neutral keys** (`SIGNAL_FIELD_KEYS`, T1): `tool_input.file_path` → `changed_paths`, `to_model` →
   `model`, `agent_id` → `subagent_id`, `new_cwd` → `next_cwd`, `notification_type` + the ask text
   → `ask`, and so on. **The neutral key is never the engine's spelling** — that is what makes the
   closed set an actual boundary rather than a rename (r5). This
   also removes the three different `needs_you_reason` constructions that forced `NEEDS_INPUT` to
   overload: **the reason string is built in the adapter**, and the fold rule copies `fields["ask"]`.
   §5.0's test — "if swapping the engine would edit `signals/`, the boundary has leaked" — had no
   mechanical form for *field* names in revision 3; T2's `test_signals_reads_only_neutral_field_keys`
   is that form.

**Consequences.** P3 (writes only declared fields) becomes checkable by reading the table; the
evidence citation for every rule is *in the code*, so a reviewer can trace any column back to a
capture without leaving the file.

**`evidence` is enforced by a test, not by the type system (r4, A6).** Revision 3 claimed "a rule
with no `evidence` string does not typecheck" — that is false: `evidence: str` accepts `""`.
**`test_every_fold_rule_cites_an_existing_section`** (T11) asserts every rule's `evidence` is
non-empty **and that the section name it gives is actually present in `docs/specs/data-schemas.md`**,
which is stronger than non-emptiness and is the **only mechanical enforcement of K1** — the user's
first hard rule. Acceptance clause 10 names this test; revision 3 named it without giving it an
owning task.

**One interaction with T2, recorded because it nearly killed a boundary (F4).** Every `evidence`
value names a `data-schemas.md` section — `"§Notification"`, `"§SubagentStop"` — and those strings
contain Claude Code event names, inside `signals/`, which is exactly what
`test_no_engine_vocabulary_in_signals` forbids. A text scan would fire on the plan's own prescribed
code and the first thing a builder would do is add an exemption, which ADR-1 calls "how boundaries
die". The scan is therefore **AST-based** and excludes string literals in **one declared position**:
the value of a field named `evidence` in a `FoldRule` construction. The exclusion is structural and
named once (`EVIDENCE_FIELD_NAME`), and T2 ships a negative fixture proving that the same event
name **anywhere else** in `signals/` still fails the build.

### ADR-7: `controld`'s threading model — one writer thread, thread-local readers, one ring lock

**Context (F8).** `controld` has three concurrent producers against shared state: a
`ThreadingHTTPServer` (one thread per request, all reading the store through `invoke()`), the fold
of frames relayed from `sessiond`, and the 2.0 s registry scan (T7b). Revision 2 opened one `Store`
(ADR-2) and said nothing about threads — not whether `Store` is thread-safe, not how `sqlite3`'s
`check_same_thread` is satisfied, not what serialises `apply_fold_delta`. The concurrency coverage
it did have (G3, `test_fold_concurrent_interleave`) tests the **pure fold**, which by construction
cannot touch any of this, and C-2's "one writer" is about **processes**, not threads.

**Decision.** Four mechanisms, each mechanical:

1. **One writer thread.** `Store` owns a `queue.Queue` and a single thread holding the one
   read-write `sqlite3.Connection`. Every write verb (`register_session`, `apply_fold_delta`,
   `upsert_*`, `set_app_state`, `bump_anomaly`) enqueues a unit of work and blocks on its result.
   The connection is created **on that thread**, so `check_same_thread` stays at its default and
   the failure mode it guards against cannot occur.
2. **Thread-local readers under WAL.** WAL is already enabled (T5). Every read verb uses a
   `threading.local()` read-only connection opened lazily per thread, so HTTP request threads never
   queue behind the writer.
3. **One lock on the ring.** `toolsurface/stream.py`'s ring and its `seq` counter are guarded by a
   single `threading.Lock` held across append-and-increment and across a subscriber's snapshot.
4. **A registry frozen before serving.** `toolsurface.register()` raises after
   `freeze_registry()` is called, and the composition root calls it before the server binds. The
   module-global registry is therefore written by exactly one thread, at startup, and read-only
   thereafter.

**Rejected.** (a) A connection shared across threads with `check_same_thread=False` and a coarse
lock — it serialises reads behind writes for no benefit, and the flag silently disables the one
guard the driver offers. (b) `sqlite3`'s own locking with retries and a busy timeout — it converts
a design question into a flake, and §7's "one writer" would then be true only statistically.

**Consequences.** Enables: P18, P19 and C-11 as real tests rather than hopes; a `Store` whose
thread-safety is a property of its construction, not of its callers' discipline. Prevents: any verb
handing out a cursor or a connection (already forbidden by D33's "verbs return dataclasses").
Requires: `open_store()` to start a thread, so it gains a `close()` that joins it — which is also
what F15's teardown needs (T10b, T18).

---

## Task list

**Notation.** Each task names its `data-schemas.md` sections. `[LINUX]` = verified on this host;
`[UNVERIFIED-MAC]` = no capture exists (G1). Validation levels per `cc10x:verification`.

---

### Task 1: Repo skeleton, toolchain gates, the engine drift check, and `core/`

**Objective:** a package that typechecks strictly and an empty test suite that runs, plus the
engine-neutral vocabulary every later task imports — and, **first**, proof that the engine on this
host still emits the shapes the fold is about to be written against.

**Step 0 — the drift check, before any other work (G12, F11).** `data-schemas.md:3` pins all 127
shapes to `2.1.270`; this host runs `2.1.273`. Run `docs/probes/drift_check.py` (in-repo, ~30
lines, no live session needed) against the running binary. It re-verifies the **33 hook-event
names** and the four enums (`SessionEnd.reason`, `SessionStart.source`, `StopFailure.error`,
`Notification.type`) as **exact ordered literals**. A name or enum that moved is a **blocker entry**
naming T11 and T9, not something to discover in the fold. Record the result (version, date,
outcome) in the plan's progress notes. This is the milestone-owned step the version drift needs,
and it is the same step every future engine upgrade runs.

**Files/Surfaces:**
- `pyproject.toml` (mypy strict, pytest config, package discovery)
- `src/shepherd/__init__.py`, and `__init__.py` for `core/ store/ logs/ host/ engines/claude_code/ signals/ toolsurface/ web/ cli/ testkit/ daemons/`
- `src/shepherd/core/ids.py` — `new_ulid(now: float | None = None) -> str`
- `src/shepherd/core/signals.py` — `SignalKind`, `Signal`, `SubagentRef`, `TaskRef`, `MalformedPayload`
- `src/shepherd/core/states.py` — `SessionState`, `Ownership`, `Origin`, `FLEET_STATE_ORDER`
- `src/shepherd/core/anomalies.py` — `AnomalyKind`, `Anomaly`
- `src/shepherd/core/fold_types.py` — **`FoldDelta`, `SessionSnapshot`** (the fold's input and
  output shapes; defined at L1 so T6, T7b, T11 and T12 all import them downward — F9)
- `src/shepherd/core/stream.py` — **`StreamEvent`** (L1, so `signals/` can return it and
  `toolsurface/` can ring it without either importing the other — ADR-4, F5)
- `src/shepherd/core/frames.py` — **`Frame`** (L1: the ingest listener produces it and the relay
  consumes it, so a shared L1 type is what keeps T10 and T10b independent rather than circular)
- `tests/test_core_ids.py`, `tests/test_core_states.py`, `tests/test_core_types.py`

**Dependencies:** none.
**Allowed Scope:** types, enums, ids, ordering, and the drift check. Pure.
**Out-of-Scope Drift:** any I/O; any Claude Code vocabulary (that belongs to `engines/`); the
7-bucket palette (M2 — M1 has three live states).
**Expected Artifacts:** a recorded drift-check result; `mypy --strict src/` exits 0; `pytest`
collects and passes.
**Required Checks:** `.venv/bin/python docs/probes/drift_check.py` (step 0 — 33 names present, four
enums byte-identical); `.venv/bin/mypy --strict src/`; `.venv/bin/pytest tests/ -q`;
`test_ulid_is_monotonic_and_sortable`; `test_fleet_state_order_matches_spec` (asserts
`needs_you → running → stopped`, §16); `test_core_types_are_frozen_and_pure` (every dataclass in
`core/` is `frozen=True`; no module in `core/` imports outside stdlib).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/test_core_*.py && .venv/bin/mypy --strict src/`.
**Exit Criteria:** drift check green and recorded; mypy strict clean; all three tests pass; no
module imports anything outside stdlib.
**Test Seams:** unit.

**Consumes:** none.
**Produces:**
```python
def new_ulid(now: float | None = None) -> str: ...
class SessionState(StrEnum): STARTING="starting"; RUNNING="running"; NEEDS_YOU="needs_you"; STOPPED="stopped"
FLEET_STATE_ORDER: tuple[SessionState, ...]
class SignalKind(StrEnum):                  # one member per DISTINCT column effect (r4, BLOCKING 2)
    SESSION_REGISTERED; PROMPT_SUBMITTED; TURN_PROGRESS
    TOOL_STARTED; TOOL_FINISHED; TOOL_FAILED; TOOL_BATCH_FINISHED
    NEEDS_INPUT; INPUT_RESOLVED; NOTICE_UNMAPPED
    SUBAGENT_STARTED; SUBAGENT_FINISHED; TASK_CREATED; TASK_COMPLETED
    SESSION_STOPPED; STOP_FAILED; CWD_CHANGED; FILES_CHANGED; MODEL_CHANGED; UNKNOWN
SIGNAL_FIELD_KEYS: frozenset[str]           # the CLOSED set of neutral keys Signal.fields may carry:
    # {"ask", "changed_paths", "model", "subagent_id", "task_id", "prompt", "next_cwd",
    #  "start_source", "tool_label", "failure_note"}
    # r5: "new_cwd" -> "next_cwd". `new_cwd` is literally Claude Code's CwdChanged field
    # (data-schemas.md:954), so a neutral key spelled that way would satisfy the closed set while
    # leaving engine vocabulary in signals/ — defeating the test it was added to enforce.
@dataclass(frozen=True) class Signal:
    kind: SignalKind; engine_session_id: str; cwd: str; transcript_path: str
    received_at: str; fields: Mapping[str, object]; raw_kind: str
    # raw_kind carries the engine's own event name for anomaly detail and `doctor` ONLY.
    # `signals/` may pass it through; it may never compare it against a literal (T2).
@dataclass(frozen=True) class Anomaly: kind: AnomalyKind; detail: str; engine_session_id: str | None
@dataclass(frozen=True) class MalformedPayload: raw_len: int; reason: str; received_at: str
@dataclass(frozen=True) class FoldDelta:                 # every field optional; None = untouched
    last_event_at: str | None; state: SessionState | None; needs_you_reason: str | None
    brief: str | None; cwd: str | None; repo_id: str | None; model: str | None
    tasks_total: int | None; tasks_done: int | None; active_subagents: int | None
    repos_touched: tuple[str, ...] | None; ended_at: str | None
    pid: int | None; proc_start: str | None              # Decision pressure 7
    observed_at: str | None                             # recency key for RD8's per-field rule
@dataclass(frozen=True) class SessionSnapshot:           # the fold's prior-state input, read-only
    session_id: str; engine_session_id: str | None; state: SessionState
    last_event_at: str | None; observed_at: str | None; needs_you_reason: str | None
    brief: str | None; cwd: str | None; repo_id: str | None; model: str | None
    tasks_total: int; tasks_done: int; active_subagents: int
    repos_touched: tuple[str, ...]; live_subagent_ids: frozenset[str]
    created_task_ids: frozenset[str]; completed_task_ids: frozenset[str]
    title: str | None; title_source: Literal["user", "engine", "brief"]
    pid: int | None; proc_start: str | None; ended_at: str | None
@dataclass(frozen=True) class StreamEvent:
    kind: str; session_id: str | None; payload: Mapping[str, object]; occurred_at: str
@dataclass(frozen=True) class Frame: payload: bytes; received_at: str; peer_pid: int | None
```

**Note on `FoldDelta`'s definition site.** It is defined **here**, at L1, and only *re-exported* by
`signals/fold.py`. That is what lets T6 (`apply_fold_delta`) and T7b (`registry_delta`) take the
type without depending on T11. Revision 2 recorded this resolution in its self-review but never
applied it to T1's Produces block; revision 3 applies it (F9). The same applies to
`SessionSnapshot`, `StreamEvent` and `MalformedPayload`, each of which was used in a signature
without ever being defined.

---

### Task 2: The boundary tests — written before the code they police

**Objective:** make §5.0's two enforced boundaries, plus three M1-specific ones, fail the build
from the first commit.

**Files/Surfaces:**
- `tests/boundaries/test_consumer_boundary.py`
- `tests/boundaries/test_storage_boundary.py`
- `tests/boundaries/test_engine_vocabulary.py`
- `tests/boundaries/test_composition_root.py`
- `tests/boundaries/test_hookd_isolation.py`
- `tests/boundaries/test_platform_branching.py`
- `tests/boundaries/test_layer_direction.py`
- `tests/boundaries/test_dispatch_command_site.py`
- `tests/boundaries/_imports.py` (shared AST walker: module → imported module names, string
  literals **with their syntactic position**, attribute and name identifiers)

**Dependencies:** T1.
**Allowed Scope:** static analysis via `ast`, over `src/shepherd/**` only (tests are not product
code and are not scanned). No runtime imports of the modules under test (a module that fails to
import must still be analysable).
**Out-of-Scope Drift:** a general-purpose lint framework; runtime import hooks; anything that
needs a package to be importable; **raw-text scanning** (see below).

**Every scan is AST-based, not textual — this is a revision-3 correction (F4), and it is load-bearing.**
Revision 2 specified two scans as text matches, and both fired on the plan's own prescribed code:

| Revision-2 rule | What it would have hit | Revision-3 form |
|---|---|---|
| forbid the literal `sun_path` outside `host/` | T3's field **`sun_path_budget`**, consumed in `engines/`, the installer and `cli/doctor` | the field is renamed **`socket_path_budget`** (no collision at all), and the scan inspects `ast.Constant` **string values** and `ast.Attribute`/`ast.Name` **identifiers** separately, so an attribute access can never match a path literal |
| forbid all 33 hook event names outside `engines/claude_code/` | ADR-6's required `evidence` strings in `signals/rules.py` — `"§Notification"`, `"§SubagentStop"`, … | the scan excludes string literals in **one declared syntactic position**: the value of a field named `evidence` in a `FoldRule` construction (`EVIDENCE_FIELD_NAME`), and ships a **negative fixture** proving the same name anywhere else in `signals/` still fails |

The point of the correction: as specified in revision 2, the first thing a builder would have done
is add an exemption — and ADR-1 itself says that is "how boundaries die". A structural exclusion
declared once, with a fixture proving its narrowness, is not an exemption.

**Two properties every string-literal scan in this task must have (r6), stated once here rather
than repeated per rule.** Both were proven to produce false positives on plausible, non-violating
code — and a boundary test that cries wolf gets an exemption added to it, which is the same death
ADR-1 describes, reached from the other side:

1. **Docstrings are not code.** A module, class or function docstring — the first statement of the
   body, per `ast` — is **excluded from every string-literal scan**. Proven false positives:
   `"""Stop the selected session."""` in `cli/`, and
   `"""...Shows a Notification when Setup completes..."""`. `Stop`, `Setup`,
   `Notification`, `FileChanged` and `MessageDisplay` are **ordinary English words** in a fleet page
   (T16) or a `cli status` line (T17), and they are five of the 33 names. Comments are already
   invisible to `ast` and need no rule.
2. **Path and token literals match at word boundaries, not as substrings.** `/proc` must not match
   inside `/procedure`. Applies to `PLATFORM_PATH_LITERALS` and to the engine event names.

**These two exemptions are narrow and structural, and each ships with a negative fixture** — that
is the same standard the `evidence`-position exclusion is held to above. Neither weakens a rule: a
docstring cannot branch on a platform, and `/procedure` is not a path.

**Expected Artifacts:** thirteen tests that pass on the T1 skeleton and demonstrably fail when a
violating import is introduced (each test ships with a `# self-check:` fixture module under
`tests/boundaries/fixtures/` proving it catches the violation), **plus the negative fixtures**
enumerated under Exit Criteria.

**Every rule below is stated as a property, and its fixture set must include the known evasions
(r6).** Three r5 rules were written as *syntactic forms* and a one-line idiom defeated each; the
builder implemented them faithfully, which is how a plan defect reaches production wearing a green
test. **A rule's positive fixtures must therefore include every evasion listed in its bullet** —
alias, `.get()`, unpacking, containment, method call, `from x import y` — not merely the obvious
form. A rule whose only positive fixture is the form its author had in mind is untested against the
form its defeater will use.
**Required Checks:**
- `test_consumer_boundary` — no module under `web/ cli/ master/` imports `store signals engines runner providers orchestration` or `sqlite3` (D19, D35).
- **`test_layer_direction_is_downward_only`** — **§5.0's general rule** (`orchestrator-platform.md:225–227`),
  not just the L5 case: the ADR-1 layer map is a data table (`LAYER_OF: Mapping[str, int]`), and no
  module may import a package whose layer is **above** its own. `daemons/` is the composition root
  and may import anything; nothing may import it. This is the test whose absence let revision 2's
  ADR-4 specify `signals/` (L2) publishing into `toolsurface/` (L4) with no test to catch it (F5, P21).
- `test_storage_boundary` — no module outside `store/` imports `sqlite3` or any DB driver (D26).
- `test_no_engine_vocabulary_in_signals` — none of the **33** hook event names appears as a string
  literal outside `engines/claude_code/`, **except** in the declared `evidence` position (§5.0),
  **and excluding docstrings, matching at word boundaries** (r6 — `Stop`, `Setup`, `Notification`,
  `FileChanged` and `MessageDisplay` are ordinary English in `web/` and `cli/` prose).
  The 33 names are parsed from `docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt`
  — the `claude doctor` capture that actually lists them — **not** from
  `hooks/binary/hook-events.json`, which is empty on disk (G13).
- `test_hook_event_names_match_the_doctor_capture` — **owned by T2, in
  `tests/boundaries/test_engine_vocabulary.py`** (it is a boundary test, and T2 is the package that
  may read the probe tree). T9 *satisfies* it and does not count it among its own checks (r5).
  T2's parsed `CLAUDE_CODE_HOOK_EVENT_NAMES` equals **both** the capture's "Valid events:" list
  **and** T9's literal
  `engines/claude_code/events.py::ALL_HOOK_EVENT_NAMES`, in order, 33 of them. The test is the only
  link between them; neither imports the other, so no product module reads the probe tree at
  runtime (G13, F11, **r4 A7**).
- `test_nothing_imports_daemons` — no module imports from `shepherd.daemons` (ADR-1); and every file in `daemons/` is ≤150 lines.
- `test_hookd_imports_nothing_from_shepherd` — **(rule disambiguated at r6; it was being read two
  ways and the strict reading blocks this plan's own prescribed code).**
  **The rule, as a property:** *the **generated command string** must invoke no Python and reference
  no module of ours* — it is a `sh` one-liner whose whole value is that no interpreter of ours is on
  the hook path (Decision pressure 1). The assertion is made **against the command string that
  `build_hook_entry` returns**: it contains no `python`, no `-m `, no `.py`, and no `shepherd`.
  **It is explicitly NOT a rule about the generating module's imports.** Read that way it fires on
  T8's own `Produces` signature — `build_hook_entry(plan: SocketPlan, dispatch: HookDispatchPlan)`
  names two types that live in `shepherd.host` — and its marker list matches the module's own
  **docstring**. *(Tell that this already bit: the shipped clean fixture opens with a `#` comment
  where a docstring belongs. A rule whose workaround is "do not write a docstring" is the wrong
  rule.)* `hookd_command.py` may import from `shepherd` freely; what it **emits** may not mention us.
- **`test_dispatch_command_has_one_definition_site`** — the dispatch command is built in exactly
  one **package**, `shepherd.host`: across `src/shepherd/**`, the literals `nc` and `-q0` appear
  only under `host/`, and every other module reaches the command through
  `HostPlatform.hook_dispatch()`. **A package, not a file** (r4, A4): `host/linux.py` and
  `host/mac.py` must each carry their own command, and `MacHost`'s differing literal ships as a
  **clean negative fixture** proving the rule does not forbid a second *driver*, only a second
  *authority*. **This is the structural fix for the near-miss that revision 2's second copy
  created** (Decision pressure 1 consequence 3; E34; P20).
- **`test_no_platform_branching_outside_host`** — **D55's "nothing else may branch on platform",
  made mechanical (rule widened at r6 after the identifier half was proven defeatable).**
  **The rule, as a property:** *outside `host/`, no module may reference a platform-probing symbol
  **whatever it is spelled locally**, and no module may contain a platform path literal.*
  - **Identifiers — resolve the alias to its origin before matching.** `PLATFORM_IDENTIFIERS` names
    the **origin** symbols `sys.platform`, `platform.system`, `os.uname`; the scan must bind
    `import x as y` / `from x import y as z` back to the origin exactly as `module_imports` already
    does, then match. Revision 5 matched three fixed dotted spellings, which all four of these
    defeat:
    ```python
    import sys as s;           s.platform == "darwin"    # chain is "s.platform"
    from sys import platform;  platform == "darwin"      # a bare Name
    import platform as pf;     pf.system()               # "pf.system"
    from os import uname;      uname()                   # a bare Name
    ```
    **This was an oversight, not a design choice, and the asymmetry proves it:** every import-based
    rule in this task is already alias-proof through `module_imports`. D55's claim is "nothing else
    may branch on platform"; the rule has to mean it. The `from x import y` forms are the important
    half — they leave no dotted chain at all.
  - **Path literals — word-bounded, docstrings exempt** (r6). `/proc`, `systemctl`, `loginctl`,
    `launchctl`, `/run/user`, `XDG_`, `nc -U` match only at token boundaries: **`/procedure` is not
    `/proc`**. See the string-literal rules below for the docstring exemption.
  The two sets remain separate constants matched against separate AST node classes, so a *field
  name* can never trip a *path literal* rule. **`signals/`, `store/`, `web/` and `cli/` are asserted
  explicitly and by name**, as the brief requires, and the rule is enforced package-wide so no
  future package can quietly become the exception.
- `test_kind_is_never_branched_on` — no module compares `RegistryEntry.kind` against a literal
  (`entrypoint` is the discriminator — E35, F3).
- **`test_signals_reads_only_neutral_field_keys`** — **§5.0's field-level boundary, made mechanical
  (r4, BLOCKING 2; rule widened at r6 after it was proven defeatable).**
  **The rule, as a property:** *inside `signals/`, every key by which the `Signal.fields` mapping is
  read must be a string literal in `SIGNAL_FIELD_KEYS` (T1).* It is **not** a rule about subscript
  syntax. Revision 5 said "every string-literal **subscript**", and all four of these passed it
  while reading engine fields:
  ```python
  a = signal.fields.get("tool_input")       # not a Subscript
  f = signal.fields; c = f["to_model"]      # subscript target is a Name, not an Attribute
  d = {**signal.fields}                     # unpacking
  if "file_path" in signal.fields: ...      # containment
  ```
  That is not an edge case: `Signal.fields` is `Mapping[str, object]` and **every neutral key is
  per-payload optional**, so `[...]` raises `KeyError` and **`.get(...)` is exactly the idiom T11's
  rule table will be written in**. The rule as written would have stayed green while `signals/` read
  `tool_input`, `agent_id` and `to_model` — the three fields this task names as the motivating
  violation.
  **The implementation must therefore:** (a) treat `.fields` as **tainted** and follow it through
  **local aliases** (`f = signal.fields` taints `f`, including via tuple assignment and `for`
  targets); (b) cover **every** read form — subscript, `.get`, `.pop`, `.setdefault`, `in`/`not in`,
  `**` unpacking, `.keys()`/`.items()`/`.values()`, and iteration; (c) **fail closed**: a read whose
  key is not a string literal (a variable, an f-string, a concatenation) **fails the test**, because
  a computed key cannot be checked — if a dynamic key is ever genuinely needed it arrives as a named
  plan change, not as a silent hole; (d) fail on any *whole-mapping* escape (`**` unpacking,
  `.keys()`, iteration, or passing `.fields` to a call), since those leak every key at once.
  Ships with negative fixtures (`fields["ask"]`, `fields.get("ask")` are clean) and positive ones
  (`fields["tool_input"]`, `fields.get("to_model")`, the alias form, and `{**signal.fields}` each
  fail).
- **`test_signals_never_compares_raw_kind`** — **(rule widened at r6 after it was proven
  defeatable).**
  **The rule, as a property:** *inside `signals/`, `Signal.raw_kind` may only be **passed through**
  — stored in an `Anomaly`, formatted into a `doctor` line, returned. It may never influence control
  flow, by any means.* Revision 5 said "a comparison or a `match` subject", which both of these
  defeat:
  ```python
  rk = signal.raw_kind
  if rk == "Stop": ...                          # Compare operand is a Name, not the Attribute
  return signal.raw_kind.startswith("Pre")      # not a Compare at all
  ```
  **The implementation must therefore:** taint `.raw_kind` through local aliases as in the `fields`
  rule, and fail on (a) any `Compare` with a tainted operand, (b) any `match` whose subject is
  tainted, (c) **any method call on a tainted value** (`.startswith`, `.endswith`, `.lower`, `.split`
  — a string method on an engine event name is branching by another route), and (d) membership tests
  (`raw_kind in (...)`). Pass-through into an f-string, a dataclass field or a `return` stays clean,
  and ships as the negative fixture. This is the escape hatch BLOCKING 2 would otherwise have forced
  open, and r5 left it ajar.
- **`test_no_source_file_exceeds_600_lines`** — every file under `src/shepherd/` is ≤ 600 lines
  (principle 6, K4), and every file in `daemons/` is ≤ 150 (ADR-1). **Acceptance clause 9 named
  this test in revision 3 without giving it an owning task** (r4, A6).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/boundaries/ -q`.
**Exit Criteria:** all thirteen pass on clean code; each fails when **every** evasion named in its
bullet is placed on the analysis path (r6 — not just the canonical form); **and the negative
fixtures pass**: a `FoldRule(evidence="§Notification")` in `signals/`; an attribute named
`socket_path_budget` in `engines/`; `MacHost`'s own `nc` literal in `host/mac.py` (A4);
`fields["ask"]` **and** `fields.get("ask")` in `signals/` (BLOCKING 2); a `raw_kind` pass-through
into an `Anomaly` and into an f-string; a `cli/` docstring reading `"""Stop the selected
session."""`; the path `/procedure` in `signals/`; and **a `hookd_command.py` that imports
`SocketPlan` from `shepherd.host` and carries a normal module docstring** (r6 — the rule is about
the emitted string, not this module's imports).
**Test Seams:** unit (static analysis).

**Consumes:** `shepherd` package layout, `SIGNAL_FIELD_KEYS`, `SignalKind` (T1).
**Produces:**
```python
def module_imports(path: Path) -> frozenset[str]: ...
def string_literals(path: Path, exclude_field: str | None = None,
                    include_docstrings: bool = False) -> frozenset[str]: ...
                                     # r6: docstrings excluded by default (prose, not code)
def identifiers(path: Path) -> frozenset[str]: ...
def resolved_identifiers(path: Path) -> frozenset[str]: ...
                                     # r6: aliases bound back to their ORIGIN module, the way
                                     # module_imports already does. `import sys as s` + `s.platform`
                                     # -> "sys.platform"; `from sys import platform` + a bare
                                     # `platform` -> "sys.platform" too.
def mapping_read_keys(path: Path, attr: str) -> frozenset[str | None]: ...
                                     # r6: every key by which `<expr>.<attr>` is read - subscript,
                                     # .get/.pop/.setdefault, `in`, `**`, .keys/.items/.values,
                                     # iteration - FOLLOWING LOCAL ALIASES of the mapping.
                                     # None marks a non-literal (computed) key: always a failure.
def tainted_attribute_uses(path: Path, attr: str) -> frozenset[str]: ...
                                     # r6: how `<expr>.<attr>` is used once bound to a local -
                                     # "compare" | "match" | "method:<name>" | "contains" | "passthrough".
FORBIDDEN_BELOW_L4: frozenset[str]   # {"shepherd.store","shepherd.signals","shepherd.engines","shepherd.runner","shepherd.providers","shepherd.orchestration"}
LAYER_OF: Mapping[str, int]          # ADR-1's map: core/store/logs=1, host/engines/signals/runner/providers=2,
                                     # orchestration=3, toolsurface=4, web/cli/master=5, daemons=6 (composition root)
CLAUDE_CODE_HOOK_EVENT_NAMES: tuple[str, ...]   # all 33, parsed from the `claude doctor` capture (G13).
                                     # Test-package only: product code never imports this (r4, A7).
EVIDENCE_FIELD_NAME: str             # "evidence" — the one declared exclusion position (ADR-6)
PLATFORM_PATH_LITERALS: tuple[str, ...]   # "/proc", "systemctl", "loginctl", "launchctl", "/run/user", "XDG_", "nc -U"
PLATFORM_IDENTIFIERS: tuple[str, ...]     # ORIGIN symbols: "sys.platform", "platform.system", "os.uname".
                                     # r6: matched AFTER alias resolution, never as literal spellings.
HOST_ONLY_PACKAGE: str               # "shepherd.host" — the only package either set may appear in
```

---

### Task 3: `HostPlatform` Protocol + `LinuxHost` [LINUX]

**Objective:** the seventh seam (D55), with the verified driver behind it, so no other module ever
branches on platform.

**Files/Surfaces:**
- `src/shepherd/host/base.py` — Protocol + the six frozen records (ADR-5)
- `src/shepherd/host/linux.py` — `LinuxHost`
- `src/shepherd/host/detect.py` — `detect_host() -> HostPlatform`
- `tests/contracts/test_hostplatform_contract.py` — **the one suite every implementation passes**

**Dependencies:** T1.
**Allowed Scope:** exactly the **six** members of ADR-5 (five, plus `hook_dispatch()` — Decision
pressure 2, re-decided at r3). Directory resolution; socket plan (path, modes, budget); the hook
dispatch command; supervision detection; process liveness; login persistence.
**Out-of-Scope Drift:** writing unit files, flipping linger, installing anything, spawning
processes other than the read-only `systemctl --user is-system-running` / `loginctl show-user`
probes. Packaging is M6.
**Evidence used:**
- dirs: §XDG base directories (`XDG_DATA_HOME`/`XDG_CONFIG_HOME` **never set** → apply defaults; `XDG_RUNTIME_DIR=/run/user/0`, no default exists) — C3, E22, G7
- socket: §Unix domain socket at mode 0600 + `SO_PEERCRED` (107-byte budget; 108 fails; umask before bind; unlink before bind) — E19, E20
- supervision: §systemd user manager (`No medium found` without `XDG_RUNTIME_DIR`; `StartLimitBurst=5`/`10s`) — C2, C3, E23, E24
- liveness: §`/proc/<pid>/stat` (field 22 start-ticks) and §pid↔session_id linkage (`procStart` == field 22 in 24/24) — C13
- login persistence: §`loginctl show-user` (Linger) — read-only
- **dispatch command:** `docs/probes/2026-09-16-hookd-latency.md` Results 1, 1b and 2. `nc` is
  present as OpenBSD netcat 1.226. **`-q0` is mandatory and measured**: without it the same command
  costs 253.6 ms instead of 3.2 ms and *still delivers*, so nothing fails loudly (E34).

**This module is the one and only definition site of the dispatch command** (Decision pressure 1,
consequence 3; P20). No other module, and no other section of this plan, writes the command as a
literal. Every consumer — T8's builder, T9's installer, T17's `doctor` — reads
`SocketPlan.dispatch_command`. `MacHost`'s command differs **precisely in the `-q0` flag**, which is
the whole argument for the sixth seam member (G2, Decision pressure 2).

**Expected Artifacts:** `LinuxHost` passing the contract suite on this host; `detect_host()`
returning it; supervision correctly reporting `foreground` when `XDG_RUNTIME_DIR` is stripped.
**Required Checks:**
`test_dirs_apply_xdg_defaults`, `test_runtime_dir_falls_back_to_run_user_uid` (derived from
`os.getuid()`, not hard-coded — G7), `test_socket_path_budget_enforced` (107 ok / 108 refused),
`test_socket_plan_dispatch_command_names_its_requirements`,
**`test_linux_dispatch_command_carries_q0`** (the literal `-q0` is present; E34 — this is the
assertion that makes the 250 ms regression impossible to reintroduce),
**`test_dispatch_command_is_the_only_platform_difference_asserted_here`** (the contract case is
that each driver *has* a command naming its requirements, not that they are equal),
`test_supervision_is_foreground_without_runtime_dir`, `test_process_liveness_matches_proc_stat_field_22`,
`test_process_liveness_rejects_mismatched_start_token` (E31 — pid reuse),
`test_login_persistence_is_read_only` (asserts no mutating argv is ever constructed).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/contracts/test_hostplatform_contract.py -q`.
**Exit Criteria:** contract suite green against `LinuxHost`; `mypy --strict` clean; every
subprocess call is an argv list (K5).
**Test Seams:** contract suite (the seam's own interface).

**Consumes:** `Anomaly`, `AnomalyKind` (T1).
**Produces:**
```python
@dataclass(frozen=True) class HostDirs: data_dir: Path; config_dir: Path; runtime_dir: Path
@dataclass(frozen=True) class SocketPlan:
    path: Path; dir_mode: int; sock_mode: int; socket_path_budget: int
@dataclass(frozen=True) class HookDispatchPlan:      # the sixth member (Decision pressure 2)
    command: str                                     # THE single definition site; Linux: carries -q0 (E34)
    requires: tuple[str, ...]; available: bool; reason: str
@dataclass(frozen=True) class Supervision:
    kind: Literal["systemd_user", "launchd", "foreground"]; detail: str; manageable: bool; start_limit_note: str
@dataclass(frozen=True) class Liveness: alive: bool; start_token: str | None; observed_at: str
@dataclass(frozen=True) class LoginPersistence: enabled: bool | None; mechanism: str; detail: str
class HostPlatform(Protocol):
    def dirs(self) -> HostDirs: ...
    def control_socket(self, name: str) -> SocketPlan: ...
    def hook_dispatch(self, plan: SocketPlan) -> HookDispatchPlan: ...   # member 6 (DP2)
    def supervision(self) -> Supervision: ...
    def process_liveness(self, pid: int, start_token: str | None) -> Liveness: ...
    def login_persistence(self) -> LoginPersistence: ...
    def verified(self) -> bool: ...
class LinuxHost: ...          # verified() -> True
def detect_host() -> HostPlatform: ...
```

**Two renames from revision 2, both deliberate:** `sun_path_budget` → **`socket_path_budget`**
(the old name collided with T2's platform-token scan on the plan's own prescribed code — F4), and
the dispatch fields move off `SocketPlan` onto **`HookDispatchPlan`**, returned by the new sixth
member. Both propagate to T4, T8, T9, T10 and T17, whose `Consumes` blocks name the new spellings.

---

### Task 4: `MacHost` (written, unverified) + `ScriptedHost`

**Objective:** D55's second driver and the seam's `Scripted*` double (§14.2), so the rest of M1 is
testable without a host and so the interface has two callers from day one (D9's argument).

**Files/Surfaces:**
- `src/shepherd/host/mac.py` — `MacHost`, `verified() -> False`
- `src/shepherd/testkit/scripted_host.py` — `ScriptedHost`
- `tests/contracts/test_hostplatform_contract.py` (extended: parametrised over all three)

**Dependencies:** T3.
**Allowed Scope:** the same **six** members. Every `MacHost` constant carries
`# UNVERIFIED (no capture) — D55` and cites D55's line for its value: `~/Library/Application Support`,
`~/Library/Preferences`, a runtime dir under `TMPDIR`, **`socket_path_budget` 103**, `launchctl`
supervision, `ps`-based liveness, `RunAtLoad` persistence, and a `hook_dispatch()` command whose
flags are **not** assumed to match Linux's. **`-q0` is the exact character they differ on**
(G2, E34): it is mandatory on OpenBSD netcat and is not present on macOS's, which is why the
command is a seam member rather than a constant. `MacHost.hook_dispatch()` therefore returns
`available=False` with the reason *"macOS netcat flag set unverified — no capture"* until a Mac
run confirms it, so the installer refuses rather than writing a hook that costs 250 ms or nothing
at all.
**Out-of-Scope Drift:** trying to make `MacHost` "probably right" by guessing. An unverified value
that says so is honest; an unverified value that looks verified is the failure D41 exists to stop.
**Expected Artifacts:** three implementations, one suite. Real-host assertions skip on
`MacHost` (`pytest.mark.skipif(sys.platform != "darwin")`); the pure logic (budget arithmetic,
path composition, record shapes) runs everywhere.
**Required Checks:** `test_contract_suite[LinuxHost|MacHost|ScriptedHost]` (six cases +
`verified()`); `test_machost_reports_unverified`;
`test_machost_dispatch_is_unavailable_with_a_reason` (G2, E34 — an unverified flag set must refuse,
not guess); `test_machost_constants_are_annotated` (a static check that every literal in `mac.py`
sits on a line carrying `UNVERIFIED`); `test_scripted_host_is_not_a_base_class`
(nothing inherits from it — §14.2 naming rules).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic on Linux; the macOS half is **Manual, deferred to M6** —
checklist: run the contract suite on a Mac, compare `sun_path` budget, confirm the netcat flag
set, confirm `launchctl print` output shape. Recorded, not run now.
**Exit Criteria:** suite green for `LinuxHost` and `ScriptedHost`; `MacHost` green on its
platform-independent cases and explicitly skipped elsewhere; `verified()` False.
**Test Seams:** contract suite.

**Consumes:** `HostPlatform`, `HostDirs`, `SocketPlan`, `HookDispatchPlan`, `Supervision`,
`Liveness`, `LoginPersistence` (T3).
**Produces:** `class MacHost: ...`, `class ScriptedHost: ...` (constructed from six frozen records).

---

### Task 5: `store/` migration runner + migration 001

**Objective:** the four tables, the bookkeeping table, and the three migration rules from §7.

**Files/Surfaces:**
- `src/shepherd/store/migrate.py`
- `src/shepherd/store/migrations/001_m1_foundation.sql`
- `tests/store/test_migrations.py`

**Dependencies:** T1, T2.
**Allowed Scope:** `workspace`, `repo`, `session`, `app_state`, `schema_migration`. Indexes
`ux_repo_path`, `ix_session_fleet` and **`ux_session_engine_id`**. WAL. `CHECK` constraints on
every enum column (§7: "Enums are TEXT with a CHECK constraint — never ints"). **Creating the data
directory** before opening the database.

**Three additions at revision 3:**

1. **`pid INTEGER NULL` and `proc_start TEXT NULL` on `session`** (Decision pressure 7, M13). Written
   only by the registry path; read only by the liveness sweep. Without them the sidecar's deletion
   destroys both inputs to `process_liveness` and the hookless path can never set `ended_at`. The
   migration comment cites C13, which names their absence as the limitation this closes.
2. **`CREATE UNIQUE INDEX ux_session_engine_id ON session(engine_session_id) WHERE engine_session_id IS NOT NULL;`**
   (F14, M15). P8/P14 — "one `session` row per `session_id`" — was enforced only by an application
   check-then-insert, i.e. by discipline under a race with three writers. One line makes it true by
   construction. The `WHERE` clause is what keeps §7's "null until the engine emits it" legal.
3. **First-run: the data directory may not exist** (F16). `migrate(db_path)` creates
   `db_path.parent` with mode 0700 before connecting. The greenfield first five minutes was the one
   path in revision 2 with no test.
**Out-of-Scope Drift:** `work_item`, `queue`, `ix_session_item`, `ux_item_external`,
`ix_item_candidate` — **M5**. `session.work_item_id` and `work_item_ref` **columns** exist (§7
lists them) but carry **no foreign key**, because their target table does not exist yet; this is
noted in the migration's own comment.
**Evidence used:** §7 tables verbatim; §7 Migrations (three rules); §Runtime toolchain (SQLite
3.45.1 — WAL, CHECK, JSON1, STRICT, RETURNING all work; **no `sqlite3` CLI**, so every check is
through the Python module).
**Expected Artifacts:** a fresh database at version 1; a `FULL OUTER JOIN` capability probe
recorded in `app_state` (closes §18's last row: 3.45.1 ≥ 3.39, asserted on the *running*
interpreter rather than assumed).
**Required Checks:**
`test_migrate_creates_four_tables_and_bookkeeping`, `test_checksum_mismatch_refuses_to_start`
(rule 1), `test_newer_db_version_refuses_to_start` (rule 2), `test_migrations_run_in_one_transaction`,
`test_wal_is_enabled`, `test_enum_check_constraints_reject_bad_values`,
`test_full_outer_join_is_available` (§18),
**`test_migrate_creates_missing_data_dir`** (first run, mode 0700 — F16),
**`test_session_has_pid_and_proc_start_columns`** (Decision pressure 7),
**`test_duplicate_engine_session_id_is_rejected_by_the_index`** (P14 by construction — F14),
**`test_two_null_engine_session_ids_are_allowed`** (the partial index must not break §7's "null
until the engine emits it").
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/store/test_migrations.py -q`.
**Exit Criteria:** all eleven pass; `test_storage_boundary` still green.
**Test Seams:** integration (real SQLite, `tmp_path`).

**Consumes:** none from other tasks (takes a `Path`, per ADR-2).
**Produces:**
```python
EXPECTED_SCHEMA_VERSION: int  # 1
def migrate(db_path: Path) -> int: ...          # returns the applied version; raises MigrationRefused
class MigrationRefused(Exception): ...
def read_schema_version(db_path: Path) -> int: ...
```

---

### Task 6: `store/` domain verbs and dataclasses (D33)

**Objective:** the only place SQL lives, exposing verbs that return dataclasses with transactions
kept inside.

**Files/Surfaces:**
- `src/shepherd/store/models.py` — `Workspace`, `Repo`, `Session`, `SubagentRollup`, `FleetRow`
- `src/shepherd/store/db.py` — `open_store(db_path) -> Store`, the verb surface
- `tests/store/test_verbs.py`

**Dependencies:** T5.
**Allowed Scope:** the verbs listed under Produces, and nothing else. Every verb returns a frozen
dataclass or a list of them. `sessiond` gets **no writer verbs** (D37: `controld` is the only
writer) — enforced by there being no second entry point.

**The threading model is part of the verb surface, not an implementation detail (ADR-7, F8).**
`controld` calls these verbs from three concurrent producers: HTTP request threads, the fold of
relayed frames, and the 2.0 s registry scan. So `Store` owns it:

- **Writes** are enqueued onto a single writer thread that holds the one read-write connection,
  created on that thread (`check_same_thread` stays at its default). Callers block on the result,
  so the verb surface is unchanged and synchronous.
- **Reads** use a `threading.local()` read-only connection under WAL, so an HTTP thread never
  queues behind a fold.
- `open_store()` starts that thread; `Store.close()` drains the queue, joins it and closes every
  connection (F15's teardown needs this too).

Revision 2 opened one `Store` and said nothing about any of this; the fold-level concurrency test
(G3) exercises a **pure function** and by construction cannot reach it.
**Out-of-Scope Drift:** a `Store` Protocol (D26/D33: the named trigger has not fired); any verb
taking SQL; any verb exposing a transaction; a `claim_*` verb (M5).
**Evidence used:** §7 column lists for all four tables; §7.0's three rules; D33.
**Expected Artifacts:** a verb surface a caller can use without knowing SQLite exists.
**Required Checks:**
`test_no_verb_accepts_sql`, `test_no_verb_returns_a_driver_row` (return annotations are checked by
a test, not just by mypy), `test_register_session_is_idempotent` (P8),
`test_apply_fold_delta_is_atomic`, `test_fleet_query_orders_by_state` (§16 ordering),
`test_repo_root_path_is_unique`, `test_app_state_roundtrips_json`,
**`test_register_session_fills_not_null_columns`** (F16 — §7's `owner_id='local'`, `ephemeral=0`,
`depth=0`, `attempt=1`, `engine='claude_code'`, plus `origin` and `ownership`, are supplied by the
verb; an M1 caller never has to know they exist),
**`test_store_writes_are_serialised_under_threads`** (P18 — 20 threads × 50 `apply_fold_delta`,
one writer thread id, no `OperationalError`),
**`test_reads_use_a_thread_local_connection`** (ADR-7),
**`test_close_drains_and_joins_the_writer`** (F15),
**`test_liveness_sweep_returns_sessions_with_a_pid`** (Decision pressure 7's read side).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/store/ -q`.
**Exit Criteria:** all twelve pass; `mypy --strict` clean; `test_storage_boundary` green.
**Test Seams:** integration (real SQLite), plus a threaded case for P18.

**Consumes:** `migrate`, `EXPECTED_SCHEMA_VERSION` (T5); `SessionState`, `FoldDelta`,
`SessionSnapshot` (T1).
**Produces:**
```python
def open_store(db_path: Path) -> Store: ...   # creates the data dir; starts the writer thread
class Store:
    def close(self) -> None: ...                       # drain · join · close every connection (F15)
    def snapshot(self, session_id: str) -> SessionSnapshot | None: ...   # the fold's prior input
    def sessions_with_liveness_inputs(self) -> list[tuple[str, int, str]]: ...  # (session_id, pid, proc_start) — DP7
    def upsert_workspace(self, name: str, root_path: str | None) -> Workspace: ...
    def upsert_repo(self, workspace_id: str, root_path: str, name: str,
                    vcs_remote: str | None, git_common_dir: str) -> Repo: ...
    def find_repo_by_common_dir(self, git_common_dir: str) -> Repo | None: ...
    def register_session(self, engine_session_id: str, workspace_id: str, repo_id: str | None,
                         cwd: str, started_at: str, origin: str, ownership: str) -> Session: ...
    def get_session_by_engine_id(self, engine_session_id: str) -> Session | None: ...
    def apply_fold_delta(self, session_id: str, delta: FoldDelta) -> Session: ...
    def fleet(self) -> list[FleetRow]: ...
    def list_sessions(self, workspace_id: str | None = None,
                      state: SessionState | None = None) -> list[Session]: ...
    def get_session(self, session_id: str) -> Session | None: ...
    def list_workspaces(self) -> list[Workspace]: ...
    def get_app_state(self, key: str) -> object | None: ...
    def set_app_state(self, key: str, value: object) -> None: ...
    def bump_anomaly(self, kind: str) -> None: ...
```

---

### Task 7: Workspace/repo discovery and cwd → repo binding (D48, D50)

**Objective:** turn a session's `cwd` into a `repo_id` and a `workspace_id` correctly — including
from inside a linked worktree, which is where prefix matching fails.

**Files/Surfaces:**
- `src/shepherd/signals/binding.py` — `run_git` (impure) + `parse_git_output`, `normalise_remote_url` (pure)
- `src/shepherd/signals/discovery.py` — `discover_repos(root: Path)`
- `tests/signals/test_binding.py`, `tests/signals/test_remote_normalisation.py`, `tests/signals/test_discovery.py`

**Dependencies:** T6.
**Allowed Scope:** git interrogation and URL normalisation. Repo identity key is
**`git rev-parse --path-format=absolute --git-common-dir`** (D48); `root_path` is the **first
`worktree` record** of `git worktree list --porcelain` (main tree first).
**Out-of-Scope Drift:** longest-prefix matching (D48 replaces it); creating worktrees (M5);
`safe.directory` mutation (never — dubious ownership is reported, not fixed).
**Evidence used:** §`git rev-parse` outputs for cwd → repo binding (§D worktree case; symlink →
physical path; rc=128 cases); §`git worktree list --porcelain` (main tree first; `.git` is a
**regular file** in a worktree — E14); §`git remote get-url` forms (all 7 spellings, the
`oauth2:<token>@` case, `insteadOf` expansion, rc=2).
**Expected Artifacts:** a binder that returns `(repo_id | None, anomaly | None)` and never raises.
**Required Checks:**
`test_bind_plain_repo`, `test_bind_subdirectory`, `test_bind_worktree_to_main_repo` (E11 — the case
prefix matching cannot do), `test_bind_submodule_resolves_to_submodule`,
`test_bind_symlinked_path_matches_physical`, `test_bind_non_repo_yields_null_repo_id`,
`test_bind_bare_repo_is_counted`, `test_bind_dubious_ownership_is_counted` (E15),
`test_vcs_remote_strips_userinfo` (P9, E13), `test_vcs_remote_normalises_all_seven_forms`,
`test_vcs_remote_null_when_no_remote` (rc=2, E12), `test_vcs_remote_null_when_ambiguous` (C19),
`test_discovery_finds_worktree_with_dotgit_file` (E14).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — throwaway repos under `tmp_path`, created by the test
(`git init`, `git worktree add`, `git remote add` with the seven captured URL forms). No network.
**Exit Criteria:** all thirteen pass; every git call is an argv list (K5); no test touches
`/root/Shepherd`'s own git state.
**Test Seams:** unit for `parse_git_output`/`normalise_remote_url`; integration for `run_git`.

**Consumes:** `Store.upsert_repo`, `Store.find_repo_by_common_dir` (T6); `Anomaly` (T1).
**Produces:**
```python
@dataclass(frozen=True) class RepoBinding:
    repo_id: str | None; workspace_id: str; git_common_dir: str | None; anomaly: Anomaly | None
@dataclass(frozen=True) class DiscoveredRepo:            # defined here at r3 — it was used, never defined (F9)
    root_path: Path; git_common_dir: str; name: str; vcs_remote: str | None; is_worktree: bool
def bind_cwd_to_repo(store: Store, cwd: str) -> RepoBinding: ...
def normalise_remote_url(raw: str) -> str | None: ...     # strips userinfo; None when ambiguous
def discover_repos(root: Path) -> list[DiscoveredRepo]: ...
```

---

### Task 7b: Hookless session discovery from the live-session registry (Decision pressure 5)

**Objective:** make the fleet page non-empty on a machine with **no hooks installed** — which is
the user's machine (K3) — by discovering, binding and state-tracking `attached` sessions from
Claude Code's own registry.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/registry.py` — `scan_registry`, `read_sidecar`, `agents_json_fallback`
- `src/shepherd/signals/discovery_loop.py` — the scan → `FoldDelta` pass
- `tests/engines/test_registry_source.py`, `tests/signals/test_discovery_loop.py`

**Dependencies:** T1 (`FoldDelta`, `SessionSnapshot`, `Anomaly` — all defined in `core/` at T1, see
T1's Produces), T3 (`process_liveness`), T6 (store verbs), T7 (cwd → repo binding). **Not T11** —
T7b needs the *types*, not the hook path's `fold()`. Revision 2 recorded this resolution in its
self-review but left T1's Produces block without the types; revision 3 applies it (F9), so the
dependency argument now rests on something that exists.
**Allowed Scope:** globbing `<config_dir>/sessions/*.json`, parsing the documented fields,
**filtering on `entrypoint`**, checking liveness, mapping `status` → `state`, mapping
`name`/`nameSource` → `title`/`title_source`, **storing `pid`/`proc_start`**, running the
**liveness sweep** that ends sessions whose process is gone, and emitting the **same `FoldDelta`**
the hook path emits so there is one writer and one rule set (D37).
**Out-of-Scope Drift:**
- **Never** open a `<pid>.<64hex>.key` file (E32, P15).
- **Never** infer a stop from a missing sidecar (E29, P16). *(An **observed process exit** is not a
  missing sidecar — it is §8's own fourth stop trigger. Decision pressure 7.)*
- **Never** branch on `kind` to decide whether a session is headless — it is `"interactive"` for
  `-p` too. **`entrypoint` is the discriminator** (E35, probe Finding 1, RD9).
- **Never** use file mtime as liveness (E30).
- **Never** poll `claude agents --json` on a timer — it forks a `claude` process per call (E33, G11).
- No `messagingSocketPath` use (addressing a live session is M3/M4, and the schema records it as
  observed-but-not-probed).
- No writes anywhere under `~/.claude`.

**Evidence used:** data-schemas §**"Session sidecar file `~/.claude/sessions/<pid>.json`"** — the
*verified-live 2026-09-14* section, which is the one that carries the real `waiting`/`waitingFor`
capture and the `status` stayed-`idle`-across-`idle_prompt` note (revision 2 cited a weaker section
and downgraded A8 on the strength of it — F13); §`claude agents --json` (a projection of the same
files, lacking `tmux`/`procStart`/`nameSource`); §PermissionRequest "Variants and edge cases" (the
sidecar flips to `waiting` **14 ms after** the hook — the captured entry *and* exit signal for
`needs_you`); §pid ↔ session_id linkage (`procStart` **==** `/proc/<pid>/stat` field 22); D47;
D29 (`title_source` ratchet `user > engine > brief`); the live re-verification recorded in
Decision pressure 5 (three real sessions, zero hooks, 2026-09-16); and
**`docs/probes/2026-09-16-registry-and-version-drift.md` Finding 1** — `-p` sessions register,
`kind` is `"interactive"` for them, `entrypoint` (`sdk-cli` vs `cli`) is the discriminator, and
`tmux` is inherited from the launching environment rather than discovered (E35, E37). Revision 2
never cited that probe although it is an artefact of record from the same day.

**The mapping table — one row per field, each citing its evidence:**

| Registry field | → | Note | Evidence |
|---|---|---|---|
| `sessionId` | `session.engine_session_id` | **the convergence key when present** — never a primary key, never assumed present (§7); uniqueness enforced by `ux_session_engine_id … WHERE NOT NULL` (T5, P14) | §Session sidecar file; §7; E3 |
| **`entrypoint`** | **filter, on this path only**: `"cli"` → register · `"sdk-cli"` → **skip and count** | **the discriminator.** `kind` is `"interactive"` for `-p` too, so branching on it would flicker every `-p` run through the fleet page. **This predicate is registry-only and cannot be otherwise: `entrypoint` is not a hook-payload field** (C8; 0 occurrences across all 429 captured payloads). **The hook path registers on the first event of any kind regardless of entrypoint, per D47** — which is what T12's 50-row replay and T18's live `-p` test rest on. The skip is **counted and reported by `doctor`**, never silent (principle 5). See RD9 | probe Finding 1; E35; **C8** |
| `kind` | **read, never branched on** | a test asserts no comparison against it exists (T2) | probe Finding 1 |
| `cwd` | `session.cwd` → `repo_id` via T7 | D48 applies unchanged | §Session sidecar file; D48 |
| `pid` + `procStart` | **stored** as `session.pid` / `session.proc_start`, **and** used as the liveness input and pid-reuse guard | **Decision pressure 7.** Storing them is what lets the sweep end a session *after* the sidecar is deleted; a differing start token is a **different** process | E31; C13; M13 |
| `status: "busy"` | `state = running` | verified live | §Session sidecar file |
| `status: "idle"`, `statusUpdatedAt` **< 60 s** old | `state = running` | §8's `running` rule — the status change *is* a signal, and it is inside `LIVENESS_WINDOW_S` | **Decision pressure 6**; §8 |
| `status: "idle"`, `statusUpdatedAt` **≥ 60 s** old | `state = needs_you`, reason `"idle — waiting for your next instruction"` | **Decision pressure 6.** Revision 2 wrote `stopped` here, which asserts a stop §8 does not license and mis-renders the common case on the user's machine. §8 puts an idle interactive session in `needs_you` at 60 s (`idle_prompt`, measured 60.03 s); reaching the same verdict from the registry makes the two sources **agree** instead of contradicting each other | **DP6**; §8; C21; `04-sidecar-idle.json` |
| `status: "waiting"` + `waitingFor` | `state = needs_you`, `needs_you_reason = waitingFor` | **verified live** (G10 closed, A8 `proven_by_code`): `{"status":"waiting",…,"waitingFor":"permission prompt"}`. Still counted on every occurrence | §Session sidecar file (verified live 2026-09-14) |
| `status` leaves `"waiting"` → `idle`\|`busy` | **clears `needs_you`** | **a captured resolution signal** — the thing G5 says the hook path lacks. A9's inference is not used on this path | **the capture pair `06-sidecar-permission.json` → `07-sidecar-running.json`** (same pid/sessionId, 9.2 s apart, `waitingFor` cleared); entry side in §PermissionRequest |
| `status` **not** in `{idle, busy, waiting}` | **keep the prior `state`**; count the anomaly; surface in `doctor` | **r4, A9.** The three values are *observed*, not a closed set — and per-event shapes are verified at 2.1.270 while the host runs 2.1.273 (G12). `RegistryEntry.status` being a `Literal` is a **typecheck, not a runtime guard**. Treated exactly as the hook path treats an unrecognised `hook_event_name`: liveness only, counted, visible (principle 5) | §Session sidecar file (values listed as observed); principle 5 |
| **pid not alive**, or alive with a **different** `procStart` | `state = stopped`, `ended_at = liveness.observed_at` | **§8's fourth stop trigger, verbatim: "observed process exit".** This is the registry path's *only* stop, and it is why `pid`/`proc_start` must be columns | §8; E31; **DP7** |
| `name` + `nameSource: "user"` | `title`, `title_source = user` | D29's ratchet, top rank | D29; §Session sidecar file |
| `name` + `nameSource: "derived"` | `title`, `title_source = engine` | D29's middle rank — and available with no hooks and no transcript read (probe Finding 1) | D29 |
| `startedAt` (epoch ms) | `session.started_at` | ISO-8601 UTC in the column (§7) | §Session sidecar file |
| `statusUpdatedAt` (epoch ms) | `FoldDelta.observed_at` | **the recency key** RD8 now turns on | §Session sidecar file; RD8 |
| `version` | recorded in the anomaly/doctor view only | not a `session` column at M1; `doctor` shows it beside the drift-check date (G12) | — |
| `tmux`, `bridgeSessionId`, `pidDomain`, `messagingSocketPath`, `peerProtocol`, `peerFeatures` | **read, not stored at M1** | `tmux` matters at M3 — and is **inherited from the launching environment, not discovered** (E37), so M3 must treat it as a hint for sessions Shepherd did not spawn. `pidDomain` matters at D55's container shape. Storing them needs columns §7 does not have | §Session sidecar file; probe Finding 1 |
| sidecar **absent**, no stored pid | *(nothing)* | absence is "not running or not trusted"; **never a stop** | E29, P16 |

**Precedence when both sources speak — by recency, not by source (RD8, overturned at revision 3).**
For each field, the observation with the **newer timestamp** wins: `FoldDelta.observed_at`, which is
`statusUpdatedAt` on the registry path and `received_at` on the hook path. Source is the **tie-break
only** (equal timestamps → the hook path, which is precise).

Revision 2's rule — "hook fields win per field, always" — has no recency term, and that is a bug
with two faces (F12):

1. **It freezes stale hook state.** Once any hook event sets `state`, the registry could never
   correct it — including after the hook path goes silent, which E8 says is routine (`SessionEnd`
   is not guaranteed; `StopFailure` is lost at `-p` shutdown). The live registry would then watch
   the process go idle or vanish and be forbidden from saying so.
2. **It discards a captured signal.** The `waiting → idle` transition above is a *real observed
   resolution* for `needs_you`; source-precedence suppresses it in favour of an older hook-derived
   value, and A9's inference has to cover the gap it created.

One rule, one comparison, two tests (`test_newer_source_wins_per_field`,
`test_stale_hook_state_is_corrected_by_the_registry`).

**Expected Artifacts:** a scanner, a loop that turns a scan into `FoldDelta`s, a **liveness sweep**
that ends sessions whose process is gone, **`run_discovery_loop` — the module that owns the 2.0 s
cadence, the sweep and the shutdown join** (r4, A8: revision 3 left the timer, its shutdown event
and its join with no owning module and no test, while ADR-1 caps `daemons/*` at 150 lines and
forbids logic there) — and a `doctor` line reporting which source is live.
**Required Checks:**
`test_registry_registers_unknown_session` (Decision pressure 5's whole point),
`test_register_stores_pid_and_proc_start` (**DP7** — the columns are written on registration),
`test_dead_pid_sets_stopped_with_ended_at` (**DP7**, P17 — §8's "observed process exit"),
`test_liveness_survives_controld_restart` (P17 — the sweep still works after a restart, because the
inputs are on the row rather than in memory),
`test_sdk_cli_entrypoint_is_skipped_and_counted` (**F3/E35** — `entrypoint`, not `kind`),
`test_kind_is_never_branched_on` (T2's AST rule, re-asserted here),
`test_registry_never_opens_key_file` (P15, E32),
`test_liveness_ignores_file_mtime` (E30 — a sidecar with an ancient mtime and a live pid is `running` by liveness, not by the file),
`test_procstart_mismatch_is_a_different_process` (E31),
`test_registry_status_maps_to_state` (**all six rows of the DP6 table**: busy, idle<60 s, idle≥60 s, waiting, unknown, dead pid),
`test_unknown_registry_status_is_counted` (**r4, A9** — an unrecognised `status` keeps the prior state, counts an anomaly, and never raises; the `Literal` annotation is a typecheck, not a runtime guard),
`test_discovery_loop_stops_on_shutdown_event` (**r4, A8** — the 2 s timer and the sweep live in `run_discovery_loop`, which exits promptly when the event is set and is joined by the composition root),
`test_idle_live_session_is_never_stopped` (**DP6/F2** — the regression revision 2 would have shipped),
`test_registry_waiting_sets_needs_you_with_waitingfor` (A8 proven; still counted),
`test_leaving_waiting_clears_needs_you` (the captured resolution signal — shrinks A9),
`test_registry_name_sets_title_source` (D29 ratchet: `user` beats `derived`, and a later `derived` never overwrites a `user`),
`test_absent_sidecar_is_not_a_stop` (P16, E29),
`test_malformed_sidecar_is_counted`,
`test_sources_converge_on_session_id` (P14 — registry-first **and** hook-first orderings each yield one row),
`test_newer_source_wins_per_field` (**RD8 as re-decided** — recency),
`test_stale_hook_state_is_corrected_by_the_registry` (**F12** — the case source-precedence could never reach),
`test_agents_json_is_one_shot_not_a_timer` (E33, G11 — **mechanism, not adjective**: an AST scan of
`src/shepherd/**` asserts (a) `agents_json_fallback` has **exactly one** call site, (b) that call
site is lexically inside `scan_registry`'s missing-directory branch, and (c) `REGISTRY_SCAN_INTERVAL_S`
is referenced by exactly one module, `signals/discovery_loop.py`. Revision 2 said "a test asserts no
scheduled call site exists" and named no mechanism),
`test_agents_json_timeout_is_bounded`,
`test_scan_makes_no_writes_under_claude_home` (instrumented open()).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — sidecar fixtures under `tmp_path` built from the documented
field list, plus **one read-only assertion against this host's real
`~/.claude/sessions/*.json`** (`test_real_registry_parses`, marked `@pytest.mark.live`, read-only,
asserting only that every file parses and every field is of the documented type — it never asserts
session counts, which change).
**Exit Criteria:** twenty-four pass; no `.key` path opened; no write under `~/.claude`; **no
`sdk-cli` entry registered by this scan** (the hook path is unaffected — C8, RD9); no idle live
session rendered `stopped`; an unrecognised `status` counted rather than mapped; the `doctor` line reports
`hooks: <state> · registry: <n> sessions (<m> sdk-cli skipped)`.
**Test Seams:** unit (pure mapping: `registry_delta`, `liveness_verdict`) + integration (real
directory scan).

**Consumes:** `HostDirs`, `process_liveness`, `Liveness` (T3); `Store.register_session`,
`Store.get_session_by_engine_id`, `Store.apply_fold_delta`, `Store.snapshot`,
`Store.sessions_with_liveness_inputs` (T6); `bind_cwd_to_repo` (T7);
`FoldDelta`, `SessionSnapshot`, `StreamEvent`, `Anomaly` (T1).
**Produces:**
```python
@dataclass(frozen=True) class RegistryEntry:
    session_id: str; pid: int; proc_start: str; cwd: str; kind: str; entrypoint: str
    status: str; waiting_for: str | None          # r5: NOT a Literal — see below
    name: str | None; name_source: str | None     # r5: same reason (an unrecognised nameSource)
    started_at_ms: int; updated_at_ms: int; status_updated_at_ms: int; version: str
    tmux: str | None; pid_domain: str | None
def scan_registry(config_dir: Path) -> tuple[list[RegistryEntry], tuple[Anomaly, ...]]: ...
def agents_json_fallback(timeout_s: float = 5.0) -> tuple[list[RegistryEntry], tuple[Anomaly, ...]]: ...
def is_attached_interactive(entry: RegistryEntry) -> bool: ...   # entrypoint == "cli"; NEVER reads .kind (E35)
def registry_delta(entry: RegistryEntry, liveness: Liveness, prior: SessionSnapshot | None,
                   now: str) -> FoldResult: ...     # same return shape as fold() — one writer, one rule set
def liveness_sweep(store: Store, host: HostPlatform, now: str) -> tuple[FoldResult, ...]: ...
                                                   # DP7: ends sessions whose process is observed gone
def run_discovery_loop(store: Store, host: HostPlatform,
                       on_result: Callable[[FoldResult], None],
                       shutdown: threading.Event) -> None: ...
                     # Also writes app_state["discovery_status"] each pass:
                     #   {hooks, registry_sessions, sdk_cli_skipped, unknown_status,
                     #    scan_interval_s, last_scan_at}
                     # That is how `fleet_summary` (T14) and `doctor` (T17) report the live
                     # sources WITHOUT importing this module's constants (r5, BLOCKING 4).
                     # r4 (A8): OWNS the 2.0s cadence, the sweep, and the shutdown join.
                     # It lives in signals/ — not daemons/ — because ADR-1 caps the composition
                     # root at 150 lines and forbids logic there. Same ownership gap F7 found
                     # for the relay hop; T18 only calls it and joins it.
REGISTRY_SCAN_INTERVAL_S: float   # 2.0 — sidecar files only; never `claude agents --json`
IDLE_TO_NEEDS_YOU_S: float        # 60.0 — §8's idle_prompt threshold, measured at 60.03 s (DP6, C21)
SDK_CLI_ENTRYPOINT: str           # "sdk-cli" — skipped and counted at M1 (RD9)
```

**Why `status` and `name_source` are `str` and not `Literal` (r5, BLOCKING 5).** Revision 4 added a
row saying an unrecognised `status` keeps the prior state and is counted, and *also* noted that the
`Literal` annotation "is a typecheck, not a runtime guard" — while leaving the `Literal` in place.
Those cannot both hold: under `mypy --strict`, `scan_registry` could not have *constructed* an entry
carrying an unknown value, so a builder would have had to drop the entry (losing the prior state the
new row promises to keep) or suppress the type error (breaking acceptance clause 9). The values are
**observed, not closed** (§Session sidecar file), and per-event shapes are verified at 2.1.270 while
the host runs 2.1.273 (G12). So the field is `str`, the three known values are checked **at the
mapping site**, and anything else takes the unknown-status row. `name_source` gets the same
treatment for the same reason — no finding demanded it, but an unrecognised `nameSource` bites
identically.

**Note on `registry_delta`'s return type (changed at r3).** It returns a **`FoldResult`**, not a
bare `FoldDelta`, so that the registry path can carry `StreamEvent`s and `Anomaly`s exactly as the
hook path does — which is what "one writer, one rule set" (D37) means, and what lets the
composition root publish both sources' events through the same line (ADR-4, F5).

---

### Task 8: The `hookd` dispatcher — the command text and its preflight

**Objective:** the shell dispatcher chosen in Decision pressure 1, owned by `HostPlatform`, with a
preflight that refuses rather than installing a hook that silently does nothing.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/hookd_command.py` — builds the command from a `SocketPlan`
- `tests/engines/test_hookd_command.py`
- `tests/engines/test_hookd_runtime.py` (spawns the real command against a real socket)

**Dependencies:** T3.
**Allowed Scope:** generating the one canonical command string (E17 — byte-stable, so user and
project scope deduplicate), the preflight check, and a runtime test that proves principle 4.
**Out-of-Scope Drift:** a Python dispatcher (Decision pressure 1); the spool-file fallback (named,
designed, **not built**); writing settings files (T9).
**Evidence used:** `docs/probes/2026-09-16-hookd-latency.md` (command shape, 3.4 ms, 40 KB frame
intact, 3.6 ms and exit 0 with no daemon); §Hook runtime contract (`/bin/sh -c`; stdin is payload
JSON + `\n` then EOF; exit 0 is non-blocking; per-entry timeout enforced; default 600 s — E18);
C7; §Unix domain socket (budget — E19).

**The command — deliberately not restated here.** It is **`HostPlatform.hook_dispatch(plan).command`**
(T3), and `host/` is its single definition site (P20). This task *consumes* it, quotes the socket
path into it, and proves its properties; it does not author it.

> **Why this section no longer carries a literal (F1 — the near-miss that produced the rule).**
> Revision 2 wrote the command out here as
> `exec 2>/dev/null; timeout 0.25 nc -U '<socket path>' || true; exit 0` — **without `-q0`**, while
> its own T3 evidence line carried the flag. Measured consequence (probe Result 1b): **253.6 ms per
> call instead of 3.2 ms**, because `nc` without `-q0` never shuts down its write side at stdin EOF
> and T10's listener reads to EOF, so neither side closes and `timeout 0.25` kills every
> invocation. That is 8× *worse* than the 31.7 ms Python dispatcher this whole decision exists to
> avoid, and it breaks C-1, `test_hookd_latency_under_10ms` and §18's write-volume argument at
> once. **And both variants delivered every frame** — so no test would have failed and no user
> would have known where the quarter-second went. A second copy of a command is what created that;
> one definition site, cited rather than restated, is the structural fix (E34, P20).

What this task owns instead: `timeout` bounds a hung `sessiond` at the spec's 250 ms (§8);
`|| true; exit 0` makes every failure mode exit 0 (K2); `2>/dev/null` keeps stderr out of the pane;
the socket path is single-quoted and validated against `SocketPlan.socket_path_budget` before it is
ever written.

**Expected Artifacts:** a command string; a preflight verdict; **seven** runtime proofs.
**Required Checks:**
`test_command_is_byte_stable` (same inputs → identical string, E17),
`test_command_comes_from_the_host_seam` (AST: this module constructs no `nc` literal — P20),
`test_command_quotes_socket_path`, `test_command_refuses_path_over_budget` (E19),
`test_preflight_reports_missing_binary` (G2 — `HookDispatchPlan.available` False with a reason),
and in `test_hookd_runtime.py`, all against a real UDS in `tmp_path`:
`test_hookd_delivers_payload_bytes` (a real corpus payload arrives byte-complete),
`test_hookd_delivers_40kb_frame`, `test_hookd_exits_zero_with_no_listener` (P4),
`test_hookd_exits_zero_on_hung_listener` (listener accepts and never reads; asserts wall time < 400 ms),
`test_hookd_exits_zero_on_empty_stdin`,
**`test_dispatch_command_shuts_down_write_side`** (**E34, the regression guard**: a listener that
reads to EOF must observe EOF within 50 ms of the payload; without `-q0` it observes it at ~250 ms.
This is the assertion that fails *loudly* where the 250 ms tax would otherwise be silent),
`test_hookd_latency_under_10ms` (25 invocations, assert mean < 10 ms — the probe measured 3.2 with
`-q0` and 253.6 without).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic for the string; **Probabilistic** for `test_hookd_latency_under_10ms`
— flake policy: 3 attempts, pass if 2 of 3 are under budget; a 3/3 failure is a real regression and
fails the build.
**Exit Criteria:** all twelve pass; the latency assertion holds; the EOF assertion holds; no Python
process is involved in the dispatch path; `test_dispatch_command_has_one_definition_site` (T2)
still green.
**Test Seams:** process seam (real socket, real `sh`).

**Consumes:** `SocketPlan`, `HookDispatchPlan`, `HostPlatform.hook_dispatch` (T3).
**Produces:**
```python
@dataclass(frozen=True) class HookEntry:        # what goes into a settings file
    command: str                                 # = HookDispatchPlan.command with the path quoted in
    timeout_s: int; available: bool; reason: str
def build_hook_entry(plan: SocketPlan, dispatch: HookDispatchPlan) -> HookEntry: ...
HOOK_ENTRY_TIMEOUT_S: int   # 5 — explicit, because the default is 600 (E18)
```

**Rename from revision 2 (`HookDispatch` → `HookEntry`, `build_hook_dispatch` → `build_hook_entry`).**
The old name collided with T3's new `HookDispatchPlan` and blurred the very distinction F1 is about:
`host/` **authors** the command; this module **quotes a path into it and packages it as a settings
entry**. T9's `Consumes` block names the new spellings.

---

### Task 9: Hook install / uninstall (`_shepherd_managed`)

**Objective:** merge a marked, idempotent block into a settings file, backing it up first and
validating after — and never touch the user's real one (K3).

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/hooks_config.py` — `install_hooks`, `uninstall_hooks`, `inspect_hooks`
- `src/shepherd/engines/claude_code/events.py` — the subscribed event list (§8) + all 33 names
- `tests/engines/test_hooks_install.py`
- `tests/conftest.py` — session-scoped guard fixture (P13)

**Dependencies:** T8. *(Not T2: T9 owns its own literal tuple of the 33 names; T2's parser is an independent second source, and the shared test reconciles them — r4, A7.)*
**Allowed Scope:** reading, backing up, merging, writing, re-reading, validating, rolling back, and
removing exactly our entries. The settings path is a **parameter**, never a default pointing at
`~/.claude`.
**Out-of-Scope Drift:** touching `~/.claude/settings.json` in any test (K3, C6); registering
`WorktreeCreate` (data-schemas: any command hook on it breaks `--worktree`); `async: true` (not
measured for the shutdown path — a change to make on evidence, not on hope).
**Evidence used:** §Hooks config schema (the group/entry shape, `_shepherd_managed` accepted
silently, one broken `PreToolUse`/`PermissionRequest` entry disables the whole file, invalid JSON
voids it, `-p` reports nothing — only `claude doctor` does — E16); §User-scope hooks with
`_shepherd_managed` (identical command strings deduplicate — E17); **the 33 event names as parsed
from `docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt`** — the
`claude doctor` capture that lists them in its "Valid events:" line. **Not**
`hooks/binary/hook-events.json`, which is empty on disk (`{"offset":null,"count":0,"events":null}`)
although data-schemas cites `"count": 33` from it (G13, F11); §8 "Events subscribed"; and Task 1's
drift-check result confirming all 33 are still present in 2.1.273 (G12).

**Subscribed events at M1** (§8's list, minus what M1 cannot use):
`SessionStart · UserPromptSubmit · PreToolUse · PostToolUse · PostToolUseFailure · MessageDisplay ·
Notification · PermissionRequest · PermissionDenied · Elicitation · ElicitationResult · Stop ·
StopFailure · SessionEnd · SubagentStart · SubagentStop · TaskCreated · TaskCompleted · PreCompact ·
PostCompact · CwdChanged · PreModelSwitch · PostModelSwitch · FileChanged`
— plus **`PostToolBatch`**, which §8 does not subscribe but which is the **only** event that records
a permission refusal or hook block (data-schemas §PostToolBatch). Adding it is additive, costs one
entry, and is listed under Recommended Defaults as unapproved.

**Expected Artifacts:** an installer with a matching uninstaller and a `doctor`-grade inspector.
**Required Checks:**
`test_install_backs_up_first` (backup exists and matches the pre-image),
`test_installed_entries_are_marked` (every group **and** every entry carries `_shepherd_managed`),
`test_install_sets_explicit_timeout` (E18),
`test_install_is_idempotent` (twice ⇒ identical file bytes, E17),
`test_install_rolls_back_on_invalid_result` (inject a write failure; original restored),
`test_install_refuses_without_dispatch_binary` (G2 — including `MacHost`'s unverified flag set),
`test_install_refuses_over_socket_path_budget` (E19),
`test_installed_command_is_the_host_command_verbatim` (P20 — the settings file contains
`HookDispatchPlan.command` with only the socket path substituted; no second spelling reaches disk),
`test_hook_event_names_match_the_doctor_capture` (G13 — 33, in order, parsed from the capture),
`test_install_detects_pre_existing_breakage` (a foreign malformed `PreToolUse` entry is reported, C6/E16),
`test_uninstall_leaves_foreign_hooks` (a user's own hook survives byte-identically),
`test_uninstall_is_idempotent`,
`test_install_registers_no_worktree_create`,
and the guard: `test_real_user_settings_untouched` (P13, K3).
**Checkpoint Type:** **human_verify** — before the first real install on this machine, a human
confirms the backup path and the diff of the merged file. *Reason category: manual-verification.*
Every automated test runs against an isolated `CLAUDE_CONFIG_DIR`; this gate exists because C6's
blast radius is "every hook the user has".
**Validation Level:** Deterministic for the suite; **Manual** for the one-time real install —
checklist: (1) `shepherd install-hooks --settings <isolated> --dry-run` shows the exact diff;
(2) the backup file exists and its sha256 matches the pre-image; (3) `claude doctor` reports no
invalid settings afterwards; (4) `shepherd uninstall-hooks` returns the file to the backup's hash.
**Exit Criteria:** thirteen tests pass (the fourteenth named above, `test_hook_event_names_match_the_doctor_capture`, is **T2's** and is listed here only because T9 must satisfy it — r5); the real `~/.claude/settings.json` hash is unchanged across
the whole suite.
**Test Seams:** integration (real files in `tmp_path` + isolated `CLAUDE_CONFIG_DIR` — installer
tests need no credentials, so K3's isolation holds here by construction; only T18's live lane
cannot have it, per A16).

**Consumes:** `build_hook_entry`, `HookEntry`, `HOOK_ENTRY_TIMEOUT_S` (T8). **Nothing from T2** —
see the note below.
**Produces:**
```python
SUBSCRIBED_EVENTS: tuple[str, ...]
ALL_HOOK_EVENT_NAMES: tuple[str, ...]          # 33, a LITERAL tuple in this module (see the note)
MANAGED_MARKER: str                             # "_shepherd_managed"
@dataclass(frozen=True) class InstallResult:
    settings_path: Path; backup_path: Path; events_installed: int
    warnings: tuple[str, ...]; refused_reason: str | None
@dataclass(frozen=True) class HookInspection:   # defined here at r3 — it was used, never defined (F9)
    installed: bool; managed_entries: int; foreign_entries: int
    pre_existing_breakage: tuple[str, ...]      # E16: a foreign malformed entry disables every hook
    command_matches_current_host: bool          # False when the host's command changed under us
def install_hooks(settings_path: Path, entry: HookEntry, dry_run: bool = False) -> InstallResult: ...
def uninstall_hooks(settings_path: Path) -> InstallResult: ...
def inspect_hooks(settings_path: Path) -> HookInspection: ...
```

**Why the 33 names are a literal here and parsed in T2 (r4, A7).** Revision 3 had T9 *consume*
`CLAUDE_CODE_HOOK_EVENT_NAMES` from `tests/boundaries/`, which makes **product code import from the
test package** — and worse, T2 parses that tuple out of
`docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt`, so the
installed package would depend on the **probe tree at runtime**. That tree is not shipped; M6's
packaging would break, and the failure would appear only after installation.

The correct shape is **two independent sources reconciled by one test**:
`engines/claude_code/events.py` holds the names as a literal tuple (the product's copy, with the
capture cited in a comment), T2's parser reads the capture (the evidence's copy), and
`test_hook_event_names_match_the_doctor_capture` asserts they are equal, in order, 33 of them. A
drift in either is a failing test rather than a silent divergence — which is the same discipline
Task 1's drift check applies to the engine binary.

---

### Task 10: `sessiond` — UDS listener, framing, relay, bounded buffer

**Objective:** the process that must not restart, doing the least possible: accept, frame, relay,
buffer, count.

**Files/Surfaces:**
- `src/shepherd/daemons/sessiond.py` (≤150 lines — ADR-1)
- `src/shepherd/engines/claude_code/ingest_socket.py` — accept loop, framing, `SO_PEERCRED`
- `src/shepherd/engines/claude_code/relay.py` — bounded buffer + reconnect
- `tests/daemons/test_sessiond_socket.py`, `tests/daemons/test_relay_buffer.py`

**Dependencies:** T3, T8.
**Allowed Scope:** bind (umask **before** bind, unlink stale first), accept, read-to-EOF, hand each
frame to an injected `on_frame` callback, and **shut down cleanly**. The `Relay` instance itself is
constructed and passed in by the composition root (T18) — `sessiond.py` names no transport, which is
what keeps this task and T10b independent of each other rather than circular.
**Out-of-Scope Drift:** **any database access** (D37: `controld` is the only writer; `sessiond`
never migrates — §7 rule 3); any fold logic; any pty (M3). `sessiond` importing `store` is a
build failure by construction — add an explicit test. **The relay hop's wire format, handshake and
reconnect policy belong to T10b**, not here.

**Teardown is part of this task (F15).** Revision 2 specified no shutdown path at all, though T18
restarts `controld` and E20 records that a stale socket yields `ECONNREFUSED`/`EADDRINUSE`. On
`SIGTERM`/`SIGINT`, `sessiond`: stops accepting, gives the relay a bounded drain window
(`SHUTDOWN_DRAIN_S = 2.0`), **unlinks its socket**, and exits 0. That is the difference between
"a restart loses nothing" and "a restart loses the buffer and cannot rebind".
**Evidence used:** §Unix domain socket (0600 via umask, no chmod window; unlink before bind;
`ECONNREFUSED` on a stale path; `SO_PEERCRED` captured at `connect()` and surviving peer exit —
E20, E21); §Hook runtime contract (`CLAUDE_PID` in the hook env equals the owning pid, so no
`/proc` walk is needed — the frame is authoritative); D37.
**Expected Artifacts:** a listener that survives `controld` restarts with a counted, bounded loss.
**Required Checks:**
`test_socket_is_0600_in_0700_dir`, `test_stale_socket_is_unlinked_before_bind` (E20),
`test_other_uid_cannot_connect` (skipped unless a second uid is available; the capture used
`runuser -u nobody`), `test_frames_are_read_to_eof`, `test_40kb_frame_is_complete`,
**`test_sigterm_unlinks_the_socket`** (F15),
**`test_restart_after_clean_shutdown_binds_without_eaddrinuse`** (F15, E20),
**`test_shutdown_drains_the_relay_within_the_window`** (F15),
`test_sessiond_never_opens_the_database`
(AST: `daemons/sessiond.py` and its imports never reach `shepherd.store`),
`test_sessiond_never_migrates` (§7 rule 3).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — real sockets under `tmp_path`, `controld` stubbed by a
`ScriptedHost`-configured runtime dir.
**Exit Criteria:** ten pass; `sessiond.py` ≤150 lines; the storage-boundary and
`test_sessiond_never_opens_the_database` tests are green; **the socket is gone after a clean exit**.
**Test Seams:** process seam.

**Consumes:** `SocketPlan`, `HostPlatform` (T3); `Frame` (T1); `HookEntry` (T8).
**Produces:**
```python
def serve_ingest(plan: SocketPlan, on_frame: Callable[[Frame], None],
                 on_shutdown: Callable[[], None], shutdown: threading.Event) -> None: ...
                 # unlinks the socket after on_shutdown returns (F15)
SHUTDOWN_DRAIN_S: float   # 2.0
```

---

### Task 10b: The `sessiond → controld` hop — listener, wire format, schema handshake, bounded buffer

**Objective:** specify and build the **other half of M1's process topology**, which revision 2 left
implicit. It produced a `Relay` and tested buffering and drain-on-reconnect without ever defining
which socket `controld` listens on, who creates it, what a frame looks like on that hop, or what
happens on reconnect — and §7 migration rule 3's handshake ("`sessiond` **waits for `controld` to
report the expected version over the UDS**", `orchestrator-platform.md:898–900`) had a risk-matrix
row claiming a test that no task built (F7). It cannot live inside T18's ≤150-line composition
root, which ADR-1 forbids from holding logic.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/relay.py` — `Relay` (client half: connect, handshake, send, buffer, drain)
- `src/shepherd/daemons/control_ingest.py` — `serve_control_ingest` (server half, ≤150 lines — it
  is in `daemons/`, so ADR-1's cap applies and the frame codec below lives in `engines/`)
- `src/shepherd/engines/claude_code/relay_wire.py` — `encode_frame` / `decode_frame` / `Hello` (pure)
- `tests/daemons/test_relay_buffer.py`, `tests/daemons/test_relay_wire.py`, `tests/daemons/test_control_handshake.py`

**Dependencies:** T1 (`Frame`), T3 (`control_socket`), T5 (`EXPECTED_SCHEMA_VERSION`). **Not T10** —
`Frame` is an L1 type (T1) and `sessiond` names no transport, so these two tasks are independent and
either may be built first. The `b` in the label is a position in the plan, not an ordering.
**Allowed Scope:** exactly the hop. Two sockets exist in M1 and the seam already names them:
`host.control_socket("sessiond")` (hooks → `sessiond`, T10) and **`host.control_socket("controld")`**
(`sessiond` → `controld`, here). **`controld` creates and owns its own socket**, with the same
umask-before-bind and unlink-stale rules (E20), and unlinks it on shutdown (F15).

**The wire format, stated once.** The ingest socket (T10) is one connection per frame, read to EOF —
that is the hook contract and it stays. This hop is **one long-lived connection carrying many
frames**, so it needs framing: **newline-delimited JSON**, one object per line, payload
base64-encoded so the framing is binary-safe regardless of what a hook sends:

```text
controld → sessiond, first line:   {"hello":"controld","schema_version":<int>,"pid":<int>}
sessiond → controld, each frame:   {"payload_b64":"<base64>","received_at":"<iso8601>","peer_pid":<int|null>}
```

**The handshake (§7 migration rule 3).** `sessiond` reads the `hello` line before sending anything.
If `schema_version != EXPECTED_SCHEMA_VERSION` it **does not relay** — it buffers, counts, and
reports the mismatch through `RelayStats`; it never migrates and never writes (D37). This is the
rule-3 behaviour the spec states and no revision-2 task built.

**Reconnect and buffering (D37's guarantee).** On a dropped connection: reconnect with backoff
0.1 s → 2.0 s capped, buffer up to `RELAY_BUFFER_MAX` frames in order, count every overflow
(principle 5), and **drain in order** once the handshake succeeds again. A frame is never dropped
silently and never reordered.

**Out-of-Scope Drift:** any fold logic (T11); any database access from `sessiond` (D37); a generic
RPC layer; compression; a second transport. Retry-forever without a bound on the buffer.
**Evidence used:** §Unix domain socket (umask before bind, unlink stale, `ECONNREFUSED` on a stale
path — E20, E21); §7 Migrations rule 3 (`orchestrator-platform.md:893–900`); D37 (`controld` is
the sole writer; `sessiond` must not restart).
**Expected Artifacts:** a relay that survives a `controld` restart with a counted, bounded loss, and
a listener that refuses to accept frames it cannot fold.
**Required Checks:**
`test_relay_wire_roundtrip` (pure codec, including a 40 KB payload and one with embedded newlines),
`test_relay_frame_roundtrip_40kb` (over a real socket),
`test_controld_socket_is_0600_in_0700_dir`,
`test_relay_waits_for_hello_before_sending` (§7 rule 3),
`test_relay_refuses_on_schema_version_mismatch` (§7 rule 3 — buffers and counts, never relays),
`test_relay_buffers_while_controld_down`,
`test_relay_buffer_overflow_is_counted` (principle 5),
`test_relay_drains_in_order_on_reconnect`,
`test_relay_backoff_is_bounded` (never busier than 0.1 s; never slower than 2.0 s),
`test_control_ingest_unlinks_socket_on_shutdown` (F15).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — real sockets under `tmp_path`; the codec is a unit test.
**Exit Criteria:** ten pass; `control_ingest.py` ≤150 lines; no `store` import in `relay.py`.
**Test Seams:** unit (codec) + process seam (real socket).

**Consumes:** `SocketPlan`, `HostPlatform.control_socket` (T3); `EXPECTED_SCHEMA_VERSION` (T5);
`Frame` (T1).
**Produces:**
```python
@dataclass(frozen=True) class Hello: schema_version: int; pid: int
def encode_frame(frame: Frame) -> bytes: ...          # NDJSON line, payload base64
def decode_frame(line: bytes) -> Frame: ...
@dataclass(frozen=True) class RelayStats:
    buffered: int; overflowed: int; delivered: int; connected: bool
    schema_mismatch: int; last_error: str | None
class Relay:
    def __init__(self, target: Path, max_buffered: int, expected_version: int) -> None: ...
    def send(self, frame: Frame) -> None: ...
    def stats(self) -> RelayStats: ...
    def close(self, drain_s: float) -> RelayStats: ...
def serve_control_ingest(plan: SocketPlan, schema_version: int,
                         on_frame: Callable[[Frame], None],
                         shutdown: threading.Event) -> None: ...
RELAY_BUFFER_MAX: int   # 10_000
RELAY_BACKOFF_S: tuple[float, float]   # (0.1, 2.0)
```

---

### Task 11: The fold — engine-neutral normalisation and the rule table

**Objective:** the differentiator. Turn a Claude Code hook payload into an engine-neutral `Signal`
inside the adapter, then fold that `Signal` into `session` columns with a pure function.

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/normalise.py` — `parse_hook_payload(raw, received_at) -> Signal | Malformed`
- `src/shepherd/signals/rules.py` — the `FoldRule` table (ADR-6)
- `src/shepherd/signals/fold.py` — `fold(signal, prior, received_at) -> FoldResult`
- `src/shepherd/signals/ordering.py` — `fleet_sort_key`
- `tests/signals/test_normalise.py`, `tests/signals/test_fold_rules.py`

**Dependencies:** T1, T6, T7.
**Allowed Scope:** the fold rule table below and nothing else. **Pure** — `received_at` is a
parameter, never a clock read (that is what makes T12's corpus deterministic). **Every engine field
name is read in `engines/claude_code/normalise.py` and projected into `Signal.fields` under a key
from `SIGNAL_FIELD_KEYS` (T1); `signals/` reads only those keys** (r4, BLOCKING 2).
**Out-of-Scope Drift:** `stop_reason`, `outcome`, `why`, `confidence`, `decided_by`,
`next_actions[]` — all **M2**. Any reference to `Stop.stop_reason`, which does not exist (D46, E9).
Any Claude Code hook name inside `signals/` (T2's `test_no_engine_vocabulary_in_signals`) — **and
any Claude Code *field* name there either** (`tool_input`, `file_path`, `to_model`, `agent_id`,
`agent_type`, `notification_type`, `error`, `new_cwd` — the neutral key is `next_cwd`, r5): they
belong to the normaliser, and
`test_signals_reads_only_neutral_field_keys` enforces it (r4). Any comparison of `Signal.raw_kind`
against a literal — it exists for anomaly detail and `doctor`, never for control flow.

**Two tables, not one (r5, BLOCKING 1).** Revision 4 kept a single table whose column 1 was an
engine event name and whose column 3 was a fold effect — two different maps in one grid. That is
why `SESSION_REGISTERED` and `TURN_PROGRESS` each appeared twice with differently-worded effects,
and why `test_every_signal_kind_has_exactly_one_rule` was contradicted by the table it polices.
Split, each map is total by inspection and the test means something.

**Table A — the normaliser's map (lives in `engines/claude_code/normalise.py`).** Engine event →
`SignalKind` + the neutral `fields` it projects. **Every engine name and every engine field name
appears only here.**

| Engine event | → `SignalKind` | `fields` the normaliser sets | Evidence | Constraint |
|---|---|---|---|---|
| `SessionStart` | `SESSION_REGISTERED` | `start_source` ∈ {startup,resume,clear,fork,compact} | §SessionStart | E3 |
| *any event whose `session_id` is unknown to the store* | *(its own kind, unchanged)* | — | §Hooks written into a running session | **D47**, E2 — registration is the store's job, not a kind: see the cross-cutting rules below |
| `UserPromptSubmit` | `PROMPT_SUBMITTED` | `prompt` | §UserPromptSubmit; §`last-prompt` entry | **C11**, E6, E7 |
| `PreToolUse` | `TOOL_STARTED` | `tool_label` | §PreToolUse | — |
| `PostToolUse` | `TOOL_FINISHED` | `changed_paths` — **the `tool_name ∈ {Edit, Write}` test and the `tool_input.file_path` read happen here** | §PostToolUse; §FileChanged spec alignment | **C9**, E5 |
| `PostToolUseFailure` | `TOOL_FAILED` | — | §PostToolUseFailure | — |
| `PostToolBatch` | `TOOL_BATCH_FINISHED` | — | §PostToolBatch | — |
| `MessageDisplay` | `TURN_PROGRESS` | — | §MessageDisplay | — |
| `PermissionRequest` | `NEEDS_INPUT` | `ask` = `"permission: {tool_name}({summary})"` | §PermissionRequest; §PermissionRequest payload (TUI) | E-G5 |
| `Notification{permission_prompt \| idle_prompt \| elicitation_dialog \| agent_needs_input \| elicitation_url_dialog}` | `NEEDS_INPUT` | `ask` = the actual ask (`"idle — waiting for your next instruction"` for `idle_prompt`) — **`notification_type` is read here and never leaves** | §Notification; §Notification payload (TUI) | **C21**, DP3, G4 |
| `Notification{any other type}` | `NOTICE_UNMAPPED` | — | §Notification (`elicitation_response`, `auth_success`, …) | **principle 5** |
| `Elicitation` | `NEEDS_INPUT` | `ask` | §Elicitation | — |
| `PermissionDenied` · `ElicitationResult` | `INPUT_RESOLVED` | — | §PermissionDenied; §Elicitation | — |
| `SubagentStart` | `SUBAGENT_STARTED` | `subagent_id` | §SubagentStart | — |
| `SubagentStop` | `SUBAGENT_FINISHED` | `subagent_id` — **the `id` of an `agent_type == ""` stop is dropped here**; the signal is still emitted, with no `subagent_id`, so the fold sees a finish with nothing to pair on, leaves the live-set count untouched and counts one `SUBAGENT_UNDERFLOW` (reworded at r7 per BLOCKER T11-1: dropping the whole *event* makes C10's "count the anomaly" unimplementable, since the normaliser returns no anomalies) | §SubagentStop; §Hook event parity | **C10**, E4, P1 |
| `TaskCreated` | `TASK_CREATED` | `task_id` | §TaskCreated/TaskCompleted | E-P11 |
| `TaskCompleted` | `TASK_COMPLETED` | `task_id` | §TaskCreated/TaskCompleted (`task_id` is a small per-session counter, **not** a UUID) | P11 |
| `FileChanged` | `FILES_CHANGED` | `changed_paths` (declared watch paths only) | §FileChanged | **C9** |
| `CwdChanged` | `CWD_CHANGED` | **`next_cwd`** (the engine's field is `new_cwd`; the neutral key is deliberately *not* that spelling — r5, BLOCKING 3) | §CwdChanged (`data-schemas.md:954`) | §5.0 |
| `PreModelSwitch` · `PostModelSwitch` | `MODEL_CHANGED` | `model` (read from `to_model`) | §PreModelSwitch/PostModelSwitch | — |
| `Stop` · `SessionEnd` | `SESSION_STOPPED` | — | §Stop (**no `stop_reason` field**); §SessionEnd (**not guaranteed in `-p`**) | **D46**, E8, E9 |
| `StopFailure` | `STOP_FAILED` | `failure_note` (read from `error`) | §StopFailure (field is `error`, not `error_type`) | **D46**, E10 |
| `InstructionsLoaded` · `ConfigChange` · `Setup` · `DirectoryAdded` · `UserPromptExpansion` · `WorktreeCreate` · `PreCompact` · `PostCompact` · `TeammateIdle` · `WorktreeRemove` | `TURN_PROGRESS` | — | §Hook event names | — |
| *unrecognised `hook_event_name`* | `UNKNOWN` | — | §Hook event names | **principle 5** |

**Table B — the fold's rule table (`signals/rules.py`): exactly one row per `SignalKind`.** This is
the table `FoldRule` types and `test_every_signal_kind_has_exactly_one_rule` polices. It names no
engine event and no engine field.

| `SignalKind` | Column effect | Clears `needs_you`? |
|---|---|---|
| `SESSION_REGISTERED` | `cwd`, `repo_id`, `started_at`; records `fields["start_source"]` in the anomaly view | no |
| `PROMPT_SUBMITTED` | `brief` **only if null** and the prompt does not start with `<task-notification>` | **yes** |
| `TURN_PROGRESS` | liveness only | no |
| `TOOL_STARTED` | `state = running` | **yes** |
| `TOOL_FINISHED` | `state = running`; append `fields["changed_paths"]`' repos to `repos_touched` | **yes** |
| `TOOL_FAILED` | `state = running` (the failure tail is M2's heuristic 3) | **yes** |
| `TOOL_BATCH_FINISHED` | `state = running`; counts that a refusal happened (counter only at M1) | **yes** |
| `NEEDS_INPUT` | `state = needs_you`; `needs_you_reason = fields["ask"]` | no (it *sets* it) |
| `INPUT_RESOLVED` | clears `needs_you` and nothing else | **yes** |
| `NOTICE_UNMAPPED` | liveness only; **counted** | no |
| `SUBAGENT_STARTED` | add `fields["subagent_id"]` to the live set | no |
| `SUBAGENT_FINISHED` | remove it; `active_subagents = len(set)`, clamped ≥ 0; unmatched stop **counted** | no |
| `TASK_CREATED` | add `fields["task_id"]` to the created set; `tasks_total = len(set)` | no |
| `TASK_COMPLETED` | add to the completed set; `tasks_done = len(completed ∩ created)` | no |
| `FILES_CHANGED` | append `fields["changed_paths"]`' repos to `repos_touched` | no |
| `CWD_CHANGED` | `cwd = fields["next_cwd"]`; **re-bind** `repo_id` | no |
| `MODEL_CHANGED` | `model = fields["model"]` | no |
| `SESSION_STOPPED` | `state = stopped`, `ended_at = received_at` | **yes** |
| `STOP_FAILED` | `state = stopped`, `ended_at`; `fields["failure_note"]` into the anomaly counter only (the mapping is M2) | **yes** |
| `UNKNOWN` | liveness only; **counted** | no |

**Three cross-cutting rules, applied by `fold()` outside the table** — stated here because each is
one rule for *every* kind, and putting them in the table is what produced revision 4's duplicate
rows:

1. **`last_event_at = received_at` on every signal**, receiver-stamped (§Common input fields: "any
   timestamp: never" — **C8**).
2. **An unknown `engine_session_id` inserts a `session` row and binds cwd→repo, whatever the kind**
   (§Hooks written into a running session — **D47**, E2). Registration is a store operation keyed on
   *absence*, not a `SignalKind`; revision 4 modelled it as one and got two `SESSION_REGISTERED`
   rows with different effects.
3. **`needs_you` is cleared by any signal whose Table-B row says "yes"** — the **inferred** rule
   (G5, E-G5: nothing marks resolution). This is *not* its own kind. Revision 4 left a row mapping
   "`PreToolUse`/`PostToolUse`/`UserPromptSubmit`/`Stop` **after** a `needs_you`" to `INPUT_RESOLVED`,
   which **became unproducible when `applies` was deleted** (r5, BLOCKING 2): one payload yields one
   `Signal` with one `kind`, and `parse_hook_payload(raw, received_at)` has no prior state, so the
   normaliser cannot know a `needs_you` preceded the event. `delta_fn` **does** receive
   `prior: SessionSnapshot | None`, so the clear happens there, in the rows above. `INPUT_RESOLVED`
   now belongs only to `PermissionDenied` and `ElicitationResult`, which are explicit resolutions.

**Liveness backstop:** a session whose `last_event_at` is older than `LIVENESS_WINDOW_S` (90, §8)
is not `running`. Computed at read time in `ordering.py`, never written by the fold — a derived
value that needs no event to become true.

**Two revision-3 notes on this table:**

- **The `INPUT_RESOLVED` row is the A9 inference, and it is now the *fallback*, not the only rule.**
  On any session with a readable sidecar, the registry supplies an **observed** clearing signal —
  `status` leaving `"waiting"` (T7b's mapping table; §PermissionRequest "Variants and edge cases").
  The inference here covers only the residual where no sidecar is readable. That is what shrinks
  A9 from a critical assumption to a bounded one (F12, A9).
- **The 33 names this task maps come from the `claude doctor` capture, not from the empty
  `hook-events.json`** (G13), and Task 1's drift check confirms all 33 are still present in the
  running 2.1.273 binary (G12). `test_normalise_all_33_event_names` parses the capture rather than
  trusting a hand-copied tuple.

**Expected Artifacts:** a pure fold; a normaliser that maps all 33 names; a sort key.
**Required Checks:**
`test_normalise_all_33_event_names` (every name maps to a `SignalKind`; none raises),
`test_normalise_stamps_nothing` (the payload's absence of a timestamp is honoured — C8),
`test_registers_on_first_event_of_any_kind` (D47),
`test_brief_ignores_injected_prompts` (C11, S18 fixture),
`test_brief_is_only_set_once`,
`test_subagent_count_never_negative` (C10, P1),
`test_subagent_internal_stops_are_ignored_and_counted`,
`test_tasks_done_never_exceeds_total` (P11),
`test_repos_touched_from_posttooluse_paths` (C9),
`test_needs_you_reason_is_the_actual_ask`,
`test_idle_prompt_sets_needs_you_with_idle_reason` (Decision pressure 3),
`test_no_rule_references_stop_reason` (D46 — greps the rule table for the literal),
**`test_every_signal_kind_has_exactly_one_rule`** (r4 — **Table B** is a total function of
`SignalKind`, which is what lets `fold()` be a dict lookup and not a predicate walk; r5 split the
tables so this is now checkable by inspection as well as by test),
**`test_every_engine_event_maps_to_a_kind`** (r5 — **Table A** is total over the 33 names plus the
unrecognised case, asserted in the normaliser's own tests),
**`test_needs_you_is_cleared_by_the_next_activity`** (r5, BLOCKING 2 — the clear happens inside the
`TOOL_*`/`PROMPT_SUBMITTED`/`SESSION_STOPPED` rules using `prior: SessionSnapshot | None`, since
`parse_hook_payload` has no prior state and cannot emit a context-dependent kind),
**`test_every_fold_rule_cites_an_existing_section`** (**A6 — the only mechanical enforcement of K1**:
every `evidence` string is non-empty *and* appears as a section heading in `docs/specs/data-schemas.md`;
acceptance clause 10 names this test),
**`test_normaliser_owns_every_engine_field_name`** (r4 — the three `needs_you_reason` strings,
`changed_paths`, `model`, `subagent_id` and `failure_note` are all composed in `engines/`),
`test_fold_writes_only_declared_fields` (P3),
`test_fold_never_raises` (P2 — 200 mutated payloads),
`test_fold_is_deterministic` (P2),
`test_unmapped_values_are_counted` (principle 5).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals/ -q`.
**Exit Criteria:** nineteen pass; `test_no_engine_vocabulary_in_signals` green, **including its new field-level half** (`test_signals_reads_only_neutral_field_keys`); `fold` has no
imports from `engines/`.
**Test Seams:** unit (pure functions).

**Consumes:** `Signal`, `SignalKind`, `SessionState`, `Anomaly`, **`FoldDelta`, `SessionSnapshot`,
`StreamEvent`, `MalformedPayload`** (all T1 — `core/`); `Store.apply_fold_delta`, `Session` (T6);
`bind_cwd_to_repo` (T7).
**Produces:**
```python
def parse_hook_payload(raw: bytes, received_at: str) -> Signal | MalformedPayload: ...
from shepherd.core.fold_types import FoldDelta, SessionSnapshot   # RE-EXPORT, not a definition (T1 owns it)
@dataclass(frozen=True) class FoldResult:
    delta: FoldDelta; events: tuple[StreamEvent, ...]; anomalies: tuple[Anomaly, ...]
@dataclass(frozen=True) class FoldRule:                  # ADR-6
    kind: SignalKind                                     # r4: typed, so no raw_kind predicate is needed
    delta_fn: Callable[[Signal, SessionSnapshot | None], FoldDelta]
    emits: tuple[str, ...]; evidence: str               # the ONE position T2's scan excludes (F4)
FOLD_RULES: tuple[FoldRule, ...]                         # exactly one row per SignalKind
def fold(signal: Signal, prior: SessionSnapshot | None, received_at: str) -> FoldResult: ...
def fleet_sort_key(row: FleetRow, now: str) -> tuple[int, str]: ...
LIVENESS_WINDOW_S: int   # 90
```

**`FoldDelta` is re-exported here, not defined here (F9).** Revision 2 defined it as a full
dataclass in this task while its own self-review asserted the definition site was `core/` at T1 —
so T7b's "not a forward reference" argument rested on a fix that had never been applied. T1's
Produces block now holds the definition; this module re-exports it so `signals/fold.py` remains the
natural import path for the hook lane.

---

### Task 12: The golden-fixture lane — 429 real events (§14 lane 1)

**Objective:** the test lane that carries the value. No mocking of Claude Code — the fixtures **are**
Claude Code.

**Files/Surfaces:**
- `tests/fixtures/corpus.py` — loader over `docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl`
- `tests/signals/test_fold_golden_corpus.py`
- `tests/signals/test_fold_concurrent_interleave.py`

**Dependencies:** T11.
**Allowed Scope:** replaying the corpus through `parse_hook_payload` → `fold` → `Store`.
**The corpus shape is measured, not assumed:** 429 lines, **0 malformed**, **50 distinct
`session_id`s**, 32 distinct `_event` values, and **54 scenario directories of which 53 carry an
`events.jsonl`** (`S09_perm_bypass_echo` has a `meta.json` and no events — r5: both counts appear in
this plan and neither was wrong, but nothing said why they differ). Each line is an envelope:

```json
{"_event":"SessionStart","_captured_at":"…","_epoch":1789398921.969238,
 "_claude_version":"2.1.270 (Claude Code)","_hook_pid":…,"_claude_pid":…,
 "_ancestry":[…],"_raw_trailing_newline":true,"payload":{…exact hook stdin JSON…}}
```

`payload` is byte-equivalent to hook stdin, so the harness feeds `payload` and synthesises nothing.
`_epoch` is a **real receipt timestamp**, which is precisely what C8 says the receiver must supply —
so the corpus tests the stamping without inventing a clock.

**Coverage, by count — re-derived from the corpus at r5, and it now sums to 429 across 32 values**
(revision 2's list summed to 421 across 31, entirely in the singleton tail; the corpus totals were
always right, but this list is what a builder reads to judge whether a rule has a fixture):

55 `SessionStart` · 51 `UserPromptSubmit` · 51 `MessageDisplay` · 50 `SessionEnd` ·
42 `PreToolUse` · 40 `PostToolBatch` · 30 `PostToolUse` · 26 `Stop` · 23 `StopFailure` ·
16 `InstructionsLoaded` · 6 `PermissionRequest` · **6 `UserPromptSubmit__from_settings_json`** ·
4 `SubagentStop` · 3 `Notification` · 3 `TaskCreated` · **3 `Setup`** · 2 `PostToolUseFailure` ·
2 `TaskCompleted` · 2 `SubagentStart` · 2 `FileChanged` · and **1 each** of `Elicitation`,
`ElicitationResult`, `PermissionDenied`, `CwdChanged`, `PreCompact`, `PostCompact`,
`DirectoryAdded`, `WorktreeCreate`, `UserPromptExpansion`, `ConfigChange`, `PreModelSwitch`,
`PostModelSwitch`. **Sum: 429.**

Two notes a builder needs from this list:

- **`UserPromptSubmit__from_settings_json` is a probe-harness label, not a hook event name.** It is
  the same `UserPromptSubmit` payload captured through a settings-file hook rather than the
  harness's own, and `_event` carries the harness's label. The loader must normalise it or the
  32-value count will not match the 33 documented names. It is also why revision 2's list, which
  silently dropped it, still appeared to balance.
- **`TeammateIdle` and `WorktreeRemove` have ZERO captures.** Both are in Table A's liveness-only
  row, so nothing rests on them, but no fixture exercises either — stated here rather than
  discovered when someone looks for one.

**Every event M1's fold consumes is represented.** Two of the thin ones are the constraints
themselves: **2 `SubagentStart` against 4 `SubagentStop` is C10's negative-counter case sitting in
the corpus**, and **both `FileChanged` captures are declared watch paths, which is C9**. Those are
testable today, not hypothetical.

**Out-of-Scope Drift:** editing a fixture to make a test pass (the fixture is the ground truth —
if the fold disagrees with a capture, the fold is wrong); adding synthesised payloads to the
corpus directory; M2 verdict assertions.
**Known coverage gaps (G3, G4), handled here rather than discovered in BUILD:**
- **No multi-session-concurrent capture.** The 50 sessions are sequential. `test_fold_concurrent_interleave`
  builds a **synthetic interleave by merge-sorting all 429 envelopes on `_epoch` across session
  ids** — a real ordering of real events — and asserts that per-session final state is identical to
  the sequential replay. Genuine contention is covered live in T18.
- **`Notification{idle_prompt}` appears only in the single TUI run.** Asserted from that one
  capture and counted in production.

**Expected Artifacts:** a replay harness; a per-session expected-state table checked into
`tests/fixtures/expected/` and regenerated by an explicit `--update-golden` flag (never
automatically).
**Required Checks:**
`test_corpus_loads_429_events_0_malformed` (guards the corpus itself against drift),
`test_corpus_has_50_sessions`,
`test_every_payload_parses` (P2),
`test_replay_produces_50_session_rows` (P8 — 429 events, 50 rows; **53 of the 54 scenarios are
`claude -p` runs, so this lane is the proof that the hook path registers `-p` sessions — RD9's
filter is registry-only and never reaches here**),
`test_replay_matches_expected_state` (the per-session golden table),
`test_subagent_count_never_negative_over_corpus` (C10, P1),
`test_repos_touched_never_from_filechanged_alone` (C9),
`test_brief_never_starts_with_task_notification` (C11),
`test_received_at_comes_from_epoch_not_the_clock` (C8),
`test_fold_concurrent_interleave` (G3),
`test_replay_is_idempotent` (replay twice ⇒ identical rows).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/signals/test_fold_golden_corpus.py -q`.
**Exit Criteria:** eleven pass; the golden table is committed; the corpus files are **read-only**
in the test (a test asserts their sha256 is unchanged after the run).
**Test Seams:** unit (the fold's own interface).

**Consumes:** `parse_hook_payload`, `fold`, `FoldResult` (T11); `Store` (T6).
**Produces:**
```python
CORPUS_ROOT: Path
def load_corpus() -> list[CorpusEvent]: ...        # sorted by _epoch
@dataclass(frozen=True) class CorpusEvent:
    event: str; epoch: float; payload: Mapping[str, object]
    claude_pid: int; scenario: str
def replay(events: Iterable[CorpusEvent], store: Store) -> ReplayStats: ...
```

---

### Task 13: Subagent rollup from the transcript

**Objective:** the third tier of the tree — read on demand, for the one session you opened (§7).

**Files/Surfaces:**
- `src/shepherd/engines/claude_code/transcript.py` — `read_subagents(transcript_path)`
- `tests/engines/test_transcript_subagents.py`

**Dependencies:** T1.
**Allowed Scope:** reading `<sessionId>/subagents/agent-*.meta.json`, the matching `.jsonl` first/last
`timestamp`, `<sessionId>/subagents/workflows/wf_*/journal.jsonl`, and `<sessionId>/workflows/wf_*.json`.
**Out-of-Scope Drift:** parsing the main transcript for anything else (M2's classifier); reversing
the project-dir slug (it is lossy — §Project directory slug rule; glob `projects/*/<id>.jsonl` instead).
**Evidence used:** §Project directory layout (the nested trees; a `SubagentStop` path may not exist
— E26); §Subagent transcript and `.meta.json` (`agentType`, `description`, `toolUseId`,
`spawnDepth`, `requestShape`; every entry has `isSidechain:true` and the **parent's** `sessionId`);
§Workflow subagents (`journal.jsonl`: `started` without `result` = running; `wf_<runId>.json`
`workflowProgress[].state`); §`queue-operation` and task-notification entries (**state comes from
the `<status>` tag** — C20, E28); spec correction l.1022 (**44.4 % of entries are neither user nor
assistant — filter by `type`, never by line count** — E25).
**Expected Artifacts:** one merged list of subagents with `type`, `description`, `started_at`,
`last_activity_at`, `state`.
**Required Checks:**
`test_reads_agent_meta_json`, `test_reads_workflow_journal`,
`test_workflow_started_without_result_is_running`,
`test_state_from_task_notification_status` (C20),
`test_unparsed_state_is_unknown_and_counted` (principle 5, E28),
`test_missing_agent_transcript_is_counted_not_raised` (E26),
`test_nested_spawn_depth_2_is_flattened_with_parent`,
`test_tail_filters_by_entry_type` (E25),
`test_locate_transcript_globs_not_slug` (§Project directory slug rule).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — against the copied transcripts in
`docs/probes/2026-09-14-schemas/transcripts/copies/` (real captures, read-only).
**Exit Criteria:** nine pass; no write to any path under `~/.claude`.
**Test Seams:** unit (pure parse over real files).

**Consumes:** `Anomaly` (T1).
**Produces:**
```python
@dataclass(frozen=True) class SubagentRow:
    agent_id: str; agent_type: str; description: str
    started_at: str | None; last_activity_at: str | None
    state: Literal["running", "done", "unknown"]; source: Literal["agent", "workflow"]
def read_subagents(transcript_path: Path) -> tuple[list[SubagentRow], tuple[Anomaly, ...]]: ...
def locate_transcript(projects_root: Path, engine_session_id: str) -> Path | None: ...
```

---

### Task 14: `toolsurface/` — `ToolDef`, registry, `invoke()`, `subscribe()` (D32, D38, D53)

**Objective:** L4, with its **final shape** and a three-line body, so M4 fills it in without
touching a file in `web/` or `cli/`.

**Files/Surfaces:**
- `src/shepherd/toolsurface/types.py` — `ToolDef`, `Audience`, `BlastClass`, `CallerContext`, `ToolResult`
- `src/shepherd/toolsurface/registry.py` — `register`, `validate_schema`, `invoke`
- `src/shepherd/toolsurface/stream.py` — `publish`, `subscribe` (ADR-4)
- `src/shepherd/toolsurface/tools_m1.py` — the five read-only tools
- `tests/toolsurface/test_registry.py`, `tests/toolsurface/test_tools_m1.py`, `tests/toolsurface/test_stream.py`

**Dependencies:** T6, T7b, T11, T13.
**Allowed Scope:** the registry, `invoke()`'s lookup + audience check + handler call, the schema
validation at registration, the event ring with `publish()`/`subscribe()`, and the `ToolDef` set.

**Amended 2026-09-16 (T18 ledger sweep; BLOCKER T14-2, T16-1, T17-1, T17-2).** Revision 6 said
"exactly five `ToolDef`s". The shipped build registers **eleven**, and the number was never the
invariant — the invariant is that every capability is a `ToolDef` behind `invoke()` with a declared
`blast_class` and audience list, so a capability absent from the registry has no surface that can
reach it (D32). The eleven, read off a running `controld`: the six read tools (`fleet_summary`,
`fleet_tree`, `list_projects`, `list_sessions`, `get_session`, `list_subagents`), D38.1's installer
trio (`install_hooks`, `uninstall_hooks`, `inspect_hooks`), and T17's two (`schema_status`,
`engine_version`). `fleet_tree` is §16's ordering (T16-1); the last two are the facts `cli/doctor`
may not reach for itself across the consumer boundary (T17-1, T17-2).

**Two structural points from revision 3:**

- **`publish()` is called by the composition root, never by `signals/`** (ADR-4, F5). `signals/` is
  L2 and this is L4; the revision-2 wording described an upward import that no test covered.
  `StreamEvent` lives in `core/` (T1) so both sides name it downward, and T2's new
  `test_layer_direction_is_downward_only` now catches the general case.
- **The ring and the registry are concurrent state and are guarded** (ADR-7, F8). One
  `threading.Lock` covers append-and-increment on the ring and a subscriber's snapshot; the module
  -global tool registry is **frozen before the server binds**, so it is written by one thread at
  startup and read-only thereafter. `ThreadingHTTPServer` (T15) means every one of these is touched
  from many threads at once.
**Out-of-Scope Drift:** `authorize()`, the audit log, any exporter (`to_sdk_mcp_server`,
`to_stdio_mcp_server`, …) — **all M4** (D38). Any write tool. Any tool not in §11's read list.

**The five M1 tools** (names verbatim from §11, `blast_class=LOCAL_READ`, `audiences` per §11 plus
`HUMAN` from ADR-3):

| Tool | Audiences | Returns |
|---|---|---|
| `fleet_summary()` | MASTER, HUMAN | counts per live state, `needs_you[]`, anomaly counts |
| `list_projects()` | MASTER, HUMAN | workspaces (D22: a project **is** a workspace) |
| `list_sessions(project_id?, state?)` | MASTER, SESSION, HUMAN | session rows |
| `get_session(id)` | MASTER, SESSION, HUMAN | one row + subagent rollup |
| `list_subagents(session_id)` | MASTER, HUMAN | `SubagentRow[]` |

**Evidence used:** §11.0 (`ToolDef` fields; `invoke()`'s body); D53 and §In-process MCP tool
declaration (`create_sdk_mcp_server` passes a schema through **only** when it has a string `type`
**and** a `properties` key — any other dict is mangled into a `{param: python_type}` map with
every key required); spec correction l.1464–1472 (the SDK validates args **before** the handler
while Claude Code's stdio path forwarded a payload missing a required field — so **`invoke()` must
validate**, or the two bindings diverge at M4).
**Expected Artifacts:** a registry that fails at **startup** on a malformed schema, and five tools.
**Required Checks:**
`test_registration_rejects_schema_without_type` (D53),
`test_registration_rejects_schema_without_properties` (D53),
`test_registration_is_startup_failure_not_runtime` (P10),
`test_invoke_validates_arguments_before_handler` (l.1464–1472),
`test_invoke_denies_wrong_audience`,
`test_invoke_returns_generic_error_for_unknown_tool` (§13 Errors — no stack trace, correlation id),
`test_every_tooldef_has_a_blast_class` (it is required, so this is a typecheck + a registry sweep),
`test_m1_tools_are_all_local_read`,
`test_no_authorize_call_exists_yet` (D38 — M1 has no gate; a test asserts the symbol is absent,
so M4's addition is visible in the diff),
`test_response_projects_an_explicit_field_whitelist` (§13 API responses — never a raw row),
`test_subscribe_replays_from_seq`, `test_subscribe_reports_gap_explicitly` (P12),
**`test_stream_ring_is_thread_safe`** (P19 — one publisher thread + 4 subscribers; every subscriber
sees a strictly increasing `seq` prefix),
**`test_registry_is_frozen_after_startup`** (ADR-7 — `register()` raises after `freeze_registry()`),
**`test_fleet_summary_is_correct_on_an_empty_database`** (F16 — zero sessions, zero counts, no
exception; the greenfield first five minutes),
**`test_signals_does_not_import_toolsurface`** (ADR-4/F5, re-asserted here where the temptation is).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/toolsurface/ -q`.
**Exit Criteria:** sixteen pass; `mypy --strict` clean.
**Test Seams:** integration seam (`invoke()` — the seam every consumer crosses).

**Consumes:** `Store` verbs (T6); `fleet_sort_key` (T11); `StreamEvent` (T1 — `core/`, per ADR-4);
`read_subagents` (T13). **Nothing from T7b** — `fleet_summary` reports which sources are live by
reading `app_state["discovery_status"]` through `Store.get_app_state`, which `run_discovery_loop`
writes. Importing `REGISTRY_SCAN_INTERVAL_S` here would fail T7b's one-module assertion exactly as
it would in T18 (r5, BLOCKING 4).
**Produces:**
```python
class Audience(StrEnum): MASTER="master"; SESSION="session"; HUMAN="human"
class BlastClass(StrEnum): LOCAL_READ="local_read"; LOCAL_WRITE="local_write"; LOCAL_DESTRUCTIVE="local_destructive"; EXTERNAL="external"
@dataclass(frozen=True) class ToolDef:
    name: str; description: str; input_schema: Mapping[str, object]
    blast_class: BlastClass; handler: Callable[..., object]; audiences: frozenset[Audience]
@dataclass(frozen=True) class CallerContext: audience: Audience; caller_id: str; correlation_id: str
@dataclass(frozen=True) class ToolResult: ok: bool; data: object; error: str | None
class SchemaInvalid(Exception): ...
def register(tool: ToolDef) -> None: ...             # raises after freeze_registry() (ADR-7)
def freeze_registry() -> None: ...                   # called by the composition root before bind
def invoke(name: str, args: Mapping[str, object], ctx: CallerContext) -> ToolResult: ...
def publish(event: StreamEvent) -> int: ...          # returns seq; called by daemons/, never by signals/
def subscribe(since_seq: int | None, idle_timeout_s: float | None = None) -> Iterator[StreamDelivery]: ...
@dataclass(frozen=True) class StreamDelivery: seq: int; event: StreamEvent
# Corrected 2026-09-16 (BLOCKER T14-1): the seq belongs to the ring, and `core.stream.StreamEvent`
# has no field for one, so the pair is what crosses the seam. `web/sse.py` writes `delivery.seq` as
# the SSE `id:`, which is what makes `Last-Event-ID` resumable rather than approximate (§12).
STREAM_RING_SIZE: int   # 4096
```

---

### Task 15: `web/` — stdlib HTTP, JSON routes through `invoke()`, SSE

**Objective:** the server half of the fleet page: loopback only, origin-checked, no polling.

**Files/Surfaces:**
- `src/shepherd/web/server.py` — `create_server(...)`
- `src/shepherd/web/routes.py` — route table generated from the registry
- `src/shepherd/web/sse.py`
- `tests/web/test_routes.py`, `tests/web/test_sse.py`, `tests/web/test_security.py`

**Dependencies:** T14.
**Allowed Scope:** `http.server`-based stdlib serving; `GET /`, `GET /static/*`, `GET /api/fleet`,
`GET /api/projects`, `GET /api/sessions`, `GET /api/sessions/{id}`, `GET /api/sessions/{id}/subagents`,
`GET /api/events` (SSE).
**Out-of-Scope Drift:** WebSocket (D51 — M3's terminal); any POST (M1 is read-only); binding
anything but `127.0.0.1` (§13: "no config knob to bind wider in v1"); importing `store` or
`signals` (T2 fails the build).
**Evidence used:** §12 Event stream (envelope, `seq`, `Last-Event-ID` gap replay, **no polling
anywhere**); §13 Network (127.0.0.1 only; origin-checked mutations), API responses (explicit field
whitelist, never a raw row), Errors (generic literal + correlation id).
**Expected Artifacts:** a server whose every route body is `invoke(...)`.
**Required Checks:**
`test_every_api_route_calls_invoke` (AST: no route handler touches anything else),
`test_binds_loopback_only`, `test_no_bind_address_configuration_exists` (§13),
`test_origin_is_checked` (asserted on the one non-GET path the server exposes — the SSE
subscription handshake — so M4's POSTs inherit it),
`test_sse_envelope_shape` (§12's exact keys),
`test_sse_seq_monotonic` (P12), `test_sse_replay_from_last_event_id`,
`test_sse_replay_gap_is_explicit`,
`test_error_body_is_generic_with_correlation_id` (§13 Errors),
`test_response_never_contains_a_raw_row` (§13 API responses),
`test_no_polling_endpoint_exists`.
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — an in-process server on an ephemeral loopback port.
**Exit Criteria:** eleven pass; `test_consumer_boundary` green.
**Test Seams:** integration seam (`invoke()`), plus HTTP-level tests for the SSE contract only.

**Consumes:** `invoke`, `subscribe`, `CallerContext`, `Audience.HUMAN` (T14).
**Produces:**
```python
def create_server(host: str, port: int, static_root: Path) -> ThreadingHTTPServer: ...
API_ROUTES: Mapping[str, str]      # path -> tool name
SSE_PATH: str                      # "/api/events"
```

---

### Task 16: The fleet page — plain ES modules, escaping enforced by a test

**Objective:** the visible deliverable, with §13's escaping rule applied from the first line of
frontend code.

**Files/Surfaces:**
- `src/shepherd/web/static/index.html`
- `src/shepherd/web/static/app.js`, `fleet.js`, `sse.js`, `escape.js`
- `tests/web/test_frontend_escaping.py`
- `tests/web/test_frontend_no_build_step.py`

**Dependencies:** T15.
**Allowed Scope:** the workspace → session → subagent tree; state chip (three live states, §16);
`needs_you_reason` shown as the actual ask; subagent rollup with a count when collapsed; live
updates from SSE; **and the empty state** — a first-run page with no sessions shows an explicit
"no sessions discovered yet" panel naming the live discovery sources (`hooks: not installed ·
registry: 0 sessions`), never a blank area (F16, C-10).
**Out-of-Scope Drift:** the 7-bucket palette, stopped-row action buttons, `[why?]`, the Needs-You
rail as a component, the matrix view, xterm.js — **M2/M3/M5**. Any bundler, any `import` from a
CDN, any framework (D51, K8).
**Evidence used:** §12 Page 2 (layout, ordering, "2/5 tasks comes free", subagents as one indented
line each); §16 (ordering uses the three live `state` values); §13 Frontend (**every
interpolation inside `innerHTML`/`outerHTML`/`insertAdjacentHTML` wrapped in
`escapeHtml(String(v))` — no exceptions for "it's just a number" — or static markup filled by
`textContent`; prefer the latter**).

**The escaping rule is enforceable without node.** `test_frontend_escaping.py` scans every
`web/static/*.js` and fails when an assignment to `innerHTML`/`outerHTML` or a call to
`insertAdjacentHTML` has a right-hand side that is **not** a single string literal with no
template substitution and no `+`. The chosen style is static markup + `textContent`, so the
expected number of allowed exceptions is **zero**, which makes the test a hard gate rather than a
judgement call.

**Expected Artifacts:** a page that renders the tree and updates over SSE without a reload.
**Required Checks:**
`test_no_unescaped_interpolation_in_frontend` (the scan above),
`test_escape_html_exists_and_is_used_where_required`,
`test_no_build_step_artifacts` (no `package.json`, no `node_modules`, no `.ts` — K8/D51),
`test_no_remote_script_sources` (every `<script src>` is local),
`test_fleet_ordering` (a Python-side test over `fleet_sort_key`, since ordering is computed
server-side and the page only renders it),
**`test_empty_fleet_payload_renders_an_empty_state`** (F16 — the `/api/fleet` body for an empty
database contains the empty-state fields the page needs; asserted server-side, since there is no
browser on this host).
**Checkpoint Type:** **human_verify** — a human opens the page against a live throwaway session and
confirms the tree, the chip and the live update. *Reason category: manual-verification* — there is
no browser on this host (data-schemas "Not probeable on this host"), so no automated test can
assert rendering.
**Validation Level:** Deterministic for the four static checks; **Manual** for rendering —
checklist: (1) **on a first run with no sessions, the page shows the empty state, not a blank
area**; (2) a session appears without a reload; (3) its state chip changes on a new turn;
(4) `needs_you_reason` shows the actual ask, not "needs attention"; (5) subagents collapse to a
count; (6) a `<script>alert(1)</script>` in a session brief renders as **text**, not as a script
(inject it via a throwaway session's prompt).
**Exit Criteria:** six static tests pass; the manual checklist is signed off in the plan's
progress notes.
**Test Seams:** unit (static scan) + manual E2E.

**Consumes:** `API_ROUTES`, `SSE_PATH` (T15).
**Produces:** `static/` assets; `escapeHtml(v)` in `escape.js`.

---

### Task 17: `cli/` — status, doctor, install-hooks, uninstall-hooks

**Objective:** the second L5 consumer, proving L4 is not a UI-only path, and the surface where the
`HostPlatform` seam's supervision and login-persistence members earn their M1 call sites.

**Files/Surfaces:**
- `src/shepherd/cli/main.py`, `src/shepherd/cli/commands.py`
- `tests/cli/test_commands.py`

**Dependencies:** T9, T14, T3.
**Allowed Scope:** `shepherd status` (via `invoke("fleet_summary")`), `shepherd doctor`,
`shepherd install-hooks`, `shepherd uninstall-hooks`, `shepherd recompute` (**stub that exits 2
with "M2"** — named so its absence is explicit, per D24/§8 Replay).
**Out-of-Scope Drift:** importing `store` or `signals` (T2 fails the build); writing unit files or
flipping linger (M6); any write tool.

**`shepherd doctor` reports** (this is where five of the six `HostPlatform` members are used):

| Line | Source | Constraint surfaced |
|---|---|---|
| host driver + `verified()` | `detect_host()` | G1 — says "unverified" on macOS |
| data/config/runtime dirs | `dirs()` | C3, E22 |
| socket path, budget, mode | `control_socket()` | E19, E20 |
| dispatch command + availability | `control_socket().dispatch_*` | G2 — refuses rather than lying |
| supervision kind + start-limit note | `supervision()` | **C2**, C3, E23, E24 |
| login persistence | `login_persistence()` | §15 linger (read-only) |
| schema version vs expected — **or `database: not created yet (controld has never run)`** | `read_schema_version` | §7 migration rules 1 and 2; **F16** — the first-run line, so a greenfield user sees a state rather than a traceback |
| hook installation state | `inspect_hooks` | **C6** — reports a pre-existing broken entry |
| **discovery sources** — `hooks: not installed · registry: 3 sessions (1 sdk-cli skipped)` | `invoke("fleet_summary")`, which projects `app_state["discovery_status"]` (r5 — never a direct `scan_registry` import: `cli/` may not import `engines/`) | **Decision pressure 5** — a user never guesses why a column is null; the skipped `-p`/SDK count is shown rather than hidden (RD9, principle 5) |
| **engine version + drift-check date** — `engine: 2.1.273 · schemas pinned 2.1.270 · names+enums verified <date>` | `claude --version` + the recorded drift-check result | **G12** — the version drift is stated on every run, not buried in a probe file |
| anomaly counts | `fleet_summary` | **principle 5** |

**Required Checks:**
`test_status_goes_through_invoke`, `test_cli_imports_nothing_below_l4` (T2's test, re-asserted),
`test_doctor_reports_all_twelve_lines`, `test_doctor_reports_discovery_sources` (Decision pressure 5),
`test_doctor_reports_skipped_sdk_cli_count` (RD9, F3),
`test_doctor_reports_engine_version_and_drift_date` (G12, F11),
**`test_doctor_reports_no_database_yet`** (F16 — first run, no data dir, no traceback),
`test_doctor_reports_unverified_host`,
`test_doctor_reports_missing_dispatch_binary`, `test_doctor_reports_start_limit_policy` (C2),
`test_recompute_is_an_explicit_m2_stub`, `test_install_hooks_requires_explicit_settings_path` (K3 —
there is **no default** that points at `~/.claude`).
**Checkpoint Type:** none (AFK).
**Validation Level:** Deterministic — `.venv/bin/pytest tests/cli/ -q`.
**Exit Criteria:** twelve pass; consumer boundary green.
**Test Seams:** integration seam (`invoke()`).

**Consumes:** `invoke`, `CallerContext`, `Audience.HUMAN` (T14); `install_hooks`, `uninstall_hooks`,
`inspect_hooks`, `HookInspection` (T9); `detect_host`, all **six** `HostPlatform` members incl.
`hook_dispatch` (T3); `read_schema_version` (T5). **Nothing from T7b** — `doctor`'s discovery-source
line comes from `invoke("fleet_summary")`, which projects `app_state["discovery_status"]`. *(Found
while fixing BLOCKING 4, r5: revision 2 had `cli/` consuming `scan_registry` from
`engines/claude_code/`, which `test_consumer_boundary` fails outright — `web/ cli/ master/` may not
import `engines`. D38's "every `web/` and `cli/` read is a registered tool" already forbade it; the
`Consumes` block had simply never been checked against T2.)*
**OPEN — routed to the blocker protocol, not resolved here (r5).** Removing `scan_registry` from
this block exposed a larger tension that revision 5 deliberately does **not** settle:
`install_hooks` / `uninstall_hooks` / `inspect_hooks` live in `engines/claude_code/`, and T2's
`test_consumer_boundary` forbids `cli/` from importing `engines`. The read path had a legal route
(`invoke("fleet_summary")`); the **write** commands do not, because M1's `toolsurface/` is
read-only by D38 and ADR-1 says nothing imports `daemons/`. Three candidate resolutions —
(a) `cli/main.py` is itself a thin composition root with a named carve-out in the boundary test,
(b) the installer moves behind a non-tool L4 surface, (c) `install-hooks` becomes the one M1 write
tool — each changes a rule this plan already fixed, and choosing one in an unreviewed revision is
how the last two rounds produced residuals. **Per the blocker protocol §3 this is a decision gap:**
T17's builder writes it into `docs/plans/2026-09-16-m1-BLOCKERS.md` in the four-part form and picks
up the next task, rather than inventing an exemption at the keyboard. T17 is not on any other
task's critical path (only T18 depends on it), so the milestone keeps moving.

**Produces:** `main(argv: list[str]) -> int`; console entry point `shepherd`.

**Dependencies (restated with T7b):** T3, T7b, T9, T14.

---

### Task 18: End-to-end live proof + `controld` wiring

**Objective:** wire the composition root and prove the whole path against a **real** `claude`
process — the one thing fixtures cannot do.

**Files/Surfaces:**
- `src/shepherd/daemons/controld.py` (≤150 lines)
- `src/shepherd/daemons/__main__.py`
- `tests/e2e/test_live_attached_session.py` (marked `@pytest.mark.live`)
- `tests/e2e/conftest.py` — the isolation fixtures

**Dependencies:** T7b, T10, T10b, T12, T15, T16, T17.
**Allowed Scope:** wiring (`controld`: store, fold, registry loop, control-ingest listener, HTTP
server, **publish**, shutdown); the hookless discovery loop; one live end-to-end run; a 3-session
concurrency run (closes G3's live half).

**Out-of-Scope Drift:** any fold rule, store verb, route or host branch appearing in `controld.py`
— the composition root wires and does not decide (ADR-1, 150-line cap); installing a hook into the
real `~/.claude/settings.json`; a live test that asserts a session **count** rather than our own
`sessionId` (the real config dir means the user's sessions are visible — F10); M2's stop-reason
assertions; any tmux invocation without `-L shepherd-e2e`.

**Isolation rules — non-negotiable (K3, K6):**

1. **The live lane uses the user's real `CLAUDE_CONFIG_DIR` and isolates through the working
   directory and `--settings`.** It **cannot** use a throwaway config dir, and this is measured,
   not assumed: `docs/probes/2026-09-16-registry-and-version-drift.md` Finding 3 shows
   `CLAUDE_CONFIG_DIR=<throwaway>` → `Not logged in · Please run /login`, rc=1. **Isolation and
   authentication are mutually exclusive on this host** (A16, E36). Revision 2's rule 1 would have
   failed at the first `claude` call, and the failure would have looked like a Shepherd bug in the
   task that is the sole acceptance evidence for Decision pressure 5, C-1, C-6, C-10 and G3's live
   half.

   **The changed risk posture, stated rather than discovered (F10).** K3 is no longer upheld *by
   construction* in this lane; it is upheld by **guards**, and the guards are therefore
   load-bearing:
   - the P13 sha256 of `~/.claude/settings.json` is asserted **before and after every test**, not
     once per suite, so a violation names the test that caused it;
   - every `claude` invocation passes an explicit `--settings <throwaway>`; no test ever writes to
     the real settings path, and `test_scan_makes_no_writes_under_claude_home` (instrumented
     `open()`) covers the daemon side;
   - trust is accepted in the throwaway working directory the way the 2026-09-14 suite did it (tmux
     `send-keys` against the `shepherd-e2e` socket), never by disabling a permission check;
   - the registry scan will now see the **user's own live sessions** as well as ours, so every
     assertion is scoped to our throwaway session's `sessionId`. **No test asserts a session
     count** — that would fail whenever the user is working.
   - the durable side effects Claude Code itself leaves (a `~/.claude.json` trust entry, a
     transcript under `~/.claude/projects/-tmp-…`) are the same ones the 2026-09-14 suite accepted,
     and are named in the test's docstring.
2. Every `claude` invocation runs in a throwaway `/tmp` directory created by `mktemp -d`.
3. If tmux is used at all, it is `tmux -L shepherd-e2e` on **every single invocation, teardown
   included**, and teardown is `tmux -L shepherd-e2e kill-server` — **never a bare `kill-server`**
   (CLAUDE.md rules 1–3; §18's 2026-09-12 incident). Session names use `_`, never `:` or `.`
   (CLAUDE.md rule 4; spec correction l.2354).
4. The user's `shepherd` socket is never named, never listed, never touched.
5. The whole lane is `@pytest.mark.live` and **excluded from the default run**; CI-equivalent is
   `pytest -m "not live"`.

**Required Checks:**
`test_live_lane_uses_real_config_dir_with_working_dir_isolation` (F10 — the fixture asserts its own
posture: real config dir, throwaway cwd, explicit `--settings`, per-test hash guard armed),
`test_hookless_discovery_sees_running_sessions` (**no hook installed anywhere**; start a throwaway
interactive session in a throwaway working directory, accept trust, assert a `session` row appears
**for that session's `sessionId`** with the right `cwd` → `repo_id`, a `title` from `name`, and a
`state` from `status` — Decision pressure 5's acceptance test; never asserts a count),
`test_live_idle_session_is_not_stopped` (**DP6/F2** — leave a real session idle past 60 s and assert
it reads `needs_you` with the idle reason, never `stopped`, while its pid is alive),
`test_live_exited_session_reaches_stopped_with_ended_at` (**DP7/F6, P17** — exit a real session and
assert the sweep sets `stopped` and `ended_at` *after* the sidecar is gone),
`test_live_session_becomes_visible` (launch `claude -p` in a throwaway repo with our installed
hook; assert a `session` row appears, bound to the right repo, with a `brief` — **the hook path
registers a `-p` run, and must: RD9's `entrypoint` filter is a registry-path predicate only, and
`entrypoint` is not a hook-payload field at all (C8)**),
`test_registry_and_hooks_converge_live` (the same session seen by both sources is one row — P14),
`test_live_session_reaches_stopped`,
`test_live_three_sessions_concurrently` (G3's live half — three throwaway sessions at once; assert
three rows, no cross-contamination of counters),
`test_controld_is_the_only_writer` (D37 — a test asserts `sessiond`'s process opened no DB file,
via `/proc/<pid>/fd`),
`test_sessiond_survives_controld_restart` (restart `controld`; assert the buffer drained, the
handshake re-succeeded, and no session row was lost — T10b),
`test_liveness_survives_controld_restart` (P17 — a session that ended while `controld` was down is
still ended afterwards, because `pid`/`proc_start` are on the row, not in memory — DP7),
`test_daemons_unlink_their_sockets_on_sigterm` (F15 — and a restart binds without `EADDRINUSE`),
`test_controld_closes_the_store_on_shutdown` (ADR-7 — the writer thread is joined),
`test_real_user_settings_untouched` (P13 — asserted **per test**),
`test_no_foreign_tmux_socket_touched` (asserts every tmux argv in the run carries `-L shepherd-e2e`).
**Checkpoint Type:** **human_action** — a human confirms, before the first live run, that
`tmux -L shepherd ls` is untouched and that the throwaway config dir is in place.
*Reason category: external-access* (this is the only task that starts a real `claude` process on
the user's machine).
**Validation Level:** **Live** — see the Live Verification Strategy below.
**Exit Criteria:** fifteen pass; `tmux -L shepherd ls` output is identical before and after; the
real settings file hash is unchanged after **every** test; `controld.py`, `sessiond.py` and
`control_ingest.py` are each ≤150 lines.
**Test Seams:** process seam + E2E.

**Consumes:** everything above, including `serve_control_ingest`, `Relay`, `RelayStats` (T10b);
`freeze_registry`, `publish` (T14); **`run_discovery_loop` (T7b — and nothing else from T7b: it
owns the cadence, the sweep and the join, so importing `liveness_sweep` would run the sweep twice
and importing `REGISTRY_SCAN_INTERVAL_S` would fail T7b's own one-module assertion — r5,
BLOCKING 4)**;
`Store.close` (T6).
**Produces:** `def run_controld(...) -> int`, `def run_sessiond(...) -> int`, console entry points.

**What the composition root wires, explicitly — so nothing lands here by default (ADR-1, ≤150 lines):**
open the store → `migrate` → register the five tools → `freeze_registry()` → start the
control-ingest listener (T10b) → start **`run_discovery_loop`**, which owns the 2.0 s registry
cadence and the liveness sweep (T7b, A8) → for
every `FoldResult` from either source, apply the delta and `publish()` its events (ADR-4) → start
the HTTP server (T15) → on `SIGTERM`: stop the loops, unlink sockets, `Store.close()`. Every line
is a call into a tested module; no branching logic and no fold rules live here.

---

## Verification strategy (critical_path requirement)

How each behavior-contract clause is actually proven, and by which lane. §14's four lanes map onto
M1 as follows.

| Lane (§14) | M1 instance | What it proves | Clauses covered |
|---|---|---|---|
| **1 — Golden fixtures** | T12: the 429 captured events replayed through `parse_hook_payload` → `fold` → `Store`, twice, against a committed expected-state table. **No mocking of Claude Code — the fixtures *are* Claude Code.** | that the fold is right about real data, deterministically | C-2, C-3, C-5 |
| **2 — Contract suites** | T3/T4: **one** `HostPlatform` suite, three implementations (`LinuxHost`, `MacHost`, `ScriptedHost`), per §14.2 and the fourth invariant | that the seam D55 draws is a real interface and not one implementation wearing a Protocol | C-9, C-10 |
| **2b — Isolation/import tests** | T2: **ten** AST tests, each shipping a paired fixture violation proving it *fails* when violated, **plus two negative fixtures** proving the two declared structural exclusions do not widen (F4) | that the boundaries are enforced by the build, not by review — and that they do not fire on the plan's own prescribed code | C-9 |
| **3 — Integration, slow lane** | T18: real `claude` processes in throwaway **working** dirs under the **real** config dir (A16), with per-test hash guards, incl. the hookless-discovery proof | that the installed hook fires, the daemons wire up, and the page is non-empty with no hooks | C-1, C-2, C-6, C-10 |
| **4 — Concurrency** | T12's `_epoch` interleave (synthetic from real events, **pure fold only**) + **T6's threaded writer test and T14's ring test (P18, P19 — the real shared state)** + T18's 3-session live run + T10b's `controld`-restart test | that contention does not corrupt a row and a restart loses nothing silently | C-2, C-4, **C-11** |

**Proof obligations that are *not* discharged at M1, stated rather than implied:**

| Clause | Residual gap | Why it is acceptable at M1 | Where it closes |
|---|---|---|---|
| C-1 | the kill-at-shutdown *mechanism* is inferred (A4) | the decision rests on measured cost + observed loss, not on the mechanism | — (may never close; does not matter) |
| C-3 | `needs_you` clearing is inferred **only where no sidecar is readable** (A9, narrowed at r3) | on every session with a sidecar the `waiting → idle\|busy` transition is an *observed* clearing signal; the residual is `-p`/SDK runs (skipped at M1) and unreadable sidecars, still isolated to one rule row and counted | M2, or the first counter-example capture |
| C-3 | per-event **field** shapes are verified at engine 2.1.270 while the host runs 2.1.273 (G12) | the 33 names and four enums were re-verified byte-identical at 2.1.273 (`drift_check.py`, A17), and C8 keeps the fold field-tolerant — only four fields are on every event | the next drift check, run by Task 1 and by every future engine upgrade |
| C-9, C-10 | macOS entirely (G1) | `verified()` is `False` and every surface says so | M6 |
| C-7 | rendering is manually verified — no browser on this host | the static scan makes the *code* rule mechanical; only the render is manual | M6 / any host with a browser |

**The gate on every task:** its Required Checks must run green **and** the clause(s) it touches
must still hold for every earlier task. `pytest -m "not live"` is the fast lane and must be green
at every commit; `pytest -m live` is run at T18 and before declaring M1 done.

---

## Live Verification Strategy (Task 18)

**Why live is required.** Three M1 claims cannot be proven by fixtures: (1) that our *installed*
hook actually fires inside a real `claude` process, (2) that the dispatcher does not harm it, and
(3) that concurrent sessions do not corrupt each other's counters (G3). §14 lane 3 exists for
exactly this.

**Harness command:**
```sh
.venv/bin/pytest tests/e2e -m live -q
```

**Environment (corrected at revision 3 — F10).** The **user's real `CLAUDE_CONFIG_DIR`**, because
there is no hermetic authenticated `claude` on this host (A16, E36: an isolated config dir has no
credentials and the run dies with `Not logged in`, rc=1). Isolation comes from a `mktemp -d`
working directory per session plus an explicit `--settings <throwaway>` on every invocation,
created and destroyed by `tests/e2e/conftest.py` — which is exactly what the 2026-09-14 probe suite
did, recording that `~/.claude/settings.json`'s sha256 was identical before and after every run.
Model: `claude-haiku-4-5` (cheapest; effort is absent for haiku, which is itself a captured fact —
§Common input fields).

**Blast radius and how it is bounded:** the only durable side effects a live run can have are
(a) writes to `~/.claude.json` trust/bookkeeping entries and a transcript under
`~/.claude/projects/-tmp-…` — which Claude Code does on its own and the 2026-09-14 probe suite
already accepted — and (b) tmux state, bounded by rule 3 above. Both are recorded in the test's
docstring so a reader knows what the run leaves behind. **Because the config dir is the real one,
the sha256 guard is the boundary rather than a backstop** and runs before and after every test.

**Abort conditions:** any of these stops the lane immediately and is a blocker entry —
the real settings hash changed; a `claude` invocation was constructed without `--settings`; a tmux
argv without `-L shepherd-e2e` was constructed; a `claude` process was started outside a `mktemp`
directory; an assertion referenced a session count rather than our own `sessionId`.

**What live does *not* prove:** macOS (G1), browser rendering (no browser on this host), and
`StopFailure` against the real API (only `model_not_found` was ever reachable — §StopFailure).
Those stay gaps.

---

## Dependency graph and the four independent tracks

```
T1 ─┬─> T2 (boundaries)
    ├─> T3 ─> T4                      [track A — host seam]
    ├─> T5 ─> T6 ─> T7 ─> T7b         [track B — persistence · binding · hookless discovery]
    └─────────────> T11 ─> T12        [track C — fold + golden lane]  (needs T6, T7)
T3 ─┬─> T8 ─> T9                      [track D — hook plumbing]
    ├─> T10                            (needs T8)
    └─> T10b                           (needs T1, T3, T5 — the sessiond→controld hop; independent of T10)
T13 (subagent rollup) is independent of everything but T1
T6,T7b,T11,T13 ─> T14 ─> T15 ─> T16
T9,T14,T3      ─> T17
T7b,T10,T10b,T12,T15,T16,T17 ─> T18
```

After T2, tracks A, B, C and D are independent — which is what makes the blocker protocol
workable: a blocker in any one leaves at least two tasks immediately startable.

**T7b is on the critical path for the milestone's whole point.** Track D (the hook plumbing) can
be blocked indefinitely and M1 still ships something visible, because T7b needs no hook installed.
The reverse is not true. If the schedule compresses, T7b lands before T8–T10.

---

## Plan Completeness Gate — self-check before save

1. **Every task has a test that verifies completion** — yes; each task's Required Checks names them.
2. **Every task lists exact file paths** — yes; no task says "the ingest module".
3. **Every task has exit criteria** — yes; each names the command and the condition.
4. **Dependencies are explicit** — yes; task ids, plus the graph above.
5. **Scope drift is named** — yes; every task has an Out-of-Scope Drift line naming the milestone
   the temptation belongs to.
6. **Consumes/Produces verbatim-matched** — checked; see Self-review below.
7. **Validation level stated for every task** — yes (T8 probabilistic with flake policy; T16 and
   T18 carry Manual/Live halves with checklists; T10b deterministic).
8. **Risk matrix complete** — yes, **29 rows** (21 at r2 + 8 added at r3), each mapped to a named test.
9. **No placeholders** — yes; every section holds a decision. The four "absent at M1" packages in
   ADR-1 are deliberate absences, named with their milestone.
10. **Open decisions listed, not hidden in prose** — yes: **none open**; eight Recommended Defaults
    (RD2–RD9; RD1 withdrawn, RD8 overturned and restated) listed explicitly below as unapproved,
    and every one of them also appears in the Plan-vs-spec gaps table or a Decision pressure, so
    none can hide as prose.

**Four added gate items — 11 and 12 at r3 (the reviewer found two claims unassertable), 13 and 14 at r4:**

11. **Every acceptance claim has a mechanism *and an owning task*.** `test_agents_json_is_one_shot_not_a_timer`
    names one (an AST scan with three specific assertions — T7b); acceptance clause 9 asserts **600**
    lines rather than "~600" **and T2 builds `test_no_source_file_exceeds_600_lines`**; acceptance
    clause 10's `evidence` test is **built by T11** and checks the cited section actually exists in
    `data-schemas.md` — it is the only mechanical enforcement of K1 (r4, A6). Revision 3 named both
    tests without giving either an owner.

13. **No acceptance clause contradicts a test the plan builds** (r4, BLOCKING 1). Clause 12's
    `-p` rule is stated as a **registry-path predicate**, which is what C8 makes it; revision 3
    stated it as a global invariant that T12's 50-row replay and T18's live `-p` test both violate.

14. **No boundary test fires on the plan's own prescribed code** — re-checked at r4 for the *field*
    level as well as the module level (BLOCKING 2). The fold table now reads only
    `SIGNAL_FIELD_KEYS`; `raw_kind` is pass-through only; both have paired fixtures.
12. **Every fix that touches a numbered decision or a spec section is a named pressure**, in the
    four-part form: D55's member count (DP2, re-decided), §8's state rules (DP6), §7's `session`
    columns (DP7). None was applied silently.

**Critical-path sections present:** Behavior contract (11 clauses) · Edge-case catalogue (37 rows) ·
Provable properties (22 rows: P1–P21 plus P7b) · Purity boundary map · Verification
strategy. **Grounding sections
present:** Codebase Reality Check · Plan-vs-spec gaps · Assumption ledger · Differences from
agreement.

### Self-review — cross-phase contract drift

**Re-run in full at revision 3**, because revision 3 renamed four symbols and added one task. Every
`Consumes` entry was matched character-by-character against the `Produces` of the task it names.

**The revision-2 failure this scan missed, and why.** Revision 2's self-review asserted "Every
`Consumes` matches a `Produces` verbatim" while **seven types were used in signatures and defined
nowhere** — `SessionSnapshot`, `StreamEvent`, `MalformedPayload`, `HookInspection`,
`DiscoveredRepo`, `RelayStats`, and `FoldDelta` at the site its own note claimed to have fixed. The
scan had checked only the names listed *in* `Consumes`/`Produces` blocks, not the names *used
inside* the signatures in those blocks. Revision 3's scan reads the signatures. A builder would
have hit the first dangling type at T6 and had to invent `SessionSnapshot` — the input to the
fold's purity contract.

**Definition sites, one per symbol (r3):**

| Symbol | Defined at | Consumed by |
|---|---|---|
| `new_ulid`, `SessionState`, `FLEET_STATE_ORDER`, `SignalKind`, `Signal`, `Anomaly` | **T1** | T3, T7, T7b, T11, T12, T13 ✔ |
| **`FoldDelta`, `SessionSnapshot`** | **T1** (`core/fold_types.py`), re-exported by T11 | T6, T7b, T11, T12 ✔ |
| **`StreamEvent`** | **T1** (`core/stream.py`) — moved from "undefined" at r3, and from T11 to L1 by ADR-4 | T11 (`FoldResult`), T7b, T14 ✔ |
| **`MalformedPayload`** | **T1** | T11 ✔ |
| **`Frame`** | **T1** (`core/frames.py`) — moved from T10 at r3 so T10 and T10b are independent | T10, T10b, T18 ✔ |
| `HostDirs`, `SocketPlan`, **`HookDispatchPlan`**, `Supervision`, `Liveness`, `LoginPersistence`, `HostPlatform`, `detect_host` | **T3** | T4, T7b, T8, T10, T10b, T17, T18 ✔ |
| `migrate`, `EXPECTED_SCHEMA_VERSION`, `read_schema_version`, `MigrationRefused` | **T5** | T6, T10b, T17 ✔ |
| `open_store`, `Store` verbs incl. **`snapshot`, `sessions_with_liveness_inputs`, `close`** | **T6** | T7, T7b, T11, T14, T18 ✔ |
| `RepoBinding`, **`DiscoveredRepo`**, `bind_cwd_to_repo`, `normalise_remote_url` | **T7** | T7b, T11 ✔ |
| `RegistryEntry`, `scan_registry`, `agents_json_fallback`, `is_attached_interactive`, `registry_delta`, `liveness_sweep`, `REGISTRY_SCAN_INTERVAL_S`, `IDLE_TO_NEEDS_YOU_S`, `SDK_CLI_ENTRYPOINT` | **T7b** | **internal to T7b only.** `run_discovery_loop` is the **sole** export T18 consumes; T14 and T17 consume **nothing** from T7b and read `app_state["discovery_status"]` instead ✔ *(corrected at r5 — revision 4 carried a checkmark here for a propagation it had not made: T18 still imported `liveness_sweep` and `REGISTRY_SCAN_INTERVAL_S`, which would have run the sweep twice and failed T7b's own one-module assertion. A self-review that ticks a row it did not verify is worse than no row; this one is now verified against both `Consumes` blocks.)* |
| **`HookEntry`, `build_hook_entry`** (renamed from `HookDispatch`/`build_hook_dispatch`), `HOOK_ENTRY_TIMEOUT_S` | **T8** | T9, T10 ✔ |
| `SUBSCRIBED_EVENTS`, `ALL_HOOK_EVENT_NAMES`, `MANAGED_MARKER`, `InstallResult`, **`HookInspection`**, `install_hooks`, `uninstall_hooks`, `inspect_hooks` | **T9** | T17 ✔ |
| `serve_ingest`, `SHUTDOWN_DRAIN_S` | **T10** | T18 ✔ |
| **`Hello`, `encode_frame`, `decode_frame`, `RelayStats`, `Relay`, `serve_control_ingest`, `RELAY_BUFFER_MAX`, `RELAY_BACKOFF_S`** | **T10b** (new) | T18 ✔ |
| `parse_hook_payload`, `FoldResult`, `FoldRule`, `FOLD_RULES`, `fold`, `fleet_sort_key`, `LIVENESS_WINDOW_S` | **T11** | T7b (`FoldResult`), T12, T14 ✔ |
| `CORPUS_ROOT`, `load_corpus`, `CorpusEvent`, `replay` | **T12** | T18 ✔ |
| `SubagentRow`, `read_subagents`, `locate_transcript` | **T13** | T14 ✔ |
| `Audience`, `BlastClass`, `ToolDef`, `CallerContext`, `ToolResult`, `SchemaInvalid`, `register`, **`freeze_registry`**, `invoke`, `publish`, `subscribe`, `STREAM_RING_SIZE` | **T14** | T15, T17, T18 ✔ |
| `create_server`, `API_ROUTES`, `SSE_PATH` | **T15** | T16, T18 ✔ |
| `module_imports`, `string_literals`, `identifiers`, `LAYER_OF`, `CLAUDE_CODE_HOOK_EVENT_NAMES`, `EVIDENCE_FIELD_NAME`, `PLATFORM_PATH_LITERALS`, `PLATFORM_IDENTIFIERS`, `HOST_ONLY_PACKAGE` | **T2** | **no product module** — T2 is a test package. `ALL_HOOK_EVENT_NAMES` (T9) is an independent literal; the shared test reconciles them (r4, A7) ✔ |

**Four renames propagated (r3):** `sun_path_budget` → `socket_path_budget` (T3 → T8, T9, T17);
`SocketPlan.dispatch_*` → `HookDispatchPlan` (T3 → T4, T8, T9, T17); `HookDispatch` → `HookEntry`
and `build_hook_dispatch` → `build_hook_entry` (T8 → T9, T10). Every consuming block was edited in
the same pass; no block names an old spelling.

**Result of revision 3's re-scan: seven dangling types found and given definition sites, four
renames propagated, one new task (T10b) introducing no dangling reference.** Every `Consumes` in
every task now matches a `Produces` verbatim, **and every type named inside a signature has exactly
one definition site.**

**Revision 4's re-scan — three changes to the symbol map, one removal:**

| Change | Definition site | Consumed by |
|---|---|---|
| `SignalKind` gains `TOOL_FAILED`, `TOOL_BATCH_FINISHED`, `STOP_FAILED`, `NOTICE_UNMAPPED` | **T1** | T11's rule table (now keyed on it), T12 ✔ |
| **`SIGNAL_FIELD_KEYS`** (new — the closed neutral key set) | **T1** | T2 (`test_signals_reads_only_neutral_field_keys`), T11 ✔ |
| **`run_discovery_loop`** (new — A8) | **T7b** | T18's wiring line ✔ |
| **`CLAUDE_CODE_HOOK_EVENT_NAMES` removed from T9's `Consumes`** (A7) | stays in **T2**, test-package only | **no product module** — T9 holds its own literal; the shared test reconciles them ✔ |

`FoldRule.kind` changes type from `str` to `SignalKind`; it is defined and consumed only within
T11, so no other block names it. **No new dangling reference; no `Consumes` names a removed
symbol.**

---

## Recommended Defaults (proposed, **explicitly unapproved** — a reviewer may overturn any of these)

| # | Decision | Default taken | Why it is safe to default | Reversal cost |
|---|---|---|---|---|
| ~~RD1~~ | ~~Where the hook dispatch command lives under D55's "exactly five"~~ | **WITHDRAWN at revision 3.** This is no longer a default; it is a **re-decided pressure** (Decision pressure 2): a **sixth seam member**, `hook_dispatch()`, with D55's spec row to be amended five → six. Widening member (2) kept the letter of an anti-growth clause while defeating its purpose and hid the change from every diff. The author of D55 confirmed the reading and authorised the change | — (decided, not defaulted) |
| RD2 | `Audience` needs a value for `web/`/`cli/` | Add `HUMAN` (ADR-3) | §11.0's own consumer table names five consumers; two audience values cannot serve them; D40 already distinguishes a human at a keyboard | one enum member |
| RD3 | Where the SSE stream attaches to L4 | `toolsurface/stream.py::subscribe()` (ADR-4) | §12 requires the stream; D35 requires it to be at L4; there is no other layer it can live in without a private read path | one module move |
| RD4 | Home for daemon entrypoints, `hookd`, `host/`, `testkit/` | ADR-1's layout, `daemons/` as a composition root above L5 | §5.0 does not name them; every alternative either breaks the import test or needs an exemption inside it | a directory move |
| RD5 | Subscribe to `PostToolBatch`, which §8's list omits | Subscribe | It is the **only** event that records a permission refusal or hook block (data-schemas §PostToolBatch); additive, one entry, no risk | one list entry |
| RD6 | `session.work_item_id` / `work_item_ref` columns at M1 with no FK | Create the columns, no foreign key | §7 lists them on `session`; their target table arrives at M5; a FK to a missing table is a runtime error | one migration line |
| RD7 | Registry scan interval, and whether to poll `claude agents --json` | 2.0 s over sidecar **files**; `claude agents --json` is a **one-shot fallback only**, never a timer | a directory read of ~3 small files is cheap; the CLI forks a `claude` process per call (§`claude agents --json`) and omits `tmux`/`procStart`/`nameSource` (E33, G11) | one constant |
| RD8 | Precedence when the registry and the hook path describe the same session | **OVERTURNED at revision 3: recency, not source.** The observation with the newer timestamp wins per field (`statusUpdatedAt` vs `received_at`); source is the tie-break only | source-precedence has no recency term, so a single hook event would freeze a field forever — including after the hook path goes silent, which E8 says is routine — and it suppresses the *captured* `waiting → idle` resolution signal that shrinks A9 | one comparison in the fold |
| RD9 | What the **registry scan** does with the `-p`/SDK sessions that **do** appear in it (proven — probe Finding 1) | **Filter on `entrypoint == "cli"`** *in `scan_registry` only*; `sdk-cli` entries are skipped, **counted**, and reported by `doctor`. **The hook path is untouched: it registers on the first event of any kind, per D47, whatever the entrypoint** | A `-p` run lives seconds; polled at 2 s it would flicker into the fleet page and out again with nothing useful attached. The count keeps the skip visible (principle 5) rather than silent. **This is a rendering choice about a polled source, not a scope rule** — see the scope note below. Reversing it means rendering them, not rediscovering them | one predicate + one counter, in one function |

**Why RD9 cannot be a milestone-wide rule, stated so no later reader widens it (r4, BLOCKING 1).**
`entrypoint` is a **sidecar** field. **It is not on hook payloads**: C8 records that only
`session_id`, `transcript_path`, `cwd` and `hook_event_name` appear on every event, and a grep of
all 429 captured payloads finds `entrypoint` **zero** times. So the filter is registry-only *by
construction*; the hook path could not apply it even if it wanted to.

That is also the right answer on the merits, not merely the available one. **§19's glossary defines
`attached` as "launched outside the platform"** — it is about *who launched the process*, not about
print mode — and D1 draws the same line (`owned` = we own the pty; `attached` = externally
launched). A hand-launched `claude -p` is an `attached` session. §16's scope therefore does not
exclude `-p`, and **no decision pressure is needed**; revision 3's acceptance clause 12 simply
overstated a polled-source predicate as a global invariant.

The corpus settles it empirically too: **53 of the 54 captured scenarios are `claude -p` runs**
(`meta.json` `cmd` arrays), which is why T12's `test_replay_produces_50_session_rows` and T18's
`test_live_session_becomes_visible` both depend on the hook path registering them. Had clause 12
been read as written, those two tests and RD9 would have been in direct contradiction at the
delivery gate.

---

## Milestone acceptance — M1 is done when

1. **With no hooks installed at all**, a session started by hand in any registered repo appears in
   the fleet page **without a reload**, bound to the right repo and workspace — including from
   inside a linked worktree (D48) — with a title and a state (Decision pressure 5).
1b. With hooks installed, the **same** session is one row, richer: `brief`, `tasks_done/total`,
   `active_subagents`, `repos_touched` (P14).
2. Its state moves `running → needs_you → stopped` from real signals, and `needs_you_reason`
   shows the actual ask — from `waitingFor` on the registry path, from
   `PermissionRequest`/`Notification` on the hook path. **An idle live session is never `stopped`**
   (Decision pressure 6), and a session **reaches `stopped` with `ended_at` set after its process
   exits**, including after `controld` has been restarted — which is what the stored
   `pid`/`proc_start` are for (Decision pressure 7, P17).
3. Its subagents appear as a rollup with a count, read from the transcript on demand.
4. The 429-event corpus replays to a committed golden state table, twice, identically.
5. `test_consumer_boundary` and `test_storage_boundary` **fail the build** when violated —
   demonstrated by their paired fixture violations.
6. `HostPlatform` has one contract suite that `LinuxHost`, `MacHost` and `ScriptedHost` all pass,
   and `MacHost.verified()` is `False` and says so in `doctor`.
7. `shepherd install-hooks` / `uninstall-hooks` round-trips a settings file byte-identically, and
   the real `~/.claude/settings.json` sha256 is unchanged across the entire test suite.
8. `hookd` exits 0 in every failure mode, in under 10 ms, with no Python interpreter on the path.
9. `mypy --strict src/` is clean and **no file under `src/shepherd/` exceeds 600 lines**, asserted
   by `test_no_source_file_exceeds_600_lines` (and ≤150 for every file in `daemons/`). *(The `~`
   was removed at revision 3: "approximately 600" cannot be asserted, so it was a claim without a
   mechanism.)* `test_no_platform_branching_outside_host` passes — `/proc` and `systemctl` appear
   **nowhere** in `signals/`, `store/`, `web/` or `cli/` (D55) — and
   `test_layer_direction_is_downward_only` passes, so §5.0's general rule is enforced and not only
   its L5 case (P21).
10. Every assertion about an external shape in the code cites a `data-schemas.md` section (K1) —
    checked by a test that the `FoldRule.evidence` field is non-empty for every rule.
11. No `.key` sidecar is ever opened, and no session is ever marked stopped because a sidecar
    vanished (P15, P16).
12. **The dispatch command has one definition site** and carries `-q0` on Linux (P20, E34); **the
    registry scan does not register a `sdk-cli` entry** — a **registry-path predicate only**, never
    a milestone-wide invariant, because `entrypoint` is not a hook-payload field at all (RD9, E35,
    C8); `controld`'s three concurrent
    producers pass P18 and P19; the `sessiond → controld` hop refuses to relay across a schema
    mismatch and drains in order after a restart (T10b, §7 rule 3); and a first run with no data
    directory, no database and no sessions produces an empty-state page and a `doctor` line rather
    than a traceback (F16).

---

## Amendment log

| Revision | Date | What changed | Sections touched |
|---|---|---|---|
| 1 | 2026-09-16 | Initial plan. | all |
| 2 | 2026-09-16 | **(a)** Folded in `docs/probes/2026-09-16-hookd-latency.md`: the dispatcher is a shell one-liner, not Python, on measured numbers (Decision pressure 1), and the hook command line moves into `HostPlatform` (Decision pressure 2). **(b)** Replaced the corpus description with the measured shape — 429 lines, 0 malformed, 50 sessions, the envelope format, the per-event counts, and the two coverage gaps (G3, G4). **(c)** Added Decision pressure 5 and **Task 7b**: hookless discovery from the live-session registry, re-verified live on this host, which is what stops M1 shipping an empty page under the "do not touch my settings" rule. | Metadata · Agreement Snapshot · Decision pressures 1, 2, 5 · Flows (A0) · Risk matrix (+5 rows) · Gaps (G6 superseded; G9–G11) · Edge cases (E29–E33) · Properties (P14–P16) · Task 7b (new) · Tasks 8, 12, 14, 17, 18 · Dependency graph · Purity map · Recommended Defaults (RD7, RD8) · Self-review · Acceptance |

| 2 (gate pass 1) | 2026-09-16 | Plan-review gate returned FAIL on five missing required sections; added inline: **Codebase Reality Check**, **Plan-vs-spec gaps**, **Assumption ledger** (with `proven_by_code` / `inferred` / `needs_user_confirmation` tags), **Differences from agreement**, **Behavior contract**, and a named **Verification strategy**. No task, dependency or decision changed. | six new sections |
| 2 (gate pass 2) | 2026-09-16 | Two further findings from the gate's own re-audit: **(a)** T7b's dependency list named T11, which reads as a forward reference — corrected to T1, since `FoldDelta` is defined in `core/` and only re-exported by `signals/fold.py`. **(b)** The brief's requirement that "`/proc` and `systemctl` never appear in `signals/`, `store/`, `web/` or `cli/`" had no test — added `test_no_platform_branching_outside_host` (T2, P7b), with `PLATFORM_TOKENS` and a matching risk row and acceptance clause. | T2 · T7b · Properties · Risk matrix · Acceptance |

| **3** | 2026-09-16 | **Resolves the fresh review of revision 2 — 12 blocking, 4 advisory, all accepted, none rejected.** Every finding was checked against the artefact it cited before being applied. **(a) F1** — Task 8's literal dispatch command had lost `-q0`; measured at 253.6 ms vs 3.2 ms (probe Result 1b), *while still delivering*. The literal is deleted; `SocketPlan`/`HostPlatform.hook_dispatch` is the single definition site, with an AST test (P20) and an EOF-timing test enforcing it. **(b) F2 → Decision pressure 6** — `status:"idle"` no longer maps to `stopped`; the mapping splits on `statusUpdatedAt` against §8's own rules, and `stopped` comes only from §8's "observed process exit". **(c) F3** — `-p` sessions are **proven** to register; `entrypoint`, not `kind`, is the discriminator; G9 closes, A13 upgrades, RD9 added. **(d) F4** — both boundary scans became AST-based; `sun_path_budget` renamed; the `evidence` field is one declared structural exclusion with a negative fixture. **(e) F5** — ADR-4's upward import removed (the composition root publishes; `StreamEvent` moves to `core/`), plus a general `test_layer_direction_is_downward_only` (P21). **(f) F6 → Decision pressure 7** — `pid`/`proc_start` become `session` columns so the hookless path can end a session at all. **(g) F7 → Task 10b** — the `sessiond → controld` hop specified and built: socket ownership, NDJSON/base64 frame format, §7 rule 3's schema handshake, bounded buffer, backoff, drain. **(h) F8 → ADR-7** — `controld`'s threading model stated: one writer thread, thread-local readers under WAL, one ring lock, a frozen registry. **(i) F9** — seven dangling types given definition sites; the self-review now reads signatures, not just block headings. **(j) F10** — T18's isolation rewritten around the proven credential constraint, with the changed K3 risk posture stated. **(k) F11** — version drift recorded (G12), the empty `hook-events.json` citation repaired (G13), the drift check owned as a Task 1 step. **(l) F12 → RD8 overturned** — precedence by recency, not source. **(m) Advisory F13–F16** — A8 upgraded to proven, `ux_session_engine_id` partial unique index added with E3 reworded, daemon teardown specified, first-run/empty-state covered end to end. **(n)** Both unassertable acceptance claims given real mechanisms. | Metadata · K3 · Decision pressures 1, 2, 5, **6**, **7** · Flow A0 · Risk matrix · Gaps G9/G10 closed, **G12/G13** · Reality Check · Plan-vs-spec gaps **M13–M15** · Assumption ledger A8, A9, A13, **A16, A17** · Behavior contract **C-11** · Purity map · Properties **P17–P21** · Edge cases **E34–E37** · ADR-4, ADR-5, ADR-6, **ADR-7** · Tasks 1, 2, 3, 4, 5, 6, 7, 7b, 8, 9, 10, **10b**, 11, 14, 16, 17, 18 · Dependency graph · Verification strategy · Live strategy · Completeness gate · Self-review · Recommended Defaults · Acceptance 2, 9, **12** |
| **4** | 2026-09-16 | **Resolves the second fresh review — 2 blocking, 7 advisory, all accepted, none rejected.** Both blocking findings were **internal contradictions**, not evidence errors, and both were verified before amending. **(a) BLOCKING 1** — acceptance clause 12 said "a `-p`/SDK session is never rendered as an attached one" while T18's `test_live_session_becomes_visible` launches `claude -p` and T12's 50-row replay depends on `-p` registration (**53 of 54 captured scenarios are `claude -p` runs**). Decisive evidence: **C8 — `entrypoint` is not a hook-payload field**, confirmed by 0 occurrences across all 429 payloads, so RD9's filter is registry-only *by construction*. Clause 12, RD9 and T7b's `entrypoint` row now say so, and T12/T18 carry the same sentence. **No new decision pressure**: §19 defines `attached` as "launched outside the platform" — about who launched it, not print mode — so §16's scope never excluded `-p`. **(b) BLOCKING 2** — four `SignalKind`s were overloaded by rows with *different* column effects, leaving `Signal.raw_kind` as the only discriminator, which would have put engine event-name literals inside `signals/` and failed T2's own vocabulary test. Fixed structurally: the enum gains `TOOL_FAILED`, `TOOL_BATCH_FINISHED`, `STOP_FAILED`, `NOTICE_UNMAPPED` so `FoldRule.kind: SignalKind` types the table and `applies` disappears; **and every engine field name moves to the normaliser**, projected into `Signal.fields` under a closed `SIGNAL_FIELD_KEYS` set, with `test_signals_reads_only_neutral_field_keys` and `test_signals_never_compares_raw_kind` as §5.0's first field-level enforcement. **(c) A3** — D55's spec row **has landed at six**; every "outstanding" claim restated as applied and gaps row M2 closed. **(d) A4** — the dispatch-command rule is "one **package**", not one file, with `MacHost`'s literal as a clean negative fixture. **(e) A5** — the `waiting → idle\|busy` clearing signal re-cited by **capture pair** (`06-sidecar-permission.json` → `07-sidecar-running.json`, same pid/sessionId, 9.2 s apart, `waitingFor` cleared), with a note that data-schemas does not yet record the sequence. **(f) A6** — `test_no_source_file_exceeds_600_lines` given to T2 and `test_every_fold_rule_cites_an_existing_section` to T11 (**the only mechanical enforcement of K1**); ADR-6's false "does not typecheck" claim corrected. **(g) A7** — `ALL_HOOK_EVENT_NAMES` is a literal in `engines/`, T2's parser an independent second source, reconciled by one test: product code must not read the probe tree at runtime or M6's package breaks. **(h) A8** — `run_discovery_loop` given the 2 s cadence, sweep and shutdown join, in `signals/` not `daemons/`. **(i) A9** — an unrecognised registry `status` keeps the prior state and is counted; the `Literal` was a typecheck, not a runtime guard. | Metadata · DP2, DP5, DP6 · Gaps M2 · Assumption ledger A9 · Properties P20 · **ADR-6 (rewritten)** · Tasks 1, 2, 7b, 9, 11, 12, 18 · RD9 · Acceptance 12 · Completeness gate · Self-review |
| **5** | 2026-09-16 | **FINAL amendment — resolves the amendment verification's 5 blocking + 2 advisory findings. Build starts from this revision.** All five blocking findings were **residuals of revision 4's own restructuring**. **(1)** The fold table conflated two maps (engine event→kind, and kind→effect), so `SESSION_REGISTERED` and `TURN_PROGRESS` each appeared twice with different effects and `test_every_signal_kind_has_exactly_one_rule` was contradicted by the table it polices. **Split into Table A (the normaliser's map — the only place an engine name or field appears) and Table B (one row per `SignalKind`)**, with the three genuinely cross-cutting rules — receiver stamping, register-on-unknown-id, and the `needs_you` clear — lifted out of both, since modelling them as rows is what produced the duplicates. **(2)** The `INPUT_RESOLVED` row keyed on "after a `needs_you`" became **unproducible** when `applies` was deleted: one payload yields one `Signal`, and `parse_hook_payload` has no prior state. The clear moves into the `TOOL_*`/`PROMPT_SUBMITTED`/`SESSION_STOPPED` rows via `delta_fn`'s `prior` argument; `INPUT_RESOLVED` now belongs only to `PermissionDenied`/`ElicitationResult`. **(3)** `new_cwd` was in `SIGNAL_FIELD_KEYS` *and* banned by T11's drift list — and it is literally Claude Code's field (`data-schemas.md:954`), so a neutral key spelled that way defeats the boundary it was added to enforce. Renamed **`next_cwd`**; `source`→`start_source` aligned. **(4)** A8's ownership move never reached T18's `Consumes`, which still imported `liveness_sweep` (double sweep) and `REGISTRY_SCAN_INTERVAL_S` (fails T7b's own one-module assertion) — **and revision 4's self-review carried a checkmark for that propagation**. `run_discovery_loop` is now T18's sole T7b import, T14 and T17 consume nothing from T7b and read `app_state["discovery_status"]`, and the false self-review row is corrected in place with the failure named. **(5)** `RegistryEntry.status` stayed `Literal[...]` beside prose saying the annotation "is a typecheck, not a runtime guard" — so `scan_registry` could not construct an unknown-status entry under `mypy --strict`. Now `str`, checked at the mapping site; `name_source` likewise. **Advisories:** four count drifts fixed (T2 negative fixtures, T8 runtime proofs, gate item 8's risk rows, the gate-item intro), `test_hook_event_names_match_the_doctor_capture` given an owning file in T2, and **T12's coverage list re-derived from the corpus** — it summed to 421/31 against the real 429/32; the gap was `UserPromptSubmit__from_settings_json` (6, a harness label, not a hook name) and `Setup` (3, not 1), with `TeammateIdle`/`WorktreeRemove` noted as **zero-capture**, and the 53-vs-54 scenario counts reconciled (`S09_perm_bypass_echo` has no `events.jsonl`). **Found while fixing (4) and NOT resolved:** `cli/` consuming `install_hooks`/`inspect_hooks` from `engines/` fails `test_consumer_boundary`, and the write commands have no legal path under D38 + ADR-1 — **routed to the blocker protocol as a decision gap with three candidate resolutions, none chosen**, rather than settled in an unreviewed revision. | Metadata · Purity map · Reality Check (corpus) · **ADR-6 / the two fold tables** · `SIGNAL_FIELD_KEYS` · Tasks 2, 7b, 8, 9, 11, 12, 14, 17, 18 · Completeness gate · Self-review |
| **6** | 2026-09-16 | **Rule-text amendment from a code review of the BUILT T1+T2 — scoped to five of T2's rules; nothing else touched.** Three rules were **proven defeated against the shipped scan functions**, not argued. **(1) `test_signals_reads_only_neutral_field_keys`** said "every string-literal **subscript** of `Signal.fields`" — clean-passing evasions: `.get("tool_input")`, a local alias (`f = signal.fields; f["to_model"]`), `{**signal.fields}`, and `"file_path" in signal.fields`. Since `fields` is `Mapping[str, object]` with **every key per-payload optional**, `.get()` is the idiom T11's rule table will actually use, so the r4-BLOCKING-2 boundary would have stayed green while `signals/` read the three exact fields this task names. Restated as a property — *any read of the mapping, by any means, including through a local alias* — with tainting, whole-mapping escapes, and **fail-closed on computed keys**. **(2) `test_no_platform_branching_outside_host`** matched three fixed dotted spellings; defeated by `import sys as s`, `from sys import platform`, `import platform as pf`, `from os import uname`. **Aliases now resolve to their origin before matching, as `module_imports` already does** — the asymmetry (every import-based rule in the same task was already alias-proof) shows this was an oversight. **(3) `test_signals_never_compares_raw_kind`** said "a comparison or a `match` subject"; defeated by `rk = signal.raw_kind; if rk == "Stop"` and by `raw_kind.startswith("Pre")`. Now tracks aliases and forbids **method calls** and membership tests, not just comparisons. **(4)** The `hookd` isolation rule was being read two ways, and the strict reading (*the module imports nothing from `shepherd`*) fires on T8's own `Produces` signature and on the module's own docstring — the shipped clean fixture already opens with a `#` where a docstring belongs. Restated unambiguously as a property of **the generated command string**. **(5)** Every string-literal scan now **exempts docstrings** and **matches at word boundaries**: `"""Stop the selected session."""` in `cli/`, a `Notification`/`Setup` sentence in prose, and `/procedure` were all proven false positives — and five of the 33 event names are ordinary English in a fleet page. **Root cause, recorded because it generalises:** all three defeated rules were **enumerations of AST syntax**; all three are now **properties**, with each rule's positive-fixture set required to include its known evasions. **Confirmed sound and untouched:** `test_consumer_boundary`, `test_storage_boundary`, `test_nothing_imports_daemons`, `test_layer_direction_is_downward_only`, and `LAYER_OF`. | **Task 2 only** (rule text + `Produces`) · Metadata · Amendment log |

**No numbered decision was reversed in any revision.** **Five** have been put under explicit
pressure and re-decided out loud, each in the four-part form: D55's member count (DP2 — raised from
five to six at revision 3, with the author's authority and the spec text proposed, **not applied by
this plan**), D47's source ranking (DP5), §8's illustrative `hookd.py` code block (DP1 — not a
numbered decision at all), **§8's `state` rules** (DP6 — an application to a source §8 never named,
adding no state and reversing no rule), and **§7's `session` table** (DP7 — two nullable columns,
closing the limitation C13 records by name).

**The one spec edit this plan called for has landed.** D55's row at
`docs/specs/orchestrator-platform.md:165` now reads "exactly **six** things … and the hook-side
dispatch command … **Six, raised from five on 2026-09-16**", applied by the decision's author.
Revision 3 deliberately did not make that edit itself — a planner amending the decision log on its
own authority is the failure K7 exists to prevent, even when the amendment has been authorised —
and revision 4 records that it is done. **Plan and decision log now agree; nothing is outstanding.**

---

## Progress notes

### T1 Step 0 — engine drift check (G12, F11)

| field | value |
|---|---|
| date | 2026-09-16 |
| command | `.venv/bin/python docs/probes/drift_check.py` (exit 0) |
| host engine | `2.1.273` (schema corpus captured at `2.1.270`) |
| 33 hook-event names | **all 33 present** in the 2.1.273 binary — none absent |
| `SessionEnd.reason` | UNCHANGED (exact ordered list found) |
| `SessionStart.source` | UNCHANGED (exact ordered list found) |
| `StopFailure.error` | UNCHANGED (exact ordered list found) |
| `Notification.type` | UNCHANGED (exact ordered list found) |
| outcome | **green — no drift.** T11 and T9 may be written against the corpus as captured. |

The probe's third line ("contiguous doctor-style event list present: 0 x") is
informational: the comma-joined list is not stored contiguously in either
binary. The 33 names are each verified individually, and the ordered list T2
asserts against comes from the `claude doctor` capture, not from the binary.

### T1 — assumptions recorded while building (none of them a decision gap)

1. **`FLEET_STATE_ORDER` places `starting` between `running` and `stopped`.** §16
   fixes `needs_you → running → stopped` and that is what the test asserts; the
   table must still be *total* over `SessionState` or a sort key falls off the
   end. A starting session is live but has produced nothing to act on.
2. **`AnomalyKind` members** are derived from the conditions this plan and
   `implementation-constraints.md` actually name (malformed payload, unknown
   event name, unmapped notice, subagent underflow, unknown registry status,
   stop failure, and the five git outcomes of C19/E12/E15). The enum is
   append-only: T7, T7b and T11 add members, they never reuse one.
3. **`SubagentRef` / `TaskRef`** are named in T1's Files/Surfaces but their
   fields are not given anywhere in the plan; they ship as
   `(subagent_id | task_id, label: str | None)` and T11 may widen them.

### T2 — the thirteen boundary tests

All thirteen pass on the T1 skeleton, and each was **also** proved to fail
against a real violation planted in `src/shepherd/` (not only against its
fixture): two planting rounds failed 8 and 5 tests respectively, 13 of 13.
The four negative fixtures (`FoldRule(evidence=…)`, `socket_path_budget`,
`MacHost`'s own `nc`, `fields["ask"]`) are asserted clean inside the same tests.

> **Superseded in part by revision 6.** A code review of this build proved three of these
> thirteen — `test_signals_reads_only_neutral_field_keys`, `test_no_platform_branching_outside_host`
> and `test_signals_never_compares_raw_kind` — **defeatable by one-line idioms**, because the plan
> specified them as syntactic forms rather than properties. **The build faithfully implemented what
> r5 said; r6 changed what it says.** The planting rounds recorded above did not catch it because
> the planted violations used the canonical form each rule named. The rule text above now requires
> each rule's positive fixtures to include its known evasions, and the negative-fixture list grows
> accordingly. Re-implement against the r6 rule text; this paragraph records the state before it.

### T2 (r6 remediation) — the checks were fixed, not just the code they check

Every finding of the adversarial review and the silent-failure hunt was first
reproduced as a failing check, then closed. The theme of all of them was *a check
that reported success without having checked*, so the acceptance evidence is a
**mutation sweep**, not a green run: emptying **any one of the 54 boundary
fixtures** to `X = 1` now fails the boundary suite — 54/54, previously 48/54.

- **A1/A3 — the two field-level rules follow the value, not the syntax.**
  `tests/boundaries/_taint.py` taints `Signal.fields` and `Signal.raw_kind`
  through local aliases and covers subscript, `.get`/`.pop`/`.setdefault`,
  `in`, `**`, `.keys()/.items()/.values()`, iteration, passing the mapping to a
  call, method calls on `raw_kind`, and `RULES[raw_kind]`. Non-literal keys fail
  closed.
- **A2 — platform identifiers resolve to their ORIGIN before matching**
  (`resolved_identifiers`), as `module_imports` always did for imports. The
  origin set gains `os.name`, `platform.machine` and `sysconfig.get_platform`,
  per r6's "consider whether they belong": D55 says nothing else may branch on
  platform, and `os.name` is one of the two commonest ways to do it.
- **A4 — the `hookd` rule asserts the emitted command**, never the generating
  module's imports, and the module is discovered by what it **declares**
  (`build_hook_entry` / `hook_command`), so `git mv` cannot switch the rule off.
  Proven: a leaking `entry_builder.py` is caught under its new name.
- **A5/C5 — docstrings are excluded from every literal scan, tokens match at
  word boundaries, and `bytes` literals are scanned** alongside `str`.
- **B1/B2/B3 — no scan may exempt before it reads.** Every `*_violations`
  function now computes the finding and applies the package exemption to the
  *result*; each test asserts `pytest.raises(FileNotFoundError)` on a missing
  path, and every clean fixture is paired with an assertion that its content is
  on the analysis path.
- **C1/C2 — `new_ulid`.** The injected clock is authoritative and decoded out of
  the id by the test; the wall-clock and injected lanes no longer share state.
  A concurrency test (8 × 20 000) kills the `with _lock:` → `if True:` mutant.
- **C3/C4/C6/C7** — `core/` purity resolves relative imports and narrows the
  escape to `shepherd.core`, scans recursively; the ADR-6 `evidence` exclusion is
  anchored to a bare `ast.Name` resolving to the real `FoldRule`; `Signal.fields`
  is deep-frozen in `__post_init__`.

Suite: 85 passed, 1 skipped, 1 xfailed (from 81/1/1). `mypy --strict src/shepherd`
clean, 30 files. No shipped `host/`, `store/` or `signals/` code needed changing:
no widened rule fires on it.
