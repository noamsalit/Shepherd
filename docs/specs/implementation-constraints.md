# Shepherd — implementation constraints

Facts found by live probes (2026-09-14, `claude` 2.1.270) that are **not**
architecture. They do not change a decision; they change how a task must be
built. Every one of them would otherwise be discovered by a builder at the
moment it breaks.

**This document is required reading for planning and for implementation.**
Architectural consequences of the same probes are decisions D42–D54 in
`orchestrator-platform.md`. Full evidence, with real captures, is in
`data-schemas.md`; paths below are relative to `docs/probes/2026-09-14-schemas/`.

| # | Area | Constraint | Evidence | Bites in |
|---|---|---|---|---|
| C1 | systemd | The user manager's `PATH` does not include `~/.local/bin`, so a unit calling `claude` exits 127. Set `Environment=PATH=…` or use an absolute path. | `linux-process-git/captures/systemd-xdg.txt` | M1 packaging |
| C2 | systemd | `Restart=always` alone gives up: with the default `StartLimitBurst=5` / `StartLimitIntervalUSec=10s` a fast-crashing unit ends `failed` after 5 restarts. Set a start-limit policy explicitly. | same | M1 packaging |
| C3 | systemd | With `XDG_RUNTIME_DIR` unset, `systemctl --user` fails with "Failed to connect to bus: No medium found". There is no automatic `/run/user/<uid>` fallback. All 24 captured hook environments did have it. | same, `linux-process-git/captures/proc-hooks.jsonl` | M1 |
| C4 | tmux | `send-keys` argv hazards: a payload starting with `-` needs `--`; the practical limit is ~16 KB; a single command string is run through `sh -c`. | `tmux-tui/` | M3 spawn, mailbox |
| C5 | tmux | `resize-window` forces `window-size=manual`, so a human attaching later sees a clipped view. `attach -r` delivers no keys. | `tmux-tui/` | M3 terminal |
| C6 | hooks | One malformed hook entry disables **every** hook in that settings file, and invalid JSON makes the whole file ignored. Install must validate after writing and back up first. | `hooks/live/R03_*`, `hooks/live/v*` | M1 install |
| C7 | hooks | The default hook timeout is 600 s. In `-p` runs that exit on an error the hook dispatched at shutdown can be killed, losing `StopFailure` and `SessionEnd`. | `hooks/live/v8-trace.txt` | M1 ingest |
| C8 | hooks | Field presence is not uniform. Only `session_id`, `transcript_path`, `cwd` and `hook_event_name` appear on every event; `permission_mode` is absent from ~15 event types; `effort` appeared only in sonnet runs, never with haiku; no payload carries a timestamp. | `hooks/live/_field-matrix.txt` | M1 ingest |
| C9 | ingest | `FileChanged` never fires for files the agent edits — only for declared watch paths. `repos_touched` needs another source, e.g. `PostToolUse` Edit/Write paths. | `hooks/live/S09_*`, `S13_*` | M1/M2 |
| C10 | ingest | `active_subagents` can go negative: a `SubagentStop` was observed with `agent_type: ""` and no matching start. Clamp and count the anomaly. | `hooks/live/` | M1 |
| C11 | ingest | `brief` from `lastPrompt` is polluted by system-injected prompts (background `<task-notification>` XML) and is a ~200-character truncated preview. Prefer the first real user entry and filter injected prompts. | `transcripts/`, `probe-env-provenance/run4-task-notification-brief.txt` | M1 |
| C12 | signals | `PreCompact{auto}` with no following `PostCompact` occurs on healthy turns, so it is not on its own evidence of `context_exhausted`. Bound it by time or by a following `Stop`. | `hooks/live/`, `tmux-tui/` | M2 |
| C13 | signals | Attached sessions give an exit **time** but never an exit **code**, so `crashed` versus `stopped` cannot always be separated. **Corrected 2026-09-21:** this row used to add *"and there is no `pid`/`procStart` column"* — `session.pid` and `session.proc_start` have existed since migration 001 and are written by the registry path and read by the liveness sweep. The missing exit code is the whole of the limitation. | `hooks/`, `linux-process-git/captures/proc-hooks.jsonl` | M1/M2 |
| C14 | lifecycle | `/resume` in the TUI ends the old `session_id` **in the same pane**. An owned session must rebind to the new id, not be marked stopped. | `tmux-tui/` | M3 |
| C15 | lifecycle | In an untrusted directory the trust dialog leaves a session neither `starting` nor `needs_you`, and no hooks fire until it is answered. A blind Enter selects "No, exit". | `tmux-tui/` | M3 spawn |
| C16 | fork | The fork's transcript persists; `--no-session-persistence` works only with `--print`; the fork inherits the user title; it carries history only after the last compact. Discarding an `ask()` fork is manual cleanup. | `transcripts/`, `hooks/live/S04_fork/` | M3 `ask()` |
| C17 | MCP | A running session does not pick up a user-scope MCP server added after it started, and allow rules are ignored in an untrusted worktree. Mount at spawn, and trust the worktree first. | `agent-sdk-mcp/captures/` | M3/M4 |
| C18 | titles | `/rename <title>` typed into the pty, and `--name` at spawn, make Claude Code write `custom-title` + `agent-name` itself. `ai-title` is the wrong channel. `can_set_title` may therefore be **True** for owned sessions — confirm at M3 (D29). | `tmux-tui/`, `transcripts/` | M3 |
| C19 | git | `remote get-url` fails with rc=2 when a repo has no remote (`/root/Shepherd` is one), and is ambiguous when several remotes exist. `vcs_remote` must tolerate both. | `linux-process-git/captures/git.txt` §A,§B,§G | M1 |
| C20 | UI | A subagent has no structured state field anywhere; its state must be derived from the transcript. | `transcripts/` | M1 fleet page |
| C21 | signals | `needs_you` reason values need care: `idle_prompt` flips an idle TUI to `needs_you` after 60 s, `elicitation_url_dialog` cannot arrive over stdio, and `agent_needs_input` was never observed. | `hooks/`, `tmux-tui/` | M2 |
| C22 | docs | Appendix A's `repo_id` values contradict D48's worktree binding, and its `workspace` row is built on `root_path`, which **D57 removes**. **Re-scoped 2026-09-21:** the macOS-paths half of this row is retired — D55 made macOS a supported host, so those paths are no longer wrong, only unrepresentative. Still unmet four milestones after its stated deadline; tracked in `docs/backlog/2026-09-21-projects-work-sources-and-ui.md`. | `orchestrator-platform.md` Appendix A | **overdue** (was: before M1) |
| C23 | docs | D12's reasoning says a mid-turn write "corrupts" a session. It does not: Claude Code absorbs the write and merges it silently. The mailbox decision still stands; only the rationale is wrong. | `tmux-tui/` | doc fix |
| C24 | master | A pending approval blocks the turn for up to 600 s, and `interrupt()` cancels it (`control_cancel_request` → `CancelledError`). The UI must show a withdrawn approval, per D54. | `agent-sdk-mcp/captures/` | M4 |
