<!-- Rendered by build_section.py from SECTION.tmpl.md. Every fenced example below is pulled
     byte-for-byte from a capture file under docs/probes/2026-09-14-schemas/hooks/; the only edit
     is trimming of long JSON strings, marked with "...". Do not hand-edit SECTION.md. -->

# Claude Code hooks (headless `-p`, plus one TUI run) — schemas observed 2026-09-14

**Scope of this section.** Claude Code 2.1.270 on Linux 6.8 (binary
`/root/.local/share/claude/versions/2.1.270`, sha256 `3a624a5a…3ef0`, recorded in
`docs/probes/2026-09-14-schemas/hooks/binary/version.txt`). Every live run records
`claude --version` in its `meta.json` and in every capture line (`_claude_version`).

**How the evidence was made.**

| Probe | What it is | Re-run |
|---|---|---|
| `extract_binary.py` | byte-search of the CLI binary for the event enum, the zod input/output schemas, the settings hooks schema, enums and runtime snippets → `binary/` | `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py` |
| `run_probes.py` | 50+ headless runs, each in a fresh `mktemp`-style dir under `/tmp`, hooks for all 33 events in `<tmpdir>/.claude/settings.json` (or `--settings`), `claude-haiku-4-5-20251001` unless noted → `live/<scenario>/` | `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py list` then `… run_probes.py S01 S02 …` (S02–S06, S14 reuse S01's session) |
| `interactive_probe.py` | one TUI session driven through a private `pty.fork()` (no tmux) for the events `-p` cannot reach → `live/I01_interactive/` | `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py` |
| `mock_api.py` | 127.0.0.1 stand-in for the Messages API (fake key, isolated `CLAUDE_CONFIG_DIR`) used only to provoke API-error classes → `live/S08_*`, `live/S22_*` | started by `run_probes.py S08` / `S22` |
| `capture_hook.sh` | the hook command: appends raw stdin + event name + UTC timestamp + `/proc` parent chain + claude pid, fork-free bash | — |
| `capture_env.py` | second hook on some events: env var names (values only for an allowlist, secrets `<redacted>`), stdin/tty facts, ancestry with cmdlines | — |
| `summarize.py` / `build_section.py` | field matrix (`live/_field-matrix.txt`, `live/_sequences.txt`) and this file | `python3 …/summarize.py && python3 …/build_section.py` |

**Safety record.** `~/.claude/settings.json` sha256 was identical before and after every run
(`meta.json` → `user_settings_sha256_*`). The cc10x user plugin was disabled in every throwaway
settings file and **did not register or fire** (debug: `Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled)`,
`live/*/debug-cc10x-lines.txt`; the only hook commands in any debug log are `capture_hook.sh`/`capture_env.py`).
`CLAUDE*`/`CLAUDECODE` vars inherited from the calling session were scrubbed before each launch;
`PATH`, `TERM`, `TMUX` were still inherited from it. Claude Code itself wrote trust/bookkeeping
entries to `~/.claude.json` and transcripts under `~/.claude/projects/-tmp-shp-hooks-*`.
No real user transcript was read for this section.

---

## Hook event names (the enum)

- **Produced by:** Claude Code 2.1.270 (settings validator `Im` and SDK schema `Sle`, identical lists)
- **Consumed by:** §6 `EngineAdapter.hook_events()` / capability matrix (spec line 550), §8 "Events subscribed" (lines 912–923); D9, D24; M1
- **Probe:** `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` → `binary/hook-events.json`, `binary/sdk-hook-events.json`; live cross-check `run_probes.py all` + `interactive_probe.py` → `live/_field-matrix.txt`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py && python3 docs/probes/2026-09-14-schemas/hooks/summarize.py`
- **Status:** partially verified — 31 of 33 names fired live 2026-09-14; TeammateIdle and WorktreeRemove from the binary only

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt` — the list as printed by `claude doctor`; same list extracted from the binary in `binary/hook-events.json`)

```text
<<RAW live/R03_config_unknown_event_name/doctor.txt|Valid events: [^\n]*|2000>>
```

