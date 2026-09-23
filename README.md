# Shepherd

One local platform that makes a fleet of coding-agent sessions legible and
directable. You run several `claude` sessions across several repos; Shepherd
tells you which one needs you, why the others stopped, and what to do about it —
and gives an orchestrator agent the same view, through the same gate you use.

It is a **consumer of Claude Code**, not a fork of it and not a part of it. It
keeps its state in its own directories and never writes inside `~/.claude`
except the one marked, reversible hook block it installs and can remove.

## Status

**M1–M4 of seven slices are built, verified and QA'd**, plus the Projects
backend and the dark-only UI redesign on top of them (2026-09-22). M4.5
(connectors), M5 (queues) and M6 (packaging and ship) are not started.

Measured on 2026-09-23 with `pytest -p no:randomly` — a **named ordering**, because the
default run is currently order-dependent (see below):

| | |
|---|---|
| suite | 2,185 passed, 2 skipped · **39 failed, 60 errors** — all in the browser lane, see the note |
| live lane (`pytest -m live`) | 75 passed **as last measured on 2026-09-21** — not re-run since; it starts real `claude` processes against the developer's own config |
| import-boundary rules | 105 |
| `mypy --strict src` | clean over **131** files, `disallow_any_explicit` on |
| verified hosts | **Linux only.** `MacHost` is written and reports `verified() == False` |

**The suite is not currently green, and the failures are in the harness rather than the
product.** Every one of the 99 is a browser-driven test failing with *"Playwright Sync API
inside the asyncio loop"* or *"asyncio.run() cannot be called when another asyncio event loop
is running"* — some earlier test leaves a running event loop in the main thread and everything
downstream of it falls over. `pytest-randomly` is installed, so which tests are downstream
changes per run. It is written up, with the measurements and the first real clue, as **W7.1**
in the forward-work register. **No product defect has been shown** — the failures are all in
fixture setup, not in assertions about the pages — but that is not the same as the product
being proved fine, and the register says so rather than rounding it off.

There is no installer yet, and **the browser UI has never been opened by a
human.** That gap is narrower than it was: a purpose-built QA harness
(`tests/qa5/`) drives all six pages through a real headless Chromium across 35
scenarios, so the pages demonstrably render. Whether they are *usable* is a
different question and nothing here answers it — `HANDOFF.md` carries the
seven-item manual checklist that does.

## What it does

1. **Visibility** — projects → sessions → subagents, ordered by urgency.
2. **Signals** — when a session stopped, *why* it stopped, and what to do about
   it. Mechanical stop reasons at confidence 1.0; heuristics above that;
   `unknown` is counted and displayed rather than hidden.
3. **Coordination** — sessions message and spawn each other through one mailbox.
4. **Queues** — prioritized work from Jira and Notion, drained by workers *(M5)*.
5. **Control** — a chat-first orchestrator that sees and drives all of it,
   reaching the system only through the tool surface every other caller uses.

### Three tiers

| Tier | What it is | Visibility |
|---|---|---|
| **Master** | one long-lived orchestrator | the chat page |
| **Session** | one real `claude` process per task, own pty, own transcript | full — terminal fidelity, drillable |
| **Subagent** | dispatched *inside* a session by its own skills | a rollup: count, task, state |

The subagent rollup is **intended**. Subagents are implementation details of a
plan the session above them is executing.

## Running it

Python 3.12+. Linux is the verified host; macOS is expected to work and has
never been run.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .

.venv/bin/shepherd doctor          # start here — engine, schema, database, discovery
.venv/bin/shepherd status
.venv/bin/shepherd-controld --port 8787
```

Then open `http://127.0.0.1:8787/`. One document, six page roots, one nav:
**Shepherd** (the orchestrator chat, and the landing page), **Flock**,
**Projects**, **Queues**, **Kanban** and **Settings**. Queues and Kanban are
placeholders. Exactly one root is visible at a time — that exclusivity is
asserted on arrival and after every nav click, not assumed.

