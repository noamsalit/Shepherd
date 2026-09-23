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
  ticket          from the owner of the outcome — never inferred (§1.11)
       │          serves · user story · success criteria · non-goals
       ▼
  ┌──────────┐   Definition of Ready. A thin ticket is RETURNED
  │  INTAKE  │   with a drafted attempt at the gaps — never interpreted.
  └────┬─────┘
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

## 1.2 The nineteen principles

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
| P16 | **Never assume a shape at a boundary you do not own** | Every external data shape, signal and protocol behaviour is **observed against a live instance** and the capture is committed. Documentation, SDK typings, memory and model priors are hypotheses, not facts. An unprobed shape is a recorded gap, never a detail. See §1.7. | The shape you assume is the one nobody tests. It is wrong silently, and it is wrong at the one boundary where you cannot see inside the other side. |
| P17 | **Sequence is a consequence, not a default** | The plan emits a dependency **graph**, not a list. The executor dispatches on unblock, never on a wave boundary. Independence is tested before two units run together, and re-checked at the join. See §1.9. | Most plans are straight lines only because they were written in order. Every dependency that isn't real is idle time, and it compounds across the whole build. |
| P18 | **Intent is an input, never an inference** | Purpose and deliberate behaviours are supplied **from outside** by the owner of the outcome, held in durable product-level artifacts, and handed to every dispatch. The framework may draft one and may refuse to run without one; it may not author one. Findings resolve to `defect`, `intended`, or **`unspecified`**. See §1.10. | An agent holding the mechanism and no purpose will infer a purpose and be confidently, well-evidencedly wrong. Intended behaviour filed as a defect is the cheap version of this failure; the expensive version is work that does the wrong thing correctly. |
| P19 | **The problem is handed over, not the solution** | Intake receives the problem, the outcome and the constraints. The solution is the framework's to propose. A constraint arrives **with its reason**, so it can be argued with; a design smuggled in as a requirement cannot. See §1.11. | A team that cannot see the problem cannot offer the cheaper answer. It will build the expensive one, faithfully and on time. |

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
| **Intake — Definition of Ready** | before routing | A ticket missing its purpose link, an outcome-bearing user story, verifiable success criteria, or its non-goals. The ticket is **returned with a drafted attempt at the gaps** — never interpreted, never completed by inference. |
| **Purpose of record** | before any route that judges correctness or changes behaviour | No signed purpose record, or a register entry the code now contradicts. An inferred purpose is never a substitute. ORIENT and CODEBASE-HEALTH are exempt — they are read-only, and ORIENT is how the record gets written in the first place. |
| **Intent readiness** | before plan or build | Intent not context-bounded (needs >5 files to understand → decompose), a criterion contradicting a constraint, or a criterion with no verifiable scenario. |
| **Plan completeness** | before the plan is saved | 10 checks: every task has a test, exact paths, exit criteria, explicit dependencies, named scope drift, verbatim-matched consumes/produces, a validation level, a risk matrix, no TBD, open decisions listed. |
| **Plan review** | after the plan is saved | 3 checks: **feasibility** (does it survive contact with the real repo), **completeness** (every sentence of the request mapped to a plan item), **scope & alignment** (right-sized, faithful, honest about defaults). No "approved with comments" — comments get ignored, fails get fixed. |
| **Plan trust** | before executing any phase | Plan missing, drifted from its recorded anchor, or carrying unresolved open decisions. |
| **Test seam** | at build dispatch | The phase must name the seam it tests at. The builder confirms or *formally disagrees with a rationale* — it may not silently pick another. |
| **TDD red** | inside build | A red must be a *behavioral* failure with the reason recorded verbatim. An import/syntax/collection error is a broken harness, not a red. |
| **Independence** | before two units run concurrently | Any one of: coupled understanding, overlapping write sets, shared in-flight state, or a shared machine resource. On failure, serialize or merge the units. Re-checked at the join against the files **actually** edited, not the declared scope. |
| **Boundary evidence** | before an external interface is designed or built | Any external shape, signal or protocol behaviour the work depends on that has no probe: no captured example, or a capture pinned to a version that has since moved. An unprobed shape blocks the phase that consumes it, not the whole plan. |
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
3a. **Any amendment to the purpose record or the decision register** the work produced (§1.10) — signed, with the date and the person.
4. **Memory** — learnings, gotchas, verification record.
5. **A permanent write-up** when the knowledge-compounding threshold is crossed.