| # | Event | Fired live? | Where |
|---|---|---|---|
| 1 | PreToolUse | yes (42) | S01, S09, S10, … |
| 2 | PostToolUse | yes (30) | S01, S17 (MCP tool), … |
| 3 | PostToolUseFailure | yes (2) | S01 (`false`, Read of missing file) |
| 4 | PostToolBatch | yes (40) | S01, S09, R01 |
| 5 | Notification | yes (3) | I01 (TUI) ×2, S17 (`-p`, MCP elicitation) |
| 6 | UserPromptSubmit | yes (57) | all runs with a prompt |
| 7 | UserPromptExpansion | yes (1) | S12 (custom slash command) |
| 8 | SessionStart | yes (55) | all runs |
| 9 | SessionEnd | yes (50) | most runs (see SessionEnd for the gaps) |
| 10 | Stop | yes (26) | S01, S10, S11, … |
| 11 | StopFailure | yes (23) | S07 (real API), S08 (mock API), R03, R04, S16 |
| 12 | SubagentStart | yes (2) | S01, S18 |
| 13 | SubagentStop | yes (4) | S01, S18, S05 (compaction), I01 |
| 14 | PreCompact | yes (1, `manual`) | S05 |
| 15 | PostCompact | yes (1, `manual`) | S05 |
| 16 | PreModelSwitch | yes (1) | S14 (`/model sonnet` in `-p`) |
| 17 | PostModelSwitch | yes (1) | S14 |
| 18 | PermissionRequest | yes (6) | S01, S09, S13, I01 |
| 19 | PermissionDenied | yes (1) | S20 (auto mode, classifier deny, sonnet) |
| 20 | Setup | yes (3) | S16 (`--init`, `--init-only`, `--maintenance`) |
| 21 | TeammateIdle | **no** | not attempted (agent teams) |
| 22 | TaskCreated | yes (3) | S01, S18 |
| 23 | TaskCompleted | yes (2) | S01, S18 |
| 24 | Elicitation | yes (1) | S17 |
| 25 | ElicitationResult | yes (1) | S17 |
| 26 | ConfigChange | yes (1) | S21 |
| 27 | WorktreeCreate | yes (1) | S15 (`--worktree`) |
| 28 | WorktreeRemove | **no** | not provoked (S15's create hook returned no path, so no worktree existed to remove) |
| 29 | InstructionsLoaded | yes (16) | every run with a `CLAUDE.md` |
| 30 | CwdChanged | yes (1) | S13 (`cd sub && pwd`) |
| 31 | FileChanged | yes (2) | S13, S21 (only for hook-declared `watchPaths`) |
| 32 | DirectoryAdded | yes (1) | I01 (`/add-dir`) |
| 33 | MessageDisplay | yes (51) | most runs |

**Variants and edge cases:**
- The settings validator and the SDK type list are the same 33 names in the same order (`binary/hook-events.json` vs `binary/sdk-hook-events.json`).
- An unknown event key in settings is ignored with a warning, not an error (see Hooks config schema).

**Spec alignment:**
- spec line 550 says `hooks | **rich** (32 events)`; reality is 33 event names in 2.1.270 (`binary/hook-events.json` `"count": 33`).
- spec lines 912–923 (events subscribed): every name exists. Not subscribed but relevant to Shepherd's columns: `PostToolBatch` (the only event emitted for a denied/hook-blocked tool call, see PostToolBatch), `InstructionsLoaded`, `ConfigChange`, `DirectoryAdded`, `Setup`, `UserPromptExpansion`, `WorktreeCreate/Remove`, `TeammateIdle`.

---

## Common input fields (every hook's stdin JSON)

- **Produced by:** Claude Code 2.1.270, builder `La()` (`binary/runtime-source-snippets.txt` line 3) and zod base schema `we` (`binary/hook-input-schemas.txt` line 2)
- **Consumed by:** §8 "Common fields on every hook event" (lines 929–931), §8 event→column table (lines 878–887), §7 `session.engine_session_id`/`cwd`/`last_event_at` (lines 652, 676); D22, D24, D37; M1
- **Probe:** `run_probes.py all` + `interactive_probe.py`, matrix by `build_section.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S10 && python3 docs/probes/2026-09-14-schemas/hooks/build_section.py`
- **Status:** verified live 2026-09-14 (429 captures, 53 runs)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl` — a main-thread and a subagent PreToolUse; `live/S10_effort_sonnet/events.jsonl` for `effort`)

```json
<<EX live/S01_startup_tools/events.jsonl|PreToolUse|1||120>>
<<EX live/S01_startup_tools/events.jsonl|PreToolUse|1|agent_type=general-purpose|120>>
<<EX live/S10_effort_sonnet/events.jsonl|PreToolUse|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | string (UUID) | always | e.g. `8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6` | Changes on `/clear` (new id on `SessionStart{source:clear}`) and on `--fork-session`; kept by `--resume`. With `--continue`, the first `InstructionsLoaded` carried a provisional id (`437540c8…`) different from the resumed id on `SessionStart` (`8bbcceab…`) (`live/S03_continue/events.jsonl`) |
| `transcript_path` | string | always | `/root/.claude/projects/<cwd with every non-alphanumeric char → "-">/<session_id>.jsonl`; under `$CLAUDE_CONFIG_DIR/projects/…` when that is set | Use verbatim; `_` in cwd becomes `-` (`-tmp-shp-hooks-slash--ul-amd7` for `/tmp/shp-hooks-slash-_ul_amd7`) |
| `cwd` | string | always | session cwd; after a Bash `cd` the value follows the new dir (`CwdChanged` example) | |
| `hook_event_name` | string | always | the 33 names | |
| `prompt_id` | string (UUID) | sometimes | see matrix | Absent before the first prompt of the process (all `SessionStart{startup/resume/fork/clear}`, `InstructionsLoaded`, `Setup`, `WorktreeCreate`); present on `SessionStart{compact}` |
| `permission_mode` | string | sometimes | `default`, `acceptEdits`, `dontAsk`, `plan`, `auto` | Only on tool/turn events (see matrix). `bypassPermissions` not observable here: refused as root (`live/S09_perm_bypass_echo/stderr.txt`). `--permission-mode auto` on haiku silently ran as `default` (`live/S09_perm_auto_mode_delete_outside`) |
| `effort` | object `{level}` | sometimes | `{"level":"low"}` (sonnet `--effort low`), `{"level":"high"}` (sonnet default; also nonexistent model) | Absent on every haiku event; never on SessionStart/SessionEnd/UserPromptSubmit/MessageDisplay/Notification/Task*/Subagent*; present on tool events, Stop, PermissionDenied and StopFailure when the model supports effort |
| `agent_id` | string | sometimes | `a7154de3fc719065c` | Only on events fired inside a subagent (and on Subagent* events) |
| `agent_type` | string | sometimes | `general-purpose`, `shpprobe` (custom `--agents`), `""` | `""` on SubagentStop of internal subagents (compaction, post-turn) |
| `scratchpad_dir` | string | sometimes | `/tmp/claude-0/<project>/<session_id>/scratchpad` | **Not in the zod schema** but emitted by `La()`; seen only in the TUI run (I01) |
| any timestamp | — | **never** | — | No payload key is a time; `seconds_since_last_response` (SessionStart resume/fork) is the only time-like field. Receipt time must be stamped by the receiver |

Common-field presence per event, over all retained captures (`live/*/events.jsonl`):

<<COMMONMATRIX>>

**Variants and edge cases:**
- Claude Code writes the JSON followed by one `\n` and then closes stdin (429/429 captures have `_raw_trailing_newline: true`).
- Field order is stable: common fields first (`session_id, transcript_path, cwd, [scratchpad_dir], [prompt_id], [permission_mode], [agent_id, agent_type], [effort]`), then `hook_event_name`, then event fields.
- `effort` sits **before** `hook_event_name` in the byte stream; do not parse positionally.

**Spec alignment:**
- spec lines 929–931 say "Common fields on every hook event: `session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode`, `effort.level`, `hook_event_name`"; reality is only `session_id`, `transcript_path`, `cwd`, `hook_event_name` are on every event. `prompt_id` is missing on 54/55 SessionStart, all InstructionsLoaded/Setup/WorktreeCreate; `permission_mode` is missing on SessionStart, SessionEnd, StopFailure, MessageDisplay, Notification, TaskCreated/TaskCompleted, SubagentStart, Pre/PostCompact, Pre/PostModelSwitch, InstructionsLoaded, ConfigChange, CwdChanged, FileChanged, DirectoryAdded, Elicitation*; `effort` is absent for haiku and on lifecycle events (matrix above; `live/_field-matrix.txt`).
- spec line 881 (`SessionStart` registers `engine_session_id`) is aligned, but the id is not stable for the life of a terminal: `/clear` ends it (`SessionEnd{reason:clear}`) and starts a new id (`live/S06_clear/events.jsonl`, `live/I01_interactive/events.jsonl`). spec line 652 ("nothing may key off it") is consistent with this.
- spec line 880 (`last_event_at` from any event) is aligned only if stamped on receipt: no event carries a timestamp.

---

## SessionStart

- **Produced by:** Claude Code 2.1.270 (zod `Ple`, `binary/hook-input-schemas.txt` line 24)
- **Consumed by:** §8 line 881 (register attached session, `cwd`→repo), line 922; §9 `ask()` fork (line 1205); D1, D13, D22; M1, M3
- **Probe:** `run_probes.py S01 S02 S03 S04 S05 S06` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S02 S03 S04 S05 S06`
- **Status:** verified live 2026-09-14 (all 5 `source` values)

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S02_resume/events.jsonl`, `live/S04_fork/events.jsonl`, `live/S05_compact/events.jsonl`, `live/S06_clear/events.jsonl`, `live/I01_interactive/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|SessionStart|1||140>>
<<EX live/S02_resume/events.jsonl|SessionStart|1||140>>
<<EX live/S04_fork/events.jsonl|SessionStart|1||140>>
<<EX live/S05_compact/events.jsonl|SessionStart|2||140>>
<<EX live/S06_clear/events.jsonl|SessionStart|2||140>>
<<EX live/I01_interactive/events.jsonl|SessionStart|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `source` | enum | always | `startup` (45), `resume` (6), `clear` (2), `fork` (1), `compact` (1) | binary enum `["startup","resume","clear","compact","fork"]`; `--continue` reports `resume` |
| `model` | string | sometimes (2/55) | `claude-haiku-4-5-20251001` | seen on TUI startup and on `compact` |
| `seconds_since_last_response` | int | sometimes (7/55) | `10`, `3` | only `resume`/`fork` |
| `context_tokens` | int | sometimes (7/55) | `25613` | only `resume`/`fork` |
| `prompt_cache_likely_expired` | bool | sometimes (7/55) | `false`, `true` | only `resume`/`fork` |
| `estimated_cache_write_usd` | number | sometimes (7/55) | `0.0512` | only `resume`/`fork` |
| `agent_type` | string | never observed | — | schema: present with `--agent` |
| `session_title` | string | never observed | — | schema only |

**Variants and edge cases:**
- Order on resume: `InstructionsLoaded` fires **before** `SessionStart` (S02–S06).
- `/compact`: `PreCompact` → internal `SubagentStop{agent_type:""}` → `SessionStart{source:compact}` (same session id, carries `prompt_id`) → `PostCompact` (`live/S05_compact/events.jsonl`).
- `/clear` in `-p` and TUI: `SessionEnd{reason:clear}` (old id) → `SessionStart{source:clear}` (new id, no `prompt_id`).
- `-p` in a never-trusted dir still runs hooks (trust dialog skipped in `-p`); in the TUI, `SessionStart` fired only after the trust dialog was accepted (`live/I01_interactive/steps.txt`).
- The matcher value is `source` (`hook_name` `SessionStart:startup` in `live/S07_bad_model/stdout.jsonl`).

**Spec alignment:**
- spec line 1205 says "`SessionStart` hook's `start_reason` enum includes `fork`"; reality: the field is `source`; `fork` verified live with `--resume <id> --fork-session` (`live/S04_fork/events.jsonl`).
- spec line 881: aligned (`session_id`, `cwd` always present).

---

## SessionEnd

- **Produced by:** Claude Code 2.1.270 (zod `ice`, reason enum `rce`, `binary/hook-input-schemas.txt`)
- **Consumed by:** §8 lines 887, 918 (stop trigger), lines 967–970 (`user_exited`, `cleared`, `logged_out`, `resumed_elsewhere`); D24; M1, M2
- **Probe:** `run_probes.py S01 S06 S07 S08 S11 R04` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S06 S07 S11 && python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — `other`, `clear`, `prompt_input_exit` live; `logout`, `resume` binary only

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S06_clear/events.jsonl`, `live/I01_interactive/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|SessionEnd|1||140>>
<<EX live/S06_clear/events.jsonl|SessionEnd|1||140>>
<<EX live/I01_interactive/events.jsonl|SessionEnd|1|reason=prompt_input_exit|140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `reason` | enum | always | `other` (47), `clear` (2), `prompt_input_exit` (1) | binary enum `["clear","resume","logout","prompt_input_exit","other"]`. Every `-p` exit, success or error, is `other` |

**Variants and edge cases:**
- **`SessionEnd` is not guaranteed in `-p`.** It was never dispatched (no SessionEnd line in the debug log) in `S07_bad_model`, `S08_mock_http429`, `R04_settings_flag` (StopFailure exits) and `S11_background_task` (`live/S11_background_task/debug-extras.txt`: `print wind-down: killing background shell bx4s43qvk ("Background sleep and echo command") after 5000ms grace`, then exit). It did arrive in the other 20 StopFailure runs. `S15_worktree` failed before any session existed. Treat process exit as the stop signal of record.
- `logout` not attempted: `/logout` would sign the user out of the real account on this machine. `resume` (switching sessions via `/resume` inside a TUI) not attempted.
- `prompt_id` present 48/50 (absent when no prompt was ever submitted in that session id, e.g. the post-`/clear` id in `-p`).

**Spec alignment:**
- spec lines 967–970 say `SessionEnd.end_reason = …`; reality: the field is `reason` (`live/S06_clear/events.jsonl`). Values `prompt_input_exit`, `clear` verified; `logout`, `resume` exist in the binary enum.
- spec line 887 (`SessionEnd` triggers classification) needs a fallback: SessionEnd was missing in 4 `-p` runs that had a session (above).

---

## UserPromptSubmit

- **Produced by:** Claude Code 2.1.270 (zod `kle`)
- **Consumed by:** §8 line 882 (`brief`), line 922; §7 `brief` (line 664); M1
- **Probe:** `run_probes.py S01 S18 R01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S18`
- **Status:** partially verified — payload verified live 2026-09-14; optional `source` and `session_title` never observed

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S18_agents_tasks/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|UserPromptSubmit|1||120>>
<<EX live/S18_agents_tasks/events.jsonl|UserPromptSubmit|2||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `prompt` | string | always | user text; `/compact` etc. do not fire it; system-injected `<task-notification>…` | |
| `source` | enum | never observed | — | binary: `["user","sdk","system","loop_wakeup","schedule_wakeup","poll_event"]`, optional; absent even on the injected `<task-notification>` prompt |
| `session_title` | string | never observed | — | schema only |

**Variants and edge cases:**
- After a background subagent finishes, Claude Code injects a `<task-notification>` prompt that fires `UserPromptSubmit` with a new `prompt_id` and a second `Stop` (`live/S18_agents_tasks/events.jsonl`).
- Exit-0 stdout of a UserPromptSubmit hook is added to the model context (R01: model quoted `PAPAYA` "from the `UserPromptSubmit hook success` message", `live/R01_exit_codes/stdout.jsonl`).

**Spec alignment:**
- spec line 882 (`brief` from `UserPromptSubmit`): partially aligned — the latest `prompt` can be a system `<task-notification>` block with no `source` to tell it apart (`live/S18_agents_tasks/events.jsonl`); only the first prompt per session is a safe `brief`.

---

## UserPromptExpansion

- **Produced by:** Claude Code 2.1.270 (zod `Ole`)
- **Consumed by:** not consumed by the spec today; relevant to §8 line 882 (`brief` for slash-command sessions)
- **Probe:** `run_probes.py S12`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S12`
- **Status:** partially verified — `expansion_type:"slash_command"` live; `mcp_prompt` binary only

**Real example** (trimmed; full capture: `live/S12_slash_command/events.jsonl`)

```json
<<EX live/S12_slash_command/events.jsonl|UserPromptExpansion|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `expansion_type` | enum | always | `slash_command` | binary: `slash_command`, `mcp_prompt` |
| `command_name` | string | always | `shpecho` | |
| `command_args` | string | always | `EXPANDED` | |
| `command_source` | string | always | `projectSettings` | optional in schema |
| `prompt` | string | always | `/shpecho EXPANDED` | the unexpanded input |

**Variants and edge cases:** fires before `UserPromptSubmit` for the same `prompt_id`.

**Spec alignment:** aligned (not referenced).

---

## PreToolUse

- **Produced by:** Claude Code 2.1.270 (zod `ble`)
- **Consumed by:** §8 line 916 (liveness); §8 heuristics 2 and 4 (tool ledger); M1, M2
- **Probe:** `run_probes.py S01 S09 S17 R01 R02`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S09_perm_deny_rule_bash_rm/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|PreToolUse|9||120>>
<<EX live/S09_perm_deny_rule_bash_rm/events.jsonl|PreToolUse|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_name` | string | always | `Bash`, `Write`, `Read`, `ToolSearch`, `TaskCreate`, `TaskUpdate`, `Agent`, `mcp__shpelicit__ask_name` | MCP tools as `mcp__<server>__<tool>` |
| `tool_input` | object | always | tool-specific, e.g. `{"command":…,"description":…}` | |
| `tool_use_id` | string | always | `toolu_…` | joins to PostToolUse / PostToolUseFailure / PermissionDenied / PostToolBatch |

**Variants and edge cases:**
- Fires **before** the permission decision: also for calls then refused by a deny rule (`--disallowedTools Bash(rm:*)`) or by `dontAsk` (S09).
- Matcher is the tool name (`hook_name` `PreToolUse:Bash`).

**Spec alignment:** aligned.

---

## PermissionRequest

- **Produced by:** Claude Code 2.1.270 (zod `Tle`)
- **Consumed by:** §8 line 883 and line 937 (`needs_you`), line 917; §7 `needs_you_reason` (line 677); §11 line 1684 (Needs-You rail); M1, M4
- **Probe:** `run_probes.py S01 S09` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S09 && python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/I01_interactive/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|PermissionRequest|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_name` | string | always | `Write` (4), `Bash` (2) | |
| `tool_input` | object | always | | |
| `permission_suggestions` | array | always | `{"type":"setMode","mode":"acceptEdits","destination":"session"}`, `{"type":"addDirectories","directories":[…],"destination":"session"}` | optional in schema |
| `tool_use_id` | — | **never** | — | not in schema; join to PreToolUse by order/`tool_input` |

**Variants and edge cases:**
- `-p` default mode: fires, then the call is auto-refused with no further permission event; the only trace is `PostToolBatch.tool_calls[].tool_response` = `"Claude requested permissions to write to …, but you haven't granted it yet."` (`live/S09_perm_default_write_outside/events.jsonl`). Same with `--permission-prompts none`.
- `dontAsk` mode and deny rules: **no** PermissionRequest (S09).
- TUI: `PermissionRequest` at 15:38:05.762, `Notification{permission_prompt}` 6.0 s later at 15:38:11.797; after the user rejected with Esc, **no** Stop, PostToolUseFailure or PermissionDenied followed — nothing until the next prompt (`live/I01_interactive/events.jsonl`, `steps.txt`).

**Spec alignment:**
- spec line 937 ("or an unresolved `PermissionRequest`"): there is no resolution event for a human rejection in the TUI (I01) and none for the automatic refusal in `-p` (S09); "unresolved" can only be cleared by a later event from the same session (next `UserPromptSubmit`/`PreToolUse`/`Stop`).

---

## PermissionDenied

- **Produced by:** Claude Code 2.1.270 (zod `Cle`; dispatched only when `decisionReason.type==="classifier" && classifier==="auto-mode"`, `binary/runtime-source-snippets.txt` line 22)
- **Consumed by:** §8 line 917 (needs-you); M1
- **Probe:** `run_probes.py S09 S19 S20`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S20`
- **Status:** verified live 2026-09-14 (auto mode on sonnet; model-dependent)

**Real example** (trimmed; full capture: `live/S20_perm_auto_deny/events.jsonl`)

```json
<<EX live/S20_perm_auto_deny/events.jsonl|PermissionDenied|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_name` | string | always | `Bash` | |
| `tool_input` | object | always | | |
| `tool_use_id` | string | always | | |
| `reason` | string | always | `[Data Exfiltration]` | classifier category |

**Variants and edge cases:**
- Not emitted for: `dontAsk` refusal, `--disallowedTools` deny rule, `-p` auto-refusal of a PermissionRequest, `--permission-prompts none`, a TUI Esc rejection (S09, I01).
- `--permission-mode auto` on haiku is silently downgraded (`live/S09_perm_auto_mode_delete_outside/debug-extras.txt`: `auto mode disabled: model claude-haiku-4-5-20251001 does not support auto mode`; payload `permission_mode:"default"`).
- The auto classifier **allowed** `rm -rf <tmp dir outside cwd>` (S19, dir deleted) and `curl … | sudo sh` to a `.invalid` host (S20, ran and failed on DNS).

**Spec alignment:**
- spec line 917 lists PermissionDenied as a needs-you source; reality: it only fires for auto-mode classifier denials, so in `default`/`acceptEdits`/`dontAsk` sessions it never fires.

---

## PostToolUse

- **Produced by:** Claude Code 2.1.270 (zod `yle`)
- **Consumed by:** §8 line 916 (liveness), heuristics 2 and 4; §18 hook write-volume risk (line 2327); M1, M2
- **Probe:** `run_probes.py S01 S11 S17`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S17`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S17_elicitation/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|PostToolUse|1||120>>
<<EX live/S17_elicitation/events.jsonl|PostToolUse|2||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_name` / `tool_input` / `tool_use_id` | | always | as PreToolUse | |
| `tool_response` | object or array | always | Bash `{stdout,stderr,interrupted,isImage,noOutputExpected[,backgroundTaskId]}`; MCP `[{"type":"text",…}]` | type varies by tool |
| `duration_ms` | int | always | `49`, `44` | optional in schema; excludes permission-prompt and hook time (schema description) |

**Variants and edge cases:** a background Bash call returns immediately with `tool_response.backgroundTaskId` (`live/S11_background_task/events.jsonl`).

**Spec alignment:** aligned.

---

## PostToolUseFailure

- **Produced by:** Claude Code 2.1.270 (zod `Ale`)
- **Consumed by:** §8 line 916, heuristic 3 "failure tail" (last 3 signals `PostToolUseFailure` on the same tool); M2
- **Probe:** `run_probes.py S01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|PostToolUseFailure|1||120>>
<<EX live/S01_startup_tools/events.jsonl|PostToolUseFailure|2||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `error` | string | always | `Exit code 1`, `File does not exist. Note: …` | free text |
| `is_interrupt` | bool | always | `false` | optional in schema |
| `duration_ms` | int | always | `10`, `6` | optional in schema |
| `tool_name` / `tool_input` / `tool_use_id` | | always | | |

**Variants and edge cases:** a tool call refused by permissions (S09) or blocked by a PreToolUse exit 2 (R01) produces **no** PostToolUseFailure; only `PostToolBatch` records it.

**Spec alignment:** aligned for real tool errors; heuristic 3 will not see permission/hook refusals (they surface only in PostToolBatch).

---

## PostToolBatch

- **Produced by:** Claude Code 2.1.270 (zod `Rle`/`vle`)
- **Consumed by:** not subscribed in §8 (lines 912–923); relevant to heuristics 3 and 4
- **Probe:** `run_probes.py S01 S09 R01`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S09 R01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S09_perm_dontAsk_write_outside/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|PostToolBatch|1||120>>
<<EX live/S09_perm_dontAsk_write_outside/events.jsonl|PostToolBatch|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tool_calls` | array of `{tool_name, tool_input, tool_use_id, tool_response?}` | always | one entry per call in the batch | `tool_response` here is a **string** (the text the model saw), not the structured PostToolUse object |

**Variants and edge cases:** the only hook event that records permission refusals and hook blocks (`tool_response` = refusal text).

**Spec alignment:** not referenced by the spec; omission matters for heuristic 3 (see PostToolUseFailure).

---

## Stop

- **Produced by:** Claude Code 2.1.270 (zod `xle`, background task `Xz`, cron `Jz`)
- **Consumed by:** §8 lines 887, 918 (classification), lines 962–963, 976, 1025 (`Stop.stop_reason`), heuristic 2 (`last_assistant_message`); §9 mailbox delivery trigger (line 1181); Appendix A line 2531; D12, D24, D34; M2, M3
- **Probe:** `run_probes.py S01 S10 S11 S18` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S10 S11 S18`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S11_background_task/events.jsonl`, `live/S10_effort_sonnet/events.jsonl`)