Loopback only, in every deployment shape, with no knob to bind wider. Reaching
it from elsewhere is an SSH tunnel, not a configuration flag — see §13.

### Tests

```bash
.venv/bin/pytest                   # the default lane
.venv/bin/pytest -m live           # opt-in: starts real engines and real panes
.venv/bin/mypy --strict src
```

The live lane is excluded from the default run **in `addopts`, not only in a
comment**. Declaring a pytest marker does not deselect it, and for three
milestones a plain `pytest` was starting real `claude` subprocesses against the
developer's own config.

**Two things to know before you run it.** The default lane now includes
`tests/qa5/`, the round-5 QA harness: it starts a headless Chromium and a tmux
server on the throwaway `shepherd-qa` socket, and it is most of the five-odd
minutes the run takes. That was never a decision — it fell out of committing the
harness under `tests/` — and it is open as **W7.2**. And **never run two pytest
processes at once**: `tests/qa5/` refuses to sweep a run root belonging to a live
pid, which is the guard working correctly and looks like a failure.

## The documents

Read in this order. The spec is self-contained; nothing in it depends on the
conversation that produced it.

| File | What it is |
|---|---|
| [`docs/specs/orchestrator-platform.md`](docs/specs/orchestrator-platform.md) | the spec. §3 is 68 decisions (D1–D67 plus D38.1) **with their reasoning** — the most important section |
| [`docs/specs/logical-architecture.md`](docs/specs/logical-architecture.md) | what may import what. Enforced as AST properties, not spellings |
| [`docs/specs/data-schemas.md`](docs/specs/data-schemas.md) | every external shape, with a **real captured example**. Check one here before building on it |
| [`docs/specs/implementation-constraints.md`](docs/specs/implementation-constraints.md) | 24 facts that change *how* a thing is built |
| [`docs/specs/harness-contract.md`](docs/specs/harness-contract.md) | what a third-party harness must supply to join the flock. Deferred, decided in outline |
| [`docs/specs/credentials-and-auth.md`](docs/specs/credentials-and-auth.md) | four authentication questions, open. Nothing is stored today and nothing needs to be |
| [`docs/design/ui-decisions.md`](docs/design/ui-decisions.md) | the dark-mode redesign, **built 2026-09-22** — why each decision was taken, and the prototype links |
| [`docs/backlog/2026-09-21-projects-work-sources-and-ui.md`](docs/backlog/2026-09-21-projects-work-sources-and-ui.md) | **the forward-work register.** Start here for what to do next |
| [`docs/plans/2026-09-21-projects-and-ui-plan.md`](docs/plans/2026-09-21-projects-and-ui-plan.md) | the most recent milestone: the Projects backend and the UI, as executed |
| [`HANDOFF.md`](HANDOFF.md) | current state: what is proved, what is recorded unverified, what is open |
| `docs/plans/` | one plan per milestone, each with its own `*-BLOCKERS.md` ledger |
| `docs/probes/` | frozen evidence. Read-only — the captures are what commands actually printed |

## How this repo is written

Three habits, because each was bought with an incident:

**A check is not evidence until a planted violation makes it red.** The dominant
defect class here is *checks that report success without checking*, and it
recurs inside checks written to close earlier instances of it. Rules are
expressed as properties; a rule you can satisfy by renaming a string is not a
rule.

**Unknown is a first-class value.** It is counted and displayed. A classifier
that guesses to avoid saying "I don't know" is worse than one that says it.

**Nothing is reversed quietly.** When implementation pressure pushes against a
decision, it is re-decided in writing, in the ledger, with what was measured.
The ledgers carry survivors, bad mutations and "what this did not prove" as
standing sections, so a later reader inherits the doubt along with the result.

See [`CLAUDE.md`](CLAUDE.md) for the working rules, including the two incidents
that produced the blast-radius rules.

## License

Not yet chosen — see the open decisions in
[`docs/backlog/2026-09-17-future-work-and-publish-cleanup.md`](docs/backlog/2026-09-17-future-work-and-publish-cleanup.md).
Until one is added, default copyright applies: all rights reserved.