Rule: **every artifact is read back after it is written.** Write-without-readback is the most common silent failure in the whole method.

## 1.7 Boundary evidence — never assume a shape you have not observed

**The rule.** Whenever the system talks to something it does not own — a third-party API,
a database, another process, a terminal, a signal, a hook payload, a file format — the
shape and behaviour of that exchange is **established by making the real call against a
live instance and capturing what comes back**. Not from the vendor's documentation, not
from SDK typings, not from memory, not from what a reasonable API *would* look like.

To talk to a database, make real calls against a real instance holding real data, and
watch what actually returns. That is the only way to learn two separate things at once:
**that the call gets through at all**, and **what the response is actually shaped like**.

### What counts as a boundary

Anything you do not compile against and control:

- HTTP/gRPC APIs, webhooks, and callback payloads
- databases and their drivers — wire protocol, driver return types, and server behaviour are three different things
- another program's stdout/stderr, exit codes, and CLI flags
- terminals, ptys, escape sequences, and byte-exact keystroke input
- signals, process lifecycle, and what a runtime does on receiving them
- message queues, event streams, and their ordering and delivery guarantees
- file and serialization formats, including "obvious" ones
- OS-level behaviour that differs by platform — path limits, socket options, credential APIs

### What must be observed, never assumed

| Assume nothing about | Because |
|---|---|
| **Field names and nesting** | The most common and most silent error. A field named in a doc is not a field emitted by a binary. |
| **Types and nullability** | A driver may hand back its own wrapper type, not the primitive the wire carried. |
| **Enum values** | The set is rarely what the docs list, and it grows between versions. |
| **Ordering and pagination** | "Returns a list" says nothing about order, stability, or what an empty page looks like. |
| **Encoding and byte-exactness** | Especially for terminals and signals, where a human-readable transcript is not the bytes. |
| **The error shape** | Usually a completely different schema from the success shape, and usually undocumented. |
| **Timing** | Latency, buffering, and whether a response arrives whole or in pieces. |
| **The empty and the failing case** | A probe that captures only the happy path has documented half a contract. |

### What a probe must produce

A probe is not "I tried it and it worked". It is a committed artifact carrying:

1. **The exact call** — command or request, verbatim and re-runnable.
2. **The pinned environment** — the version of the thing on the other side, the platform, the date. A shape is only true *at a version*.
3. **The raw capture**, committed to the repo — not a summary of it.
4. **A real example value for every field** — a shape stated without a real example is a gap.
5. **An explicit statement of what the probe does NOT cover.** Partial coverage reported as full coverage is worse than no probe.

### Re-probing, doubles, and honesty

- **A capture can be re-probed; a guess cannot.** That is the whole reason to capture. Ship a drift check that re-runs the cheap part of the probe and **exits non-zero** when a name or an enum has moved, and wire it to dependency and version upgrades.
- **Doubles are generated from captures, never hand-written.** A fake built from imagination encodes the very assumption the probe existed to test, and then the suite passes against the assumption.
- **Probe safely.** Use a real instance of the real thing — a local or staging instance first. Against production, read-only and least-privilege, and never a schema experiment against a shared database.
- **Declare coverage honestly.** Say which surface is verified, at which version, and what remains unverified.

### The worked example

This project's own decision D41 exists because of exactly this failure. Shapes for the
engine's hook events had been written into the spec from documentation and memory. Probes
against the live binary found four of them wrong: an `error_type` field that is actually
`error`, an `end_reason` that is `reason`, a `start_reason` that is `source`, and a
documented `stop_reason` that the payload does not contain at all. Every one would have
compiled, and every one would have failed silently at runtime.

The rule that came out of it — *a shape stated without a probe and a real example is a
gap* — is the same rule stated generally above.

## 1.8 Principles this project added

Hard-won here, not in the plugin, and they generalize:

