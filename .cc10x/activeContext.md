# Active Context

## Current Focus

Implement the Shepherd orchestrator platform from `docs/specs/orchestrator-platform.md`,
scoped to milestones **M1–M4** (foundation+visibility, signals engine, owned sessions,
orchestrator). Per spec §0, each milestone gets its own plan → implementation cycle.
Full flow requested: planner → builder → review → QA route.

## Recent Changes

[DEBUG-RESET: wf:wf-20260920T063421Z-c6df8bbd]
macOS portability pass: 14 failed / 25 errors on the first Mac run of a tree built and verified on Linux as root.

- Repo was docs-only at session start (spec + QA-experiment methodology docs, one baseline commit).
- Environment and hook-payload ground truth established before planning (see `## Learnings`).

## Next Steps

1. ~~M1 (foundation + visibility)~~ — **DONE and verified.** 20/20 tasks, all three verification
   defects closed with negative controls, hookless discovery proven live on the user's own machine.
2. ~~M2 (signals engine)~~ — **DONE and verified, 19/19.** Milestone verification returned FAIL on
   2 of its 16 acceptance clauses; both were the plan claiming proof it did not have, neither was a
   bug in the engine, and both are now closed with the check proven to bite. Final state:
   **869 passed / 1 skipped** on `-m "not live"`, **12** live, **23** boundary rules,
   `mypy --strict src` clean over 79 files.
3. ~~M3 (owned sessions)~~ — **DONE and verified.** 24/24. Verification: 12 PASS / 4 FAIL / 1
   UNVERIFIED on 17 clauses, all four closed. The real one: the `kill-server` guard was a spelling,
   and tmux resolves `kill-serv`.

4. ~~M4 (orchestrator)~~ — **DONE and verified.** 23/23 tasks (Track C cut on a security finding —
   a deviation from §16, recorded with its reversal condition). Verification: **20 PASS / 1 FAIL** on
   21 clauses; the FAIL was a clause whose deciding command named a file nobody built. Remediated.

5. ~~M1–M4 QA pass~~ — **DONE.** The first pass to test the four milestones **composed**. Five
   defects; two fixed, three recorded. The one that justified the pass: **D31's wake set could never
   fill in production** — the query filtered on an origin nothing wrote, and every wake test passed
   because each planted its own row.

**Final state: 1840 passed / 1 skipped, 75 live, 105 boundary rules, `mypy --strict` clean over 127
files, `controld.py` still 140.** `HANDOFF.md` at the repo root is the macOS handoff.

**Still open, each with an owner:** `fleet_summary` at 85 lines for one session against a documented
~40 (design decision, two viable options); `caller_id` is an unauthenticated self-stamp, so per-caller
scope is expressible but not yet trustworthy; `shepherd status` blind to a running daemon (needs a
transport decision *and* a second Gate A re-base, owed together); Track C's reversal condition.

**Process lessons that cost the most, all now structural:** a shared ledger four builders appended to
lost two tasks' entries (per-task files now); a baseline frozen while builders were writing (freeze on
a quiet tree); mutations of live source while siblings ran sweeps (per-task shadow trees); a mutation
planted in a *shadow* that rebooted the host (inert fixtures only — `CLAUDE.md` and spec §18); stale
bytecode recording a **false survivor** (clear `__pycache__`); and **"recorded" is not "applied"** — a
decision written into the ledger while the code still had the old behaviour, twice.