```json
<<EX live/S11_background_task/events.jsonl|Stop|1||120>>
<<EX live/S10_effort_sonnet/events.jsonl|Stop|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `stop_hook_active` | bool | always | `false` | |
| `last_assistant_message` | string | always | final assistant text | optional in schema |
| `background_tasks` | array of `{id,type,status,description,command?,agent_type?,server?,tool?,name?}` | always | `[]`; `[{"id":"bx4s43qvk","type":"shell","status":"running",…}]` | |
| `session_crons` | array of `{id,schedule,recurring,prompt}` | always | `[]` | |
| `stop_reason` | — | **never** | — | not in the schema and never observed |

**Variants and edge cases:**
- Fires once per turn, not once per session: S18 had two (`Stop`, then an injected `<task-notification>` `UserPromptSubmit`, then `Stop`).
- In `-p`, a turn that ends with a running background shell gets `Stop` and then the process kills the shell 5 s later with no `SessionEnd` (S11).
- A human rejection of a permission prompt in the TUI ends the turn with **no** Stop (I01).
- Hitting the output cap does not produce `Stop`; it produces `StopFailure{error:max_output_tokens}` (S08_mock_max_tokens).

**Spec alignment:**
- spec lines 962, 963, 976, 1025 and 2531 key rules on `Stop.stop_reason` (`max_tokens`, `tool_use`, `end_turn`); reality: `Stop` has no `stop_reason` field (26 captures; binary schema `xle`). Truncation arrives as `StopFailure.error = max_output_tokens`; `end_turn` vs `tool_use` must come from the transcript.
- spec line 1181 (mailbox delivers on `Stop`): aligned for normal turns; no Stop after a TUI permission rejection (I01).

---

## StopFailure

- **Produced by:** Claude Code 2.1.270 (zod `Ile`, error enum `o_`, dispatcher `pet()` in `binary/runtime-source-snippets.txt` line 18)
- **Consumed by:** §8 lines 887, 918, 951–971 (mechanical `stop_reason` table); §18 line 2330; D21, D24; M1, M2
- **Probe:** `run_probes.py S07 S08`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S07 S08`
- **Status:** verified live 2026-09-14 (model_not_found against the real API; other classes via the local mock API, marked)

