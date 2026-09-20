# Running QA in parallel with BUILD under cc10x

**Status:** protocol defined, not yet run
**Subject under test:** cc10x 12.8.2 + the QA route from PR #91 (`noamsalit:feat/qa-route-clean`, head `6ff8ae4`)
**Target work:** Shepherd M1 (§16 of `docs/specs/orchestrator-platform.md`)
**Author:** Noam Salit + Claude (Opus 5), 2026-09-12

This document is the experiment design. Findings go in `findings.md` alongside
it, written *during* the run, not reconstructed afterwards.

---

## 1. Why this needs a protocol at all

cc10x's router is **one request → one route**. The route table is a priority
list and the lowest matching number wins:

| # | Route | |
|---|---|---|
| 1 | DEBUG | |
| 2 | PLAN | |
| 3 | REVIEW | |
| 4 | ORIENT | |
| **5** | **QA** | ← added by PR #91 |
| 6 | TRIAGE | |
| 7 | CODEBASE-HEALTH | |
| 8 | DEFAULT → BUILD | |

There is no route that runs QA and BUILD together, and no way to ask for one.
Worse, a prompt that mentions both is actively hazardous: "build the ingest
path and write a test plan for it" contains `test plan` (QA, priority 5) and
falls through to BUILD only at priority 8 — **the router sends it to QA**, and
the implementation never gets written.

So parallelism cannot come from a cleverer prompt. It has to come from **two
concurrent sessions**, and the protocol exists to keep them from corrupting each
other.

---

## 2. The hypothesis

> A spec that pins its interfaces before its implementations lets the QA lane
> build a real harness against those interfaces while the BUILD lane is still
> writing the code behind them. Where the interfaces are pinned, the lanes run
> parallel; where they are not, QA serializes behind BUILD.

Shepherd is an unusually fair test of this, because the spec already commits to
six `Protocol` seams (`Runner`, `EngineAdapter`, `MasterRuntime`,
`ModelProvider`, `Credentials`, `WorkItemProvider`), three capability
dataclasses, and — decisively — the `Scripted*` test doubles in §14.2. The QA
lane has something to bind to on day zero.

**The falsifier is the interesting half.** If the QA harness binds to a Protocol
and the BUILD lane's implementation drifts off it, the drift surfaces when the
lanes merge. That is D9's "cheapest second implementation" argument playing out
for real: the QA lane *becomes* the second implementation that proves the seam.
If no drift is ever caught, the parallel lane bought coordination cost and
nothing else, and this methodology should be abandoned.

---

## 3. Expected phase behaviour

The QA route has seven phases. They do not parallelize uniformly:

```
qa-research (fan-out) → qa-plan → plan-gap-reviewer → qa-preflight
  → qa-harness-builder → [code-reviewer ‖ failure-hunter] → qa-executor
```

| Phase | Runs against | Parallel with BUILD? |
|---|---|---|
| `qa-research` | the spec | **yes** |
| `qa-plan` | the spec | **yes** |
| `plan-gap-reviewer` | the QA plan | **yes** |
| `qa-preflight` | the repo as it stands | partial — it will measure an empty `src/` |
| `qa-harness-builder` | the Protocols | **yes, if the hypothesis holds** — this is the phase under test |
| `code-reviewer ‖ failure-hunter` | the harness | yes |
| `qa-executor` | running code | **no** — hard barrier, needs BUILD to have landed |

Predicted result: **6 of 7 phases parallelize, `qa-executor` is the barrier.**
If `qa-harness-builder` also blocks, the hypothesis is false and the honest
finding is that QA-parallel-to-BUILD needs a spec even more interface-first
than this one.

---

## 4. Lane definitions

Both lanes run in `/root/Shepherd`, in **separate Claude Code sessions**,
started after a restart so cc10x is actually loaded.