| Principle | Statement |
|---|---|
| **Isolation of the name is not isolation of the effect** | A shadow directory isolates *file writes*. A planted mutation is *code that runs* — a signal, a subprocess, a socket, a reboot is not contained by a directory. Same shape as passing an explicit socket to every command, not just the outer one. |
| **Prove by fixture and predicate, never by execution** | A deliberately-broken example lives as an inert fixture that nothing imports, read as text or parsed as a syntax tree. Never plant a signal, a kill, or a teardown verb into code that will run — not in the repo, not in a shadow, not in a scratch copy. |
| **Mutation-proof the check itself** | A test that has never been observed to fail is not known to work. Clear the bytecode cache before every mutation run: a same-size change landing in the same second re-imports the old bytecode and records a **false survivor** — a hole written down as proof there isn't one. |
| **The runtime net is not a substitute for the rule** | Guards exist and must themselves be proven to bite — using an operation that delivers nothing. A guard against a catastrophe must not be able to cause one. |
| **Assert on the invariant, not the snapshot** | Assert on the thing that is structurally true (the socket, the boundary), not on today's list of names. A check written against a snapshot goes red the next time a human touches the system. |

## 1.9 Parallelism — plan the graph, execute on unblock

**The rule.** Work that is genuinely independent runs at the same time, and a unit starts
the moment **its own** dependencies are satisfied — not when a phase, a wave, or a batch
finishes. Sequencing is a consequence of the dependency graph. It is never the default.

Two distinct failures this prevents, and they are worth naming separately:

| Failure | Shape | Example |
|---|---|---|
| **False serialization** | A, B and C are unrelated but run one after another, because they were *written* one after another. | Three independent modules planned as phases 1, 2, 3. |
| **The barrier** | B depends only on A1, but waits for A2 and A3 too, because they were grouped into one phase. | Screen 1's UI waits on backends 2 and 3 for no reason. Its own backend was ready an hour ago. |

The barrier is the more expensive of the two and the harder to see, because the plan looks
correct: every stated dependency is real. The defect is the *grouping*, not the edges.

### The plan owns the graph

- **Edges are declared at the artifact level.** A dependency means *"I consume something
  you produce"* — nothing else is one. The plan already carries verbatim-matched
  **Consumes / Produces** per unit; that **is** the edge data. Use it to compute the graph
  rather than restating an order by hand.
- **A declared dependency that names no consumed artifact is a false edge — delete it.**
  False edges are the single largest source of accidental serialization, and they are
  invisible because they look like caution.
- **The plan states its critical path and its width** — the longest chain of real
  dependencies, and how many units can run at once. A plan whose critical path equals its
  total length is a straight line: either justify it or re-cut it.
- **Shared resources are edges too.** A port, a fixture database, a migration, a lockfile,
  a single build cache. Model them explicitly, or two lanes will collide on a machine that
  file isolation cannot separate. *Worktrees isolate files, not the host.*

### The executor runs on unblock

- Hold a **runnable set**, not a cursor.
- On **every** completion, recompute what is now unblocked and dispatch it **immediately**.
- **No wave barriers.** A unit never waits on a sibling it does not consume from.
- Cap concurrency to what the machine and the budget support. When more is runnable than
  the cap allows, **prefer the unit on the longest remaining chain** — critical path first,
  because that is the only work that can extend the finish time.

### The independence test

All four must hold before two units run concurrently. This generalizes the test the debug
route already applies to a fan-out.

1. **Separable understanding** — each unit is comprehensible and completable without
   reading the other. If doing A requires knowing B's outcome, they are one unit.
2. **Disjoint write sets** — no file is written by both.
3. **No shared in-flight state** — neither depends on the other's uncommitted output.
4. **No shared machine resource** — port, database, fixture, external account, lockfile.

If any one fails: serialize, or merge them into a single unit. **When in doubt,
serialize.** A wrongly-parallelized pair costs more than a wrongly-serialized one.

### The join

A join **is** a barrier, and that is correct — barriers belong at joins, never inside lanes.

- **Fan-in conflict check** against the files each lane **actually** edited, not what it
  declared. Two write agents that strayed past their scope clobber each other silently.
- **Per-lane baseline and per-lane verify before the join.** This is what buys back
  attribution: with several lanes in flight, a red suite at the end is very hard to
  attribute to a change. Verify each lane against its own baseline first, then run one
  whole-system verification at the join.