**Real example** (trimmed; full captures: `live/S07_bad_model/events.jsonl` [real API]; `live/S08_mock_prompt_too_long/events.jsonl`, `live/S08_mock_http529/events.jsonl` [mock API])

```json
<<EX live/S07_bad_model/events.jsonl|StopFailure|1||120>>
<<EX live/S08_mock_prompt_too_long/events.jsonl|StopFailure|1||110>>
<<EX live/S08_mock_http529/events.jsonl|StopFailure|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `error` | enum | always | `model_not_found`, `authentication_failed`, `billing_error`, `rate_limit`, `server_error`, `invalid_request`, `max_output_tokens`, `unknown` | see Enumerations for the full list and the stimulus→value map |
| `error_details` | string | sometimes (1/23) | raw API error body (`prompt_too_long`) | |
| `last_assistant_message` | string | always | the user-facing error text | |
| `permission_mode` | — | never | — | `pet()` passes `undefined` |
| `effort` | object | sometimes (13/23) | `{"level":"high"}` | present when the (claimed) model supports effort |

**Variants and edge cases:**
- **Delivery race in `-p`.** StopFailure is dispatched while the CLI is shutting down and hook processes still running at exit are killed: in S07 the Python `capture_env.py` hook `completed with status 1` and wrote nothing, while the fork-free bash capture `completed with status 0` (`live/S07_bad_model/debug-hooklines.txt`).
- Retries: the real 404 was tried streaming, then non-streaming, before StopFailure (two `API error (attempt 1/11)` lines in `live/S07_bad_model/debug-extras.txt`); mock runs set `CLAUDE_CODE_MAX_RETRIES=0`.
- The matcher value is `error` (`StopFailure:model_not_found` in debug).

**Spec alignment:**
- spec lines 951, 956, 971 say `StopFailure` carries `error_type`; reality: the field is `error` (`live/S07_bad_model/events.jsonl`).
- spec line 956 maps `overloaded` → `rate_limited`; reality: a 529 produced `error:"server_error"` ("The API is at capacity"/"529 Overloaded", `live/S08_mock_http529`) and the binary contains 0 assignments of `error:"overloaded"` (`binary/stopfailure-error-assignments.txt`). Would classify 529 as `server_error`, not `rate_limited`.
- spec line 960 maps `invalid_request` → `bad_request`; reality: a plain 400 produced `error:"unknown"` (`live/S08_mock_http400`); only special 400s map to `invalid_request` (prompt too long) or `billing_error` (credit balance).
- spec lines 958–960 omit `verification_required` and `cloud_credential_error` (binary enum `o_`).
- spec line 962 `= max_output_tokens`: aligned (`live/S08_mock_max_tokens`, mock).
- spec line 2330 ("documented, not observed"): now observed.

---

## SubagentStart

- **Produced by:** Claude Code 2.1.270 (zod `Dle`)
- **Consumed by:** §8 line 885 (`active_subagents`), line 919; §7 line 679; M1
- **Probe:** `run_probes.py S01 S18`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S18`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|SubagentStart|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `agent_id` | string | always | `a7154de3fc719065c` | also the id inside `<task-notification>` |
| `agent_type` | string | always | `general-purpose`, `shpprobe` | |
| `permission_mode` | — | never | — | |

