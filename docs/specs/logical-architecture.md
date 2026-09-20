# Logical architecture — what may import what

**Extracted 2026-09-20 from §5.0 of [`orchestrator-platform.md`](orchestrator-platform.md) (F3).**
It lived at line 218 of a 2,700-line document, which is the wrong place for the
one rule every task in every milestone has to satisfy. Nothing in it was changed
by the move; it is cited from the spec the way `data-schemas.md` is (D41), and
the spec's §5.0 is now a pointer to this file.

**This document is enforced, not descriptive.** The rules below are checked as
**AST properties rather than spellings** by the suite under `tests/boundaries/`.
A rule you can satisfy by renaming an import is not a rule, and that is the
failure mode these tests are written against.

---

## The layers (D35, D36)

§5's process topology below says **where code runs**. This section says **what
may import what**. They are different rules: layers are an import rule,
processes are a restart rule. This is the reference every plan's module layout
and import tests are checked against.

#### The five layers

Dependencies point **down only**. A layer may import any layer below it, never
one above it.

```
L5  CONSUME   master/          web/               cli/
              orchestrator     HTTP + SSE         status · replay
              AgentSDKMaster   no polling         recompute · uninstall
    ════════════════════ consumer boundary ═══════════════════════════════
L4  GATE      toolsurface/
              registry of ToolDefs · invoke() · authorize() · audit log
              exporters → SDK MCP · stdio MCP · HTTP routes · CLI commands
    ──────────────────────────────────────────────────────────────────────
L3  DRIVE     orchestration/
              queues · workers · reconcile · claims · mailbox · channels · wake set
    ──────────────────────────────────────────────────────────────────────
L2  OBSERVE   signals/         runner/          providers/          engines/
              ingest → fold    seam: Runner     seams: WorkItem-    seam: EngineAdapter
              → classify       tmux · pty       Provider, Creds     claude_code · hookd
              verdict +        owned vs         jira · notion       transcript · hooks
              next_actions[]   attached         secret store
    ════════════════════ storage boundary ════════════════════════════════
L1  PERSIST   store/           logs/            core/
              all SQL          stops · audit    types · enums · ids
              the only DB      replay           the 7-bucket palette
              importer (D26)   rotating JSONL (D25)
```

The two double lines are the boundaries a **test** fails on. Everything else in
the diagram is convention a reviewer checks.

| Layer | Modules | Owns |
|---|---|---|
| **L5 Consume** | `master/`, `web/`, `cli/` | Everything a human or the orchestrator agent uses. Three **equal** consumers, and none of them is special. |
| **L4 Gate** | `toolsurface/` | The only place an action is authorized. The master, a tier-2 session over MCP, a queue write-back and a UI click all arrive at the same `authorize()` (D8, D32). |
| **L3 Drive** | `orchestration/` | Anything that acts on its own timer: queues, workers, reconcile, the wake set (D31). |
| **L2 Observe** | `signals/`, `runner/`, `providers/`, `engines/`, `host/` | Everything that reads or drives the outside world: engines, ptys, trackers, credentials, and the host itself. **Six of the seven seams have their drivers here.** `MasterRuntime` is the exception: its `Protocol` is declared in `core/` (L1, so `orchestration/` and `master/` can both name it without either importing the other) and its drivers live in `master/` at L5. |
| **L1 Persist** | `store/`, `logs/`, `core/` | State, logs, and the shared vocabulary every layer above uses. |

**Engine-specific vocabulary stays inside its adapter.** Claude Code's hook
names, payload fields and transcript entry types belong in `engines/claude_code/`.
`signals/` consumes what `EngineAdapter` produces, not what Claude Code emits.
If swapping the engine would edit `signals/`, the boundary has leaked.

#### The two enforced boundaries

1. **Consumer boundary.** L5 reaches the system **only through L4**. `master/`,
   `web/` and `cli/` import `toolsurface` and nothing below it. D19 states this
   for `master/`; D35 extends it to all three consumers, because they are
   equals. Enforced by an import test.
2. **Storage boundary.** Nothing outside `store/` imports a database driver
   (D26). `store/` exposes domain verbs that return dataclasses, and keeps
   transactions inside (D33). Enforced by an import test.

#### The four invariants

Each one is enforced by a build, not by a reviewer.

| Invariant | Rule | Enforced by |
|---|---|---|
| `store/` owns all SQL | Nothing outside `store/` imports a DB driver, so SQLite stays a packaging choice that the multi-user path can reopen without a rewrite (D26, D33). | storage-boundary import test |
| `master/` is a consumer | The orchestrator runs inside `controld` but imports only the `toolsurface` client. That is what makes extracting a `masterd` later a packaging change (D19). | consumer-boundary import test |
| One chokepoint | One `authorize()` and one audit log. Level 2 asks before anything leaves the machine; level 3 auto-approves, and **never unlogged** (D8). | single writer to the audit log |
| One contract suite per seam | Every seam ships one suite that all its implementations pass, **its `Scripted*` double included** (§14.2). A new provider is done when it passes the suite that already exists. | contract suites |