- Any conflict → reconcile with a single agent that sees both sides, then re-check. Do not
  verify through a conflict.

### Contract-first parallelism (the stronger version)

With interfaces fixed at plan time (PLAN W2), a consumer does not wait for its producer's
**implementation** — only for its **contract**. The UI lane starts when the interface is
agreed, both sides build against the same contract suite, and integration is the join.

This is strictly more parallel than waiting for the producer, and it is only safe under
conditions:

- The interface is genuinely fixed — designed twice, owned by the caller's need, and
  carrying its error contract and invariants, not just a signature.
- **One shared contract suite** that both sides run. Two private interpretations of one
  interface is not contract-first; it is two guesses.
- If the contract moves, **both** sides rework. So spend this only where the plan is
  confident, and treat a mid-flight contract change as the scope increase it is.
- For an **external** boundary the contract comes from a probe (P16), never from
  imagination. Contract-first against an unprobed third party is a guess with two
  consumers instead of one.

### What parallelism costs

Say it plainly, so the choice is made rather than assumed:

- **Attribution** degrades with width. Per-lane verify is the mitigation, and it is not free.
- **Context and tokens** multiply with lanes.
- **Human checkpoints do not parallelize.** A lane that hits one stops, and a plan that
  puts checkpoints on several lanes serializes itself through the human.
- **Gates do not weaken.** Every lane carries the full gate set. Parallelism changes *when*
  work runs, never *what it must prove*.

---

## 1.10 Purpose and decided behaviour — intent is an input, never an inference

**The failure.** An agent can be entirely right about what the code does and entirely
wrong about whether that is good, because "good" is defined outside the code. Denied the
definition, it infers one from the mechanism — and then produces confident, well-evidenced,
wrong verdicts. The cheap version is deliberate behaviour filed as a defect. The expensive
version is work that does the wrong thing correctly.

**The rule.** Purpose is supplied **from outside the framework**, by the person who owns
the outcome. The framework may refuse to run without it, may draft one for a human to
correct, and may report that it has gone stale. It may never author one, and it may never
proceed on an inferred one.

Two artifacts, both **durable and product-level** — not per change, because the route that
most needs them (testing code that already exists) has no plan to inherit from.

### The purpose record — what this is for

Handed to **every** agent, always, in every route. This is not anchoring: anchoring is
about the *implementation*, and this is about the *goal*. A reviewer that knows the end
game finds better defects, including the class no test catches — *it works, and nobody can
use it*.

It holds:

- who uses this, and what they are trying to accomplish
- what "working" looks like **from outside the system**
- what the product deliberately does **not** try to do
- the vocabulary of the domain, in the user's words rather than the code's

### The decision register — behaviours that are deliberate

Handed only to routes that judge or change behaviour. This one **is** anchoring-adjacent,
so it carries rules:

| Rule | Why |
|---|---|
| **Stated as a fact with its reason, never as an instruction.** "Ctrl-C ends the session, because X" — not "do not flag termination." | An instruction suppresses findings. A fact gets argued with. |
| **Registered before the work.** | A decision produced *in response to* a finding is a rationalization. The ordering is the entire safeguard. |
| **Binds only the behaviour described.** Every entry carries an explicit *does not cover*. | A decision is a point, not an umbrella. The most dangerous defect is the one adjacent to a documented decision. |
| **Challengeable.** A reviewer may answer "intended, and the intent is wrong", or "the decision does not reach this case". | It changes shape; it does not vanish. |
| **No stated user-visible consequence → not a decision, just a preference.** | Forces the author to say what the user actually experiences. |

Entry shape: **id · the behaviour in user-visible terms · the reason · what it does not
cover · the date · who signed it.**

### Three outcomes, not two

The machinery must have somewhere for "surprising and correct" to land, or it will
manufacture defects:

| Outcome | Meaning | Routes to |
|---|---|---|
| `defect` | The product is wrong. | remediation / DEBUG |
| `intended` | Matches a registered decision. Closes, **citing the entry**, and the closure is logged and surfaced at the end so it can be audited. | closed, with provenance |
| **`unspecified`** | Surprising, and **nothing anywhere says what should happen.** | the owner, or PLAN — as a missing decision |