**Variants and edge cases:** for an async-launched Agent call (`tool_response.status:"async_launched"`, S18) `SubagentStart` (15:23:44.780) and `PostToolUse{Agent}` (15:23:44.782) are 2 ms apart and their capture lines landed in the opposite order; do not rely on arrival order. The subagent's result later arrives as an injected `<task-notification>` prompt (see UserPromptSubmit).

**Spec alignment:** aligned in shape; see SubagentStop for the counter problem.

---

## SubagentStop

- **Produced by:** Claude Code 2.1.270 (zod `Nle`)
- **Consumed by:** §8 line 885 (`active_subagents`), line 919; §7 line 679; M1
- **Probe:** `run_probes.py S01 S05 S18` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S05`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/events.jsonl`, `live/S05_compact/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|SubagentStop|1||120>>
<<EX live/S05_compact/events.jsonl|SubagentStop|1||120>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `agent_id` | string | always | | |
| `agent_type` | string | always | `general-purpose`, `shpprobe`, `""` (2/4) | `""` = internal subagent |
| `agent_transcript_path` | string | always | `…/<session_id>/subagents/agent-<agent_id>.jsonl` | |
| `last_assistant_message` | string | sometimes (3/4) | | |
| `stop_hook_active` / `background_tasks` / `session_crons` | | always | as Stop | |

**Variants and edge cases:** internal subagents emit **SubagentStop without SubagentStart**: compaction (`live/S05_compact`, `agent_type:""`, `last_assistant_message` = the compaction analysis) and a post-turn agent 7.5 s after Stop in the TUI (`live/I01_interactive`, 15:38:46.760).

**Spec alignment:**
- spec line 885 (`active_subagents` from `SubagentStart`/`SubagentStop`): a naive +1/−1 counter goes negative — 2 of 4 SubagentStop captures had no matching SubagentStart (`live/S05_compact/events.jsonl`, `live/I01_interactive/events.jsonl`). Count by `agent_id` pairing and ignore `agent_type:""`.

---

## TaskCreated / TaskCompleted

- **Produced by:** Claude Code 2.1.270 (zod `Gle` / `Vle`)
- **Consumed by:** §8 line 884 and heuristic 1 (open task ledger); §7 `tasks_done`/`tasks_total` (line 678); §18 line 2330; M1, M2
- **Probe:** `run_probes.py S01 S18`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S18`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|TaskCreated|1||140>>
<<EX live/S01_startup_tools/events.jsonl|TaskCompleted|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `task_id` | string | always | `"1"`, `"2"` | small per-session counter, not a UUID |
| `task_subject` | string | always | `probe task`, `alpha`, `beta` | |
| `task_description` | string | always | | optional in schema |
| `teammate_name` / `team_name` | string | never observed | — | agent teams only |
| `permission_mode` | — | never | — | |

**Variants and edge cases:**
- `TaskCompleted` fires inside the `TaskUpdate{status:"completed"}` tool call, between its PreToolUse and PostToolUse.
- S18 created 2, completed 1, then stopped: the ledger shows 1 open task at `Stop` (heuristic 1 input available).
- Task deletion/other statuses not probed.

**Spec alignment:** aligned (spec line 884; line 2330 "documented, not observed" is now observed).

---

## Notification

- **Produced by:** Claude Code 2.1.270 (zod `wle`; dispatcher `ZT()`, matcher = `notification_type`, `binary/enums.json`)
- **Consumed by:** §8 line 883, 917, 937, 945 (`needs_you`), line 957 (`quota_paused`); §7 `needs_you_reason` (line 677); §18 line 2330; M1, M2
- **Probe:** `interactive_probe.py` (TUI) + `run_probes.py S17` (`-p`). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — `permission_prompt`, `idle_prompt` (TUI) and `elicitation_response` (`-p`) live; other types binary only

**Real example** (trimmed; full captures: `live/I01_interactive/events.jsonl`, `live/S17_elicitation/events.jsonl`)

```json
<<EX live/I01_interactive/events.jsonl|Notification|1||140>>
<<EX live/I01_interactive/events.jsonl|Notification|2||140>>
<<EX live/S17_elicitation/events.jsonl|Notification|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message` | string | always | `Claude needs your permission`, `Claude is waiting for your input`, `Elicitation response for server "shpelicit": cancel` | |
| `notification_type` | string | always | `permission_prompt`, `idle_prompt`, `elicitation_response` | schema types it as free string |
| `title` | string | never observed | — | optional |
| `permission_mode` | — | never | — | |

**Variants and edge cases:**
- `permission_prompt` arrived 6.0 s after `PermissionRequest` (I01).
- `idle_prompt` arrived 60.0 s after the turn's `Stop` (15:38:39.241 → 15:39:39.272) with no keystroke in between. The binary's idle timer (class `wee`) only sends it when no user interaction happened after the last completed query and no dialog is on screen; sender in `binary/runtime-source-snippets.txt` line 25.
- `-p` does emit Notification for MCP elicitation (`elicitation_response`), but never `permission_prompt`/`idle_prompt` (no prompt UI).

**Spec alignment:**
- spec line 937 value set: `permission_prompt`, `idle_prompt` verified; `agent_needs_input`, `elicitation_dialog`, `elicitation_url_dialog` exist in the binary list `VAr` (not observed). Unlisted real values: `elicitation_response` (observed), `auth_success`, `elicitation_complete`, `agent_completed`, `worker_permission_prompt`, `push_notification`, `computer_use_enter`, `computer_use_exit`.
- spec line 957 (`quota_auto_resume_fired|stale|disabled`): present in `VAr`, not provoked (needs a real quota exhaustion).
- spec line 883 (Notification → `needs_you`): headless (`owned` `-p`) sessions never emit `permission_prompt`/`idle_prompt`; for them `needs_you` can only come from `PermissionRequest`.

---

## MessageDisplay

- **Produced by:** Claude Code 2.1.270 (zod `nce`; dispatched with `forceSyncExecution:!0`)
- **Consumed by:** §8 line 916 (liveness); M1
- **Probe:** `run_probes.py S01` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S01_startup_tools/events.jsonl`)

```json
<<EX live/S01_startup_tools/events.jsonl|MessageDisplay|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `turn_id` | string (UUID) | always | | |
| `message_id` | string (UUID) | always | | "Not the API msg_… id" (schema) |
| `index` | int | always | `0` in all retained captures | schema: chunk index within one `message_id`; multi-chunk flushes not retained |
| `final` | bool | always | `true` in all retained captures | |
| `delta` | string | always | the displayed text chunk | |
| `permission_mode` | — | never | — | |

**Variants and edge cases:** fired even for synthetic error messages (the model-not-found text in S07); one MessageDisplay per displayed assistant message in `-p`.

**Spec alignment:** aligned (liveness only). Volume note for §18 line 2327: MessageDisplay is synchronous (`forceSyncExecution`), so a slow hook delays display.

---

## PreCompact / PostCompact

