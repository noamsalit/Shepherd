# Shepherd M1 — Foundation + Visibility Plan

## Metadata
- Created: 2026-09-13
- Status: draft
- plan_revision: 2 · last_reviewed_revision: 1 · planning_review_status: revised_after_review

**Revision 2 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 1/2 (cap reached). This revision was amended after the last fresh pass and has been checked only by amendment verification (not run); no adversarial pass has read it whole. Sections changed since the last fresh review: Metadata; Agreement Snapshot; Codebase Reality Check; Deviation Register (DV-03, DV-04, DV-07, DV-26, new DV-30, DV-31); Planner Decisions (PD-07, PD-08, PD-11); Hidden-Assumption Pass (A10); Behavior contract 1 (SessionStart, PermissionRequest, PostToolUseFailure/PermissionDenied rows, sweep); Behavior contract 2; Edge-case catalog (E43–E47); Spec S2 (token, control-socket outbound queue); Spec S3 (labels, health); Spec S4 registry; Tasks T02, T06, T09, T10, T11, T12, T13, T14, T15, T16, T17, T19; Live Verification Strategy; Risk Matrix; Glossary; Plan Self-Review; new §Revision 2 Disposition Log.
> Wording note: the mandated sentence above is copied verbatim. The fresh-review cap is **not** actually reached. One of two passes has been used, so the "(cap reached)" clause does not apply to this revision.
- Verification Rigor: critical_path
- Plan Mode: execution_plan
- Workflow: wf-20260912T123500Z-a7c3f9e1
- Design source: `docs/specs/orchestrator-platform.md` (approved spec, incl. the 2026-09-12 tmux-incident edits) + `CLAUDE.md` (repo working rules)
- Scope: **M1 only** (spec §0 step 4, §16). M2/M3/M4 get their own plans.

---

# PART 1 — HUMAN LAYER (what and why)

## Agreement Snapshot

- **Goal:** Hand-launched `claude` sessions show up on their own in a local fleet page. The page groups them as workspace → session → subagent, sorts them by live state, and updates over SSE without polling. Two daemons (`controld`, `sessiond`), a `hookd` dispatcher, and a four-table SQLite store with migrations back it.
- **Constraints:**
  - Spec §3 decisions are settled. Every place M1 departs from them is listed in §Deviation Register, with the reason.
  - Python 3.12, `mypy --strict` plus `disallow_any_explicit`, no `Any`. Each file stays under ~600 lines, and a test enforces it.
  - Principle 4: hookd always exits 0, prints nothing, and has a 250 ms socket deadline. Installing hooks must never break a user's Claude Code settings.
  - Principle 5: `unknown` gets counted and shown. Degrades are recorded, never hidden.
  - D24: there is no event store. D25: logs go to rotating files, and readers skip malformed trailing lines. D26/D33: all SQL lives in `store/`, which exposes verbs that return dataclasses.
  - §13 security: listen on loopback only, check Origin and Host, sockets are 0600 with a per-boot token, no `shell=True`, never return a raw row, never use `innerHTML`.
  - The host is Linux with no node, npm or tsc. The frontend is plain ES modules.
  - **tmux safety (CLAUDE.md and the §18 incident).** Pass `-L` explicitly on every tmux call. Never run a bare `kill-server`. Never put `:` in a session name. The user's live sessions run on the `shepherd` socket. M1 runs no tmux, but its config and repo rules must encode all of this so M3 inherits it.
  - Dev, test and QA must never touch the user's real state. No writes to `~/.claude/settings.json`. No systemd units get enabled. Nothing touches the `shepherd` tmux socket.
- **In Scope:**
  - Platform seam: config and profiles, paths, process probe, `Credentials`, service supervision. Linux drivers are live. macOS drivers are written but unverified.
  - Migration runner and `0001_foundation.sql`: `workspace`, `repo`, `session` (spawn, live and title groups, plus `ended_at`/`exit_code`), `app_state`.
  - Domain verbs in `store/`. Workspace and repo registration, discovery, and longest-prefix binding (D22).
  - The sessiond UDS frame protocol, hookd, field-tolerant ingest and folding.
  - Claude Code transcript reading: title, brief, model, subagent listing. Hook install and uninstall.
  - controld: migrations at startup, the sessiond link, `EventHub` with SSE gap replay, the HTTP API and the fleet page.
  - CLI. The `Scripted*` implementation and contract suite for each seam M1 touches.
  - Hook write-volume measurement (§18). Live verification against a real `claude`.
- **Out of Scope:**
  - Owned sessions, `Runner`, tmux, spawn, terminal, mailbox, `ask()`, rename write-back (M3).
  - Stop classification, the stop-group columns, `next_actions[]`, the 7-bucket palette, the Needs-You rail, `replay`/`recompute`, the stops log (M2).
  - The tool registry, `authorize()`, approvals, audit, master and chat (M4).
  - Connectors (M4.5). `work_item`/`queue`, providers, the matrix view (M5). Notion, channels, `.pkg` (M6). The LLM verdict lane (D34).
- **Re-decided out loud (visible for review, not silent):** DV-07 (`needs_you` source), DV-09 (liveness rule for attached sessions), DV-10 (stop-group columns deferred to M2), DV-11 (no FK on `work_item_id`), DV-13 (unassigned workspace + null-binding rebind), DV-14 (`EngineAdapter` subset/additions), DV-17 (temporary hand routes vs D32), DV-22 (both sockets on sessiond). None reverses a numbered §3 decision permanently; DV-17 is temporary by construction.
- **Open Decisions:** none. Every judgment call M1 needed is made and recorded, with its reason, in §Deviation Register and §Planner Decisions. None of them changes scope, platform or credentials, which the user already settled.

## Context References (MUST READ before building)

| Path | Why |
|---|---|
| `docs/specs/orchestrator-platform.md` §3, §4 | Decision log and principles. They are law. |
| same, §6 | Seam Protocols, verbatim. M1 implements `Credentials` and a subset of `EngineAdapter`. |
| same, §7 (+ §7.0, §7.1, Indexes, Logs, Migrations) | Data model, the D33 store rules, the three migration rules. |
| same, §8 (the event→column table and `state`) | What ingest folds. Read it next to §Ground Truth below, because the spec's field list is wrong. |
| same, §12 Page 2 + Event stream | Fleet page layout, ordering, SSE envelope. |
| same, §13 | Security posture. |
| same, §14 (lanes 2, 2b, 4; `Scripted*` definition) | Test obligations. |
| same, §18 incl. "Incident 2026-09-12" | tmux isolation rules (for the M3 note), the hook-volume probe. |
| `CLAUDE.md` | Repo working rules: tmux `-L`, no bare `kill-server`, no `:` in session names. |
| `.cc10x/activeContext.md` | Probe findings and environment facts. |
| **Do not read** `docs/methodology/*` | The user said to ignore it. |

Durability horizons are marked per task: **stable** means the architectural seam or schema, **near-term-refactor** means M2/M4 will reshape it, **session-only** means throwaway.

## Codebase Reality Check (verified 2026-09-13)

| Check | Result | Evidence |
|---|---|---|
| Tracked files | `.gitignore`, `docs/specs/orchestrator-platform.md`, `docs/methodology/*` (ignored by user instruction). **No source code, no `pyproject.toml`, no tests.** `CLAUDE.md` is untracked and new. | `git ls-files` |
| Existing ADRs / decision records | **None.** No `docs/adr/`, `docs/decisions/`, `docs/rfcs/`, `*ADR*.md`, or `CONTEXT.md`. The spec's §3 decision log is the only settled-decision source and is treated as law. | `find . -ipath '*adr*' -o -ipath '*decisions*' -o -ipath '*rfc*' -o -name 'CONTEXT*.md'` → empty |
| Existing code patterns to follow | None (greenfield). Patterns come from the spec (§6 Protocols, §7.0 store rules, §14 `Scripted*`) and CLAUDE.md. | — |
| `.gitignore` | Python caches, `.venv/`, `venv/`, egg-info, pytest/mypy caches. T00 adds `build/`. | `cat .gitignore` |
| Plan-vs-code mismatch table | With no code, the mismatches are **spec vs observed reality**. They are §Ground Truth below, and each one M1 acts on is in §Deviation Register. | this document |
| Toolchain | Python 3.12.3; SQLite 3.45.1; no system pip (venv + `get-pip.py` works, network up); no node/npm/tsc; tmux present; `claude` 2.1.270; systemd `--user` reachable, root `Linger=no`; `$XDG_RUNTIME_DIR=/run/user/0` exists but is deliberately not used (DV-03) | probes in `.cc10x/activeContext.md` + re-run 2026-09-13 |
| SQLite features the plan relies on | `STRICT` tables; `json_valid`/`json_type`; partial unique index + `INSERT … ON CONFLICT(col) WHERE … DO NOTHING` (changes() 1 then 0); `ALTER TABLE ADD COLUMN` with CHECK and `NOT NULL DEFAULT` on a STRICT table; GLOB CHECK on time format; DDL rollback | executed against 3.45.1 on this host |
| Browser access | The host is headless Linux, and controld binds `127.0.0.1` only (§13). Manual UI checks (T19) are done through an SSH local forward **on the same port number**, `ssh -L 7421:127.0.0.1:7421 <host>`, then `http://localhost:7421/`. The Host check accepts `localhost:<port>` and `127.0.0.1:<port>` only, so a different local port is rejected by design. | Spec §13; `check_host` in S3 |

## Ground Truth That Overrides the Spec (probe-verified)

These facts come from real `claude` 2.1.269 sessions (77 events in 4 runs) and 18 transcripts. I re-checked the probe data on 2026-09-13. The host now runs `claude` 2.1.270, and T19 re-verifies against it.

1. **Events that fire, and their fields.**
   - `SessionStart{source}`, `UserPromptSubmit{prompt, prompt_id}`
   - `PreToolUse`/`PostToolUse{tool_name, tool_input, tool_use_id, agent_id?, agent_type?}`
   - `MessageDisplay`, `PermissionRequest{tool_name, tool_input}` (**no `tool_use_id`**)
   - `Stop{last_assistant_message, stop_hook_active, background_tasks}` (**no `stop_reason`**)
   - `SessionEnd{reason}` (only `"other"` was observed), `TaskCreated`/`TaskCompleted{task_id, …}`, `SubagentStart`/`SubagentStop{agent_id, agent_type, agent_transcript_path}`
2. **Never fired:** `StopFailure`, `Notification`, `FileChanged`, `PostToolUseFailure`, `PermissionDenied`, `Elicitation`, `ElicitationResult`, `PreCompact`, `PostCompact`, `CwdChanged`, `PreModelSwitch`, `PostModelSwitch`. No M1 logic may depend on them.
3. **`effort` in a hook payload is an object, `{"level": "high"}`.** In a transcript it is the top-level string `"high"`.
4. **Every observed payload carries `session_id`, `cwd` and `transcript_path`.** None carries a timestamp.
5. **Transcripts** live at `~/.claude/projects/<slug>/<engine_session_id>.jsonl`. The slug is `cwd` with every non-alphanumeric character replaced by `-`: `/tmp/claude-0/-root-Shepherd/x` becomes `-tmp-claude-0--root-Shepherd-x`.
   - **Subagent transcripts** are at `<slug>/<engine_session_id>/subagents/agent-<agent_id>.jsonl`.
   - Each has a `.meta.json` next to it: `{agentType, description, toolUseId, spawnDepth, requestShape}`.
6. **Transcript entry types:**
   - `ai-title{aiTitle}`, `custom-title{customTitle}`, `last-prompt{lastPrompt}`, `agent-name`
   - `assistant` (carries `message.model` and a top-level `effort`), `user`, `attachment`, `system`, `file-history-snapshot`
   - **No `pr-link`** entry appears anywhere.