`unspecified` is the valuable one. Most "false positives" of the intended-behaviour kind
are really this: nobody ever decided, so the tester inferred one thing and the implementer
another. The observation was real signal, mislabelled. Routing it as a **missing decision**
turns the framework's most irritating failure mode into its best source of spec gaps.

### Who provides it, and when

| Moment | Who | What happens |
|---|---|---|
| **Adoption — once** | the owner of the outcome | Writes the purpose record. The framework may draft it from a structured interview; the human edits and **signs**. A record with no signature is not a record. |
| **Plan time** | planner **surfaces**, owner **rules** | Any choice with a user-visible consequence is raised as a *candidate* decision. The planner may not rule on it. |
| **Mid-flight** | builder or investigator **stops**, owner **rules** | A fork with a user-visible consequence is a checkpoint (P13), not a judgement call to be made quietly inside a phase. |
| **Continuously** | any route | A register entry the code now contradicts is itself a finding: either the code drifted or the decision did. Someone must say which. |

**The framework drafts; the human signs.** Drafting is not authoring. Without provenance —
who said it, and when — an inferred purpose is laundered into authority, which is precisely
the failure this section exists to prevent.

**Where the gate sits.** Routes that judge correctness (REVIEW, QA, TRIAGE) or change
behaviour (BUILD, DEBUG) do not start without a signed purpose record. Stopping to ask for
one is legitimate under P13 — it is input only the human can give. ORIENT and
CODEBASE-HEALTH are exempt: they are read-only, and ORIENT is how the understanding needed
to write the record gets built.

**The cost, stated honestly.** This puts an authoring burden at the front, on a human, before
anything runs. Three things keep it affordable: it is mostly one-time; it is the
highest-leverage text in the repo; and it can start very small — a paragraph of purpose
plus the decisions you have already made and never wrote down. A project that already keeps
a purpose statement and a numbered decision log is not authoring these, only extracting
them.

---

## 1.11 Intake — the ticket is the handover

P18 says intent is supplied from outside. This is the **form** it arrives in. A rule with
no form is a rule people route around.

### Two scopes, one link

| | Lives in | Changes |
|---|---|---|
| **Product / feature purpose** | the purpose record (§1.10) | rarely |
| **Task purpose** | the ticket | per unit of work |

**The ticket cites the record; it never restates it.** If every ticket re-explains why the
product exists, the record is not doing its job and nobody reads either. But every ticket
must name **which part** of the purpose it serves. That link is the thing that lets a
reviewer ask *"does this serve the goal?"* rather than only *"does this work?"*

### The template — required

| Field | Contains | The rule that makes it real |
|---|---|---|
| **Serves** | which part of the purpose record this advances | A ticket that serves nothing identifiable is a preference, not work. |
| **User story** | who, what they can now do, and what outcome that produces for them | **The *so that* must name an outcome outside the system.** "So that I can use the new button" is a tautology wearing the costume of a reason. |
| **Success criteria** | observable from outside, each one verifiable | If you cannot name how it would be proven, it is not a criterion. This is the Intent Readiness Gate, moved to where it is cheap. |
| **Non-goals** | behaviour deliberately **not** included | Behaviour-level, not work-level. This is where you pre-empt the finding that is correct and not a defect. |
| **Decisions touched** | register entries this relies on or would change | Changing one is a product decision, never an implementation detail discovered mid-build. |

### The template — conditional

| Field | When | Why |
|---|---|---|
| **User-visible consequence** | always, but "none" is allowed | If nothing changes for anyone, say so and justify it. Feeds PLAN W5. |
| **Boundaries** | when external systems are involved | Schedules the probes (P16, PLAN W3) before anyone designs an adapter. |
| **Provenance** | always worth one line | Incident, customer, or hypothesis. A hypothesis labelled as a requirement is how teams build the wrong thing with total confidence. |
| **Who to ask** | always | A named, reachable person. A ticket nobody owns is an unanswerable ticket. |

### What does not belong on a ticket

