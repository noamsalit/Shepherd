# Orchestrator Platform — Design Spec

**Date:** 2026-09-08
**Status:** approved design, ready for implementation planning
**Author:** design dialogue between Noam Salit and Claude (Opus 5)

---

## 0. How to read this document

This spec is **self-contained**. A session picking it up needs nothing from the
conversation that produced it. Every decision is recorded with its reasoning in
§3 (Decision log), so you can tell an intentional choice from an accidental one.

Read §1–§4 before touching anything. §5–§12 are the design proper. §13–§18 are
execution.

### Picking this up in a fresh session

You have everything you need. Do this, in order:

1. Read §1–§4. §3 (Decision log) is the most important section in the document —
   34 decisions with their reasoning. If implementation pressure pushes against
   one, say so and re-decide out loud; do not quietly reverse it.
2. Note §2 — the product name (`shepherd`) and repo location are settled. Prose
   written earlier still says `shepherd` in places; same product.
3. Run the **tmux ↔ Claude Code TUI spike** from §18 before committing to M3.
   It is the one assumption that could force a redesign.
4. Then invoke the `writing-plans` skill against this spec, scoped to **M1
   only** (§16). Do not plan all six milestones at once — each milestone gets its
   own plan → implementation cycle.

What is *not* in this document: any code, any file layout beyond §15, and any
task breakdown. That is `writing-plans`' job, deliberately.