7. **`claude --resume <id>` keeps the same `session_id` and transcript file.** Observed: this planning session's own id `9bc1bf13…` runs as `claude --resume 9bc1bf13…` and writes `9bc1bf13….jsonl`.
8. **Process names.** Live `claude` processes have `comm == "claude"`, and the Bash tool's parent process is `claude`. Whether a hook's ancestry includes `claude` is unverified, so T19 checks it.
9. **SQLite 3.45.1 behaviour (verified with Python's `sqlite3`):**
   - `FULL OUTER JOIN` works.
   - `ALTER TABLE ADD COLUMN … CHECK(...)` works and is enforced, including `NOT NULL DEFAULT '[]' CHECK(json_valid(...))`.
   - DDL inside `BEGIN … ROLLBACK` rolls back.
   - **With `foreign_keys=ON`, inserting into a table whose FK references a missing table fails even when the FK value is NULL.**
   - Python's `executescript()` issues an implicit COMMIT, so it cannot be used inside a migration transaction.
10. **The `claude` CLI silently ignores a settings file that fails validation** (from `claude --help`). A bad merge into a settings file can silently disable every setting in it.
11. **tmux (for M3 only).** Spike on `-L shepherd-spike`, 2.1.270:
    - The TUI renders, `alternate_on=1`, `capture-pane -e -p` keeps ANSI, and `send-keys -l` + Enter drives a prompt.
    - A fresh directory stops on the workspace-trust dialog (default "No, exit"), and **no hooks fire until someone answers it.**

## Deviation Register (every intentional departure from the spec, in one place)

A reader can tell an intentional choice from a mistake by checking this table. Anything not listed here follows the spec.

| ID | Spec says | M1 does | Why |
|---|---|---|---|
| DV-01 | §5 Stack: "vanilla TypeScript … `tsc`" | Plain ES modules served as-is, JSDoc-annotated with `// @ts-check`. No build step. | The host has no node, npm or tsc. The spec's goal (inspectable, no bundler) still holds. No TypeScript migration is scheduled in M1–M4; reintroducing `tsc` would be its own plan item if a toolchain appears. |
| DV-02 | D2 / §13 / §15: macOS `.pkg`, launchd, Keychain | Every host concern sits behind the platform seam. **Linux drivers are live and QA'd** (systemd `--user` unit files, a 0600 file credential store, `/proc` process probe). macOS drivers (launchd plist, `security`-CLI Keychain, `os.kill` probe) are written against the same Protocols but **unverified**. `.pkg` is deferred. | User-approved decision 2. D2's seam is kept exactly. |
| DV-03 | §7/§15 put state under `~/Library/Application Support/shepherd/`; §2 (resolved 2026-09-12) says `~/.shepherd/` | `data_dir = $SHEPHERD_HOME or ~/.shepherd` on every platform. Non-default profiles use `~/.shepherd/profiles/<profile>/`. Runtime sockets, token and locks live in **`<data_dir>/run/`** (mode 0700) on every platform. The environment (`$XDG_RUNTIME_DIR`) is never consulted, and the token is regenerated when it is older than boot time (Spec S2). | §2 is the later, explicitly resolved statement. **Profiles** exist so dev, test and QA never share state, sockets, ports or tmux sockets with the user's real instance. The runtime dir does not depend on the environment because the hook command bakes `--runtime-dir` at install (PD-07). An env-dependent choice (`$XDG_RUNTIME_DIR` present under systemd but absent in a shell, and `/run/user/0` vanishing with `Linger=no`) would silently drop every event (fresh-review A10). |
| DV-04 | §8 subscribes 24 event names, 12 of which never fired | **`hook_events()` registers only the 14 events the fold consumes:** the 12 observed (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `MessageDisplay`, `PermissionRequest`, `Stop`, `SessionEnd`, `TaskCreated`, `TaskCompleted`, `SubagentStart`, `SubagentStop`) plus `PostToolUseFailure` and `PermissionDenied`. Every group uses `"matcher": "*"`, which is the exact group shape of the probe's accepted settings file. `FileChanged`/`CwdChanged` (which need `watchPaths`) and the other never-fired, unconsumed events are **not** registered. `KNOWN_EVENTS` still lists all 24 §8 names, so arriving events are classified; anything else counts as `unknown_event`. | Ground truth 2 and 10. A settings file Claude Code rejects is ignored **in full**, and at user scope that is the user's global settings. So the generated shape must be a subset of a shape proven accepted, and T19 L02 live-verifies the exact file T11 generates (fresh-review A4). Registering unconsumed events buys nothing in M1. |
| DV-05 | §8/§9: `SessionStart.start_reason`, `SessionEnd.end_reason`, `Stop.stop_reason` | M1 reads `source` and `reason` (the real names). Nothing reads `stop_reason`, which does not exist. | Ground truth 1. The M2 plan must redesign the `end_turn` gate (see §Preconditions for M2). |
| DV-06 | §7/§8: `repos_touched` is accumulated from `FileChanged` | Built from `PostToolUse` where `tool_name ∈ {Edit, Write, MultiEdit, NotebookEdit}`, using `tool_input.file_path` / `notebook_path`. Each path is resolved against `cwd`, canonicalized, then bound to a repo by longest prefix. Capped at 50 ids. | `FileChanged` never fires, while `PostToolUse` `file_path` is observed. **Recorded degrade:** files changed through `Bash` (`sed -i`, `git mv`, generators) are invisible. The chip shows only when the list has more than one entry or differs from `repo_id`. |
| DV-07 | §8: `needs_you` comes from `Notification.notification_type` ∈ {permission, idle, …} or `PermissionRequest` | **`PermissionRequest` is the only `needs_you` source.** The reason is `"permission: Tool(summary)"`. Idle-waiting cannot be detected: after `Stop` a session is `stopped`, shown as "at prompt", not `needs_you: idle`. | `Notification` never fires. **Recorded degrade:** Appendix A's `"idle — waiting for your next instruction"` row cannot be produced in M1. It is also why "at prompt" and "exited" are separate labels. **TUI deny/Esc behaviour is unproven** (probe was `-p`, where requests auto-deny). `PostToolUseFailure`/`PermissionDenied` are consumed defensively, and T19 L3b records what the TUI actually emits, under a decision rule. |
| DV-08 | §7: `pr_url` is "free — the transcript emits `pr-link` entries" | The column is created and nothing in M1 writes it. The UI hides the chip when it is null. | No `pr-link` entry was observed. This is unverified and moves to M2's plan if it matters. |
| DV-09 | §8 `state`: running ⇔ a signal within `LIVENESS_WINDOW_S` (90 s) | **Re-decided for `attached` sessions:** silence does *not* flip state. The fleet card shows "quiet Nm" once `last_event_at` is older than 90 s. `sessiond`'s sweep moves a session to `stopped` in two cases: (a) the `claude` process found from hookd's `/proc` ancestry has died (sets `ended_at`), or (b) a `running`/`starting` session has had no event for `attached_abandon_s` (default 10800 s; `ended_at` stays null). **`needs_you` never times out.** | The 90 s rule assumed pty output (owned sessions). Attached sessions have no pty, and a long `Bash` tool call is legitimately silent for more than 90 s, so flipping would lie. A killed `claude` never sends `SessionEnd`, so without (a) and (b) the fleet would show ghosts forever. A pending permission prompt is the human's rail and is never aged out. |
| DV-10 | §7 `session` includes the stop group (`stop_reason, outcome, why, confidence, decided_by, next_actions`) | **`0001` creates every `session` column except those six.** `ended_at` and `exit_code` are included. M2 adds the six with `ALTER TABLE ADD COLUMN` (verified on 3.45.1, CHECK included). | M2 must re-decide their enums. `Stop` has no `stop_reason`, and §7's `decided_by` enum (`mechanical\|model\|declared\|manual`) conflicts with D34's `decided_by='heuristic'`. Baking the wrong CHECK now would force a table rebuild. T05 includes a forward-compat test that proves the M2 path. |
| DV-11 | §7: `session.work_item_id` is a FK | `work_item_id TEXT` has **no `REFERENCES` clause** in M1. | Verified: SQLite refuses inserts, even NULL ones, when the referenced table is missing (`work_item` arrives in M5). **Precondition for the M5 plan:** either do a 12-step table rebuild to add the FK, or accept app-level integrity. |
| DV-12 | §7 Indexes (list) | Adds `CREATE UNIQUE INDEX ux_session_engine_sid ON session(engine_session_id) WHERE engine_session_id IS NOT NULL`. | Every hook event looks up a session by engine id, and registration must be idempotent. §8 describes this query; §7's list just omitted the index. |
| DV-13 | §7: `session.workspace_id NOT NULL`; spawn group is "written once" | Migration `0001` seeds a workspace `wsp_unassigned` named `(unassigned)`. A session whose `cwd` matches no repo and no workspace root binds there. When a repo or workspace is registered later, **sessions with `repo_id IS NULL`** whose `cwd` now matches are rebound in the same transaction. Sessions already bound to a real repo never move. | Principle 5: an unbound session must be visible and counted, not dropped. Rebinding only null bindings keeps D22's meaning without trapping sessions launched before their repo was registered. |
| DV-14 | §6 `EngineAdapter` Protocol | M1's Protocol is a **subset plus three additions**. **Omitted until M3**, where `SessionSpec`/`RunnerHandle` exist: `spawn_argv`, `set_title`. **Added:** `engine_id() -> str`, `process_names() -> frozenset[str]`, `list_subagents(engine_session_id, parent_live) -> list[SubagentInfo]`. **Changed:** `install_hooks(dispatcher: Path, target: HookTarget) -> HookInstallReport` and `uninstall_hooks(target: HookTarget) -> HookInstallReport`, where the target is a settings-file path. **`locate_transcript(engine_session_id)` keeps the spec signature**; it globs `<projects>/*/<id>.jsonl`. | `list_subagents` is the §8/§11 "read from the transcript on demand" path, and it belongs to the engine. The hook target exists so dev and QA install into a throwaway project's `.claude/settings.local.json` and never the user's global file. Omitting methods now avoids stubs. The spec forbids stub `Scripted*` too. |
| DV-15 | §7: "**Six tables**" | The spec's later sections need more storage than six tables: `mailbox_message` (§9, M3), `channel` + `channel_message` (§9, M6), `approval` (§11, M4), `connector` (§11, M4.5). The runner also creates `schema_migration` for bookkeeping. **M1 records this.** Migrations are numbered sequentially; each milestone plan adds its own `NNNN_*.sql`; the runner supports any contiguous count. M1 ships `0001` only. | Spec gap called out by the user. Recording it now keeps the M3/M4 plans from discovering it late. |
| DV-16 | §12 SSE envelope has `project_id`; lists `subagent.*`, `task.*` | The envelope uses **`workspace_id`** (D22 vocabulary). M1 event types are exactly: `session.registered`, `session.state_changed`, `session.updated`, `needs_you.raised`, `needs_you.cleared`, `task.progress`, `subagent.count_changed`, `workspace.changed`, `repo.changed`. **`resync`** is added for reconnects outside the replay window. Every `session.*` event carries a full session card, so clients can apply events idempotently. | A project *is* a workspace (D22). `resync` is what makes gap replay honest after a `controld` restart. |
| DV-17 | D32: HTTP routes are generated from the registry; D22: `add_repo` is `local_destructive` | M1 hand-writes four mutating routes: create workspace, discover, register repo, deactivate repo. The CLI uses them; the UI stays read-only. There is no `authorize()` yet. **M4 replaces these routes with `to_http_routes` and gates `add_repo`.** | M1 has no registry. Widening the repo allowlist in M1 has no consumer, because nothing spawns before M3. Durability: near-term-refactor. |
| DV-18 | §8 hookd sketch forwards stdin raw | hookd parses the payload, **drops `tool_response`**, truncates strings longer than 8 KiB (recursion depth ≤ 6), and wraps the result in an envelope with `observed_at` and `/proc` ancestry. If the body is still over 1 MiB, it sends a minimal `{oversize, hook_event_name, session_id, cwd}`. If the JSON is unparseable, it sends `{unparsed_len}`. | Frames stay bounded. D24 discards the payload anyway, and M2 reads evidence from the transcript. T08 benchmarks it: a 5 MiB payload must finish well inside the budget. |
| DV-19 | none | hookd reads `/proc/<ppid>/stat` up to 6 levels and sends `[pid, comm, starttime]` triples. Any failure is swallowed and the list is empty; on macOS it is always empty. | This is the only process-liveness signal available for attached sessions (DV-09). |
| DV-20 | §15: every hook entry carries `"_shepherd_managed": true` | Each hook entry also embeds `--shepherd-managed` in its command. Ownership means `_shepherd_managed is True` **or** the command contains `hookd.py` and `--shepherd-managed`. The `_shepherd_managed` key is written only while `HOOK_MARKER_KEY_ENABLED = True`. **T19 runs a live probe; if `claude` rejects the key, the builder sets the constant to `False` and records it here.** | Ground truth 10: an unknown key could make Claude Code silently ignore the **whole** settings file. That breaks principle 4, so the key must be proven harmless before it reaches a real settings file. |
| DV-21 | §9: tmux socket and session naming | Config key **`tmux_socket`** (default `"shepherd"`) and constant `TMUX_SESSION_PREFIX = "shepherd_"` live in M1's config. Validation: the name matches `^[A-Za-z0-9_-]{1,64}$`, is never `"default"`, and **non-default profiles may not use `"shepherd"`**. The `test` and `qa` profiles default to `shepherd-test` and `shepherd-qa`. A repo-rules test requires `-L` on every tmux invocation in `src/`, `tests/`, `scripts/`, and bans `kill-server` without `-L`. | The 2026-09-12 incident and CLAUDE.md. The user's live Remote Control sessions already run on `shepherd` on this host, so the socket name must be configuration. M3 consumes it. |
| DV-22 | §13: "both Unix sockets" at 0600 | **Both sockets belong to `sessiond`:** `sessiond-hook.sock` (hookd, fire-and-forget) and `sessiond-control.sock` (the controld link). controld has no UDS in M1. | hookd floods can never starve the control connection. controld is restartable and connects to the long-lived sessiond, matching §5's arrow. |
| DV-23 | §7 Appendix: timestamps like `2026-09-11T10:22:41Z` | Every stored time is fixed-width UTC with milliseconds, `YYYY-MM-DDTHH:MM:SS.mmmZ` (24 chars), and CHECK-enforced. | Sorting by string stays correct, and ordering needs sub-second precision. |
| DV-24 | §7: `BOOLEAN` | Tables are `STRICT`. Booleans are `INTEGER CHECK (x IN (0,1))`. | `STRICT` does not allow `BOOLEAN`, and strict typing keeps a raw `sqlite3` shell honest. |
| DV-25 | §7.1: `engine` title source | Within `title_source='engine'`, the newest `custom-title` beats the newest `ai-title`. | `custom-title` is the user's rename inside Claude Code. It is engine-owned but more intentional than a generated title. The `user > engine > brief` ratchet is unchanged. |
| DV-26 | §12 ordering `needs_you → … → idle`, "never alphabetical, never by mtime" | Session rank: `needs_you`=0, `running`/`starting`=1, `stopped` with `ended_at IS NULL` ("at prompt")=2, `stopped` with `ended_at` set ("exited", which is M1's **idle**)=3. Ties: `needs_you` oldest `last_event_at` first (waited longest); others newest `started_at` first; then `id`. A workspace ranks by its best session; a workspace with none ranks 4. Exited sessions older than `fleet_idle_horizon_s` (86400) are hidden from the fleet and **counted** as "+N older". | M1 has only the three live states. The tie-breaks are state-derived, not file mtimes. The hidden count follows principle 5. |
| DV-27 | §18 lists `FULL OUTER JOIN` as an M1 probe | Answered: supported on 3.45.1. The M5 matrix needs no fallback. | Ground truth 9. |
| DV-28 | §8: `stopped` outranks nothing; hook events arrive in order | **Late-event guard:** an event with the same `prompt_id` as the last `Stop`, observed no later than `LATE_EVENT_GRACE_S = 1.0` after it, does not revive a `stopped` session. After `SessionEnd`, only `SessionStart` or `UserPromptSubmit` revive. | Each hook runs as its own process, so delivery order is not guaranteed (for example, `MessageDisplay` racing `Stop`). The grace window still lets a Stop-hook continuation (such as cc10x's), which reuses the `prompt_id` after a model turn, revive correctly. |
| DV-30 | §8 `state`: `running` = a tool/message signal within `LIVENESS_WINDOW_S`; `starting` is set at spawn | **`SessionStart` does not mean running.** `source ∈ {startup, resume, clear}`, absent, or unknown → `stopped` with `ended_at IS NULL`, labelled **"at prompt"**. `source == "compact"` → running, because compaction happens mid-work. A newly registered attached session takes its initial state from folding its first event: it is inserted as `stopped`/`ended_at NULL`, and the same handling step applies that event's fold before one combined notification. `starting` stays reserved for owned spawns (M3). | SessionStart is neither a tool nor a message signal. With DV-09's no-silence rule, a freshly opened, resumed or `/clear`-ed session idling at its prompt would otherwise show as ● running for up to `attached_abandon_s` (3 h). Found by fresh review (B1). The `resume`/`clear`/`compact` values are documented, not observed (A10); an unrecognized value falls back to the safe, not-running state. |
| DV-31 | §16 M1 slice does not list a credential store | T01 builds the `Credentials` seam (Protocol, `FileCredentials`, unverified `KeychainCredentials`, `ScriptedCredentials`, contract suite) **with no production caller in M1**. | The M1 planning request explicitly requires the platform seam "state dir, service supervision, credential store" with its Linux driver. Its cost is one small module plus a contract suite. M4.5/M5 are the first consumers, and the seam is stable (§6 verbatim). Kept rather than deferred on the requester's instruction; recorded so it does not read as scope creep (fresh-review A13). |
| DV-29 | `EngineCapabilities` for Claude Code (§6 matrix) | M1's `ClaudeCodeEngine.capabilities()` returns `can_spawn=False, can_steer=False, can_fork=False, can_set_title=False, has_hooks=True, effort_ladder=["low","medium","high","xhigh","max"], transcript_format="jsonl"`. M3 flips spawn, steer and fork after its probes. | A capability flag states what *this build* can do, not what the engine could do (D29). |

## Planner Decisions (inside the spec's latitude; spec §0 leaves these to the plan)

| ID | Decision | Rationale |
|---|---|---|
| PD-01 | **Concurrency model: threads, not asyncio.** `controld` uses `http.server.ThreadingHTTPServer` (one thread per SSE client). `sessiond` uses `socketserver.ThreadingUnixStreamServer` for both sockets and a **single writer thread** that owns all ingest mutation and in-memory fold memory, fed by a bounded `queue.Queue(10_000)`. | stdlib only, simple to reason about, and one writer thread means no lost updates between events. M4 can run the Agent SDK's asyncio loop in its own thread. |
| PD-02 | **sessiond inserts attached `session` rows (`register_attached_session`), is the only writer of `session` live/title columns, and bumps `workspace.last_activity_at` (coalesced, inside `apply_live_patch`). controld is the only writer of the rest of `workspace`, of `repo`, of the rebind columns (`session.workspace_id`/`repo_id` on rows with `repo_id IS NULL`), and of `app_state`.** Registration and rebinding each run in one `BEGIN IMMEDIATE`, so they serialize. Both processes use `store/` with WAL and `busy_timeout=5000`. | Disjoint column ownership gives read-modify-write safety without optimistic-version columns. The DB is the one store (principle 1). |
| PD-03 | **Pure core, IO shell.** `shepherd.domain.*`, `shepherd.ingest.events`, `shepherd.ingest.fold`, `shepherd.ipc.frames` (encode/decode), `shepherd.engine.claude_code.hooks_settings.merge_hooks/strip_hooks`, `shepherd.engine.claude_code.transcript.parse_signals` are pure and import no IO modules (enforced). | Everything with branching logic is testable at a unit seam without sockets or SQLite. |
| PD-04 | **Snapshot + stream consistency without locks:** `GET /api/fleet` returns `seq = hub.current_seq()` taken *before* the DB read. Every `session.*` event carries the full card, so replaying an event already reflected in the snapshot is harmless. | Removes a snapshot/stream race without holding a lock across a DB read. |
| PD-05 | **SSE seq survives controld restarts:** app_state key `sse.seq_reserved` holds R. Issued seqs are always `< R`. On startup, seq begins at the stored R and R is bumped by 10 000 before any event is issued. Clients whose `Last-Event-ID` is outside the in-memory ring (2048) or `> current` get a single `resync`. | Keeps §12's integer `seq` strictly monotonic across restarts with one write per 10 000 events. |
| PD-06 | **Package layout: `src/shepherd/`**, pytest `pythonpath=["src"]`, setuptools backend, **no runtime dependencies in M1** (dev: `pytest`, `mypy`). | Greenfield. `claude-agent-sdk` arrives with M4. |
| PD-07 | **hookd is a single stdlib-only file**, `src/shepherd/hookd.py`, that imports nothing from `shepherd`. `shepherd hooks install` copies it to `<data_dir>/bin/hookd.py` and bakes `shlex.join([<python3 realpath>, "-I", "-S", <copied hookd>, "--runtime-dir", <runtime_dir>, "--shepherd-managed"])` as the hook command. Each install is recorded in `<data_dir>/hooks_installed.json` as `{settings_path, runtime_dir, installed_at}`. `hooks install` and `status` **warn** when a recorded baked `runtime_dir` differs from the profile's current `runtime_dir` or has no `sessiond-hook.sock` (fresh-review A10). | Principle 4: minimal import time, no dependence on the venv or repo location. `-I -S` isolates it from user site and `PYTHON*` env. `shlex.join` makes the string safe for the shell Claude Code runs it in. We never use `shell=True` ourselves. |
| PD-08 | **Dev/test/QA isolation is a hard rule:** an autouse pytest fixture points `HOME`, `SHEPHERD_HOME`, `XDG_RUNTIME_DIR`, `XDG_CONFIG_HOME` at temp dirs and sets `SHEPHERD_PROFILE=test`. `SHEPHERD_HOME` is `make_short_base_dir()` (`tempfile.mkdtemp(prefix="shp-", dir="/tmp")`), so `<data_dir>/run/*.sock` stays under 108 bytes (DV-03). **No test writes `~/.claude`, enables a systemd unit, or runs tmux.** **Single exemption: `tests/live/`** (T19 only, skipped unless `SHEPHERD_LIVE=1`). The root fixture detects items under `tests/live/` and skips `HOME`/`Path.home` isolation there, because real `claude` needs the user's subscription auth and writes transcripts to the real `~/.claude/projects`. `tests/live/conftest.py` then enforces its own contract: `SHEPHERD_HOME`, `XDG_RUNTIME_DIR` and `XDG_CONFIG_HOME` stay isolated; the real home is used read-only by our code; and a session-scoped guard snapshots (a) the sha256 of `~/.claude/settings.json` (or "absent") and (b) the stdout, stderr and rc of `tmux -L shepherd ls`, then asserts both unchanged at session end. A mismatch fails the run and prints the diff. Because the user may legitimately change either during the run, a failure is resolved at the T19 HITL checkpoint by the user, never by relaxing the assertion. | CLAUDE.md, the §18 incident, and the fact that this host runs the user's live sessions. The live exemption exists because a temp `HOME` makes L5 unpassable (fresh-review B2). |
| PD-09 | **Subagent state from transcripts:** `finished` when the parent transcript contains a `tool_result` whose `tool_use_id == meta.toolUseId` **and** `meta.requestShape != "background"`; `running` when not finished and the parent is live; else `unknown`. | Reconstructible from engine files (principle 2). Background agents return a tool result immediately, so they are honestly `unknown` (counted). |
| PD-10 | **Brief for attached sessions** = latest `UserPromptSubmit.prompt` (≤ 4000 chars), which equals the transcript's `lastPrompt`. While `title_source='brief'`, `title` = the first 60 chars of the brief, whitespace collapsed. | §7 / §7.1 exactly. The hook gives it without a transcript read. |
| PD-11 | **Transcript reads happen only on `SessionStart`, `Stop`, `SessionEnd`** (title, model, effort), starting from a per-session in-memory byte offset. A `sessiond` restart re-reads from offset 0, which `read_jsonl_delta` defines as "the last 8 MiB, starting at the first complete line" for larger files (T10). | Titles arrive after turns, and reading on every event would cost IO per tool call. |
| PD-12 | **Exit codes:** `0` ok, `64` config/usage error, `69` controld unreachable (CLI only), `75` another instance holds the lock, `78` schema refusal. The systemd unit sets `RestartPreventExitStatus=75 78`. | The §7 migration refusals must not become a crash loop under a supervisor (the §7 rule-2 scenario). |
| PD-13 | **Single-instance locks:** `fcntl.flock` on `<runtime_dir>/controld.lock` and `<runtime_dir>/sessiond.lock`. sessiond unlinks a stale socket only while it holds its lock. | Two sessionds racing one socket path or two controlds racing migrations is undebuggable. `BEGIN IMMEDIATE` also serializes migrations. |

## Hidden-Assumption Pass

| # | Assumption | Class (`proven_by_code` / `inferred` / `needs_user_confirmation`) | If wrong |
|---|---|---|---|
| A1 | Interactive (TUI) `claude` sessions emit the same hook events and fields as the probed `-p` runs | **inferred** (critical) | T19 verifies this with an interactive session on `tmux -L shepherd-qa`. Folding is field-tolerant, so a missing event degrades one column, not ingest. |
| A2 | A hook process's `/proc` ancestry contains a process with `comm == "claude"` | inferred (non-critical) | Liveness falls back to the `attached_abandon_s` timeout (DV-09). T19 verifies. |
| A3 | `_shepherd_managed` in a hook entry passes Claude Code settings validation | inferred (non-critical; decision rule defined in DV-20) | Set `HOOK_MARKER_KEY_ENABLED=False`. The command marker alone identifies ownership. |
| A4 | `--resume` keeps `session_id` | proven_by_code (observed on host, ground truth 7) | n/a |
| A5 | Hook delivery order across concurrent hook processes is not guaranteed | inferred (designed for, DV-28) | If delivery is in fact ordered, the guard is a no-op. |
| A6 | Every observed event carries `cwd` | proven_by_code (probe data) | A first event without `cwd` defers registration and counts `deferred_no_cwd`. |
| A7 | The SQLite behaviours in ground truth 9 and §Codebase Reality Check | proven_by_code (executed on this host) | n/a |
| A8 | `PermissionRequest` with parallel tool calls on the same `tool_name` can clear `needs_you` early | inferred (accepted degrade) | `PermissionRequest` has no `tool_use_id`. The match is `(tool_name, agent_id)`. Recorded. |
| A10 | `SessionStart.source` takes the documented values `startup`, `resume`, `clear`, `compact` (only `startup` observed) | inferred (non-critical) | Unknown or absent values fall to at-prompt (DV-30); only `compact` revives. T19 L13 records observed sources. |
| A9 | The user reaches the fleet page through an SSH forward on the same port (§Codebase Reality Check) | needs_user_confirmation (only at the T19 HITL checkpoint; it does not block building) | T19 manual checks run from any loopback-capable browser on the host; the Host rule is unchanged |

## Preconditions Recorded for Later Milestone Plans (not M1 work)

**M2 plan must:**
- Redesign the §8 completeness gate. `Stop` has no `stop_reason`, so `end_turn` has no direct source. Candidates: the last `assistant` transcript entry's `message.stop_reason`, to be probed.
- Treat the 10 mechanical reasons that depend on `StopFailure.error_type` and `Notification` as `unknown` unless new evidence appears.
- Resolve the `decided_by` enum conflict (§7 vs D34's `heuristic`).
- Add the six stop-group columns via `ADD COLUMN` (DV-10).
- Note that `SessionEnd.reason` has only been observed as `"other"`.
- Decide whether `pr_url` has any source (DV-08).
- Own the stops log (D25), reusing M1's `shepherd.jsonl` reader and `shepherd.logs` rotation.

**M3 plan must (tmux precondition):**
1. **Finish the §18 tmux ↔ TUI spike on a throwaway socket.** Use `tmux -L shepherd-spike …` for every call, teardown included (`tmux -L shepherd-spike kill-server`). Never run a bare `kill-server`. Pass `-L` explicitly even inside tmux, because `$TMUX` otherwise resolves to the enclosing socket.
2. Session names are **settled as `shepherd_<session_id>`**. `:` and `.` are tmux target separators. The spike must still confirm that `-t shepherd_<id>` resolves exactly to that session.
3. The runner socket comes from **`ShepherdConfig.tmux_socket`** (M1, DV-21). On this dev host the user's live sessions own `shepherd`, so every M3 build, test and QA run uses a non-default profile (`shepherd-test`, `shepherd-qa`).
4. The spawn path must handle **Claude Code's workspace-trust dialog**. A fresh directory blocks on "No, exit" by default and fires no hooks until it is answered (ground truth 11).
5. systemd: sessiond's unit uses `KillMode=process`. Verify that tmux servers spawned by sessiond survive `systemctl --user restart` (cgroup membership). Otherwise D14's "survives sessiond restart" fails under systemd. Root has `Linger=no`, so user units stop at logout.
6. Add a `mailbox_message` migration (DV-15), run the D29 title write-back probe, and verify forking for `ask()`.
7. Extend `EngineAdapter` with `spawn_argv`/`set_title`, and `ScriptedEngine` alongside it (DV-14).

**M4 plan must:**
- Add an `approval` table migration (DV-15).
- Replace M1's hand-written mutating routes with registry exporters and gate `add_repo` as `local_destructive` (DV-17).
- Note that `test_repo_rules.py` already carries the D19 `shepherd.master` import rule, which passes vacuously in M1.

**M5 plan must:**
- Decide how to add the `session.work_item_id` FK (DV-11).
- Note that `FULL OUTER JOIN` is available (DV-27).

## Functionality Flows (each step and error path maps to a test)

```
Flow A — a hand-launched session appears on the fleet page
1. user runs `claude` in /work/ox/api (hooks installed) → Claude Code runs hookd with the SessionStart payload
   → test: tests/unit/test_hookd.py::test_sends_enveloped_frame
2. hookd builds the envelope and writes a HOOK_EVENT frame to sessiond-hook.sock within 250 ms, exits 0, no output
   → test: tests/unit/test_hookd.py::test_exit_zero_matrix
3. sessiond validates magic, version, token and length, then enqueues
   → test: tests/unit/test_frames.py::test_decode_header_rejections, tests/integration/test_sessiond.py::test_hook_socket_rejects_bad_token
4. the writer parses tolerantly and registers the attached session, binding cwd by longest prefix
   → test: tests/unit/test_events.py::test_parse_total, tests/unit/test_binding.py::test_innermost_repo_wins,
           tests/integration/test_store_sessions.py::test_register_idempotent
5. fold → SessionStart leaves it at prompt (stopped, ended_at null; DV-30), last_event_at set → store patch → one combined SESSION_CHANGED frame (session.registered) to controld; the first UserPromptSubmit/tool event moves it to running
   → test: tests/unit/test_fold.py::test_session_start_idle_is_not_running, tests/integration/test_sessiond.py::test_change_pushed_to_control
6. controld publishes session.registered with a card; SSE clients receive it
   → test: tests/unit/test_events_hub.py::test_publish_order, tests/integration/test_e2e_scripted.py::test_hook_to_sse
7. the fleet page inserts the card at its rank
   → test: tests/unit/test_ordering.py::test_session_order_key; manual: T19 checklist L7
Error paths:
- sessiond down / socket missing → hookd exit 0, wall < 300 ms → test_hookd.py::test_socket_absent
- sessiond accepts but never reads → hookd deadline → test_hookd.py::test_blocked_socket_deadline
- malformed / non-JSON payload → counted `malformed`, no row → test_events.py::test_malformed_counts
- cwd matches no repo or workspace root → wsp_unassigned, shown → test_binding.py::test_unassigned_fallback
- sessiond not yet schema-gated → events buffered (bounded), folded after SCHEMA_READY → test_sessiond.py::test_gate_buffers_then_drains
- writer queue full → `dropped_backpressure` counted → test_sessiond.py::test_backpressure_counts

Flow B — a permission prompt surfaces as needs_you
1. PermissionRequest{tool_name: Bash, tool_input.command: "npm test"} → needs_you, reason "permission: Bash(npm test)"
   → test: test_fold.py::test_permission_request_raises
2. controld publishes needs_you.raised and session.state_changed → test: test_e2e_scripted.py::test_needs_you_roundtrip
3. user approves → PostToolUse(Bash) → running, reason cleared → test: test_fold.py::test_matching_posttool_clears
Error paths:
- user denies → Stop → stopped, reason cleared → test_fold.py::test_stop_clears_needs_you
- tool_name absent → "permission: (unknown tool)" → test_fold.py::test_permission_reason_absent_fields
- PostToolUse for a different tool while pending → stays needs_you → test_fold.py::test_nonmatching_posttool_keeps

Flow C — expand a session's subagents
1. SubagentStart/SubagentStop → active_subagents ±1 (clamped ≥ 0) → test: test_fold.py::test_subagent_counts_clamp
2. UI GET /api/sessions/{id}/subagents → engine.list_subagents reads meta.json + parent transcript
   → test: test_transcript.py::test_list_subagents_states, test_http_api.py::test_subagents_projection
Error paths:
- transcript missing → empty list (200) → test_transcript.py::test_missing_transcript_empty
- malformed trailing line → skipped and counted → test_jsonl.py::test_skips_malformed_trailing_line

Flow D — browser reconnects after a gap
1. EventSource reconnects with Last-Event-ID k → events k+1..current, in order, no duplicates
   → test: test_events_hub.py::test_gap_replay_exact, test_sse_http.py::test_last_event_id_header_replay
2. k outside the ring, k > current, or k from before a controld restart → exactly one `resync`
   → test: test_events_hub.py::test_resync_outside_ring, test_events_hub.py::test_seq_monotonic_across_restart

Flow E — register a workspace and its repos
1. `shepherd workspace add ox --root /work/ox` → POST /api/workspaces → repo-less sessions under the root are rebound
   → test: test_store_workspaces.py::test_create_workspace_rebinds_unassigned
2. `shepherd discover /work/ox --workspace ox --add` → candidates → POST /api/repos for each
   → test: test_discovery.py::test_finds_nested_git_dirs, test_cli.py::test_discover_add_posts
Error paths:
- path already registered to another workspace → 409 with generic text → test_http_api.py::test_repo_conflict_409
- cross-origin POST → 403 → test_http_security.py::test_origin_rejected
- symlink loop during discovery → not followed → test_discovery.py::test_does_not_follow_symlinks

Flow F — start or upgrade against an incompatible database
1. controld start → apply_migrations in one transaction → test: test_migrate.py::test_fresh_apply
2. an applied checksum differs → exit 78, no writes → test: test_migrate.py::test_checksum_mismatch_refuses
3. DB version > bundled → exit 78 → test: test_migrate.py::test_db_newer_refuses
4. sessiond receives a mismatched SCHEMA_READY → stays gated, never migrates → test: test_sessiond.py::test_schema_mismatch_stays_gated
```

## Architecture

### Container view (M1)

```
browser ──HTTP/SSE 127.0.0.1:<http_port>──► controld ──UDS sessiond-control.sock (frames)──► sessiond
                                              │                                              ▲
                                              │ store/ (SQLite WAL)                          │ UDS sessiond-hook.sock
                                              └────────────── shepherd.db ◄──────────────────┤ (HOOK_EVENT frames)
                                                                                             │
                                     claude (attached) ──hook stdin──► hookd.py ─────────────┘
                                     ~/.claude/projects transcripts ◄── read-only by engine/claude_code (sessiond + controld)
```

| Container | Responsibility | Writes | Restart semantics |
|---|---|---|---|
| `hookd.py` | Forward one hook payload. Never harm Claude. | nothing | per event, one short process |
| `sessiond` | Ingest, fold, liveness sweep, title/model refresh from transcripts | inserts attached `session` rows; `session` live and title columns; `workspace.last_activity_at` (coalesced) | long-lived. Loses in-memory fold memory (pending permission, last stop prompt id, pid, transcript offsets), all recoverable from later events. |
| `controld` | Migrate; serve API, SSE, UI; handle registration | `workspace` (except `last_activity_at`), `repo`, rebind columns, `app_state` | restartable freely. Clients get `resync`. |

### Integration table

| System | Protocol | Direction | Contract | Failure mode | Retry |
|---|---|---|---|---|---|
| Claude Code hooks | command hook, JSON on stdin | they call us | §Ground Truth 1 | hookd exits 0, event lost, degrade is visible | none (principle 4) |
| Claude Code transcripts | JSONL files | we read | §Ground Truth 5–6 | missing or malformed → column stays null, counted | next Start/Stop/End |
| Claude Code settings | JSON file merge | we write (CLI, explicit target) | DV-20 | invalid source JSON → refuse; backup before every write | manual |
| systemd `--user` / launchd | unit or plist files | we write files; user enables | T03 | not enabled → foreground `shepherd controld run` | supervisor restart, except exit 75/78 |

Dependency classes: Claude Code is **Wrapped** (`EngineAdapter`). SQLite is **Infra wrapped by `store/`** (D26). systemd, launchd, Keychain and `/proc` are **Wrapped** (platform seam).

### Observability (M1)

- **Logs:** `logs/daemon/{controld,sessiond}.log`. Daily rotation plus a 50 MB size cap, gzip on rotation, 14 days (D25). Logged events: start/stop, migration report or refusal, socket bind, link connect/disconnect, gate open/close, frame rejections (reason, never the token), counters every 5 min.
- **Counters (principle 5, shown on the fleet footer):** `frames_rejected`, `malformed`, `unknown_event`, `deferred_no_cwd`, `dropped_backpressure`, `notifications_dropped`, `transcript_malformed_lines`, plus `unassigned_sessions` and `hidden_idle` from the store.
- **Health:** `GET /api/health` → controld schema version, boot id, link status, sessiond gated flag and counters.

### Module layout (component view)

```
pyproject.toml                                   T00  project, mypy strict, pytest markers (slow, live), setuptools
scripts/bootstrap_venv.sh                        T00  venv --without-pip + get-pip.py via python urllib + pip install -e '.[dev]'
src/shepherd/__init__.py                         T00
src/shepherd/jsontypes.py                        T00  JsonValue, JsonObject
src/shepherd/timeutil.py                         T00  utc_now_iso, to_iso, parse_iso, iso_age_s
src/shepherd/ids.py                              T00  new_id
src/shepherd/exitcodes.py                        T00  EXIT_OK, EXIT_CONFIG, EXIT_LOCKED, EXIT_SCHEMA_REFUSED
src/shepherd/config.py                           T02  ShepherdConfig, resolve_profile, load_config, ConfigError, TMUX_SESSION_PREFIX
src/shepherd/platform/__init__.py                T03  Platform, current_platform
src/shepherd/platform/base.py                    T02  PlatformPaths, ensure_private_dirs, ProcessProbe, ServiceSupervisor, ServiceSpec, ServiceStatus, names
src/shepherd/platform/linux.py                   T02+T03  linux_paths, LinuxProcessProbe (T02); SystemdUserSupervisor (T03)
src/shepherd/platform/macos.py                   T02+T03  macos_paths, DarwinProcessProbe (T02); LaunchdSupervisor (T03)   (UNVERIFIED)
src/shepherd/platform/credentials.py             T01  Credentials, AuthMaterial, FileCredentials, KeychainCredentials, errors
src/shepherd/domain/models.py                    T04  dataclasses + Literals + UNSET
src/shepherd/domain/signals.py                   T04  Signal union
src/shepherd/domain/binding.py                   T04  path binding (pure)
src/shepherd/domain/ordering.py                  T04  order keys + labels (pure)
src/shepherd/store/_conn.py                      T05  connection factory, pragmas
src/shepherd/store/migrate.py                    T05  apply_migrations
src/shepherd/store/schema.py                     T05  SCHEMA_VERSION, read_schema_version
src/shepherd/store/errors.py                     T05+T06
src/shepherd/store/migrations/0001_foundation.sql T05
src/shepherd/store/__init__.py                   T06  exports Store + errors
src/shepherd/store/store.py                      T06  Store (open, workspace/repo/app_state verbs; delegates session verbs)
src/shepherd/store/_sessions.py                  T06  session SQL
src/shepherd/store/_rows.py                      T06  row → dataclass converters
src/shepherd/discovery.py                        T07
src/shepherd/ipc/frames.py                       T08
src/shepherd/ipc/messages.py                     T08
src/shepherd/hookd.py                            T08  standalone, stdlib only
src/shepherd/ingest/events.py                    T09
src/shepherd/ingest/fold.py                      T09
src/shepherd/jsonl.py                            T10
src/shepherd/engine/claude_code/transcript.py    T10
src/shepherd/engine/claude_code/hooks_settings.py T11
src/shepherd/engine/base.py                      T12
src/shepherd/engine/claude_code/adapter.py       T12
src/shepherd/testkit/env.py                      T02  isolated_env, make_short_base_dir
src/shepherd/testkit/scripted_platform.py        T02+T03  ScriptedProcessProbe (T02); ScriptedSupervisor (T03)
src/shepherd/testkit/scripted_credentials.py     T01
src/shepherd/testkit/hook_payloads.py            T09
src/shepherd/testkit/scripted_engine.py          T12
src/shepherd/logs.py                             T13
src/shepherd/sessiond/{writer,ingest_service,servers,main}.py   T13
src/shepherd/controld/{events,sessiond_link,main}.py            T14
src/shepherd/controld/{security,projections,http}.py            T15
src/shepherd/web/static/{index.html, css/app.css, js/app.js, js/api.js, js/sse.js, js/fleet.js, js/dom.js}  T16
src/shepherd/cli/{__main__,main,http_client}.py  T17
tests/conftest.py                                T00+T02 (autouse isolation)
tests/test_repo_rules.py                         T00
tests/{unit,integration,contract,perf,live}/…    per task
tests/fixtures/hooks/*.json                      T09  sanitized probe payloads (paths rewritten under /work)
tests/fixtures/claude_projects/…                 T10  sanitized transcripts + subagents dir
```

### Import rules (enforced by `tests/test_repo_rules.py`; AST-based, written in T00, applies to packages as they appear)

| Rule | Statement |
|---|---|
| R1 | `sqlite3` is imported only under `shepherd/store/` (D26). |
| R2 | `shepherd.store.migrate` is imported only by `shepherd.store`, `shepherd.controld`, and tests. **`shepherd.sessiond` never** (§7 migration rule 3). |
| R3 | `shepherd.store._conn`, `._rows`, `._sessions` are imported only inside `shepherd.store` (D33). |
| R4 | `shepherd.sessiond` ↛ `shepherd.controld`, and `shepherd.controld` ↛ `shepherd.sessiond`. They share only `shepherd.ipc`. |
| R5 | `shepherd.hookd` imports only `{sys, os, json, socket, struct, time}` and nothing from `shepherd`. |
| R6 | Pure modules `shepherd.domain.*`, `shepherd.ingest.*`, `shepherd.ipc.frames`, `shepherd.ipc.messages`, `shepherd.engine.base` import none of `{socket, sqlite3, http, subprocess, threading, urllib}` and none of `shepherd.{store,controld,sessiond,cli,platform}`. `shepherd.ipc.frames.read_frame` takes a socket-like `Protocol`, so it does not import `socket`. |
| R7 | `shepherd.engine` ↛ `shepherd.store`. |
| R8 | Production modules ↛ `shepherd.testkit`. |
| R9 | If `shepherd/master/` exists, it imports only `shepherd.toolsurface.client`, `claude_agent_sdk`, and stdlib (D19). Vacuous in M1. |
| R10 | No `shell=True`, `os.system`, `os.popen`, `subprocess.getoutput`, `subprocess.getstatusoutput` (§13). |
| R11 | No `Any` imported from `typing` (principle 6). mypy `disallow_any_explicit = true` as well. |
| R12 | No `.py` file under `src/` or `tests/` exceeds 600 lines. |
| R13 | `src/shepherd/web/**` contains none of `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function` (§13). |
| R14 | In `src/`, `tests/`, `scripts/`, every `tmux` invocation (string or argv literal) includes `-L`. `kill-server` appears only right after `-L <name>` with name ∉ {`shepherd`, `default`} (CLAUDE.md). |

## Critical-Path Contracts

### Behavior contract 1 — the fold state machine (`shepherd.ingest.fold.fold_event`)

Notation: `S` is the current `Session`, `M` the in-memory `FoldMemory`, `e` the `HookEvent`, `t` the envelope's `observed_at` (float epoch seconds from hookd), and `iso(t)` its ISO string.

**Always applied:**
- `last_event_at := max(S.last_event_at, iso(t))`
- if `M.engine_proc is None`, set `M.engine_proc` to the first ancestor whose `comm ∈ process_names`

**`late(e)`** is true if either:
- `S.state == "stopped"`, `M.ended is False`, `e.prompt_id is not None`, `e.prompt_id == M.last_stop_prompt_id`, and `t <= M.last_stop_observed_at + LATE_EVENT_GRACE_S` (1.0); or
- `M.ended is True` and `e.name ∉ {"SessionStart", "UserPromptSubmit"}`.

**`revive`** means: if `S.state ∈ {"stopped", "starting"}` and not `late(e)`, then set `state := "running"`.

| `e.name` | State effect | Other column effects | Memory effect | `refresh_transcript` |
|---|---|---|---|---|
| `SessionStart` | `source == "compact"` → revive (running). Any other `source` (`startup`, `resume`, `clear`, absent, or unknown) → `stopped` with `ended_at := None` (**at prompt**, DV-30) | `ended_at := None`; `needs_you_reason := None` | `ended=False`, `pending=None`, `last_stop_prompt_id=None` | yes |
| `UserPromptSubmit` | `running` (always) | `needs_you_reason := None`; `ended_at := None`; if `prompt` is a str: `brief := prompt[:4000]`, and if `S.title_source == "brief"` then `title := brief_title(prompt)` | `ended=False`, `pending=None`, `last_stop_prompt_id=None` | no |
| `PermissionRequest` | if late: **no effect at all** (no state, reason, or pending change). Otherwise `needs_you` | only when not late: `needs_you_reason := permission_reason(tool_name, tool_input, cwd)` | only when not late: `pending := (tool_name, agent_id)` | no |
| `PostToolUse` | if not late: if `S.state == "needs_you"` and (`M.pending is None` or `M.pending == (tool_name, agent_id)`), set `running` and clear the reason; else revive | if `tool_name ∈ PATH_TOOLS`: `repos_touched := append_unique(repo_for_path(path))`, capped at 50 | on clear: `pending=None` | no |
| `PostToolUseFailure`, `PermissionDenied` | handled exactly like `PostToolUse` for the pending match (clear `needs_you` → `running`) and revive. Neither is in the probe; both are consumed defensively (A3 / fresh-review A3) | none (no `repos_touched` update) | on clear: `pending=None` | no |
| `PreToolUse`, `MessageDisplay` | revive (`needs_you` unchanged) | none | none | no |
| `TaskCreated` | revive | `tasks_total += 1` | none | no |
| `TaskCompleted` | revive | `tasks_done += 1`; `tasks_total := max(tasks_total, tasks_done)` | none | no |
| `SubagentStart` | revive | `active_subagents += 1` | none | no |
| `SubagentStop` | none | `active_subagents := max(0, active_subagents - 1)` | none | no |
| `Stop` | if not `M.ended`: `stopped` | `needs_you_reason := None`; if `background_tasks == []`: `active_subagents := 0` | `pending=None`, `last_stop_prompt_id=e.prompt_id`, `last_stop_observed_at=t` | yes |
| `SessionEnd` | `stopped` | `ended_at := iso(t)`; `active_subagents := 0`; `needs_you_reason := None` | `ended=True`, `pending=None` | yes |
| any other name | none | none (only `last_event_at`) | none | no; the service counts `unknown_event` if the name ∉ `KNOWN_EVENTS` |

**Invariants the fold must keep:**
- `(state == "needs_you") ⇔ (needs_you_reason is not None)`
- counters ≥ 0
- `tasks_done ≤ tasks_total`
- `repos_touched` has no duplicates and at most 50 entries
- `title_source` never moves down the `user > engine > brief` ratchet

`FoldOutcome.changes` lists the change kinds for every column group that actually changed. If nothing changed besides `last_event_at`, it is empty. **Liveness throttling is the service's job, not the fold's.** `IngestService` writes a liveness-only patch at most once per 5 s per session (`LIVENESS_WRITE_INTERVAL_S = 5`), and sends a liveness-only `SessionChange` with `kinds=("session.updated",)` at most once per 30 s per session (`LIVENESS_NOTIFY_INTERVAL_S = 30`). A 30 s ceiling is well under `liveness_window_s` (90), so the UI's "quiet" chip never shows for an active session.

**`sweep_decision(session, memory, now_iso, abandon_s, proc_alive)`**, run every 15 s by the writer thread:
1. If (`session.state ∈ {running, needs_you, starting}`, or `state == "stopped"` with `ended_at is None`), `memory.engine_proc` is set, and `proc_alive(pid, starttime)` is False → patch `state="stopped"`, `ended_at=now`, `active_subagents=0`, `needs_you_reason=None`.
2. Else if `session.state ∈ {running, starting}` and `iso_age_s(last_event_at, now) > abandon_s` → patch `state="stopped"` (ended_at unchanged).
3. Else → `None`. **`needs_you` is never aged out.**

`permission_reason`:

| Tool | Reason |
|---|---|
| `Bash` | `permission: Bash(<command, first line, ≤80 chars>)` |
| `Edit`/`Write`/`MultiEdit`/`Read`/`NotebookEdit` | `permission: <Tool>(<path relative to cwd if under it, else basename>)` |
| `WebFetch` | `permission: WebFetch(<hostname>)` |
| other, with `tool_name` | `permission: <tool_name>` |
| `tool_name` absent | `permission: (unknown tool)` |

Output is stripped of control characters and capped at 160 chars.

### Behavior contract 2 — SSE (`EventHub`)

- `publish` is called from the sessiond-link thread and from HTTP handler threads. Under one `threading.Lock`, it assigns `seq = next`, reserves a new block if needed, appends to a `deque(maxlen=2048)`, and enqueues to subscribers. Seq is therefore strictly increasing across concurrent publishers.
- `current_seq()` is the last issued seq, or `start - 1` before anything has been issued.
- `subscribe(last_event_id)`:
  - `None` → live only.
  - `k == current` → live only. This holds **including when the ring is empty**, such as a page that fetched `/api/fleet` right after controld started; there is no resync loop.
  - ring non-empty and `ring_first - 1 <= k < current` → replay `(k, current]` and then live, in one ordered sequence. Subscription registration and replay happen under the same lock as `publish`, so no event falls between them.
  - otherwise → one `resync` event (`seq` = current, `data={"reason": "out_of_window"}`), then live.
- A slow subscriber whose private queue exceeds 4096 events gets a `resync` and its backlog is dropped. Publishing never blocks.
- Wire format per event: `id: <seq>\nevent: <type>\ndata: <json envelope>\n\n`. Heartbeat is `: hb\n\n` every 15 s. The first bytes are `retry: 2000\n\n`. `Last-Event-ID` header takes precedence over the `?last_event_id=` query.

### Edge-case catalog (each has a named test in its task)

| # | Edge case | Expected | Task |
|---|---|---|---|
| E01 | hookd: socket path missing, refused, or a directory | exit 0, no output, < 300 ms | T08 |
| E02 | hookd: peer accepts and never reads, with 2 MiB of socket buffer pressure | exit 0 within the deadline | T08 |
| E03 | hookd: empty stdin, binary garbage, JSON array, 5 MiB payload | exit 0; envelope `unparsed_len` or stripped | T08 |
| E04 | hookd: token file missing or unreadable | exit 0, nothing sent | T08 |
| E05 | frame: bad magic, version 2, oversize length, short header, wrong token | rejected before the body is read, counted | T08, T13 |
| E06 | payload fields with the wrong type (`cwd: 5`, `tool_input: "x"`, `effort: "high"` string) | field becomes None, no raise | T09 |
| E07 | first event for an unknown session is `Stop` or `SessionEnd` | registered, then stopped | T09, T13 |
| E08 | `MessageDisplay` delivered after `Stop` with the same `prompt_id` within 1 s | stays stopped | T09 |
| E09 | Stop-hook continuation: same `prompt_id`, 5 s after `Stop` | revives to running | T09 |
| E10 | `SubagentStop` without `SubagentStart` (after a sessiond restart) | stays 0 | T09 |
| E11 | `TaskCompleted` with no `TaskCreated` seen | `done=1`, `total=1` | T09 |
| E12 | cwd `/a/foobar` with repo `/a/foo` | no match | T04 |
| E13 | nested repos `/a` and `/a/b`, cwd `/a/b/c` | `/a/b` | T04 |
| E14 | cwd through a symlink into a repo | binds (realpath) | T04 |
| E15 | repo root `/` registered | allowed only as an explicit path; matches everything, lowest priority | T04 |
| E16 | re-register an inactive repo path in the same workspace | reactivated, `reactivated=True` | T06 |
| E17 | register a path already active in another workspace | `RepoPathConflict` → 409 | T06, T15 |
| E18 | migration file edited after apply | refuse, exit 78 | T05 |
| E19 | DB applied version 2, binary knows 1 | refuse, exit 78 | T05 |
| E20 | migration SQL fails midway | full rollback; version unchanged; no partial table | T05 |
| E21 | non-contiguous migration files (0001, 0003) | `MigrationSetInvalid` | T05 |
| E22 | two controlds start concurrently | one migrates, the other exits 75 (lock) | T14 |
| E23 | transcript last line truncated mid-write | skipped; offset stops before it; re-read after completion | T10 |
| E24 | `transcript_path` outside `claude_projects_dir` (e.g. `/etc/passwd`) | ignored, counted | T13 |
| E25 | settings file is invalid JSON | `SettingsFileInvalid`, file untouched | T11 |
| E26 | settings with user hooks on the same events | preserved exactly after install then uninstall | T11 |
| E27 | SSE `Last-Event-ID` garbage (`abc`) or negative | treated as out of window → `resync` | T14 |
| E28 | controld restart between client events | client gets `resync`; seq stays > previous max | T14 |
| E29 | Host header `evil.com:7420` (DNS rebinding) | 403 | T15 |
| E30 | POST with `Origin: http://evil.com` | 403; no `Origin` + valid Host + JSON content type → allowed | T15 |
| E31 | untrusted strings (`<img onerror>`) in title, brief or reason | rendered as text | T15 (JSON), T16 (textContent + R13) |
| E32 | runtime dir is group/other-accessible or owned by another uid | sessiond refuses to start (exit 64) | T13 |
| E33 | AF_UNIX path > 107 bytes | `ConfigError` with a clear message | T02 |
| E34 | profile `qa` with `tmux_socket = "shepherd"` | `ConfigError` | T02 |
| E35 | an engine process dies with no `SessionEnd` | the sweep marks it stopped within 30 s (probe) | T09, T13 |
| E36 | a permission prompt left open for 10 h | still `needs_you` | T09 |
| E37 | POST body is not valid JSON, not an object, or has missing/wrong-typed fields | 400 `{"error":"bad request"}` | T15 |
| E38 | POST body > 64 KiB by `Content-Length`, or `Content-Length` absent | 413 / 411; body not read | T15 |
| E39 | `config.json` invalid JSON, wrong types, or unknown keys | `ConfigError` naming the key (unknown keys rejected); daemon exits 64 | T02 |
| E40 | discover `root_path` missing, not a directory, relative, or unreadable | 400; nothing registered | T07, T15 |
| E41 | workspace name empty or > 200 chars; repo path relative or nonexistent | 400 (store CHECK is the backstop) | T06, T15 |
| E43 | `SessionStart` with source startup/resume/clear, or absent (fresh session idle at prompt) | `stopped`, `ended_at` null, label "at prompt"; never running (DV-30) | T09, T13 |
| E44 | TUI permission denied or Esc | observed and recorded; clears on any consumed follow-up event (T19 L3b decision rule) | T09, T19 |
| E45 | page connects with `last_event_id == current` while the ring is empty | live stream, no resync loop | T14 |
| E46 | controld connected but not reading (stalled) | writer unaffected; connection closed after 2 s send timeout; drops counted | T13 |
| E47 | hooks baked with a runtime dir different from the daemon's | `hooks install`/`status` print WARNING; runtime dir is env-independent so the case needs a `SHEPHERD_HOME` change | T02, T17 |
| E42 | CLI given an invalid profile name, or controld not running | exit 64 with a message; `ControldError` for connection failure → exit 69 | T17 |

### Provable properties (and how each is proven)

| ID | Property | Proof |
|---|---|---|
| P01 | For every stdin input and socket condition, hookd exits 0 with empty stdout and stderr, in wall time ≤ interpreter start + 250 ms + 50 ms slack | subprocess matrix test over E01–E04 (T08) |
| P02 | `apply_migrations` is atomic: afterwards `schema_version ∈ {before, max_bundled}` and `sqlite_master` equals the snapshot of one of those two states | injected-failure test + SIGKILL-mid-apply test (slow lane) (T05) |
| P03 | A refusal (checksum or newer) performs zero writes: the DB file bytes are unchanged | hash-before/after test (T05) |
| P04 | sessiond never executes DDL | R2 import rule + integration test on an unmigrated DB: sessiond stays gated and `sqlite_master` stays empty (T13) |
| P05 | `bind_cwd` returns the repo with the maximal `root_path` that is a component-wise prefix of canonical cwd, independent of input order | table tests + a permutation property test over all orderings of 6 repos (T04) |
| P06 | `parse_envelope` and `fold_event` are total: no input raises; invariants hold after every step | randomized sequence test: 2000 seeded random event sequences of fixture-derived and mutated payloads; invariants asserted after each step (T09) |
| P07 | `(state='needs_you') ⇔ needs_you_reason IS NOT NULL`, counters ≥ 0, `tasks_done ≤ tasks_total` also hold in the DB | SQL CHECK constraints (T05) + constraint-violation tests (T05) |
| P08 | SSE replay delivers exactly `(k, current]` in order with no duplicates, or exactly one `resync`; seq is strictly increasing across hub restarts on the same store | hub unit tests + HTTP-level test (T14) |
| P09 | No API response contains a key outside its projection whitelist; no raw row escapes | key-set equality tests for every route (T15) |
| P10 | The import and source rules R1–R14 hold | `tests/test_repo_rules.py` (T00, extended as packages land) |
| P11 | A frame with the wrong token, magic, version or length is rejected before JSON parsing; token comparison is constant-time (`hmac.compare_digest`); sockets are 0600 and the runtime dir is 0700 | unit + `os.stat` tests (T08, T13) |
| P12 | For any valid settings object `s`: `strip(merge(s)) == strip(s)`, `merge(merge(s)) == merge(s)`, and non-shepherd entries are preserved in order | property test over generated settings (T11) |
| P13 | `title_source` is monotone under the ratchet for any sequence of signals and UI renames | unit test (T09) + store-level guarded UPDATE test (T06) |

### Purity boundary map

| Pure (unit seam, no IO) | Impure shell (integration seam) |
|---|---|
| `domain.binding`, `domain.ordering`, `domain.models`, `domain.signals` | `store.*` (SQLite) |
| `ingest.events.parse_envelope`, `ingest.fold.*` | `sessiond.*` (sockets, threads) |
| `ipc.frames.encode_frame/decode_header`, `ipc.messages.*` | `ipc.frames.read_frame` (a reader Protocol; tested with socketpair) |
| `engine.claude_code.transcript.parse_signals`, `project_slug`, `subagent_state` | `jsonl.read_jsonl_delta`, `transcript.locate_transcript_in`, `list_subagents_in` (files) |
| `engine.claude_code.hooks_settings.merge_hooks/strip_hooks/is_shepherd_entry/hook_command` | `hooks_settings.install_into/uninstall_from` (files, backup, atomic write) |
| `controld.events.EventHub` (in-memory, deterministic; store only for `reserve_event_seq`) | `controld.http`, `controld.sessiond_link` |
| `controld.projections.*`, `controld.security.check_host/check_origin` | `hookd.main`, `discovery.discover_repos`, `platform.*` drivers |

### Verification strategy (lanes)

| Lane | Marker / command | Contents | Gate |
|---|---|---|---|
| L0 static | `.venv/bin/python -m mypy` (config: `strict`, `disallow_any_explicit`, `warn_unreachable`, files `src`, `tests`) | types | every task |
| L1 unit | `.venv/bin/python -m pytest -q tests/unit tests/test_repo_rules.py` | pure modules, hookd subprocess matrix | every task |
| L2 integration | `.venv/bin/python -m pytest -q tests/integration tests/contract` | store on a temp DB, daemons on temp sockets, HTTP on an ephemeral port, contract suites | T05+ |
| L3 slow | `.venv/bin/python -m pytest -q -m slow` | SIGKILL mid-migration, hook-volume measurement | T05, T18 |
| L4 live | `SHEPHERD_LIVE=1 .venv/bin/python -m pytest -q -m live tests/live` + the manual checklist | real `claude` on profile `qa`, throwaway project | T19 (HITL) |

Default `pytest` addopts: `-m "not slow and not live"`. Live tests skip unless `SHEPHERD_LIVE=1`.

---

# PART 2 — EXECUTION CONTRACT LAYER (buildable without improvisation)

## Spec S1 — `src/shepherd/store/migrations/0001_foundation.sql` (exact DDL)

The runner creates `schema_migration` itself, before applying any file, inside the same transaction. It is not part of `0001`.

```sql
CREATE TABLE IF NOT EXISTS schema_migration (
  version    INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  checksum   TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
```

`0001_foundation.sql`:

```sql
-- 0001_foundation: M1 tables. work_item/queue arrive in M5; stop-group columns in M2 (plan DV-10, DV-11).

CREATE TABLE workspace (
  id               TEXT PRIMARY KEY CHECK (id GLOB 'wsp_*'),
  owner_id         TEXT NOT NULL DEFAULT 'local',
  name             TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  root_path        TEXT CHECK (root_path IS NULL OR substr(root_path, 1, 1) = '/'),
  created_at       TEXT NOT NULL CHECK (length(created_at) = 24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z'),
  last_activity_at TEXT CHECK (last_activity_at IS NULL OR length(last_activity_at) = 24)
) STRICT;

INSERT INTO workspace (id, owner_id, name, root_path, created_at, last_activity_at)
VALUES ('wsp_unassigned', 'local', '(unassigned)', NULL, '1970-01-01T00:00:00.000Z', NULL);

CREATE TABLE repo (
  id           TEXT PRIMARY KEY CHECK (id GLOB 'rep_*'),
  owner_id     TEXT NOT NULL DEFAULT 'local',
  workspace_id TEXT NOT NULL REFERENCES workspace(id) CHECK (workspace_id <> 'wsp_unassigned'),
  name         TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  root_path    TEXT NOT NULL CHECK (substr(root_path, 1, 1) = '/' AND (root_path = '/' OR substr(root_path, -1, 1) <> '/')),
  vcs_remote   TEXT,
  active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  added_at     TEXT NOT NULL CHECK (length(added_at) = 24)
) STRICT;

CREATE UNIQUE INDEX ux_repo_path ON repo(root_path);

CREATE TABLE session (
  -- written once at registration/spawn
  id                TEXT PRIMARY KEY CHECK (id GLOB 'ses_*'),
  owner_id          TEXT NOT NULL DEFAULT 'local',
  engine_session_id TEXT,
  workspace_id      TEXT NOT NULL REFERENCES workspace(id),
  repo_id           TEXT REFERENCES repo(id),
  work_item_id      TEXT,                                   -- FK deferred to M5 (DV-11)
  work_item_ref     TEXT,
  parent_session_id TEXT REFERENCES session(id),
  origin            TEXT NOT NULL CHECK (origin IN ('orchestrator', 'queue_worker', 'user_ui', 'external', 'ask_fork')),
  ownership         TEXT NOT NULL CHECK (ownership IN ('owned', 'attached')),
  ephemeral         INTEGER NOT NULL DEFAULT 0 CHECK (ephemeral IN (0, 1)),
  depth             INTEGER NOT NULL DEFAULT 0 CHECK (depth >= 0),
  retry_of          TEXT REFERENCES session(id),
  attempt           INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  brief             TEXT,
  cwd               TEXT NOT NULL,
  worktree_path     TEXT,
  runner_handle     TEXT,
  engine            TEXT,
  provider          TEXT,
  model             TEXT,
  effort            TEXT,
  credential_ref    TEXT,
  runner            TEXT,
  started_at        TEXT NOT NULL CHECK (length(started_at) = 24),
  -- title (§7.1, D29)
  title             TEXT,
  title_source      TEXT NOT NULL DEFAULT 'brief' CHECK (title_source IN ('user', 'engine', 'brief')),
  title_synced_at   TEXT,
  -- overwritten continuously while alive (D24)
  state             TEXT NOT NULL CHECK (state IN ('starting', 'running', 'needs_you', 'stopped')),
  last_event_at     TEXT CHECK (last_event_at IS NULL OR length(last_event_at) = 24),
  needs_you_reason  TEXT,
  tasks_done        INTEGER NOT NULL DEFAULT 0 CHECK (tasks_done >= 0),
  tasks_total       INTEGER NOT NULL DEFAULT 0 CHECK (tasks_total >= 0),
  active_subagents  INTEGER NOT NULL DEFAULT 0 CHECK (active_subagents >= 0),
  repos_touched     TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(repos_touched) AND json_type(repos_touched) = 'array'),
  pr_url            TEXT,
  -- stop group, M1 subset (rest via M2 ADD COLUMN, DV-10)
  ended_at          TEXT CHECK (ended_at IS NULL OR length(ended_at) = 24),
  exit_code         INTEGER,
  -- cross-column invariants
  CHECK ((state = 'needs_you') = (needs_you_reason IS NOT NULL)),
  CHECK (tasks_done <= tasks_total),
  CHECK (title_source <> 'user' OR title IS NOT NULL),
  CHECK (ephemeral = 0 OR origin = 'ask_fork'),
  CHECK (ownership = 'owned' OR (exit_code IS NULL AND runner_handle IS NULL AND worktree_path IS NULL))
) STRICT;

CREATE INDEX ix_session_fleet ON session(workspace_id, state);
CREATE INDEX ix_session_item  ON session(work_item_id);
CREATE UNIQUE INDEX ux_session_engine_sid ON session(engine_session_id) WHERE engine_session_id IS NOT NULL;

CREATE TABLE app_state (
  key        TEXT PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 100),
  value      TEXT NOT NULL CHECK (json_valid(value)),
  updated_at TEXT NOT NULL CHECK (length(updated_at) = 24)
) STRICT;
```

**Connection pragmas** (`_conn.py`, set on every connection outside any transaction): `journal_mode=WAL` (once, at open), `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. Connections open with `isolation_level=None`; transactions are explicit `BEGIN IMMEDIATE` (writes) or `BEGIN` (multi-statement reads).

**Migration runner algorithm (`apply_migrations`):**
1. List `migrations/*.sql` matching `^(\d{4})_([a-z0-9_]+)\.sql$`. Versions must be exactly `1..N`, contiguous; otherwise raise `MigrationSetInvalid`. Checksum is `sha256(file bytes)` hex.
2. Open a connection, set pragmas, `BEGIN IMMEDIATE`, create `schema_migration` if missing.
3. For each applied row: if `version > N` → `DatabaseNewerThanBinary`. If the checksum differs from the file → `MigrationChecksumMismatch`. On either, `ROLLBACK` before raising, and **write nothing** (creating `schema_migration` on an empty DB is rolled back too).
4. For each pending file in order: split the text into statements with `sqlite3.complete_statement` while accumulating lines, `execute` each, then insert a `schema_migration` row. **Never use `executescript`** (ground truth 9).
5. `PRAGMA foreign_key_check` must return no rows, else `MigrationFailed`. Then `COMMIT`.
6. Any exception → `ROLLBACK` → re-raise as `MigrationFailed(version, cause_text)`, unless it is already a `StoreRefusal`.

`SCHEMA_VERSION` in `store/schema.py` is a literal `1`. A test asserts it equals the highest bundled file number.

## Spec S2 — sessiond UDS frame protocol (`shepherd.ipc.frames`, `shepherd.ipc.messages`, hookd)

**Transport:**
- Directory: `PlatformPaths.runtime_dir`, mode `0700`, owned by `os.getuid()`. sessiond verifies both before binding and refuses otherwise (E32).
- Sockets: `sessiond-hook.sock` and `sessiond-control.sock`. Each is bound under `os.umask(0o177)`, then `os.chmod(path, 0o600)`, then verified with `os.stat`.
- Token file: `token`, mode 0600. It holds 64 lowercase hex chars (32 random bytes from `secrets.token_bytes(32)`) plus `\n`. sessiond creates it at startup when absent, and regenerates it whenever the file mtime is older than system boot time (`/proc/stat` `btime`; macOS: always regenerate at sessiond start). This keeps it per-boot even though `<data_dir>/run` is not tmpfs. Readers load it on every connect.

**Header**, 44 bytes, big-endian, `struct` format `">4sBBH32sI"`:

| offset | size | field | value |
|---|---|---|---|
| 0 | 4 | magic | `b"SHP1"` |
| 4 | 1 | version | `1` |
| 5 | 1 | kind | `FrameKind` |
| 6 | 2 | reserved | `0` |
| 8 | 32 | token | raw 32 bytes |
| 40 | 4 | body_len | `0 ≤ n ≤ 1_048_576` |

**Body:** UTF-8 JSON object.

**Validation order:**
1. Short read → reject `short_header`.
2. magic → reject `bad_magic`.
3. version → reject `bad_version`.
4. token via `hmac.compare_digest` → reject `bad_token`.
5. kind known for this socket → reject `bad_kind`.
6. length ≤ max → reject `oversize`.

Only after all six pass is the body read. A rejection closes the connection and increments `frames_rejected`. The token is never logged.

| kind | name | socket | direction | body |
|---|---|---|---|---|
| 1 | `HOOK_EVENT` | hook | hookd → sessiond | envelope `{"v":1,"observed_at":float,"ancestry":[[pid:int,comm:str,starttime:int],…],"payload":object}` or `{"v":1,"observed_at":…,"ancestry":…,"unparsed_len":int}` or `{"v":1,…,"oversize":true,"hook_event_name":str\|null,"session_id":str\|null,"cwd":str\|null}` |
| 16 | `HELLO` | control | controld → sessiond | `{"role":"controld","protocol":1,"boot_id":str}` |
| 17 | `SCHEMA_READY` | control | controld → sessiond | `{"version":int}` |
| 18 | `SESSION_CHANGED` | control | sessiond → controld | `{"session_id":str,"workspace_id":str,"kinds":[ChangeKind…],"state_from":str\|null,"state_to":str\|null,"at":iso}` |
| 19 | `STATUS_REQUEST` | control | controld → sessiond | `{}` |
| 20 | `STATUS` | control | sessiond → controld | `{"gated":bool,"schema_version_expected":int,"counters":{…IngestCounters fields…}}` |
| 21 | `ERROR` | control | sessiond → controld | `{"code":"schema_mismatch"\|"bad_sequence"\|"unsupported_kind","expected":int\|null}` |

**Hook socket semantics:**
- Exactly one frame per connection, 1 s read deadline, no reply. hookd never waits for a response.
- The socket handler thread only validates the frame and calls `WriterLoop.submit`. It does no parsing and no DB access.

**Control socket semantics:**
- At most one controld connection. A new `HELLO` supersedes and closes the previous one.
- Required order: `HELLO`, then `SCHEMA_READY`. sessiond replies `STATUS` if `version == SCHEMA_VERSION` (gate opens), otherwise `ERROR{schema_mismatch, expected}` and stays or becomes gated.
- After that, sessiond pushes `SESSION_CHANGED` asynchronously through a bounded outbound queue (1024) and sender thread with a 2 s send timeout (a stalled controld is disconnected, never waited on). controld sends `STATUS_REQUEST` every 10 s. Either side treats 30 s without a frame as dead and closes. controld reconnects with exponential backoff from 0.2 s up to 5 s.
- When no controld is connected, notifications are dropped and `notifications_dropped` is counted. Clients recover via `resync` because controld's boot changes.

**hookd algorithm** (`src/shepherd/hookd.py`, stdlib only, entire `main` body in `try/except BaseException: pass`, then `os._exit(0)`):
1. `t = time.time()`, `deadline = time.monotonic() + 0.25`.
2. Parse `--runtime-dir` from argv by hand, without argparse (import cost and `SystemExit` output).
3. `raw = sys.stdin.buffer.read(16 MiB cap)`.
4. Try `json.loads`. On success, if it is a dict: drop `tool_response`, truncate strings > 8192 chars (depth ≤ 6). If it is not a dict or fails to parse: `unparsed_len`.
5. Ancestry: start at `os.getppid()`. Up to 6 levels, read `/proc/<pid>/stat`: comm is the text between the first `(` and the last `)`; after `)`, field 2 is ppid and field 20 is starttime. Stop at pid ≤ 1. Any error → stop.
6. `body = json.dumps(envelope, separators=(",", ":")).encode()`. If > 1 MiB → oversize envelope.
7. `token = bytes.fromhex(open(runtime_dir/"token").read().strip())`, which must be 32 bytes.
8. `socket.AF_UNIX` connect with `settimeout(max(0.001, deadline - monotonic()))`, then `sendall(header + body)` with the timeout reset to the remaining time, then `close`.
9. Write nothing to stdout or stderr. Exit 0.

The constants `MAGIC`, `PROTOCOL_VERSION`, `HEADER_FORMAT`, `HOOK_SOCKET_NAME`, `TOKEN_NAME`, `MAX_BODY` are duplicated in hookd. `tests/unit/test_hookd.py::test_constants_match_ipc` asserts they are equal to `shepherd.ipc.frames` / `shepherd.platform.base`. `test_hookd_frame_matches_ipc` asserts byte-identical frames.

## Spec S3 — controld HTTP API (M1)

**Server:**
- Binds `127.0.0.1:<config.http_port>` only. There is no host knob (§13).
- Every request: `check_host(Host)` must accept `127.0.0.1:<port>` or `localhost:<port>`, else 403 `{"error":"forbidden"}`.
- Every POST: Origin absent or ∈ {`http://127.0.0.1:<port>`, `http://localhost:<port>`}, else 403. `Content-Type` must start with `application/json`, else 415. `Content-Length` is required (else 411) and must be ≤ 64 KiB (else 413, body not read). The body must be a JSON object with correctly typed fields, else 400 `{"error":"bad request"}`.
- `SECURITY_HEADERS` on every response:
  - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`
  - `Cache-Control: no-store` (API)
- Errors: `{"error": "<generic literal>", "correlation_id": "corr_<ulid>"}`. Detail goes to the log only. Never a stack trace or a path.

| Method | Path | Response (projection) | Notes |
|---|---|---|---|
| GET | `/` | `index.html` | static |
| GET | `/static/css/app.css`, `/static/js/{app,api,sse,fleet,dom}.js` | file | fixed allowlist dict; `text/javascript; charset=utf-8` for `.js`; everything else 404 |
| GET | `/api/fleet` | `fleet_view` | `{seq, generated_at, liveness_window_s, workspaces:[WorkspaceView], hidden_idle:int, unknown:{unassigned_sessions:int, counters: IngestCounters\|null}}` |
| GET | `/api/sessions/{id}` | `{"session": session_card, "brief": str\|null, "cwd": str}` | 404 if missing |
| GET | `/api/sessions/{id}/subagents` | `{"session_id": str, "subagents": [subagent_view]}` | on-demand transcript read (PD-09) |
| GET | `/api/workspaces` | `{"workspaces":[{id,name,root_path,repos:[RepoView]}]}` | used by the CLI |
| GET | `/api/health` | `health_view` | `{controld:{schema_version, boot_id, runtime_dir}, sessiond:{connected, gated\|null, counters\|null}}` |
| GET | `/api/events` | SSE (S2 contract 2) | `Last-Event-ID` header or `?last_event_id=` |
| POST | `/api/workspaces` | `{"workspace": WorkspaceView, "rebound_session_ids":[…]}` | body `{name, root_path?}`; 400 on validation |
| POST | `/api/workspaces/{id}/discover` | `{"candidates":[{root_path,name,vcs_remote,registered:bool}]}` | body `{root_path, max_depth?}`; read-only; 400 if root is relative, missing, not a directory, or unreadable; `max_depth` 1–6 |
| POST | `/api/repos` | `{"repo": RepoView, "reactivated": bool, "rebound_session_ids":[…]}` | body `{workspace_id, path, name?}`; 409 on conflict |
| POST | `/api/repos/{id}/deactivate` | `{"repo": RepoView}` | 404 if missing |

**Projection whitelists (exact key sets; tests assert equality):**
- `SESSION_CARD_FIELDS = ("id", "workspace_id", "repo_id", "repo_name", "ownership", "origin", "state", "state_label", "needs_you_reason", "title", "title_source", "brief_excerpt", "model", "effort", "tasks_done", "tasks_total", "active_subagents", "repos_touched", "pr_url", "started_at", "last_event_at", "ended_at", "order_key")`
  - `brief_excerpt` = the first 200 chars of `brief`.
  - `state_label` ∈ {`needs you`, `running`, `starting`, `at prompt`, `exited`}.
- `WORKSPACE_VIEW_FIELDS = ("id", "name", "root_path", "last_activity_at", "counts", "order_key", "repos", "sessions")`. `counts` keys are `needs_you`, `running`, `stopped`, `exited`.
- `REPO_VIEW_FIELDS = ("id", "workspace_id", "name", "root_path", "vcs_remote", "active")`
- `SUBAGENT_VIEW_FIELDS = ("agent_id", "agent_type", "description", "state", "started_at", "last_activity_at")`

**SSE envelope:** `{"seq": int, "at": iso, "type": str, "session_id": str|null, "workspace_id": str|null, "data": object}`. For every `session.*` or `needs_you.*` event, `data = {"card": session_card, "from": str|null, "to": str|null}`. For `workspace.changed` and `repo.changed`, `data = {"workspace": WorkspaceView-without-sessions}`. For `resync`, `data = {"reason": "out_of_window"|"slow_consumer"}`.

## Spec S4 — Interface Registry (verbatim; each task's Consumes/Produces cite these names exactly)

**Notation.** Names, parameter names, parameter types and return types are binding. For brevity some dataclasses are written with `;`-separated fields on one line (`@dataclass(frozen=True) class X: a: int; b: str`), and bodies are elided with `...`. That is registry shorthand, not valid Python: builders write one field per line. `type X = …` is the PEP 695 alias statement (Python 3.12, mypy ≥ 1.13).

```python
# ---- T00 ----------------------------------------------------------------------------------------
# shepherd/jsontypes.py
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
# shepherd/timeutil.py
def utc_now_iso() -> str                                  # "YYYY-MM-DDTHH:MM:SS.mmmZ", 24 chars
def to_iso(epoch_s: float) -> str
def parse_iso(value: str) -> datetime                     # raises ValueError
def iso_age_s(then_iso: str | None, now_iso: str) -> float | None
# shepherd/ids.py
def new_id(prefix: str) -> str                            # prefix ∈ [a-z]{2,5}; returns f"{prefix}_{ulid26}"
# shepherd/exitcodes.py
EXIT_OK: Final = 0; EXIT_CONFIG: Final = 64; EXIT_UNAVAILABLE: Final = 69; EXIT_LOCKED: Final = 75; EXIT_SCHEMA_REFUSED: Final = 78

# ---- T01 ----------------------------------------------------------------------------------------
# shepherd/platform/credentials.py   (Protocol verbatim from spec §6)
@dataclass(frozen=True)
class AuthMaterial:
    kind: Literal["api_key", "oauth_token", "bearer_token"]; secret: str; meta: tuple[tuple[str, str], ...]
    # __repr__ / __str__ redact secret
class CredentialNotFound(Exception): ...
class Credentials(Protocol):
    def resolve(self, owner_id: str, provider: str) -> AuthMaterial: ...
    def resolve_ref(self, credential_ref: str) -> AuthMaterial: ...
    def store(self, owner_id: str, provider: str, material: AuthMaterial) -> str: ...
    def forget(self, credential_ref: str) -> None: ...
    def available(self, provider: str) -> bool: ...
class FileCredentials:                                                    # Linux live driver
    def __init__(self, path: Path) -> None: ...
class KeychainCredentials:                                                # macOS, UNVERIFIED
    def __init__(self, service: str = "ai.shepherd") -> None: ...
# shepherd/testkit/scripted_credentials.py
class ScriptedCredentials:
    def __init__(self, initial: Mapping[tuple[str, str], AuthMaterial] | None = None) -> None: ...

# ---- T02 ----------------------------------------------------------------------------------------
# shepherd/platform/base.py
HOOK_SOCKET_NAME: Final = "sessiond-hook.sock"
CONTROL_SOCKET_NAME: Final = "sessiond-control.sock"
TOKEN_NAME: Final = "token"
@dataclass(frozen=True)
class PlatformPaths:
    data_dir: Path; runtime_dir: Path; db_path: Path; log_dir: Path; bin_dir: Path
    backup_dir: Path; config_path: Path; credentials_path: Path
    hook_socket: Path; control_socket: Path; token_path: Path
    controld_lock: Path; sessiond_lock: Path
def ensure_private_dirs(paths: PlatformPaths) -> None      # 0700 dirs; verifies owner uid; raises ConfigError
class ProcessProbe(Protocol):
    def is_alive(self, pid: int, starttime: int) -> bool: ...
@dataclass(frozen=True)
class ServiceSpec:
    name: Literal["controld", "sessiond"]; profile: str; argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...]; kill_mode_process: bool
@dataclass(frozen=True)
class ServiceStatus:
    name: str; installed: bool; active: bool | None; detail: str
class ServiceSupervisor(Protocol):
    def render(self, spec: ServiceSpec) -> tuple[Path, str]: ...        # (unit/plist path, file text)
    def install(self, specs: Sequence[ServiceSpec]) -> list[Path]: ...  # writes files only; never enables
    def uninstall(self, specs: Sequence[ServiceSpec]) -> list[Path]: ...
    def status(self, spec: ServiceSpec) -> ServiceStatus: ...
# shepherd/config.py
TMUX_SESSION_PREFIX: Final = "shepherd_"
class ConfigError(Exception): ...
@dataclass(frozen=True)
class ShepherdConfig:
    profile: str; http_port: int; tmux_socket: str
    liveness_window_s: int; attached_abandon_s: int; fleet_idle_horizon_s: int
    claude_projects_dir: Path; discovery_max_depth: int
def resolve_profile(env: Mapping[str, str]) -> str                       # SHEPHERD_PROFILE or "default"; [a-z0-9-]{1,32}
def load_config(profile: str, paths: PlatformPaths, env: Mapping[str, str]) -> ShepherdConfig
# shepherd/platform/linux.py
def linux_paths(profile: str, env: Mapping[str, str]) -> PlatformPaths
class LinuxProcessProbe: ...                                              # satisfies ProcessProbe
# shepherd/platform/macos.py   (UNVERIFIED)
def macos_paths(profile: str, env: Mapping[str, str]) -> PlatformPaths
class DarwinProcessProbe: ...
# shepherd/testkit/env.py
def make_short_base_dir() -> Path                                         # tempfile.mkdtemp(prefix="shp-", dir="/tmp"), 0700; used as SHEPHERD_HOME so <data_dir>/run socket paths stay < 108 bytes
def isolated_env(base: Path, profile: str = "test", *, keep_real_home: bool = False) -> dict[str, str]
    # keep_real_home=True only from tests/live/conftest.py: HOME untouched; SHEPHERD_HOME, XDG_RUNTIME_DIR, XDG_CONFIG_HOME still under base
def real_state_fingerprint() -> tuple[str, str]   # (sha256 of ~/.claude/settings.json or "absent", repr of `tmux -L shepherd ls` (stdout, stderr, rc)); tmux argv always carries -L
# shepherd/testkit/scripted_platform.py
class ScriptedProcessProbe:                                               # satisfies ProcessProbe
    def __init__(self, alive: set[tuple[int, int]]) -> None: ...

# ---- T03 ----------------------------------------------------------------------------------------
# shepherd/platform/linux.py (added)
class SystemdUserSupervisor:        # satisfies ServiceSupervisor; unit_dir = $XDG_CONFIG_HOME/systemd/user
    def __init__(self, unit_dir: Path) -> None: ...
# shepherd/platform/macos.py (added, UNVERIFIED)
class LaunchdSupervisor:            # agents_dir = ~/Library/LaunchAgents
    def __init__(self, agents_dir: Path) -> None: ...
# shepherd/testkit/scripted_platform.py (added)
class ScriptedSupervisor:           # writes rendered text under root; status() answers from files present
    def __init__(self, root: Path) -> None: ...
# shepherd/platform/__init__.py
@dataclass(frozen=True)
class Platform:
    name: Literal["linux", "darwin"]; paths: PlatformPaths; probe: ProcessProbe
    supervisor: ServiceSupervisor; credentials: Credentials
def current_platform(profile: str, env: Mapping[str, str], sys_platform: str) -> Platform   # raises ConfigError on other OS

# ---- T04 ----------------------------------------------------------------------------------------
# shepherd/domain/models.py
type SessionState = Literal["starting", "running", "needs_you", "stopped"]
type TitleSource = Literal["user", "engine", "brief"]
type Origin = Literal["orchestrator", "queue_worker", "user_ui", "external", "ask_fork"]
type Ownership = Literal["owned", "attached"]
type ChangeKind = Literal["session.registered", "session.state_changed", "session.updated",
                          "needs_you.raised", "needs_you.cleared", "task.progress", "subagent.count_changed"]
type SubagentState = Literal["running", "finished", "unknown"]
class Unset(Enum): UNSET = "UNSET"
UNSET: Final = Unset.UNSET
@dataclass(frozen=True)
class Workspace: id: str; owner_id: str; name: str; root_path: str | None; created_at: str; last_activity_at: str | None
@dataclass(frozen=True)
class Repo: id: str; owner_id: str; workspace_id: str; name: str; root_path: str; vcs_remote: str | None; active: bool; added_at: str
@dataclass(frozen=True)
class Session:                      # every 0001 column, same names; ephemeral: bool; repos_touched: tuple[str, ...]
    id: str; owner_id: str; engine_session_id: str | None; workspace_id: str; repo_id: str | None
    work_item_id: str | None; work_item_ref: str | None; parent_session_id: str | None
    origin: Origin; ownership: Ownership; ephemeral: bool; depth: int; retry_of: str | None; attempt: int
    brief: str | None; cwd: str; worktree_path: str | None; runner_handle: str | None
    engine: str | None; provider: str | None; model: str | None; effort: str | None
    credential_ref: str | None; runner: str | None; started_at: str
    title: str | None; title_source: TitleSource; title_synced_at: str | None
    state: SessionState; last_event_at: str | None; needs_you_reason: str | None
    tasks_done: int; tasks_total: int; active_subagents: int; repos_touched: tuple[str, ...]
    pr_url: str | None; ended_at: str | None; exit_code: int | None
@dataclass(frozen=True)
class SessionLivePatch:             # every field defaults to UNSET
    state: SessionState | Unset = UNSET
    last_event_at: str | Unset = UNSET
    needs_you_reason: str | None | Unset = UNSET
    tasks_done: int | Unset = UNSET
    tasks_total: int | Unset = UNSET
    active_subagents: int | Unset = UNSET
    repos_touched: tuple[str, ...] | Unset = UNSET
    brief: str | Unset = UNSET
    title: str | Unset = UNSET
    title_source: Literal["engine", "brief"] | Unset = UNSET
    model: str | Unset = UNSET
    effort: str | Unset = UNSET
    ended_at: str | None | Unset = UNSET
    def is_empty(self) -> bool: ...
@dataclass(frozen=True)
class SubagentInfo: agent_id: str; agent_type: str | None; description: str | None; state: SubagentState; started_at: str | None; last_activity_at: str | None
@dataclass(frozen=True)
class ProcAncestor: pid: int; comm: str; starttime: int
@dataclass(frozen=True)
class AttachedSessionRegistration: engine_session_id: str; engine: str; cwd: str; observed_at: str
@dataclass(frozen=True)
class SessionRegistration: session: Session; created: bool
@dataclass(frozen=True)
class RepoRegistration: repo: Repo; reactivated: bool; rebound_session_ids: tuple[str, ...]
@dataclass(frozen=True)
class WorkspaceCreation: workspace: Workspace; rebound_session_ids: tuple[str, ...]
@dataclass(frozen=True)
class FleetSnapshot: workspaces: tuple[Workspace, ...]; repos: tuple[Repo, ...]; sessions: tuple[Session, ...]; hidden_idle: int
# shepherd/domain/signals.py
@dataclass(frozen=True) class TitleSignal: kind: Literal["ai", "custom"]; text: str
@dataclass(frozen=True) class PromptSignal: text: str
@dataclass(frozen=True) class ModelSignal: model: str
@dataclass(frozen=True) class EffortSignal: level: str
type Signal = TitleSignal | PromptSignal | ModelSignal | EffortSignal
# shepherd/domain/binding.py
UNASSIGNED_WORKSPACE_ID: Final = "wsp_unassigned"
@dataclass(frozen=True) class Binding: workspace_id: str; repo_id: str | None
def canonical_path(path: str, base: str | None = None) -> str            # realpath(strict=False), join with base if relative
def is_path_prefix(root: str, path: str) -> bool                          # component-wise
def repo_for_path(path: str, repos: Sequence[Repo]) -> Repo | None        # active repos only; longest prefix
def bind_cwd(cwd: str, repos: Sequence[Repo], workspaces: Sequence[Workspace]) -> Binding
# shepherd/domain/ordering.py
def state_label(session: Session) -> str                                  # "needs you"|"running"|"starting"|"at prompt"|"exited"
def session_order_key(session: Session) -> str                            # f"{rank}|{tie:010d}|{id}"
def workspace_order_key(sessions: Sequence[Session], workspace: Workspace) -> str
def brief_title(prompt: str) -> str                                       # first 60 chars, whitespace collapsed

# ---- T05 ----------------------------------------------------------------------------------------
# shepherd/store/errors.py
class StoreError(Exception): ...
class StoreRefusal(StoreError): ...
class MigrationSetInvalid(StoreRefusal): ...
class MigrationChecksumMismatch(StoreRefusal): ...
class DatabaseNewerThanBinary(StoreRefusal): ...
class MigrationFailed(StoreError): ...
class SchemaVersionMismatch(StoreRefusal): ...
# shepherd/store/migrate.py
@dataclass(frozen=True) class MigrationReport: from_version: int; to_version: int; applied: tuple[str, ...]
def apply_migrations(db_path: Path, migrations_dir: Path | None = None) -> MigrationReport
# shepherd/store/schema.py
SCHEMA_VERSION: Final = 1
def read_schema_version(db_path: Path) -> int | None                     # read-only; None if no schema_migration table

# ---- T06 ----------------------------------------------------------------------------------------
# shepherd/store/errors.py (added)
class WorkspaceNotFound(StoreError): ...
class RepoNotFound(StoreError): ...
class RepoPathConflict(StoreError): ...
class SessionNotFound(StoreError): ...
# shepherd/store/store.py  (exported as shepherd.store.Store)
class Store:
    @classmethod
    def open(cls, db_path: Path, *, expected_schema_version: int) -> "Store": ...   # never migrates
    def create_workspace(self, name: str, root_path: str | None, now_iso: str) -> WorkspaceCreation: ...
    def list_workspaces(self) -> list[Workspace]: ...
    def get_workspace(self, workspace_id: str) -> Workspace | None: ...
    def register_repo(self, workspace_id: str, root_path: str, name: str | None, vcs_remote: str | None, now_iso: str) -> RepoRegistration: ...
    def deactivate_repo(self, repo_id: str) -> Repo: ...
    def list_repos(self, *, active_only: bool) -> list[Repo]: ...
    def get_session(self, session_id: str) -> Session | None: ...
    def get_session_by_engine_id(self, engine_session_id: str) -> Session | None: ...
    def register_attached_session(self, reg: AttachedSessionRegistration) -> SessionRegistration: ...
    def apply_live_patch(self, session_id: str, patch: SessionLivePatch) -> Session: ...
    def list_live_sessions(self) -> list[Session]: ...                    # state ∈ starting|running|needs_you
    def fleet_snapshot(self, idle_horizon_start_iso: str) -> FleetSnapshot: ...
    def count_unassigned_sessions(self) -> int: ...
    def get_app_state(self, key: str) -> JsonValue | None: ...
    def put_app_state(self, key: str, value: JsonValue, now_iso: str) -> None: ...
    def reserve_event_seq(self, block: int, now_iso: str) -> int: ...     # returns first usable seq; persists start+block
    def close(self) -> None: ...

# ---- T07 ----------------------------------------------------------------------------------------
# shepherd/discovery.py
@dataclass(frozen=True) class DiscoveredRepo: root_path: str; name: str; vcs_remote: str | None
def discover_repos(root: Path, max_depth: int) -> list[DiscoveredRepo]
def read_origin_remote(repo_root: Path) -> str | None

# ---- T08 ----------------------------------------------------------------------------------------
# shepherd/ipc/frames.py
MAGIC: Final = b"SHP1"; PROTOCOL_VERSION: Final = 1; HEADER_FORMAT: Final = ">4sBBH32sI"
HEADER_LEN: Final = 44; MAX_BODY: Final = 1_048_576
class FrameKind(IntEnum):
    HOOK_EVENT = 1; HELLO = 16; SCHEMA_READY = 17; SESSION_CHANGED = 18; STATUS_REQUEST = 19; STATUS = 20; ERROR = 21
class FrameRejected(Exception):
    reason: str        # short_header|bad_magic|bad_version|bad_token|bad_kind|oversize|bad_body|timeout
@dataclass(frozen=True) class Frame: kind: FrameKind; body: bytes
class ByteReader(Protocol):
    def recv(self, bufsize: int) -> bytes: ...
def encode_frame(kind: FrameKind, token: bytes, body: bytes) -> bytes
def decode_header(header: bytes, token: bytes, allowed: frozenset[FrameKind]) -> tuple[FrameKind, int]
def read_frame(reader: ByteReader, token: bytes, allowed: frozenset[FrameKind]) -> Frame   # caller sets socket timeout
def create_token(path: Path) -> bytes
def load_token(path: Path) -> bytes
# shepherd/ipc/messages.py
@dataclass(frozen=True) class SessionChange: session_id: str; workspace_id: str; kinds: tuple[ChangeKind, ...]; state_from: SessionState | None; state_to: SessionState | None; at: str
@dataclass(frozen=True) class IngestCounters:
    frames_rejected: int = 0; malformed: int = 0; unknown_event: int = 0; deferred_no_cwd: int = 0
    dropped_backpressure: int = 0; notifications_dropped: int = 0; transcript_malformed_lines: int = 0; transcript_path_rejected: int = 0
@dataclass(frozen=True) class SessiondStatus: gated: bool; schema_version_expected: int; counters: IngestCounters
def encode_json(obj: JsonObject) -> bytes
def decode_json_object(body: bytes) -> JsonObject                        # raises FrameRejected("bad_body")
def encode_session_change(change: SessionChange) -> bytes
def decode_session_change(body: bytes) -> SessionChange
def encode_status(status: SessiondStatus) -> bytes
def decode_status(body: bytes) -> SessiondStatus
def counters_to_json(counters: IngestCounters) -> JsonObject
# shepherd/hookd.py
HOOKD_ENVELOPE_VERSION: Final = 1
def build_envelope(raw: bytes, ancestry: list[list[int | str]], observed_at: float) -> bytes
def read_ancestry(start_pid: int, max_depth: int = 6) -> list[list[int | str]]
def main(argv: list[str]) -> None                                         # never raises; caller does os._exit(0)

# ---- T09 ----------------------------------------------------------------------------------------
# shepherd/ingest/events.py
KNOWN_EVENTS: Final[frozenset[str]]      # exactly the 24 §8 subscription names (PermissionRequest included)
PATH_TOOLS: Final = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
@dataclass(frozen=True)
class HookEvent:
    name: str; session_id: str | None; cwd: str | None; transcript_path: str | None; prompt_id: str | None
    agent_id: str | None; agent_type: str | None; tool_name: str | None; tool_input: JsonObject | None
    effort_level: str | None; source: str | None; reason: str | None; prompt: str | None
    background_tasks: tuple[JsonValue, ...] | None; task_id: str | None
@dataclass(frozen=True)
class HookEnvelope: observed_at: float; ancestry: tuple[ProcAncestor, ...]; event: HookEvent | None; malformed_reason: str | None
def parse_envelope(body: bytes) -> HookEnvelope                          # total
# shepherd/ingest/fold.py
LATE_EVENT_GRACE_S: Final = 1.0
MAX_REPOS_TOUCHED: Final = 50
CONSUMED_EVENTS: Final[frozenset[str]]   # the 14 names with fold rules (DV-04); ClaudeCodeEngine.hook_events() must equal this set
@dataclass(frozen=True)
class FoldMemory:
    pending: tuple[str | None, str | None] | None = None
    last_stop_prompt_id: str | None = None
    last_stop_observed_at: float | None = None
    ended: bool = False
    engine_proc: ProcAncestor | None = None
@dataclass(frozen=True)
class FoldInput: envelope: HookEnvelope; event: HookEvent; current: Session; memory: FoldMemory; repos: Sequence[Repo]; process_names: frozenset[str]
@dataclass(frozen=True)
class FoldOutcome: patch: SessionLivePatch; memory: FoldMemory; changes: tuple[ChangeKind, ...]; refresh_transcript: bool
def fold_event(inp: FoldInput) -> FoldOutcome
def apply_signals(current: Session, signals: Sequence[Signal]) -> SessionLivePatch
def permission_reason(tool_name: str | None, tool_input: JsonObject | None, cwd: str | None) -> str
def sweep_decision(session: Session, memory: FoldMemory | None, now_iso: str, abandon_s: int,
                   proc_alive: Callable[[int, int], bool]) -> SessionLivePatch | None
def changes_between(before: Session, after: Session) -> tuple[ChangeKind, ...]
# shepherd/testkit/hook_payloads.py
def hook_payload(name: str, *, session_id: str, cwd: str, **fields: JsonValue) -> JsonObject
def envelope_bytes(payload: JsonObject | bytes, *, observed_at: float, ancestry: list[list[int | str]] | None = None) -> bytes

# ---- T10 ----------------------------------------------------------------------------------------
# shepherd/jsonl.py
@dataclass(frozen=True) class JsonlDelta: records: tuple[JsonObject, ...]; new_offset: int; malformed: int
def read_jsonl_delta(path: Path, offset: int, max_bytes: int = 8 * 1024 * 1024) -> JsonlDelta
# shepherd/engine/claude_code/transcript.py
def project_slug(cwd: str) -> str
def parse_signals(records: Sequence[JsonObject]) -> list[Signal]
def locate_transcript_in(projects_dir: Path, engine_session_id: str) -> Path | None
def is_transcript_path_allowed(projects_dir: Path, candidate: str) -> Path | None
def subagent_state(meta: JsonObject, finished_tool_use_ids: frozenset[str], parent_live: bool) -> SubagentState
def list_subagents_in(projects_dir: Path, engine_session_id: str, parent_live: bool) -> list[SubagentInfo]

# ---- T11 ----------------------------------------------------------------------------------------
# shepherd/engine/claude_code/hooks_settings.py
HOOK_MARKER_KEY: Final = "_shepherd_managed"
HOOK_MARKER_KEY_ENABLED: Final[bool] = True          # DV-20: flip only on live-probe evidence
MANAGED_ARG: Final = "--shepherd-managed"
PROBE_ACCEPTED_EVENTS: Final[frozenset[str]]   # the 24 event keys present in the probe's accepted settings file; generated keys must be a subset
class SettingsFileInvalid(Exception): ...
def hook_command(python: Path, dispatcher: Path, runtime_dir: Path) -> str
def is_shepherd_entry(entry: JsonObject) -> bool
def merge_hooks(settings: JsonObject, command: str, events: Sequence[str]) -> JsonObject
def strip_hooks(settings: JsonObject) -> tuple[JsonObject, int]
def install_into(settings_path: Path, command: str, events: Sequence[str], backup_dir: Path) -> tuple[Path | None, int, bool]
def uninstall_from(settings_path: Path, backup_dir: Path) -> tuple[Path | None, int, bool]

# ---- T12 ----------------------------------------------------------------------------------------
# shepherd/engine/base.py
@dataclass(frozen=True)
class EngineCapabilities:           # verbatim spec §6
    can_spawn: bool; can_steer: bool; can_fork: bool; can_set_title: bool; has_hooks: bool
    effort_ladder: list[str]; transcript_format: Literal["jsonl", "sqlite", "none"]
@dataclass(frozen=True) class HookTarget: settings_path: Path
@dataclass(frozen=True) class HookInstallReport: settings_path: Path; backup_path: Path | None; added: int; removed: int; changed: bool
class EngineAdapter(Protocol):
    def engine_id(self) -> str: ...
    def capabilities(self) -> EngineCapabilities: ...
    def process_names(self) -> frozenset[str]: ...
    def locate_transcript(self, engine_session_id: str) -> Path | None: ...
    def parse_transcript_delta(self, path: Path, offset: int) -> tuple[list[Signal], int]: ...
    def list_subagents(self, engine_session_id: str, parent_live: bool) -> list[SubagentInfo]: ...
    def accept_transcript_path(self, candidate: str) -> Path | None: ...   # engine-owned path validation (fresh-review A14)
    def hook_events(self) -> list[str]: ...
    def install_hooks(self, dispatcher: Path, target: HookTarget) -> HookInstallReport: ...
    def uninstall_hooks(self, target: HookTarget) -> HookInstallReport: ...
# shepherd/engine/claude_code/adapter.py
class ClaudeCodeEngine:
    def __init__(self, projects_dir: Path, runtime_dir: Path, backup_dir: Path, python: Path) -> None: ...
    last_malformed_lines: int     # updated by parse_transcript_delta
# shepherd/testkit/scripted_engine.py
class ScriptedEngine:
    def __init__(self, *, transcripts: Mapping[str, Sequence[Signal]], subagents: Mapping[str, Sequence[SubagentInfo]],
                 events: Sequence[str], settings_root: Path, transcript_root: Path) -> None: ...   # accept_transcript_path allows only paths under transcript_root

# ---- T13 ----------------------------------------------------------------------------------------
# shepherd/logs.py
def configure_daemon_logging(log_dir: Path, daemon: Literal["controld", "sessiond"], retention_days: int = 14, max_bytes: int = 50_000_000) -> logging.Logger
# shepherd/sessiond/ingest_service.py
class IngestService:
    def __init__(self, store: Store, engine: EngineAdapter, probe: ProcessProbe, config: ShepherdConfig,
                 notify: Callable[[SessionChange], None], now_iso: Callable[[], str]) -> None: ...
    def handle_envelope_body(self, body: bytes) -> None: ...
    def sweep(self) -> None: ...
    def counters(self) -> IngestCounters: ...
    def count_rejected_frame(self) -> None: ...
LIVENESS_WRITE_INTERVAL_S: Final = 5
LIVENESS_NOTIFY_INTERVAL_S: Final = 30
# shepherd/sessiond/writer.py
class WriterLoop:
    def __init__(self, service: IngestService, *, queue_max: int = 10_000, sweep_interval_s: float = 15.0) -> None: ...
    def submit(self, body: bytes) -> bool: ...
    def open_gate(self) -> None: ...
    def close_gate(self) -> None: ...
    def is_gated(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
# shepherd/sessiond/main.py
def run_sessiond(platform: Platform, config: ShepherdConfig, *, stop: threading.Event,
                 engine: EngineAdapter | None = None, ready: threading.Event | None = None) -> int

# ---- T14 ----------------------------------------------------------------------------------------
# shepherd/controld/events.py
type EventType = Literal["session.registered", "session.state_changed", "session.updated", "needs_you.raised",
                         "needs_you.cleared", "task.progress", "subagent.count_changed", "workspace.changed",
                         "repo.changed", "resync"]
@dataclass(frozen=True) class EventEnvelope: seq: int; at: str; type: EventType; session_id: str | None; workspace_id: str | None; data: JsonObject
class Subscription:
    def next(self, timeout_s: float) -> list[EventEnvelope]: ...          # [] on timeout
    def close(self) -> None: ...
class EventHub:
    def __init__(self, store: Store, *, ring_size: int = 2048, reserve_block: int = 10_000,
                 subscriber_queue_max: int = 4096, now_iso: Callable[[], str] = utc_now_iso) -> None: ...
    def publish(self, type_: EventType, session_id: str | None, workspace_id: str | None, data: JsonObject) -> int: ...
    def current_seq(self) -> int: ...
    def subscribe(self, last_event_id: int | None) -> Subscription: ...
def parse_last_event_id(header: str | None, query: str | None) -> int | None | Literal["invalid"]
def format_sse(envelope: EventEnvelope) -> bytes
# shepherd/controld/sessiond_link.py
@dataclass(frozen=True) class LinkStatus: connected: bool; sessiond: SessiondStatus | None; last_error: str | None
class SessiondLink:
    def __init__(self, paths: PlatformPaths, schema_version: int, boot_id: str, on_change: Callable[[SessionChange], None]) -> None: ...
    def start(self) -> None: ...
    def status(self) -> LinkStatus: ...
    def stop(self) -> None: ...
# shepherd/controld/main.py
def run_controld(platform: Platform, config: ShepherdConfig, *, stop: threading.Event,
                 engine: EngineAdapter | None = None, ready: threading.Event | None = None,
                 serve_http: bool = True) -> int                     # serve_http=False only in T14 tests
def publish_session_change(store: Store, hub: EventHub, change: SessionChange) -> None

# ---- T15 ----------------------------------------------------------------------------------------
# shepherd/controld/security.py
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]]
def check_host(host: str | None, port: int) -> bool
def check_origin(origin: str | None, port: int) -> bool
# shepherd/controld/projections.py
SESSION_CARD_FIELDS: Final[tuple[str, ...]]; WORKSPACE_VIEW_FIELDS: Final[tuple[str, ...]]
REPO_VIEW_FIELDS: Final[tuple[str, ...]]; SUBAGENT_VIEW_FIELDS: Final[tuple[str, ...]]
def session_card(session: Session, repo_names: Mapping[str, str]) -> JsonObject
def repo_view(repo: Repo) -> JsonObject
def workspace_view(workspace: Workspace, repos: Sequence[Repo], sessions: Sequence[Session], repo_names: Mapping[str, str]) -> JsonObject
def fleet_view(snapshot: FleetSnapshot, seq: int, generated_at: str, liveness_window_s: int, unassigned_sessions: int, counters: IngestCounters | None) -> JsonObject
def subagent_view(info: SubagentInfo) -> JsonObject
def health_view(schema_version: int, boot_id: str, runtime_dir: str, link: LinkStatus) -> JsonObject
# shepherd/controld/http.py
@dataclass(frozen=True)
class HttpDeps: store: Store; hub: EventHub; link: SessiondLink; engine: EngineAdapter; config: ShepherdConfig; boot_id: str; stop: threading.Event
def make_server(deps: HttpDeps, port: int) -> ThreadingHTTPServer

# ---- T17 ----------------------------------------------------------------------------------------
# shepherd/cli/main.py
def main(argv: Sequence[str] | None = None) -> int
# shepherd/cli/http_client.py
class ControldClient:
    def __init__(self, port: int, timeout_s: float = 5.0) -> None: ...
    def get(self, path: str) -> JsonObject: ...
    def post(self, path: str, body: JsonObject) -> JsonObject: ...        # raises ControldError(status, error, correlation_id)
class ControldError(Exception): ...
# ---- T18 ----------------------------------------------------------------------------------------
# shepherd/testkit/e2e.py
@dataclass(frozen=True)
class StackHandle: http_port: int; paths: PlatformPaths; config: ShepherdConfig; stop: threading.Event
@contextmanager
def running_stack(base: Path, *, engine: EngineAdapter | None = None) -> Iterator[StackHandle]

```

## Phase Plan (tasks in dependency order)

Execution groups. Tasks inside a group can run in parallel once their dependencies are met.
- **G1:** T00
- **G2:** T01, T02, T04
- **G3:** T03, T05, T07, T08, T10
- **G4:** T06, T09, T11
- **G5:** T12 (after T09, T10, T11)
- **G6:** T13
- **G7:** T14
- **G8:** T15
- **G9:** T16, T17
- **G10:** T18 (then T18b only if its decision rule triggers)
- **G11:** T19 (HITL)

Commands used below:
- `$PY` = `/root/Shepherd/.venv/bin/python`
- `MYPY` = `$PY -m mypy`, configured in `pyproject.toml`
- `PYTEST` = `$PY -m pytest -q`

Every task's exit criteria **implicitly include**: `MYPY` clean on `src tests`; `PYTEST tests/test_repo_rules.py` green; no file over 600 lines.

---

### Task T00: Bootstrap, toolchain, repo rules
- **Objective:** A typed, testable, empty package skeleton, with the repo-wide rules R1–R14 enforced from the first commit.
- **Files/Surfaces:**
  - `pyproject.toml`, `scripts/bootstrap_venv.sh`, `.gitignore` (add `build/`), `tests/test_toolchain.py`
  - `src/shepherd/{__init__,jsontypes,timeutil,ids,exitcodes}.py`
  - `tests/conftest.py`, `tests/test_repo_rules.py`
  - `tests/unit/test_timeutil.py`, `tests/unit/test_ids.py`
- **Dependencies:** none
- **Allowed Scope:**
  - pyproject: `requires-python >=3.12`; no runtime deps; `[project.optional-dependencies] dev = ["pytest>=9", "mypy>=1.13"]` (full PEP 695 `type` alias support); `[project.scripts] shepherd = "shepherd.cli.main:main"`.
  - `[tool.mypy]`: `strict = true`, `disallow_any_explicit = true`, `warn_unreachable = true`, `mypy_path = "src"`, `files = ["src", "tests"]`.
  - `[tool.pytest.ini_options]`: `pythonpath = ["src"]`, `testpaths = ["tests"]`, `markers = ["slow", "live"]`, `addopts = "-m 'not slow and not live'"`.
  - Bootstrap script: `python3 -m venv --without-pip .venv`, fetch `get-pip.py` with python `urllib`, run `pip install -e '.[dev]'`. It is idempotent.
  - `ids.new_id` is a stdlib ULID: 48-bit ms time plus 80 random bits, Crockford base32.
  - `test_repo_rules.py` implements R1–R14 as AST or text scans. They pass vacuously on empty packages.
- **Out-of-Scope Drift:** any domain code; adding runtime dependencies; a lint tool beyond mypy.
- **Expected Artifacts:** a working venv; green `PYTEST`; `MYPY` clean.
- **Required Checks:**
  - `tests/test_toolchain.py::test_mypy_version_supports_pep695` (asserts ≥ 1.13)
  - `test_timeutil.py::test_iso_fixed_width`, `::test_roundtrip`, `::test_iso_age_none`
  - `test_ids.py::test_prefix_and_length`, `::test_monotonic_sort_within_ms_bound`
  - `test_repo_rules.py::test_r01_sqlite_only_in_store` … `::test_r14_tmux_requires_socket_flag`. Each rule also has a self-test: a synthetic source string that violates it must be flagged.
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `bash scripts/bootstrap_venv.sh && MYPY && PYTEST`
- **Exit Criteria:** bootstrap succeeds from a clean clone; all T00 tests green; every R-rule is proven to detect its own synthetic violation.
- **Test Seams:** unit (pure functions); source-scan seam (repo rules)
- **Durability:** stable
- **Consumes:** none
- **Produces:** `JsonValue`, `JsonObject`, `utc_now_iso`, `to_iso`, `parse_iso`, `iso_age_s`, `new_id`, `EXIT_OK`, `EXIT_CONFIG`, `EXIT_UNAVAILABLE`, `EXIT_LOCKED`, `EXIT_SCHEMA_REFUSED`, `tests/test_repo_rules.py` (R1–R14)

### Task T01: Platform seam — `Credentials` (Protocol, Linux driver, macOS driver, Scripted, contract suite)
- **Objective:** The spec §6 `Credentials` seam, with a live Linux file driver and an unverified Keychain driver. Both are proven by one contract suite. **M1 has no production caller**: the request requires the seam, and M4.5/M5 consume it.
- **Files/Surfaces:**
  - `src/shepherd/platform/__init__.py` (empty for now), `src/shepherd/platform/credentials.py`
  - `src/shepherd/testkit/__init__.py`, `src/shepherd/testkit/scripted_credentials.py`
  - `tests/contract/test_credentials_contract.py`, `tests/unit/test_file_credentials.py`
- **Dependencies:** T00
- **Allowed Scope:**
  - `FileCredentials` stores `{credential_ref: {owner_id, provider, kind, secret, meta}}` in one JSON file. It writes atomically (tmp file in the same dir, `fsync`, `os.replace`) at mode 0600, and refuses to read a file that is group- or other-readable.
  - `credential_ref = new_id("cred")`. `resolve(owner, provider)` returns the newest ref for that pair.
  - `KeychainCredentials` uses `security add-generic-password -U -s ai.shepherd -a <ref> -w <secret>` / `find-generic-password -w` / `delete-generic-password`. argv only; the secret goes via argv (a known `security` limitation, commented). Its index of refs lives in a 0600 JSON file with no secrets.
  - `AuthMaterial.__repr__` redacts the secret.
- **Out-of-Scope Drift:** OAuth flows; encrypting at rest beyond 0600 (not in spec); any CLI command.
- **Expected Artifacts:** three `Credentials` implementations; a contract suite parametrized over `FileCredentials` and `ScriptedCredentials`. `KeychainCredentials` is skipped unless `sys.platform == "darwin"`.
- **Required Checks:**
  - `test_credentials_contract.py::test_store_then_resolve_ref`, `::test_resolve_newest_for_owner_provider`, `::test_forget_then_not_found`, `::test_available_reflects_store`, `::test_repr_redacts_secret`
  - `test_file_credentials.py::test_mode_0600_after_store`, `::test_refuses_group_readable_file`, `::test_atomic_write_survives_crash_between_tmp_and_replace`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/contract/test_credentials_contract.py tests/unit/test_file_credentials.py`
- **Exit Criteria:** contract suite green for File and Scripted; macOS case skipped with reason "unverified driver (DV-02)".
- **Test Seams:** contract seam (Protocol); integration seam (filesystem modes)
- **Durability:** stable
- **Consumes:** `new_id`
- **Produces:** `Credentials`, `AuthMaterial`, `CredentialNotFound`, `FileCredentials`, `KeychainCredentials`, `ScriptedCredentials`

### Task T02: Platform seam — config, profiles, paths, process probe
- **Objective:** Resolve profile, paths and configuration for Linux (live) and macOS (unverified). This includes the **tmux socket key M3 inherits** and the process probe DV-09 needs.
- **Files/Surfaces:**
  - `src/shepherd/config.py`, `src/shepherd/platform/base.py`, `src/shepherd/platform/linux.py`, `src/shepherd/platform/macos.py`
  - `src/shepherd/testkit/env.py`, `src/shepherd/testkit/scripted_platform.py`
  - `tests/conftest.py` (autouse isolation, PD-08)
  - `tests/unit/test_config.py`, `tests/unit/test_paths.py`, `tests/integration/test_process_probe.py`
- **Dependencies:** T00
- **Allowed Scope:**
  - **Profiles:** `resolve_profile` reads `SHEPHERD_PROFILE`, default `default`.
  - **`linux_paths`:**
    - `data_dir` = `$SHEPHERD_HOME` or `~/.shepherd`, plus `/profiles/<p>` when the profile is not `default`.
    - `runtime_dir` = `<data_dir>/run`, always. `XDG_RUNTIME_DIR` is ignored (DV-03).
    - `db_path` = `data_dir/shepherd.db`, `log_dir` = `data_dir/logs`, `bin_dir` = `data_dir/bin`, `backup_dir` = `data_dir/backups`, `config_path` = `data_dir/config.json`, `credentials_path` = `data_dir/credentials.json`.
    - Sockets, token and locks live under `runtime_dir`.
  - `macos_paths`: the same layout.
  - **`load_config`** merges defaults, then `config.json`, then env overrides `SHEPHERD_HTTP_PORT` and `SHEPHERD_TMUX_SOCKET`.
    - Defaults: `http_port` = 7420 (default profile), 7421 (`qa`), 0 (`test`, meaning ephemeral). `tmux_socket` = `shepherd`, `shepherd-qa`, `shepherd-test` for those profiles, `shepherd-<p>` otherwise. `liveness_window_s` 90, `attached_abandon_s` 10800, `fleet_idle_horizon_s` 86400, `claude_projects_dir` `~/.claude/projects`, `discovery_max_depth` 3.
    - Validation raises `ConfigError`: `http_port` must be 1024–65535, or 0 only for the `test` profile; the `tmux_socket` regex; the socket is never `default`; **non-default profiles may not use `shepherd`** (DV-21); every AF_UNIX path must be ≤ 107 bytes.
    - There is no bind-host setting (§13).
  - **`LinuxProcessProbe.is_alive`** reads `/proc/<pid>/stat` and compares field 22 (starttime). `DarwinProcessProbe` uses `os.kill(pid, 0)` and ignores starttime.
  - `ensure_private_dirs` creates dirs at 0700 and raises if an existing dir is not owned by the uid or is group/other-accessible.
  - The conftest autouse fixture sets env via `isolated_env` and monkeypatches `Path.home`.
- **Out-of-Scope Drift:** any tmux invocation; supervisor drivers (T03); a config-editing CLI.
- **Expected Artifacts:** config and path resolution usable by every daemon.
- **Required Checks:**
  - `test_config.py::test_defaults_per_profile`, `::test_non_default_profile_rejects_shepherd_socket` (E34), `::test_rejects_default_socket_name`, `::test_rejects_colon_and_dot_in_socket`, `::test_env_overrides`, `::test_no_bind_host_setting_exists`, `::test_invalid_config_json_and_unknown_keys_raise` (E39)
  - `test_paths.py::test_linux_default_and_profile_paths`, `::test_runtime_dir_ignores_xdg_runtime_dir`, `::test_socket_path_length_guard` (E33), `::test_ensure_private_dirs_refuses_open_mode` (E32)
  - `test_process_probe.py::test_self_alive_with_correct_starttime`, `::test_wrong_starttime_is_dead`, `::test_nonexistent_pid_dead`
  - `tests/unit/test_isolation.py::test_home_is_temp_in_tests`, `::test_real_state_untouched_by_suite`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_config.py tests/unit/test_paths.py tests/integration/test_process_probe.py tests/unit/test_isolation.py`
- **Exit Criteria:** all listed tests green. `tests/unit/test_isolation.py::test_real_state_untouched_by_suite` asserts that the sha256 of the real `~/.claude/settings.json` is unchanged across the session (not mtimes: the builder's own `claude` writes under `~/.claude`), and that the real `~/.shepherd` was not created if it was absent before the run (fresh-review A11).
- **Test Seams:** unit (config/path resolution with injected env); integration (real `/proc`)
- **Durability:** stable
- **Consumes:** `EXIT_CONFIG`
- **Produces:** `real_state_fingerprint`, `PlatformPaths`, `ensure_private_dirs`, `ProcessProbe`, `ServiceSpec`, `ServiceStatus`, `ServiceSupervisor`, `HOOK_SOCKET_NAME`, `CONTROL_SOCKET_NAME`, `TOKEN_NAME`, `ShepherdConfig`, `ConfigError`, `TMUX_SESSION_PREFIX`, `resolve_profile`, `load_config`, `linux_paths`, `macos_paths`, `LinuxProcessProbe`, `DarwinProcessProbe`, `make_short_base_dir`, `isolated_env`, `ScriptedProcessProbe`

### Task T03: Platform seam — service supervision + `Platform` factory
- **Objective:** Supervisors that render and install unit files, without ever enabling them, plus the `current_platform` factory that wires paths, probe, supervisor and credentials.
- **Files/Surfaces:**
  - `src/shepherd/platform/linux.py` (add), `src/shepherd/platform/macos.py` (add), `src/shepherd/platform/__init__.py`
  - `src/shepherd/testkit/scripted_platform.py` (add)
  - `tests/contract/test_supervisor_contract.py`, `tests/unit/test_systemd_render.py`, `tests/unit/test_current_platform.py`
- **Dependencies:** T01, T02
- **Allowed Scope:**
  - **`SystemdUserSupervisor.render`** produces `shepherd-<profile>-<name>.service` containing:
    - `Type=simple`
    - `ExecStart=<argv joined; each element validated: no whitespace, quotes, $, % or backslash — else ConfigError>`
    - `Environment=SHEPHERD_PROFILE=<p>`
    - `Restart=always`, `RestartSec=2`, `RestartPreventExitStatus=75 78` (PD-12)
    - `KillMode=process` when `kill_mode_process` (sessiond; M3 precondition 5)
    - `[Install] WantedBy=default.target`
  - `install` writes files at 0644 and returns their paths. **It never runs `systemctl`.**
  - `status` runs `["systemctl", "--user", "show", "-p", "ActiveState", "--value", unit]` via `subprocess.run` with a timeout of 3 s. If that fails, it returns `active=None`.
  - `LaunchdSupervisor` renders a plist with `KeepAlive` and `ProgramArguments` (unverified).
  - `current_platform` selects `linux` or `darwin` and raises `ConfigError` for anything else. Credentials are `FileCredentials(paths.credentials_path)` on Linux and `KeychainCredentials()` on macOS.
- **Out-of-Scope Drift:** enabling or starting units; `loginctl enable-linger`; any installer beyond files.
- **Expected Artifacts:** golden unit text; a contract suite over `SystemdUserSupervisor` and `ScriptedSupervisor` (both write under a temp dir).
- **Required Checks:**
  - `test_systemd_render.py::test_golden_controld_unit`, `::test_sessiond_has_killmode_process`, `::test_restart_prevent_exit_status`, `::test_rejects_unsafe_argv_chars`
  - `test_supervisor_contract.py::test_install_writes_and_uninstall_removes`, `::test_install_is_idempotent`, `::test_install_never_invokes_subprocess` (monkeypatch `subprocess.run` to raise)
  - `test_current_platform.py::test_linux_wiring`, `::test_unsupported_platform_raises`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/contract/test_supervisor_contract.py tests/unit/test_systemd_render.py tests/unit/test_current_platform.py`. Optionally also `systemd-analyze --user verify <rendered file>` when available (skip otherwise).
- **Exit Criteria:** tests green; no test enables, starts or queries a real unit.
- **Test Seams:** contract seam (`ServiceSupervisor`); unit (render)
- **Durability:** stable (Linux); near-term-refactor (macOS, unverified)
- **Consumes:** `ServiceSpec`, `ServiceStatus`, `ServiceSupervisor`, `PlatformPaths`, `ProcessProbe`, `LinuxProcessProbe`, `DarwinProcessProbe`, `linux_paths`, `macos_paths`, `ConfigError`, `Credentials`, `FileCredentials`, `KeychainCredentials`
- **Produces:** `SystemdUserSupervisor`, `LaunchdSupervisor`, `ScriptedSupervisor`, `Platform`, `current_platform`

### Task T04: Domain core — models, signals, binding, ordering (pure)
- **Objective:** The vocabulary dataclasses and the two pure algorithms everything else depends on: D22 longest-prefix binding and fleet ordering.
- **Files/Surfaces:**
  - `src/shepherd/domain/__init__.py`, `src/shepherd/domain/models.py`, `src/shepherd/domain/signals.py`, `src/shepherd/domain/binding.py`, `src/shepherd/domain/ordering.py`
  - `tests/unit/test_binding.py`, `tests/unit/test_ordering.py`, `tests/unit/test_models.py`
- **Dependencies:** T00
- **Allowed Scope:**
  - **`bind_cwd`:** canonicalize `cwd`, then pick the active repo with the longest component-wise prefix. On a match, return `workspace_id = repo.workspace_id`. Otherwise use the workspace with the longest `root_path` prefix (excluding `wsp_unassigned`) and `repo_id=None`. Otherwise `UNASSIGNED_WORKSPACE_ID`.
  - Ties are impossible for repos (unique path). For workspace roots, break ties by `id`.
  - **`session_order_key`**, per DV-26:
    - rank: `needs_you` 0; `running`/`starting` 1; `stopped` with `ended_at` None 2; `stopped` with `ended_at` 3.
    - tie for rank 0: `int(epoch(last_event_at or started_at))`.
    - tie for other ranks: `9_999_999_999 - int(epoch(started_at))`.
  - **`workspace_order_key`** = `min(session keys)`, or `"4|0000000000|" + workspace.id` when there are no sessions.
  - `SessionLivePatch.is_empty` returns True when every field is `UNSET`.
- **Out-of-Scope Drift:** any IO; the 7-bucket palette; filesystem discovery.
- **Expected Artifacts:** the pure domain package.
- **Required Checks:**
  - `test_binding.py::test_innermost_repo_wins` (E13), `::test_component_boundary_no_partial_match` (E12), `::test_symlinked_cwd_binds` (E14), `::test_root_repo_lowest_priority` (E15), `::test_inactive_repo_ignored`, `::test_workspace_root_fallback_repo_none`, `::test_unassigned_fallback`, `::test_order_independent_permutations` (P05, all 720 orderings of 6 repos), `::test_relative_path_joined_with_base`
  - `test_ordering.py::test_session_order_key`, `::test_needs_you_oldest_first`, `::test_running_newest_first`, `::test_exited_after_turn_ended`, `::test_workspace_without_sessions_last`, `::test_state_labels`, `::test_brief_title_60_collapsed`
  - `test_models.py::test_patch_is_empty`, `::test_dataclasses_frozen`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_binding.py tests/unit/test_ordering.py tests/unit/test_models.py`
- **Exit Criteria:** green; R6 purity rule passes for `shepherd.domain`.
- **Test Seams:** unit
- **Durability:** stable
- **Consumes:** `JsonValue`, `JsonObject`, `parse_iso`
- **Produces:** `SessionState`, `TitleSource`, `Origin`, `Ownership`, `ChangeKind`, `SubagentState`, `Unset`, `UNSET`, `Workspace`, `Repo`, `Session`, `SessionLivePatch`, `SubagentInfo`, `ProcAncestor`, `AttachedSessionRegistration`, `SessionRegistration`, `RepoRegistration`, `WorkspaceCreation`, `FleetSnapshot`, `TitleSignal`, `PromptSignal`, `ModelSignal`, `EffortSignal`, `Signal`, `UNASSIGNED_WORKSPACE_ID`, `Binding`, `canonical_path`, `is_path_prefix`, `repo_for_path`, `bind_cwd`, `state_label`, `session_order_key`, `workspace_order_key`, `brief_title`

### Task T05: Store I — migration runner, `0001_foundation.sql`, migration-safety tests
- **Objective:** A forward-only, checksummed, single-transaction migration system that enforces the three §7 migration rules, plus the exact M1 schema (Spec S1).
- **Files/Surfaces:**
  - `src/shepherd/store/__init__.py` (placeholder export of errors), `src/shepherd/store/_conn.py`, `src/shepherd/store/errors.py`, `src/shepherd/store/migrate.py`, `src/shepherd/store/schema.py`
  - `src/shepherd/store/migrations/0001_foundation.sql`
  - `tests/integration/test_migrate.py`, `tests/integration/test_schema_constraints.py`
  - `tests/fixtures/migrations_future/0002_m2_stop_columns_probe.sql` (test-only)
- **Dependencies:** T04 (the `UNASSIGNED_WORKSPACE_ID` literal must match the seed)
- **Allowed Scope:** exactly Spec S1. The package-data config ships `*.sql`, and `importlib.resources` locates the default migrations dir.
- **Out-of-Scope Drift:** down-migrations; `work_item`/`queue`/stop-group columns; any domain verb (T06).
- **Expected Artifacts:** `apply_migrations`; `SCHEMA_VERSION = 1`.
- **Required Checks** (all in `tests/integration/`):
  - `test_migrate.py::test_fresh_apply` (tables, 4 indexes incl. `ux_session_engine_sid`, `wsp_unassigned` seed, `schema_migration` row, WAL mode)
  - `::test_second_apply_is_noop`
  - `::test_checksum_mismatch_refuses` (E18; file bytes unchanged, P03)
  - `::test_db_newer_refuses` (E19, P03)
  - `::test_failing_migration_rolls_back_everything` (E20, P02; synthetic dir with `0001` + a broken `0002`)
  - `::test_non_contiguous_set_invalid` (E21)
  - `::test_does_not_use_executescript` (source scan)
  - `::test_schema_version_equals_max_file`
  - `::test_unassigned_seed_matches_domain_constant`
  - `::test_m2_forward_add_column_with_check_applies_on_populated_db` (applies the future fixture on top of 0001 with rows present; asserts CHECK enforced)
  - `::test_sigkill_mid_migration_leaves_old_version` (`@pytest.mark.slow`; subprocess applies a synthetic slow migration, parent SIGKILLs it, then version and `sqlite_master` equal the pre-state)
  - `test_schema_constraints.py::test_enum_checks_reject_bad_values` (table-driven over `origin`, `ownership`, `state`, `title_source`)
  - `::test_needs_you_reason_biconditional` (P07), `::test_tasks_done_le_total`, `::test_repos_touched_must_be_json_array`, `::test_attached_cannot_have_exit_code`, `::test_repo_cannot_join_unassigned`, `::test_time_format_check`, `::test_work_item_id_accepts_value_without_fk` (DV-11)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/integration/test_migrate.py tests/integration/test_schema_constraints.py && PYTEST -m slow tests/integration/test_migrate.py`
- **Exit Criteria:** all green incl. the slow lane; R1 (`sqlite3` only in store) and R2 hold.
- **Test Seams:** integration (a real SQLite file in a temp dir)
- **Durability:** stable (the schema is the contract M2–M5 extend)
- **Consumes:** `utc_now_iso`, `UNASSIGNED_WORKSPACE_ID`
- **Produces:** `StoreError`, `StoreRefusal`, `MigrationSetInvalid`, `MigrationChecksumMismatch`, `DatabaseNewerThanBinary`, `MigrationFailed`, `SchemaVersionMismatch`, `MigrationReport`, `apply_migrations`, `SCHEMA_VERSION`, `read_schema_version`, `0001_foundation.sql`

### Task T06: Store II — domain verbs (D33)
- **Objective:** Every read and write M1 needs, as verbs returning dataclasses, with transactions kept inside.
- **Files/Surfaces:**
  - `src/shepherd/store/store.py`, `src/shepherd/store/_sessions.py`, `src/shepherd/store/_rows.py`, `src/shepherd/store/__init__.py`, `src/shepherd/store/errors.py` (add)
  - `tests/integration/test_store_workspaces.py`, `tests/integration/test_store_sessions.py`, `tests/integration/test_store_app_state.py`, `tests/integration/test_store_concurrency.py`
- **Dependencies:** T04, T05
- **Allowed Scope:**
  - **`Store.open`** raises `SchemaVersionMismatch` unless `read_schema_version == expected_schema_version`. It never calls `apply_migrations`. It uses thread-local connections (`_conn.py`).
  - **`create_workspace`** validates `root_path` (absolute, canonicalized) and rebinds sessions where `workspace_id = 'wsp_unassigned' AND repo_id IS NULL`, using `bind_cwd` over current repos and workspaces. Insert and rebind happen in one `BEGIN IMMEDIATE`.
  - **`register_repo`:**
    - canonicalizes the path;
    - if the path exists with the same workspace, reactivates it;
    - if it exists with a different workspace and is active, raises `RepoPathConflict`; if inactive, reassigns the workspace and reactivates;
    - `name` defaults to the basename;
    - then rebinds sessions with `repo_id IS NULL` whose cwd `repo_for_path` now resolves to this repo, setting `workspace_id` and `repo_id` in the same transaction (DV-13).
  - **`register_attached_session`** runs in a single transaction:
    - `INSERT … ON CONFLICT(engine_session_id) WHERE engine_session_id IS NOT NULL DO NOTHING`, then `SELECT`;
    - sets `origin='external'`, `ownership='attached'`, `state='stopped'` with `ended_at NULL` (DV-30: the caller folds the triggering event next), `started_at=last_event_at=observed_at`, `engine=reg.engine`;
    - binds via `bind_cwd`;
    - returns `created` from `changes()`.
  - **`apply_live_patch`:**
    - builds `UPDATE session SET <only non-UNSET columns> WHERE id=?`;
    - the title ratchet is SQL-guarded (`title` and `title_source` are written only `WHERE title_source <> 'user'`, and an `engine` value is never overwritten by `brief`), P13;
    - `repos_touched` is serialized as a JSON array;
    - also runs `UPDATE workspace SET last_activity_at=? WHERE id=? AND (last_activity_at IS NULL OR last_activity_at < ?)` with a 10 s coalescing threshold computed in Python;
    - returns the fresh `Session`; raises `SessionNotFound`.
  - **`fleet_snapshot`** returns all workspaces (including `wsp_unassigned` only if it has visible sessions) and active repos. It returns every session except `stopped` sessions whose `coalesce(ended_at, last_event_at)` is older than the horizon; that covers both exited and long-idle at-prompt sessions. Those are counted in `hidden_idle`. There is **no `ephemeral` filter** in M1: attached sessions are never ephemeral.
  - **`reserve_event_seq(block)`** reads `app_state['sse.seq_reserved']` (default 1), writes `start+block`, returns `start`, all in one transaction.
- **Out-of-Scope Drift:** a public `query()` or `transaction()`; returning `sqlite3.Row`; claim verbs (M5); stop-column verbs (M2).
- **Expected Artifacts:** the `Store` class.
- **Required Checks** (all in `tests/integration/`):
  - `test_store_workspaces.py::test_create_workspace_rebinds_unassigned`, `::test_register_repo_rebinds_null_repo_sessions_only`, `::test_bound_session_never_moves`, `::test_reactivate_inactive_repo` (E16), `::test_conflict_active_other_workspace` (E17), `::test_deactivate_repo`, `::test_list_repos_active_only`
  - `test_store_sessions.py::test_register_idempotent`, `::test_register_binds_innermost`, `::test_apply_patch_only_set_columns`, `::test_title_ratchet_sql_guard` (P13), `::test_patch_violating_check_raises_store_error`, `::test_workspace_activity_coalesced`, `::test_fleet_snapshot_hides_old_exited_and_counts`, `::test_list_live_sessions`, `::test_open_refuses_version_mismatch_without_writing`
  - `test_store_app_state.py::test_put_get_json_roundtrip`, `::test_reserve_event_seq_monotonic_blocks`
  - `test_store_concurrency.py::test_two_processes_register_same_engine_id_one_row` (multiprocessing, 8 procs), `::test_patch_and_rebind_from_two_connections_no_lost_columns`
  - `tests/test_repo_rules.py` R3 green (`_rows`/`_sessions`/`_conn` private)
  - `tests/integration/test_store_api_surface.py::test_no_public_method_returns_row_or_accepts_sql` (introspects `Store` annotations: return types are dataclasses, lists/tuples of them, primitives, or `JsonValue`)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/integration/test_store_*.py`
- **Exit Criteria:** green; `store/store.py` and `store/_sessions.py` each < 600 lines.
- **Test Seams:** integration (real SQLite; multiprocess for races)
- **Durability:** stable (verbs); near-term-refactor (M2 adds stop verbs)
- **Consumes:** `apply_migrations`, `read_schema_version`, `SCHEMA_VERSION`, `SchemaVersionMismatch`, `StoreError`, `Workspace`, `Repo`, `Session`, `SessionLivePatch`, `UNSET`, `AttachedSessionRegistration`, `SessionRegistration`, `RepoRegistration`, `WorkspaceCreation`, `FleetSnapshot`, `bind_cwd`, `repo_for_path`, `canonical_path`, `UNASSIGNED_WORKSPACE_ID`, `new_id`, `JsonValue`, `iso_age_s`
- **Produces:** `Store` (with every method listed in Spec S4 T06), `WorkspaceNotFound`, `RepoNotFound`, `RepoPathConflict`, `SessionNotFound`

### Task T07: Workspace repo discovery
- **Objective:** Find candidate repos under a root for D22 registration, without subprocesses and without following symlinks.
- **Files/Surfaces:** `src/shepherd/discovery.py`, `tests/unit/test_discovery.py`
- **Dependencies:** T04
- **Allowed Scope:**
  - `os.scandir` walk to `max_depth`.
  - A directory is a repo if it contains `.git` (dir, or a file for worktrees/submodules). Continue descending inside a repo to find nested repos, but never enter `.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, or `.tox`. Skip symlinks.
  - `read_origin_remote` parses `.git/config` with `configparser` (section `remote "origin"`, key `url`). A `.git` file resolves `gitdir:`. Any error → None.
  - Results are sorted by `root_path` and canonicalized.
- **Out-of-Scope Drift:** registering (T06/T15); invoking `git`; reading `.gitmodules`.
- **Expected Artifacts:** `discover_repos`.
- **Required Checks:** `test_discovery.py::test_finds_nested_git_dirs`, `::test_worktree_git_file_detected`, `::test_does_not_follow_symlinks`, `::test_skips_ignored_dirs`, `::test_depth_limit`, `::test_origin_remote_parsed`, `::test_broken_config_remote_none`, `::test_root_missing_or_not_dir_raises` (E40: missing → `FileNotFoundError`, file → `NotADirectoryError`, relative → `ValueError`)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_discovery.py`
- **Exit Criteria:** green
- **Test Seams:** integration-lite (temp filesystem trees)
- **Durability:** stable
- **Consumes:** `canonical_path`
- **Produces:** `DiscoveredRepo`, `discover_repos`, `read_origin_remote`

### Task T08: IPC frame protocol + `hookd` dispatcher
- **Objective:** The Spec S2 wire protocol, and a hook dispatcher that provably cannot harm Claude Code (P01, P11).
- **Files/Surfaces:**
  - `src/shepherd/ipc/__init__.py`, `src/shepherd/ipc/frames.py`, `src/shepherd/ipc/messages.py`, `src/shepherd/hookd.py`
  - `tests/unit/test_frames.py`, `tests/unit/test_messages.py`, `tests/unit/test_hookd.py`, `tests/perf/test_hookd_budget.py`
- **Dependencies:** T02 (socket and token names), T04 (`ChangeKind`, `SessionState`)
- **Allowed Scope:**
  - Spec S2 exactly. `read_frame` loops `recv` until the header and body are complete and raises `FrameRejected("short_header" | "timeout")` on EOF or `socket.timeout`. The socket.timeout type is caught via `OSError`, so the `socket` module is not imported (R6).
  - `create_token` writes via `os.open(O_WRONLY|O_CREAT|O_EXCL, 0o600)`, replacing any existing file atomically.
  - **hookd:** subprocess tests run `[sys.executable, "-I", "-S", hookd_path, "--runtime-dir", d]` with stdin payloads. The fake server is a thread using `socket.socketpair`/AF_UNIX listeners in tests (tests may import `socket`).
- **Out-of-Scope Drift:** sessiond server loops (T13); parsing hook semantics (T09); any retry in hookd.
- **Expected Artifacts:** protocol module; `hookd.py`.
- **Required Checks:**
  - `test_frames.py::test_encode_decode_roundtrip`, `::test_decode_header_rejections` (bad magic, bad version, bad token, bad kind, oversize, short; E05), `::test_token_compare_uses_hmac_compare_digest` (source scan), `::test_read_frame_timeout_is_rejection`, `::test_create_token_mode_0600`, `::test_load_token_rejects_wrong_length`
  - `test_messages.py::test_session_change_roundtrip`, `::test_status_roundtrip`, `::test_decode_rejects_non_object`
  - `test_hookd.py::test_sends_enveloped_frame`, `::test_exit_zero_matrix` (P01 over: valid JSON, empty stdin, garbage bytes, JSON array, 5 MiB payload; each asserts rc==0, stdout==b"", stderr==b""), `::test_socket_absent` (E01, wall < 300 ms plus measured interpreter baseline), `::test_socket_path_is_directory`, `::test_blocked_socket_deadline` (E02: listener that accepts and never reads, with a 4 MiB payload forcing a blocked send), `::test_token_missing_sends_nothing` (E04), `::test_strips_tool_response_and_truncates` (E03), `::test_oversize_minimal_envelope`, `::test_ancestry_contains_parent_pid` (Linux), `::test_constants_match_ipc`, `::test_hookd_frame_matches_ipc`, `::test_hookd_imports_stdlib_only` (R5)
  - `tests/perf/test_hookd_budget.py::test_p99_wall_under_budget` (`@pytest.mark.slow`; 200 runs; records p50/p99 to `build/perf/hookd_budget.json`; asserts p99 ≤ interpreter-baseline p99 + 250 ms)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_frames.py tests/unit/test_messages.py tests/unit/test_hookd.py`. The perf test is probabilistic (slow lane): flake policy is one automatic retry, and two consecutive failures fail the task.
- **Exit Criteria:** green, including the slow perf test.
- **Test Seams:** unit (codec); process seam (hookd as a real subprocess against a real AF_UNIX socket)
- **Durability:** stable
- **Consumes:** `HOOK_SOCKET_NAME`, `TOKEN_NAME`, `ChangeKind`, `SessionState`, `JsonObject`, `JsonValue`
- **Produces:** `MAGIC`, `PROTOCOL_VERSION`, `HEADER_FORMAT`, `HEADER_LEN`, `MAX_BODY`, `FrameKind`, `FrameRejected`, `Frame`, `ByteReader`, `encode_frame`, `decode_header`, `read_frame`, `create_token`, `load_token`, `SessionChange`, `IngestCounters`, `SessiondStatus`, `encode_json`, `decode_json_object`, `encode_session_change`, `decode_session_change`, `encode_status`, `decode_status`, `counters_to_json`, `HOOKD_ENVELOPE_VERSION`, `build_envelope`, `read_ancestry`, `main` (hookd)

### Task T09: Ingest — tolerant parse + the fold state machine (pure)
- **Objective:** Turn an envelope into a column patch, implementing Behavior contract 1 exactly, total over all inputs.
- **Files/Surfaces:**
  - `src/shepherd/ingest/__init__.py`, `src/shepherd/ingest/events.py`, `src/shepherd/ingest/fold.py`, `src/shepherd/testkit/hook_payloads.py`
  - `tests/fixtures/hooks/*.json`: one sanitized file per observed event type, copied from the probe with paths rewritten to `/work/ox/api` and prompts shortened
  - `tests/unit/test_events.py`, `tests/unit/test_fold.py`, `tests/unit/test_fold_sequences.py`, `tests/unit/test_fold_properties.py`
- **Dependencies:** T04, T08
- **Allowed Scope:**
  - **`parse_envelope`** never raises. Rules:
    - wrong-typed fields become None (E06);
    - `effort_level` accepts `{"level": str}` or a str;
    - `background_tasks` is a list, else None;
    - `hook_event_name` missing → `event=None`, `malformed_reason="no_event_name"`;
    - `unparsed_len` or `oversize` envelope → `event=None` with a reason (an oversize envelope with a `session_id` and name still yields a minimal `HookEvent`).
  - **`fold_event`** follows Behavior contract 1. `changes_between` derives change kinds by comparing before and after `Session` values: state → `session.state_changed`; `needs_you_reason` None→value or value→None → `needs_you.raised`/`needs_you.cleared`; tasks → `task.progress`; subagents → `subagent.count_changed`; title/brief/model/effort/repos_touched → `session.updated`.
  - **`apply_signals`:** the newest `custom` title beats the newest `ai` title (DV-25); the ratchet is respected; `ModelSignal`/`EffortSignal` set model/effort; `PromptSignal` sets brief only when `current.brief is None`.
  - `sweep_decision` per contract.
  - The fixtures record real shapes; tests never invent fields the probe did not observe, except in the E06 mutation tests.
- **Out-of-Scope Drift:** DB access; socket code; stop classification (M2); reading transcripts.
- **Expected Artifacts:** the pure ingest core.
- **Required Checks:**
  - `test_events.py::test_parse_total` (fixtures + garbage), `::test_malformed_counts` (reason set, event None), `::test_effort_object_and_string`, `::test_wrong_types_become_none` (E06), `::test_oversize_envelope_minimal_event`, `::test_ancestry_parsed_and_bad_entries_dropped`
  - `test_fold.py`:
    - `::test_session_start_idle_is_not_running` (B1: startup/resume/clear/absent/unknown source → stopped, ended_at None)
    - `::test_session_start_compact_revives`
    - `::test_user_prompt_sets_brief_and_brief_title`
    - `::test_permission_request_raises`, `::test_permission_reason_absent_fields`, `::test_permission_reason_formats` (Bash, Edit relative path, WebFetch host, control chars stripped, 160 cap)
    - `::test_matching_posttool_clears`, `::test_nonmatching_posttool_keeps`, `::test_posttool_clears_when_pending_unknown_after_restart`, `::test_posttoolfailure_and_permission_denied_clear_matching_pending`, `::test_late_permission_request_has_no_effect` (A8)
    - `::test_stop_clears_needs_you`, `::test_stop_zeroes_subagents_only_when_background_tasks_empty`
    - `::test_session_end_sets_ended_at`
    - `::test_late_message_display_after_stop_ignored` (E08), `::test_stop_hook_continuation_revives` (E09)
    - `::test_after_session_end_only_start_or_prompt_revive`
    - `::test_subagent_counts_clamp` (E10), `::test_task_completed_without_created` (E11)
    - `::test_repos_touched_from_edit_write_paths` (DV-06; relative path joined with cwd; path outside any repo ignored; dedupe; cap 50)
    - `::test_unknown_event_only_liveness`
    - `::test_no_changes_when_only_last_event_at`
    - `::test_engine_proc_captured_from_ancestry`
    - `::test_apply_signals_custom_beats_ai_and_ratchet` (P13)
    - `::test_sweep_dead_process_stops_with_ended_at` (E35), `::test_sweep_abandon_timeout_running_only`, `::test_sweep_never_ages_needs_you` (E36)
  - `test_fold_sequences.py::test_probe_run1_sequence_end_state` (replays `events-run1`-shaped fixtures: subagent run then Stop then SessionEnd → stopped, ended, subagents 0), `::test_probe_run2_task_counts` (3 created, 3 completed), `::test_probe_permission_run` (PermissionRequest → Stop → stopped, reason None)
  - `test_fold_properties.py::test_random_sequences_preserve_invariants` (P06; `random.Random(seed)` over 2000 sequences of length ≤ 60 drawn from fixture events plus mutations; after each step asserts the needs_you biconditional, counters ≥ 0, done ≤ total, repos_touched unique ≤ 50, title_source monotone; seeds printed on failure)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic (seeded), `PYTEST tests/unit/test_events.py tests/unit/test_fold*.py`
- **Exit Criteria:** green; R6 passes for `shepherd.ingest`; `fold.py` < 600 lines (split `permission_reason` and sweep into `ingest/reasons.py` if needed, keeping the exported names re-exported from `fold.py`).
- **Test Seams:** unit (pure); fixture seam (sanitized real payloads)
- **Durability:** stable (the fold contract); near-term-refactor (M2 adds a stop-trigger output)
- **Consumes:** `build_envelope`, `Session`, `SessionLivePatch`, `UNSET`, `Repo`, `ChangeKind`, `ProcAncestor`, `Signal`, `TitleSignal`, `PromptSignal`, `ModelSignal`, `EffortSignal`, `repo_for_path`, `canonical_path`, `brief_title`, `to_iso`, `iso_age_s`, `JsonObject`, `JsonValue`
- **Produces:** `KNOWN_EVENTS`, `PATH_TOOLS`, `HookEvent`, `HookEnvelope`, `parse_envelope`, `LATE_EVENT_GRACE_S`, `MAX_REPOS_TOUCHED`, `CONSUMED_EVENTS`, `FoldMemory`, `FoldInput`, `FoldOutcome`, `fold_event`, `apply_signals`, `permission_reason`, `sweep_decision`, `changes_between`, `hook_payload`, `envelope_bytes`

### Task T10: JSONL reader + Claude Code transcript reading
- **Objective:** Read the engine's transcripts tolerantly (D25 reader rule) for titles, model and effort, and list subagents on demand (PD-09).
- **Files/Surfaces:**
  - `src/shepherd/jsonl.py`, `src/shepherd/engine/__init__.py`, `src/shepherd/engine/claude_code/__init__.py`, `src/shepherd/engine/claude_code/transcript.py`
  - `tests/fixtures/claude_projects/-work-ox-api/<uuid>.jsonl` plus `<uuid>/subagents/agent-<id>.{jsonl,meta.json}` (sanitized from real files: one foreground finished agent, one foreground running agent, one background agent; includes `ai-title`, `custom-title`, `last-prompt`, `assistant` with `message.model`, and a truncated final line)
  - `tests/unit/test_jsonl.py`, `tests/unit/test_transcript.py`
- **Dependencies:** T00, T04
- **Allowed Scope:**
  - **`read_jsonl_delta`:**
    - seek to offset, read up to `max_bytes`;
    - consume only through the last `\n`, so a partial trailing line is not consumed and `new_offset` stops before it;
    - lines that are not valid JSON objects are counted in `malformed` and skipped;
    - if `offset > file size` (rotation or truncation), restart at 0;
    - **tail start:** when `offset == 0` and the file is larger than `max_bytes`, seek to `size - max_bytes`, discard bytes up to and including the first `\n` (that leading partial line is **not** counted as malformed), and parse from there. `new_offset` is the end of the last complete line. This is PD-11's "restart re-reads the last 8 MiB";
    - when `offset > 0`, read forward at most `max_bytes`; the next call continues from `new_offset`.
  - `project_slug` replaces every char outside `[A-Za-z0-9]` with `-`.
  - `locate_transcript_in` globs `projects_dir/*/<id>.jsonl`. The id must match a UUID regex, else None. With multiple matches it takes the newest mtime.
  - `is_transcript_path_allowed` returns a resolved path only if `realpath` is under `realpath(projects_dir)` and the suffix is `.jsonl` (E24).
  - `parse_signals` maps `ai-title.aiTitle` → `TitleSignal("ai")`, `custom-title.customTitle` → `TitleSignal("custom")`, `last-prompt.lastPrompt` → `PromptSignal`, `assistant.message.model` → `ModelSignal`, `assistant.effort` (str) → `EffortSignal`. It ignores `isSidechain: true` entries and every other type.
  - `list_subagents_in` reads `*.meta.json` and the parent transcript's `user` entries whose `message.content[*]` has `type=="tool_result"`, collecting their `tool_use_id`s (bounded to the last 32 MiB). It computes `subagent_state`, and takes `started_at`/`last_activity_at` from the first and last `timestamp` in the agent's jsonl.
- **Out-of-Scope Drift:** writing to transcripts (principle 4, D29); stop-evidence extraction (M2); `pr-link` (DV-08).
- **Expected Artifacts:** transcript utilities.
- **Required Checks:**
  - `test_jsonl.py::test_skips_malformed_trailing_line` (E23), `::test_partial_line_consumed_after_completion`, `::test_offset_beyond_size_restarts`, `::test_offset_zero_on_large_file_starts_at_tail_and_partial_line_not_counted` (A5), `::test_max_bytes_bound`, `::test_non_object_lines_counted`
  - `test_transcript.py::test_project_slug_examples` (`/root/Shepherd` → `-root-Shepherd`; `/tmp/claude-0/-root-Shepherd/x` → `-tmp-claude-0--root-Shepherd-x`), `::test_parse_signals_types`, `::test_sidechain_entries_ignored`, `::test_locate_by_glob`, `::test_locate_rejects_non_uuid`, `::test_transcript_path_outside_projects_rejected` (E24), `::test_list_subagents_states` (finished / running / background unknown), `::test_missing_transcript_empty`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_jsonl.py tests/unit/test_transcript.py`
- **Exit Criteria:** green; fixtures contain no real prompts from the user's sessions (sanitized; reviewed in the diff).
- **Test Seams:** integration-lite (fixture files)
- **Durability:** near-term-refactor (engine file formats drift across `claude` versions)
- **Consumes:** `JsonObject`, `JsonValue`, `Signal`, `TitleSignal`, `PromptSignal`, `ModelSignal`, `EffortSignal`, `SubagentInfo`, `SubagentState`
- **Produces:** `JsonlDelta`, `read_jsonl_delta`, `project_slug`, `parse_signals`, `locate_transcript_in`, `is_transcript_path_allowed`, `subagent_state`, `list_subagents_in`

### Task T11: Claude Code hook settings — merge, install, uninstall
- **Objective:** Install and remove exactly our hook entries in a *chosen* settings file. Idempotent, reversible, backed up, and never corrupting (P12).
- **Files/Surfaces:** `src/shepherd/engine/claude_code/hooks_settings.py`, `tests/unit/test_hooks_settings.py`, `tests/integration/test_hooks_install_io.py`
- **Dependencies:** T00, T02
- **Allowed Scope:**
  - **Entry shape per event E:**
    - `{"matcher": "*", "hooks": [ENTRY]}` for **every** event (the probe-accepted group shape; DV-04). No `watchPaths` events are ever generated;
    - `ENTRY = {"type": "command", "command": <hook_command>, "timeout": 5}`, plus `"_shepherd_managed": true` when `HOOK_MARKER_KEY_ENABLED`.
  - **`merge_hooks`** first strips existing shepherd entries, then appends ours at the end of each event list. It preserves all other keys and their order.
  - **`strip_hooks`** removes entries where `is_shepherd_entry`, drops groups that become empty, drops event keys that become empty, and drops `hooks` if it becomes empty **only if we created it**, recorded via the absence of other events. It returns the count removed.
  - **`install_into`/`uninstall_from`:**
    - missing file → treat as `{}` (install creates it with mode 0600);
    - invalid JSON or non-object → `SettingsFileInvalid`, file untouched (E25);
    - when content changes, back up the original to `backup_dir/claude-settings/<utc-ts>-<basename>` at 0600, then atomically replace, preserving the original mode;
    - return `(backup_path, count, changed)`.
  - `hook_command` = `shlex.join([str(python), "-I", "-S", str(dispatcher), "--runtime-dir", str(runtime_dir), MANAGED_ARG])`.
- **Out-of-Scope Drift:** choosing a target (the CLI's job, T17); writing `~/.claude/settings.json` in any test; the settings-validation probe (T19).
- **Expected Artifacts:** a pure merge core plus a thin IO layer.
- **Required Checks:**
  - `test_hooks_settings.py::test_merge_idempotent`, `::test_strip_merge_is_identity_on_user_settings` (P12, generated settings incl. user hooks on the same events, E26), `::test_order_of_user_entries_preserved`, `::test_every_group_has_star_matcher`, `::test_generated_events_subset_of_probe_accepted_and_no_watchpaths`, `::test_is_shepherd_entry_by_key_or_command_marker`, `::test_marker_key_toggle_respected`, `::test_hook_command_is_shell_safe` (paths with spaces and quotes round-trip through `shlex.split`)
  - `test_hooks_install_io.py::test_invalid_json_untouched` (E25), `::test_backup_created_and_mode_preserved`, `::test_missing_file_created_0600`, `::test_uninstall_restores_semantic_equality`, `::test_no_change_no_backup`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_hooks_settings.py tests/integration/test_hooks_install_io.py`
- **Exit Criteria:** green; a repo-rules addition asserts no test file references `.claude/settings.json` under the real home (text scan for `Path.home()` combined with `settings.json`).
- **Test Seams:** unit (pure merge); integration (temp files)
- **Durability:** stable
- **Consumes:** `JsonObject`, `JsonValue`, `utc_now_iso`
- **Produces:** `HOOK_MARKER_KEY`, `HOOK_MARKER_KEY_ENABLED`, `MANAGED_ARG`, `PROBE_ACCEPTED_EVENTS`, `SettingsFileInvalid`, `hook_command`, `is_shepherd_entry`, `merge_hooks`, `strip_hooks`, `install_into`, `uninstall_from`

### Task T12: `EngineAdapter` seam — `ClaudeCodeEngine`, `ScriptedEngine`, contract suite
- **Objective:** The M1 `EngineAdapter` Protocol (DV-14) with its real implementation and its `Scripted*` peer, both passing one contract suite (§14 lane 2).
- **Files/Surfaces:** `src/shepherd/engine/base.py`, `src/shepherd/engine/claude_code/adapter.py`, `src/shepherd/testkit/scripted_engine.py`, `tests/contract/test_engine_adapter_contract.py`, `tests/unit/test_claude_code_engine.py`
- **Dependencies:** T04, T09 (`CONSUMED_EVENTS`), T10, T11
- **Allowed Scope:**
  - `ClaudeCodeEngine`:
    - `engine_id()` = `"claude_code"`; `process_names()` = `frozenset({"claude"})`; capabilities per DV-29.
    - `hook_events()` = the 14 names of DV-04, in a fixed order; a test asserts `set(hook_events()) == CONSUMED_EVENTS`.
    - `locate_transcript` delegates to `locate_transcript_in`.
    - `parse_transcript_delta` delegates to `read_jsonl_delta` + `parse_signals` and sets `last_malformed_lines`.
    - `list_subagents` delegates to `list_subagents_in`.
    - `accept_transcript_path` delegates to `is_transcript_path_allowed(self.projects_dir, candidate)`.
    - `install_hooks(dispatcher, target)` builds `hook_command(self.python, dispatcher, self.runtime_dir)` and calls `install_into(target.settings_path, cmd, self.hook_events(), self.backup_dir)`; `uninstall_hooks` calls `uninstall_from`. Both return `HookInstallReport`.
  - `ScriptedEngine` answers from its constructor data. Its `install_hooks` writes a JSON record under `settings_root` so the contract suite can observe install and uninstall symmetry.
  - **Contract suite**, parametrized over both implementations, asserts:
    - `engine_id` is non-empty;
    - capabilities are well-formed;
    - `parse_transcript_delta` offset is monotone and idempotent at EOF;
    - `list_subagents` for an unknown id returns `[]`;
    - `accept_transcript_path` rejects `/etc/passwd`, a relative path, and a non-`.jsonl` file, and accepts a file inside its root;
    - `locate_transcript` for an unknown id returns None;
    - `hook_events` is non-empty and unique;
    - install then uninstall reports `changed` symmetric and `added == removed`;
    - a second install reports `changed == False`.
- **Out-of-Scope Drift:** `spawn_argv`, `set_title` (M3); other engines.
- **Expected Artifacts:** the seam, two adapters, one contract suite.
- **Required Checks:** `test_engine_adapter_contract.py::*` (≥ 7 cases × 2 implementations); `test_claude_code_engine.py::test_capabilities_m1_honest`, `::test_hook_events_equal_consumed_events` (DV-04), `::test_install_targets_given_settings_path_only`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/contract/test_engine_adapter_contract.py tests/unit/test_claude_code_engine.py`
- **Exit Criteria:** green; both implementations pass the identical suite; R7 holds (engine ↛ store); R8 holds.
- **Test Seams:** contract seam (the Protocol is the test surface)
- **Durability:** stable (seam); near-term-refactor (M3 adds methods)
- **Consumes:** `Signal`, `SubagentInfo`, `read_jsonl_delta`, `parse_signals`, `locate_transcript_in`, `is_transcript_path_allowed`, `list_subagents_in`, `hook_command`, `install_into`, `uninstall_from`, `CONSUMED_EVENTS`
- **Produces:** `EngineCapabilities`, `HookTarget`, `HookInstallReport`, `EngineAdapter`, `ClaudeCodeEngine`, `ScriptedEngine`

### Task T13: `sessiond` — sockets, schema gate, writer loop, ingest service, sweep, logging
- **Objective:** The long-lived daemon that accepts hook frames, stays gated until controld confirms the schema, folds events through `store/`, sweeps liveness, and pushes `SESSION_CHANGED` frames.
- **Files/Surfaces:**
  - `src/shepherd/logs.py`
  - `src/shepherd/sessiond/__init__.py`, `src/shepherd/sessiond/ingest_service.py`, `src/shepherd/sessiond/writer.py`, `src/shepherd/sessiond/servers.py`, `src/shepherd/sessiond/main.py`
  - `tests/integration/test_sessiond.py`, `tests/integration/test_ingest_service.py`, `tests/unit/test_logs.py`
- **Dependencies:** T03, T06, T08, T09, T12
- **Allowed Scope:**
  - **`run_sessiond`** does, in order:
    1. `ensure_private_dirs`;
    2. `flock(sessiond_lock)` (fail → `EXIT_LOCKED`);
    3. create the token if absent or stale (Spec S2);
    4. unlink stale sockets while holding the lock, then bind both sockets at 0600 and verify;
    5. start `WriterLoop` **gated**;
    6. serve until `stop` is set;
    7. set `ready` after bind.
    - `Store.open(expected_schema_version=SCHEMA_VERSION)` happens **only when the gate first opens**. `SchemaVersionMismatch` keeps it gated and is logged.
  - **Hook server:** one frame per connection, 1 s deadline, `allowed={HOOK_EVENT}`. On success, `writer.submit(body)`. On `FrameRejected`, call `service.count_rejected_frame()` and close.
  - **Control server:**
    - enforces `HELLO` → `SCHEMA_READY` and supersedes any previous connection;
    - on a version match, sends `writer.open_gate()` + `STATUS`; on a mismatch, sends `writer.close_gate()` + `ERROR{schema_mismatch}`;
    - answers `STATUS_REQUEST`;
    - `notify` never touches the socket. It does `put_nowait` onto a bounded outbound `queue.Queue(maxsize=1024)` drained by a dedicated sender thread; a full queue means `notifications_dropped += 1`. The sender writes with a 2 s socket send timeout, and on timeout closes the connection and counts the queued items as dropped; controld reconnects and clients `resync`. With no connection, `notifications_dropped += 1`. **The writer thread can never block on controld.**
  - **`WriterLoop`:**
    - a bounded queue; `submit` returns False and counts `dropped_backpressure` when full;
    - while gated, it does not consume (the queue buffers up to its max);
    - when open, it drains, calls `service.handle_envelope_body`, and every `sweep_interval_s` calls `service.sweep()`;
    - all service calls happen on this one thread (PD-01).
  - **`IngestService.handle_envelope_body`:**
    1. `parse_envelope`; a malformed result counts and returns.
    2. `session_id` None → malformed.
    3. `get_session_by_engine_id`; if missing and `cwd` present → `register_attached_session` (inserted at prompt, DV-30) and remember `session.registered` for this step's single combined notification; if `cwd` absent → `deferred_no_cwd`.
    4. Load repos (5 s TTL cache).
    5. `fold_event`, then `apply_live_patch` if the patch is not empty. A liveness-only patch is written at most once per `LIVENESS_WRITE_INTERVAL_S` (5 s) per session.
    6. Notify `SessionChange` with `changes_between(before, after)` when non-empty. Otherwise send a liveness-only `session.updated` if the last notification for this session is older than `LIVENESS_NOTIFY_INTERVAL_S` (30 s).
    7. On `refresh_transcript`, resolve the path with `engine.accept_transcript_path(event.transcript_path)`, falling back to `engine.locate_transcript(engine_session_id)` and counting `transcript_path_rejected` when rejected (seam-only access, D9). Then run `parse_transcript_delta` from the in-memory offset, `apply_signals`, `apply_live_patch`, and notify.
    8. Unknown names increment `unknown_event`.
    9. Any unexpected exception is logged with the correlation id, counted as `malformed`, and never kills the thread.
  - **`sweep`** runs `sweep_decision` for each of `list_live_sessions()` with `probe.is_alive`.
  - **Logging** via `configure_daemon_logging` (daily + size rotation, gzip, 14 days).
- **Out-of-Scope Drift:** runner or tmux; mailbox; any DDL (P04); HTTP.
- **Expected Artifacts:** a runnable sessiond (`run_sessiond` in a thread for tests).
- **Required Checks** (in `tests/integration/` unless noted):
  - `test_sessiond.py::test_sockets_mode_0600_and_dir_0700` (P11), `::test_refuses_insecure_runtime_dir` (E32), `::test_second_instance_exits_locked`, `::test_hook_socket_rejects_bad_token` (E05; counter increments; body never parsed), `::test_gate_buffers_then_drains`, `::test_schema_mismatch_stays_gated`, `::test_never_migrates_unmigrated_db` (P04: DB file with no tables; sessiond stays gated; `sqlite_master` empty afterwards), `::test_change_pushed_to_control`, `::test_backpressure_counts`, `::test_notifications_dropped_without_controld`, `::test_stalled_controld_does_not_block_writer` (A9: controld peer that never reads; ingest of 5000 envelopes completes; connection closed after the send timeout; drops counted), `::test_new_hello_supersedes_old_connection`, `::test_hookd_to_sessiond_real_subprocess` (real hookd process → row registered)
  - `test_ingest_service.py::test_first_event_stop_registers_then_stopped` (E07), `::test_registration_initial_state_from_fold` (DV-30: SessionStart-first → at prompt; PreToolUse-first → running; one combined notification), `::test_transcript_refresh_sets_engine_title_and_model`, `::test_transcript_path_outside_projects_counted` (E24), `::test_liveness_only_patch_throttled`, `::test_liveness_notification_throttled_30s`, `::test_sweep_uses_probe` (`ScriptedProcessProbe`), `::test_exception_in_fold_does_not_kill_writer`, `::test_rebind_visible_to_next_event` (controld-side `register_repo` then event → same row, repo set)
  - `tests/unit/test_logs.py::test_rotates_on_size_and_gzips`, `::test_retention_deletes_old`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/integration/test_sessiond.py tests/integration/test_ingest_service.py tests/unit/test_logs.py`. Socket tests use `make_short_base_dir()`, with every wait bounded (≤ 5 s) through `threading.Event`, never bare sleeps.
- **Exit Criteria:** green; R2 and R4 hold; each sessiond module < 600 lines.
- **Test Seams:** integration (real sockets, real SQLite, `ScriptedEngine`/`ScriptedProcessProbe`); process seam (real hookd)
- **Durability:** stable
- **Consumes:** `Platform`, `PlatformPaths`, `ensure_private_dirs`, `ProcessProbe`, `ShepherdConfig`, `EXIT_LOCKED`, `EXIT_CONFIG`, `Store`, `SCHEMA_VERSION`, `SchemaVersionMismatch`, `FrameKind`, `FrameRejected`, `read_frame`, `encode_frame`, `create_token`, `load_token`, `SessionChange`, `IngestCounters`, `SessiondStatus`, `encode_session_change`, `encode_status`, `encode_json`, `decode_json_object`, `parse_envelope`, `fold_event`, `FoldInput`, `FoldMemory`, `apply_signals`, `sweep_decision`, `changes_between`, `KNOWN_EVENTS`, `AttachedSessionRegistration`, `EngineAdapter`, `utc_now_iso`, `new_id`
- **Produces:** `configure_daemon_logging`, `IngestService`, `LIVENESS_WRITE_INTERVAL_S`, `LIVENESS_NOTIFY_INTERVAL_S`, `WriterLoop`, `run_sessiond`

### Task T14: `controld` core — startup and migrations, sessiond link, `EventHub`, SSE gap replay
- **Objective:** A restartable control plane that migrates (§7 rules 1–2), links to sessiond (rule 3), and turns `SESSION_CHANGED` into a strictly-monotonic, replayable event stream (P08).
- **Files/Surfaces:**
  - `src/shepherd/controld/__init__.py`, `src/shepherd/controld/events.py`, `src/shepherd/controld/sessiond_link.py`, `src/shepherd/controld/main.py`
  - `tests/unit/test_events_hub.py`, `tests/integration/test_sessiond_link.py`, `tests/integration/test_controld_startup.py`
- **Dependencies:** T05, T06, T08, T13
- **Allowed Scope:**
  - **`run_controld`** does, in order:
    1. `ensure_private_dirs`;
    2. `flock(controld_lock)` → `EXIT_LOCKED`;
    3. `configure_daemon_logging`;
    4. `apply_migrations(paths.db_path)`; `StoreRefusal` → log + `EXIT_SCHEMA_REFUSED`;
    5. `Store.open`;
    6. `boot_id = new_id("boot")`;
    7. `EventHub(store)`;
    8. `SessiondLink(..., on_change=lambda c: publish_session_change(store, hub, c))`;
    9. if `serve_http`, start `make_server(HttpDeps(...), config.http_port)` (imported lazily from `shepherd.controld.http`, which T15 creates); T14's tests call `run_controld(..., serve_http=False)`.
  - **`publish_session_change`:**
    - loads the session and repo names;
    - `kinds` containing `session.registered` → publish `session.registered`;
    - state changed → `session.state_changed` with `from`/`to`;
    - reason raised or cleared → `needs_you.raised`/`needs_you.cleared`;
    - remaining kinds each publish their own type with the card.
  - **`EventHub`** follows Behavior contract 2 exactly. It reserves a seq block on construction and whenever `next == reserved`. `parse_last_event_id`: header beats query; non-integer or negative → `"invalid"` (→ `resync`). `format_sse` per the wire format.
  - **`SessiondLink`:** a thread that connects, sends `HELLO` + `SCHEMA_READY{SCHEMA_VERSION}`, reads frames (`SESSION_CHANGED` → `on_change`; `STATUS` → cached; `ERROR` → cached `last_error`), sends `STATUS_REQUEST` every 10 s, times out after 30 s, and reconnects with backoff 0.2 → 5 s.
- **Out-of-Scope Drift:** HTTP routes (T15); the registry (M4); persisting events (D24: the ring is memory-only).
- **Expected Artifacts:** controld minus HTTP.
- **Required Checks:**
  - `tests/unit/test_events_hub.py::test_publish_order`, `::test_gap_replay_exact` (P08), `::test_empty_ring_k_equals_current_goes_live` (A7), `::test_concurrent_publishers_strictly_increasing` (A7: 8 threads × 1000 publishes; every subscriber sees a strictly increasing, gap-free sequence), `::test_resync_outside_ring`, `::test_resync_when_last_id_greater_than_current`, `::test_invalid_last_event_id_resync` (E27), `::test_seq_monotonic_across_restart` (E28: two hubs over one store; the second's first seq > the first's max), `::test_reserve_block_rollover_persists`, `::test_slow_subscriber_gets_resync_not_block`, `::test_format_sse_wire`
  - `tests/integration/test_sessiond_link.py::test_handshake_opens_gate`, `::test_reconnect_after_sessiond_restart`, `::test_status_cached`, `::test_schema_mismatch_error_surfaces`
  - `tests/integration/test_controld_startup.py::test_checksum_refusal_exit_78`, `::test_db_newer_exit_78`, `::test_second_controld_exits_75` (E22), `::test_change_to_event_published` (real sessiond + ScriptedEngine + real hookd envelope → hub event with card)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_events_hub.py tests/integration/test_sessiond_link.py tests/integration/test_controld_startup.py`
- **Exit Criteria:** green; R4 holds (controld imports sessiond nothing).
- **Test Seams:** unit (hub, deterministic with injected `now_iso`); integration (link + startup against real sessiond in-thread)
- **Durability:** stable
- **Consumes:** `apply_migrations`, `StoreRefusal`, `Store`, `SCHEMA_VERSION`, `EXIT_LOCKED`, `EXIT_SCHEMA_REFUSED`, `Platform`, `PlatformPaths`, `ensure_private_dirs`, `ShepherdConfig`, `configure_daemon_logging`, `FrameKind`, `encode_frame`, `read_frame`, `load_token`, `encode_json`, `decode_session_change`, `decode_status`, `SessionChange`, `SessiondStatus`, `new_id`, `utc_now_iso`, `EngineAdapter`, `run_sessiond`, `ScriptedEngine`
- **Produces:** `EventType`, `EventEnvelope`, `Subscription`, `EventHub`, `parse_last_event_id`, `format_sse`, `LinkStatus`, `SessiondLink`, `run_controld`, `publish_session_change`

### Task T15: `controld` HTTP API — routes, security, projections, SSE endpoint
- **Objective:** The Spec S3 surface: read-only fleet API, SSE, and CLI registration routes, with §13 posture and whitelist projections (P09).
- **Files/Surfaces:**
  - `src/shepherd/controld/security.py`, `src/shepherd/controld/projections.py`, `src/shepherd/controld/http.py`, `src/shepherd/controld/main.py` (wire `make_server`)
  - `src/shepherd/web/__init__.py` and stub `src/shepherd/web/static/{index.html,css/app.css,js/app.js,js/api.js,js/sse.js,js/fleet.js,js/dom.js}`
  - `tests/unit/test_projections.py`, `tests/unit/test_http_security.py`, `tests/integration/test_http_api.py`, `tests/integration/test_sse_http.py`
- **Dependencies:** T06, T07, T12, T14
- **Allowed Scope:**
  - Spec S3 exactly. Routing is a small table dispatch in `http.py` with regex path params: ids must match `^(wsp|rep|ses)_[0-9A-Za-z]{1,40}$`, else 404.
  - The SSE handler writes `retry`, replays or resyncs, then loops `subscription.next(15)` → write events or a heartbeat. It exits on `BrokenPipeError`/`ConnectionResetError` or `deps.stop`.
  - The discover route calls `discover_repos(Path(root_path), max_depth)` and marks `registered` by comparing against `list_repos(active_only=False)`.
  - The subagents route calls `engine.list_subagents(session.engine_session_id, parent_live=state != 'stopped')`, returning `[]` if `engine_session_id` is None.
  - Registration routes publish `workspace.changed`/`repo.changed` plus `session.updated` for each rebound id.
  - Each handler catches exceptions → 500 generic JSON with a correlation id, logged in full.
  - Static assets are loaded with `importlib.resources.files("shepherd.web") / "static"` using the fixed allowlist.
  - T15 creates **minimal stub files** at every allowlisted path (`index.html` with the module script tag, empty `css/app.css`, and one-line `// @ts-check` modules) so the static tests run; T16 replaces their contents without changing the file list.
- **Out-of-Scope Drift:** approvals, authorize, any session-mutating route (M3/M4); CORS headers; binding a non-loopback host.
- **Expected Artifacts:** a complete controld.
- **Required Checks:**
  - `tests/unit/test_projections.py::test_session_card_exact_keys` (P09), `::test_workspace_view_exact_keys`, `::test_repo_view_exact_keys`, `::test_subagent_view_exact_keys`, `::test_brief_excerpt_200`, `::test_card_never_contains_engine_session_id_or_cwd_or_credential_ref`
  - `tests/unit/test_http_security.py::test_host_check` (E29), `::test_origin_rejected` (E30), `::test_origin_absent_allowed`, `::test_security_headers_present`
  - `tests/integration/test_http_api.py::test_fleet_snapshot_shape_and_order`, `::test_fleet_includes_counters_and_unassigned`, `::test_session_detail_404`, `::test_subagents_projection`, `::test_create_workspace_then_rebound_events`, `::test_repo_conflict_409`, `::test_discover_marks_registered`, `::test_non_json_post_415`, `::test_invalid_json_or_fields_400` (E37), `::test_oversize_body_413_and_missing_length_411` (E38), `::test_discover_bad_root_400` (E40), `::test_workspace_name_and_repo_path_validation_400` (E41), `::test_static_allowlist_and_js_mime`, `::test_path_traversal_404`, `::test_500_is_generic_with_correlation_id`, `::test_untrusted_strings_are_json_escaped_not_mangled` (E31), `::test_server_binds_loopback_only`
  - `tests/integration/test_sse_http.py::test_last_event_id_header_replay` (P08 over real HTTP with `http.client` reading the stream), `::test_query_param_used_when_no_header`, `::test_resync_after_controld_restart`, `::test_heartbeat_emitted` (hub with injected short interval), `::test_client_disconnect_releases_subscription`
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/unit/test_projections.py tests/unit/test_http_security.py tests/integration/test_http_api.py tests/integration/test_sse_http.py`
- **Exit Criteria:** green; `http.py` < 600 lines (split route handlers into `controld/routes_fleet.py` and `controld/routes_registry.py` if needed, named in the diff).
- **Test Seams:** unit (projections, security predicates); integration (real HTTP on ephemeral port 0)
- **Durability:** stable (read API); near-term-refactor (mutating routes → M4 registry, DV-17)
- **Consumes:** `Store`, `RepoPathConflict`, `WorkspaceNotFound`, `RepoNotFound`, `EventHub`, `parse_last_event_id`, `format_sse`, `SessiondLink`, `LinkStatus`, `EngineAdapter`, `ShepherdConfig`, `discover_repos`, `session_order_key`, `workspace_order_key`, `state_label`, `FleetSnapshot`, `Session`, `Workspace`, `Repo`, `SubagentInfo`, `IngestCounters`, `counters_to_json`, `new_id`, `utc_now_iso`, `run_controld`
- **Produces:** `SECURITY_HEADERS`, `check_host`, `check_origin`, `SESSION_CARD_FIELDS`, `WORKSPACE_VIEW_FIELDS`, `REPO_VIEW_FIELDS`, `SUBAGENT_VIEW_FIELDS`, `session_card`, `repo_view`, `workspace_view`, `fleet_view`, `subagent_view`, `health_view`, `HttpDeps`, `make_server`

### Task T16: Fleet page (plain ES modules)
- **Objective:** Workspace → session → subagent tree, ordered by `order_key`, live over SSE, read-only, text-only DOM.
- **Files/Surfaces:** `src/shepherd/web/static/index.html`, `src/shepherd/web/static/css/app.css`, `src/shepherd/web/static/js/{app,api,sse,fleet,dom}.js`, `tests/integration/test_web_static.py`
- **Dependencies:** T15
- **Allowed Scope:**
  - **`dom.js`:** `el(tag, attrs, children)` sets text through `textContent` only, and `attrs` never includes `on*`/`href` for untrusted data.
  - **`api.js`:** `fetch` JSON helpers.
  - **`sse.js`:**
    - opens `EventSource('/api/events?last_event_id=' + seq)`;
    - on `resync` → refetch `/api/fleet` and reopen;
    - exposes connection state.
  - **`fleet.js`:**
    - keeps `Map` of workspaces and cards, applying card events idempotently by id;
    - sorts by `order_key` (string compare), workspaces by their `order_key`;
    - collapsed by default, with expansion state in `localStorage`;
    - workspace header shows counts;
    - session row shows glyph + `state_label` (⏸ amber `#F59E0B` needs you; ● blue `#3B82F6` running/starting; ○ neutral `#9CA3AF` at prompt / exited — M1-only neutral per DV-26), title (or `(untitled)`), repo name, `attached` badge, model · effort, age from `started_at`;
    - chips (**hidden when null or zero**): `needs_you_reason`, `tasks_done/tasks_total`, `N subagents` (click → GET subagents → indented lines), `repos_touched` (>1), "quiet Nm" when running and `last_event_at` is older than `liveness_window_s`;
    - `+N older sessions hidden`;
    - footer: sessiond connected, gated, and each non-zero `unknown`/counter (principle 5);
    - SSE connection indicator.
  - A 30 s local timer re-renders relative ages only (not polling: no network).
  - JSDoc `// @ts-check` headers. No inline scripts or styles (CSP).
- **Out-of-Scope Drift:** chat, Needs-You rail, session view, terminal, palette buckets beyond the three live states, any POST from the UI.
- **Expected Artifacts:** static UI.
- **Required Checks:**
  - `test_web_static.py::test_index_references_only_allowlisted_modules`, `::test_no_inline_script_or_style` (CSP), `::test_all_js_files_have_ts_check_header`, `::test_no_polling_constructs` (no `setInterval`/`setTimeout` whose callback contains `fetch(`: text scan), `::test_modules_served_with_js_mime`
  - R13 repo rule green
  - Manual checklist in T19 (L7–L12)
- **Checkpoint Type:** none (AFK); visual verification is HITL in T19
- **Validation Level:** deterministic (static scans) + manual (T19 checklist)
- **Exit Criteria:** scans green; page loads without console errors against a T18 scripted e2e instance (verified in T19).
- **Test Seams:** source-scan seam; manual browser seam (T19)
- **Durability:** near-term-refactor (M2 palette, Needs-You rail)
- **Consumes:** `SESSION_CARD_FIELDS`, `WORKSPACE_VIEW_FIELDS`, `REPO_VIEW_FIELDS`, `SUBAGENT_VIEW_FIELDS` (as JSON keys), `make_server` (static route)
- **Produces:** `src/shepherd/web/static/*` (fixed file list used by the T15 allowlist)

### Task T17: CLI — daemons, hooks, registration, service files, status
- **Objective:** The `shepherd` command. It runs both daemons in the foreground, installs hooks into an **explicit** target, registers workspaces and repos through controld, and writes (never enables) service files.
- **Files/Surfaces:** `src/shepherd/cli/__init__.py`, `src/shepherd/cli/__main__.py`, `src/shepherd/cli/main.py`, `src/shepherd/cli/http_client.py`, `tests/integration/test_cli.py`
- **Dependencies:** T03, T12, T13, T14, T15
- **Allowed Scope:** argparse subcommands. Every command honours `--profile` (sets `SHEPHERD_PROFILE`).

  | Subcommand | Behaviour |
  |---|---|
  | `controld run`, `sessiond run` | foreground, SIGTERM/SIGINT → `stop.set()` → exit code from `run_*` |
  | `hooks install (--project DIR \| --user --confirm-user-scope)` | copies `hookd.py` to `paths.bin_dir/hookd.py` (0644); `--project` targets `DIR/.claude/settings.local.json`; `--user` targets `~/.claude/settings.json` and **requires** `--confirm-user-scope`, else exit 64 with a message explaining it affects every Claude Code session on the machine; prints the `HookInstallReport` |
  | `hooks uninstall (--project DIR \| --user --confirm-user-scope)` | mirror of install |
  | `workspace add NAME [--root PATH]`, `workspace list` | via `ControldClient` |
  | `repo add PATH --workspace ID_OR_NAME [--name N]`, `repo deactivate ID` | names resolve through `GET /api/workspaces`; ambiguous → exit 64 |
  | `discover ROOT --workspace ID_OR_NAME [--max-depth N] [--add]` | prints candidates; `--add` POSTs each unregistered candidate |
  | `service install\|uninstall\|status` | builds `ServiceSpec`s for both daemons (sessiond `kill_mode_process=True`, argv `[sys.executable, "-m", "shepherd.cli", "--profile", p, "<daemon>", "run"]`); **prints** the `systemctl --user daemon-reload && systemctl --user enable --now …` hint; never runs it |
  | `status` | `GET /api/health`, human-readable; also reads `<data_dir>/hooks_installed.json` and prints `WARNING` for every recorded install whose baked `runtime_dir` ≠ `paths.runtime_dir` (A10) |

  `ControldClient` uses `urllib.request` to `http://127.0.0.1:<port>` with `Content-Type: application/json` and no Origin. It maps error JSON to `ControldError`. The `shepherd` script entry point is `shepherd.cli.main:main`.
- **Out-of-Scope Drift:** registry-generated commands (M4); `uninstall` of the whole product (M6); interactive prompts.
- **Expected Artifacts:** CLI.
- **Required Checks:** `test_cli.py::test_hooks_install_project_target_only`, `::test_user_scope_requires_confirm_flag` (exit 64; settings untouched), `::test_hooks_install_copies_dispatcher`, `::test_hooks_install_records_and_warns_when_socket_absent` (A10), `::test_status_warns_on_runtime_dir_mismatch` (A10), `::test_workspace_add_and_list_via_http` (in-thread controld + sessiond), `::test_repo_add_by_workspace_name`, `::test_discover_add_posts`, `::test_service_install_writes_files_never_runs_systemctl` (monkeypatch `subprocess.run` to fail if called with `enable`/`start`), `::test_controld_run_sigterm_exit_0` (subprocess), `::test_status_prints_counters`, `::test_controld_unreachable_exit_69` (E42), `::test_bad_profile_name_exit_64` (E42)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic, `PYTEST tests/integration/test_cli.py`
- **Exit Criteria:** green; `$PY -m shepherd.cli --help` lists all subcommands.
- **Test Seams:** integration (CLI in-process via `main(argv)` against in-thread daemons; subprocess for signal handling)
- **Durability:** near-term-refactor (M4 generates CLI from the registry)
- **Consumes:** `resolve_profile`, `current_platform`, `load_config`, `Platform`, `ServiceSpec`, `run_controld`, `run_sessiond`, `ClaudeCodeEngine`, `HookTarget`, `HookInstallReport`, `EXIT_CONFIG`, `EXIT_UNAVAILABLE`, `JsonObject`
- **Produces:** `main` (cli), `ControldClient`, `ControldError`

### Task T18: End-to-end (scripted) integration + hook write-volume measurement (§18)
- **Objective:** Prove the whole M1 pipeline without `claude`, and measure hook write volume under concurrency.
- **Files/Surfaces:** `tests/integration/test_e2e_scripted.py`, `tests/perf/test_hook_volume.py`, `src/shepherd/testkit/e2e.py` (a context manager starting sessiond + controld in threads on a temp profile, returning ports and paths; stays < 200 lines)
- **Dependencies:** T13, T14, T15, T16, T17
- **Allowed Scope:**
  - Drive real `hookd.py` subprocesses with fixture payloads into real sessiond, controld, SQLite, HTTP and SSE.
  - The **perf test** simulates 20 sessions × 50 `PostToolUse` events + 5 `TaskCreated` + 5 `TaskCompleted` each. Concurrency is 20 via `concurrent.futures.ThreadPoolExecutor`, each call spawning hookd.
  - It records hookd wall p50/p99, fold lag p50/p99 (`observed_at` → SSE receipt), total events/s, `dropped_backpressure`, and `sessiond` RSS. Output goes to `build/perf/hook_volume.json` (gitignored).
  - **Assertions:** zero drops; every session's final `tasks_done == tasks_total == 5`; fold-lag p99 < 500 ms.
  - **Decision rule (§18):** if fold-lag p99 ≥ 500 ms, or there is any drop, **task T18b becomes in-scope for M1** and must pass before T19. Thresholds are never raised silently.
- **Out-of-Scope Drift:** real `claude`; tuning beyond the decision rule.
- **Expected Artifacts:** e2e suite; perf JSON; the numbers copied into §Verification Evidence of this plan by the builder.
- **Required Checks:** `test_e2e_scripted.py::test_hook_to_sse`, `::test_needs_you_roundtrip`, `::test_subagent_expand_via_api` (fixture projects dir via `ClaudeCodeEngine(projects_dir=fixtures)`), `::test_sessiond_restart_keeps_rows_and_resumes` (§14 lane 4), `::test_controld_restart_clients_resync` (§14 lane 4), `::test_daemons_down_hookd_still_exits_zero` (principle 4), `::test_workspace_registration_rebinds_live_session`; `tests/perf/test_hook_volume.py::test_20_sessions_burst` (`@pytest.mark.slow`)
- **Checkpoint Type:** none (AFK)
- **Validation Level:** e2e deterministic; perf probabilistic (slow lane). Flake policy: one retry; report both runs' numbers; two consecutive failures of the assertions fail the task.
- **Exit Criteria:** all e2e green; perf test green with numbers recorded.
- **Test Seams:** e2e seam (all first-party components real; engine files from fixtures; no `claude`)
- **Durability:** stable
- **Consumes:** `run_sessiond`, `run_controld`, `ClaudeCodeEngine`, `ScriptedEngine`, `make_short_base_dir`, `isolated_env`, `current_platform`, `load_config`, `hook_payload`, `envelope_bytes`, `ControldClient`, `format_sse`
- **Produces:** `running_stack`, `StackHandle`, `build/perf/hook_volume.json`

### Task T19: Live verification against real `claude` (HITL)
- **Objective:** Verify the inferred assumptions A1–A3 and M1's acceptance criteria against a real Claude Code 2.1.270 on this host, **without touching the user's real state**.
- **Files/Surfaces:** `tests/live/conftest.py` (live isolation contract, PD-08), `tests/live/test_live_claude.py`, `scripts/live_m1.sh`, `tests/live/manifest_m1.json`
- **Dependencies:** T18 (and T18b when triggered)
- **Allowed Scope:**
  - Profile `qa` throughout (`SHEPHERD_PROFILE=qa`, `SHEPHERD_HOME=/tmp/shepherd-live/home`, http port 7421).
  - A throwaway git repo `/tmp/shepherd-live/work/demo`. Hooks installed **only** via `shepherd hooks install --project /tmp/shepherd-live/work/demo`.
  - Headless proofs use `claude -p` inside that repo.
  - The one interactive proof (A1) runs **only** on `tmux -L shepherd-qa` with an explicit `-L` on every call. Teardown is `tmux -L shepherd-qa kill-server`.
  - **Trust dialog**, exact sequence as used by the spike:
    1. `tmux -L shepherd-qa new-session -d -s shepherd_qa_l13 -c /tmp/shepherd-live/work/demo claude`
    2. Poll `tmux -L shepherd-qa capture-pane -p -t shepherd_qa_l13` (≤ 30 s) until the trust-dialog text is visible. **If it is not detected, abort without sending any key**; a blind Enter selects "No, exit".
    3. `tmux -L shepherd-qa send-keys -t shepherd_qa_l13 Down`, then `tmux -L shepherd-qa send-keys -t shepherd_qa_l13 Enter`.
    4. Re-capture and assert the dialog is gone before sending the prompt with `send-keys -l` + `Enter`.
    - The session name uses `_`, never `:`.
  - **Recorded side effect:** accepting trust makes Claude Code write a trust entry for `/tmp/shepherd-live/work/demo` into the user's real Claude config (`~/.claude.json`). Our code never edits that engine-owned file (principle 4). The stale entry for the deleted directory is harmless and is logged in §Verification Evidence; the B2 guard hashes `~/.claude/settings.json`, which trust does not touch.
  - No `~/.claude/settings.json` edits, no systemd enablement, no use of the `shepherd` socket.
- **Out-of-Scope Drift:** installing user-scope hooks; running the user's real profile; any change to the user's live sessions; macOS verification.
- **Expected Artifacts:** live test results; the completed manual checklist; evidence recorded in §Verification Evidence; DV-20 constant confirmed or flipped, with a note.
- **Required Checks:**
  - **Live isolation contract** (`tests/live/conftest.py`): uses `isolated_env(base, "qa", keep_real_home=True)`; the session-scoped autouse fixture calls `real_state_fingerprint()` before and after and asserts equality (B2). `tests/live/test_live_claude.py::test_l00_guard_self_check` proves the guard detects a synthetic change in a temp copy.
  - Automated (`SHEPHERD_LIVE=1`). **Order is enforced:** `scripts/live_m1.sh proof` runs `pytest -m live -k "l00 or l02"` first and aborts on failure, then runs the rest.
    - `test_live_claude.py::test_l1_session_start_registers_attached_and_binds_repo`
    - `::test_l02_generated_settings_shape_accepted`. **Runs first**, on the exact file T11 generates. The decision rule covers the case where no hook fires:
      1. With `_shepherd_managed` present, hooks fire → keep the key.
      2. No hook fires → rerun with `HOOK_MARKER_KEY_ENABLED=False`. If hooks fire, flip the constant and record it on DV-20.
      3. Still none → rerun with only the 12 observed events (drop `PostToolUseFailure` and `PermissionDenied`). If hooks fire, narrow `hook_events()` and `CONSUMED_EVENTS` and record it on DV-04.
      4. Still none → **M1 is blocked.** Stop and escalate at the HITL checkpoint. Never install anything at user scope.
    - `::test_l3_permission_request_needs_you_then_stopped` (-p mode auto-deny)
    - `::test_l3b_tui_permission_approve_and_deny` (tmux `-L shepherd-qa` only).
      - **Approve** (send the approve key after `capture-pane` shows the prompt) → asserts `needs_you` then `running` with the reason cleared.
      - **Deny and Esc** → records the observed event sequence and final state in §Verification Evidence.
      - **Decision rule:** if deny/Esc emits a consumed event (`PostToolUseFailure`, `PermissionDenied`, `Stop`, `UserPromptSubmit`), assert `needs_you` clears.
      - If it emits nothing, record the degrade on DV-07: the reason stays until the next prompt or event, which is honest because the session is waiting on the human. The test passes with a recorded degrade, and no code change is made in M1.
    - `::test_l4_task_counts_and_subagent_count`
    - `::test_l5_engine_title_arrives_from_transcript`
    - `::test_l6_ancestry_contains_claude` (A2; on failure record degrade, don't fail M1)
    - `::test_l13_interactive_tui_emits_same_core_events` (A1; tmux on `-L shepherd-qa` only)
    - `::test_l14_hook_overhead_per_tool_call` (median added latency of hooks, recorded)
  - **Manual checklist** (browser at `http://localhost:7421/` through `ssh -L 7421:127.0.0.1:7421 <host>`, same port on both ends; see A9):
    - **L7** the new session appears without reload, in its workspace
    - **L8** order is needs you → running → at prompt → exited
    - **L9** subagent expand shows type, description, state
    - **L10** chips hidden when null
    - **L11** kill `controld` and restart: the page reconnects and resyncs with no duplicate rows
    - **L12** a `<b>` in a prompt renders as literal text
- **Checkpoint Type:** human_verify — **HITL: manual-verification** (visual fleet checks L7–L12) and **external-access** (spends Claude subscription usage on a real `claude`)
- **Validation Level:** live (harness) + manual (checklist)
- **Exit Criteria:** L1–L5 and L13 pass; L6 and L14 pass or are recorded as degrades; the checklist is signed off by the user; `scripts/live_m1.sh cleanup` leaves no `shepherd-qa` tmux server, no QA daemons, and `/tmp/shepherd-live` removed.
- **Test Seams:** live e2e seam (real engine, first-party stack on the QA profile)
- **Durability:** session-only (evidence); stable (harness)
- **Consumes:** `main` (cli), `HOOK_MARKER_KEY_ENABLED`, `ControldClient` (the live lane runs real daemons through the CLI, not the T18 testkit stack)
- **Produces:** §Verification Evidence entries; possibly an amended DV-20

### Task T18b (conditional; in M1 scope only if T18's decision rule triggers): writer batching
- **Objective:** Meet the T18 volume thresholds by folding a writer drain of up to 64 envelopes in one store transaction.
- **Files/Surfaces:** `src/shepherd/sessiond/writer.py`, `src/shepherd/sessiond/ingest_service.py`, `src/shepherd/store/store.py` (adds `apply_live_patches(patches: Sequence[tuple[str, SessionLivePatch]]) -> list[Session]`), `tests/integration/test_writer_batching.py`
- **Dependencies:** T18
- **Allowed Scope:** batch per drain; keep single-writer semantics and per-event fold order; WAL `wal_autocheckpoint` tuning only.
- **Out-of-Scope Drift:** multiple writer threads; changing hookd; dropping events.
- **Expected Artifacts:** batched writes; re-run T18 numbers.
- **Required Checks:** `test_writer_batching.py::test_batch_preserves_event_order_per_session`, `::test_batch_failure_isolates_bad_envelope`; re-run `tests/perf/test_hook_volume.py::test_20_sessions_burst` green.
- **Checkpoint Type:** none (AFK)
- **Validation Level:** deterministic (batching) + probabilistic (perf, 1 retry)
- **Exit Criteria:** T18 thresholds met; numbers appended to §Verification Evidence.
- **Test Seams:** integration (store + writer)
- **Durability:** stable
- **Consumes:** `WriterLoop`, `IngestService`, `Store`, `SessionLivePatch`
- **Produces:** `Store.apply_live_patches`

## Live Verification Strategy

- **Manifest:** `tests/live/manifest_m1.json`
- **Environment ownership:** first-party `hookd`, `sessiond`, `controld`, SQLite, HTTP and SSE are live on profile `qa`. Claude Code 2.1.270 is the real external engine (consumed, not stubbed). The user's real `~/.claude/settings.json`, systemd user units and the `shepherd` tmux socket are **explicitly not touched**. Browser checks are manual.
- **Setup:** `bash scripts/bootstrap_venv.sh && bash scripts/live_m1.sh setup` — creates `/tmp/shepherd-live/{home,work/demo}`, `git init`s the demo repo, then runs `shepherd --profile qa hooks install --project /tmp/shepherd-live/work/demo` and starts `sessiond run` and `controld run` in the background with pidfiles.
- **Reset/Seed:** `bash scripts/live_m1.sh reset` stops the daemons, deletes the QA `SHEPHERD_HOME` (DB included), re-runs setup, then `shepherd --profile qa workspace add demo --root /tmp/shepherd-live/work` and `shepherd --profile qa discover /tmp/shepherd-live/work --workspace demo --add`.
- **Health:** `.venv/bin/python -m shepherd.cli --profile qa status` must report `sessiond.connected=true` and `gated=false`.
- **Isolation guard:** `tests/live/conftest.py` keeps the real HOME read-only for `claude` auth and transcripts, isolates `SHEPHERD_HOME`/`XDG_RUNTIME_DIR`/`XDG_CONFIG_HOME`, and asserts `real_state_fingerprint()` is unchanged (B2).
- **Proof scenarios** (L00 and L02 run first; the script aborts if either fails):
  - `Shape gate: the exact generated settings file makes hooks fire (4-step decision rule)` (L02)
  - `Golden path: hand-launched claude -p registers at prompt, binds to demo repo, then runs on first prompt` (L1)
  - `TUI permission: approve → running; deny/Esc recorded under decision rule` (L3b)
  - `Needs-you path: PermissionRequest raises needs_you with "permission: Bash(...)"` (L3)
  - `Progress path: TaskCreated/TaskCompleted and SubagentStart/Stop update counters` (L4)
  - `Title path: ai-title from transcript sets title_source=engine` (L5)
  - `Interactive path: TUI session on tmux -L shepherd-qa emits SessionStart/UserPromptSubmit/Pre/PostToolUse/Stop` (L13)
  - `Recovery path: controld restart → SSE resync, no duplicates` (L11, manual)
- **Stress scenarios:** `Hook overhead per tool call stays recorded` (L14). Synthetic concurrency is covered deterministically in T18 and is not repeated live.
- **Cleanup:** `bash scripts/live_m1.sh cleanup` stops the QA daemons by pidfile, runs `tmux -L shepherd-qa kill-server` if the socket exists (never a bare `kill-server`), and runs `rm -rf /tmp/shepherd-live`.

## Risk-Based Testing Matrix

| # | Risk | Prob. | Impact | Test required |
|---|---|---|---|---|
| R01 | hookd blocks, fails, or prints and so harms Claude Code (principle 4) | med | high | deterministic: `test_hookd.py::test_exit_zero_matrix`, `::test_blocked_socket_deadline`, `::test_socket_absent`; slow `test_hookd_budget.py` |
| R02 | Hook install corrupts or invalidates a user's settings file (ground truth 10) | med | high | deterministic: `test_hooks_settings.py::test_strip_merge_is_identity_on_user_settings`, `test_hooks_install_io.py::test_invalid_json_untouched`; live `test_l2_marker_key_tolerated`; CLI `test_user_scope_requires_confirm_flag` |
| R03 | Partial or failed migration leaves a corrupt schema | low | high | deterministic: `test_migrate.py::test_failing_migration_rolls_back_everything`; slow `::test_sigkill_mid_migration_leaves_old_version` |
| R04 | Old binary runs against a newer DB, or edited migration history | med | high | deterministic: `test_migrate.py::test_db_newer_refuses`, `::test_checksum_mismatch_refuses`; `test_controld_startup.py::test_*_exit_78` |
| R05 | sessiond migrates or races controld | low | high | deterministic: R2 rule; `test_sessiond.py::test_never_migrates_unmigrated_db`, `::test_schema_mismatch_stays_gated` |
| R06 | Wrong repo binding (partial-component match, nested repos, symlinks) | med | med | deterministic: `test_binding.py::*` incl. the permutation property |
| R07 | Out-of-order hook delivery shows a wrong state | high | med | deterministic: `test_fold.py::test_late_message_display_after_stop_ignored`, `::test_stop_hook_continuation_revives`; property `test_random_sequences_preserve_invariants` |
| R08 | Ghost `running` sessions after a kill with no `SessionEnd` | high | med | deterministic: `test_fold.py::test_sweep_dead_process_stops_with_ended_at`, `test_ingest_service.py::test_sweep_uses_probe`; live `test_l6_ancestry_contains_claude` |
| R09 | Field drift across `claude` versions (2.1.269 → 2.1.270) breaks ingest | med | med | deterministic: `test_events.py::test_wrong_types_become_none`, the property test; live L1–L5, L13 |
| R10 | SSE gap loses or duplicates events; seq regresses after restart | med | high | deterministic: `test_events_hub.py::test_gap_replay_exact`, `::test_seq_monotonic_across_restart`; `test_sse_http.py::test_last_event_id_header_replay`; e2e `test_controld_restart_clients_resync` |
| R11 | Frame spoofing by another local user or process | low | high | deterministic: `test_frames.py::test_decode_header_rejections`, `test_sessiond.py::test_sockets_mode_0600_and_dir_0700`, `::test_hook_socket_rejects_bad_token` |
| R12 | DNS rebinding or CSRF drives the mutating routes | low | med | deterministic: `test_http_security.py::*`, `test_http_api.py::test_non_json_post_415` |
| R13 | XSS via transcript, prompt or reason text | med | high | deterministic: R13 rule, `test_web_static.py::test_no_inline_script_or_style`, `test_http_api.py::test_untrusted_strings_are_json_escaped_not_mangled`; manual L12 |
| R14 | Raw row, secret, or internal path leaks through the API | low | high | deterministic: `test_projections.py::*_exact_keys`, `::test_card_never_contains_engine_session_id_or_cwd_or_credential_ref` |
| R15 | Dev, test or QA touches the user's live tmux sessions or real state (the §18 incident class) | med | high | deterministic: R14 rule, `test_config.py::test_non_default_profile_rejects_shepherd_socket`, `test_isolation.py::test_home_is_temp_in_tests`, `test_supervisor_contract.py::test_install_never_invokes_subprocess` |
| R16 | Hook write volume overwhelms the single writer | med | med | probabilistic (1 retry): `test_hook_volume.py::test_20_sessions_burst`, with the §18 decision rule |
| R17 | Concurrent registration creates duplicate session rows | med | med | deterministic: `test_store_concurrency.py::test_two_processes_register_same_engine_id_one_row` |
| R18 | Interactive TUI sessions differ from `-p` (A1) | med | med | live: `test_l13_interactive_tui_emits_same_core_events` |
| R19 | Transcript path injection makes sessiond read arbitrary files | low | med | deterministic: `test_transcript.py::test_transcript_path_outside_projects_rejected`, `test_ingest_service.py::test_transcript_path_outside_projects_counted` |
| R20 | The macOS drivers do not work | high | low | manual (recorded unverified, DV-02); deferred |
| R21 | Files grow past 600 lines, or `Any` creeps in | med | low | deterministic: R11, R12 rules + mypy `disallow_any_explicit` |
| R22 | Idle-at-prompt sessions shown as running (fresh-review B1) | high | med | deterministic: `test_fold.py::test_session_start_idle_is_not_running`, `test_ingest_service.py::test_registration_initial_state_from_fold` |
| R23 | Live lane breaks isolation or cannot authenticate (fresh-review B2) | med | high | deterministic guard: `tests/live/conftest.py` fingerprint assertion + `test_l00_guard_self_check` |
| R24 | Stalled controld blocks ingest (A9) | low | high | deterministic: `test_sessiond.py::test_stalled_controld_does_not_block_writer` |
| R25 | Generated hook settings shape rejected by Claude Code (A4) | med | high | live gate: `test_l02_generated_settings_shape_accepted` runs first with a 4-step decision rule; deterministic: `test_generated_events_subset_of_probe_accepted_and_no_watchpaths` |

## Acceptance Criteria → Proof (from the workflow intent)

| Acceptance criterion | Proven by |
|---|---|
| controld and sessiond both start on Linux; controld migrates in one transaction; sessiond refuses to migrate | T14 `test_controld_startup.py`, T05 `test_fresh_apply`/`test_failing_migration_rolls_back_everything`, T13 `test_never_migrates_unmigrated_db`, R2 |
| Checksum mismatch refuses to start; DB newer than binary refuses to start | T05 + T14 `test_checksum_refusal_exit_78`, `test_db_newer_exit_78` |
| hookd writes with a 250 ms timeout and exits 0 when the socket is absent, the payload malformed, or the write blocks | T08 `test_exit_zero_matrix`, `test_socket_absent`, `test_blocked_socket_deadline` |
| A real hand-launched claude session registers as attached, binding cwd to the innermost repo | T19 L1 (live) + T04 binding tests + T18 e2e |
| Hook events fold into `last_event_at`, `state`, `needs_you_reason`, tasks and subagents; no event row stored | T09 fold tests, T18 e2e; schema has no event table (T05 `test_fresh_apply` asserts the exact table set) |
| Absent fields degrade to null; the UI hides chips | T09 `test_wrong_types_become_none`; T16 chip rules; T19 L10 |
| Fleet renders workspace → session → subagent, ordered needs_you → running → stopped → idle, no polling | T04 ordering tests, T16 `test_no_polling_constructs`, T19 L7–L9 |
| SSE with monotonic seq and gap replay on `Last-Event-ID` | T14 hub tests, T15 `test_sse_http.py`, T18 restart test |
| Hook write volume measured and recorded | T18 `test_20_sessions_burst` → `build/perf/hook_volume.json` → §Verification Evidence; T19 L14 |
| `mypy --strict` passes and the suite is green | every task's implicit exit criteria; final `MYPY && PYTEST && PYTEST -m slow` at T18 |

## Glossary Additions (for the doc-syncer; terms used by this plan beyond spec §19)

| Term | Meaning |
|---|---|
| **unassigned workspace** | the seeded `wsp_unassigned` workspace, holding attached sessions whose `cwd` matches no registered repo or workspace root. Counted and shown (DV-13). |
| **at prompt** | an attached session in `stopped` with `ended_at IS NULL`. It has just started, resumed or cleared (DV-30), or its last turn ended, and the process may still be waiting for input. M1 cannot tell this apart from idle-waiting (DV-07). |
| **exited** | `stopped` with `ended_at` set: `SessionEnd` arrived, or the process probe saw the engine process die. This is M1's "idle". |
| **quiet** | a `running` session with no event for more than `liveness_window_s`. A display state, not a stored state (DV-09). |
| **profile** | an isolated Shepherd instance (state dir, runtime sockets, HTTP port, tmux socket). `default` is the user's instance; `test` and `qa` never share anything with it. |
| **gate** | sessiond's schema gate: closed until controld reports the expected schema version over the control socket (§7 migration rule 3). |

## Verification Evidence (appended by builders; each entry cites a command and its output)

This section is a slot for build-time evidence, not a planning placeholder. Entries required before M1 is called complete:
- T08: `build/perf/hookd_budget.json` p50/p99.
- T18: `build/perf/hook_volume.json` (hookd p50/p99, fold lag p50/p99, events/s, drops, RSS), plus the §18 decision-rule outcome.
- T19: live L1–L6, L13, L14 results; manual checklist L7–L12 sign-off; the DV-20 marker-key outcome.

## Revision 2 Disposition Log (fresh review, REVIEW_MODE fresh: 2 blocking, 12 advisory)

| Finding | Disposition | Where |
|---|---|---|
| B1 SessionStart → running | **fixed.** `SessionStart` (startup/resume/clear/absent/unknown) → at prompt (`stopped`, `ended_at` null); `compact` revives. Registration takes its initial state from the fold. Sweep also closes dead at-prompt sessions; the fleet horizon hides long-idle at-prompt sessions. | DV-30, A10, Behavior contract 1, T06, T09 (`test_session_start_idle_is_not_running`, `test_session_start_compact_revives`), T13 (`test_registration_initial_state_from_fold`), E43, R22, label rename "turn ended" → "at prompt" |
| B2 live lane vs autouse isolation | **fixed.** `tests/live/` exemption; `tests/live/conftest.py` keeps real HOME for `claude` auth and transcripts, isolates `SHEPHERD_HOME`/`XDG_RUNTIME_DIR`/`XDG_CONFIG_HOME`, and asserts the `~/.claude/settings.json` sha256 and `tmux -L shepherd ls` are unchanged; guard self-check test | PD-08, T02 (`real_state_fingerprint`, `isolated_env(keep_real_home)`), T19, R23 |
| A3 needs_you clearing unproven in TUI | **fixed.** `PostToolUseFailure`/`PermissionDenied` handled like `PostToolUse` for the pending match; T19 L3b (approve and deny/Esc) with a decision rule | Behavior contract 1, DV-07, T09, T19, E44 |
| A4 registering all §8 events | **fixed.** Register only the 14 consumed events; every group `matcher: "*"` (probe-accepted shape); no `watchPaths` events; L02 runs first on the exact generated file with a 4-step rule covering "no hooks fired" | DV-04, T11 (`PROBE_ACCEPTED_EVENTS`), T12, T19, R25 |
| A5 8 MiB tail read unspecified | **fixed.** `offset == 0` on a larger file seeks to size − max_bytes and skips the partial line uncounted | PD-11, T10 (`test_offset_zero_on_large_file_starts_at_tail_and_partial_line_not_counted`) |
| A6 event counts wrong | **fixed.** 12 observed; §8 has 24 names incl. `PermissionRequest`; `KNOWN_EVENTS` = 24; `CONSUMED_EVENTS` = 14 | DV-04, S4 T09, T12 |
| A7 empty ring and publisher locking | **fixed.** `k == current` → live even with an empty ring; `publish`/subscribe under one lock; two new tests | Behavior contract 2, T14, E45 |
| A8 late PermissionRequest sets reason | **fixed.** A late `PermissionRequest` has no effect at all; test added | Behavior contract 1, T09 (`test_late_permission_request_has_no_effect`) |
| A9 stalled controld blocks writer | **fixed.** Bounded outbound queue (1024) + sender thread + 2 s send timeout; `notifications_dropped` | Spec S2, T13 (`test_stalled_controld_does_not_block_writer`), E46, R24 |
| A10 baked runtime dir mismatch | **fixed** (two layers). Runtime dir is now always `<data_dir>/run`, env-independent. `hooks install` records installs; `hooks install`/`status` warn on mismatch or a missing socket; health exposes `runtime_dir` | DV-03, PD-07, T02, S2 token, S3 health, T15, T17, E47 |
| A11 mtime-based isolation criterion flaky | **fixed.** sha256 of `~/.claude/settings.json` + "`~/.shepherd` not created" | T02 exit criteria (`test_real_state_untouched_by_suite`) |
| A12 trust keys and side effect | **fixed.** Exact sequence (capture → Down → Enter → verify), abort if the dialog is not detected; `~/.claude.json` trust-entry side effect recorded and never edited | T19 |
| A13 Credentials without an M1 caller | **not removed; recorded.** The M1 planning request explicitly requires the credential-store seam with a Linux driver; small, stable, first consumer M4.5/M5 | DV-31 |
| A14 transcript-path check outside the seam | **fixed.** `EngineAdapter.accept_transcript_path`; `ScriptedEngine(transcript_root=…)`; contract case; T13 consumes only the seam | S4 T12, T12, T13 |

Reviewer caveat acknowledged: the reviewer could not re-run the SQLite, systemd and `claude --help` claims. They were executed by the planner on this host (§Codebase Reality Check), and T05/T03/T19 re-prove them in the build.

## Plan Self-Review (cross-phase contract drift)

- Every `Consumes` name was checked mechanically against the `Produces` of tasks earlier in the numbering (a script over this file). Drift found and fixed inline:
  (a) T09 consumed `HookEnvelope` before producing it; changed to consume `build_envelope`;
  (b) T19 referenced `running_stack`, which it does not use; removed;
  (c) T14 relied on an unregistered `serve_http` keyword; added to the Spec S4 `run_controld` signature;
  (d) T15's static allowlist tests needed T16's files; T15 now creates stub files at the fixed paths;
  (e) `Platform`/`current_platform` and the supervisors were re-homed from T02/T17 into T03 so `Platform` is defined after `Credentials` (T01).
  After the fixes: **Self-review: no cross-phase reference drift.** Revision 2 re-ran the mechanical check after the amendments listed in §Revision 2 Disposition Log: clean.
- Plan-review-gate iteration 1 (SPEC_GATE_FAIL) findings resolved in this same revision: added §Codebase Reality Check; SSH same-port browser access (A9); mypy ≥ 1.13 pin + registry notation note; edge cases E37–E42 with tests; assumption classes normalized; liveness notification contract made consistent (`LIVENESS_NOTIFY_INTERVAL_S`); PD-02/container writer ownership corrected; T18's vague follow-up replaced by conditional task T18b. Mechanical drift re-check after revision: clean.
- Remaining intentional cross-references: T16 consumes projection key names as JSON keys, not Python imports. T19 consumes the CLI entry point.
- Completeness gate:
  - (1) every task names tests;
  - (2) exact paths;
  - (3) exit criteria;
  - (4) explicit dependency IDs;
  - (5) drift named;
  - (6) Consumes/Produces verbatim, per the self-review fixes;
  - (7) validation level per task;
  - (8) risk matrix complete, with every high/high and high/med row mapped to a deterministic test;
  - (9) no TBDs;
  - (10) open decisions: none.