- **The solution.** A ticket that specifies the implementation has pre-empted PLAN and
  discarded every cheaper option. Where product genuinely does know the answer, it enters
  as a **constraint with its reason** — a constraint can be argued with; a design smuggled
  in as a requirement cannot.
- **Acceptance criteria written as implementation steps.** "Adds a column to the users
  table" is not a criterion. It is a task with a checkbox on it.
- **A link instead of content.** A ticket that is a pointer to a conversation is a
  conversation.
- **An epic with no slice.** Hand over something shippable end to end. Layers are not
  slices, and only slices create width (§1.9).

### The intake gate — return, do not interpret

A ticket that fails Definition of Ready is **returned**. Interpreting a thin ticket is
exactly the inference P18 forbids, performed at the one moment when preventing it is
almost free.

**Returned with a draft.** Rejection carries a real social cost, and a gate that is pure
friction gets switched off in week two. So the framework returns the ticket **with its own
drafted attempt at the missing fields** — *"here is my reading of your success criteria;
confirm or correct."* Draft, never author (§1.10). That is what lets this survive contact
with people.

### Product-to-dev handover — what actually works

| Practice | The rule | What breaks without it |
|---|---|---|
| **Hand over the problem** | Product owns the problem, the outcome and the constraints. Engineering owns the solution. | Engineering cannot propose the cheaper answer it was never shown. |
| **Outcome over output** | State the change in the world, not the artifact to be built. | "Add a progress bar" cannot be evaluated; "reduce abandoned checkouts" can. |
| **Thin vertical slices** | Hand over something shippable end to end. | Layer-shaped handovers cannot be validated until the last layer lands, and they serialize the graph. |
| **Examples beat specifications** | Concrete examples with real data and real values, not prose rules. | A rule is interpretable; an example is testable. Ambiguity survives prose and dies on an example. |
| **Three-way review before commitment** | Product, engineering and test read the ticket **together, before work starts**. Test's question — *"how would I prove this?"* — is what surfaces ambiguity. | **This framework already has the three:** the planner, the fresh plan reviewer, and QA's coverage lens. Running them against the ticket at intake is that conversation, automated. |
| **Ready and Done are different gates** | Ready = it may be started. Done = it may be believed. | Conflating them means work starts on hope and finishes on assertion. |
| **A named person, not a document throw** | Handover is a conversation that begins with a document. | An unanswerable question stops a lane, and the lane guesses. |
| **Decisions outlive the work** | Why beats what, and it goes in the register (§1.10), not in a closed ticket. | The reasoning is lost exactly when someone later asks "why is it like this?" |
| **The loop closes back to product** | Report what was learned and whether the outcome moved. | **Named gap:** today the framework's learnings persist to *engineering* memory. What product needs back — did the outcome move, what did we learn about the user — has no channel at all. |

### Intake anti-patterns

| Anti-pattern | Tell |
|---|---|
| The solution-shaped ticket | It names files, tables or components before anyone planned. |
| The tautological user story | The *so that* restates the *want*. |
| Unmeasurable success criteria | Proving it needs access nobody on the team has. |
| The epic with no slice | Nothing in it could ship on its own. |
| The ticket written after the work | It describes what was built. It is a changelog with a ticket number. |

---

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

**W3 — the plan names every external boundary and schedules its probe.**

Follows from P16 (§1.7). An interface table (W2) for an adapter **cannot be filled in from
documentation** — the shapes on the far side are not the plan's to invent. So:

| Requirement | Detail |
|---|---|
| **Enumerate** | The plan lists every boundary the work crosses: each API, database, external process, terminal, signal, hook, file format. Nothing crosses a boundary that the plan did not name. |
| **Cite or schedule** | Each boundary either cites an existing probe — with its pinned version — or gets a **probe phase scheduled before** the phase that designs the adapter against it. Probe first, design second. |
| **Mark the diagram** | Every edge in W1's architecture document that leaves the system is drawn as a boundary crossing and carries its probe reference. An unprobed external edge is visibly unproven. |
| **Version pin** | The plan records the version each shape was observed at, so a later upgrade has something to invalidate. |
| **Gap, not silence** | Where a boundary genuinely cannot be probed (no access, no instance, vendor-only), that is recorded as an open risk with its blast radius — never quietly assumed. |