**Lane B (BUILD)** — owns `src/`, `pyproject.toml`, migrations.
Scope: M1 only. Starts with the §18 hook-payload probe, which is the one
assumption that can force a redesign; if it fails, both lanes stop.

**Lane Q (QA)** — owns `tests/`. Structurally barred from product code: per PR
#91 neither `qa-researcher`, `qa-harness-builder` nor `qa-executor` may edit it,
and `qa-executor` may not edit test code either. **That prohibition is what makes
the parallel lane safe**, and it is enforced by the route rather than by this
protocol — which is the part worth trusting.

### Write-ownership table

| Path | Owner | Collision risk |
|---|---|---|
| `src/**` | Lane B | none — Lane Q is barred |
| `tests/**` | Lane Q | none — Lane B instructed to leave it |
| `pyproject.toml` | **Lane B only** | Lane Q requests deps via findings log, never edits |
| `conftest.py` | Lane Q | low |
| `docs/specs/**` | neither | frozen for the run — see §6 |

---

## 5. Predicted collisions

Two cc10x sessions in one repo share more state than the workflow artifacts
suggest. Ranked by expected damage:

| # | Shared resource | Risk | Mitigation |
|---|---|---|---|
| 1 | `.cc10x/` memory: `activeContext.md`, `progress.md`, `patterns.md` | **high** — single path, both lanes write, last writer wins and silently discards the other lane's context | none available in-tool. **Measure it.** This is the finding most likely to matter to anyone else trying this. |
| 2 | `.cc10x/stop-state.json` | medium | cc10x already anticipates this: the router's failure table says a stop-state hint contradicting task metadata is **discarded**, metadata authoritative. A designed-in defence — worth confirming it actually fires. |
| 3 | `.cc10x/workflows/{uuid}.json` | low | per-workflow UUID, no shared path |
| 4 | `.cc10x/events` log | low | append-only; interleaving is legible |
| 5 | git worktree | low | disjoint paths by §4 |

Collision #1 is the reason this experiment is worth running even if the
hypothesis fails. cc10x's memory layer assumes one session per repo, and nothing
in its documentation says so.

---

## 6. Measurement

Record in `findings.md` as it happens. Reconstructed notes are worthless here.

**Per lane:** wall-clock per phase; gates that fired and whether they were right;
any phase that stalled waiting on the other lane; any hand-holding needed.

**Cross-lane, the things this experiment exists to learn:**

1. **Did the QA harness catch BUILD drifting off a Protocol?** Quote the
   mismatch. This is the primary signal.
2. **Did the memory files lose an update?** Snapshot `.cc10x/*.md` hashes at each
   phase boundary in both lanes; a hash that moves backwards, or content from one
   lane vanishing, is the finding.
3. **Where exactly did Lane Q block on Lane B?** Expected at `qa-executor`. If it
   blocks earlier, say which phase and why.
4. **Did the router ever misroute?** Especially any BUILD prompt that got pulled
   into QA by a stray keyword — §1's hazard.
5. **Cost.** Always-on is ~3,415 tok/session; `cc10x-router` is ~23k on invoke.
   Two lanes pay both. Was the parallelism worth the tokens?

**Spec is frozen during the run.** Both lanes read
`docs/specs/orchestrator-platform.md`; neither edits it. A spec change mid-run
makes the two lanes disagree about the contract, and contract-drift detection is
the thing being measured. Amendments go to `findings.md` and land after.

---

## 7. Honest limits of this experiment

- **n=1, one codebase, one milestone.** M1 is foundation work — daemons, tables,
  discovery. It is more testable than average. A UI-heavy milestone would likely
  parallelize worse.
- **The author of the QA route is running the experiment.** Findings about
  whether the QA route is *good* are not independent. Findings about whether the
  two lanes *collide* are, since that is a property of cc10x's shared state and
  not of the route.
- **No control arm.** M1 is being built once, in parallel. There is no serial
  M1 to compare against, so "was it faster" is not answerable — only "did it
  work, and what broke."
