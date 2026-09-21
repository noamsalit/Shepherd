# Shepherd

One local platform that makes a fleet of coding-agent sessions legible and
directable. You run several `claude` sessions across several repos; Shepherd
tells you which one needs you, why the others stopped, and what to do about it —
and gives an orchestrator agent the same view, through the same gate you use.

It is a **consumer of Claude Code**, not a fork of it and not a part of it. It
keeps its state in its own directories and never writes inside `~/.claude`
except the one marked, reversible hook block it installs and can remove.

## Status

**M1–M4 of seven slices are built, verified and QA'd.** M4.5 (connectors),
M5 (queues) and M6 (packaging and ship) are not started.

| | |
|---|---|
| suite | 1,866 passed, 2 skipped |
| live lane (`pytest -m live`) | 75 passed — real `claude` processes, real tmux panes |
| import-boundary rules | 105 |
| `mypy --strict src` | clean over 127 files, `disallow_any_explicit` on |
| verified hosts | **Linux only.** `MacHost` is written and reports `verified() == False` |

There is no installer yet, and the browser UI has never been opened by a human —
every web claim in the tree is bytes on disk or bytes on a socket. `HANDOFF.md`
lists exactly what that leaves unproven, with the seven-item manual checklist.

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

Then open `http://127.0.0.1:8787/`. Chat is the landing page; the fleet is page 2.

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

## The documents

Read in this order. The spec is self-contained; nothing in it depends on the
conversation that produced it.

| File | What it is |
|---|---|
| [`docs/specs/orchestrator-platform.md`](docs/specs/orchestrator-platform.md) | the spec. §3 is 64 decisions **with their reasoning** — the most important section |
| [`docs/specs/logical-architecture.md`](docs/specs/logical-architecture.md) | what may import what. Enforced as AST properties, not spellings |
| [`docs/specs/data-schemas.md`](docs/specs/data-schemas.md) | every external shape, with a **real captured example**. Check one here before building on it |
| [`docs/specs/implementation-constraints.md`](docs/specs/implementation-constraints.md) | 24 facts that change *how* a thing is built |
| [`docs/specs/harness-contract.md`](docs/specs/harness-contract.md) | what a third-party harness must supply to join the flock. Deferred, decided in outline |
| [`docs/specs/credentials-and-auth.md`](docs/specs/credentials-and-auth.md) | four authentication questions, open. Nothing is stored today and nothing needs to be |
| [`docs/design/ui-decisions.md`](docs/design/ui-decisions.md) | the 2026-09-21 dark-mode redesign — what is settled, what is open, and the prototype links |
| [`docs/backlog/2026-09-21-projects-work-sources-and-ui.md`](docs/backlog/2026-09-21-projects-work-sources-and-ui.md) | **the forward-work register.** Start here for what to do next |
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