**Gate to add:** the plan-completeness checklist grows a third blocking row — *every
external boundary is named, and each one cites a probe or schedules one before its
consuming phase*.

**W4 — the plan is a dependency graph, and it is optimized for width.**

Follows from P17 (§1.9). Planning is not only "what are the steps" — it is "what is the
shortest path through them given everything that can run at once".

| Requirement | Detail |
|---|---|
| **Graph, not list** | Every unit declares what it consumes and what it produces, verbatim. Dependencies are **derived** from those artifacts, not written by hand as an order. |
| **No false edges** | A declared dependency that names no consumed artifact is deleted. "It felt safer after" is not a dependency. |
| **Cut for width** | Decompose deliberately so independent work *is* independent — split by artifact ownership, not by chronology. A unit that produces one thing three others consume should produce it early and alone. |
| **Declare the shape** | The plan states its **critical path** (longest real chain) and its **maximum width** (how many units can run at once). A plan whose critical path equals its full length must justify it. |
| **Model shared resources** | Ports, fixture databases, migrations, lockfiles and external accounts are edges. Unmodelled, they become collisions no file isolation can prevent. |
| **Mark contract-first lanes** | Where a consumer can start from the interface rather than the implementation (§1.9), the plan says so explicitly and names the shared contract suite both sides run. |
| **Checkpoint placement is a design decision** | Human checkpoints do not parallelize. Put them on the critical path where they are unavoidable — not scattered across lanes, where they serialize the whole plan through one person. |

**Gate to add:** the plan-completeness checklist grows a fourth blocking row — *every
dependency names the artifact it consumes, and the plan states its critical path and
width*. The plan reviewer's scope-and-alignment check gains a matching question: **could
any two of these units have run at the same time?**

**W5 — the plan surfaces candidate decisions; it never rules on them.**

Follows from P18 (§1.10). Planning is where most user-visible consequences are chosen, and
it is the point at which they are cheapest to notice and most likely to be decided by
accident.

| Requirement | Detail |
|---|---|
| **Read purpose first** | The purpose record is an input to planning, ahead of the code. A plan that solves the mechanism without the goal is the failure P18 describes, one stage earlier. |
| **Flag every user-visible fork** | Any choice a user would notice is raised explicitly as a **candidate decision** — behaviour, reason, what it would not cover — and the owner rules. The planner may not settle it by picking a default and moving on. |
| **Candidates are Open Decisions** | They land in the plan's Open Decisions, which already block the build. No new machinery needed. |
| **Amend, do not fork** | Ruled decisions are appended to the register with their date and signer, not restated inside the plan where they die with it. |
| **Say what changes for the user** | Every plan states, in the user's vocabulary, what will be different once it is built. A plan whose user-visible consequence is "none" should say so and justify it. |

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

**W1 — execute on unblock, not on phase completion.**

Follows from P17 (§1.9). This is a real change to how BUILD runs, not a tuning knob:
today's model is one cursor, one builder, advance on verify. Replace the cursor with a
**runnable set**.

| Requirement | Detail |
|---|---|
| **Recompute on every completion** | The moment a unit finishes, dispatch everything it unblocked. Do not wait for its siblings. Backend A finishing starts UI A, even while backends B and C are still running. |
| **Lane isolation** | Each concurrent lane gets its own workspace and its own recorded base commit, so its review and verification see only its own diff. |
| **Per-lane baseline and per-lane verify** | Mandatory, not optional. This is what keeps failures attributable once several lanes are in flight. |
| **Independence tested before dispatch** | The four-part test in §1.9. Fail any part → serialize. When in doubt, serialize. |
| **Fan-in conflict check** | At the join, intersect the files each lane **actually** edited. Any overlap → reconcile with one agent that sees both sides, then re-check. Never verify through a conflict. |
| **Critical path first** | When more is runnable than the concurrency cap allows, dispatch the unit on the longest remaining chain. |
| **Full gates per lane** | Every lane runs the whole gate set. Width changes when work happens, never what it must prove. |
| **Escalate on graph drift** | If a unit turns out to depend on something the plan said it did not, that is a scope increase: stop the lane, repair the graph, and say so — do not quietly serialize around it. |

