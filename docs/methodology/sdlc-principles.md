# SDLC principles and flow

**Status:** draft — Part 1 is extracted, Part 2 is where your opinions go.
**Written:** 2026-09-20
**Source for Part 1:** the cc10x plugin as installed (`/root/src/cc10x-qa`, branch
`feat/qa-route-clean`, commit `6ff8ae4` = PR #91), generalized off its own vocabulary.
**New file. Referenced by nothing.**

---

## TL;DR

- **Part 1** — the method, stated vendor-neutrally: one router, single-purpose agents,
  durable state, and a small number of gates and caps that everything hangs off. 15
  principles, 4 reviewer postures, 9 caps, 14 gates.
- **Part 2** — one section per route (PLAN, BUILD, DEBUG, REVIEW, QA, ORIENT, TRIAGE,
  CODEBASE-HEALTH). Each says what the route does today and what you want it to do.
  PLAN's wants are filled in (visual logical architecture + interface-first design). The
  rest carry candidates marked **undecided** plus an empty slot for your own.

---

# Part 1 — The methodology, generalized

## 1.1 The shape

```
  user request
       │
       ▼
  ┌─────────┐   routes by PRIMARY DELIVERABLE, not keyword
  │ ROUTER  │   owns ALL orchestration state — agents never own it
  └────┬────┘
       │ writes durable state before dispatching anything
       ▼
  workflow artifact (JSON)  +  append-only event log (JSONL)
       │
       ▼
  a task graph of single-purpose agents, each in a FRESH context,
  each handed a structured scaffold — never conversation history
       │
       ▼
  gates between every phase. Nothing advances on prose.
       │
       ▼
  memory finalization — the only step that runs inline, never delegated
```

Three separations do the real work:

| Separation | Rule |
|---|---|
| **Orchestration vs. execution** | Only the router creates, blocks, unblocks or completes work. Agents propose; they never route. |
| **Doing vs. judging** | The agent that wrote the code never certifies it. Advisory routes cannot start write work. The route that measures cannot repair. |
| **State vs. conversation** | Every fact a later step needs lives in a file, not in the transcript. Compaction must cost nothing. |

## 1.2 The fifteen principles

| # | Principle | Mechanism | Why |
|---|---|---|---|
| P1 | **One entry point, route on the deliverable** | A keyword only *nominates* a route; the primary deliverable *decides*. Ties break by fixed priority. | "Fix the alignment while adding dark mode" is a build, not a debug. Keyword routing gets this wrong every time. |
| P2 | **Agreement before execution** | The plan is a contract with an explicit goal, constraints, in/out of scope, and **Open Decisions**. Unresolved decisions block the build outright. | A plan that hides its unknowns converts them into silent implementation choices. |
| P3 | **Fresh context per phase** | Each phase runs in a new agent handed a structured scaffold: objective, inputs, artifacts, checks, exit criteria. Conversation history is never inherited. | Inherited context causes scope pollution and non-reproducible runs. |
| P4 | **Durable state, not recall** | Artifact + event log are written *before* the first child task and re-read after every write. Resume reconstructs from state; the transcript is a hint at best. | Sessions die, context compacts. A workflow that can only continue in one window is not a workflow. |
| P5 | **Separation of powers** | Advisory routes (review, orient, triage, health) may never create code-changing work. QA may never edit product code, and its executor may never edit tests. | A route that can fix what it measures cannot be believed about what it measured. |
| P6 | **Anti-anchoring** | Adversarial reviewers get no author narrative, no prior findings, and no sight of each other. Approved decisions travel as neutral facts, never as "don't flag X". | A reviewer told what to think reports what it was told. |
| P7 | **Evidence over assertion** | `COMPLETION → TRUTH → PROOF`. A pass needs exit codes, commands, expected/actual per scenario. A clean baseline is recorded *before* the build so only new failures count. | "I ran the tests and they passed" is not evidence. Without a baseline you cannot tell a new break from an old one. |
| P8 | **Fail closed** | Missing contract, unparseable output, contradictory verdicts, incomplete evidence → stop. Strictest verdict wins; never average two signals. | Ambiguity resolved optimistically is how bad work ships. |
| P9 | **Every loop is bounded and every bound has an exit** | See §1.4. Each cap names what happens on exhaustion — usually escalate to a human, never "try again". | An unbounded retry polishes a wrong answer. |
| P10 | **Change something before re-dispatch** | Never re-run the same agent, same model, same input. Add the missing context, raise the tier, shrink the scope, or escalate. | Re-running an unchanged failure burns a cycle to reproduce it. |
| P11 | **Ceremony scales with risk; rigor never does** | Trivial work gets a reduced graph. The verifier's proof path is identical either way. A terse imperative ("just add the endpoint") sets the goal, not the method. | Process weight should track blast radius. Proof standards should not. |
| P12 | **Nothing is silently discarded** | Non-blocking findings accumulate in a deferred list and are surfaced once, at the end, for an explicit decision: fix, file, or knowingly accept. | A dropped minor finding is indistinguishable from a finding that was never made. |
| P13 | **Push the checkpoint right** | Stop for humans only on irreversible actions, real scope changes, or input only they can give. Never to narrate or to ask "shall I continue?". | Each unnecessary stop trains the human to stop reading. |
| P14 | **Enforce in code, not in prose** | Deny-lists, blast-radius limits, destructive-op consent, artifact schema, remediation counting — all hooks. A rule that lives only in a prompt is a request. | Proven the hard way: prompt-only isolation was bypassed by a tool nobody thought to guard. |
| P15 | **Compound the knowledge** | Learnings, gotchas and verification results persist after every workflow. Cross a threshold — 3+ failed hypotheses, the same defect in 3+ files, a fix that contradicts a documented assumption — and it becomes a permanent write-up. | Otherwise every session re-learns the same constraint. |

## 1.3 Reviewer taxonomy — four postures

Not all reviewers are the same thing, and the differences are load-bearing.

| Posture | Role | Writes? | Blind to | Can block? |
|---|---|---|---|---|
| **Self-gate** | The author checks its own artifact against a fixed checklist before saving (plan completeness; build self-critique). | yes — its own artifact | nothing | yes — it must fix inline before it may save |
| **Fresh adversarial** | An independent reviewer that has never seen the work being reviewed, judging the *artifact* against the *original request*. | no | prior findings, author narrative | yes — blocking findings halt the chain |
| **Blind parallel pair** | Two read-only reviewers with different lenses on the same diff, dispatched simultaneously, neither seeing the other. Agreement is independent confirmation and raises confidence a tier. | no | each other | yes |
| **Certifier** | The last agent before "done". Runs the scenarios, reconciles the counts, holds revert authority, and validates the *other reviewers'* findings — a finding it cannot confirm at `file:line` is dropped as hallucinated. | no | — | yes, and it outranks an approval |

Concrete roster (cc10x names in brackets):

| Agent | Posture | Notes |
|---|---|---|
| Planner `[planner]` | author + self-gate | The only writer of plans. Returns `NEEDS_CLARIFICATION` rather than assuming. |
| Plan reviewer, fresh mode `[plan-gap-reviewer]` | fresh adversarial | Capped at 2 passes. Never reads the prior findings. |
| Plan reviewer, amendment mode | diff-scoped verifier | Uncapped, does not count against the cap, and **does not close the loop**. Answers two questions only: did every accepted finding land, and did the amendment break anything new. |
| Code reviewer `[code-reviewer]` | blind parallel pair (A) | Two stages: spec compliance, then code quality. Confidence floor 80. |
| Failure hunter `[failure-hunter]` | blind parallel pair (B) | One lens only: silent failures — empty catches, swallowed errors, log-only handlers. |
| Integration verifier `[integration-verifier]` | certifier | Scenario accounting must reconcile. Environment problems are `BLOCKED`, never `FAIL`. |
| Doc syncer `[doc-syncer]` | mechanical | Diff-driven. `SKIPPED` is a passing state. |
| QA trio `[qa-researcher / qa-harness-builder / qa-executor]` | measurement | Builds and runs a test *system*. May not touch product code or tests-to-make-green. |
| Triage / scanner / researcher | advisory | Produce briefs and reports. Never auto-route into write work. |

Two rules that keep the roster honest:

- **Tier floor.** A gating role is never run on the cheapest model. The cheapest tier rubber-stamps. A narrower brief is scope-cheap, never tier-cheap.
- **Zero-finding halt.** Zero findings on a non-trivial change means insufficient depth, not perfect code. Re-scan before reporting clean.

## 1.4 Caps — the actual numbers

| Loop | Cap | On exhaustion |
|---|---|---|
| Fresh plan-review passes | **2** | Escalate to the human. More passes polish a wrong plan. |
| Plan self-gate iterations | **3** | Stop and escalate. Three failed revisions means the premise is wrong, not the wording. |
| Remediation cycles per workflow | **3** | Human checkpoint before a 4th. Enforced independently by a hook that counts the artifact's own history, deliberately one cycle behind so it fires only if the router already missed its stop. |
| TDD green failures on one test | **3** | Fail with the error. Three failures means the approach is wrong, not unlucky. |
| Same build/lint error after fixes | **3** | Fail with error code + file. |
| Failed debug hypotheses | **3** | Trigger external research. Still stuck after research → `BLOCKED`. |
| Hypotheses generated *before* testing any | **3–5** | Fewer than 3 means you anchored on the first plausible one. |
| Confidence floor to report a finding | **80** | Below that it is noise. *Exception:* a security finding under 80 is surfaced as an open question, never silently dropped. |
| Fix waves | **1 per review** | One review → one consolidated fix task → one cycle. Per-finding dispatch rebuilds context N times and trips the circuit breaker on a single review's work. |

Two framing rules:
- **Amendment lanes are uncapped but non-closing.** Verifying that a change landed is not a review pass, and it never ends the loop.
- **Reaching a cap is a stopping point, not a pass.**

## 1.5 Mandatory gates

| Gate | Where | Blocks on |
|---|---|---|
| **Intent readiness** | before plan or build | Intent not context-bounded (needs >5 files to understand → decompose), a criterion contradicting a constraint, or a criterion with no verifiable scenario. |
| **Plan completeness** | before the plan is saved | 10 checks: every task has a test, exact paths, exit criteria, explicit dependencies, named scope drift, verbatim-matched consumes/produces, a validation level, a risk matrix, no TBD, open decisions listed. |
| **Plan review** | after the plan is saved | 3 checks: **feasibility** (does it survive contact with the real repo), **completeness** (every sentence of the request mapped to a plan item), **scope & alignment** (right-sized, faithful, honest about defaults). No "approved with comments" — comments get ignored, fails get fixed. |
| **Plan trust** | before executing any phase | Plan missing, drifted from its recorded anchor, or carrying unresolved open decisions. |
| **Test seam** | at build dispatch | The phase must name the seam it tests at. The builder confirms or *formally disagrees with a rationale* — it may not silently pick another. |
| **TDD red** | inside build | A red must be a *behavioral* failure with the reason recorded verbatim. An import/syntax/collection error is a broken harness, not a red. |
| **Self-critique** | before running any verification | No stubs, no debug logging, no `as any`, every acceptance criterion has code, every scenario has a test. Never run a suite you know will fail on hygiene. |
| **Phase exit** | end of every phase | Contract validates, result persisted, event logged. A failed contract routes to remediation and never advances the cursor. |
| **Failure stop** | anywhere | Any `FAIL`/`BLOCKED` halts the chain until cleared by remediation, research, or a human. |
| **Evidence / scenario accounting** | at certification | Totals must reconcile with the evidence array; every scenario needs explicit expected *and* actual. |
| **Teardown** | QA | A run that leaks containers, databases or cloud resources is not a passing run. Teardown is itself a scenario with evidence. |
| **Memory sync** | workflow end | The workflow cannot reach final state until learnings persisted, and the audit checks the event, not the claim. |
| **Skill precedence** | any conflict | Fixed order: explicit user instruction > project standards > approved plan > domain skills > tool-internal skills > model defaults. Conflicts resolved are recorded. |
| **Destructive consent** | finishing | Push, branch delete and discard are blocked by default and unlocked by a single-use, expiring token written only *after* the human picks that exact option. `reset --hard`, `clean -f`, force-push have no unlock path at all. |

## 1.6 What every workflow must leave behind

1. **Workflow artifact** — intent, phases, per-agent results, evidence, baseline, telemetry, decision history, pending gate.
2. **Event log** — append-only, one line per state change. An artifact mutation without an event is a desync, and a desync breaks the audit trail.
3. **The plan** (if any), with its open decisions resolved or explicitly deferred.
4. **Memory** — learnings, gotchas, verification record.
5. **A permanent write-up** when the knowledge-compounding threshold is crossed.

Rule: **every artifact is read back after it is written.** Write-without-readback is the most common silent failure in the whole method.

## 1.7 Principles this project added

Hard-won here, not in the plugin, and they generalize:

| Principle | Statement |
|---|---|
| **Isolation of the name is not isolation of the effect** | A shadow directory isolates *file writes*. A planted mutation is *code that runs* — a signal, a subprocess, a socket, a reboot is not contained by a directory. Same shape as passing an explicit socket to every command, not just the outer one. |
| **Prove by fixture and predicate, never by execution** | A deliberately-broken example lives as an inert fixture that nothing imports, read as text or parsed as a syntax tree. Never plant a signal, a kill, or a teardown verb into code that will run — not in the repo, not in a shadow, not in a scratch copy. |
| **Mutation-proof the check itself** | A test that has never been observed to fail is not known to work. Clear the bytecode cache before every mutation run: a same-size change landing in the same second re-imports the old bytecode and records a **false survivor** — a hole written down as proof there isn't one. |
| **The runtime net is not a substitute for the rule** | Guards exist and must themselves be proven to bite — using an operation that delivers nothing. A guard against a catastrophe must not be able to cause one. |
| **Assert on the invariant, not the snapshot** | Assert on the thing that is structurally true (the socket, the boundary), not on today's list of names. A check written against a snapshot goes red the next time a human touches the system. |

---

# Part 2 — The routes

Eight routes, mirroring cc10x plus the QA route. For each: what it is today, then
**Wanted** — what should be there. Items marked **[undecided]** are candidates I am
proposing, not decisions you have made.

---

## PLAN

**Deliverable:** an agreement. Nothing is built.
**Chain:** mandatory brainstorm → planner → fresh review (≤2) → revise → memory.
**Produces today:** one markdown plan — metadata, agreement snapshot, per-task objective /
files / dependencies / scope / artifacts / checks / exit criteria / consumes / produces,
risk matrix, flow mapping, inline decision records.

### Wanted

**W1 — every plan produces a visual logical architecture document, not only markdown.**

The plan must ship a *rendered, viewable* diagram of the logical architecture alongside
the markdown. Requirements:

| Aspect | Requirement |
|---|---|
| **Content** | Every logical component as a box. Every communication path as a **labelled** edge — the label says what crosses and how (call, event, stream, poll), not just "talks to". Boundaries drawn explicitly: process, trust, storage, layer. |
| **Per component** | Name, one-sentence responsibility, what it owns, what it depends on, what state it holds. |
| **Fidelity** | The diagram and the markdown are one source of truth. They may not disagree. If a component is in one and not the other, the plan is incomplete. |
| **Format** | Rendered and openable — including on a phone. Committed to the repo, not left in a scratch directory. |
| **Diff** | For a change to an existing system, show the **delta**: what is added, what is removed, which edge moves. A diagram of the whole system with no indication of what this plan changes is decoration. |
| **When** | Produced at plan time, reviewed by the plan reviewer, and amended whenever the plan is amended. |

*Feasibility note:* the mechanism already exists in the plugin — the codebase-health
scanner emits an HTML report with before/after diagrams. Nothing analogous is wired into
PLAN. The architecture skill does describe layered views (context → container →
component) but only as prose, and it is only loaded for work already judged
integration-heavy. This want makes the visual mandatory for **every** plan.

**W2 — the plan decides the interfaces; the build does not.**

For every logical unit the plan must fix the contract *before* anyone writes an
implementation. Per unit:

| Field | Meaning |
|---|---|
| **Operations** | Exact signatures — names, parameters, return types. Verbatim, so later phases match by copy, not by memory. |
| **Data shapes** | The types that cross the boundary, not prose descriptions of them. |
| **Error contract** | Every failure this unit can return, and which are the caller's to handle. |
| **Invariants** | What is always true on entry and on exit. |
| **Ownership** | Which side owns the interface — the caller's need, or the implementer's convenience. (Design it twice: the obvious version usually mirrors the implementation, not the caller.) |
| **Test seam** | Where a test attaches to this unit, and what a usable double/fake looks like. |
| **Durability horizon** | Throwaway / refactor-likely / architectural. This sets how much abstraction the unit earns. |
| **Swap rule** | If two implementations must be alive at once and chosen at runtime → it is a real seam, and it needs a protocol, a scripted double, and a contract suite. If swapping means a new build → a module boundary and an import rule are enough. Do not pay protocol cost for an edit-time swap. |

**Gate to add:** the plan-completeness checklist grows two rows — *every component appears
in both the diagram and the interface table*, and *every interface has operations, errors,
and a seam*. Both blocking.

**[undecided] Further candidates**
- A standing "what would make this plan wrong?" adversarial pass on the key decision, before the plan is finalized rather than after the build discovers it.
- A dependency-order proof: walk the phases and show each prerequisite exists in an earlier one.
- Require the *rejected* architecture, not just the chosen one.

**Your notes:**
>

---

## BUILD

**Deliverable:** working, verified code.
**Chain:** builder → [reviewer ‖ hunter] → verifier → doc-sync → memory. Trivial scope
gets a reduced graph; the verifier's proof path is unchanged.
**Discipline:** red → green → refactor, one phase at a time, clean baseline recorded
first, per-phase base commit so each review sees only that phase's diff.

### Wanted

**[undecided] Candidates**
- **Implementation must match the plan's interface table verbatim.** Today the builder can confirm or disagree about the *seam*; it cannot silently redraw an *interface*. Make interface drift a blocking review finding, not a code-quality note.
- **Diagram drift check.** If a phase adds a component or an edge that is not in the plan's architecture document, that is a scope increase and must escalate.
- **A whole-branch review before done, by default.** It exists but is optional. Per-phase gates structurally cannot catch a phase-6 misuse of a phase-2 seam.
- **Where the mutation-proof discipline (§1.7) attaches** — per phase, per milestone, or on a sampled basis.

**Your notes:**
>

---

## DEBUG

**Deliverable:** a root cause and a repair.
**Chain:** investigator → reviewer → verifier → memory.
**Discipline:** build the repro loop *before* the first hypothesis — a hypothesis without
a red signal is a guess. Capture the failing output while it is still red. Minimize the
repro before theorizing. Generate 3–5 ranked hypotheses before testing any. Explain the
full causal chain with no "somehow" before proposing a fix. Fan out only when the failures
are provably separable *and* touch disjoint files; on fan-in, check for overlapping edits
before verifying.

### Wanted

**[undecided] Candidates**
- **Every root cause answers: why did no existing gate catch this?** The fix is the code change; the outcome is the missing check. Make it a required field.
- **Variant sweep is explicit** — name the dimensions that must keep working (config, platform, data shape, concurrency) and show the fix holds across them.
- **A repro that survives the workflow** — promote the repro loop into a permanent regression test, or state why it cannot be.

**Your notes:**
>

---

## REVIEW

**Deliverable:** a judgement. Advisory only — it may never create code-changing work; it
may only *offer* to start a build.

### Wanted

**[undecided] Candidates**
- **Review against the plan's interfaces and architecture document**, not only the diff. Once PLAN produces both (W1/W2), REVIEW gains a spec surface it does not have today.
- **A review has a declared scope** — diff, module, or whole branch — stated up front, because the three find different classes of defect.
- **Standing lenses beyond code quality**: operability, failure modes, and whether the change is observable in production.

**Your notes:**
>

---

## QA

**Deliverable:** a trustworthy answer to "does this actually work?" — a test *system*, built
and run. Distinct from the build's inner TDD, which tests code as it is written.
**Chain:** research fan-out → feature map → test plan + environment plan → fresh plan
review → preflight (measure, never boot) → harness build → [reviewer ‖ hunter] → execute →
memory.
**Hard rules:** QA never edits product code. The executor never edits tests to turn a run
green. Environment problems are `BLOCKED`, never `FAIL`. A leak on teardown fails the run.
No pass without the report on disk. Bugs are handed to DEBUG as a *hint with its basis*,
never as a verdict about where the bug is.
**Failure vocabulary:** `missing-input` (a human must supply something) | `wrong-guess` (a
prediction the measurement contradicted) | `defect` (the product is wrong — the only class
that may become a bug candidate). A failing check with no class is invalid output.

### Wanted

**[undecided] Candidates**
- **Resolve the draft.** The route still carries placeholders and two recorded gaps: no machine-readable mutation log, and no verifier for a plan amended after the second review pass.
- **The test plan's scenario matrix derives from the plan's flow mapping** — so a flow the plan named cannot be a flow QA forgot to test.
- **Prove the suite can fail** before trusting a green run — the QA analogue of the false-red guard.
- **A standing regression lane**: re-run a saved harness alone, without repeating research and planning. The capability exists; nothing schedules it.

**Your notes:**
>

---

## ORIENT

**Deliverable:** understanding. Read-only, no agents, no task graph. Exists so that "help
me understand this" can never fall through into a route that starts writing code.
**Discipline:** map the modules, trace one layer of callers and dependents, explain in the
project's own vocabulary — not generic abstractions. Stop at understanding.

### Wanted

**[undecided] Candidates**
- **Orientation should read the architecture document first** once PLAN produces one, rather than re-deriving structure from source every time.
- **Cheap upkeep:** when orientation finds the committed architecture document is wrong, say so. It is the only route that routinely reads structure with fresh eyes.

**Your notes:**
>

---

## TRIAGE

**Deliverable:** an agent-ready brief for an incoming issue or PR. Advisory. Categorizes,
verifies the claim, checks for redundancy and prior rejection, assigns a state. Never
writes code, never auto-routes. Category and won't-fix decisions stop for a human.

### Wanted

**[undecided] Candidates**
- **A brief is only "ready" if it carries a repro or an explicit statement that none exists.**
- **Check the compounded knowledge before triaging** — a prior write-up may already answer it.
- **Decide whether this route matters at all here**, given this is currently a single-author project.

**Your notes:**
>

---

## CODEBASE-HEALTH

**Deliverable:** a list of deepening candidates — shallow modules, pass-throughs, semantic
duplicates — with a rendered report. Advisory. A chosen candidate feeds PLAN only on a
fresh request.
**Discipline:** the deletion test (does complexity vanish if this is deleted?) and the
two-adapter rule (a port with one adapter is not a boundary; an ordinary caller or a test
is not an adapter).

### Wanted

**[undecided] Candidates**
- **Run it against the architecture document**, not only the source: the highest-value finding is a component whose real dependencies no longer match its drawn ones.
- **A cadence.** Right now the route exists but nothing ever triggers it.
- **Surface unused seams** — a protocol with one implementation that was never swapped is a cost paid for nothing.

**Your notes:**
>

---

## Cross-route open questions

1. **Where does the architecture document live and who owns it?** One per plan, or one per
   system that each plan amends? The second is more useful and much harder to keep honest.
2. **Does the visual requirement apply to every plan, or above a size threshold?** A
   one-file change producing a box diagram is ceremony (P11) — but a threshold is also the
   crack every skipped diagram slips through.
3. **What is the minimum viable interface spec?** W2's table is the full version. A trivial
   change should not need all eight fields; say which are always required.
4. **Should routes be composable?** Today each is entered fresh. QA→DEBUG and
   HEALTH→PLAN are deliberately manual handoffs, and that manual step is a feature — but
   it is also the step that never happens.