#### Why L4 exists: one read path, not one per consumer

The design is drawn against a failure it watched happen. A prior tool grew 349
endpoints, each with its own read logic, until its architecture document no
longer described the system.

```
the failure mode                         the layer map
every consumer keeps a private           everyone consumes one surface
read path

 ui  chat  worker  cli  hooks             ui  chat  worker  cli  hooks
  │    │     │      │     │                └────┴─────┼──────┴─────┘
  ▼    ▼     ▼      ▼     ▼                           ▼
 ─────────── store/ ───────────           toolsurface/ · authorize() · audit
                                                      │
 5 read paths · 5 places to fix a bug                store/
                                          1 read path · 1 audit entry per action
```

The difference is one bar. On the right, every action is also auditable and
gateable for free, because there is nowhere else for it to go.

#### The swap rule: which engines get a Protocol (D36)

Every component must be written so the engine under it is easy to replace: the
master's model vendor, the database, the runner, the tracker. That does **not**
mean every engine gets an interface. The rule:

| If the swap happens at... | Then | Examples |
|---|---|---|
| **Runtime.** Two implementations are alive at once, chosen by config or per call. | A `Protocol` seam, a `Scripted*` double, and a contract suite. | `Runner`, `EngineAdapter`, `MasterRuntime`, `ModelProvider`, `Credentials`, `WorkItemProvider` (§6) |
| **Edit time.** Only one implementation is ever alive; changing it means shipping a new build. | A **module boundary** is enough: an import rule plus an interface of domain verbs. | `store/` (D26, D33): SQLite today, a document DB for the remote path, never both at once |

An edit-time boundary is promoted to a Protocol only when its named trigger
fires. For `store/`, the trigger is two engines shipping from one codebase
(D33). Writing a Protocol before a second implementation exists is D9's mistake.

#### How the layers fold into processes

| Process | Hosts | Lifecycle |
|---|---|---|
| **`controld`** | L1–L5. Runs migrations, serves the UI, drives the queues, hosts the master. | Restart, upgrade and crash freely. |
| **`sessiond`** | The pty supervisor (`runner/`) and the hook-ingest endpoint (`engines/` → `hookd`). **Never migrates the schema.** | Long-lived; outlives `controld`. |

They are joined by a Unix socket with mode `0600`. The hook dispatcher writes
to that socket with a 250 ms timeout and **always exits 0**, so nothing the
platform installs can block Claude Code. Principle 4: a dead daemon degrades
visibility, never agents.

Real shapes and examples: data-schemas.md §Hook runtime contract (process, stdin, env, exit codes, stdout, timeout, sync, ancestry).

#### The one thing to watch

`master/`, `web/` and `cli/` sitting as equals at L5 is the invariant most
likely to erode under implementation pressure. The first time the fleet page
wants a query that is not in the tool surface, the honest move is to add it
there, **not** to let `web/` reach down one layer "just this once". That is
the exact edge the one-read-path diagram above is about.

#### Settled: who processes events, and how M1 honours L4 early (D37, D38)

- **`controld` processes hook events and is the only process that writes the
  database (D37).** `sessiond` receives events from `hookd` and relays them to
  `controld`, holding them in a bounded in-memory buffer while `controld` is
  down. The buffer is not an event store (D24). It is drained on reconnect,
  and anything that overflows is counted (principle 5) and rebuilt by
  `shepherd recompute` from transcripts.
- **M1 ships a minimal `toolsurface/` with its final shape (D38).** `web/` and
  `cli/` call `invoke()` from M1 onward. In M1–M3, `invoke()` looks up a
  read-only `ToolDef` and runs it, with no permission gate and no audit log.
  M4 adds `authorize()`, the audit log and the MCP exporters **behind**
  `invoke()`. **Acceptance test for M4: no file in `web/` or `cli/` changes.**

---

## L6 — `daemons/`, the composition root

**Added 2026-09-20, and it is a correction rather than a new layer.** The section
above writes *five* layers and does not mention `daemons/` at all. The **enforced**
map has carried six since ADR-1 — `tests/boundaries/_imports.py` reads
`"shepherd.daemons": 6` — so for four milestones the document and the test have
disagreed about how many layers there are. The test was right, and this is the
test being written down.

`daemons/` sits **above** L5 and is imported by **nothing**. That is the whole
point of a composition root: it is where the seams get their drivers, where
`bind_master_client()` and `register()` and `reset_stream()` are called, and
where the wiring order is decided once. Every layer below it can be constructed
in a test without it.

The rule it obeys is therefore the mirror of every other layer's: **`daemons/`
may import anything; nothing may import `daemons/`.** A module below L6 that
imports it has inverted the root — it can no longer be constructed without
starting a process — and that is what the boundary suite fails on.

Its size is a deliberate budget, not an accident: `daemons/controld.py` is **140
lines**. A composition root that grows logic stops being a root and becomes an
undeclared layer, so its length is asserted.