**[undecided] Candidates**
- **Implementation must match the plan's interface table verbatim.** Today the builder can confirm or disagree about the *seam*; it cannot silently redraw an *interface*. Make interface drift a blocking review finding, not a code-quality note.
- **Diagram drift check.** If a phase adds a component or an edge that is not in the plan's architecture document, that is a scope increase and must escalate.
- **Doubles are generated from captures, never hand-written.** A fake built from an assumption makes the suite pass against the assumption. If a test crosses a boundary, name the capture its double came from.
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
- **Check the decision register before repairing anything.** An investigator that does not know a behaviour is deliberate will fix it, competently, and the repair is the regression. A bug report that contradicts a register entry stops and goes back to the owner.
- **Suspect the observation before the system at a boundary.** When a third party behaves impossibly, re-probe the shape before theorizing about the code — a moved field name mimics a logic bug perfectly.
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
- **Review against purpose, not only against the plan.** The defect class no diff review catches is the one where every line is correct and the result is not worth having. A reviewer holding the purpose record can raise it; one holding only the spec cannot.
- **Flag every unprobed external shape as a finding.** A field name read off documentation and typed into code is a defect waiting for runtime, and it is invisible in a diff unless someone is looking for it.
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

**W1 — judge against intent, and report three outcomes.**

Follows from P18 (§1.10). This is the route where the failure actually happened here: the
technical observation was correct and the verdict was wrong, because the end game was
missing.

| Requirement | Detail |
|---|---|
| **Purpose record is a required input** | QA does not start without it. It is the route most exposed, because testing existing code means there is no plan to inherit intent from. |
| **The feature map covers purpose, not only mechanism** | Today it describes what the system does. It must also carry what the feature is *for* and what counts as working from outside — sourced from the record, never inferred from the code under test. |
| **Three outcomes** | Every finding resolves to `defect`, `intended` (citing the register entry) or `unspecified`. A finding with no outcome is invalid output — the same rule the route already applies to its failure classes. |
| **`unspecified` routes to the owner, not to DEBUG** | It is a missing decision, not a bug. Handing it to DEBUG produces a "fix" for behaviour nobody ever specified. |
| **An `intended` closure is logged and surfaced** | Every closure cites its entry and appears in the end-of-run summary. This is the audit trail that stops the register becoming a suppression list. |
| **Register conflicts are findings** | Behaviour that contradicts a registered decision is reported as exactly that, and someone says whether the code drifted or the decision did. |

**[undecided] Candidates**
- **Resolve the draft.** The route still carries placeholders and two recorded gaps: no machine-readable mutation log, and no verifier for a plan amended after the second review pass.
- **The test plan's scenario matrix derives from the plan's flow mapping** — so a flow the plan named cannot be a flow QA forgot to test.
- **Prove the suite can fail** before trusting a green run — the QA analogue of the false-red guard.
- **The harness asserts the observed shape, and a shape change is a finding, not a flake.** QA's preflight already measures rather than asks; extend that to the contract itself, so a third party moving under you surfaces as a `wrong-guess` rather than a mystery red.
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
- **ORIENT is the natural author's-assistant for the purpose record.** It is exempt from the gate precisely so it can run first, and a structured orientation is the cheapest way to draft a record the owner then corrects and signs.
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
- **Triage is the first place "bug or intended?" gets asked** — so the decision register belongs here, and `unspecified` is a legitimate triage state. An issue that is really a missing decision should be routed to the owner, not filed as a defect for someone to argue with later.
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
5. **Who owns re-probing, and on what trigger?** A drift check only helps if something
   runs it. Dependency upgrade, engine upgrade, scheduled, or all three — and which route
   owns the failure when it exits non-zero.
6. **Who retires a decision, and how is the register kept from rotting?** Entries
   accumulate, and a stale one is worse than a missing one — it closes findings on
   behaviour nobody still wants. ORIENT can audit it; only the owner can retire an entry.
7. **Does the return-path to product get built, or stay a known gap?** The framework
   persists learnings to engineering memory and nothing flows back to whoever wrote the
   ticket. Closing it means a product-facing summary per workflow — outcome moved or not,
   what was learned about the user — which nothing currently produces.