- **Produced by:** Claude Code 2.1.270 (zod `Lle` / `Ule`)
- **Consumed by:** §8 line 921; `context_exhausted` rule (line 966); M2
- **Probe:** `run_probes.py S05` (manual) and `S22` (auto attempt). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S05 S22`
- **Status:** partially verified — `trigger:"manual"` live; `trigger:"auto"` binary only

**Real example** (trimmed; full capture: `live/S05_compact/events.jsonl`)

```json
<<EX live/S05_compact/events.jsonl|PreCompact|1||140>>
<<EX live/S05_compact/events.jsonl|PostCompact|1||110>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `trigger` | enum | always | `manual` | binary `["manual","auto"]` |
| `custom_instructions` | string or null | always (Pre) | `null` | |
| `compact_summary` | string | always (Post) | the summary text | |
| `permission_mode` | — | never | — | |

**Variants and edge cases:** `/compact` sent as the `-p` prompt works; sequence Pre → internal SubagentStop → SessionStart{compact} → Post (14.7 s). Auto-compaction not provoked: S22 made the mock API report `input_tokens: 195000` on the first call; the second request went out with no compaction (`live/S22_mock_autocompact/mock-requests.jsonl`; `live/S22_mock_autocompact/debug-extras.txt`: `turn 1 end (turns=2 usage in=195050 …)`), and a second streamed user message was folded into the same turn.

**Spec alignment:** spec line 966 `PreCompact{auto}`: field is `trigger`, value `auto` is in the enum; not observed live.

---

## PreModelSwitch / PostModelSwitch

- **Produced by:** Claude Code 2.1.270 (zod `Fle` / `Ble` + `Qz`)
- **Consumed by:** §8 line 922 (identity); §7 `model` column; M1
- **Probe:** `run_probes.py S14`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S14`
- **Status:** partially verified — `source:"command"` live; `picker`, `sdk`, `auto`, `resume` binary only

**Real example** (trimmed; full capture: `live/S14_model_switch/events.jsonl`)

```json
<<EX live/S14_model_switch/events.jsonl|PreModelSwitch|1||140>>
<<EX live/S14_model_switch/events.jsonl|PostModelSwitch|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `from_model` / `to_model` | string | always | `claude-haiku-4-5-20251001` → `claude-sonnet-5` | resolved ids |
| `requested_model` | string or null | always | `sonnet` | the alias typed |
| `source` | enum | always | `command` | Pre: `command,picker,sdk`; Post adds `auto,resume` |
| `context_tokens` | int | always | `1844` | |
| `prompt_cache_warm` | bool | always | `false` | |
| `cache_ttl` | enum | always | `1h` | `5m`/`1h` |
| `estimated_cache_write_usd` | number | always | `0.0074` | |
| `pricing` | enum | always | `catalog` | `configured/catalog/default` |

**Variants and edge cases:** `--resume` with a different `--model` emitted **no** model-switch event (`live/S14b_resume_other_model/events.jsonl`).

**Spec alignment:** aligned (names only in spec).

---

## InstructionsLoaded

- **Produced by:** Claude Code 2.1.270 (zod `Xle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `run_probes.py S01 S03 S12`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S12`
- **Status:** partially verified — `load_reason:"session_start"`, `memory_type:"Project"` live; other values binary only

**Real example** (trimmed; full capture: `live/S03_continue/events.jsonl`)

```json
<<EX live/S03_continue/events.jsonl|InstructionsLoaded|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `file_path` | string | always | `<cwd>/CLAUDE.md` | |
| `memory_type` | enum | always | `Project` | `User/Project/Local/Managed` |
| `load_reason` | enum | always | `session_start` | `session_start/nested_traversal/path_glob_match/include/compact` |
| `globs` / `trigger_file_path` / `parent_file_path` | | never observed | — | |

**Variants and edge cases:** fires before SessionStart; on `--continue` it carried a provisional `session_id` different from the resumed one (example above vs `SessionStart` `8bbcceab…` in the same file).

**Spec alignment:** aligned (not referenced).

---

## ConfigChange

- **Produced by:** Claude Code 2.1.270 (zod `$le`)
- **Consumed by:** not consumed by the spec; relevant to §15 (Shepherd editing `~/.claude/settings.json` under running sessions)
- **Probe:** `run_probes.py S21`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S21`
- **Status:** partially verified — `source:"local_settings"` live; other sources binary only

**Real example** (trimmed; full capture: `live/S21_config_change/events.jsonl`)

```json
<<EX live/S21_config_change/events.jsonl|ConfigChange|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `source` | enum | always | `local_settings` | `user_settings/project_settings/local_settings/policy_settings/skills` |
| `file_path` | string | always | `<cwd>/.claude/settings.local.json` | optional in schema |

**Variants and edge cases:** triggered by an outside process rewriting the file mid-session. A Bash write to a `.claude/settings.local.json` path by the model raised a PermissionRequest even with `--allowedTools Bash` (`live/S13_watch_cwd_config/events.jsonl`).

**Spec alignment:** aligned (not referenced). Implication for §15: a running session observes Shepherd's install/uninstall edits live (debug `Watching for changes in setting files /root/.claude/settings.json, …`).

---

## CwdChanged

- **Produced by:** Claude Code 2.1.270 (zod `Zle`)
- **Consumed by:** §8 line 922 (identity); D22 (cwd → repo binding); M1
- **Probe:** `run_probes.py S13`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S13`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S13_watch_cwd_config/events.jsonl`)

```json
<<EX live/S13_watch_cwd_config/events.jsonl|CwdChanged|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `old_cwd` / `new_cwd` | string | always | `/tmp/shp-hooks-watch-jnn4_1pq` → `…/sub` | |

**Variants and edge cases:** the common `cwd` already shows the new directory on this event (and on the PostToolUse of the `cd` call). The Bash cwd persists: the next `pwd` call printed `…/sub` and emitted no further CwdChanged.

**Spec alignment:** aligned.

---

## FileChanged

- **Produced by:** Claude Code 2.1.270 (zod `ece`)
- **Consumed by:** §8 line 886 and line 923 (`repos_touched`); §7 line 680; D22; §18 line 2330; M1
- **Probe:** `run_probes.py S13 S21` (+ negative control S09 acceptEdits Write). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S13 S21`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S13_watch_cwd_config/events.jsonl`, `live/S21_config_change/events.jsonl`)

```json
<<EX live/S13_watch_cwd_config/events.jsonl|FileChanged|1||140>>
<<EX live/S21_config_change/events.jsonl|FileChanged|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `file_path` | string | always | the watched path | |
| `event` | enum | always | `change`, `unlink` | binary `change/add/unlink`; the re-create in S21 did not emit `add` before exit |

**Variants and edge cases:** FileChanged fires **only for paths a hook registered** via `hookSpecificOutput.watchPaths` (SessionStart/CwdChanged/FileChanged output). S13 debug: `Hook SessionStart (…emit_watchpaths.sh) provided 1 watchPaths` then `FileChanged: change …/watched.txt`. Claude's own `Write` of `./inside.txt` in `acceptEdits` produced no FileChanged (`live/S09_perm_acceptEdits_write_inside/events.jsonl`).

**Spec alignment:**
- spec lines 680 and 886 say `repos_touched` accumulates from `FileChanged`; reality: FileChanged does not report files the agent edits — only hook-declared watch paths (S13, S21, negative control S09). `repos_touched` needs PostToolUse `tool_input.file_path` (Edit/Write) and Bash cwd, or a watch list Shepherd returns from a SessionStart hook.

---

## DirectoryAdded

- **Produced by:** Claude Code 2.1.270 (zod `tce`)
- **Consumed by:** not consumed by the spec; relevant to D22 (multi-repo sessions)
- **Probe:** `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/interactive_probe.py`
- **Status:** partially verified — TUI `/add-dir` (`source:"slash_command"`) live; `register_repo_root` binary only

**Real example** (trimmed; full capture: `live/I01_interactive/events.jsonl`)

```json
<<EX live/I01_interactive/events.jsonl|DirectoryAdded|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `directory` | string | always | the added dir | |
| `source` | enum | always | `slash_command` | binary `slash_command/register_repo_root` |

**Variants and edge cases:** `--add-dir` at launch was not tested for this event.

**Spec alignment:** aligned (not referenced).

---

## Elicitation / ElicitationResult

- **Produced by:** Claude Code 2.1.270 (zod `Kle` / `jle`)
- **Consumed by:** §8 line 917 (needs-you); M1
- **Probe:** `run_probes.py S17` with the stdio MCP server `mcp_elicit.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S17`
- **Status:** partially verified — `form` mode with `-p` auto-cancel live; `url` mode and `accept`/`decline` binary only

**Real example** (trimmed; full capture: `live/S17_elicitation/events.jsonl`; MCP wire log `live/S17_elicitation/mcp-messages.jsonl`)