Prior art: this design was distilled by reading
[`claude-command-center`](https://github.com/amirfish1/claude-command-center)
("CCC") in full. CCC is referenced only where it justifies a decision — either a
pattern worth adopting or a failure worth avoiding. This is **not** a fork and
shares no code.

---

## 1. Purpose

One local platform that makes a fleet of coding-agent sessions legible and
directable. Five capabilities, in priority order:

1. **Visibility** — projects → sessions → subagents, ordered by urgency.
2. **Signals** — know when a session needs you, and when it stopped, *why*, and
   *what to do about it* (`next_actions[]`, D21).
3. **Coordination** — sessions message each other and spawn each other.
4. **Queues** — prioritized work read from Jira and Notion, drained by workers.
5. **Control** — a chat-first orchestrator agent that sees and drives all of it.

### The three tiers

The mental model the whole system is built around:

| Tier | What it is | Visibility | Created by |
|---|---|---|---|
| **1. Master** | one long-lived orchestrator, high-level reasoning | the chat page | you |
| **2. Session** | one real `claude` process per task, own pty, own transcript | full — terminal fidelity, drillable | master, queue worker, or you |
| **3. Subagent** | dispatched *inside* a tier-2 session by its own skills (cc10x, superpowers) | rollup: count + task + state | the session's skills |

Tier 3 being a rollup rather than a full view is **intended**, not a limitation.
Subagents are implementation details of a plan a tier-2 session is executing.

### Non-goals for v1

Not a Claude Code replacement. Not a CI system. Not a work iteming system. Not
multi-user. Not multi-engine. See §17 for the full deferred list.

---

## 2. Naming and placement (resolved)

**Both resolved 2026-09-12.** Recorded here rather than deleted, so a reader
who finds a stale `shepherd` knows it is a leftover, not a second name.

| Item | Resolved to | Notes |
|---|---|---|
| Product / CLI name | `shepherd` | CLI binary `shepherd`, bundle id `ai.shepherd`, state dir `~/.shepherd/` |
| Daemon names | `controld`, `sessiond` | unchanged — generic on purpose, they are not user-facing |
| Repo location | `/root/Shepherd/` | this spec lives at `docs/specs/` within it; `git init` done, baseline commit on `main` |

`shepherd` remains as a placeholder in prose written before this was settled. It is
the same product. Treat `shepherd` as authoritative and correct `shepherd` on sight
in any file you are already editing — a sweeping rename commit is not worth the
diff noise.

---

## 3. Decision log

Each row is a decision that was explicitly made, with the reasoning. **Do not
silently reverse one of these** — if implementation reveals a problem, say so and
re-decide.

| # | Decision | Reasoning |
|---|---|---|
| D1 | **Hybrid execution ownership**: own the pty for sessions the platform spawns (`owned`); attach read-mostly to externally-launched ones (`attached`). | Terminal fidelity and safe steering require owning the pty. Losing sight of hand-launched terminal sessions is unacceptable. Hybrid gets both, at the cost of two session classes with different capabilities. |
| D2 | **Local single-user, macOS `.pkg`**, but every host-dependent concern behind a seam from day 1. | Today it runs on one Mac. Remote/multi-user is a real future requirement, so `Runner`, `Credentials`, and `owner_id` exist now and get drivers later. |
| D3 | **Layered stop verdicts**: heuristics always, LLM on suspicion or on demand. **All raw signals persisted append-only** with a `replay` command. | "Did it actually finish?" is not mechanically knowable. Storing raw signals means a missed case is fixed by editing a rule and replaying history, not by waiting for it to recur. |
| D4 | **Work-item mirroring = mirror + reconcile + local claim + explicit write-back.** | Provider-as-source-of-truth cannot work offline and burns rate limits. Local-as-source-of-truth drifts. Mirror with a sync cursor gets both; a *local* claim avoids racing the provider's assignee field. |
| D5 | **REST APIs for Jira/Notion, not `acli`/`glab`.** | CLIs are macOS-local, interactively authed, and their output is not a stable contract. All three break on the remote/multi-user path. |
| D6 | **Reconcile is a cursor poll, not webhooks.** | A loopback-only daemon cannot receive webhooks. Webhooks become an optional ingest on the server path. |
| D7 | **Fresh session per work item** + a `build_brief()` seam + per-attempt outcome logging. **Memory layer deferred**, to be derived from those logs. | CCC's per-queue `LEARNINGS.md` is prompt-convention with no dedupe, no size cap, no scoping, no evidence a line ever helped, and a write race across parallel workers. Better to accumulate real outcome data and derive memory from it than to hand-append a file from day one. |
| D8 | **Autonomy toggle, level 2 default, level 3 opt-in.** One `authorize()` chokepoint; audit log always on at both levels. | Level 2 = act freely on the fleet, confirm anything leaving the machine. Level 3 = auto-approve and log. Level 3 is "auto-approved", never "unlogged". |
| D9 | **`EngineAdapter` interface with one implementation (Claude Code)**, plus a written capability matrix for Codex and Antigravity so the interface is constrained by three engines. | An interface designed against one implementation is usually wrong. Implementing two engines costs ~40% more and Codex's signal quality is far worse (no hook system), which would make the differentiator Claude-only in practice anyway. |
| D10 | **Master = Claude Agent SDK session**, not a raw Messages API loop. *(Refined by D30: this is now `AgentSDKMaster`, one implementation of the `MasterRuntime` seam.)* `disallowed_tools=["Agent","Task"]`, `allowed_tools` = orchestration MCP tools only, `setting_sources=[]`, `can_use_tool=authorize`. | Runs on the local Claude subscription (no per-token API cost). `disallowed_tools` makes "real session, not subagent" a property of the harness rather than a prompt instruction that the model will eventually ignore. `setting_sources=[]` stops the master inheriting the global `CLAUDE.md` / cc10x routing rules. |
| D11 | **Four orthogonal axes**: Engine · Provider · Credential · Runner. Resolved once in a `SessionSpec` resolver. | These are routinely conflated. Keeping them independent is what makes "any vendor's API or subscription, per user" a config change rather than a rewrite. |
| D12 | **Coordination = mailbox + broadcast channels.** Channels fan out *into* the mailbox; they have no delivery code of their own. | Direct injection into a running session corrupts its state. One delivery path, one policy, one place to get it right. |
| D13 | **`ask()` forks the target's session**, asks the fork, discards it. | The target is never interrupted and its context is never polluted by the question. Latency is one turn, not "however long the target's current turn takes." |
| D14 | **tmux for `LocalRunner`**, not a bare pty. | Survives `sessiond` restarts; `capture-pane -e -p` gives correct late-attach resync; `tmux attach` makes "jump to terminal" exact instead of AppleScript keystroke injection; alt-screen and resize already handled. |
| D15 | **Worktree per work item for queue workers only.** | `max_parallel > 1` on one repo means N processes fighting over one index and branch. Your own sessions and orchestrator-spawned sessions stay in the main tree. CCC refuses worktrees because it attaches to *your* sessions; a queue worker is a disposable executor and isolation is right for it. |
| D16 | **Seven-bucket outcome palette**, red reserved for errors. | See §4. |
| D17 | **Session `finished` ≠ work `done`.** Session outcome and work-item progress are two chips from two sources, never merged. | A session can finish flawlessly while the work is a week from prod. Merging them makes the dashboard lie. |
| D18 | **`blocked_external` is a first-class stop reason** with a self-declaration tool. | "Waiting on a merge/review/CI" would otherwise land as `completed` or `incomplete`, and a worker would pointlessly retry it. |
| D19 | **Master is a separate module with a hard import boundary**, running in `controld`'s process but reaching the rest of the system *only* through the tool-surface client — never a direct import of storage, signals, queues, or runners. Enforced by a lint rule and an import test, not convention. | The master is a consumer of the event stream like the UI and the workers (principle 1); if it grows a private read path, the "one direction, one store" invariant is gone. Keeping it in-process avoids a third launchd agent and a third socket for a single-user v1. **The boundary is what makes extracting a `masterd` later a packaging change rather than a rewrite** — the seam is drawn now, the process split is deferred (§17). |
| D20 | **Connectors are third-party MCP servers mounted into the master only**, chosen from a UI list of supported platforms (Claude-Desktop-style). Tier-2 sessions never receive a platform credential; when one needs a connector it brokers through `ask_orchestrator()`. | One auth surface, one audit trail, one `authorize()` gate. Attaching connectors to N spawned sessions would multiply the credential blast radius and put third-party tools inside processes we do not gate. A session that genuinely owns a tool already has its own `CLAUDE.md` MCP config, which the platform does not touch. |
| D21 | **Every stopped session carries `next_actions[]` — at most three, for *every* stop reason**, not just `end_turn`. Heuristic table always; LLM refines when a key exists. | "It stopped" is not actionable; "it stopped and here is the one thing to do" is. A crash, a rate limit, and a derailed completion each have an obvious next move, and the mechanical stop reasons (§8) already tell us which. Deriving the list from `stop_reason` makes it free for the ~80% of stops that never reach the LLM lane. |

| D22 | **A project is a workspace of 1..N repos.** `repo` is a first-class entity; a session binds to a repo by **longest-prefix match of `cwd` against registered repo paths**, then repo → workspace. The master can add and remove repos; `add_repo` is `local_destructive`. | One work item routinely spans four repos here (OXDEV-71937 touched ox-ai-agent, factor, reporting-service, frontend). A one-repo project cannot represent that, and correlating N sessions by a shared reference loses the single view of what the work touched. Prefix-matching on repo paths rather than a workspace root lets a repo live anywhere on disk and resolves nested repos to the innermost. `add_repo` is destructive because §13 validates every spawn against the registered allowlist — adding a repo *widens that allowlist*. **Revises D15**: worktrees become per (work item, repo), created lazily on first write to a repo, not one per work item. |
| D23 | **Hierarchy is mirrored, not modelled.** `kind_raw` (provider's word, verbatim) + `kind_class` (`container` \| `work` \| `unknown`) + `parent_external_id`. **Dispatchable = `kind_class == 'work'`.** Decomposition creates real child items through the provider; when `supports_children` is false it degrades to linked siblings. | Exactly the `status` / `status_class` pattern already in the spec, so it adds no new concept. Making dispatch depend on a mapped enum means an epic is unclaimable *mechanically* — no code anywhere contains the word "epic", which is Jira's vocabulary and not Notion's. Real child items (rather than a local task table) keep one source of truth and stay visible to the team; `HierarchyUnsupported` makes the Notion case an explicit degrade rather than a silent one. |
| D24 | **No event store.** Hook events are folded into `session` columns as they arrive and then discarded. Stop analysis reads the **transcript Claude Code already writes to disk** plus the stop event's own metadata: mechanical reasons resolve with certainty and cost nothing; a cheap model runs **only** when `stop_reason = end_turn`. | The firehose was 200 MB–1.2 GB/day to serve three jobs, two of which only need the last 90 seconds. Liveness, registration, and the counters are all "update a field when the event arrives" — the event has no value once folded in. The evidence for the third job already exists on disk in `~/.claude/projects/*.jsonl`, so storing it again was duplication. Mechanical reasons (`rate_limit`, `crashed`, `auth_failed`, exit codes) are never in the text and never need a model; `end_turn` is the one genuinely ambiguous case. **Revises D3** — raw signals are no longer persisted; `replay` now runs over the stop-evidence log (D25), which is kilobytes per session rather than gigabytes per day. **Revises D7** — `worker_run` is dropped: attempt history is `SELECT … FROM session WHERE work_item_id = ?`, and the future memory layer derives from that plus the stop log. |
| D25 | **Evidence, audit, and replay diffs go to rotating JSONL logs, never the database.** Daily files, gzip on rotation, size cap as a second trigger, 90-day retention (14 for daemon logs). **Nothing the UI renders may read a log** — the audit view is the single exception, because it is a literal tail. | These are append-only, human-read, and offline-analysed: `grep` and `jq` territory, not queries. Keeping them out of the database is what lets the database stay six small tables. The rule about UI reads is the guardrail — the moment a page wants "every derailed session last month", that fact belongs in a column instead. A reader must skip malformed trailing lines, since a daemon killed mid-write leaves one. |
| D26 | **SQLite is a delivery choice, not an architectural one.** All SQL lives in `store/`; nothing outside it imports a database driver. Switching engines must be a contained change. | Today's constraint is a signed `.pkg` with no server to babysit, which rules out Postgres and MongoDB on packaging grounds — not on data-model grounds. MongoDB in particular is a good fit for the *shape* of this data and a bad fit for shipping a desktop app (a third daemon, ~100 MB bundled, WiredTiger claiming half the RAM of the machine running the fleet). When the remote/multi-user path in D2 arrives, that decision genuinely reopens, and it must not be a rewrite. No `Store` Protocol — a storage interface written against one implementation is the D9 mistake, and SQL leaks through it anyway. The boundary is an import rule, enforced by the same test as D19. |
| D27 | **The fleet page gets a third view: a cross-tab of work-item status × session outcome**, with a `(no work item)` column and a `(no session)` row. | The two chips of D17 are the two axes of one grid. The `finished × in_review|in_qa` cell is the "stuck between my desk and prod" question the spec already wanted a filter for; the `(no session)` row is the backlog in the same view; the `(no work item)` column is where hand-launched sessions live, which is most of a real day. Lands with M5, not M2 — the columns are work-item status, which does not exist before the mirror. |
| D31 | **Wake queue.** A session that stops is routed by whoever owns it: queue-spawned → the worker loop (unchanged); **master-spawned → a wake set the master drains**. At level 2 it drains at the start of your next turn as a summary; at level 3 it wakes the master immediately. Capped at **2 master-initiated attempts per lineage**, and narrow by construction — only `unfinished` and `error` outcomes on master-owned sessions wake anything. | The worker loop runs forever, so it notices a stop at 3am; the master only runs while you are typing, so it does not. That inverts the two halves: the component holding the context to decide is asleep, and the component that is awake has no context. Nothing is *lost* — the conclusion and its action items are already written — so this is latency, not data loss, which is why level 2 stays a summary rather than silent autonomy. The retry cap mirrors the worker's `attempt < 2`; without it "stops → retry → stops → retry" runs until morning. `needs_you` deliberately does **not** wake the master: that is the human's rail, and handing it to an agent would hide the one thing you asked to be shown. |
| D30 | **`MasterRuntime` is the sixth seam**, with `AgentSDKMaster` (subscription, Anthropic) in v1 and `ApiLoopMaster` (`api_key` + `base_url`, any vendor) defined but unbuilt. **LangChain/LangGraph rejected.** | Seat and API are two transports, not two settings: a claude.ai seat is reachable only through the Claude Code harness, never over an API. A framework that speaks only to APIs therefore *removes* the zero-marginal-cost path for the chattiest component in the system, rather than adding choice. Between a plain tool-call loop and LangGraph the loop wins on merit — the master is forbidden from dispatching subagents (D10), so its graph is one node; LangGraph's branching-state machinery earns nothing here and costs a dependency tree in a stack whose stated ethos is stdlib HTTP and no frontend framework. Tool restriction is **not** a tiebreaker: both implementations consume the same MCP tool surface (§11), so the allowlist is ours either way. |
| D29 | **Session title is one field with a `title_source` ratchet** (`user` > `engine` > `brief`), and pushing a user rename back into the harness is an **engine capability** (`can_set_title`), not an assumption. Until verified it is local-only, and the UI says `local only` rather than implying a sync that did not happen. | You want to name a session and have the name mean something everywhere. But writing into a transcript the engine owns runs at design principle 4, and no engine other than Claude Code is even a candidate yet. One field plus a precedence rule keeps the display logic identical no matter which source won; adding an engine that can rename flips a capability flag instead of changing the schema. A visible `local only` marker is the difference between a degrade and a lie. |
| D28 | **`ticket` → `work_item` throughout.** | "Ticket" is Jira's word; a Notion page is not a ticket, and neither is a GitHub issue. Renamed while the spec was the only artifact and the cost was a find-and-replace. |
| D32 | **The tool surface is a registry, and MCP is an output format — never an input type.** Every capability is declared once as a `ToolDef` (name, JSON Schema, blast class, handler, audiences); one `invoke()` runs it; thin **exporters** translate the registry into whatever a consumer needs — SDK MCP, stdio MCP, OpenAI functions, HTTP routes, CLI subcommands. **Revises D30**: `mount_tools(mcp_servers)` becomes `configure(tools, system_prompt)`. | MCP appears in this system for two unrelated reasons and only one of them is a choice. At the **tier-2 boundary it is forced and correct** — Claude Code is a program we do not control and MCP is the contract it speaks. At the **master it is incidental** — that is our own Python behind our own model, and MCP is there only because the Agent SDK happens to accept tools that way. Putting the incidental case in the `MasterRuntime` signature made every future runtime accept a format only one of them uses: the D9 mistake, committed inside the decision that cites D9. A registry also kills three hand-maintained lists — `SESSION_TOOLS`, the `BLAST_CLASS` lookup, and the UI's own route table — and turns principle 1 from a discipline into a property: a capability absent from the registry has no surface that can reach it. |
| D33 | **`store/` exposes domain verbs returning dataclasses, with transaction scope kept inside.** No caller may pass SQL, receive a driver row, or open a transaction. **Promote to a `Store` Protocol only when two engines must ship from one codebase** — that is the named trigger, and until it fires the import rule stands. | D26 refused a storage interface and was right for one shipping engine, but "no interface" is not the same as "no discipline": an abstraction leaks through a module boundary exactly as easily as through a Protocol if callers touch rows or drive transactions. These three rules are what make the Mongo port in D2's remote path a rewrite of one package rather than a rewrite of its callers — the claim becomes `findOneAndUpdate`, the matrix cross-tab becomes an aggregation pipeline, and nothing above `store/` notices. They also make the eventual promotion mechanical: a list of typed verbs with dataclass returns *is* a Protocol, minus the `class` line. |
| D34 | **The LLM verdict lane is deferred past M2.** Mechanical stop reasons ship as specified; `end_turn` resolves on heuristics alone, `decided_by='heuristic'`, and the residue is `unknown`. **No seam is written for it** — one named call site in `signals/` instead. | Every mechanical reason in §8 is certain and free, and they cover the majority of stops; the model is needed for exactly one question — *it ended cleanly, but did it finish?* §8 already made that lane optional by construction for the no-API-key case, so deferring it is a configuration the design anticipated rather than a cut. Writing a `Classifier` seam now would be D9's mistake with **zero** implementations behind it instead of one; a single call site is the cheaper placeholder and costs nothing to promote later. `unknown` being visible and counted is principle 5 working as intended — it is the tuning backlog that tells you when the lane is worth building. |

---

## 4. Design principles

1. **One direction, one store.** Engine state → signals → verdicts → consumers.
   The UI, the orchestrator, and queue workers are three consumers of the same
   event stream. No consumer gets a private read path into engine state.
   *(CCC has 349 endpoints each with its own read logic; its `architecture.md`
   no longer describes the system it documents. That is the failure mode.)*
2. **Raw in, derived out.** Engine events are folded into `session` columns as
   they arrive and then discarded (D24); the evidence behind a *stop* is written
   to the stop log (D25). Every derived column is reconstructible — from the
   engine's own transcript plus that log — and `shepherd recompute` does exactly
   that. What the UI shows is an answer we stored, never an answer only we can
   remember.
3. **Every pluggable thing has exactly one interface** and exactly one test
   suite that every implementation must pass.
4. **Nothing we install may harm Claude Code.** Hooks time out, swallow all
   exceptions, and always exit 0. A dead daemon degrades visibility, never
   agents.
5. **Unknown is a first-class value**, counted and displayed. An `unknown` rate
   is a tuning backlog, not a bug to hide.
6. **Typed, strict, small.** Python 3.12, `mypy --strict`, no `Any`. Single
   responsibility per module; a file that grows past ~600 lines is a signal it
   is doing too much.

### The outcome palette (D16)

Seven buckets. Every bucket has both a colour **and** a glyph, so the amber/red
distinction survives colourblindness and greyscale.

| bucket | colour | glyph | meaning | who acts |
|---|---|---|---|---|
| `running` | blue `#3B82F6` | ● | working, nothing wanted from you | nobody |
| `needs_you` | amber `#F59E0B` | ⏸ | permission request, question, or idle-waiting | **you, now** |
| `finished` | green `#10B981` | ✓ | session's assigned task complete and verified | nobody |
| `unfinished` | violet `#8B5CF6` | ◑ | stopped clean, work remains (`incomplete`, `derailed`, `truncated`) | you, when ready |
| `blocked` | slate `#64748B` | ⏳ | did its part, waiting on something external | someone else |
| `paused` | cyan `#06B6D4` | ⏱ | rate limited / quota — resumes by itself | nobody, wait |
| `error` | red `#EF4444` | ✕ | crashed, auth failure, bad request, stalled | you, fix it |

Slate is deliberately desaturated: a blocked session should read as *parked*,
not as demanding.

---

## 5. Architecture

### Process topology

```
┌──────────────────────────────────────────────┐
│  UI (browser)                                │
│  Chat page  ·  Fleet page  ·  Session view   │
└───────────────┬──────────────────────────────┘
                │  HTTP + SSE  (never in-process calls)
┌───────────────▼──────────────────────────────┐
│  controld — control plane (restartable)      │
│                                              │
│  ┌────────────┐ ┌──────────┐ ╔════════════╗  │
│  │ Signals    │ │ Queues   │ ║Orchestrator║  │
│  │ + Verdicts │ │ + Workers│ ║(Agent SDK) ║  │
│  └────────────┘ └──────────┘ ║+ connectors║  │
│                              ╚═════╤══════╝  │
│         no direct import ──────────┘         │
│  ┌────────────────────────────────────────┐  │
│  │ authorize()   ·   audit log            │  │
│  └────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │ Tool registry · invoke() · exporters   │  │
│  └────────────────────────────────────────┘  │
│                   SQLite (WAL)               │
└───────────────┬──────────────────────────────┘
                │  Runner interface / UDS
┌───────────────▼──────────────────────────────┐
│  sessiond — pty supervisor (long-lived)      │
│  owns every tmux session + hook ingest UDS   │
└───────────────┬──────────────────────────────┘
                │
     claude(tmux)   claude(tmux)   claude(tmux)
```

**The double border around Orchestrator is D19.** It runs in `controld`'s
process but may import nothing from Signals, Queues, Runner, or storage — it
calls the same tool-surface client a tier-2 session calls over MCP. An import
test asserts the boundary; violating it is a failing build, not a review
comment. That is also what lets the master move into its own `masterd` process
later (§17) without touching a line of its logic.

**Why two processes:** if the control plane owns the ptys, restarting or
upgrading it kills your agents. CCC split this after the fact for exactly this
reason. Splitting up front costs one Unix socket and buys a control plane you can
restart, upgrade, and crash freely.

### Data flow

```
Claude Code hooks ─────┐
tmux pty bytes ────────┼──► ingest ──► fold into session columns   (D24)
process exit ──────────┘                  │      (event then dropped)
                                          │
                        on stop ──────────┤
                                          ▼
              engine transcript ───► classify ───► session.stop_* columns
              stop metadata       │                        │
                                  └──► stops log (D25) ────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                     fleet UI        SSE stream     queue worker
                                                      routing
```

### Stack

- **Backend:** Python 3.12, stdlib HTTP + SSE, SQLite (WAL), `claude-agent-sdk`
- **Frontend:** vanilla TypeScript, no framework; `xterm.js` the only runtime dep
- **Runner:** tmux
- **Packaging:** signed + notarized macOS `.pkg`, two launchd user agents

No build server, no bundler beyond `tsc`. The frontend is the layer that changes
most and the one you debug at 2am when a signal renders wrong; keep it
inspectable.

---

## 6. The six seams

Everything pluggable goes through exactly one interface. No module has a second
path to the same capability.

```python
class Runner(Protocol):
    def start(self, spec: SessionSpec) -> RunnerHandle: ...
    def attach(self, handle: RunnerHandle) -> ByteStream: ...        # live output
    def snapshot(self, handle: RunnerHandle, lines: int) -> bytes: ...  # screen+scrollback
    def write(self, handle: RunnerHandle, data: bytes) -> None: ...
    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None: ...
    def signal(self, handle: RunnerHandle, sig: Signal) -> None: ...
    def probe(self, handle: RunnerHandle) -> ProcState: ...          # alive?, exit_code


class EngineAdapter(Protocol):
    def capabilities(self) -> EngineCapabilities: ...
    def spawn_argv(self, spec: SessionSpec) -> list[str]: ...
    def locate_transcript(self, engine_session_id: str) -> Path | None: ...
    def parse_transcript_delta(self, path: Path, offset: int) -> tuple[list[Signal], int]: ...
    def set_title(self, handle: RunnerHandle, title: str) -> None: ...  # D29
    def hook_events(self) -> list[str]: ...          # which hooks to register
    def install_hooks(self, dispatcher: Path) -> None: ...
    def uninstall_hooks(self) -> None: ...


class MasterRuntime(Protocol):                                     # D30, revised by D32
    def configure(self, tools: list[ToolDef], system_prompt: str) -> None: ...
    def send(self, text: str) -> AsyncIterator[Event]: ...
    def resume(self, master_session_id: str) -> None: ...   # opaque id — see below
    def interrupt(self) -> None: ...
    def capabilities(self) -> MasterCapabilities: ...


class ModelProvider(Protocol):
    def models(self) -> list[ModelInfo]: ...          # id, context, cost, release
    def effort_ladder(self) -> list[str]: ...         # [] when the engine has none


class Credentials(Protocol):
    def resolve(self, owner_id: str, provider: str) -> AuthMaterial: ...
    def resolve_ref(self, credential_ref: str) -> AuthMaterial: ...   # for stored refs
    def store(self, owner_id: str, provider: str, material: AuthMaterial) -> str: ...  # -> credential_ref
    def forget(self, credential_ref: str) -> None: ...
    def available(self, provider: str) -> bool: ...   # gates optional features (§8 LLM verdict)


class WorkItemProvider(Protocol):
    def capabilities(self) -> WorkItemCapabilities: ...
    def list(self, query: ProviderQuery, since: str | None) -> tuple[list[WorkItem], str]: ...
    def get(self, external_id: str) -> WorkItem: ...
    def comment(self, external_id: str, text: str) -> None: ...
    def set_status(self, external_id: str, status: str) -> None: ...
    def create(self, project_ref: str, fields: WorkItemDraft) -> str: ...
```

### The four axes (D11)

| Axis | Seam | v1 | Later |
|---|---|---|---|
| **Engine** — which agent harness | `EngineAdapter` | Claude Code | Codex, Antigravity |
| **Provider** — whose model API | `ModelProvider` | Anthropic | OpenAI, Google, OpenRouter |
| **Credential** — how we authenticate | `Credentials` | local Claude subscription | per-user API key / OAuth / BYOK |
| **Runner** — where the process runs | `Runner` | `LocalRunner` (tmux) | `SSHRunner`, `ContainerRunner` |
| **Master runtime** — how the orchestrator talks to a model (D30) | `MasterRuntime` | `AgentSDKMaster` — subscription seat | `ApiLoopMaster` — `api_key` + `base_url`, any vendor |

A session is `(engine, provider, credential, runner, project, task)`. Every field
is defaulted today and a lookup later. Nothing else in the system knows about
vendors.

### Capability records

```python
@dataclass(frozen=True)
class EngineCapabilities:
    can_spawn: bool
    can_steer: bool
    can_fork: bool                  # gates ask() strategy (§9)
    can_set_title: bool             # gates rename write-back (D29); False until probed
    has_hooks: bool                 # gates signal quality
    effort_ladder: list[str]        # [] = hide the control, drop the field
    transcript_format: Literal["jsonl", "sqlite", "none"]


@dataclass(frozen=True)
class WorkItemCapabilities:
    status_model: Literal["workflow", "property"]   # jira | notion
    legal_statuses: list[str] | None                # None = free-form
    supports_transitions: bool
    supports_comments: bool
    supports_create: bool
    supports_priority: bool
    supports_incremental_sync: bool
    supports_children: bool                         # D23 — jira yes, notion per-database
    child_kind_raw: str | None                      # "Sub-task" — what to pass on create


@dataclass(frozen=True)
class MasterCapabilities:                                          # D30, D32
    billing_mode: Literal["seat", "api"]   # seat = zero marginal cost; api = per token
    owns_history: bool                     # True = the runtime persists the conversation
    owns_compaction: bool                  # True = the runtime trims its own context
    supports_parallel_tool_calls: bool
    context_window: int
```

**`MasterRuntime.resume(master_session_id)` takes an opaque id and the runtime owns
what it means.** `AgentSDKMaster` hands it to the Agent SDK, which resumes a
transcript Claude Code already wrote to disk — hence `owns_history=True`,
`owns_compaction=True`, and one continuous orchestrator conversation across
restarts for free. `ApiLoopMaster` gets neither: it keys its **own** persisted
message list by that id and must trim or summarize when the conversation outgrows
the window. That asymmetry is the largest real cost of the second implementation
and the reason both flags exist rather than being assumed — the master is by
design the longest-lived conversation in the system, so compaction is not a
someday concern for it. §11's context strategy (frozen system prompt,
`fleet_summary()` bounded at ~40 lines regardless of fleet size) is what keeps
that tractable, and it was written with this in mind.

`WorkItemCapabilities.status_model` is load-bearing: Jira has a workflow where a
status change may be illegal from the current state; Notion has a Status
property you simply set. `set_status` is the common verb and the provider
resolves it (Jira: find the legal transition id or raise `IllegalTransition`;
Notion: patch the property).

### Engine capability matrix (D9 — written to constrain the interface)

| | Claude Code (v1) | Codex (later) | Antigravity (later) |
|---|---|---|---|
| spawn headless | `claude -p` | `codex exec` | `agy` print mode |
| steer / resume | yes, both | yes, both | AGY CLI or LSP RPC |
| transcript | JSONL `~/.claude/projects/` | JSONL, partial parity | JSONL `~/.gemini/antigravity/brain/` |
| hooks | **rich** (32 events) | **none** | none |
| fork | yes | unknown | unknown |
| effort ladder | `low·medium·high·xhigh·max` | `low·medium·high·xhigh` | none |

The hooks row is why Claude Code is v1: the signal engine (§8) is built on hook
events, and an engine without hooks gets materially weaker `needs_you` and stop
detection. `EngineCapabilities.has_hooks=False` must degrade gracefully to
transcript-tail + process-probe inference, and the UI must say so.

---

## 7. Data model

**Six tables.** SQLite with WAL, one file — and per D26 that is a packaging
decision, not an architectural one: all SQL lives in `store/`, nothing else
imports a database driver, and the engine is expected to change when the
remote/multi-user path in D2 arrives.

Every table carries `owner_id TEXT NOT NULL DEFAULT 'local'` (D2). Times are
`TEXT` ISO-8601 UTC. Enums are `TEXT` with a `CHECK` constraint — never ints —
so a raw `sqlite3` shell is readable. **Columns for what gets filtered, sorted,
or constrained; JSON for what only gets read back whole.**

### 7.0 What `store/` may expose (D33)

D26 refused a `Store` Protocol. That decision stands, but "no interface" is not
"no contract" — a module boundary leaks exactly as easily as a bad Protocol if
callers reach through it. Three rules, and each one is what makes the Mongo port
in D2's remote path a rewrite of *one package* instead of a rewrite of its
callers:

1. **Expose verbs, not queries.** `claim_work_item(item_id, session_id, ttl_s)
   -> bool`, never `query(sql, params)`. A verb can be implemented by another
   engine; a SQL string cannot.
2. **Return dataclasses, never driver rows.** The moment a caller touches
   `row["status_class"]` or a `sqlite3.Row`, the engine has escaped the package.
   `store/` converts at its own boundary and hands back `Session`, `WorkItem`,
   `Repo`. This is §13's "never return a raw DB row" rule, applied one layer
   earlier.
3. **Transactions stay inside.** No caller writes `with store.transaction():`.
   The atomic thing *is* one function — `claim_work_item()` is a conditional
   `UPDATE` in SQLite and a `findOneAndUpdate` in Mongo, and the caller cannot
   tell which.

**The named trigger for promoting this to a `Store` Protocol: the day two
engines must ship from one codebase** — a desktop `.pkg` on SQLite and a server
deployment on something else. At that point drift between them is a real risk and
one contract suite both must pass earns its keep. Until then the import rule is
cheaper and less misleading. Following the three rules above makes that promotion
mechanical rather than a redesign: a list of typed verbs with dataclass returns
already *is* the Protocol, minus the `class` line.

### What is deliberately *not* stored

Naming these matters more than the tables, because each was in an earlier draft:

| not stored | why, and where it went instead |
|---|---|
| raw hook events | folded into `session` columns on arrival, then dropped (D24). 200 MB–1.2 GB/day for data whose two live consumers need 90 seconds of it |
| subagent rows | a count lives on `session`; the expanded list is read from the transcript on demand, for the one session you opened |
| a claims table | four columns on `work_item`. One row per item means there is nothing to double-claim; a conditional write settles the race |
| `worker_run` history | attempt history is `SELECT … FROM session WHERE work_item_id = ?` (D24) |
| stop evidence, audit, replay diffs | rotating JSONL logs (D25) |

### `workspace`

| field | type | null | notes |
|---|---|---|---|
| `id` | TEXT PK | no | ulid |
| `owner_id` | TEXT | no | |
| `name` | TEXT | no | |
| `root_path` | TEXT | **yes** | only where `discover_repos` starts looking; repos may live anywhere (D22) |
| `created_at` | TEXT | no | |
| `last_activity_at` | TEXT | **yes** | fleet-page ordering |

### `repo`

| field | type | null | notes |
|---|---|---|---|
| `id` | TEXT PK | no | |
| `workspace_id` | TEXT FK | no | |
| `name` | TEXT | no | defaults to directory basename |
| `root_path` | TEXT | no | absolute, canonicalized, **UNIQUE**. The longest-prefix key that binds `cwd` → repo (D22) |
| `vcs_remote` | TEXT | **yes** | null for non-git |
| `active` | BOOLEAN | no | soft delete — past sessions still reference it |
| `added_at` | TEXT | no | |

Prefix matching is done in Python over the full repo list. It is tens of rows;
SQL prefix-matching on paths is a trap and there is no index for it.

### `session`

Three groups of fields with completely different write behaviour. Keeping them
visually separate is load-bearing — the middle group is what replaces the event
store.

**Written once at spawn, never changes:**

| field | type | null | notes |
|---|---|---|---|
| `id` | TEXT PK | no | **ours**, ulid, assigned before the process starts |
| `owner_id` | TEXT | no | |
| `engine_session_id` | TEXT | **yes** | the engine's own id. **Null until the engine emits it** — nothing may key off it |
| `workspace_id` | TEXT FK | no | |
| `repo_id` | TEXT FK | **yes** | nearest enclosing repo; null for a workspace-root session |
| `work_item_id` | TEXT FK | **yes** | **the join key for the matrix view (D27)** |
| `work_item_ref` | TEXT | **yes** | `jira:OXDEV-1234` — display and logs only, never a join |
| `parent_session_id` | TEXT FK | **yes** | who spawned it |
| `origin` | TEXT enum | no | `orchestrator` \| `queue_worker` \| `user_ui` \| `external` \| `ask_fork` |
| `ownership` | TEXT enum | no | `owned` \| `attached`. (Was `class` — a reserved word almost everywhere) |
| `ephemeral` | BOOLEAN | no | `TRUE` for `ask()` forks; hidden from the fleet by default |
| `depth` | INTEGER | no | recursion cap |
| `retry_of` | TEXT FK→session | **yes** | set when this session is a retry of another (D31) |
| `attempt` | INTEGER | no | `1` for an original; `+1` along the `retry_of` chain. The master's cap reads this |
| `brief` | TEXT | **yes** | what it was asked to do. For `attached` sessions, the transcript's `lastPrompt` |
| `cwd` · `worktree_path` · `runner_handle` | TEXT | worktree/handle yes | |
| `engine` · `provider` · `model` · `effort` · `credential_ref` · `runner` | TEXT | mostly yes | null = engine default. `effort` is a top-level transcript field; `model` is at `message.model` |
| `started_at` | TEXT | no | |

**Title is its own small subsystem** — see `title` / `title_source` in §7.1.

**Overwritten continuously while alive — this group *is* the event store (D24):**

| field | type | null | notes |
|---|---|---|---|
| `state` | TEXT enum | no | `starting` \| `running` \| `needs_you` \| `stopped` |
| `last_event_at` | TEXT | **yes** | the liveness clock. Nothing within `LIVENESS_WINDOW_S` → not running |
| `needs_you_reason` | TEXT | **yes** | the actual ask — `"permission: Bash(git push)"` — never "needs attention" |
| `tasks_done` / `tasks_total` | INTEGER | no | the `2/5` chip, counted as `Task*` events arrive |
| `active_subagents` | INTEGER | no | the `3 subagents` count |
| `repos_touched` | TEXT **JSON** | no | `[]`; repo ids accumulated from `FileChanged`. What makes a multi-repo workspace legible (D22) |
| `pr_url` | TEXT | **yes** | **free — the transcript emits `pr-link` entries.** The `[↗]` on a blocked row |

**Written at stop, overwritten when a rule improves:**

| field | type | null | notes |
|---|---|---|---|
| `stop_reason` | TEXT enum | **yes** | values in §8 |
| `outcome` | TEXT enum | **yes** | one of the seven palette buckets (§4) |
| `why` | TEXT | **yes** | one line, ≤120 chars |
| `confidence` | REAL | **yes** | |
| `decided_by` | TEXT enum | **yes** | `mechanical` \| `model` \| `declared` \| `manual` |
| `next_actions` | TEXT **JSON** | no | `[]`; up to 3 `{text, kind, target}` (D21) |
| `ended_at` · `exit_code` | | yes | `exit_code` is `owned` only |

The stop group is **derived and recomputable**: truth is the transcript plus the
stop-evidence log (D25), and `shepherd recompute` rebuilds these columns. They exist
because the fleet page needs a colour for fifty sessions per render, and
re-deriving that per row would scan fifty transcripts.

### 7.1 Session title — three sources, one field (D29)

| field | type | null | notes |
|---|---|---|---|
| `title` | TEXT | **yes** | what the UI shows |
| `title_source` | TEXT enum | no | `user` \| `engine` \| `brief` — default `brief` |
| `title_synced_at` | TEXT | **yes** | set when a `user` title was accepted by the engine |

Precedence is **`user` > `engine` > `brief`**, and it is a one-way ratchet: once
you rename a session, the engine's own title never overwrites it again.

- **`brief`** — first 60 chars of the brief. Always available, including before
  the process emits anything.
- **`engine`** — Claude Code writes `ai-title` entries into its transcript, so a
  generated title arrives for free, including for `attached` sessions.
- **`user`** — you renamed it in the UI.

**Pushing a rename back into the harness** is an engine capability, not a given:

```python
can_set_title: bool          # added to EngineCapabilities (§6)
def set_title(self, handle: RunnerHandle, title: str) -> None: ...
```

For Claude Code the candidate mechanism is appending an `ai-title` entry to the
session transcript, and **that is not yet verified** — writing into a file the
engine owns runs straight at design principle 4 ("nothing we install may harm
Claude Code"). Until the probe in §18 says otherwise, `can_set_title` is
`False` for every engine, the rename is stored locally, and **the UI says so**:
a small `local only` marker beside a renamed session rather than a silent
half-success. If the probe passes, `title_synced_at` records the write-back and
the marker disappears.

This is why `title` is one field with a `title_source` rather than two columns:
the display rule stays a single precedence check no matter which of the three
wrote it, and adding an engine that *can* rename changes a capability flag, not
the schema.

### `work_item`

| field | type | null | notes |
|---|---|---|---|
| `id` | TEXT PK | no | ours, ulid |
| `owner_id` | TEXT | no | |
| `provider` | TEXT enum | no | `jira` \| `notion` |
| `external_id` | TEXT | no | **UNIQUE with `provider`** — the reconcile upsert key |
| `workspace_id` | TEXT FK | **yes** | null until mapped |
| `project_ref` | TEXT | no | Jira project key · Notion `database_id` |
| `title` · `url` | TEXT | no | |
| `body` | TEXT | **yes** | |
| `status_raw` | TEXT | no | the provider's own string, **verbatim** — write-back needs it exact |
| `status_class` | TEXT enum | no | `open` \| `in_progress` \| `in_review` \| `in_qa` \| `blocked` \| `done` \| `cancelled` \| `orphaned` |
| `kind_raw` | TEXT | no | `"Epic"`, `"Story"`, `"Sub-task"`, a Notion select — verbatim (D23) |
| `kind_class` | TEXT enum | no | `container` \| `work` \| `unknown`. **`work` is what makes it dispatchable** |
| `parent_external_id` | TEXT | **yes** | hierarchy, as the provider reports it |
| `priority` | INTEGER | **yes** | normalized 1 (highest) … 5 |
| `assignee` | TEXT | **yes** | |
| `labels` | TEXT **JSON** | no | `[]` |
| `raw` | TEXT **JSON** | no | untouched provider payload — a field you want in six months costs no migration |
| `external_updated_at` · `synced_at` | TEXT | no | `external_updated_at` drives the sync cursor |
| `shipped_at` | TEXT | **yes** | reserved; only a future `DeployProvider` sets it |
| `claimed_by_session_id` | TEXT FK | **yes** | the claim, folded in — no separate table |
| `claimed_at` · `claim_expires_at` | TEXT | **yes** | expiry frees a dead worker's item with no reaper logic |
| `attempt` | INTEGER | no | default `0` |

Claiming is a **conditional write**, which is what makes double-claiming
impossible without a second table:

```sql
UPDATE work_item
   SET claimed_by_session_id = ?, claimed_at = ?, claim_expires_at = ?,
       attempt = attempt + 1
 WHERE id = ? AND (claimed_by_session_id IS NULL OR claim_expires_at < ?);
```

Zero rows changed means another worker won. No application logic to get wrong.

### `queue`

Runtime-editable configuration, not a config file: you edit it from the UI and
it holds a credential reference. Arrives with M5.

| field | type | null | notes |
|---|---|---|---|
| `id` | TEXT PK | no | |
| `owner_id` | TEXT | no | |
| `name` | TEXT | no | |
| `workspace_id` | TEXT FK | no | a queue belongs to exactly one workspace |
| `provider` | TEXT enum | no | `jira` \| `notion` |
| `provider_config` | TEXT **JSON** | no | the query plus the field, status, and kind maps (§10) |
| `credential_ref` | TEXT | no | opaque handle; **never a secret** |
| `priority_rule` | TEXT enum | no | `priority_then_age` \| `age` \| `external_rank` |
| `max_parallel` | INTEGER | no | default `1` |
| `enabled` | BOOLEAN | no | default **`FALSE`** — a new queue never auto-drains |
| `writeback` | TEXT **JSON** | no | per-outcome comment / status policy (§10) |
| `sync_interval_s` | INTEGER | no | default `300` |
| `sync_cursor` | TEXT | **yes** | |
| `last_sync_at` · `last_sync_error` | TEXT | **yes** | surfaced in Settings, not silently swallowed |

### `app_state`

A key/value row store for the handful of singletons that have no other home —
`master_session_id` (referenced by §11's `resume=`), `autonomy_level`,
`master_last_turn_at` (D31), and the schema's own bookkeeping. Six rows, not six
thousand.

| field | type | null | notes |
|---|---|---|---|
| `key` | TEXT PK | no | |
| `value` | TEXT **JSON** | no | |
| `updated_at` | TEXT | no | |

### Indexes

Each maps to a query this document already describes.

```sql
CREATE UNIQUE INDEX ux_repo_path      ON repo(root_path);
CREATE        INDEX ix_session_fleet  ON session(workspace_id, state);
CREATE        INDEX ix_session_item   ON session(work_item_id);      -- matrix cross-tab
CREATE UNIQUE INDEX ux_item_external  ON work_item(provider, external_id);
CREATE        INDEX ix_item_candidate ON work_item(status_class, kind_class);
```

SQLite gained `FULL OUTER JOIN` in 3.39; if the shipped runtime is older, the
matrix falls back to two `LEFT JOIN`s and a `UNION`. Verify in M1.

### Logs — the other half of the data layer (D25)

```
~/Library/Application Support/shepherd/
  shepherd.db
  logs/stops/2026-09-11.jsonl     evidence + the conclusion drawn from it    90 d
  logs/audit/2026-09-11.jsonl     every action authorize() allowed or denied 90 d
  logs/replay/2026-09-11.log      what changed when a rule was fixed         90 d
  logs/daemon/controld.log        ordinary operational logging               14 d
  sessions/<id>/pty.log           terminal scrollback, ring file             (§9)
```

Daily rotation, gzip on close, size cap as a second trigger. A `stops` record is
a few KB: the stop metadata, the last assistant message, the task counts, and
the verdict produced. That is what `shepherd replay` reads — kilobytes per session
instead of gigabytes per day. A reader **skips malformed trailing lines**; a
daemon killed mid-write leaves one.

### Migrations

Forward-only numbered SQL files in `store/migrations/`, applied in one
transaction at `controld` startup.

```sql
CREATE TABLE schema_migration (
  version INTEGER PRIMARY KEY, name TEXT NOT NULL,
  checksum TEXT NOT NULL, applied_at TEXT NOT NULL);
```

Three rules, each guarding a failure that is hard to debug later:

1. **Checksum mismatch on an applied migration → refuse to start.** History was
   edited; guessing is worse than stopping.
2. **Database version newer than the binary → refuse to start.** launchd will
   happily run yesterday's binary after a failed upgrade, and old code reading a
   new schema corrupts quietly.
3. **`sessiond` never migrates.** It waits for `controld` to report the expected
   version over the UDS. Two processes racing one migration is the bug you
   cannot debug at 2am.

---

## 8. Signals and the stop-reason engine

This is the differentiator. Everything here rests on Claude Code's hook system,
whose contract was verified against the official docs on 2026-09-08.

**Nothing in this section is stored as an event (D24).** Each arriving event
updates a column on `session` and is then discarded. Only at *stop* is evidence
written down, and it goes to the stop log (D25), not a table.

| event | what it updates, immediately |
|---|---|
| any event | `last_event_at` — the liveness clock |
| `SessionStart` | registers an `attached` session: `engine_session_id`, `cwd` → `repo_id` by longest prefix (D22) |
| `UserPromptSubmit` | `brief`, when we did not write one ourselves |
| `Notification` / `PermissionRequest` | `state = needs_you` + `needs_you_reason` |
| `TaskCreated` / `TaskCompleted` | `tasks_total` / `tasks_done` |
| `SubagentStart` / `SubagentStop` | `active_subagents` |
| `FileChanged` | appends to `repos_touched` |
| `Stop` / `StopFailure` / `SessionEnd` | triggers classification (below) |

The expanded subagent list, and anything else you drill into, is read from the
engine's transcript on demand — for the one session you opened, not for all of
them on every render.

### Hook installation: one dispatcher, all events

CCC installs two hook scripts. We install **one** — `hookd.py` — registered for
every event we need. It reads the JSON on stdin, writes it to `sessiond`'s UDS
with a **250 ms timeout**, and **always exits 0**:

```python
def main() -> None:
    try:
        payload = sys.stdin.read()
        send_uds(payload, timeout=0.25)
    except BaseException:
        pass
    sys.exit(0)
```

A hook that can block or fail Claude Code is unacceptable; this one can do
neither (principle 4).

**Events subscribed:**

| Purpose | Events |
|---|---|
| liveness | `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `MessageDisplay` |
| needs-you | `Notification`, `PermissionRequest`, `PermissionDenied`, `Elicitation`, `ElicitationResult` |
| stop | `Stop`, `StopFailure`, `SessionEnd` |
| subagents | `SubagentStart`, `SubagentStop` |
| progress | `TaskCreated`, `TaskCompleted` |
| context | `PreCompact`, `PostCompact` |
| identity | `SessionStart`, `UserPromptSubmit`, `CwdChanged`, `PreModelSwitch`, `PostModelSwitch` |
| changes | `FileChanged` |

`SessionStart` is what binds an `external` session to a repo and its workspace — it carries
`session_id` and `cwd`, so a hand-launched session registers itself on its first
turn with no filesystem polling.

**Common fields on every hook event:** `session_id`, `prompt_id`,
`transcript_path`, `cwd`, `permission_mode`, `effort.level`, `hook_event_name`,
and — **when inside a subagent** — `agent_id` and `agent_type`.

### `state` — three live values, hard signals only

| state | rule |
|---|---|
| `needs_you` | last signal is `Notification` with `notification_type` ∈ {`permission_prompt`, `idle_prompt`, `agent_needs_input`, `elicitation_dialog`, `elicitation_url_dialog`}, or an unresolved `PermissionRequest` |
| `stopped` | `Stop`, `StopFailure`, `SessionEnd`, or observed process exit |
| `running` | any tool/message signal within `LIVENESS_WINDOW_S` (90), or pty output within it |
| `starting` | set at spawn; holds until the first signal of any kind arrives, or `SPAWN_TIMEOUT_S` (60) elapses → then `stopped` / `crashed` |

**`needs_you` outranks `stopped`.** A session waiting on a permission prompt is
not finished — it is blocked on you, and it sorts to the top.

`notification_type` distinguishes `permission_prompt` from `idle_prompt`. Those
are different asks and the UI must say which: *"needs permission: Bash(git
push)"* vs *"idle — waiting for your next instruction."*

### `stop_reason` — mechanical, confidence 1.0

`StopFailure` carries an `error_type` whose allowed values map almost
one-to-one onto the reasons you want:

| `stop_reason` | rule | `outcome_class` |
|---|---|---|
| `rate_limited` | `StopFailure.error_type` ∈ {`rate_limit`, `overloaded`} | `paused` |
| `quota_paused` | `Notification` ∈ {`quota_auto_resume_fired`, `quota_auto_resume_stale`, `quota_auto_resume_disabled`} | `paused` |
| `auth_failed` | ∈ {`authentication_failed`, `oauth_org_not_allowed`} | `error` |
| `account_blocked` | ∈ {`account_on_hold`, `billing_error`} | `error` |
| `bad_request` | ∈ {`invalid_request`, `model_not_found`} | `error` |
| `server_error` | `= server_error` | `error` |
| `truncated` | `= max_output_tokens`, or `Stop.stop_reason = max_tokens` | `unfinished` |
| `stalled_pending_tool` | `Stop.stop_reason = tool_use` — stopped holding an unexecuted tool call | `error` |
| `crashed` | process exit ≠ 0 with no preceding `Stop`/`StopFailure` | `error` |
| `killed` | we sent the signal (recorded in `action_log`) | `unfinished` |
| `context_exhausted` | `PreCompact{auto}` with no `PostCompact` before death | `unfinished` |
| `user_exited` | `SessionEnd.end_reason = prompt_input_exit` | `unfinished` |
| `cleared` | `SessionEnd.end_reason = clear` | `unfinished` |
| `logged_out` | `SessionEnd.end_reason = logout` | `error` |
| `resumed_elsewhere` | `SessionEnd.end_reason = resume` | `unfinished` |
| `unknown` | `StopFailure.error_type = unknown`, or nothing matched | `error` |

`quota_paused` shows the resume time rather than an error — it is not a failure
and it recovers itself.

### The completeness split — only when `Stop.stop_reason = end_turn`

The one thing no mechanical rule can settle.

| `stop_reason` | meaning | `outcome_class` |
|---|---|---|
| `completed` | did what was asked | `finished` |
| `incomplete` | open work remains | `unfinished` |
| `derailed` | believed it finished, but did something else | `unfinished` |
| `blocked_external` | finished its part, waiting on something outside | `blocked` |

**Heuristics — free, always run:**

1. **Open task ledger.** `TaskCreated` minus `TaskCompleted`. Stopped with 3
   tasks open is `incomplete`, mechanically, no LLM. Strongest and cheapest.
2. **Unkept promise.** `Stop.last_assistant_message` says "I'll now run…",
   "next I'll…", "let me…" with no matching `PostToolUse` after it. Catches
   "the agent didn't dispatch what it meant to dispatch."
3. **Failure tail.** Last 3 signals are `PostToolUseFailure` on the same tool →
   it gave up, not finished.
4. **No-op session.** Zero `Edit`/`Write` calls on a session whose brief asked
   for changes.
5. **Blocked phrasing.** Last message matches review/merge/CI/deploy waiting
   language *and* zero open tasks → candidate `blocked_external`.

**`blocked_external` detection, best source first (D18):**

1. **Self-declared** — the session calls `report_blocked(waiting_on, detail,
   expect_by?)` where `waiting_on` ∈ `merge` | `review` | `ci` | `deploy` |
   `person` | `external_service` | `other`. `source='declared'`, confidence 1.0.
2. **Provider-derived, free** — the linked work item's `status_class == 'blocked'`.
   No inference needed and we already sync it.
3. **LLM verdict** — returns `blocked_external` plus `waiting_on`.

> **Deferred past M2 (D34).** Everything above this line ships as specified —
> the mechanical table, the five heuristics, and the `blocked_external` sources
> 1 and 2 all run with no model and no credential. The lane described below is
> **not built in v1**: on `end_turn` the heuristics decide, `decided_by` is
> `'heuristic'`, and what they cannot settle lands as `unknown` and is counted.
> **No `Classifier` seam is written for it** — an interface with zero
> implementations behind it is D9's mistake in its purest form. Instead the model
> call has exactly **one named call site**, `signals/verdict.py::classify_end_turn()`,
> which today returns the heuristic result unchanged. Building the lane means
> filling that function in; nothing else in the system moves. The `unknown` rate
> on the fleet page is what tells you when it is worth doing.

**The model verdict** — `claude-haiku-4-5` over the **transcript tail** (last
~20 entries, which the engine already wrote to disk) plus the task ledger.

**It runs only when `Stop.stop_reason = end_turn`.** Every mechanical reason in
the table above resolves with certainty and costs nothing — a rate limit, a
crash, an auth failure, and an exit code are not in the text and must never be
guessed at. That short-circuit is what keeps the common case free.

> **This is the only API-billed path in the system.** Everything else runs on the
> local Claude Code subscription. The verdict lane therefore needs an Anthropic
> API credential and is **optional by construction**: if
> `Credentials.available("anthropic") is False`, the classifier runs
> heuristics-only, every verdict carries `source='heuristic'`, and the UI
> replaces `[why?]` with a one-time note that an API key enables it. A missing
> key degrades precision; it never breaks classification.

```jsonc
// in
{ "task_brief": "…", "last_assistant_message": "…",
  "open_tasks": ["update schema.gql", "specs"],
  "tool_ledger_summary": {"Bash": 43, "Edit": 12, "Write": 0},
  "failures": ["PostToolUseFailure Bash ×3"] }

// out
{ "state": "completed" | "incomplete" | "derailed" | "blocked_external",
  "waiting_on": "review" | null,
  "confidence": 0.0,
  "why": "<one line, max 120 chars>",
  "missing": ["<what was asked but not done>", "…"],
  "next_actions": [ { "text": "<imperative, max 80 chars>",
                      "kind": "retry|resume|respawn|inspect|external|requeue|escalate",
                      "target": null } ] }   // max 3, see next_actions[] below
```

`missing[]` is what a queue worker feeds back as context on a requeue, and what
the UI shows under a violet row.

### `next_actions[]` — what to do about it (D21)

Every verdict whose `state = 'stopped'` carries **one to three action items**.
This is not an LLM feature: the mechanical `stop_reason` already determines the
obvious move for most stops, so the list is a lookup, computed for free, in the
same pass that sets `outcome_class`.

```jsonc
// verdict.next_actions — ordered, most useful first, max 3
[ { "text": "Re-run: it promised specs and never ran them",   // ≤80 chars, imperative
    "kind": "respawn",          // retry | resume | respawn | inspect
                                // | external | reauth | escalate | requeue | none
    "target": null,             // url for `external`, tool arg for the others
    "source": "heuristic" } ]   // heuristic | llm | declared
```

`kind` is what makes the row a **button** rather than a sentence — the fleet UI
renders the first item as an affordance and the rest as text.

**The default table — one row per `stop_reason`, always applied:**

| `stop_reason` | default action items |
|---|---|
| `completed` | *(empty when confidence ≥ 0.8)* · else `Review the diff` (`inspect`) |
| `incomplete` / `derailed` | one item per `missing[]` entry, truncated to 3 · `Requeue with what's missing` (`requeue`) |
| `blocked_external` | `Chase <waiting_on>` (`external`, `target` = MR / work-item url) |
| `rate_limited` / `quota_paused` | `Resumes <time> — nothing to do` (`none`) · `Retry now` (`retry`) |
| `truncated` | `Resume — output hit the token cap` (`resume`) |
| `context_exhausted` | `Re-spawn with a compacted brief` (`respawn`) |
| `crashed` | `Read the last 50 lines` (`inspect`) · `Re-spawn from the last good commit` (`respawn`) |
| `stalled_pending_tool` | `Open logs — a tool call never executed; likely a bug` (`inspect`) · `Escalate` (`escalate`) |
| `killed` | `Re-spawn with the remaining brief` (`respawn`) |
| `user_exited` / `cleared` / `resumed_elsewhere` | `Resume the session` (`resume`) |
| `auth_failed` / `logged_out` | `Re-authenticate <provider>` (`reauth`) |
| `account_blocked` | `Check billing` (`external`) |
| `bad_request` | `Inspect the request — model or args rejected` (`inspect`) |
| `server_error` | `Retry` (`retry`) |
| `unknown` | `Open logs` (`inspect`) · `Run shepherd replay after fixing the rule` (`inspect`) |

**LLM refinement, when it runs.** The classifier prompt (above) gains a
`next_actions` key in its output; when the LLM lane fires, its items **replace**
the defaults for `completed` / `incomplete` / `derailed` / `blocked_external`
(where a generic sentence is weakest) and are **merged behind** the defaults for
every mechanical reason (where the default is already right). Items always carry
their `source`, so the UI can show which line a model wrote.

**Ordering guarantee:** a `declared` item (from `report_blocked`) outranks an
`llm` item, which outranks a `heuristic` one. Deduped on `kind` + `target`.

Because the list lives on the verdict, `shepherd replay` regenerates it — improving
the table retroactively fixes every historical row, same as any other rule (§8
Replay).

### Replay

```
$ shepherd replay --since 30d --classifier h-8
  reclassified 412 sessions
  changed 37:  unknown → stalled_pending_tool (31)
               completed → incomplete (6)
               completed → blocked_external (1)
  unknown rate: 8.2% → 0.7%
```

Replay reads the **stop log** (D25) — a few KB per session — re-runs the current
classifier over each record, overwrites the `stop_*` columns on `session`, and
writes the before/after diff to `logs/replay/`. The diff is the review artifact;
it is a file you read, not a table you query. The `unknown` rate is a
first-class metric on the fleet page — it *is* the tuning backlog (principle 5).

---

## 9. Session I/O

### LocalRunner: tmux (D14)

Each `owned` session is a tmux session named `shepherd:<session_id>`.

| Problem | How tmux solves it |
|---|---|
| Survive `sessiond` restart/upgrade | the tmux server is its own process |
| Correct resync on late attach | `capture-pane -e -p -S -2000` returns the current screen **with ANSI intact** plus scrollback. A raw pty gives a byte firehose with no way to reconstruct the screen for a client that connects late — you would need a server-side terminal emulator |
| Real "jump to terminal" | `tmux attach -t shepherd:<id>` and you are driving it by hand. CCC fakes this with AppleScript keystroke injection into Terminal.app |
| Alt-screen + resize + reflow | already handled; Claude Code's TUI uses the alternate screen |

Fallback `PtyRunner` behind the same interface if tmux is unavailable —
degraded (no late-attach resync), and the UI says so.

### Terminal fidelity in the browser

```
browser ──WS──► sessiond
  on connect:  snapshot(2000 lines) ──► xterm.js write
  then:        live byte stream ─────► xterm.js write
  keystrokes:  ──► write policy ──► pty
```

`xterm.js` renders the same bytes your terminal renders — not a re-render of a
transcript. Status line, spinners, box-drawing, colours, cc10x output: identical.

`attached` sessions have no pty. The pane falls back to a rendered transcript
with a banner: *"read-only — this session wasn't started here. Open it in the
platform to get a terminal."*

### Write policy — the part that must not be wrong

| session state | programmatic send | explicit interrupt |
|---|---|---|
| `stopped` | write immediately | n/a |
| `needs_you` | write immediately (it is *asking* you) | n/a |
| `running` | **queue to mailbox**, deliver at next `Stop` | allowed, requires confirmation |

You typing in the terminal pane is a **direct write and bypasses the queue** —
it is your keyboard, you own the consequences. Programmatic writes
(orchestrator, worker, sibling session) always go through the policy. The
asymmetry is deliberate.

### Mailbox — the one delivery path (D12)

Delivery trigger is the `Stop` hook: the moment we *know* the turn ended.
Pending messages for that session are **coalesced into one write** — five queued
notes become one message with five bullets, not five interrupting turns. A
dormant target with a pending message is resumed on demand.
`idempotency_key` means a retrying caller never double-delivers.

### Channels — fan-out, not a second mechanism

Posting to a channel writes one `channel_message` and fans out one
`mailbox_message` per active member. **Channels have no delivery code of their
own** — same policy, same coalescing, same idempotency. The channel is the
addressing layer; the mailbox is the transport.

Members read history via the `channel_history` tool, so a session joining late
catches up without anyone pasting anything.

### `ask()` — synchronous, and it never touches the target (D13)

```
ask(session_id, question, timeout_ms) -> { text, method, from_fork_of, duration_ms }
```

**Implementation: fork the target's session**, put the question to the fork,
return its answer, discard the fork. (Claude Code supports forking — the
`SessionStart` hook's `start_reason` enum includes `fork`.)

Why not "message the target and wait": the target is never interrupted, its
context is never polluted by the question, and latency is one turn instead of
however long its current turn takes. Cost: one forked context's tokens.

Forks are `ephemeral = TRUE`, `origin = 'ask_fork'`, and hidden from the fleet
view by default — otherwise every `ask` litters the board.

**Fallback:** when `EngineCapabilities.can_fork` is `False`, `ask` degrades to
mailbox-and-wait with the timeout. The response's `method` field reports
`"fork"` or `"mailbox"`, so it is never a silent downgrade.

---

### 9.5 Who talks to whom — the complete list

Every path between the master, a session, and you. There are no others.

**Master → session**

| action | mechanism |
|---|---|
| spawn | `spawn_session(...)` — recursion caps enforced inside the tool |
| talk to it mid-run | `send_to_session()` → the write policy above: immediate when stopped or `needs_you`, **queued to the mailbox when running** |
| ask it something | `ask_session()` → forks the target (D13); never interrupts it |
| interrupt · kill | `interrupt_session()` · `kill_session()` — `local_destructive` |
| broadcast | `post_to_channel()` → fans out into each member's mailbox |
| read | `get_session`, `get_session_output`, `get_session_evidence` |

**Session → master, or → you**

| action | mechanism |
|---|---|
| escalate to a human | `request_help(question, options[])` → a Needs-You card; the session ends its turn |
| declare it is blocked | `report_blocked(waiting_on, detail)` → `source='declared'`, confidence 1.0 |
| reach a platform | `ask_orchestrator()` → **brokered tool call, not a master turn** (below) |
| report its outcome | implicit — Analysis writes the conclusion when it stops |

**When a session stops (D31)**

```
session stops
  ├─ spawned by a queue   → the worker loop routes it        (§10, unchanged)
  └─ spawned by the master
       outcome finished / paused / blocked / needs_you → nothing wakes
       outcome unfinished / error
            level 2 → added to the wake set; the master is handed
                      "while you were away: …" at the start of your next turn
            level 3 → the master is woken now, acts, and logs
                      hard cap: attempt < 2 along the `retry_of` chain
```

The wake set is **a query, not a table**: master-owned sessions whose `ended_at`
is later than `app_state.master_last_turn_at` and whose `outcome` is
`unfinished` or `error`. Draining it stamps a new `master_last_turn_at`.

`needs_you` is excluded on purpose. That is the human's rail, and routing it to
an agent would hide the one thing the platform exists to show you.

---

## 10. Queues, work-item providers, and workers

### Field mapping is per-source, not per-provider

Notion property names are arbitrary per database, so mapping is config stored on
the queue.

```jsonc
// queue.provider_config — Notion
{
  "database_id": "…",
  "filter": { "property": "Status", "status": { "does_not_equal": "Done" } },
  "map": {
    "title": "Name", "body": "Description", "status": "Status",
    "priority": "Priority", "assignee": "Owner"
  },
  "status_class": {
    "Not started": "open", "In progress": "in_progress",
    "In review": "in_review", "QA": "in_qa",
    "Blocked": "blocked", "Done": "done", "Cancelled": "cancelled"
  },
  "priority_map": { "P0": 1, "P1": 2, "P2": 3, "P3": 4 }
}
```

```jsonc
// queue.provider_config — Jira
{
  "site": "https://<your-site>.atlassian.net",
  "jql": "project = OXDEV AND statusCategory != Done AND assignee = currentUser()",
  "status_class": {
    "To Do": "open", "In Progress": "in_progress",
    "Code Review": "in_review", "In QA": "in_qa",
    "Blocked": "blocked", "Done": "done", "Won't Do": "cancelled"
  },
  "priority_map": { "Highest": 1, "High": 2, "Medium": 3, "Low": 4, "Lowest": 5 }
}
```

Adding a third provider = one class + one config shape. Nothing else changes.

### Reconcile (D4, D6)

Every `sync_interval_s` (default 300) plus manual refresh, per queue:

1. `list(query, since=queue.sync_cursor)` → work items with
   `external_updated_at > cursor`.
2. Upsert on `(provider, external_id)`. **Provider wins on content, always.**
3. Advance `sync_cursor` to `max(external_updated_at)`.
4. Work items that dropped out of the query (closed, reassigned, moved) get a fresh
   `get`; a 404 marks them `status_class='orphaned'`. **Nothing silently
   lingers** — that is the drift failure of a naive mirror.
5. A work item with a live claim that went `done` externally → the claim is revoked
   (`release_kind='revoked'`) and the running worker gets a mailbox message:
   *"OXDEV-1234 was closed in Jira by someone else. Stop and report."*
6. A work item leaving `status_class='blocked'` re-enters the candidate set
   automatically — that is how a parked work item unparks.

### Write-back

```jsonc
// queue.writeback
{
  "on_claim":     { "comment": true,  "set_status": "In Progress" },
  "on_completed": { "comment": true,  "set_status": "In Code Review" },
  "on_blocked":   { "comment": true,  "set_status": "Blocked" },
  "on_escalated": { "comment": true,  "set_status": null },
  "on_requeued":  { "comment": false, "set_status": null }
}
```

Every write-back is an `external` action → passes `authorize()` → level 2 asks,
level 3 auto-approves and logs (D8).

### Two independent timers

`controld` runs **reconcile** (per queue, `sync_interval_s`, default 300 s) and
the **worker tick** (per queue, short) as separate loops on purpose: a provider
outage must not stall a worker that is already running, and a slow worker must
not delay the mirror.

### Who may write the mirror

**B10 — the sync loop — is the only writer to `work_item`.** A connector (D20)
may read anything and comment on anything, but it must never write into the
mirror. Two writers on one row means the sync cursor starts lying about what it
has seen, and that failure is silent. Write-backs go *out* through the provider
and come *back* on the next reconcile, like every other external change.

### The worker loop (D7, D15)

**The worker has no intelligence and never touches code.** It selects, claims,
spawns, and then routes the resulting verdict — that last step is its whole
value, because it is what turns "a session stopped" into "the work moved"
without you in the loop.

```python
def tick(queue: Queue) -> None:
    if not queue.enabled or active_claims(queue) >= queue.max_parallel:
        return
    item = next_candidate(queue)          # status_class == 'open', no live claim
    if item is None:
        return
    claim = acquire(item)                 # atomic INSERT; loses harmlessly on conflict
    if claim is None:
        return
    writeback(queue, "on_claim", item)
    worktree = make_worktree(workspace, item)     # <repo>-wt/<KEY>/ on feat/<KEY>
    brief = build_brief(item, workspace, prior_attempts(item), memory_sections=[])
    ref = f"{item.provider}:{item.external_id}"        # e.g. "jira:OXDEV-1234"
    session = spawn_session(project, brief, cwd=worktree,
                            work_item_ref=ref, origin="queue_worker")
    claim.session_id = session.id
```

`build_brief()` is the **memory seam** (D7): a future memory provider fills
`memory_sections` and nothing else changes.

Worktrees are created at claim, removed on `completed`, and **kept on
escalation** so you can inspect what happened.

### Verdict routing — one table, no ad-hoc branches

| verdict | action | write-back |
|---|---|---|
| `completed`, confidence ≥ 0.8 | release `completed` | `on_completed` |
| `completed`, confidence < 0.8 | escalate to Needs-You with the verdict | none |
| `incomplete` / `derailed` | `attempt < 2` → requeue with `missing[]` attached; else escalate | `on_requeued` |
| **`blocked_external`** | release `blocked`, **do not retry**, **free the worker slot**, park the work item out of the candidate set until its external state changes | `on_blocked` |
| `rate_limited` / `quota_paused` | release, back off to the resume time, retry | none |
| `crashed` / `server_error` | `attempt < 2` → requeue; else escalate | none |
| `auth_failed` / `account_blocked` | **disable the queue**, alert the user | none |
| `stalled_pending_tool` | escalate immediately — a bug, not a retry candidate | none |
| `bad_request` / `truncated` | escalate | none |
| claim expired | requeue, `attempt += 1` | none |

Two rows earn special mention. **`auth_failed` disables the whole queue**:
without that, a broken credential burns every work item into a failure within
minutes. **`blocked_external` neither retries nor holds a slot**: without that, a
blocked work item either occupies a worker forever or gets retried into the same
wall twice.

---

## 11. Orchestrator, tool surface, and the authorize gate

### 11.0 The tool registry (D32)

Five consumers need the same ~25 capabilities, and every one of them must pass
through `authorize()` and land in the audit log:

| consumer | what it is |
|---|---|
| the master | a language model deciding what to do |
| a tier-2 session | also a language model, in a process we do not control |
| `web/` | a human clicking |
| `cli/` | a human typing |
| a queue worker | plain Python |

Two of the five are models, and a model cannot call a Python function — it emits
*"call `spawn_session` with these arguments"* and something must have described
the tools to it beforehand and route the call back. **That, and only that, is why
MCP appears in this system.** It appears in two places for two different reasons:

- **Tier-2 sessions — forced, and correct.** Claude Code is a program we do not
  control and MCP over stdio is the contract it speaks. Codex speaks it too.
  Nothing about this binding is a choice, and it does not change.
- **The master — incidental.** This is our Python, our model, our process. MCP is
  there only because the Agent SDK happens to accept tools as
  `create_sdk_mcp_server(...)`. An OpenAI loop wants a JSON functions array; a
  raw Messages API loop wants Anthropic's `tools=[…]`.

So MCP is **an output format, not an input type**. Four layers, and only the last
knows a vendor exists.

**① The capability** — plain, typed, vendor-free:

```python
def spawn_session(project_id: str, task: str, model: str | None = None) -> SessionRef: ...
```

**② The registry** — each capability declared exactly once, in our vocabulary:

```python
@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict                  # plain JSON Schema
    blast_class: BlastClass             # local_read | local_write | local_destructive | external
    handler: Callable[..., Any]
    audiences: frozenset[Audience]      # {MASTER, SESSION} — replaces the SESSION_TOOLS list
```

**③ `invoke()` — the chokepoint.** The only way any tool ever runs:

```python
def invoke(name: str, args: dict, ctx: CallerContext) -> ToolResult:
    tool = REGISTRY[name]
    require_audience(tool, ctx.audience)          # a session cannot reach a master-only tool
    decision = authorize(tool, args, ctx)         # blast class × autonomy level
    if not decision.allowed:
        return ToolResult.denied(decision.reason)
    result = tool.handler(**args)
    audit(tool, args, ctx, decision, result)
    return result
```

**④ Exporters** — thin translators, roughly 30 lines each, that map `ToolDef`
fields into a target shape and wrap the call in `invoke()`:

```python
to_sdk_mcp_server(tools)      # AgentSDKMaster            — v1
to_stdio_mcp_server(tools)    # shepherd-mcp, tier-2 sessions — v1, and forced
to_openai_functions(tools)    # a future OpenAI-backed ApiLoopMaster
to_anthropic_tools(tools)     # a future raw Messages API loop
to_http_routes(tools)         # web/
to_cli_commands(tools)        # cli/
```

Adding a vendor is a new exporter beside the others. Nothing above layer ④ moves.

**Three things this buys beyond vendor-swapping**, each of which removes a list
someone would otherwise have to keep in sync by hand:

1. **Audience is a field, not a literal list.** "A tier-2 session cannot kill
   anything" becomes a property of the registry rather than a `SESSION_TOOLS`
   array that drifts.
2. **Blast class cannot be missed.** It is a required field on `ToolDef`, so a
   tool without one does not typecheck — stronger than §11's `lookup()` with an
   `external` default, which still relies on someone registering the tool.
3. **Principle 1 becomes structural.** Generate `web/`'s routes and `cli/`'s
   subcommands from the same registry and "no consumer gets a private read path"
   stops being a discipline: a capability absent from the registry has no surface
   that can reach it. This is the specific erosion the three L5 siblings invite.

**Connectors fit without a special case.** A connector (D20) genuinely *is* a
third-party MCP server — that is its nature, not our choice. Its advertised tools
are **imported into the registry** as `ToolDef`s with `blast_class=external` and
`audiences={MASTER}`, so connector calls route through the same `invoke()` as
everything else. That is what D20's "one auth surface, one audit trail" already
asks for, and it means a non-MCP master gets connector access for free rather
than not at all.

### Master configuration (D10, D30)

The block below configures `AgentSDKMaster`, the v1 implementation of the
`MasterRuntime` seam (§6). `ApiLoopMaster` — `api_key` plus `base_url`, any
vendor, per-token billing — satisfies the same Protocol and is selected by
config; it is defined and unbuilt (§17). Which implementation is active is the
single place "seat or API, and whose model" is decided.

**Everything MCP-shaped below is produced inside this implementation** by
`to_sdk_mcp_server()` and `connector_tool_allowlist()` from the §11.0 registry —
it is `AgentSDKMaster`'s business, not the seam's. `configure(tools,
system_prompt)` is what the orchestrator hands it (D32).

```python
ClaudeAgentOptions(
    model="claude-opus-5",
    system_prompt=ORCHESTRATOR_PROMPT,
    setting_sources=[],                          # no CLAUDE.md, no cc10x, no skills
    disallowed_tools=["Agent", "Task"],          # cannot dispatch subagents
    allowed_tools=[f"mcp__shepherd__{t}" for t in ORCHESTRATOR_TOOLS]
                 + connector_tool_allowlist(),          # D20, resolved at mount
    mcp_servers={"shepherd": create_sdk_mcp_server(name="shepherd", tools=SHEPHERD_TOOLS),
                 **mount_enabled_connectors()},         # D20
    can_use_tool=authorize,
    resume=state.master_session_id,              # survives daemon restarts
    cwd=None,                                    # it delegates; it does not edit
)
```

`allowed_tools` stays a strict allowlist: `mcp__shepherd__*` plus, for each
**enabled** connector, exactly the tools that connector advertises and its
`tool_allowlist` permits. **The master still has no Read, Write, Edit, Bash, or
WebFetch** — it cannot touch the filesystem. Every capability it has is a tool we
wrote or a connector you explicitly turned on.

**Module boundary (D19).** Everything in this section lives in a `master/`
package that imports only `toolsurface.client` and the Agent SDK. It may not
import `store`, `signals`, `queues`, or `runner`. `test_master_isolation.py`
walks the module's imports and fails the build on a violation — the same test
that asserts `setting_sources=[]` really isolates it (§18).

The master's session id is persisted, so `resume` gives one continuous
orchestrator conversation across restarts, reboots, and upgrades.

**Auth caveat, recorded deliberately.** The Agent SDK runs the Claude Code
harness locally and picks up local Claude Code credentials — the user's
subscription. Anthropic's Agent SDK docs state: *"Unless previously approved,
Anthropic does not allow third party developers to offer claude.ai login or rate
limits for their products, including agents built on the Claude Agent SDK."*
Personal single-user use on one's own machine is ordinary use. **The future
multi-user deployment cannot proxy one subscription to other people** — each user
brings their own credential, or that deployment uses API keys. This is exactly
what the `Credentials` seam (D11) exists for.

### Connectors (D20)

The master can be given tools it did not write, the way Claude Desktop does it:
a **list of supported platforms**, each a row you toggle on.

```
Settings → Connectors
  ┌──────────────────────────────────────────────────────────────┐
  │ ⬤ Jira          atlassian.net           ok        [ ⚙ ][ ⏻ ] │
  │ ⬤ Datadog       app.datadoghq.com       ok        [ ⚙ ][ ⏻ ] │
  │ ○ GitLab        gitlab.com              —         [connect ] │
  │ ○ Slack         slack.com               —         [connect ] │
  │ ○ Notion        api.notion.com          —         [connect ] │
  │ ⬤ Figma         figma.com          auth_error     [ reauth ] │
  └──────────────────────────────────────────────────────────────┘
```

Rules, all of them load-bearing:

1. **Catalogue, not free text.** v1 ships a fixed list of `connector` rows
   (§7). You cannot paste an arbitrary MCP command into the UI — that is a
   remote-code-execution surface behind a text box. A custom-connector escape
   hatch is a config-file-only, deferred item (§17).
2. **Credentials by reference.** `connect` runs the platform's OAuth or takes a
   token, stores it via `Credentials.store()`, and keeps only a
   `credential_ref`. The token is resolved once, inside the MCP launcher, in the
   master's process. It never enters the DB, the audit log, the master's
   context, or a response body.
3. **Every connector tool defaults to blast class `external`** — level 2 asks,
   level 3 auto-approves and logs (D8). Per D32 the blast class is a **required
   field on the `ToolDef`**, not a lookup table that can miss: importing a
   connector's tools into the registry stamps `external` on each one, the safe
   direction, and a tool with no class does not typecheck. Read-only tools can be
   demoted per-tool via `connector.blast_overrides` once you have seen them
   behave.
4. **Health is polled, not assumed.** A connector that fails to mount or returns
   an auth error is marked in the list and its tools drop out of
   `allowed_tools` — the master is told they are unavailable rather than
   watching calls fail.
5. **Enabling or disabling a connector is itself `local_destructive`** and
   remounts the master's MCP servers on the next turn boundary, never mid-turn.

**Tier-2 access — brokered, never attached.** A tier-2 session that needs a
connector calls:

```
ask_orchestrator(question, connector_hint?) -> { text, answered_by, duration_ms }
```

**This is a brokered tool call, not a master turn.** The session needs the
master's *credentials*, not its reasoning, so the broker resolves the connector,
executes the tool under `authorize()`, and returns the result synchronously. No
master turn means no cost, no latency waiting for one, and no dependency on the
master being awake (D31). The session never holds a platform credential and the
audit trail has exactly one entry, attributed to the calling session.

Two things this deliberately does *not* replace: a session's **own** MCP servers
from its `CLAUDE.md` (the platform neither reads nor touches those), and
`request_help`, which is for questions only a human can answer.

### Blast-radius classes (refines D8 from two classes to four)

| class | examples | level 2 | level 3 |
|---|---|---|---|
| `local_read` | everything read-only | allow | allow |
| `local_write` | spawn, send, channel post, queue enable/parallelism, `report_blocked`, `ask_orchestrator` | allow | allow |
| `local_destructive` | interrupt, kill, release the claim, remove worktree, enable/disable a connector | **ask** | allow |
| `external` | work-item comment / status / create, **every connector tool by default** | **ask** | allow |

### Tool surface

**Read — `local_read`**

```
fleet_summary()                              → counts by bucket, needs_you[], stuck[], unknown_rate
list_projects()
list_sessions(project_id?, state?, outcome_class?, include_ephemeral=False)
get_session(id)                              → row + newest verdict + subagent rollup
get_session_output(id, lines=200)            → pty tail (owned) or transcript tail (attached)
list_subagents(session_id)
get_session_evidence(session_id)             → the stop-log record behind the conclusion
list_queues() · get_queue(id)
list_work_items(queue_id?, status_class?, limit=50) · get_work_item(id)
list_channels() · channel_history(channel_id, limit=50)
list_connectors()                            → id, health, tool count (never a credential)
get_audit_log(limit=50)
```

**Act — `local_write`**

```
spawn_session(project_id, task, model?, effort?, parent_session_id?)
send_to_session(id, text)                    → write policy (§9)
ask_session(id, question, timeout_ms=120000) → fork (§9)
create_channel(name, goal, session_ids[]) · post_to_channel(channel_id, text)
set_queue_enabled(queue_id, enabled) · set_queue_parallelism(queue_id, n)
requeue_work_item(work_item_id, note?)
```

`report_blocked` is deliberately **not** in the master's set — the master
delegates and does not itself get blocked. It belongs to `SESSION_TOOLS` only.

**Act — `local_destructive`**

```
interrupt_session(id) · kill_session(id) · release_claim(work_item_id, reason)
set_connector_enabled(connector_id, enabled)
```

**Act — `external`**

```
work_item_comment(work_item_id, text)
work_item_set_status(work_item_id, status)
work_item_create(provider, project_ref, draft)
```

Note what is **absent**: no `git_push`, no `open_mr`. Those happen inside tier-2
sessions, where Claude Code's own permission system already gates them and the
`PermissionRequest` hook surfaces them into the Needs-You rail. We do not rebuild
that.

### Two bindings, scoped differently

Both are **exporters over the one registry** (§11.0, D32) — not two tool
implementations, and not two places a capability is defined:

| consumer | exporter | tools |
|---|---|---|
| master | `to_sdk_mcp_server()` — in-process | `audiences ∋ MASTER` |
| tier-2 session | `to_stdio_mcp_server()` — `shepherd-mcp` | `audiences ∋ SESSION` |

The list below is therefore **derived, not maintained**: it is what you get by
filtering the registry on `SESSION`, reproduced here for readability.

```
SESSION_TOOLS =
    list_sessions (own project only) · get_session · ask_session · send_to_session
  · create_channel · post_to_channel · channel_history · spawn_session
  · get_work_item · work_item_comment · work_item_create
  · report_blocked · request_help(question, options[])
  · ask_orchestrator(question, connector_hint?)      # brokered connector access, D20
```

A tier-2 session cannot kill anything, cannot reconfigure a queue, cannot see
other projects, and **cannot mount or reach a connector directly** — D20. `request_help` is how a worker escalates: it files a
Needs-You card with its recommended options and ends its turn — the answer
arrives as its next message.

**Recursion caps, enforced inside `spawn_session` for both bindings:**

```
max_session_depth        = 3     # master → session → session, then refuse
max_children_per_session = 5
max_total_owned_sessions = 20    # global circuit breaker
```

The cap returns a tool **error the agent can read and reason about**, never a
silent failure.

### `authorize()` — one chokepoint

```python
def authorize(tool: ToolDef, args: dict, ctx: CallerContext) -> Decision:
    cls = tool.blast_class                 # a field on the registry entry, D32 —
                                           # not a lookup that can miss
    if cls in ("local_read", "local_write"):
        log_action(tool.name, args, cls, decision="allow", approved_by="policy")
        return Allow()
    if ctx.autonomy_level == 3:
        log_action(tool.name, args, cls, decision="allow", approved_by="policy")
        return Allow()
    approval = create_approval(tool.name, args, summary=describe(tool, args))
    decision = await_decision(approval, timeout_s=600)
    if decision is APPROVED:
        log_action(tool.name, args, cls, decision="allow", approved_by="user")
        return Allow()
    if decision is REJECTED:
        return Deny("you declined this")
    return Deny("approval timed out — proceed without it or ask me directly")
```

The callback **blocks the agent's turn** while an approval is pending, so the UI
shows a card and the turn resumes on the click. A timeout denies with a message
the agent can act on, not a dead turn.

The same function serves the master, tier-2 sessions via MCP, queue write-backs,
and UI-initiated actions. **There is no second path** — that is the entire point.
Per-action policy overrides ("always allow work-item comments, never allow push")
are a rule table on top of this same function, deferred to later.

### Context strategy for the master

The fleet changes every few seconds. Stuffing fleet state into the system prompt
would invalidate the prompt cache every turn and blow the context on a busy day.

Instead: a **small, frozen system prompt** (role, the three tiers, the current
autonomy level, how to escalate) plus **`fleet_summary()` as the cheap first
call.** The prompt instructs the master to call `fleet_summary()` at the start of
any turn that depends on current state, then drill down with `get_session` /
`list_work_items` only where needed.

`fleet_summary()` returns ~40 lines regardless of fleet size: counts per bucket,
the full `needs_you` list, the three oldest stuck items, queue health, and the
`unknown` verdict rate. Bounded, cacheable; the master's context grows with the
conversation, not with the fleet.

---

## 12. UI

Three surfaces, one settings page, and one rail that is always present.

### The Needs-You rail — on every page

```
┌────────────────────────────────────────────────────────────────────────┐
│ ● 3 NEED YOU    ox-ai-agent · permission: Bash(git push)         [→]  │
│                 reporting-service · OXDEV-71937 · question       [→]  │
│                 1 approval pending · work_item_set_status           [→]  │
└────────────────────────────────────────────────────────────────────────┘
```

Fixed to the top of every page — **not a page you navigate to.** Empty state
collapses to a 4px green line. Non-empty: amber bar, count, and *the actual ask*
on each row — never "session needs attention". Plus a macOS notification and an
optional sound on transition into `needs_you`.

### Page 1 — Chat (default landing)

```
┌──────────────────────────────┬─────────────────────────────────────────┐
│                              │  FLEET                                  │
│  you: what's blocked?        │  ● 2 running  ⏸ 3 need you  ✓ 5 finished│
│                              │  ────────────────────────────────────   │
│  shepherd: two things.           │  OXDEV queue    3 open · 1 draining     │
│    reporting-service is on   │  unknown rate   0.7%                    │
│    OXDEV-71937 and stopped   │  ────────────────────────────────────   │
│    early — it didn't run     │  PENDING APPROVAL                       │
│    the specs it promised.    │  work_item_set_status                      │
│    ox-ai-agent wants         │    OXDEV-71937 → In Code Review         │
│    permission to push.       │         [Approve]  [Reject]             │
│                              │                                         │
│    [Requeue with note]       │  autonomy:  ( 2 ) ─── 3                 │
│    [Show me the session]     │                                         │
│  > ________________________  │                                         │
└──────────────────────────────┴─────────────────────────────────────────┘
```

Left: the master conversation. Right: a live SSE-fed sidebar, so you are never
reading a stale claim while the chat is turn-based. Approval cards appear in the
sidebar **and** inline in the chat at the blocked turn.

The autonomy toggle lives here, visible at all times. You should never have to
remember which level you are on.

**The wake summary (D31)** opens the first turn of a session where anything
stopped while you were away — at level 2 it is the only way that work moves:

```
  shepherd: while you were away —
        2 sessions stopped needing a decision
        ◑ OXDEV-81711 resolver   promised specs, never ran them   [re-run]
        ✕ frontend lint          exit 1 during Edit               [logs]
        Want me to re-run the first one?
```

At level 3 the same set is acted on when it happens, and this becomes a report
of what was already done rather than a question.

### Page 2 — Fleet: projects → sessions → subagents

```
┌────────────────────────────────────────────────────────────────────────┐
│  ▼ ox-ai-agent                              2 running · 1 needs you   │
│     ┌──────────────────────────────────────────────────────────────┐   │
│     │ ⏸ needs you   OXDEV-86559 federation      permission: push   │   │
│     │               owned · opus-5 · 14m                    [open] │   │
│     ├──────────────────────────────────────────────────────────────┤   │
│     │ ● running     OXDEV-81711 custom reports          3 subagents│   │
│     │               owned · opus-5 · 6m · 2/5 tasks             ▼  │   │
│     │      ├─ ● cc10x:component-builder  resolver + specs     4m   │   │
│     │      ├─ ● general-purpose          scan schema.gql      1m   │   │
│     │      └─ ✓ cc10x:planner            plan revision 2      2m   │   │
│     ├──────────────────────────────────────────────────────────────┤   │
│     │ ⏱ paused      OXDEV-74458 skills scan      rate limited      │   │
│     │               resumes 14:20 · attempt 1/2            [retry] │   │
│     └──────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ▶ reporting-service                        1 stopped early           │
│  ▶ frontend                                 idle                      │
│  ▶ vibesec-scanner                          attached · 1 running      │
└────────────────────────────────────────────────────────────────────────┘
```

Projects collapsed by default. **Ordering is derived from state, never
alphabetical and never by mtime:**

```
needs_you → error → unfinished → running → paused → blocked → finished → idle
```

`blocked` sorts *below* `running` deliberately: it is real, it is visible, and it
is not yours to act on.

Subagents are one indented line each — type, description, elapsed, state.
Expandable in place; the parent row shows the count when collapsed. `2/5 tasks`
comes free from `TaskCreated`/`TaskCompleted` — real progress, not a spinner.

**Stopped rows carry a bucket chip, one line of `why`, and the first action
item as a button (D21):**

```
✓ finished           verified · all 4 tasks closed
◑ stopped early      promised to run specs, never ran them     [re-run][why?]
◑ derailed           edited the wrong service (report vs reporting) [why?]
⏳ blocked            waiting on review · MR !9291 · opened 2h ago   [↗]
⏱ rate limited       resumes 14:20                              [retry]
✕ crashed            exit 1 during Edit · no Stop received        [logs]
✕ stalled            held an unexecuted Bash call — likely a bug  [logs]
```

`[why?]` fires the LLM verdict on demand and expands with `missing[]`.

**Expanding a stopped row shows its full action list** — the whole point of
D21: a session that stopped for *any* reason answers "so what do I do" without
you reading a transcript.

```
◑ stopped early      promised to run specs, never ran them        [why?]
   ├─ 1  Re-run: it promised specs and never ran them        [re-run]
   ├─ 2  Requeue OXDEV-81711 with what's missing             [requeue]
   └─ 3  Read the last 50 lines                              [logs]
                                              2 heuristic · 1 llm ⓘ
```

Buttons come from `next_actions[].kind`; the row is never a dead end. `[↗]` on
a blocked row is just the `external` item's `target`, so "what is it waiting on"
stays one click. A `⚡ do all` control on the Needs-You rail is **not** in v1 —
you press the buttons.

The same list renders in the Session view header (below) and is returned by
`get_session()`, so the master reads the identical items rather than
re-reasoning about a stop it can already see classified.

**Two chips, two sources (D17).** A session's own outcome and the work's progress
are never merged:

```
◑ OXDEV-81711  custom reports
  ✓ finished        4/4 tasks · specs pass          ← the session
  ⏳ in review       MR !9291 · 2h                   ← the work (work_item.status_class)
```

Only the work item chip may ever read as shipped. A fleet filter *"stuck between
review and prod"* queries `status_class ∈ {in_review, in_qa}` ordered by age.

### Page 2b — the matrix view (D27)

A third view mode on the fleet page — `cards | table | matrix`, persisted per
workspace. **Its subject is the work item, not the session**, which is why it
has an extra row and an extra column that no session-only view could show.

```
                    open  in_prog  in_review  in_qa  blocked  done   (no item)
                   ------ -------  ---------  -----  -------  ----   ---------
  ⏸ needs_you        ·       3         ·        ·       ·       ·         1
  ✕ error            1       1         ·        ·       ·       ·         ·
  ◑ unfinished       ·       2         ·        ·       ·       ·         2
  ● running          ·       4         ·        ·       ·       ·         1
  ⏱ paused           ·       1         ·        ·       ·       ·         ·
  ⏳ blocked          ·       ·         2        1       1       ·         ·
  ✓ finished         ·       1        [3]       2       ·       4         ·
  ─────────────────────────────────────────────────────────────────────────
  (no session)      12       ·         1        ·       2       ·         —
```

- **`(no item)` column** — hand-launched `attached` sessions. Without it the
  grid hides most of a real day.
- **`(no session)` row** — unclaimed work. That `12` is the backlog, in the
  same view as everything else.
- **`[3]` is a named cell**: `finished × in_review|in_qa` is the "stuck between
  my desk and prod" question §12 already wanted a filter for. It carries a
  permanent label and a badge count.
- Empty columns hide by default — eight `status_class` values otherwise leave a
  mostly blank grid.
- A cell click opens the ordinary card list, pre-filtered. **The matrix is
  navigation; nothing is edited here.**

One `GROUP BY outcome, status_class` over `session` ⟗ `work_item`, recomputed
on SSE invalidation. Ships with **M5**, not M2: its columns are work-item
status, which does not exist before the mirror.

### Page 3 — Session view

```
┌───────────────────────────────────────────────┬────────────────────────┐
│  ● running · owned · opus-5 · xhigh           │ WORK ITEM              │
│  ─────────────────────────────────────────────│ OXDEV-81711            │
│                                               │ In Progress → Jira ↗   │
│    (xterm.js — the real terminal bytes)       │ ──────────────────     │
│                                               │ SUBAGENTS (3)          │
│    ● Bash(npm test -- resolver.spec.ts)       │ ● component-builder 4m │
│      PASS  12 passed                          │ ● general-purpose   1m │
│                                               │ ✓ planner           2m │
│    > _                                        │ ──────────────────     │
│                                               │ TASKS  2/5             │
│  ─────────────────────────────────────────────│ ✓ read the plan        │
│  [type here — writes straight to the pty]     │ ✓ add resolver         │
│                                               │ ○ update schema.gql    │
│  ⏎ send   ⎋ interrupt (confirm)   ⌘K queue    │ ○ specs · ○ lint       │
└───────────────────────────────────────────────┴────────────────────────┘
```

When the session is **stopped**, the header band is replaced by its bucket chip,
its `why`, and its `next_actions[]` as buttons (D21) — the terminal pane stays
below, frozen at its last frame:

```
┌───────────────────────────────────────────────┬────────────────────────┐
│  ◑ stopped early · owned · opus-5 · 12m       │ WORK ITEM              │
│  promised to run specs, never ran them        │ OXDEV-81711            │
│  [re-run]  [requeue with missing]  [logs]     │ In Progress → Jira ↗   │
```

`⌘K` queues a message through the mailbox instead of writing now.
`[tmux attach]` in the header hands the session to your own terminal.

**Renaming (D29).** The title in the header is click-to-edit. A rename sets
`title_source = 'user'` and from then on the engine's own generated title never
overwrites it. If the engine cannot accept the name back, the header shows a
quiet `local only` marker beside it — never a silent half-success:

```
  ◑ OXDEV-81711 custom reports  ✎            ← click to rename
  ◑ resolver + schema rewrite   ✎ local only ← renamed, engine can't sync it
```

### Page 4 — Settings: connectors, autonomy, queues

The connector list (§11, D20), the autonomy toggle, queue configuration, and
`shepherd uninstall`. It is a settings page, not a fourth workspace — nothing here
is watched during a working day.

### Event stream

One SSE endpoint, one envelope:

```jsonc
GET /api/events
{ "seq": 41822, "at": "2026-09-08T11:04:12Z",
  "type": "session.state_changed",   // | session.verdict | subagent.* | task.*
                                     // | needs_you.raised | needs_you.cleared
                                     // | approval.created | approval.decided
                                     // | queue.synced | claim.* | work_item.updated
                                     // | connector.health_changed
  "session_id": "…", "project_id": "…",
  "data": { "from": "running", "to": "needs_you",
            "why": "permission: Bash(git push)" } }
```

`seq` is monotonic. A reconnecting client sends `Last-Event-ID` and gets the gap
replayed. **No polling anywhere in the UI.**

---

## 13. Security posture

Single-user, loopback, no auth in v1 — which is precisely why the boundaries
below are strict.

### Network

- **`127.0.0.1` only, with no config knob to bind wider in v1.** The terminal
  write endpoint types into a live shell as the user; exposing it on a LAN with
  no auth is not a tradeoff worth offering. Remote access arrives with the auth
  seam, not before.
- **Origin-checked mutations.** Every POST validates `Origin`/`Host` against the
  bound address, blocking a random page in the browser from driving the fleet.
- **Both Unix sockets at mode 0600**, plus a per-boot shared token in the frame
  header.

### Credentials

- Stored via the macOS Keychain (`security`, service `ai.shepherd`).
- The DB, the audit log, the agent's context, and the UI see only
  `credential_ref`. `Credentials.resolve()` is the sole reader.
- Redaction pass on `action_log.args` and on `work_item.raw` for known
  secret-shaped keys.

### Connectors (D20)

- **No arbitrary MCP command from the UI.** The catalogue is code; the UI only
  toggles rows and supplies credentials. A pasted argv is remote code execution
  behind a text box.
- Connector tokens follow the same rule as everything else: `Credentials.store()`
  → `credential_ref`, resolved once inside the master's MCP launcher. Never in
  `connector.spec`, the DB, `action_log.args`, the master's context, or a
  response body. `list_connectors()` returns health and tool counts only.
- **Connector tool output is untrusted content** — it is third-party text
  reaching an agent that holds `local_destructive` tools. It is never
  interpolated into `innerHTML` (see below) and never treated as an instruction
  by the master: the orchestrator prompt states that tool results are data.
- HTTP-transport connectors are subject to the same hostname allowlist as
  work-item providers, validated at save time.

### Outbound requests (SSRF)

Outbound calls go only to configured work-item provider hosts, but
`queue.provider_config` is editable from the UI, so the host is
runtime-influenced. Each provider validates **inline, in the same function as
the request**, against a non-empty hostname allowlist:

```python
JIRA_ALLOWED_HOSTS = ["<your-site>.atlassian.net"]   # from provider_config, validated at save
NOTION_ALLOWED_HOSTS = ["api.notion.com"]
```

Parse with a URL parser, compare on **hostname** (never `origin` or the raw
string), reject anything not in the list, allow only `http:`/`https:`, and
**disable redirect following** so a redirect cannot bypass the allowlist. No
blocklists, no IP-range checks, no scheme-only validation — an allowlist is the
only accepted shape.

### Frontend (untrusted content)

Work item titles and bodies come from Jira/Notion, and terminal/transcript text
comes from agents. **All of it is untrusted.**

- Every interpolation inside `innerHTML` / `outerHTML` /
  `insertAdjacentHTML` must be wrapped in `escapeHtml(String(v))` — no
  exceptions for "it's just a number" — **or** keep the markup static and fill
  slots with `textContent`. Prefer the latter.
- `xterm.js` handles its own escaping for the terminal pane; never route pty
  bytes through `innerHTML`.
- Work item URLs are rendered as links only after validating scheme and host
  against the provider allowlist.

### API responses

**Never return a raw DB row or a spread of one.** Project an explicit field
whitelist at every response sink. Never serialize `credential_ref` resolution
output, a raw transcript entry, or `work_item.raw` to the browser — the
fleet/session endpoints return named fields only.

### Subprocess and filesystem

- **No `shell=True` anywhere.** argv lists only.
- Project roots canonicalized and validated against the registered-project
  allowlist before any spawn; no path traversal into an unregistered directory.
- Worktree paths derived from a slugified work-item key, never from raw provider
  text.

### Errors

Error text reaching the browser is a generic literal plus a correlation id. Full
detail goes to the local log only. No stack traces, environment values, or
paths in a response body.

---

## 14. Testing

Four lanes. The first two carry the value.

1. **Classifier over golden fixtures.** A directory of **real stop-log records
   plus their transcript tails** — a rate limit, a crash mid-`Edit`, a
   permission prompt answered, a derailed completion, a `blocked_external`, a
   `stalled_pending_tool`. Pure function in, verdict out. **No mocking of Claude
   Code — the fixtures *are* Claude Code.** Adding a missed case is: capture signals, drop in a fixture,
   fix the rule, run `replay`.
2. **Contract suites, one per seam.** `WorkItemProvider`, `Runner`,
   `EngineAdapter` and `MasterRuntime` each get **one** test suite that every
   implementation must pass. A new provider is done when it passes the existing
   suite. This is the mechanism that stops the abstractions rotting into
   CCC's 400KB-per-engine shape.

#### `Scripted*` — what they are and why every seam gets one

**Every seam ships a `Scripted*` implementation**: `ScriptedRunner`,
`ScriptedWorkItemProvider`, `ScriptedEngine`, `ScriptedMaster`. They live in
`testkit/` and ship with the package, not only with the tests.

**What one is.** A real implementation of the seam's `Protocol` that answers from
a fixture instead of from the outside world. `ScriptedMaster` satisfies
`MasterRuntime` — `configure`, `send`, `resume`, `interrupt`, `capabilities` —
but `send()` walks a list you handed it rather than calling a model:

```python
master = ScriptedMaster([
    Turn(says="Two sessions need you.",
         calls=[("fleet_summary", {}),
                ("kill_session", {"id": "ses_7f3k"})]),   # local_destructive → must prompt
])
```

Now you can assert that a `local_destructive` call raised an approval card, that
the audit log got exactly one entry, and that a denial came back as a message the
agent can read — deterministically, in milliseconds, with no process spawned and
no tokens spent.

**What one is not.** Not a mock (nothing records call expectations), not a
stub that returns `None`, and **not a base class** — the seams are `Protocol`s and
the typing is structural, so `ScriptedMaster` is a concrete *peer* of
`AgentSDKMaster`, never its parent. Nothing inherits from it. It is also not
"the simple version to start from": it never grows toward the real thing, and its
only job is to answer predictably.

**Why every seam gets one.** Two reasons, and the second is the important one:

1. The system becomes testable end-to-end without a Jira sandbox, a tmux server,
   a `claude` process, or an API key. Lane 4's concurrency tests need twenty
   workers racing one work item — spawning twenty real sessions to test a
   `WHERE` clause is absurd.
2. **It is the cheapest possible second implementation of the interface.** D9's
   whole argument is that an interface written against one implementation is
   usually wrong — it silently encodes that implementation's assumptions. A
   `Scripted*` is a second caller of the contract from day one, and it is what
   catches an interface that has quietly grown a vendor's shape long before the
   real second implementation shows up. `MasterRuntime` carrying
   `mount_tools(mcp_servers)` until D32 is exactly the mistake a `ScriptedMaster`
   would have surfaced in an afternoon: it has no MCP to mount.

**Naming.** Not `Fake*` (says nothing about behaviour), not `Base*` (implies a
parent class, which is the opposite of what these are), not `Test*` (pytest
collects `Test`-prefixed classes on import and warns on any that has an
`__init__`). `Scripted*` says what it does: it replays a script.
2b. **Isolation tests.** `test_master_isolation.py` asserts the D19 import
   boundary (the `master/` package imports nothing but `toolsurface.client` and
   the SDK) and that `setting_sources=[]` keeps the global `CLAUDE.md` and cc10x
   routing out of the master (§18).
3. **Integration, slow lane.** Real `claude -p` runs in a temp git repo: spawn →
   observe → verdict → write-back against a Jira sandbox project.
   The classifier fixtures assert `next_actions[]` too (D21): every stop reason
   in the §8 table has a fixture, and a stop reason with an empty action list on
   a non-`completed` verdict is a test failure.
4. **Concurrency.** Claim races (N workers, 1 work item, assert exactly one claim),
   mailbox idempotency, SSE reconnect gap replay, `sessiond` restart with live
   sessions.

---

## 15. Packaging

Signed + notarized `.pkg`:

```
/usr/local/libexec/shepherd/                              daemons + venv
/usr/local/bin/shepherd                                   CLI
~/Library/LaunchAgents/ai.shepherd.controld.plist          KeepAlive
~/Library/LaunchAgents/ai.shepherd.sessiond.plist          KeepAlive
~/Library/Application Support/shepherd/                    db, pty logs, fixtures, config
```

State lives under `Application Support`, **not** `~/.claude` — we are a consumer
of Claude Code, not part of it.

Hook installation merges a **marked, idempotent block** into
`~/.claude/settings.json`, backing the file up first. Every entry we own carries
`"_shepherd_managed": true`, so `shepherd uninstall` removes exactly our entries and
leaves the user's own hooks untouched. CCC merges hooks with no ownership marker,
which makes clean removal impossible.

---

## 16. Milestones

Seven shippable slices. Each is useful on its own; none requires the next to earn
its keep.

| # | Slice | Working at the end | Est. |
|---|---|---|---|
| **M1** | Foundation + visibility | **Hook-payload probe first** (§18), then both daemons, `hookd` dispatcher, ingest folding into `session` columns (D24), **four of the six tables** (`workspace`, `repo`, `session`, `app_state` — `work_item` and `queue` arrive with M5) + migrations, workspace/repo discovery and binding (D22), workspace→session→subagent tree, fleet page, SSE. **Read-only, `attached` sessions only.** Ordering uses the three live `state` values (`needs_you` → `running` → `stopped` → idle) — the full 7-bucket palette lands in M2. | 4–6 d |
| **M2** | Signals engine | Classifier over transcript tail + stop metadata (D24), the `session` stop columns, **`next_actions[]` and the default table (D21)**, 7-bucket palette and its ordering, expandable stopped rows with action buttons, Needs-You rail, `replay`, `unknown` rate. **Mechanical reasons + heuristics only — the LLM verdict lane is deferred (D34)**, stubbed behind `classify_end_turn()`. | 5–6 d |
| **M3** | Owned sessions | tmux runner, spawn, xterm.js terminal, write policy, mailbox, `ask()` via fork, rename + the `can_set_title` probe (D29). | 5–7 d |
| **M4** | Orchestrator | **The tool registry first (§11.0, D32)** — `ToolDef`, `invoke()`, and the two MCP exporters — then `MasterRuntime` + `AgentSDKMaster` **behind the D19 import boundary + its isolation test**, `ScriptedMaster` and the `MasterRuntime` contract suite (§14.2), the wake set and its retry cap (D31), `authorize()` off `tool.blast_class`, approvals, audit, chat page. | 5–6 d |
| **M4.5** | Connectors | `connector` table + catalogue, settings page, OAuth/token capture into Keychain, mount/unmount at turn boundaries, health polling, `ask_orchestrator()` brokering, per-tool blast overrides. | 3–4 d |
| **M5** | Queues | Jira provider, reconcile, the `work_item` table + claims, hierarchy and leaf-only dispatch (D23), workers, lazy per-repo worktrees (D22), verdict routing, two-chip rows, **the matrix view (D27)**. | 7–9 d |
| **M6** | Notion + channels + ship | Notion provider (proves the seam), broadcast channels, `.pkg`, notarization, uninstall. | 4–6 d |

**~33–44 focused dev days.** M1+M2 alone — roughly two weeks — already exceeds
what CCC provides on visibility and stop-reason detection.

---

## 17. Explicitly deferred

Named so they do not leak into v1:

- **Memory layer** — deferred by D7; derived later from past sessions per work
  item plus the stop log (D24, D25).
- **Multi-user + remote runners** — seams exist (`Runner`, `Credentials`,
  `owner_id`), drivers do not.
- **Extracting the master into its own `masterd` process** — the D19 import
  boundary makes this a packaging change (one plist, one socket) whenever
  "restart `controld` without ending the orchestrator conversation" starts to
  hurt. Not worth a third daemon for a single user on day one.
- **`ApiLoopMaster`** — the second `MasterRuntime` implementation (D30). Built
  when someone needs a non-Anthropic master, or when the multi-user path makes
  the subscription route unusable. With D32 the seam carries no vendor shape, so
  this is **one new class plus one exporter** (`to_openai_functions`). Two things
  it must bring that `AgentSDKMaster` gets free from the harness, both flagged on
  `MasterCapabilities` (§6): **its own persisted message history**, keyed by the
  opaque `master_session_id`, and **its own context compaction** — the master is
  the longest-lived conversation in the system, so that is not optional. Two
  things get *easier*: `disallowed_tools` is moot because the loop only ever
  sends our own tools, and `setting_sources=[]` is moot because there is no
  `CLAUDE.md` to inherit. **Switching runtime starts a new orchestrator
  conversation** — message formats and tool-call ids are not portable between
  vendors — and takes effect at a turn boundary, never mid-turn (D20 rule 5).
- **The LLM verdict lane** (D34) — deferred past M2, stubbed at one call site in
  `signals/verdict.py`. No seam until it is built.
- **A UI for master runtime selection** — the config shape it will read is a
  single `app_state` row (`runtime`, `provider`, `model`, `base_url`,
  `credential_ref`), the model list comes from `ModelProvider.models()`, and the
  key goes in through `Credentials.store()` like every other secret. Named here
  so M4 does not hard-code the runtime choice somewhere a settings page cannot
  reach; the page itself is post-v1.
- **`NotificationChannel`** — the seam behind mobile access. The valuable phone
  action is answering the Needs-You rail, not reading a terminal, which makes it
  a chat surface rather than an app. **Slack Socket Mode is the mechanism**: an
  outbound WebSocket, so a loopback-only daemon can receive interactive button
  clicks with no tunnel, no inbound port, and no auth server — the one thing
  §13's network posture would otherwise forbid. Post-M6. A native mobile app is
  not planned; a responsive web UI over a private network covers the read case.
- **Custom / user-supplied connectors** — v1 ships a fixed catalogue (D20). A
  config-file-only escape hatch comes after the catalogue has proven the mount,
  health, and blast-class machinery.
- **Attaching connectors directly to tier-2 sessions** — brokered via
  `ask_orchestrator()` in v1. Direct attach needs per-session credential scoping
  and `authorize()` inside session processes; revisit if brokering proves too
  slow for queue workers.
- **`⚡ do all` on action items** — `next_actions[]` renders buttons you press,
  never a batch the platform executes for you.
- **Other engines** — `EngineAdapter` written against three, implemented for one.
- **Other work-item providers** beyond Jira and Notion.
- **`DeployProvider` / prod verification** — a session can only see as far as the
  work item's status. Literal prod confirmation (GitLab pipelines, Datadog) is a new
  provider on the same seam, setting `work_item.shipped_at`.
- **Cost and usage tracking**, plan-window pacing, model advisor.
- **Semantic history search.**
- **Shared blackboard** for coordination (mailbox + channels only).
- **Per-action policy overrides** on `authorize()`.
- **Webhook ingest** for work-item updates.
- **Mobile UI**, kanban board view, federation across machines.

---

## 18. Open risks, each with an early probe

| Risk | Probe |
|---|---|
| tmux ↔ Claude Code TUI (alt-screen, resize, reflow) | **Spike before M3 starts** — it is M3's load-bearing assumption |
| Session forking for `ask()` | Verify the flag/SDK path in M3; the `can_fork=False` mailbox fallback is already designed |
| Hook write volume — `PostToolUse` × 20 concurrent sessions | Measure in M1; batch writes + WAL tuning if it bites |
| Notion rate limits (~3 req/s) | Design reconcile for it in M6; backoff + cursor already present |
| `setting_sources=[]` truly isolating the master from the global `CLAUDE.md`/cc10x | Verify in M4 and **assert it in a test** — do not trust it |
| **Hook payload fields** — `TaskCreated`/`TaskCompleted`, `FileChanged`, `SubagentStart`/`Stop`, `Notification.notification_type`, `StopFailure.error_type`. The §7 live-group columns all rest on these, and they are **documented, not observed** | **M1, first task.** Install a logging hook, run one real session, diff the arriving events against the field list. Anything missing degrades a column to null and the UI hides that chip |
| **Title write-back** (D29) — can a rename be pushed into Claude Code without writing into a file it owns? | Probe in M3 alongside the tmux spike. Until it passes, `can_set_title = False` and renames stay local |
| Whether the shipped SQLite has `FULL OUTER JOIN` (3.39+) | One line in M1; the matrix falls back to two `LEFT JOIN`s and a `UNION` |

---

## 19. Glossary

| Term | Meaning |
|---|---|
| **owned** session | the platform spawned it and owns its pty; full terminal, steering, exit code |
| **attached** session | launched outside the platform; visible and read-mostly, no pty |
| **subagent** | an `Agent`-tool dispatch inside a tier-2 session; rollup only |
| **signal** | one raw observation, stored verbatim and never mutated |
| **verdict** | a derived, versioned classification of a session's state and stop reason |
| **outcome_class** | one of the seven palette buckets (§4) |
| **claim** | a local, expiring claim on a work item; never written to the provider |
| **blast class** | how far an action reaches; decides whether `authorize()` asks |
| **the mirror** | the `work_item` table; B10's sync loop is its only writer |
| **wake set** | master-owned sessions that stopped `unfinished` or `error` since the master's last turn (D31) — a query, not a table |
| **seat vs API** | two transports, not two settings — a subscription is reachable only through the engine harness, never over an API (D30) |
| **connector** | a third-party MCP server whose tools are imported into the registry as `external` and reachable by the master only; catalogue-selected, credential-by-reference (D20, D32) |
| **the registry** | the one place a capability is declared — a `ToolDef` per tool, carrying its schema, blast class, handler and audiences (D32) |
| **exporter** | a ~30-line translator from the registry into one consumer's shape: SDK MCP, stdio MCP, OpenAI functions, HTTP routes, CLI subcommands. Adding a vendor is adding one of these |
| **`Scripted*`** | a real implementation of a seam that answers from a fixture instead of the outside world (`ScriptedMaster`, `ScriptedRunner`, …). A concrete peer of the real implementation, never a parent class — nothing inherits from it. Lives in `testkit/`, ships with the package (§14.2) |
| **action item** | one entry of `verdict.next_actions[]` — an imperative line plus a `kind` the UI renders as a button (D21) |
| **finished** | *the session* did its assigned task and we verified it |
| **done** | *the work* shipped — a work item-level fact, never a session colour |

---

## Appendix A — Worked example: one real day's data

Concrete rows, so the shape of §7 is arguable rather than abstract. Values are
realistic for this repo set, not invented.

### `workspace` — one row

```jsonc
{ "id": "wsp_01J8Q...", "name": "ox", "root_path": "/Users/noamsalit/Git",
  "created_at": "2026-08-02T09:12:00Z", "last_activity_at": "2026-09-11T10:41:07Z" }
```

### `repo` — five rows, one workspace

```jsonc
{ "id": "rep_a1", "workspace_id": "wsp_01J8Q...", "name": "ox-ai-agent",
  "root_path": "/Users/noamsalit/Git/ox-ai-agent",
  "vcs_remote": "git@gitlab.com:ox-security/ox-ai-agent.git", "active": true }
{ "id": "rep_b2", "name": "reporting-service", "active": true,  "...": "..." }
{ "id": "rep_c3", "name": "frontend",          "active": true,  "...": "..." }
{ "id": "rep_d4", "name": "vibesec-scanner",   "active": true,  "...": "..." }
{ "id": "rep_e5", "name": "security-rules",    "active": false, "...": "..." }  // removed, history intact
```

`rep_e5` shows the soft delete: it no longer appears in spawns, discovery, or
the matrix, and last month's sessions that reference it still read correctly.

### `session` — three rows covering the three interesting shapes

**A queue worker, running, spanning two repos.** Note `repos_touched` has two
entries while `repo_id` has one: it started in `reporting-service` and has since
edited `ox-ai-agent` too. That is the multi-repo case D22 exists for.

```jsonc
{ "id": "ses_7f3k", "engine_session_id": "29e08da4-3584-470d-9e30-dede9ea3141b",
  "workspace_id": "wsp_01J8Q...", "repo_id": "rep_b2",
  "work_item_id": "wit_811", "work_item_ref": "jira:OXDEV-81711",
  "origin": "queue_worker", "ownership": "owned", "depth": 1,
  "brief": "Implement the custom-reports resolver per plan rev 2. Update schema.gql by hand — it is not generated in this repo.",
  "title": "OXDEV-81711 custom reports", "title_source": "engine",
  "cwd": "/Users/noamsalit/Git/reporting-service-wt/OXDEV-81711",
  "worktree_path": "/Users/noamsalit/Git/reporting-service-wt/OXDEV-81711",
  "runner_handle": "shepherd:ses_7f3k", "model": "claude-opus-5", "effort": "xhigh",
  "started_at": "2026-09-11T10:22:41Z",

  "state": "running", "last_event_at": "2026-09-11T10:41:07Z",
  "needs_you_reason": null, "tasks_done": 2, "tasks_total": 5,
  "active_subagents": 3, "repos_touched": ["rep_b2", "rep_a1"], "pr_url": null,

  "stop_reason": null, "outcome": null, "why": null,
  "confidence": null, "decided_by": null, "next_actions": [],
  "ended_at": null, "exit_code": null }
```

**A hand-launched session, `attached`, that you renamed.** No brief was written
by us — it came from the transcript's `lastPrompt`. No worktree, no exit code,
no terminal. `title_source: "user"` with a null `title_synced_at` is exactly the
`local only` marker in §7.1.

```jsonc
{ "id": "ses_2a9x", "engine_session_id": "b71c...", "repo_id": "rep_a1",
  "work_item_id": null, "work_item_ref": null,
  "origin": "external", "ownership": "attached", "depth": 0,
  "brief": "why is enableSecuredByOx not taking effect for org 4412?",
  "title": "secured-by-ox flag debugging", "title_source": "user",
  "title_synced_at": null,
  "worktree_path": null, "runner_handle": null,
  "state": "needs_you", "last_event_at": "2026-09-11T10:39:55Z",
  "needs_you_reason": "idle — waiting for your next instruction",
  "tasks_done": 0, "tasks_total": 0, "active_subagents": 0,
  "repos_touched": ["rep_a1"], "exit_code": null }
```

**A session that stopped early** — the case the whole signals engine exists for.
It stopped cleanly (`end_turn`), so the mechanical table had no answer and the
model ran over the transcript tail:

```jsonc
{ "id": "ses_5m1p", "repo_id": "rep_b2", "work_item_id": "wit_811",
  "origin": "queue_worker", "ownership": "owned",
  "brief": "Add the custom-reports resolver and its specs.",
  "title": "OXDEV-81711 resolver", "title_source": "brief",
  "state": "stopped", "tasks_done": 3, "tasks_total": 5,
  "repos_touched": ["rep_b2"],

  "stop_reason": "incomplete", "outcome": "unfinished",
  "why": "promised to run the specs and never ran them",
  "confidence": 0.91, "decided_by": "model",
  "next_actions": [
    { "text": "Re-run: it promised specs and never ran them",
      "kind": "respawn", "target": null },
    { "text": "Requeue OXDEV-81711 with what is missing",
      "kind": "requeue", "target": "wit_811" },
    { "text": "Read the last 50 lines", "kind": "inspect", "target": "ses_5m1p" } ],
  "ended_at": "2026-09-11T09:58:12Z", "exit_code": 0 }
```

### `work_item` — a container and one of its children

The epic is **never dispatchable**: `kind_class = "container"`. Nothing in the
code says "epic" — that word only ever appears in `kind_raw`, which came from
Jira verbatim (D23).

```jsonc
{ "id": "wit_800", "provider": "jira", "external_id": "OXDEV-81700",
  "title": "Skills scanner reporting", "kind_raw": "Epic",
  "kind_class": "container", "parent_external_id": null,
  "status_raw": "In Progress", "status_class": "in_progress",
  "claimed_by_session_id": null }

{ "id": "wit_811", "provider": "jira", "external_id": "OXDEV-81711",
  "workspace_id": "wsp_01J8Q...", "project_ref": "OXDEV",
  "title": "Skills custom reports", "url": "https://<site>.atlassian.net/browse/OXDEV-81711",
  "kind_raw": "Story", "kind_class": "work", "parent_external_id": "OXDEV-81700",
  "status_raw": "In Progress", "status_class": "in_progress",
  "priority": 2, "assignee": "noam.salit",
  "labels": ["vibesec", "reporting"],
  "raw": { "...": "the untouched Jira payload" },
  "external_updated_at": "2026-09-11T08:03:22Z", "synced_at": "2026-09-11T10:40:00Z",
  "claimed_by_session_id": "ses_7f3k",
  "claimed_at": "2026-09-11T10:22:39Z",
  "claim_expires_at": "2026-09-11T10:37:39Z",   // heartbeat + 3 × interval
  "attempt": 2 }
```

`attempt: 2` and `ses_5m1p` above are the same story from two sides: attempt 1
stopped early, attempt 2 is `ses_7f3k` and currently running. **That history is
a query, not a table** — `SELECT … FROM session WHERE work_item_id = 'wit_811'
ORDER BY started_at` (D24).

### `logs/stops/2026-09-11.jsonl` — one record, ~2 KB

The evidence behind `ses_5m1p`'s conclusion. This is what `shepherd replay` reads
when a rule improves, and what `[why?]` expands.

```jsonc
{ "at": "2026-09-11T09:58:12Z", "session_id": "ses_5m1p",
  "classifier_version": "h-7+m-3",
  "input": {
    "brief": "Add the custom-reports resolver and its specs.",
    "stop_event": { "hook": "Stop", "stop_reason": "end_turn" },
    "last_assistant_message": "Resolver added and schema.gql updated. I'll run the specs now.",
    "open_tasks": ["run resolver.spec.ts", "lint"],
    "tool_counts": { "Bash": 31, "Edit": 9, "Write": 2 },
    "failures": [],
    "transcript_tail_entries": 20 },
  "output": { "stop_reason": "incomplete", "outcome": "unfinished",
              "confidence": 0.91, "decided_by": "model",
              "why": "promised to run the specs and never ran them",
              "missing": ["resolver.spec.ts was never executed"],
              "next_actions": ["..."] } }
```

Note `open_tasks` is non-empty: heuristic 1 (the task ledger) would have reached
`incomplete` on its own. The model ran anyway because it supplies the `why` and
the action items, and it is the only thing that could have spotted the unkept
promise in `last_assistant_message`.

### `logs/audit/2026-09-11.jsonl` — one record

```jsonc
{ "at": "2026-09-11T10:22:40Z", "actor_kind": "worker", "actor_id": "ses_7f3k",
  "tool": "work_item_set_status", "blast_class": "external",
  "args": { "work_item_id": "wit_811", "status": "In Progress" },
  "autonomy_level": 2, "decision": "allow", "approved_by": "user",
  "result": "ok", "duration_ms": 412 }
```

No credential appears — tools take a `credential_ref` and resolution happens
inside the provider (§13).

### The matrix cell, as a query

The `[3]` cell in §12 — finished sessions whose work is still in review — is:

```sql
SELECT s.id, s.title, w.external_id, w.status_raw
  FROM session s JOIN work_item w ON w.id = s.work_item_id
 WHERE s.outcome = 'finished'
   AND w.status_class IN ('in_review', 'in_qa')
 ORDER BY w.external_updated_at;
```

Which is the whole argument for `session.work_item_id` being a real foreign key
rather than the `"jira:OXDEV-81711"` string in `work_item_ref`.
