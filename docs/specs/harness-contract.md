# Bring your own harness — the contract

**Status: deferred, decided in outline.** Nothing here is built. This document
exists so that the decisions taken on 2026-09-21 are not re-argued, and so the
next person to pick this up starts from the shape rather than the blank page.

Anchors already in the platform spec: **D9** (`EngineAdapter` written against
three engines, implemented for one), **D56** (`Runner` is a *terminal* seam,
`EngineAdapter` a *CLI-harness* seam, and a harness-less engine is a third
`session.ownership` value — not a `Runner` driver), **§17** (deferred list),
and **principle 5** (display the unknown, never invent it).

---

## 1. What this is for

Today Shepherd drives Claude Code. Tomorrow it should drive Codex, and after
that it should drive *a harness somebody wrote themselves* — a LangGraph graph,
an SDK loop, a shell script around the Messages API — **without forking this
repository**.

The goal is not "support every harness". It is: *a harness supplies what it
can, and the Fleet page shows everything that was supplied and nothing it was
not.*

*(The unshipped redesign renames the Fleet page **Flock**; this document uses the
shipped name. See `docs/design/ui-decisions.md`.)*

## 2. Decided

### D-H1 — The stop-reason vocabulary stays closed. 7 outward, 20 inward.

`core/stops.py` holds **20 `StopReason` values**; migration 002 has a `CHECK`
listing exactly those. They are **not** a UI vocabulary — the UI shows 7
buckets plus unknown. The two lists do different jobs:

* the **7 buckets** answer *how worried should I be?*
* the **20 reasons** answer *what do I do about it?* — `DEFAULT_ACTIONS` in
  `signals/stop_rules.py` is keyed on the **reason**, not the bucket, because
  `rate_limited` ("wait, it comes back") and `quota_paused` ("top up or switch
  account") land in the same bucket and need different advice.

The vocabulary stays **closed**, for a reason stronger than tidiness: D25 makes
the stop log truth for 90 days *across rule changes*, and the 20→7 mapping **is
a rule**. Store only the 7 and you have stored today's conclusion and discarded
the evidence — history can never be re-bucketed. Store the 20 and a better
mapping can be replayed over everything already on disk.

**But a third-party harness is not asked to learn 20.** It maps straight to a
**bucket** — the 7 — and leaves the reason unmapped. Simplicity where it is
needed; resolution where it is needed. Rejected: collapsing the 20 to 7.

*Honest trim, if the list is ever shortened:* `crashed`, `killed` and
`derailed` are unreachable in the current build (G-M2-2, G-M2-4, G-M2-6).
Those three are the real cleanup target. Collapsing to 7 is not.

### D-H2 — Out of process. Configuration points at an executable.

An in-process Python adapter means a third party forks or vendors into this
repo, which is not "bring your own" in any useful sense. Instead: configuration
names an **executable** — a binary, a `.py`, a `.js`, anything — which Shepherd
runs and talks a **versioned protocol** to. No fork, no PR, no Python.

**Unresolved and load-bearing (see §4):** this means Shepherd executes
third-party code on the user's machine under the user's credentials. That is a
security surface to be designed deliberately, once, before anything ships.

### D-H3 — `unknown` is a fall-through, never a target.

`unknown` is not offered to an adapter author and must not appear in the
contract's menu. A harness maps the signals it has; **anything unmapped falls
through to unknown on our side.**

Two unknowns exist and stay distinct, because they are different failures and
only the first is the harness's fault:

| | meaning | whose fault |
|---|---|---|
| `StopReason.UNKNOWN` | it reported something we could not place | the mapping's |
| `Bucket.UNCLASSIFIED` | nothing was ever reported | ours, or the wire's |

Both render grey. Telemetry must be able to tell them apart.

**Always store the harness's own raw string alongside.** An unmapped signal is
then a lead, not a shrug — and it is what tells you which mapping to add next.

### D-H4 — Normalisation lives on our side of the seam.

The boundary that turns a harness's vocabulary into ours belongs to Shepherd,
so a harness stays ignorant of Shepherd's internal types. This is the
decoupling the whole feature is for.

### D-H5 — Every stop reason gets an engine-neutral description, on the enum.

Spec §8 documents each reason by its **detection rule** in Claude Code's own
hook vocabulary (`context_exhausted` = "`PreCompact{auto}` with no
`PostCompact` before death"). That is the wrong half of the information for a
harness author, who has no `PreCompact`.

Each `StopReason` gets a docstring stating **what it means**, in words no
engine owns: *"the context window filled before the work was done — not a
failure, the session simply ran out of room."* The Claude-specific detection
rule stays in the Claude adapter. Putting a hook name in the shared enum would
leak one engine into the contract for all of them.

Three reasons must say plainly that nothing currently produces them
(`crashed`, `killed`, `derailed`), and `unknown` needs the most careful wording
of all, because every partial harness will lean on it.

## 3. Proposed shape: capability tiers

Each tier is independently claimable, and maps to exactly what the Fleet page
can then render. A harness claiming 0–2 is useful; one claiming 0–3 is most of
the product.

| Tier | The harness supplies | What lights up |
|---|---|---|
| 0 Identity | session id, project, title, last-activity time | appears on the fleet page; grey card; relative time |
| 1 Liveness | running vs stopped | the running/stopped split; liveness demotion |
| 2 Verdict | a termination mapped to a bucket | the colours, the why line, the stop log, replay |
| 3 The ask | a pending decision: the verbatim prompt and its choices | `needs you`, the rail, the in-session decision card |
| 4 Control | accept an answer, interrupt, resume | live buttons instead of read-only |
| 5 Narrative | turn-level events, subagent rollup | the conversation view, the subagent panel |

Degradation is already free: `StopReason.UNKNOWN` and `Bucket.UNCLASSIFIED`
exist, so a Tier-0 harness renders as honest grey rather than breaking
anything.

## 4. Open — not yet discussed, and needed before this can be built

1. **The wire protocol itself.** Transport, framing, and versioning are
   undecided. Version it the way the stop record is versioned: a reader meeting
   a version it does not know skips and counts, never parses optimistically.
2. **Security.** Shepherd would execute third-party code under the user's
   credentials. Sandboxing, declared capabilities, and what a harness may reach
   are undesigned. This is the one that can sink the feature.
3. **Tier 4 is bidirectional.** Tiers 0–3 are a harness *reporting*. Tier 4 is
   Shepherd *commanding*. That is a different protocol shape and was not
   discussed.
4. **Lifecycle.** Does Shepherd spawn the harness process, or does a running
   harness register itself? Both have been assumed at different moments above.
5. **Identity.** How a third-party session gets a `session_id` that survives a
   restart, and how it avoids colliding with a discovered Claude Code session.
6. **Conformance is proved, not claimed.** A capability declared but not
   honoured is worse than one never claimed. There should be a conformance
   suite an adapter runs, in the shape of the one-suite-every-driver-passes
   rule already stated for `EngineAdapter` and `MasterRuntime`.

## 5. Why it is deferred

Every engine worth driving today ships a CLI, so `EngineAdapter` covers the
near term. The basics of the product come first. This document is the promise
that the decisions above survive until then.