```json
<<EX live/S17_elicitation/events.jsonl|Elicitation|1||140>>
<<EX live/S17_elicitation/events.jsonl|ElicitationResult|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `mcp_server_name` | string | always | `shpelicit` | matcher value |
| `message` | string | always (Elicitation) | | |
| `mode` | enum | always | `form` | `form/url` |
| `requested_schema` | object | always (Elicitation) | | |
| `url`, `elicitation_id` | string | never observed | — | url mode |
| `action` | enum | always (Result) | `cancel` | `accept/decline/cancel` |
| `content` | object | never observed | — | |

**Variants and edge cases:** in `-p` the client answered `{"action":"cancel"}` within 10 ms and then emitted `Notification{elicitation_response}`; the session never blocked.

**Spec alignment:** spec line 917 treats Elicitation as needs-you; in `-p` it is auto-cancelled immediately, so it is not a blocking state there.

---

## Setup

- **Produced by:** Claude Code 2.1.270 (zod `Mle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `run_probes.py S16`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S16`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `live/S16_setup__maintenance/events.jsonl`)

```json
<<EX live/S16_setup__maintenance/events.jsonl|Setup|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `trigger` | enum | always | `init` (`--init`, `--init-only`), `maintenance` (`--maintenance`) | fires before SessionStart |

**Variants and edge cases:** `--init-only` exits after Setup/SessionStart/SessionEnd without a prompt.

**Spec alignment:** aligned (not referenced).

---

## WorktreeCreate / WorktreeRemove

- **Produced by:** Claude Code 2.1.270 (zod `Jle` / `Qle`)
- **Consumed by:** not consumed by the spec; relevant to D15 (worker worktrees)
- **Probe:** `run_probes.py S15`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S15`
- **Status:** partially verified — WorktreeCreate live; WorktreeRemove binary only

**Real example** (trimmed; full capture: `live/S15_worktree/events.jsonl`)

```json
<<EX live/S15_worktree/events.jsonl|WorktreeCreate|1||140>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `name` | string | always | `shpwt` (from `--worktree shpwt`) | |
| `worktree_path` | string | (WorktreeRemove) not observed | — | |

**Variants and edge cases:** **registering any WorktreeCreate command hook replaces git worktree creation**: the capture hook printed nothing and the launch failed with `Error creating worktree: WorktreeCreate hook failed: hook succeeded but returned no worktree path` (`live/S15_worktree/stderr.txt`, exit 1). A catch-all "subscribe to every event" dispatcher must not register WorktreeCreate.

**Spec alignment:** not referenced; the "all events" framing of §8 line 893 ("one dispatcher, all events") would break `--worktree` if taken literally.

---

## TeammateIdle

- **Produced by:** Claude Code 2.1.270 (zod `Hle`)
- **Consumed by:** not consumed by the spec
- **Probe:** `extract_binary.py` → `binary/hook-input-schemas.txt`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py`
- **Status:** not verifiable here — requires the agent-teams feature; not attempted

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/binary/hook-input-schemas.txt`)

```text
<<RAW binary/hook-input-schemas.txt|Hle=f\(\(\)=>we\(\)\.and\(u\(\{hook_event_name:R\("TeammateIdle"\),teammate_name:o\(\),team_name:o\(\)|200>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `teammate_name` | string | not observed | — | schema |
| `team_name` | string | not observed | — | schema |

**Variants and edge cases:** none observed.

**Spec alignment:** aligned (not referenced).

---

## Enumerations (SessionStart.source, SessionEnd.reason, StopFailure.error, Notification.notification_type)

- **Produced by:** Claude Code 2.1.270 (`binary/enums.json`; error assignment counts `binary/stopfailure-error-assignments.txt`)
- **Consumed by:** §8 lines 937, 951–971, 1205; D21; M2
- **Probe:** `extract_binary.py` + `run_probes.py S04 S05 S06 S07 S08` + `interactive_probe.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/extract_binary.py && python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S07 S08`
- **Status:** partially verified (per value below)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/hooks/binary/enum-sources.txt`)

```text
<<LINES binary/enum-sources.txt|2|5>>
```

**SessionStart.source** (binary enum): `startup` live (S01) · `resume` live (S02 `--resume`, S03 `--continue`) · `fork` live (S04 `--fork-session`) · `compact` live (S05 `/compact`) · `clear` live (S06, I01 `/clear`).

**SessionEnd.reason** (binary enum): `other` live (every `-p` exit) · `clear` live (S06, I01) · `prompt_input_exit` live (I01 `/exit`) · `logout` not verified (would sign out the real account) · `resume` not verified (TUI `/resume` switch not attempted).

**StopFailure.error** (binary enum `o_`, 13 values), with the stimulus that produced each observed value:

| error | assignments in binary | Observed | Stimulus |
|---|---|---|---|
| `authentication_failed` | 10 | yes | mock HTTP 401 `authentication_error`; mock HTTP 403 `permission_error` |
| `oauth_org_not_allowed` | 1 | no | needs a real org policy |
| `account_on_hold` | 1 | no | needs a real account state |
| `verification_required` | 1 | no | — |
| `billing_error` | 1 | yes | mock HTTP 400 "Your credit balance is too low…" |
| `rate_limit` | 10 | yes | mock HTTP 429 |
| `overloaded` | **0** | no | mock HTTP 529 produced `server_error` instead |
| `invalid_request` | 37 | yes | mock HTTP 400 "prompt is too long…" (with `error_details`) |
| `model_not_found` | 2 | yes | **real API** `--model claude-nonexistent-model-shp` (S07); mock HTTP 404 |
| `server_error` | 8 | yes | mock HTTP 500; mock HTTP 529 |
| `unknown` | 4 | yes | mock HTTP 400 `messages: field required` |
| `max_output_tokens` | 2 | yes | mock SSE `stop_reason:"max_tokens"` |
| `cloud_credential_error` | 1 | no | 3P cloud providers only |

**Notification.notification_type** — the binary list `VAr` (14 values): `permission_prompt` live (I01) · `idle_prompt` live (I01) · `auth_success` · `elicitation_dialog` · `agent_needs_input` · `agent_completed` · `elicitation_url_dialog` · `worker_permission_prompt` · `push_notification` · `computer_use_enter` · `computer_use_exit` · `quota_auto_resume_fired` · `quota_auto_resume_stale` · `quota_auto_resume_disabled`. Also emitted but **not** in `VAr`: `elicitation_response` live (S17), `elicitation_complete` (binary literal).

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| (enum values) | string | — | see lists above | mock-API results reflect Claude Code's own error mapping of a real HTTP status/body, not a real outage |

**Variants and edge cases:** the mock runs used an isolated `CLAUDE_CONFIG_DIR`, a fake `ANTHROPIC_API_KEY`, `CLAUDE_CODE_MAX_RETRIES=0`; with retries on, 429/529/5xx would be retried before StopFailure.

**Spec alignment:** see StopFailure (`overloaded` unreachable, plain 400 → `unknown`, two values missing), SessionEnd (`end_reason` → `reason`), SessionStart (`start_reason` → `source`), Notification (value set).

---

## Hooks config schema (`hooks` in settings.json)

- **Produced by:** Claude Code 2.1.270 settings validator (`Rd()`, `Rt`, `Gq`, `A6()`/`kzn()` in `binary/settings-hook-config-schema.txt`)
- **Consumed by:** §8 "Hook installation" (lines 893–907); §15 install/uninstall with `_shepherd_managed` (lines 2230–2233); §6 `install_hooks()`/`uninstall_hooks()`; principle 4; M1, M6
- **Probe:** `run_probes.py R03 R04 R05 S13`. Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py R03 R04 R05`
- **Status:** partially verified — project, local and `--settings` scopes live 2026-09-14; user scope (`~/.claude/settings.json`) not tested (probe safety rule forbids editing it)

**Real example** (trimmed; full captures: `live/S01_startup_tools/settings.json` [accepted], `live/R03_config_pretooluse_broken/doctor.txt`, `live/R03_config_stop_not_a_list/doctor.txt`)

```json
<<RAW live/S01_startup_tools/settings.json|  "PreToolUse": \[\n   \{\n    "hooks": \[\n     \{\n[^\]]*\],\n    "matcher": "\*"\n   \}\n  \]|400>>
```

```text
<<LINES live/R03_config_stop_not_a_list/doctor.txt|2|3>>
<<LINES live/R03_config_pretooluse_broken/doctor.txt|2|5>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `hooks` | object `{<EventName>: Group[]}` | — | | an array here disables every hook in the file (doctor: `"hooks" must be an object …`) |
| `Group.matcher` | string | optional | `"*"`, `"Bash"`, `"startup"` | omitted key accepted and matches all (R03 no_matcher_key fired); `"*"` accepted on events without matchers |
| `Group.hooks` | array of entries | required | | |
| `entry.type` | enum | required | `command` | also `prompt`, `agent`, `http`, `mcp_tool` |
| `entry.command` | string | required for `command` | shell string | runs via `/bin/sh -c` |
| `entry.args` | string[] | optional | not used | exec form, no shell |
| `entry.timeout` | positive number (seconds) | optional | `10`, `15`, `2` | `-5` → entry ignored; default 600 s (`Mp=600000`) |
| `entry.async` | bool | optional | `true` (R02) | runs in background |
| `entry.if`, `shell` (`bash`/`powershell`), `statusMessage`, `once`, `asyncRewake`, `rewakeMessage`, `rewakeSummary`, `cloud` | | optional | not used | schema only |
| `entry._shepherd_managed` (extra key) | any | — | `true` on every probe entry | accepted silently; hooks fired and `claude doctor` reported nothing (R03 extra_keys) |