3b. **Wave 1, kept for its ordering decision (historical).** Plan at `docs/plans/2026-09-17-m3-owned-sessions-plan.md`
   **revision 2** (24 tasks; two fresh reviews returned 6 and 14 blocking findings, all
   dispositioned). Wave 1 dispatched: T2 (core runner vocabulary + 7 `AnomalyKind` members),
   T3 (mailbox + migration 003), T7 (`HostPlatform.detached_launch`).
   **Router ordering change:** T1's live probes are held until T5's runtime argv guard exists.
   The plan runs T1 from day 1 on a parallel track, but it touches real tmux and real `claude`
   while every M3 safety mechanism is still unbuilt (reviewer 2's B11), and its only dependents
   (T15, T16) are far downstream — so the delay costs nothing and nothing reaches live tmux before
   the thing that refuses a bad argv is real.
4. Then M4 (orchestrator), its own plan -> implementation cycle (§0).

**M3 acceptance is SEVENTEEN clauses** (plan lines 3849-3946), not sixteen and not thirteen.
Counted by reading the whole section, not a `sed` window. This is written down because M2's
milestone verifier was briefed on 13 of its 16 clauses — my `sed` window cut three — and the two
FAILs it did return were both in the part I had seen. The M3 verifier brief must carry all 17
verbatim.

**Resume note (2026-09-17, second rate-limit resume).** The session limit cut in with three
builders mid-task. On resume the tree was verified: **1013 passed / 1 skipped / 1 xfailed**,
`mypy --strict src` clean over 88 files, 35 boundary rules green, 102 store tests green, user's
machine untouched (settings sha `375e5322...`, three live tmux sessions on the `shepherd` socket,
1 commit).

**T4-1 turned out to be already closed** — the verb split landed before the cutoff.
`store/sessions.py` carries both `bind_engine_session_id` (a conditional write reporting its own
rowcount) and `rebind_engine_session_id` (C14's move); the strict xfail is gone and
`test_an_unbound_ask_fork_row_is_bindable_exactly_once` is a real passing test. So only **T4-2**
(split `db.py`, then wire the verbs onto `Store`) remained of that pair.

Wave dispatched on resume, chosen for file-disjointness so three builders can run at once:
**T4-2** (`store/`), **T8** (`runner/local.py` + `core/runner.py`'s tenth member), **T10**
(`engines/claude_code/spawn.py`). T13 and T9 are held — both depend on T8.

**Resume note (2026-09-17 morning).** The overnight run ended on a session rate limit with two
builders mid-task. T12/T17's builder got T12 onto disk and died before T17; the T18-wiring builder
left no trace. Baseline at resume: **798 passed, 1 skipped**, `mypy --strict` clean over 78 files,
14 boundary rules green. User's machine verified untouched — settings sha `375e5322…`, three tmux
sessions alive on the `shepherd` socket, 1 commit.

## Decisions

- **(2026-09-17) PENDING RE-DECISION for M3 — D29's `can_set_title` mechanism is wrong in the spec,
  and the evidence to fix it already exists.** §18's "spike before M3" is **already done**
  (`docs/probes/2026-09-14-schemas/tmux-tui/`, five capture folders, `-L shepherd-probe` throughout
  with verified teardown), so M3 is not blocked on a new spike. Two findings that must be stated as
  a four-part Decision pressure when the M3 plan is written, **not applied silently**:
  1. **`can_fork = True` for Claude Code** — data-schemas §Fork, line 2920: "Spec line 2326 (verify
     fork path in M3): answered." The `can_fork=False` mailbox fallback stays built, but it is now
     the fallback, not the expected path.
  2. **`can_set_title`: the spec's candidate mechanism targets the wrong entry type.** Spec lines
     724–731 propose "appending an `ai-title` entry to the session transcript" and set
     `can_set_title = False` until a probe says otherwise. The probe says otherwise *and* says the
     mechanism is wrong: `ai-title` is the **engine-generated** channel; a user-supplied title is
     `custom-title` (written by the engine itself on `/rename` over the pty, or by `--name` at
     spawn), and the registry then reports `nameSource:"user"`. So **Shepherd never writes the file**
     — for *owned* sessions `can_set_title` can be `True` by driving the engine, and
     `title_synced_at` can be read from the `custom-title` entry, the sidecar's `nameSource`, or
     `#{pane_title}`. Appending `ai-title` would at best record a user title in the engine's channel
     and may be hidden by an existing `custom-title`. Not verified: `/rename` against a session live
     in another process (the **attached** case) — that gap is M3's, and the honest default for
     attached sessions stays `can_set_title = False`.

- **(2026-09-17) T10-2 — the quota latch. Option 1, decided and applied.** `TURN_STOPPED` clears
  `quota_notice_at`, exactly as it already clears `auto_compact_at`. The reasoning is symmetry with
  the mark beside it: both are evidence about the turn that just ended, not about the session's
  history. `quota_paused` must mean "this stop was a quota pause", not "this session once saw a
  notice" — a mark set and never cleared is a latch, and the first user to hit a real quota limit
  would get every later stop in that session misclassified, whose cost under D18 is a parked work
  item. Option 2 (splitting `QUOTA_NOTICE` by payload value) is revisited **when a quota notice is
  actually captured**; G-M2-1 forbids reading a payload value to choose a kind until then.

- **Scope = M1–M4.** User chose "M1–M4 core" over full M1–M6. Queues (M5), connectors (M4.5),
  Notion/channels/packaging (M6) are out of scope for this run.
- **(2026-09-16) D55 written into the spec — revises D39.** User: the daemons must also run on
  macOS, and the end state is "a macOS package we install and work locally, and code that runs
  inside a container on a remote Linux server." Three deployment shapes: macOS package, Linux
  host under the systemd user manager, Linux container (no systemd — foreground process, the
  container runtime restarts it). Host-dependent behaviour goes behind a **seventh seam,
  `HostPlatform`** (`LinuxHost` verified, `MacHost` written-unverified), owning exactly five
  things: dir resolution, socket dir + path-length budget, service supervision, process
  liveness/exit observation, login persistence. Under D36 this is a **runtime** swap (one build
  must start on either host) so it gets a Protocol + `ScriptedHost` + contract suite, drawn at
  **M1**, not at packaging. §13's loopback posture is NOT reopened: the container binds loopback
  and is reached by SSH tunnel / port-forward.
- **(2026-09-16) Real `~/.claude/settings.json` is off limits.** User chose "don't touch it". The
  hook installer is built (backup → marked `_shepherd_managed` block → validate after write →
  uninstall) but exercised only against an isolated `CLAUDE_CONFIG_DIR` / `--settings` file. The
  user's live sessions stay invisible to Shepherd until they run the installer themselves.
- **(2026-09-16) Live `claude` runs allowed, fixtures first.** 429 captured hook events in
  `docs/probes/2026-09-14-schemas/hooks/live/` carry the deterministic tests; a few short haiku
  `claude -p` / TUI runs in `/tmp` prove ingest and the M3 runner for real. Never on the user's
  `shepherd` tmux socket.
- **(2026-09-16) Toolchain bootstrapped with permission.** `apt-get install python3.12-venv`, then
  `/root/Shepherd/.venv` with `claude-agent-sdk` 0.2.153, `pytest` 9.1.1, `mypy` 2.3.1. M4's
  AgentSDKMaster can therefore be live-tested; principle 6's `mypy --strict` is enforceable.
- **Provider credentials deferred.** User: "Start without being placed on those and I will
  provide later on maybe only after we finish." Moot for M1–M4 — Jira/Notion are M5.
- **QA-parallel experiment is OFF.** User: ignore `docs/methodology/*`; do not run QA lanes in
  parallel with BUILD. QA runs once, after the code is built and reviewed.
- **LLM verdict lane stays deferred (spec D34).** One named call site in `signals/verdict.py`,
  no `Classifier` seam.

## Learnings

> **SUPERSEDED BLOCK (2026-09-12, `claude` 2.1.269).** Everything between this line and
> "END SUPERSEDED" was written before the 2026-09-14 probe suite. It is kept for history only.
> The authoritative source is now `docs/specs/data-schemas.md` (127 schemas, 88 verified live
> against 2.1.270, every one with a real captured example) plus
> `docs/specs/implementation-constraints.md` (C1–C24). **Read those, not this.** Specifically
> corrected below: the "never fired" list (all of `StopFailure`, `Notification`, `FileChanged`,
> `PostToolUseFailure`, `PermissionDenied`, `Elicitation*`, `Pre/PostCompact`, `CwdChanged`,
> `Pre/PostModelSwitch` DID fire in the 2026-09-14 runs), "Platform is Linux, not macOS" (see
> D55), and the `get-pip.py` note (apt `python3.12-venv` was used instead).

- **Hook-payload ground truth (spec §18's top risk, resolved empirically).** A prior session
  probed real `claude` 2.1.269 sessions. Observed and carrying the fields the spec needs:
  `PreToolUse`, `PostToolUse` (with `agent_id`, `agent_type`, `effort`, `duration_ms`,
  `tool_response`), `MessageDisplay`, `SessionStart`, `UserPromptSubmit`, `Stop`
  (with `last_assistant_message`), `SessionEnd`, `TaskCreated`/`TaskCompleted`
  (with `task_id`, `task_description`, `task_subject`), `SubagentStart`/`SubagentStop`
  (with `agent_transcript_path`), `PermissionRequest`.
- **Hook events that never fired** despite being registered: `StopFailure`, `Notification`,
  `FileChanged`, `PostToolUseFailure`, `PermissionDenied`, `Elicitation`/`ElicitationResult`,
  `PreCompact`/`PostCompact`, `CwdChanged`, `PreModelSwitch`/`PostModelSwitch`.
- **Consequences of the above:** `StopFailure.error_type` is the sole source for 10 of the 16
  mechanical `stop_reason`s (§8) — those degrade to `unknown`. `Notification.notification_type`
  backs `needs_you_reason` detail and `quota_paused`. `FileChanged` backs `repos_touched`.
  `Stop` carries **no `stop_reason` field at all**, so §8's `end_turn` gate has no direct source.
- **Field-name deltas from the spec:** `SessionStart.source` (spec says `start_reason`),
  `SessionEnd.reason` (spec says `end_reason`).
- **Transcript ground truth** (18 real transcripts): `ai-title` and `custom-title` entries both
  exist (D29 title), `last-prompt`/`lastPrompt` exists (attached-session brief), `effort` is
  top-level, `isSidechain` and `agentId`/`agentName` mark subagents. **No `pr-link` entry type
  was observed** — spec §7 calls `pr_url` "free" from the transcript; treat as unverified.
- **Environment:** Python 3.12.3, SQLite 3.45.1, tmux present, `claude` 2.1.269, network up.
  `pytest`/`mypy`/`claude-agent-sdk` 0.2.152 all install into a venv. **No node/npm/tsc** —
  the frontend cannot be compiled TypeScript. **Platform is Linux, not macOS.**
- **SQLite `FULL OUTER JOIN` is supported** (3.45.1 ≥ 3.39) — spec §18's probe is answered yes;
  no `LEFT JOIN`+`UNION` fallback needed for the matrix view.
- **pip is not installed system-wide**; `python3 -m venv --without-pip` + bootstrapped
  `get-pip.py` is the working path.

- **tmux TUI spike PASSED (2026-09-13)** — `docs/probes/2026-09-13-tmux-tui-spike.md`. D14 holds. New M3 constraints:
  workspace-trust dialog blocks fresh spawns (default "No, exit", no hooks fire); pane targets need `=<name>:`;
  runner socket name must be config because the user's live sessions use socket `shepherd` on this host.
- **D29 title write-back works for owned sessions** via `/rename <title>` over the pty; Claude Code writes
  `custom-title` itself. Attached sessions stay `local only`.

END SUPERSEDED.

### Current ground truth (2026-09-16, from the 2026-09-14 probe suite)

- **Every external shape has a captured example** in `docs/specs/data-schemas.md`. The project rule
  from the user: *no data shape may be asserted without one*. Check it before building on a shape.
- **The four facts that bite M1 hardest** (all from `implementation-constraints.md`):
  C7/C8 — only `session_id`, `transcript_path`, `cwd`, `hook_event_name` are on *every* event, and
  no payload carries a timestamp (the receiver stamps it); C9 — `FileChanged` never fires for files
  the agent edits, so `repos_touched` needs `PostToolUse` Edit/Write paths instead; C10 —
  `active_subagents` goes negative on a naive ±1 (internal subagents emit `SubagentStop` with
  `agent_type:""` and no start: pair by `agent_id`, ignore `""`, clamp, count the anomaly);
  C11 — `brief` from the latest prompt is polluted by injected `<task-notification>` XML, so use
  the first real user prompt.
- **`hookd` has a hard latency budget, not just a socket timeout.** A Python hook was killed at
  `-p` shutdown and lost `StopFailure` 2/2, while a fork-free bash hook survived
  (data-schemas §StopFailure, §Hook runtime contract). Interpreter start is the risk. Design the
  dispatcher for a few ms, and treat observed process exit as the stop signal of record.
- **`~/.claude/projects/*.jsonl` matches nothing.** Main transcripts are one level down
  (`projects/<slug>/<sid>.jsonl`); subagents are deeper. The slug rule is lossy and hash-suffixed
  past 200 UTF-16 units — glob for the session id, never reverse the slug.
- **Environment (re-probed 2026-09-16):** Python 3.12.3, SQLite 3.45.1 (WAL/JSON1/STRICT/RETURNING,
  `FULL OUTER JOIN` OK), tmux 3.4, git 2.43.0, `claude` 2.1.270. No node/npm/tsc — matches D51
  (plain ES modules, no build step), so this is not a gap. No Secret Service on this host → the
  `Credentials` Linux driver is the 0600 file under `$XDG_CONFIG_HOME/shepherd/`.
- **Linux `sun_path` is 107 usable bytes; macOS is 103.** With D55 that budget is a `HostPlatform`
  concern, and `SO_PEERCRED` is Linux-only (`getpeereid` on macOS).

## References

- Spec: `docs/specs/orchestrator-platform.md` — **55 decisions** (D1–D55), approved
- External shapes, with real captures: `docs/specs/data-schemas.md` (127 schemas)
- Build-affecting facts: `docs/specs/implementation-constraints.md` (C1–C24)
- Probe evidence + re-run scripts: `docs/probes/2026-09-14-schemas/`
  (429 captured hook events in `hooks/live/*/events.jsonl` — the fixture corpus for M1/M2)
- tmux TUI spike: `docs/probes/2026-09-13-tmux-tui-spike.md`
- Repo working rules (tmux safety): `CLAUDE.md`
- Ignored by user instruction: `docs/methodology/*`, and `docs/plans/2026-09-13-*` (STALE —
  predates D35–D55)
- Python: `/root/Shepherd/.venv` (pytest, mypy, claude-agent-sdk)

## Blockers

None blocking. Known gaps to resolve in the milestone that needs them, not to stop on:

- §7 declares six tables but §9 (mailbox, channels) and §11 (approvals) require storage that is
  not among them. M3 needs a mailbox; M4 needs approvals.
- **This harness has no `TaskCreate`/`TaskList`/`TaskGet` primitive.** Subagent dispatch works.
  The cc10x task graph is therefore tracked in `.cc10x/workflows/{wf}.json` instead of the task
  system; every gate still runs. Logged as `task_primitive_unavailable`.
- Appendix A of the spec is stale (C22): macOS paths under a Linux target, and `repo_id` values
  that contradict D48's worktree binding. Rewrite it when M1 settles the real layout.

## Session Settings

- AUTO_PROCEED: true
- Rationale: user asked to "be as autonomous as possible" and to run the full flow end to end.

## Last Updated

2026-09-16

## Debug History
[DEBUG-1]: Lead 1 as stated ("tests/engines/test_hookd_command.py fails because MacHost refuses") → WRONG. Those 3 tests never touch MacHost: their `host_dispatch()` helper calls `LinuxHost().hook_dispatch(plan)`, which does a live `shutil.which("timeout")` against the *running* host. `timeout` is absent on macOS, so the Linux driver reports `available=False` here. The MacHost product gap is real and separate.
[DEBUG-2]: Candidate macOS dispatch `nc -U -w 0` (the obvious `-q0` analogue) → REJECTED by measurement: it silently TRUNCATES a 40 KB frame to ~16-18 KB (3/3 runs). It is the exact "delivers, but not all of it" failure class E34 names.
[DEBUG-3]: Lead 3's account of the test_controld failures ("tmp_path too long") → INCOMPLETE. Root cause is that `MacHost.environ` defaults to `{}` (LinuxHost defaults to `dict(os.environ)`), so `detect_host()` on macOS returns a host blind to HOME and TMPDIR: it wrote a real `shepherd.db` into `~/Library/Application Support/Shepherd` and a real socket into the shared `/tmp/Shepherd`. Both confirmed present on disk.
[DEBUG-4]: WINNING — one root cause behind Lead 1 and most of Lead 3: **the product and its tests both asked the Linux driver about a macOS host.** `MacHost.environ` defaulted to `{}` (so `detect_host()` returned a driver blind to HOME/TMPDIR), `MacHost.hook_dispatch()` refused unconditionally over a flag set nobody had measured, and eight test modules spelled `LinuxHost()` where they meant "this host". Fixed at the seam in every case; 28 tests that had been silently skipping on macOS now run.
[DEBUG-5]: Live-lane pass. Redirecting HOME in tests/e2e/conftest.py::shepherd_home isolated Shepherd's data dir AND broke the engine's login ("Not logged in · Please run /login") — measured: the engine resolves its account record from $CLAUDE_CONFIG_DIR/.claude.json, so no env combination gives "throwaway HOME for Shepherd, real config for the engine". Reverted: net-better to leave 1 pre-existing failure than to trade it for 2 new ones. The e2e lane needs an injected HostPlatform, not a mutated environment.
[DEBUG-6]: HostPlatform injection landed. controld.start(host=...) threads host through control_socket, dirs(), compose_tool_surface, log_root and the discovery loop — so both the database AND logs/stops/ relocate with it, and no src/ change was needed. log_root's own docstring already said "a test relocates both by handing in a host". Proved: /tmp/shp-proof/.../shepherd-home/Library/Application Support/Shepherd/{shepherd.db,logs}. Key asymmetry: the process environment stays the ENGINE's (real HOME, real login), Shepherd's dirs arrive by injection — which is what my previous pass got wrong by redirecting HOME process-wide.