**Variants and edge cases** (what `-p` did silently; what `claude doctor` then said):
- Invalid JSON in `settings.json`: the whole file ignored; `settings.local.json` next to it still loaded (`Expected object, but received undefined`).
- `hooks.Stop: "not-a-list"`: only that event dropped (`This entry was ignored.`); other hooks in the file fired.
- Unknown event `BogusEvent`: dropped, rest fired.
- Negative `timeout` / unknown `type`: that entry dropped (`entry ignored`), rest fired.
- **A broken `PreToolUse` or `PermissionRequest` entry disables every hook in that file** (doctor: "nothing it sits in is applied until the entry is fixed or removed"; the file's valid UserPromptSubmit probe did not fire, `live/R03_config_pretooluse_broken/events.jsonl`).
- Hooks given only through `--settings <file>` load and fire (R04).
- No validation message appears in `-p` stderr or the debug log for any of these; only `claude doctor` shows them.

**Spec alignment:**
- spec lines 2231–2232 (`"_shepherd_managed": true` on each entry): accepted in project/local/`--settings` scope (R03 extra_keys, all S* runs). Not tested in user scope.
- spec line 2230 (merge into `~/.claude/settings.json`): a user's own malformed PreToolUse/PermissionRequest entry in that file silently disables Shepherd's hooks too (R03 pretooluse_broken); install should validate the merged file with `claude doctor` or the same rules.
- spec line 893 ("one dispatcher, all events"): registering `WorktreeCreate` breaks `--worktree` (see WorktreeCreate).

---

## Hook runtime contract (process, stdin, env, exit codes, stdout, timeout, sync, ancestry)

- **Produced by:** Claude Code 2.1.270 hook runner (`VE()`, `rS()`, `fet()` in `binary/runtime-source-snippets.txt`)
- **Consumed by:** §8 `hookd.py` (lines 895–909: 250 ms UDS, always exit 0); §5.0 (line 312, 0600 socket); principle 4 (line 163); D37; §18 volume risk; M1
- **Probe:** `run_probes.py S01 S07 R01 R02` (+ `capture_env.py`). Re-run: `python3 docs/probes/2026-09-14-schemas/hooks/run_probes.py S01 S07 R01 R02`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `live/S01_startup_tools/env.jsonl` [SessionStart env], `live/R01_exit_codes/stdout.jsonl`, `live/R02_timeout_sync/stdout.jsonl`, `live/R02_timeout_sync/timing.txt`, `live/S01_startup_tools/events.jsonl` [ancestry])

```json
<<ENV live/S01_startup_tools/env.jsonl|1>>
<<RAW live/S01_startup_tools/events.jsonl|"_hook_pid":[0-9]+,"_claude_pid":[0-9]+,"_ancestry":\[\{[^\]]*\]|400>>
<<RAW live/R01_exit_codes/stdout.jsonl|^\{"type":"system","subtype":"hook_response"[^\n]*"exit_code":2[^\n]*$|200>>
<<RAW live/R01_exit_codes/stdout.jsonl|^\{"type":"user"[^\n]*SHP_BLOCKED_BY_HOOK[^\n]*$|200>>
<<RAW live/R02_timeout_sync/stdout.jsonl|^\{"type":"system","subtype":"hook_response"[^\n]*"outcome":"cancelled"[^\n]*$|200>>
```

```text
<<LINES live/R02_timeout_sync/timing.txt|1|5>>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| process | — | always | `claude` → `/bin/sh -c <command>` (dash) → hook | 429/429 captures: parent `sh`, grandparent `claude`. Owning pid = first ancestor with comm `claude` = `$CLAUDE_PID` |
| stdin | bytes | always | payload JSON + `\n`, then EOF; not a tty | open fds 0,1,2 (plus the probe's own directory-listing fd) |
| hook cwd | path | always | session `cwd` | |
| `CLAUDE_PID` | env | always (every env capture: SessionStart, UserPromptSubmit, PreToolUse, Stop, SessionEnd in S01; PreToolUse, Stop in S10) | owning claude pid | |
| `CLAUDE_CODE_SESSION_ID` | env | always | = payload `session_id` | |
| `CLAUDE_PROJECT_DIR` | env | always | launch dir | |
| `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ATTENDED`, `CLAUDE_CODE_CHILD_SESSION` | env | always | `1`, `sdk-cli` (`-p`), `0`, `1` | |
| `CLAUDE_CODE_MESSAGING_SOCKET` / `_TOKEN` | env | sometimes | not on SessionEnd | token value `<redacted>` |
| `CLAUDE_ENV_FILE` | env | SessionStart only | `~/.claude/session-env/<sid>/sessionstart-hook-1.sh` | |
| `CLAUDE_EFFORT` | env | when effort applies | `low` (S10 PreToolUse/Stop) | absent for haiku |
| exit 0 | — | — | success; stdout parsed as JSON if it starts with `{`, else plain text (UserPromptSubmit stdout became model context) | |
| exit 2 | — | — | PreToolUse: call blocked, stderr sent to the model as `tool_result` `is_error:true`, `outcome:"error"` | |
| exit 1 | — | — | non-blocking error (`Stop` exit 1 → `outcome:"error"`, session finished normally) | |
| timeout | seconds | per entry | `timeout: 2` on an 8 s sleep → killed at ~2.1 s (`end` line never written), `exit_code:1`, `outcome:"cancelled"`, tool then ran | default 600 s |
| synchronicity | — | — | blocking: a 3 s PostToolUse hook delayed the next event (PostToolBatch) by 3.0 s; hooks for one event start in parallel (capture and slow hook started 4 ms apart) | `async:true` → backgrounded (debug `Registering async hook … with timeout 600000ms`) |

**Variants and edge cases:**
- **`-p` shutdown kills slow hooks.** StopFailure/SessionEnd hooks still running when the CLI exits are killed (Python capture lost, fork-free bash kept; `live/S07_bad_model/debug-hooklines.txt`).
- Hooks run in never-trusted directories under `-p`; the binary skips all hooks when workspace trust is not accepted in interactive mode (`Skipping … hook execution - workspace trust not accepted`, `binary/runtime-source-snippets.txt` line 12).
- `--include-hook-events` with `--output-format stream-json` emits `hook_started`/`hook_response` system messages (hook name, exit code, stdout, stderr, outcome) — an alternative signal path for `owned` sessions.
- The environment is inherited from the launching process (here `TMUX`, `TERM`, a plugin `PATH` entry leaked from the parent).

**Spec alignment:**
- spec lines 897–907 (`hookd.py` reads stdin, 250 ms UDS write, always exit 0): contract aligned (exit 0 is non-blocking, stdin closes). Timing risk: a Python `hookd` of the shape shown (interpreter start + UDS connect) is exactly what was killed on `-p` StopFailure in S07; the StopFailure/SessionEnd path needs a hook that finishes in a few ms, or a fallback on process exit.
- spec line 163 ("Hooks time out"): the per-entry `timeout` is enforced by Claude Code (R02) — Shepherd's install should set it, since the default is 600 s of blocking.
- Owning-pid discovery: `$CLAUDE_PID` in the hook env equals the `claude` parent of the hook's `sh` (S01 env vs ancestry) — no `/proc` walk needed.
